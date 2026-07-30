"""
Property Envelope + Provenance metadata for the Knowledge Layer.

The public shape stored on disk for every property is:

    {
      "value":            <sanitized primitive|dict|list>,
      "value_type":       "string|number|boolean|date|iso_datetime|object|string_list|object_list",
      "unit":             Optional[str],       # "EUR", "km", "%", ...
      "format":           Optional[str],       # ISO-8601, IBAN masked, ...
      "sensitivity":      "public|personal|sensitive|highly_sensitive",
      "provenance": {
        "source_type":      "user_input|ai_extraction|document|email|calendar|banking|system|migration",
        "source_id":        Optional[str],
        "confidence":       float in [0, 1],
        "verified_by_user": bool,
        "extracted_at":     iso datetime,
        "last_confirmed_at": Optional[iso datetime],
      }
    }

Input is very permissive: callers can pass either a bare value or a partial
envelope; we fill the rest with sensible defaults.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


VALID_SOURCE_TYPES = frozenset({
    "user_input", "ai_extraction", "document", "email",
    "calendar", "banking", "system", "migration",
})

VALID_SENSITIVITY = ("public", "personal", "sensitive", "highly_sensitive")

VALID_VALUE_TYPES = frozenset({
    "string", "number", "boolean", "date", "iso_datetime",
    "object", "string_list", "object_list",
})


def _coerce_value(value: Any, value_type: str) -> Any:
    """Best-effort coercion of `value` to match `value_type`.

    Rules:
      - Never raise; if coercion fails, return the original value untouched.
      - `number`: string with digits → int/float; empty/None → None.
      - `boolean`: recognizable truthy/falsy strings, else bool(value).
      - `string_list`: scalar → [str(scalar)]; list → coerced to strings.
      - `object_list`: scalar → [{"value": scalar}]; list untouched.
      - `object`: scalar → {"value": scalar}; dict untouched.
      - `string`: any → str(value).
      - `date`/`iso_datetime`: pass-through (string expected).
    """
    if value is None:
        return None
    if value_type == "number":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            s = value.strip()
            if s == "":
                return None
            try:
                f = float(s)
                if f != f or f in (float("inf"), float("-inf")):
                    return value
                return int(f) if f.is_integer() else f
            except ValueError:
                return value
        return value
    if value_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            s = value.strip().lower()
            if s in ("true", "1", "yes", "si", "sì", "on"):
                return True
            if s in ("false", "0", "no", "off", ""):
                return False
        return bool(value)
    if value_type == "string":
        return value if isinstance(value, str) else str(value)
    if value_type == "string_list":
        if isinstance(value, list):
            return [x if isinstance(x, str) else str(x) for x in value]
        return [value if isinstance(value, str) else str(value)]
    if value_type == "object_list":
        if isinstance(value, list):
            return [x if isinstance(x, dict) else {"value": x} for x in value]
        return [value if isinstance(value, dict) else {"value": value}]
    if value_type == "object":
        return value if isinstance(value, dict) else {"value": value}
    # date / iso_datetime: leave as-is (already sanitized upstream).
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def infer_value_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        if all(isinstance(x, str) for x in value):
            return "string_list"
        return "object_list"
    return "string"


def default_provenance(source_type: str = "user_input", *, source_id: Optional[str] = None) -> Dict[str, Any]:
    return {
        "source_type": source_type if source_type in VALID_SOURCE_TYPES else "user_input",
        "source_id": source_id,
        "confidence": 1.0 if source_type == "user_input" else 0.5,
        "verified_by_user": source_type == "user_input",
        "extracted_at": _now(),
        "last_confirmed_at": _now() if source_type == "user_input" else None,
    }


def _clamp_confidence(v: Any) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.5
    if f < 0.0:
        return 0.0
    if f > 1.0:
        return 1.0
    return f


def coerce_provenance(raw: Optional[Dict[str, Any]], *, default_source: str = "user_input") -> Dict[str, Any]:
    base = default_provenance(default_source)
    if not raw or not isinstance(raw, dict):
        return base
    out = dict(base)
    st = raw.get("source_type")
    if isinstance(st, str) and st in VALID_SOURCE_TYPES:
        out["source_type"] = st
    if "source_id" in raw:
        sid = raw["source_id"]
        out["source_id"] = str(sid)[:128] if sid is not None else None
    if "confidence" in raw:
        out["confidence"] = _clamp_confidence(raw["confidence"])
    if "verified_by_user" in raw:
        out["verified_by_user"] = bool(raw["verified_by_user"])
    if "extracted_at" in raw and isinstance(raw["extracted_at"], str):
        out["extracted_at"] = raw["extracted_at"][:64]
    if "last_confirmed_at" in raw:
        lca = raw["last_confirmed_at"]
        out["last_confirmed_at"] = lca[:64] if isinstance(lca, str) else None
    return out


# ------------------------------------------------------------------
# envelope
# ------------------------------------------------------------------
ENVELOPE_KEYS = frozenset({"value", "value_type", "unit", "format", "sensitivity", "provenance"})


def is_envelope(raw: Any) -> bool:
    """Heuristic: a dict with a `value` key AND at least one envelope field
    other than `value` is treated as an envelope."""
    if not isinstance(raw, dict):
        return False
    if "value" not in raw:
        return False
    return any(k in raw for k in ("value_type", "unit", "format", "sensitivity", "provenance"))


def build_envelope(
    raw: Any,
    *,
    schema_hint: Optional[Dict[str, Any]] = None,
    default_source: str = "user_input",
    actor_provenance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Turn either a bare value or a partial envelope into a full envelope.

    `schema_hint` is a single schema entry (dict with type/unit/sensitivity),
    used to fill missing fields.
    """
    if is_envelope(raw):
        value = raw.get("value")
        env: Dict[str, Any] = {"value": value}
        # value_type: explicit > schema > inferred
        vt = raw.get("value_type") or (schema_hint or {}).get("type") or infer_value_type(value)
        env["value_type"] = vt if vt in VALID_VALUE_TYPES else "string"
        env["value"] = _coerce_value(value, env["value_type"])
        env["unit"] = raw.get("unit") or (schema_hint or {}).get("unit")
        env["format"] = raw.get("format") or (schema_hint or {}).get("format")
        env["sensitivity"] = raw.get("sensitivity") or (schema_hint or {}).get("sensitivity") or "personal"
        env["provenance"] = coerce_provenance(
            raw.get("provenance") or actor_provenance,
            default_source=default_source,
        )
    else:
        value = raw
        vt = (schema_hint or {}).get("type") or infer_value_type(value)
        vt = vt if vt in VALID_VALUE_TYPES else "string"
        env = {
            "value": _coerce_value(value, vt),
            "value_type": vt,
            "unit": (schema_hint or {}).get("unit"),
            "format": (schema_hint or {}).get("format"),
            "sensitivity": (schema_hint or {}).get("sensitivity") or "personal",
            "provenance": coerce_provenance(actor_provenance, default_source=default_source),
        }
    return env


