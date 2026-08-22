"""Suggestion document model + API bodies."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from proactive_engine.types import PriorityLevel, SuggestionStatus, SuggestionType


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_suggestion_id() -> str:
    return f"psug_{uuid.uuid4().hex[:14]}"


class ScoreFactor(BaseModel):
    code: str
    label: str
    weight: float = 0.0
    value: float = 0.0
    detail: Optional[str] = None


class SuggestionAction(BaseModel):
    """Concrete next step — never fake completion."""

    kind: str  # open|recover_session|prep|modify_event|flashcards|navigate|schedule
    label: str
    route: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)


class SuggestionExplain(BaseModel):
    """Structured explainability — no chain-of-thought."""

    summary: str
    factors: List[ScoreFactor] = Field(default_factory=list)
    would_assistant_speak: bool = True
    gate_notes: List[str] = Field(default_factory=list)


class Suggestion(BaseModel):
    id: str = Field(default_factory=new_suggestion_id)
    user_id: str
    title: str
    description: Optional[str] = None
    reason: str = ""
    type: SuggestionType = "generic"
    priority: PriorityLevel = "medium"
    importance: float = 0.0  # 0–1
    urgency: float = 0.0  # 0–1
    confidence: float = 0.0  # 0–1
    score: float = 0.0  # composite; never random
    source: str = ""  # study_plan|travel_project|calendar|document|goal|…
    goal_id: Optional[str] = None
    project_id: Optional[str] = None
    calendar_event: Optional[str] = None
    document_id: Optional[str] = None
    study_plan_id: Optional[str] = None
    travel_project_id: Optional[str] = None
    action: Optional[SuggestionAction] = None
    status: SuggestionStatus = "candidate"
    factors: List[ScoreFactor] = Field(default_factory=list)
    explain: Optional[SuggestionExplain] = None
    dedupe_key: str = ""
    expires_at: Optional[str] = None
    snooze_until: Optional[str] = None
    dismissed: bool = False
    accepted: bool = False
    completed: bool = False
    accept_result: Optional[Dict[str, Any]] = None
    meta: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    def public(self, *, include_score: bool = False) -> Dict[str, Any]:
        d = self.model_dump()
        if not include_score:
            d.pop("score", None)
        return d


class SuggestionCandidate(BaseModel):
    """Pre-gate candidate from a generator."""

    title: str
    description: Optional[str] = None
    reason: str
    type: SuggestionType
    source: str
    goal_id: Optional[str] = None
    project_id: Optional[str] = None
    calendar_event: Optional[str] = None
    document_id: Optional[str] = None
    study_plan_id: Optional[str] = None
    travel_project_id: Optional[str] = None
    action: Optional[SuggestionAction] = None
    dedupe_key: str
    expires_at: Optional[str] = None
    importance_hint: float = 0.5
    urgency_hint: float = 0.5
    confidence: float = 0.7
    # Optional, domain-neutral quality signal from the emitting layer: how
    # actionable and novel it judged this item to be. Sits beside the other
    # hints because it is the same kind of thing — a claim the scorer weighs,
    # not a permission. Legacy generators leave it None and score exactly as
    # they did before it existed.
    quality_hint: Optional[float] = None
    evidence: Dict[str, Any] = Field(default_factory=dict)
    meta: Dict[str, Any] = Field(default_factory=dict)


class SnoozeBody(BaseModel):
    preset: Optional[Literal["15m", "1h", "stasera", "domani", "custom"]] = None
    until: Optional[str] = None  # required when preset=custom


class SearchBody(BaseModel):
    q: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    limit: int = 40


class LearningStats(BaseModel):
    user_id: str
    suggestion_type: str
    source: str
    accepted: int = 0
    dismissed: int = 0
    completed: int = 0
    multiplier: float = 1.0
    updated_at: str = Field(default_factory=now_iso)
