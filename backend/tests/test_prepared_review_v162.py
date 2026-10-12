"""An explicit incomplete review belongs to one saved preparation only.

The reader, preparation, repository and service are real, with owned synthetic
records and controlled judgements. No provider call or external effect occurs.
"""
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agent import reasoning
from agent.execution import StepExecutor
from agent.models import ActionIntent, AgentBudget, AgentRun, GoalVerification
from agent.prepared_review import (
    PreparedReviewUnavailable, capture_prepared_result, current_prepared_result,
    current_prepared_review, persist_prepared_review, prepared_result_ref,
)
from agent.service import AgentService
from scripts import autonomy_completion_eval_v162 as gate
from test_pending_outcome_contract_v162 import synthetic_transport_only  # noqa: F401
from test_verification_recovery_v162 import (
    OWNER, MEMORY, MISSING, REASON, UNSUPPORTED, CORRECTED, prepared_with_missed_defect,
)


def negative_verdict(goal):
    return GoalVerification(goal_id=goal.id, outcome="uncertain",
        what_is_missing=MISSING, reasoning=REASON)


async def review_current(db, goal):
    assert await persist_prepared_review(db, OWNER, goal,
        capture_prepared_result(goal), negative_verdict(goal))


async def prepare_again(db, goal, step, source, text):
    replies = AsyncMock(side_effect=[
        {"content": text, "evidence_ids": [source.id]},
        {"verified": True, "content": text, "evidence_ids": [source.id]},
    ])
    with patch.object(reasoning, "_ask_model", replies):
        result = await StepExecutor(db).run(OWNER, goal, step, may_touch_the_world=False)
    assert result.status == "succeeded" and replies.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome,public", [("partially_achieved", "partial"), ("uncertain", "uncertain")])
async def test_incomplete_review_survives_reload_and_qualifies_the_exact_public_draft(outcome, public):
    db, goal, plan, source, _ = await prepared_with_missed_defect()
    service = AgentService(db)
    original_ai = deepcopy(goal.for_ai())
    before_evidence = await db.agent_evidence.count_documents({})
    run = AgentRun(owner_id=OWNER, goal_id=goal.id)
    with patch.object(reasoning, "verify_goal", AsyncMock(return_value={
        "outcome": outcome, "what_is_missing": MISSING, "reasoning": REASON,
    })), patch.object(service, "_reconsider", AsyncMock(return_value=None)):
        result = await service._finish(OWNER, goal, plan, run, AgentBudget(), language="it")
    assert result["state"] == "in_progress"
    reloaded = AgentService(db)
    saved = await reloaded.repo.get_goal(OWNER, goal.id)
    detail = await reloaded.for_detail(OWNER, goal.id)
    review = detail.get("prepared_review")
    assert review is not None, "A rejected current draft must retain its actual review in the public projection."
    assert review["outcome"] == public
    assert review["what_is_missing"] == MISSING and review["reasoning"] == REASON
    assert datetime.fromisoformat(review["reviewed_at"]).tzinfo is not None
    assert set(review) == {"outcome", "what_is_missing", "reasoning", "reviewed_at"}
    assert detail["prepared_text"] == saved.prepared_text == UNSUPPORTED
    assert saved.prepared_sources == [source.id] and saved.status == "active"
    assert saved.for_ai() == original_ai
    facts = await reloaded._run_facts(OWNER, saved, run)
    assert facts["prepared_review"] == review
    assert facts["_prepared_result_ref"]
    assert not facts["how_it_stands"]["finished"]
    assert await db.agent_evidence.count_documents({}) == before_evidence
    assert await db.agent_action_attempts.count_documents({}) == 0
    assert await db.agent_needs.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("text", [UNSUPPORTED, CORRECTED], ids=["identical_new_preparation", "corrected_preparation"])
async def test_successful_preparation_mints_identity_and_retires_previous_review_even_with_same_text(text):
    db, goal, plan, source, _ = await prepared_with_missed_defect()
    await review_current(db, goal)
    old_identity, old_ref = goal.prepared_result_id, prepared_result_ref(goal)
    assert old_identity and current_prepared_review(goal)
    await prepare_again(db, goal, plan.steps[1], source, text)
    current = await current_prepared_result(db, OWNER, goal.id)
    assert current.goal.prepared_result_id != old_identity
    assert current.ref != old_ref and current.review is None
    assert current.goal.prepared_text == text and current.goal.prepared_sources == [source.id]
    assert current.goal.prepared_review is None and goal.prepared_review is None
    assert current.goal.for_human()["prepared_text"] == text
    assert current.goal.for_human()["prepared_review"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["same_text_new_preparation", "different_text", "criteria", "cancelled"])
