"""Typed Intent models — the only contract Action Engine uses for flow choice."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

CLASSIFIER_VERSION = "intent-engine-1.0"

IntentName = Literal[
    "study",
    "travel",
    "event",
    "medical",
    "payment",
    "financial",
    "administrative",
    "document_review",
    "task",
    "communication",
    "shopping",
    "project",
    "generic",
]

# Subtypes are free-form strings validated by knowledge base
KNOWN_SUBTYPES = frozenset({
    "exam_preparation",
    "vacation",
    "concert",
    "appointment",
    "bill",
    "invoice",
    "transfer",
})

CONFIDENCE_ACCEPT = 0.62
CONFIDENCE_MARGIN = 0.12


class IntentEntities(BaseModel):
    subject: Optional[str] = None
    person: Optional[str] = None
    place: Optional[str] = None
    amount: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    document: Optional[str] = None
    event: Optional[str] = None
    travel: Optional[str] = None
    university: Optional[str] = None
    exam: Optional[str] = None
    deadline: Optional[str] = None
    goal: Optional[str] = None
    start_date: Optional[str] = None  # travel period start YYYY-MM-DD
    end_date: Optional[str] = None
    period: Optional[str] = None  # raw / label
    departure: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        d = self.model_dump(exclude_none=True)
        extra = d.pop("extra", {}) or {}
        d.update({k: v for k, v in extra.items() if v is not None})
        return d


class ClarifyOption(BaseModel):
    id: str
    label: str
    intent: str
    subtype: Optional[str] = None


class IntentResult(BaseModel):
    intent: IntentName
    subtype: Optional[str] = None
    confidence: float = 0.0
    reason: str = ""
    entities: IntentEntities = Field(default_factory=IntentEntities)
    clarify_options: Optional[List[ClarifyOption]] = None
    needs_clarify: bool = False
    classifier_version: str = CLASSIFIER_VERSION
    scores: Dict[str, float] = Field(default_factory=dict)
    source_hints_used: List[str] = Field(default_factory=list)

    def public(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "subtype": self.subtype,
            "confidence": round(self.confidence, 4),
            "reason": self.reason,
            "entities": self.entities.as_dict(),
            "clarify_options": (
                [c.model_dump() for c in self.clarify_options]
                if self.clarify_options
                else None
            ),
            "needs_clarify": self.needs_clarify,
            "classifier_version": self.classifier_version,
        }


class ClassifyBody(BaseModel):
    text: str
    description: Optional[str] = None
    source_type: Optional[str] = None
    item_type: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)
    use_llm: bool = False
    # Precomputed / forced intent (skip classification)
    intent: Optional[IntentResult] = None
