"""Slot memory — never re-ask answered entities (Intent + AE answers)."""
from __future__ import annotations

from typing import Any, Dict, Optional


def entities_to_slots(entities: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not entities or not isinstance(entities, dict):
        return {}
    slots: Dict[str, Any] = {}
    # Study
    if entities.get("subject"):
        slots["subject"] = entities["subject"]
        slots["confirm_subject"] = entities["subject"]
    if entities.get("exam"):
        slots["exam"] = entities["exam"]
    if entities.get("exam_date"):
        slots["exam_date"] = entities["exam_date"]
    # Travel
    dest = entities.get("travel") or entities.get("place") or entities.get("destination")
    if dest:
        slots["destination"] = dest
    if entities.get("departure") or entities.get("from"):
        slots["departure"] = entities.get("departure") or entities.get("from")
    period = entities.get("period") or entities.get("when") or entities.get("date_range")
    if period:
        slots["period"] = period
    if entities.get("companions"):
        slots["companions"] = entities["companions"]
    return slots


def merge_slots(*parts: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for p in parts:
        if p:
            out.update({k: v for k, v in p.items() if v is not None and v != ""})
    return out


def slots_from_ae_answers(answers: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not answers:
        return {}
    return {k: v for k, v in answers.items() if v is not None}


def should_skip_step(step_id: Optional[str], known: Dict[str, Any]) -> bool:
    if not step_id or not known:
        return False
    aliases = {
        "confirm_subject": ("confirm_subject", "subject"),
        "destination": ("destination",),
        "period": ("period",),
        "departure": ("departure", "departure_place"),
        "departure_place": ("departure", "departure_place"),
        "exam_date": ("exam_date",),
    }
    keys = aliases.get(step_id, (step_id,))
    return any(k in known and known[k] not in (None, "", []) for k in keys)
