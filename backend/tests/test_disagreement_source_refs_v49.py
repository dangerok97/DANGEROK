from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.service import AgentService
from agent.source_refs import expand_opportunity_source_refs
from opportunities.models import EvidenceRef, Opportunity
from opportunities.repository import OpportunityRepository


def _opp(owner="alice"):
    return Opportunity(
        owner_id=owner,
        identity_key="calendar_disagreement:test",
        status="active",
        semantic_summary="Mail e calendario non concordano sull'orario.",
        why_it_matters="L'appuntamento potrebbe richiedere una correzione.",
        initiative="prepare",
        evidence=[
            EvidenceRef(
                kind="disagreement",
                ref="link_1",
                summary="Due fonti dicono orari diversi.",
            )
        ],
    )


async def _link(db, owner="alice"):
    await db.connected_situation_links.insert_one({
        "id": "link_1",
        "owner_id": owner,
        "source_type": "email",
        "source_object_ref": "m1",
        "relationship": "same_situation",
        "target_kind": "appointment",
        "target_ref": "event_123",
    })


@pytest.mark.asyncio
async def test_disagreement_ref_expands_to_exact_mail_and_calendar_handles():
    db = AsyncMongoMockClient().test
    await _link(db)

    refs = await expand_opportunity_source_refs(
        db,
        "alice",
        [{"kind": "disagreement", "ref": "link_1"}],
    )

    assert refs == ["link_1", "mail:m1", "calendar:event_123"]


@pytest.mark.asyncio
async def test_disagreement_expansion_is_owner_scoped():
    db = AsyncMongoMockClient().test
    await _link(db, owner="bob")

    refs = await expand_opportunity_source_refs(
        db,
        "alice",
        [{"kind": "disagreement", "ref": "link_1"}],
    )

    assert refs == ["link_1"]
    assert "mail:m1" not in refs
    assert "calendar:event_123" not in refs


@pytest.mark.asyncio
async def test_admission_passes_expanded_handles_to_agent(monkeypatch):
    from agent.admission import drain

    db = AsyncMongoMockClient().test
    await _link(db)
    row = await OpportunityRepository(db).save(_opp())

    decide = AsyncMock(return_value={"outcome": "no_goal"})
    monkeypatch.setattr(AgentService, "consider", decide)

    await drain(db, owner_id="alice", limit=1)

    decide.assert_awaited_once()
    refs = decide.await_args.kwargs["source_refs"]
    assert refs == ["link_1", "mail:m1", "calendar:event_123"]
    assert decide.await_args.kwargs["opportunity_id"] == row.id


@pytest.mark.asyncio
async def test_source_refresh_keeps_expanded_handles():
    from agent.models import AutonomousGoal
    from agent.source_refresh import refresh

    db = AsyncMongoMockClient().test
    await _link(db)
    opp = await OpportunityRepository(db).save(_opp())
    row = await db.opportunities.find_one({"id": opp.id}, {"_id": 0})

    service = AgentService(db)
    goal = AutonomousGoal(
        owner_id="alice",
        status="active",
        origin="agent_initiated",
        objective="Correggere l'appuntamento",
        desired_outcome="Calendario coerente con la comunicazione verificata",
        opportunity_id=opp.id,
        opportunity_revision="old_revision",
        source_refs=["link_1"],
    )
    await service.repo.create_goal(goal)

    changed = await refresh(service, goal)

    assert changed is True
    assert goal.source_refs == ["link_1", "mail:m1", "calendar:event_123"]
    assert goal.opportunity_revision == row["agent_review_revision"]


@pytest.mark.asyncio
async def test_calendar_prefixed_google_ref_is_reread_for_goal_context(monkeypatch):
    from agent import reasoning
    from opportunities import snapshot

    db = AsyncMongoMockClient().test
    service = AgentService(db)

    calendar = AsyncMock(return_value=[{
        "ref": "event_123",
        "title": "Dentista",
        "starts_at": "2026-10-06T15:00:00+02:00",
        "ends_at": "2026-10-06T16:00:00+02:00",
        "timezone": "Europe/Rome",
        "location": "Studio dentistico",
        "preparation_notes": "",
        "all_day": False,
    }])
    monkeypatch.setattr(snapshot, "_calendar", calendar)

    decide = AsyncMock(return_value={
        "outcome": "no_goal",
        "reasoning": "Test contesto",
    })
    monkeypatch.setattr(reasoning, "decide_goal", decide)

    out = await service.consider(
        "alice",
        situation={"what": "L'orario potrebbe essere cambiato."},
        source_kind="opportunity",
        source_refs=["calendar:event_123"],
    )

    assert out["outcome"] == "no_goal"
    shown = decide.await_args.args[0]
    assert shown["source_context"][0]["ref"] == "event_123"
    assert shown["source_context"][0]["title"] == "Dentista"
    assert shown["source_context_unavailable"] is False
