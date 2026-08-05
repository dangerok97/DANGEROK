"""Unified Home item model and response schemas."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


RANKING_VERSION = "home-rank-1.0"

ItemType = Literal[
    "event",
    "travel",
    "bill",
    "study",
    "verify",
    "visit",
    "reply",
    "activity",
    "payment",
    "needs_review",
    "insight",
    "resume",
    "generic",
]

PriorityBand = Literal["critical", "today", "this_week", "waiting", "later"]
UrgencyLevel = Literal["none", "upcoming", "soon", "urgent", "overdue"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReasonFactor(BaseModel):
    code: str
    label: str
    weight: float = 0.0
    detail: Optional[str] = None


class HomeAction(BaseModel):
    id: str
    label: str
    kind: str  # complete|snooze|ignore|correct|open|navigate|maps|pay|study|confirm|resume
    route: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    primary: bool = False


class HomeItem(BaseModel):
    id: str
    type: ItemType
    subtype: Optional[str] = None
    title: str
    description: Optional[str] = None
    source_type: str
    source_id: str
    priority: PriorityBand = "later"
    urgency: UrgencyLevel = "none"
    confidence: Optional[float] = None
    due_at: Optional[str] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    duration_minutes: Optional[int] = None
    location: Optional[str] = None
    amount: Optional[str] = None
    status: str = "open"
    actions: List[HomeAction] = Field(default_factory=list)
    reason_factors: List[ReasonFactor] = Field(default_factory=list)
    reason_summary: Optional[str] = None
    score: float = 0.0  # persisted; never shown in UI
    ranking_version: str = RANKING_VERSION
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)

    def to_public(self) -> Dict[str, Any]:
        """Serialize for API — omit raw score from client payloads."""
        d = self.model_dump()
        d.pop("score", None)
        return d


class ExplanationBlock(BaseModel):
    summary: str
    factors: List[ReasonFactor] = Field(default_factory=list)
    sources: List[Dict[str, str]] = Field(default_factory=list)
    confidence: Optional[float] = None
    missing_data: List[str] = Field(default_factory=list)
    ranking_version: str = RANKING_VERSION
    item_id: Optional[str] = None


class SituationIndicator(BaseModel):
    id: str
    label: str
    value: str
    tone: Literal["default", "warning", "success", "info"] = "default"
    detail: Optional[str] = None


class CurrentSituation(BaseModel):
    indicators: List[SituationIndicator] = Field(default_factory=list)
    free_window: Optional[str] = None
    next_commitment: Optional[str] = None
    open_actions_count: int = 0
    needs_review_count: int = 0
    cta_label: str = "Vedi situazione completa"
    cta_route: str = "/situazione"


class InsightItem(BaseModel):
    id: str
    text: str
    source: str
    action: Optional[HomeAction] = None
    status: str = "active"  # active|read|ignored
    created_at: str
    valid_until: Optional[str] = None
    dedupe_key: str


class ConnectionWarning(BaseModel):
    code: str
    message: str
    severity: Literal["info", "warning"] = "info"
    dismissible: bool = True


class PriorityGroup(BaseModel):
    key: PriorityBand
    label: str
    items: List[Dict[str, Any]] = Field(default_factory=list)


class HomeResponse(BaseModel):
    primary_focus: Optional[Dict[str, Any]] = None
    explanation: Optional[ExplanationBlock] = None
    current_situation: CurrentSituation = Field(default_factory=CurrentSituation)
    priorities: List[PriorityGroup] = Field(default_factory=list)
    insights: List[InsightItem] = Field(default_factory=list)
    resume_item: Optional[Dict[str, Any]] = None
    connection_warnings: List[ConnectionWarning] = Field(default_factory=list)
    google_calendar: Dict[str, Any] = Field(default_factory=dict)
    generated_at: str
    ranking_version: str = RANKING_VERSION
    partial: bool = False


class HomeActionBody(BaseModel):
    item_id: str
    action: str  # complete|snooze|ignore|correct|open|mark_insight_read|resume|dismiss_banner
    until: Optional[str] = None
    reason: Optional[str] = None
    priority: Optional[PriorityBand] = None
    note: Optional[str] = None
