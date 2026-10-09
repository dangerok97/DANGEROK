"""Regression for Vibo Marina 20/09/2026 disagreement still shown on 09/10.

A disagreement can have time_sensitivity='changing' and no valid_until.
The underlying owner-owned calendar event, not the model's "42 days", decides.
"""
from datetime import datetime, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import AutonomousGoal, CommunicationNeed
from agent.service import AgentService
from delivery.models import DeliveryPlan
from delivery.service import DeliveryService
from opportunities.models import EvidenceRef, Opportunity
from opportunities.snapshot import _disagreements
from opportunities.surfacing import SurfacingService


OWNER = "fixture_owner"
END = "2026-09-20T21:00:00+02:00"


async def setup(db, *, owner=OWNER, when=END, sensitivity="changing"):
    # Source on the calendar; older than the alert created on 8 October.
    await db.ingestion_events.insert_one({
        "user_id": owner,
        "source_record_type": "calendar_event",
        "external_id": "vibo_evt_2026",
        "ingestion_status": "active",
        "source_status": "connected",
        "ingested_at": "2026-09-16T11:00:00+00:00",
        "normalized_payload": {
            "title": "Viaggio a Vibo Marina",
            "starts_at": ("2030-09-20T18:00:00+02:00" if when.startswith("2030") else "2026-09-20T18:00:00+02:00"),
            "ends_at": when,
            "status": "confirmed",
        },
    })
    await db.connected_situation_links.insert_one({
        "id": "link_vibo_2026", "owner_id": owner,
        "target_kind": "appointment", "target_ref": "vibo_evt_2026",
        "source_type": "email", "source_object_ref": "message_mock",
        "disagreements": [{
            "what_this_source_says": "Partenza alle 17",
            "what_the_other_says": "Partenza alle 18",
        }],
        "decided_at": "2026-10-08T10:00:00+00:00",
    })
    opportunity = Opportunity(
        id="opp_vibo_fixture", owner_id=owner,
        identity_key="two_times_vibo_2026",
        status="active", surface_state="surfaced",
        time_sensitivity=sensitivity,
        semantic_summary="Orari contrastanti per il viaggio a Vibo Marina",
        why_it_matters="Chiarire prima della partenza",
        why_now="La data si avvicina (42 giorni)",
        evidence=[EvidenceRef(kind="disagreement", ref="link_vibo_2026")],
        created_at="2026-10-08T13:00:00+02:00",
    )
    await db.opportunities.insert_one(opportunity.model_dump())
    goal = AutonomousGoal(
        id="gol_vibo_fixture", owner_id=owner,
        status="waiting", origin="agent_initiated",
        source_kind="opportunity", opportunity_id=opportunity.id,
        source_refs=["link_vibo_2026", "calendar:vibo_evt_2026"],
        objective="Risolvere due orari contrastanti del viaggio",
        desired_outcome="Confermare l'orario prima di partire",
        created_at="2026-10-08T14:00:00+02:00",
        requires_user_input=True,
    )
    await db.agent_goals.insert_one(goal.model_dump())
    need = CommunicationNeed(
        id="ned_vibo_fixture", owner_id=owner, goal_id=goal.id,
        kind="needs_information", summary=(
            "Il viaggio a Vibo Marina (20/09/2026) ha ancora due orari "
            "contrastanti nel calendario: confermare quale sia corretto prima di agire."
        ), requires_response=True,
    )
    await db.agent_needs.insert_one(need.model_dump())
    return opportunity, goal, need


@pytest.mark.asyncio
async def test_stale_disagreement_is_not_raised_or_shown_after_actual_event():
    db = AsyncMongoMockClient().vibo_fixture
    opp, goal, _ = await setup(db)
    # Same day as the screenshot, but source expired weeks before it.
    rows = await _disagreements(
        db, OWNER, datetime(2026, 10, 9, 12, 22, tzinfo=timezone.utc),
    )
    assert rows == [], "historic conflict must not enter a fresh LLM scan"
    surfacing = SurfacingService(db)
    assert not await surfacing._current(
        OWNER, opp, "2026-10-09T12:22:00+00:00"
    ), "AI's wrong 'changing' label must not override calendar end"
    agent = AgentService(db)
    assert await agent.for_detail(OWNER, goal.id) is None
    assert await agent.for_home(OWNER) == []


