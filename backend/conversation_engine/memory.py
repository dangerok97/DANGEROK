"""Slot memory — never re-ask answered entities (Semantic + Intent + AE answers)."""
from __future__ import annotations

from typing import Any, Dict, Optional


def entities_to_slots(entities: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not entities or not isinstance(entities, dict):
        return {}
    slots: Dict[str, Any] = {}

    def _val(v: Any) -> Any:
        if isinstance(v, dict) and ("normalized" in v or "raw" in v):
            return v.get("normalized") if v.get("normalized") is not None else v.get("raw")
        return v

    # Study
    if entities.get("subject"):
        slots["subject"] = _val(entities["subject"])
        slots["confirm_subject"] = slots["subject"]
    if entities.get("exam"):
        slots["exam"] = _val(entities["exam"])
    if entities.get("exam_date"):
        slots["exam_date"] = _val(entities["exam_date"])
    # Travel
    dest = entities.get("travel") or entities.get("place") or entities.get("destination")
    if dest:
        slots["destination"] = _val(dest)
    if entities.get("departure") or entities.get("from"):
        slots["departure"] = _val(entities.get("departure") or entities.get("from"))
    if entities.get("departure_place"):
        slots["departure_place"] = _val(entities["departure_place"])
    if entities.get("departure_date") or entities.get("start_date"):
        slots["departure_date"] = _val(entities.get("departure_date") or entities.get("start_date"))
        slots["start_date"] = slots["departure_date"]
    if entities.get("return_date") or entities.get("end_date"):
        slots["return_date"] = _val(entities.get("return_date") or entities.get("end_date"))
        slots["end_date"] = slots["return_date"]
    period = entities.get("period") or entities.get("when") or entities.get("date_range")
    if period:
        slots["period"] = _val(period)
    elif slots.get("departure_date") and slots.get("return_date"):
        slots["period"] = {
            "start_date": str(slots["departure_date"])[:10],
            "end_date": str(slots["return_date"])[:10],
        }
    if entities.get("transport"):
        slots["transport"] = _val(entities["transport"])
    if entities.get("lodging"):
        slots["lodging"] = _val(entities["lodging"])
    if entities.get("companions"):
        slots["companions"] = _val(entities["companions"])
    # Medical / payment
    for k in (
        "appointment_type", "appointment_date", "appointment_time",
        "payee", "amount", "due_date", "time",
    ):
        if entities.get(k) is not None:
            slots[k] = _val(entities[k])
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
    out: Dict[str, Any] = {}
    for k, v in answers.items():
        if v is None:
            continue
        out[k] = v
        if k == "departure_date" and isinstance(v, dict):
            if v.get("departure_date") or v.get("start_date"):
                out["departure_date"] = v.get("departure_date") or v.get("start_date")
                out["start_date"] = out["departure_date"]
            if v.get("return_date") or v.get("end_date"):
                out["return_date"] = v.get("return_date") or v.get("end_date")
                out["end_date"] = out["return_date"]
        if k == "return_date" and isinstance(v, dict):
            if v.get("return_date") or v.get("end_date"):
                out["return_date"] = v.get("return_date") or v.get("end_date")
                out["end_date"] = out["return_date"]
        if k == "period" and isinstance(v, dict):
            out["period"] = v
            if v.get("start_date"):
                out.setdefault("departure_date", v["start_date"])
            if v.get("end_date"):
                out.setdefault("return_date", v["end_date"])
    return out


def should_skip_step(step_id: Optional[str], known: Dict[str, Any]) -> bool:
    if not step_id or not known:
        return False
    aliases = {
        "confirm_subject": ("confirm_subject", "subject"),
        "destination": ("destination",),
        "period": ("period",),
        "departure_date": ("departure_date", "start_date"),
        "return_date": ("return_date", "end_date"),
        "transport": ("transport",),
        "lodging": ("lodging",),
        "departure": ("departure", "departure_place"),
        "departure_place": ("departure", "departure_place"),
        "exam_date": ("exam_date",),
    }
    keys = aliases.get(step_id, (step_id,))
    return any(k in known and known[k] not in (None, "", []) for k in keys)
