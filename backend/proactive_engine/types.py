"""Suggestion type taxonomy.

Real generators (emit grounded candidates): study, travel, calendar, documents, projects, life, generic.
Predisposed stubs (never invent content): finance, emails, weather, health.
"""
from __future__ import annotations

from typing import FrozenSet, Literal

SuggestionType = Literal[
    "study",
    "travel",
    "finance",
    "calendar",
    "documents",
    "health",
    "projects",
    "emails",
    "weather",
    "life",
    "generic",
]

ALL_TYPES: FrozenSet[str] = frozenset({
    "study", "travel", "finance", "calendar", "documents", "health",
    "projects", "emails", "weather", "life", "generic",
})

# Types that may emit from real data today.
ACTIVE_GENERATOR_TYPES: FrozenSet[str] = frozenset({
    "study", "travel", "calendar", "documents", "projects", "life", "generic",
})

# Predisposed only — generators must return empty; never fabricate facts.
STUB_ONLY_TYPES: FrozenSet[str] = frozenset({
    "finance", "emails", "weather", "health",
})

PriorityLevel = Literal["low", "medium", "high", "critical"]
SuggestionStatus = Literal[
    "candidate", "active", "snoozed", "dismissed", "accepted", "completed", "expired",
]
