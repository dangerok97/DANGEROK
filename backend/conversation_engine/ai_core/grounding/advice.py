"""Bounded, deterministic grounding guard for live route advice.

This is NOT a general hallucination detector. It only blocks a narrow class
of traffic/departure conclusions that cannot follow from one current ETA.
It never infers a future comparison from an alternate route or a static ETA.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

_TRAFFIC_CLAIMS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"\b(?:traffico|circolazione)(?:\s+\w+){0,3}\s+(?:favorevol\w*|scorrevol\w*|fluid\w*|legger\w*|scarso)\b",
    r"\b(?:per|cos[iì]\s+da)\s+(?:evitare|saltare|schivare)\s+(?:il\s+|le\s+)?(?:traffico|code|ingorghi)\b",
    r"\b(?:evit\w*|riduc\w*)\s+(?:il\s+|le\s+)?(?:traffico|code|ingorghi)\b",
    r"\b(?:parti|partire|partenza|muoversi)\s+(?:ora|adesso|subito)\b.{0,110}\b(?:pi[uù]\s+veloc\w*|meno\s+traffic\w*|risparmi\w*|miglior\w*\s+moment\w*|sfruttare|approfittare)\b",
    r"\b(?:sfruttare|approfittare)\s+(?:del\s+)?tempo\s+di\s+percorrenza\s+attuale\b",
    r"\b(?:convien\w*|consigl\w*)\b.{0,65}\b(?:partire|ora|subito)\b.{0,75}\b(?:traffico|percorrenza|pi[uù]\s+veloce)\b",
    r"\b(?:traffic\s+(?:is\s+)?(?:light|favorable|favourable|free.flowing)|avoid\s+(?:the\s+)?traffic|beat\s+(?:the\s+)?traffic)\b",
))
_DISCLAIMER = re.compile(
    r"\b(?:non\s+(?:posso|possiamo|si\s+pu[oò]|[eè]\s+possibile|ho\s+(?:dati|un\s+confronto)|"
    r"abbiamo\s+(?:dati|un\s+confronto)|[eè]\s+dimostrato|significa|dimostra)|"
    r"senza\s+(?:un\s+)?(?:confronto|dati)|impossibile\s+(?:dire|stabilire)|"
    r"cannot\s+(?:infer|tell|confirm|say)|not\s+enough\s+(?:data|evidence))\b",
    re.IGNORECASE,
)
_CLAUSE_SPLIT = re.compile(r"\b(?:ma|per[oò]|tuttavia|eppure|however|but)\b", re.IGNORECASE)
_SEGMENTS = re.compile(r"[^\n.!?]+[.!?]?|\n", re.DOTALL)
_SAFE_SENTENCE = (
    "Ho verificato soltanto la durata stimata con il traffico attuale: "
    "non ho confrontato orari di partenza diversi e non posso stabilire "
    "se partire ora sia più conveniente per il traffico."
)


def _payload(observation: Any) -> dict:
    if isinstance(observation, dict):
        payload = observation.get("payload")
    else:
        payload = getattr(observation, "payload", None)
    return payload if isinstance(payload, dict) else {}


def _name(observation: Any) -> str:
    if isinstance(observation, dict):
        return str(observation.get("capability") or observation.get("name") or "")
    return str(getattr(observation, "name", "") or "")


def has_current_route(observations: Iterable[Any]) -> bool:
    return any(
        _name(item) == "get_route"
        and _payload(item).get("status") == "ok"
        and _payload(item).get("reflects_current_traffic") is True
        and isinstance(_payload(item).get("duration_seconds"), (int, float))
        for item in observations
    )


def has_dated_departure_comparison(observations: Iterable[Any]) -> bool:
    """Only a separately verified multi-departure result can ground such advice."""
    for item in observations:
        payload = _payload(item)
        comparison = payload.get("departure_time_comparison")
        if not isinstance(comparison, dict) or comparison.get("verified") is not True:
            continue
        alternatives = comparison.get("departures")
        if not isinstance(alternatives, list):
            continue
        times = {
            str(row.get("departure_at") or "")
            for row in alternatives if isinstance(row, dict)
            and row.get("source") and row.get("estimated_seconds")
            and row.get("departure_at")
        }
        if len(times) >= 2:
            return True
    return False


def unsupported_traffic_claims(text: str, observations: Iterable[Any]) -> list[str]:
    """Return stable finding codes; no private text enters logs/traces."""
    observed = list(observations)
    if not has_current_route(observed) or has_dated_departure_comparison(observed):
        return []
    for sentence in _SEGMENTS.findall(str(text or "")):
        for clause in _CLAUSE_SPLIT.split(sentence):
            if _DISCLAIMER.search(clause):
                continue
            if any(pattern.search(clause) for pattern in _TRAFFIC_CLAIMS):
                return ["UNSUPPORTED_TRAFFIC_COMPARISON"]
    return []


def guard_route_advice(text: str, observations: Iterable[Any]) -> tuple[str, list[str]]:
    """Replace unsupported assertions BEFORE the reply is persisted or shown."""
    observed = list(observations)
    if not has_current_route(observed) or has_dated_departure_comparison(observed):
        return str(text or ""), []
    changed = False
    output = []
    for sentence in _SEGMENTS.findall(str(text or "")):
        if sentence == "\n":
            output.append(sentence)
            continue
        parts = _CLAUSE_SPLIT.split(sentence)
        violation = any(
            not _DISCLAIMER.search(part) and any(p.search(part) for p in _TRAFFIC_CLAIMS)
            for part in parts
        )
        if not violation:
            output.append(sentence)
            continue
        changed = True
        # Retain indentation but not a model assertion that was not verified.
        whitespace = re.match(r"^\s*", sentence).group(0)
        output.append(whitespace + _SAFE_SENTENCE)
    return "".join(output), (["UNSUPPORTED_TRAFFIC_COMPARISON"] if changed else [])
