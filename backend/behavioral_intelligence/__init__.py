"""
Behavioral Intelligence Engine (Iterazione 15).

PRINCIPIO: OSSERVATORE PASSIVO. Non crea Decision, non modifica ranking,
non influenza altri moduli. Compone timeline append-only + metriche
incrementali + pattern deterministici a partire da collezioni esistenti.

Modules:
- types      : Pydantic models (events, metrics, patterns, profile).
- storage    : DAL for behavioral collections (append-only).
- timeline   : Append-only event log wrapper.
- observers  : Lazy-sync from source collections (decision_action_history,
               ingestion_events, connector_instances, context_snapshots,
               daily_summaries).
- metrics    : Incremental counters and time-based aggregates.
- patterns   : Deterministic pattern detectors (NO LLM, NO ML).
- confidence : Confidence-level classifier (low/medium/high).
- service    : Orchestrator (single entrypoint for router).
- provider   : Context Assembler provider gated by BEHAVIOR_PROFILE_ENABLED.
"""

from .service import BehavioralIntelligenceService  # noqa: F401
from .provider import BehaviorProfileProvider  # noqa: F401
from .types import (  # noqa: F401
    BehavioralEvent,
    BehavioralEventType,
    BehaviorMetrics,
    BehaviorPattern,
    BehaviorProfile,
    Confidence,
    Trend,
)
