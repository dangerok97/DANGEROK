"""Flow registry — category → turn builder."""
from __future__ import annotations

from typing import Any, Callable, Dict, List

from action_engine.flows import admin, event, generic, medical, study, travel
from action_engine.flows.base import resolve_category
from action_engine.models import QuestionTurn

Builder = Callable[[Dict[str, Any]], List[QuestionTurn]]

REGISTRY: Dict[str, Builder] = {
    "study": study.build_turns,
    "event": event.build_turns,
    "travel": travel.build_turns,
    "medical": medical.build_turns,
    "admin": admin.build_turns,
    "generic": generic.build_turns,
}


def build_flow_turns(category: str, ctx: Dict[str, Any]) -> List[QuestionTurn]:
    builder = REGISTRY.get(category) or REGISTRY["generic"]
    turns = builder(ctx)
    if not turns:
        # Hard guarantee: never open an empty guided flow
        return REGISTRY["generic"](ctx)
    return turns


__all__ = ["REGISTRY", "build_flow_turns", "resolve_category"]
