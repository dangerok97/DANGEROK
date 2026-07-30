"""Canonical dataclasses for the Daily Intelligence Layer."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


DAILY_SUMMARY_VERSION = "daily_intelligence/v1.0"


# ---------- primitives ----------
@dataclass
class TimeSlot:
    """Half-open interval [start, end) in ISO-8601 UTC."""
    start: str
    end: str
    duration_min: int
    kind: Optional[str] = None  # "busy" | "free" | None
    category: Optional[str] = None  # meeting/travel/study/... for busy slots

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EnergyLevel:
    level: str  # "high" | "medium" | "low"
    score: int  # 0..100 (higher = more energy expected remaining)
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------- top-level daily summary ----------
@dataclass
class DailySummary:
    date: str            # YYYY-MM-DD in the requested timezone
    timezone: str        # tz name used to bucket the day
    generated_at: str    # ISO-8601 UTC
    score: int           # 0..100 balance score (100 = calm/balanced, 0 = crushed)
    confidence: str      # "high" | "medium" | "low"

    # Raw counts
    total_events: int
    all_day_events: int
    is_weekend: bool
    is_holiday: bool
    is_vacation_day: bool

    # Time metrics (minutes)
    busy_minutes: int
    free_minutes: int
    consecutive_events: int   # count of back-to-back events (gap <= threshold)
    total_break_minutes: int  # total inter-event free time inside the "day window"

    # First / last event of the day (may be None on empty day)
    first_event_at: Optional[str]
    last_event_at: Optional[str]

    # Category buckets (minutes spent)
    by_category: Dict[str, int]

    # Slots
    busy_slots: List[Dict[str, Any]]  # each: TimeSlot.to_dict()
    free_slots: List[Dict[str, Any]]

    # Human-friendly outputs
    signals: List[str]         # e.g. ["many_meetings", "back_to_back"]
    warnings: List[str]        # e.g. ["stressful_day", "no_break"]
    opportunities: List[str]   # e.g. ["free_morning", "long_lunch_available"]

    # Energy
    energy_estimation: Dict[str, Any]  # EnergyLevel.to_dict()

    # Provenance
    version: str = DAILY_SUMMARY_VERSION
    source_counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
