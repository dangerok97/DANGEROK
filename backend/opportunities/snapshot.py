"""
What ORA can say about a life, compactly, without handing over the life.

The model needs enough to judge and no more. Not a document, a summary of one;
not a coordinate, the name the person gave the place; not a history, the shape
of the recent past. Every field here exists because a judgement about whether
something is worth saying would be wrong without it.

    LOCATION IS CONTEXT, NOT A TRIGGER.
    EVENT != OPPORTUNITY.

So this file gathers facts and refuses to grade them. There is nothing here
that marks a calendar event as important, a deadline as pressing or a place as
significant — those are the judgements being delegated, and pre-judging them in
the payload would be the rule engine this sprint exists to avoid, hidden one
layer down.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# How far ahead is worth describing. Beyond a fortnight almost nothing is
# actionable today, and a longer window mostly adds noise to the payload.
HORIZON_DAYS = 14

# Per-source caps. A model given forty of anything reads the first few and
# guesses about the rest.
MAX_PER_SOURCE = 6


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def build(
    db, user_id: str, *, changes: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    A relevant life state snapshot: facts, bounded, unranked.

    Every source is best-effort. A domain that fails to answer leaves its part
    of the picture empty rather than failing the scan — the model is told what
    is missing, and a judgement made on less is still a judgement, whereas no
    judgement at all is a silence for the wrong reason.
    """
    now = _now()
    snapshot: Dict[str, Any] = {
        "now": now.isoformat(),
        "local_weekday": now.strftime("%A").lower(),
        "horizon_days": HORIZON_DAYS,
        # What moved since last time, when the caller knows. It focuses
        # attention; it never implies that a change is an opportunity.
        "what_changed": (changes or [])[:MAX_PER_SOURCE],
        "unavailable_sources": [],
    }

    for name, gather in (
        ("open_questions", _open_questions),
        ("recently_settled", _recently_settled),
        ("places", _places),
        ("presence", _presence),
        ("routines", _routines),
        ("open_comparisons", _comparisons),
        ("calendar", _calendar),
        ("existing_work", _existing_work),
    ):
        try:
            snapshot[name] = await gather(db, user_id, now)
        except Exception as e:
            logger.info("snapshot source %s unavailable: %s", name, type(e).__name__)
            snapshot[name] = []
            snapshot["unavailable_sources"].append(name)

    return snapshot


async def _open_questions(db, user_id: str, now: datetime) -> List[Dict[str, Any]]:
    """
    Things ORA asked and nobody has answered.

    The stake travels with the question. Without it a model sees only that
    something was asked, which says nothing about whether the answer still
    matters — and an unanswered question is not, by itself, a problem.
    """
    from waiting.repository import OpenQuestionRepository

    rows = await OpenQuestionRepository(db).list_open(user_id, limit=MAX_PER_SOURCE)
    return [
        {
            "ref": r.get("id"),
            "question": (r.get("question") or "")[:200],
            "why_it_matters": (r.get("why_needed") or "")[:200] or None,
            "about": (r.get("context_label") or "")[:80] or None,
            "asked_at": r.get("created_at"),
        }
        for r in rows
    ]


async def _recently_settled(db, user_id: str, now: datetime) -> List[Dict[str, Any]]:
    """
    Questions that were open and are not any more.

    Without this a snapshot only ever grows: something raised because an
    answer was missing would stay raised for ever, because the moment the
    answer arrives the question leaves `open` and disappears from view. A
    review that cannot see what got settled has nothing to settle anything
    with, so the answer travels here in the words it was given.
    """
    since = (now - timedelta(days=HORIZON_DAYS)).isoformat()
    rows = await db.open_questions.find(
        {
            "user_id": user_id,
            "status": {"$ne": "open"},
            "updated_at": {"$gte": since},
        },
        {"_id": 0, "id": 1, "question": 1, "answer_raw": 1, "context_label": 1,
         "answered_at": 1, "status": 1},
    ).sort("updated_at", -1).to_list(MAX_PER_SOURCE)
    return [
        {
            "ref": r.get("id"),
            "question": (r.get("question") or "")[:200],
            "answer": (r.get("answer_raw") or "")[:200] or None,
            "about": (r.get("context_label") or "")[:80] or None,
            "settled_at": r.get("answered_at") or None,
        }
        for r in rows
    ]


async def _places(db, user_id: str, now: datetime) -> List[Dict[str, Any]]:
    """
    The places the person named — names and roles, never coordinates.

    A model deciding whether something is worth saying does not need to know
    where anybody lives to a metre. It needs to know that "Casa" exists.
    """
    from places.service import PlacesService

    places = await PlacesService(db).list_places(user_id)
    return [
        {
            "ref": p.id,
            "name": p.label,
            "role": p.role if p.role_confirmed_by_user else None,
            "locality": p.locality or None,
        }
        for p in places[:MAX_PER_SOURCE]
    ]


