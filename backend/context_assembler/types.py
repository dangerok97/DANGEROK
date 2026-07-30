"""Canonical types + constants for the Context Assembler."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


ASSEMBLER_VERSION = "context_assembler/v1.0"

# Reliability order (higher = more reliable). Used to break duplicate ties.
SOURCE_RELIABILITY = {
    "user_verified":    100,
    "verifiable_id":     90,
    "official":          80,
    "document":          70,
    "system_derived":    50,
    "keyword":           30,
    "unknown":            0,
}

# Data minimization: per decision.category, which node types are relevant.
# Anything outside these types is excluded from the snapshot by default.
CATEGORY_ALLOWED_NODE_TYPES: Dict[str, frozenset] = {
    "bill":          frozenset({"home", "car", "subscription", "contract", "finance"}),
    "subscription":  frozenset({"subscription", "contract", "finance"}),
    "communication": frozenset({"person"}),
    "travel":        frozenset({"trip", "car", "event"}),
    "travel_prep":   frozenset({"trip", "event"}),
    "health":        frozenset({"health", "person"}),
    "fitness":       frozenset({"health"}),
    "exam":          frozenset({"university"}),
    "study":         frozenset({"university"}),
    "work_deadline": frozenset({"job"}),
    "purchase":      frozenset({"purchase", "finance"}),
    "insight":       frozenset({"finance", "home", "car"}),
    "generic":       frozenset({"generic"}),
}


class Freshness(str, Enum):
    FRESH = "fresh"
    AGING = "aging"
    STALE = "stale"
    UNKNOWN = "unknown"


@dataclass
class Signal:
    """A single fact/observation about the context."""
    key: str
    value: Any
    value_type: str
    source_module: str          # decision | linked_nodes | knowledge | graph | auto_link | system
    source_id: Optional[str] = None
    unit: Optional[str] = None
    confidence: float = 1.0
    verified: bool = False
    sensitivity: str = "personal"  # public | personal | sensitive | highly_sensitive
    observed_at: Optional[str] = None
    expires_at: Optional[str] = None
    freshness: str = "unknown"
    reliability_tier: str = "system_derived"  # from SOURCE_RELIABILITY

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "value_type": self.value_type,
            "unit": self.unit,
            "source_module": self.source_module,
            "source_id": self.source_id,
            "confidence": self.confidence,
            "verified": self.verified,
            "sensitivity": self.sensitivity,
            "observed_at": self.observed_at,
            "expires_at": self.expires_at,
            "freshness": self.freshness,
            "reliability_tier": self.reliability_tier,
        }


@dataclass
class ContextConflict:
    """Two signals share a key but disagree on the value. Kept as-is."""
    key: str
    signals: List[Signal]
    detected_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "signals": [s.to_dict() for s in self.signals],
            "detected_at": self.detected_at,
        }


@dataclass
class ProviderResult:
    """What a provider returns. Provider errors are captured, not raised."""
    name: str
    signals: List[Signal] = field(default_factory=list)
    linked_node_ids: List[str] = field(default_factory=list)
    knowledge_versions: Dict[str, int] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    duration_ms: float = 0.0
    error: Optional[str] = None
