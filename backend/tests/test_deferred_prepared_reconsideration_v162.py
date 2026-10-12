"""A deferred review resumes the owed judgement, using the existing wake.

Real owned Memory reads, preparation, review CAS, plan storage, recovery and
worker dispatch run over synthetic Mongo. Model replies are controlled; this
does not attest their semantic quality, external effects or device delivery.
"""
from copy import deepcopy
from datetime import datetime, timedelta
import json
from unittest.mock import AsyncMock

import pytest

from agent import reasoning
from agent.background import advance_wake, recover_due
from agent.models import AgentBudget, AgentRun
from agent.models import ActionStep
from agent.execution import StepExecutor
from agent.service import AgentService
from ambient.repository import AmbientRepository
from scripts import autonomy_completion_eval_v162 as gate
from test_autonomy_wait_recovery_v162 import clock  # noqa: F401
from test_agent_preparation_dependency_v162 import OWNER, comparison_claim_review
from test_preparation_passages_v162 import source_claim
from test_verification_recovery_v162 import (
    CORRECTED, MISSING, REASON, UNSUPPORTED, prepared_with_missed_defect, repair_plan,
)


async def deferred_review(monkeypatch, *, verdict="partially_achieved"):
    db, goal, plan, source, text = await prepared_with_missed_defect()
    await AgentService(db).repo.ensure_indexes()
    verifier = AsyncMock(return_value={
        "outcome": verdict, "reasoning": REASON, "what_is_missing": MISSING,
    })
    monkeypatch.setattr(reasoning, "verify_goal", verifier)
    budget = AgentBudget(cognitive_calls=7)
    result = await AgentService(db)._finish(
        OWNER, goal, plan, AgentRun(owner_id=OWNER, goal_id=goal.id), budget, language="it",
    )
    assert result["state"] == "in_progress" and verifier.await_count == 1
    assert budget.cognitive_calls == budget.max_cognitive_calls == 8
    current = await AgentService(db).repo.get_goal(OWNER, goal.id)
    assert current.prepared_review and current.next_run_at
    # The fixture begins at the end of the first background pass. Its
    # original persisted continuation is still present, not lost.
    await db.agent_goals.update_one({"owner_id": OWNER, "id": goal.id},
                                   {"$set": {"background_runs": 1}})
    return db, goal, plan, source, text, verifier


async def resume_due(db, goal_id, clock):
    current = await AgentService(db).repo.get_goal(OWNER, goal_id)
    clock[0] = datetime.fromisoformat(current.next_run_at) + timedelta(seconds=1)
    existing = await db.ambient_wakes.find_one({
        "owner_id": OWNER, "source_ref": f"goal:{goal_id}", "status": "pending",
    })
    if existing:
        clock[0] = max(clock[0], datetime.fromisoformat(existing["scheduled_for"]) + timedelta(seconds=1))
    assert await recover_due(db, now=clock[0], admit=False) == int(existing is None)
    assert await db.ambient_wakes.count_documents({
        "scheduled_for": {"$lte": clock[0].isoformat()}, "status": "pending", "attempts": {"$lt": 5},
    }) == 1
    repository = AmbientRepository(db)
    # Reuse the harness's mongomock-only atomic-claim projection adapter.
    # No model/service step runs inside this context.
    with gate.isolated_engine(db):
        wake = await repository.claim_due(worker_id="synthetic-review", now=clock[0])
    assert wake is not None and wake.owner_id == OWNER and wake.source_ref == f"goal:{goal_id}", {
        "scheduled_for": (existing or {}).get("scheduled_for"), "now": clock[0].isoformat(),
        "attempts": (existing or {}).get("attempts"), "status": (existing or {}).get("status"),
    }
    result = await advance_wake(db, wake)
    await repository.complete(wake.id, result=result.result, worker_id="synthetic-review")
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize("verdict", ["partially_achieved", "uncertain"])
async def test_last_budget_verdict_resumes_reconsideration_before_reverification(monkeypatch, clock, verdict):
    db, goal, plan, source, text, verifier = await deferred_review(monkeypatch, verdict=verdict)
    original_steps = deepcopy([step.model_dump() for step in plan.steps])
    observed = []

    async def answer(_system, encoded, *, response_schema=None):
        payload = json.loads(encoded)
        if "what_happened" in payload:
            observed.append("reconsider")
            failure = payload["what_happened"]["result"]
            assert failure["what_is_missing"] == MISSING and failure["reasoning"] == REASON
            assert failure["verification_outcome"] == verdict
            return repair_plan()
        if "still_to_do" in payload:
            observed.append("choose")
            pending, = payload["still_to_do"]
            return {"decision": "execute", "step_id": pending["id"]}
        row, = payload["evidence"]
        assert row["id"] == source.id and source_claim(row) == text
        observed.append("audit" if "draft" in payload else "prepare")
        result = {"content": CORRECTED, "evidence_ids": [source.id]}
        if "draft" in payload:
            result.update(verified=True, claim_review=comparison_claim_review(source.id))
        return result

    async def verify(_goal, *, evidence, language):
        observed.append("verify")
        assert evidence["prepared_result"] == CORRECTED, "Do not reverify the unchanged rejected draft."
        return {"outcome": "achieved", "reasoning": "La correzione ora conserva il limite della fonte."}

    monkeypatch.setattr(reasoning, "_ask_model", answer)
    monkeypatch.setattr(reasoning, "verify_goal", verify)
    result = await resume_due(db, goal.id, clock)
    current = await AgentService(db).repo.get_goal(OWNER, goal.id)
    saved_plan = await AgentService(db).repo.plan_for(OWNER, goal.id)
    assert result.result == current.status == "completed"
    assert observed == ["reconsider", "choose", "prepare", "audit", "verify"]
    assert current.background_runs == 2 and current.next_run_at is None
    assert current.prepared_text == CORRECTED and current.prepared_sources == [source.id]
    assert [step.model_dump() for step in saved_plan.steps[:2]] == original_steps
    assert len(saved_plan.steps) == 3 and saved_plan.steps[-1].status == "succeeded"
    assert await db.agent_evidence.count_documents({"owner_id": OWNER, "goal_id": goal.id,
        "provenance.capability": "information.read"}) == 1
    assert await recover_due(db, now=clock[0], admit=False) == 0
    assert await AgentService(db).advance(OWNER, goal.id) == {
        "ok": True, "state": "completed", "goal": current.for_human(),
    }
    assert len(observed) == 5 and verifier.await_count == 1
    assert await db.agent_action_attempts.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", [None, {"decision": "modify", "revised_steps": []}])
