"""Readable, source-bounded fallback for malformed route/weather model messages."""
from __future__ import annotations

import math
import re

from conversation_engine.ai_core.grounding.advice import _name, _payload


def _finite(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def normalize_route_weather_reply(text, observations):
    """Only intervene when a model leaked a serialized object into a trip reply."""
    value = str(text or "")
    if not value.lstrip().startswith(("{'summary':", '{"summary":', "{'details':", '{"details":')):
        return value, []
    rows = list(observations)
    route = next((_payload(row) for row in reversed(rows) if _name(row) == "get_route"
                  and _payload(row).get("status") == "ok"), {})
    weather = next((_payload(row) for row in reversed(rows) if _name(row) == "get_weather_forecast"
                    and _payload(row).get("status") == "ok"), {})
    if not route and not weather:
        return value, []
    seconds = route.get("duration_seconds")
    if not _finite(seconds) or seconds < 0 or not isinstance(weather.get("current"), dict):
        return "Non riesco a presentare un riepilogo verificato del percorso e del meteo.", [
            "STRUCTURED_MESSAGE_UNUSABLE"
        ]
    dest = re.sub(r"[\r\n]+", " ", str(route.get("destination") or "la destinazione"))[:100]
    minutes = round(seconds / 60)
    parts = [
        f"Per {dest} il percorso dura circa {minutes} minuti secondo la stima con il traffico attuale.",
        "Non ho confrontato altri orari di partenza: non posso indicare il momento migliore per il traffico.",
    ]
    if _finite(route.get("distance_meters")):
        parts[0] = parts[0][:-1] + (
            f", per circa {route['distance_meters'] / 1000:.1f} km."
        ).replace(".", ",", 1)
    current = weather["current"]
    condition = str(current.get("condition") or "condizioni non specificate")[:60]
    temperature = current.get("temperature_c")
    summary = f"Il meteo osservato dal provider indica {condition.lower()}"
    if _finite(temperature):
        summary += f" e {temperature:g} °C"
    parts.append(summary + ".")
    hours = [h for h in (weather.get("hours") or []) if isinstance(h, dict)]
    if hours and _finite(hours[0].get("rain_chance_pct")):
        parts.append(
            "La prima previsione oraria disponibile segnala probabilità di pioggia "
            f"del {hours[0]['rain_chance_pct']:g}%: non è una misura dell'intensità."
        )
    return " ".join(parts), ["STRUCTURED_MESSAGE_RENDERED_FROM_EVIDENCE"]
