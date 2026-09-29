"""
Capabilities for places and getting to them.

Every one of these is semantically blind. `list_life_places` returns names and
roles; it does not know which of them matters today. `open_navigation` builds a
link; it does not decide that somebody should leave now. Whether a place is
worth mentioning, and whether the person actually wants to be taken there, is
reasoning — and reasoning is not a tool call.
"""

from __future__ import annotations

from typing import Any, Dict, List

import logging

from conversation_engine.ai_core.models import Observation

logger = logging.getLogger("ora.places.caps")


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
        # A named public destination need not already be in the person's Life
        # Places. Maps can resolve it at handoff, without ORA pretending to
        # know its coordinates or current traffic. Keep personal roles and
        # genuinely ambiguous saved names out of this query fallback.
        if (spoken and len(spoken) <= 160
                and spoken.casefold() not in {"casa", "home", "lavoro", "work"}
                and not resolution.reason.startswith("più luoghi")):
            from places.navigation import search_handoff

            preview = await _public_route_preview(
                spoken, runtime, arrival_request=arguments.get("arrival_request")
            )
            return _ok("open_navigation", {
                "ready": True,
                "destination_unverified": True,
                "has_origin": bool(preview),
                "route": preview.get("route") if preview else None,
                "place": {"label": spoken} if preview else None,
                "journey_options": preview.get("journey_options", []) if preview else [],
                "advice": preview.get("advice", "") if preview else "",
                "road_choices": preview.get("road_choices", []) if preview else [],
                "route_weather": preview.get("route_weather", []) if preview else [],
                "route_provider": "mapbox" if preview else None,
                "routing": None if preview else (
                    {"available": False, "why_unavailable":
                     "non ho una posizione attuale e una destinazione univoca da stimare; "
                     "la mappa cercherà il luogo quando la apri"}
                    if _mapbox_enabled() else _routing_note()
                ),
                "say_this": (
                    f"Per «{spoken}» ho trovato {preview['label']} ({preview['context']}). "
                    "Ti mostro i tempi stimati e il traffico. Verifica che sia la destinazione giusta: "
                    "la navigazione partirà dalla posizione del dispositivo e potrà aggiornare la strada."
                    if preview else
                    f"Ti porto verso «{spoken}»: apri Google Maps qui sotto. "
                    "Userà la posizione del dispositivo e mostrerà percorso e traffico aggiornati. "
                    "Controlla che abbia trovato la destinazione giusta."
                ),
                **(preview["handoff"] if preview else search_handoff(spoken, str(arguments.get("mode") or "driving"))),
            }, uid, status="needs_client")
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
        origin = _navigation_origin(presence)
    except Exception:
        origin = None

    plan = handoff(
        latitude=place.coordinates.latitude,
        longitude=place.coordinates.longitude,
        label=place.label,
        # The navigation app uses the device's live fix at tap time. A cached
        # ORA presence can support an estimate but must not pin the start of
        # turn-by-turn guidance to a place the person has since left.
        origin=None,
        mode=str(arguments.get("mode") or "driving"),
        preferred_app=await _preferred_app(runtime["db"], uid),
        platform=str(runtime.get("platform") or "web"),
    )

    # How long it will take, when there is a service that knows and a position
    # to start from. Somebody about to leave wants the number in the same
    # breath as the button, not after a second question — and it is a live
    # number here, so it may be spoken as one.
    journey = None
    scelte: List[Dict[str, Any]] = []
    consiglio = ""
    road_choices: List[Dict[str, Any]] = []
    route_weather: List[Dict[str, Any]] = []
    destination_weather = None
    route_provider = None
    requested_mode = _travel_mode(arguments.get("mode"))
    if origin is not None:
        from places import routing, briefing

        route = await routing.get_route(
            origin=origin,
            destination=place.coordinates.precise(),
            travel_mode=requested_mode,
            alternatives=requested_mode == "drive",
        )
        if route.get("available"):
            route_provider = route.get("provider")
            journey = {
                "duration_seconds": route.get("duration_seconds"),
                "distance_meters": route.get("distance_meters"),
                "reflects_current_traffic": route.get("reflects_current_traffic"),
                "is_live": True,
            }
        #     TRE MODI DI ANDARCI, CONFRONTATI.
        # Non è un elenco di link: è la domanda che si fa una persona che deve
        # uscire. Ogni riga esiste solo se il servizio ha risposto per quel
        # modo — niente tempi inventati, e se non risponde nessuno non c'è
        # nessun confronto da mostrare.
        scelte = await _how_to_get_there(origin, place.coordinates.precise(),
                                        first_route=route, first_mode=requested_mode)
        consiglio, parti_entro = await _when_to_leave(
            runtime["db"], uid, scelte, place, requested_mode,
            arrival_request=arguments.get("arrival_request"),
        )
        if requested_mode == "drive" and route.get("available"):
            raw_alternatives = route.get("alternatives") or []
            road_choices = briefing.route_choices(raw_alternatives)
            best = min(raw_alternatives, key=lambda r: r["duration_seconds"], default=None)
            if best and best.get("polyline"):
                route_weather = await briefing.weather_along_route(
                    best["polyline"], best["duration_seconds"],
                )
    if not route_weather:
        # Current weather at the confirmed destination is useful even without
        # live routing, but must never be described as weather along the road.
        from weather import now_at

        current = await now_at(lat=place.coordinates.latitude,
                               lon=place.coordinates.longitude, place=place.label)
        if current.get("available"):
            destination_weather = {
                "condition": current.get("condition_label"),
                "temperature_c": current.get("temperature_c"),
            }

    return _ok(
        "open_navigation",
        {
            "ready": True,
            "place": place.for_ai(),
            "has_origin": origin is not None,
            "route": journey,
            #     PRIMA IL CONSIGLIO, POI I LINK.
            "journey_options": scelte,
            "advice": consiglio,
            "road_choices": road_choices,
            "route_weather": route_weather,
            "route_provider": route_provider,
            "destination_weather": destination_weather,
            "routing": None if scelte else _routing_note(),
            "say_this": (
                f"Ti porto a «{place.label}»: scegli l'app mappe qui sotto per avviare la navigazione. "
                + (f"{consiglio} " if consiglio else "")
                + (f"A destinazione adesso: {destination_weather['condition'].lower()}, {destination_weather['temperature_c']}°. " if destination_weather else "")
                + ("Il confronto dei percorsi tiene conto del traffico attuale. " if scelte and any(x.get("reflects_current_traffic") for x in scelte) else "L'app mappe mostrerà il traffico aggiornato.")
            ),
            **plan,
        },
        uid,
        status="needs_client",
    )


