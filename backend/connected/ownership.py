"""
Whose commitment a calendar event is, asked from anywhere.

    AN APPOINTMENT SOMEBODY WAS INVITED TO IS SOMEBODY ELSE'S DECISION.

Sprint 1 recorded this on every signal and nothing read it. This is the read:
one question, answered from what the sensors already observed, so that the
authority ceiling can treat acting on somebody else's arrangement as what it
is — an act that reaches a third party.

Deliberately conservative in both directions. An event we have never observed
answers `unknown`, not `own`: assuming ownership is the assumption that would
let ORA move a meeting it was merely invited to. And `unknown` does not by
itself block anything — it means the caller must decide without this fact,
which is where it started.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("ora.connected.ownership")


async def relationship_for_event(db, owner_id: str, external_ref: str) -> str:
    """
    What the last observation said about whose event this is.

    Looked up by the provider's own handle, which is the only identity that
    survives between a calendar, an ingestion row and a signal.
    """
    if not owner_id or not external_ref:
        return "unknown"
    try:
        found = await db.connected_signals.find_one(
            {"owner_id": owner_id, "source_object_ref": str(external_ref)},
            {"_id": 0, "relationship": 1},
            sort=[("observed_at", -1)],
        )
    except Exception as e:
        logger.info("relationship read soft-fail: %s", type(e).__name__)
        return "unknown"
    return str((found or {}).get("relationship") or "unknown")


async def reaches_other_people(db, owner_id: str, calendar_ref: str) -> bool:
    """
    Whether acting on this event would reach somebody besides its owner.

        ORA DOES NOT REARRANGE OTHER PEOPLE'S DAYS.

    `shared` and `invited` both answer yes, for different reasons that lead to
    the same ceiling: one has other people on it, the other belongs to
    somebody else entirely. `own` and `unknown` answer no — `unknown` because
    a fact we do not have cannot be used to widen *or* narrow anything, and
    every other safeguard is still in front of the act.

    Takes ORA's own draft reference, resolves it to the provider handle the
    observations are keyed by, and asks. A draft with nothing on the provider
    yet is something ORA is making now, and nobody else is on it.
    """
    if not calendar_ref:
        return False
    try:
        draft = await db.calendar_event_drafts.find_one(
            {"id": str(calendar_ref), "user_id": owner_id},
            {"_id": 0, "google_event_id": 1},
        )
    except Exception as e:
        logger.info("draft read soft-fail: %s", type(e).__name__)
        return False
    handle = str((draft or {}).get("google_event_id") or "")
    if not handle:
        return False
    return await relationship_for_event(db, owner_id, handle) in ("shared", "invited")
