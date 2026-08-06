"""ConversationEngineService — feature flag + thin facade over orchestrator."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from conversation_engine.orchestrator import ConversationOrchestrator
from conversation_engine.repository import ConversationRepository

logger = logging.getLogger("ora.conversation_engine")


def conversation_engine_enabled() -> bool:
    raw = (os.environ.get("CONVERSATION_ENGINE_ENABLED") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


class ConversationEngineService:
    def __init__(self, db, *, life_graph=None, knowledge=None, decisions=None):
        self.db = db
        self.repo = ConversationRepository(db)
        self.orchestrator = ConversationOrchestrator(
            db, life_graph=life_graph, knowledge=knowledge, decisions=decisions,
        )

    async def ensure_indexes(self) -> None:
        await self.repo.ensure_indexes()

    def _disabled(self) -> Dict[str, Any]:
        return {
            "ok": False,
            "error": "conversation_engine_disabled",
            "enabled": False,
            "honesty": "CONVERSATION_ENGINE_ENABLED is off — no session created.",
        }

    async def start(self, user_id: str, **kwargs) -> Dict[str, Any]:
        if not conversation_engine_enabled():
            return self._disabled()
        return await self.orchestrator.start(user_id, **kwargs)

    async def message(self, user_id: str, session_id: str, **kwargs) -> Dict[str, Any]:
        if not conversation_engine_enabled():
            return self._disabled()
        return await self.orchestrator.message(user_id, session_id, **kwargs)

    async def continue_session(self, user_id: str, session_id: str, **kwargs) -> Dict[str, Any]:
        if not conversation_engine_enabled():
            return self._disabled()
        return await self.orchestrator.continue_session(user_id, session_id, **kwargs)

    async def cancel(self, user_id: str, session_id: str, **kwargs) -> Dict[str, Any]:
        if not conversation_engine_enabled():
            return self._disabled()
        return await self.orchestrator.cancel(user_id, session_id, **kwargs)

    async def pause(self, user_id: str, session_id: str) -> Dict[str, Any]:
        if not conversation_engine_enabled():
            return self._disabled()
        return await self.orchestrator.pause(user_id, session_id)

    async def resume(self, user_id: str, **kwargs) -> Dict[str, Any]:
        if not conversation_engine_enabled():
            return self._disabled()
        return await self.orchestrator.resume(user_id, **kwargs)

    async def history(self, user_id: str, session_id: str) -> Dict[str, Any]:
        if not conversation_engine_enabled():
            return self._disabled()
        return await self.orchestrator.history(user_id, session_id)

    async def summary(self, user_id: str, session_id: str) -> Dict[str, Any]:
        if not conversation_engine_enabled():
            return self._disabled()
        return await self.orchestrator.summary(user_id, session_id)

    async def get(self, user_id: str, session_id: str) -> Dict[str, Any]:
        if not conversation_engine_enabled():
            return self._disabled()
        return await self.orchestrator.get(user_id, session_id)

    async def list_resumable(self, user_id: str, *, limit: int = 10) -> List[Dict[str, Any]]:
        if not conversation_engine_enabled():
            return []
        sessions = await self.repo.list_active(user_id, limit=limit)
        return [s.public() for s in sessions]

    async def start_from_proactive(
        self,
        user_id: str,
        suggestion: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Proactive Accept handoff — open or resume Conversation Session."""
        if not conversation_engine_enabled():
            return self._disabled()
        from conversation_engine.adapters.suggestions import SuggestionsAdapter

        sid = suggestion.get("id")
        # Resume linked conversation first
        meta = suggestion.get("meta") or {}
        ces_id = meta.get("conversation_session_id") or suggestion.get("conversation_session_id")
        if ces_id:
            resumed = await self.orchestrator.resume(user_id, session_id=ces_id)
            if resumed.get("ok"):
                return {**resumed, "handoff": "resume_conversation"}

        if sid:
            existing = await self.repo.find_resumable_for_suggestion(user_id, sid)
            if existing:
                resumed = await self.orchestrator.resume_session(user_id, existing)
                return {**resumed, "handoff": "resume_conversation"}

        ctx = SuggestionsAdapter.conversational_context(suggestion)
        text = suggestion.get("title") or suggestion.get("description") or "Continua con ORA"
        # Prefer resume phrasing for interrupted prep
        if (suggestion.get("action") or {}).get("kind") in ("resume", "resume_conversation", "guide"):
            origin = "proactive"
        else:
            origin = "notifications"

        started = await self.orchestrator.start(
            user_id,
            text=text,
            origin=origin,
            suggestion_id=sid,
            context={"proactive": ctx, "known_slots": {}},
        )
        return {**started, "handoff": "start_conversation"}
