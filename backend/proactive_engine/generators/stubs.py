"""Predisposed stub generators — Email / Finance / Weather / Health.

These exist so the pipeline can wire future connectors. They MUST return
empty lists and MUST NOT invent weather, finance, email, or health facts.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from proactive_engine.models import SuggestionCandidate
from proactive_engine.types import STUB_ONLY_TYPES

# Explicit registry for tests / docs
STUB_TYPE_STATUS = {
    "emails": "predisposed_only",
    "finance": "predisposed_only",
    "weather": "predisposed_only",
    "health": "predisposed_only",
}


async def generate_stub_candidates(
    db, user_id: str, *, now: Optional[datetime] = None,
) -> List[SuggestionCandidate]:
    """Never emit — predisposed hooks only."""
    _ = (db, user_id, now, STUB_ONLY_TYPES)
    return []


async def generate_email_candidates(db, user_id: str, *, now=None) -> List[SuggestionCandidate]:
    return await generate_stub_candidates(db, user_id, now=now)


async def generate_finance_candidates(db, user_id: str, *, now=None) -> List[SuggestionCandidate]:
    return await generate_stub_candidates(db, user_id, now=now)


async def generate_weather_candidates(db, user_id: str, *, now=None) -> List[SuggestionCandidate]:
    return await generate_stub_candidates(db, user_id, now=now)


async def generate_health_candidates(db, user_id: str, *, now=None) -> List[SuggestionCandidate]:
    return await generate_stub_candidates(db, user_id, now=now)