async def _presence(db, user_id: str, now: datetime) -> Dict[str, Any]:
    """
    Where they are, if anywhere known, and for how long.

    Context, not a trigger. "Sei a casa" on its own means nothing, and the
    payload says as much by carrying no importance alongside it.
    """
    from places.service import PlacesService

    here = await PlacesService(db).where_now(user_id)
    if not here.get("at_a_known_place"):
        return {"at_a_known_place": False}
    seconds = here.get("seconds_here") or 0
    return {
        "at_a_known_place": True,
        "place": here.get("place"),
        "place_ref": here.get("place_id"),
        "roughly_minutes_there": int(seconds // 60) if seconds else None,
    }


async def _routines(db, user_id: str, now: datetime) -> List[Dict[str, Any]]:
    """Shapes the days keep taking, as the model itself once read them."""
    from places.service import PlacesService

    rows = await PlacesService(db).list_routines(user_id)
    return [
        {
            "ref": r.get("id"),
            "what": r.get("what_ora_thinks"),
            "weekdays": r.get("weekdays"),
            "state": r.get("state"),
        }
        for r in rows[:MAX_PER_SOURCE]
        if r.get("what_ora_thinks")
    ]


async def _comparisons(db, user_id: str, now: datetime) -> List[Dict[str, Any]]:
    """
    Choices ORA worked through, and whether one was made.

    A comparison with no chosen option is a fact about a decision, not a
    reason to push somebody towards making it.
    """
    rows = await db.comparison_runs.find(
        {"user_id": user_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(MAX_PER_SOURCE)
    out = []
    for r in rows:
        recommendation = r.get("recommendation") or {}
        out.append(
            {
                "ref": r.get("id"),
                "decision": ((r.get("need") or {}).get("decision") or "")[:160],
                "options": [
                    (a.get("name") or "")[:60] for a in (r.get("alternatives") or [])
                ][:4],
                "verdict": recommendation.get("verdict"),
                "chosen": bool(recommendation.get("chosen_alternative_id")),
                "at": r.get("created_at"),
            }
        )
    return out


async def _calendar(db, user_id: str, now: datetime) -> List[Dict[str, Any]]:
    """
    What is on the calendar within the horizon.

    Titles and times. No attendees, no locations, no descriptions: a judgement
    about whether an event needs preparing does not require reading who else
    is coming.
    """
    horizon = now + timedelta(days=HORIZON_DAYS)
    rows = await db.calendar_events.find(
        {
            "user_id": user_id,
            "start_at": {"$gte": now.isoformat(), "$lte": horizon.isoformat()},
        },
        {"_id": 0, "id": 1, "title": 1, "start_at": 1, "end_at": 1, "all_day": 1},
    ).sort("start_at", 1).to_list(MAX_PER_SOURCE)
    return [
        {
            "ref": r.get("id"),
            "title": (r.get("title") or "")[:120],
            "starts_at": r.get("start_at"),
            "in_days": _days_from_now(r.get("start_at"), now),
            "all_day": bool(r.get("all_day")),
        }
        for r in rows
    ]


def _days_from_now(when: Optional[str], now: datetime) -> Optional[int]:
    """
    How many days away, counted here rather than by the model.

    A model asked to reason about whether something matters should not also be
    subtracting dates in its head: it says "in three days" about the day after
    tomorrow and the sentence is wrong in the only part a person would check.
    Counting is arithmetic, and arithmetic belongs to the code.

    Days are counted the way a person counts them, on the calendar. Elapsed
    hours would call tomorrow morning "in 0 days" and something four days out
    "in 3", which is how a correct number still produces a wrong sentence.
    """
    if not when:
        return None
    try:
        start = datetime.fromisoformat(str(when))
    except ValueError:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return max(0, (start.date() - now.date()).days)


async def _existing_work(db, user_id: str, now: datetime) -> List[Dict[str, Any]]:
    """
    What is already on the person's plate.

    So the model can tell the difference between noticing something and
    repeating something they are already looking at.
    """
    rows = await db.home_snapshots.find(
        {"user_id": user_id}, {"_id": 0, "items": 1}
    ).sort("generated_at", -1).to_list(1)
    if not rows:
        return []
    out = []
    for item in (rows[0].get("items") or [])[:MAX_PER_SOURCE]:
        out.append(
            {
                "ref": item.get("id"),
                "title": (item.get("title") or "")[:120],
                "why": ((item.get("meta") or {}).get("work_reason")),
            }
        )
    return out


def evidence_refs(snapshot: Dict[str, Any]) -> Dict[str, str]:
    """
    Every reference the snapshot actually contains, by ref.

    The set an opportunity's evidence must be drawn from. A model that cites
    something absent from here has invented it, and the caller drops it —
    which is the whole reason this returns a lookup rather than a count.
    """
    found: Dict[str, str] = {}

    def take(kind: str, rows) -> None:
        for row in rows or []:
            ref = row.get("ref") if isinstance(row, dict) else None
            if ref:
                found[str(ref)] = kind

    take("open_question", snapshot.get("open_questions"))
    take("settled_question", snapshot.get("recently_settled"))
    take("place", snapshot.get("places"))
    take("routine", snapshot.get("routines"))
    take("comparison", snapshot.get("open_comparisons"))
    take("calendar_event", snapshot.get("calendar"))
    take("existing_work", snapshot.get("existing_work"))

    presence = snapshot.get("presence") or {}
    if presence.get("place_ref"):
        found[str(presence["place_ref"])] = "presence"

    for change in snapshot.get("what_changed") or []:
        if isinstance(change, dict) and change.get("ref"):
            found[str(change["ref"])] = str(change.get("kind") or "change")
    return found
