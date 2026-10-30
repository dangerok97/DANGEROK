"""
«È ora di metterti in moto»: when to leave, computed and sent by code.

Owner 30/10: «alle 15 ho l'appuntamento dal parrucchiere a Montalto di
Castro» — ORA must work out how long before to say it's time to go, and have
the route ready.

The departure estimate already existed (places/departures.py) but only ran
with a phone position less than two minutes old — rare for a web app — and
the notice itself was left to a model's judgement. Here, for every timed
appointment with a place in the next 12 hours:

* origin: a fresh position if there is one; else the confirmed home; else
  the last known position of the last 8 hours (said which, in the notice);
* destination: a saved place by name, else the place service (the town or
  the business named), else the map provider's own match;
* the drive time from the routing provider (with live traffic where the
  provider has it), plus a 10-minute margin;
* one reminder in the one-time reminder lane at the leave time, with the
  route ready to open, recomputed every 15 minutes until it is sent: traffic
  and position move the time, a moved or cancelled appointment moves or
  cancels it.

A route that cannot be computed never becomes a guess: no notice, and the
reason is returned to whoever asked.
"""
from __future__ import annotations

import hashlib
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

logger = logging.getLogger("ora.leave")

LOOKAHEAD_HOURS = 12
MARGIN_MINUTES = 10
LAST_KNOWN_HOURS = 8
KIND = "leave_notice"
ORIGIN = "leave_notice"


def _instant(value) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else None


def route_url(dest: Dict[str, float], mode: str = "drive") -> str:
    travel = {"drive": "driving", "walk": "walking", "bicycle": "bicycling", "transit": "transit"}.get(mode, "driving")
    return (f"https://www.google.com/maps/dir/?api=1&destination={dest['latitude']:.5f},{dest['longitude']:.5f}"
            f"&travelmode={travel}")


def reminder_id(event_ref: str) -> str:
    return "rem_leave_" + hashlib.sha256(str(event_ref).encode()).hexdigest()[:20]


async def origin_for(db, owner: str, now: datetime) -> Optional[Dict[str, Any]]:
    """Where the trip starts: here now, else home, else the last known place."""
    try:
        from places.departures import DepartureService, current_origin
        presence = await DepartureService(db)._departure_presence(owner, now)
        fresh = current_origin(presence, now)
        if fresh:
            return {**fresh, "kind": "here"}
    except Exception as exc:
        logger.info("leave origin presence soft-fail: %s", type(exc).__name__)
        presence = None
    try:
        from places.service import PlacesService
        for p in await PlacesService(db).list_places(owner):
            if p.role == "home" and p.coordinates is not None and p.state == "confirmed":
                return {"latitude": p.coordinates.latitude, "longitude": p.coordinates.longitude, "kind": "home"}
    except Exception as exc:
        logger.info("leave origin home soft-fail: %s", type(exc).__name__)
    seen = _instant(getattr(presence, "last_seen_at", None)) if presence else None
    if (presence is not None and seen and now - seen <= timedelta(hours=LAST_KNOWN_HOURS)
            and presence.latitude is not None and presence.longitude is not None):
        return {"latitude": presence.latitude, "longitude": presence.longitude, "kind": "last_known"}
    return None


async def destination_for(db, owner: str, location: str, origin: Dict[str, float]) -> Optional[Dict[str, Any]]:
    label = " ".join(str(location or "").split())[:160]
    if not label:
        return None
    try:
        from places.service import PlacesService
        res = await PlacesService(db).resolve_destination(owner, label)
        if res.resolved and res.place and res.place.coordinates:
            c = res.place.coordinates
            return {"latitude": c.latitude, "longitude": c.longitude, "label": res.place.label or label}
    except Exception as exc:
        logger.info("leave destination saved soft-fail: %s", type(exc).__name__)
    try:
        from places import lookup
        sugg = await lookup.suggest(label)
        if sugg.get("available"):
            items = [i for i in (sugg.get("suggestions") or []) if isinstance(i, dict) and i.get("place_id")]
            pid = lookup.unique_locality_match(sugg, label) or (items[0]["place_id"] if len(items) == 1 else None)
            if pid is None and items:
                # «parrucchiere a Montalto di Castro»: the town is enough to leave on time.
                town = label.rsplit(" a ", 1)[-1] if " a " in label else ""
                if town and town != label:
                    tsugg = await lookup.suggest(town)
                    pid = lookup.unique_locality_match(tsugg, town) if tsugg.get("available") else None
            if pid:
                r = await lookup.resolve(pid)
                if r.get("available") and r.get("latitude") is not None:
                    return {"latitude": float(r["latitude"]), "longitude": float(r["longitude"]),
                            "label": str(r.get("locality") or r.get("address") or label)[:80]}
    except Exception as exc:
        logger.info("leave destination lookup soft-fail: %s", type(exc).__name__)
    try:
        from places.public_search import preview_destination
        d = await preview_destination(label, origin)
        if d:
            return {"latitude": d["latitude"], "longitude": d["longitude"], "label": label}
    except Exception as exc:
        logger.info("leave destination preview soft-fail: %s", type(exc).__name__)
    return None


