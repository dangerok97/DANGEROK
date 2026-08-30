"""
Where decisions-in-progress live.

Its own store, next to `research_runs` and for the same reason: what ORA worked
out about a choice on a given day, from evidence that had a shelf life, is not
a fact about a person. It is a reading, and readings are superseded.

Kept so that a later run can say what it is superseding and why — the data has
to allow "I said A, now I would say B, because" even though nothing in this
phase goes looking for the opportunity to say it.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from comparison.models import ComparisonRun

logger = logging.getLogger("ora.comparison.repository")

COLLECTION = "comparison_runs"


class ComparisonRepository:
    def __init__(self, db):
        self.db = db

    @property
    def col(self):
        return self.db[COLLECTION]

    async def ensure_indexes(self) -> None:
        try:
            await self.col.create_index([("user_id", 1), ("started_at", -1)])
            await self.col.create_index([("id", 1)], unique=True)
        except Exception as e:  # pragma: no cover - index setup is advisory
            logger.info("comparison index setup: %s", type(e).__name__)

    async def save(self, run: ComparisonRun) -> None:
        await self.col.update_one({"id": run.id}, {"$set": run.model_dump()}, upsert=True)

    async def get(self, user_id: str, run_id: str) -> Optional[ComparisonRun]:
        """Ownership is part of the read, not a filter applied afterwards."""
        row = await self.col.find_one({"id": run_id, "user_id": user_id}, {"_id": 0})
        return ComparisonRun.model_validate(row) if row else None

    async def latest_for_session(
        self, user_id: str, session_id: str
    ) -> Optional[ComparisonRun]:
        """
        The last thing decided in this conversation.

        What makes a new run a revision rather than a new decision: same
        person, same conversation, something already concluded there.
        """
        row = await self.col.find_one(
            {"user_id": user_id, "session_id": session_id},
            {"_id": 0},
            sort=[("started_at", -1)],
        )
        return ComparisonRun.model_validate(row) if row else None

    async def recent(self, user_id: str, *, limit: int = 20) -> List[ComparisonRun]:
        cursor = (
            self.col.find({"user_id": user_id}, {"_id": 0})
            .sort("started_at", -1)
            .limit(limit)
        )
        out: List[ComparisonRun] = []
        for row in await cursor.to_list(limit):
            try:
                out.append(ComparisonRun.model_validate(row))
            except Exception:
                continue
        return out
