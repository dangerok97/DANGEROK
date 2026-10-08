"""Phase 1: the AI execution contract survives exhaustion of its reasoning budget.

The model chooses capabilities. These tests fake only their observed outcomes;
nothing connects to a real account, calendar, or provider.
"""
import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.ai_core.models import Observation
from conversation_engine.ai_core.tools.registry import ToolRegistry
from conversation_engine.models import ConversationSession


@pytest.fixture(autouse=True)
def _enable_trace_for_fixture(monkeypatch):
    # CI normally redacts diagnostic steps; these tests use only fake data.
    monkeypatch.setenv("AI_CORE_TRACE", "1")


def _session():
    return ConversationSession(
        user_id="phase1-owner", meta={"ui_mode": "ai_core", "ai_core": {}}
    )


def _tool_decision(capability, required):
    return {
        "response_mode": "tool",
        "reasoning_status": "needs_tool",
        "message_to_user": "Ok.",
        "user_intent_summary": "gestire una richiesta usando skill reali",
        "tool_call": {
            "capability": capability,
            "arguments": {},
        },
        "skill_plan": {
            "objective": "Verificare e completare i passaggi",
            "required_capabilities": required,
            "completion_condition": "Esiti osservati delle skill richieste.",
        },
        "situation_update": {"operation": "none"},
    }


@pytest.mark.asyncio
async def test_reasoning_bound_keeps_unseen_skill_and_never_claims_done(monkeypatch):
    async def execute(self, capability, args, *, runtime):
        assert capability == "get_calendar_events"
        return Observation(
            kind="tool", name=capability, status="ok",
            payload={"status": "ok", "events": []},
        )

    monkeypatch.setattr(ToolRegistry, "execute", execute)
    sess = _session()

    async def decide(system, payload):
        return _tool_decision(
            "get_calendar_events",
            ["get_calendar_events", "get_route"],
        )

    result = await run_cognitive_loop(
        sess=sess, user_message="Organizza lo spostamento",
        db=AsyncMongoMockClient().phase1_unseen, decision_fn=decide, max_steps=1,
    )
    assert result.ok
    assert "non ho ancora completato" in result.ora_text.lower()
    assert "passaggi" in result.ora_text
    state = sess.meta["ai_core"]
    plan = state["active_skill_plan"]
    assert plan["required_capabilities"] == ["get_calendar_events", "get_route"]
    assert plan["capability_outcomes"][0]["status"] == "ok"
    assert plan["waiting"] is False
    assert "arguments" not in str(plan)
    assert any(
        row.get("event") == "SKILL_PLAN_BOUND_UNFINISHED"
        for row in result.trace.get("steps", [])
    )


@pytest.mark.asyncio
async def test_reasoning_bound_failed_tool_cannot_be_reported_as_success(monkeypatch):
    async def execute(self, capability, args, *, runtime):
        return Observation(
            kind="tool", name=capability, status="error",
            payload={"status": "error", "failure_code": "PROVIDER_UNAVAILABLE"},
        )

    monkeypatch.setattr(ToolRegistry, "execute", execute)
    sess = _session()

    async def decide(system, payload):
        return _tool_decision("get_calendar_events", ["get_calendar_events"])

    result = await run_cognitive_loop(
        sess=sess, user_message="Controlla il calendario",
        db=AsyncMongoMockClient().phase1_error, decision_fn=decide, max_steps=1,
    )
    assert result.ok
    assert "non sono riuscita a completare" in result.ora_text.lower()
    assert "errore" in result.ora_text.lower()
    assert sess.meta["ai_core"]["active_skill_plan"] is None
    assert result.trace.get("skill_plan_failed") == ["get_calendar_events"]


@pytest.mark.asyncio
async def test_calendar_confirmation_survives_bound_and_can_be_resumed(monkeypatch):
    confirmation = {
        "question": "Vuoi confermare la cancellazione?",
        "arguments": {"calendar_ref": "calendar:opaque"},
    }

    async def execute(self, capability, args, *, runtime):
        return Observation(
            kind="tool", name=capability, status="partial",
            payload={
                "status": "authority_required",
                "confirmation_request": confirmation,
            },
        )

    monkeypatch.setattr(ToolRegistry, "execute", execute)
    sess = _session()

    async def decide(system, payload):
        return _tool_decision(
            "cancel_calendar_event", ["cancel_calendar_event"]
        )

    result = await run_cognitive_loop(
        sess=sess, user_message="Cancella l'impegno indicato",
        db=AsyncMongoMockClient().phase1_authority, decision_fn=decide,
        max_steps=1,
    )
    assert result.ok
    assert result.ora_text == confirmation["question"]
    state = sess.meta["ai_core"]
    assert state["pending_act"]["calendar_cancel"] == confirmation
    assert state["active_skill_plan"]["waiting"] is True
    assert state["active_skill_plan"]["capability_outcomes"][0]["status"] == "partial"


@pytest.mark.asyncio
async def test_all_successful_skills_at_bound_never_return_just_ok(monkeypatch):
    async def execute(self, capability, args, *, runtime):
        return Observation(
            kind="tool", name=capability, status="ok",
            payload={"status": "ok", "events": []},
        )

    monkeypatch.setattr(ToolRegistry, "execute", execute)
    sess = _session()

    async def decide(system, payload):
        return _tool_decision("get_calendar_events", ["get_calendar_events"])

    result = await run_cognitive_loop(
        sess=sess, user_message="Controlla gli impegni",
        db=AsyncMongoMockClient().phase1_done, decision_fn=decide,
        max_steps=1,
    )
    assert result.ok
    assert result.ora_text.strip().casefold() != "ok."
    assert result.trace.get("skill_plan_completed") is True
    assert sess.meta["ai_core"]["active_skill_plan"] is None
