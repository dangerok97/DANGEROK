"""
One-time reminders that actually remind.

Audit 26/10/2026: the guided flows ("ricordamelo un'ora prima" on an
appointment, study revisions, travel steps) wrote a row in `reminders` with a
`due_at`, and Home showed it. Nothing ever read `due_at`: no wake, no
notification. A reminder the person asked for and never receives is the
opposite of autonomy.

This lane does for a one-time reminder what the recurring memo lane does for
a birthday: when the moment arrives it raises one ordinary Opportunity
(decided by the person, not by a model) and the existing delivery pipeline
decides how it reaches them. Before every send Delivery re-reads the row, so
a reminder completed or deleted in the meantime is never sent.

A reminder whose moment passed long ago (ORA was stopped, or the row predates
this lane) is marked missed, never announced late as if it were now.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("ora.memos.one_shot")

COLLECTION = "reminders"
SOURCE_CONTEXT = "one_shot_reminder"
OPEN = ("open", "active", "pending")
# Late by more than this is missed: a reminder is about a moment.
LATE_GRACE_MINUTES = 45
# How long after its moment the notification may still be useful.
VALID_HOURS = 6
MAX_PER_PASS = 20
# How long a reminder that was told stays in Home.
SHOWN_AFTER_HOURS = 12


def _moment(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    # A naive moment was written by our own code with datetime.utcnow-style
    # values; treat it as UTC rather than guessing a local zone.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _due(row: Dict[str, Any]) -> Optional[datetime]:
    return _moment(row.get("due_at") or row.get("remind_at"))


async def fire_due(db, *, now: Optional[datetime] = None) -> Dict[str, int]:
    from opportunities.models import EvidenceRef, Opportunity
    from opportunities.repository import OpportunityRepository

    moment = now or datetime.now(timezone.utc)
    out = {"due": 0, "raised": 0, "missed": 0}
    # Strings are compared loosely here (offsets differ); the exact test is
    # done on parsed instants below. One day of slack covers any offset.
    rows = await db[COLLECTION].find(
        {"status": {"$in": list(OPEN)}, "notified_state": {"$exists": False},
         "$or": [{"due_at": {"$lte": (moment + timedelta(days=1)).isoformat()}},
                 {"remind_at": {"$lte": (moment + timedelta(days=1)).isoformat()}}]},
        {"_id": 0},
    ).limit(MAX_PER_PASS * 3).to_list(MAX_PER_PASS * 3)
    repo = OpportunityRepository(db)
    for row in rows:
        due = _due(row)
        owner = str(row.get("user_id") or "")
        rid = str(row.get("id") or "")
        if due is None or due > moment or not owner or not rid:
            continue
        out["due"] += 1
        late = moment - due > timedelta(minutes=LATE_GRACE_MINUTES)
        superseded = False
        if not late:
            from situations.stated_time import already_said
            superseded = await already_said(db, owner, row)
        claimed = await db[COLLECTION].find_one_and_update(
            {"id": rid, "user_id": owner, "status": {"$in": list(OPEN)},
             "notified_state": {"$exists": False}},
            {"$set": {"notified_state": "missed" if late else "superseded" if superseded else "raised",
                      "notified_at": moment.isoformat()}},
        )
        if not claimed:
            continue  # another instance, or closed in the meantime
        if late:
            out["missed"] += 1
            continue
        if superseded:
            # The watch already said it, or the Situation is over: once is enough.
            out["superseded"] = out.get("superseded", 0) + 1
            continue
        title = str(row.get("title") or "Promemoria").strip()[:280]
        body = str(row.get("body") or row.get("description") or "").strip()
        opportunity = Opportunity(
            owner_id=owner,
            identity_key=f"{SOURCE_CONTEXT}:{rid}",
            status="active",
            semantic_summary=title,
            why_it_matters=("Mi avevi chiesto di fare questa telefonata."
                            if row.get("origin") == "phone_call_result" else "Mi hai chiesto di ricordartelo."),
            why_now=(f"È il momento: {title}" + (f" — {body}" if body else ""))[:400],
            relevance="high",
            urgency="urgent",
            time_sensitivity="perishable",
            confidence="strong",
            initiative="inform",
            what_ora_can_do="Ricordartelo adesso.",
            evidence=[EvidenceRef(kind="phone_call" if row.get("origin") == "phone_call_result" else "reminder",
                                  ref=rid, summary=title[:240])],
            source_context=SOURCE_CONTEXT,
            decision_provenance="user",
            valid_until=(due + timedelta(hours=VALID_HOURS)).isoformat(),
            surface_state="surfaced",
            surface_rationale="Promemoria richiesto dalla persona.",
        )
        await repo.save(opportunity)
        out["raised"] += 1
        if out["raised"] >= MAX_PER_PASS:
            break
    # Told (or missed) more than half a day ago: no longer a thing to show
    # in Home. Kept, not deleted.
    try:
        await db[COLLECTION].update_many(
            {"status": {"$in": list(OPEN)}, "notified_state": {"$in": ["raised", "missed", "superseded"]},
             "notified_at": {"$lte": (moment - timedelta(hours=SHOWN_AFTER_HOURS)).isoformat()}},
            {"$set": {"status": "past", "updated_at": moment.isoformat()}})
    except Exception as exc:
        logger.info("one_shot past sweep deferred: %s", type(exc).__name__)
    if out["due"]:
        logger.info("one_shot_reminders %s", out)
    return out


async def reminder_opportunity_current(db, subject: Any) -> bool:
    """Delivery's last-mile check: the reminder still exists and is open."""
    if str(getattr(subject, "source_context", "") or "") != SOURCE_CONTEXT:
        return True
    owner = str(getattr(subject, "owner_id", "") or "")
    key = str(getattr(subject, "identity_key", "") or "")
    if not owner or not key.startswith(SOURCE_CONTEXT + ":"):
        return False
    rid = key.split(":", 1)[1]
    try:
        row = await db[COLLECTION].find_one(
            {"id": rid, "user_id": owner}, {"_id": 0, "status": 1, "due_at": 1, "remind_at": 1})
    except Exception:
        return False
    return bool(row and row.get("status") in OPEN and _due(row) is not None)


def push_decision(subject: Any) -> Dict[str, Any]:
    """The delivery decision the person made when they asked for the reminder."""
    summary = str(getattr(subject, "semantic_summary", "") or "Promemoria")
    call = any(getattr(e, "kind", "") == "phone_call" for e in getattr(subject, "evidence", []) or [])
    if call:
        return {
            "mode": "push", "timing": "now",
            "reason_to_interrupt": "Mi avevi chiesto di fare questa telefonata: ecco com'è andata.",
            "reason_to_open": "L'esito della telefonata.",
            "what_decided_the_mode": "telefonata richiesta dalla persona",
            "confidence": "strong", "sensitivity": "personal", "requires_recheck": True,
            "copy": {"title": "Telefonata conclusa", "body": summary[:200],
                     "public_title": "Telefonata conclusa", "public_body": "Apri ORA per l'esito."},
        }
    return {
        "mode": "push", "timing": "now",
        "reason_to_interrupt": "Mi avevi chiesto di ricordartelo a quest'ora.",
        "reason_to_open": "Il promemoria che hai chiesto.",
        "what_decided_the_mode": "promemoria richiesto dalla persona",
        "confidence": "strong", "sensitivity": "personal", "requires_recheck": True,
        "copy": {"title": "Promemoria", "body": summary[:200],
                 "public_title": "Promemoria", "public_body": "Apri ORA per vederlo."},
    }
