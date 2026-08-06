"""Declarative flow slot schemas for Gap Analyzer."""
from __future__ import annotations

from typing import Dict, Optional

from semantic_engine.schemas.base import FlowSlotSchema
from semantic_engine.schemas.administrative import ADMINISTRATIVE_SCHEMA
from semantic_engine.schemas.document_review import DOCUMENT_REVIEW_SCHEMA
from semantic_engine.schemas.event import EVENT_SCHEMA
from semantic_engine.schemas.exam_preparation import EXAM_PREPARATION_SCHEMA
from semantic_engine.schemas.generic import GENERIC_SCHEMA
from semantic_engine.schemas.medical import MEDICAL_SCHEMA
from semantic_engine.schemas.payment import PAYMENT_SCHEMA
from semantic_engine.schemas.study import STUDY_SCHEMA
from semantic_engine.schemas.travel import TRAVEL_SCHEMA
from semantic_engine.schemas.vacation import VACATION_SCHEMA

SCHEMAS: Dict[str, FlowSlotSchema] = {
    "study": STUDY_SCHEMA,
    "exam_preparation": EXAM_PREPARATION_SCHEMA,
    "travel": TRAVEL_SCHEMA,
    "vacation": VACATION_SCHEMA,
    "event": EVENT_SCHEMA,
    "medical": MEDICAL_SCHEMA,
    "payment": PAYMENT_SCHEMA,
    "administrative": ADMINISTRATIVE_SCHEMA,
    "document_review": DOCUMENT_REVIEW_SCHEMA,
    "generic": GENERIC_SCHEMA,
}

# Intent → schema flow key
INTENT_TO_FLOW = {
    "study": "study",
    "exam_preparation": "exam_preparation",
    "travel": "travel",
    "vacation": "vacation",
    "event": "event",
    "medical": "medical",
    "payment": "payment",
    "administrative": "administrative",
    "document_review": "document_review",
    "document": "document_review",
    "generic": "generic",
    "clarify": "generic",
}


def schema_for(flow_or_intent: Optional[str]) -> FlowSlotSchema:
    if not flow_or_intent:
        return GENERIC_SCHEMA
    key = INTENT_TO_FLOW.get(flow_or_intent, flow_or_intent)
    return SCHEMAS.get(key) or GENERIC_SCHEMA


__all__ = ["SCHEMAS", "schema_for", "INTENT_TO_FLOW", "FlowSlotSchema"]
