"""Travel flow — delegates to travel package (Life Planner slice)."""
from __future__ import annotations

from typing import Any, Dict, List

from action_engine.models import QuestionTurn
from action_engine.travel.flow import build_turns as _build_turns


def build_turns(ctx: Dict[str, Any]) -> List[QuestionTurn]:
    return _build_turns(ctx)