async def test_unavailable_reconsideration_retains_owed_work_without_resetting_the_cap(monkeypatch, clock, answer):
    db, goal, _plan, _source, _text, verifier = await deferred_review(monkeypatch)
    reconsider = AsyncMock(return_value=answer)
    monkeypatch.setattr(reasoning, "reconsider", reconsider)
    for count in (2, 3):
        await resume_due(db, goal.id, clock)
        current = await AgentService(db).repo.get_goal(OWNER, goal.id)
        assert current.status == "active" and current.background_runs == count
        assert current.prepared_text == UNSUPPORTED and current.prepared_review
        assert bool(current.next_run_at) is (count < 3)
        assert verifier.await_count == 1, "Only the unfinished reconsideration may be retried."
        assert reconsider.await_count == count - 1
    result = await AgentService(db).advance(OWNER, goal.id, worker_id="ambient:cap")
    assert result["state"] == "background_paused"
    assert await recover_due(db, now=clock[0], admit=False) == 0
    assert reconsider.await_count == 2 and verifier.await_count == 1


@pytest.mark.asyncio
async def test_accepted_revision_and_ack_survive_reload_without_appending_twice(monkeypatch, clock):
    db, goal, _plan, _source, _text, verifier = await deferred_review(monkeypatch)
    reconsider = AsyncMock(return_value=repair_plan())
    monkeypatch.setattr(reasoning, "reconsider", reconsider)
    # Stop at the existing technical ceiling after accepting the revision;
    # the next worker must see that exact saved repair and its acknowledgement.
    monkeypatch.setattr(AgentService, "_next", AsyncMock(return_value=("budget", None)))
    await resume_due(db, goal.id, clock)
    saved = await AgentService(db).repo.plan_for(OWNER, goal.id)
    assert len(saved.steps) == 3 and saved.steps[-1].status == "pending"
    assert saved.prepared_review_reconsidered and "prepared_review_reconsidered" not in saved.for_ai()
    before = deepcopy([step.model_dump() for step in saved.steps])
    await resume_due(db, goal.id, clock)
    after = await AgentService(db).repo.plan_for(OWNER, goal.id)
    assert [step.model_dump() for step in after.steps] == before
    assert after.prepared_review_reconsidered == saved.prepared_review_reconsidered
    assert reconsider.await_count == verifier.await_count == 1


async def new_identical_preparation(db, goal_id, source, monkeypatch):
    current = await AgentService(db).repo.get_goal(OWNER, goal_id)
    previous_id = current.prepared_result_id
    replies = AsyncMock(side_effect=[
        {"content": UNSUPPORTED, "evidence_ids": [source.id]},
        {"verified": True, "content": UNSUPPORTED, "evidence_ids": [source.id],
         "claim_review": comparison_claim_review(source.id)},
    ])
    monkeypatch.setattr(reasoning, "_ask_model", replies)
    result = await StepExecutor(db).run(OWNER, current,
        ActionStep(step_type="prepare", capability_needed="document.create", intent="Nuova bozza controllata."),
        may_touch_the_world=False)
    assert result.status == "succeeded" and replies.await_count == 2
    assert current.prepared_result_id != previous_id and current.prepared_review is None
    return current.prepared_result_id


