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
    created_at: str = Field(default_factory=now_iso)


class SuggestedAction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: f"sa_{uuid.uuid4().hex[:10]}")
    title: str
    kind: str = "generic"
    priority: Literal["low", "medium", "high"] = "medium"
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)


class LifeObjectHealth(BaseModel):
    model_config = ConfigDict(extra="ignore")
    score: float = Field(ge=0, le=1, default=0.5)
    label: str = "unknown"
    issues: List[str] = Field(default_factory=list)
    updated_at: Optional[str] = None


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
    properties: Dict[str, Any] = Field(default_factory=dict)
    pending_questions: List[PendingQuestion] = Field(default_factory=list)
    suggested_actions: List[SuggestedAction] = Field(default_factory=list)
    health: LifeObjectHealth = Field(default_factory=LifeObjectHealth)
    source_count: int = 0
    last_reasoning: Optional[Dict[str, Any]] = None
    next_reasoning: Optional[str] = None
    origin: str = "unknown"
    ai_summary: str = ""
    ai_reasoning_version: str = AI_REASONING_VERSION
    ai_confidence: float = Field(ge=0, le=1, default=0.0)
    # Stable fingerprint keys for dedup (never title alone)
    identity_keys: Dict[str, str] = Field(default_factory=dict)
    merged_into_id: Optional[str] = None
    merged_from_ids: List[str] = Field(default_factory=list)
    # Merge proposals when conflict (never silent second Casa)
    merge_proposals: List[Dict[str, Any]] = Field(default_factory=list)

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
    identity_keys: Dict[str, str] = Field(default_factory=dict)
    origin: str = "api"
    confidence: float = 0.5


class LifeObjectPatchBody(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    status: Optional[LifeObjectStatus] = None
    properties: Optional[Dict[str, Any]] = None
    identity_keys: Optional[Dict[str, str]] = None
    confidence: Optional[float] = None
    pending_questions: Optional[List[PendingQuestion]] = None
    suggested_actions: Optional[List[SuggestedAction]] = None


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
