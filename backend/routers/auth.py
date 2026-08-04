"""AUTH router: email, Google/Apple ID-token login, identities, logout."""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from deps import (
    DEMO_EMAILS,
    db,
    get_current_user,
    hash_password,
    make_jwt,
    upsert_user,
    verify_password,
)
from social_auth import SocialAuthService, social_auth_status
from social_auth.store import IdentityStore

from ._seed import prepare_user_decisions

router = APIRouter(prefix="/auth", tags=["auth"])


def _social() -> SocialAuthService:
    return SocialAuthService(db)


# --- Models ----------------------------------------------------------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class GoogleSessionIn(BaseModel):
    session_token: str


class GoogleIdTokenIn(BaseModel):
    id_token: str = Field(..., min_length=20)
    nonce: Optional[str] = None


class AppleIdTokenIn(BaseModel):
    id_token: str = Field(..., min_length=20)
    nonce: Optional[str] = None
    authorization_code: Optional[str] = None
    # First-login Apple profile hints — stored only if identity has empty fields
    # after cryptographic verification of id_token. Never used as proof of identity.
    email: Optional[str] = None
    full_name: Optional[dict[str, Any]] = None


class UserOut(BaseModel):
    user_id: str
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
    provider: str


class AuthOut(BaseModel):
    token: str
    user: UserOut


def user_to_out(u: dict) -> UserOut:
    return UserOut(
        user_id=u["user_id"],
        email=u["email"],
        name=u.get("name"),
        picture=u.get("picture"),
        provider=u.get("provider", "email"),
    )


async def _ensure_password_identity(user: dict) -> None:
    store = IdentityStore(db)
    if await store.find_password_for_user(user["user_id"]):
        return
    if not user.get("password_hash"):
        return
    await store.create(
        provider="password",
        provider_subject=user["user_id"],
        user_id=user["user_id"],
        email=user.get("email"),
        email_verified=True,
        display_name=user.get("name"),
        avatar_url=user.get("picture"),
    )


async def _auth_out(user: dict) -> AuthOut:
    await prepare_user_decisions(user["user_id"], is_demo=user["email"] in DEMO_EMAILS)
    return AuthOut(token=make_jwt(user["user_id"]), user=user_to_out(user))


# --- Email -----------------------------------------------------------
@router.post("/register", response_model=AuthOut)
async def register(body: RegisterIn):
    existing = await db.users.find_one({"email": body.email}, {"_id": 0})
    if existing and existing.get("password_hash"):
        raise HTTPException(status_code=409, detail="Email già registrata")
    user = await upsert_user(
        email=body.email,
        name=body.name,
        picture=None,
        provider="email",
        password_hash=hash_password(body.password),
    )
    await _ensure_password_identity(user)
    return await _auth_out(user)


@router.post("/login", response_model=AuthOut)
async def login(body: LoginIn):
    user = await db.users.find_one({"email": body.email}, {"_id": 0})
    if not user or not user.get("password_hash"):
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    await _ensure_password_identity(user)
    store = IdentityStore(db)
    pwd = await store.find_password_for_user(user["user_id"])
    if pwd:
        await store.touch_login(pwd["id"])
    return await _auth_out(user)


# --- Legacy Emergent (kept, gated) -----------------------------------
@router.post("/google-session", response_model=AuthOut)
async def google_session(body: GoogleSessionIn):
    """Legacy Emergent Google bridge — disabled unless EMERGENT_GOOGLE_AUTH=1."""
    if os.environ.get("EMERGENT_GOOGLE_AUTH", "0").lower() not in ("1", "true", "yes"):
        raise HTTPException(
            status_code=503,
            detail=(
                "Integrazione non configurata in questo ambiente. "
                "Usa POST /api/auth/google con ID token, oppure email/password."
            ),
        )
    async with httpx.AsyncClient(timeout=15) as h:
        r = await h.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": body.session_token},
        )
        if r.status_code != 200:
            raise HTTPException(status_code=401, detail="Google auth failed")
        data = r.json()
    user = await upsert_user(
        email=data["email"],
        name=data.get("name"),
        picture=data.get("picture"),
        provider="google",
    )
    return await _auth_out(user)


# --- First-party Google / Apple --------------------------------------
@router.get("/providers")
async def providers_status():
    """Public: which social providers are configured (no secrets)."""
    return social_auth_status()


@router.post("/google", response_model=AuthOut)
async def google_login(body: GoogleIdTokenIn):
    svc = _social()
    verified = svc.verify_google(body.id_token, nonce=body.nonce)
    user = await svc.login_with_verified(verified)
    return await _auth_out(user)


@router.post("/apple", response_model=AuthOut)
async def apple_login(body: AppleIdTokenIn):
    svc = _social()
    verified = svc.verify_apple(body.id_token, nonce=body.nonce)
    full = body.full_name or {}
    user = await svc.login_with_verified(
        verified,
        first_name=full.get("givenName") or full.get("firstName"),
        last_name=full.get("familyName") or full.get("lastName"),
        apple_email_hint=body.email,
    )
    return await _auth_out(user)


@router.post("/link/google")
async def link_google(body: GoogleIdTokenIn, user=Depends(get_current_user)):
    svc = _social()
    verified = svc.verify_google(body.id_token, nonce=body.nonce)
    ident = await svc.link_with_verified(user, verified)
    return {"ok": True, "provider": "google", "identity": {
        "id": ident.get("id"),
        "email": ident.get("email"),
    }}


@router.post("/link/apple")
async def link_apple(body: AppleIdTokenIn, user=Depends(get_current_user)):
    svc = _social()
    verified = svc.verify_apple(body.id_token, nonce=body.nonce)
    ident = await svc.link_with_verified(user, verified)
    return {"ok": True, "provider": "apple", "identity": {
        "id": ident.get("id"),
        "email": ident.get("email"),
    }}


@router.delete("/link/{provider}")
async def unlink_provider(provider: str, user=Depends(get_current_user)):
    svc = _social()
    return await svc.unlink(user, provider.lower().strip())


@router.get("/identities")
async def list_identities(user=Depends(get_current_user)):
    return await _social().list_providers_for_user(user)


@router.get("/me", response_model=UserOut)
async def me(user=Depends(get_current_user)):
    return user_to_out(user)


@router.post("/logout")
async def logout(user=Depends(get_current_user)):
    return {"ok": True}
