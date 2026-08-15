"""GenerativeObject — AI-defined durable workspace objects (domain-neutral)."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from life_os.generative_schema import normalize_content_blocks_for_display
from life_os.models import EvidenceRef, now_iso

ObjectStatus = Literal["ready", "failed", "pending", "archived"]


def new_object_id() -> str:
    return f"lgo_{uuid.uuid4().hex[:14]}"


class GenerativeObject(BaseModel):
    """Durable AI-authored object. object_kind is a label, never a cognition switch."""

    id: str = Field(default_factory=new_object_id)
    user_id: str
    plan_id: Optional[str] = None
    goal_id: Optional[str] = None
    conversation_session_id: Optional[str] = None
    title: str
    purpose: str = ""
    object_kind: str = "workspace_object"
    schema_version: int = 1
    content_schema: Dict[str, Any] = Field(default_factory=dict)
    content: Dict[str, Any] = Field(default_factory=dict)
    interaction_schema: Dict[str, Any] = Field(default_factory=dict)
    presentation_hints: Dict[str, Any] = Field(default_factory=dict)
    evidence_refs: List[EvidenceRef] = Field(default_factory=list)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    generation_reason: str = ""
    status: ObjectStatus = "ready"
    revision: int = 1
    interaction_events: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    def touch(self, *, bump_revision: bool = False) -> None:
        self.updated_at = now_iso()
        if bump_revision:
            try:
                self.revision = int(self.revision or 1) + 1
            except (TypeError, ValueError):
                self.revision = 2

    def public(self) -> Dict[str, Any]:
        d = self.model_dump()
        # Cap events in public payload
        d["interaction_events"] = (self.interaction_events or [])[-20:]
        # API boundary: normalize card/reveal aliases for older persisted shapes
        d["content"] = normalize_content_blocks_for_display(d.get("content"))
        return d
