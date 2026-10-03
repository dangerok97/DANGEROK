"""Calendar departure evidence, refreshed by the existing ambient runtime.

Routes and subtraction are facts. Whether to raise an opportunity or notify
is still decided by Opportunity/Delivery. No destination, mode or current
position is inferred from a person's habits.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone

COLLECTION = "calendar_departure_estimates"
WAKE_SOURCE = "calendar_departures"
MARGIN_MINUTES = 10
LABELS = {"drive": "in auto", "walk": "a piedi", "bicycle": "in bici", "transit": "con i mezzi"}


def _now():
    return datetime.now(timezone.utc)


def _instant(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (TypeError, ValueError):
        return None


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:24]


def event_version(event):
    return _digest({k: event.get(k) for k in ("ref", "title", "starts_at", "ends_at", "location", "all_day")})


def current_origin(presence, now):
    observed = _instant(presence.last_seen_at)
    if (presence.preference == "off" or presence.permission_state != "granted_foreground"
            or presence.source not in ("foreground_device", "background_device")
            or presence.acquisition_error or not observed
            or not -5 <= (now - observed).total_seconds() <= 120
            or presence.accuracy_meters is None or presence.accuracy_meters > 200):
        return None
    lat, lon = presence.latitude, presence.longitude
    if (lat is None or lon is None or not math.isfinite(lat) or not math.isfinite(lon)
            or not -90 <= lat <= 90 or not -180 <= lon <= 180):
        return None
    return {"latitude": lat, "longitude": lon}


def with_timing(evidence, now, clock):
    """Arithmetic for this read, not a model's comparison of UTC/local clocks."""
    from zoneinfo import ZoneInfo

    if evidence.get("status") != "ready":
        return evidence
    zone = ZoneInfo(clock["timezone"])
    options = []
    for option in evidence["options"]:
        leave = _instant(option["leave_at"])
        remaining = math.floor((leave - now).total_seconds())
        options.append({**option, "leave_local": leave.astimezone(zone).isoformat(),
                        "seconds_until_departure": remaining,
                        "full_margin_still_available": remaining >= 0,
                        "estimated_lateness_if_leaving_now_seconds": max(
                            0, -remaining - MARGIN_MINUTES * 60)})
    return {**evidence, "options": options, "timing_as_of": now.astimezone(zone).isoformat(),
            "timezone": clock["timezone"], "timezone_authority": clock["authority"],
            "event_local": _instant(evidence["starts_at"]).astimezone(zone).isoformat()}


