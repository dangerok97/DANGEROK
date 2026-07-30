"""Storage layer for the Behavioral Intelligence Engine.

Collections
-----------
- ``behavioral_events``          — append-only observed events (immutable).
- ``behavioral_cursors``         — per (user, source) progress cursor for lazy-sync.
- ``behavior_metric_snapshots``  — versioned metric snapshots (append-only).
- ``behavior_profile_snapshots`` — versioned profile snapshots (append-only).
- ``behavior_pattern_snapshots`` — versioned pattern list per user (append-only).

Invariants
----------
* No document is ever updated in ``behavioral_events`` or the ``*_snapshots``
  collections. Snapshots are versioned by ``computed_at`` and older versions
  remain queryable for audit/history purposes.
* Cursors are the *only* writable collection (idempotent progress markers).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase


EVENTS = "behavioral_events"
CURSORS = "behavioral_cursors"
METRIC_SNAPSHOTS = "behavior_metric_snapshots"
PROFILE_SNAPSHOTS = "behavior_profile_snapshots"
PATTERN_SNAPSHOTS = "behavior_pattern_snapshots"


class BehavioralStorage:
    """Thin DAL. Enforces append-only semantics for event/snapshot collections."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    # ------------------------ indexes ------------------------
    async def ensure_indexes(self) -> None:
        await self.db[EVENTS].create_index("id", unique=True)
        await self.db[EVENTS].create_index([("user_id", 1), ("occurred_at", -1)])
        await self.db[EVENTS].create_index([("user_id", 1), ("event_type", 1), ("occurred_at", -1)])
        await self.db[EVENTS].create_index(
            [("user_id", 1), ("source_type", 1), ("source_ref", 1)],
            unique=True,
            partialFilterExpression={"source_ref": {"$type": "string"}},
        )

        await self.db[CURSORS].create_index(
            [("user_id", 1), ("source_type", 1)], unique=True,
        )

        for coll in (METRIC_SNAPSHOTS, PROFILE_SNAPSHOTS, PATTERN_SNAPSHOTS):
            await self.db[coll].create_index([("user_id", 1), ("computed_at", -1)])
            await self.db[coll].create_index("id", unique=True)

    # ------------------------ events (append-only) ------------------------
    async def insert_event(self, doc: Dict[str, Any]) -> bool:
        """Insert one event. Returns True on insert, False if duplicated."""
        try:
            await self.db[EVENTS].insert_one(doc)
            return True
        except Exception as e:  # duplicate key on (user_id, source_type, source_ref)
            if "duplicate key" in str(e).lower() or getattr(e, "code", None) == 11000:
                return False
            raise

    async def bulk_insert_events(self, docs: List[Dict[str, Any]]) -> int:
        if not docs:
            return 0
        try:
            res = await self.db[EVENTS].insert_many(docs, ordered=False)
            return len(res.inserted_ids)
        except Exception as e:  # BulkWriteError with duplicates
            inserted = getattr(getattr(e, "details", None) or {}, "get", lambda k, d=0: d)("nInserted", 0)
            if not inserted:
                # Compat: newer motor exposes details as dict
                try:
                    inserted = int(e.details.get("nInserted", 0))
                except Exception:
                    inserted = 0
            return inserted

    async def list_events(
        self,
        user_id: str,
        *,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        event_types: Optional[List[str]] = None,
        limit: int = 200,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {"user_id": user_id}
        if since or until:
            rng: Dict[str, Any] = {}
            if since:
                rng["$gte"] = since
            if until:
                rng["$lte"] = until
            q["occurred_at"] = rng
        if event_types:
            q["event_type"] = {"$in": event_types}
        cur = (
            self.db[EVENTS]
            .find(q, {"_id": 0})
            .sort("occurred_at", -1)
            .skip(max(skip, 0))
            .limit(max(1, min(limit, 1000)))
        )
        return await cur.to_list(length=1000)

    async def count_events(self, user_id: str, event_types: Optional[List[str]] = None) -> int:
        q: Dict[str, Any] = {"user_id": user_id}
        if event_types:
            q["event_type"] = {"$in": event_types}
        return await self.db[EVENTS].count_documents(q)

    async def last_event(self, user_id: str, event_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        q: Dict[str, Any] = {"user_id": user_id}
        if event_type:
            q["event_type"] = event_type
        doc = await self.db[EVENTS].find_one(q, {"_id": 0}, sort=[("occurred_at", -1)])
        return doc

    # ------------------------ cursors ------------------------
    async def get_cursor(self, user_id: str, source_type: str) -> Optional[Dict[str, Any]]:
        return await self.db[CURSORS].find_one(
            {"user_id": user_id, "source_type": source_type}, {"_id": 0},
        )

    async def upsert_cursor(
        self,
        user_id: str,
        source_type: str,
        *,
        last_processed_at: Optional[datetime] = None,
        last_processed_id: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        set_doc: Dict[str, Any] = {
            "user_id": user_id,
            "source_type": source_type,
            "updated_at": now,
        }
        if last_processed_at is not None:
            set_doc["last_processed_at"] = last_processed_at
        if last_processed_id is not None:
            set_doc["last_processed_id"] = last_processed_id
        await self.db[CURSORS].update_one(
            {"user_id": user_id, "source_type": source_type},
            {"$set": set_doc},
            upsert=True,
        )

    # ------------------------ snapshots (append-only) ------------------------
    async def save_metric_snapshot(self, doc: Dict[str, Any]) -> None:
        await self.db[METRIC_SNAPSHOTS].insert_one(doc)

    async def save_profile_snapshot(self, doc: Dict[str, Any]) -> None:
        await self.db[PROFILE_SNAPSHOTS].insert_one(doc)

    async def save_pattern_snapshot(self, doc: Dict[str, Any]) -> None:
        await self.db[PATTERN_SNAPSHOTS].insert_one(doc)

    async def latest_snapshot(self, coll: str, user_id: str) -> Optional[Dict[str, Any]]:
        return await self.db[coll].find_one(
            {"user_id": user_id}, {"_id": 0}, sort=[("computed_at", -1)],
        )