async def _public_route_preview(name: str, runtime: Dict[str, Any], *, arrival_request=None) -> Dict[str, Any] | None:
    """A temporary coordinate lookup, only with a current origin and exact unique name."""
    from places import briefing, routing
    from places.navigation import navigation_url
    from places.public_search import preview_destination

    if routing.configured_provider() != "mapbox":
        return None
    try:
        from location.service import LocationService

        presence = await LocationService(runtime["db"]).build_presence(runtime["user_id"])
        origin = _navigation_origin(presence)
        if origin is None:
            return None
        destination = await preview_destination(name, origin)
        if not destination:
            return None
        point = {"latitude": destination["latitude"], "longitude": destination["longitude"]}
        route = await routing.get_route(origin=origin, destination=point, alternatives=True)
        if not route.get("available"):
            return None
        choices = await _how_to_get_there(origin, point, first_route=route, first_mode="drive")
        if not choices:
            return None
        alternatives = route.get("alternatives") or []
        best = min(alternatives, key=lambda r: r["duration_seconds"], default=None)
        weather = await briefing.weather_along_route(best["polyline"], best["duration_seconds"]) if best and best.get("polyline") else []
        roads = briefing.route_choices(alternatives)
        advice = briefing.departure_advice(roads, weather)
        # A named public place can also be the location of an imminent
        # appointment; no need to save it in Life Places to give a departure
        # time. Without such an appointment, only say "parti ora" for an
        # explicit navigation command.
        from types import SimpleNamespace

        deadline, _ = await _when_to_leave(
            runtime["db"], runtime["user_id"], choices,
            SimpleNamespace(label=destination["label"], address=destination["context"]),
            arrival_request=arrival_request,
        )
        if deadline:
            advice = deadline
        return {
            "label": destination["label"], "context": destination["context"],
            "route": {"duration_seconds": route["duration_seconds"],
                      "distance_meters": route.get("distance_meters"),
                      "reflects_current_traffic": True, "is_live": True},
            "journey_options": choices,
            "road_choices": roads, "route_weather": weather, "advice": advice,
            "handoff": {"needs_choice": False, "app": "google_maps",
                        "url": navigation_url("google_maps", latitude=point["latitude"],
                                              longitude=point["longitude"]),
                        "destination_label": destination["label"]},
        }
    except Exception as e:
        logger.info("public route preview soft-fail: %s", type(e).__name__)
        return None


