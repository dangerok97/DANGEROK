"""Life Object document model — collection: life_objects."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from life_objects.types import LIFE_OBJECT_TYPES, LifeObjectStatus, LifeObjectType


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_life_object_id() -> str:
    return f"lo_{uuid.uuid4().hex[:14]}"


AI_REASONING_VERSION = "life-object-reasoner-1.0"
AI_ENRICHMENT_VERSION = "life-object-enrichment-1.0"

# Property keys that define the object (stable) vs state (mutable).
IDENTITY_PROPERTY_KEYS = frozenset({
    "address", "property_address", "cadastral_data", "cadastral",
    "pod", "pdr", "plate", "vin", "brand", "model",
    "institution", "university", "employer", "company_vat",
    "person_key", "coords", "lender_property", "course_key",
    "travel_dest_period", "iban_last4", "company_name_norm",
})
STATE_PROPERTY_KEYS = frozenset({
    "supplier", "utility_supplier", "utility_type", "utility_amount",
    "utility_due_date", "amount_total", "amount", "consumption",
    "monthly_installment", "rate", "interest_rate", "company",
    "insurance_company", "policy_number", "contract_code", "insured_object",
    "lender", "loan_number", "mortgage_years_left", "mortgage_assimilated",
    "utility_assimilated", "price", "status_detail", "coverage", "expiry",
    "due_date", "course_name", "subject", "destination", "start_date",
    "end_date", "profession", "document_type", "domain",
    "travel_project_id", "study_plan_id", "goal_id", "goal_type",
})


class LifeObjectRelationship(BaseModel):
    model_config = ConfigDict(extra="ignore")
    target_id: str = ""
    relation: str = "related_to"
    confidence: float = Field(ge=0, le=1, default=0.5)
    meta: Dict[str, Any] = Field(default_factory=dict)


class LifeObjectHistoryEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    at: str = Field(default_factory=now_iso)
    event: str = "updated"
    source: str = ""
    source_id: Optional[str] = None
    summary: str = ""
    delta: Dict[str, Any] = Field(default_factory=dict)
    improves: List[str] = Field(default_factory=list)
    worsens: List[str] = Field(default_factory=list)


class PendingQuestion(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: f"pq_{uuid.uuid4().hex[:10]}")
    question: str
    why: str = ""
    priority: Literal["low", "medium", "high"] = "medium"
    category: str = "missing_info"  # missing_info | clarify | help_ability
    source: str = "deterministic"  # deterministic | gemini
    created_at: str = Field(default_factory=now_iso)


class SuggestedAction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: f"sa_{uuid.uuid4().hex[:10]}")
    title: str
    kind: str = "generic"
    priority: Literal["low", "medium", "high"] = "medium"
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)


class AINarrative(BaseModel):
    """Natural-language situation description — not a field dump. Versioned."""

    model_config = ConfigDict(extra="ignore")
    text: str = ""
    version: int = 1
    updated_at: Optional[str] = None
    source: str = "deterministic"  # deterministic | gemini
    provider: str = "local-deterministic"
    model: str = "local-deterministic"
    confidence: float = Field(ge=0, le=1, default=0.5)
    enrichment_version: str = AI_ENRICHMENT_VERSION


class AIInsight(BaseModel):
    """Observation (not a notification) derived from object history + facts."""

    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: f"ins_{uuid.uuid4().hex[:10]}")
    kind: str = "observation"  # observation | trend | change | risk | opportunity
    title: str = ""
    detail: str = ""
    evidence: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1, default=0.5)
    created_at: str = Field(default_factory=now_iso)
    source: str = "deterministic"


class TemporalComparison(BaseModel):
    """Present vs history for the same object (bills, providers, etc.)."""

    model_config = ConfigDict(extra="ignore")
    observations: List[str] = Field(default_factory=list)
    changes: List[Dict[str, Any]] = Field(default_factory=list)
    utility_trend: Optional[Dict[str, Any]] = None
    compared_at: str = Field(default_factory=now_iso)
    source: str = "deterministic"
    provider: str = "local-deterministic"
    model: str = "local-deterministic"


class LifeObjectHealth(BaseModel):
    """Explainable life-health evaluation (Health 2.0 — not a bare scalar)."""

    model_config = ConfigDict(extra="ignore")
    score: float = Field(ge=0, le=1, default=0.5)  # overall derived
    label: str = "unknown"
    issues: List[str] = Field(default_factory=list)  # legacy compat
    completeness: float = Field(ge=0, le=1, default=0.5)  # legacy = identity_completeness
    reliability: float = Field(ge=0, le=1, default=0.5)
    # Health 2.0 dimensions (explainable)
    identity_completeness: float = Field(ge=0, le=1, default=0.5)
    state_completeness: float = Field(ge=0, le=1, default=0.5)
    source_consistency: float = Field(ge=0, le=1, default=0.5)
    temporal_confidence: float = Field(ge=0, le=1, default=0.5)
    pending_conflicts: float = Field(ge=0, le=1, default=0.0)  # 0 clean → 1 many
    pending_links: float = Field(ge=0, le=1, default=0.0)
    ai_confidence: float = Field(ge=0, le=1, default=0.0)
    missing_info: List[str] = Field(default_factory=list)
    opportunities: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)
    dimensions: Dict[str, Any] = Field(default_factory=dict)  # explainable dump
    updated_at: Optional[str] = None
    source: str = "deterministic"


class LifeObject(BaseModel):
    """Core Life Object — center of ORA knowledge identity (shadow mode)."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=new_life_object_id)
    user_id: str
    type: LifeObjectType = "CUSTOM"
    title: str
    status: LifeObjectStatus = "active"
    confidence: float = Field(ge=0, le=1, default=0.5)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    summary: str = ""
    relationships: List[LifeObjectRelationship] = Field(default_factory=list)
    documents: List[str] = Field(default_factory=list)
    calendar_events: List[str] = Field(default_factory=list)
    goals: List[str] = Field(default_factory=list)
    projects: List[str] = Field(default_factory=list)
    brain_nodes: List[str] = Field(default_factory=list)
    knowledge: Dict[str, Any] = Field(default_factory=dict)
    history: List[LifeObjectHistoryEntry] = Field(default_factory=list)
    # Legacy bag — kept; migrated non-destructively into identity / state
    properties: Dict[str, Any] = Field(default_factory=dict)
    # Identity = what defines the object; State = what changes over time
    identity: Dict[str, Any] = Field(default_factory=dict)
    state: Dict[str, Any] = Field(default_factory=dict)
    pending_questions: List[PendingQuestion] = Field(default_factory=list)
    suggested_actions: List[SuggestedAction] = Field(default_factory=list)
    narrative: AINarrative = Field(default_factory=AINarrative)
    insights: List[AIInsight] = Field(default_factory=list)
    temporal: Optional[TemporalComparison] = None
    health: LifeObjectHealth = Field(default_factory=LifeObjectHealth)
    # Provenance (typed sources) — source_count kept as alias of total_sources
    document_sources: List[str] = Field(default_factory=list)
    conversation_sources: List[str] = Field(default_factory=list)
    goal_sources: List[str] = Field(default_factory=list)
    calendar_sources: List[str] = Field(default_factory=list)
    brain_sources: List[str] = Field(default_factory=list)
    manual_sources: List[str] = Field(default_factory=list)
    total_sources: int = 0
    source_count: int = 0  # legacy alias of total_sources
    last_reasoning: Optional[Dict[str, Any]] = None
    next_reasoning: Optional[str] = None
    origin: str = "unknown"
    ai_summary: str = ""
    ai_reasoning_version: str = AI_REASONING_VERSION
    ai_confidence: float = Field(ge=0, le=1, default=0.0)
    ai_enrichment_version: str = AI_ENRICHMENT_VERSION
    # Stable fingerprint keys for dedup (never title alone)
    identity_keys: Dict[str, str] = Field(default_factory=dict)
    merged_into_id: Optional[str] = None
    merged_from_ids: List[str] = Field(default_factory=list)
    # Merge proposals — only REAL_CONFLICT should disturb the user
    merge_proposals: List[Dict[str, Any]] = Field(default_factory=list)
    pending_links: List[Dict[str, Any]] = Field(default_factory=list)
    # Last semantic validation meta (backend authority)
    last_validation: Optional[Dict[str, Any]] = None
    assimilated_kinds: List[str] = Field(default_factory=list)

    @field_validator("type", mode="before")
    @classmethod
    def _type(cls, v: Any) -> str:
        s = str(v or "CUSTOM").strip().upper()
        if s not in LIFE_OBJECT_TYPES:
            return "CUSTOM"
        return s

    @field_validator("confidence", "ai_confidence", mode="before")
    @classmethod
    def _conf(cls, v: Any) -> float:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.5

    def public(self) -> Dict[str, Any]:
        return self.model_dump()

    def touch(self) -> None:
        self.updated_at = now_iso()


