"""Semantic Engine service facade."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from semantic_engine.context_merge import apply_confirmation, apply_correction, layer_from_raw
from semantic_engine.extractor import analyze_only, extract_semantics
from semantic_engine.gap_analyzer import analyze_gaps
from semantic_engine.gemini_extractor import optional_rephrase_question
from semantic_engine.models import (
    EXTRACTION_VERSION,
    ExtractionResult,
    GapAnalysisResult,
    DEFAULT_TZ,
)
from semantic_engine.normalizer import entities_to_known_slots, normalize_entity


class SemanticEngineService:
    def __init__(self) -> None:
        self.version = EXTRACTION_VERSION

    @property
    def enabled(self) -> bool:
        return (os.environ.get("SEMANTIC_ENGINE_ENABLED") or "1").lower() in ("1", "true", "yes")

    async def extract(
        self,
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
    ) -> ExtractionResult:
        if not self.enabled:
            return ExtractionResult(reason_summary="semantic_engine_disabled")
        return await extract_semantics(
            text,
            intent=intent,
            flow=flow,
            confirmed_entities=confirmed_entities,
            prior_entities=prior_entities,
            corrections=corrections,
            context=context,
            use_gemini=use_gemini,
            user_preference=user_preference,
            timezone=timezone,
        )

    async def gaps(
        self,
        *,
        flow: Optional[str] = None,
        intent: Optional[str] = None,
        entities: Optional[Dict[str, Any]] = None,
        text: Optional[str] = None,
        confirmed_entities: Optional[Dict[str, Any]] = None,
        use_gemini: Optional[bool] = None,
        user_preference: Optional[str] = None,
        timezone: str = DEFAULT_TZ,
    ) -> Dict[str, Any]:
        extraction: Optional[ExtractionResult] = None
        if text:
            extraction = await self.extract(
                text,
                intent=intent,
                flow=flow,
                confirmed_entities=confirmed_entities,
                use_gemini=use_gemini,
                user_preference=user_preference,
                timezone=timezone,
            )
            ents = extraction.entities
            flow_key = flow or extraction.flow_hint or intent or "generic"
        else:
            from semantic_engine.context_merge import merge_entity_layers
            ents = merge_entity_layers(
                layer_from_raw(confirmed_entities, source="user_confirmed", timezone=timezone),
                {k: normalize_entity(k, v, timezone=timezone) for k, v in (entities or {}).items()},
                timezone=timezone,
            )
            flow_key = flow or intent or "generic"

        gap = analyze_gaps(flow_key, ents, intent=intent)
        if gap.next_best_question and gap.next_slot:
            rephrased = await optional_rephrase_question(
                gap.next_best_question, slot=gap.next_slot, user_preference=user_preference,
            )
            if rephrased:
                gap.next_best_question = rephrased

        out: Dict[str, Any] = {"gaps": gap.public(), "ok": True}
        if extraction:
            out["extraction"] = extraction.public()
        return out

    def confirm_entity(
        self,
        entities: Dict[str, Any],
        slot: str,
        value: Any,
        *,
        timezone: str = DEFAULT_TZ,
    ) -> Dict[str, Any]:
        from semantic_engine.normalizer import normalize_entity
        current = {k: normalize_entity(k, v, timezone=timezone) for k, v in (entities or {}).items()}
        updated = apply_confirmation(current, slot, value, timezone=timezone)
        return {
            "entities": {k: v.model_dump() for k, v in updated.items()},
            "known_slots": entities_to_known_slots(updated),
        }

    def correct_entity(
        self,
        entities: Dict[str, Any],
        slot: str,
        value: Any,
        *,
        timezone: str = DEFAULT_TZ,
    ) -> Dict[str, Any]:
        from semantic_engine.normalizer import normalize_entity
        current = {k: normalize_entity(k, v, timezone=timezone) for k, v in (entities or {}).items()}
        updated = apply_correction(current, slot, value, timezone=timezone)
        return {
            "entities": {k: v.model_dump() for k, v in updated.items()},
            "known_slots": entities_to_known_slots(updated),
        }


_svc: Optional[SemanticEngineService] = None


def get_semantic_engine() -> SemanticEngineService:
    global _svc
    if _svc is None:
        _svc = SemanticEngineService()
    return _svc
