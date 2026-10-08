"""Phase 1: a model saying 'ready_to_act' is not proof of action.

The cognitive loop and its governance are real; decisions and read-only tool
responses are scripted. No user data, account, or external provider is used.
"""
import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.ai_core.models import Observation
from conversation_engine.ai_core.tools.registry import ToolRegistry
from conversation_engine.models import ConversationSession


@pytest.fixture(autouse=True)
def diagnostic_trace(monkeypatch):
    monkeypatch.setenv("AI_CORE_TRACE", "1")


def session():
    return ConversationSession(
        user_id="phase1-ready-owner",
        meta={"ui_mode": "ai_core", "ai_core": {}},
    )


def claim():
    return {
        "response_mode": "answer",
        "reasoning_status": "ready_to_act",
        "message_to_user": "Ho organizzato tutto per te.",
        "user_intent_summary": "organizzare un impegno",
        "situation_update": {"operation": "none"},
    }


@pytest.mark.asyncio
async def test_action_claim_is_retried_and_real_capability_is_used(monkeypatch):
    executed = []

    async def execute(self, capability, args, *, runtime):
        executed.append(capability)
        return Observation(
            kind="tool", name=capability, status="ok",
            payload={"status": "ok", "events": []},
        )

    monkeypatch.setattr(ToolRegistry, "execute", execute)
    calls = 0

    async def decide(system, payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            return claim()
        if calls == 2:
            return {
                "response_mode": "tool",
                "reasoning_status": "needs_tool",
                "tool_call": {
                    "capability": "get_calendar_events", "arguments": {},
                },
                "situation_update": {"operation": "none"},
            }
        return {
            "response_mode": "answer",
            "reasoning_status": "enough_information",
            "message_to_user": "Ho verificato il calendario.",
            "situation_update": {"operation": "none"},
        }

    result = await run_cognitive_loop(
        sess=session(), user_message="Verifica i miei impegni.",
        db=AsyncMongoMockClient().ready_action_retried,
        decision_fn=decide, max_steps=4,
    )
    assert result.ok
    assert executed == ["get_calendar_events"]
    assert result.tool_calls == 1
    assert "verificato il calendario" in result.ora_text.lower()
    assert any(
        step.get("event") == "READY_ACT_NO_EFFECT_NUDGE"
        for step in result.trace.get("steps", [])
    )


@pytest.mark.asyncio
async def test_repeated_unexecuted_ready_to_act_cannot_claim_completion():
    async def decide(system, payload):
        return claim()

    result = await run_cognitive_loop(
        sess=session(), user_message="Organizza questo impegno.",
        db=AsyncMongoMockClient().ready_action_blocked,
        decision_fn=decide, max_steps=2,
    )
    assert result.ok
    assert result.tool_calls == 0
    assert "non ho ancora eseguito" in result.ora_text.lower()
    assert "non la considero completata" in result.ora_text.lower()
    assert any(
        step.get("event") == "READY_ACT_NO_EFFECT_BLOCKED"
        for step in result.trace.get("steps", [])
    )


@pytest.mark.asyncio
async def test_ready_to_act_at_one_step_bound_cannot_escape():
    async def decide(system, payload):
        return claim()

    result = await run_cognitive_loop(
        sess=session(), user_message="Organizzati tu.",
        db=AsyncMongoMockClient().ready_action_bound,
        decision_fn=decide, max_steps=1,
    )
    assert result.ok
    assert result.tool_calls == 0
    assert "non ho ancora eseguito" in result.ora_text.lower()


@pytest.mark.asyncio
async def test_information_answer_without_action_is_not_blocked():
    async def decide(system, payload):
        return {
            "response_mode": "answer",
            "reasoning_status": "enough_information",
            "message_to_user": "Oggi è giovedì.",
            "situation_update": {"operation": "none"},
        }

    result = await run_cognitive_loop(
        sess=session(), user_message="Che giorno è oggi?",
        db=AsyncMongoMockClient().info_answer,
        decision_fn=decide, max_steps=1,
    )
    assert result.ok
    assert result.ora_text == "Oggi è giovedì."
