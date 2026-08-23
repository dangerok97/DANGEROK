"""Continuous Life Reasoning orchestration (V2.9.4).

Turns three explicitly-invoked passes into one event-driven pipeline:

    life mutation → LifeChangeSignal → ImpactAssessment → AttentionDecision
                  → (only if permitted) Suggestion

EVENT-DRIVEN, NOT POLLING-DRIVEN. A wake-up is requested when a signal is
actually emitted; while nothing changes, nothing runs, nothing is queried and
no AI call is made. Mongo remains the source of truth, so a lost in-process
wake-up costs latency, never work.
"""

from life_orchestration.scheduler import (
    orchestrator_stats,
    schedule_user_reasoning,
    start_orchestrator,
    stop_orchestrator,
)
from life_orchestration.service import OrchestrationService

__all__ = [
    "OrchestrationService",
    "schedule_user_reasoning",
    "start_orchestrator",
    "stop_orchestrator",
    "orchestrator_stats",
]
