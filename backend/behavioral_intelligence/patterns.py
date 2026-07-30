"""Deterministic pattern detection.

STRICTLY no ML/LLM/embeddings. Each detector is a hand-written rule with
observable thresholds. If sample size is insufficient, the pattern is
suppressed (never emitted with fake confidence).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .confidence import classify
from .storage import BehavioralStorage
from .types import BehaviorMetrics, BehaviorPattern, Confidence, Trend

MIN_SAMPLE = 5  # never emit a pattern below this


def _sum(counts):
    return sum(x.count for x in counts) if counts else 0


def _peak_hour_share(counts, start_hour: int, end_hour: int) -> float:
    """Return share of counts falling within [start_hour, end_hour] range."""
    total = _sum(counts)
    if not total:
        return 0.0
    peak = sum(x.count for x in counts if start_hour <= x.hour <= end_hour)
    return peak / total


def _peak_weekday_share(counts, weekdays: List[int]) -> float:
    total = _sum(counts)
    if not total:
        return 0.0
    peak = sum(x.count for x in counts if x.weekday in weekdays)
    return peak / total


def _dominant_hours(counts, top_n: int = 3) -> List[int]:
    if not counts:
        return []
    ordered = sorted(counts, key=lambda x: x.count, reverse=True)
    return [x.hour for x in ordered[:top_n]]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PatternDetector:
    """Compose ``BehaviorPattern`` objects from a metrics snapshot + history."""

    def __init__(self, storage: BehavioralStorage):
        self.store = storage

    async def detect(self, user_id: str, current: BehaviorMetrics) -> List[BehaviorPattern]:
        patterns: List[BehaviorPattern] = []
        # Lookup previous metric snapshot for trend estimation.
        prev = await self._prev_metrics(user_id)
        # Helper: trend based on delta between prev.X and current.X.
        def trend_of(cur_v: Optional[float], prev_v: Optional[float]) -> Trend:
            if prev_v is None or cur_v is None:
                return Trend.STABLE
            if cur_v > prev_v * 1.15:
                return Trend.INCREASING
            if cur_v < prev_v * 0.85:
                return Trend.DECREASING
            return Trend.STABLE

        first_seen = _now()
        last_seen = _now()

        # ------------------------ P1: morning completer
        share = _peak_hour_share(current.completed_by_hour, 6, 12)
        n_comp = current.decisions_completed
        if n_comp >= MIN_SAMPLE and share >= 0.5:
            patterns.append(BehaviorPattern(
                id="morning_completer",
                title="Completa spesso attività al mattino",
                description="La maggior parte delle tue attività completate avviene tra le 06:00 e le 12:00.",
                confidence=classify(n_comp),
                sample_size=n_comp,
                first_seen=first_seen,
                last_seen=last_seen,
                trend=trend_of(share, _peak_hour_share(prev.completed_by_hour, 6, 12) if prev else None),
                active=True,
                evidence={"morning_share": round(share, 3), "completed_total": n_comp},
            ))

        # ------------------------ P2: evening postponer
        share = _peak_hour_share(current.postponed_by_hour, 18, 23)
        n_post = current.decisions_postponed
        if n_post >= MIN_SAMPLE and share >= 0.4:
            patterns.append(BehaviorPattern(
                id="evening_postponer",
                title="Tendi a rimandare attività serali",
                description="Molte delle tue Decision vengono rimandate nella fascia serale (18–23).",
                confidence=classify(n_post),
                sample_size=n_post,
                first_seen=first_seen,
                last_seen=last_seen,
                trend=trend_of(share, _peak_hour_share(prev.postponed_by_hour, 18, 23) if prev else None),
                active=True,
                evidence={"evening_share": round(share, 3), "postponed_total": n_post},
            ))

        # ------------------------ P3: heavy calendar user
        if current.calendar_syncs >= 5 and current.calendar_events_imported >= 5:
            patterns.append(BehaviorPattern(
                id="heavy_calendar_user",
                title="Usi molto Google Calendar",
                description="Google Calendar è la tua fonte principale di impegni.",
                confidence=classify(current.calendar_syncs + current.calendar_events_imported),
                sample_size=current.calendar_syncs + current.calendar_events_imported,
                first_seen=first_seen,
                last_seen=last_seen,
                trend=trend_of(current.calendar_syncs, prev.calendar_syncs if prev else None),
                active=True,
                evidence={"syncs": current.calendar_syncs, "imported": current.calendar_events_imported},
            ))

        # ------------------------ P4: post-dinner opener
        share = _peak_hour_share(_synth_hour_from_last_open(current), 20, 23)
        opens = current.daily_openings
        if opens >= MIN_SAMPLE and current.avg_first_open_local_hour is not None and current.avg_first_open_local_hour >= 20:
            patterns.append(BehaviorPattern(
                id="post_dinner_opener",
                title="Apri ORA soprattutto dopo cena",
                description="La tua prima apertura giornaliera cade spesso dopo le 20:00.",
                confidence=classify(opens),
                sample_size=opens,
                first_seen=first_seen,
                last_seen=last_seen,
                trend=Trend.STABLE,
                active=True,
                evidence={"avg_first_open_hour": current.avg_first_open_local_hour, "openings": opens},
            ))

        # ------------------------ P5: quick winner (short completion time)
        if current.avg_completion_minutes is not None and n_comp >= MIN_SAMPLE and current.avg_completion_minutes <= 15:
            patterns.append(BehaviorPattern(
                id="quick_winner",
                title="Chiudi rapidamente le attività",
                description="Completi le Decision in media in meno di 15 minuti.",
                confidence=classify(n_comp),
                sample_size=n_comp,
                first_seen=first_seen,
                last_seen=last_seen,
                trend=trend_of(-1 * current.avg_completion_minutes, -1 * prev.avg_completion_minutes if prev and prev.avg_completion_minutes else None),
                active=True,
                evidence={"avg_completion_minutes": current.avg_completion_minutes},
            ))

        # ------------------------ P6: weekday power user
        weekday_share = _peak_weekday_share(current.completed_by_weekday, [0, 1, 2, 3, 4])
        if n_comp >= MIN_SAMPLE and weekday_share >= 0.7:
            patterns.append(BehaviorPattern(
                id="weekday_power_user",
                title="Attivo soprattutto nei giorni feriali",
                description="Completi la maggior parte delle attività dal lunedì al venerdì.",
                confidence=classify(n_comp),
                sample_size=n_comp,
                first_seen=first_seen,
                last_seen=last_seen,
                trend=Trend.STABLE,
                active=True,
                evidence={"weekday_share": round(weekday_share, 3)},
            ))

        # ------------------------ P7: weekend light user
        weekend_share = _peak_weekday_share(current.completed_by_weekday, [5, 6])
        if opens >= MIN_SAMPLE and weekend_share <= 0.15:
            patterns.append(BehaviorPattern(
                id="weekend_light_user",
                title="Usi poco l'app nel weekend",
                description="Fine settimana con bassa attività.",
                confidence=classify(opens),
                sample_size=opens,
                first_seen=first_seen,
                last_seen=last_seen,
                trend=Trend.STABLE,
                active=True,
                evidence={"weekend_share": round(weekend_share, 3)},
            ))

        return patterns

    async def _prev_metrics(self, user_id: str) -> Optional[BehaviorMetrics]:
        raw = await self.store.latest_snapshot("behavior_metric_snapshots", user_id)
        if not raw:
            return None
        try:
            # Strip surrogate fields not present in Pydantic model.
            raw.pop("id", None)
            return BehaviorMetrics(**raw)
        except Exception:
            return None


def _synth_hour_from_last_open(m: BehaviorMetrics):
    """Best-effort projection: reuse completed_by_hour skeleton for shape."""
    return m.completed_by_hour
