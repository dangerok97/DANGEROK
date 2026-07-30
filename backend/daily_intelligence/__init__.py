"""ORA Daily Intelligence Layer.

Deterministic (no LLM), read-only. Transforms a user's calendar events
for a given day into a `DailySummary` that other layers can consume.

The layer NEVER creates Decisions, notifications, or side effects. It
only observes and describes the day.
"""
from .service import DailySummaryService
from .types import (
    DAILY_SUMMARY_VERSION,
    DailySummary,
    EnergyLevel,
    TimeSlot,
)

__all__ = [
    "DAILY_SUMMARY_VERSION",
    "DailySummary",
    "DailySummaryService",
    "EnergyLevel",
    "TimeSlot",
]
