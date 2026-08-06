"""Entity normalization — dates, amounts, places, transport codes."""
from __future__ import annotations

from typing import Any, Dict, Optional

from semantic_engine.dates import parse_relative_single, parse_range_it, DEFAULT_TZ
from semantic_engine.models import EntityValue


def normalize_entity(name: str, value: Any, *, timezone: str = DEFAULT_TZ) -> EntityValue:
    """Normalize a raw slot value into EntityValue."""
    if isinstance(value, EntityValue):
        return value
    if isinstance(value, dict) and {"normalized", "confidence"} <= set(value.keys()) | {"raw"}:
        try:
            return EntityValue(**{k: v for k, v in value.items() if k in EntityValue.model_fields})
        except Exception:
            pass

    raw = value
    if name in ("departure_date", "return_date", "exam_date", "appointment_date", "due_date", "event_date", "date"):
        if isinstance(value, dict) and value.get("start_date"):
            return EntityValue(
                raw=value, normalized=value.get("start_date") if name != "return_date" else value.get("end_date"),
                confidence=0.9, status="known", source="current_input", timezone=timezone,
            )
        parsed = parse_range_it(str(value), tz_name=timezone) or {}
        single = parse_relative_single(str(value), tz_name=timezone)
        if name == "return_date":
            d = parsed.get("return_date") or parsed.get("end_date")
            if d:
                return EntityValue(raw=raw, normalized=d, confidence=0.9, status="known", source="current_input", timezone=timezone)
        d = parsed.get("departure_date") or parsed.get("start_date") or (single or {}).get("date")
        if d:
            status = "ambiguous" if (single or {}).get("status") == "ambiguous" else "known"
            return EntityValue(
                raw=raw, normalized=d, confidence=0.45 if status == "ambiguous" else 0.9,
                status=status, source="current_input", timezone=timezone,
                ambiguity=(single or {}).get("ambiguity"),
            )
        # ISO passthrough
        s = str(value).strip()
        if len(s) >= 10 and s[4] == "-":
            return EntityValue(raw=raw, normalized=s[:10], confidence=0.99, status="known", source="current_input", timezone=timezone)

    if name == "period" and isinstance(value, dict):
        return EntityValue(raw=value, normalized=value, confidence=0.95, status="known", source="current_input", timezone=timezone)

    if name == "amount":
        try:
            if isinstance(value, (int, float)):
                return EntityValue(raw=raw, normalized=float(value), confidence=0.95, status="known", source="current_input", label=f"€ {float(value):.2f}")
            s = str(value).replace("€", "").replace("euro", "").strip().replace(",", ".")
            return EntityValue(raw=raw, normalized=float(s), confidence=0.9, status="known", source="current_input", label=f"€ {float(s):.2f}")
        except Exception:
            return EntityValue(raw=raw, normalized=value, confidence=0.5, status="low_confidence", source="current_input")

    if name == "transport":
        mapping = {"auto": "car", "macchina": "car", "treno": "train", "aereo": "plane", "car": "car", "train": "train", "plane": "plane"}
        key = str(value).lower().strip()
        return EntityValue(raw=raw, normalized=mapping.get(key, key), confidence=0.9, status="known", source="current_input")

    return EntityValue(
        raw=raw,
        normalized=value if not isinstance(value, str) else value.strip(),
        confidence=0.85,
        status="known",
        source="current_input",
        label=str(value) if value is not None else None,
    )


def entities_to_known_slots(entities: Dict[str, EntityValue], *, min_confidence: float = 0.60) -> Dict[str, Any]:
    known: Dict[str, Any] = {}
    for k, ev in entities.items():
        if ev.status in ("confirmed", "corrected") or (
            ev.confidence >= min_confidence and ev.status not in ("ambiguous", "missing", "low_confidence")
        ):
            known[k] = ev.normalized if ev.normalized is not None else ev.raw
    # Convenience period for AE when both dates present
    if "departure_date" in known and "return_date" in known and "period" not in known:
        known["period"] = {
            "start_date": str(known["departure_date"])[:10],
            "end_date": str(known["return_date"])[:10],
        }
    return known
