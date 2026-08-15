"""Graceful fallback — never resurrect domain wizards."""
from __future__ import annotations

from conversation_engine.ai_core.models import CognitiveDecision, CognitiveTurnResult


PROVIDER_UNAVAILABLE_IT = (
    "In questo momento non riesco a usare il mio motore di ragionamento. "
    "Puoi riprovare tra poco."
)


def provider_unavailable_result(*, session_id: str = "") -> CognitiveTurnResult:
    return CognitiveTurnResult(
        ok=True,
        mode="answer",
        ora_text=PROVIDER_UNAVAILABLE_IT,
        session_id=session_id,
        error="provider_unavailable",
    )


def fallback_decision_after_malformed() -> CognitiveDecision:
    return CognitiveDecision(
        response_mode="answer",
        user_intent_summary="unparsed",
        reasoning_status="enough_information",
        message_to_user=PROVIDER_UNAVAILABLE_IT,
        confidence=0.0,
    )
