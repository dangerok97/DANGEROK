from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import (
    AgentBudget,
    AgentEvidence,
    AgentRun,
    AutonomousGoal,
    ResultProvenance,
)
from agent.service import AgentService


OWNER = "alice"


async def _weather_goal(db, *, claim: str):
    service = AgentService(db)
    goal = AutonomousGoal(
        id="goal_weather_visibility_v78",
        owner_id=OWNER,
        status="waiting",
        objective="Seguire una situazione temporanea all'aperto",
        desired_outcome=(
            "Avvisare solo se condizioni fresche rendono utile agire, "
            "altrimenti non disturbare"
        ),
        why_now="La situazione è ancora attiva.",
        source_kind="opportunity",
        source_refs=["situation:sit_laundry_v78", "place:home_v78"],
    )
    await service.repo.create_goal(goal)
    await service.evidence.record(
        AgentEvidence(
            owner_id=OWNER,
            goal_id=goal.id,
            step_id="weather_check",
            claim=claim,
            supports="capire se la situazione richiede attenzione adesso",
            provenance=ResultProvenance(
                source_class="external_research",
                capability="weather.read",
                provider="open_meteo",
                freshness="fresh",
                source_refs=["place:home_v78"],
            ),
        )
    )
    await service.repo.journal(
        OWNER,
        goal.id,
        kind="step_done",
        note="Ho riletto condizioni esterne aggiornate.",
        detail={
            "really_happened": True,
            "came_from": "external_research",
        },
    )
    return service, goal


@pytest.mark.asyncio
async def test_time_sensitive_weather_result_becomes_useful_attention_not_narration(monkeypatch):
    from agent import reasoning
    from delivery.service import DeliveryService

    db = AsyncMongoMockClient().test
    service, goal = await _weather_goal(
        db,
        claim=(
            "Nel luogo della situazione la probabilità di pioggia sale "
            "all'85% entro i prossimi 45 minuti."
        ),
    )
    captured = {}

    async def judge(system, user):
        captured["system"] = system
        captured["user"] = user
        return {
            "outcome": "requires_attention",
            "headline": (
                "Tra meno di un'ora aumenta molto il rischio di pioggia: "
                "se i panni sono ancora fuori, conviene ritirarli."
            ),
            "reasoning": (
                "Il risultato fresco apre una finestra breve in cui avvisare "
                "può evitare un inconveniente concreto."
            ),
            "about": "rischio pioggia per la situazione all'aperto",
        }

    monkeypatch.setattr(reasoning, "_ask_model", judge)
    note_activity = AsyncMock(return_value=None)
    delivered = AsyncMock(return_value=SimpleNamespace(mode="in_app"))
    monkeypatch.setattr(DeliveryService, "note_activity", note_activity)
    monkeypatch.setattr(DeliveryService, "evaluate_subject", delivered)

    run = AgentRun(owner_id=OWNER, goal_id=goal.id, background=True)
    budget = AgentBudget()
    decision = await service._consider_visibility(
        OWNER, goal.id, run, budget, language="it"
    )

    assert decision is not None
    assert decision.outcome == "requires_attention"
    assert "rischio di pioggia" in decision.headline.lower()
    assert "85%" in captured["user"]
    assert "time-sensitive" in captured["system"]
    assert "semantic judgements" in captured["system"]

    need = await db.agent_needs.find_one(
        {"owner_id": OWNER, "goal_id": goal.id}, {"_id": 0}
    )
    assert need is not None
    assert need["kind"] == "important_outcome"
    assert need["requires_response"] is False
    assert "rischio di pioggia" in need["summary"].lower()

    note_activity.assert_awaited_once()
    delivered.assert_awaited_once()
    subject = delivered.await_args.args[1]
    assert subject.source_type == "agent_need"
    assert subject.goal_id == goal.id


@pytest.mark.asyncio
async def test_fresh_weather_that_changes_nothing_stays_silent(monkeypatch):
    from agent import reasoning
    from delivery.service import DeliveryService

    db = AsyncMongoMockClient().test
    service, goal = await _weather_goal(
        db,
        claim=(
            "Nel luogo della situazione le prossime quattro ore restano "
            "asciutte e la probabilità massima di pioggia è 5%."
        ),
    )

    async def judge(system, user):
        assert "5%" in user
        assert "silence is normally better" in system
        return {
            "outcome": "silent",
            "headline": "",
            "reasoning": (
                "Il controllo fresco non cambia alcuna decisione e non "
                "aggiunge qualcosa per cui valga interrompere la persona."
            ),
            "about": "condizioni stabili della situazione all'aperto",
        }

    monkeypatch.setattr(reasoning, "_ask_model", judge)
    note_activity = AsyncMock(return_value=None)
    delivered = AsyncMock(return_value=SimpleNamespace(mode="in_app"))
    monkeypatch.setattr(DeliveryService, "note_activity", note_activity)
    monkeypatch.setattr(DeliveryService, "evaluate_subject", delivered)

    decision = await service._consider_visibility(
        OWNER,
        goal.id,
        AgentRun(owner_id=OWNER, goal_id=goal.id, background=True),
        AgentBudget(),
        language="it",
    )

    assert decision is not None
    assert decision.outcome == "silent"
    assert await db.agent_needs.count_documents(
        {"owner_id": OWNER, "goal_id": goal.id}
    ) == 0
    note_activity.assert_not_awaited()
    delivered.assert_not_awaited()
