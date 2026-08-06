"""Dedicated Document Reasoner façade.

AI Document Understanding sits AFTER Documents V2 extraction. This module is
the stable import surface for Life Experience / Documents V2 callers; the
implementation lives in ``life_reasoning`` + ``document_context`` +
``document_actions`` + ``document_memory``.
"""
from __future__ import annotations

from documents.intelligence.document_actions import build_document_actions
from documents.intelligence.document_context import assemble_document_context
from documents.intelligence.document_memory import persist_document_understanding
from documents.intelligence.life_reasoning import (
    DOCUMENT_TYPES,
    DocumentReasoning,
    LIFE_REASONING_VERSION,
    PROMPT_VERSION,
    guess_document_type,
    run_life_document_reasoning,
)
from documents.intelligence.versions import (
    ANALYSIS_SCHEMA_VERSION,
    coerce_analysis_revision,
    next_analysis_revision,
)

__all__ = [
    "ANALYSIS_SCHEMA_VERSION",
    "DOCUMENT_TYPES",
    "DocumentReasoning",
    "LIFE_REASONING_VERSION",
    "PROMPT_VERSION",
    "assemble_document_context",
    "build_document_actions",
    "coerce_analysis_revision",
    "guess_document_type",
    "next_analysis_revision",
    "persist_document_understanding",
    "run_life_document_reasoning",
]
