"""Flow definition helpers."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from action_engine.models import AnswerOption, QuestionTurn


def opt(oid: str, label: str, value: Any = None) -> AnswerOption:
    return AnswerOption(id=oid, label=label, value=value if value is not None else oid)


def turn(
    tid: str,
    question: str,
    *,
    explanation: Optional[str] = None,
    options: Optional[Sequence[AnswerOption]] = None,
    input_kind: str = "chips",
    allow_skip: bool = False,
    required: bool = True,
    brain_key: Optional[str] = None,
) -> QuestionTurn:
    return QuestionTurn(
        id=tid,
        question=question,
        explanation=explanation,
        options=list(options or []),
        input_kind=input_kind,  # type: ignore[arg-type]
        allow_skip=allow_skip,
        required=required,
        brain_key=brain_key,
    )


def resolve_category(item_type: Optional[str], source_type: Optional[str] = None) -> str:
    t = (item_type or "").lower()
    st = (source_type or "").lower()
    if t == "study" or st in ("study", "quiz_session"):
        return "study"
    if t == "event" or st in ("event_candidate", "google_calendar", "internal_calendar"):
        return "event"
    if t == "travel":
        return "travel"
    if t in ("visit", "medical"):
        return "medical"
    if t in ("bill", "payment", "admin") or st == "admin":
        return "admin"
    if t in ("needs_review", "verify") and st in ("document", "document_action"):
        return "admin"
    return "generic"


def next_unanswered(turns: List[QuestionTurn], answers: Dict[str, Any]) -> Optional[QuestionTurn]:
    for t in turns:
        if t.id not in answers:
            return t
    return None