async def test_stale_verifier_cannot_review_or_overwrite_new_preparation_or_user_control(change):
    db, goal, plan, source, _ = await prepared_with_missed_defect()
    service = AgentService(db)
    old_identity = goal.prepared_result_id
    latest = None

    async def verifier(_goal, *, evidence, language):
        nonlocal latest
        assert evidence["prepared_result"] == UNSUPPORTED
        assert evidence["prepared_source_refs"] == [source.id]
        newer = await service.repo.get_goal(OWNER, goal.id)
        if change in ("same_text_new_preparation", "different_text"):
            await prepare_again(db, newer, plan.steps[1], source,
                UNSUPPORTED if change == "same_text_new_preparation" else CORRECTED)
            assert newer.prepared_result_id != old_identity
        elif change == "criteria":
            newer.success_criteria.append("Conservare anche il nuovo requisito esplicito della persona.")
            await service.repo.save_goal(newer)
        else:
            assert (await AgentService(db).cancel(OWNER, goal.id))["state"] == "cancelled"
        latest = await service.repo.get_goal(OWNER, goal.id)
        return {"outcome": "uncertain", "what_is_missing": MISSING, "reasoning": REASON}

    with gate.isolated_engine(db), patch.object(reasoning, "verify_goal", verifier), patch.object(
        service, "_reconsider", AsyncMock(return_value=None),
    ) as reconsider, patch.object(service, "_consider_visibility", AsyncMock()):
        result = await service.advance(OWNER, goal.id)
    saved = await service.repo.get_goal(OWNER, goal.id)
    assert result["state"] == ("cancelled" if change == "cancelled" else "in_progress")
    assert saved.prepared_text == latest.prepared_text
    assert saved.prepared_sources == latest.prepared_sources
    assert saved.prepared_result_id == latest.prepared_result_id
    assert saved.success_criteria == latest.success_criteria and saved.status == latest.status
    assert saved.prepared_review is None and reconsider.await_count == 0
    assert await db.agent_journal.count_documents({"goal_id": goal.id, "kind": "verified"}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["text", "citations", "source_revision", "requirements"])
async def test_review_projection_and_cas_require_the_entire_current_artifact(change):
    db, goal, _, source, _ = await prepared_with_missed_defect()
    snapshot = capture_prepared_result(goal)
    await review_current(db, goal)
    original_ref = prepared_result_ref(goal)
    changed = goal.model_copy(deep=True)
    if change == "text":
        changed.prepared_text += " Nuova frase."
    elif change == "citations":
        changed.prepared_sources = ["evd_different_synthetic_source", source.id]
    elif change == "source_revision":
        changed.opportunity_revision = "different-source-revision"
    else:
        changed.success_criteria.append("Un requisito aggiuntivo esplicito.")
    # Persist a concurrent change without touching the old snapshot, just as
    # a prior worker would still hold it while the verifier is in flight.
    await AgentService(db).repo.save_goal(changed)
    assert prepared_result_ref(changed) != original_ref
    assert current_prepared_review(changed) is None
    assert not await persist_prepared_review(db, OWNER, goal, snapshot, negative_verdict(goal))
    current = await current_prepared_result(db, OWNER, goal.id)
    assert current.review is None and current.ref == prepared_result_ref(changed)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["forget", "correct"])
