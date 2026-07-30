"""DailySummaryProvider — feature-flagged (DAILY_SUMMARY_ENABLED).

When the flag is OFF (default) it's a strict no-op: zero signals, zero
DB reads → `context_hash` byte-stable across the flag boundary as long
as no calendar data is present.

When ON, computes today's DailySummary (deterministic, rules-only) and
emits summary metadata as signals. Never contains sensitive titles.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import List

from .types import ProviderResult, Signal


def _flag_enabled() -> bool:
    return os.environ.get("DAILY_SUMMARY_ENABLED", "false").lower() in ("1", "true", "yes")


async def daily_summary_provider(db, user_id: str) -> ProviderResult:
    t0 = time.perf_counter()
    if not _flag_enabled():
        return ProviderResult(name="daily_summary", duration_ms=(time.perf_counter() - t0) * 1000)

    try:
        from daily_intelligence import DailySummaryService  # lazy import
    except Exception:
        return ProviderResult(name="daily_summary", error="unavailable", duration_ms=(time.perf_counter() - t0) * 1000)

    svc = DailySummaryService(db)
    summary = await svc.today(user_id)
    now = datetime.now(timezone.utc).isoformat()

    signals: List[Signal] = []
    signals.append(Signal(
        key="daily_summary",
        value={
            "date": summary.date,
            "score": summary.score,
            "confidence": summary.confidence,
            "busy_minutes": summary.busy_minutes,
            "free_minutes": summary.free_minutes,
            "total_events": summary.total_events,
            "consecutive_events": summary.consecutive_events,
            "energy_level": (summary.energy_estimation or {}).get("level"),
            "signals": summary.signals,
            "warnings": summary.warnings,
            "opportunities": summary.opportunities,
        },
        value_type="object",
        source_module="daily_summary",
        confidence=1.0,
        verified=True,
        sensitivity="personal",
        observed_at=now,
        reliability_tier="official",
    ))
    signals.append(Signal(
        key="daily_summary_enabled",
        value=True,
        value_type="boolean",
        source_module="daily_summary",
        confidence=1.0,
        verified=True,
        sensitivity="public",
        observed_at=now,
        reliability_tier="official",
    ))

    return ProviderResult(name="daily_summary", signals=signals, duration_ms=(time.perf_counter() - t0) * 1000)
