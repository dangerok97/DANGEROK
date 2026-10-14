"""Correct weekday/date arithmetic, never choose or change an appointment.

Only explicit full dates supported by successful calendar reads/writes are
eligible. Missing years, unrelated dates, quotes and code are left alone.
This is a presentation guard; it cannot grant authority or mutate state.
"""
from __future__ import annotations

from datetime import date, datetime
import re
from zoneinfo import ZoneInfo

_DAYS = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
_MONTHS = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre")
_CALENDAR_CAPS = {"get_calendar_events", "create_calendar_event", "update_calendar_event", "cancel_calendar_event", "continue_calendar_action"}
_PAIR = re.compile(
    r"\b(?P<weekday>luned[iì]|marted[iì]|mercoled[iì]|gioved[iì]|venerd[iì]|sabato|domenica)"
    r"\*{0,2}\s+\*{0,2}(?P<day>\d{1,2})\s+(?P<month>" + "|".join(_MONTHS) + r")\s+(?P<year>\d{4})\b",
    re.IGNORECASE,
)
_PROTECTED = re.compile(r'```[\s\S]*?```|`[^`]*`|«[^»]*»|“[^”]*”|"[^"\n]*"')


def _event_date(item):
    if not isinstance(item, dict):
        return None
    raw = item.get("start_datetime") or item.get("starts_at")
    if not isinstance(raw, str):
        return None
    try:
        if len(raw) == 10:
            return date.fromisoformat(raw)
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        zone = item.get("timezone")
        if isinstance(zone, dict):
            zone = zone.get("tz_name")
        if zone and moment.tzinfo is not None:
            moment = moment.astimezone(ZoneInfo(str(zone)))
        return moment.date()
    except (ValueError, TypeError, KeyError):
        return None


def guard_calendar_weekdays(text, observations, calendar_ahead=None):
    """Return (text, correction_count), retaining all event dates and times."""
    if not isinstance(text, str) or not text:
        return text, 0
    dates = set()
    for obs in observations or []:
        if not isinstance(obs, dict) or obs.get("name") not in _CALENDAR_CAPS or obs.get("status") != "ok":
            continue
        payload = obs.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        if payload.get("status") not in (None, "ok", "success"):
            continue
        rows = [payload]
        for key in ("events", "items"):
            items = payload.get(key)
            if isinstance(items, list):
                rows.extend(items[:40])
        dates.update(found for item in rows if (found := _event_date(item)))
    if isinstance(calendar_ahead, dict):
        items = calendar_ahead.get("events")
        if isinstance(items, list):
            dates.update(found for item in items[:40] if (found := _event_date(item)))
    if not dates:
        return text, 0
    protected = [match.span() for match in _PROTECTED.finditer(text)]
    edits = []
    for match in _PAIR.finditer(text):
        if any(start <= match.start() < end for start, end in protected):
            continue
        try:
            stated = date(int(match["year"]), _MONTHS.index(match["month"].lower()) + 1, int(match["day"]))
        except ValueError:
            continue
        if stated not in dates:
            continue
        correct = _DAYS[stated.weekday()]
        named = match["weekday"].lower().replace("ì", "i")
        if named == correct.replace("ì", "i"):
            continue
        if match["weekday"][0].isupper():
            correct = correct.capitalize()
        edits.append((*match.span("weekday"), correct))
    for start, end, replacement in reversed(edits):
        text = text[:start] + replacement + text[end:]
    return text, len(edits)
