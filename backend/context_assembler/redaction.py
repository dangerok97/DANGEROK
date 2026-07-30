"""Redaction helpers. Nothing sensitive leaves this module in plain text."""
from __future__ import annotations

from typing import Any


HIGHLY_SENSITIVE_KEYS = frozenset({
    "password", "token", "pin", "secret",
    "card_number", "cvv", "iban_full", "medications", "blood_type",
})


def is_highly_sensitive_key(key: str) -> bool:
    k = (key or "").lower()
    if k in HIGHLY_SENSITIVE_KEYS:
        return True
    for suf in ("_password", "_token", "_pin", "_secret", "_cvv"):
        if k.endswith(suf):
            return True
    return False


def redact_for_hash(value: Any, sensitivity: str) -> Any:
    """Return a canonical, safe representation for hashing/logging."""
    if sensitivity in ("sensitive", "highly_sensitive"):
        return "<redacted>"
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [redact_for_hash(v, sensitivity) for v in value[:20]]
    if isinstance(value, dict):
        return {k: redact_for_hash(v, sensitivity) for k, v in list(value.items())[:20]}
    return str(type(value).__name__)


def safe_display(value: Any, sensitivity: str, max_len: int = 48) -> str:
    if sensitivity in ("sensitive", "highly_sensitive"):
        return "<redacted>"
    s = str(value) if value is not None else ""
    return s[:max_len]
