from __future__ import annotations

from semantic_engine.schemas.study import STUDY_SCHEMA

EXAM_PREPARATION_SCHEMA = STUDY_SCHEMA.model_copy(update={"flow": "exam_preparation"})
