"""Study plan + session models (UTC storage, Europe/Rome default display TZ)."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

DEFAULT_TZ = "Europe/Rome"

PlanStatus = Literal[
    "draft",
    "awaiting_confirmation",
    "active",
    "paused",
    "completed",
    "cancelled",
]

Intensity = Literal["light", "distributed", "intensive", "custom"]

SessionType = Literal[
    "study",
    "review",
    "flashcards",
    "interrogami",
    "exam_questions",
]

SessionStatus = Literal[
    "planned",
    "in_progress",
    "completed",
    "snoozed",
    "skipped",
    "cancelled",
]

ToolPref = Literal["study", "review", "flashcards", "interrogami", "exam_questions"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


def make_idempotency_key(
    user_id: str,
    source_priority_id: Optional[str],
    exam_name: str,
    exam_date: str,
) -> str:
    raw = f"{user_id}|{source_priority_id or ''}|{exam_name.strip().lower()}|{exam_date[:10]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class TimeRange(BaseModel):
    start: str  # HH:MM local
    end: str


class StudySessionItem(BaseModel):
    id: str = Field(default_factory=lambda: _uid("ssn"))
    plan_id: str = ""
    user_id: str = ""
    session_type: SessionType = "study"
    status: SessionStatus = "planned"
    title: str = ""
    topic: Optional[str] = None
    starts_at: str  # UTC ISO
    ends_at: str
    duration_minutes: int = 60
    document_ids: List[str] = Field(default_factory=list)
    calendar_node_id: Optional[str] = None
    google_event_id: Optional[str] = None
    google_calendar_id: Optional[str] = None
    google_sync_status: Optional[str] = None  # synced|failed|pending|skipped|deleted
    completed_at: Optional[str] = None
    snoozed_until: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class StudyPlan(BaseModel):
    id: str = Field(default_factory=lambda: _uid("spl"))
    user_id: str
    status: PlanStatus = "draft"
    exam_name: str
    subject: Optional[str] = None
    exam_date: Optional[str] = None  # UTC ISO date/datetime
    timezone: str = DEFAULT_TZ
    intensity: Intensity = "distributed"
    daily_minutes: int = 60
    available_days: List[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])  # Mon=0
    preferred_ranges: List[TimeRange] = Field(default_factory=list)
    tools: List[ToolPref] = Field(default_factory=lambda: ["study", "review"])
    document_ids: List[str] = Field(default_factory=list)
    calendar_sync: bool = False
    source_priority_id: Optional[str] = None
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    action_session_id: Optional[str] = None
    project_id: Optional[str] = None
    brain_node_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    sessions: List[StudySessionItem] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)
    flashcard_document_ids: List[str] = Field(default_factory=list)
    interrogami_document_ids: List[str] = Field(default_factory=list)
    google_sync: Dict[str, Any] = Field(default_factory=dict)
    preview: Dict[str, Any] = Field(default_factory=dict)
    answers: Dict[str, Any] = Field(default_factory=dict)
    duplicate_of: Optional[str] = None
    progress: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    confirmed_at: Optional[str] = None
    cancelled_at: Optional[str] = None

    def public(self) -> Dict[str, Any]:
        completed = sum(1 for s in self.sessions if s.status == "completed")
        total = len(self.sessions)
        today = datetime.now(timezone.utc).date().isoformat()
        today_sessions = [
            s.model_dump() for s in self.sessions
            if (s.starts_at or "")[:10] == today and s.status in ("planned", "in_progress", "snoozed")
        ]
        next_session = None
        for s in sorted(self.sessions, key=lambda x: x.starts_at or ""):
            if s.status in ("planned", "in_progress", "snoozed"):
                next_session = s.model_dump()
                break
        return {
            "id": self.id,
            "user_id": self.user_id,
            "status": self.status,
            "exam_name": self.exam_name,
            "subject": self.subject,
            "exam_date": self.exam_date,
            "timezone": self.timezone,
            "intensity": self.intensity,
            "daily_minutes": self.daily_minutes,
            "available_days": self.available_days,
            "preferred_ranges": [r.model_dump() for r in self.preferred_ranges],
            "tools": self.tools,
            "document_ids": self.document_ids,
            "calendar_sync": self.calendar_sync,
            "source_priority_id": self.source_priority_id,
            "action_session_id": self.action_session_id,
            "project_id": self.project_id,
            "brain_node_id": self.brain_node_id,
            "idempotency_key": self.idempotency_key,
            "sessions": [s.model_dump() for s in self.sessions],
            "topics": self.topics,
            "flashcard_document_ids": self.flashcard_document_ids,
            "interrogami_document_ids": self.interrogami_document_ids,
            "google_sync": self.google_sync,
            "preview": self.preview,
            "duplicate_of": self.duplicate_of,
            "progress": {
                "completed_sessions": completed,
                "total_sessions": total,
                "ratio": (completed / total) if total else 0.0,
                "today_sessions": today_sessions,
                "next_session": next_session,
                **self.progress,
            },
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "confirmed_at": self.confirmed_at,
        }


class DuplicateResolution(BaseModel):
    action: Literal["open", "update", "merge", "replace", "create_anyway"]
    existing_plan_id: Optional[str] = None


class PlanModifyBody(BaseModel):
    daily_minutes: Optional[int] = None
    available_days: Optional[List[int]] = None
    preferred_ranges: Optional[List[TimeRange]] = None
    intensity: Optional[Intensity] = None
    document_ids: Optional[List[str]] = None
    calendar_sync: Optional[bool] = None
    tools: Optional[List[ToolPref]] = None
    exam_date: Optional[str] = None


class SessionActionBody(BaseModel):
    action: Literal["start", "complete", "snooze", "skip"]
    snooze_minutes: Optional[int] = 60
