"""Digital Twin Knowledge Model — internal layer of Life Objects.

Five independent sections per Life Object:
  facts | hypotheses | decisions | goals (link-only) | memory

Hard rules:
- A Fact is NEVER deleted (only superseded / archived / replaced).
- Hypotheses are NEVER treated as Facts; never auto-promoted.
- Gemini = consultant; backend = authority.
"""
from life_objects.knowledge_model.models import (
    KnowledgeDecision,
    KnowledgeFact,
    KnowledgeHypothesis,
    MemoryEvent,
    TimelineGroup,
)
from life_objects.knowledge_model.service import KnowledgeModelService, get_knowledge_service

__all__ = [
    "KnowledgeFact",
    "KnowledgeHypothesis",
    "KnowledgeDecision",
    "MemoryEvent",
    "TimelineGroup",
    "KnowledgeModelService",
    "get_knowledge_service",
]
