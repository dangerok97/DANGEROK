"""Code-owned time/place identity for read-only Situation history.

A language model must not turn an older similar Situation into evidence for
a new, explicitly dated request. Only the user's *current* words authorize
exact-date and place filters. No DB writes or domain heuristics.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from zoneinfo import ZoneInfo

MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}


def explicit_dates(message: str) -> tuple[str | None, str | None]:
    """Recognize only complete, user-authored calendar dates with a year.

    If several distinct dates appear, never guess the event date. The model
    must clarify or request a date-specific read. A single date is data, not
    evidence that an event with matching subject actually exists.
    """
    text = str(message or "")[:8000].casefold()
    found: set[str] = set()

    def add(year: str, month: str | int, day: str):
        try:
            month_number = MONTHS[month] if isinstance(month, str) else month
            found.add(date(int(year), int(month_number), int(day)).isoformat())
        except (TypeError, ValueError, KeyError):
            pass

    for y, m, d in re.findall(
        r"(?<!\d)(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)", text
    ):
        add(y, int(m), d)
    for d, m, y in re.findall(
        r"(?<!\d)(\d{1,2})[/.](\d{1,2})[/.](20\d{2})(?!\d)", text
    ):
        add(y, int(m), d)
    names = "|".join(MONTHS)
    for d, month, y in re.findall(
        rf"(?<!\w)(\d{{1,2}})\s+({names})\s+(20\d{{2}})(?!\d)", text
    ):
        add(y, month, d)
    if len(found) > 1:
        return None, "multiple_explicit_dates"
    return (next(iter(found)), None) if found else (None, None)


def normalized_place(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(value.casefold().split()).strip()


def place_spoken_by_user(message: str, place: str) -> bool:
    clean = normalized_place(place)
    if len(clean) < 3:
        return False
    haystack = normalized_place(message[:8000] if isinstance(message, str) else "")
    return bool(re.search(r"(?<!\w)" + re.escape(clean) + r"(?!\w)", haystack))


def authoritative_place(message: str, proposed: str, known_places) -> tuple[str | None, str | None]:
    """Use the model's place ONLY if the user spoke it; else find one exact
    matching label from owner-owned records. Never infer device GPS/location.
    """
    proposed = normalized_place(proposed)
    if proposed:
        if not place_spoken_by_user(message, proposed):
            return None, "place_not_user_grounded"
        return proposed, None
    present = {
        normalized_place(location)
        for location in known_places
        if location and place_spoken_by_user(message, location)
    }
    if len(present) > 1:
        return None, "multiple_explicit_places"
    return (next(iter(present)), None) if present else (None, None)


def record_event_day(row: dict, zone: str) -> tuple[str | None, str]:
    """The explicitly stored physical start outranks insertion time.

    An updated_at is never the event date, and a note created on October 11
    cannot be silently reassigned to October 19.
    """
    raw_start = str(row.get("started_at") or "")
    authority = "started_at" if raw_start else "created_at"
    raw = raw_start or str(row.get("created_at") or "")
    if not raw:
        return None, "missing_date"
    try:
        instant = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if instant.tzinfo is None:
            return None, "unverified_naive_date"
        return instant.astimezone(ZoneInfo(zone)).date().isoformat(), authority
    except (ValueError, TypeError, KeyError):
        return None, "invalid_record_date"


def location_matches(record_label: str, requested: str) -> bool:
    """Exact locality match or a more-qualified, comma-separated label."""
    a, b = normalized_place(record_label), normalized_place(requested)
    return bool(a and b and (a == b or a.startswith(b + ",")))
