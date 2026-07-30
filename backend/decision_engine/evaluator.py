"""
DecisionEvaluator — computes the base multi-factor score for a single decision.

This is deliberately conservative and boring: it just weights the numeric
attributes of the decision itself. The *reasoning* (dependencies, dampening,
boosts) is the Reasoner's job and comes on top.

Replace this class with a learned model in the future without touching the
Reasoner or the Service.
"""
from __future__ import annotations

from typing import Any, Dict

DEFAULT_WEIGHTS = {
    "urgency": 2.2,
    "importance": 1.8,
    "risk": 1.4,
    "personal_impact": 1.2,
    "economic_impact": 1.0,
    "time_inverse": 0.6,   # short things bubble up
    "energy_inverse": 0.5,  # low-effort things bubble up
}


class DecisionEvaluator:
    def __init__(self, weights: Dict[str, float] | None = None):
        self.weights = {**DEFAULT_WEIGHTS, **(weights or {})}

    def base_score(self, d: Dict[str, Any]) -> float:
        w = self.weights
        time_inv = max(0.0, 10.0 - min((d.get("time_required_min") or 15) / 15.0, 10.0))
        energy_inv = max(0.0, 10.0 - (d.get("energy") or 3))
        score = (
            (d.get("urgency") or 5) * w["urgency"]
            + (d.get("importance") or 5) * w["importance"]
            + (d.get("risk") or 3) * w["risk"]
            + (d.get("personal_impact") or 5) * w["personal_impact"]
            + (d.get("economic_impact") or 3) * w["economic_impact"]
            + time_inv * w["time_inverse"]
            + energy_inv * w["energy_inverse"]
        )
        return round(score, 2)
