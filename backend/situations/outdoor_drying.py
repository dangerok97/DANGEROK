"""
Things drying outdoors: an estimate computed from the weather, not guessed.

24-26/10/2026, Tarquinia, 16 °C and 65% humidity: the watch was a model
reading a weather summary as text. It announced "dry by mid-afternoon",
drifted, misread the clock, and with the stronger model out of quota it
stopped answering. The person's verdict: "non mi quadra".

Drying is physics the code can do. Every hour of the provider's hourly
forecast contributes evaporation in proportion to:

* the vapour-pressure deficit (how much water the air can still take:
  temperature and relative humidity together),
* wind (moving air carries the vapour away),
* sunshine (shortwave radiation; at night it almost stops),

and nothing while it rains. When the sum reaches the amount a normal load
needs, that is the estimate. The constant is calibrated on common
experience: about 1.5-2.5 hours on a hot dry summer day, about 7 on a sunny autumn
one (late October, 16-17 °C: close to dusk), a full day or more when grey and damp.

What the person hears, all sent by code through the one-time reminder lane:
* "dovrebbero essere asciutti" at the computed time;
* "sta per piovere" before rain the forecast puts ahead of that time;
* "oggi non si asciugano prima di sera" when the estimate runs past dusk,
  with a reminder before dark to take them in.

The plan is recomputed with a fresh forecast every hour by the self-check,
so the time moves with the weather instead of with a model's mood. It is an
estimate from a forecast, never an observation of the clothes, and says so.
"""
from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ORIGIN = "situation_stated_time"  # same lane and lifecycle as stated moments
# Drying units a normal load needs (see module docstring for calibration).
LOAD_UNITS = 13.0
RAIN_PROBABILITY = 50
RAIN_MM = 0.2
RAIN_WARN_MINUTES = 45
DUSK_MARGIN_MINUTES = 30
REPLAN_MINUTES = 60
HORIZON_HOURS = 36

_ITEMS = r"(?:panni|bucato|biancheria|lenzuol[ao]|asciugaman[oi]|vestiti|maglie|jeans|tovagli[ae]|lavatrice)"
_OUT = r"(?:stes[oiae]|stender[eli]|stendo|appes[oiae]|fuori|balcone|terrazz[oa]|giardino|stendino|filo)"
_PATTERN = re.compile(rf"\b{_ITEMS}\b[^.?!]{{0,40}}\b{_OUT}|\b{_OUT}\b[^.?!]{{0,40}}\b{_ITEMS}\b")
_INDOOR = re.compile(r"\b(?:asciugatrice|in casa|dentro casa|termosifon[ei]|stendino in casa)\b")


def applies(*texts: str) -> bool:
    joined = " . ".join(" ".join(str(t or "").casefold().split()) for t in texts if t)
    return bool(joined) and "?" not in joined and bool(_PATTERN.search(joined)) and not _INDOOR.search(joined)


def _vpd_kpa(temp_c: float, rh: float) -> float:
    es = 0.6108 * math.exp(17.27 * temp_c / (temp_c + 237.3))
    return max(0.0, es * (1 - max(0.0, min(100.0, rh)) / 100))


def hourly_rate(temp_c: float, rh: float, wind_kmh: float, radiation_wm2: Optional[float],
                is_day: Optional[bool]) -> float:
    """Drying units per hour for one hour of weather."""
    wind = 1 + 0.08 * min(max(wind_kmh or 0.0, 0.0), 30.0)
    if radiation_wm2 is not None:
        sun = 0.4 + min(max(radiation_wm2, 0.0), 600.0) / 600.0 * 1.1
    else:
        sun = 1.0 if is_day else 0.4
    return _vpd_kpa(temp_c, rh) * wind * sun


