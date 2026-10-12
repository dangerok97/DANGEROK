"""Invalid model output is diagnosed, never substituted with another action.

The engine, source reader, preparation and persistence are real over an owned
synthetic database. SDK tests replace HTTP only; no live model or effect runs.
"""
from copy import deepcopy
import json
from unittest.mock import AsyncMock, patch

import pytest

from agent import preparation
from agent.models import ActionStep, AgentBudget, AgentRun
from agent.service import AgentService
from scripts import autonomy_completion_eval_v162 as gate
from test_agent_preparation_dependency_v162 import OWNER, MEMORY, RESULT, comparison_claim_review, fake_gemini
from test_pending_outcome_contract_v162 import synthetic_transport_only  # noqa: F401
from test_preparation_passages_v162 import source_claim
from test_preparation_recovery_v162 import seed_recovery


async def failed_with_pending():
    db, goal, plan, source, text = await seed_recovery()
    failed = plan.steps[1]
    failed.status = "failed"
    failed.note = "La risposta precedente non rispettava il formato richiesto."
    pending = ActionStep(ordinal=2, step_type="inspect", capability_needed="information.read",
        input_refs=[MEMORY], intent="Una lettura ancora da valutare, non scelta dal modello.")
    plan.steps.append(pending)
    await AgentService(db).repo.save_plan(plan)
    return db, goal, plan, source, text, failed, pending


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["execute", "skip"])
@pytest.mark.parametrize("reference", ["failed", "unknown", "missing"])
async def test_invalid_selection_reaches_reconsider_without_executing_or_skipping_another_step(
    monkeypatch, decision, reference,
):
    db, goal, plan, source, text, failed, pending = await failed_with_pending()
    original_steps = [deepcopy(step.model_dump()) for step in plan.steps]
    response = {"decision": decision, "reasoning": "Scelta sintetica non valida."}
    if reference != "missing":
        response["step_id"] = failed.id if reference == "failed" else "unknown-private-marker"
    captured = []

    def reply(_system, payload):
        if "what_happened" not in payload:
            return response
        captured.append(payload)
        return {"decision": "wait", "wait_minutes": 17,
                "reasoning": "Attesa decisa dal modello sintetico dopo la diagnosi."}

    transported = fake_gemini(monkeypatch, reply)
    with gate.isolated_engine(db, mode="live") as probe:
        service = AgentService(db)
        executed = AsyncMock(return_value={"state": "unexpected_execution"})
        finished = AsyncMock(return_value={"state": "unexpected_finish"})
        with patch.object(service, "_do_step", executed), patch.object(service, "_finish", finished), \
             patch.object(service, "_consider_visibility", AsyncMock()):
            result = await service.advance(OWNER, goal.id)
        assert result["state"] == "waiting" and result["for_minutes"] == 17
        executed.assert_not_awaited()
        finished.assert_not_awaited()
        event = captured[0]["what_happened"]
        assert event["problem"] == "action_selection_invalid"
        assert event["selection"]["decision"] == decision
        assert event["selection"]["issue"] == {
            "failed": "not_pending", "unknown": "unknown_step", "missing": "missing_step_id",
        }[reference]
        assert event["selection"]["candidate_step_ids"] == [pending.id]
        assert event["selection"]["requested_step_id"] == (failed.id if reference == "failed" else None)
        assert "unknown-private-marker" not in json.dumps(event)
        current = await AgentService(db).repo.get_goal(OWNER, goal.id)
        current_plan = await AgentService(db).repo.plan_for(OWNER, goal.id)
        assert current.status == "waiting" and current.next_run_at
        assert [step.model_dump() for step in current_plan.steps] == original_steps
        recorded = await db.agent_journal.find_one({"owner_id": OWNER, "goal_id": goal.id,
                                                   "kind": "chose_next"})
        assert recorded["detail"]["problem"] == "action_selection_invalid"
        assert recorded["detail"]["selection"] == event["selection"]
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 2
        assert not probe.blocked_effects and not probe.network.blocked


