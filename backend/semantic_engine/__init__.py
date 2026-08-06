"""ORA Semantic Extraction Layer + Gap Analyzer."""
from __future__ import annotations

from semantic_engine.models import (
    EXTRACTION_VERSION,
    EntityValue,
    ExtractionResult,
    GapAnalysisResult,
)
from semantic_engine.service import SemanticEngineService, get_semantic_engine

__all__ = [
    "EXTRACTION_VERSION",
    "EntityValue",
    "ExtractionResult",
    "GapAnalysisResult",
    "SemanticEngineService",
    "get_semantic_engine",
    "is_semantic_engine_enabled",
]


def is_semantic_engine_enabled() -> bool:
    import os
    return (os.environ.get("SEMANTIC_ENGINE_ENABLED") or "1").lower() in ("1", "true", "yes", "on")