def _navigation_origin(presence) -> Dict[str, float] | None:
    """Only a device fix from this departure, never a five-minute-old sighting."""
    from datetime import datetime, timedelta, timezone

    if (not presence or presence.freshness != "CURRENT"
            or presence.latitude is None or presence.longitude is None
            or presence.acquisition_error or presence.source not in ("foreground_device", "background_device")
            or not presence.last_seen_at):
        return None
    try:
        observed = datetime.fromisoformat(presence.last_seen_at.replace("Z", "+00:00"))
        if observed.tzinfo is None:
            return None
        age = datetime.now(timezone.utc) - observed.astimezone(timezone.utc)
        if not timedelta(seconds=-5) <= age <= timedelta(seconds=120):
            return None
    except (ValueError, TypeError):
        return None
    return {"latitude": presence.latitude, "longitude": presence.longitude}


def _mapbox_enabled() -> bool:
    from places.routing import configured_provider

    return configured_provider() == "mapbox"


#     I MODI CHE SI CONFRONTANO, E COME SI CHIAMANO PER CHI LEGGE.
_MODI = (
    ("drive", "In auto", "car-outline"),
    ("transit", "Con i mezzi", "train-outline"),
    ("bicycle", "In bici", "bicycle-outline"),
)


def _routing_note() -> Dict[str, Any]:
    """Perché non c'è un confronto: si dice, non si inventa."""
    from places import routing

    c = routing.capabilities()
    return {
        "available": bool(c.get("available")),
        "why_unavailable": (
            "il servizio per confrontare i percorsi non è ancora attivo; "
            "la mappa mostrerà il traffico quando la apri"
            if not c.get("available") else ""
        ),
    }


async def _how_to_get_there(origin, destination, *, first_route=None, first_mode="drive") -> List[Dict[str, Any]]:
    """
    Quanto ci vuole per ognuno dei modi, da chi lo sa davvero.

    Ogni voce porta anche se il tempo tiene conto del traffico: «22 minuti» con
    il traffico dentro e «22 minuti» senza sono due frasi diverse, e chi legge
    ha diritto di sapere quale sta guardando.
    """
    from places import routing

    fuori: List[Dict[str, Any]] = []
    for modo, etichetta, icona in _MODI:
        r = (first_route if modo == first_mode and first_route is not None
             else await routing.get_route(origin=origin, destination=destination, travel_mode=modo))
        if not r.get("available") or not r.get("duration_seconds"):
            continue
        fuori.append({
            "mode": modo,
            "label": etichetta,
            "icon": icona,
            "duration_seconds": int(r["duration_seconds"]),
            "duration_label": _minuti(int(r["duration_seconds"])),
            "distance_meters": r.get("distance_meters"),
            "reflects_current_traffic": bool(r.get("reflects_current_traffic")),
        })
    if fuori:
        #     IL CONSIGLIO È IL PIÙ VELOCE, E SI DICE PERCHÉ.
        piu_veloce = min(fuori, key=lambda x: x["duration_seconds"])
        for v in fuori:
            v["recommended"] = v is piu_veloce
    return fuori