@pytest.mark.asyncio
async def test_invalid_selection_can_replan_and_complete_without_rewriting_failed_history(monkeypatch):
    db, goal, plan, source, text, failed, pending = await failed_with_pending()
    failed_history = deepcopy(failed.model_dump())
    selection_count = 0

    def reply(_system, payload):
        nonlocal selection_count
        if "what_happened" in payload:
            assert payload["what_happened"]["problem"] == "action_selection_invalid"
            return {"decision": "modify", "reasoning": "Preparare il risultato dalle fonti già lette.",
                "replace_step_ids": [pending.id],
                "revised_steps": [{"step_type": "prepare", "capability_needed": "document.create",
                    "input_refs": [MEMORY], "intent": "Preparare il confronto dalle prove correnti."}]}
        if "what_has_been_found" in payload:
            selection_count += 1
            if selection_count == 1:
                return {"decision": "execute", "step_id": failed.id}
            candidate, = payload["still_to_do"]
            return {"decision": "execute", "step_id": candidate["id"]}
        if "what_was_done" in payload:
            assert payload["what_was_done"]["prepared_result"] == RESULT
            return {"outcome": "achieved", "reasoning": "Verifica sintetica del risultato preparato."}
        answer = {"content": RESULT, "evidence_ids": [source.id]}
        if "draft" in payload:
            answer.update(verified=True, claim_review=comparison_claim_review(source.id))
        return answer

    transported = fake_gemini(monkeypatch, reply)
    with gate.isolated_engine(db, mode="live") as probe:
        service = AgentService(db)
        with patch.object(service, "_consider_visibility", AsyncMock()):
            result = await service.advance(OWNER, goal.id)
        current = await AgentService(db).repo.get_goal(OWNER, goal.id)
        current_plan = await AgentService(db).repo.plan_for(OWNER, goal.id)
        assert result["state"] == "completed" and current.status == "completed"
        assert current.prepared_text == RESULT and current.prepared_sources == [source.id]
        assert current_plan.steps[1].model_dump() == failed_history
        assert current_plan.steps[2].status == "skipped"
        assert current_plan.steps[3].status == "succeeded"
        assert selection_count == 2 and len(transported) == probe.model_attempts == 6
        assert await db.agent_evidence.count_documents({"goal_id": goal.id,
            "provenance.capability": "information.read"}) == 1
        assert await db.agent_action_attempts.count_documents({}) == 0
        assert not probe.blocked_effects and not probe.network.blocked


@pytest.mark.asyncio
async def test_invalid_selection_keeps_existing_background_cap_and_durable_budget_retry(monkeypatch):
    db, goal, plan, source, text, failed, pending = await failed_with_pending()
    transported = fake_gemini(monkeypatch, lambda _system, payload: {
        "decision": "execute", "step_id": failed.id,
    })
    with gate.isolated_engine(db, mode="live") as probe:
        for attempt in range(1, 4):
            service = AgentService(db)
            executed = AsyncMock(return_value={"state": "unexpected_execution"})
            budget = AgentBudget(max_cognitive_calls=1)
            with patch.object(service, "_do_step", executed), patch.object(service, "_consider_visibility", AsyncMock()):
                await service.advance(OWNER, goal.id, budget=budget, worker_id="ambient:protocol-test")
            current = await service.repo.get_goal(OWNER, goal.id)
            executed.assert_not_awaited()
            assert current.background_runs == attempt and current.status == "active"
            assert bool(current.next_run_at) is (attempt < 3)
            assert budget.cognitive_calls == 1 and budget.steps_executed == 0
        service = AgentService(db)
        assert (await service.advance(OWNER, goal.id, worker_id="ambient:protocol-test"))["state"] == "background_paused"
        assert len(transported) == probe.model_attempts == 3
        assert not probe.steps and not probe.blocked_effects


