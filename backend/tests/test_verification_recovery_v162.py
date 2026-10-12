"""A final review can repair a prepared result through the existing plan.

The actual reader, preparation, executor, persistence and service run against
owned synthetic records. An intentionally mistaken audit and controlled
verdicts exercise recovery, not live model quality. Verifier/reconsideration
use the real SDK with fake HTTP; no external action or notification occurs.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
from unittest.mock import AsyncMock, patch

import pytest

from agent import reasoning
from agent.execution import StepExecutor
from agent.models import ActionIntent, AgentBudget, AgentRun, ExecutionReceipt
from agent.service import AgentService
from scripts import autonomy_completion_eval_v162 as gate
from test_agent_preparation_dependency_v162 import OWNER, MEMORY, RESULT, fake_gemini
from test_pending_outcome_contract_v162 import synthetic_transport_only  # noqa: F401
from test_preparation_recovery_v162 import seed_recovery


UNSUPPORTED = RESULT + " B permette di interrompere senza vincoli."
CORRECTED = RESULT + " La nota non specifica i vincoli di interruzione di B."
MISSING = "La libertà di interrompere B non è stabilita dalla nota; il confronto deve conservare questo limite."
REASON = "Una conclusione materiale nella bozza supera i dati letti."
FEEDBACK = "preparation_feedback_non_authoritative"


async def prepared_with_missed_defect(draft=UNSUPPORTED):
    db, goal, plan, source, text = await seed_recovery()
    # Deliberately reproduce an earlier audit that accepted a bad clause.
    # This is the real save path, not a manually injected prepared_text.
    replies = AsyncMock(side_effect=[
        {"content": draft, "evidence_ids": [source.id]},
        {"verified": True, "content": draft, "evidence_ids": [source.id]},
    ])
    with patch.object(reasoning, "_ask_model", replies):
        result = await StepExecutor(db).run(OWNER, goal, plan.steps[1], may_touch_the_world=False)
    assert result.status == "succeeded" and replies.await_count == 2
    assert goal.prepared_text == draft and goal.prepared_sources == [source.id]
    plan.steps[1].status, plan.steps[1].note = "succeeded", result.observation
    await AgentService(db).repo.save_plan(plan)
    return db, goal, plan, source, text


def repair_plan():
    return {
        "decision": "modify", "reasoning": "Correggere la bozza usando la lettura corrente.",
        "revised_steps": [{
            "step_type": "prepare", "capability_needed": "document.create", "input_refs": [MEMORY],
            "intent": "Preparare il confronto lasciando ignote le condizioni non riportate.",
        }],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("verdict", ["partially_achieved", "uncertain"])
async def test_incomplete_verdict_reconsiders_then_repairs_after_reload_without_another_read(monkeypatch, verdict):
    db, goal, plan, source, text = await prepared_with_missed_defect()
    original_due = goal.next_run_at
    original_steps = deepcopy([step.model_dump() for step in plan.steps])
    resumed = False

    def reply(_system, payload):
        if "what_was_done" in payload:
            done = payload["what_was_done"]
            assert done["prepared_result"] == (CORRECTED if resumed else UNSUPPORTED)
            assert done["prepared_source_refs"] == [source.id]
            proof = next(row for row in done["what_was_found"] if row["evidence_id"] == source.id)
            assert proof["what_was_found"] == text
            return {"outcome": "achieved" if resumed else verdict,
                    "reasoning": "Il testo corretto rispetta la fonte." if resumed else REASON,
                    "what_is_missing": "" if resumed else MISSING}
        if "what_happened" in payload:
            return repair_plan()
        row, = payload["evidence"]
        assert resumed and row["id"] == source.id and row["claim"] == text
        return {"verified": True, "content": CORRECTED, "evidence_ids": [source.id]}

    transported = fake_gemini(monkeypatch, reply)
    with gate.isolated_engine(db, mode="live") as probe, patch.object(
        reasoning, "decide_visibility", AsyncMock(return_value={"outcome": "silent"}),
    ), patch.object(AgentService, "_observe_life_change", AsyncMock()):
        service = AgentService(db)
        budget = AgentBudget()
        result = await service._finish(OWNER, goal, plan,
            AgentRun(owner_id=OWNER, goal_id=goal.id), budget, language="it")
        reconsidered = [row["payload"] for row in transported if "what_happened" in row["payload"]]
        assert len(reconsidered) == 1, "An incomplete final review must reach the existing reconsideration path."
        assert result["state"] == "in_progress"
        failure = reconsidered[0]["what_happened"]["result"]
        assert failure["problem"] == "prepared_result_verification_incomplete"
        assert failure["verification_outcome"] == verdict
        assert failure["what_is_missing"] == MISSING and failure["reasoning"] == REASON
        assert failure["worth_retrying"] is True
        assert MISSING in json.dumps(reconsidered[0].get(FEEDBACK), ensure_ascii=False)
        assert budget.cognitive_calls == 2
        assert goal.prepared_text == UNSUPPORTED and goal.next_run_at == original_due
        assert goal.status == "active" and not goal.requires_user_input and not goal.requires_user_authority
        assert [step.model_dump() for step in plan.steps[:2]] == original_steps
        assert len(plan.steps) == 3 and plan.steps[-1].step_type == "prepare"
        assert plan.steps[-1].status == "pending"
        journal = await db.agent_journal.find_one({"owner_id": OWNER, "goal_id": goal.id,
            "kind": "preparation_review_feedback", "detail.feedback.origin": "goal_verification"})
        assert journal and MISSING in journal["detail"]["feedback"]["reason"]
        assert UNSUPPORTED not in json.dumps(journal["detail"], ensure_ascii=False)

        # A new service receives no in-memory review state. The normal loop
        # must load the planned repair and preparation's journal feedback.
        resumed = True
        service = AgentService(db)
        current = await service.repo.get_goal(OWNER, goal.id)
        pending_plan = await service.repo.plan_for(OWNER, goal.id)
        target = pending_plan.steps[-1]
        with patch.object(reasoning, "choose_next_action", AsyncMock(return_value={
            "decision": "execute", "step_id": target.id, "reasoning": "Eseguire la correzione già pianificata.",
        })):
            completed = await service.advance(OWNER, goal.id)
        assert completed["state"] == "completed"
        saved = await service.repo.get_goal(OWNER, goal.id)
        saved_plan = await service.repo.plan_for(OWNER, goal.id)
        assert saved.prepared_text == CORRECTED and saved.prepared_sources == [source.id]
        assert saved.completed_at and saved.status == "completed"
        assert [step.model_dump() for step in saved_plan.steps[:2]] == original_steps
        assert saved_plan.steps[-1].status == "succeeded"
        drafts = [row["payload"] for row in transported if "evidence" in row["payload"]]
        assert len(drafts) == 2
        assert drafts[0][FEEDBACK]["origin"] == "goal_verification"
        assert MISSING in drafts[0][FEEDBACK]["reason"]
        assert drafts[0]["evidence"][0]["memory_reads"] == source.provenance.for_ai()["memory_reads"]
        assert drafts[1]["draft"] == CORRECTED
        assert await db.agent_evidence.count_documents({"owner_id": OWNER, "goal_id": goal.id,
            "provenance.capability": "information.read"}) == 1
        assert await db.agent_action_attempts.count_documents({}) == 0
        assert await db.agent_needs.count_documents({}) == 0
        assert await db.delivery_plans.count_documents({}) == 0
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 5
        assert not probe.blocked_effects and not probe.network.blocked and probe.push_attempts == 0


@pytest.mark.asyncio
async def test_last_verification_budget_keeps_feedback_and_a_due_retry_without_extra_judgement(monkeypatch):
    db, goal, plan, source, text = await prepared_with_missed_defect()
    original_due = goal.next_run_at

    def reply(_system, payload):
        assert "what_was_done" in payload
        return {"outcome": "uncertain", "reasoning": REASON, "what_is_missing": MISSING}

    transported = fake_gemini(monkeypatch, reply)
    with gate.isolated_engine(db, mode="live") as probe:
        budget = AgentBudget(cognitive_calls=7)
        service = AgentService(db)
        result = await service._finish(OWNER, goal, plan,
            AgentRun(owner_id=OWNER, goal_id=goal.id), budget, language="it")
        assert result["state"] == "in_progress"
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 1
        assert budget.cognitive_calls == budget.max_cognitive_calls
        saved = await service.repo.get_goal(OWNER, goal.id)
        assert saved.prepared_text == UNSUPPORTED and saved.prepared_sources == [source.id]
        assert saved.status == "active" and saved.next_run_at != original_due
        assert datetime.fromisoformat(saved.next_run_at) > datetime.now(timezone.utc)
        feedback = await db.agent_journal.find_one({"owner_id": OWNER, "goal_id": goal.id,
            "kind": "preparation_review_feedback", "detail.feedback.origin": "goal_verification"})
        assert feedback and MISSING in feedback["detail"]["feedback"]["reason"]
        assert await db.agent_journal.count_documents({"owner_id": OWNER, "goal_id": goal.id,
            "kind": "continues_later"}) == 1
        assert len(plan.steps) == 2 and plan.steps[-1].status == "succeeded"
        assert not probe.blocked_effects and probe.push_attempts == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["wait", "ask", "continue"])
async def test_reconsidered_wait_question_or_continue_is_preserved_without_editing_the_draft(monkeypatch, decision):
    db, goal, plan, source, text = await prepared_with_missed_defect()
    original_due = goal.next_run_at

    def reply(_system, payload):
        if "what_was_done" in payload:
            return {"outcome": "partially_achieved", "reasoning": REASON, "what_is_missing": MISSING}
        assert "what_happened" in payload
        return {"decision": decision, "reasoning": "Decisione di recupero controllata.",
                "wait_minutes": 13, "asks": "Quale criterio personale preferisci?", "ask_kind": "knowledge"}

    transported = fake_gemini(monkeypatch, reply)
    with gate.isolated_engine(db, mode="live") as probe:
        service = AgentService(db)
        result = await service._finish(OWNER, goal, plan,
            AgentRun(owner_id=OWNER, goal_id=goal.id), AgentBudget(), language="it")
        saved = await service.repo.get_goal(OWNER, goal.id)
        assert saved.prepared_text == UNSUPPORTED and saved.prepared_sources == [source.id]
        if decision == "wait":
            assert result["state"] == "waiting" and result["for_minutes"] == 13
            assert saved.status == "waiting" and saved.next_run_at
            assert not saved.requires_user_input and not saved.requires_user_authority
        elif decision == "ask":
            assert result["state"] == "waiting_for_person" and result["kind"] == "knowledge"
            assert result["asks"] == "Quale criterio personale preferisci?"
            assert saved.status == "waiting" and saved.requires_user_input and not saved.requires_user_authority
        else:
            assert result["state"] == "in_progress" and saved.status == "active"
            assert saved.next_run_at == original_due
            assert len(plan.steps) == 2 and all(step.status == "succeeded" for step in plan.steps)
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 2
        assert await db.agent_action_attempts.count_documents({}) == 0
        assert not probe.blocked_effects and probe.push_attempts == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("verdict,state", [
    ("achieved", "completed"), ("not_achieved", "failed"),
    ("needs_followup", "waiting"), ("waiting_for_external_result", "waiting"),
])
async def test_existing_complete_failure_and_external_wait_verdicts_do_not_enter_draft_repair(monkeypatch, verdict, state):
    db, goal, plan, source, text = await prepared_with_missed_defect(draft=RESULT)

    def reply(_system, payload):
        assert "what_was_done" in payload
        return {"outcome": verdict, "reasoning": "Giudizio sintetico da propagare.", "revisit_in_hours": 2}

    transported = fake_gemini(monkeypatch, reply)
    with gate.isolated_engine(db, mode="live") as probe, patch.object(
        AgentService, "_observe_life_change", AsyncMock(),
    ):
        result = await AgentService(db)._finish(OWNER, goal, plan,
            AgentRun(owner_id=OWNER, goal_id=goal.id), AgentBudget(), language="it")
        assert result["state"] == goal.status == state
        assert goal.prepared_text == RESULT and goal.prepared_sources == [source.id]
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 1
        assert await db.agent_journal.count_documents({"owner_id": OWNER, "goal_id": goal.id,
            "kind": "preparation_review_feedback", "detail.feedback.origin": "goal_verification"}) == 0
        assert await db.agent_journal.count_documents({"owner_id": OWNER, "goal_id": goal.id,
            "kind": "replanned"}) == 0
        assert not probe.blocked_effects and probe.push_attempts == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("external_record", ["intent", "receipt"])
async def test_a_result_with_external_effect_state_keeps_its_existing_incomplete_path(monkeypatch, external_record):
    db, goal, plan, source, text = await prepared_with_missed_defect()
    service = AgentService(db)
    if external_record == "intent":
        intent = ActionIntent(owner_id=OWNER, goal_id=goal.id, step_id="stp_synthetic_external",
            capability="calendar.write", effect_summary="Intento sintetico mai eseguito.")
        await service.executor._record(intent)
    else:
        receipt = ExecutionReceipt(owner_id=OWNER, goal_id=goal.id, action_intent_id="int_synthetic_external",
            provider_status="unknown", capability="calendar.write", provider="synthetic_fixture")
        await db.agent_receipts.insert_one(receipt.model_dump())

    def reply(_system, payload):
        done = payload["what_was_done"]
        assert done["what_was_prepared"] if external_record == "intent" else done["what_the_services_said"]
        return {"outcome": "uncertain", "reasoning": "L'effetto esterno non è dimostrato.",
                "what_is_missing": "Manca una prova reale del risultato esterno."}

    transported = fake_gemini(monkeypatch, reply)
    with gate.isolated_engine(db, mode="live") as probe:
        result = await service._finish(OWNER, goal, plan,
            AgentRun(owner_id=OWNER, goal_id=goal.id), AgentBudget(), language="it")
        assert result["state"] == "in_progress" and goal.prepared_text == UNSUPPORTED
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 1
        assert await db.agent_journal.count_documents({"owner_id": OWNER, "goal_id": goal.id,
            "kind": "preparation_review_feedback", "detail.feedback.origin": "goal_verification"}) == 0
        assert len(plan.steps) == 2 and not probe.blocked_effects and probe.push_attempts == 0


@pytest.mark.asyncio
async def test_owner_boundary_prevents_another_account_from_entering_the_recovery(monkeypatch):
    db, goal, plan, source, text = await prepared_with_missed_defect()
    model = AsyncMock()
    with gate.isolated_engine(db), patch.object(reasoning, "_ask_model", model):
        assert await AgentService(db).advance("other-synthetic-owner", goal.id) == {
            "ok": False, "reason": "unknown_goal",
        }
    assert model.await_count == 0
    saved = await AgentService(db).repo.get_goal(OWNER, goal.id)
    assert saved.prepared_text == UNSUPPORTED and saved.status == "active"
    assert await db.agent_journal.count_documents({"owner_id": "other-synthetic-owner"}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("withdrawal", ["memory", "opportunity"])
async def test_source_withdrawal_during_verification_outranks_the_repair_judgement(monkeypatch, withdrawal):
    from opportunities.service import OpportunityService

    db, goal, plan, source, text = await prepared_with_missed_defect()
    transported = fake_gemini(monkeypatch, lambda _system, _payload: {
        "outcome": "uncertain", "reasoning": REASON, "what_is_missing": MISSING,
    })
    with gate.isolated_engine(db, mode="live") as probe:
        verify = reasoning.verify_goal

        async def withdraw_after_verdict(*args, **kwargs):
            answer = await verify(*args, **kwargs)
            if withdrawal == "memory":
                await db.memories.update_one({"user_id": OWNER, "id": MEMORY}, {"$set": {"status": "forgotten"}})
            else:
                assert (await OpportunityService(db).dismiss(OWNER, goal.opportunity_id))["ok"]
            return answer

        with patch.object(reasoning, "verify_goal", withdraw_after_verdict):
            result = await AgentService(db)._finish(OWNER, goal, plan,
                AgentRun(owner_id=OWNER, goal_id=goal.id), AgentBudget(), language="it")
        assert result["state"] in ("abandoned", "cancelled")
        saved = await AgentService(db).repo.get_goal(OWNER, goal.id)
        assert not saved.is_open and saved.next_run_at is None
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 1
        assert await db.agent_journal.count_documents({"owner_id": OWNER, "goal_id": goal.id,
            "kind": "preparation_review_feedback", "detail.feedback.origin": "goal_verification"}) == 0
        assert not probe.blocked_effects and probe.push_attempts == 0
