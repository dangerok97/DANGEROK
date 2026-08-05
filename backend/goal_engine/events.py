"""Internal Goal Engine events — persist to goal_events (no UI)."""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from goal_engine.models import now_iso

logger = logging.getLogger("ora.goal_engine.events")

EVENT_CREATED = "GoalCreated"
EVENT_UPDATED = "GoalUpdated"
EVENT_COMPLETED = "GoalCompleted"
EVENT_CANCELLED = "GoalCancelled"
EVENT_MERGED = "GoalMerged"
EVENT_ARCHIVED = "GoalArchived"


class GoalEventBus:
    def __init__(self, db):
        self.db = db
        self.col = db.goal_events

    async def ensure_indexes(self) -> None:
        await self.col.create_index("id", unique=True)
        await self.col.create_index([("user_id", 1), ("goal_id", 1), ("created_at", -1)])
        await self.col.create_index([("user_id", 1), ("type", 1), ("created_at", -1)])

    async def emit(
        self,
        *,
        user_id: str,
        goal_id: str,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        doc = {
            "id": f"gev_{uuid.uuid4().hex[:14]}",
            "user_id": user_id,
            "goal_id": goal_id,
            "type": event_type,
            "payload": payload or {},
            "created_at": now_iso(),
        }
        try:
            await self.col.insert_one(doc)
        except Exception:
            logger.info("goal event persist soft-fail: %s", event_type, exc_info=True)
        # Drop Mongo _id from return
        doc.pop("_id", None)
        return doc