@pytest.mark.asyncio
@pytest.mark.parametrize("fallback", [False, True], ids=["ordinary_step", "finish_fallback"])
@pytest.mark.parametrize("failure,stage,field,issue,received", [
    ("generation_missing_refs", "generation", "evidence_ids", "missing", "missing"),
    ("audit_object", "audit", "content", "wrong_type", "object"),
    ("audit_foreign_ref", "audit", "evidence_ids", "not_supplied", "array"),
])
async def test_structural_preparation_error_is_specific_and_survives_reload_without_coercion(
    monkeypatch, fallback, failure, stage, field, issue, received,
):
    db, goal, plan, source, text = await seed_recovery()
    resumed = False
    private = "private-model-payload-must-not-enter-feedback"

    def reply(_system, payload):
        if "what_happened" in payload:
            return {"decision": "modify", "reasoning": "Correggere il formato, conservando le fonti lette.",
                "replace_step_ids": [plan.steps[1].id] if fallback else [],
                "revised_steps": [{"step_type": "prepare", "capability_needed": "document.create",
                    "input_refs": [MEMORY], "intent": "Preparare il confronto dalle prove correnti."}]}
        if not resumed:
            if failure == "generation_missing_refs":
                return {"content": RESULT}
            if "draft" in payload:
                return {"verified": True,
                    "content": {"private": private} if failure == "audit_object" else RESULT,
                    "evidence_ids": [private] if failure == "audit_foreign_ref" else [source.id],
                    "reason": private}
        answer = {"content": RESULT, "evidence_ids": [source.id]}
        if "draft" in payload:
            answer.update(verified=True, claim_review=comparison_claim_review(source.id))
        return answer

    transported = fake_gemini(monkeypatch, reply)
    with gate.isolated_engine(db, mode="live") as probe:
        service = AgentService(db)
        run, budget = AgentRun(owner_id=OWNER, goal_id=goal.id), AgentBudget()
        if fallback:
            await service._finish(OWNER, goal, plan, run, budget, language="it")
        else:
            await service._do_step(OWNER, goal, plan, plan.steps[1], run, budget, language="it")
        initial_calls = 2 if failure == "generation_missing_refs" else 3
        assert len(transported) == initial_calls
        reconsidered = transported[-1]["payload"]
        event = reconsidered["what_happened"]["result"]
        assert event["problem"] == ("preparation_ungrounded" if stage == "generation" else "preparation_review_invalid")
        assert event["worth_retrying"] is False  # No automatic semantic/schema retry.
        encoded = reconsidered[preparation._FEEDBACK_FIELD]
        immediate = json.loads(encoded[len(preparation._FEEDBACK_PREFIX):])
        expected = {"field": field, "issue": issue, "received": received}
        assert immediate["origin"] == "preparation_protocol" and immediate["stage"] == stage
        assert immediate["validation_errors"] == [expected]
        assert private not in json.dumps(immediate)
        saved = await service.repo.get_goal(OWNER, goal.id)
        assert not saved.prepared_text and not saved.prepared_sources and not saved.prepared_result_id
        assert await db.agent_evidence.count_documents({"goal_id": goal.id}) == 1
        record = await db.agent_journal.find_one({"owner_id": OWNER, "goal_id": goal.id,
                                                 "kind": preparation._FEEDBACK_KIND})
        assert record["detail"]["feedback"]["validation_errors"] == [expected]
        assert private not in json.dumps(record, default=str)

        # New service and objects: only persisted scoped diagnostics can reach
        # the next model call, which must still supply valid text and citations.
        resumed = True
        service = AgentService(db)
        current = await service.repo.get_goal(OWNER, goal.id)
        current_plan = await service.repo.plan_for(OWNER, goal.id)
        await service._do_step(OWNER, current, current_plan, current_plan.steps[-1],
            AgentRun(owner_id=OWNER, goal_id=goal.id), AgentBudget(), language="it")
        for call in transported[initial_calls:]:
            feedback = call["payload"][preparation._FEEDBACK_FIELD]
            assert feedback["validation_errors"] == [expected] and feedback["stage"] == stage
            assert source_claim(call["payload"]["evidence"][0]) == text
        current = await service.repo.get_goal(OWNER, goal.id)
        assert current.prepared_text == RESULT and current.prepared_sources == [source.id]
        assert current.prepared_result_id and current.prepared_review is None
        assert len(transported) == probe.model_attempts == probe.model_http_requests == initial_calls + 2
        assert await db.agent_action_attempts.count_documents({}) == 0
        assert not probe.blocked_effects and not probe.network.blocked
