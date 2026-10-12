"""Observe durable completion recovery without extending the runtime budget.

Decisions and the transient provider failure are scripted. The reader,
worker, executor, persistence, result checks and Home handoff remain real
internal services over an isolated synthetic database; no network is used.
"""
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from mongomock.collection import Collection
from mongomock_motor import AsyncMongoMockClient

from agent import preparation
from agent.models import ResultProvenance
from agent.providers import CapabilityOutcome
from scripts import autonomy_completion_eval_v162 as gate


async def read_then_verify(*args, **kwargs):
    read = next((step for step in kwargs.get("candidates", [])
                 if step.get("type") == "inspect"), None)
    if read:
        return {"decision": "execute", "step_id": read["id"],
                "reasoning": "Read the supplied source."}
    return {"decision": "verify", "reasoning": "Synthetic premature verification."}


@pytest.mark.asyncio
@pytest.mark.parametrize("persistent", [False, True])
async def test_completion_observes_existing_retry_and_preserves_failed_history(monkeypatch, persistent):
    original_prepare = preparation.prepare
    attempts = []

    async def unavailable_first(db, owner, goal, step):
        attempts.append(goal.background_runs)
        if persistent or len(attempts) == 1:
            return CapabilityOutcome(
                status="unavailable", observation="Synthetic transient preparation failure.",
                provenance=ResultProvenance(source_class="internal_observation", provider="generated_draft"),
                error_type="preparation_model_unavailable", retryable=True,
            )
        return await original_prepare(db, owner, goal, step)

    monkeypatch.setattr(gate.baseline, "scripted_choose", read_then_verify)
    monkeypatch.setattr(preparation, "prepare", unavailable_first)
    probe = gate.Probe()
    if persistent:
        with pytest.raises(gate.EvaluationFailure, match="^COMPLETION_BUDGET_EXHAUSTED$"):
            await gate.run_case("planning_outage", probe=probe)
    else:
        report = await gate.run_case("planning_outage", probe=probe)
        assert report["passed"] and report["result"]["prepared"]
        assert report["result"]["home_delivered"]
        assert report["result"]["replay_idempotent"]
        assert report["result"]["owner_isolation"]

    # The successful read used run 1. No counter is reset to make a third
    # preparation attempt fit: only the two remaining runs can be observed.
    assert attempts == [2, 3]
    goal = await probe.database.agent_goals.find_one({"owner_id": gate.OWNER})
    plan = await probe.database.agent_plans.find_one({"owner_id": gate.OWNER, "goal_id": goal["id"]})
    assert goal["background_runs"] == 3 and goal["next_run_at"] is None
    failed = [step for step in plan["steps"] if step["status"] == "failed"]
    assert len(failed) == (2 if persistent else 1)
    assert all(step["note"] == "Synthetic transient preparation failure." for step in failed)
    assert sum(step["capability"] == "information.read" for step in probe.steps) == 1
    assert probe.model_attempts == probe.model_http_requests == probe.blocked_effects == 0
    if persistent:
        assert goal["status"] == "active" and not goal.get("prepared_text")
        assert await probe.database.agent_updates.count_documents({"home_delivered_at": {"$type": "string"}}) == 0
    else:
        assert goal["status"] == plan["status"] == "completed"
        assert all(step["status"] in ("succeeded", "skipped", "failed") for step in plan["steps"])


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {"status": "waiting"},
    {"requires_user_input": True},
    {"requires_user_authority": True},
    {"user_deferred_until": "2099-01-01T00:00:00+00:00"},
])
async def test_completion_cannot_advance_a_new_decision_or_user_clock(monkeypatch, change):
    db = AsyncMongoMockClient().v162_completion_clock
    await db.eval_guards.insert_one({"_id": gate.VERSION, "owner": gate.OWNER})
    row = {"id": "synthetic-goal", "owner_id": gate.OWNER, "status": "active",
           "background_runs": 1, "next_run_at": "2099-01-01T00:00:00+00:00", **change}
    await db.agent_goals.insert_one(deepcopy(row))
    fire = AsyncMock(side_effect=AssertionError("A new decision must not be accelerated"))
    monkeypatch.setattr(gate, "fire_due", fire)
    with pytest.raises(gate.EvaluationFailure, match="^COMPLETION_NEEDS_NEW_DECISION$"):
        await gate.complete_due_work(db, row["id"], gate.Probe())
    assert fire.await_count == 0
    assert await db.agent_goals.find_one({"id": row["id"]}, {"_id": 0}) == row


