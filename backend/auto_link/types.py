"""
Canonical types + constants for the Auto-Link Engine.

Kept as plain enums / dicts so we can bump `MATCHER_VERSION` in isolation:
every proposal is stamped with the version that produced it, and old
proposals become `superseded` when the version changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional


MATCHER_VERSION = "auto_link/v1.0"


class ProposalStatus(str, Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


@dataclass(frozen=True)
class Thresholds:
    """Confidence thresholds. Configurable via constructor injection."""
    auto_accept: float = 0.95
    propose: float = 0.70
    diagnostic: float = 0.50
    ambiguity_floor: float = 0.60  # if ≥2 candidates cross this, mark ambiguous


# ------------------------------------------------------------------
# Category ↔ Node type compatibility matrix.
# Contributes a modest confidence bump when they match, never enough alone.
# ------------------------------------------------------------------
CATEGORY_TYPE_COMPAT: Dict[str, FrozenSet[str]] = {
    "bill":          frozenset({"home", "subscription", "contract", "finance"}),
    "subscription":  frozenset({"subscription", "contract", "finance"}),
    "communication": frozenset({"person"}),
    "travel":        frozenset({"trip", "car"}),
    "travel_prep":   frozenset({"trip"}),
    "health":        frozenset({"health", "person"}),
    "fitness":       frozenset({"health"}),
    "exam":          frozenset({"university"}),
    "study":         frozenset({"university"}),
    "work_deadline": frozenset({"job"}),
    "purchase":      frozenset({"purchase", "finance"}),
    "insight":       frozenset({"finance", "home", "car"}),
    "generic":       frozenset({"generic"}),
}


# Canonical machine tags for matching signals (used in matching_signals output).
SIGNAL_TAGS = {
    "EXPLICIT_LINK":        "decision.node_ids includes candidate",
    "EXPLICIT_LINKED_TO":   "decision.linked_to references candidate",
    "VERIFIABLE_PLATE":     "candidate.knowledge.plate matches decision.metadata.plate",
    "VERIFIABLE_CONTRACT":  "candidate.knowledge.contract_id matches decision.metadata.contract_id",
    "VERIFIABLE_DOCUMENT":  "candidate.knowledge.document_id matches decision.metadata.document_id",
    "VERIFIABLE_PROVIDER":  "candidate.knowledge.provider matches decision provider",
    "VERIFIABLE_IBAN":      "candidate.knowledge.iban matches decision iban",
    "CATEGORY_TYPE":        "decision.category compatible with node.type",
    "KNOWLEDGE_PROVIDER":   "knowledge.provider appears in decision text",
    "KNOWLEDGE_PLATE":      "knowledge.plate appears in decision text",
    "KNOWLEDGE_ADDRESS":    "knowledge.address appears in decision text",
    "KNOWLEDGE_NAME":       "knowledge.name appears in decision text",
    "KNOWLEDGE_INSTITUTION":"knowledge.institution appears in decision text",
    "KNOWLEDGE_KEY_MATCH":  "another schema key matches decision text",
    "NODE_LABEL":           "node.label appears in decision text",
    "GRAPH_DIRECT":         "candidate is directly connected to a strong match",
    "GRAPH_PARENT":         "candidate is parent of a strong match",
    "KEYWORD_ONLY":         "only weak keyword association",
}


VERIFIABLE_TAGS: FrozenSet[str] = frozenset({
    "EXPLICIT_LINK",
    "EXPLICIT_LINKED_TO",
    "VERIFIABLE_PLATE",
    "VERIFIABLE_CONTRACT",
    "VERIFIABLE_DOCUMENT",
    "VERIFIABLE_IBAN",
})


# ------------------------------------------------------------------
# Data carriers used inside the engine (never persisted directly).
# ------------------------------------------------------------------
@dataclass
class MatchSignal:
    """One deterministic reason a Decision could relate to a Node."""
    tag: str                 # machine tag (key of SIGNAL_TAGS)
    description: str         # human-readable, safe (no sensitive values)
    contribution: float      # local confidence 0..1
    verifiable: bool = False # true if the signal alone justifies auto-accept


@dataclass
class Candidate:
    """A Node considered for a Decision, with its accumulated signals."""
    node_id: str
    node_type: str
    node_label: str
    signals: List[MatchSignal] = field(default_factory=list)
    confidence: float = 0.0
    ambiguous: bool = False
    # Versioning inputs (for idempotence).
    node_knowledge_version: int = 0
