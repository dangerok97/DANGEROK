"""Old updates leave Home by themselves.

Home showed a 12 October question and an "11 giorni fa" deadline on 23 October:
entries without an explicit validity never expired. The rule, applied once to
every update list Home returns:

- an explicit validity (valid_until / expires_at) that has passed removes it;
  a date-only value means "through that day";
- an explicit validity still in the future keeps it, whatever its age;
- with no validity, an entry with no activity for STALE_AFTER_HOURS is removed.
  Activity is the latest of updated_at / created_at / raised_at, so work that
  ORA is still moving forward stays visible.

Nothing is deleted from the database: this is presentation freshness only.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

STALE_AFTER_HOURS = 72
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _moment(value: Any, *, end_of_day: bool = False) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    try:
        if _DATE_ONLY.match(text):
            day = datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
            return day + timedelta(days=1) - timedelta(microseconds=1) if end_of_day else day
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def is_current(item: Dict[str, Any], now: datetime, *, stale_after_hours: int = STALE_AFTER_HOURS) -> bool:
    if not isinstance(item, dict):
        return False
    deadline = item.get("valid_until") or item.get("expires_at")
    if deadline:
        moment = _moment(deadline, end_of_day=True)
        if moment is not None:
            return moment >= now
    activity = [m for m in (_moment(item.get(key)) for key in ("updated_at", "created_at", "raised_at")) if m]
    if not activity:
        return True  # nothing to judge age by: never hide on a guess
    return now - max(activity) <= timedelta(hours=stale_after_hours)


def current_only(items: Iterable[Dict[str, Any]], now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    moment = now or datetime.now(timezone.utc)
    return [item for item in (items or []) if is_current(item, moment)]