def _moment(value: Any) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def compute(hours: List[Dict[str, Any]], *, start: datetime, now: datetime) -> Dict[str, Any]:
    """
    hours: [{at (aware), temp_c, rh, wind_kmh, radiation, is_day, rain_pct, rain_mm}] in order.
    Returns {dry_at, rain_at, dusk_at, done_fraction, conditions} — instants are aware or None.
    """
    total = 0.0
    dry_at = rain_at = dusk_at = None
    done_now = None
    seen: Dict[str, List[float]] = {"temp": [], "rh": [], "wind": []}
    for h in hours:
        at = h["at"]
        end = at + timedelta(hours=1)
        if end <= start:
            continue
        span_from = max(at, start)
        fraction = (end - span_from).total_seconds() / 3600
        raining = (h.get("rain_mm") or 0) >= RAIN_MM or (h.get("rain_pct") or 0) >= RAIN_PROBABILITY
        if at >= now - timedelta(hours=1) and dry_at is None:
            if raining and rain_at is None and end > now:
                rain_at = max(at, now)
            if dusk_at is None and h.get("is_day") is not None and not h["is_day"] and at > now:
                dusk_at = at
        if end > now and at < now + timedelta(hours=12):
            seen["temp"].append(h["temp_c"]); seen["rh"].append(h["rh"]); seen["wind"].append(h["wind_kmh"])
        rate = 0.0 if raining else hourly_rate(h["temp_c"], h["rh"], h["wind_kmh"], h.get("radiation"), h.get("is_day"))
        if done_now is None and at <= now < end:
            done_now = min(1.0, (total + rate * max(0.0, (now - span_from).total_seconds() / 3600)) / LOAD_UNITS)
        if dry_at is None and rate > 0 and total + rate * fraction >= LOAD_UNITS:
            dry_at = span_from + timedelta(hours=(LOAD_UNITS - total) / rate)
        total += rate * fraction
    conditions = {k: [round(min(v)), round(max(v))] for k, v in seen.items() if v}
    night_now = any(h["at"] <= now < h["at"] + timedelta(hours=1) and h.get("is_day") is False for h in hours)
    if done_now is None:
        done_now = min(1.0, total / LOAD_UNITS) if hours and hours[-1]["at"] < now else 0.0
    return {"dry_at": dry_at, "rain_at": rain_at if (rain_at and (dry_at is None or rain_at < dry_at)) else None,
            "dusk_at": dusk_at, "done_fraction": round(done_now, 2), "conditions": conditions,
            "night_now": night_now}


