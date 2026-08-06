"""Italian date/time normalization — Europe/Rome default, real now.

Supports: oggi, domani, dopodomani, tra N giorni/settimane/mesi, weekend,
dal X al Y, 18 settembre, lunedì prossimo, stasera, alle 15, per tre giorni, etc.
Keeps original + normalized + tz + confidence + ambiguity.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta, time as dtime
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Europe/Rome"

_MONTHS = {
    "gennaio": 1, "gen": 1, "febbraio": 2, "feb": 2, "marzo": 3, "mar": 3,
    "aprile": 4, "apr": 4, "maggio": 5, "mag": 5, "giugno": 6, "giu": 6,
    "luglio": 7, "lug": 7, "agosto": 8, "ago": 8, "settembre": 9, "set": 9,
    "sett": 9, "ottobre": 10, "ott": 10, "novembre": 11, "nov": 11,
    "dicembre": 12, "dic": 12,
}
_WEEKDAYS = {
    "lunedì": 0, "lunedi": 0, "martedì": 1, "martedi": 1,
    "mercoledì": 2, "mercoledi": 2, "giovedì": 3, "giovedi": 3,
    "venerdì": 4, "venerdi": 4, "sabato": 5, "domenica": 6,
}
_NUM_WORDS = {
    "un": 1, "una": 1, "uno": 1, "due": 2, "tre": 3, "quattro": 4,
    "cinque": 5, "sei": 6, "sette": 7, "otto": 8, "nove": 9, "dieci": 10,
    "undici": 11, "dodici": 12, "quindici": 15, "venti": 20, "trenta": 30,
}


def _tz(name: str = DEFAULT_TZ) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo(DEFAULT_TZ)


def today_local(tz_name: str = DEFAULT_TZ, now: Optional[datetime] = None) -> date:
    if now is not None:
        if now.tzinfo is None:
            now = now.replace(tzinfo=_tz(tz_name))
        return now.astimezone(_tz(tz_name)).date()
    return datetime.now(_tz(tz_name)).date()


def to_iso_date(d: date) -> str:
    return d.isoformat()


def format_it(d: date) -> str:
    months = list(_MONTHS.keys())
    # pick long month name
    inv = {v: k for k, v in _MONTHS.items() if len(k) > 3}
    return f"{d.day} {inv.get(d.month, str(d.month))} {d.year}"


def _resolve_year(month: int, day: int, year: Optional[int], tz_name: str, now: Optional[datetime]) -> int:
    today = today_local(tz_name, now)
    if year:
        return year if year > 100 else 2000 + (year % 100)
    try:
        cand = date(today.year, month, day)
    except ValueError:
        return today.year
    if cand < today:
        return today.year + 1
    return today.year


def _num(token: str) -> Optional[int]:
    t = token.lower().strip()
    if t.isdigit():
        return int(t)
    return _NUM_WORDS.get(t)


def parse_time_it(text: str) -> Optional[Dict[str, Any]]:
    t = (text or "").lower()
    if "stasera" in t or "questa sera" in t:
        return {"raw": "stasera", "hour": 20, "minute": 0, "confidence": 0.9, "label": "stasera (~20:00)"}
    if "stamattina" in t or "questa mattina" in t:
        return {"raw": "stamattina", "hour": 9, "minute": 0, "confidence": 0.88, "label": "stamattina (~09:00)"}
    if "a mezzogiorno" in t or "mezzogiorno" in t:
        return {"raw": "mezzogiorno", "hour": 12, "minute": 0, "confidence": 0.92, "label": "12:00"}
    m = re.search(r"\balle?\s+(\d{1,2})(?:[:.](\d{2}))?\b", t)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2) or 0)
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return {
                "raw": m.group(0),
                "hour": h,
                "minute": mi,
                "confidence": 0.95,
                "label": f"{h:02d}:{mi:02d}",
                "normalized": f"{h:02d}:{mi:02d}",
            }
    m2 = re.search(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b", t)
    if m2:
        h, mi = int(m2.group(1)), int(m2.group(2))
        return {
            "raw": m2.group(0),
            "hour": h,
            "minute": mi,
            "confidence": 0.96,
            "label": f"{h:02d}:{mi:02d}",
            "normalized": f"{h:02d}:{mi:02d}",
        }
    return None


def parse_relative_single(
    text: str,
    *,
    tz_name: str = DEFAULT_TZ,
    now: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """Parse a single relative/absolute date. Does NOT invent a return date."""
    raw = (text or "").strip()
    t = raw.lower().replace("’", "'")
    today = today_local(tz_name, now)

    if re.search(r"\boggi\b", t):
        return {
            "raw": "oggi", "date": to_iso_date(today), "confidence": 0.98,
            "label": format_it(today), "kind": "relative", "timezone": tz_name,
        }
    if re.search(r"\bdomani\b", t):
        d = today + timedelta(days=1)
        return {
            "raw": "domani", "date": to_iso_date(d), "confidence": 0.98,
            "label": format_it(d), "kind": "relative", "timezone": tz_name,
        }
    if re.search(r"\bdopodomani\b", t):
        d = today + timedelta(days=2)
        return {
            "raw": "dopodomani", "date": to_iso_date(d), "confidence": 0.97,
            "label": format_it(d), "kind": "relative", "timezone": tz_name,
        }

    # tra N giorni/settimane/mesi — departure-only relative
    m = re.search(
        r"\b(?:fra|tra)\s+(\d+|un|una|uno|due|tre|quattro|cinque|sei|sette|otto|nove|dieci|"
        r"undici|dodici|quindici|venti|trenta)\s+"
        r"(giorn[oi]|settiman[ae]|mes[ei])\b",
        t,
    )
    if m:
        n = _num(m.group(1)) or 1
        unit = m.group(2)
        if unit.startswith("giorn"):
            delta = timedelta(days=n)
        elif unit.startswith("settiman"):
            delta = timedelta(weeks=n)
        else:
            # months ≈ 30 days
            delta = timedelta(days=30 * n)
        d = today + delta
        return {
            "raw": m.group(0),
            "date": to_iso_date(d),
            "confidence": 0.93,
            "label": format_it(d),
            "kind": "relative_offset",
            "offset_days": delta.days,
            "timezone": tz_name,
            "departure_only": True,
        }

    # weekend / questo weekend
    if re.search(r"\b(?:questo\s+)?weekend\b", t) or re.search(r"\bfine\s+settimana\b", t):
        days_to_sat = (5 - today.weekday()) % 7
        if days_to_sat == 0 and today.weekday() != 5:
            days_to_sat = 7
        start = today + timedelta(days=days_to_sat if today.weekday() != 5 else 0)
        end = start + timedelta(days=1)
        return {
            "raw": "weekend",
            "date": to_iso_date(start),
            "end_date": to_iso_date(end),
            "confidence": 0.88,
            "label": f"{format_it(start)} – {format_it(end)}",
            "kind": "weekend",
            "timezone": tz_name,
            "range": True,
        }

    # entro venerdì / entro lunedì
    m = re.search(
        r"\bentro\s+(luned[iì]|marted[iì]|mercoled[iì]|gioved[iì]|venerd[iì]|sabato|domenica)\b",
        t,
    )
    if m:
        wd_raw = m.group(1).replace("ì", "i")
        wd = None
        for k, v in _WEEKDAYS.items():
            if k.replace("ì", "i") == wd_raw or k == m.group(1):
                wd = v
                break
        if wd is not None:
            days_ahead = (wd - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            d = today + timedelta(days=days_ahead)
            return {
                "raw": m.group(0),
                "date": to_iso_date(d),
                "confidence": 0.92,
                "label": format_it(d),
                "kind": "entro_weekday",
                "timezone": tz_name,
            }

    # lunedì prossimo / prossimo lunedì
    m = re.search(
        r"\b(prossim[oa]\s+)?(luned[iì]|marted[iì]|mercoled[iì]|gioved[iì]|venerd[iì]|sabato|domenica)"
        r"(?:\s+prossim[oa])?\b",
        t,
    )
    if m:
        wd_raw = m.group(2).replace("ì", "i")
        # normalize accentless keys
        key = None
        for k, v in _WEEKDAYS.items():
            if k.replace("ì", "i") == wd_raw or k == m.group(2):
                key = v
                break
        if key is not None:
            days_ahead = (key - today.weekday()) % 7
            if days_ahead == 0 or "prossim" in (m.group(0) or ""):
                if days_ahead == 0:
                    days_ahead = 7
            d = today + timedelta(days=days_ahead)
            return {
                "raw": m.group(0),
                "date": to_iso_date(d),
                "confidence": 0.9,
                "label": format_it(d),
                "kind": "weekday",
                "timezone": tz_name,
            }

    # 18 settembre [2026]
    m = re.search(
        r"\b(?:il\s+)?(\d{1,2})\s+"
        r"(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre|"
        r"gen|feb|mar|apr|mag|giu|lug|ago|set|sett|ott|nov|dic)"
        r"(?:\s+(\d{4}))?\b",
        t,
    )
    if m:
        day = int(m.group(1))
        month = _MONTHS[m.group(2).lower()]
        year = _resolve_year(month, day, int(m.group(3)) if m.group(3) else None, tz_name, now)
        try:
            d = date(year, month, day)
        except ValueError:
            return None
        return {
            "raw": m.group(0),
            "date": to_iso_date(d),
            "confidence": 0.94,
            "label": format_it(d),
            "kind": "day_month",
            "timezone": tz_name,
        }

    # Ambiguous numeric: 03/04/2027 — flag ambiguity (DMY vs MDY)
    m = re.search(r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\b", t)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        candidates: List[Dict[str, Any]] = []
        # DMY (IT default)
        if 1 <= b <= 12 and 1 <= a <= 31:
            try:
                candidates.append({
                    "interpretation": "dmy",
                    "date": to_iso_date(date(y, b, a)),
                    "label": f"{a:02d}/{b:02d}/{y} (giorno/mese)",
                })
            except ValueError:
                pass
        # MDY
        if 1 <= a <= 12 and 1 <= b <= 31 and a != b:
            try:
                candidates.append({
                    "interpretation": "mdy",
                    "date": to_iso_date(date(y, a, b)),
                    "label": f"{a:02d}/{b:02d}/{y} (mese/giorno)",
                })
            except ValueError:
                pass
        if len(candidates) >= 2:
            return {
                "raw": m.group(0),
                "date": candidates[0]["date"],
                "confidence": 0.45,
                "status": "ambiguous",
                "ambiguity": {"candidates": candidates, "reason": "dmy_vs_mdy"},
                "label": m.group(0),
                "kind": "numeric_ambiguous",
                "timezone": tz_name,
            }
        if candidates:
            return {
                "raw": m.group(0),
                "date": candidates[0]["date"],
                "confidence": 0.9 if candidates[0]["interpretation"] == "dmy" else 0.7,
                "label": candidates[0]["label"],
                "kind": "numeric",
                "timezone": tz_name,
            }

    # ISO
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", t)
    if m:
        try:
            d = date.fromisoformat(m.group(1))
        except ValueError:
            return None
        return {
            "raw": m.group(1),
            "date": to_iso_date(d),
            "confidence": 0.99,
            "label": format_it(d),
            "kind": "iso",
            "timezone": tz_name,
        }

    return None


def parse_range_it(
    text: str,
    *,
    tz_name: str = DEFAULT_TZ,
    now: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """Parse 'dal X al Y' ranges. Returns start + end without inventing missing end."""
    raw = (text or "").strip()
    t = raw.lower().replace("’", "'")
    today = today_local(tz_name, now)

    # dal 9 al 24 agosto [YYYY]
    m = re.search(
        r"(?:dal|da)\s+(\d{1,2})\s+(?:al|a)\s+(\d{1,2})\s+"
        r"(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre|"
        r"gen|feb|mar|apr|mag|giu|lug|ago|set|sett|ott|nov|dic)"
        r"(?:\s+(\d{4}))?",
        t,
    )
    if m:
        d1, d2 = int(m.group(1)), int(m.group(2))
        month = _MONTHS[m.group(3).lower()]
        year = _resolve_year(month, d1, int(m.group(4)) if m.group(4) else None, tz_name, now)
        try:
            start = date(year, month, d1)
            end = date(year, month, d2)
        except ValueError:
            return None
        if end < start:
            # end may be next month
            if month == 12:
                end = date(year + 1, 1, d2)
            else:
                try:
                    end = date(year, month + 1, d2)
                except ValueError:
                    end = start
        return {
            "raw": m.group(0),
            "start_date": to_iso_date(start),
            "end_date": to_iso_date(end),
            "departure_date": to_iso_date(start),
            "return_date": to_iso_date(end),
            "confidence": 0.96,
            "label": f"{start.day}–{end.day} {m.group(3)} {year}",
            "kind": "dal_al",
            "timezone": tz_name,
            "range": True,
        }

    # per tre giorni (duration from a known start or today+offset elsewhere)
    m = re.search(
        r"\bper\s+(\d+|un|una|due|tre|quattro|cinque|sei|sette)\s+giorn[oi]\b",
        t,
    )
    duration_days = None
    if m:
        duration_days = _num(m.group(1)) or 3

    single = parse_relative_single(text, tz_name=tz_name, now=now)
    if single and single.get("end_date"):
        return {
            **single,
            "start_date": single["date"],
            "departure_date": single["date"],
            "return_date": single["end_date"],
        }
    if single and duration_days and single.get("date"):
        start = date.fromisoformat(single["date"])
        end = start + timedelta(days=duration_days - 1)
        return {
            "raw": f"{single.get('raw')} per {duration_days} giorni",
            "start_date": to_iso_date(start),
            "end_date": to_iso_date(end),
            "departure_date": to_iso_date(start),
            "return_date": to_iso_date(end),
            "confidence": min(0.9, float(single.get("confidence") or 0.85)),
            "label": f"{format_it(start)} – {format_it(end)}",
            "kind": "start_plus_duration",
            "timezone": tz_name,
            "range": True,
        }
    if single and single.get("departure_only"):
        return {
            "raw": single.get("raw"),
            "start_date": single["date"],
            "departure_date": single["date"],
            "end_date": None,
            "return_date": None,
            "confidence": single.get("confidence", 0.9),
            "label": single.get("label"),
            "kind": "departure_only",
            "timezone": tz_name,
            "range": False,
            "departure_only": True,
        }
    if single and single.get("date") and not duration_days:
        # Single absolute/relative without duration — departure only unless weekend range
        return {
            "raw": single.get("raw"),
            "start_date": single["date"],
            "departure_date": single["date"],
            "end_date": None,
            "return_date": None,
            "confidence": single.get("confidence", 0.9),
            "label": single.get("label"),
            "kind": single.get("kind"),
            "timezone": tz_name,
            "range": False,
            "departure_only": True,
            "ambiguity": single.get("ambiguity"),
            "status": single.get("status"),
        }
    if duration_days and not single:
        return {
            "raw": m.group(0) if m else f"per {duration_days} giorni",
            "duration_days": duration_days,
            "confidence": 0.85,
            "kind": "duration_only",
            "timezone": tz_name,
        }
    return None


def extract_dates_from_text(
    text: str,
    *,
    tz_name: str = DEFAULT_TZ,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """High-level helper for travel/study/medical date fields."""
    rng = parse_range_it(text, tz_name=tz_name, now=now)
    tm = parse_time_it(text)
    out: Dict[str, Any] = {"timezone": tz_name}
    if rng:
        out["range"] = rng
        if rng.get("departure_date") or rng.get("start_date"):
            out["departure_date"] = rng.get("departure_date") or rng.get("start_date")
        if rng.get("return_date") or rng.get("end_date"):
            out["return_date"] = rng.get("return_date") or rng.get("end_date")
        if rng.get("status") == "ambiguous" or rng.get("ambiguity"):
            out["ambiguous"] = True
            out["ambiguity"] = rng.get("ambiguity")
        out["departure_only"] = bool(rng.get("departure_only"))
    else:
        single = parse_relative_single(text, tz_name=tz_name, now=now)
        if single:
            out["single"] = single
            out["departure_date"] = single.get("date")
            if single.get("end_date"):
                out["return_date"] = single["end_date"]
            if single.get("status") == "ambiguous":
                out["ambiguous"] = True
                out["ambiguity"] = single.get("ambiguity")
            out["departure_only"] = bool(single.get("departure_only") or not single.get("end_date"))
    if tm:
        out["time"] = tm
    return out
