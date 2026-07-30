"""
Auto-Link Engine — deterministic Decision ↔ Node link proposer.

This module ONLY proposes and persists link proposals. It does not:
- rank Decisions;
- create Decisions or Nodes;
- modify Knowledge;
- call GPT or external services.

Applying an accepted proposal goes through `LifeGraphService.link_decision`
(the ONLY write it performs to another module's data).
"""
from .types import (
    ProposalStatus,
    MATCHER_VERSION,
    Thresholds,
    CATEGORY_TYPE_COMPAT,
    SIGNAL_TAGS,
)
from .service import AutoLinkService

__all__ = [
    "AutoLinkService",
    "ProposalStatus",
    "MATCHER_VERSION",
    "Thresholds",
    "CATEGORY_TYPE_COMPAT",
    "SIGNAL_TAGS",
]
