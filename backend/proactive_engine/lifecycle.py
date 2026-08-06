"""Suggestion lifecycle — expire, unsnooze, cleanup."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from proactive_engine.dedupe import is_expired, is_snoozed
from proactive_engine.models import Suggestion, now_iso


async def apply_lifecycle(repo, user_id: str, *, now: datetime | None = None) -> Dict[str, int]:
    now = now or datetime.now(timezone.utc)
    active = await repo.list_for_user(
        user_id, statuses=["active", "snoozed", "candidate"], limit=200,
    )
    expired_n = 0
    unsnooze_n = 0
    for s in active:
        if is_expired(s, now) and s.status not in ("expired", "dismissed", "completed"):
            await repo.update_fields(
                user_id, s.id,
                {
                    "status": "expired",
                    "updated_at": now_iso(),
                },
            )
            expired_n += 1
            continue
        if s.status == "snoozed" and not is_snoozed(s, now):
            await repo.update_fields(
                user_id, s.id,
                {
                    "status": "active",
                    "snooze_until": None,
                    "updated_at": now_iso(),
                },
            )
            unsnooze_n += 1
    return {"expired": expired_n, "unsnoozed": unsnooze_n}


def default_ttl_hours(suggestion_type: str) -> int:
    return {
        "study": 48,
        "travel": 72,
        "calendar": 24,
        "documents": 72,
        "projects": 48,
        "life": 36,
        "generic": 24,
    }.get(suggestion_type, 36)
