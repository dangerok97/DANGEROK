"""Mongo persistence for the `goals` collection."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from goal_engine.goal_types import ACTIVE_LIKE
from goal_engine.models import Goal, now_iso

logger = logging.getLogger("ora.goal_engine.repository")


class GoalRepository:
    def __init__(self, db):
        self.db = db
        self.col = db.goals

    async def ensure_indexes(self) -> None:
        """Non-destructive indexes for goals."""
        await self.col.create_index("id", unique=True)
        await self.col.create_index([("user_id", 1), ("status", 1), ("updated_at", -1)])
        await self.col.create_index([("user_id", 1), ("goal_type", 1)])
        await self.col.create_index(
            [("user_id", 1), ("idempotency_key", 1)],
            unique=True,
            sparse=True,
            name="uniq_user_goal_idempotency",
        )
        await self.col.create_index([("user_id", 1), ("study_plan_id", 1)], sparse=True)
        await self.col.create_index([("user_id", 1), ("travel_project_id", 1)], sparse=True)
        await self.col.create_index([("user_id", 1), ("project_id", 1)], sparse=True)
        await self.col.create_index([("user_id", 1), ("brain_node_id", 1)], sparse=True)
        await self.col.create_index([("user_id", 1), ("source_action_session_id", 1)], sparse=True)

    async def get(self, user_id: str, goal_id: str) -> Optional[Goal]:
        doc = await self.col.find_one({"id": goal_id, "user_id": user_id}, {"_id": 0})
        return Goal(**doc) if doc else None

    async def find_by_idempotency(self, user_id: str, key: str) -> Optional[Goal]:
        if not key:
            return None
        doc = await self.col.find_one(
            {"user_id": user_id, "idempotency_key": key},
            {"_id": 0},
        )
        return Goal(**doc) if doc else None

    async def find_by_study_plan(self, user_id: str, plan_id: str) -> Optional[Goal]:
        if not plan_id:
            return None
        doc = await self.col.find_one(
            {"user_id": user_id, "study_plan_id": plan_id, "status": {"$in": list(ACTIVE_LIKE)}},
            {"_id": 0},
        )
        return Goal(**doc) if doc else None

    async def find_by_travel_project(self, user_id: str, project_id: str) -> Optional[Goal]:
        if not project_id:
            return None
        doc = await self.col.find_one(
            {
                "user_id": user_id,
                "travel_project_id": project_id,
                "status": {"$in": list(ACTIVE_LIKE)},
            },
            {"_id": 0},
        )
        return Goal(**doc) if doc else None

    async def list_active(self, user_id: str, *, limit: int = 80) -> List[Goal]:
        docs = await self.col.find(
            {"user_id": user_id, "status": {"$in": list(ACTIVE_LIKE)}},
            {"_id": 0},
        ).sort("updated_at", -1).to_list(limit)
        return [Goal(**d) for d in docs]

    async def search(
        self,
        user_id: str,
        *,
        q: Optional[str] = None,
        goal_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 40,
    ) -> List[Goal]:
        filt: Dict[str, Any] = {"user_id": user_id}
        if goal_type:
            filt["goal_type"] = goal_type
        if status:
            filt["status"] = status
        if q and q.strip():
            # Case-insensitive substring on title/description
            import re
            rx = re.compile(re.escape(q.strip()), re.IGNORECASE)
            filt["$or"] = [{"title": rx}, {"description": rx}, {"desired_outcome": rx}]
        docs = await self.col.find(filt, {"_id": 0}).sort("updated_at", -1).to_list(max(1, min(limit, 100)))
        return [Goal(**d) for d in docs]

    async def upsert(self, goal: Goal) -> Goal:
        goal.updated_at = now_iso()
        await self.col.update_one(
            {"id": goal.id, "user_id": goal.user_id},
            {"$set": goal.model_dump()},
            upsert=True,
        )
        return goal

    async def delete(self, user_id: str, goal_id: str, *, soft: bool = True) -> bool:
        if soft:
            res = await self.col.update_one(
                {"id": goal_id, "user_id": user_id},
                {"$set": {
                    "status": "cancelled",
                    "cancelled_at": now_iso(),
                    "updated_at": now_iso(),
                }},
            )
            return res.matched_count > 0
        res = await self.col.delete_one({"id": goal_id, "user_id": user_id})
        return res.deleted_count > 0

    async def timeline(self, user_id: str, goal_id: str, *, limit: int = 50) -> List[Dict[str, Any]]:
        """Events for a goal (from goal_events collection)."""
        return await self.db.goal_events.find(
            {"user_id": user_id, "goal_id": goal_id},
            {"_id": 0},
        ).sort("created_at", -1).to_list(limit)
