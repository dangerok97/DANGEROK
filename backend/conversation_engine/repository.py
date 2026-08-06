"""Mongo persistence for conversation_sessions."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from conversation_engine.models import ConversationSession, now_iso


class ConversationRepository:
    def __init__(self, db):
        self.db = db
        self.col = db.conversation_sessions

    async def ensure_indexes(self) -> None:
        await self.col.create_index("id", unique=True)
        await self.col.create_index("resume_token", unique=True)
        await self.col.create_index([("user_id", 1), ("status", 1), ("updated_at", -1)])
        await self.col.create_index([("user_id", 1), ("origin", 1), ("updated_at", -1)])
        await self.col.create_index([("user_id", 1), ("action_session_id", 1)])
        await self.col.create_index([("user_id", 1), ("goal_id", 1)])

    async def insert(self, session: ConversationSession) -> ConversationSession:
        await self.col.insert_one(session.model_dump())
        return session

    async def replace(self, session: ConversationSession) -> ConversationSession:
        session.touch()
        await self.col.replace_one({"id": session.id, "user_id": session.user_id}, session.model_dump())
        return session

    async def get(self, user_id: str, session_id: str) -> Optional[ConversationSession]:
        doc = await self.col.find_one({"id": session_id, "user_id": user_id}, {"_id": 0})
        return ConversationSession(**doc) if doc else None

    async def get_by_resume_token(self, user_id: str, token: str) -> Optional[ConversationSession]:
        doc = await self.col.find_one(
            {"resume_token": token, "user_id": user_id},
            {"_id": 0},
        )
        return ConversationSession(**doc) if doc else None

    async def list_active(
        self,
        user_id: str,
        *,
        statuses: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[ConversationSession]:
        statuses = statuses or ["active", "waiting_user", "running_action", "paused"]
        cur = (
            self.col.find(
                {"user_id": user_id, "status": {"$in": statuses}},
                {"_id": 0},
            )
            .sort("updated_at", -1)
            .limit(limit)
        )
        docs = await cur.to_list(limit)
        return [ConversationSession(**d) for d in docs]

    async def find_resumable_for_suggestion(
        self, user_id: str, suggestion_id: str,
    ) -> Optional[ConversationSession]:
        doc = await self.col.find_one(
            {
                "user_id": user_id,
                "suggestion_id": suggestion_id,
                "status": {"$in": ["active", "waiting_user", "running_action", "paused"]},
            },
            {"_id": 0},
        )
        return ConversationSession(**doc) if doc else None

    async def update_fields(self, user_id: str, session_id: str, fields: Dict[str, Any]) -> None:
        fields = {**fields, "updated_at": now_iso()}
        await self.col.update_one(
            {"id": session_id, "user_id": user_id},
            {"$set": fields},
        )