async def test_canonical_memory_change_during_verification_invalidates_old_draft_and_review(change):
    from conversation_engine.ai_core.models import MemoryCandidate
    from life_memory.governance import MemoryGovernanceService

    db, goal, plan, source, text = await prepared_with_missed_defect()
    await review_current(db, goal)
    service = AgentService(db)

    async def verifier(*args, **kwargs):
        changed = await MemoryGovernanceService(db).apply(
            user_id=OWNER, session_id="synthetic-prepared-review",
            reasoning_epoch=f"prepared-review:{change}", candidate_index=0,
            candidate=MemoryCandidate(operation=change, existing_memory_ref=MEMORY,
                summary=text.replace("84", "88") if change == "correct" else "Dimentica la nota ritirata.",
                user_authorized=True, authority="user_stated", epistemic_status="confirmed", confidence=0.95,
                permanence="indefinite", reason_for_future_utility="Conservare le condizioni della scelta ancora aperta."),
        )
        assert changed.persisted
        return {"outcome": "uncertain", "what_is_missing": MISSING, "reasoning": REASON}

    with gate.isolated_engine(db), patch.object(reasoning, "verify_goal", verifier), patch.object(
        service, "_reconsider", AsyncMock(return_value=None),
    ) as reconsider:
        result = await service._finish(OWNER, goal, plan,
            AgentRun(owner_id=OWNER, goal_id=goal.id), AgentBudget(), language="it")
    saved = await service.repo.get_goal(OWNER, goal.id)
    assert result["state"] == ("abandoned" if change == "forget" else "source_changed")
    assert not saved.prepared_text and not saved.prepared_sources
    assert current_prepared_review(saved) is None and prepared_result_ref(saved) == ""
    assert reconsider.await_count == 0
    assert await db.agent_journal.count_documents({"goal_id": goal.id, "kind": "verified"}) == 0
    detail = await service.for_detail(OWNER, goal.id)
    assert detail is None or not detail.get("prepared_text")


@pytest.mark.asyncio
async def test_legacy_preparation_can_receive_negative_review_without_fabricating_identity_or_success():
    db, goal, plan, source, _ = await prepared_with_missed_defect()
    await db.agent_goals.update_one({"owner_id": OWNER, "id": goal.id},
        {"$unset": {"prepared_result_id": "", "prepared_review": ""}})
    state = await current_prepared_result(db, OWNER, goal.id)
    assert state.goal.prepared_result_id == "" and state.review is None
    assert state.ref.startswith("prepared_result:legacy:")
    assert "prepared_result_id" not in await db.agent_goals.find_one({"id": goal.id})
    await review_current(db, state.goal)
    reloaded = await current_prepared_result(db, OWNER, goal.id)
    assert reloaded.ref == state.ref and reloaded.goal.prepared_result_id == ""
    assert reloaded.review["outcome"] == "uncertain"
    assert reloaded.goal.status == "active" and reloaded.goal.completed_at is None
    assert reloaded.goal.for_human()["prepared_text"] == UNSUPPORTED


@pytest.mark.asyncio
async def test_external_approval_draft_is_visible_without_an_internal_negative_review():
    db, goal, plan, _, _ = await prepared_with_missed_defect(CORRECTED)
    service = AgentService(db)
    goal.status, goal.requires_user_authority = "waiting", True
    await service.repo.save_goal(goal)
    intent = ActionIntent(owner_id=OWNER, goal_id=goal.id, step_id="stp_synthetic_approval",
        capability="calendar.write", effect_summary="Proposta sintetica ancora da autorizzare.")
    await service.executor._record(intent)
    with patch.object(reasoning, "verify_goal", AsyncMock(return_value={
        "outcome": "uncertain", "what_is_missing": "Manca l'accettazione esterna.",
        "reasoning": "La bozza è disponibile; l'azione non è stata eseguita.",
    })), patch.object(service, "_reconsider", AsyncMock()) as reconsider:
        await service._finish(OWNER, goal, plan,
            AgentRun(owner_id=OWNER, goal_id=goal.id), AgentBudget(), language="it")
    detail = await AgentService(db).for_detail(OWNER, goal.id)
    saved = await service.repo.get_goal(OWNER, goal.id)
    assert detail["prepared_text"] == CORRECTED and detail["prepared_review"] is None
    assert saved.requires_user_authority and saved.status == "waiting"
    assert reconsider.await_count == 0
    assert await db.agent_receipts.count_documents({}) == 0