def merge_envelope_update(existing: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """When merging, `new` fully overrides value/value_type/unit/format/sensitivity,
    but provenance keeps `extracted_at` history-safe by refreshing `last_confirmed_at`
    when the value is unchanged."""
    out = dict(new)
    prov = dict(new.get("provenance") or {})
    if existing and existing.get("value") == new.get("value"):
        # Same value re-declared: bump last_confirmed_at, keep original extracted_at.
        old_prov = existing.get("provenance") or {}
        if old_prov.get("extracted_at"):
            prov["extracted_at"] = old_prov["extracted_at"]
        prov["last_confirmed_at"] = _now()
    out["provenance"] = prov
    return out


# ------------------------------------------------------------------
# extraction helpers for the outside world
# ------------------------------------------------------------------
def value_of(envelope: Any) -> Any:
    """Convenience: return the primitive value from an envelope, or the raw value if
    it's not an envelope. Used by legacy readers."""
    if isinstance(envelope, dict) and "value" in envelope and "value_type" in envelope:
        return envelope["value"]
    return envelope


def project_public(properties: Dict[str, Any], *, hide_sensitive_values: bool = False) -> Dict[str, Any]:
    """Return a copy of properties. If `hide_sensitive_values` is True, replace
    the `.value` of sensitive envelopes with None. Used for future export contexts.
    """
    if not properties:
        return {}
    out: Dict[str, Any] = {}
    for k, v in properties.items():
        if k == "_extra":
            out[k] = v
            continue
        if hide_sensitive_values and isinstance(v, dict) and v.get("sensitivity") in ("sensitive", "highly_sensitive"):
            copy = dict(v)
            copy["value"] = None
            copy["_redacted"] = True
            out[k] = copy
        else:
            out[k] = v
    return out
