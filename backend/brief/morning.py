"""
The morning brief: the day in one notification, written by code.

ORA knew today's appointments, the deadlines, the reminders and the weather
of the person's home, and said none of it together. At the person's chosen
hour (08:00 unless changed) one notification sums the day up:

    Oggi: dentista alle 10:30; scade F24. Promemoria: pastiglia alle 20.
    Tarquinia 12-19 °C, pioggia 10%: se stendi alle 9, asciutti verso le 15.

Built only from stored facts and the hourly forecast, no model: it arrives
even when the model is out of quota. Nothing to say means no notification.
It travels through the one-time reminder lane, once a day at most, and can be
switched off in Settings.
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ora.brief")

DEFAULT_HOUR = 8
# A brief later than this after its hour is no longer a morning brief.
LATE_HOURS = 3
MAX_CHARS = 280
ORIGIN = "morning_brief"


async def preference(db, owner: str) -> Dict[str, Any]:
    row = await db.users.find_one({"user_id": owner}, {"_id": 0, "preferences.morning_brief": 1})
    pref = ((row or {}).get("preferences") or {}).get("morning_brief") or {}
    hour = pref.get("hour", DEFAULT_HOUR)
    try:
        hour = max(5, min(11, int(hour)))
    except (TypeError, ValueError):
        hour = DEFAULT_HOUR
    return {"enabled": pref.get("enabled", True) is not False, "hour": hour}


async def set_preference(db, owner: str, *, enabled: Optional[bool] = None, hour: Optional[int] = None) -> Dict[str, Any]:
    current = await preference(db, owner)
    if enabled is not None:
        current["enabled"] = bool(enabled)
    if hour is not None:
        current["hour"] = max(5, min(11, int(hour)))
    await db.users.update_one({"user_id": owner}, {"$set": {"preferences.morning_brief": current}})
    return current


def _hhmm(value: Any, tz) -> str:
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (moment if moment.tzinfo else moment.replace(tzinfo=tz)).astimezone(tz).strftime("%H:%M")
    except (TypeError, ValueError):
        return ""


async def _appointments(db, owner: str, local_now: datetime) -> List[str]:
    from opportunities.snapshot import _calendar

    out = []
    for e in await _calendar(db, owner, local_now):
        if e.get("in_days") != 0:
            continue
        title = " ".join(str(e.get("title") or "Appuntamento").split())[:40]
        clock = "" if e.get("all_day") else _hhmm(e.get("starts_at"), local_now.tzinfo)
        out.append(f"{title} alle {clock}" if clock else title)
    return out[:3]


async def _deadlines(db, owner: str, local_now: datetime) -> List[str]:
    from opportunities.deadlines import as_facts, upcoming

    facts = as_facts(await upcoming(db, owner, local_now, days=1), local_now)
    out = []
    for f in facts:
        title = " ".join(str(f.get("title") or "").split())[:40]
        if f.get("overdue"):
            out.append(f"{title} (scaduta)")
        elif f.get("days_left") == 0:
            out.append(f"{title} oggi")
        elif f.get("days_left") == 1:
            out.append(f"{title} domani")
    return out[:3]


async def _reminders(db, owner: str, local_now: datetime) -> List[str]:
    end = datetime.combine(local_now.date() + timedelta(days=1), time(0), tzinfo=local_now.tzinfo)
    rows = await db.reminders.find(
        {"user_id": owner, "status": {"$in": ["open", "active", "pending"]},
         "notified_state": {"$exists": False}, "origin": {"$nin": [ORIGIN, "phone_call_result"]},
         "due_at": {"$gte": local_now.astimezone(timezone.utc).isoformat(),
                    "$lt": end.astimezone(timezone.utc).isoformat()}},
        {"_id": 0, "title": 1, "due_at": 1}).sort("due_at", 1).to_list(5)
    return [f"{' '.join(str(r.get('title') or '').split())[:35]} alle {_hhmm(r.get('due_at'), local_now.tzinfo)}"
            for r in rows][:3]


async def _home_weather(db, owner: str, local_now: datetime) -> str:
    """Today at home, and whether a load hung out at 9 would dry today."""
    try:
        point = await _where(db, owner)
        if point is None:
            return ""
        lat, lon, label = point
        import weather as weather_service
        data = await weather_service.forecast_at(lat=lat, lon=lon, place=label)
        if not data.get("available"):
            return ""
        today = (data.get("days") or [{}])[0]
        place = (label or "Da te")[:24]
        bits = [place]
        if today.get("min_c") is not None and today.get("max_c") is not None:
            bits.append(f"{today['min_c']}-{today['max_c']} °C")
        if today.get("rain_chance_pct") is not None:
            bits.append(f"pioggia {today['rain_chance_pct']}%")
        text = " ".join(bits[:1]) + (", " + ", ".join(bits[1:]) if len(bits) > 1 else "")
        from situations import outdoor_drying as od
        from situations.calibration import factor
        hang = local_now.replace(hour=9, minute=0, second=0, microsecond=0)
        if local_now > hang:
            hang = local_now
        hours = await od._fetch_hours(lat, lon, hang)
        units = od.LOAD_UNITS * await factor(db, owner, "drying")
        result = od.compute(hours, start=hang.astimezone(timezone.utc), now=hang.astimezone(timezone.utc), units=units)
        dry, dusk = result.get("dry_at"), result.get("dusk_at")
        if dry and (dusk is None or dry <= dusk + timedelta(minutes=30)):
            text += f": se stendi alle {hang.strftime('%H:%M')}, asciutti verso le {dry.astimezone(local_now.tzinfo).strftime('%H:%M')}"
        elif hours:
            text += ": oggi i panni fuori non si asciugano entro sera"
        return text
    except Exception as exc:
        logger.info("brief weather skipped: %s", type(exc).__name__)
        return ""


async def _where(db, owner: str):
    """
    Where the day's weather is read: the confirmed home; else the place where
    things were last hung out to dry (30/10: no home saved, so the first brief
    had nothing to say); else where the person is now, if location is on.
    """
    from places.service import PlacesService

    places = PlacesService(db)
    for p in await places.list_places(owner):
        if p.role == "home" and p.coordinates is not None and p.state == "confirmed":
            return p.coordinates.latitude, p.coordinates.longitude, p.locality or p.label
    last = await db.reminders.find_one(
        {"user_id": owner, "meta.kind": "drying_end"}, {"_id": 0, "meta": 1}, sort=[("updated_at", -1)])
    meta = (last or {}).get("meta") or {}
    if meta.get("place_ref"):
        p = await places.get_place(owner, str(meta["place_ref"]).split(":", 1)[-1])
        if p and p.coordinates is not None:
            return p.coordinates.latitude, p.coordinates.longitude, p.locality or p.label
    if meta.get("point"):
        sit = await db.situations.find_one({"user_id": owner, "id": meta.get("situation_id")},
                                           {"_id": 0, "location_label": 1})
        return float(meta["point"][0]), float(meta["point"][1]), (sit or {}).get("location_label") or ""
    try:
        from home.service import HomeService
        here = await HomeService(db)._where_they_are(owner)
        if here:
            return here
    except Exception:
        pass
    return None


def compose(appointments: List[str], deadlines: List[str], reminders: List[str], weather: str) -> str:
    parts = []
    today = appointments + deadlines
    if today:
        parts.append("Oggi: " + "; ".join(today) + ".")
    if reminders:
        parts.append("Promemoria: " + "; ".join(reminders) + ".")
    if weather:
        parts.append(weather[0].upper() + weather[1:] + ".")
    text = " ".join(parts)
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS - 1].rstrip() + "…"


async def build(db, owner: str, local_now: datetime) -> str:
    return compose(await _appointments(db, owner, local_now), await _deadlines(db, owner, local_now),
                   await _reminders(db, owner, local_now), await _home_weather(db, owner, local_now))


async def fire_due(db, *, now: Optional[datetime] = None, limit: int = 50) -> Dict[str, int]:
    """Once a day per person, at their hour: queue the brief in the reminder lane."""
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
        due = local_now.replace(hour=pref["hour"], minute=0, second=0, microsecond=0)
        if not (due <= local_now < due + timedelta(hours=LATE_HOURS)):
            continue
        out["checked"] += 1
        rid = f"rem_brief_{owner}_{local_now.date().isoformat()}"[:80]
        claimed = await db.brief_runs.update_one(
            {"_id": rid}, {"$setOnInsert": {"owner_id": owner, "at": now.isoformat()}}, upsert=True)
        if not claimed.upserted_id:
            continue  # already done today (or by another instance)
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
        logger.info("morning_brief %s", out)
    return out