@pytest.mark.asyncio
async def test_owner_and_unavailable_boundaries_never_mean_an_unreviewed_success():
    db, goal, _, _, _ = await prepared_with_missed_defect()
    snapshot = capture_prepared_result(goal)
    assert await current_prepared_result(db, "other-synthetic-owner", goal.id) is None
    assert not await persist_prepared_review(db, "other-synthetic-owner", goal,
        snapshot, negative_verdict(goal))
    assert not await persist_prepared_review(db, OWNER, goal, snapshot,
        GoalVerification(goal_id=goal.id, outcome="achieved"))
    assert (await current_prepared_result(db, OWNER, goal.id)).review is None
    fault_db = SimpleNamespace(agent_goals=SimpleNamespace(
        find_one=AsyncMock(side_effect=RuntimeError("synthetic read failure")),
        update_one=AsyncMock(side_effect=RuntimeError("synthetic write failure")),
    ))
    with pytest.raises(PreparedReviewUnavailable, match="RuntimeError"):
        await current_prepared_result(fault_db, OWNER, goal.id)
    with pytest.raises(PreparedReviewUnavailable, match="RuntimeError"):
        await persist_prepared_review(fault_db, OWNER, goal, snapshot, negative_verdict(goal))
    assert goal.prepared_review is None
    assert (await current_prepared_result(db, OWNER, goal.id)).review is None


@pytest.mark.asyncio
async def test_later_authorized_success_retires_negative_review_on_the_same_artifact():
    db, goal, plan, source, _ = await prepared_with_missed_defect(CORRECTED)
    await review_current(db, goal)
    snapshot = capture_prepared_result(goal)
    service = AgentService(db)
    with gate.isolated_engine(db), patch.object(reasoning, "verify_goal", AsyncMock(return_value={
        "outcome": "achieved", "reasoning": "La nuova verifica conferma il risultato e i suoi limiti.",
    })), patch.object(service, "_reconsider", AsyncMock()) as reconsider, patch.object(
        service, "_observe_life_change", AsyncMock(),
    ):
        result = await service._finish(OWNER, goal, plan,
            AgentRun(owner_id=OWNER, goal_id=goal.id), AgentBudget(), language="it")
    current = await current_prepared_result(db, OWNER, goal.id)
    assert result["state"] == current.goal.status == "completed"
    assert current.goal.completed_at and current.review is None
    assert current.goal.prepared_review is None and current.ref == snapshot.ref
    assert current.goal.prepared_result_id == snapshot.prepared_result_id
    assert current.goal.prepared_text == CORRECTED and current.goal.prepared_sources == [source.id]
    assert reconsider.await_count == 0
    assert await db.agent_journal.count_documents({"goal_id": goal.id, "kind": "goal_completed"}) == 1
    detail = await service.for_detail(OWNER, goal.id)
    assert detail["prepared_review"] is None and detail["prepared_text"] == CORRECTED


@pytest.mark.asyncio
async def test_late_achieved_cannot_clear_new_drafts_review_or_close_it():
    db, goal, plan, source, _ = await prepared_with_missed_defect(CORRECTED)
    await review_current(db, goal)
    old_snapshot = capture_prepared_result(goal)
    service = AgentService(db)
    latest = None

    async def verifier(_goal, *, evidence, language):
        nonlocal latest
        assert evidence["prepared_result"] == CORRECTED
        newer = await service.repo.get_goal(OWNER, goal.id)
        await prepare_again(db, newer, plan.steps[1], source, UNSUPPORTED)
        await review_current(db, newer)
        latest = await current_prepared_result(db, OWNER, goal.id)
        assert latest.ref != old_snapshot.ref and latest.review
        return {"outcome": "achieved", "reasoning": "Solo il vecchio testo rispettava la fonte."}

    with gate.isolated_engine(db), patch.object(reasoning, "verify_goal", verifier), patch.object(
        service, "_reconsider", AsyncMock(),
    ) as reconsider, patch.object(service, "_consider_visibility", AsyncMock()), patch.object(
        service, "_observe_life_change", AsyncMock(),
    ) as observe:
        result = await service.advance(OWNER, goal.id)
    current = await current_prepared_result(db, OWNER, goal.id)
    assert result["state"] == "in_progress" and current.goal.status == "active"
    assert current.ref == latest.ref and current.review == latest.review
    assert current.goal.prepared_text == UNSUPPORTED and not current.goal.completed_at
    assert reconsider.await_count == observe.await_count == 0
    assert await db.agent_journal.count_documents({"goal_id": goal.id, "kind": "goal_completed"}) == 0
    assert (await service.repo.plan_for(OWNER, goal.id)).model_dump() == plan.model_dump()
    assert (await db.opportunities.find_one({"owner_id": OWNER, "id": goal.opportunity_id}))["status"] == "active"
