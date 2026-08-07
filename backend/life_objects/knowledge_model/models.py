"""Pydantic models for the Digital Twin Knowledge Model."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_fact_id() -> str:
    return f"kf_{uuid.uuid4().hex[:14]}"


def new_hypothesis_id() -> str:
    return f"kh_{uuid.uuid4().hex[:14]}"


def new_decision_id() -> str:
    return f"kd_{uuid.uuid4().hex[:14]}"


def new_memory_id() -> str:
    return f"km_{uuid.uuid4().hex[:14]}"


FactStatus = Literal["current", "superseded", "archived"]
HypothesisStatus = Literal["active", "confirmed", "rejected", "expired"]
DecisionOutcome = Literal[
    "pending",
    "accepted",
    "rejected",
    "postponed",
    "completed",
    "dismissed",
    "never_ask_again",
]
FactOrigin = Literal[
    "document",
    "user",
    "calendar",
    "email",
    "banking",
    "whatsapp",
    "conversation",
    "manual",
    "migration",
    "hypothesis_confirm",
]


class KnowledgeFact(BaseModel):
    """Confirmed Digital Twin fact — immutable history (never hard-deleted)."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=new_fact_id)
    type: str = ""  # e.g. address, utility_supplier, lender
    value: Any = None
    source: str = "document"
    source_id: Optional[str] = None
    confidence: float = Field(ge=0, le=1, default=0.8)
    verified: bool = True
    verified_by: Optional[str] = None  # user | document | system
    verified_at: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    origin: FactOrigin = "document"
    version: int = 1
    explanation: str = ""
    ai_summary: str = ""
    status: FactStatus = "current"
    superseded_by: Optional[str] = None
    superseded_at: Optional[str] = None
    active: bool = True
    life_object_id: Optional[str] = None

    @field_validator("confidence", mode="before")
    @classmethod
    def _c(cls, v: Any) -> float:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.8


class KnowledgeHypothesis(BaseModel):
    """What ORA thinks — never treated as a Fact until user/system confirms."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=new_hypothesis_id)
    type: str = ""
    value: Any = None
    confidence: float = Field(ge=0, le=1, default=0.4)
    reason: str = ""
    evidence: List[str] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    question_to_confirm: str = ""
    status: HypothesisStatus = "active"
    source: str = "ai"
    source_id: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    confirmed_fact_id: Optional[str] = None
    life_object_id: Optional[str] = None

    @field_validator("confidence", mode="before")
    @classmethod
    def _c(cls, v: Any) -> float:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.4


class KnowledgeDecision(BaseModel):
    """Important suggestion elevated to a Decision with user outcome memory."""

    model_config = ConfigDict(extra="ignore")

    decision_id: str = Field(default_factory=new_decision_id)
    life_object_id: str = ""
    reason: str = ""
    benefit: str = ""
    risk: str = ""
    alternatives: List[str] = Field(default_factory=list)
    ai_reasoning: str = ""
    user_choice: Optional[str] = None
    outcome: DecisionOutcome = "pending"
    decision_date: str = Field(default_factory=now_iso)
    review_date: Optional[str] = None
    fingerprint: str = ""  # stable key to suppress re-proposals
    kind: str = "suggestion"
    title: str = ""
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class MemoryEvent(BaseModel):
    """Tellable narrative event — not a technical audit log."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=new_memory_id)
    life_object_id: str = ""
    kind: str = "life_event"  # purchase | mortgage | supplier_change | solar | insurance | sale | …
    title: str = ""
    narrative: str = ""
    at: str = Field(default_factory=now_iso)
    related_fact_ids: List[str] = Field(default_factory=list)
    related_hypothesis_ids: List[str] = Field(default_factory=list)
    related_decision_ids: List[str] = Field(default_factory=list)
    source: str = ""
    source_id: Optional[str] = None
    timeline_group: Optional[str] = None  # e.g. mortgage_path
    meta: Dict[str, Any] = Field(default_factory=dict)


class TimelineGroup(BaseModel):
    """Semantic grouping of related life events (not raw document order)."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    group_key: str = ""  # mortgage_path | utility_path | purchase_path | insurance_path
    title: str = ""
    summary: str = ""
    events: List[Dict[str, Any]] = Field(default_factory=list)
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    status: str = "active"  # active | completed | unknown


# --- API bodies (minimal write for tests) ---------------------------------

class ConfirmHypothesisBody(BaseModel):
    hypothesis_id: str
    verified_by: str = "user"


class RejectHypothesisBody(BaseModel):
    hypothesis_id: str
    reason: str = ""


class ProposeHypothesisBody(BaseModel):
    """Internal/test: seed a hypothesis (never a Fact)."""
    type: str
    value: Any = None
    confidence: float = 0.4
    reason: str = ""
    question_to_confirm: str = ""
    evidence: List[str] = Field(default_factory=list)


class DecisionOutcomeBody(BaseModel):
    decision_id: str
    outcome: DecisionOutcome
    user_choice: Optional[str] = None


class ProposeDecisionBody(BaseModel):
    """Internal/test: elevate a suggestion to Decision."""
    title: str
    reason: str = ""
    benefit: str = ""
    risk: str = ""
    alternatives: List[str] = Field(default_factory=list)
    ai_reasoning: str = ""
    kind: str = "suggestion"
