"""Last-resort, source-verified scheduling for an unambiguous *explicit* command.

The cognitive model owns task selection. If it has ALREADY selected the
schedule_situation_check capability as required, but burns its bounded
reasoning passes without ever calling it, this small repair may execute the
same governed capability on the person's exact command. It is never a generic
life-state classifier or an excuse to claim that the weather was observed.

Strict opt-in: one canonical Situation ID, an imperative to schedule a weather
check, and one relative minute interval. The original Situation's owner, event
date, locality, revision, active status, goal, source snapshot and pending wake
are read and verified. No new Situation, inferred GPS, provider weather call,
phone notification or external write is permitted.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from situations.history_identity import (
    authoritative_place,
    explicit_dates,
    location_matches,
    record_event_day,
)
from situations.repository import SituationRepository

_ID = re.compile(r"(?<!\w)sit_[0-9a-f]{16}(?!\w)", re.IGNORECASE)
_MINUTES = re.compile(r"\b(?:fra|tra)\s+(\d{1,2})\s+minut[oi]\b", re.IGNORECASE)
_SCHEDULE = re.compile(r"\b(?:programma|programmare|pianifica|imposta|fissa)\b", re.IGNORECASE)
_CHECK = re.compile(r"\b(?:controllo|verifica|ricontrollo)\b", re.IGNORECASE)
_NEGATED = re.compile(
    r"\b(?:non|evita|senza)\s+(?:\w+\s+){0,2}"
    r"(?:programmar[ea]?|programma|pianifica|fissa|imposta)\b",
    re.IGNORECASE,
)


def _candidate(message: str) -> tuple[str, int] | None:
    text = str(message or "")[:2000]
    found_ids = set(match.casefold() for match in _ID.findall(text))
    intervals = _MINUTES.findall(text)
    if (
        len(found_ids) != 1 or len(intervals) != 1
        or not _SCHEDULE.search(text) or not _CHECK.search(text)
        or not re.search(r"\bmeteo\b", text, re.IGNORECASE)
        or _NEGATED.search(text)
    ):
        return None
    minutes = int(intervals[0])
    if not (2 <= minutes <= 60):
        return None
    return next(iter(found_ids)), minutes


def _same_instant(left, right) -> bool:
    try:
        a = datetime.fromisoformat(str(left).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(right).replace("Z", "+00:00"))
        return bool(a.tzinfo and b.tzinfo and
                    a.astimezone(timezone.utc) == b.astimezone(timezone.utc))
    except (ValueError, TypeError):
        return False


async def recover_explicit_weather_schedule(
    db, owner: str, message: str, *, model_selected_capability: bool,
) -> dict[str, Any] | None:
    """Attempt exactly one missing, model-selected, consented soft write.

    None means no matching explicit command. A returned response is entirely
    backed by actual owner-scoped reads. Failed or ambiguous verification is
    never silently classified as a scheduled success.
    """
    if not model_selected_capability or db is None or not owner:
        return None
    matched = _candidate(message)
    if matched is None:
        return None
    sid, minutes = matched

    def failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False, "reason": reason,
            "text": (
                "Non ho confermato un nuovo controllo meteo per questa "
                "Situazione. " + reason
            ),
        }

    situation = await SituationRepository(db).get(owner, sid)
    if situation is None or situation.status not in ("active", "changed"):
        return failed("L'identificativo non è una Situazione attiva di questo account.")

    # The declared locality and event day are constraints, NOT fuzzy matches
    # against whichever recent laundry-like record is found first.
    date_query, date_error = explicit_dates(message)
    if date_error:
        return failed("La richiesta contiene più date e non posso sceglierne una.")
    if date_query:
        from timezone_service import user_clock_context
        clock = await user_clock_context(db, owner)
        event_day, _ = record_event_day(situation.model_dump(), clock["timezone"])
        if event_day != date_query:
            return failed("La data originale della Situazione non corrisponde alla richiesta.")

    spoken_place, place_error = authoritative_place(
        message, "", [situation.location_label],
    )
    if (place_error or not spoken_place
            or not location_matches(situation.location_label, spoken_place)):
        return failed("La località dichiarata non coincide con quella salvata.")

    from situations.followup import schedule_situation_check
    from conversation_engine.ai_core.models import Observation

    check_at = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
    observation: Observation = await schedule_situation_check(
        {
            "situation_id": sid,
            "expected_revision": situation.revision,
            "check_at": check_at,
            "purpose": "Controllare il meteo della Situazione esistente all'orario richiesto.",
            "completion_when": (
                "Valutare la prossima azione utile in base alla fonte meteo "
                "senza inventare che il processo fisico sia completato."
            ),
            "notify_when": (
                "Solo se la fonte conferma un rischio che richiede una decisione."
            ),
            "read_capability": "weather.read",
        },
        {"db": db, "user_id": owner, "user_message": message},
    )
    result = observation.payload or {}
    if observation.status != "ok" or result.get("status") not in (
        "scheduled", "due", "running",
    ):
        return failed(
            "Il sistema non ha restituito una sveglia confermata; "
            f"stato: {str(result.get('error') or result.get('status') or 'unavailable')[:65]}."
        )

    # Even an 'ok/reused' scheduling tool response is insufficient if the
    # existing goal never actually acquired the selected future source read.
    gid = str(result.get("goal_id") or "")
    raw = await db.agent_goals.find_one(
        {"id": gid, "owner_id": owner, "source_kind": "situation_followup",
         "source_refs": f"situation:{sid}"},
        {"_id": 0, "source_situation": 1, "next_run_at": 1},
    ) if gid else None
    source = (raw or {}).get("source_situation") or {}
    due = str(result.get("next_check_at") or "")
    if not (
        raw and source.get("situation_id") == sid
        and str(source.get("situation_revision") or "") == str(situation.revision)
        and source.get("checkpoint_read_capability") == "weather.read"
        and _same_instant(source.get("checkpoint_due_at"), due)
        and _same_instant(raw.get("next_run_at"), due)
    ):
        return failed(
            "La capacità di leggere il meteo all'orario previsto "
            "non risulta associata al controllo salvato."
        )
    wake = await db.ambient_wakes.find_one(
        {"owner_id": owner, "source_ref": f"goal:{gid}",
         "status": "pending", "scheduled_for": due},
        {"_id": 1},
    )
    if wake is None:
        return failed(
            "Non risulta una sveglia ancora eseguibile per l'orario dichiarato."
        )

    label = str(result.get("next_check_label") or "").strip()
    zone = str(result.get("timezone") or "").strip()
    if not label or not zone:
        return failed("La conferma manca dell'orario locale verificato.")
    return {
        "ok": True,
        "observation": observation,
        "situation_id": sid,
        "time": label,
        "text": (
            f"Ho programmato e verificato un controllo meteo per la Situazione "
            f"{sid}: {label} ({zone}). La sveglia è salvata e include la "
            "lettura reale weather.read. Il meteo non è stato ancora letto "
            "per questo controllo; nessuna asciugatura fisica o notifica "
            "esterna è stata confermata."
        ),
    }
