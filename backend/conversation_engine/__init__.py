"""ORA Conversation Engine — entry orchestrator (NOT a chatbot).

Pipeline:
  Input → Conversation Engine → Intent → Goal → Action Engine → Projects → Brain → Proactive → Home

Domain logic stays in existing engines; this package only orchestrates sessions.
"""
from conversation_engine.models import ConversationSession, StartBody
from conversation_engine.service import (
    ConversationEngineService,
    conversation_engine_enabled,
)
from conversation_engine.router import router as conversation_engine_router

__all__ = [
    "ConversationSession",
    "StartBody",
    "ConversationEngineService",
    "conversation_engine_enabled",
    "conversation_engine_router",
]
