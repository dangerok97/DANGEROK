"""Live weather capability for the conversational AI.

The AI decides why weather matters. This module only reads current/local
conditions and returns bounded facts. It contains no domain rules.
"""

from __future__ import annotations

from typing import Any, Dict

from conversation_engine.ai_core.models import Observation


def _fail(code: str, detail: str = "") -> Observation:
    return Observation(
        kind="tool",
        name="get_weather_forecast",
        status="error",
        payload={
            "capability": "get_weather_forecast",
            "status": "error",
            "error": code,
            "detail": detail[:240],
        },
    )


async def get_weather_forecast(
    arguments: Dict[str, Any], runtime: Dict[str, Any]
) -> Observation:
    uid = str(runtime.get("user_id") or "")
    db = runtime.get("db")
    if not uid or db is None:
        return _fail("NOT_CONFIGURED")

    point = None
    place_ref = str(arguments.get("place_ref") or "").strip()
    if place_ref:
        if not place_ref.startswith("place:"):
            return _fail("INVALID_PLACE_REF")
        try:
            from places.service import PlacesService

            place = await PlacesService(db).get_place(
                uid, place_ref.split(":", 1)[1]
            )
            if (
                place is not None
                and place.coordinates is not None
                and place.state != "dismissed"
            ):
                point = (
                    float(place.coordinates.latitude),
                    float(place.coordinates.longitude),
                    str(place.locality or place.label or "").strip(),
                )
        except Exception:
            point = None
        if point is None:
            return _fail(
                "PLACE_UNAVAILABLE",
                "Il luogo indicato non è più disponibile o non ha coordinate.",
            )
    else:
        try:
            from home.service import HomeService

            point = await HomeService(db)._where_they_are(uid)
        except Exception:
            point = None
        if point is None:
            return Observation(
                kind="tool",
                name="get_weather_forecast",
                status="partial",
                payload={
                    "capability": "get_weather_forecast",
                    "status": "location_required",
                    "reason": (
                        "Per leggere il meteo locale serve un luogo confermato "
                        "oppure una posizione corrente autorizzata."
                    ),
                },
            )

    lat, lon, label = point
    try:
        import weather

        data = await weather.forecast_at(lat=lat, lon=lon, place=label)
    except Exception:
        return _fail("WEATHER_READ_FAILED")
    if not data.get("available"):
        return _fail(
            "WEATHER_UNAVAILABLE",
            str(data.get("why_unavailable") or "Meteo non disponibile."),
        )

    hours = []
    for row in list(data.get("hours") or [])[:12]:
        if not isinstance(row, dict):
            continue
        hours.append({
            "time": str(row.get("time") or "")[:5],
            "temperature_c": row.get("temperature_c"),
            "humidity_pct": row.get("humidity_pct"),
            "wind_kmh": row.get("wind_kmh"),
            "rain_chance_pct": row.get("rain_chance_pct"),
        })

    return Observation(
        kind="tool",
        name="get_weather_forecast",
        status="ok",
        payload={
            "capability": "get_weather_forecast",
            "status": "ok",
            "place": str(data.get("place") or label or "")[:120],
            "current": {
                "condition": data.get("condition_label"),
                "temperature_c": data.get("temperature_c"),
                "humidity_pct": data.get("humidity_pct"),
                "wind_kmh": data.get("wind_kmh"),
                "precipitation_mm": data.get("precipitation_mm"),
                # Mechanical fact only: >0 means the provider reports
                # precipitation now. What that means for the user's Situation
                # remains the cognitive model's judgement.
                "precipitation_active": (
                    isinstance(data.get("precipitation_mm"), (int, float))
                    and float(data.get("precipitation_mm")) > 0
                ),
            },
            "near_term": {
                "next_3h_max_rain_chance_pct": (
                    max(
                        [
                            row.get("rain_chance_pct")
                            for row in hours[:3]
                            if isinstance(row.get("rain_chance_pct"), (int, float))
                        ],
                        default=None,
                    )
                ),
            },
            "hours": hours,
            "sunrise": data.get("sunrise"),
            "sunset": data.get("sunset"),
            "why": (
                "Dati live letti dal provider meteo configurato. "
                "Usali per la decisione attuale; non trattarli come certi per il futuro."
            ),
        },
        provenance=[place_ref] if place_ref else [],
    )
