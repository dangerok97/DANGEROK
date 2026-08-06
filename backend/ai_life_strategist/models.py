"""Structured AI Life Strategist outputs — never free-form decision dumps."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

ENGINE_VERSION = "ai-life-strategist-1.0"

DomainId = Literal[
    "casa",
    "auto",
    "finanze",
    "studio",
    "lavoro",
    "salute",
    "famiglia",
    "animali",
    "viaggi",
    "documenti",
    "assicurazioni",
    "abbonamenti",
    "internet",
    "servizi",
]

DOMAINS: tuple[str, ...] = (
    "casa",
    "auto",
    "finanze",
    "studio",
    "lavoro",
    "salute",
    "famiglia",
    "animali",
    "viaggi",
    "documenti",
    "assicurazioni",
    "abbonamenti",
    "internet",
    "servizi",
)

DOMAIN_LABELS_IT: Dict[str, str] = {
    "casa": "Casa",
    "auto": "Auto",
    "finanze": "Finanze",
    "studio": "Studio",
    "lavoro": "Lavoro",
    "salute": "Salute",
    "famiglia": "Famiglia",
    "animali": "Animali",
    "viaggi": "Viaggi",
    "documenti": "Documenti",
    "assicurazioni": "Assicurazioni",
    "abbonamenti": "Abbonamenti",
    "internet": "Internet",
    "servizi": "Servizi",
}

# Presentation-only icons (FE may map; never drive logic)
DOMAIN_ICONS: Dict[str, str] = {
    "casa": "home",
    "auto": "car",
    "finanze": "wallet",
    "studio": "book",
    "lavoro": "briefcase",
    "salute": "heart",
    "famiglia": "people",
    "animali": "paw",
    "viaggi": "airplane",
    "documenti": "document",
    "assicurazioni": "shield",
    "abbonamenti": "repeat",
    "internet": "wifi",
    "servizi": "grid",
}

PlanSource = Literal["gemini", "deterministic_fallback", "cache"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_plan_id() -> str:
    return f"als_{uuid.uuid4().hex[:14]}"


class RecommendedDocument(BaseModel):
    """Document the strategist prefers over another spoken answer."""

    doc_type: str  # e.g. rogito, bolletta, libretto, polizza
    label: str
    reason: str
    expected_fields: List[str] = Field(default_factory=list)
    upload_hint: Optional[str] = None


class StrategistPlan(BaseModel):
    """Always structured — every question explainable with a concrete benefit."""

    id: str = Field(default_factory=new_plan_id)
    next_best_question: str
    question_reason: str
    expected_benefit: str
    information_gain: float = Field(ge=0.0, le=1.0, default=0.5)
    recommended_document: Optional[RecommendedDocument] = None
    alternative_question: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)
    domain: DomainId
    priority: int = Field(ge=1, le=100, default=50)
    prefer_document: bool = False
    skip_allowed: bool = True
    privacy_safe: bool = True
    source: PlanSource = "deterministic_fallback"
    asked_keys: List[str] = Field(default_factory=list)
    gap_keys: List[str] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)
    engine_version: str = ENGINE_VERSION

    def public(self) -> Dict[str, Any]:
        return self.model_dump()

    def explain_for_user(self) -> str:
        """User-facing explanation — benefit first, never jargon."""
        parts = [self.expected_benefit.strip()]
        if self.question_reason:
            parts.append(self.question_reason.strip())
        return " ".join(p for p in parts if p)


class GapItem(BaseModel):
    key: str
    domain: DomainId
    label: str
    information_gain: float = 0.5
    prefer_document: bool = False
    document_type: Optional[str] = None
    benefit_code: str = ""
    question_template: str = ""
    asked: bool = False


class BenefitDescriptor(BaseModel):
    code: str
    domain: DomainId
    title: str
    user_benefit: str  # concrete, never vague
    requires: List[str] = Field(default_factory=list)
    activates_when: List[str] = Field(default_factory=list)
    home_signal: Optional[str] = None
    proactive_signal: Optional[str] = None


class ReasoningContext(BaseModel):
    """Proportional context for the strategist — never secrets / bank creds."""

    user_id: str
    domains_touched: List[str] = Field(default_factory=list)
    known_facts: Dict[str, Any] = Field(default_factory=dict)
    missing_keys: List[str] = Field(default_factory=list)
    asked_questions: List[str] = Field(default_factory=list)
    linked_doc_types: List[str] = Field(default_factory=list)
    last_user_text: Optional[str] = None
    session_phase: str = "active"  # greeting|active|document|wrap
    benefits_available: List[str] = Field(default_factory=list)
    benefits_active: List[str] = Field(default_factory=list)
