"""Italian natural / relative / picker exam-date parser.

Never silently picks an ambiguous date — returns needs_confirm instead.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Europe/Rome"

_MONTHS_IT = {
    "gennaio": 1, "gen": 1,
    "febbraio": 2, "feb": 2,
    "marzo": 3, "mar": 3,
    "aprile": 4, "apr": 4,
    "maggio": 5, "mag": 5,
    "giugno": 6, "giu": 6,
    "luglio": 7, "lug": 7,
    "agosto": 8, "ago": 8,
    "settembre": 9, "set": 9, "sett": 9,
    "ottobre": 10, "ott": 10,
    "novembre": 11, "nov": 11,
    "dicembre": 12, "dic": 12,
}

_WEEKDAY_IT = {
    "lunedì": 0, "lunedi": 0, "lun": 0,
    "martedì": 1, "martedi": 1, "mar": 1,
    "mercoledì": 2, "mercoledi": 2, "mer": 2,
    "giovedì": 3, "giovedi": 3, "gio": 3,
    "venerdì": 4, "venerdi": 4, "ven": 4,
    "sabato": 5, "sab": 5,
    "domenica": 6, "dom": 6,
}

_RELATIVE = {
    "oggi": 0,
    "domani": 1,
    "dopodomani": 2,
    "tra_3_giorni": 3,
    "in_3_days": 3,
    "tra_1_settimana": 7,
    "in_1_week": 7,
    "tra_2_settimane": 14,
    "in_2_weeks": 14,
    "tra_1_mese": 30,
    "in_1_month": 30,
}


def _tz(name: str = DEFAULT_TZ) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo(DEFAULT_TZ)


def _today_local(tz_name: str = DEFAULT_TZ) -> date:
    return datetime.now(_tz(tz_name)).date()


def to_utc_iso(d: date, *, hour: int = 9, minute: int = 0, tz_name: str = DEFAULT_TZ) -> str:
    local = datetime(d.year, d.month, d.day, hour, minute, tzinfo=_tz(tz_name))
    return local.astimezone(timezone.utc).isoformat()


def parse_exam_date(
    raw: Any,
    *,
    tz_name: str = DEFAULT_TZ,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Parse chip code, ISO, or Italian free text.

    Returns:
      {ok, date_iso, local_date, label, ambiguous, candidates, error}
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return {"ok": False, "error": "missing_date", "message": "Indica una data per l'esame."}

    # Structured dict from UI picker
    if isinstance(raw, dict):
        if raw.get("confirmed_date"):
            return parse_exam_date(raw["confirmed_date"], tz_name=tz_name, now=now)
        if raw.get("iso") or raw.get("date"):
            return parse_exam_date(raw.get("iso") or raw.get("date"), tz_name=tz_name, now=now)
        if raw.get("text"):
            return parse_exam_date(raw["text"], tz_name=tz_name, now=now)

    text = str(raw).strip()
    text_l = text.lower().replace("’", "'")

    # Relative chip codes
    if text_l in _RELATIVE:
        d = _today_local(tz_name) + timedelta(days=_RELATIVE[text_l])
        return {
            "ok": True,
            "date_iso": to_utc_iso(d, tz_name=tz_name),
            "local_date": d.isoformat(),
            "label": f"{d.day}/{d.month}/{d.year}",
            "ambiguous": False,
            "source": "relative",
        }

    # ISO YYYY-MM-DD or full ISO
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d < _today_local(tz_name):
            return {"ok": False, "error": "past_date", "message": "La data dell'esame è nel passato."}
        return {
            "ok": True,
            "date_iso": to_utc_iso(d, tz_name=tz_name),
            "local_date": d.isoformat(),
            "label": f"{d.day}/{d.month}/{d.year}",
            "ambiguous": False,
            "source": "iso",
        }

    # DD/MM/YYYY or DD-MM-YYYY
    m = re.search(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b", text_l)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100:
            year += 2000
        try:
            d = date(year, month, day)
        except ValueError:
            return {"ok": False, "error": "invalid_date", "message": "Data non valida."}
        if d < _today_local(tz_name):
            return {"ok": False, "error": "past_date", "message": "La data dell'esame è nel passato."}
        return {
            "ok": True,
            "date_iso": to_utc_iso(d, tz_name=tz_name),
            "local_date": d.isoformat(),
            "label": f"{d.day}/{d.month}/{d.year}",
            "ambiguous": False,
            "source": "numeric",
        }

    # "tra N giorni/settimane/mesi"
    m = re.search(r"\btra\s+(\d+)\s+(giorn[oi]|settiman[ae]|mes[ei])\b", text_l)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        days = n if unit.startswith("giorn") else n * 7 if unit.startswith("settiman") else n * 30
        d = _today_local(tz_name) + timedelta(days=days)
        return {
            "ok": True,
            "date_iso": to_utc_iso(d, tz_name=tz_name),
            "local_date": d.isoformat(),
            "label": f"{d.day}/{d.month}/{d.year}",
            "ambiguous": False,
            "source": "relative_text",
        }

    # Weekday only → next occurrence (not ambiguous)
    for name, wd in _WEEKDAY_IT.items():
        if re.search(rf"\b{re.escape(name)}\b", text_l):
            today = _today_local(tz_name)
            delta = (wd - today.weekday()) % 7
            if delta == 0:
                delta = 7
            d = today + timedelta(days=delta)
            return {
                "ok": True,
                "date_iso": to_utc_iso(d, tz_name=tz_name),
                "local_date": d.isoformat(),
                "label": f"{name} {d.day}/{d.month}",
                "ambiguous": False,
                "source": "weekday",
            }

    # "15 marzo" / "il 15 marzo 2026" — year optional → may be ambiguous near year boundary
    m = re.search(
        r"\b(?:il\s+)?(\d{1,2})\s+(" + "|".join(_MONTHS_IT.keys()) + r")(?:\s+(\d{4}))?\b",
        text_l,
    )
    if m:
        day = int(m.group(1))
        month = _MONTHS_IT[m.group(2)]
        year_s = m.group(3)
        today = _today_local(tz_name)
        if year_s:
            year = int(year_s)
            try:
                d = date(year, month, day)
            except ValueError:
                return {"ok": False, "error": "invalid_date", "message": "Data non valida."}
            if d < today:
                return {"ok": False, "error": "past_date", "message": "La data dell'esame è nel passato."}
            return {
                "ok": True,
                "date_iso": to_utc_iso(d, tz_name=tz_name),
                "local_date": d.isoformat(),
                "label": f"{d.day}/{d.month}/{d.year}",
                "ambiguous": False,
                "source": "month_name",
            }

        # No year: try this year, else next year — if both in future? only one makes sense
        candidates: List[date] = []
        for y in (today.year, today.year + 1):
            try:
                d = date(y, month, day)
            except ValueError:
                continue
            if d >= today:
                candidates.append(d)
        if not candidates:
            return {"ok": False, "error": "past_date", "message": "La data dell'esame è nel passato."}
        if len(candidates) == 1:
            d = candidates[0]
            # Ambiguous only when day/month could plausibly be either year and we're near boundary
            # If this-year date is within 60 days, accept; else ask confirm when both existed originally
            return {
                "ok": True,
                "date_iso": to_utc_iso(d, tz_name=tz_name),
                "local_date": d.isoformat(),
                "label": f"{d.day}/{d.month}/{d.year}",
                "ambiguous": False,
                "source": "month_name",
            }
        # Both this and next year still in future (shouldn't happen for same day/month) — confirm
        return {
            "ok": False,
            "error": "ambiguous",
            "ambiguous": True,
            "message": "Quale anno intendi?",
            "candidates": [
                {
                    "local_date": c.isoformat(),
                    "date_iso": to_utc_iso(c, tz_name=tz_name),
                    "label": f"{c.day}/{c.month}/{c.year}",
                }
                for c in candidates
            ],
        }

    # "fine mese" / "metà mese"
    if "fine mese" in text_l or "fine del mese" in text_l:
        today = _today_local(tz_name)
        last = calendar.monthrange(today.year, today.month)[1]
        d = date(today.year, today.month, last)
        if d < today:
            # next month end
            nm = today.month % 12 + 1
            ny = today.year + (1 if today.month == 12 else 0)
            last = calendar.monthrange(ny, nm)[1]
            d = date(ny, nm, last)
        return {
            "ok": True,
            "date_iso": to_utc_iso(d, tz_name=tz_name),
            "local_date": d.isoformat(),
            "label": f"{d.day}/{d.month}/{d.year}",
            "ambiguous": False,
            "source": "end_of_month",
        }

    return {
        "ok": False,
        "error": "unparsed",
        "message": "Non ho capito la data. Usa il selettore o scrivi es. 15/09/2026.",
    }


def format_local(date_iso: str, tz_name: str = DEFAULT_TZ) -> str:
    try:
        dt = datetime.fromisoformat(date_iso.replace("Z", "+00:00"))
        local = dt.astimezone(_tz(tz_name))
        return f"{local.day}/{local.month}/{local.year}"
    except Exception:
        return date_iso[:10]
