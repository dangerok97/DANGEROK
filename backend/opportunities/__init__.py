"""Opportunity Intelligence — whether anything is worth saying, and what."""
from opportunities.models import (
    Opportunity,
    OpportunityCandidate,
    OpportunityDecision,
    ScanResult,
)
from opportunities.service import OpportunityService

__all__ = [
    "Opportunity",
    "OpportunityCandidate",
    "OpportunityDecision",
    "ScanResult",
    "OpportunityService",
]
