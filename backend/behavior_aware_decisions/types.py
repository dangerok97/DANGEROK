"""Shadow-mode types (iter17)."""
from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

RULE_SET_VERSION = "v1.0"

# Deadline guardrail categories — the shadow delta cannot be negative for these
CRITICAL_CATEGORIES = {"safety", "legal", "health", "financial"}

# Cap configuration
DELTA_MIN_TOTAL = -5.0
DELTA_MAX_TOTAL = 10.0
DELTA_MAX_PER_RULE = 3.0


class ShadowRuleResult(BaseModel):
    rule_id: str
    version: str = RULE_SET_VERSION
    delta: float = 0.0
    applied: bool = False
    reason: str = ""
    confidence: str = "low"  # low|medium|high
    evidence: Dict[str, Any] = Field(default_factory=dict)


class ShadowEvaluation(BaseModel):
    evaluation_id: str
    user_id: str
    decision_id: str
    effective_score: float
    shadow_priority_delta: float
    shadow_score: float
    confidence: str
    rules_applied: List[ShadowRuleResult] = Field(default_factory=list)
    rules_evaluated: List[ShadowRuleResult] = Field(default_factory=list)
    ranking_applied: bool = False
    behavior_profile_version: str = "v1.0"
    decision_version: Optional[str] = None
    rule_set_version: str = RULE_SET_VERSION
    context_hash: Optional[str] = None
    created_at: datetime
    duration_ms: float = 0.0
    cap_hit: bool = False
