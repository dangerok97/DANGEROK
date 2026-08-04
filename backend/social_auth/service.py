"""Unified social login / link / unlink against ORA users + identities."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from .apple import AppleTokenError, verify_apple_id_token
from .google import GoogleTokenError, verify_google_id_token
from .models import VerifiedIdentity, identity_public
from .store import IdentityStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SocialAuthService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.identities = IdentityStore(db)

    # --- token verify wrappers (testable via _claims) -----------------
    def verify_google(
        self,
        id_token: str,
        *,
        nonce: Optional[str] = None,
        _claims: Optional[dict] = None,
    ) -> VerifiedIdentity:
        try:
            return verify_google_id_token(id_token, expected_nonce=nonce, _claims=_claims)
        except GoogleTokenError as e:
            status = 503 if e.code == "not_configured" else 401
            raise HTTPException(status_code=status, detail=e.message) from e

    def verify_apple(
        self,
        id_token: str,
        *,
        nonce: Optional[str] = None,
        _claims: Optional[dict] = None,
    ) -> VerifiedIdentity:
        try:
            return verify_apple_id_token(id_token, expected_nonce=nonce, _claims=_claims)
        except AppleTokenError as e:
            status = 503 if e.code == "not_configured" else 401
            raise HTTPException(status_code=status, detail=e.message) from e

    # --- core resolve ------------------------------------------------
    async def login_with_verified(
        self,
        verified: VerifiedIdentity,
        *,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        apple_email_hint: Optional[str] = None,
    ) -> dict:
        """Return user dict for JWT issuance. Never trusts hints without verified token."""
        existing_ident = await self.identities.find_by_provider_subject(
            verified.provider, verified.subject
        )
        if existing_ident:
            user = await self.db.users.find_one({"user_id": existing_ident["user_id"]}, {"_id": 0})
            if not user:
                raise HTTPException(status_code=401, detail="Identità orfana")
            patch = self._safe_identity_patch(existing_ident, verified, first_name, last_name, apple_email_hint)
            await self.identities.touch_login(existing_ident["id"], patch=patch or None)
            await self._touch_user_profile(user, verified, first_name, last_name)
            return user

        # New identity — resolve or create user
        display = verified.display_name or self._compose_name(first_name, last_name)
        user = await self._resolve_user_for_new_identity(verified, display_name=display)
        email = verified.email or (
            apple_email_hint if verified.provider == "apple" and apple_email_hint else None
        )
        # Never use apple_email_hint to merge accounts; only store if creating new identity
        await self.identities.create(
            provider=verified.provider,
            provider_subject=verified.subject,
            user_id=user["user_id"],
            email=email,
            email_verified=verified.email_verified,
            display_name=display,
            avatar_url=verified.avatar_url,
        )
        # Fill name on brand-new or sparse profiles (Apple first consent)
        if display and not user.get("name"):
            await self.db.users.update_one(
                {"user_id": user["user_id"]},
                {"$set": {"name": display}},
            )
            user["name"] = display
        await self._ensure_user_provider_flag(user["user_id"], verified.provider)
        return user

    async def link_with_verified(self, user: dict, verified: VerifiedIdentity) -> dict:
        uid = user["user_id"]
        existing = await self.identities.find_by_provider_subject(verified.provider, verified.subject)
        if existing:
            if existing["user_id"] != uid:
                raise HTTPException(
                    status_code=409,
                    detail="Questa identità è già collegata a un altro account ORA",
                )
            await self.identities.touch_login(existing["id"])
            return existing

        same_provider = await self.identities.get_for_user_provider(uid, verified.provider)
        if same_provider:
            raise HTTPException(
                status_code=409,
                detail=f"Hai già un account {verified.provider} collegato",
            )

        # Optional: block linking if verified email belongs to another user
        if verified.email and verified.email_verified:
            other = await self.db.users.find_one(
                {"email": verified.email, "user_id": {"$ne": uid}},
                {"_id": 0, "user_id": 1},
            )
            if other:
                raise HTTPException(
                    status_code=409,
                    detail="Email del provider già usata da un altro account ORA",
                )

        return await self.identities.create(
            provider=verified.provider,
            provider_subject=verified.subject,
            user_id=uid,
            email=verified.email,
            email_verified=verified.email_verified,
            display_name=verified.display_name or user.get("name"),
            avatar_url=verified.avatar_url or user.get("picture"),
        )

    async def unlink(self, user: dict, provider: str) -> dict[str, Any]:
        if provider not in ("google", "apple", "password"):
            raise HTTPException(status_code=400, detail="Provider non valido")
        if provider == "password":
            raise HTTPException(
                status_code=400,
                detail="Per rimuovere la password usa il flusso cambio credenziali (non implementato)",
            )
        linked = await self.identities.list_for_user(user["user_id"])
        if not any(i.get("provider") == provider for i in linked):
            raise HTTPException(status_code=404, detail="Provider non collegato")
        if len(linked) <= 1:
            raise HTTPException(
                status_code=400,
                detail="Non puoi scollegare l'unico metodo di accesso. Aggiungi prima email o un altro provider.",
            )
        # Also refuse if only this social + no password hash
        others = [i for i in linked if i.get("provider") != provider]
        has_password = bool(user.get("password_hash")) or any(
            i.get("provider") == "password" for i in linked
        )
        if not others and not has_password:
            raise HTTPException(
                status_code=400,
                detail="Non puoi scollegare l'unico metodo di accesso.",
            )
        if len(others) == 0 and not has_password:
            raise HTTPException(status_code=400, detail="Non puoi scollegare l'unico metodo di accesso.")

        # If after unlink there would be zero identities and no password — block
        remaining = len(linked) - 1
        if remaining < 1 and not has_password:
            raise HTTPException(status_code=400, detail="Non puoi scollegare l'unico metodo di accesso.")

        ok = await self.identities.delete_for_user_provider(user["user_id"], provider)
        if not ok:
            raise HTTPException(status_code=404, detail="Provider non collegato")
        # Update legacy providers array
        provs = set(user.get("providers") or [])
        provs.discard(provider)
        await self.db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"providers": list(provs)}},
        )
        return {"ok": True, "provider": provider}

    async def list_providers_for_user(self, user: dict) -> dict[str, Any]:
        idents = await self.identities.list_for_user(user["user_id"])
        by = {i["provider"]: i for i in idents}
        has_password = bool(user.get("password_hash")) or "password" in by
        return {
            "user_id": user["user_id"],
            "email": user.get("email"),
            "methods": {
                "password": {
                    "linked": has_password,
                    "email": user.get("email") if has_password else None,
                },
                "google": {
                    "linked": "google" in by,
                    "email": (by.get("google") or {}).get("email"),
                },
                "apple": {
                    "linked": "apple" in by,
                    "email": (by.get("apple") or {}).get("email"),
                },
            },
            "identities": [identity_public(i) for i in idents],
            "can_unlink": {
                "google": "google" in by and (len(idents) > 1 or has_password),
                "apple": "apple" in by and (len(idents) > 1 or has_password),
            },
        }

    # --- helpers -----------------------------------------------------
    async def _resolve_user_for_new_identity(
        self,
        verified: VerifiedIdentity,
        *,
        display_name: Optional[str] = None,
    ) -> dict:
        name = display_name or verified.display_name
        email = verified.email
        if not email:
            # Apple may omit email after first consent — create opaque placeholder user email
            synthetic = f"{verified.provider}_{verified.subject[:16]}@identity.ora.local"
            return await self._create_user(
                email=synthetic,
                name=name,
                picture=verified.avatar_url,
                provider=verified.provider,
            )

        existing = await self.db.users.find_one({"email": email}, {"_id": 0})
        if not existing:
            return await self._create_user(
                email=email,
                name=name,
                picture=verified.avatar_url,
                provider=verified.provider,
            )

        # CASE C — password account with same email: do not auto-link
        if existing.get("password_hash"):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Esiste già un account ORA con questa email. "
                    "Accedi con email e password, poi collega il provider da Impostazioni."
                ),
            )

        # Legacy Emergent Google-only: allow claiming once if email verified
        legacy_google = (
            verified.provider == "google"
            and verified.email_verified
            and not existing.get("password_hash")
            and (
                existing.get("provider") == "google"
                or "google" in (existing.get("providers") or [])
            )
        )
        if legacy_google:
            # Ensure no other google identity already on this user
            already = await self.identities.get_for_user_provider(existing["user_id"], "google")
            if already:
                raise HTTPException(
                    status_code=409,
                    detail="Conflitto identità Google. Contatta il supporto.",
                )
            return existing

        # Same email, no password, different provider (e.g. Apple vs Google) — do not merge
        raise HTTPException(
            status_code=409,
            detail=(
                "Email già associata a un altro metodo di accesso. "
                "Accedi con il metodo esistente e collega il nuovo provider da Impostazioni."
            ),
        )

    async def _create_user(
        self,
        *,
        email: str,
        name: Optional[str],
        picture: Optional[str],
        provider: str,
    ) -> dict:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        doc = {
            "user_id": user_id,
            "email": email,
            "name": name,
            "picture": picture,
            "provider": provider,
            "providers": [provider],
            "password_hash": None,
            "created_at": _now(),
        }
        await self.db.users.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def _ensure_user_provider_flag(self, user_id: str, provider: str) -> None:
        user = await self.db.users.find_one({"user_id": user_id}, {"_id": 0})
        if not user:
            return
        provs = set(user.get("providers") or [user.get("provider") or provider])
        provs.add(provider)
        await self.db.users.update_one(
            {"user_id": user_id},
            {"$set": {"providers": list(provs), "provider": user.get("provider") or provider}},
        )

    async def _touch_user_profile(
        self,
        user: dict,
        verified: VerifiedIdentity,
        first_name: Optional[str],
        last_name: Optional[str],
    ) -> None:
        updates: dict[str, Any] = {}
        name = verified.display_name or self._compose_name(first_name, last_name)
        if name and not user.get("name"):
            updates["name"] = name
        if verified.avatar_url and not user.get("picture"):
            updates["picture"] = verified.avatar_url
        # Never overwrite real email with null; never replace with synthetic if real exists
        if updates:
            await self.db.users.update_one({"user_id": user["user_id"]}, {"$set": updates})
            user.update(updates)

    def _safe_identity_patch(
        self,
        existing: dict,
        verified: VerifiedIdentity,
        first_name: Optional[str],
        last_name: Optional[str],
        apple_email_hint: Optional[str],
    ) -> dict[str, Any]:
        """Apple: do not overwrite stored name/email with null on subsequent logins."""
        patch: dict[str, Any] = {}
        if verified.email and not existing.get("email"):
            patch["email"] = verified.email
        if verified.provider == "apple" and apple_email_hint and not existing.get("email"):
            patch["email"] = apple_email_hint
        name = verified.display_name or self._compose_name(first_name, last_name)
        if name and not existing.get("display_name"):
            patch["display_name"] = name
        if verified.avatar_url and not existing.get("avatar_url"):
            patch["avatar_url"] = verified.avatar_url
        if verified.email_verified and not existing.get("email_verified"):
            patch["email_verified"] = True
        return patch

    @staticmethod
    def _compose_name(first: Optional[str], last: Optional[str]) -> Optional[str]:
        parts = [p for p in (first, last) if p and str(p).strip()]
        return " ".join(parts) if parts else None
