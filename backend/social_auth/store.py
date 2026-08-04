"""Mongo persistence for user_identities."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return f"ident_{uuid.uuid4().hex[:16]}"


class IdentityStore:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.col = db.user_identities

    async def find_by_provider_subject(self, provider: str, subject: str) -> Optional[dict]:
        return await self.col.find_one(
            {"provider": provider, "provider_subject": subject},
            {"_id": 0},
        )

    async def list_for_user(self, user_id: str) -> list[dict]:
        cur = self.col.find({"user_id": user_id}, {"_id": 0}).sort("created_at", 1)
        return await cur.to_list(100)

    async def count_for_user(self, user_id: str) -> int:
        return int(await self.col.count_documents({"user_id": user_id}))

    async def find_password_for_user(self, user_id: str) -> Optional[dict]:
        return await self.col.find_one(
            {"user_id": user_id, "provider": "password"},
            {"_id": 0},
        )

    async def create(
        self,
        *,
        provider: str,
        provider_subject: str,
        user_id: str,
        email: Optional[str],
        email_verified: bool,
        display_name: Optional[str],
        avatar_url: Optional[str],
    ) -> dict:
        now = _now()
        doc = {
            "id": _new_id(),
            "provider": provider,
            "provider_subject": provider_subject,
            "user_id": user_id,
            "email": email,
            "email_verified": bool(email_verified),
            "display_name": display_name,
            "avatar_url": avatar_url,
            "created_at": now,
            "updated_at": now,
            "last_login_at": now,
        }
        await self.col.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def touch_login(self, identity_id: str, *, patch: Optional[dict[str, Any]] = None) -> None:
        updates: dict[str, Any] = {"last_login_at": _now(), "updated_at": _now()}
        if patch:
            updates.update(patch)
        await self.col.update_one({"id": identity_id}, {"$set": updates})

    async def delete_for_user_provider(self, user_id: str, provider: str) -> bool:
        res = await self.col.delete_one({"user_id": user_id, "provider": provider})
        return res.deleted_count > 0

    async def get_for_user_provider(self, user_id: str, provider: str) -> Optional[dict]:
        return await self.col.find_one(
            {"user_id": user_id, "provider": provider},
            {"_id": 0},
        )
