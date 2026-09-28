"""Validate a calendar day and clock time in the owner's timezone."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def home_event_times(day: str, clock: str, tz_name: str) -> tuple[str, str]:
    if len(day) != 10 or len(clock) != 5:
        raise ValueError("invalid format")
    date = datetime.strptime(day, "%Y-%m-%d").date()
    hour, minute = map(int, clock.split(":"))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("invalid clock")
    zone = ZoneInfo(tz_name)
    start = datetime(date.year, date.month, date.day, hour, minute, tzinfo=zone)
    utc = start.astimezone(timezone.utc)
    if utc.astimezone(zone).replace(tzinfo=None) != start.replace(tzinfo=None):
        raise ValueError("nonexistent local time")
    end = (utc + timedelta(hours=1)).astimezone(zone)
    return start.isoformat(), end.isoformat()