class DepartureService:
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self):
        await self.db[COLLECTION].create_index([("owner_id", 1), ("event_ref", 1)], unique=True)
        await self.db[COLLECTION].create_index("expires_at", expireAfterSeconds=0)

    async def collect(self, owner_id, events, *, now=None):
        """Bounded, owner-scoped facts; an unavailable provider never yields an ETA."""
        from location.service import LocationService
        from places import routing

        now = now or _now()
        upcoming = [event for event in events if event.get("location") and not event.get("all_day")
                    and _instant(event.get("starts_at")) and _instant(event["starts_at"]) > now]
        location = LocationService(self.db)
        if await location.get_preference(owner_id) == "off":
            await self._schedule(owner_id, [], now)
            return []
        await self._schedule(owner_id, upcoming, now)
        imminent = [e for e in upcoming if _instant(e["starts_at"]) <= now + timedelta(hours=24)][:2]
        if not imminent:
            return []
        presence = await location.build_presence(owner_id)
        origin = current_origin(presence, now)
        output = []
        for event in imminent:
            base = {"ref": "departure:" + event_version(event), "event_ref": event["ref"],
                    "event_version": event_version(event), "title": event["title"],
                    "starts_at": event["starts_at"], "location": str(event["location"])[:300],
                    "margin_minutes": MARGIN_MINUTES, "mode_selected": False}
            if not origin:
                output.append({**base, "status": "needs_current_location", "options": []})
                continue
            if not routing.capabilities()["available"]:
                output.append({**base, "status": "routing_unavailable", "options": []})
                continue
            # Hash the short-lived fix; don't create another coordinate history.
            origin_key = _digest(origin)
            stored = await self.db[COLLECTION].find_one(
                {"owner_id": owner_id, "event_ref": event["ref"]}, {"_id": 0})
            if (stored and stored.get("origin_key") == origin_key
                    and stored.get("event_version") == base["event_version"]
                    and (stored["evidence"].get("status") != "ready"
                         or (_instant(stored["evidence"].get("valid_until")) or now) > now)
                    and (_instant(stored.get("refresh_after")) or now) > now):
                output.append(stored["evidence"])
                continue
            evidence = await self._estimate(owner_id, event, base, origin, presence, now)
            await self.db[COLLECTION].update_one(
                {"owner_id": owner_id, "event_ref": event["ref"]},
                {"$set": {"event_version": base["event_version"], "origin_key": origin_key,
                          "refresh_after": (now + timedelta(seconds=60)).isoformat(),
                          "expires_at": now + timedelta(hours=2), "evidence": evidence}}, upsert=True)
            output.append(evidence)
        from timezone_service import user_clock_context
        clock = await user_clock_context(self.db, owner_id, now=now)
        return [with_timing(row, now, clock) for row in output]

    async def _estimate(self, owner_id, event, base, origin, presence, now):
        from places import routing, briefing
        from places.public_search import preview_destination
        from places.service import PlacesService

        resolution = await PlacesService(self.db).resolve_destination(owner_id, base["location"])
        if resolution.resolved and resolution.place.coordinates:
            coords = resolution.place.coordinates
            destination = {"latitude": coords.latitude, "longitude": coords.longitude}
        elif (resolution.candidates or resolution.resolved
              or base["location"].strip().casefold() in ("casa", "a casa", "lavoro", "ufficio", "casa mia")):
            destination = None
        else:
            destination = await preview_destination(base["location"], origin)
        if not destination:
            return {**base, "status": "destination_unresolved", "options": []}
        destination = {k: destination[k] for k in ("latitude", "longitude")}
        modes = [m for m in LABELS if m in routing.capabilities()["modes"]]
        routes = await asyncio.gather(*[
            routing.get_route(origin=origin, destination=destination, travel_mode=mode,
                              alternatives=mode == "drive") for mode in modes], return_exceptions=True)
        options = []
        roads, weather = [], []
        for mode, route in zip(modes, routes):
            if not isinstance(route, dict) or not route.get("available"):
                continue
            duration = route.get("duration_seconds")
            if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
                continue
            leave = _instant(event["starts_at"]) - timedelta(seconds=duration, minutes=MARGIN_MINUTES)
            options.append({"mode": mode, "label": LABELS[mode], "duration_minutes": math.ceil(duration / 60),
                            "leave_at": leave.isoformat(), "distance_meters": route.get("distance_meters"),
                            "reflects_current_traffic": bool(route.get("reflects_current_traffic")),
                            "provider": route.get("provider")})
            if mode == "drive":
                alternatives = route.get("alternatives") or []
                roads = briefing.route_choices(alternatives)
                best = min(alternatives, key=lambda r: r.get("duration_seconds", math.inf), default={})
                if best.get("polyline"):
                    weather = await briefing.weather_along_route(best["polyline"], int(duration))
        if not options:
            return {**base, "status": "routing_unavailable", "options": []}
        valid_until = min(_instant(presence.last_seen_at) + timedelta(seconds=120),
                          now + timedelta(seconds=120), _instant(event["starts_at"]))
        return {**base, "status": "ready", "options": options, "road_choices": roads,
                "route_weather": weather, "observed_at": now.isoformat(),
                "valid_until": valid_until.isoformat(), "origin_seen_at": presence.last_seen_at,
                "ref": base["ref"] + ":" + _digest([options, now.isoformat()]),
                "future_traffic_unknown": _instant(event["starts_at"]) > now + timedelta(minutes=90)}

    async def _schedule(self, owner_id, events, now):
        """One bounded ambient review, rearmed durably even if the app is closed."""
        from ambient.repository import AmbientRepository
        from ambient.service import AmbientService

        query = {"owner_id": owner_id, "source_ref": WAKE_SOURCE, "status": "pending"}
        if not events:
            await self.db.ambient_wakes.update_many(query, {"$set": {"status": "cancelled"}})
            return
        first = min(_instant(e["starts_at"]) for e in events)
        # 24h is an observation horizon, not an instruction to interrupt.
        due = max(now + timedelta(minutes=2), first - timedelta(hours=24))
        due = min(due, now + timedelta(hours=72))
        pending = await self.db.ambient_wakes.find_one(query, {"_id": 0}, sort=[("scheduled_for", 1)])
        if pending:
            if (_instant(pending.get("scheduled_for")) or due) > due:
                await AmbientRepository(self.db).reschedule(pending["id"], when=due.isoformat())
            return
        # Stable minute bucket lets the existing unique identity coalesce races.
        due = due.replace(second=0, microsecond=0) + timedelta(minutes=1)
        await AmbientService(self.db).schedule(owner_id, reason="ambient_review", when=due,
                                             source_ref=WAKE_SOURCE, provenance="code_schedule")

    async def evidence_is_current(self, owner_id, opportunity):
        refs = [e.ref for e in opportunity.evidence if e.kind == "departure"]
        if not refs:
            return True
        from location.service import LocationService
        from opportunities.snapshot import _calendar

        now = _now()
        if not _instant(opportunity.valid_until) or _instant(opportunity.valid_until) <= now:
            return False
        presence = await LocationService(self.db).build_presence(owner_id)
        origin = current_origin(presence, now)
        if not origin:
            return False
        events = await _calendar(self.db, owner_id, now)
        versions = {e["ref"]: event_version(e) for e in events}
        origin_key = _digest(origin)
        for ref in refs:
            row = await self.db[COLLECTION].find_one(
                {"owner_id": owner_id, "evidence.ref": ref}, {"_id": 0})
            if (not row or versions.get(row["event_ref"]) != row["event_version"]
                    or row.get("origin_key") != origin_key
                    or (_instant(row["evidence"].get("valid_until")) or now) <= now):
                return False
        return True


