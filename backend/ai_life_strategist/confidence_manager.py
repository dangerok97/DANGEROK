"""Confidence manager — track trust in domain facts and plans."""
from __future__ import annotations

from typing import Any, Dict, Optional


def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))


def source_confidence(source: str) -> float:
    s = (source or "").lower()
    table = {
        "user_confirmed": 0.95,
        "document_extract": 0.88,
        "semantic_extract": 0.8,
        "user_said": 0.78,
        "inferred": 0.55,
        "default": 0.4,
        "gemini": 0.72,
        "deterministic_fallback": 0.7,
        "cache": 0.68,
    }
    return table.get(s, 0.5)


def merge_confidence(old: Optional[float], new: float, *, overwrite_confirmed: bool = False) -> float:
    """Never silently overwrite a higher confirmed confidence downward without flag."""
    if old is None:
        return clamp(new)
    if overwrite_confirmed:
        return clamp(new)
    # Confirmed/high stays unless new is clearly stronger
    if old >= 0.9 and new < old:
        return old
    return clamp(max(old * 0.35 + new * 0.65, new if new > old else old * 0.9 + new * 0.1))


def plan_confidence(
    *,
    gap_gain: float,
    domain_coverage: float,
    used_gemini: bool,
    privacy_ok: bool,
) -> float:
    base = 0.55 + 0.3 * gap_gain + 0.1 * domain_coverage
    if used_gemini:
        base += 0.05
    if not privacy_ok:
        base -= 0.2
    return clamp(base)


def domain_confidence_from_objects(objects: Dict[str, Any]) -> float:
    if not objects:
        return 0.0
    confs = []
    for v in objects.values():
        if isinstance(v, dict) and "confidence" in v:
            try:
                confs.append(float(v["confidence"]))
            except (TypeError, ValueError):
                confs.append(0.5)
        else:
            confs.append(0.6)
    return clamp(sum(confs) / len(confs))
