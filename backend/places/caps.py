"""
Capabilities for places and getting to them.

Every one of these is semantically blind. `list_life_places` returns names and
roles; it does not know which of them matters today. `open_navigation` builds a
link; it does not decide that somebody should leave now. Whether a place is
worth mentioning, and whether the person actually wants to be taken there, is
reasoning — and reasoning is not a tool call.
"""

from __future__ import annotations

from typing import Any, Dict

from conversation_engine.ai_core.models import Observation


def _fail(name: str, code: str, detail: str = "") -> Observation:
    return Observation(
        kind="tool",
        name=name,
        status="error",
        payload={
            "capability": name,
            "status": "error",
            "error": code,
            "detail": detail[:200],
            "memory_eligible": False,
        },
    )


def _ok(name: str, payload: Dict[str, Any], uid: str, status: str = "ok") -> Observation:
    return Observation(
        kind="tool",
        name=name,
        status=status,
        payload={"capability": name, "status": "ok", **payload},
        provenance=[f"places:{uid[:8]}"],
    )


def _service(runtime: Dict[str, Any]):
    from places.service import PlacesService

    return PlacesService(runtime["db"])


async def list_life_places(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    uid = runtime.get("user_id") or ""
    if not uid or runtime.get("db") is None:
        return _fail("list_life_places", "NOT_CONFIGURED")
    places = await _service(runtime).list_places(uid)
    return _ok(
        "list_life_places",
        {
            "places": [p.for_ai() for p in places],
            "count": len(places),
        },
        uid,
    )


async def get_life_place(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    """
    Find the place somebody meant by what they called it.

    Ambiguity comes back as ambiguity. A destination picked from several
    near-matches is how a person ends up somewhere they did not ask for.
    """
    uid = runtime.get("user_id") or ""
    if not uid or runtime.get("db") is None:
        return _fail("get_life_place", "NOT_CONFIGURED")

    spoken = str(arguments.get("name") or arguments.get("place") or "").strip()
    resolution = await _service(runtime).resolve_destination(uid, spoken)
    if resolution.resolved and resolution.place:
        return _ok(
            "get_life_place",
            {"resolved": True, "place": resolution.place.for_ai()},
            uid,
        )
    return _ok(
        "get_life_place",
        {
            "resolved": False,
            "why": resolution.reason,
            "options": [p.for_ai() for p in resolution.candidates],
        },
        uid,
    )


async def save_life_place(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    """
    Remember a place, with the name the person gave it.

    A role is only written when the person's own words carried one. This
    capability cannot decide that somewhere is home.
    """
    uid = runtime.get("user_id") or ""
    if not uid or runtime.get("db") is None:
        return _fail("save_life_place", "NOT_CONFIGURED")

    label = str(arguments.get("label") or arguments.get("name") or "").strip()
    if not label:
        return _fail("save_life_place", "NO_LABEL", "un luogo ha bisogno di un nome")

    from places.models import Coordinates

    coordinates = None
    lat, lon = arguments.get("latitude"), arguments.get("longitude")
    if lat is not None and lon is not None:
        try:
            coordinates = Coordinates(
                latitude=float(lat),
                longitude=float(lon),
                accuracy_meters=arguments.get("accuracy_meters"),
                precision="exact",
            )
        except (TypeError, ValueError):
            return _fail("save_life_place", "BAD_COORDINATES")

    place = await _service(runtime).save_place(
        uid,
        label=label,
        role=str(arguments.get("role") or "other"),
        coordinates=coordinates,
        address=str(arguments.get("address") or ""),
        locality=str(arguments.get("locality") or ""),
        source=str(arguments.get("source") or "user_stated"),
    )
    return _ok("save_life_place", {"place": place.for_ai()}, uid)


async def record_location_observation(
    arguments: Dict[str, Any], runtime: Dict[str, Any]
) -> Observation:
    """File a sighting. Evidence, never a fact about anybody's life."""
    uid = runtime.get("user_id") or ""
    if not uid or runtime.get("db") is None:
        return _fail("record_location_observation", "NOT_CONFIGURED")
    try:
        latitude = float(arguments["latitude"])
        longitude = float(arguments["longitude"])
    except (KeyError, TypeError, ValueError):
        return _fail("record_location_observation", "BAD_COORDINATES")

    result = await _service(runtime).record_observation(
        uid,
        latitude=latitude,
        longitude=longitude,
        accuracy_meters=arguments.get("accuracy_meters"),
        dwell_seconds=arguments.get("dwell_seconds"),
    )
    return _ok("record_location_observation", result, uid)


async def open_navigation(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    """
    Everything needed to start navigating, or the question of which app.

    ORA works out where. The app the person already trusts does the driving.
    """
    uid = runtime.get("user_id") or ""
    if not uid or runtime.get("db") is None:
        return _fail("open_navigation", "NOT_CONFIGURED")

    service = _service(runtime)
    spoken = str(arguments.get("destination") or arguments.get("name") or "").strip()
    resolution = await service.resolve_destination(uid, spoken)
    if not resolution.resolved or resolution.place is None:
        return _ok(
            "open_navigation",
            {
                "ready": False,
                "why": resolution.reason,
                "options": [p.for_ai() for p in resolution.candidates],
            },
            uid,
            status="needs_client",
        )

    place = resolution.place
    if place.coordinates is None:
        return _ok(
            "open_navigation",
            {
                "ready": False,
                "why": f"so dov'è «{place.label}» come nome, ma non ho le coordinate",
                "place": place.for_ai(),
            },
            uid,
            status="needs_client",
        )

    from places.navigation import handoff

    origin = None
    try:
        from location.service import LocationService

        presence = await LocationService(runtime["db"]).build_presence(uid)
        if presence and presence.latitude is not None and presence.longitude is not None:
            origin = {"latitude": presence.latitude, "longitude": presence.longitude}
    except Exception:
        origin = None

    plan = handoff(
        latitude=place.coordinates.latitude,
        longitude=place.coordinates.longitude,
        label=place.label,
        origin=origin,
        mode=str(arguments.get("mode") or "driving"),
        preferred_app=await _preferred_app(runtime["db"], uid),
        platform=str(runtime.get("platform") or "web"),
    )

    # How long it will take, when there is a service that knows and a position
    # to start from. Somebody about to leave wants the number in the same
    # breath as the button, not after a second question — and it is a live
    # number here, so it may be spoken as one.
    journey = None
    if origin is not None:
        from places import routing

        route = await routing.get_route(
            origin=origin,
            destination=place.coordinates.precise(),
            travel_mode=_travel_mode(arguments.get("mode")),
        )
        if route.get("available"):
            journey = {
                "duration_seconds": route.get("duration_seconds"),
                "distance_meters": route.get("distance_meters"),
                "reflects_current_traffic": route.get("reflects_current_traffic"),
                "is_live": True,
            }

    return _ok(
        "open_navigation",
        {
            "ready": True,
            "place": place.for_ai(),
            "has_origin": origin is not None,
            "route": journey,
            **plan,
        },
        uid,
        status="needs_client",
    )


def _travel_mode(mode) -> str:
    """The navigation vocabulary and the routing vocabulary, reconciled."""
    return {
        "driving": "drive", "walking": "walk",
        "transit": "transit", "cycling": "bicycle",
    }.get(str(mode or "driving"), "drive")


async def _preferred_app(db, user_id: str):
    """The navigation app this person already chose, if they chose one."""
    try:
        doc = await db.user_settings.find_one(
            {"user_id": user_id}, {"_id": 0, "navigation_app": 1}
        )
        return (doc or {}).get("navigation_app")
    except Exception:
        return None


async def get_current_place(arguments, runtime) -> Observation:
    """
    Which of their own places they are in right now, if any.

    Call this before asking somebody where they are. A question ORA can answer
    from what it already holds is a question it should not be asking.
    """
    uid = runtime.get("user_id") or ""
    if not uid or runtime.get("db") is None:
        return _fail("get_current_place", "NOT_CONFIGURED")
    return _ok("get_current_place", await _service(runtime).where_now(uid), uid)


async def get_time_at_place(arguments, runtime) -> Observation:
    """
    Time spent somewhere over a period, with the visits behind the total.

    `still_there` is part of the answer, not decoration: "sei stato a casa sei
    ore" and "finora oggi sei stato a casa sei ore" are different sentences and
    only one of them is true at a time.
    """
    uid = runtime.get("user_id") or ""
    if not uid or runtime.get("db") is None:
        return _fail("get_time_at_place", "NOT_CONFIGURED")

    service = _service(runtime)
    name = str(arguments.get("place") or arguments.get("name") or "").strip()
    resolution = await service.resolve_destination(uid, name)
    if not resolution.resolved or resolution.place is None:
        return _ok(
            "get_time_at_place",
            {
                "resolved": False,
                "why": resolution.reason,
                "options": [p.for_ai() for p in resolution.candidates],
            },
            uid,
        )
    result = await service.time_at(
        uid, resolution.place.id, period=str(arguments.get("period") or "this_week")
    )
    return _ok("get_time_at_place", {"resolved": True, **result}, uid)


async def get_journeys_between_places(arguments, runtime) -> Observation:
    """
    How long their own trips between two places actually took.

    Observed, not routed. This is the answer to "quanto ci metto normalmente",
    and it says nothing whatsoever about the traffic right now — the payload
    carries `is_live_traffic: false` so that distinction cannot be lost on the
    way to a sentence.
    """
    uid = runtime.get("user_id") or ""
    if not uid or runtime.get("db") is None:
        return _fail("get_journeys_between_places", "NOT_CONFIGURED")

    service = _service(runtime)

    async def resolve(name):
        if not name:
            return None
        found = await service.resolve_destination(uid, str(name).strip())
        return found.place.id if found.resolved and found.place else None

    from_id = await resolve(arguments.get("from"))
    to_id = await resolve(arguments.get("to"))
    result = await service.journeys_between(
        uid,
        from_place_id=from_id,
        to_place_id=to_id,
        period=str(arguments.get("period") or "last_30_days"),
    )
    return _ok(
        "get_journeys_between_places",
        {
            **result,
            "is_live_traffic": False,
            "means": "durate osservate dei suoi spostamenti, non traffico attuale",
        },
        uid,
    )


async def get_day_patterns(arguments, runtime) -> Observation:
    """
    The shape of their days: places, order, times, journeys.

    Evidence, handed over whole. Nothing here says a pattern is a routine; that
    reading is yours, and it still has to be worth saying out loud.
    """
    uid = runtime.get("user_id") or ""
    if not uid or runtime.get("db") is None:
        return _fail("get_day_patterns", "NOT_CONFIGURED")
    result = await _service(runtime).routine_evidence(
        uid, period=str(arguments.get("period") or "last_30_days")
    )
    return _ok("get_day_patterns", result, uid)


async def get_route(arguments, runtime) -> Observation:
    """
    A live journey time from a routing service, or an honest refusal.

    When no provider is configured this returns available=false. Do not fill
    the gap with their usual commute: somebody who leaves at a time chosen by a
    number you invented misses the thing they were going to.
    """
    uid = runtime.get("user_id") or ""
    if not uid or runtime.get("db") is None:
        return _fail("get_route", "NOT_CONFIGURED")

    from places import routing

    service = _service(runtime)
    name = str(arguments.get("destination") or arguments.get("to") or "").strip()
    resolution = await service.resolve_destination(uid, name)
    if not resolution.resolved or resolution.place is None or resolution.place.coordinates is None:
        return _ok(
            "get_route",
            {
                "available": False,
                "why_unavailable": resolution.reason or "destinazione senza coordinate",
                "options": [p.for_ai() for p in resolution.candidates],
            },
            uid,
        )

    origin = None
    try:
        from location.service import LocationService

        presence = await LocationService(runtime["db"]).build_presence(uid)
        if presence and presence.latitude is not None and presence.longitude is not None:
            origin = {"latitude": presence.latitude, "longitude": presence.longitude}
    except Exception:
        origin = None
    if origin is None:
        return _ok(
            "get_route",
            {
                "available": False,
                "why_unavailable": "non so dove si trova adesso",
                **routing.capabilities(),
            },
            uid,
            status="needs_client",
        )

    result = await routing.get_route(
        origin=origin,
        destination=resolution.place.coordinates.precise(),
        travel_mode=str(arguments.get("travel_mode") or "drive"),
    )
    return _ok("get_route", {"destination": resolution.place.label, **result}, uid)
