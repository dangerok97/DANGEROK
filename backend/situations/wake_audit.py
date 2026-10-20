"""Read-only owner-scoped audit of background wake attempts for one Situation.

A wake ending 'completed' only proves the scheduler acknowledged a task.
It does NOT prove that weather was read or the person's desired outcome
was achieved. The caller must use the independently verified step/evidence
fields for those stronger claims. All timestamps and identities are stored
facts: never infer an attempt from model prose or from a similar title.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone


def _when(raw):
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except (TypeError, ValueError):
        return None


def _safe_result(value):
    text = str(value or "").strip().lower()
    # The last_error field is also used by Ambient to store a sanitized
    # result. Only expose known state-like codes, never raw error text.
    if re.fullmatch(r"[a-z][a-z0-9_]{0,79}", text):
        return text
    return "unavailable" if text else None


async def read_situation_wake_audit(db, owner: str, situation, *, limit=8) -> dict:
    """Read at most 12 recent scheduler records for the exact owned goal.

    Query matches owner_id AND goal-derived source_ref, not summary/title.
    The Situation must have been loaded from the owner's repository. Include
    only wakes scheduled at/after the recorded physical start when available,
    else the original Situation creation. Earlier lifecycle attempts are not
    evidence for this event instance. Returned dates are UTC timestamps;
    the assistant can use the owner's timezone for display.
    """
    from situations.followup import goal_id_for

    default = {
        "wake_audit_status": "unavailable",
        "wake_attempt_count": 0,
        "wake_attempts": [],
        "wake_audit_note": (
            "Nessuna prova di un controllo fisico o meteo emerge "
            "dalle sole sveglie del worker."
        ),
    }
    if db is None or not owner or situation is None or situation.user_id != owner:
        return default
    sid = str(situation.id or "")
    if not sid:
        return default
    gid = goal_id_for(owner, sid)
    floor = _when(situation.started_at) or _when(situation.created_at)
    cap = max(1, min(int(limit or 8), 12))
    try:
        records = await db.ambient_wakes.find(
            {"owner_id": owner, "source_ref": f"goal:{gid}"},
            {"_id": 0, "scheduled_for": 1, "status": 1, "attempts": 1,
             "claimed_at": 1, "completed_at": 1,
             "last_error": 1, "reason": 1},
        ).sort("scheduled_for", -1).limit(24).to_list(24)
        observed = []
        for rec in records:
            due = _when(rec.get("scheduled_for"))
            if due is None or (floor is not None and due < floor):
                continue
            # A scheduler retry is not a completed external inspection.
            result = _safe_result(rec.get("last_error"))
            observed.append({
                "scheduled_for": due.isoformat(),
                "worker_started_at": str(rec.get("claimed_at") or "")[:64] or None,
                "worker_finished_at": str(rec.get("completed_at") or "")[:64] or None,
                "worker_status": str(rec.get("status") or "")[:24],
                "worker_result": result,
                "attempts": min(max(0, int(rec.get("attempts") or 0)), 99),
                "proves_weather_or_physical_outcome": False,
            })
            if len(observed) >= cap:
                break
        # The result is intentionally NOT an assertion of full history:
        # Ambient has TTL retention and this is a bounded 24-row window.
        return {
            **default,
            "wake_audit_status": (
                "records_found" if observed else "no_records_in_bounded_history"
            ),
            "wake_attempt_count": len(observed),
            "wake_attempts": observed,
            "wake_audit_note": (
                "Sono registrate attività del worker per questa specifica "
                "Situazione. Anche worker_status=completed con "
                "worker_result=in_progress significa SOLO che il ciclo "
                "del worker è finito senza un esito finale verificato. "
                "Per accertare una lettura meteo completata serve un "
                "last_checked_at collegato a prove di fonte e località."
            ) if observed else (
                "Nessuna sveglia di questa Situazione è presente nell'archivio "
                "limitato consultato; non prova che sia stata cancellata "
                "automaticamente né che non sia mai esistita."
            ),
        }
    except Exception:
        # Avoid exposing provider exceptions and never guess a zero count
        # when the actual read failed.
        return {**default, "wake_audit_status": "storage_read_failed"}
