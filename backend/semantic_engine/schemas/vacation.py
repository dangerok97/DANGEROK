"""Vacation shares travel slots (alias flow)."""
from __future__ import annotations

from semantic_engine.schemas.travel import TRAVEL_SCHEMA

VACATION_SCHEMA = TRAVEL_SCHEMA.model_copy(update={"flow": "vacation"})
