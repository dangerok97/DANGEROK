"""Validated Pydantic contracts for Semantic Extraction + Gap Analyzer."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

EXTRACTION_VERSION = "semantic-engine-1.0"
PROMPT_VERSION = "semantic-prompt-1.0"
DEFAULT_TZ = "Europe/Rome"

CONFIDENCE_HIGH = 0.85
CONFIDENCE_MEDIUM = 0.60
CONFIDENCE_MID = CONFIDENCE_MEDIUM  # alias

SOURCE_PRECEDENCE = {
    "user_confirmed": 1,
    "confirmed_user": 1,
    "manual_correction": 2,
    "current_input": 3,
    "prior_conversation": 4,
    "document": 5,
    "calendar": 6,
    "deterministic": 7,
    "gemini": 7,
    "inference": 7,
    "default": 8,
}

EntityStatus = Literal[
    "known",
    "extracted",
    "normalized",
    "confirmed",
    "corrected",
    "inferred",
    "ambiguous",
    "missing",
    "low_confidence",
]

EntitySource = Literal[
    "current_input",
    "prior_conversation",
    "user_confirmed",
    "confirmed_user",
    "manual_correction",
    "document",
    "calendar",
    "inference",
    "default",
    "gemini",
    "deterministic",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class QuestionChip(BaseModel):
    id: str
    label: str
    value: Any = None


class EntityValue(BaseModel):
    """Structured entity — {raw, normalized, confidence, status, source}."""

    raw: Optional[Any] = None
    normalized: Optional[Any] = None
    confidence: float = 0.0
    status: EntityStatus = "known"
    source: EntitySource = "deterministic"
    timezone: Optional[str] = None
    ambiguity: Optional[Dict[str, Any]] = None
    ambiguous: bool = False
    candidates: List[Any] = Field(default_factory=list)
    label: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)

    def is_high(self, high: float = CONFIDENCE_HIGH) -> bool:
        return self.confidence >= high and self.status not in ("ambiguous", "missing", "low_confidence")

    def is_mid(self, high: float = CONFIDENCE_HIGH, medium: float = CONFIDENCE_MEDIUM) -> bool:
        return medium <= self.confidence < high and self.status not in ("ambiguous", "missing")

    def usable(self, medium: float = CONFIDENCE_MEDIUM) -> bool:
        return (
            self.confidence >= medium
            and self.status not in ("ambiguous", "missing", "low_confidence")
            and self.normalized is not None
        )

    def is_usable(self, *, high: float = CONFIDENCE_HIGH, medium: float = CONFIDENCE_MEDIUM) -> bool:
        if self.status in ("confirmed", "corrected"):
            return True
        if self.status in ("ambiguous", "missing", "low_confidence") or self.ambiguous:
            return False
        return self.confidence >= medium

    def needs_confirm(self, high: float = CONFIDENCE_HIGH, medium: float = CONFIDENCE_MEDIUM) -> bool:
        if self.status == "ambiguous" or self.ambiguous:
            return True
        if self.status in ("confirmed", "corrected"):
            return False
        return medium <= self.confidence < high

    def flat_known_value(self) -> Any:
        return self.normalized if self.normalized is not None else self.raw


class ExtractionResult(BaseModel):
    entities: Dict[str, EntityValue] = Field(default_factory=dict)
    missing_slots: List[str] = Field(default_factory=list)
    ambiguous_slots: List[str] = Field(default_factory=list)
    known_slots: Dict[str, Any] = Field(default_factory=dict)
    needs_clarification: bool = False
    reason_summary: str = ""
    flow_hint: Optional[str] = None
    intent_hint: Optional[str] = None
    domain: Optional[str] = None
    subtype: Optional[str] = None
    domain_confidence: float = 0.0
    extraction_version: str = EXTRACTION_VERSION
    extracted_at: str = Field(default_factory=now_iso)
    used_gemini: bool = False
    cache_hit: bool = False
    usage: Dict[str, Any] = Field(default_factory=dict)
    source_engine: str = "deterministic"
    input_hash: Optional[str] = None
    privacy_redacted: bool = True
    meta: Dict[str, Any] = Field(default_factory=dict)

    def public(self) -> Dict[str, Any]:
        return {
            "entities": {k: v.model_dump() for k, v in self.entities.items()},
            "missing_slots": list(self.missing_slots),
            "ambiguous_slots": list(self.ambiguous_slots),
            "known_slots": self.known_slots,
            "needs_clarification": self.needs_clarification,
            "reason_summary": self.reason_summary,
            "flow_hint": self.flow_hint,
            "intent_hint": self.intent_hint,
            "domain": self.domain or self.flow_hint,
            "extraction_version": self.extraction_version,
            "extracted_at": self.extracted_at,
            "used_gemini": self.used_gemini,
            "cache_hit": self.cache_hit,
            "usage": self.usage,
            "meta": self.meta,
        }


class GapAnalysisResult(BaseModel):
    flow: str = "generic"
    domain: Optional[str] = None
    known_slots: Dict[str, Any] = Field(default_factory=dict)
    missing_required: List[str] = Field(default_factory=list)
    missing_conditional: List[str] = Field(default_factory=list)
    missing_optional: List[str] = Field(default_factory=list)
    ambiguous_slots: List[str] = Field(default_factory=list)
    next_best_question: Optional[str] = None
    next_slot: Optional[str] = None
    question_reason: Optional[str] = None
    suggested_chips: List[QuestionChip] = Field(default_factory=list)
    completion_ready: bool = False
    reason_summary: str = ""
    analysis_version: str = EXTRACTION_VERSION

    def public(self) -> Dict[str, Any]:
        return {
            "flow": self.flow,
            "domain": self.domain or self.flow,
            "known_slots": self.known_slots,
            "missing_required": list(self.missing_required),
            "missing_conditional": list(self.missing_conditional),
            "missing_optional": list(self.missing_optional),
            "ambiguous_slots": list(self.ambiguous_slots),
            "next_best_question": self.next_best_question,
            "next_slot": self.next_slot,
            "question_reason": self.question_reason,
            "suggested_chips": [c.model_dump() for c in self.suggested_chips],
            "completion_ready": self.completion_ready,
            "reason_summary": self.reason_summary,
            "analysis_version": self.analysis_version,
        }


class ExtractBody(BaseModel):
    text: str
    intent: Optional[str] = None
    flow: Optional[str] = None
    domain_hint: Optional[str] = None
    confirmed_entities: Optional[Dict[str, Any]] = None
    prior_entities: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None
    use_gemini: Optional[bool] = False
    timezone: str = DEFAULT_TZ
    conversation_session_id: Optional[str] = None


class GapsBody(BaseModel):
    flow: Optional[str] = None
    intent: Optional[str] = None
    domain: Optional[str] = None
    entities: Optional[Dict[str, Any]] = None
    text: Optional[str] = None
    confirmed_entities: Optional[Dict[str, Any]] = None
    prior_slots: Optional[Dict[str, Any]] = None
    timezone: str = DEFAULT_TZ


class ConfirmEntityBody(BaseModel):
    slot: str
    value: Any
    entities: Optional[Dict[str, Any]] = None
    raw: Optional[Any] = None
    conversation_session_id: Optional[str] = None


class PatchEntitiesBody(BaseModel):
    conversation_session_id: Optional[str] = None
    entities: Optional[Dict[str, Any]] = None
    confirmed: Optional[Dict[str, Any]] = None
    corrections: Optional[Dict[str, Any]] = None
    clear_slots: Optional[List[str]] = None


class NormalizeMergeBody(BaseModel):
    entities: Dict[str, Any] = Field(default_factory=dict)
    prior: Optional[Dict[str, Any]] = None
    confirmed: Optional[Dict[str, Any]] = None
    corrections: Optional[Dict[str, Any]] = None
    documents: Optional[Dict[str, Any]] = None
    calendar: Optional[Dict[str, Any]] = None
    timezone: str = DEFAULT_TZ