class LifeObjectCreateBody(BaseModel):
    type: LifeObjectType = "CUSTOM"
    title: str
    summary: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict)
    identity: Dict[str, Any] = Field(default_factory=dict)
    state: Dict[str, Any] = Field(default_factory=dict)
    identity_keys: Dict[str, str] = Field(default_factory=dict)
    origin: str = "api"
    confidence: float = 0.5


class LifeObjectPatchBody(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    status: Optional[LifeObjectStatus] = None
    properties: Optional[Dict[str, Any]] = None
    identity: Optional[Dict[str, Any]] = None
    state: Optional[Dict[str, Any]] = None
    identity_keys: Optional[Dict[str, str]] = None
    confidence: Optional[float] = None
    pending_questions: Optional[List[PendingQuestion]] = None
    suggested_actions: Optional[List[SuggestedAction]] = None


class LifeObjectEnrichBody(BaseModel):
    force: bool = False
    sections: List[str] = Field(
        default_factory=lambda: ["narrative", "questions", "insights", "temporal", "health"],
    )


class LifeObjectSearchBody(BaseModel):
    q: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    limit: int = 40


class LifeObjectLinkBody(BaseModel):
    target_id: str
    relation: str = "related_to"
    confidence: float = 0.7


class LifeObjectMergeBody(BaseModel):
    source_id: str
    target_id: str
    prefer_target_title: bool = True


class LifeObjectReasonBody(BaseModel):
    document_id: Optional[str] = None
    force: bool = False
    context: Dict[str, Any] = Field(default_factory=dict)


# --- AI structured reasoning output ---------------------------------
class ObjectReasoningDecision(BaseModel):
    """Gemini / fallback structured decision — never invent facts."""

    model_config = ConfigDict(extra="ignore")

    action: Literal["create", "update", "propose_merge", "skip", "uncertain"] = "skip"
    object_type: LifeObjectType = "CUSTOM"
    object_id: Optional[str] = None  # existing id when update / merge target
    merge_with_id: Optional[str] = None
    title: str = ""
    summary: str = ""
    identity_keys: Dict[str, str] = Field(default_factory=dict)
    properties_delta: Dict[str, Any] = Field(default_factory=dict)
    improves: List[str] = Field(default_factory=list)
    worsens: List[str] = Field(default_factory=list)
    next_question: Optional[str] = None
    next_question_why: str = ""
    suggested_actions: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1, default=0.4)
    reason_summary: str = ""
    invented_facts: bool = False  # must stay False; reject if True
    ai_used: bool = False
    provider: str = "local-deterministic"
    model: str = "local-deterministic"

    @field_validator("object_type", mode="before")
    @classmethod
    def _ot(cls, v: Any) -> str:
        s = str(v or "CUSTOM").strip().upper()
        return s if s in LIFE_OBJECT_TYPES else "CUSTOM"

    @field_validator("confidence", mode="before")
    @classmethod
    def _c(cls, v: Any) -> float:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.4

    @field_validator("identity_keys", "properties_delta", mode="before")
    @classmethod
    def _dict(cls, v: Any) -> Dict[str, Any]:
        return v if isinstance(v, dict) else {}

    @field_validator("improves", "worsens", "suggested_actions", mode="before")
    @classmethod
    def _list(cls, v: Any) -> List[str]:
        if not isinstance(v, list):
            return []
        return [str(x) for x in v if x is not None]


