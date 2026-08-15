"""Epistemic grounding helpers for AI Core."""
from conversation_engine.ai_core.grounding.authority import authority_for_url
from conversation_engine.ai_core.grounding.temporal import (
    apply_current_fact,
    current_facts_as_context,
    get_current_facts,
    merge_context_with_current,
)

__all__ = [
    "authority_for_url",
    "apply_current_fact",
    "current_facts_as_context",
    "get_current_facts",
    "merge_context_with_current",
]
