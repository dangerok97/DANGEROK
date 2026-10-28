"""
A finished thing is closed, by the person or, after a while, by ORA.

28/10/2026: the clothes of 27/10 were announced at 22:08 and never marked as
taken in. The watch went on all night and all the next day; the self-check
re-armed it five times. Nothing was wrong except that nobody had said "done".

Two ways a Situation ends now:
* the person taps «Fatto» on the reminder that told them: the Situation is
  resolved at that moment, and that moment is a real data point;
* ORA's final notice was given hours ago (or the watch itself concluded the
  outcome was reached long ago) and nobody said anything: ORA closes it and
  writes down that it was ORA, so the closing time is never taken for the
  person's.

Closing goes through the ordinary Situation service: the watch is withdrawn,
the experience is recorded, the reminders are disarmed.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)

# After ORA's final notice, how long a Situation may stay open unanswered.
AFTER_NOTICE_HOURS = 6
# After the watch itself concluded the outcome was reached.
AFTER_OUTCOME_HOURS = 12


def _moment(value) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def close(db, owner: str, situation_id: str, *, by: str, fact: str) -> bool:
    """Resolve one Situation. `by` is "person" or "ora". Never raises."""
    try:
        from situations.models import SituationUpdate
        from situations.service import SituationService

        result = await SituationService(db).apply(
            user_id=owner, session_id=f"ora_close_{by}",
            update=SituationUpdate(
                operation="resolve", situation_id=situation_id, facts=[fact[:280]],
                source="user_conversation" if by == "person" else "inferred",
            ),
            reasoning_epoch=f"close:{situation_id}:{by}",
        )
        return result.get("status") == "success"
    except Exception as exc:
        logger.info("situation close deferred: %s", type(exc).__name__)
        return False


async def close_finished(db, owner: str, *, now: Optional[datetime] = None) -> List[dict]:
    """Self-check: close what was told long ago and never closed."""
    now = now or datetime.now(timezone.utc)
    out: List[dict] = []
    rows = await db.situations.find(
        {"user_id": owner, "status": {"$in": ["active", "changed"]}},
        {"_id": 0, "id": 1, "updated_at": 1}).to_list(30)
    for row in rows:
        sid = row["id"]
        why = None
        told = await db.reminders.find_one(
            {"user_id": owner, "id": f"rem_sit_{sid}"[:80], "notified_state": "raised"},
            {"_id": 0, "notified_at": 1})
        told_at = _moment((told or {}).get("notified_at"))
        if told_at and now - told_at >= timedelta(hours=AFTER_NOTICE_HOURS):
            # A newer «non ancora» keeps it open until that reminder is told too.
            pending = await db.reminders.find_one(
                {"user_id": owner, "meta.situation_id": sid, "status": "open",
                 "meta.kind": {"$ne": "rain_risk"}, "notified_state": {"$exists": False}}, {"_id": 1})
            if not pending:
                why = f"l'ultimo avviso è delle {told_at.astimezone(timezone.utc).strftime('%H:%M')} UTC"
        if why is None:
            goal = await db.agent_goals.find_one(
                {"owner_id": owner, "source_refs": f"situation:{sid}"},
                {"_id": 0, "situation_outcome": 1, "updated_at": 1}, sort=[("updated_at", -1)])
            outcome = (goal or {}).get("situation_outcome") or {}
            reached = _moment(outcome.get("assessed_at") or (goal or {}).get("updated_at"))
            if (outcome.get("action_reason") == "outcome_ready" and reached
                    and now - reached >= timedelta(hours=AFTER_OUTCOME_HOURS)):
                why = "la sorveglianza aveva concluso che l'esito era raggiunto"
        if why is None:
            continue
        if await close(db, owner, sid, by="ora",
                       fact=f"Chiusa da ORA perché nessuno l'aveva chiusa: {why}. L'ora di chiusura non è un dato della persona."):
            out.append({"code": "situation_auto_closed", "ref": f"situation:{sid}", "repaired": True})
    return out
