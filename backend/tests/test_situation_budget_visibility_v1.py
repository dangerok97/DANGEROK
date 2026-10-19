"""Test 2 postmortem: 3 background passes must never stop silently.

A real AgentService.advance state transition is exercised with an isolated
in-memory Mongo. Its expensive model/work adapters are scripted; this cannot
prove the physical outcome or notification delivery, only truthful persistence.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import AutonomousGoal
from agent.service import AgentService
from situations.followup import goal_id_for
from situations.models import SituationState

OWNER = "synthetic-autonomy-budget-owner"
SID = "sit_budget_own"


async def setup(monkeypatch):
    from agent import source_refresh

    db = AsyncMongoMockClient().budget_visible_test
    await db.situations.insert_one(SituationState(
        id=SID, user_id=OWNER, summary="Synthetic situation requiring attention",
        status="active", attention_intent="Know the real useful next action",
    ).model_dump())
    goal = AutonomousGoal(
        id=goal_id_for(OWNER, SID), owner_id=OWNER,
        objective="Check synthetic temporary situation without inventing outcome",
        desired_outcome="Evidence-backed advice",
        source_kind="situation_followup", source_refs=[f"situation:{SID}"],
        source_situation={
            "situation_id": SID, "situation_revision": "1",
            "attention_started_at": "2026-10-19T12:00:00+00:00",
        },
        status="active", background_runs=2,
        next_run_at=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
    )
    await db.agent_goals.insert_one(goal.model_dump())
    service = AgentService(db)
    monkeypatch.setattr(service.repo, "claim", AsyncMock(return_value=True))
    monkeypatch.setattr(service.repo, "release", AsyncMock(return_value=None))
    monkeypatch.setattr(service, "_legacy_event_alert_expired",
                        AsyncMock(return_value=False))
    monkeypatch.setattr(service, "_consider_visibility",
                        AsyncMock(return_value=None))
    monkeypatch.setattr(source_refresh, "refresh", AsyncMock(return_value=None))
    return db, service, goal


@pytest.mark.asyncio
async def test_three_nonconclusive_passes_leave_single_visible_activity(monkeypatch):
    db, service, goal = await setup(monkeypatch)
    monkeypatch.setattr(
        service, "_work", AsyncMock(return_value={"ok": True, "state": "in_progress"}),
    )
    result = await service.advance(
        OWNER, goal.id, worker_id="ambient:synthetic-owner-wake",
    )
    assert result["state"] == "in_progress"
    latest = await service.repo.get_goal(OWNER, goal.id)
    assert latest.is_open and latest.background_runs >= 3
    assert latest.next_run_at is None, "budget must not spin on the old wake"
    entries = await db.ambient_activity.find(
        {"owner_id": OWNER}, {"_id": 0}
    ).to_list(5)
    assert len(entries) == 1
    assert entries[0]["kind"] == "monitoring_suspended"
    assert entries[0]["visibility"] == "ambient"
    assert entries[0]["source_refs"][0] == f"situation:{SID}"
    assert "senza un risultato conclusivo verificato" in entries[0]["summary"]
    assert "asciutti" not in entries[0]["summary"].lower()
    assert await db.delivery_plans.count_documents({}) == 0

    # A duplicate/replayed emission is a no-op in the persisted activity ledger.
    assert await service._note_situation_monitoring_suspended(OWNER, latest)
    assert await db.ambient_activity.count_documents({"owner_id": OWNER}) == 1

    # Closing the Situation stops any attempt to raise a fresh alert.
    await db.situations.update_one(
        {"id": SID, "user_id": OWNER}, {"$set": {"status": "cancelled"}},
    )
    assert not await service._note_situation_monitoring_suspended(OWNER, latest)
    assert await db.ambient_activity.count_documents({"owner_id": OWNER}) == 1
    assert await db.ambient_activity.count_documents({"owner_id": "other"}) == 0


@pytest.mark.asyncio
async def test_real_model_chosen_wait_survives_third_background_pass(monkeypatch):
    db, service, goal = await setup(monkeypatch)
    due = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

    async def newly_planned_wait(owner_id, mutable_goal, run, budget, **kwargs):
        assert owner_id == OWNER
        mutable_goal.status = "waiting"
        mutable_goal.next_run_at = due
        return {"ok": True, "state": "waiting"}

    monkeypatch.setattr(service, "_work", newly_planned_wait)
    result = await service.advance(
        OWNER, goal.id, worker_id="ambient:synthetic-wait",
    )
    assert result["state"] == "waiting"
    latest = await service.repo.get_goal(OWNER, goal.id)
    assert latest.background_runs >= 3
    assert latest.status == "waiting" and latest.next_run_at == due
    assert await db.ambient_activity.count_documents({}) == 0
    assert await db.delivery_plans.count_documents({}) == 0
