"""
The evening before: tomorrow, said tonight.

The leave notice looks twelve hours ahead, so a 9:00 appointment was first
mentioned at 8:20 the same morning — too late to set an alarm, find the
documents or see that it will rain. At the person's evening hour (20:30
unless changed) one notification says what tomorrow holds:

    Domani: 9:00 Medico (Viterbo), parti verso le 8:15 da casa. Scade F24.
    Pioggia 70%: serve l'ombrello.

Only when tomorrow has something (an appointment or a deadline): an empty
tomorrow means no notification. Built by code from stored facts, the routing
provider and the forecast, through the one-time reminder lane, once a day.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ora.evening")

DEFAULT_HOUR, DEFAULT_MINUTE = 20, 30
LATE_HOURS = 3
MAX_CHARS = 280
ORIGIN = "evening_brief"


async def preference(db, owner: str) -> Dict[str, Any]:
    row = await db.users.find_one({"user_id": owner}, {"_id": 0, "preferences.evening_brief": 1})
    pref = ((row or {}).get("preferences") or {}).get("evening_brief") or {}
    try:
        hour = max(18, min(22, int(pref.get("hour", DEFAULT_HOUR))))
    except (TypeError, ValueError):
        hour = DEFAULT_HOUR
    return {"enabled": pref.get("enabled", True) is not False, "hour": hour}


async def set_preference(db, owner: str, *, enabled: Optional[bool] = None, hour: Optional[int] = None) -> Dict[str, Any]:
    current = await preference(db, owner)
    if enabled is not None:
        current["enabled"] = bool(enabled)
    if hour is not None:
        current["hour"] = max(18, min(22, int(hour)))
    await db.users.update_one({"user_id": owner}, {"$set": {"preferences.evening_brief": current}})
    return current


async def _leave_estimate(db, owner: str, event: Dict[str, Any], local_now: datetime) -> str:
    """«parti verso le 8:15 da casa», from home (tomorrow you start from home)."""
    try:
        from brief.morning import clock
        from places import routing
        from places.leave_notice import MARGIN_MINUTES, destination_for, origin_for
        from places.travel_mode import LABELS, get as preferred, order

        start = datetime.fromisoformat(str(event.get("starts_at")).replace("Z", "+00:00"))
        origin = await origin_for(db, owner, datetime.now(timezone.utc))
        if origin is None or not routing.capabilities().get("available"):
            return ""
        dest = await destination_for(db, owner, str(event.get("location") or ""), origin)
        if dest is None:
            return ""
        for mode in order(await preferred(db, owner)):
            if mode not in routing.capabilities().get("modes", []):
                continue
            r = await routing.get_route(origin={k: origin[k] for k in ("latitude", "longitude")},
                                        destination={k: dest[k] for k in ("latitude", "longitude")}, travel_mode=mode)
            d = r.get("duration_seconds") if isinstance(r, dict) and r.get("available") else None
            if isinstance(d, (int, float)) and math.isfinite(d) and d > 0:
                minutes = math.ceil(d / 60)
                leave = (start - timedelta(minutes=minutes + MARGIN_MINUTES)).astimezone(local_now.tzinfo)
                where = " da casa" if origin["kind"] == "home" else ""
                return f"parti verso le {clock(leave)}{where} ({minutes} min {LABELS[mode]})"
        return ""
    except Exception as exc:
        logger.info("evening leave estimate skipped: %s", type(exc).__name__)
        return ""


async def _tomorrow(db, owner: str, local_now: datetime) -> Dict[str, Any]:
    from brief.morning import _hhmm
    from opportunities.deadlines import as_facts, upcoming
    from opportunities.snapshot import _calendar

    events = [e for e in await _calendar(db, owner, local_now) if e.get("in_days") == 1][:4]
    lines: List[str] = []
    first_with_place = next((e for e in events if not e.get("all_day") and e.get("location")), None)
    for e in events:
        title = " ".join(str(e.get("title") or "Appuntamento").split())[:50]
        at = "" if e.get("all_day") else _hhmm(e.get("starts_at"), local_now.tzinfo)
        line = f"{at} {title}" if at else title
        place = " ".join(str(e.get("location") or "").split())[:40]
        if place:
            line += f" ({place})"
        if e is first_with_place:
            leave = await _leave_estimate(db, owner, e, local_now)
            if leave:
                line += f", {leave}"
        lines.append(line)
    facts = as_facts(await upcoming(db, owner, local_now, days=2), local_now)
    deadlines = [" ".join(str(f.get("title") or "").split())[:50] for f in facts if f.get("days_left") == 1][:3]
    return {"events": lines, "deadlines": deadlines}


async def _rain_tomorrow(db, owner: str) -> str:
    try:
        from brief.morning import _where
        import weather as weather_service

        point = await _where(db, owner)
        if point is None:
            return ""
        data = await weather_service.forecast_at(lat=point[0], lon=point[1], place=point[2])
        days = data.get("days") or []
        if not data.get("available") or len(days) < 2:
            return ""
        d = days[1]
        rain = d.get("rain_chance_pct")
        temp = f"{d['min_c']}–{d['max_c']} °C" if d.get("min_c") is not None and d.get("max_c") is not None else ""
        if rain is not None and rain >= 50:
            return f"Pioggia {rain}%: serve l'ombrello" + (f", {temp}" if temp else "")
        return (f"{d.get('condition_label') or 'Tempo'}, {temp}" if temp else "")
    except Exception as exc:
        logger.info("evening weather skipped: %s", type(exc).__name__)
        return ""


def compose(events: List[str], deadlines: List[str], weather: str) -> str:
    if not events and not deadlines:
        return ""
    parts = []
    if events:
        parts.append("Domani: " + "; ".join(events) + ".")
    if deadlines:
        parts.append(("Scade domani: " if events else "Domani scade: ") + "; ".join(deadlines) + ".")
    if weather:
        parts.append(weather[0].upper() + weather[1:] + ".")
    text = " ".join(parts)
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS - 1].rstrip() + "…"


async def build(db, owner: str, local_now: datetime) -> str:
    t = await _tomorrow(db, owner, local_now)
    if not t["events"] and not t["deadlines"]:
        return ""
    return compose(t["events"], t["deadlines"], await _rain_tomorrow(db, owner))


async def fire_due(db, *, now: Optional[datetime] = None, limit: int = 50) -> Dict[str, int]:
    from timezone_service import user_clock_context

    now = now or datetime.now(timezone.utc)
    out = {"checked": 0, "queued": 0, "empty": 0}
    owners: List[str] = []
    for field in ("owner_id", "user_id"):
        try:
            owners += await db.push_endpoints.distinct(field, {"status": "active"})
        except Exception:
            pass
    for owner in list(dict.fromkeys(o for o in owners if o))[:limit]:
        pref = await preference(db, owner)
        if not pref["enabled"]:
            continue
        clock = await user_clock_context(db, owner, now=now)
        local_now = datetime.fromisoformat(clock["local_datetime"])
        due = local_now.replace(hour=pref["hour"], minute=DEFAULT_MINUTE if pref["hour"] == DEFAULT_HOUR else 0,
                                second=0, microsecond=0)
        if not (due <= local_now < due + timedelta(hours=LATE_HOURS)) or local_now.date() != due.date():
            continue
        out["checked"] += 1
        rid = f"rem_evening_{owner}_{local_now.date().isoformat()}"[:80]
        claimed = await db.brief_runs.update_one(
            {"_id": rid}, {"$setOnInsert": {"owner_id": owner, "at": now.isoformat()}}, upsert=True)
        if not claimed.upserted_id:
            continue
        text = await build(db, owner, local_now)
        if not text:
            out["empty"] += 1
            continue
        stamp = now.isoformat()
        await db.reminders.insert_one({
            "id": rid, "user_id": owner, "title": text, "status": "open", "due_at": stamp,
            "origin": ORIGIN, "created_at": stamp, "updated_at": stamp, "meta": {"kind": ORIGIN},
        })
        out["queued"] += 1
    if out["queued"] or out["empty"]:
        logger.info("evening_brief %s", out)
    return out
