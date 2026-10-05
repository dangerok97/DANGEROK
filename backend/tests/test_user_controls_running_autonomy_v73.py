from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import ActionPlan, ActionStep, AutonomousGoal, CommunicationNeed
from agent.needs import NeedService
from agent.repository import AgentRepository
from ambient.service import AmbientService
from opportunities.models import Opportunity
from opportunities.repository import OpportunityRepository
from opportunities.service import OpportunityService
from opportunities.surfacing import SurfacingService


OWNER = "alice"


async def setup_running_goal(db):
    opp = await OpportunityRepository(db).save(
        Opportunity(
            owner_id=OWNER,
            identity_key="user-control-test",
            status="active",
            semantic_summary="Una situazione su cui ORA sta già lavorando",
            why_it_matters="Serve verificare le conseguenze",
            initiative="prepare",
        )
    )
    goal = AutonomousGoal(
        owner_id=OWNER,
        status="active",
        objective="Verificare la situazione",
        desired_outcome="Avere un risultato utile e verificato",
        opportunity_id=opp.id,
        next_run_at=datetime.now(timezone.utc).isoformat(),
    )
    repo = AgentRepository(db)
    await repo.ensure_indexes()
    assert await repo.create_goal(goal) is not None
    await repo.save_plan(
        ActionPlan(
            owner_id=OWNER,
            goal_id=goal.id,
            status="active",
            plan_summary="Continuare la verifica",
            expected_outcome="Arrivare a una conclusione verificata",
            steps=[
                ActionStep(
                    ordinal=0,
                    intent="Rileggere i fatti disponibili",
                    step_type="inspect",
                    status="pending",
                )
            ],
        )
    )
    old_wake = await AmbientService(db).schedule(
        OWNER,
        reason="opportunity_revisit",
        when=datetime.now(timezone.utc) + timedelta(minutes=5),
        source_ref=f"goal:{goal.id}",
        provenance="code_schedule",
    )
    assert old_wake is not None
    return opp, goal, old_wake


@pytest.mark.asyncio
async def test_defer_moves_existing_goal_and_wake_to_same_moment(monkeypatch):
    db = AsyncMongoMockClient().test
    opp, goal, old_wake = await setup_running_goal(db)

    monkeypatch.setattr(
        "opportunities.reasoning.decide_revisit",
        AsyncMock(return_value={
            "revisit_in_hours": 3,
            "rationale": "Tre ore tengono il lavoro fuori dai piedi senza farlo scadere.",
        }),
    )

    result = await SurfacingService(db).defer(OWNER, opp.id)

    assert result["ok"] is True
    assert result["goal_deferred"] is True

    saved_goal = await AgentRepository(db).get_goal(OWNER, goal.id)
    assert saved_goal is not None
    assert saved_goal.status == "waiting"
    assert saved_goal.next_run_at == result["deferred_until"]

    plan = await AgentRepository(db).plan_for(OWNER, goal.id)
    assert plan is not None and plan.status == "waiting"

    old = await db.ambient_wakes.find_one({"id": old_wake.id}, {"_id": 0})
    assert old["status"] == "cancelled"

    pending = await db.ambient_wakes.find_one({
        "owner_id": OWNER,
        "source_ref": f"goal:{goal.id}",
        "status": "pending",
    }, {"_id": 0})
    assert pending is not None
    assert pending["scheduled_for"] == result["deferred_until"]

    # A worker that started before the tap may still hold an old object. Its
    # later save must not erase the person's newer "più tardi".
    goal.status = "active"
    goal.next_run_at = datetime.now(timezone.utc).isoformat()
    goal.user_deferred_until = None
    await AgentRepository(db).save_goal(goal)
    protected = await AgentRepository(db).get_goal(OWNER, goal.id)
    assert protected is not None
    assert protected.status == "waiting"
    assert protected.next_run_at == result["deferred_until"]
    assert protected.user_deferred_until == result["deferred_until"]


@pytest.mark.asyncio
async def test_defer_does_not_create_background_work_for_goal_waiting_on_person(monkeypatch):
    db = AsyncMongoMockClient().test
    opp, goal, old_wake = await setup_running_goal(db)

    repo = AgentRepository(db)
    goal = await repo.get_goal(OWNER, goal.id)
    goal.status = "waiting"
    goal.requires_user_input = True
    goal.next_run_at = None
    await repo.save_goal(goal)
    await db.ambient_wakes.update_one(
        {"id": old_wake.id},
        {"$set": {"status": "cancelled"}},
    )

    monkeypatch.setattr(
        "opportunities.reasoning.decide_revisit",
        AsyncMock(return_value={"revisit_in_hours": 2, "rationale": "Più tardi."}),
    )

    result = await SurfacingService(db).defer(OWNER, opp.id)

    assert result["ok"] is True
    assert result["goal_deferred"] is False
    saved_goal = await repo.get_goal(OWNER, goal.id)
    assert saved_goal.status == "waiting"
    assert saved_goal.requires_user_input is True
    assert saved_goal.next_run_at is None
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER,
        "source_ref": f"goal:{goal.id}",
        "status": "pending",
    }) == 0


@pytest.mark.asyncio
async def test_dismiss_cancels_linked_goal_plan_wake_and_need():
    db = AsyncMongoMockClient().test
    opp, goal, old_wake = await setup_running_goal(db)

    needs = NeedService(db)
    await needs.ensure_indexes()
    need = await needs.raise_need(
        CommunicationNeed(
            owner_id=OWNER,
            goal_id=goal.id,
            kind="needs_information",
            summary="Mi serve una risposta.",
            requires_response=True,
            response_kind="information",
            what_is_missing="Una risposta.",
        )
    )

    result = await OpportunityService(db).dismiss(OWNER, opp.id)

    assert result["ok"] is True
    assert result["status"] == "dismissed"
    assert result["goal_cancelled"] is True

    saved_goal = await AgentRepository(db).get_goal(OWNER, goal.id)
    assert saved_goal is not None and saved_goal.status == "cancelled"
    plan = await AgentRepository(db).plan_for(OWNER, goal.id)
    assert plan is not None and plan.status == "cancelled"
    wake = await db.ambient_wakes.find_one({"id": old_wake.id}, {"_id": 0})
    assert wake["status"] == "cancelled"
    saved_need = await needs.get(OWNER, need.id)
    assert saved_need is not None and saved_need.status == "cancelled"
