"""Live weather capability for the conversational AI.

The AI decides why weather matters. This module only reads current/local
conditions and returns bounded facts. It contains no domain rules.
"""

from __future__ import annotations

from typing import Any, Dict
import re

from conversation_engine.ai_core.models import Observation


def _fail(
    code: str, detail: str = "", *, failure_code: str = "",
    retryable: bool = False,
) -> Observation:
    return Observation(
        kind="tool",
        name="get_weather_forecast",
        status="error",
        payload={
            "capability": "get_weather_forecast",
            "status": "error",
            "error": code,
            "detail": detail[:240],
            "failure_code": (failure_code or code)[:100],
            "retryable": retryable is True,
        },
    )


async def _resolve_user_named_locality(arguments: Dict[str, Any], runtime: Dict[str, Any], uid: str, db):
    """Read weather at a person-named locality, not at a guessed device location.

    The model proposes a name, but code verifies that name was actually spoken
    this turn, or is the active owner's explicitly recorded Situation place.
    Google's answer must be unique and resolve to the same locality; this is
    not a source of precise house/street coordinates or a persistent LifePlace.
    """
    label = " ".join(str(arguments.get("place_query") or "").split())
    if not 3 <= len(label) <= 120:
        return None, "PLACE_QUERY_INVALID"
    normalized = label.casefold()
    spoken = " ".join(str(runtime.get("user_message") or "")[:8000].casefold().split())
    user_named = bool(re.search(r"(?<!\w)" + re.escape(normalized) + r"(?!\w)", spoken))
    verified_situation_ref = ""
    sid = str(arguments.get("situation_id") or "").strip()
    if sid:
        # An explicit Situation ID always requires an owned, *current* match.
        # A separate mention of the same town must never legitimise a foreign
        # or retired Situation or lend it somebody else's source evidence.
        try:
            from situations.repository import SituationRepository
            sit = await SituationRepository(db).get(uid, sid)
            matches = bool(
                sit and sit.status in ("active", "changed")
                and " ".join(str(sit.location_label or "").casefold().split()) == normalized
                and any(
                    e.source == "user_conversation"
                    and " ".join(str(e.changes.get("location_label") or "").casefold().split()) == normalized
                    for e in (sit.history or [])
                )
            )
            if not matches:
                return None, "PLACE_QUERY_SITUATION_NOT_CURRENT"
            verified_situation_ref = f"situation:{sid}:revision:{sit.revision}"
            user_named = True
        except Exception:
            return None, "PLACE_QUERY_SITUATION_NOT_CURRENT"
    if not user_named:
        return None, "PLACE_QUERY_NOT_USER_GROUNDED"
    try:
        from places import lookup
        from places.models import Coordinates
        suggestions = await lookup.suggest(label)
        if not suggestions.get("available"):
            return None, "PLACE_LOOKUP_UNAVAILABLE"
        candidates = {
            str(item["place_id"])
            for item in (suggestions.get("suggestions") or [])
            if isinstance(item, dict) and item.get("place_id")
            and normalized in {
                " ".join(str(item.get("primary") or "").casefold().split()),
                " ".join(str(item.get("text") or "").casefold().split()),
            }
        }
        if len(candidates) != 1:
            return None, "PLACE_QUERY_AMBIGUOUS"
        place_id = next(iter(candidates))
        resolved = await lookup.resolve(place_id)
        if (
            not resolved.get("available")
            or str(resolved.get("place_id") or "") != place_id
            or normalized not in {
                " ".join(str(resolved.get("locality") or "").casefold().split()),
                " ".join(str(resolved.get("address") or "").casefold().split()),
            }
        ):
            return None, "PLACE_QUERY_MISMATCH"
        coordinates = Coordinates(
            latitude=resolved["latitude"], longitude=resolved["longitude"],
        )
        return (float(coordinates.latitude), float(coordinates.longitude), label, place_id, verified_situation_ref), None
    except Exception:
        return None, "PLACE_LOOKUP_UNAVAILABLE"


