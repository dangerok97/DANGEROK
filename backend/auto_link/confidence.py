"""
Confidence combination + ambiguity detection.

Not a machine-learned model — just a transparent, deterministic combiner:
saturating sum bounded to [0, 1].

    combined = 1 - Π_i (1 - contribution_i)

That way individual signals stack multiplicatively without ever exceeding 1,
and there's no opaque "score" — each contribution is inspectable.
"""
from __future__ import annotations

from typing import List

from .types import Candidate, MatchSignal, Thresholds


def combine(signals: List[MatchSignal]) -> float:
    if not signals:
        return 0.0
    prob_not = 1.0
    for s in signals:
        c = max(0.0, min(1.0, float(s.contribution)))
        prob_not *= (1.0 - c)
    return round(1.0 - prob_not, 4)


def apply_confidence(candidates: List[Candidate]) -> None:
    """Mutate the confidence of each candidate in place."""
    for c in candidates:
        c.confidence = combine(c.signals)


def mark_ambiguity(candidates: List[Candidate], thresholds: Thresholds) -> None:
    """If multiple candidates cross the ambiguity floor, mark them all as ambiguous."""
    strong = [c for c in candidates if c.confidence >= thresholds.ambiguity_floor]
    if len(strong) >= 2:
        for c in strong:
            c.ambiguous = True


def can_auto_accept(candidate: Candidate, thresholds: Thresholds) -> bool:
    """True only if:
      - confidence >= auto_accept threshold,
      - at least one signal is `verifiable` (unique identifier or explicit link),
      - candidate is NOT flagged as ambiguous.
    A simple keyword match therefore can never trigger auto-accept.
    """
    if candidate.ambiguous:
        return False
    if candidate.confidence < thresholds.auto_accept:
        return False
    return any(s.verifiable for s in candidate.signals)
