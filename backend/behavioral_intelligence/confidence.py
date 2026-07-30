"""Confidence classifier — deterministic, based on sample size only."""
from __future__ import annotations

from .types import Confidence


def classify(sample_size: int, *, low_thr: int = 5, med_thr: int = 20, high_thr: int = 60) -> Confidence:
    """Return a confidence bucket from a sample size.

    Defaults are conservative:
    * <5 → low
    * 5..19 → low
    * 20..59 → medium
    * ≥60 → high
    """
    if sample_size < low_thr:
        return Confidence.LOW
    if sample_size < med_thr:
        return Confidence.LOW
    if sample_size < high_thr:
        return Confidence.MEDIUM
    return Confidence.HIGH


def aggregate(*confidences: Confidence) -> Confidence:
    """Return the *minimum* confidence across inputs (safe combining)."""
    order = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}
    if not confidences:
        return Confidence.LOW
    return min(confidences, key=lambda c: order[c])