@pytest.mark.asyncio
async def test_stale_source_blocks_push_for_both_opportunity_and_need():
    db = AsyncMongoMockClient().vibo_notifications
    opp, goal, need = await setup(db)
    service = DeliveryService(db)
    about_source = DeliveryPlan(owner_id=OWNER, source_type="opportunity",
                                source_id=opp.id, mode="push")
    about_need = DeliveryPlan(owner_id=OWNER, source_type="agent_need",
                              source_id=need.id, mode="push")
    assert await service._current_subject_for_plan(OWNER, about_source) is None
    assert await service._current_subject_for_plan(OWNER, about_need) is None


@pytest.mark.asyncio
async def test_no_foreign_calendar_data_or_future_trip_false_expiry():
    db = AsyncMongoMockClient().vibo_future
    opp, goal, _ = await setup(db, owner=OWNER, when="2030-09-20T21:00:00+02:00")
    assert await SurfacingService(db)._current(
        OWNER, opp, "2026-10-09T12:00:00+00:00"
    ), "a future event may still require a decision"
    assert await AgentService(db).for_detail(OWNER, goal.id) is not None
    assert await AgentService(db).for_detail("foreign-owner", goal.id) is None
    assert len(await _disagreements(
        db, OWNER, datetime(2026, 10, 9, 12, tzinfo=timezone.utc)
    )) == 1


@pytest.mark.asyncio
async def test_old_goal_wake_retired_without_any_external_action():
    db = AsyncMongoMockClient().vibo_retire
    _, goal, need = await setup(db)
    agent = AgentService(db)
    # A blocked task must be invalidated before a planner can execute it.
    result = await agent.advance(OWNER, goal.id)
    assert result.get("state") == "source_expired"
    stored = await db.agent_goals.find_one({"owner_id": OWNER, "id": goal.id})
    assert stored["status"] == "abandoned"
    assert not stored.get("next_run_at")
    other = await db.agent_needs.find_one({"owner_id": OWNER, "id": need.id})
    assert other["status"] != "open"


@pytest.mark.asyncio
async def test_old_update_url_and_actions_respond_gone_not_prepare(monkeypatch):
    import deps
    from fastapi import HTTPException
    from opportunities.router import one, read_update_work, begin_update_work, UpdateWorkIn
    from agent.router import need as read_need
    db = AsyncMongoMockClient().vibo_deeplink
    _, _, need = await setup(db)
    monkeypatch.setattr(deps, "db", db)
    for invoke in [
        one("opp_vibo_fixture", user={"user_id": OWNER}),
        read_update_work("opp_vibo_fixture", user={"user_id": OWNER}),
        begin_update_work("opp_vibo_fixture", UpdateWorkIn(reply="si"),
                          user={"user_id": OWNER}),
        read_need(need.id, user={"user_id": OWNER}),
    ]:
        with pytest.raises(HTTPException) as err:
            await invoke
        assert err.value.status_code == 410
    assert await db.update_work.count_documents({}) == 0


@pytest.mark.asyncio
async def test_missing_calendar_source_is_held_without_deleting_old_data():
    db = AsyncMongoMockClient().vibo_disconnected
    opp, goal, need = await setup(db)
    await db.ingestion_events.delete_many({"user_id": OWNER})
    # Disconnection or retention must not make a stale question actionable.
    assert await _disagreements(
        db, OWNER, datetime(2026, 10, 9, 12, tzinfo=timezone.utc)
    ) == []
    assert not await SurfacingService(db)._current(
        OWNER, opp, "2026-10-09T12:22:00+00:00"
    )
    assert await AgentService(db).for_detail(OWNER, goal.id) is None
    assert await db.opportunities.count_documents({"owner_id": OWNER}) == 1
    assert await db.agent_needs.count_documents({"owner_id": OWNER}) == 1
    # Another user's copy with the same external id cannot make this source
    # magically available to the owner of the stale notification.
    await db.ingestion_events.insert_one({
        "user_id": "another_owner", "source_record_type": "calendar_event",
        "external_id": "vibo_evt_2026", "ingestion_status": "active",
        "normalized_payload": {"starts_at": "2030-09-20T17:00:00+02:00"}
    })
    assert not await SurfacingService(db)._current(
        OWNER, opp, "2026-10-09T12:22:00+00:00"
    )
