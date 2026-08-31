"""
Storage for opportunities and the decisions taken about them.

Owner-scoped throughout: an opportunity is a statement about one person's
life, and there is no query here that could return somebody else's by
forgetting a filter — the user id is a parameter of every method.

Identity is a unique index, not a convention. Two records sharing an
`identity_key` would be the duplication this whole design exists to prevent,
and a rule the database enforces cannot be forgotten by a caller.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from opportunities.models import Opportunity, OpportunityDecision

logger = logging.getLogger(__name__)

OPPORTUNITIES = "opportunities"
DECISIONS = "opportunity_decisions"

# States in which a concern is settled: raising it again needs a reason, not
# just a new scan.
CLOSED = ("dismissed", "suppressed", "resolved", "expired")


class OpportunityRepository:
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        try:
            await self.db[OPPORTUNITIES].create_index("id", unique=True)
            await self.db[OPPORTUNITIES].create_index(
                [("owner_id", 1), ("identity_key", 1)], unique=True
            )
            await self.db[OPPORTUNITIES].create_index([("owner_id", 1), ("status", 1)])
            await self.db[DECISIONS].create_index([("owner_id", 1), ("opportunity_id", 1)])
        except Exception:
            logger.exception("indici opportunities non creati (non fatale)")

    async def save(self, opportunity: Opportunity) -> Opportunity:
        opportunity.touch()
        await self.db[OPPORTUNITIES].update_one(
            {"owner_id": opportunity.owner_id, "identity_key": opportunity.identity_key},
            {"$set": opportunity.model_dump()},
            upsert=True,
        )
        return opportunity

    async def get(self, owner_id: str, opportunity_id: str) -> Optional[Opportunity]:
        doc = await self.db[OPPORTUNITIES].find_one(
            {"id": opportunity_id, "owner_id": owner_id}, {"_id": 0}
        )
        return Opportunity.model_validate(doc) if doc else None

    async def by_identity(self, owner_id: str, identity_key: str) -> Optional[Opportunity]:
        """
        The record for this concern, whatever state it is in.

        Closed ones are included on purpose: finding a dismissed concern is
        what stops the next scan from raising it again.
        """
        doc = await self.db[OPPORTUNITIES].find_one(
            {"owner_id": owner_id, "identity_key": identity_key}, {"_id": 0}
        )
        return Opportunity.model_validate(doc) if doc else None

    async def list(
        self, owner_id: str, *, statuses: Optional[List[str]] = None, limit: int = 50
    ) -> List[Opportunity]:
        query: Dict[str, Any] = {"owner_id": owner_id}
        if statuses:
            query["status"] = {"$in": statuses}
        docs = await self.db[OPPORTUNITIES].find(query, {"_id": 0}).to_list(limit)
        found = [Opportunity.model_validate(d) for d in docs]
        # Ordered by the words the model chose, turned into an order here.
        return sorted(found, key=lambda o: o.order_key)

    async def record_decision(self, decision: OpportunityDecision) -> OpportunityDecision:
        await self.db[DECISIONS].insert_one(decision.model_dump())
        return decision

    async def decisions_for(
        self, owner_id: str, opportunity_id: str
    ) -> List[OpportunityDecision]:
        docs = await self.db[DECISIONS].find(
            {"owner_id": owner_id, "opportunity_id": opportunity_id}, {"_id": 0}
        ).sort("decided_at", 1).to_list(20)
        return [OpportunityDecision.model_validate(d) for d in docs]

    async def forget_all(self, owner_id: str) -> Dict[str, int]:
        """Everything ORA thought was worth raising, gone."""
        opportunities = await self.db[OPPORTUNITIES].delete_many({"owner_id": owner_id})
        decisions = await self.db[DECISIONS].delete_many({"owner_id": owner_id})
        return {
            "opportunities_deleted": opportunities.deleted_count,
            "decisions_deleted": decisions.deleted_count,
        }
