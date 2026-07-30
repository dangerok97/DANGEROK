"""Types for the Behavioral Intelligence Engine.

All data-classes are read-only outward projections. Persistence is done
via plain dicts in storage.py so the append-only invariant is enforced
at the DAL layer.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ------------------------ Enums ------------------------
class BehavioralEventType(str, Enum):
    # Decisions (from decision_action_history)
    DECISION_STARTED = "decision_started"
    DECISION_COMPLETED = "decision_completed"
    DECISION_PARTIAL = "decision_partial"
    DECISION_POSTPONED = "decision_postponed"
    DECISION_BLOCKED = "decision_blocked"
    DECISION_DISMISSED = "decision_dismissed"
    # Calendar (from ingestion_events + connector_instances)
    CALENDAR_CONNECTED = "calendar_connected"
    CALENDAR_DISCONNECTED = "calendar_disconnected"
    CALENDAR_SYNC = "calendar_sync"
    CALENDAR_EVENT_IMPORTED = "calendar_event_imported"
    CALENDAR_EVENT_UPDATED = "calendar_event_updated"
    CALENDAR_EVENT_DELETED = "calendar_event_deleted"
    # App usage (from middleware — passive)
    FIRST_APP_OPEN_TODAY = "first_app_open_today"
    LAST_APP_CLOSE = "last_app_close"
    MANUAL_REFRESH = "manual_refresh"
    # System pipeline (from daily_summaries + context_snapshots)
    DAILY_SUMMARY_GENERATED = "daily_summary_generated"
    CONTEXT_SNAPSHOT_CREATED = "context_snapshot_created"


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Trend(str, Enum):
    INCREASING = "increasing"
    STABLE = "stable"
    DECREASING = "decreasing"


class PlanningStyle(str, Enum):
    UNKNOWN = "unknown"
    STRUCTURED = "structured"
    FLEXIBLE = "flexible"
    REACTIVE = "reactive"


class CompletionStyle(str, Enum):
    UNKNOWN = "unknown"
    QUICK = "quick"
    STEADY = "steady"
    SLOW = "slow"
    MIXED = "mixed"


class ActivityLevel(str, Enum):
    UNKNOWN = "unknown"
    LIGHT = "light"
    MODERATE = "moderate"
    INTENSE = "intense"


class ConsistencyLevel(str, Enum):
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CalendarUsage(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ------------------------ Persisted document schemas ------------------------
class BehavioralEvent(BaseModel):
    """Immutable behavioral event record.

    Written by `timeline.append_event`. Never mutated.
    """

    id: str
    user_id: str
    event_type: BehavioralEventType
    occurred_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)
    source_ref: Optional[str] = None   # id/foreign key of the originating record
    source_type: Optional[str] = None  # e.g. "decision_action_history"
    recorded_at: datetime              # when this observer wrote it
    version: int = 1
    immutable: bool = True


class TimelineCursor(BaseModel):
    """Progress marker for lazy-sync observers (per user, per source)."""

    user_id: str
    source_type: str
    last_processed_at: Optional[datetime] = None
    last_processed_id: Optional[str] = None
    updated_at: datetime


# ------------------------ Metrics ------------------------
class HourBucket(BaseModel):
    hour: int  # 0..23
    count: int


class WeekdayBucket(BaseModel):
    weekday: int  # 0=Mon .. 6=Sun
    count: int


class BehaviorMetrics(BaseModel):
    user_id: str
    computed_at: datetime
    window_days: int
    confidence: Confidence

    # Session counts
    daily_openings: int = 0
    total_sessions: int = 0
    avg_session_minutes: Optional[float] = None
    last_open_at: Optional[datetime] = None
    avg_first_open_local_hour: Optional[float] = None

    # Decision counters
    decisions_started: int = 0
    decisions_completed: int = 0
    decisions_postponed: int = 0
    decisions_partial: int = 0
    decisions_blocked: int = 0
    decisions_dismissed: int = 0

    # Timings (minutes)
    avg_completion_minutes: Optional[float] = None
    avg_postpone_minutes: Optional[float] = None

    # Calendar
    calendar_syncs: int = 0
    calendar_events_imported: int = 0

    # Heatmaps
    completed_by_hour: List[HourBucket] = Field(default_factory=list)
    postponed_by_hour: List[HourBucket] = Field(default_factory=list)
    completed_by_weekday: List[WeekdayBucket] = Field(default_factory=list)
    postponed_by_weekday: List[WeekdayBucket] = Field(default_factory=list)

    # Rates (0..1)
    completion_rate: Optional[float] = None
    postpone_rate: Optional[float] = None
    dismiss_rate: Optional[float] = None

    # Sample size (drives confidence)
    sample_size: int = 0


class BehaviorPattern(BaseModel):
    id: str  # canonical stable id ("morning_completer" etc.)
    title: str
    description: str
    confidence: Confidence
    sample_size: int
    first_seen: datetime
    last_seen: datetime
    trend: Trend
    active: bool
    evidence: Dict[str, Any] = Field(default_factory=dict)


class BehaviorProfile(BaseModel):
    user_id: str
    computed_at: datetime
    confidence: Confidence

    planning_style: PlanningStyle = PlanningStyle.UNKNOWN
    completion_style: CompletionStyle = CompletionStyle.UNKNOWN
    activity_level: ActivityLevel = ActivityLevel.UNKNOWN
    calendar_usage: CalendarUsage = CalendarUsage.NONE
    consistency: ConsistencyLevel = ConsistencyLevel.UNKNOWN

    procrastination_index: Optional[float] = None      # 0..1
    average_daily_load: Optional[float] = None         # avg started decisions/day

    preferred_work_hours: List[int] = Field(default_factory=list)
    preferred_study_hours: List[int] = Field(default_factory=list)
    preferred_break_hours: List[int] = Field(default_factory=list)
    preferred_app_usage_hours: List[int] = Field(default_factory=list)

    average_completion_time_minutes: Optional[float] = None
    average_postpone_time_minutes: Optional[float] = None
    average_session_duration_minutes: Optional[float] = None

    decision_completion_rate: Optional[float] = None
    decision_postpone_rate: Optional[float] = None
    decision_dismiss_rate: Optional[float] = None

    sample_size: int = 0


class BehaviorConfidenceReport(BaseModel):
    """Aggregate confidence bucket per computed section."""

    user_id: str
    metrics: Confidence
    profile: Confidence
    patterns: Confidence
    events_observed: int
    days_observed: int
    computed_at: datetime


# ------------------------ Timeline projection ------------------------
class TimelinePage(BaseModel):
    items: List[BehavioralEvent]
    next_cursor: Optional[str] = None
    total: Optional[int] = None
