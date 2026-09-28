"""An ambiguous Home card must not ask what ORA itself meant by exam/event."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import MethodType, SimpleNamespace

import pytest

from action_engine import effects
from action_engine.flows import build_flow_turns, resolve_flow_from_intent
from action_engine.models import ActionSession, AnswerBody, OpenBody, TurnAnswer
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
        if query.get("current_turn_id", self.row["current_turn_id"]) != self.row["current_turn_id"]:
            return SimpleNamespace(matched_count=0)
        self.row = replacement
        self.replacements += 1
        return SimpleNamespace(matched_count=1)


def _service(session: ActionSession) -> tuple[ActionEngineService, Sessions]:
    collection = Sessions(session)
    service = object.__new__(ActionEngineService)
    service.db = SimpleNamespace(action_sessions=collection)
    service.knowledge = None
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


def test_untouched_home_guide_refreshes_to_only_useful_choices():
    session = _old_session()
    session.flow = "generic"
    session.current_turn_id = "intent"
    session.turns = build_flow_turns("generic", {"title": session.title})
    session.meta["intent_reason"] = "home_card_needs_purpose"
    service, collection = _service(session)
    result = asyncio.run(service.open("u_test", _home_body()))
    turn = result["session"]["current_turn"]
    assert [option["id"] for option in turn["options"]] == ["organize", "remind"]
    assert [option["id"] for option in collection.row["turns"][2]["options"]] == ["checklist", "reminder"]
    assert collection.replacements == 1


def test_answered_home_guide_keeps_its_original_turns():
    session = _old_session()
    session.flow = "generic"
    session.current_turn_id = "when"
    session.turns = build_flow_turns("generic", {"title": session.title})
    session.meta["intent_reason"] = "home_card_needs_purpose"
    session.answers["intent"] = "calendar"
    session.turn_history.append(TurnAnswer(turn_id="intent", option_id="calendar", value="calendar"))
    service, collection = _service(session)
    result = asyncio.run(service.open("u_test", _home_body()))
    assert result["session"]["current_turn"]["id"] == "when"
    assert collection.replacements == 0


def test_home_reminder_needs_only_a_delivery_time():
    session = _old_session()
    session.flow = "generic"
    session.turns = build_flow_turns("generic", {
        "title": session.title, "intent_reason": "home_card_needs_purpose",
    })
    session.current_turn_id = "intent"
    session.meta["intent_reason"] = "home_card_needs_purpose"
    service, collection = _service(session)
    first = asyncio.run(service.answer("u_test", session.id, AnswerBody(option_id="remind")))
    assert first["session"]["current_turn"]["question"] == "Quando vuoi che te lo ricordi?"
    assert [o["id"] for o in first["session"]["current_turn"]["options"]] == [
        "in_1_hour", "tomorrow", "in_3_days", "in_1_week",
    ]
    assert collection.row["answers"]["support"] == "reminder"

    async def completed(self, user_id, session_id):
        return {"completed": True, "session": self.col.row}

    service.complete = MethodType(completed, service)
    second = asyncio.run(service.answer("u_test", session.id, AnswerBody(option_id="tomorrow")))
    assert second["completed"]
    assert second["session"]["answers"]["when"] == "tomorrow"
    assert len(second["session"]["turn_history"]) == 2


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


@pytest.mark.parametrize(
    ("intent", "support", "reminders", "events", "decisions"),
    [
        ("organize", "checklist", 0, 0, 1),
        ("organize", "project", 0, 0, 0),
        ("remind", "checklist", 1, 0, 1),
        ("organize", "reminder", 1, 0, 0),
        ("calendar", "project", 0, 1, 0),
    ],
)
def test_generic_effects_follow_explicit_choices(monkeypatch, intent, support, reminders, events, decisions):
    calls = {"reminders": 0, "events": 0, "decisions": 0}

    async def reminder(*args, **kwargs):
        calls["reminders"] += 1
        return {"id": "rem_test"}

    async def event(*args, **kwargs):
        calls["events"] += 1
        return {"id": "event_test"}

    async def decision(*args, **kwargs):
        calls["decisions"] += 1
        return {"id": "decision_test"}

    monkeypatch.setattr(effects, "_create_reminder", reminder)
    monkeypatch.setattr(effects, "_create_life_event", event)
    monkeypatch.setattr(effects, "_create_decision", decision)
    session = {"id": "s1", "user_id": "u_test", "flow": "generic", "title": "Una priorità",
               "answers": {"intent": intent, "when": "today", "support": support}}
    _, result = asyncio.run(effects.apply_completion_effects(
        db=None, life_graph=None, knowledge=None, decisions=None, session=session,
    ))
    assert calls == {"reminders": reminders, "events": events, "decisions": decisions}
    assert len(result["reminder_ids"]) == reminders
    assert len(result["calendar_ids"]) == events


@pytest.mark.parametrize("when,delta", [
    ("in_1_hour", timedelta(hours=1)),
    ("tomorrow", timedelta(days=1)),
    ("in_3_days", timedelta(days=3)),
    ("in_1_week", timedelta(days=7)),
])
def test_home_reminder_delivery_is_scheduled_after_selected_delay(monkeypatch, when, delta):
    captured = []

    async def reminder(*args, **kwargs):
        captured.append(kwargs["due_at"])
        return {"id": "rem_test"}

    monkeypatch.setattr(effects, "_create_reminder", reminder)
    before = datetime.now(timezone.utc)
    asyncio.run(effects.apply_completion_effects(
        db=None, life_graph=None, knowledge=None, decisions=None,
        session={"id": "s1", "user_id": "u_test", "flow": "generic", "title": "Una priorità",
                 "answers": {"intent": "remind", "support": "reminder", "when": when}},
    ))
    assert len(captured) == 1
    assert before + delta <= captured[0] <= datetime.now(timezone.utc) + delta
