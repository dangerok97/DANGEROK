"""Situation waits report only an owned, durable, executable future alarm."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import ActionPlan, AgentRun
from agent.service import AgentService
from ambient.models import AmbientWake
from ambient.repository import AmbientRepository
from ambient.service import AmbientService
from opportunities.discovery import OpportunityDiscovery
from situations.followup import INITIAL_KIND, goal_id_for, read_followup
from situations.models import SituationUpdate
from situations.service import SituationService

OWNER = "wait-integrity-fixture"


async def setup(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    monkeypatch.setattr(OpportunityDiscovery, "note", AsyncMock(return_value={"outcome": "accepted"}))
    db = AsyncMongoMockClient().wait_integrity
    await db.agent_goals.create_index("id", unique=True)
    await db.agent_runs.create_index("goal_id", unique=True)
    await db.ambient_wakes.create_index(
        "identity", unique=True,
        partialFilterExpression={"status": {"$in": ["pending", "claimed"]}},
    )
    created = await SituationService(db).apply(
        user_id=OWNER, session_id="wait-fixture", reasoning_epoch="wait-fixture-created",
        update=SituationUpdate(
            operation="create", summary="Una condizione temporanea sintetica",
            attention_intent="Rileggere una fonte al prossimo momento utile",
            next_check_summary="Conoscere la condizione aggiornata", source="user_conversation",
        ),
    )
    sid = created["situation"]["id"]
    service = AgentService(db)
    monkeypatch.setattr(service, "_note_ambient", AsyncMock())
    goal = await service.repo.get_goal(OWNER, goal_id_for(OWNER, sid))
    plan = ActionPlan(owner_id=OWNER, goal_id=goal.id, status="active")
    run = AgentRun(owner_id=OWNER, goal_id=goal.id)
    return db, service, goal, plan, run, sid


async def cancel(db, goal):
    # Direct goal controls do not need to change the underlying Situation.
    await db.agent_goals.update_one(
        {"id": goal.id, "owner_id": OWNER},
        {"$set": {"status": "cancelled", "next_run_at": None}},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["before_wait", "during_save", "during_schedule", "during_note"])
async def test_direct_cancellation_fences_wait_and_cleans_new_wakes(monkeypatch, phase):
    db, service, goal, plan, run, sid = await setup(monkeypatch)
    foreign = AmbientWake(
        owner_id="another-fixture-owner", reason="opportunity_revisit",
        source_ref=f"goal:{goal.id}", scheduled_for=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    )
    await AmbientRepository(db).schedule(foreign)
    if phase == "before_wait":
        await cancel(db, goal)
    elif phase == "during_save":
        save = service.repo.save_goal

        async def cancel_then_save(candidate):
            await cancel(db, candidate)
            return await save(candidate)

        monkeypatch.setattr(service.repo, "save_goal", cancel_then_save)
    elif phase == "during_schedule":
        schedule = AmbientService.schedule

        async def schedule_then_cancel(ambient, *args, **kwargs):
            wake = await schedule(ambient, *args, **kwargs)
            await cancel(db, goal)
            return wake

        monkeypatch.setattr(AmbientService, "schedule", schedule_then_cancel)
    else:
        async def note_then_cancel(*args, **kwargs):
            await cancel(db, goal)

        monkeypatch.setattr(service, "_note_ambient", note_then_cancel)

    result = await service._wait(OWNER, goal, plan, None, run, minutes=20, note="Rileggere la fonte")
    assert not result["ok"] and result["state"] == "cancelled"
    assert "until" not in result
    durable = await service.repo.get_goal(OWNER, goal.id)
    assert durable.status == "cancelled" and durable.next_run_at is None
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "source_ref": f"goal:{goal.id}", "status": {"$in": ["pending", "claimed"]},
    }) == 0
    assert (await db.ambient_wakes.find_one({"id": foreign.id}))["status"] == "pending"
    situation = await db.situations.find_one({"id": sid, "user_id": OWNER})
    assert situation["attention_intent"], "The goal control is independently authoritative."


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["none", "exception", "unpersisted_result"])
async def test_schedule_failure_cannot_use_old_or_foreign_wake_as_confirmation(monkeypatch, failure):
    db, service, goal, plan, run, sid = await setup(monkeypatch)
    due = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
    for owner, source in [("another-fixture-owner", f"goal:{goal.id}"), (OWNER, "goal:another-fixture-goal")]:
        await AmbientRepository(db).schedule(AmbientWake(
            owner_id=owner, reason="opportunity_revisit", source_ref=source, scheduled_for=due,
        ))
    phantom = AmbientWake(owner_id=OWNER, reason="opportunity_revisit", source_ref=f"goal:{goal.id}", scheduled_for=due)
    schedule = AsyncMock(
        side_effect=RuntimeError("synthetic persistence failure") if failure == "exception" else None,
        return_value=phantom if failure == "unpersisted_result" else None,
    )
    monkeypatch.setattr(AmbientService, "schedule", schedule)
    result = await service._wait(OWNER, goal, plan, None, run, wait_until=due, note="Rileggere la fonte")
    assert not result["ok"] and result["state"] == "recovery_pending"
    assert "until" not in result
    durable = await service.repo.get_goal(OWNER, goal.id)
    assert durable.next_run_at == due, "The durable request remains recoverable."
    assert (await read_followup(db, OWNER, sid))["status"] == "recovery_pending"
    assert await db.agent_journal.count_documents({"owner_id": OWNER, "goal_id": goal.id, "kind": "waiting"}) == 0
    service._note_ambient.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending", "claimed"])
async def test_equivalent_owned_wake_is_confirmed_at_its_actual_instant(monkeypatch, status):
    db, service, goal, plan, run, _ = await setup(monkeypatch)
    due = datetime.now(timezone.utc).replace(second=30, microsecond=0) + timedelta(minutes=20)
    actual = due - timedelta(seconds=10)
    wake = AmbientWake(
        owner_id=OWNER, reason="opportunity_revisit", source_ref=f"goal:{goal.id}",
        scheduled_for=actual.isoformat(), status=status,
    )
    await AmbientRepository(db).schedule(wake)
    # Ambient reports None on minute-bucket dedup; readback determines success.
    monkeypatch.setattr(AmbientService, "schedule", AsyncMock(return_value=None))
    result = await service._wait(OWNER, goal, plan, None, run, wait_until=due.isoformat(), note="Rileggere la fonte")
    assert result["ok"] and result["state"] == "waiting"
    assert result["until"] == actual.isoformat()
    assert (await service.repo.get_goal(OWNER, goal.id)).next_run_at == actual.isoformat()
    assert (await db.ambient_wakes.find_one({"id": wake.id}))["status"] == status


@pytest.mark.asyncio
async def test_technical_review_adopts_ambient_horizon_without_promising_a_checkpoint(monkeypatch):
    db, service, goal, plan, run, sid = await setup(monkeypatch)
    before = datetime.now(timezone.utc)
    result = await service._wait(OWNER, goal, plan, None, run, hours=14 * 24, note="Attendere dati verificabili")
    assert result["ok"]
    due = datetime.fromisoformat(result["until"])
    assert before + timedelta(hours=71) < due < before + timedelta(hours=73)
    durable = await service.repo.get_goal(OWNER, goal.id)
    assert durable.next_run_at == result["until"]
    assert durable.source_kind == INITIAL_KIND
    assert await db.ambient_wakes.find_one({
        "owner_id": OWNER, "source_ref": f"goal:{goal.id}",
        "status": "pending", "scheduled_for": result["until"],
    })
    assert (await read_followup(db, OWNER, sid))["next_check_at"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["consumed", "rescheduled"])
async def test_wait_does_not_confirm_a_wake_changed_during_final_readback(monkeypatch, change):
    db, service, goal, plan, run, _ = await setup(monkeypatch)

    async def consume_wakes(*args, **kwargs):
        changed = ({"status": "completed"} if change == "consumed" else
                   {"scheduled_for": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()})
        await db.ambient_wakes.update_many(
            {"owner_id": OWNER, "source_ref": f"goal:{goal.id}"},
            {"$set": changed},
        )

    monkeypatch.setattr(service, "_note_ambient", consume_wakes)
    result = await service._wait(OWNER, goal, plan, None, run, minutes=20, note="Rileggere la fonte")
    assert not result["ok"] and result["state"] == "recovery_pending"
    assert "until" not in result
