from unittest.mock import AsyncMock

import pytest

from agent.models import ActionStep


@pytest.mark.asyncio
async def test_make_plan_contract_forbids_create_as_calendar_correction(monkeypatch):
    from agent import reasoning

    seen = {}

    async def ask(system, user):
        seen["system"] = system
        seen["user"] = user
        return {
            "plan_summary": "Verificare e correggere l'orario.",
            "expected_outcome": "Calendario coerente.",
            "steps": [{
                "intent": "Leggere la mail rilevante.",
                "step_type": "inspect",
                "capability_needed": "mail.read",
                "input_refs": ["mail:m1"],
                "expected_result": "Nuovo orario verificato",
                "external_effect": False,
            }],
        }

    monkeypatch.setattr(reasoning, "_ask_model", ask)
    out = await reasoning.make_plan(
        {
            "objective": "Correggere il dentista",
            "source_refs": ["link_1", "mail:m1", "calendar:event_123"],
        },
        capabilities=[
            {"capability": "mail.read", "status": "available_real"},
            {"capability": "calendar.write", "status": "available_real"},
        ],
        context={"weekday": "monday"},
    )

    assert out is not None
    contract = seen["system"]
    assert "never use create to correct an appointment that already exists" in contract
    assert "effect_type=modify" in contract
    assert "copy that exact ref into input_refs" in contract
    assert "never guess an hour" in contract
    assert '"effect_type": "create|modify|cancel|send|transfer|publish|remove"' in contract


@pytest.mark.asyncio
async def test_choose_next_refuses_incomplete_calendar_modify_contract(monkeypatch):
    from agent import reasoning

    seen = {}

    async def ask(system, user):
        seen["system"] = system
        seen["user"] = user
        return {
            "decision": "replan",
            "step_id": "",
            "reasoning": "Ora il nuovo orario è noto e va messo nel passo di modifica.",
            "asks": "",
            "ask_kind": None,
            "wait_hours": None,
        }

    monkeypatch.setattr(reasoning, "_ask_model", ask)
    step = ActionStep(
        id="s1",
        ordinal=0,
        intent="Spostare il dentista",
        step_type="execute",
        capability_needed="calendar.write",
        input_refs=["calendar:event_123"],
        external_effect=True,
        effect_type="modify",
        effect_target="Dentista",
        parameters={},
        expected_result="Dentista al nuovo orario",
    )

    answer = await reasoning.choose_next_action(
        {"objective": "Correggere il dentista"},
        plan={"steps": [step.for_ai()]},
        candidates=[step.for_ai()],
        evidence=[{"what_was_found": "La mail conferma le 16:30"}],
        capabilities=[{"capability": "calendar.write", "status": "available_real"}],
    )

    assert answer["decision"] == "replan"
    assert "not executable yet" in seen["system"]
    assert "choose replan" in seen["system"]


def test_calendar_step_exposes_effect_and_only_bounded_execution_parameters():
    step = ActionStep(
        intent="Spostare il dentista",
        step_type="execute",
        capability_needed="calendar.write",
        input_refs=["calendar:event_123"],
        external_effect=True,
        effect_type="modify",
        effect_target="Dentista",
        parameters={
            "title": "Dentista",
            "starts_at": "2026-10-06T16:30:00+02:00",
            "ends_at": "2026-10-06T17:30:00+02:00",
            "timezone": "Europe/Rome",
            "unrelated_internal_value": "must not be shown",
        },
    )

    shown = step.for_ai()

    assert shown["what_kind_of_change"] == "modify"
    assert shown["effect_target"] == "Dentista"
    assert shown["input_refs"] == ["calendar:event_123"]
    assert shown["execution_parameters"] == {
        "title": "Dentista",
        "starts_at": "2026-10-06T16:30:00+02:00",
        "ends_at": "2026-10-06T17:30:00+02:00",
        "timezone": "Europe/Rome",
    }


def test_agent_step_parser_preserves_calendar_modify_fields():
    from agent.service import AgentService

    step = AgentService._read_step({
        "intent": "Applicare il nuovo orario verificato",
        "step_type": "execute",
        "capability_needed": "calendar.write",
        "input_refs": ["calendar:event_123"],
        "expected_result": "Evento aggiornato",
        "external_effect": True,
        "effect_type": "modify",
        "effect_target": "Dentista",
        "reaches_somebody_else": False,
        "reversibility": "easily",
        "parameters": {
            "title": "Dentista",
            "starts_at": "2026-10-06T16:30:00+02:00",
            "ends_at": "2026-10-06T17:30:00+02:00",
            "timezone": "Europe/Rome",
        },
    }, 2)

    assert step is not None
    assert step.effect_type == "modify"
    assert step.effect_target == "Dentista"
    assert step.input_refs == ["calendar:event_123"]
    assert step.parameters["starts_at"].endswith("+02:00")
