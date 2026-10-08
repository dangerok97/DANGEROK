"""
How long a journey takes, according to somebody who actually knows.

    OBSERVED COMMUTE != LIVE ETA.

Two different claims, and conflating them is the failure this module exists to
prevent. "Di solito ci metti mezz'ora" is a fact about the person's own past
journeys and needs no network. "Con il traffico adesso ce ne vogliono
trentasette" is a fact about a road right now, and nothing in this codebase can
know it without asking a routing service.

So when no provider is configured this returns `unavailable` and says why. It
never falls back to history dressed up as traffic: a person told "ci vogliono
34 minuti" will leave at a time chosen by that number, and being wrong there
costs them a meeting.

The adapter is deliberately blind. It receives two coordinate pairs and a
travel mode. It does not know that one of them is home, that the other is work,
or why anybody is going.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# The provider is a configuration decision, not a code decision. One
# abstraction, with the configured adapter selected for the deployment.
PROVIDER_ENV = "ROUTING_PROVIDER"
KEY_ENV = "ROUTING_API_KEY"

TRAVEL_MODES = ("drive", "walk", "bicycle", "transit")


def configured_provider() -> Optional[str]:
    """Which routing service this deployment has, if any."""
    provider = (os.environ.get(PROVIDER_ENV) or "").strip().lower()
    key = (os.environ.get(KEY_ENV) or "").strip()
    if not provider or not key:
        return None
    return provider


def capabilities() -> Dict[str, Any]:
    """
    What this deployment can actually answer, stated plainly.

    Read by the capability layer so ORA can say "non posso verificare il
    traffico" rather than discovering it mid-sentence.
    """
    provider = configured_provider()
    return {
        "available": provider is not None,
        "provider": provider,
        "live_traffic": provider in {"google_routes", "mapbox"},
        "modes": ["drive", "walk", "bicycle"] if provider == "mapbox" else list(TRAVEL_MODES),
        "why_unavailable": (
            None
            if provider
            else f"nessun servizio di routing configurato ({PROVIDER_ENV}/{KEY_ENV})"
        ),
    }


def _unavailable(
    provider: Optional[str], reason: str, *,
    failure_code: str = "ROUTING_UNAVAILABLE", retryable: bool = False,
) -> Dict[str, Any]:
    """A failed read, with explicit retry safety and no provider response body."""
    return {
        "available": False,
        "provider": provider,
        "why_unavailable": reason,
        "failure_code": failure_code,
        "retryable": retryable is True,
    }


def _http_failure(provider: str, status_code: int) -> Dict[str, Any]:
    return _unavailable(
        provider, f"il servizio ha risposto {status_code}",
        failure_code=f"ROUTING_HTTP_{status_code}",
        retryable=status_code == 429 or 500 <= status_code < 600,
    )


async def get_route(
    *,
    origin: Dict[str, float],
    destination: Dict[str, float],
    travel_mode: str = "drive",
    alternatives: bool = False,
) -> Dict[str, Any]:
    """
    Distance and duration for one journey, from the configured provider.

    Returns `{"available": False, ...}` when there is nothing to ask. That is a
    real answer and callers must treat it as one — there is no silent fallback
    here, because the only fallback available would be a lie about traffic.
    """
    provider = configured_provider()
    if provider is None:
        return {
            **capabilities(), "available": False,
            "failure_code": "ROUTING_NOT_CONFIGURED", "retryable": False,
        }

    mode = travel_mode if travel_mode in TRAVEL_MODES else "drive"
    try:
        if provider == "google_routes":
            return await _google_routes(origin, destination, mode, alternatives=alternatives)
        if provider == "mapbox":
            return await _mapbox_routes(origin, destination, mode, alternatives=alternatives)
        return _unavailable(
            provider, f"provider «{provider}» non ha un adattatore qui",
            failure_code="ROUTING_UNSUPPORTED_PROVIDER",
        )
    except Exception as e:
        # A routing failure is a routing failure, not an ETA of zero.
        import httpx

        logger.info("routing soft-fail: %s", type(e).__name__)
        if isinstance(e, httpx.TimeoutException):
            failure_code, retryable = "ROUTING_TIMEOUT", True
        elif isinstance(e, httpx.NetworkError):
            failure_code, retryable = "ROUTING_NETWORK_ERROR", True
        else:
            failure_code, retryable = "ROUTING_READ_FAILED", False
        return _unavailable(
            provider, "il servizio di routing non ha risposto",
            failure_code=failure_code, retryable=retryable,
        )


_GOOGLE_MODES = {
    "drive": "DRIVE",
    "walk": "WALK",
    "bicycle": "BICYCLE",
    "transit": "TRANSIT",
}


async def _google_routes(
    origin: Dict[str, float], destination: Dict[str, float], mode: str,
    *, alternatives: bool = False,
) -> Dict[str, Any]:
    """
    Google Routes API v2. Traffic-aware for driving, plain otherwise.

    `TRAFFIC_AWARE` is asked for only when driving, because it is what makes
    the answer a live one — and the response says which routing preference was
    used, so the caller can tell the person whether traffic was actually
    considered.
    """
    import httpx

    traffic_aware = mode == "drive"
    payload: Dict[str, Any] = {
        "origin": {"location": {"latLng": {
            "latitude": origin["latitude"], "longitude": origin["longitude"]}}},
        "destination": {"location": {"latLng": {
            "latitude": destination["latitude"], "longitude": destination["longitude"]}}},
        "travelMode": _GOOGLE_MODES[mode],
        "languageCode": "it",
    }
    if traffic_aware:
        payload["routingPreference"] = "TRAFFIC_AWARE"
        if alternatives:
            payload["computeAlternativeRoutes"] = True

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": (os.environ.get(KEY_ENV) or "").strip(),
        "X-Goog-FieldMask": (
            "routes.duration,routes.distanceMeters,routes.staticDuration,"
            "routes.routeLabels,routes.polyline.encodedPolyline"
            + (",routes.legs.steps.navigationInstruction.instructions,"
               "routes.legs.steps.distanceMeters" if traffic_aware and alternatives else "")
        ),
    }
    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.post(
            "https://routes.googleapis.com/directions/v2:computeRoutes",
            headers=headers,
            content=json.dumps(payload),
        )
    if response.status_code != 200:
        return _http_failure("google_routes", response.status_code)

    routes = (response.json() or {}).get("routes") or []
    if not routes:
        return _unavailable(
            "google_routes", "nessun percorso trovato",
            failure_code="ROUTING_NO_ROUTE",
        )

    # Google orders routes by its preference, not necessarily by the shortest
    # duration. Preserve that order while exposing the reason for our choice.
    choices = []
    for item in routes[:3]:
        duration = _seconds(item.get("duration"))
        if duration is None:
            continue
        baseline = _seconds(item.get("staticDuration"))
        choices.append({
            "duration_seconds": duration,
            "distance_meters": item.get("distanceMeters"),
            "delay_seconds": max(0, duration - baseline) if baseline is not None else None,
            "polyline": (item.get("polyline") or {}).get("encodedPolyline") or "",
            "provider_labels": item.get("routeLabels") or [],
            "main_steps": [
                str(step.get("navigationInstruction", {}).get("instructions") or "")[:140]
                for step in sorted(
                    [step for leg in item.get("legs") or [] for step in leg.get("steps") or []],
                    key=lambda step: step.get("distanceMeters") or 0,
                    reverse=True,
                )[:2]
                if step.get("navigationInstruction", {}).get("instructions")
            ] if alternatives and traffic_aware else [],
        })
    if not choices:
        return _unavailable(
            "google_routes", "durate non disponibili",
            failure_code="ROUTING_INVALID_RESPONSE",
        )
    best = min(choices, key=lambda item: item["duration_seconds"])
    return {
        "available": True,
        "provider": "google_routes",
        "travel_mode": mode,
        "distance_meters": best["distance_meters"],
        "duration_seconds": best["duration_seconds"],
        # What it would take with no traffic, when the provider offers it: the
        # gap between the two is the traffic, and saying so is more useful than
        # a single number.
        "duration_without_traffic_seconds": (
            best["duration_seconds"] - best["delay_seconds"]
            if best["delay_seconds"] is not None else None
        ),
        "reflects_current_traffic": traffic_aware,
        "alternatives": choices if alternatives and traffic_aware else [],
    }


def _seconds(value: Optional[str]) -> Optional[int]:
    """Google returns durations as "1234s"."""
    if not value:
        return None
    try:
        return int(str(value).rstrip("s"))
    except ValueError:
        return None


_MAPBOX_PROFILES = {
    "drive": "driving-traffic", "walk": "walking", "bicycle": "cycling",
}
_INCIDENTS_IT = {
    "accident": "Incidente", "congestion": "Coda", "construction": "Lavori",
    "disabled_vehicle": "Veicolo fermo", "lane_restriction": "Corsia limitata",
    "road_closure": "Strada chiusa", "road_hazard": "Pericolo sulla strada",
    "weather": "Condizioni meteo sulla strada", "planned_event": "Evento programmato",
}


def _mapbox_incidents(route: Dict[str, Any]) -> list[Dict[str, str]]:
    """Only incidents on this returned route; do not infer their cause."""
    seen = set()
    result = []
    for leg in route.get("legs") or []:
        for incident in leg.get("incidents") or []:
            if not isinstance(incident, dict):
                continue
            identifier = str(incident.get("id") or "")
            if identifier and identifier in seen:
                continue
            seen.add(identifier)
            kind = str(incident.get("type") or "").lower()
            roads = incident.get("affected_road_names") or []
            road = str(roads[0])[:80] if isinstance(roads, list) and roads else ""
            label = _INCIDENTS_IT.get(kind, "Disagio segnalato")
            result.append({"label": label, "road": road})
            if len(result) >= 3:
                return result
    return result


async def _mapbox_routes(
    origin: Dict[str, float], destination: Dict[str, float], mode: str,
    *, alternatives: bool = False,
) -> Dict[str, Any]:
    """Mapbox Directions v5, one request for the route and its alternatives."""
    import httpx
    import math

    if mode not in _MAPBOX_PROFILES:
        return _unavailable(
            "mapbox", "Mapbox non offre il percorso con i mezzi pubblici",
            failure_code="ROUTING_UNSUPPORTED_MODE",
        )
    coords = []
    for point in (origin, destination):
        lat, lon = float(point["latitude"]), float(point["longitude"])
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            return _unavailable(
                "mapbox", "coordinate non valide",
                failure_code="ROUTING_INVALID_COORDINATES",
            )
        coords.append(f"{lon:.6f},{lat:.6f}")
    profile = _MAPBOX_PROFILES[mode]
    url = f"https://api.mapbox.com/directions/v5/mapbox/{profile}/{';'.join(coords)}"
    params = {
        "access_token": (os.environ.get(KEY_ENV) or "").strip(),
        "alternatives": "true" if alternatives and mode == "drive" else "false",
        "overview": "full", "geometries": "polyline", "language": "it",
    }
    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.get(url, params=params)
    if response.status_code != 200:
        return _http_failure("mapbox", response.status_code)
    data = response.json() or {}
    if data.get("code") != "Ok":
        return _unavailable(
            "mapbox", "nessun percorso verificato",
            failure_code="ROUTING_NO_ROUTE",
        )
    choices = []
    for item in (data.get("routes") or [])[:3]:
        try:
            duration = float(item["duration"])
            distance = float(item["distance"])
            if not all(math.isfinite(x) and x >= 0 for x in (duration, distance)):
                continue
            typical = item.get("duration_typical")
            typical = float(typical) if typical is not None else None
            if typical is not None and not math.isfinite(typical):
                typical = None
        except (TypeError, ValueError, KeyError):
            continue
        choices.append({
            "duration_seconds": round(duration), "distance_meters": round(distance),
            "delay_seconds": max(0, round(duration - typical)) if typical is not None else None,
            "delay_reference": "tempo tipico" if typical is not None else None,
            "polyline": str(item.get("geometry") or ""),
            "main_steps": [str(leg.get("summary"))[:140] for leg in item.get("legs") or []
                           if leg.get("summary")][:2],
            "incidents": _mapbox_incidents(item) if mode == "drive" else [],
        })
    if not choices:
        return _unavailable(
            "mapbox", "durate non disponibili",
            failure_code="ROUTING_INVALID_RESPONSE",
        )
    best = min(choices, key=lambda item: item["duration_seconds"])
    return {
        "available": True, "provider": "mapbox", "travel_mode": mode,
        "distance_meters": best["distance_meters"],
        "duration_seconds": best["duration_seconds"],
        "reflects_current_traffic": mode == "drive",
        "alternatives": choices if alternatives and mode == "drive" else [],
    }
