"""Canonical dataclasses for DecisionExplanation."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

DECISION_EXPLANATION_VERSION = "explainability/v1.0"


@dataclass
class AppliedRule:
    id: str            # e.g. "imminent_event"
    label: str         # human, e.g. "Evento imminente"
    evidence: List[str] = field(default_factory=list)  # human short bullets
    weight: str = "medium"  # low | medium | high

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DataSource:
    source: str        # ONE of the safe display names (Google Calendar, Life Graph, ...)
    confidence: str    # high | medium | low
    last_updated_at: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DecisionExplanation:
    decision_id: str
    priority_score: Optional[float]
    confidence: str              # high | medium | low
    estimated_duration_minutes: int
    estimated_impact: str        # low | medium | high
    estimated_postpone_risk: str # low | medium | high
    generated_at: str

    human_summary: str
    reasoning_steps: List[str] = field(default_factory=list)
    data_sources: List[Dict[str, Any]] = field(default_factory=list)
    applied_rules: List[Dict[str, Any]] = field(default_factory=list)
    context_used: List[str] = field(default_factory=list)

    version: str = DECISION_EXPLANATION_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
