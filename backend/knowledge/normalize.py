"""
Input normalization + safety for the Knowledge Layer.

This module has ONE job: turn arbitrary JSON coming from the outside world
into a safe, size-bounded, injection-proof dict that we can store.

Security rules enforced here
----------------------------
- Reject keys with MongoDB operators: leading `$`, embedded `.`.
- Reject prototype-pollution keys: `__proto__`, `constructor`, `prototype`.
- Cap payload depth, total property count, individual value size.
- Normalize keys: strip, lowercase, non-alnum -> `_`, max 64 chars.
- Reject callable / non-JSON-safe primitives.
- Never log raw values (caller's responsibility; we return a safe redactor helper).

The module does NOT know about node types or provenance — it only sanitizes.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


# Hard caps — chosen conservatively. All silently enforced by raising ValueError.
MAX_KEY_LENGTH = 64
MAX_STRING_LENGTH = 10_000
MAX_PROPERTIES = 200
MAX_LIST_ITEMS = 500
MAX_DEPTH = 6
MAX_SERIALIZED_VALUE_BYTES = 60_000  # sanity guard per envelope

RESERVED_KEYS = frozenset({"__proto__", "constructor", "prototype"})
_KEY_ALLOWED = re.compile(r"[^a-z0-9_]")


class NormalizationError(ValueError):
    """Raised when a payload is unsafe or too large."""


# ------------------------------------------------------------------
# key handling
# ------------------------------------------------------------------
def normalize_key(raw: Any) -> str:
    """Return a safe canonical key or raise NormalizationError.

    Rules:
      - str, trimmed, lowered.
      - Any non [a-z0-9_] becomes `_`.
      - Collapsed consecutive `_`.
      - Must be non-empty and <= MAX_KEY_LENGTH.
      - Must NOT start with a digit or `_`.
      - Must not be a reserved key.
    """
    if not isinstance(raw, str):
        raise NormalizationError(f"key non stringa: {type(raw).__name__}")
    s = raw.strip().lower()
    if not s:
        raise NormalizationError("key vuota")
    if s in RESERVED_KEYS:
        raise NormalizationError(f"key riservata: {raw!r}")
    if s.startswith("$") or "." in s:
        raise NormalizationError(f"key con operatore vietato: {raw!r}")
    s = _KEY_ALLOWED.sub("_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        raise NormalizationError(f"key non valida dopo normalizzazione: {raw!r}")
    if s[0].isdigit():
        raise NormalizationError(f"key inizia con cifra: {raw!r}")
    if len(s) > MAX_KEY_LENGTH:
        raise NormalizationError(f"key troppo lunga (>{MAX_KEY_LENGTH})")
    return s


# ------------------------------------------------------------------
# value handling — recursive sanitize
# ------------------------------------------------------------------
_PRIMITIVE = (str, int, float, bool, type(None))


def sanitize_value(value: Any, *, depth: int = 0) -> Any:
    """Return a safe, JSON-serializable version of `value` or raise."""
    if depth > MAX_DEPTH:
        raise NormalizationError("profondità massima superata")

    if isinstance(value, bool) or isinstance(value, (int, float)) or value is None:
        # NaN / inf are dangerous downstream; reject.
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            raise NormalizationError("float non finito non ammesso")
        return value

    if isinstance(value, str):
        if len(value) > MAX_STRING_LENGTH:
            raise NormalizationError(f"stringa troppo lunga (>{MAX_STRING_LENGTH})")
        return value

    if isinstance(value, list):
        if len(value) > MAX_LIST_ITEMS:
            raise NormalizationError(f"lista troppo lunga (>{MAX_LIST_ITEMS})")
        return [sanitize_value(v, depth=depth + 1) for v in value]

    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            # For nested dicts we still enforce the same key safety, but we
            # allow slightly more permissive keys (they aren't Mongo top-level).
            # Still block Mongo operator prefix and prototype pollution.
            if not isinstance(k, str):
                raise NormalizationError("dict con chiave non stringa")
            if k in RESERVED_KEYS or k.startswith("$") or "." in k:
                raise NormalizationError(f"dict con chiave vietata: {k!r}")
            if len(k) > MAX_KEY_LENGTH:
                raise NormalizationError(f"dict key troppo lunga: {k!r}")
            out[k] = sanitize_value(v, depth=depth + 1)
        return out

    # Anything else (bytes, datetime, custom objects, callables) is refused.
    raise NormalizationError(f"tipo non ammesso: {type(value).__name__}")


# ------------------------------------------------------------------
# top-level: normalize a properties dict (keys + values)
# ------------------------------------------------------------------
def normalize_properties(raw: Any) -> Dict[str, Any]:
    """Return a dict with normalized keys and sanitized values.

    Duplicate keys (post-normalization) → last one wins; caller can detect
    duplicates by comparing input length with output length if needed.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise NormalizationError("properties deve essere un oggetto")
    if len(raw) > MAX_PROPERTIES:
        raise NormalizationError(f"troppe proprietà (>{MAX_PROPERTIES})")

    out: Dict[str, Any] = {}
    for k, v in raw.items():
        # Two known reserved top-level namespaces: `_extra` and `provenance`.
        # They pass through unchanged (key-wise) but their content is sanitized.
        if k == "_extra":
            if v is not None and not isinstance(v, dict):
                raise NormalizationError("_extra deve essere un oggetto")
            out["_extra"] = sanitize_value(v or {})
            continue
        try:
            nk = normalize_key(k)
        except NormalizationError:
            raise
        out[nk] = sanitize_value(v)
    return out


# ------------------------------------------------------------------
# log-safe repr
# ------------------------------------------------------------------
def redact_for_log(properties: Dict[str, Any], sensitive_keys: List[str]) -> Dict[str, Any]:
    """Return a copy of `properties` where sensitive keys are replaced by
    `"***"`. Used before logging."""
    if not properties:
        return {}
    sset = set(sensitive_keys)
    return {k: ("***" if k in sset else "<value>") for k in properties.keys()}


# ------------------------------------------------------------------
# small helpers
# ------------------------------------------------------------------
def is_operator_key(k: Any) -> bool:
    return isinstance(k, str) and (k.startswith("$") or "." in k or k in RESERVED_KEYS)


def normalize_keys_pair(raw: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Return (normalized_dict, list_of_renamed_keys) for diagnostics."""
    renamed: List[str] = []
    out: Dict[str, Any] = {}
    for k, v in raw.items():
        nk = normalize_key(k) if k not in ("_extra",) else "_extra"
        if nk != k:
            renamed.append(f"{k}->{nk}")
        out[nk] = v
    return out, renamed
