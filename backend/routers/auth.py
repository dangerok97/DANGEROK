"""AUTH router: register, login, google-session, me, logout."""
from __future__ import annotations

from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from deps import (
    db,
    DEMO_EMAILS,
    get_current_user,
    hash_password,
    make_jwt,
    upsert_user,
    verify_password,
)

from ._seed import prepare_user_decisions

router = APIRouter(prefix="/auth", tags=["auth"])


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


# --- Routes ----------------------------------------------------------
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
    await prepare_user_decisions(user["user_id"], is_demo=user["email"] in DEMO_EMAILS)
    return AuthOut(token=make_jwt(user["user_id"]), user=user_to_out(user))


@router.post("/login", response_model=AuthOut)
async def login(body: LoginIn):
    user = await db.users.find_one({"email": body.email}, {"_id": 0})
    if not user or not user.get("password_hash"):
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    await prepare_user_decisions(user["user_id"], is_demo=user["email"] in DEMO_EMAILS)
    return AuthOut(token=make_jwt(user["user_id"]), user=user_to_out(user))


@router.post("/google-session", response_model=AuthOut)
async def google_session(body: GoogleSessionIn):
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
    await prepare_user_decisions(user["user_id"], is_demo=user["email"] in DEMO_EMAILS)
    return AuthOut(token=make_jwt(user["user_id"]), user=user_to_out(user))


@router.get("/me", response_model=UserOut)
async def me(user=Depends(get_current_user)):
    return user_to_out(user)


@router.post("/logout")
async def logout(user=Depends(get_current_user)):
    return {"ok": True}
