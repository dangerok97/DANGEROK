"""Source review rejection remains an unfinished, bounded autonomous mission.

A stopped or contradictory synthetic critic cannot publish a result. A busy
worker defers model-led repair without exceeding its technical budget, without
re-reading a source or creating a duplicate autonomous goal. No real model,
payment, notification, device, or external effect is involved in these tests.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from mongomock_motor import AsyncMongoMockClient
import pytest

from agent.models import (
    ActionPlan, ActionStep, AgentBudget, AgentRun, AutonomousGoal,
    ExecutionResult, ResultProvenance,
)
from agent.service import AgentService


OWNER = "synthetic-source-repair"
FEEDBACK = "La revisione ha rilevato una clausola non sostenuta dalla fonte."


async def fixture(*, attempts=0, failure="preparation_challenge_rejected"):
    db = AsyncMongoMockClient().source_repair_budget_v162
    goal = AutonomousGoal(
        owner_id=OWNER, status="active",
        objective="Produrre un confronto fondato sulla nota corrente",
        desired_outcome="Confronto scritto attribuito alle fonti",
        background_runs=2,
    )
    step = ActionStep(
        ordinal=1, step_type="prepare", capability_needed="document.create",
        intent="Preparare la sintesi verificabile", attempts=attempts,
    )
    plan = ActionPlan(owner_id=OWNER, goal_id=goal.id, status="active", steps=[step])
    await db.agent_goals.insert_one(goal.model_dump())
    await db.agent_plans.insert_one(plan.model_dump())
    service = AgentService(db)
    service.executor.run = AsyncMock(return_value=ExecutionResult(
        step_id=step.id, status="unavailable", observation=FEEDBACK,
        error_type=failure, retryable=True,
        provenance=ResultProvenance(
            source_class="internal_observation", capability="document.create",
            provider="generated_draft",
        ),
    ))
    run = AgentRun(owner_id=OWNER, goal_id=goal.id, background=True)
    budget = AgentBudget(
        started_at=(datetime.now(timezone.utc) - timedelta(minutes=4)).isoformat(),
    )
    return db, service, goal, plan, step, run, budget


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [
    "preparation_challenge_rejected",
    "preparation_challenge_unavailable",
    "preparation_review_self_contradiction",
    "preparation_reference_leak",
])
async def test_exhausted_worker_reschedules_one_owned_review_without_replanning_now(
    monkeypatch, failure
):
    db, service, goal, plan, step, run, budget = await fixture(failure=failure)
    monkeypatch.setattr(service, "_reconsider", AsyncMock(
        side_effect=AssertionError("Do not replan after the time budget"),
    ))
    before = datetime.now(timezone.utc)
    result = await service._do_step(OWNER, goal, plan, step, run, budget, language="it")
    assert result["ok"] is True and result["state"] == "in_progress"
    assert service._reconsider.await_count == 0
    saved = await db.agent_goals.find_one({"owner_id": OWNER, "id": goal.id})
    persisted = await db.agent_plans.find_one({"owner_id": OWNER, "goal_id": goal.id})
    assert saved["status"] == "active" and saved["background_runs"] == 0
    assert not saved.get("prepared_text") and not saved.get("prepared_sources")
    assert persisted["status"] == "active"
    assert persisted["steps"][0]["status"] == "pending"
    assert persisted["steps"][0]["attempts"] == 1
    due = datetime.fromisoformat(saved["next_run_at"])
    assert before + timedelta(minutes=4) < due < datetime.now(timezone.utc) + timedelta(minutes=6)
    wakes = await db.ambient_wakes.find({
        "owner_id": OWNER, "source_ref": f"goal:{goal.id}", "status": "pending",
    }, {"_id": 0}).to_list(10)
    assert len(wakes) == 1
    assert wakes[0]["scheduled_for"] == saved["next_run_at"]
    assert await db.agent_goals.count_documents({"owner_id": OWNER}) == 1
    assert await db.agent_action_attempts.count_documents({}) == 0
    recorded = await db.agent_journal.find({
        "owner_id": OWNER, "goal_id": goal.id, "kind": "source_review_retry_queued",
    }).to_list(4)
    assert len(recorded) == 1
    assert recorded[0]["detail"]["attempt"] == 1
    assert recorded[0]["detail"]["failure_code"] == failure
    assert run.stopped_because == "source_review_retry_scheduled"


@pytest.mark.asyncio
async def test_rejected_result_does_not_trigger_immediate_replanning_even_with_budget_left(monkeypatch):
    db, service, goal, plan, step, run, budget = await fixture(
        failure="preparation_reference_leak",
    )
    budget.started_at = datetime.now(timezone.utc).isoformat()
    budget.cognitive_calls = 1
    monkeypatch.setattr(service, "_reconsider", AsyncMock(
        side_effect=AssertionError("Only the next bounded pass may reconsider"),
    ))
    result = await service._do_step(OWNER, goal, plan, step, run, budget, language="it")
    assert result["state"] == "in_progress"
    service._reconsider.assert_not_awaited()
    saved = await db.agent_plans.find_one({"owner_id": OWNER, "goal_id": goal.id})
    assert saved["steps"][0]["status"] == "pending"
    assert saved["steps"][0]["attempts"] == 1
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "source_ref": f"goal:{goal.id}", "status": "pending",
    }) == 1
    assert await db.agent_action_attempts.count_documents({}) == 0


@pytest.mark.asyncio
async def test_insufficient_reserved_cognitive_calls_pause_before_consume_attempt_or_model(monkeypatch):
    monkeypatch.setenv("ORA_PREPARATION_BLIND_CHALLENGE", "1")
    db, service, goal, plan, step, run, budget = await fixture()
    budget.started_at = datetime.now(timezone.utc).isoformat()
    budget.cognitive_calls = 6
    budget.max_cognitive_calls = 8
    service.executor.run = AsyncMock(
        side_effect=AssertionError("The model/preparation must not start"),
    )
    replan = AsyncMock(side_effect=AssertionError("No immediate replan"))
    monkeypatch.setattr(service, "_reconsider", replan)
    result = await service._do_step(OWNER, goal, plan, step, run, budget, language="it")
    assert result["ok"] is True and result["state"] == "in_progress"
    service.executor.run.assert_not_awaited()
    replan.assert_not_awaited()
    assert budget.cognitive_calls == 6 and budget.steps_executed == 0
    assert run.steps_executed == 0
    saved = await db.agent_plans.find_one({"owner_id": OWNER, "goal_id": goal.id})
    assert saved["steps"][0]["status"] == "pending"
    assert saved["steps"][0]["attempts"] == 0
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "source_ref": f"goal:{goal.id}", "status": "pending",
    }) == 1
    assert (await db.agent_goals.find_one({"owner_id": OWNER}))["prepared_text"] == ""
    assert await db.agent_action_attempts.count_documents({}) == 0


@pytest.mark.asyncio
async def test_preparation_reservation_does_not_override_future_explicit_defer(monkeypatch):
    monkeypatch.setenv("ORA_PREPARATION_BLIND_CHALLENGE", "1")
    db, service, goal, plan, step, run, budget = await fixture()
    budget.started_at = datetime.now(timezone.utc).isoformat()
    budget.cognitive_calls, budget.max_cognitive_calls = 7, 8
    deferred = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    await db.agent_goals.update_one(
        {"owner_id": OWNER, "id": goal.id},
        {"$set": {"user_deferred_until": deferred, "next_run_at": deferred, "status": "waiting"}},
    )
    service.executor.run = AsyncMock(
        side_effect=AssertionError("Do not act after user deferral"),
    )
    result = await service._do_step(OWNER, goal, plan, step, run, budget, language="it")
    assert result["state"] == "user_deferred"
    service.executor.run.assert_not_awaited()
    assert await db.ambient_wakes.count_documents({}) == 0
    current = await db.agent_goals.find_one({"owner_id": OWNER, "id": goal.id})
    assert current["user_deferred_until"] == deferred
    assert current["next_run_at"] == deferred


@pytest.mark.asyncio
async def test_corrective_review_retry_is_bounded_by_original_step_attempt_cap(monkeypatch):
    db, service, goal, plan, step, run, budget = await fixture(attempts=2)
    reconsider = AsyncMock(return_value={"ok": True, "state": "replan_required"})
    monkeypatch.setattr(service, "_reconsider", reconsider)
    result = await service._do_step(OWNER, goal, plan, step, run, budget, language="it")
    assert result["state"] == "replan_required"
    reconsider.assert_awaited_once()
    saved = await db.agent_plans.find_one({"owner_id": OWNER, "goal_id": goal.id})
    assert saved["steps"][0]["attempts"] == 3
    assert saved["steps"][0]["status"] == "failed"
    assert await db.ambient_wakes.count_documents({}) == 0


@pytest.mark.asyncio
async def test_generic_reconsider_uses_elapsed_time_budget_without_model_call(monkeypatch):
    db, service, goal, plan, step, run, budget = await fixture(failure="provider_unavailable")
    monkeypatch.setattr(service, "_source_change_result", AsyncMock(return_value=None))
    from agent import reasoning
    model = AsyncMock(side_effect=AssertionError("Time budget exhausted before replan"))
    monkeypatch.setattr(reasoning, "reconsider", model)
    result = await service._reconsider(
        OWNER, goal, plan, run, budget,
        what_happened={"result": {"status": "unavailable"}},
        language="it",
    )
    assert result["state"] == "in_progress"
    model.assert_not_awaited()
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "source_ref": f"goal:{goal.id}", "status": "pending",
    }) == 1


@pytest.mark.asyncio
async def test_unrelated_failure_still_calls_model_reconsideration(monkeypatch):
    db, service, goal, plan, step, run, budget = await fixture(
        failure="source_missing",
    )
    decision = AsyncMock(return_value={"ok": True, "state": "reconsidered"})
    monkeypatch.setattr(service, "_reconsider", decision)
    result = await service._do_step(OWNER, goal, plan, step, run, budget, language="it")
    assert result["state"] == "reconsidered"
    decision.assert_awaited_once()
    assert (await db.agent_plans.find_one({"goal_id": goal.id}))["steps"][0]["status"] == "failed"
    assert await db.ambient_wakes.count_documents({}) == 0


@pytest.mark.asyncio
async def test_finish_fallback_cannot_regenerate_a_rejected_unsourced_draft():
    """Finishing twice must not invent fresh step IDs after an audit failure."""
    from test_preparation_recovery_v162 import seed_recovery

    db, goal, plan, _source, _note = await seed_recovery()
    owner = goal.owner_id
    service = AgentService(db)
    # No ordinary preparation is pending; the fallback is needed once.
    plan.steps[1].status = "skipped"
    await service.repo.save_plan(plan)
    service.executor.run = AsyncMock(return_value=ExecutionResult(
        step_id="stp_synthetic_failed_fallback", status="unavailable",
        observation="La bozza non è sostenuta dalle fonti correnti.",
        error_type="preparation_not_supported", retryable=True,
        provenance=ResultProvenance(
            source_class="internal_observation", capability="document.create",
            provider="generated_draft",
        ),
    ))
    service._reconsider = AsyncMock(return_value=None)
    first = await service._finish(owner, goal, plan,
        AgentRun(owner_id=owner, goal_id=goal.id), AgentBudget(), language="it")
    assert first["state"] == "in_progress"
    assert len(plan.steps) == 3
    fallback = plan.steps[-1]
    assert fallback.status == "failed" and fallback.attempts == 1
    assert not goal.prepared_text and not goal.prepared_sources
    assert service.executor.run.await_count == 1
    assert service._reconsider.await_count == 1

    # An unchanged source and plan do not license a second auto fallback.
    second = await service._finish(owner, goal, plan,
        AgentRun(owner_id=owner, goal_id=goal.id), AgentBudget(), language="it")
    assert second["state"] == "failed"
    assert len(plan.steps) == 3 and plan.steps[-1].id == fallback.id
    assert service.executor.run.await_count == 1
    assert service._reconsider.await_count == 1
    assert not goal.prepared_text and goal.status == "failed"
    recorded = await db.agent_journal.find_one({
        "owner_id": owner, "goal_id": goal.id,
        "kind": "completion_fallback_exhausted",
    })
    assert recorded["detail"]["step_id"] == fallback.id
    assert recorded["detail"]["attempts"] == 1


@pytest.mark.asyncio
async def test_finish_preserves_pending_repair_after_fallback_rejection():
    """A replanned pending correction is not replaced by another auto fallback."""
    from test_preparation_recovery_v162 import seed_recovery

    db, goal, plan, _source, _note = await seed_recovery()
    owner = goal.owner_id
    service = AgentService(db)
    service.executor.run = AsyncMock(return_value=ExecutionResult(
        step_id="stp_synthetic_rejected", status="unavailable",
        observation="Revisione della bozza negativa.",
        error_type="preparation_not_supported", retryable=True,
        provenance=ResultProvenance(
            source_class="internal_observation", capability="document.create",
            provider="generated_draft",
        ),
    ))
    service._reconsider = AsyncMock(return_value=None)
    await service._finish(owner, goal, plan,
        AgentRun(owner_id=owner, goal_id=goal.id), AgentBudget(), language="it")
    assert len(plan.steps) == 3
    assert plan.steps[1].status == "pending"
    calls = service.executor.run.await_count
    resumed = await service._finish(owner, goal, plan,
        AgentRun(owner_id=owner, goal_id=goal.id), AgentBudget(), language="it")
    assert resumed["state"] == "in_progress"
    assert len(plan.steps) == 3 and plan.steps[1].status == "pending"
    assert service.executor.run.await_count == calls
    assert goal.status == "active" and not goal.prepared_text


@pytest.mark.asyncio
async def test_finish_reserves_optional_third_audit_before_starting_fallback(monkeypatch):
    """Never start a 3-call preparation that leaves no budget for verification."""
    from test_preparation_recovery_v162 import seed_recovery

    monkeypatch.setenv("ORA_PREPARATION_BLIND_CHALLENGE", "1")
    db, goal, plan, _source, _note = await seed_recovery()
    owner = goal.owner_id
    service = AgentService(db)
    plan.steps[1].status = "skipped"
    await service.repo.save_plan(plan)
    service.executor.run = AsyncMock(
        side_effect=AssertionError("Insufficient budget must not start a preparation"),
    )
    budget = AgentBudget(cognitive_calls=5, max_cognitive_calls=8)
    result = await service._finish(owner, goal, plan,
        AgentRun(owner_id=owner, goal_id=goal.id), budget, language="it")
    assert result["state"] == "in_progress"
    assert len(plan.steps) == 2
    service.executor.run.assert_not_awaited()
    assert budget.cognitive_calls == 5
    assert not goal.prepared_text
    saved = await db.agent_goals.find_one({"owner_id": owner, "id": goal.id})
    assert saved["next_run_at"]
    assert await db.ambient_wakes.count_documents({
        "owner_id": owner, "source_ref": f"goal:{goal.id}", "status": "pending",
    }) == 1
