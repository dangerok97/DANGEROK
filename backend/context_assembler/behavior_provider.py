"""BehaviorProfile provider for the Context Assembler.

Gated by env flag ``BEHAVIOR_PROFILE_ENABLED``. When disabled (default),
this provider is a strict no-op: it emits zero signals and never touches
the DB, guaranteeing bit-identical ``context_hash`` before and after
this iteration.

When enabled it produces one deterministic ``behavior.profile`` signal
composed from the behavioral engine snapshot. It NEVER modifies ranking,
Decision Engine or Explainability outputs; it only extends the context
provenance.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict

from .types import ProviderResult, Signal


PROVIDER_NAME = "behavior_profile"
PROVIDER_VERSION = "v1.0"


def _flag_on() -> bool:
    return os.environ.get("BEHAVIOR_PROFILE_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")


async def behavior_profile_provider(db, user_id: str) -> ProviderResult:
    """STRICT no-op when flag is OFF: no DB read, no logging."""
    t0 = time.perf_counter()
    if not _flag_on():
        return ProviderResult(name=PROVIDER_NAME, duration_ms=(time.perf_counter() - t0) * 1000)

    try:
        # Lazy import to keep the coupling loose when the flag is off.
        from behavioral_intelligence import BehavioralIntelligenceService

        svc = BehavioralIntelligenceService(db)
        profile = await svc.get_profile(user_id, persist=False)

        payload: Dict[str, Any] = {
            "planning_style": profile.planning_style.value,
            "completion_style": profile.completion_style.value,
            "activity_level": profile.activity_level.value,
            "calendar_usage": profile.calendar_usage.value,
            "consistency": profile.consistency.value,
            "procrastination_index": profile.procrastination_index,
            "avg_completion_minutes": profile.average_completion_time_minutes,
            "avg_postpone_minutes": profile.average_postpone_time_minutes,
            "avg_session_minutes": profile.average_session_duration_minutes,
            "completion_rate": profile.decision_completion_rate,
            "postpone_rate": profile.decision_postpone_rate,
            "dismiss_rate": profile.decision_dismiss_rate,
            "sample_size": profile.sample_size,
            "confidence_bucket": profile.confidence.value,
        }
        signal = Signal(
            key="behavior.profile",
            value=payload,
            value_type="object",
            source_module=PROVIDER_NAME,
            confidence=0.8,
            verified=False,
            sensitivity="personal",
            freshness="fresh",
            reliability_tier="system_derived",
        )
        return ProviderResult(
            name=PROVIDER_NAME,
            signals=[signal],
            duration_ms=(time.perf_counter() - t0) * 1000,
        )
    except Exception as e:
        return ProviderResult(
            name=PROVIDER_NAME,
            error=f"{type(e).__name__}",
            duration_ms=(time.perf_counter() - t0) * 1000,
        )
