"""Context merge with strict precedence — never overwrite confirmed."""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from semantic_engine.models import SOURCE_PRECEDENCE, EntityValue
from semantic_engine.normalizer import normalize_entity


def _rank(source: str) -> int:
    return SOURCE_PRECEDENCE.get(source, 99)


def merge_entity_layers(
    *layers: Optional[Dict[str, Any]],
    timezone: str = "Europe/Rome",
) -> Dict[str, EntityValue]:
    """Merge entity dicts. Each layer is slot → EntityValue | raw.

    Precedence (strongest first):
      1 user_confirmed  2 manual_correction  3 current_input
      4 prior_conversation  5 document  6 calendar
      7 inference/deterministic/gemini  8 default
    """
    out: Dict[str, EntityValue] = {}
    for layer in layers:
        if not layer:
            continue
        for key, val in layer.items():
            if val is None or val == "":
                continue
            ev = normalize_entity(key, val, timezone=timezone)
            if key not in out:
                out[key] = ev
                continue
            existing = out[key]
            # Never overwrite confirmed / manual correction with weaker sources
            if existing.source in ("user_confirmed", "manual_correction") and _rank(ev.source) > _rank(existing.source):
                continue
            if existing.status in ("confirmed", "corrected") and ev.source not in ("user_confirmed", "manual_correction"):
                continue
            if _rank(ev.source) < _rank(existing.source):
                out[key] = ev
            elif _rank(ev.source) == _rank(existing.source) and ev.confidence > existing.confidence:
                out[key] = ev
    return out


def apply_confirmation(
    entities: Dict[str, EntityValue],
    slot: str,
    value: Any,
    *,
    timezone: str = "Europe/Rome",
) -> Dict[str, EntityValue]:
    ev = normalize_entity(slot, value, timezone=timezone)
    ev.source = "user_confirmed"
    ev.status = "confirmed"
    ev.confidence = max(ev.confidence, 0.99)
    out = dict(entities)
    out[slot] = ev
    return out


def apply_correction(
    entities: Dict[str, EntityValue],
    slot: str,
    value: Any,
    *,
    timezone: str = "Europe/Rome",
) -> Dict[str, EntityValue]:
    ev = normalize_entity(slot, value, timezone=timezone)
    ev.source = "manual_correction"
    ev.status = "corrected"
    ev.confidence = max(ev.confidence, 0.99)
    out = dict(entities)
    out[slot] = ev
    return out


def layer_from_raw(
    raw: Optional[Dict[str, Any]],
    *,
    source: str,
    timezone: str = "Europe/Rome",
) -> Dict[str, EntityValue]:
    if not raw:
        return {}
    out: Dict[str, EntityValue] = {}
    for k, v in raw.items():
        if v is None or v == "":
            continue
        ev = normalize_entity(k, v, timezone=timezone)
        ev.source = source  # type: ignore[assignment]
        if source == "user_confirmed":
            ev.status = "confirmed"
            ev.confidence = max(ev.confidence, 0.99)
        elif source == "manual_correction":
            ev.status = "corrected"
            ev.confidence = max(ev.confidence, 0.99)
        out[k] = ev
    return out
