from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import AutonomousGoal
from agent.repository import AgentRepository
from opportunities.models import Opportunity
from opportunities.repository import OpportunityRepository
from opportunities.surfacing import SurfacingService


OWNER = "alice"


async def surfaced_opportunity(db):
    opp = Opportunity(
        owner_id=OWNER,
        identity_key="one-situation-one-card",
        status="active",
        semantic_summary="ORA ha notato una situazione da seguire",
        why_it_matters="Merita un controllo",
        initiative="prepare",
        surface_state="surfaced",
    )
    return await OpportunityRepository(db).save(opp)


async def add_goal(db, *, objective, created_at, opportunity_id=""):
    repo = AgentRepository(db)
    await repo.ensure_indexes()
    goal = AutonomousGoal(
        owner_id=OWNER,
        status="active",
        objective=objective,
        desired_outcome="Arrivare a un risultato verificato",
        opportunity_id=opportunity_id,
        created_at=created_at,
        next_run_at=datetime.now(timezone.utc).isoformat(),
    )
    assert await repo.create_goal(goal) is not None
    return goal


@pytest.mark.asyncio
async def test_visible_agent_work_replaces_its_source_opportunity_card():
    db = AsyncMongoMockClient().test
    opp = await surfaced_opportunity(db)
    now = datetime.now(timezone.utc)

    goal = await add_goal(
        db,
        objective="Seguire la situazione già notata",
        opportunity_id=opp.id,
        created_at=(now - timedelta(hours=3)).isoformat(),
    )

    visible = await SurfacingService(db).for_home(OWNER)
    assert visible == []

    open_goals = await AgentRepository(db).open_goals(OWNER, limit=3)
    assert [g.id for g in open_goals] == [goal.id]


@pytest.mark.asyncio
async def test_opportunity_stays_visible_when_linked_goal_is_outside_agent_work_limit():
    db = AsyncMongoMockClient().test
    opp = await surfaced_opportunity(db)
    now = datetime.now(timezone.utc)

    for i in range(3):
        await add_goal(
            db,
            objective=f"Altro lavoro {i}",
            created_at=(now - timedelta(hours=6 - i)).isoformat(),
        )
    linked = await add_goal(
        db,
        objective="Lavoro collegato ma quarto",
        opportunity_id=opp.id,
        created_at=now.isoformat(),
    )

    first_three = await AgentRepository(db).open_goals(OWNER, limit=3)
    assert linked.id not in {g.id for g in first_three}

    visible = await SurfacingService(db).for_home(OWNER)
    assert [row["id"] for row in visible] == [opp.id]