async def plan_event(db, owner: str, event: Dict[str, Any], *, now: datetime, tz) -> Dict[str, Any]:
    """Compute and (re)write the leave reminder for one appointment."""
    from places import routing

    start = _instant(event.get("starts_at"))
    title = " ".join(str(event.get("title") or "Appuntamento").split())[:60]
    location = str(event.get("location") or "")
    rid = reminder_id(event.get("ref") or f"{title}|{event.get('starts_at')}")
    if start is None or not location:
        return {"status": "no_place_or_time"}
    existing = await db.reminders.find_one({"id": rid, "user_id": owner}, {"_id": 0})
    if existing and existing.get("notified_state"):
        return {"status": "already_told"}
    if existing and existing.get("status") == "open":
        # Far from the leave time a fresh route every 15 minutes buys nothing:
        # refresh every 30 minutes, and every pass in the last two hours.
        meta = existing.get("meta") or {}
        planned, due = _instant(meta.get("planned_at")), _instant(existing.get("due_at"))
        if (planned and due and meta.get("starts_at") == start.isoformat()
                and now - planned < timedelta(minutes=30) and due - now > timedelta(hours=2)):
            return {"status": "planned", "unchanged": True}
    if not routing.capabilities().get("available"):
        return {"status": "routing_unavailable"}
    origin = await origin_for(db, owner, now)
    if origin is None:
        return {"status": "needs_location"}
    dest = await destination_for(db, owner, location, origin)
    if dest is None:
        return {"status": "destination_unresolved"}
    route = None
    mode = "drive"
    for mode in ("drive", "transit", "walk"):
        if mode not in routing.capabilities().get("modes", []):
            continue
        r = await routing.get_route(origin={k: origin[k] for k in ("latitude", "longitude")},
                                    destination={k: dest[k] for k in ("latitude", "longitude")}, travel_mode=mode)
        d = r.get("duration_seconds") if isinstance(r, dict) and r.get("available") else None
        if isinstance(d, (int, float)) and math.isfinite(d) and d > 0:
            route = r
            break
    if route is None:
        return {"status": "routing_unavailable"}
    minutes = math.ceil(route["duration_seconds"] / 60)
    leave = start - timedelta(minutes=minutes + MARGIN_MINUTES)
    late = leave <= now
    labels = {"drive": "in auto", "transit": "con i mezzi", "walk": "a piedi"}
    from_where = {"here": "", "home": " da casa", "last_known": " dall'ultima posizione nota"}[origin["kind"]]
    clock = start.astimezone(tz).strftime("%H:%M")
    if late:
        text = (f"Per «{title}» alle {clock} dovresti già essere in viaggio: servono circa {minutes} min "
                f"{labels[mode]}{from_where}. Il percorso è pronto.")
    else:
        text = (f"È ora di metterti in moto per «{title}» alle {clock}: circa {minutes} min {labels[mode]}"
                f"{from_where}, con {MARGIN_MINUTES} min di margine. Il percorso è pronto.")
    due = (now + timedelta(minutes=1)) if late else leave
    stamp = now.isoformat()
    meta = {"kind": KIND, "event_ref": event.get("ref"), "route_url": route_url(dest, mode), "mode": mode,
            "minutes": minutes, "origin_kind": origin["kind"], "destination": dest.get("label") or location,
            "reflects_traffic": bool(route.get("reflects_current_traffic")), "planned_at": stamp,
            "starts_at": start.isoformat()}
    await db.reminders.update_one(
        {"id": rid, "user_id": owner},
        {"$set": {"id": rid, "user_id": owner, "title": text[:280], "status": "open",
                  "due_at": due.astimezone(timezone.utc).isoformat(), "origin": ORIGIN, "updated_at": stamp,
                  "meta": meta},
         "$setOnInsert": {"created_at": stamp}},
        upsert=True)
    return {"status": "planned", "leave_at_local": leave.astimezone(tz).strftime("%H:%M"), "minutes": minutes,
            "mode": labels[mode], "from": origin["kind"], "late": late, "destination": meta["destination"]}


async def plan_owner(db, owner: str, *, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Self-check and after a new appointment: every upcoming appointment with a place."""
    from opportunities.snapshot import _calendar
    from timezone_service import user_clock_context

    now = now or datetime.now(timezone.utc)
    clock = await user_clock_context(db, owner, now=now)
    local_now = datetime.fromisoformat(clock["local_datetime"])
    out = []
    live = set()
    for event in await _calendar(db, owner, local_now):
        start = _instant(event.get("starts_at"))
        if (event.get("all_day") or not event.get("location") or start is None
                or not (now < start <= now + timedelta(hours=LOOKAHEAD_HOURS))):
            continue
        live.add(reminder_id(event.get("ref") or ""))
        try:
            result = await plan_event(db, owner, event, now=now, tz=local_now.tzinfo)
        except Exception as exc:
            logger.info("leave plan deferred: %s", type(exc).__name__)
            continue
        out.append({"event": event.get("title"), **result})
    # A moved or cancelled appointment must not leave its notice behind.
    stale = {"user_id": owner, "origin": ORIGIN, "status": "open", "notified_state": {"$exists": False}}
    if live:
        stale["id"] = {"$nin": list(live)}
    await db.reminders.update_many(stale, {"$set": {"status": "cancelled", "updated_at": now.isoformat()}})
    return out
