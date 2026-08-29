"""
Where research runs live.

A separate store on purpose. What the world said this morning is not something
true about a person, and putting the two in one place is how a rate quoted on a
comparison page becomes, three months later, a fact ORA believes about
somebody's life. Life Memory keeps what the person is; this keeps what was
looked up, when, and from where.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from research.models import ResearchRun

logger = logging.getLogger("ora.research.repository")

COLLECTION = "research_runs"


class ResearchRepository:
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
            logger.info("research index setup: %s", type(e).__name__)

    async def save(self, run: ResearchRun) -> None:
        await self.col.update_one(
            {"id": run.id}, {"$set": run.model_dump()}, upsert=True
        )

    async def get(self, user_id: str, run_id: str) -> Optional[ResearchRun]:
        """Ownership is not a filter applied later — it is part of the read."""
        row = await self.col.find_one({"id": run_id, "user_id": user_id}, {"_id": 0})
        return ResearchRun.model_validate(row) if row else None

    async def still_valid(self, user_id: str, *, limit: int = 8) -> List[ResearchRun]:
        """
        This person's completed runs whose own freshness window has not closed.

        The window came from the model that ran them; the only thing decided
        here is whether a timestamp has passed.
        """
        now = datetime.now(timezone.utc).isoformat()
        cursor = (
            self.col.find(
                {
                    "user_id": user_id,
                    "status": {"$in": ["completed", "partial"]},
                    "valid_until": {"$gt": now},
                },
                {"_id": 0},
            )
            .sort("started_at", -1)
            .limit(limit)
        )
        rows = await cursor.to_list(limit)
        out: List[ResearchRun] = []
        for row in rows:
            try:
                out.append(ResearchRun.model_validate(row))
            except Exception:
                continue
        return out

    async def recent(self, user_id: str, *, limit: int = 20) -> List[ResearchRun]:
        cursor = (
            self.col.find({"user_id": user_id}, {"_id": 0})
            .sort("started_at", -1)
            .limit(limit)
        )
        rows = await cursor.to_list(limit)
        out: List[ResearchRun] = []
        for row in rows:
            try:
                out.append(ResearchRun.model_validate(row))
            except Exception:
                continue
        return out
