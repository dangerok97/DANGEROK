"""Append-only behavioral timeline.

The timeline is the projection layer over the ``behavioral_events``
collection. Records are immutable: this module NEVER updates or deletes
an event. Uniqueness is enforced at the DAL layer (see ``storage.py``).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .storage import BehavioralStorage
from .types import BehavioralEvent, BehavioralEventType, TimelinePage


def _iso(dt: datetime) -> datetime:
    """Return a timezone-aware datetime (UTC). Used to normalize sources."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class BehavioralTimeline:
    def __init__(self, storage: BehavioralStorage):
        self._store = storage

    # ------------------------ append (single) ------------------------
    async def append_event(
        self,
        *,
        user_id: str,
        event_type: BehavioralEventType,
        occurred_at: datetime,
        metadata: Optional[Dict[str, Any]] = None,
        source_type: Optional[str] = None,
        source_ref: Optional[str] = None,
    ) -> bool:
        """Idempotently append one event. Returns True if inserted."""
        doc = {
            "id": f"bhv_{uuid.uuid4().hex[:16]}",
            "user_id": user_id,
            "event_type": event_type.value if isinstance(event_type, BehavioralEventType) else str(event_type),
            "occurred_at": _iso(occurred_at),
            "metadata": metadata or {},
            "source_type": source_type,
            "source_ref": source_ref,
            "recorded_at": datetime.now(timezone.utc),
            "version": 1,
            "immutable": True,
        }
        return await self._store.insert_event(doc)

    async def append_events(self, docs: List[Dict[str, Any]]) -> int:
        """Bulk append. Docs must be already normalized (see observers)."""
        return await self._store.bulk_insert_events(docs)

    # ------------------------ query ------------------------
    async def get_page(
        self,
        user_id: str,
        *,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        event_types: Optional[List[BehavioralEventType]] = None,
        limit: int = 200,
        skip: int = 0,
    ) -> TimelinePage:
        types_val = [e.value if isinstance(e, BehavioralEventType) else e for e in (event_types or [])] or None
        raw = await self._store.list_events(
            user_id,
            since=since,
            until=until,
            event_types=types_val,
            limit=limit,
            skip=skip,
        )
        items = [BehavioralEvent(**d) for d in raw]
        total = await self._store.count_events(user_id, event_types=types_val)
        next_cursor = None
        if len(items) == limit and (skip + limit) < total:
            next_cursor = str(skip + limit)
        return TimelinePage(items=items, next_cursor=next_cursor, total=total)

    async def count(self, user_id: str, event_type: Optional[BehavioralEventType] = None) -> int:
        return await self._store.count_events(
            user_id,
            event_types=[event_type.value] if event_type else None,
        )