async def _fetch_hours(lat: float, lon: float, start: datetime) -> List[Dict[str, Any]]:
    import httpx

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat:.3f}&longitude={lon:.3f}"
        "&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation_probability,"
        "precipitation,shortwave_radiation,is_day"
        "&timezone=UTC&past_days=1&forecast_days=2"
    )
    async with httpx.AsyncClient(timeout=8.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = (r.json() or {}).get("hourly") or {}
    out = []
    for i, t in enumerate(data.get("time") or []):
        at = _moment(str(t) + ("" if str(t).endswith("Z") else "+00:00"))
        def v(key):
            seq = data.get(key) or []
            return seq[i] if i < len(seq) else None
        if at is None or v("temperature_2m") is None or v("relative_humidity_2m") is None:
            continue
        if at + timedelta(hours=1) <= start - timedelta(hours=1):
            continue
        out.append({"at": at, "temp_c": float(v("temperature_2m")), "rh": float(v("relative_humidity_2m")),
                    "wind_kmh": float(v("wind_speed_10m") or 0), "radiation": v("shortwave_radiation"),
                    "is_day": (bool(v("is_day")) if v("is_day") is not None else None),
                    "rain_pct": v("precipitation_probability"), "rain_mm": v("precipitation")})
    return out


async def where(db, owner: str, situation) -> Optional[Dict[str, Any]]:
    """
    Where the things are drying: the Situation's own place, never the phone.

    The person may leave; what is drying stays. Same rule as the watch's
    weather read: the place linked to the Situation, else its confirmed
    locality resolved unambiguously, else the confirmed home.
    """
    try:
        from places.service import PlacesService

        places = PlacesService(db)
        for ref in getattr(situation, "linked_object_refs", None) or []:
            if str(ref).startswith("place:"):
                p = await places.get_place(owner, str(ref).split(":", 1)[1])
                if p and p.coordinates is not None and p.state == "confirmed":
                    return {"lat": p.coordinates.latitude, "lon": p.coordinates.longitude,
                            "label": p.locality or p.label, "ref": f"place:{p.id}"}
        label = " ".join(str(getattr(situation, "location_label", "") or "").split())
        if label:
            from places import lookup

            suggestions = await lookup.suggest(label)
            place_id = lookup.unique_locality_match(suggestions, label) if suggestions.get("available") else None
            if place_id:
                resolved = await lookup.resolve(place_id)
                if resolved.get("available") and resolved.get("latitude") is not None:
                    return {"lat": round(float(resolved["latitude"]), 2), "lon": round(float(resolved["longitude"]), 2),
                            "label": label, "ref": ""}
        for p in await places.list_places(owner):
            if p.role == "home" and p.coordinates is not None and p.state == "confirmed":
                return {"lat": p.coordinates.latitude, "lon": p.coordinates.longitude,
                        "label": p.locality or p.label, "ref": f"place:{p.id}"}
    except Exception as exc:
        logger.info("drying place soft-fail: %s", type(exc).__name__)
    return None


def _hhmm(moment: datetime, tz) -> str:
    return moment.astimezone(tz).strftime("%H:%M")


def _conditions_text(c: Dict[str, List[int]]) -> str:
    bits = []
    if "temp" in c:
        bits.append(f"{c['temp'][0]}–{c['temp'][1]} °C" if c["temp"][0] != c["temp"][1] else f"{c['temp'][0]} °C")
    if "rh" in c:
        bits.append(f"umidità {c['rh'][0]}–{c['rh'][1]}%")
    if "wind" in c:
        bits.append(f"vento fino a {c['wind'][1]} km/h")
    return ", ".join(bits)


async def plan(db, owner: str, situation, *, now: Optional[datetime] = None, tz=None,
               place: Optional[Dict[str, Any]] = None, hours=None) -> Optional[Dict[str, Any]]:
    """Compute and (re)write the drying reminders for this Situation. Never raises."""
    try:
        now = now or datetime.now(timezone.utc)
        if tz is None:
            from timezone_service import user_clock_context
            tz = datetime.fromisoformat((await user_clock_context(db, owner))["local_datetime"]).tzinfo
        place = place or await where(db, owner, situation)
        if place is None:
            return None
        start = _moment(getattr(situation, "started_at", None)) or _moment(getattr(situation, "created_at", None)) or now
        if start > now or now - start > timedelta(hours=HORIZON_HOURS):
            start = now
        hours = hours if hours is not None else await _fetch_hours(place["lat"], place["lon"], start)
        if not hours:
            return None
        result = compute(hours, start=start, now=now)
        summary = " ".join(str(situation.summary or "").split())[:100]
        weather = _conditions_text(result["conditions"])
        sid = situation.id
        dry_at, rain_at, dusk_at = result["dry_at"], result["rain_at"], result["dusk_at"]
        not_today = bool(dry_at and dusk_at and dry_at > dusk_at + timedelta(minutes=60)) or (dry_at is None)
        if dry_at and dry_at <= now:
            dry_at = now + timedelta(minutes=1)  # already enough: say it now
        main_at = dry_at
        at_dusk = None
        if not_today and dusk_at:
            main_at = max(now + timedelta(minutes=2), dusk_at - timedelta(minutes=DUSK_MARGIN_MINUTES))
            at_dusk = compute(hours, start=start, now=main_at)["done_fraction"]
            share = f", a quell'ora circa al {round(at_dusk * 100)}%" if at_dusk and at_dusk < 1 else ""
            if result.get("night_now"):
                # Already dark: drying has practically stopped until morning.
                main_at = now + timedelta(minutes=2)
                share = f" (ora circa al {round(result['done_fraction'] * 100)}%)" if result["done_fraction"] < 1 else ""
                title = (f"È già buio e l'aria si fa umida: con questo meteo non si asciugano stanotte, "
                         f"conviene ritirarli{share} ({summary})")
            else:
                title = (f"Con questo meteo non si asciugano del tutto prima di sera: conviene ritirarli verso "
                         f"le {_hhmm(main_at, tz)}{share} ({summary})")
        elif dry_at:
            title = f"Dovrebbero essere asciutti, secondo il meteo: {summary}"
        else:
            title = ""
        meta = {"situation_id": sid, "kind": "drying_end", "place_ref": place.get("ref", ""),
                "point": None if place.get("ref") else [place["lat"], place["lon"]],
                "planned_at": now.isoformat(), "done_fraction": result["done_fraction"],
                "weather": weather[:120]}
        stamp = now.isoformat()
        if main_at and main_at > now:
            await _upsert(db, owner, f"rem_sit_{sid}"[:80], main_at, title, meta, stamp)
        if rain_at and rain_at > now - timedelta(minutes=5):
            warn = max(now + timedelta(minutes=1), rain_at - timedelta(minutes=RAIN_WARN_MINUTES))
            rain_title = f"Il meteo dà pioggia verso le {_hhmm(rain_at, tz)}: conviene ritirarli prima ({summary})"
            await _upsert(db, owner, f"rem_sit_{sid}_rain"[:80], warn, rain_title,
                          {**meta, "kind": "rain_risk", "rain_at": rain_at.isoformat()}, stamp)
        else:
            await db.reminders.update_many(
                {"id": f"rem_sit_{sid}_rain"[:80], "user_id": owner, "status": "open",
                 "notified_state": {"$exists": False}},
                {"$set": {"status": "cancelled", "updated_at": stamp}})
        return {
            "at_local": _hhmm(main_at, tz) if main_at else None,
            "dry_at_local": _hhmm(dry_at, tz) if dry_at else None,
            "not_today": not_today,
            "rain_at_local": _hhmm(rain_at, tz) if rain_at else None,
            "done_fraction": result["done_fraction"],
            "done_fraction_by_evening": at_dusk,
            "weather": weather,
            "place": place.get("label") or "",
            "method": "calcolo dal meteo orario (temperatura, umidità, vento, sole, pioggia); stima, non osservazione",
        }
    except Exception as exc:
        logger.info("drying plan deferred: %s", type(exc).__name__)
        return None


async def _upsert(db, owner, rid, due: datetime, title, meta, stamp) -> None:
    existing = await db.reminders.find_one({"id": rid, "user_id": owner}, {"_id": 0})
    due_iso = due.astimezone(timezone.utc).isoformat()
    if existing and existing.get("notified_state"):
        return  # already told: never say it twice
    if existing and existing.get("due_at") == due_iso and existing.get("title") == title:
        await db.reminders.update_one({"id": rid, "user_id": owner}, {"$set": {"meta": meta}})
        return
    await db.reminders.update_one(
        {"id": rid, "user_id": owner},
        {"$set": {"id": rid, "user_id": owner, "status": "open", "due_at": due_iso, "title": title[:160],
                  "origin": ORIGIN, "updated_at": stamp, "meta": meta},
         "$setOnInsert": {"created_at": stamp}},
        upsert=True)


async def replan_due(db, owner: str, *, now: Optional[datetime] = None) -> List[dict]:
    """Self-check: refresh every open drying plan whose forecast is an hour old."""
    from situations.repository import SituationRepository

    now = now or datetime.now(timezone.utc)
    out = []
    rows = await db.reminders.find(
        {"user_id": owner, "origin": ORIGIN, "meta.kind": "drying_end", "status": "open",
         "notified_state": {"$exists": False}}, {"_id": 0}).to_list(10)
    for row in rows:
        meta = row.get("meta") or {}
        planned = _moment(meta.get("planned_at"))
        if planned and now - planned < timedelta(minutes=REPLAN_MINUTES):
            continue
        situation = await SituationRepository(db).get(owner, meta.get("situation_id") or "")
        if situation is None or situation.status not in ("active", "changed"):
            continue
        place = None
        if meta.get("point"):
            place = {"lat": meta["point"][0], "lon": meta["point"][1], "label": "", "ref": ""}
        before = row.get("due_at")
        result = await plan(db, owner, situation, now=now, place=place)
        after = (await db.reminders.find_one({"id": row["id"]}, {"_id": 0, "due_at": 1}) or {}).get("due_at")
        out.append({"code": "drying_replanned", "ref": f"situation:{situation.id}",
                    "repaired": bool(result), "moved": before != after})
    return out


def _texts(situation) -> list:
    return [str(getattr(situation, f, "") or "") for f in
            ("summary", "tracking_summary", "current_state_summary", "attention_intent")] + \
           [" ".join(getattr(situation, "facts", None) or [])]


def concerns(situation) -> bool:
    """Whether this Situation is about something drying outdoors (its own words)."""
    return applies(*_texts(situation))


async def ensure_planned(db, owner: str, situation) -> Optional[Dict[str, Any]]:
    """
    Plan once for a drying Situation that has no plan yet. Never raises.

    27/10: the plan was armed only from the chat turn that created the
    Situation, and only if the model had already marked it as watched. That
    mark arrived a step later, the plan never ran, and the person heard from
    the model's own watch at 21:04, hours after dark.
    """
    try:
        if situation.status not in ("active", "changed") or not concerns(situation):
            return None
        if await db.reminders.find_one({"user_id": owner, "id": f"rem_sit_{situation.id}"[:80]}, {"_id": 1}):
            return None
        return await plan(db, owner, situation)
    except Exception as exc:
        logger.info("drying ensure deferred: %s", type(exc).__name__)
        return None


async def plan_missing(db, owner: str, *, now: Optional[datetime] = None) -> List[dict]:
    """Self-check: every active drying Situation has a computed plan."""
    from situations.models import SituationState

    out = []
    rows = await db.situations.find(
        {"user_id": owner, "status": {"$in": ["active", "changed"]}}, {"_id": 0}).to_list(20)
    for row in rows:
        try:
            situation = SituationState(**row)
        except Exception:
            continue
        if not concerns(situation):
            continue
        planned = await ensure_planned(db, owner, situation)
        if planned:
            out.append({"code": "drying_planned", "ref": f"situation:{situation.id}", "repaired": True})
    return out


async def speaks_for(db, owner: str, situation_id: str) -> bool:
    """The computed plan is the one voice for this Situation (no double pushes)."""
    if not situation_id:
        return False
    row = await db.reminders.find_one(
        {"user_id": owner, "id": f"rem_sit_{situation_id}"[:80], "meta.kind": "drying_end",
         "status": {"$ne": "cancelled"}}, {"_id": 1})
    return row is not None


async def situation_of(db, owner: str, kind: str, subject) -> str:
    """The Situation a notification is about, when it is about exactly one."""
    refs: list = []
    if kind == "agent_need":
        goal = await db.agent_goals.find_one(
            {"owner_id": owner, "id": getattr(subject, "goal_id", "")}, {"_id": 0, "source_refs": 1})
        refs = [str(r) for r in (goal or {}).get("source_refs") or []]
    elif kind == "opportunity":
        refs = [str(getattr(e, "ref", "")) for e in getattr(subject, "evidence", None) or []]
    ids = {r.split(":")[1] for r in refs if r.startswith("situation:") and len(r.split(":")) > 1}
    return next(iter(ids)) if len(ids) == 1 else ""
