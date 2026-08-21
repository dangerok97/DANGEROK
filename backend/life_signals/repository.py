"""Mongo persistence for user-owned Life Change Signals.

Mirrors `context_graph.repository` conventions (COLLECTION constant, an
`ensure_indexes` called once at startup, user-scoped queries throughout).
"""

from __future__ import annotations

from typing import List, Optional

from life_signals.models import LifeChangeSignal, now_iso


class DuplicateSignal(Exception):
    """The same mutation identity was already recorded (idempotent replay)."""


class LifeSignalRepository:
    COLLECTION = "life_change_signals"

    def __init__(self, db):
        self.db = db
        self.col = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self.col.create_index([("user_id", 1), ("id", 1)], unique=True)
        # Storage-level idempotency: a replayed mutation cannot become a
        # second signal even if two callers race.
        await self.col.create_index(
            [("user_id", 1), ("dedupe_key", 1)], unique=True, sparse=True
        )
        # The consumer query: pending work for one user, oldest first.
        await self.col.create_index(
            [("user_id", 1), ("status", 1), ("created_at", 1), ("id", 1)]
        )

    async def insert(self, signal: LifeChangeSignal) -> None:
        try:
            await self.col.insert_one(signal.model_dump())
        except Exception as e:  # pragma: no cover - driver-specific type
            if _is_duplicate_key(e):
                raise DuplicateSignal(signal.dedupe_key) from e
            raise

    async def get_by_dedupe_key(
        self, user_id: str, dedupe_key: str
    ) -> Optional[LifeChangeSignal]:
        doc = await self.col.find_one(
            {"user_id": user_id, "dedupe_key": dedupe_key}, {"_id": 0}
        )
        return LifeChangeSignal.model_validate(doc) if doc else None

    async def list_by_status(
        self, user_id: str, *, status: str = "pending", limit: int = 20
    ) -> List[LifeChangeSignal]:
        """Bounded, user-scoped, deterministically ordered. Oldest first with
        `id` as tiebreaker so two signals written in the same millisecond
        still have a stable total order across calls."""
        cur = (
            self.col.find({"user_id": user_id, "status": status}, {"_id": 0})
            .sort([("created_at", 1), ("id", 1)])
            .limit(limit)
        )
        docs = await cur.to_list(limit)
        return [LifeChangeSignal.model_validate(d) for d in docs]

    async def count_by_status(self, user_id: str, *, status: str = "pending") -> int:
        return await self.col.count_documents({"user_id": user_id, "status": status})

    async def mark_processed(self, user_id: str, signal_ids: List[str]) -> int:
        if not signal_ids:
            return 0
        result = await self.col.update_many(
            {"user_id": user_id, "id": {"$in": list(signal_ids)[:100]}},
            {"$set": {"status": "processed", "processed_at": now_iso()}},
        )
        return int(getattr(result, "modified_count", 0))

    async def mark_failed(
        self, user_id: str, signal_ids: List[str], *, error_code: str = "UNKNOWN"
    ) -> int:
        if not signal_ids:
            return 0
        result = await self.col.update_many(
            {"user_id": user_id, "id": {"$in": list(signal_ids)[:100]}},
            {
                "$set": {"status": "failed", "last_error_code": str(error_code)[:80]},
                "$inc": {"attempts": 1},
            },
        )
        return int(getattr(result, "modified_count", 0))


def _is_duplicate_key(error: Exception) -> bool:
    """pymongo raises DuplicateKeyError (code 11000); avoid importing the
    driver here so the repository stays testable against a fake db."""
    if type(error).__name__ == "DuplicateKeyError":
        return True
    return getattr(error, "code", None) == 11000
