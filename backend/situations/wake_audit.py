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
from zoneinfo import ZoneInfo


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


async def read_situation_wake_audit(
    db, owner: str, situation, *, limit=8, timezone_name: str = "UTC",
) -> dict:
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
        zone = ZoneInfo(str(timezone_name or "UTC"))
        zone_name = str(timezone_name or "UTC")
    except (TypeError, ValueError, KeyError):
        zone = timezone.utc
        zone_name = "UTC"
    try:
        records = await db.ambient_wakes.find(
            {"owner_id": owner, "source_ref": f"goal:{gid}"},
            {"_id": 0, "scheduled_for": 1, "status": 1, "attempts": 1,
             "claimed_at": 1, "completed_at": 1,
             "last_error": 1, "reason": 1},
        ).limit(48).to_list(48)
        # Historical alarms can still carry different offsets. Never sort
        # their raw ISO strings as clock instants; parse then sort by UTC.
        dated = sorted(
            ((instant, rec) for rec in records
             if (instant := _when(rec.get("scheduled_for"))) is not None),
            key=lambda pair: pair[0], reverse=True,
        )
        observed = []
        for due, rec in dated:
            if floor is not None and due < floor:
                continue
            # An acknowledged worker is not a completed weather observation.
            started, finished = _when(rec.get("claimed_at")), _when(rec.get("completed_at"))
            result = _safe_result(rec.get("last_error"))
            early = started is not None and started < due
            recorded = {
                "scheduled_for": due.isoformat(),
                "scheduled_for_utc": due.isoformat(),
                "scheduled_for_local": due.astimezone(zone).isoformat(),
                "scheduled_for_local_label": (
                    due.astimezone(zone).strftime("%d/%m/%Y %H:%M:%S") + f" ({zone_name})"
                ),
                "timezone": zone_name,
                "worker_started_at": started.isoformat() if started else None,
                "worker_started_at_utc": started.isoformat() if started else None,
                "worker_started_at_local": started.astimezone(zone).isoformat() if started else None,
                "worker_finished_at": finished.isoformat() if finished else None,
                "worker_finished_at_utc": finished.isoformat() if finished else None,
                "worker_finished_at_local": finished.astimezone(zone).isoformat() if finished else None,
                "time_consistency": (
                    "worker_started_before_due" if early else
                    "not_started" if started is None else "normal"
                ),
                "worker_status": str(rec.get("status") or "")[:24],
                "worker_result": result,
                "attempts": min(max(0, int(rec.get("attempts") or 0)), 99),
                "proves_weather_or_physical_outcome": False,
            }
            observed.append(recorded)
            if len(observed) >= cap:
                break
        # This is a bounded view: neither a complete lifelong audit nor
        # proof of an external check. Provide one code-owned chronology so
        # the LLM cannot relabel local wall-clock values as "UTC".
        chronology = " ".join(
            f"{n + 1}) previsto {row['scheduled_for_local_label']} "
            f"= {row['scheduled_for_utc']} UTC; "
            f"worker {row['worker_started_at_local'] or 'non partito'}; "
            f"stato {row['worker_status']}; risultato "
            f"{row['worker_result'] or 'nessun esito'}."
            for n, row in enumerate(observed[:6])
        )
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
                "last_checked_at collegato a prove di fonte e località. "
                "Orari nel resoconto: formato locale con fuso esplicito, "
                "poi lo stesso istante UTC. " + chronology
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
