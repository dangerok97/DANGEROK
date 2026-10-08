"""Bounded weather-advice guard: forecast chance is not rainfall intensity."""
from __future__ import annotations

import re

from conversation_engine.ai_core.grounding.advice import _name, _payload, _SEGMENTS

_SEVERITY = re.compile(
    r"(?:pioggia|rovesci|precipitazioni|temporali).{0,85}"
    r"(?:intensit[aà]\s+(?:moderata|crescente|forte|elevata|alta)|"
    r"si\s+intensific\w*|pi[uù]\s+fort\w*|forti|violenti)|"
    r"\bintensit[aà]\s+(?:moderata|crescente|forte)\b",
    re.I,
)
_CAVEAT = re.compile(
    r"\b(?:non\s+(?:indica|significa|dimostra|misura|posso\s+stabilire)|"
    r"non\s+si\s+pu[oò]\s+stabilire|senza\s+(?:dati|misure))\b", re.I,
)
_SAFE = (
    "Le previsioni indicano una probabilità di pioggia, non quanto forte pioverà. "
    "I dati disponibili non permettono di stabilire l'intensità delle prossime precipitazioni."
)


def guard_weather_intensity(text, observations):
    rows = list(observations)
    forecast = next((_payload(r) for r in reversed(rows)
                     if _name(r) == "get_weather_forecast"
                     and _payload(r).get("status") == "ok"), {})
    if not forecast:
        return str(text or ""), []
    hours = [h for h in forecast.get("hours", []) if isinstance(h, dict)]
    if any(h.get("precipitation_mm") is not None or h.get("intensity") for h in hours):
        return str(text or ""), []
    changed, result = False, []
    for section in _SEGMENTS.findall(str(text or "")):
        if _SEVERITY.search(section) and not _CAVEAT.search(section):
            result.append(re.match(r"^\s*", section).group() + _SAFE)
            changed = True
        else:
            result.append(section)
    return "".join(result), (["UNVERIFIED_FORECAST_INTENSITY"] if changed else [])
