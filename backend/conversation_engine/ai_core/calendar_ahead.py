"""Bounded calendar context from the original owner-scoped read handler.

The next 48 hours may save a model/tool round trip, but do not cover the whole
calendar. A successful empty window and a failed read are distinct facts.
Neither makes a previous conversational answer into a current observation.
This module does not infer user intent, plan an action or write any event.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("ora.ai_core.calendar_ahead")
HOURS_AHEAD = 48
MAX_EVENTS = 20


def _one_each(events: Any) -> list:
    """Keep the original bounded projection and one copy of matching events."""
    visti = set()
    uno_per_uno = []
    for e in events:
        if not isinstance(e, dict):
            continue
        chi = (str(e.get("title") or "").strip().lower(), str(e.get("start_datetime") or ""))
        if chi in visti:
            continue
        visti.add(chi)
        uno_per_uno.append({
            k: e.get(k)
            for k in ("calendar_ref", "title", "start_datetime", "end_datetime", "all_day",
                      "location", "source", "description", "timezone", "day_label")
            if e.get(k) not in (None, "")
        })
        if len(uno_per_uno) >= MAX_EVENTS:
            break
    return uno_per_uno


def _coverage(now: datetime, until: datetime) -> Dict[str, Any]:
    return {
        "window": {"from": now.isoformat(), "to": until.isoformat()},
        "events": [],
        "status": "unavailable",
        "observed_at": None,
        "source_capability": "get_calendar_events",
        "historical_conversation_is_current_evidence": False,
        "this_is_only_the_next_48_hours": (
            "Only the events actually listed in this block were observed in the current turn. "
            "This window is NOT the whole calendar. For a specific date outside it, or a "
            "named appointment absent here, call get_calendar_events for the relevant date "
            "before stating its current time or that it no longer exists. A previously "
            "successful creation or update, an earlier tool observation and recent_turns "
            "are HISTORICAL: they cannot substitute for reading the requested current "
            "calendar state, because the person may have edited the event elsewhere. "
            "Do not change any calendar event merely to make a read succeed."
        ),
    }


async def the_next_two_days(db, user_id: str) -> Optional[Dict[str, Any]]:
    """Preserve observation coverage even when no nearby event was found.

    None is reserved for missing identity/database. A failed reader yields an
    unavailable snapshot, never a claim of an empty calendar. The same real
    handler, consent filters, period and event cap remain authoritative.
    """
    if db is None or not user_id:
        return None
    now = datetime.now(timezone.utc)
    until = now + timedelta(hours=HOURS_AHEAD)
    snapshot = _coverage(now, until)
    try:
        from conversation_engine.ai_core.tools.calendar_caps import get_calendar_events
        seen = await get_calendar_events(
            {"time_min": now.isoformat(), "time_max": until.isoformat()},
            {"db": db, "user_id": user_id},
        )
    except Exception as exc:
        logger.info("agenda non precaricata: %s", type(exc).__name__)
        snapshot["reason"] = "Current calendar read unavailable; do not answer from an earlier time as if verified now."
        return snapshot
    payload = getattr(seen, "payload", None) or {}
    if (getattr(seen, "kind", "") == "error" or getattr(seen, "status", "") != "ok"
            or not isinstance(payload, dict) or payload.get("status") not in (None, "ok", "success")):
        snapshot["reason"] = "Calendar reader did not confirm a successful current observation."
        return snapshot
    events = payload.get("items") if isinstance(payload.get("items"), list) else payload.get("events")
    if not isinstance(events, list):
        snapshot["reason"] = "Calendar reader did not provide a valid event list."
        return snapshot
    projected = _one_each(events)
    snapshot.update(
        events=projected,
        status="observed_events" if projected else "observed_empty_window",
        observed_at=datetime.now(timezone.utc).isoformat(),
        may_be_truncated=len(events) >= MAX_EVENTS,
    )
    return snapshot
