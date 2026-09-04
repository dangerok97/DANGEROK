"""Unified Home item model and response schemas."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# 1.3 — Presentation Aggregation Layer: one card per Goal (flag-gated attach);
# identical to 1.0 inputs when GOAL_ENGINE_ENABLED=0 (no goal_* attached).
RANKING_VERSION = "home-rank-1.4"
PRESENTATION_VERSION = "home-pres-1.0"

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
    # Goal context (invisible layer — no Goal UX). Present only when linked + flag ON.
    # Refs only — never embed a full Goal document.
    goal_id: Optional[str] = None
    goal_title: Optional[str] = None
    goal_type: Optional[str] = None
    goal_status: Optional[str] = None
    goal_progress: Optional[float] = None  # 0–100 when reliable; omit for travel soft phase
    goal_progress_label: Optional[str] = None
    goal_next_action: Optional[str] = None
    goal_target_date: Optional[str] = None
    goal_blockers: Optional[List[str]] = None
    goal_project_id: Optional[str] = None

    def to_public(self) -> Dict[str, Any]:
        """Serialize for API — omit raw score from client payloads."""
        d = self.model_dump()
        d.pop("score", None)
        # Drop null / empty goal_* when flag off / unlinked — keep payload lean
        for k in (
            "goal_id", "goal_title", "goal_type", "goal_status",
            "goal_progress", "goal_progress_label", "goal_next_action",
            "goal_target_date", "goal_blockers", "goal_project_id",
        ):
            if d.get(k) is None or d.get(k) == []:
                d.pop(k, None)
        # Promote presentation aggregation fields to top-level for FE
        meta = d.get("meta") or {}
        for pk in (
            "presentation_id", "card_type", "subtitle", "next_action",
            "supporting_details", "source_refs", "hidden_artifact_count",
            "presentation_badges", "presentation_version",
            # Ranking/presentation signals for Horizon + FE (no PII)
            "temporal_state", "actionable_now", "route", "canonical_execution",
            "life_os_plan_id", "current_item_title", "ownership",
        ):
            if meta.get(pk) is not None and pk not in d:
                d[pk] = meta[pk]
        if d.get("presentation_id") and not d.get("generated_at"):
            d["generated_at"] = meta.get("aggregated_at")
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
    # Proactive Engine — max 3; omit/empty → FE hides section (no spam)
    ora_ti_consiglia: List[Dict[str, Any]] = Field(default_factory=list)
    # V3.1 — what ORA is actually waiting for an answer to. These are not
    # suggestions the attention layer thought worth surfacing: each one is a
    # blocker on a real piece of work, and answering it continues that work.
    # Empty when nothing is blocked, which is the common case.
    open_questions: List[Dict[str, Any]] = Field(default_factory=list)
    # V3.7 — what ORA thought was worth a quiet line, and then thought was
    # worth it *now*. Two judgements, both the model's, both already made by
    # the time Home reads this: nothing is decided at render time. Human words
    # only — no relevance, no urgency, no confidence. Usually empty.
    opportunities: List[Dict[str, Any]] = Field(default_factory=list)
    # V3.8 — one line about what ORA has actually been doing, or nothing.
    # Read from a record written by work that ran; there is no path from
    # "this screen would like something to say" to a line appearing here.
    ambient: Optional[Dict[str, Any]] = None
    # V3.9 — what ORA is working on, as outcomes. Never steps, never plan
    # status: somebody wants to know whether the thing is handled, not how
    # many stages it has.
    agent_work: List[Dict[str, Any]] = Field(default_factory=list)
    # V3.8 — present only when ORA has actually judged something worth an
    # interruption and could not deliver it. Absent at first launch, absent
    # when nothing is waiting: the question is never asked about a feature.
    notification_prompt: Optional[Dict[str, Any]] = None
    connection_warnings: List[ConnectionWarning] = Field(default_factory=list)
    google_calendar: Dict[str, Any] = Field(default_factory=dict)
    generated_at: str
    ranking_version: str = RANKING_VERSION
    partial: bool = False
    # DEV-only ranking trace (HOME_RANK_TRACE=1 or DEV=1) — no PII dumps
    dev_rank_trace: Optional[List[Dict[str, Any]]] = None


class HomeActionBody(BaseModel):
    item_id: str
    action: str  # complete|snooze|ignore|correct|open|mark_insight_read|resume|dismiss_banner
    until: Optional[str] = None
    reason: Optional[str] = None
    priority: Optional[PriorityBand] = None
    note: Optional[str] = None