def ground_candidate(candidate, evidence, tz_name):
    """After the model chose relevance, pin the claim to actual route arithmetic."""
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(tz_name or "UTC")
    options = evidence["options"]
    def departure_clock(option):
        when = _instant(option["leave_at"]).astimezone(zone)
        clock = f"{when:%H:%M}"
        if when.date() != _instant(evidence["starts_at"]).astimezone(zone).date():
            clock = f"{when:%d/%m} {clock}"
        return f"{option['label']} entro le {clock}"
    clocks = "; ".join(departure_clock(o) for o in options)
    candidate.identity_key = "departure:" + _digest(evidence["event_ref"])
    candidate.semantic_summary = (f"Per «{evidence['title']}» il "
        f"{_instant(evidence['starts_at']).astimezone(zone):%d/%m} alle "
        f"{_instant(evidence['starts_at']).astimezone(zone):%H:%M}: {clocks}.")[:280]
    candidate.why_it_matters = (
        f"Stime per {evidence['location']}, con {MARGIN_MINUTES} minuti di margine. "
        "Il mezzo di trasporto è da scegliere. "
        + ("L'orario è indicativo: il traffico futuro può cambiare. " if evidence["future_traffic_unknown"] else "")
        + "Il percorso va aggiornato prima di partire.")[:600]
    candidate.why_now = f"Percorso verificato alle {_instant(evidence['observed_at']).astimezone(zone):%H:%M}."
    candidate.what_ora_can_do = f"Posso aggiornare il percorso e aprire il navigatore per {evidence['location']}."[:600]
    candidate.initiative = "inform"
    candidate.valid_until = evidence["valid_until"]
    candidate.time_sensitivity = "perishable"
    candidate.requires_clarification = False
    candidate.clarifying_question = ""
    candidate.needs_research = False
    candidate.research_question = ""