# --- AI enrichment structured outputs (Gemini / fallback) ----------------
class NarrativeAIResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    narrative: str = ""
    invented_facts: bool = False
    confidence: float = Field(ge=0, le=1, default=0.5)
    ai_used: bool = False
    provider: str = "local-deterministic"
    model: str = "local-deterministic"

    @field_validator("confidence", mode="before")
    @classmethod
    def _c(cls, v: Any) -> float:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.5


class QuestionItemAI(BaseModel):
    model_config = ConfigDict(extra="ignore")
    question: str = ""
    why: str = ""
    priority: Literal["low", "medium", "high"] = "medium"
    category: str = "missing_info"


class QuestionsAIResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    questions: List[QuestionItemAI] = Field(default_factory=list)
    invented_facts: bool = False
    ai_used: bool = False
    provider: str = "local-deterministic"
    model: str = "local-deterministic"


class InsightItemAI(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: str = "observation"
    title: str = ""
    detail: str = ""
    evidence: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1, default=0.5)


class InsightsAIResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    insights: List[InsightItemAI] = Field(default_factory=list)
    invented_facts: bool = False
    ai_used: bool = False
    provider: str = "local-deterministic"
    model: str = "local-deterministic"


class TemporalAIResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    observations: List[str] = Field(default_factory=list)
    changes: List[Dict[str, Any]] = Field(default_factory=list)
    invented_facts: bool = False
    ai_used: bool = False
    provider: str = "local-deterministic"
    model: str = "local-deterministic"


class HealthAIResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    completeness: float = Field(ge=0, le=1, default=0.5)
    reliability: float = Field(ge=0, le=1, default=0.5)
    identity_completeness: Optional[float] = None
    state_completeness: Optional[float] = None
    source_consistency: Optional[float] = None
    temporal_confidence: Optional[float] = None
    pending_conflicts: Optional[float] = None
    pending_links: Optional[float] = None
    ai_confidence: Optional[float] = None
    missing_info: List[str] = Field(default_factory=list)
    opportunities: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)
    overall_score: Optional[float] = None
    invented_facts: bool = False
    ai_used: bool = False
    provider: str = "local-deterministic"
    model: str = "local-deterministic"

    @field_validator(
        "completeness", "reliability", "overall_score",
        "identity_completeness", "state_completeness", "source_consistency",
        "temporal_confidence", "pending_conflicts", "pending_links", "ai_confidence",
        mode="before",
    )
    @classmethod
    def _score(cls, v: Any) -> Any:
        if v is None:
            return None
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.5
