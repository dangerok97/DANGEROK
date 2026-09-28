"""An ambiguous Home card must not ask what ORA itself meant by exam/event."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from action_engine.flows import build_flow_turns, resolve_flow_from_intent
from action_engine.models import ActionSession, OpenBody, TurnAnswer
from action_engine.service import ActionEngineService


class Sessions:
    def __init__(self, session: ActionSession):
        self.row = session.model_dump()
        self.replacements = 0

    async def find_one(self, query, projection=None):
        return self.row.copy() if query.get("id", self.row["id"]) == self.row["id"] else None

    async def replace_one(self, query, replacement):
        if query.get("turn_history") == [] and self.row["turn_history"]:
            return SimpleNamespace(matched_count=0)
        self.row = replacement
        self.replacements += 1
        return SimpleNamespace(matched_count=1)


def _service(session: ActionSession) -> tuple[ActionEngineService, Sessions]:
    collection = Sessions(session)
    service = object.__new__(ActionEngineService)
    service.db = SimpleNamespace(action_sessions=collection)
    return service, collection


def _home_body() -> OpenBody:
    return OpenBody(home_item={
        "id": "focus_ambiguous", "type": "generic", "source_type": "life_experience",
        "source_id": "experience_123", "title": "xyz qwerty nonsense",
    })


def _old_session() -> ActionSession:
    turns = build_flow_turns("clarify", {"title": "xyz qwerty nonsense"})
    return ActionSession(
        id="aes_old_123", user_id="u_test", flow="clarify",
        home_item_id="focus_ambiguous", title="xyz qwerty nonsense",
        current_turn_id=turns[0].id, turns=turns,
    )


def test_ambiguous_home_card_asks_about_its_own_title():
    service, _ = _service(_old_session())
    body = _home_body()
    intent = service._intent_from_body(body, service._ctx_from_open(body))
    assert intent.intent == "generic" and not intent.needs_clarify
    assert resolve_flow_from_intent(intent.intent, needs_clarify=intent.needs_clarify) == "generic"
    question = build_flow_turns("generic", {"title": body.home_item["title"]})[0].question
    assert body.home_item["title"] in question
    assert "esame" not in question


def test_precomputed_uncertainty_on_home_card_also_uses_its_title():
    service, _ = _service(_old_session())
    body = _home_body().model_copy(update={"intent": {
        "intent": "study", "confidence": 0.4, "needs_clarify": True,
    }})
    intent = service._intent_from_body(body, service._ctx_from_open(body))
    assert intent.intent == "generic" and not intent.needs_clarify


def test_unanswered_legacy_clarifier_is_repaired_on_open():
    service, collection = _service(_old_session())
    result = asyncio.run(service.open("u_test", _home_body()))
    assert result["resumed"]
    assert result["session"]["flow"] == "generic"
    assert "xyz qwerty nonsense" in result["session"]["current_turn"]["question"]
    assert collection.replacements == 1


def test_answered_clarifier_keeps_the_persons_choice():
    session = _old_session()
    session.turn_history.append(TurnAnswer(turn_id="clarify_intent", option_id="clarify_study", value={"intent": "study"}))
    service, collection = _service(session)
    result = asyncio.run(service.open("u_test", _home_body()))
    assert result["session"]["flow"] == "clarify"
    assert collection.replacements == 0


def test_free_text_without_home_card_still_uses_clarifier():
    service, _ = _service(_old_session())
    body = OpenBody(title="xyz qwerty nonsense")
    intent = service._intent_from_body(body, service._ctx_from_open(body))
    assert intent.needs_clarify
