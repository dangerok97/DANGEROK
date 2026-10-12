"""Planning outages preserve owned work and its durable, bounded continuation."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from mongomock_motor import AsyncMongoMockClient

from agent import reasoning
from agent.admission import drain
from agent.background import advance_wake, recover_due
from agent.models import AutonomousGoal
from agent.service import AgentService, MAX_PLANNING_ATTEMPTS, PLANNING_RETRY_SECONDS
from ambient.models import AmbientWake
from opportunities.models import Opportunity
from opportunities.repository import OpportunityRepository

OWNER = "planning-recovery-synthetic-owner"
PLAN = {
    "planning_outcome": "plan", "plan_summary": "Rivalutare una fonte al momento utile.",
    "steps": [{"step_type": "wait", "intent": "Attendere un aggiornamento della fonte",
               "parameters": {"wait_minutes": 15}}],
}


@pytest_asyncio.fixture
async def setup(monkeypatch):
    db = AsyncMongoMockClient().planning_recovery_v162
    service = AgentService(db)
    await service.ensure_indexes()
    await OpportunityRepository(db).ensure_indexes()
    # Isolate model/network boundaries, while retaining the real goal/wake path.
    monkeypatch.setattr(AgentService, "_consider_visibility", AsyncMock())
    monkeypatch.setattr(AgentService, "_note_ambient", AsyncMock())
    return db, service


async def admit(db, monkeypatch):
    opportunity = Opportunity(
        owner_id=OWNER, identity_key="v162:planning-recovery", status="active",
        semantic_summary="Una fonte richiede una verifica", why_it_matters="Preparare un esito fondato",
        what_ora_can_do="Verificare la fonte", initiative="prepare",
    )
    await OpportunityRepository(db).save(opportunity)
    monkeypatch.setattr(reasoning, "decide_goal", AsyncMock(return_value={
        "outcome": "create_goal", "objective": "Verificare la fonte",
        "desired_outcome": "Una conclusione sostenuta dalle fonti",
        "success_criteria": ["Conclusione disponibile con i suoi limiti"],
    }))
    await drain(db, owner_id=OWNER, limit=1)
    row = await db.agent_goals.find_one({"owner_id": OWNER})
    assert row is not None
    wake = AmbientWake.model_validate(await db.ambient_wakes.find_one({
        "owner_id": OWNER, "source_ref": f"goal:{row['id']}",
    }))
    return opportunity, AutonomousGoal.model_validate(row), wake


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [
    None, TimeoutError("synthetic network timeout"), "invalid JSON value",
    {"steps": []}, {"steps": [{"step_type": "unknown", "intent": "Invalid"}]},
    {"planning_outcome": "not_possible", "reasoning": "", "steps": []},
    {"planning_outcome": "not_possible", "reasoning": "Conflicting response", "steps": PLAN["steps"]},
])
async def test_admitted_work_recovers_from_unavailable_or_invalid_plan(setup, monkeypatch, failure):
    db, service = setup
    opportunity, goal, wake = await admit(db, monkeypatch)
    planner = AsyncMock(side_effect=[failure, PLAN])
    monkeypatch.setattr(reasoning, "make_plan", planner)
    before = datetime.now(timezone.utc)
    first = await advance_wake(db, wake)
    current = await service.repo.get_goal(OWNER, goal.id)
    assert first.result == "planning_retry_scheduled"
    assert current.is_open and current.status == "active"
    assert current.planning_unavailable and current.planning_attempts == 1
    assert current.background_runs == 0
    assert not current.requires_user_input and not current.requires_user_authority
    due = datetime.fromisoformat(current.next_run_at)
    assert 59 <= (due - before).total_seconds() < 65
    assert await service.for_home(OWNER) == []  # a retry is not a result or an alarm
    admission = await db.opportunities.find_one({"id": opportunity.id})
    assert admission["agent_review_state"] == "settled"
    assert await service.repo.plan_for(OWNER, goal.id) is None

    # An early replay obeys the durable time instead of buying another call.
    assert (await advance_wake(db, wake)).result == "goal_not_due"
    assert planner.await_count == 1

    # Simulate a process restart and a missing accelerator. Existing recovery
    # rebuilds the wake from the goal, with no new opportunity or admission.
    await db.ambient_wakes.delete_many({"owner_id": OWNER})
    await db.agent_goals.update_one({"id": goal.id}, {"$set": {
        "next_run_at": (before - timedelta(seconds=1)).isoformat(),
    }})
    assert await recover_due(db, now=before, admit=False) == 1
    resumed_wake = AmbientWake.model_validate(await db.ambient_wakes.find_one({"owner_id": OWNER}))
    resumed = await advance_wake(db, resumed_wake)
    current = await AgentService(db).repo.get_goal(OWNER, goal.id)
    assert resumed.result == "waiting"
    assert current.is_open and current.next_run_at
    assert not current.planning_unavailable and current.planning_attempts == 0
    assert planner.await_count == 2
    assert await db.agent_goals.count_documents({"owner_id": OWNER}) == 1
    assert await db.agent_plans.count_documents({"owner_id": OWNER}) == 1
    assert await db.communication_needs.count_documents({"owner_id": OWNER}) == 0


@pytest.mark.asyncio
async def test_exhaustion_is_visible_and_cannot_be_reset_by_another_worker(setup, monkeypatch):
    db, service = setup
    _, goal, _ = await admit(db, monkeypatch)
    planner = AsyncMock(return_value=None)
    monkeypatch.setattr(reasoning, "make_plan", planner)
    for attempt in range(1, MAX_PLANNING_ATTEMPTS + 1):
        before = datetime.now(timezone.utc)
        result = await AgentService(db).advance(OWNER, goal.id, worker_id="ambient:restart")
        current = await service.repo.get_goal(OWNER, goal.id)
        assert current.planning_attempts == attempt and current.is_open
        if attempt < MAX_PLANNING_ATTEMPTS:
            assert result["state"] == "planning_retry_scheduled"
            seconds = (datetime.fromisoformat(current.next_run_at) - before).total_seconds()
            assert PLANNING_RETRY_SECONDS[attempt - 1] - 1 <= seconds < PLANNING_RETRY_SECONDS[attempt - 1] + 5
        else:
            assert result["state"] == "planning_unavailable" and current.next_run_at is None
    result = await AgentService(db).advance(OWNER, goal.id, worker_id="ambient:stale-wake")
    assert result["state"] == "planning_unavailable"
    assert planner.await_count == MAX_PLANNING_ATTEMPTS
    cards = await service.for_home(OWNER)
    assert len(cards) == 1 and cards[0]["id"] == goal.id
    assert cards[0]["retry_available"] and cards[0]["planning_unavailable"]
    assert "sospesa" in cards[0]["problem"]
    assert cards[0]["needs_you"] == ""
    assert "Proseguo da sola" not in cards[0]["next_step"]
    assert await db.communication_needs.count_documents({"owner_id": OWNER}) == 0


@pytest.mark.asyncio
async def test_valid_negative_judgement_is_not_a_provider_outage(setup, monkeypatch):
    db, service = setup
    _, goal, wake = await admit(db, monkeypatch)
    reason = "L'esito richiede una capacità che ORA non possiede e non esiste un percorso preparatorio utile."
    planner = AsyncMock(return_value={"planning_outcome": "not_possible", "reasoning": reason, "steps": []})
    monkeypatch.setattr(reasoning, "make_plan", planner)
    result = await advance_wake(db, wake)
    current = await service.repo.get_goal(OWNER, goal.id)
    assert result.result == "failed"
    assert not current.is_open and not current.planning_unavailable
    assert current.next_run_at is None and current.rationale == reason
    assert current.completed_at is None
    assert await service.repo.plan_for(OWNER, goal.id) is None
    assert any(row["kind"] == "planning_not_possible" for row in await service.repo.history(OWNER, goal.id))
    assert (await advance_wake(db, wake)).result == "goal_closed"
    assert planner.await_count == 1


@pytest.mark.asyncio
async def test_interrupted_planning_preserves_budget_and_recovery(setup, monkeypatch):
    db, service = setup
    _, goal, _ = await admit(db, monkeypatch)
    planner = AsyncMock(side_effect=asyncio.CancelledError())
    monkeypatch.setattr(reasoning, "make_plan", planner)
    with pytest.raises(asyncio.CancelledError):
        await service.advance(OWNER, goal.id, worker_id="ambient:interrupted")
    current = await service.repo.get_goal(OWNER, goal.id)
    assert current.planning_attempts == 1 and current.next_run_at and current.is_open
    assert current.background_runs == 0
    assert await service.repo.plan_for(OWNER, goal.id) is None
    planner.side_effect = None
    planner.return_value = None
    await AgentService(db).advance(OWNER, goal.id, worker_id="ambient:replacement")
    assert (await service.repo.get_goal(OWNER, goal.id)).planning_attempts == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["cancel", "revision"])
async def test_inflight_plan_cannot_outlive_its_source(setup, monkeypatch, change):
    db, service = setup
    opportunity, goal, _ = await admit(db, monkeypatch)
    async def during_plan(*args, **kwargs):
        if change == "cancel":
            await AgentService(db).cancel(OWNER, goal.id, reason="Caso sintetico concluso")
        else:
            opportunity.why_now = "Una nuova informazione modifica la verifica"
            await OpportunityRepository(db).save(opportunity)
        return PLAN
    monkeypatch.setattr(reasoning, "make_plan", during_plan)
    result = await service.advance(OWNER, goal.id, worker_id="ambient:stale-plan")
    current = await service.repo.get_goal(OWNER, goal.id)
    assert result["state"] == ("cancelled" if change == "cancel" else "source_changed")
    assert await service.repo.plan_for(OWNER, goal.id) is None
    if change == "cancel":
        assert current.next_run_at is None
        assert await db.ambient_wakes.count_documents({"owner_id": OWNER, "status": {"$in": ["pending", "claimed"]}}) == 0
    else:
        assert current.planning_attempts == 0 and not current.planning_unavailable
        assert current.next_run_at and current.is_open


@pytest.mark.asyncio
async def test_changed_source_resets_exhausted_retry_without_recreating_the_goal(setup, monkeypatch):
    db, service = setup
    opportunity, goal, _ = await admit(db, monkeypatch)
    await db.agent_goals.update_one({"id": goal.id}, {"$set": {
        "planning_attempts": MAX_PLANNING_ATTEMPTS, "planning_unavailable": True, "next_run_at": None,
    }})
    opportunity.why_now = "La fonte ora include un nuovo elemento utile"
    await OpportunityRepository(db).save(opportunity)
    planner = AsyncMock(return_value=PLAN)
    monkeypatch.setattr(reasoning, "make_plan", planner)
    result = await service.advance(OWNER, goal.id, worker_id="ambient:updated-source")
    current = await service.repo.get_goal(OWNER, goal.id)
    assert result["state"] == "waiting"
    assert current.planning_attempts == 0 and not current.planning_unavailable
    assert await db.agent_goals.count_documents({"owner_id": OWNER}) == 1
    planner.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_endpoint_is_owned_idempotent_and_grants_no_authority(setup, monkeypatch):
    db, service = setup
    import deps
    from agent.router import router
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[deps.get_current_user] = lambda: {"user_id": OWNER}
    monkeypatch.setattr(deps, "db", db)
    monkeypatch.delenv("DEV", raising=False)
    suspended = AutonomousGoal(
        owner_id=OWNER, objective="Preparare una verifica", desired_outcome="Un esito utile", status="active",
        planning_attempts=MAX_PLANNING_ATTEMPTS, planning_unavailable=True,
    )
    await service.repo.save_goal(suspended)
    foreign = suspended.model_copy(update={"id": "foreign-goal", "owner_id": "another-owner"})
    await service.repo.save_goal(foreign)
    normal = suspended.model_copy(update={"id": "normal-goal", "planning_unavailable": False})
    await service.repo.save_goal(normal)
    closed = suspended.model_copy(update={"id": "closed-goal", "status": "completed"})
    await service.repo.save_goal(closed)
    authority = suspended.model_copy(update={"id": "authority-goal", "requires_user_authority": True})
    await service.repo.save_goal(authority)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://synthetic") as client:
        assert (await client.post("/agent/foreign-goal/retry")).status_code == 404
        for goal_id in ("normal-goal", "closed-goal", "authority-goal"):
            assert (await client.post(f"/agent/{goal_id}/retry")).status_code == 409
        assert await db.ambient_wakes.count_documents({}) == 0
        first = await client.post(f"/agent/{suspended.id}/retry")
        again = await client.post(f"/agent/{suspended.id}/retry")
    assert first.status_code == again.status_code == 200
    assert first.json()["state"] == "planning_retry_scheduled"
    assert again.json()["state"] == "already_scheduled"
    current = await service.repo.get_goal(OWNER, suspended.id)
    assert current.planning_attempts == 0 and current.next_run_at
    assert not (await service.for_detail(OWNER, suspended.id))["retry_available"]
    assert await db.ambient_wakes.count_documents({"source_ref": f"goal:{suspended.id}"}) == 1
    assert (await service.repo.get_goal(OWNER, authority.id)).requires_user_authority
    assert await db.agent_consents.count_documents({}) == 0
    assert await db.communication_needs.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("response,expected", [
    ({"planning_outcome": "not_possible", "reasoning": "Manca una capacità necessaria", "steps": []}, True),
    ({"planning_outcome": "not_possible", "reasoning": "", "steps": []}, False),
    ({"steps": []}, False),
    (PLAN, True),
])
async def test_model_boundary_preserves_only_a_structured_negative(monkeypatch, response, expected):
    monkeypatch.setattr(reasoning, "_ask_model", AsyncMock(return_value=response))
    result = await reasoning.make_plan({}, capabilities=[], context={})
    assert (result is not None) is expected
