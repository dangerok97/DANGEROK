"""Incremental metrics builder.

Reads events from the append-only timeline and aggregates them into a
``BehaviorMetrics`` snapshot. All calculations are deterministic and O(N)
on the events retrieved (bounded by the window). Older snapshots stay in
the collection for auditability.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .confidence import classify
from .storage import BehavioralStorage
from .types import (
    BehaviorMetrics,
    BehavioralEventType,
    Confidence,
    HourBucket,
    WeekdayBucket,
)


DECISION_EVENTS = {
    BehavioralEventType.DECISION_STARTED.value,
    BehavioralEventType.DECISION_COMPLETED.value,
    BehavioralEventType.DECISION_POSTPONED.value,
    BehavioralEventType.DECISION_PARTIAL.value,
    BehavioralEventType.DECISION_BLOCKED.value,
    BehavioralEventType.DECISION_DISMISSED.value,
}


def _hour_of(dt: datetime) -> int:
    return int(dt.astimezone(timezone.utc).hour)


def _weekday_of(dt: datetime) -> int:
    # Monday=0
    return int(dt.astimezone(timezone.utc).weekday())


class MetricsBuilder:
    def __init__(self, storage: BehavioralStorage):
        self._store = storage

    async def compute(self, user_id: str, *, window_days: int = 60) -> BehaviorMetrics:
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=window_days)
        # Pull decision & app-open & sync events for the window (bounded).
        events = await self._store.list_events(user_id, since=since, limit=1000)
        # We may have >1000 events; fetch in pages until exhausted.
        # Bounded loop for safety (max 100k events → 100 pages).
        skip = len(events)
        while len(events) < 100_000:
            page = await self._store.list_events(user_id, since=since, skip=skip, limit=1000)
            if not page:
                break
            events.extend(page)
            skip += len(page)
            if len(page) < 1000:
                break

        by_id: Dict[str, List[Dict[str, Any]]] = {}
        opens: List[datetime] = []
        completions_by_hour: Dict[int, int] = {}
        completions_by_weekday: Dict[int, int] = {}
        postpones_by_hour: Dict[int, int] = {}
        postpones_by_weekday: Dict[int, int] = {}
        calendar_syncs = 0
        calendar_events_imported = 0

        n_started = n_completed = n_postponed = n_partial = n_blocked = n_dismissed = 0
        last_open_at: Optional[datetime] = None

        for e in events:
            etype = e.get("event_type")
            occurred = e.get("occurred_at")
            if isinstance(occurred, str):
                try:
                    occurred = datetime.fromisoformat(occurred.replace("Z", "+00:00"))
                except Exception:
                    continue
            if not isinstance(occurred, datetime):
                continue
            occurred = occurred if occurred.tzinfo else occurred.replace(tzinfo=timezone.utc)

            if etype in DECISION_EVENTS:
                did = (e.get("metadata") or {}).get("decision_id")
                if did:
                    by_id.setdefault(did, []).append({"type": etype, "occurred_at": occurred})

            if etype == BehavioralEventType.DECISION_STARTED.value:
                n_started += 1
            elif etype == BehavioralEventType.DECISION_COMPLETED.value:
                n_completed += 1
                h = _hour_of(occurred); w = _weekday_of(occurred)
                completions_by_hour[h] = completions_by_hour.get(h, 0) + 1
                completions_by_weekday[w] = completions_by_weekday.get(w, 0) + 1
            elif etype == BehavioralEventType.DECISION_POSTPONED.value:
                n_postponed += 1
                h = _hour_of(occurred); w = _weekday_of(occurred)
                postpones_by_hour[h] = postpones_by_hour.get(h, 0) + 1
                postpones_by_weekday[w] = postpones_by_weekday.get(w, 0) + 1
            elif etype == BehavioralEventType.DECISION_PARTIAL.value:
                n_partial += 1
            elif etype == BehavioralEventType.DECISION_BLOCKED.value:
                n_blocked += 1
            elif etype == BehavioralEventType.DECISION_DISMISSED.value:
                n_dismissed += 1
            elif etype == BehavioralEventType.FIRST_APP_OPEN_TODAY.value:
                opens.append(occurred)
                last_open_at = max(last_open_at, occurred) if last_open_at else occurred
            elif etype == BehavioralEventType.CALENDAR_SYNC.value:
                calendar_syncs += 1
            elif etype == BehavioralEventType.CALENDAR_EVENT_IMPORTED.value:
                calendar_events_imported += 1

        # --- avg completion time (start → complete, per decision)
        completion_minutes: List[float] = []
        postpone_minutes: List[float] = []
        for did, records in by_id.items():
            records.sort(key=lambda r: r["occurred_at"])
            started_at: Optional[datetime] = None
            for rec in records:
                t = rec["type"]
                if t == BehavioralEventType.DECISION_STARTED.value:
                    started_at = rec["occurred_at"]
                elif t == BehavioralEventType.DECISION_COMPLETED.value and started_at:
                    delta = (rec["occurred_at"] - started_at).total_seconds() / 60.0
                    if 0 <= delta <= 60 * 24 * 7:  # sanity: within a week
                        completion_minutes.append(delta)
                    started_at = None
                elif t == BehavioralEventType.DECISION_POSTPONED.value and started_at:
                    delta = (rec["occurred_at"] - started_at).total_seconds() / 60.0
                    if 0 <= delta <= 60 * 24 * 7:
                        postpone_minutes.append(delta)
                    started_at = None

        def _avg(xs: List[float]) -> Optional[float]:
            return round(sum(xs) / len(xs), 2) if xs else None

        # --- avg first-open local hour (UTC-based here; local TZ mapping is
        # a future enhancement — recorded in metadata but not applied).
        avg_first_hour = None
        if opens:
            avg_first_hour = round(sum(_hour_of(t) for t in opens) / len(opens), 2)

        decisions_touched = n_completed + n_postponed + n_dismissed + n_blocked + n_partial
        sample = max(n_started, decisions_touched, len(opens))
        conf = classify(sample)

        # Rates
        denom_completion = max(n_completed + n_postponed + n_dismissed, 0)
        completion_rate = round(n_completed / denom_completion, 3) if denom_completion else None
        postpone_rate = round(n_postponed / denom_completion, 3) if denom_completion else None
        dismiss_rate = round(n_dismissed / denom_completion, 3) if denom_completion else None

        return BehaviorMetrics(
            user_id=user_id,
            computed_at=now,
            window_days=window_days,
            confidence=conf,
            daily_openings=len(opens),
            total_sessions=len(opens),
            avg_session_minutes=None,  # sessions require app-close pairing; kept None until reliably observable
            last_open_at=last_open_at,
            avg_first_open_local_hour=avg_first_hour,
            decisions_started=n_started,
            decisions_completed=n_completed,
            decisions_postponed=n_postponed,
            decisions_partial=n_partial,
            decisions_blocked=n_blocked,
            decisions_dismissed=n_dismissed,
            avg_completion_minutes=_avg(completion_minutes),
            avg_postpone_minutes=_avg(postpone_minutes),
            calendar_syncs=calendar_syncs,
            calendar_events_imported=calendar_events_imported,
            completed_by_hour=[HourBucket(hour=h, count=c) for h, c in sorted(completions_by_hour.items())],
            postponed_by_hour=[HourBucket(hour=h, count=c) for h, c in sorted(postpones_by_hour.items())],
            completed_by_weekday=[WeekdayBucket(weekday=w, count=c) for w, c in sorted(completions_by_weekday.items())],
            postponed_by_weekday=[WeekdayBucket(weekday=w, count=c) for w, c in sorted(postpones_by_weekday.items())],
            completion_rate=completion_rate,
            postpone_rate=postpone_rate,
            dismiss_rate=dismiss_rate,
            sample_size=sample,
        )
