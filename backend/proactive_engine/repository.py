"""Mongo persistence for proactive suggestions."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from proactive_engine.models import Suggestion, now_iso


class SuggestionRepository:
    def __init__(self, db):
        self.db = db
        self.col = db.proactive_suggestions

    async def ensure_indexes(self) -> None:
        await self.col.create_index("id", unique=True)
        await self.col.create_index([("user_id", 1), ("status", 1), ("score", -1)])
        await self.col.create_index([("user_id", 1), ("dedupe_key", 1), ("status", 1)])
        await self.col.create_index([("user_id", 1), ("goal_id", 1)])
        await self.col.create_index([("user_id", 1), ("expires_at", 1)])
        await self.col.create_index([("user_id", 1), ("type", 1), ("created_at", -1)])

    async def insert(self, s: Suggestion) -> Suggestion:
        await self.col.insert_one(s.model_dump())
        return s

    async def get(self, user_id: str, suggestion_id: str) -> Optional[Suggestion]:
        doc = await self.col.find_one({"id": suggestion_id, "user_id": user_id}, {"_id": 0})
        return Suggestion(**doc) if doc else None

    async def update_fields(
        self, user_id: str, suggestion_id: str, fields: Dict[str, Any],
    ) -> Optional[Suggestion]:
        fields = {**fields, "updated_at": now_iso()}
        await self.col.update_one(
            {"id": suggestion_id, "user_id": user_id},
            {"$set": fields},
        )
        return await self.get(user_id, suggestion_id)

    async def list_for_user(
        self,
        user_id: str,
        *,
        statuses: Optional[List[str]] = None,
        suggestion_type: Optional[str] = None,
        limit: int = 40,
    ) -> List[Suggestion]:
        q: Dict[str, Any] = {"user_id": user_id}
        if statuses:
            q["status"] = {"$in": statuses}
        if suggestion_type:
            q["type"] = suggestion_type
        cur = self.col.find(q, {"_id": 0}).sort([("score", -1), ("created_at", -1)]).limit(limit)
        rows = await cur.to_list(limit)
        return [Suggestion(**r) for r in rows]

    async def active_dedupe_keys(self, user_id: str) -> set:
        cur = self.col.find(
            {
                "user_id": user_id,
                "status": {"$in": ["active", "snoozed", "accepted"]},
                "dismissed": {"$ne": True},
            },
            {"_id": 0, "dedupe_key": 1},
        )
        rows = await cur.to_list(300)
        return {r["dedupe_key"] for r in rows if r.get("dedupe_key")}

    async def count_recent(self, user_id: str, *, since_iso: str) -> int:
        return int(await self.col.count_documents({
            "user_id": user_id,
            "created_at": {"$gte": since_iso},
            "status": {"$in": ["active", "snoozed", "accepted", "dismissed"]},
        }))

    async def has_dedupe_recent(
        self, user_id: str, dedupe_key: str, *, since_iso: str,
    ) -> bool:
        doc = await self.col.find_one({
            "user_id": user_id,
            "dedupe_key": dedupe_key,
            "created_at": {"$gte": since_iso},
            "status": {"$nin": ["expired"]},
        }, {"_id": 1})
        return bool(doc)

    async def search(
        self,
        user_id: str,
        *,
        q: Optional[str] = None,
        suggestion_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 40,
    ) -> List[Suggestion]:
        query: Dict[str, Any] = {"user_id": user_id}
        if suggestion_type:
            query["type"] = suggestion_type
        if status:
            query["status"] = status
        if q:
            query["$or"] = [
                {"title": {"$regex": q, "$options": "i"}},
                {"description": {"$regex": q, "$options": "i"}},
                {"reason": {"$regex": q, "$options": "i"}},
            ]
        cur = self.col.find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
        rows = await cur.to_list(limit)
        return [Suggestion(**r) for r in rows]
