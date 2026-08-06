"""Proactive / suggestions adapter — open or resume from suggestion context."""
from __future__ import annotations

from typing import Any, Dict, Optional


class SuggestionsAdapter:
    def __init__(self, db):
        self.db = db

    async def get_suggestion(self, user_id: str, suggestion_id: str) -> Optional[Dict[str, Any]]:
        doc = await self.db.proactive_suggestions.find_one(
            {"id": suggestion_id, "user_id": user_id},
            {"_id": 0},
        )
        return doc

    @staticmethod
    def conversational_context(suggestion: Dict[str, Any]) -> Dict[str, Any]:
        """Extract context for Conversation Engine start/resume — no domain inventing."""
        action = suggestion.get("action") or {}
        return {
            "suggestion_id": suggestion.get("id"),
            "type": suggestion.get("type"),
            "title": suggestion.get("title"),
            "description": suggestion.get("description"),
            "goal_id": suggestion.get("goal_id"),
            "project_id": suggestion.get("project_id") or suggestion.get("travel_project_id"),
            "study_plan_id": suggestion.get("study_plan_id"),
            "travel_project_id": suggestion.get("travel_project_id"),
            "route": action.get("route"),
            "kind": action.get("kind"),
            "params": action.get("params") or {},
            "reason": suggestion.get("reason"),
        }

    @staticmethod
    def wants_conversation(suggestion: Dict[str, Any]) -> bool:
        """True when Accept should hand off to Conversation Engine (resume/guide)."""
        action = suggestion.get("action") or {}
        kind = (action.get("kind") or "").lower()
        route = (action.get("route") or "").lower()
        stype = (suggestion.get("type") or "").lower()
        if kind in ("resume_conversation", "conversation", "guide", "resume"):
            return True
        if "conversation" in route or route.startswith("/action/"):
            return True
        if stype in ("study", "travel") and kind in ("recover_session", "prep", "resume"):
            return True
        # Explicit conversation_session_id on suggestion meta
        meta = suggestion.get("meta") or {}
        if meta.get("conversation_session_id") or suggestion.get("conversation_session_id"):
            return True
        return False
