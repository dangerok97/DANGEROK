"""Mongo persistence for user-owned contextual situations."""

from __future__ import annotations

from typing import List, Optional

from situations.models import SituationState


class SituationRepository:
    COLLECTION = "situations"

    def __init__(self, db):
        self.db = db
        self.col = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self.col.create_index([("user_id", 1), ("id", 1)], unique=True)
        await self.col.create_index([("user_id", 1), ("status", 1), ("updated_at", -1)])
        await self.col.create_index(
            [("user_id", 1), ("session_id", 1), ("updated_at", -1)]
        )
        await self.col.create_index([("user_id", 1), ("linked_plan_id", 1)])

    async def insert(self, situation: SituationState) -> None:
        await self.col.insert_one(situation.model_dump())

    async def get(self, user_id: str, situation_id: str) -> Optional[SituationState]:
        doc = await self.col.find_one(
            {"user_id": user_id, "id": situation_id}, {"_id": 0}
        )
        return SituationState.model_validate(doc) if doc else None

    async def get_by_epoch(
        self, user_id: str, reasoning_epoch: str
    ) -> Optional[SituationState]:
        doc = await self.col.find_one(
            {"user_id": user_id, "applied_epochs": reasoning_epoch}, {"_id": 0}
        )
        return SituationState.model_validate(doc) if doc else None

    async def save(self, situation: SituationState, *, previous_revision: int) -> bool:
        result = await self.col.update_one(
            {
                "user_id": situation.user_id,
                "id": situation.id,
                "revision": previous_revision,
            },
            {"$set": situation.model_dump()},
        )
        return bool(getattr(result, "modified_count", 0))

    async def list_recent(
        self, user_id: str, *, session_id: Optional[str] = None, limit: int = 5
    ) -> List[SituationState]:
        query = {"user_id": user_id, "status": {"$in": ["active", "changed"]}}
        if session_id:
            query["session_id"] = session_id
        cur = self.col.find(query, {"_id": 0}).sort("updated_at", -1).limit(limit)
        docs = await cur.to_list(limit)
        return [SituationState.model_validate(d) for d in docs]
