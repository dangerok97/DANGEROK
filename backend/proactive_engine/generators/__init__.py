"""Candidate generators — real data only for active types; stubs never invent."""
from __future__ import annotations

from typing import Any, Dict, List

from proactive_engine.generators.calendar import generate_calendar_candidates
from proactive_engine.generators.conversation import generate_conversation_candidates
from proactive_engine.generators.documents import generate_document_candidates
from proactive_engine.generators.study import generate_study_candidates
from proactive_engine.generators.stubs import generate_stub_candidates
from proactive_engine.generators.travel import generate_travel_candidates
from proactive_engine.models import SuggestionCandidate


async def gather_candidates(db, user_id: str, *, now=None) -> List[SuggestionCandidate]:
    out: List[SuggestionCandidate] = []
    out.extend(await generate_study_candidates(db, user_id, now=now))
    out.extend(await generate_travel_candidates(db, user_id, now=now))
    out.extend(await generate_calendar_candidates(db, user_id, now=now))
    out.extend(await generate_document_candidates(db, user_id, now=now))
    out.extend(await generate_conversation_candidates(db, user_id, now=now))
    # Stubs always empty — included so wiring is exercised
    out.extend(await generate_stub_candidates(db, user_id, now=now))
    return out