@pytest.mark.asyncio
@pytest.mark.parametrize("during_judgement", [False, True])
async def test_new_identical_preparation_does_not_inherit_or_receive_the_old_repair(monkeypatch, clock, during_judgement):
    db, goal, _plan, source, _text, verifier = await deferred_review(monkeypatch)
    new_ids = []

    async def replan(*args, **kwargs):
        new_ids.append(await new_identical_preparation(db, goal.id, source, monkeypatch))
        return repair_plan()

    reconsider = AsyncMock(side_effect=replan)
    monkeypatch.setattr(reasoning, "reconsider", reconsider)
    monkeypatch.setattr(AgentService, "_next", AsyncMock(return_value=("budget", None)))
    if not during_judgement:
        new_ids.append(await new_identical_preparation(db, goal.id, source, monkeypatch))
    await resume_due(db, goal.id, clock)
    current = await AgentService(db).repo.get_goal(OWNER, goal.id)
    saved_plan = await AgentService(db).repo.plan_for(OWNER, goal.id)
    assert current.prepared_result_id == new_ids[-1] and current.prepared_review is None
    assert current.prepared_text == UNSUPPORTED and len(saved_plan.steps) == 2
    assert reconsider.await_count == int(during_judgement) and verifier.await_count == 1
    assert saved_plan.prepared_review_reconsidered == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["owner", "knowledge", "authority", "deferred", "cancelled", "revoked"])
async def test_pending_judgement_preserves_person_source_and_owner_boundaries(monkeypatch, clock, boundary):
    db, goal, _plan, _source, _text, verifier = await deferred_review(monkeypatch)
    service = AgentService(db)
    if boundary in ("knowledge", "authority"):
        field = "requires_user_input" if boundary == "knowledge" else "requires_user_authority"
        await db.agent_goals.update_one({"owner_id": OWNER, "id": goal.id}, {"$set": {field: True}})
    elif boundary == "deferred":
        await service.repo.defer_goal(OWNER, goal.id, until=(clock[0] + timedelta(hours=2)).isoformat())
    elif boundary == "cancelled":
        await service.cancel(OWNER, goal.id, reason="Ritiro sintetico.")
    elif boundary == "revoked":
        from opportunities.service import OpportunityService
        await OpportunityService(db).dismiss(OWNER, goal.opportunity_id)
    reconsider = AsyncMock(return_value=repair_plan())
    monkeypatch.setattr(reasoning, "reconsider", reconsider)
    if boundary == "owner":
        result = await AgentService(db).advance("foreign-synthetic-owner", goal.id, worker_id="ambient:foreign")
        assert result["reason"] == "unknown_goal"
    else:
        from ambient.models import AmbientWake
        if boundary != "deferred":
            clock[0] = datetime.fromisoformat(goal.next_run_at) + timedelta(seconds=1)
        wake = AmbientWake(owner_id=OWNER, reason="opportunity_revisit", source_ref=f"goal:{goal.id}")
        # A stale wake is not permission to bypass the person's control.
        await advance_wake(db, wake)
    assert reconsider.await_count == 0 and verifier.await_count == 1
    current = await service.repo.get_goal(OWNER, goal.id)
    assert current.prepared_text in (UNSUPPORTED, "")
    saved_plan = await db.agent_plans.find_one({"owner_id": OWNER, "goal_id": goal.id})
    assert len(saved_plan["steps"]) == 2
    if boundary in ("cancelled", "revoked"):
        assert not current.is_open and current.next_run_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["revoked", "cancelled"])
async def test_revocation_during_the_pending_judgement_cannot_save_a_repair(monkeypatch, clock, boundary):
    db, goal, _plan, _source, _text, verifier = await deferred_review(monkeypatch)

    async def replan(*args, **kwargs):
        if boundary == "revoked":
            from opportunities.service import OpportunityService
            await OpportunityService(db).dismiss(OWNER, goal.opportunity_id)
        else:
            await AgentService(db).cancel(OWNER, goal.id, reason="Ritiro durante il giudizio.")
        return repair_plan()

    reconsider = AsyncMock(side_effect=replan)
    monkeypatch.setattr(reasoning, "reconsider", reconsider)
    await resume_due(db, goal.id, clock)
    current = await AgentService(db).repo.get_goal(OWNER, goal.id)
    saved_plan = await db.agent_plans.find_one({"owner_id": OWNER, "goal_id": goal.id})
    assert not current.is_open and current.next_run_at is None
    assert len(saved_plan["steps"]) == 2 and not saved_plan.get("prepared_review_reconsidered")
    assert reconsider.await_count == verifier.await_count == 1
