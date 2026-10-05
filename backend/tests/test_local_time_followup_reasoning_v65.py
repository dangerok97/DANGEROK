from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import (
    ActionPlan,
    ActionStep,
    AgentBudget,
    AgentEvidence,
    AgentRun,
    AutonomousGoal,
    ResultProvenance,
)
from agent.service import AgentService, _user_clock_context


OWNER = "alice"
CLOCK = {
    "local_datetime": "2026-10-05T11:28:00+02:00",
    "local_time": "11:28",
    "local_date": "2026-10-05",
    "timezone": "Europe/Rome",
    "authority": "user_confirmed",
    "today": "2026-10-05",
    "today_weekday": "Monday",
}


@pytest.mark.asyncio
async def test_agent_clock_context_uses_existing_timezone_resolver(monkeypatch):
    import timezone_service

    monkeypatch.setattr(
        timezone_service,
        "user_clock_context",
        AsyncMock(return_value=dict(CLOCK)),
    )

    db = AsyncMongoMockClient().test
    context = await _user_clock_context(db, OWNER)

    assert context["local_time"] == "11:28"
    assert context["local_date"] == "2026-10-05"
    assert context["timezone"] == "Europe/Rome"
    assert context["authority"] == "user_confirmed"
    assert context["today"] == "2026-10-05"
    assert context["today_weekday"] == "Monday"


@pytest.mark.asyncio
async def test_initial_autonomous_plan_receives_local_clock(monkeypatch):
    from agent import reasoning
    import agent.service as agent_service

    db = AsyncMongoMockClient().test
    service = AgentService(db)
    goal = AutonomousGoal(
        id="goal_clock_plan",
        owner_id=OWNER,
        status="active",
        objective="Ricontrollare una situazione prima di sera",
        desired_outcome="Agire nel momento locale utile",
    )

    monkeypatch.setattr(
        agent_service,
        "_user_clock_context",
        AsyncMock(return_value=dict(CLOCK)),
    )

    captured = {}

    async def make_plan(goal_payload, *, capabilities, context, language="it"):
        captured["context"] = context
        return {
            "plan_summary": "Controllare e rivalutare al momento giusto.",
            "expected_outcome": "Contesto rivalutato.",
            "assumptions": [],
            "known_constraints": [],
            "steps": [{
                "intent": "Leggere il contesto",
                "step_type": "inspect",
                "capability_needed": "information.read",
                "input_refs": [],
                "parameters": {},
                "expected_result": "Contesto aggiornato",
                "external_effect": False,
                "reversibility": "easily",
            }],
        }

    monkeypatch.setattr(reasoning, "make_plan", make_plan)
    monkeypatch.setattr(service.capabilities, "available", AsyncMock(return_value=[]))

    plan = await service._build_plan(
        OWNER,
        goal,
        AgentRun(owner_id=OWNER, goal_id=goal.id, background=True),
        AgentBudget(),
        language="it",
    )

    assert plan is not None
    assert captured["context"]["local_time"] == "11:28"
    assert captured["context"]["timezone"] == "Europe/Rome"
    assert captured["context"]["today_weekday"] == "Monday"


@pytest.mark.asyncio
async def test_next_action_reasoning_receives_same_local_clock(monkeypatch):
    from agent import reasoning

    captured = {}

    async def ask_model(system, user):
        captured["user"] = user
        return {
            "decision": "wait",
            "step_id": "",
            "reasoning": "Ricontrollare nel pomeriggio locale.",
            "asks": "",
            "ask_kind": None,
            "wait_hours": 4,
        }

    monkeypatch.setattr(reasoning, "_ask_model", ask_model)

    result = await reasoning.choose_next_action(
        {
            "objective": "Seguire una situazione prima di sera",
            "desired_outcome": "Controllo nel momento utile",
        },
        plan={"summary": "Piano"},
        candidates=[{
            "id": "verify_1",
            "intent": "Verificare di nuovo",
            "type": "verify",
            "status": "pending",
        }],
        evidence=[{
            "what_was_found": "Il contesto attuale non basta ancora.",
            "how_old": "fresh",
        }],
        capabilities=[],
        clock_context=dict(CLOCK),
        language="it",
    )

    assert result is not None
    assert result["decision"] == "wait"
    assert result["wait_hours"] == 4
    assert '"local_time": "11:28"' in captured["user"]
    assert '"timezone": "Europe/Rome"' in captured["user"]
    assert '"authority": "user_confirmed"' in captured["user"]


@pytest.mark.asyncio
async def test_reconsider_reasoning_receives_local_clock(monkeypatch):
    from agent import reasoning

    captured = {}

    async def ask_model(system, user):
        captured["user"] = user
        return {
            "decision": "wait",
            "reasoning": "Aspetto fino al prossimo controllo locale utile.",
            "replace_step_ids": [],
            "revised_steps": [],
            "wait_hours": 2,
            "asks": "",
            "ask_kind": None,
        }

    monkeypatch.setattr(reasoning, "_ask_model", ask_model)

    result = await reasoning.reconsider(
        {"objective": "Seguire un esito esterno"},
        plan={"steps": []},
        what_happened={"problem": "scheduled_external_checkpoint"},
        capabilities=[],
        clock_context=dict(CLOCK),
        language="it",
    )

    assert result is not None
    assert result["decision"] == "wait"
    assert result["wait_hours"] == 2
    assert '"local_time": "11:28"' in captured["user"]
    assert '"timezone": "Europe/Rome"' in captured["user"]
