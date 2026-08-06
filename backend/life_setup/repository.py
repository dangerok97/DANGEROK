"""Mongo persistence for Life Profile + Life Setup sessions."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from life_setup.models import LifeProfile, LifeSetupSession, now_iso


class LifeSetupRepository:
    def __init__(self, db):
        self.db = db

    @property
    def sessions(self):
        return self.db.life_setup_sessions

    @property
    def profiles(self):
        return self.db.life_profiles

    async def ensure_indexes(self) -> None:
        await self.sessions.create_index("id", unique=True)
        await self.sessions.create_index([("user_id", 1), ("updated_at", -1)])
        await self.sessions.create_index([("user_id", 1), ("status", 1)])
        await self.profiles.create_index("user_id", unique=True)
        await self.profiles.create_index([("user_id", 1), ("updated_at", -1)])

    async def get_session(self, user_id: str, session_id: str) -> Optional[LifeSetupSession]:
        doc = await self.sessions.find_one({"user_id": user_id, "id": session_id}, {"_id": 0})
        return LifeSetupSession.model_validate(doc) if doc else None

    async def latest_session(self, user_id: str) -> Optional[LifeSetupSession]:
        doc = await self.sessions.find_one(
            {"user_id": user_id},
            {"_id": 0},
            sort=[("updated_at", -1)],
        )
        return LifeSetupSession.model_validate(doc) if doc else None

    async def insert_session(self, sess: LifeSetupSession) -> None:
        await self.sessions.insert_one(sess.model_dump())

    async def save_session(self, sess: LifeSetupSession) -> None:
        sess.touch()
        await self.sessions.update_one(
            {"user_id": sess.user_id, "id": sess.id},
            {"$set": sess.model_dump()},
            upsert=True,
        )

    async def get_profile(self, user_id: str) -> Optional[LifeProfile]:
        doc = await self.profiles.find_one({"user_id": user_id}, {"_id": 0})
        return LifeProfile.model_validate(doc) if doc else None

    async def save_profile(self, profile: LifeProfile) -> None:
        profile.updated_at = now_iso()
        await self.profiles.update_one(
            {"user_id": profile.user_id},
            {"$set": profile.model_dump()},
            upsert=True,
        )

    async def delete_profile(self, user_id: str) -> bool:
        """User-initiated delete — never AI."""
        res = await self.profiles.delete_one({"user_id": user_id})
        return res.deleted_count > 0

    async def delete_domain(self, user_id: str, domain: str) -> Optional[LifeProfile]:
        profile = await self.get_profile(user_id)
        if not profile or domain not in profile.domains:
            return profile
        del profile.domains[domain]
        await self.save_profile(profile)
        return profile
