"""Adapters — Conversation Engine talks to domain engines only through these."""
from conversation_engine.adapters.action import ActionAdapter
from conversation_engine.adapters.brain import BrainAdapter
from conversation_engine.adapters.calendar import CalendarAdapter
from conversation_engine.adapters.documents import DocumentsAdapter
from conversation_engine.adapters.goal import GoalAdapter
from conversation_engine.adapters.intent import IntentAdapter
from conversation_engine.adapters.maps import MapsAdapter
from conversation_engine.adapters.projects import ProjectsAdapter
from conversation_engine.adapters.stubs import StubOriginAdapter
from conversation_engine.adapters.suggestions import SuggestionsAdapter

__all__ = [
    "IntentAdapter",
    "GoalAdapter",
    "ActionAdapter",
    "ProjectsAdapter",
    "DocumentsAdapter",
    "CalendarAdapter",
    "BrainAdapter",
    "SuggestionsAdapter",
    "MapsAdapter",
    "StubOriginAdapter",
]
