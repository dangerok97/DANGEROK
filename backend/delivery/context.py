"""
Everything a judgement about interrupting somebody needs, and nothing else.

    PRESENCE IS CONTEXT, NOT A TRIGGER.

Being at home is not a reason to send anything. Neither is it nothing: the
same fact means different things depending on where somebody is, whether they
are already inside the app, whether three notifications arrived in the last
hour and whether it is a quarter past two in the morning. So all of that is
supplied, flat, unranked, and none of it carries a recommendation.

The temptation this file exists to resist is the helpful pre-computation: a
field called `should_interrupt`, a number called `interruption_cost`, a
boolean called `good_moment`. Each would be the judgement smuggled into the
payload, and the model would rightly defer to it. What is here instead is the
raw shape of the moment — hours, counts, labels, timestamps — leaving the one
question that matters unanswered until somebody answers it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# How far back interruptions still count as recent. Long enough that three in
# an hour is visible, short enough that yesterday is not held against today.
FATIGUE_WINDOW_HOURS = 6

# How much of the recent past is described at all.
MAX_RECENT = 6

# How far back the qualitative history reaches. Long enough to notice a
# pattern of things going unread; short enough that last month is not held
# against today.
HISTORY_DAYS = 7


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def build(
    db,
    user_id: str,
    *,
    opportunity: Optional[Any] = None,
    app_state: str = "unknown",
) -> Dict[str, Any]:
    """
    The moment, as facts.

    Every source is best-effort and every failure is declared rather than
    silently filled in with a default: a model told the calendar is empty when
    it is actually unreachable will reason confidently about a life it cannot
    see.
    """
    now = _now()
    context: Dict[str, Any] = {
        "now": now.isoformat(),
        # foreground | background | unknown. A push to somebody already
        # reading the same screen is usually noise — but that is a judgement,
        # so it is a fact here and a conclusion elsewhere.
        "app_state": app_state if app_state in ("foreground", "background") else "unknown",
        "unavailable_sources": [],
    }

    for name, gather in (
        ("clock", _clock),
        ("where_they_are", _presence),
        ("what_they_are_committed_to", _commitments),
        ("recent_interruptions", _recent_interruptions),
        ("recently_shown", _recently_shown),
        ("they_already_refused", _refused),
        ("can_be_notified", _permission),
        ("what_they_asked_for", _preferences),
        ("how_past_notifications_went", _history),
    ):
        try:
            context[name] = await gather(db, user_id, now)
        except Exception as e:
            logger.info("delivery context %s unavailable: %s", name, type(e).__name__)
            context["unavailable_sources"].append(name)

    if opportunity is not None:
        context["about"] = _about(opportunity, now)
        # "Ti ho già interrotto ieri per QUESTA cosa" is a different fact from
        # "ieri hai ricevuto una notifica su tutt'altro", and only one of them
        # is a reason to say this one differently. The general history cannot
        # answer it, so the same concern gets its own two lines.
        context["about"]["how_this_one_went_before"] = await _same_concern(
            db, user_id, getattr(opportunity, "id", ""), now
        )

    return context


def _about(opportunity: Any, now: datetime) -> Dict[str, Any]:
    """
    The thing being weighed, and what it is waiting on.

    Relevance and urgency travel here because the model that wrote them is
    the one reading them back — it is its own earlier judgement, not a score
    the code is asking it to obey. Nothing downstream branches on either.
    """
    valid_until = getattr(opportunity, "valid_until", None)
    return {
        "what": getattr(opportunity, "semantic_summary", ""),
        "why_it_matters": getattr(opportunity, "why_it_matters", ""),
        "why_now": getattr(opportunity, "why_now", "") or None,
        "raised_at": getattr(opportunity, "created_at", None),
        "relevance": getattr(opportunity, "relevance", None),
        "urgency": getattr(opportunity, "urgency", None),
        "how_time_sensitive": getattr(opportunity, "time_sensitivity", None),
        "stops_being_useful_at": valid_until,
        "hours_until_it_stops_being_useful": _hours_until(valid_until, now),
        "waiting_on_an_answer": bool(getattr(opportunity, "requires_clarification", False)),
        "times_already_shown": int(getattr(opportunity, "surfaced_count", 0) or 0),
        "already_seen": bool(getattr(opportunity, "seen_at", None)),
        "they_said_later_until": getattr(opportunity, "deferred_until", None),
    }


async def _same_concern(db, user_id: str, opportunity_id: str, now: datetime) -> Dict[str, Any]:
    """
    How this particular thing has gone, as opposed to notifications at large.

    Bounded and qualitative, like the general history: how many times this one
    was already sent, whether it was ever opened, how long ago the last
    attempt was. No ratio, because a ratio is a metric and a metric invites
    optimising.
    """
    if not opportunity_id:
        return {"times_already_sent": 0, "ever_opened": False}

    since = (now - timedelta(days=HISTORY_DAYS)).isoformat()
    rows = await db.delivery_plans.find(
        {
            "owner_id": user_id,
            "opportunity_id": opportunity_id,
            "delivered_at": {"$gte": since},
        },
        {"_id": 0, "delivered_at": 1, "outcome": 1},
    ).sort("delivered_at", -1).to_list(MAX_RECENT)

    return {
        "times_already_sent": len(rows),
        "ever_opened": any(r.get("outcome") == "opened" for r in rows),
        "minutes_since_the_last_one": _minutes_since(
            rows[0].get("delivered_at") if rows else None, now
        ),
    }


async def _clock(db, user_id: str, now: datetime) -> Dict[str, Any]:
    """
    What time it is where they are — never whether that is a good time.

    `quiet_hours` is the one borderline field here, and it stays because it is
    a fact about a convention, not a decision: it says the hour falls in the
    range people generally call night. What follows from that is the model's
    to say.
    """
    from life_attention.context import is_quiet_hour, is_sleep_hour, resolve_local_time

    _, tz_name, local_hour = await resolve_local_time(db, user_id)
    return {
        "local_hour": local_hour,
        "timezone": tz_name,
        "weekday": now.strftime("%A").lower(),
        "inside_quiet_hours": is_quiet_hour(local_hour),
        "probably_asleep": is_sleep_hour(local_hour),
    }


async def _presence(db, user_id: str, now: datetime) -> Dict[str, Any]:
    """Where they are, by the name they gave it. Never coordinates."""
    from places.service import PlacesService

    here = await PlacesService(db).where_now(user_id)
    if not here.get("at_a_known_place"):
        return {"at_a_known_place": False}
    seconds = here.get("seconds_here") or 0
    return {
        "at_a_known_place": True,
        "place": here.get("place"),
        "roughly_minutes_there": int(seconds // 60) if seconds else None,
    }


async def _commitments(db, user_id: str, now: datetime) -> Dict[str, Any]:
    """
    Whether they are inside something right now, by time overlap only.

    Never the title. What somebody is doing is not knowable from what they
    called the entry, and guessing produces confident nonsense.
    """
    from life_attention.context import calendar_occupancy

    occupancy = await calendar_occupancy(db, user_id, now)
    return {
        "in_something_now": bool(occupancy.get("busy_now")),
        "starting_within_two_hours": int(occupancy.get("upcoming_soon") or 0),
    }


async def _recent_interruptions(db, user_id: str, now: datetime) -> List[Dict[str, Any]]:
    """
    What has already cost them attention lately.

        Three pushes in twenty minutes from three different opportunities,
        each individually useful, is not three good decisions.

    Each one was right on its own and the fourth is wrong because of the
    first three — which is a fact about the day, not about any of them, and
    only visible from here.
    """
    since = (now - timedelta(hours=FATIGUE_WINDOW_HOURS)).isoformat()
    rows = await db.delivery_plans.find(
        {
            "owner_id": user_id,
            "status": "delivered",
            "delivered_at": {"$gte": since},
        },
        {"_id": 0, "delivered_at": 1, "mode": 1, "opportunity_id": 1, "outcome": 1},
    ).sort("delivered_at", -1).to_list(MAX_RECENT)
    return [
        {
            "when": r.get("delivered_at"),
            "how": r.get("mode"),
            "minutes_ago": _minutes_since(r.get("delivered_at"), now),
            "what_they_did": r.get("outcome") or "no reaction yet",
        }
        for r in rows
    ]


async def _recently_shown(db, user_id: str, now: datetime) -> List[Dict[str, Any]]:
    """What is already on their Home, so a push does not repeat a card."""
    rows = await db.opportunities.find(
        {"owner_id": user_id, "status": "active", "surface_state": "surfaced"},
        {"_id": 0, "semantic_summary": 1, "last_surfaced_at": 1, "seen_at": 1},
    ).to_list(MAX_RECENT)
    return [
        {
            "what": (r.get("semantic_summary") or "")[:120],
            "since": r.get("last_surfaced_at"),
            "already_seen": bool(r.get("seen_at")),
        }
        for r in rows
    ]


async def _refused(db, user_id: str, now: datetime) -> List[Dict[str, Any]]:
    rows = await db.opportunities.find(
        {"owner_id": user_id, "status": {"$in": ["dismissed", "suppressed"]}},
        {"_id": 0, "semantic_summary": 1, "status": 1},
    ).to_list(MAX_RECENT)
    return [
        {"what": (r.get("semantic_summary") or "")[:120], "how": r.get("status")}
        for r in rows
    ]


async def _permission(db, user_id: str, now: datetime) -> Dict[str, Any]:
    """
    Whether a push is even possible, and whether they asked not to be.

    A fact, not a veto — the veto is enforced in code afterwards. The model is
    told because a judgement made as though a push were available, when it is
    not, would choose silence where it should have chosen the screen.
    """
    from life_attention.context import notifications_allowed

    return {"push": bool(await notifications_allowed(db, user_id))}


async def _preferences(db, user_id: str, now: datetime) -> Dict[str, Any]:
    """
    What they said about being interrupted — as a fact, never as a switch.

        NO HARDCODE: `if level == "minimal": never_push()`.

    Somebody who asked for less noise has not asked to be kept in the dark
    about the one thing that would have mattered, and only a judgement can
    tell those apart. So their words travel here and the model weighs them
    against everything else.
    """
    from ambient.preferences import PreferenceService
    from life_attention.context import resolve_local_time

    prefs = await PreferenceService(db).get(user_id)
    local_hour = None
    try:
        _, _, local_hour = await resolve_local_time(db, user_id)
    except Exception:
        pass
    return prefs.for_ai(local_hour=local_hour)


async def _history(db, user_id: str, now: datetime) -> Dict[str, Any]:
    """
    How the last few notifications went, qualitatively.

        NO ENGAGEMENT OPTIMIZATION.

    There is no open rate here, no click-through, no score to maximise. What
    the model gets is the shape of a recent history — three sent today, two
    never opened, the last one opened straight away — because "I have told
    them this twice and they did not look" is a real reason to say it
    differently or not at all, and it is not available from any single plan.

    Counts, not ratios: a ratio is a metric, and a metric invites optimising.
    """
    since = (now - timedelta(days=HISTORY_DAYS)).isoformat()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    rows = await db.delivery_plans.find(
        {"owner_id": user_id, "delivered_at": {"$gte": since}},
        {"_id": 0, "delivered_at": 1, "outcome": 1, "opportunity_id": 1},
    ).sort("delivered_at", -1).to_list(20)

    opened = sum(1 for r in rows if r.get("outcome") == "opened")
    # Deliberately not called "dismissed": we usually cannot know that, and a
    # notification nobody opened is not a notification somebody refused.
    not_opened = sum(1 for r in rows if r.get("outcome") in (None, "delivered", "expired"))

    out: Dict[str, Any] = {
        "sent_in_the_last_days": len(rows),
        "sent_today": sum(1 for r in rows if (r.get("delivered_at") or "") >= today),
        "they_opened": opened,
        "they_did_not_open": not_opened,
        "minutes_since_the_last_one": _minutes_since(
            rows[0].get("delivered_at") if rows else None, now
        ),
    }

    try:
        from ambient.preferences import PreferenceService

        muted = await PreferenceService(db).suppressed_targets(user_id)
        if muted:
            out["they_asked_not_to_be_told_about"] = len(muted)
    except Exception:
        pass
    return out


def _hours_until(when: Optional[str], now: datetime) -> Optional[int]:
    """Counted here, so the model is never subtracting dates in its head."""
    if not when:
        return None
    try:
        moment = datetime.fromisoformat(str(when))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return max(0, int((moment - now).total_seconds() // 3600))


def _minutes_since(when: Optional[str], now: datetime) -> Optional[int]:
    if not when:
        return None
    try:
        moment = datetime.fromisoformat(str(when))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return max(0, int((now - moment).total_seconds() // 60))
