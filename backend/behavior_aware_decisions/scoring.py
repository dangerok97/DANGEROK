"""Confidence gating + cap enforcement (iter17)."""
from __future__ import annotations
from typing import List, Tuple
from .types import ShadowRuleResult, DELTA_MAX_PER_RULE, DELTA_MIN_TOTAL, DELTA_MAX_TOTAL
from .rules import rule_deadline_guardrail, _is_urgent, _is_critical

CONFIDENCE_MULTIPLIER = {"low": 0.0, "medium": 0.5, "high": 1.0}


def apply_confidence(rule_results: List[ShadowRuleResult]) -> List[ShadowRuleResult]:
    """Return a new list with delta scaled by confidence multiplier."""
    scaled = []
    for r in rule_results:
        mult = CONFIDENCE_MULTIPLIER.get(r.confidence, 0.0)
        new_delta = round(r.delta * mult, 3)
        # Deadline guardrail rule has no delta by itself, keep as-is
        new = r.model_copy(update={"delta": new_delta, "applied": r.applied and (new_delta != 0 or r.rule_id == "deadline_guardrail")})
        scaled.append(new)
    return scaled


def clip_per_rule(rule_results: List[ShadowRuleResult]) -> List[ShadowRuleResult]:
    out = []
    for r in rule_results:
        d = max(-DELTA_MAX_PER_RULE, min(DELTA_MAX_PER_RULE, r.delta))
        out.append(r.model_copy(update={"delta": d}))
    return out


def aggregate(
    rule_results: List[ShadowRuleResult],
    decision: dict,
) -> Tuple[float, bool, List[ShadowRuleResult]]:
    """Sum applied deltas, enforce deadline guardrail, enforce global cap.

    Returns (final_delta, cap_hit, applied_rules_final).
    """
    applied = [r for r in rule_results if r.applied and r.delta != 0]
    total = sum(r.delta for r in applied)

    # Deadline guardrail: if urgent/critical, clip negative deltas to 0
    if (_is_urgent(decision) or _is_critical(decision)) and total < 0:
        total = 0.0

    cap_hit = False
    if total > DELTA_MAX_TOTAL:
        total = DELTA_MAX_TOTAL
        cap_hit = True
    elif total < DELTA_MIN_TOTAL:
        # This branch is theoretically unreachable given guardrail + per-rule cap
        total = DELTA_MIN_TOTAL
        cap_hit = True

    return round(total, 3), cap_hit, applied
