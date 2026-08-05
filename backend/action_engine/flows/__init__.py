"""Flow registry — Intent (+subtype) → turn builder. NOT home item type strings."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from action_engine.flows import admin, clarify, event, generic, medical, study, travel
from action_engine.models import QuestionTurn
from intent_engine.mapping import flow_for_intent

Builder = Callable[[Dict[str, Any]], List[QuestionTurn]]

# Keyed by Action Engine flow name (derived from Intent via intent_engine.mapping)
REGISTRY: Dict[str, Builder] = {
    "study": study.build_turns,
    "event": event.build_turns,
    "travel": travel.build_turns,
    "medical": medical.build_turns,
    "admin": admin.build_turns,
    "generic": generic.build_turns,
    "clarify": clarify.build_turns,
}


def resolve_flow_from_intent(
    intent: str,
    subtype: Optional[str] = None,
    *,
    needs_clarify: bool = False,
) -> str:
    if needs_clarify:
        return "clarify"
    return flow_for_intent(intent, subtype)


def build_flow_turns(flow: str, ctx: Dict[str, Any]) -> List[QuestionTurn]:
    builder = REGISTRY.get(flow) or REGISTRY["generic"]
    turns = builder(ctx)
    if not turns:
        return REGISTRY["generic"](ctx)
    return turns


# Backward-compatible name used by older imports — delegates to Intent mapping only
# when called with legacy args; prefer resolve_flow_from_intent.
def resolve_category(item_type: Optional[str] = None, source_type: Optional[str] = None) -> str:
    """DEPRECATED for flow choice. Soft hint only — Action Engine must use Intent."""
    from intent_engine import classify_text
    # Without text we cannot classify; return generic (never invent event)
    _ = (item_type, source_type)
    return "generic"


__all__ = [
    "REGISTRY",
    "build_flow_turns",
    "resolve_flow_from_intent",
    "resolve_category",
]
