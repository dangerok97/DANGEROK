"""Evidence-backed route choices and weather at expected passage times."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List


def decode_polyline(value: str) -> List[tuple[float, float]]:
    """Decode the Routes API's encoded path, with a bound on untrusted input."""
    points: List[tuple[float, float]] = []
    latitude = longitude = index = 0
    value = value[:120000]
    try:
        while index < len(value) and len(points) < 10000:
            coords = []
            for _ in range(2):
                shift = result = 0
                while True:
                    chunk = ord(value[index]) - 63
                    index += 1
                    result |= (chunk & 0x1f) << shift
                    if chunk < 0x20:
                        break
                    shift += 5
                    if shift > 35:
                        return []
                coords.append((result >> 1) ^ -(result & 1))
            latitude += coords[0]
            longitude += coords[1]
            points.append((latitude / 1e5, longitude / 1e5))
    except (IndexError, ValueError):
        return []
    return points


async def weather_along_route(polyline: str, duration_seconds: int) -> List[Dict[str, Any]]:
    """Three points on the actual route, at approximate passage times.

    Weather is a forecast, never a traffic or road incident report. Sampling
    uses point indices as a rough proxy for progress, so the times are marked
    approximate; road segments do not all take the same time to drive.
    """
    from weather import configured_provider

    if configured_provider() != "open_meteo" or duration_seconds <= 0:
        return []
    points = decode_polyline(polyline)
    if len(points) < 2:
        return []
    import httpx

    positions = [("Partenza", 0), ("Lungo il tragitto", len(points) // 2),
                 ("Arrivo", len(points) - 1)]
    coords = [points[index] for _, index in positions]
    params = {
        "latitude": ",".join(str(p[0]) for p in coords),
        "longitude": ",".join(str(p[1]) for p in coords),
        "hourly": "precipitation_probability,weather_code,temperature_2m",
        "timezone": "UTC",
        "forecast_days": 2,
    }
    try:
        async with httpx.AsyncClient(timeout=7.0) as client:
            response = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
            response.raise_for_status()
            forecasts = response.json()
    except Exception:
        return []
    if not isinstance(forecasts, list) or len(forecasts) != 3:
        return []

    now = datetime.now(timezone.utc)
    result = []
    from weather import _WMO, COME_SI_DICE

    for i, (label, _) in enumerate(positions):
        hourly = forecasts[i].get("hourly") or {}
        times = hourly.get("time") or []
        target = now + timedelta(seconds=duration_seconds * i / 2)
        try:
            chosen = min(range(len(times)), key=lambda j: abs(
                datetime.fromisoformat(times[j]).replace(tzinfo=timezone.utc) - target
            ))
            if abs(datetime.fromisoformat(times[chosen]).replace(tzinfo=timezone.utc) - target) > timedelta(hours=2):
                continue
            code = int(hourly["weather_code"][chosen])
            chance = hourly["precipitation_probability"][chosen]
            temperature = hourly["temperature_2m"][chosen]
            condition = _WMO.get(code)
            if condition is None or chance is None or temperature is None:
                continue
            result.append({"label": label, "time_utc": times[chosen] + "Z",
                           "condition": COME_SI_DICE[condition],
                           "rain_chance_pct": round(float(chance)),
                           "temperature_c": round(float(temperature))})
        except (KeyError, IndexError, ValueError, TypeError):
            continue
    return result


def route_choices(routes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Only explain a delay when the provider supplied a comparison baseline."""
    valid = [r for r in routes[:3] if r.get("duration_seconds") is not None]
    if not valid:
        return []
    fastest = min(valid, key=lambda item: item["duration_seconds"])
    def slower_reason(route: Dict[str, Any]) -> str:
        seconds = max(0, int(route["duration_seconds"]) - int(fastest["duration_seconds"]))
        minutes = max(1, round(seconds / 60))
        unit = "minuto" if minutes == 1 else "minuti"
        return f"Circa {minutes} {unit} più lento secondo il traffico stimato ora."

    return [{
        "label": f"Percorso {i + 1}",
        "duration_seconds": int(route["duration_seconds"]),
        "distance_meters": route.get("distance_meters"),
        "main_steps": route.get("main_steps") or [],
        "delay_minutes": round(route["delay_seconds"] / 60) if route.get("delay_seconds") is not None else None,
        "delay_reference": route.get("delay_reference") or "senza traffico",
        "incidents": (route.get("incidents") or [])[:3],
        "recommended": route is fastest,
        "reason": (
            "Il più rapido secondo il traffico stimato ora."
            if route is fastest else
            slower_reason(route)
        ),
    } for i, route in enumerate(valid)]


def departure_advice(roads: List[Dict[str, Any]], weather: List[Dict[str, Any]]) -> str:
    """A short recommendation from the same route and forecast shown below it."""
    recommended = next((road for road in roads if road.get("recommended")), None)
    if not recommended:
        return ""
    minutes = max(1, round(recommended["duration_seconds"] / 60))
    steps = [str(step) for step in recommended.get("main_steps") or [] if step]
    via = f" via {', '.join(steps)}" if steps else ""
    result = f"Se parti ora in auto, considera {recommended['label']}{via}: circa {minutes} min."
    others = [road for road in roads if road is not recommended]
    if others:
        next_best = min(others, key=lambda road: road["duration_seconds"])
        advantage = max(0, round((next_best["duration_seconds"] - recommended["duration_seconds"]) / 60))
        if advantage >= 2:
            result += f" Risparmi circa {advantage} min rispetto all'alternativa più vicina."
        else:
            result += " Le alternative hanno tempi molto simili."
    if recommended.get("delay_minutes") is not None:
        delay = recommended["delay_minutes"]
        if delay > 0:
            result += f" Il traffico aggiunge circa {delay} min rispetto al {recommended['delay_reference']}."
    wet = [point for point in weather if point.get("rain_chance_pct", 0) >= 50]
    if wet:
        point = wet[0]
        result += f" Possibile pioggia {point['label'].lower()} ({point['rain_chance_pct']}%)."
    return result
