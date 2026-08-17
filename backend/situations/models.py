"""Domain-neutral Situation Model V1.

A situation is contextual life state, not durable personal Memory and not a
domain router. Semantic labels are descriptive free text owned by the AI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

SituationStatus = Literal["active", "changed", "resolved", "cancelled"]
SituationOperation = Literal["none", "create", "update", "cancel", "resolve"]
SituationSource = Literal[
    "user_conversation", "user_file", "external_evidence", "inferred"
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SituationUpdate(BaseModel):
    operation: SituationOperation = "none"
    situation_id: Optional[str] = None
    expected_revision: Optional[int] = Field(default=None, ge=1)
    summary: Optional[str] = Field(default=None, max_length=400)
    semantic_kind: Optional[str] = Field(default=None, max_length=80)
    temporal_scope: Optional[str] = Field(default=None, max_length=240)
    participants: List[str] = Field(default_factory=list, max_length=12)
    constraints: List[str] = Field(default_factory=list, max_length=20)
    facts: List[str] = Field(default_factory=list, max_length=20)
    assumptions: List[str] = Field(default_factory=list, max_length=12)
    supersedes: List[str] = Field(default_factory=list, max_length=20)
    source_refs: List[str] = Field(default_factory=list, max_length=20)
    linked_plan_id: Optional[str] = Field(default=None, max_length=80)
    linked_object_refs: List[str] = Field(default_factory=list, max_length=20)
    source: SituationSource = "user_conversation"

    @field_validator(
        "participants",
        "constraints",
        "facts",
        "assumptions",
        "supersedes",
        "source_refs",
        "linked_object_refs",
    )
    @classmethod
    def _bounded_strings(cls, values: List[str]) -> List[str]:
        out: List[str] = []
        for value in values or []:
            clean = " ".join(str(value or "").split())[:300]
            if clean and clean not in out:
                out.append(clean)
        return out


class SituationEvent(BaseModel):
    revision: int
    operation: SituationOperation
    source: SituationSource
    source_refs: List[str] = Field(default_factory=list)
    changes: Dict[str, Any] = Field(default_factory=dict)
    at: str = Field(default_factory=now_iso)
    reasoning_epoch: Optional[str] = None


class SituationState(BaseModel):
    id: str
    user_id: str
    session_id: Optional[str] = None
    status: SituationStatus = "active"
    summary: str
    semantic_kind: Optional[str] = None
    temporal_scope: Optional[str] = None
    participants: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    facts: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    source_refs: List[str] = Field(default_factory=list)
    linked_plan_id: Optional[str] = None
    linked_object_refs: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    resolved_at: Optional[str] = None
    revision: int = 1
    history: List[SituationEvent] = Field(default_factory=list)
    applied_epochs: List[str] = Field(default_factory=list)

    def context_preview(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "summary": self.summary,
            "semantic_kind": self.semantic_kind,
            "temporal_scope": self.temporal_scope,
            "participants": self.participants[:6],
            "constraints": self.constraints[:8],
            "facts": self.facts[:8],
            "assumptions": self.assumptions[:6],
            "linked_plan_id": self.linked_plan_id,
            "linked_object_refs": self.linked_object_refs[:6],
            "revision": self.revision,
            "updated_at": self.updated_at,
        }
