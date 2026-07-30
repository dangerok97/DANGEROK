"""DailySummaryService — bridges the persistence layer with `analyzer`.

Reads events from ORA's canonical Life Graph (`life_nodes` with
`type=='event'`). Optionally also considers Decisions with a
`starts_at` on the target day, so user-authored engagements count too.

Never writes to any collection except its own cache (`daily_summaries`).
Never creates Decisions.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .analyzer import analyze_day
from .types import DailySummary


class DailySummaryService:
    def __init__(self, db):
        self.db = db

    @property
    def cache_col(self):
        return self.db.daily_summaries

    # ------------------------------------------------------------------
    async def _load_events_for_day(
        self,
        user_id: str,
        target_date: date,
    ) -> List[Dict[str, Any]]:
        """Fetch all candidate events for a specific date from the Life Graph.

        Filters:
          - user-scoped;
          - node type == 'event';
          - status == 'active' (archived → cancelled/removed = excluded);
          - `attributes.starts_at` overlaps [day_start, day_end).
        """
        day_start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        day_start_iso = day_start.isoformat()
        day_end_iso = day_end.isoformat()

        # Overlap: (starts_at < day_end) AND (ends_at > day_start OR starts_at >= day_start)
        # We cannot express OR cleanly on Mongo without $or on ends_at existence; keep it simple.
        query = {
            "user_id": user_id,
            "type": "event",
            "status": "active",
            "attributes.starts_at": {"$lt": day_end_iso},
            "$or": [
                {"attributes.ends_at": {"$gt": day_start_iso}},
                {"attributes.ends_at": {"$exists": False}},
                {"attributes.ends_at": None},
                # all-day events with starts_at on the day still overlap
                {"attributes.starts_at": {"$gte": day_start_iso}},
            ],
        }
        cursor = self.db.life_nodes.find(
            query, {"_id": 0, "id": 1, "label": 1, "attributes": 1}
        ).sort("attributes.starts_at", 1)
        docs = await cursor.to_list(length=500)

        events: List[Dict[str, Any]] = []
        for d in docs:
            attrs = d.get("attributes") or {}
            events.append({
                "id": d.get("id"),
                "title": d.get("label"),
                "starts_at": attrs.get("starts_at"),
                "ends_at": attrs.get("ends_at"),
                "all_day": bool(attrs.get("all_day")),
                "location": attrs.get("location"),
                "status": attrs.get("status") or "confirmed",
                "source": attrs.get("connector_id") or "user",
            })
        return events

    async def _calendar_sync_hint(self, user_id: str) -> bool:
        """True if the user has at least one connected calendar instance."""
        n = await self.db.connector_instances.count_documents({
            "user_id": user_id,
            "connector_id": "calendar_google",
            "status": {"$in": ["connected", "syncing"]},
        })
        return n > 0

    # ------------------------------------------------------------------
    async def compute(self, user_id: str, target_date: date, *, tz_name: str = "UTC") -> DailySummary:
        events = await self._load_events_for_day(user_id, target_date)
        sync_hint = await self._calendar_sync_hint(user_id)
        return analyze_day(
            target_date=target_date,
            events=events,
            tz_name=tz_name,
            calendar_sync_hint=sync_hint,
        )

    async def today(self, user_id: str, *, tz_name: str = "UTC") -> DailySummary:
        return await self.compute(user_id, datetime.now(timezone.utc).date(), tz_name=tz_name)

    async def tomorrow(self, user_id: str, *, tz_name: str = "UTC") -> DailySummary:
        return await self.compute(
            user_id, datetime.now(timezone.utc).date() + timedelta(days=1), tz_name=tz_name,
        )

    async def refresh(self, user_id: str, *, tz_name: str = "UTC") -> Dict[str, Any]:
        """Bust any cache and return `today`. The current iteration is
        stateless (recomputes on every call) — this endpoint therefore is
        idempotent and safe to hit as often as needed."""
        today = await self.today(user_id, tz_name=tz_name)
        tomorrow = await self.tomorrow(user_id, tz_name=tz_name)
        return {"today": today.to_dict(), "tomorrow": tomorrow.to_dict()}