async def _when_to_leave(db, uid: str, scelte: List[Dict[str, Any]], place,
                         requested_mode="drive", *, arrival_request=None, now_utc=None):
    """
    A che ora conviene partire, solo per un impegno in quel luogo.

    Torna (frase, ora_di_partenza). Senza un impegno o senza un tempo di
    percorrenza non c'è niente da consigliare, e la frase resta vuota: meglio
    nessun consiglio di un consiglio inventato.
    """
    if not scelte:
        return "", ""
    consigliato = next((s for s in scelte if s.get("mode") == requested_mode), None)
    if consigliato is None:
        return "", ""
    try:
        from datetime import datetime, timedelta, timezone
        from agenda.service import AgendaService
        from timezone_service import resolve_user_timezone
        from zoneinfo import ZoneInfo

        now = now_utc or datetime.now(timezone.utc)
        local = ZoneInfo((await resolve_user_timezone(db, uid)).tz_name)
        if isinstance(arrival_request, dict) and arrival_request.get("day") in ("oggi", "domani"):
            from datetime import time

            hour = int(arrival_request["hour"])
            minute = int(arrival_request["minute"])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return "", ""
            local_day = now.astimezone(local).date()
            if arrival_request["day"] == "domani":
                return (
                    f"Per arrivare domani alle {hour:02d}:{minute:02d}, "
                    "i tempi e il traffico qui mostrati sono di adesso: "
                    "non posso indicare ancora un orario di partenza affidabile. "
                    "Ricontrolla il percorso domani prima di uscire."
                ), ""
            target = datetime.combine(local_day, time(hour, minute), tzinfo=local).astimezone(timezone.utc)
            if target <= now:
                return f"L'orario di arrivo delle {hour:02d}:{minute:02d} è già passato oggi.", ""
            partenza = target - timedelta(seconds=consigliato["duration_seconds"], minutes=10)
            if partenza <= now:
                return (
                    f"Per arrivare a «{place.label}» alle {hour:02d}:{minute:02d}, "
                    "parti ora: il tempo di percorso stimato e 10 minuti di margine "
                    "superano l'orario prudente di partenza. Ricontrolla il traffico."
                ), "ora"
            ora = partenza.astimezone(local).strftime("%H:%M")
            if target > now + timedelta(minutes=90):
                return (
                    f"Per arrivare a «{place.label}» alle {hour:02d}:{minute:02d}, "
                    f"la partenza indicativa è alle {ora}: "
                    f"{_minuti(int(consigliato['duration_seconds']))} di percorso {consigliato['label'].lower()} "
                    "e 10 minuti di margine, usando il traffico di adesso. "
                    "Ricontrolla prima di uscire: il traffico futuro può cambiare."
                ), ora
            return (
                f"Per arrivare a «{place.label}» alle {hour:02d}:{minute:02d}, "
                f"parti entro le {ora}: "
                f"{_minuti(int(consigliato['duration_seconds']))} di percorso stimato {consigliato['label'].lower()} "
                "e 10 minuti di margine. Ricontrolla il traffico prima di uscire."
            ), ora
        agenda = await AgendaService(db).days_ahead(uid, days=2)
        matches = []
        for day in agenda.get("days") or []:
            for event in day.get("events") or []:
                if event.get("all_day") or not _event_at_destination(event, place):
                    continue
                try:
                    starts = datetime.fromisoformat(str(event.get("starts_at") or "").replace("Z", "+00:00"))
                    if starts.tzinfo is None:
                        continue
                    starts = starts.astimezone(timezone.utc)
                except (TypeError, ValueError):
                    continue
                # A live traffic estimate is useful for an imminent departure,
                # not as a promise about tomorrow's road conditions.
                if now < starts <= now + timedelta(minutes=90):
                    matches.append((starts, event))
        if not matches:
            return "", ""
        quando, primo = min(matches, key=lambda pair: pair[0])
        margine = timedelta(minutes=10)
        partenza = quando - timedelta(seconds=consigliato["duration_seconds"]) - margine
        titolo = str(primo.get("title") or primo.get("label") or "il tuo impegno")
        if partenza <= now:
            return (
                f"Per «{titolo}» alle {quando.astimezone(local).strftime('%H:%M')}, "
                "parti ora: con il tempo di percorrenza stimato "
                f"{consigliato['label'].lower()} e 10 minuti di margine, "
                "l'orario prudente di partenza è già passato. Ricontrolla il traffico."
            ), "ora"
        return (
            f"Per «{titolo}» alle {quando.astimezone(local).strftime('%H:%M')}, "
            f"parti entro le {partenza.astimezone(local).strftime('%H:%M')}: "
            f"{_minuti(int(consigliato['duration_seconds']))} di percorso stimato {consigliato['label'].lower()} "
            "e 10 minuti di margine. Ricontrolla il traffico prima di uscire."
        ), partenza.astimezone(local).strftime("%H:%M")
    except Exception as e:  # pragma: no cover
        logger.info("consiglio di partenza non calcolato: %s", type(e).__name__)
        return "", ""


def _event_at_destination(event: Dict[str, Any], place) -> bool:
    """An agenda location must actually name the confirmed destination."""
    import re
    import unicodedata

    def words(value):
        normalized = unicodedata.normalize("NFKD", str(value or "").casefold())
        normalized = "".join(c for c in normalized if not unicodedata.combining(c))
        return re.findall(r"[a-z0-9]+", normalized)

    location = words(event.get("location"))
    if not location:
        return False
    for candidate in (place.label, place.address):
        needle = words(candidate)
        if needle and any(location[i:i + len(needle)] == needle for i in range(len(location) - len(needle) + 1)):
            return True
    return False


def _minuti(secondi: int) -> str:
    minuti = max(1, round(secondi / 60))
    if minuti < 60:
        return f"{minuti} min"
    ore, resto = divmod(minuti, 60)
    return f"{ore} h" if not resto else f"{ore} h {resto} min"


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
