"""Gap Analyzer — declarative slots → next best question (no static sequences)."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from semantic_engine.models import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    EntityValue,
    GapAnalysisResult,
    QuestionChip,
)
from semantic_engine.normalizer import entities_to_known_slots
from semantic_engine.schemas import schema_for
from semantic_engine.schemas.base import FlowSlotSchema, SlotDef


def _has(known: Dict[str, Any], slot: SlotDef) -> bool:
    keys = [slot.name, *slot.aliases]
    for k in keys:
        v = known.get(k)
        if v is not None and v != "" and v != []:
            return True
    return False


def _get(known: Dict[str, Any], *names: str) -> Any:
    for n in names:
        if known.get(n) not in (None, "", []):
            return known[n]
    return None


def _condition(name: Optional[str], known: Dict[str, Any], entities: Dict[str, EntityValue]) -> bool:
    if not name:
        return True
    if name == "departure_known_return_missing":
        return bool(_get(known, "departure_date", "start_date")) and not _get(
            known, "return_date", "end_date"
        )
    if name == "core_travel_known":
        return bool(
            _get(known, "destination", "travel", "place")
            and _get(known, "departure_date", "start_date")
            and _get(known, "return_date", "end_date")
            and _get(known, "transport")
        )
    if name == "date_known_time_missing":
        return bool(_get(known, "appointment_date", "date", "exam_date")) and not _get(
            known, "appointment_time", "time"
        )
    if name == "core_study_known":
        return bool(_get(known, "subject", "exam") and _get(known, "exam_date", "date"))
    if name == "core_medical_known":
        return bool(
            _get(known, "appointment_type")
            and _get(known, "appointment_date", "date")
        )
    return True


def _label_for(entities: Dict[str, EntityValue], known: Dict[str, Any], key: str) -> str:
    ev = entities.get(key)
    if ev and ev.label:
        return ev.label
    v = known.get(key)
    if isinstance(v, dict):
        return str(v.get("label") or v.get("start_date") or v)
    return str(v) if v is not None else ""


def render_template(template: str, entities: Dict[str, EntityValue], known: Dict[str, Any]) -> str:
    def repl(m: re.Match) -> str:
        key = m.group(1)
        if key.endswith("_label"):
            base = key[: -len("_label")]
            return _label_for(entities, known, base) or _label_for(
                entities, known, base.replace("departure_date", "start_date")
            )
        return str(_get(known, key) or "")

    return re.sub(r"\{(\w+)\}", repl, template)


def analyze_gaps(
    flow: str,
    entities: Dict[str, EntityValue],
    *,
    intent: Optional[str] = None,
    high: float = CONFIDENCE_HIGH,
    medium: float = CONFIDENCE_MEDIUM,
) -> GapAnalysisResult:
    schema: FlowSlotSchema = schema_for(flow or intent or "generic")
    known = entities_to_known_slots(entities, min_confidence=medium)
    ambiguous: List[str] = []
    for k, ev in entities.items():
        if ev.status == "ambiguous" or ev.needs_confirm(high=high, medium=medium):
            if k not in ambiguous:
                ambiguous.append(k)

    missing_required: List[str] = []
    missing_conditional: List[str] = []
    missing_optional: List[str] = []

    for slot in schema.slots:
        if _has(known, slot):
            continue
        if slot.kind == "required":
            missing_required.append(slot.name)
        elif slot.kind == "conditional":
            if _condition(slot.when, known, entities):
                missing_conditional.append(slot.name)
        elif slot.kind == "optional":
            missing_optional.append(slot.name)

    next_slot: Optional[SlotDef] = None
    travel_like = schema.flow in ("travel", "vacation")

    # Travel: departure known & destination missing → destination first (NEVER combo date Q)
    if travel_like and _get(known, "departure_date", "start_date") and not _get(
        known, "destination", "travel", "place"
    ):
        next_slot = schema.slot_map().get("destination")
    # Full trip known → lodging before re-asking dates/place/transport
    elif travel_like and _condition("core_travel_known", known, entities) and not _get(
        known, "lodging", "accommodation", "bookings"
    ):
        next_slot = schema.slot_map().get("lodging")
    else:
        # Required first, then conditional (active), never optional until core done
        for slot in schema.slots:
            if slot.name not in missing_required:
                continue
            next_slot = slot
            break
        if next_slot is None:
            for slot in schema.slots:
                if slot.name not in missing_conditional:
                    continue
                if slot.when and not _condition(slot.when, known, entities):
                    continue
                # return only after destination when departure known
                if (
                    slot.name == "return_date"
                    and travel_like
                    and not _get(known, "destination", "travel", "place")
                ):
                    continue
                next_slot = slot
                break

    question = None
    reason = None
    chips: List[QuestionChip] = []
    if next_slot:
        question = render_template(next_slot.question_template, entities, known)
        # Hard ban on the screenshot bug phrasing
        if question and "quando parti e quando torni" in question.lower():
            if _get(known, "departure_date", "start_date"):
                rd = schema.slot_map().get("return_date")
                if rd:
                    next_slot = rd
                    question = render_template(rd.question_template, entities, known)
            else:
                question = "Quando parti?"
        reason = next_slot.question_reason
        chips = list(next_slot.chips)

    completion_ready = True
    for c in schema.completion:
        slot = schema.slot_map().get(c)
        if slot and not _has(known, slot):
            completion_ready = False
            break
        if not slot and not _get(known, c):
            completion_ready = False
            break

    summary_parts = []
    if known:
        summary_parts.append(f"noti: {', '.join(list(known.keys())[:6])}")
    if missing_required:
        summary_parts.append(f"mancano: {', '.join(missing_required[:6])}")
    if next_slot:
        summary_parts.append(f"prossima: {next_slot.name}")

    return GapAnalysisResult(
        flow=schema.flow,
        domain=schema.flow,
        known_slots=known,
        missing_required=missing_required,
        missing_conditional=missing_conditional,
        missing_optional=missing_optional,
        ambiguous_slots=ambiguous,
        next_best_question=question,
        next_slot=next_slot.name if next_slot else None,
        question_reason=reason,
        suggested_chips=chips,
        completion_ready=completion_ready and not missing_required,
        reason_summary="; ".join(summary_parts) or "nessun gap",
    )


def render_contextual_question(gap: GapAnalysisResult) -> Optional[str]:
    return gap.next_best_question
