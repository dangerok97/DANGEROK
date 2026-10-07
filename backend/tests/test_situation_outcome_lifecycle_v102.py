"""V102 — temporary Situation monitoring has an outcome and can end.

The monitoring goal may finish when it has reached and surfaced the useful action
moment. The real-world Situation remains until separately resolved; finishing the
watch must not pretend that the physical state changed.
"""
from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from ambient.eligibility import EligibilityService
from agent.models import ActionPlan, AgentRun
from agent.service import AgentService
from situations.followup import arrange_followup, read_followup, settle_completed_followup
from situations.models import SituationState
from situations.repository import SituationRepository

OWNER = "v102-owner"
SID = "sit_v102"


async def setup(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().test
    await db.agent_goals.create_index("id", unique=True)
    await db.agent_runs.create_index("goal_id", unique=True)
    await db.ambient_wakes.create_index("identity", unique=True)
    state = SituationState(
        id=SID,
        user_id=OWNER,
        summary="Una situazione temporanea è ancora in corso.",
        attention_intent="Capire quando arriva il momento utile per intervenire.",
        expected_outcome_summary="Arrivare al momento utile per concludere l'attività.",
        next_check_summary="Rivalutare più tardi.",
    )
    await SituationRepository(db).insert(state)
    return db, state


@pytest.mark.asyncio
async def test_notification_trigger_is_not_the_goal_outcome(monkeypatch):
    db, state = await setup(monkeypatch)
    due = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
    notify_when = "Se emerge un rischio che richiede attenzione."

    result = await arrange_followup(
        db, OWNER, situation_id=SID, expected_revision=state.revision,
        check_at=due, purpose="Rileggere le condizioni reali.",
        notify_when=notify_when,
    )
    assert result["ok"] is True
    goal = await db.agent_goals.find_one({"id": result["goal_id"]}, {"_id": 0})
    assert goal["desired_outcome"] != notify_when
    assert "conclusione utile" in goal["desired_outcome"]
    assert any("monitoraggio" in x.lower() for x in goal["stop_conditions"])
    followup = await read_followup(db, OWNER, SID)
    assert followup["notify_when"] == notify_when
    assert "conclusione utile" in followup["monitoring_goal"]
    assert "monitoraggio" in followup["ends_when"].lower()


@pytest.mark.asyncio
async def test_completed_watch_clears_attention_but_does_not_resolve_situation(monkeypatch):
    db, state = await setup(monkeypatch)
    due = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
    result = await arrange_followup(
        db, OWNER, situation_id=SID, expected_revision=state.revision,
        check_at=due, purpose="Rileggere le condizioni reali.",
        notify_when="Quando è utile intervenire.",
    )
    goal = await AgentService(db).repo.get_goal(OWNER, result["goal_id"])
    assert await settle_completed_followup(db, OWNER, goal) is True

    refreshed = await SituationRepository(db).get(OWNER, SID)
    assert refreshed.status == "changed", "monitoring completion is not physical resolution"
    assert refreshed.resolved_at is None
    assert refreshed.attention_intent is None
    assert refreshed.next_check_summary is None
    assert "situation_unattended" not in await EligibilityService(db).reasons_to_look_again(OWNER)


@pytest.mark.asyncio
async def test_agent_close_completed_settles_watch_lifecycle(monkeypatch):
    db, state = await setup(monkeypatch)
    due = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
    result = await arrange_followup(
        db, OWNER, situation_id=SID, expected_revision=state.revision,
        check_at=due, purpose="Rileggere le condizioni reali.",
        notify_when="Quando è utile intervenire.",
    )
    service = AgentService(db)
    goal = await service.repo.get_goal(OWNER, result["goal_id"])
    plan = ActionPlan(owner_id=OWNER, goal_id=goal.id, status="active",
                      plan_summary="Seguire fino al momento utile.",
                      expected_outcome=goal.desired_outcome, steps=[])
    await service.repo.save_plan(plan)
    run = AgentRun(owner_id=OWNER, goal_id=goal.id)

    closed = await service._close(OWNER, goal, plan, run, "completed",
                                  "Il momento utile è stato raggiunto e comunicato.")
    assert closed["state"] == "completed"
    refreshed = await SituationRepository(db).get(OWNER, SID)
    assert refreshed.status == "changed"
    assert refreshed.attention_intent is None
    assert refreshed.next_check_summary is None
    assert (await read_followup(db, OWNER, SID))["status"] == "not_scheduled"
