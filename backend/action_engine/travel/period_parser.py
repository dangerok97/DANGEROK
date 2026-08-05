"""Italian travel period parser — 'dal 9 al 24 agosto', ranges, ISO."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from action_engine.study.date_parser import DEFAULT_TZ, _MONTHS_IT, _today_local, to_utc_iso

_DAL_AL = re.compile(
    r"(?:dal|da)\s+(\d{1,2})\s+(?:al|a)\s+(\d{1,2})\s+"
    r"(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre|"
    r"gen|feb|mar|apr|mag|giu|lug|ago|set|sett|ott|nov|dic)"
    r"(?:\s+(\d{4}))?",
    re.I,
)
_RANGE_SLASH = re.compile(
    r"(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?\s*[-–a]\s*"
    r"(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?",
    re.I,
)
_ISO_RANGE = re.compile(
    r"(\d{4}-\d{2}-\d{2})\s*(?:al|a|-|–)\s*(\d{4}-\d{2}-\d{2})",
    re.I,
)
_SINGLE_DAY_MONTH = re.compile(
    r"(?:il\s+)?(\d{1,2})\s+"
    r"(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre|"
    r"gen|feb|mar|apr|mag|giu|lug|ago|set|sett|ott|nov|dic)"
    r"(?:\s+(\d{4}))?",
    re.I,
)


def _tz(name: str = DEFAULT_TZ) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo(DEFAULT_TZ)


def _resolve_year(month: int, day: int, year: Optional[int], tz_name: str) -> int:
    today = _today_local(tz_name)
    if year:
        return year if year > 100 else 2000 + year
    # Prefer current year if date still upcoming or today; else next year
    try:
        cand = date(today.year, month, day)
    except ValueError:
        return today.year
    if cand < today:
        return today.year + 1
    return today.year


def format_period_label(start: date, end: date) -> str:
    if start.month == end.month and start.year == end.year:
        return f"{start.day}–{end.day}/{start.month}/{start.year}"
    return f"{start.day}/{start.month}/{start.year} – {end.day}/{end.month}/{end.year}"


def parse_travel_period(
    raw: Any,
    *,
    tz_name: str = DEFAULT_TZ,
) -> Dict[str, Any]:
    """Parse travel period from chips, ISO, or Italian free text.

    Returns {ok, start_date, end_date, start_iso, end_iso, label, source, error, message}
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return {"ok": False, "error": "missing_period", "message": "Indica le date del viaggio."}

    if isinstance(raw, dict):
        if raw.get("start_date") and raw.get("end_date"):
            return parse_travel_period(
                f"{raw['start_date']} - {raw['end_date']}", tz_name=tz_name,
            )
        if raw.get("text"):
            return parse_travel_period(raw["text"], tz_name=tz_name)
        if raw.get("iso"):
            return parse_travel_period(raw["iso"], tz_name=tz_name)

    text = str(raw).strip()
    text_l = text.lower().replace("’", "'")

    # Relative chips
    rel = {
        "this_weekend": 0,
        "next_week": 7,
        "in_2_weeks": 14,
        "in_1_month": 30,
    }
    if text_l in rel:
        today = _today_local(tz_name)
        start = today + timedelta(days=rel[text_l] or (5 - today.weekday()) % 7 or 7)
        if text_l == "this_weekend":
            # Next Saturday
            days_to_sat = (5 - today.weekday()) % 7
            if days_to_sat == 0 and today.weekday() != 5:
                days_to_sat = 7
            start = today + timedelta(days=days_to_sat if today.weekday() != 5 else 0)
            end = start + timedelta(days=1)
        else:
            end = start + timedelta(days=7)
        return {
            "ok": True,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "start_iso": to_utc_iso(start, hour=9, tz_name=tz_name),
            "end_iso": to_utc_iso(end, hour=18, tz_name=tz_name),
            "label": format_period_label(start, end),
            "source": "relative",
        }

    m = _ISO_RANGE.search(text)
    if m:
        try:
            start = date.fromisoformat(m.group(1))
            end = date.fromisoformat(m.group(2))
        except ValueError:
            return {"ok": False, "error": "invalid_period", "message": "Date non valide."}
        if end < start:
            start, end = end, start
        return {
            "ok": True,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "start_iso": to_utc_iso(start, hour=9, tz_name=tz_name),
            "end_iso": to_utc_iso(end, hour=18, tz_name=tz_name),
            "label": format_period_label(start, end),
            "source": "iso_range",
        }

    # Single ISO date → ask for end later; treat as 1-day stub
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        start = date.fromisoformat(text)
        end = start + timedelta(days=7)
        return {
            "ok": True,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "start_iso": to_utc_iso(start, hour=9, tz_name=tz_name),
            "end_iso": to_utc_iso(end, hour=18, tz_name=tz_name),
            "label": format_period_label(start, end),
            "source": "iso_single_default_week",
            "assumed_end": True,
        }

    m = _DAL_AL.search(text_l)
    if m:
        d1, d2 = int(m.group(1)), int(m.group(2))
        month = _MONTHS_IT[m.group(3).lower()]
        year = int(m.group(4)) if m.group(4) else None
        y = _resolve_year(month, d1, year, tz_name)
        try:
            start = date(y, month, d1)
            end = date(y, month, d2)
        except ValueError:
            return {"ok": False, "error": "invalid_period", "message": "Giorno/mese non validi."}
        if end < start:
            # Cross-month rare in this pattern — swap
            start, end = end, start
        today = _today_local(tz_name)
        if end < today:
            return {"ok": False, "error": "past_period", "message": "Il periodo del viaggio è nel passato."}
        return {
            "ok": True,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "start_iso": to_utc_iso(start, hour=9, tz_name=tz_name),
            "end_iso": to_utc_iso(end, hour=18, tz_name=tz_name),
            "label": format_period_label(start, end),
            "source": "dal_al",
        }

    m = _RANGE_SLASH.search(text)
    if m:
        d1, m1, y1 = int(m.group(1)), int(m.group(2)), m.group(3)
        d2, m2, y2 = int(m.group(4)), int(m.group(5)), m.group(6)
        y1i = int(y1) if y1 else None
        y2i = int(y2) if y2 else None
        if y1i and y1i < 100:
            y1i += 2000
        if y2i and y2i < 100:
            y2i += 2000
        y1i = y1i or _resolve_year(m1, d1, None, tz_name)
        y2i = y2i or y1i
        try:
            start = date(y1i, m1, d1)
            end = date(y2i, m2, d2)
        except ValueError:
            return {"ok": False, "error": "invalid_period", "message": "Date non valide."}
        if end < start:
            start, end = end, start
        return {
            "ok": True,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "start_iso": to_utc_iso(start, hour=9, tz_name=tz_name),
            "end_iso": to_utc_iso(end, hour=18, tz_name=tz_name),
            "label": format_period_label(start, end),
            "source": "slash_range",
        }

    # "Vacanza Vibo Marina" style — no period
    return {
        "ok": False,
        "error": "unparsed",
        "message": "Non ho capito le date. Prova «dal 9 al 24 agosto» o 2026-08-09 - 2026-08-24.",
    }


def extract_period_from_text(text: str, *, tz_name: str = DEFAULT_TZ) -> Dict[str, Any]:
    """Best-effort extract for Intent entities."""
    return parse_travel_period(text or "", tz_name=tz_name)
