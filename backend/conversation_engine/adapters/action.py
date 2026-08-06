"""Action Engine adapter — open / answer / get / cancel guided flows."""
from __future__ import annotations

from typing import Any, Dict, Optional

from action_engine.models import AnswerBody, OpenBody
from action_engine.service import ActionEngineService


class ActionAdapter:
    def __init__(self, db, *, life_graph=None, knowledge=None, decisions=None):
        self.svc = ActionEngineService(
            db, life_graph=life_graph, knowledge=knowledge, decisions=decisions,
        )

    async def open_from_text(
        self,
        user_id: str,
        *,
        text: str,
        intent: Optional[Dict[str, Any]] = None,
        origin: str = "text",
        conversation_session_id: Optional[str] = None,
        known_slots: Optional[Dict[str, Any]] = None,
        force_new: bool = False,
    ) -> Dict[str, Any]:
        entities: Dict[str, Any] = {}
        if intent and isinstance(intent.get("entities"), dict):
            entities = dict(intent["entities"])
        # Merge Conversation memory slots into entities so AE skips known turns
        for k, v in (known_slots or {}).items():
            if v in (None, "", []):
                continue
            if k == "destination":
                entities.setdefault("travel", v)
                entities.setdefault("destination", v)
                entities.setdefault("place", v)
            elif k == "subject":
                entities.setdefault("subject", v)
            elif k == "confirm_subject":
                entities.setdefault("subject", v)
            else:
                entities.setdefault(k, v)

        meta: Dict[str, Any] = {
            "conversation_session_id": conversation_session_id,
            "conversation_origin": origin,
            "known_slots": known_slots or {},
        }
        if intent:
            meta["classified_intent"] = {**intent, "entities": entities}
            meta["intent"] = intent.get("intent")
            meta["intent_subtype"] = intent.get("subtype")
            meta["intent_confidence"] = intent.get("confidence")
            meta["intent_entities"] = entities
            # Keep body.intent entities aligned for AE _intent_from_body
            intent = {**intent, "entities": entities}

        body = OpenBody(
            title=text.strip()[:200] if text else "Parla con ORA",
            description=text,
            source_type="conversation",
            source_id=conversation_session_id,
            intent=intent,
            meta=meta,
            force_new=force_new,
        )
        return await self.svc.open(user_id, body)

    async def answer(
        self,
        user_id: str,
        action_session_id: str,
        *,
        option_id: Optional[str] = None,
        value: Any = None,
        text: Optional[str] = None,
        skip: bool = False,
    ) -> Dict[str, Any]:
        return await self.svc.answer(
            user_id,
            action_session_id,
            AnswerBody(option_id=option_id, value=value, text=text, skip=skip),
        )

    async def get(self, user_id: str, action_session_id: str) -> Optional[Dict[str, Any]]:
        return await self.svc.get_session(user_id, action_session_id)

    async def cancel(self, user_id: str, action_session_id: str) -> Dict[str, Any]:
        return await self.svc.cancel(user_id, action_session_id)
