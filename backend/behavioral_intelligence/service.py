"""Behavioral Intelligence Service — orchestrator.

Provides the read-only orchestration used by the /api/behavior/* router.
Every entrypoint performs a lazy-sync from source collections and then
composes metrics/patterns/profile snapshots. Snapshots are persisted
append-only so history is queryable but never rewritten.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from .confidence import aggregate, classify
from .metrics import MetricsBuilder
from .observers import Observers
from .patterns import PatternDetector
from .storage import BehavioralStorage, METRIC_SNAPSHOTS, PROFILE_SNAPSHOTS, PATTERN_SNAPSHOTS
from .timeline import BehavioralTimeline
from .types import (
    ActivityLevel,
    BehaviorConfidenceReport,
    BehaviorMetrics,
    BehaviorPattern,
    BehaviorProfile,
    BehavioralEventType,
    CalendarUsage,
    CompletionStyle,
    Confidence,
    ConsistencyLevel,
    PlanningStyle,
    TimelinePage,
)


class BehavioralIntelligenceService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.storage = BehavioralStorage(db)
        self.timeline = BehavioralTimeline(self.storage)
        self.observers = Observers(db, self.storage, self.timeline)
        self.metrics = MetricsBuilder(self.storage)
        self.patterns = PatternDetector(self.storage)
        self._indexes_ready = False

    async def ensure_ready(self) -> None:
        if not self._indexes_ready:
            await self.storage.ensure_indexes()
            self._indexes_ready = True

    # ------------------------ helpers ------------------------
    async def _sync_and_load(self, user_id: str) -> BehaviorMetrics:
        await self.ensure_ready()
        await self.observers.sync_all(user_id)
        m = await self.metrics.compute(user_id)
        return m

    def _persist_snapshot(self, coll: str, doc: Dict[str, Any]) -> None:
        # fire-and-forget helper (still awaited from callers)
        raise NotImplementedError

    # ------------------------ public: timeline ------------------------
    async def timeline_page(
        self,
        user_id: str,
        *,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        event_types: Optional[List[BehavioralEventType]] = None,
        limit: int = 200,
        skip: int = 0,
    ) -> TimelinePage:
        await self.ensure_ready()
        await self.observers.sync_all(user_id)
        return await self.timeline.get_page(
            user_id, since=since, until=until, event_types=event_types, limit=limit, skip=skip,
        )

    # ------------------------ public: metrics ------------------------
    async def get_metrics(self, user_id: str, *, persist: bool = True) -> BehaviorMetrics:
        m = await self._sync_and_load(user_id)
        if persist:
            doc = m.model_dump()
            doc["id"] = f"bmet_{uuid.uuid4().hex[:16]}"
            await self.storage.save_metric_snapshot(doc)
        return m

    # ------------------------ public: patterns ------------------------
    async def get_patterns(self, user_id: str, *, persist: bool = True) -> List[BehaviorPattern]:
        m = await self._sync_and_load(user_id)
        detected = await self.patterns.detect(user_id, m)
        # Filter out low-sample patterns even if detectors accidentally emit them.
        filtered = [p for p in detected if p.sample_size >= 5]
        if persist:
            doc = {
                "id": f"bpat_{uuid.uuid4().hex[:16]}",
                "user_id": user_id,
                "computed_at": datetime.now(timezone.utc),
                "patterns": [p.model_dump() for p in filtered],
                "count": len(filtered),
            }
            await self.storage.save_pattern_snapshot(doc)
        return filtered

    # ------------------------ public: profile ------------------------
    async def get_profile(self, user_id: str, *, persist: bool = True) -> BehaviorProfile:
        m = await self._sync_and_load(user_id)

        # Derive fields deterministically.
        completed = m.decisions_completed
        started = m.decisions_started or 0
        postponed = m.decisions_postponed
        dismissed = m.decisions_dismissed

        # Planning style — inferred from calendar usage + sample volume.
        planning = PlanningStyle.UNKNOWN
        if m.calendar_syncs >= 3 and m.calendar_events_imported >= 5:
            planning = PlanningStyle.STRUCTURED
        elif started >= 5 and m.calendar_syncs <= 1:
            planning = PlanningStyle.REACTIVE
        elif started >= 5:
            planning = PlanningStyle.FLEXIBLE

        # Completion style — from average completion time.
        completion_style = CompletionStyle.UNKNOWN
        if m.avg_completion_minutes is not None and completed >= 5:
            if m.avg_completion_minutes <= 15:
                completion_style = CompletionStyle.QUICK
            elif m.avg_completion_minutes <= 45:
                completion_style = CompletionStyle.STEADY
            elif m.avg_completion_minutes <= 120:
                completion_style = CompletionStyle.SLOW
            else:
                completion_style = CompletionStyle.MIXED

        # Activity level.
        activity = ActivityLevel.UNKNOWN
        if started >= 20 or m.daily_openings >= 20:
            activity = ActivityLevel.INTENSE
        elif started >= 8 or m.daily_openings >= 8:
            activity = ActivityLevel.MODERATE
        elif started >= 1 or m.daily_openings >= 1:
            activity = ActivityLevel.LIGHT

        # Consistency — number of distinct days with openings.
        # (Approximation: count of first-open events is 1 per day).
        consistency = ConsistencyLevel.UNKNOWN
        if m.daily_openings >= 20:
            consistency = ConsistencyLevel.HIGH
        elif m.daily_openings >= 8:
            consistency = ConsistencyLevel.MEDIUM
        elif m.daily_openings >= 1:
            consistency = ConsistencyLevel.LOW

        # Calendar usage.
        cal_usage = CalendarUsage.NONE
        if m.calendar_events_imported >= 30:
            cal_usage = CalendarUsage.HIGH
        elif m.calendar_events_imported >= 10:
            cal_usage = CalendarUsage.MEDIUM
        elif m.calendar_events_imported >= 1:
            cal_usage = CalendarUsage.LOW

        # Procrastination index (0..1): postpone rate weighted by dismiss rate.
        proc: Optional[float] = None
        if m.postpone_rate is not None or m.dismiss_rate is not None:
            proc = round(min(1.0, (m.postpone_rate or 0) * 0.7 + (m.dismiss_rate or 0) * 0.3), 3)

        # Average daily load: started / days_observed.
        days_obs = max(m.daily_openings, 1)
        avg_daily_load = round(started / days_obs, 2) if started else 0.0

        # Preferred hour buckets (top 3 by count).
        def top_hours(pairs):
            return [p.hour for p in sorted(pairs, key=lambda x: x.count, reverse=True)[:3]]

        pref_work = top_hours(m.completed_by_hour)
        pref_study = top_hours(m.completed_by_hour)  # same distribution absent domain tagging
        pref_break = []                              # unknown without a break-event source
        pref_app = []                                # opens aren't stored per-hour bucket yet
        # Confidence: minimum across sub-metrics.
        conf = aggregate(m.confidence, classify(started or completed or m.daily_openings))

        profile = BehaviorProfile(
            user_id=user_id,
            computed_at=datetime.now(timezone.utc),
            confidence=conf,
            planning_style=planning,
            completion_style=completion_style,
            activity_level=activity,
            calendar_usage=cal_usage,
            consistency=consistency,
            procrastination_index=proc,
            average_daily_load=avg_daily_load,
            preferred_work_hours=pref_work,
            preferred_study_hours=pref_study,
            preferred_break_hours=pref_break,
            preferred_app_usage_hours=pref_app,
            average_completion_time_minutes=m.avg_completion_minutes,
            average_postpone_time_minutes=m.avg_postpone_minutes,
            average_session_duration_minutes=m.avg_session_minutes,
            decision_completion_rate=m.completion_rate,
            decision_postpone_rate=m.postpone_rate,
            decision_dismiss_rate=m.dismiss_rate,
            sample_size=max(started, completed, m.daily_openings),
        )

        if persist:
            doc = profile.model_dump()
            doc["id"] = f"bprof_{uuid.uuid4().hex[:16]}"
            await self.storage.save_profile_snapshot(doc)
        return profile

    # ------------------------ public: confidence report ------------------------
    async def confidence_report(self, user_id: str) -> BehaviorConfidenceReport:
        m = await self._sync_and_load(user_id)
        events_observed = await self.storage.count_events(user_id)
        days_observed = m.daily_openings
        return BehaviorConfidenceReport(
            user_id=user_id,
            metrics=m.confidence,
            profile=classify(m.sample_size),
            patterns=classify(max(m.decisions_completed, m.decisions_postponed)),
            events_observed=events_observed,
            days_observed=days_observed,
            computed_at=datetime.now(timezone.utc),
        )
