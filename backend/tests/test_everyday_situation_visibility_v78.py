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


async def _weather_goal(db, *, rain_pct: int):
    service = AgentService(db)
    goal = AutonomousGoal(
        id=f"goal_weather_visibility_{rain_pct}",
        owner_id=OWNER,
        status="waiting",
        objective="Seguire una situazione temporanea all'aperto",
        desired_outcome=(
            "Rivalutare la situazione quando condizioni esterne possono "
            "cambiare ciò che conviene fare"
        ),
        source_kind="opportunity",
        source_refs=["situation:sit_laundry_v78", "place:home_v78"],
    )
    await service.repo.save_goal(goal)
    await service.evidence.record(
        AgentEvidence(
            owner_id=OWNER,
            goal_id=goal.id,
            step_id="weather_check",
            kind="inspect",
            claim=(
                "Nelle prossime ore la probabilità massima di pioggia "
                f"indicata dal provider è {rain_pct}%."
            ),
            supports="rischio di pioggia nelle prossime ore",
            provenance=ResultProvenance(
                source_class="external_research",
                capability="weather.read",
                provider="open_meteo",
                source_refs=["place:home_v78"],
                freshness="fresh",
            ),
        )
    )
    return service, goal


@pytest.mark.asyncio
async def test_ordinary_followup_stays_silent_when_fresh_evidence_changes_nothing(monkeypatch):
    """
    v78 negative Reality Gate:
    useful autonomous checking is allowed to end in true silence.

    The production path is domain-neutral: the visibility model receives real
    evidence and decides whether it changes anything worth saying.
    """
    from agent import reasoning
    from delivery.service import DeliveryService

    db = AsyncMongoMockClient().test
    service, goal = await _weather_goal(db, rain_pct=10)

    async def visibility_model(system, user):
        assert "10%" in user
        assert "silent" in system
        return {
            "outcome": "silent",
            "headline": "",
            "reasoning": "Le condizioni non cambiano ciò che serve fare adesso.",
            "about": "situazione temporanea",
        }

    monkeypatch.setattr(reasoning, "_ask_model", visibility_model)
    note_activity = AsyncMock()
    monkeypatch.setattr(DeliveryService, "note_activity", note_activity)
    offered = AsyncMock()
    monkeypatch.setattr(service.needs, "offer_to_delivery", offered)

    result = await service._consider_visibility(
        OWNER,
        goal.id,
        AgentRun(owner_id=OWNER, goal_id=goal.id, background=True),
        AgentBudget(),
        language="it",
    )

    assert result is not None
    assert result.outcome == "silent"
    assert await db.agent_needs.count_documents(
        {"owner_id": OWNER, "goal_id": goal.id}
    ) == 0
    note_activity.assert_not_awaited()
    offered.assert_not_awaited()
    assert await db.agent_updates.count_documents({"owner_id": OWNER}) == 0


@pytest.mark.asyncio
async def test_material_weather_change_becomes_evidence_backed_user_update(monkeypatch):
    """
    v78 positive Reality Gate:
    when fresh evidence materially changes what is useful, ORA surfaces one
    concise update and hands the need to delivery instead of merely logging it.
    """
    from agent import reasoning
    from delivery.service import DeliveryService

    db = AsyncMongoMockClient().test
    service, goal = await _weather_goal(db, rain_pct=80)

    async def visibility_model(system, user):
        assert "80%" in user
        assert "inform_user" in system
        return {
            "outcome": "inform_user",
            "headline": (
                "La pioggia è diventata abbastanza probabile da rendere utile "
                "ricontrollare la situazione adesso."
            ),
            "reasoning": (
                "La nuova previsione cambia concretamente ciò che conviene "
                "valutare nel breve periodo."
            ),
            "about": "cambio meteo rilevante per la situazione",
        }

    monkeypatch.setattr(reasoning, "_ask_model", visibility_model)
    note_activity = AsyncMock(return_value=True)
    monkeypatch.setattr(DeliveryService, "note_activity", note_activity)
    offered = AsyncMock(return_value=None)
    monkeypatch.setattr(service.needs, "offer_to_delivery", offered)

    result = await service._consider_visibility(
        OWNER,
        goal.id,
        AgentRun(owner_id=OWNER, goal_id=goal.id, background=True),
        AgentBudget(),
        language="it",
    )

    assert result is not None
    assert result.outcome == "inform_user"
    assert result.headline
    assert result.refs, "a visible update must have real proof behind it"
    assert await db.agent_updates.count_documents(
        {"owner_id": OWNER, "goal_id": goal.id}
    ) == 1

    need = await db.agent_needs.find_one(
        {"owner_id": OWNER, "goal_id": goal.id}, {"_id": 0}
    )
    assert need is not None
    assert need["kind"] == "useful_result"
    assert "pioggia" in need["summary"].lower()
    assert need["source_refs"], "delivery must retain evidence handles"

    note_activity.assert_awaited_once()
    offered.assert_awaited_once()
    offered_need = offered.await_args.args[1]
    assert offered_need.goal_id == goal.id
    assert offered_need.summary == need["summary"]
