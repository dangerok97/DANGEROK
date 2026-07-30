"""CalendarContextProvider — feature-flagged, uses ingestion metadata only.

When CALENDAR_CONTEXT_ENABLED=false (default) it's a strict no-op.
When ON, it emits signals about imminent calendar events (starts_at,
category, connector_instance_id) that AlreadyAccessed via valid consent.
It NEVER re-fetches from Google; it only reads from `ingestion_events`
that already went through the pipeline.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import List

from .types import ProviderResult, Signal


def _flag_enabled() -> bool:
    return os.environ.get("CALENDAR_CONTEXT_ENABLED", "false").lower() in ("1", "true", "yes")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def calendar_provider(repo, user_id: str) -> ProviderResult:
    t0 = time.perf_counter()
    if not _flag_enabled():
        return ProviderResult(name="calendar", duration_ms=(time.perf_counter() - t0) * 1000)

    now = _now()
    horizon = (now + timedelta(days=7)).isoformat()
    cursor = repo.db.ingestion_events.find(
        {
            "user_id": user_id,
            "connector_id": "calendar_google",
            "source_record_type": "calendar_event",
            "ingestion_status": {"$in": ["processed", "normalized"]},
            "normalized_payload.starts_at.value": {"$gte": now.isoformat(), "$lte": horizon},
        },
        {"_id": 0, "id": 1, "normalized_payload": 1, "connector_instance_id": 1, "ingested_at": 1},
    ).sort("normalized_payload.starts_at.value", 1).limit(25)

    docs = await cursor.to_list(length=25)
    signals: List[Signal] = []
    for d in docs:
        np = d.get("normalized_payload") or {}
        title = (np.get("title") or {}).get("value")
        starts_at = (np.get("starts_at") or {}).get("value")
        signals.append(Signal(
            key="upcoming_calendar_event",
            value={
                "title": title,
                "starts_at": starts_at,
                "calendar_id": np.get("calendar_id"),
                "connector_instance_id": d.get("connector_instance_id"),
                "external_event_id": np.get("external_event_id"),
            },
            value_type="object",
            source_module="calendar",
            source_id=d.get("id"),
            confidence=1.0,
            verified=True,
            sensitivity="personal",
            observed_at=d.get("ingested_at") or now.isoformat(),
            reliability_tier="official",
        ))

    signals.append(Signal(
        key="calendar_provider_enabled",
        value=True,
        value_type="boolean",
        source_module="calendar",
        confidence=1.0,
        verified=True,
        sensitivity="public",
        observed_at=now.isoformat(),
        reliability_tier="official",
    ))

    return ProviderResult(name="calendar", signals=signals, duration_ms=(time.perf_counter() - t0) * 1000)
