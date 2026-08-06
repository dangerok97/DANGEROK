"""Goal document model — durable outcome identity (collection: goals)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from goal_engine.goal_types import GoalStatus, GoalSubtype, GoalType


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_goal_id() -> str:
    return f"goal_{uuid.uuid4().hex[:14]}"


class GoalProgress(BaseModel):
    """Computed projection — never invent a fixed percentage."""

    ratio: float = 0.0
    label: Optional[str] = None
    phase: Optional[str] = None
    completed_units: int = 0
    total_units: int = 0
    source: str = "none"  # study_sessions | travel_prep | none
    updated_at: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class Goal(BaseModel):
    id: str = Field(default_factory=new_goal_id)
    user_id: str
    goal_type: GoalType = "generic"
    goal_subtype: Optional[GoalSubtype] = None
    title: str
    description: Optional[str] = None
    status: GoalStatus = "idea"
    priority: Optional[int] = None
    importance: Optional[int] = None
    urgency: Optional[int] = None
    desired_outcome: Optional[str] = None
    current_state: Optional[str] = None
    next_action: Optional[str] = None
    progress: GoalProgress = Field(default_factory=GoalProgress)
    completion_percentage: float = 0.0  # 0–100, derived from progress.ratio
    brain_node_id: Optional[str] = None
    # Shadow link to Life Object Engine (non-breaking; optional)
    life_object_id: Optional[str] = None
    project_id: Optional[str] = None  # action_projects id (bag ≠ Goal)
    study_plan_id: Optional[str] = None
    travel_project_id: Optional[str] = None
    source_action_session_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    linked_documents: List[str] = Field(default_factory=list)
    linked_calendar_events: List[str] = Field(default_factory=list)
    linked_decisions: List[str] = Field(default_factory=list)
    linked_people: List[str] = Field(default_factory=list)
    linked_places: List[str] = Field(default_factory=list)
    linked_memories: List[str] = Field(default_factory=list)
    linked_finances: List[str] = Field(default_factory=list)
    created_from: Dict[str, Any] = Field(default_factory=dict)
    # created_from: intent, intent_subtype, source_type, source_id, home_item_id, artifact
    merged_into_id: Optional[str] = None
    merged_from_ids: List[str] = Field(default_factory=list)
    target_date: Optional[str] = None
    start_date: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    completed_at: Optional[str] = None
    cancelled_at: Optional[str] = None
    archived_at: Optional[str] = None

    def apply_progress(self, prog: GoalProgress) -> None:
        self.progress = prog
        ratio = max(0.0, min(1.0, float(prog.ratio or 0.0)))
        self.completion_percentage = round(ratio * 100.0, 2)
        self.updated_at = now_iso()

    def public(self) -> Dict[str, Any]:
        d = self.model_dump()
        d["progress"] = self.progress.model_dump()
        return d


class GoalCreateBody(BaseModel):
    title: str
    goal_type: GoalType = "generic"
    goal_subtype: Optional[str] = None
    description: Optional[str] = None
    status: GoalStatus = "idea"
    priority: Optional[int] = None
    importance: Optional[int] = None
    urgency: Optional[int] = None
    desired_outcome: Optional[str] = None
    current_state: Optional[str] = None
    next_action: Optional[str] = None
    project_id: Optional[str] = None
    study_plan_id: Optional[str] = None
    travel_project_id: Optional[str] = None
    source_action_session_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    linked_documents: List[str] = Field(default_factory=list)
    linked_calendar_events: List[str] = Field(default_factory=list)
    linked_decisions: List[str] = Field(default_factory=list)
    created_from: Dict[str, Any] = Field(default_factory=dict)
    target_date: Optional[str] = None
    start_date: Optional[str] = None
    brain_node_id: Optional[str] = None
    life_object_id: Optional[str] = None


class GoalPatchBody(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[GoalStatus] = None
    priority: Optional[int] = None
    importance: Optional[int] = None
    urgency: Optional[int] = None
    desired_outcome: Optional[str] = None
    current_state: Optional[str] = None
    next_action: Optional[str] = None
    goal_subtype: Optional[str] = None
    project_id: Optional[str] = None
    study_plan_id: Optional[str] = None
    travel_project_id: Optional[str] = None
    brain_node_id: Optional[str] = None
    life_object_id: Optional[str] = None
    linked_documents: Optional[List[str]] = None
    linked_calendar_events: Optional[List[str]] = None
    linked_decisions: Optional[List[str]] = None
    linked_people: Optional[List[str]] = None
    linked_places: Optional[List[str]] = None
    linked_memories: Optional[List[str]] = None
    linked_finances: Optional[List[str]] = None
    target_date: Optional[str] = None
    start_date: Optional[str] = None


class GoalMergeBody(BaseModel):
    source_goal_id: str
    target_goal_id: str
    prefer_target_title: bool = True


class GoalSearchBody(BaseModel):
    q: Optional[str] = None
    goal_type: Optional[str] = None
    status: Optional[str] = None
    limit: int = 40
