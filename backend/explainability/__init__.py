"""ORA Explainability Layer — deterministic decision explanations.

No LLM. No randomness. Every explanation is a pure function of:
  - the Decision doc,
  - the latest ContextSnapshot for that decision (if any),
  - today's DailySummary (if enabled/available),
  - the Life Graph nodes linked to the decision.
"""
from .service import ExplanationService
from .types import (
    DECISION_EXPLANATION_VERSION,
    AppliedRule,
    DataSource,
    DecisionExplanation,
)

__all__ = [
    "DECISION_EXPLANATION_VERSION",
    "AppliedRule",
    "DataSource",
    "DecisionExplanation",
    "ExplanationService",
]
