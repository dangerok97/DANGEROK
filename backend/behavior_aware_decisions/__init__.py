"""Behavior-Aware Decision Engine — SHADOW MODE (iter17).

Read-only motor that computes a *theoretical* priority delta from the
behavioral profile. Never modifies the real score / ranking / Home.
"""
from .service import BehaviorShadowService  # noqa: F401
from .types import ShadowEvaluation, ShadowRuleResult, RULE_SET_VERSION  # noqa: F401
