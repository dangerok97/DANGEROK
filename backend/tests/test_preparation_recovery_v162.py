"""Preparation failures retain their diagnosis and recover through the plan.

Synthetic records use the actual reader, preparation, executor and service.
Controlled replies exercise rejection and persistence, not live model quality.
The transport tests use the real SDK with fake HTTP; no external effect occurs.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from unittest.mock import AsyncMock, patch

from mongomock_motor import AsyncMongoMockClient
import pytest

from agent import reasoning
from agent.evidence import EvidenceStore
from agent.execution import StepExecutor
from agent.models import ActionPlan, ActionStep, AgentBudget, AgentRun
from agent.service import AgentService
from agent.source_refresh import context as source_context
from opportunities.models import EvidenceRef, Opportunity
from opportunities.repository import OpportunityRepository
from scripts import autonomy_completion_eval_v162 as gate
from test_agent_preparation_dependency_v162 import (
    OWNER, MEMORY, RESULT, SOURCE, fake_gemini, seed,
)
from test_pending_outcome_contract_v162 import synthetic_transport_only  # noqa: F401


async def seed_recovery():
    db = AsyncMongoMockClient().preparation_recovery_v162
    goal, text = await seed(db)
    opportunity = Opportunity(
        owner_id=OWNER, identity_key="synthetic:preparation-recovery", status="active",
        semantic_summary="Il confronto scritto della nota resta da preparare.", initiative="prepare",
        why_it_matters="Rendere disponibile il confronto ancora utile.",
        evidence=[EvidenceRef(kind="memory", ref=MEMORY, summary="Nota riferita dalla persona.")],
    )
    await OpportunityRepository(db).save(opportunity)
    source_row = await db.opportunities.find_one({"owner_id": OWNER, "id": opportunity.id})
    goal.origin, goal.opportunity_id = "agent_initiated", opportunity.id
    goal.opportunity_revision = source_row["agent_review_revision"]
    goal.source_situation = source_context(source_row)
    # advance writes this continuation before entering _finish. Preserve it
    # across the failure instead of inventing a new retry loop or timer.
    goal.next_run_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    service = AgentService(db)
    await service.repo.save_goal(goal)
    read = ActionStep(step_type="inspect", capability_needed="information.read", input_refs=[MEMORY],
        intent="Leggere la nota attuale.")
    result = await StepExecutor(db).run(OWNER, goal, read, may_touch_the_world=False)
    assert result.status == "succeeded"
    read.status, read.note = "succeeded", result.observation[:200]
    source, = await EvidenceStore(db).for_goal(OWNER, goal.id)
    pending = ActionStep(ordinal=1, step_type="prepare", capability_needed="document.create",
        intent="Preparare il confronto dalla fonte già letta.", input_refs=[MEMORY])
    plan = ActionPlan(owner_id=OWNER, goal_id=goal.id, steps=[read, pending],
        plan_summary="Leggere la nota e preparare il confronto.")
    await service.repo.save_plan(plan)
    return db, goal, plan, source, text


@pytest.mark.asyncio
@pytest.mark.parametrize("failure,error,retryable", [
    ("generation_unavailable", "preparation_model_unavailable", True),
    ("generation_invalid_citation", "preparation_ungrounded", False),
    ("audit_rejected", "preparation_not_supported", True),
    ("audit_invalid_citation", "preparation_review_invalid", False),
])
async def test_finish_preserves_actual_failure_for_reconsider_and_resumes_from_current_read(
    monkeypatch, failure, error, retryable,
):
    db, goal, plan, source, text = await seed_recovery()
    original_due = goal.next_run_at
    original_read = deepcopy(plan.steps[0].model_dump())
    reconsidered, stages = [], []
    recovered = False

    async def reply(_system, encoded):
        payload = json.loads(encoded)
        if "what_happened" in payload:
            reconsidered.append(payload)
            return {
                "decision": "modify", "reasoning": "Correggere la preparazione senza rileggere la fonte corrente.",
                "replace_step_ids": [plan.steps[1].id],
                "revised_steps": [{"step_type": "prepare", "capability_needed": "document.create",
                    "input_refs": [MEMORY], "intent": "Preparare il confronto con le citazioni della lettura attuale."}],
            }
        stages.append("audit" if "draft" in payload else "generation")
        row, = payload["evidence"]
        assert row["id"] == source.id and row["claim"] == text
        if not recovered:
            if failure == "generation_unavailable":
                return None
            if failure == "generation_invalid_citation":
                return {"content": RESULT, "evidence_ids": ["evd_not_supplied"]}
            if "draft" in payload:
                if failure == "audit_rejected":
                    return {"verified": False, "content": "", "evidence_ids": [],
                            "reason": "Una conclusione materiale non è sostenuta dalle premesse."}
                return {"verified": True, "content": RESULT, "evidence_ids": ["evd_not_supplied"]}
        return {"verified": True, "content": RESULT, "evidence_ids": [source.id]}

    with gate.isolated_engine(db), patch.object(reasoning, "_ask_model", reply):
        service = AgentService(db)
        budget = AgentBudget(cognitive_calls=5)
        result = await service._finish(OWNER, goal, plan,
            AgentRun(owner_id=OWNER, goal_id=goal.id), budget, language="it")
        assert result["state"] == "in_progress"
        assert len(reconsidered) == 1
        failure_payload = reconsidered[0]["what_happened"]
        assert failure_payload["step"]["status"] == "failed"
        assert failure_payload["result"]["problem"] == error
        assert failure_payload["result"]["worth_retrying"] is retryable
        assert failure_payload["result"]["where_this_came_from"] == "internal_observation"
        assert failure_payload["result"]["capability"] == "document.create"
        assert budget.cognitive_calls <= budget.max_cognitive_calls
        assert not goal.prepared_text and goal.next_run_at == original_due
        failed = plan.steps[2]
        journal = await db.agent_journal.find_one({"owner_id": OWNER, "goal_id": goal.id,
                                                   "kind": "step_done", "detail.step_id": failed.id})
        assert journal["detail"]["error_type"] == error
        assert journal["detail"]["retryable"] is retryable
        assert failed.status == "failed" and failed.note

        # A fresh service sees only persisted state. The ordinary next pass
        # executes the revised preparation using the same current evidence.
        recovered = True
        service = AgentService(db)
        current = await service.repo.get_goal(OWNER, goal.id)
        current_plan = await service.repo.plan_for(OWNER, goal.id)
        failed_history = deepcopy(current_plan.steps[2].model_dump())
        target = current_plan.steps[-1]

        async def choose(*args, **kwargs):
            latest = await service.repo.get_goal(OWNER, goal.id)
            return {"decision": "verify"} if latest.prepared_text else {"decision": "execute", "step_id": target.id}

        with patch.object(reasoning, "choose_next_action", choose), patch.object(reasoning, "verify_goal", AsyncMock(
            return_value={"outcome": "uncertain", "what_is_missing": "Giudizio controllato: nessuna qualità live attestata."},
        )):
            await service.advance(OWNER, goal.id)
        current = await service.repo.get_goal(OWNER, goal.id)
        current_plan = await service.repo.plan_for(OWNER, goal.id)
        assert current.prepared_text == RESULT and current.prepared_sources == [source.id]
        assert current.is_open and not current.requires_user_input and not current.requires_user_authority
        assert current_plan.steps[0].model_dump() == original_read
        assert current_plan.steps[2].model_dump() == failed_history
        assert current_plan.steps[-1].status == "succeeded"
        assert await db.agent_evidence.count_documents({"owner_id": OWNER, "goal_id": goal.id,
                                                       "provenance.capability": "information.read"}) == 1
        assert await db.agent_action_attempts.count_documents({}) == 0
        assert stages[-2:] == ["generation", "audit"]


@pytest.mark.asyncio
@pytest.mark.parametrize("verified", [True, False, "true"])
async def test_claim_review_reaches_real_sdk_with_complete_sources_and_only_audited_content_is_saved(
    monkeypatch, verified,
):
    db, goal, plan, source, text = await seed_recovery()
    assert text == SOURCE
    goal.success_criteria = [
        "Confrontare i totali sul medesimo orizzonte e mostrare la differenza.",
        "Distinguere i vincoli riportati dalle condizioni non specificate.",
        "Attribuire i dati alla nota, conservando il limite della conferma esterna e ogni premessa necessaria.",
    ]
    plan.steps[1].expected_result = "Un confronto completo con differenza, condizioni e provenienza."
    await AgentService(db).repo.save_goal(goal)
    unsupported = RESULT + " B permette sempre di interrompere senza vincoli."
    corrected = RESULT + " La nota non specifica i vincoli di interruzione di B."
    captured_rows = []

    def reply(system, payload):
        row, = payload["evidence"]
        captured_rows.append(deepcopy(row))
        assert row["id"] == source.id and row["claim"] == SOURCE
        assert row["bears_on"] == source.supports
        assert "user_stated" in row["bears_on"]
        assert row["source_class"] == "internal_observation"
        assert row["source_refs"] == [MEMORY]
        assert row["limits"] == source.provenance.certainty_note[:180]
        assert row["memory_reads"] == source.provenance.for_ai()["memory_reads"]
        page, = row["memory_reads"]
        assert page["end"] == page["total"] == len(SOURCE) and page["next_offset"] is None
        assert payload["evidence_truncated"] is False
        if "draft" not in payload:
            return {"content": unsupported, "evidence_ids": [source.id]}
        assert payload["draft"] == unsupported
        assert captured_rows[0] == captured_rows[1]
        assert system.index('{"claim_review"') < system.index('"verified": true')
        # This controlled review proves the transport and persistence
        # contract. It does not assert that a live model finds this error.
        return {
            "claim_review": [
                {"claim": "Totali e differenza su quattro periodi.", "evidence_ids": [source.id],
                 "premises": "Applicazione dei prezzi annotati al medesimo periodo.",
                 "support": "derived", "correction": ""},
                {"claim": "Assenza di vincoli per B.", "evidence_ids": [],
                 "premises": "La nota non specifica condizioni di interruzione per B.",
                 "support": "unsupported", "correction": "Rimuovere il vantaggio e mantenere il limite."},
            ],
            "verified": verified,
            "content": "" if verified is False else corrected,
            "evidence_ids": [] if verified is False else [source.id],
            "reason": "Rimangono solo il confronto attribuito e i limiti sostenuti.",
        }

    transported = fake_gemini(monkeypatch, reply)
    with gate.isolated_engine(db, mode="live") as probe:
        budget = AgentBudget()
        result = await StepExecutor(db).run(
            OWNER, goal, plan.steps[1], may_touch_the_world=False, budget=budget,
        )
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 2
        assert budget.cognitive_calls == 2 and budget.capability_calls == 1
        assert not probe.network.blocked and not probe.blocked_effects
    request = transported[1]["payload"]["request"]
    assert request["objective"] == goal.objective
    assert request["desired_outcome"] == goal.desired_outcome
    assert request["success_criteria"] == goal.success_criteria
    assert request["step_intent"] == plan.steps[1].intent
    assert request["expected_result"] == plan.steps[1].expected_result
    assert request["goal_origin"] == goal.origin
    assert request["previous_interpretation_may_be_obsolete"] is False
    assert request["source_update_reason"] is None
    saved = await db.agent_goals.find_one({"owner_id": OWNER, "id": goal.id})
    evidence = await EvidenceStore(db).for_goal(OWNER, goal.id)
    generated = [item for item in evidence if item.provenance.provider == "generated_draft"]
    if verified is True:
        assert result.status == "succeeded"
        assert saved["prepared_text"] == goal.prepared_text == corrected
        assert saved["prepared_sources"] == [source.id]
        assert generated and all(item.provenance.source_refs == [source.id] for item in generated)
        assert all("non è una verifica indipendente" in item.provenance.certainty_note for item in generated)
        assert all("B permette sempre" not in item.claim for item in generated)
    else:
        # Descriptive checks/reason, plausible content and even the string
        # "true" cannot replace the operational boolean verdict.
        assert result.status == "unavailable" and result.error_type == "preparation_not_supported"
        assert not saved.get("prepared_text") and not saved.get("prepared_sources")
        assert not generated and not result.evidence_refs
    assert saved["status"] == "active"
    assert await db.agent_action_attempts.count_documents({}) == 0


@pytest.mark.asyncio
async def test_finish_propagates_reconsidered_wait_with_exact_failure_and_within_budget():
    db, goal, plan, source, text = await seed_recovery()
    model_calls = []

    async def reply(_system, encoded):
        payload = json.loads(encoded)
        model_calls.append(payload)
        if "what_happened" not in payload:
            assert payload["evidence"][0]["claim"] == text
            return None
        assert payload["what_happened"]["result"]["problem"] == "preparation_model_unavailable"
        return {"decision": "wait", "wait_minutes": 13,
                "reasoning": "La preparazione non è disponibile: riprovare più tardi."}

    with gate.isolated_engine(db), patch.object(reasoning, "_ask_model", reply):
        service, budget = AgentService(db), AgentBudget(cognitive_calls=5)
        result = await service._finish(OWNER, goal, plan,
            AgentRun(owner_id=OWNER, goal_id=goal.id), budget, language="it")
        assert result["state"] == "waiting"
        assert result["for_minutes"] == 13
        assert goal.status == "waiting" and goal.next_run_at
        assert len(model_calls) == 2  # Failed generation and existing reconsideration.
        assert budget.cognitive_calls <= budget.max_cognitive_calls
        assert not goal.prepared_text and not goal.requires_user_input and not goal.requires_user_authority
        persisted = await service.repo.get_goal(OWNER, goal.id)
        assert persisted.status == "waiting" and persisted.next_run_at == goal.next_run_at
        journal = await db.agent_journal.find_one({"owner_id": OWNER, "goal_id": goal.id,
                                                   "kind": "replanned"})
        assert journal["detail"]["decision"] == "wait"
        assert journal["note"] == "La preparazione non è disponibile: riprovare più tardi."
        evidence, = await service.evidence.for_goal(OWNER, goal.id)
        assert evidence.id == source.id and evidence.claim == text


@pytest.mark.asyncio
async def test_audit_request_keeps_original_interpretation_qualified_after_current_memory_read(monkeypatch):
    from agent.source_refresh import refresh

    db, goal, plan, old_source, _ = await seed_recovery()
    goal.objective = "Confrontare le formule annotate e il precedente totale di 84 crediti."
    goal.desired_outcome = "Il confronto riferito a quattro periodi, prima stimato con differenza 16 crediti."
    goal.success_criteria = ["Mostrare i totali e la differenza precedente di 16 crediti.",
                             "Conservare i vincoli documentati e le condizioni ignote."]
    old_requirements = deepcopy((goal.objective, goal.desired_outcome, goal.success_criteria))
    service = AgentService(db)
    await service.repo.save_goal(goal)
    current_text = SOURCE.replace("84 crediti", "88 crediti")
    await db.memories.update_one({"id": MEMORY, "user_id": OWNER},
                                {"$set": {"statement": current_text, "revision": 2}})
    assert await refresh(service, goal)
    reason = goal.source_situation["memory_refresh_reason"]
    assert reason and (goal.objective, goal.desired_outcome, goal.success_criteria) == old_requirements
    # A later process reads the corrected source; the old derived target is
    # retained as historical interpretation, never rewritten by this test.
    goal = await AgentService(db).repo.get_goal(OWNER, goal.id)
    result = await StepExecutor(db).run(OWNER, goal, ActionStep(
        step_type="inspect", capability_needed="information.read", input_refs=[MEMORY],
        intent="Rileggere la fonte corretta.",
    ), may_touch_the_world=False)
    assert result.status == "succeeded"
    source, = await EvidenceStore(db).for_goal(OWNER, goal.id)
    assert source.id != old_source.id and source.claim == current_text
    corrected = RESULT.replace("84 crediti", "88 crediti").replace("16 crediti", "12 crediti")
    audited = []

    def reply(_system, payload):
        row, = payload["evidence"]
        assert row["id"] == source.id and row["claim"] == current_text
        assert row["memory_reads"] == source.provenance.for_ai()["memory_reads"]
        if "draft" in payload:
            audited.append(payload)
            assert "88 crediti" in row["claim"] and "84 crediti" not in row["claim"]
        return {"verified": True, "content": corrected, "evidence_ids": [source.id]}

    transported = fake_gemini(monkeypatch, reply)
    with gate.isolated_engine(db, mode="live") as probe:
        result = await StepExecutor(db).run(OWNER, goal, ActionStep(
            step_type="prepare", capability_needed="document.create",
            intent="Preparare il confronto sulle condizioni correnti.",
            expected_result="Un risultato con premesse e limiti attuali.",
        ), may_touch_the_world=False)
        assert result.status == "succeeded"
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 2
        assert not probe.network.blocked and not probe.blocked_effects
    assert len(audited) == 1 and goal.prepared_text == corrected
    request = audited[0]["request"]
    assert (request["objective"], request["desired_outcome"], request["success_criteria"]) == old_requirements
    assert request["source_update_reason"] == reason
    assert request["previous_interpretation_may_be_obsolete"] is True
    assert request["goal_origin"] == "agent_initiated"
    assert goal.prepared_sources == [source.id]
    assert (goal.objective, goal.desired_outcome, goal.success_criteria) == old_requirements


@pytest.mark.asyncio
async def test_request_and_cited_source_overflow_stops_before_audit_without_truncation(monkeypatch):
    db, goal, plan, source, _ = await seed_recovery()
    # The generation request fits, while the complete returned draft plus
    # these material criteria and its sole cited source exceed the audit cap.
    goal.success_criteria = [
        ("Condizione materiale da conservare. " * 25) + f"FINE_CRITERIO_{i}"
        for i in range(6)
    ]
    await AgentService(db).repo.save_goal(goal)
    draft = ("Confronto sintetico attribuito, con condizioni e limiti espliciti. " * 70)[:3900]
    seen = []

    def reply(_system, payload):
        seen.append(payload)
        row, = payload["evidence"]
        assert row["id"] == source.id and row["claim"] == SOURCE
        if "draft" in payload:
            return {"verified": True, "content": draft, "evidence_ids": [source.id]}
        assert payload["goal"]["success_criteria"] == goal.success_criteria
        request = {"objective": goal.objective, "desired_outcome": goal.desired_outcome,
                   "success_criteria": goal.success_criteria, "step_intent": plan.steps[1].intent,
                   "expected_result": plan.steps[1].expected_result}
        assert len(json.dumps({"request": request, "draft": draft, "evidence": [row]},
                              ensure_ascii=False)) > 9000
        return {"content": draft, "evidence_ids": [source.id]}

    transported = fake_gemini(monkeypatch, reply)
    with gate.isolated_engine(db, mode="live") as probe:
        result = await StepExecutor(db).run(
            OWNER, goal, plan.steps[1], may_touch_the_world=False, budget=AgentBudget(),
        )
        assert result.status == "unavailable" and result.error_type == "preparation_context_too_large"
        assert result.retryable is False
        assert len(seen) == len(transported) == probe.model_attempts == probe.model_http_requests == 1
        assert not probe.network.blocked and not probe.blocked_effects
    assert not goal.prepared_text and not result.evidence_refs
    persisted = await AgentService(db).repo.get_goal(OWNER, goal.id)
    assert not persisted.prepared_text and not persisted.prepared_sources
    assert persisted.success_criteria == goal.success_criteria
    evidence, = await EvidenceStore(db).for_goal(OWNER, goal.id)
    assert evidence.id == source.id and evidence.claim == SOURCE