@pytest.mark.asyncio
@pytest.mark.parametrize("marker,owner,code", [
    (False, gate.OWNER, "SYNTHETIC_CLOCK_GUARD_MISSING"),
    (True, "another-synthetic-owner", "COMPLETION_GOAL_MISSING"),
])
async def test_completion_requires_synthetic_guard_and_owned_goal(marker, owner, code):
    db = AsyncMongoMockClient().v162_completion_guard
    if marker:
        await db.eval_guards.insert_one({"_id": gate.VERSION, "owner": gate.OWNER})
    row = {"id": "synthetic-goal", "owner_id": owner, "status": "active",
           "background_runs": 1, "next_run_at": "2099-01-01T00:00:00+00:00"}
    await db.agent_goals.insert_one(deepcopy(row))
    with pytest.raises(gate.EvaluationFailure, match="^" + code + "$"):
        await gate.complete_due_work(db, row["id"], gate.Probe())
    assert await db.agent_goals.find_one({"id": row["id"]}, {"_id": 0}) == row


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {"owner_id": "another-synthetic-owner"},
    {"opportunity_revision": "changed-before-clock-write"},
    {"requires_user_authority": True},
])
async def test_due_clock_cas_does_not_overwrite_a_changed_checkpoint(monkeypatch, change):
    db = AsyncMongoMockClient().v162_completion_cas
    with gate.isolated_engine(db) as probe:
        await gate.seed_case(db, "completed_result")
        goal_id = await gate.admit(db, "completed_result", probe)
        before = await db.agent_goals.find_one({"id": goal_id})
        original_update = Collection.update_one
        raced = []

        def change_before_write(collection, query, update, *args, **kwargs):
            if (collection.name == "agent_goals" and query.get("id") == goal_id
                    and set(update.get("$set", {})) == {"next_run_at"} and not raced):
                raced.append(True)
                original_update(collection, {"id": goal_id}, {"$set": change})
            return original_update(collection, query, update, *args, **kwargs)

        monkeypatch.setattr(Collection, "update_one", change_before_write)
        with pytest.raises(gate.EvaluationFailure, match="^CONTINUATION_CHECKPOINT_CHANGED$"):
            await gate.fire_due(db, goal_id, probe)
        after = await db.agent_goals.find_one({"id": goal_id})
        assert raced == [True]
        assert after == {**before, **change}
        assert probe.ticks == [] and probe.steps == []


@pytest.mark.asyncio
@pytest.mark.parametrize("saved_due", ["not-a-time", "2026-10-12T00:00:00"])
async def test_due_clock_rejects_invalid_or_unqualified_persisted_time(saved_due):
    db = AsyncMongoMockClient().v162_completion_invalid_clock
    await db.eval_guards.insert_one({"_id": gate.VERSION, "owner": gate.OWNER})
    row = {"id": "synthetic-goal", "owner_id": gate.OWNER, "next_run_at": saved_due}
    await db.agent_goals.insert_one(deepcopy(row))
    with pytest.raises(gate.EvaluationFailure, match="^DURABLE_CONTINUATION_INVALID$"):
        await gate.fire_due(db, row["id"], gate.Probe())
    assert await db.agent_goals.find_one({"id": row["id"]}, {"_id": 0}) == row


@pytest.mark.asyncio
async def test_corrected_memory_does_not_accelerate_a_model_wait_or_reset_its_counter(monkeypatch):
    original_change, original_choose, original_fire = gate.change_memory, gate.baseline.scripted_choose, gate.fire_due
    changed, waits, saved_waits = [], [], []

    async def correct(*args, **kwargs):
        result = await original_change(*args, **kwargs)
        changed.append(result)
        return result

    async def choose(*args, **kwargs):
        if not changed:
            return await original_choose(*args, **kwargs)
        waits.append(True)
        return {"decision": "wait", "wait_minutes": 37,
                "reasoning": "Synthetic model wait after the source correction."}

    async def observe_fire(*args, **kwargs):
        current = await original_fire(*args, **kwargs)
        if current["status"] == "waiting":
            saved_waits.append(deepcopy(current))
        return current

    monkeypatch.setattr(gate, "change_memory", correct)
    monkeypatch.setattr(gate.baseline, "scripted_choose", choose)
    monkeypatch.setattr(gate, "fire_due", observe_fire)
    probe = gate.Probe()
    with pytest.raises(gate.EvaluationFailure, match="^COMPLETION_NEEDS_NEW_DECISION$"):
        await gate.run_case("memory_corrected", probe=probe)
    goal = await probe.database.agent_goals.find_one({"owner_id": gate.OWNER}, {"_id": 0})
    assert len(changed) == len(waits) == len(saved_waits) == 1
    assert goal["status"] == "waiting" and goal["next_run_at"]
    assert goal == saved_waits[0]  # Includes the persisted clock and run counter.
    assert not goal.get("prepared_text")
    assert probe.model_attempts == probe.model_http_requests == probe.blocked_effects == 0
