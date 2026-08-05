"""Intent (+ subtype) → Action Engine flow / Home type. Registry keyed by intent."""
from __future__ import annotations

from typing import Optional

from intent_engine.models import IntentResult

# Action Engine flow keys
FLOW_BY_INTENT = {
    "study": "study",
    "travel": "travel",
    "event": "event",
    "medical": "medical",
    "payment": "admin",
    "financial": "admin",
    "administrative": "admin",
    "document_review": "admin",
    "task": "generic",
    "communication": "generic",
    "shopping": "generic",
    "project": "generic",
    "generic": "generic",
}

HOME_TYPE_BY_INTENT = {
    "study": "study",
    "travel": "travel",
    "event": "event",
    "medical": "visit",
    "payment": "bill",
    "financial": "payment",
    "administrative": "generic",
    "document_review": "needs_review",
    "task": "activity",
    "communication": "reply",
    "shopping": "activity",
    "project": "activity",
    "generic": "generic",
}

DECISION_CATEGORY_BY_INTENT = {
    "study": "study",
    "travel": "travel",
    "event": "event",
    "medical": "medical",
    "payment": "bill",
    "financial": "bill",
    "administrative": "generic",
    "document_review": "generic",
    "task": "generic",
    "communication": "generic",
    "shopping": "generic",
    "project": "generic",
    "generic": "generic",
}


def flow_for_intent(intent: str, subtype: Optional[str] = None) -> str:
    """Map Intent → Action Engine flow. Subtype may refine later; currently intent-keyed."""
    _ = subtype  # reserved (e.g. exam_preparation still uses study flow)
    return FLOW_BY_INTENT.get(intent, "generic")


def home_type_for_intent(intent: str) -> str:
    return HOME_TYPE_BY_INTENT.get(intent, "generic")


def decision_category_for_intent(intent: str) -> str:
    return DECISION_CATEGORY_BY_INTENT.get(intent, "generic")


def flow_from_result(result: IntentResult) -> str:
    if result.needs_clarify:
        return "clarify"
    return flow_for_intent(result.intent, result.subtype)
