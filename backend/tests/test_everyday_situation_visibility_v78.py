from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import (
    AgentBudget,
    AgentEvidence,
    AgentRun,
    AutonomousGoal,
    ResultProvenance,
    VisibilityDecision,
)
from agent.service import AgentService


OWNER = "alice"


async def _weather_run(db, *, rain_claim: str):
    service = AgentService(db)
    goal = AutonomousGoal(
        id="goal_weather_visibility",
        owner_id=OWNER,
        status="waiting",
        objective="Seguire una situazione temporanea all'aperto",
        desired_outcome="Sapere se emerge qualcosa di utile per la situazione",
        source_kind="opportunity",
        source_refs=["situation:sit_laundry", "place:home"],
    )
    await service.repo.save_goal(goal)

    run = AgentRun(owner_id=OWNER, goal_id=goal.id, background=True)
    evidence = AgentEvidence(
        owner_id=OWNER,
        goal_id=goal.id,
        step_id="weather_check",
        kind="inspect",
        claim=rain_claim,
        supports="rischio di pioggia nelle prossime ore",
        provenance=ResultProvenance(
            source_class="external_research",
            capability="weather.read",
            provider="open_meteo",
            freshness="fresh",
        ),
    )
    await service.evidence.record(evidence)
    await service.repo.journal(
        OWNER,
        goal.id,
        kind="step_done",
        note="Ho riletto le condizioni meteo del luogo della situazione.",
        detail={
            "step_id": "weather_check",
            "status": "succeeded",
            "came_from": "external_research",
            "really_happened": True,
            "evidence": 1,
        },
    )
    return service, goal, run


@pytest.mark.asyncio
async def test_unchanged_harmless_conditions_stay_silent(monkeypatch):
    """Same autonomous Situation, no useful consequence -> no user need."""
    from agent import reasoning

    db = AsyncMongoMockClient().test
    service, goal, run = await _weather_run(
        db,
        rain_claim=(
            "Nelle prossime ore la probabilità massima di pioggia indicata "
            "dal provider è 10%."
        ),
    )

    async def decide(goal_payload, *, what_happened, already_said, language="it"):
        assert "10%" in str(what_happened)
        return {
            "outcome": "silent",
            "headline": "",
            "reasoning": "Non è emerso nulla che richieda l'attenzione della persona.",
            "about": "condizioni della situazione temporanea",
        }

    monkeypatch.setattr(reasoning, "decide_visibility", decide)
    show = AsyncMock()
    offer = AsyncMock()
    monkeypatch.setattr(service.visibility, "show", show)
    monkeypatch.setattr(service.needs, "offer_to_delivery", offer)

    decision = await service._consider_visibility(
        OWNER,
        goal.id,
        run,
        AgentBudget(),
        language="it",
    )

    assert decision is not None
    assert decision.outcome == "silent"
    show.assert_not_awaited()
    offer.assert_not_awaited()
    assert await db.agent_needs.count_documents({
        "owner_id": OWNER,
        "goal_id": goal.id,
    }) == 0


@pytest.mark.asyncio
async def test_material_weather_change_becomes_useful_result(monkeypatch):
    """Same autonomous Situation, material consequence -> a delivery-eligible need."""
    from agent import reasoning

    db = AsyncMongoMockClient().test
    service, goal, run = await _weather_run(
        db,
        rain_claim=(
            "Nelle prossime ore la probabilità massima di pioggia indicata "
            "dal provider è 75%."
        ),
    )

    async def decide(goal_payload, *, what_happened, already_said, language="it"):
        assert "75%" in str(what_happened)
        assert "external_research" in str(what_happened)
        return {
            "outcome": "inform_user",
            "headline": (
                "È aumentato il rischio di pioggia nel luogo della situazione: "
                "conviene controllarla adesso."
            ),
            "reasoning": (
                "La nuova evidenza meteo può cambiare concretamente cosa conviene fare."
            ),
            "about": "rischio pioggia per la situazione temporanea",
        }

    monkeypatch.setattr(reasoning, "decide_visibility", decide)
    show = AsyncMock(return_value=True)
    offer = AsyncMock(return_value=None)
    monkeypatch.setattr(service.visibility, "show", show)
    monkeypatch.setattr(service.needs, "offer_to_delivery", offer)

    decision = await service._consider_visibility(
        OWNER,
        goal.id,
        run,
        AgentBudget(),
        language="it",
    )

    assert decision is not None
    assert decision.outcome == "inform_user"
    assert "pioggia" in decision.headline.lower()
    show.assert_awaited_once()

    need = await db.agent_needs.find_one(
        {"owner_id": OWNER, "goal_id": goal.id},
        {"_id": 0},
    )
    assert need is not None
    assert need["kind"] == "useful_result"
    assert "pioggia" in need["summary"].lower()
    assert need["source_refs"], "a useful update must keep proof handles"
    offer.assert_awaited_once()
