"""Maps deep links + best-effort distance/time (free/public only)."""
from __future__ import annotations

import logging
import math
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from action_engine.travel.models import MapsInfo

logger = logging.getLogger("ora.action_engine.travel.maps")

# Rough average speeds km/h for heuristic duration (not traffic — labeled as estimate)
_SPEED = {"car": 80.0, "train": 100.0, "plane": 700.0, "other": 60.0}


def google_maps_dir_link(origin: str, destination: str, *, travelmode: str = "driving") -> str:
    mode = {
        "car": "driving",
        "train": "transit",
        "plane": "driving",  # airport drive; flight not in Maps dir modes for free deep link
        "other": "driving",
    }.get(travelmode, travelmode if travelmode in ("driving", "transit", "walking") else "driving")
    q = urllib.parse.urlencode({
        "api": "1",
        "origin": origin,
        "destination": destination,
        "travelmode": mode,
    })
    return f"https://www.google.com/maps/dir/?{q}"


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


_NOMINATIM_UA = "ORA-TravelFlow/1.0 (local-dev; contact=dev@ora.local)"


async def _nominatim_geocode(query: str) -> Optional[Tuple[float, float]]:
    """Optional public Nominatim — soft fail, never invents coordinates."""
    if not query or not query.strip():
        return None
    try:
        import httpx

        url = "https://nominatim.openstreetmap.org/search"
        headers = {"User-Agent": _NOMINATIM_UA}
        async with httpx.AsyncClient(timeout=6.0, headers=headers) as client:
            r = await client.get(url, params={"q": query, "format": "json", "limit": 1})
            if r.status_code != 200:
                return None
            data = r.json()
            if not data:
                return None
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        logger.info("geocode unavailable: %s", type(e).__name__)
        return None


async def nominatim_reverse_city(lat: float, lon: float) -> Optional[str]:
    """
    Reverse-geocode to a city/town label only.
    Soft fail — never invents a place. Does not persist coordinates.
    """
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return None
    if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0):
        return None
    try:
        import httpx

        url = "https://nominatim.openstreetmap.org/reverse"
        headers = {"User-Agent": _NOMINATIM_UA}
        params = {
            "lat": lat_f,
            "lon": lon_f,
            "format": "json",
            "zoom": 10,
            "addressdetails": 1,
        }
        async with httpx.AsyncClient(timeout=6.0, headers=headers) as client:
            r = await client.get(url, params=params)
            if r.status_code != 200:
                return None
            data = r.json() or {}
            addr = data.get("address") or {}
            for key in (
                "city",
                "town",
                "village",
                "municipality",
                "city_district",
                "county",
            ):
                val = addr.get(key)
                if val and isinstance(val, str) and val.strip():
                    return val.strip()
            # Fallback: first token of display_name
            display = (data.get("display_name") or "").split(",")[0].strip()
            return display or None
    except Exception as e:
        logger.info("reverse geocode unavailable: %s", type(e).__name__)
        return None


def _suggested_stops_car(distance_km: Optional[float]) -> List[Dict[str, Any]]:
    """Best-effort rest-stop suggestions — labeled, not real POI data."""
    if not distance_km or distance_km < 120:
        return []
    n = max(1, int(distance_km // 180))
    return [
        {
            "label": f"Sosta consigliata ~{i * 180} km",
            "kind": "rest",
            "source": "heuristic",
            "honesty": "Suggerimento generico — non da dati traffico/POI reali.",
        }
        for i in range(1, n + 1)
    ]


def _tolls_note(transport: str, distance_km: Optional[float]) -> Optional[str]:
    if transport != "car" or not distance_km or distance_km < 50:
        return None
    return (
        "Possibili pedaggi in autostrada (Italia) — stima non disponibile senza dati reali; "
        "verifica su Autostrade / Google Maps."
    )


async def build_maps_info(
    *,
    origin: Optional[str],
    destination: Optional[str],
    transport: str = "car",
    allow_network: bool = True,
) -> MapsInfo:
    if not origin or not destination:
        return MapsInfo(
            honesty="Mancano partenza o destinazione — link Maps incompleto.",
            estimate_source="unavailable",
        )
    link = google_maps_dir_link(origin, destination, travelmode=transport)
    distance_km = None
    duration_min = None
    source = "unavailable"
    honesty = "Distanza/tempo non disponibili senza geocoding."

    if allow_network:
        o = await _nominatim_geocode(origin)
        d = await _nominatim_geocode(destination)
        if o and d:
            distance_km = round(_haversine_km(o[0], o[1], d[0], d[1]), 1)
            # Road factor ~1.3 for car/train surface
            factor = 1.0 if transport == "plane" else 1.3
            road_km = distance_km * factor
            speed = _SPEED.get(transport, 60.0)
            duration_min = int((road_km / speed) * 60)
            source = "haversine"
            honesty = (
                "Distanza in linea d'aria (OpenStreetMap Nominatim) × fattore strada; "
                "tempo stimato senza traffico reale."
            )

    dur_label = None
    if duration_min is not None:
        h, m = divmod(duration_min, 60)
        dur_label = f"~{h}h {m}m" if h else f"~{m} min"

    stops = _suggested_stops_car(distance_km) if transport == "car" else []
    return MapsInfo(
        deep_link=link,
        origin=origin,
        destination=destination,
        distance_km=distance_km,
        duration_minutes=duration_min,
        duration_label=dur_label,
        estimate_source=source,
        suggested_stops=stops,
        tolls_note=_tolls_note(transport, distance_km),
        honesty=honesty,
    )


def departure_time_advice(
    *,
    transport: str,
    duration_minutes: Optional[int],
    calendar_busy: Optional[List[dict]] = None,
) -> Dict[str, Any]:
    """Heuristic leave-by advice — honest when traffic data missing."""
    if duration_minutes is None:
        return {
            "status": "unavailable",
            "message": (
                "Non ho una stima affidabile del tempo di viaggio. "
                "Controlla Google Maps il giorno della partenza."
            ),
            "traffic_used": False,
        }
    buffer = {"car": 30, "train": 45, "plane": 120, "other": 30}.get(transport, 30)
    leave_before = duration_minutes + buffer
    h, m = divmod(leave_before, 60)
    leave_label = f"{h}h {m}m" if h else f"{m} min"
    busy_note = None
    if calendar_busy:
        busy_note = (
            f"Ho visto {len(calendar_busy)} impegni nel periodo — "
            "tieni conto di eventuali overlap; non uso traffico live."
        )
    return {
        "status": "estimate",
        "leave_before_minutes": leave_before,
        "leave_before_label": leave_label,
        "buffer_minutes": buffer,
        "message": (
            f"Parti con ~{leave_label} di anticipo rispetto all'orario desiderato "
            f"(viaggio stimato + {buffer} min di margine). Nessun dato traffico live."
        ),
        "traffic_used": False,
        "calendar_note": busy_note,
    }
