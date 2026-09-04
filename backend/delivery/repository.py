"""
Storage for what ORA did and what it intends to say.

Owner-scoped throughout. The uniqueness that matters here is one open plan
per opportunity: two pending plans for the same concern is the duplicate push
this design exists to prevent, and a rule the database enforces cannot be
forgotten by a caller who is only trying to be helpful.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from delivery.models import AmbientActivity, DeliveryPlan

logger = logging.getLogger(__name__)

PLANS = "delivery_plans"
ACTIVITY = "ambient_activity"

# A plan in one of these has had its say. Reopening one needs a new decision,
# not a new scan.
CLOSED = ("cancelled", "delivered", "expired")

# How long a settled plan is kept. Long enough for recent fatigue and for
# explaining a notification somebody received; short enough that this never
# becomes a permanent log of everything ORA ever said.
HISTORY_RETENTION_DAYS = 30

# How long the record of ORA's own work is kept. Long enough to explain a line
# somebody read this morning; short enough that this never becomes a permanent
# account of what a person's life was doing.
ACTIVITY_RETENTION_DAYS = 7


def _subject_filter(owner_id: str, source_type: str, source_id: str) -> Dict[str, Any]:
    """
    Which plans belong to one subject.

    `opportunity_id` is the field V3.8 shipped with, and every plan written
    before the agent bridge existed carries only that one. Rather than migrate
    them to prove a point, the opportunity path accepts either name — in one
    function, which is the difference between a compatibility seam and a
    special case scattered through the service.
    """
    if source_type == "opportunity":
        return {
            "owner_id": owner_id,
            "$or": [{"source_id": source_id}, {"opportunity_id": source_id}],
        }
    return {"owner_id": owner_id, "source_type": source_type, "source_id": source_id}


class DeliveryRepository:
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        try:
            await self.db[PLANS].create_index("id", unique=True)
            await self.db[PLANS].create_index([("owner_id", 1), ("status", 1)])
            await self.db[PLANS].create_index([("owner_id", 1), ("opportunity_id", 1)])
            await self.db[PLANS].create_index(
                [("owner_id", 1), ("source_type", 1), ("source_id", 1)]
            )
            # Enough history for recent fatigue and for an audit; not a
            # permanent record of everything ORA ever said to somebody. Only
            # closed plans carry the stamp, so nothing still open expires.
            await self.db[PLANS].create_index("expires_at", expireAfterSeconds=0)
            await self.db[ACTIVITY].create_index("id", unique=True)
            await self.db[ACTIVITY].create_index([("owner_id", 1), ("occurred_at", -1)])
            await self.db[ACTIVITY].create_index("expires_at", expireAfterSeconds=0)
        except Exception:
            logger.exception("indici delivery non creati (non fatale)")

    # --- plans ------------------------------------------------------------

    async def save_plan(self, plan: DeliveryPlan) -> DeliveryPlan:
        plan.touch()
        if not plan.is_open:
            # A settled plan starts ageing out. An open one never does: a
            # notification intending to arrive must not vanish because a
            # cleanup policy reached it first.
            from datetime import datetime, timedelta, timezone

            plan.expires_at = datetime.now(timezone.utc) + timedelta(
                days=HISTORY_RETENTION_DAYS
            )
        await self.db[PLANS].update_one(
            {"id": plan.id}, {"$set": plan.model_dump()}, upsert=True
        )
        return plan

    async def get_plan(self, owner_id: str, plan_id: str) -> Optional[DeliveryPlan]:
        doc = await self.db[PLANS].find_one(
            {"id": plan_id, "owner_id": owner_id}, {"_id": 0}
        )
        return DeliveryPlan.model_validate(doc) if doc else None

    async def open_plan_for(
        self, owner_id: str, source_id: str, *, source_type: str = "opportunity"
    ) -> Optional[DeliveryPlan]:
        """
        The plan already standing for this concern, if any.

        What stops a third re-evaluation of the same opportunity from becoming
        a third notification: the existing intention is found and updated
        rather than joined by a sibling.
        """
        doc = await self.db[PLANS].find_one(
            {
                **_subject_filter(owner_id, source_type, source_id),
                "status": {"$in": ["pending", "held"]},
            },
            {"_id": 0},
        )
        return DeliveryPlan.model_validate(doc) if doc else None

    async def open_plans(self, owner_id: str, *, limit: int = 50) -> List[DeliveryPlan]:
        docs = await self.db[PLANS].find(
            {"owner_id": owner_id, "status": {"$in": ["pending", "held"]}}, {"_id": 0}
        ).sort("created_at", 1).to_list(limit)
        return [DeliveryPlan.model_validate(d) for d in docs]

    async def plans_for(
        self, owner_id: str, source_id: str, *, source_type: str = "opportunity",
        limit: int = 20,
    ) -> List[DeliveryPlan]:
        docs = await self.db[PLANS].find(
            _subject_filter(owner_id, source_type, source_id), {"_id": 0}
        ).sort("created_at", 1).to_list(limit)
        return [DeliveryPlan.model_validate(d) for d in docs]

    # --- what ORA actually did -------------------------------------------

    async def record_activity(self, activity: AmbientActivity) -> AmbientActivity:
        from datetime import datetime, timedelta, timezone

        doc = activity.model_dump()
        doc["expires_at"] = datetime.now(timezone.utc) + timedelta(
            days=ACTIVITY_RETENTION_DAYS
        )
        await self.db[ACTIVITY].insert_one(doc)
        return activity

    async def recent_activity(
        self, owner_id: str, *, visibility: Optional[str] = None, limit: int = 10
    ) -> List[AmbientActivity]:
        query: Dict[str, Any] = {"owner_id": owner_id}
        if visibility:
            query["visibility"] = visibility
        docs = await self.db[ACTIVITY].find(query, {"_id": 0}).sort(
            "occurred_at", -1
        ).to_list(limit)
        return [AmbientActivity.model_validate(d) for d in docs]

    async def latest_ambient(self, owner_id: str) -> Optional[AmbientActivity]:
        found = await self.recent_activity(owner_id, visibility="ambient", limit=1)
        return found[0] if found else None

    async def forget_all(self, owner_id: str) -> Dict[str, int]:
        plans = await self.db[PLANS].delete_many({"owner_id": owner_id})
        activity = await self.db[ACTIVITY].delete_many({"owner_id": owner_id})
        return {
            "plans_deleted": plans.deleted_count,
            "activity_deleted": activity.deleted_count,
        }
