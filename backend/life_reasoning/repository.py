"""Mongo persistence for user-owned Impact Assessments.

Mirrors `life_signals.repository` conventions exactly: a COLLECTION constant,
an `ensure_indexes` called once at startup, and `user_id` on every query.
"""

from __future__ import annotations

from typing import List, Optional

from life_reasoning.models import ImpactAssessment


class DuplicateAssessment(Exception):
    """The same batch identity was already assessed (idempotent replay)."""


class ImpactAssessmentRepository:
    COLLECTION = "life_impact_assessments"

    def __init__(self, db):
        self.db = db
        self.col = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self.col.create_index([("user_id", 1), ("id", 1)], unique=True)
        # Storage-level idempotency: the same batch of signals cannot be
        # assessed twice, even if two passes race.
        await self.col.create_index(
            [("user_id", 1), ("batch_key", 1)], unique=True, sparse=True
        )
        # The V2.9.3 read path: most recent assessments for one user.
        await self.col.create_index([("user_id", 1), ("created_at", -1)])
        # Continuity: "what did we already conclude about this ref?"
        await self.col.create_index([("user_id", 1), ("focal_refs", 1)])
        # The V2.9.3 attention pass read path: assessments not yet evaluated.
        await self.col.create_index(
            [("user_id", 1), ("attention_status", 1), ("created_at", 1), ("id", 1)]
        )

    async def insert(self, assessment: ImpactAssessment) -> None:
        try:
            await self.col.insert_one(assessment.model_dump())
        except Exception as e:  # pragma: no cover - driver-specific type
            if _is_duplicate_key(e):
                raise DuplicateAssessment(assessment.batch_key) from e
            raise

    async def get_by_batch_key(
        self, user_id: str, batch_key: str
    ) -> Optional[ImpactAssessment]:
        doc = await self.col.find_one(
            {"user_id": user_id, "batch_key": batch_key}, {"_id": 0}
        )
        return ImpactAssessment.model_validate(doc) if doc else None

    async def list_recent(
        self, user_id: str, *, limit: int = 10
    ) -> List[ImpactAssessment]:
        """Bounded, user-scoped, newest first — the shape V2.9.3 will read."""
        capped = max(1, min(int(limit or 10), 25))
        cur = (
            self.col.find({"user_id": user_id}, {"_id": 0})
            .sort([("created_at", -1), ("id", -1)])
            .limit(capped)
        )
        docs = await cur.to_list(capped)
        return [ImpactAssessment.model_validate(d) for d in docs]

    async def list_for_ref(
        self, user_id: str, ref: str, *, limit: int = 5
    ) -> List[ImpactAssessment]:
        """Prior conclusions touching one canonical ref — cross-session
        continuity without re-reasoning from scratch."""
        capped = max(1, min(int(limit or 5), 25))
        cur = (
            self.col.find({"user_id": user_id, "focal_refs": ref}, {"_id": 0})
            .sort([("created_at", -1), ("id", -1)])
            .limit(capped)
        )
        docs = await cur.to_list(capped)
        return [ImpactAssessment.model_validate(d) for d in docs]

    async def list_awaiting_attention(
        self, user_id: str, *, limit: int = 5
    ) -> List[ImpactAssessment]:
        """Assessments the V2.9.3 attention pass has not evaluated yet.

        `$ne: "evaluated"` deliberately also matches documents written before
        the field existed, so no backfill is required.
        """
        capped = max(1, min(int(limit or 5), 25))
        cur = (
            self.col.find(
                {"user_id": user_id, "attention_status": {"$ne": "evaluated"}},
                {"_id": 0},
            )
            .sort([("created_at", 1), ("id", 1)])
            .limit(capped)
        )
        docs = await cur.to_list(capped)
        return [ImpactAssessment.model_validate(d) for d in docs]

    async def mark_attention_evaluated(
        self, user_id: str, assessment_ids: List[str]
    ) -> int:
        """Marks assessments consumed by the attention pass. Touches ONLY the
        lifecycle field — never the reasoning content."""
        if not assessment_ids:
            return 0
        result = await self.col.update_many(
            {"user_id": user_id, "id": {"$in": list(assessment_ids)[:50]}},
            {"$set": {"attention_status": "evaluated"}},
        )
        return int(getattr(result, "modified_count", 0))

    async def count(self, user_id: str) -> int:
        return await self.col.count_documents({"user_id": user_id})


def _is_duplicate_key(error: Exception) -> bool:
    if type(error).__name__ == "DuplicateKeyError":
        return True
    return getattr(error, "code", None) == 11000
