"""Operational context for the attention pass (V2.9.3).

Deliberately narrow. V2.9.2 already did the expensive work of understanding
what changed and what it might mean; this layer only needs to know what it
would cost to say it right now. So it loads no Profile, no Memory, no document
and no conversation — only bounded operational signals.

Every signal here is computed deterministically from real data. Nothing about
interruption cost is asked of the model: the moment "is the user asleep?"
becomes a prompt question, it becomes negotiable.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ora.life_attention.context")

# Local hours treated as quiet / likely asleep. Applied against the user's
# RESOLVED timezone, not a fixed offset.
QUIET_START_HOUR = 22
QUIET_END_HOUR = 7
SLEEP_START_HOUR = 23
SLEEP_END_HOUR = 6

CALENDAR_LOOKAHEAD_HOURS = 2
RECENT_SUGGESTION_WINDOW_HOURS = 1

# Suggestion type/source used by the AI-native path. "generic" is an existing
# domain-neutral member of the taxonomy — no new type was added, because a new
# type would be a domain category by another name.
AI_NATIVE_SOURCE = "life_reasoning"
AI_NATIVE_TYPE = "generic"


async def resolve_local_time(db, user_id: str) -> Tuple[datetime, str, int]:
    """Current local time via the existing timezone service. Returns
    (utc_now, tz_name, local_hour)."""
    from timezone_service import resolve_user_timezone

    utc_now = datetime.now(timezone.utc)
    tz_name = "UTC"
    try:
        resolved = await resolve_user_timezone(db, user_id)
        tz_name = resolved.tz_name
    except Exception as exc:
        logger.info("attention timezone soft-fail: %s", type(exc).__name__)
    try:
        from zoneinfo import ZoneInfo

        local_hour = utc_now.astimezone(ZoneInfo(tz_name)).hour
    except Exception:
        tz_name = "UTC"
        local_hour = utc_now.hour
    return utc_now, tz_name, local_hour


def is_quiet_hour(local_hour: int) -> bool:
    return local_hour >= QUIET_START_HOUR or local_hour < QUIET_END_HOUR


def is_sleep_hour(local_hour: int) -> bool:
    return local_hour >= SLEEP_START_HOUR or local_hour < SLEEP_END_HOUR


async def calendar_occupancy(db, user_id: str, now: datetime) -> Dict[str, Any]:
    """Whether the user is inside a calendar commitment RIGHT NOW, by time
    overlap only.

    It never reads the event title. Guessing what someone is doing from the
    words in a calendar entry is exactly the kind of keyword inference this
    architecture avoids elsewhere, and being wrong about it is worse than not
    knowing: the honest signal is "busy", not "driving".
    """
    busy_now = False
    upcoming = 0
    window_end = (now + timedelta(hours=CALENDAR_LOOKAHEAD_HOURS)).isoformat()
    try:
        docs = await db.calendar_event_drafts.find(
            {
                "user_id": user_id,
                "status": {"$ne": "cancelled"},
                "start_datetime": {"$lte": window_end},
            },
            {"_id": 0, "start_datetime": 1, "end_datetime": 1},
        ).sort("start_datetime", -1).limit(20).to_list(20)
    except Exception as exc:
        logger.info("attention calendar soft-fail: %s", type(exc).__name__)
        return {"busy_now": False, "upcoming_soon": 0}

    for doc in docs:
        start = _parse(doc.get("start_datetime"))
        if not start:
            continue
        end = _parse(doc.get("end_datetime")) or (start + timedelta(hours=1))
        if start <= now <= end:
            busy_now = True
        elif now < start <= now + timedelta(hours=CALENDAR_LOOKAHEAD_HOURS):
            upcoming += 1
    return {"busy_now": busy_now, "upcoming_soon": upcoming}


async def suggestion_pressure(db, user_id: str, now: datetime) -> Dict[str, Any]:
    """How much ORA has already been speaking. Reuses the Proactive Engine's
    own repository — this is the same volume the legacy path is measured
    against, not a parallel count."""
    from proactive_engine.repository import SuggestionRepository

    repo = SuggestionRepository(db)
    since = (now - timedelta(hours=RECENT_SUGGESTION_WINDOW_HOURS)).isoformat()
    try:
        recent = await repo.count_recent(user_id, since_iso=since)
        active = await repo.list_for_user(user_id, statuses=["active"], limit=40)
    except Exception as exc:
        logger.info("attention suggestion pressure soft-fail: %s", type(exc).__name__)
        return {"recent_1h": 0, "active_count": 0}
    return {"recent_1h": int(recent or 0), "active_count": len(active)}


async def learning_signals(db, user_id: str) -> Dict[str, Any]:
    """Bounded accept/dismiss history for the AI-native path, from the
    existing LearningStore. A first-time user gets a neutral multiplier — the
    store itself refuses to learn from fewer than three interactions."""
    from proactive_engine.learning import LearningStore

    store = LearningStore(db)
    try:
        multiplier = await store.multiplier(user_id, AI_NATIVE_TYPE, AI_NATIVE_SOURCE)
        dismiss_rate = await store.dismiss_rate(user_id, AI_NATIVE_TYPE, AI_NATIVE_SOURCE)
    except Exception as exc:
        logger.info("attention learning soft-fail: %s", type(exc).__name__)
        return {"multiplier": 1.0, "dismiss_rate": 0.0}
    return {"multiplier": float(multiplier or 1.0), "dismiss_rate": float(dismiss_rate or 0.0)}


async def notifications_allowed(db, user_id: str) -> bool:
    """Whether the user actually granted notification delivery.

    Reuses the existing permission registry capability `notifications.deliver`
    rather than inventing a settings flag. Ungranted is the default, so
    `notify` downgrades unless the user has explicitly opted in.
    """
    try:
        from permissions.service import PermissionService

        return bool(await PermissionService(db).check_access(
            user_id=user_id,
            capability_id="notifications.deliver",
            connector_id="notifications",
        ))
    except Exception as exc:
        logger.info("attention notification permission soft-fail: %s", type(exc).__name__)
        return False


def compute_interruption_cost(
    *,
    quiet: bool,
    sleep: bool,
    busy_now: bool,
    recent_1h: int,
    active_count: int,
    dismiss_rate: float,
) -> float:
    """Deterministic cost of speaking right now, in [0, 1].

    Computed, never asked of the model — and never inferred from what a
    calendar entry is *called*.
    """
    cost = 0.0
    if sleep:
        cost += 0.5
    elif quiet:
        cost += 0.35
    if busy_now:
        cost += 0.3
    cost += min(0.2, 0.07 * max(0, int(recent_1h)))
    if active_count >= 6:
        cost += 0.15
    cost += max(0.0, min(0.3, float(dismiss_rate or 0.0) * 0.3))
    return round(max(0.0, min(1.0, cost)), 3)


async def build_operational_context(db, user_id: str) -> Dict[str, Any]:
    """The whole bounded situation the attention prompt is allowed to see."""
    now, tz_name, local_hour = await resolve_local_time(db, user_id)
    quiet = is_quiet_hour(local_hour)
    sleep = is_sleep_hour(local_hour)
    occupancy = await calendar_occupancy(db, user_id, now)
    pressure = await suggestion_pressure(db, user_id, now)
    learning = await learning_signals(db, user_id)

    cost = compute_interruption_cost(
        quiet=quiet,
        sleep=sleep,
        busy_now=bool(occupancy.get("busy_now")),
        recent_1h=int(pressure.get("recent_1h") or 0),
        active_count=int(pressure.get("active_count") or 0),
        dismiss_rate=float(learning.get("dismiss_rate") or 0.0),
    )

    return {
        "now_utc": now,
        "timezone": tz_name,
        "local_hour": local_hour,
        "quiet_hours": quiet,
        "likely_sleep": sleep,
        "busy_in_commitment_now": bool(occupancy.get("busy_now")),
        "commitments_next_2h": int(occupancy.get("upcoming_soon") or 0),
        "suggestions_shown_last_hour": int(pressure.get("recent_1h") or 0),
        "suggestions_currently_visible": int(pressure.get("active_count") or 0),
        "user_dismiss_rate": round(float(learning.get("dismiss_rate") or 0.0), 3),
        "learning_multiplier": round(float(learning.get("multiplier") or 1.0), 3),
        "interruption_cost": cost,
    }


def prompt_view(context: Dict[str, Any], *, times_already_raised: int) -> Dict[str, Any]:
    """What the model is allowed to see: the operational shape of the moment,
    without the permission facts it must not try to reason around."""
    return {
        "local_hour": context.get("local_hour"),
        "timezone": context.get("timezone"),
        "busy_in_commitment_now": context.get("busy_in_commitment_now"),
        "commitments_next_2h": context.get("commitments_next_2h"),
        "suggestions_shown_last_hour": context.get("suggestions_shown_last_hour"),
        "suggestions_currently_visible": context.get("suggestions_currently_visible"),
        "times_ora_already_raised_this": times_already_raised,
    }


def _parse(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None
