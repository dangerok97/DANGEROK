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
# abstraction, one adapter behind it: three adapters for a capability nobody
# has configured yet would be three things to keep working for no one.
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
        "live_traffic": provider in {"google_routes", "here"},
        "modes": list(TRAVEL_MODES),
        "why_unavailable": (
            None
            if provider
            else f"nessun servizio di routing configurato ({PROVIDER_ENV}/{KEY_ENV})"
        ),
    }


async def get_route(
    *,
    origin: Dict[str, float],
    destination: Dict[str, float],
    travel_mode: str = "drive",
) -> Dict[str, Any]:
    """
    Distance and duration for one journey, from the configured provider.

    Returns `{"available": False, ...}` when there is nothing to ask. That is a
    real answer and callers must treat it as one — there is no silent fallback
    here, because the only fallback available would be a lie about traffic.
    """
    provider = configured_provider()
    if provider is None:
        return {"available": False, **capabilities()}

    mode = travel_mode if travel_mode in TRAVEL_MODES else "drive"
    try:
        if provider == "google_routes":
            return await _google_routes(origin, destination, mode)
        return {
            "available": False,
            "provider": provider,
            "why_unavailable": f"provider «{provider}» non ha un adattatore qui",
        }
    except Exception as e:
        # A routing failure is a routing failure, not an ETA of zero.
        logger.info("routing soft-fail: %s", type(e).__name__)
        return {
            "available": False,
            "provider": provider,
            "why_unavailable": "il servizio di routing non ha risposto",
        }


_GOOGLE_MODES = {
    "drive": "DRIVE",
    "walk": "WALK",
    "bicycle": "BICYCLE",
    "transit": "TRANSIT",
}


async def _google_routes(
    origin: Dict[str, float], destination: Dict[str, float], mode: str
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
    }
    if traffic_aware:
        payload["routingPreference"] = "TRAFFIC_AWARE"

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": (os.environ.get(KEY_ENV) or "").strip(),
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.staticDuration",
    }
    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.post(
            "https://routes.googleapis.com/directions/v2:computeRoutes",
            headers=headers,
            content=json.dumps(payload),
        )
    if response.status_code != 200:
        return {
            "available": False,
            "provider": "google_routes",
            "why_unavailable": f"il servizio ha risposto {response.status_code}",
        }

    routes = (response.json() or {}).get("routes") or []
    if not routes:
        return {
            "available": False,
            "provider": "google_routes",
            "why_unavailable": "nessun percorso trovato",
        }

    best = routes[0]
    return {
        "available": True,
        "provider": "google_routes",
        "travel_mode": mode,
        "distance_meters": best.get("distanceMeters"),
        "duration_seconds": _seconds(best.get("duration")),
        # What it would take with no traffic, when the provider offers it: the
        # gap between the two is the traffic, and saying so is more useful than
        # a single number.
        "duration_without_traffic_seconds": _seconds(best.get("staticDuration")),
        "reflects_current_traffic": traffic_aware,
    }


def _seconds(value: Optional[str]) -> Optional[int]:
    """Google returns durations as "1234s"."""
    if not value:
        return None
    try:
        return int(str(value).rstrip("s"))
    except ValueError:
        return None