async def get_weather_forecast(
    arguments: Dict[str, Any], runtime: Dict[str, Any]
) -> Observation:
    uid = str(runtime.get("user_id") or "")
    db = runtime.get("db")
    if not uid or db is None:
        return _fail("NOT_CONFIGURED")

    point = None
    named_place_provenance = []
    place_ref = str(arguments.get("place_ref") or "").strip()
    place_query = str(arguments.get("place_query") or "").strip()
    if place_query and place_ref:
        return _fail("AMBIGUOUS_PLACE_INPUT", "Indica un solo luogo, non due luoghi concorrenti.")
    if place_query:
        resolved, error = await _resolve_user_named_locality(arguments, runtime, uid, db)
        if error:
            return Observation(
                kind="tool", name="get_weather_forecast", status="partial",
                payload={
                    "capability": "get_weather_forecast",
                    "status": "location_required",
                    "reason": (
                        "La località indicata non è stata verificata in modo "
                        "univoco dalla richiesta della persona o dal servizio luoghi."
                    ),
                    "failure_code": error,
                },
            )
        point = resolved[:3]
        named_place_provenance = ["google_place:" + resolved[3]]
        if resolved[4]:
            named_place_provenance.append(resolved[4])
    elif place_ref:
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
    elif point is None:
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
    # This external read may take seconds. A formerly authorized Situation
    # might be cancelled, moved, or corrected while Google/forecast are
    # responding. Re-read the precise owner/revision fence before publishing
    # environmental evidence to the cognitive Core. The weather itself may
    # still be valid for that town; it is not valid for the *old Situation*.
    if named_place_provenance and len(named_place_provenance) > 1:
        from situations.repository import SituationRepository

        sid = str(arguments.get("situation_id") or "").strip()
        expected = named_place_provenance[1]
        try:
            current = await SituationRepository(db).get(uid, sid)
            valid = bool(
                current and current.status in ("active", "changed")
                and f"situation:{sid}:revision:{current.revision}" == expected
                and " ".join(str(current.location_label or "").casefold().split())
                    == " ".join(str(place_query).casefold().split())
            )
        except Exception:
            valid = False
        if not valid:
            return Observation(
                kind="tool", name="get_weather_forecast", status="partial",
                payload={
                    "capability": "get_weather_forecast",
                    "status": "source_changed",
                    "failure_code": "PLACE_QUERY_SITUATION_CHANGED",
                    "reason": (
                        "La situazione o il luogo è cambiato mentre leggevo "
                        "il meteo. Occorre rileggere la situazione aggiornata."
                    ),
                },
            )
    if not data.get("available"):
        return _fail(
            "WEATHER_UNAVAILABLE",
            str(data.get("why_unavailable") or "Meteo non disponibile."),
            failure_code=str(data.get("failure_code") or "WEATHER_UNAVAILABLE"),
            retryable=data.get("retryable") is True,
        )

    hours = []
    for row in list(data.get("hours") or [])[:12]:
        if not isinstance(row, dict):
            continue
        hours.append({
            "time": str(row.get("time") or "")[:5],
            "datetime": str(row.get("datetime") or "")[:64] or None,
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
            "provider": str(data.get("provider") or "")[:64] or None,
            "retrieved_at": str(data.get("retrieved_at") or "")[:64] or None,
            "observed_at": str(data.get("observed_at") or "")[:64] or None,
            "timezone": str(data.get("timezone") or "")[:64] or None,
            "utc_offset_seconds": data.get("utc_offset_seconds"),
            "current": {
                "condition": data.get("condition_label"),
                "temperature_c": data.get("temperature_c"),
                "humidity_pct": data.get("humidity_pct"),
                "wind_kmh": data.get("wind_kmh"),
                "precipitation_mm": data.get("precipitation_mm"),
            },
            "hours": hours,
            "sunrise": data.get("sunrise"),
            "sunset": data.get("sunset"),
            "why": (
                "Dati live letti dal provider meteo configurato. "
                "observed_at e hours.datetime sono orari del provider nel fuso indicato; "
                "retrieved_at indica solo quando ORA ha letto la risposta, "
                "non l'aggiornamento dei dati. Se data o fuso mancano non inventarli. "
                "Usali per la decisione attuale; non trattarli come certi per il futuro."
            ),
        },
        provenance=[place_ref] if place_ref else named_place_provenance,
    )
