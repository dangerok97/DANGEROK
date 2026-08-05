"""Action Engine session / turn / answer models."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


ENGINE_VERSION = "action-engine-1.0"

FlowCategory = Literal[
    "study",
    "event",
    "travel",
    "medical",
    "admin",
    "generic",
]

SessionStatus = Literal["active", "completed", "cancelled"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AnswerOption(BaseModel):
    id: str
    label: str
    value: Any = None


class QuestionTurn(BaseModel):
    id: str
    question: str
    explanation: Optional[str] = None
    input_kind: Literal["chips", "chips_or_text", "text"] = "chips"
    options: List[AnswerOption] = Field(default_factory=list)
    allow_skip: bool = False
    required: bool = True
    brain_key: Optional[str] = None  # knowledge property key


class TurnAnswer(BaseModel):
    turn_id: str
    option_id: Optional[str] = None
    value: Any = None
    text: Optional[str] = None
    answered_at: str = Field(default_factory=now_iso)


class ProposedAction(BaseModel):
    id: str
    kind: str  # calendar|reminder|project|study|maps|document|decision|merge
    label: str
    detail: Optional[str] = None
    status: Literal["proposed", "done", "skipped", "blocked"] = "proposed"
    meta: Dict[str, Any] = Field(default_factory=dict)


class ProjectLink(BaseModel):
    project_id: str
    title: str
    created: bool = True
    merge_candidate_id: Optional[str] = None
    merge_candidate_title: Optional[str] = None


class ActionSession(BaseModel):
    id: str
    user_id: str
    status: SessionStatus = "active"
    flow: FlowCategory
    engine_version: str = ENGINE_VERSION
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    home_item_id: Optional[str] = None
    home_item_type: Optional[str] = None
    title: str
    description: Optional[str] = None
    answers: Dict[str, Any] = Field(default_factory=dict)
    turn_history: List[TurnAnswer] = Field(default_factory=list)
    current_turn_id: Optional[str] = None
    turns: List[QuestionTurn] = Field(default_factory=list)
    proposed_actions: List[ProposedAction] = Field(default_factory=list)
    project: Optional[ProjectLink] = None
    brain_node_id: Optional[str] = None
    effects: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    completed_at: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)

    def public(self) -> Dict[str, Any]:
        current = None
        if self.current_turn_id:
            for t in self.turns:
                if t.id == self.current_turn_id:
                    current = t.model_dump()
                    break
        done = self.status != "active"
        progress = 0
        if self.turns:
            answered = len(self.turn_history)
            progress = min(1.0, answered / max(1, len(self.turns)))
        return {
            "id": self.id,
            "status": self.status,
            "flow": self.flow,
            "engine_version": self.engine_version,
            "title": self.title,
            "description": self.description,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "home_item_id": self.home_item_id,
            "home_item_type": self.home_item_type,
            "current_turn": current,
            "answers": self.answers,
            "progress": progress,
            "done": done,
            "proposed_actions": [p.model_dump() for p in self.proposed_actions],
            "project": self.project.model_dump() if self.project else None,
            "brain_node_id": self.brain_node_id,
            "effects": self.effects,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "meta": {
                k: v for k, v in self.meta.items()
                if k in ("merge_proposal", "next_focus_hint", "home_invalidate")
            },
        }


class OpenBody(BaseModel):
    """Open a guided flow from a Home item or source refs."""
    home_item: Optional[Dict[str, Any]] = None
    home_item_id: Optional[str] = None
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    item_type: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    due_at: Optional[str] = None
    start_at: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)
    force_new: bool = False


class AnswerBody(BaseModel):
    option_id: Optional[str] = None
    value: Any = None
    text: Optional[str] = None
    skip: bool = False


class MergeProjectBody(BaseModel):
    target_project_id: str
