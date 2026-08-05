"""Study flow — exam prep conversational plan (delegates to study package)."""
from __future__ import annotations

from typing import Any, Dict, List

from action_engine.models import QuestionTurn
from action_engine.study.flow import build_turns as _build_turns


def build_turns(ctx: Dict[str, Any]) -> List[QuestionTurn]:
    return _build_turns(ctx)
