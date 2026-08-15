"""Generic Life OS plans & artifacts — domain-neutral execution state."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

PlanStatus = Literal["active", "paused", "completed", "cancelled"]
ItemStatus = Literal["not_started", "in_progress", "completed", "skipped"]
# DEPRECATED (V2.4): closed artifact catalog — AI Core uses GenerativeObject instead.
# Kept only for read-compat with legacy life_os_artifacts documents.
ArtifactType = Literal[
    "summary",
    "concept_map",
    "flashcards",
    "quiz",
    "checklist",
    "notes",
    "guide",
]
ArtifactStatus = Literal["ready", "failed", "pending"]
EvidenceKind = Literal[
    "USER_PROVIDED_CONTENT",
    "PERSONAL_CONTEXT",
    "TARGET_SPECIFIC_EVIDENCE",
    "GENERAL_EXTERNAL_EVIDENCE",
    "MODEL_KNOWLEDGE",
    "INFERENCE",
]
EvidenceStatus = Literal["active", "superseded", "historical"]
ItemOrigin = Literal[
    "user_stated",
    "user_file",
    "external_evidence",
    "model_assumption",
    "inherited",
    "generated",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_plan_id() -> str:
    return f"lop_{uuid.uuid4().hex[:14]}"


def new_item_id() -> str:
    return f"lpi_{uuid.uuid4().hex[:12]}"


def new_artifact_id() -> str:
    return f"loa_{uuid.uuid4().hex[:14]}"


class EvidenceRef(BaseModel):
    ref: str
    kind: EvidenceKind = "GENERAL_EXTERNAL_EVIDENCE"
    label: str = ""
    url: Optional[str] = None
    # V2.6.1 — public presentation + currentness (optional, backward compatible)
    display_name: str = ""
    status: EvidenceStatus = "active"
    source_type: str = ""  # e.g. user_file — descriptive, not a domain router
    source_id: str = ""


class PlanItem(BaseModel):
    id: str = Field(default_factory=new_item_id)
    title: str
    description: str = ""
    due_date: Optional[str] = None  # YYYY-MM-DD
    order: int = 0
    status: ItemStatus = "not_started"
    artifact_refs: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    # Lightweight assumption provenance — NOT a cognitive graph
    origin: ItemOrigin = "generated"
    meta: Dict[str, Any] = Field(default_factory=dict)


class LifeOsPlan(BaseModel):
    """Generic plan — no domain fields (no exam_subject, dog_breed, …)."""

    id: str = Field(default_factory=new_plan_id)
    user_id: str
    goal_id: Optional[str] = None
    summary: str
    desired_outcome: str = ""
    target_date: Optional[str] = None
    status: PlanStatus = "active"
    strategy: str = ""
    constraints: List[str] = Field(default_factory=list)
    items: List[PlanItem] = Field(default_factory=list)
    evidence_refs: List[EvidenceRef] = Field(default_factory=list)
    conversation_session_id: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    meta: Dict[str, Any] = Field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = now_iso()

    def public(self) -> Dict[str, Any]:
        return self.model_dump()

    def progress_ratio(self) -> float:
        if not self.items:
            return 0.0
        done = sum(1 for i in self.items if i.status == "completed")
        return round(done / max(1, len(self.items)), 3)

    def next_open_item(self) -> Optional[PlanItem]:
        ordered = sorted(self.items, key=lambda x: (x.order, x.due_date or ""))
        for it in ordered:
            if it.status in ("not_started", "in_progress"):
                return it
        return None

    def today_items(self, today: Optional[str] = None) -> List[PlanItem]:
        day = today or datetime.now(timezone.utc).date().isoformat()
        return [
            i
            for i in self.items
            if (i.due_date or "")[:10] == day
            and i.status in ("not_started", "in_progress")
        ]


class LifeOsArtifact(BaseModel):
    id: str = Field(default_factory=new_artifact_id)
    user_id: str
    type: ArtifactType
    title: str
    goal_id: Optional[str] = None
    plan_id: Optional[str] = None
    plan_item_id: Optional[str] = None
    content: Dict[str, Any] = Field(default_factory=dict)
    evidence_refs: List[EvidenceRef] = Field(default_factory=list)
    evidence_quality: Dict[str, Any] = Field(default_factory=dict)
    status: ArtifactStatus = "ready"
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    def public(self) -> Dict[str, Any]:
        return self.model_dump()
