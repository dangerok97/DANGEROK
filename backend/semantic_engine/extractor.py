"""Semantic Extraction pipeline orchestration (deterministic first, Gemini optional)."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from semantic_engine import cache as sem_cache
from semantic_engine.context_merge import layer_from_raw, merge_entity_layers
from semantic_engine.deterministic import deterministic_extract
from semantic_engine.gap_analyzer import analyze_gaps
from semantic_engine.gemini_extractor import gemini_extract
from semantic_engine.models import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    EXTRACTION_VERSION,
    DEFAULT_TZ,
    EntityValue,
    ExtractionResult,
    GapAnalysisResult,
    now_iso,
)
from semantic_engine.normalizer import entities_to_known_slots

logger = logging.getLogger("ora.semantic_engine")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except Exception:
        return default


async def extract_semantics(
    text: str,
    *,
    intent: Optional[str] = None,
    flow: Optional[str] = None,
    confirmed_entities: Optional[Dict[str, Any]] = None,
    prior_entities: Optional[Dict[str, Any]] = None,
    corrections: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    use_gemini: Optional[bool] = None,
    user_preference: Optional[str] = None,
    timezone: str = DEFAULT_TZ,
    now: Optional[datetime] = None,
) -> ExtractionResult:
    high = _env_float("SEMANTIC_CONFIDENCE_HIGH", CONFIDENCE_HIGH)
    medium = _env_float("SEMANTIC_CONFIDENCE_MEDIUM", CONFIDENCE_MEDIUM)

    ck = sem_cache.cache_key(text, context, intent=intent, timezone=timezone)
    cached = sem_cache.get(ck)
    if cached and not corrections:
        try:
            er = ExtractionResult(**cached)
            er.cache_hit = True
            return er
        except Exception:
            pass

    # 1) Deterministic
    det = deterministic_extract(text, intent=intent, timezone=timezone, now=now)
    for ev in det.values():
        ev.source = "deterministic"

    # 2) Optional Gemini fill gaps only
    gemini_ents: Dict[str, EntityValue] = {}
    usage: Dict[str, Any] = {}
    used_gemini = False
    want_gemini = use_gemini if use_gemini is not None else (
        (os.environ.get("SEMANTIC_GEMINI_ENABLED") or "1").lower() in ("1", "true", "yes")
    )
    if want_gemini:
        try:
            gemini_ents, usage = await gemini_extract(
                text,
                intent=intent,
                known=entities_to_known_slots(det, min_confidence=medium),
                user_preference=user_preference,
                timezone=timezone,
            )
            used_gemini = bool(usage.get("ok"))
        except Exception as e:
            logger.info("gemini optional skipped: %s", type(e).__name__)
            usage = {"ok": False, "error": type(e).__name__}

    # Merge: confirmed > correction > current(det+gemini) > prior > …
    current_layer = {**gemini_ents, **det}  # det wins over gemini on same key if equal rank — force det higher
    # Actually: deterministic and gemini same rank 7 — prefer higher confidence; det first then gemini only fills missing
    filled = dict(det)
    for k, ev in gemini_ents.items():
        if k not in filled:
            filled[k] = ev
        elif filled[k].confidence < medium and ev.confidence >= filled[k].confidence:
            filled[k] = ev

    # Mark current_input source for merge ranking
    for ev in filled.values():
        if ev.source in ("deterministic", "gemini"):
            # keep source but merge uses current_input layer wrapper
            pass

    current_as_input = {}
    for k, ev in filled.items():
        e2 = ev.model_copy()
        e2.source = "current_input"
        current_as_input[k] = e2

    merged = merge_entity_layers(
        layer_from_raw(confirmed_entities, source="user_confirmed", timezone=timezone),
        layer_from_raw(corrections, source="manual_correction", timezone=timezone),
        current_as_input,
        layer_from_raw(prior_entities, source="prior_conversation", timezone=timezone),
        layer_from_raw((context or {}).get("document_entities"), source="document", timezone=timezone),
        layer_from_raw((context or {}).get("calendar_entities"), source="calendar", timezone=timezone),
        timezone=timezone,
    )

    # Restore original extraction source labels where not confirmed
    for k, ev in merged.items():
        if ev.source == "current_input" and k in filled:
            ev.source = filled[k].source

    known = entities_to_known_slots(merged, min_confidence=medium)
    ambiguous = [k for k, ev in merged.items() if ev.status == "ambiguous" or ev.needs_confirm(high=high, medium=medium)]

    flow_key = flow or intent or usage.get("flow_hint") or _infer_flow(text, intent, merged)
    gaps = analyze_gaps(flow_key, merged, intent=intent, high=high, medium=medium)

    reason = _reason_summary(text, merged, gaps)
    result = ExtractionResult(
        entities=merged,
        missing_slots=list(gaps.missing_required) + list(gaps.missing_conditional),
        ambiguous_slots=ambiguous or list(gaps.ambiguous_slots),
        known_slots=known,
        needs_clarification=bool(gaps.missing_required or ambiguous),
        reason_summary=reason,
        flow_hint=flow_key,
        intent_hint=intent,
        extraction_version=EXTRACTION_VERSION,
        extracted_at=now_iso(),
        used_gemini=used_gemini,
        cache_hit=False,
        usage=usage or {},
        meta={"next_slot": gaps.next_slot, "next_question": gaps.next_best_question},
    )
    sem_cache.set(ck, result.model_dump())
    return result


def analyze_only(
    flow: str,
    entities_raw: Dict[str, Any],
    *,
    intent: Optional[str] = None,
) -> GapAnalysisResult:
    from semantic_engine.normalizer import normalize_entity
    ents: Dict[str, EntityValue] = {}
    for k, v in (entities_raw or {}).items():
        ents[k] = normalize_entity(k, v)
    return analyze_gaps(flow or intent or "generic", ents, intent=intent)


def _infer_flow(text: str, intent: Optional[str], ents: Dict[str, EntityValue]) -> str:
    if intent:
        from semantic_engine.schemas import INTENT_TO_FLOW
        return INTENT_TO_FLOW.get(intent, intent)
    tl = (text or "").lower()
    # Strong domain cues first (avoid payment→travel via dates)
    if ents.get("payee") or "bolletta" in tl or "pagare" in tl:
        return "payment"
    if ents.get("appointment_type") or "dentista" in tl or "visita" in tl:
        return "medical"
    if ents.get("subject") or "esame" in tl:
        return "study"
    if ents.get("destination") or ents.get("departure_date") or "parto" in tl or "vacanza" in tl:
        return "travel"
    if ents.get("amount") and ("euro" in tl or "€" in tl):
        return "payment"
    return "generic"


def _reason_summary(text: str, ents: Dict[str, EntityValue], gaps: GapAnalysisResult) -> str:
    bits = []
    if ents.get("departure_date") and not ents.get("return_date"):
        bits.append("partenza nota senza rientro")
    if ents.get("destination"):
        bits.append("destinazione nota")
    if ents.get("subject"):
        bits.append("materia nota")
    if gaps.next_slot:
        bits.append(f"prossima domanda: {gaps.next_slot}")
    return "; ".join(bits) or "estrazione base"
