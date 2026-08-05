"""Intent Classification Engine — single reusable intent brain for ORA.

Home → Priority → Intent Classification → Intent → Action Engine → Flow

Deterministic rules first; optional LLM enricher never required.
"""
from intent_engine.models import (
    CLASSIFIER_VERSION,
    ClarifyOption,
    IntentEntities,
    IntentResult,
)
from intent_engine.service import IntentEngine, classify_text, get_intent_engine
from intent_engine.mapping import flow_for_intent, home_type_for_intent
from intent_engine.router import router as intent_engine_router

__all__ = [
    "CLASSIFIER_VERSION",
    "ClarifyOption",
    "IntentEntities",
    "IntentResult",
    "IntentEngine",
    "classify_text",
    "get_intent_engine",
    "flow_for_intent",
    "home_type_for_intent",
    "intent_engine_router",
]
