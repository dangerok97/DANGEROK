"""Rejected review feedback survives the real executor and a persisted retry.

Only owned synthetic records and the real SDK over fake HTTP are used. These
replies prove transport and persistence, not the quality of a live review.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest

from agent import preparation, reasoning
from agent.evidence import EvidenceStore
from agent.execution import StepExecutor
from agent.models import ActionStep, AgentBudget, AgentRun
from agent.service import AgentService
from scripts import autonomy_completion_eval_v162 as gate
from test_agent_preparation_dependency_v162 import OWNER, MEMORY, RESULT, comparison_claim_review, fake_gemini
from test_pending_outcome_contract_v162 import synthetic_transport_only  # noqa: F401
from test_preparation_recovery_v162 import seed_recovery


REASON = "La libertà di interrompere B non è documentata nella nota."
CORRECTION = "Rimuovere il vantaggio non dimostrato e conservare il confronto dei costi."
UNSUPPORTED = RESULT + " B permette di interrompere senza vincoli."
CORRECTED = RESULT + " La nota non specifica i vincoli di interruzione di B."
FEEDBACK = "preparation_feedback_non_authoritative"


def rejected_review(source):
    return {
        "verified": False, "content": UNSUPPORTED, "evidence_ids": [source.id],
        "reason": REASON,
        "claim_review": [{
            "claim": "B permette di interrompere senza vincoli.",
            "premises": "La nota riporta il prezzo di B, non le condizioni di interruzione.",
            "support": "unsupported", "correction": CORRECTION,
            "evidence_ids": [source.id], "source_quotes": [],
        }],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("fallback", [False, True], ids=["ordinary_step", "finish_fallback"])
async def test_rejected_audit_reaches_reconsider_and_next_preparation_after_reload(monkeypatch, fallback):
    db, goal, plan, source, text = await seed_recovery()
    original_due = goal.next_run_at
    original_read = deepcopy(plan.steps[0].model_dump())
    resumed = False

    def reply(_system, payload):
        if "what_happened" in payload:
            return {
                "decision": "modify", "reasoning": "Correggere l'asserzione non sostenuta dalle fonti correnti.",
                "replace_step_ids": [plan.steps[1].id] if fallback else [],
                "revised_steps": [{"step_type": "prepare", "capability_needed": "document.create",
                    "input_refs": [MEMORY], "intent": "Preparare il confronto dalle prove correnti."}],
            }
        if "draft" in payload and not resumed:
            return rejected_review(source)
        answer = {"content": CORRECTED if resumed else UNSUPPORTED, "evidence_ids": [source.id]}
        if "draft" in payload:
            answer.update(verified=True, claim_review=comparison_claim_review(source.id))
        return answer

    transported = fake_gemini(monkeypatch, reply)
    with gate.isolated_engine(db, mode="live") as probe:
        service = AgentService(db)
        budget = AgentBudget()
        run = AgentRun(owner_id=OWNER, goal_id=goal.id)
        if fallback:
            await service._finish(OWNER, goal, plan, run, budget, language="it")
        else:
            await service._do_step(OWNER, goal, plan, plan.steps[1], run, budget, language="it")
        assert len(transported) == 3
        reconsidered = transported[2]["payload"]
        assert reconsidered["what_happened"]["result"]["problem"] == "preparation_not_supported"
        immediate = reconsidered.get(FEEDBACK)
        assert immediate and REASON in json.dumps(immediate, ensure_ascii=False)
        assert CORRECTION in json.dumps(immediate, ensure_ascii=False)
        assert "not source evidence" in transported[2]["system"]
        assert not goal.prepared_text and not goal.prepared_sources
        assert goal.next_run_at == original_due
        assert not [row for row in await EvidenceStore(db).for_goal(OWNER, goal.id)
                    if row.provenance.provider == "generated_draft"]

        # Reload everything that can affect the new preparation. No closure
        # carries review state into production; only the controlled reply changes.
        resumed = True
        service = AgentService(db)
        current = await service.repo.get_goal(OWNER, goal.id)
        current_plan = await service.repo.plan_for(OWNER, goal.id)
        target = current_plan.steps[-1]
        await service._do_step(OWNER, current, current_plan, target,
            AgentRun(owner_id=OWNER, goal_id=goal.id), AgentBudget(), language="it")
        resumed_payload = transported[3]["payload"]
        feedback = resumed_payload.get(FEEDBACK)
        assert feedback["reason"] == REASON
        assert feedback["claim_review"][0]["correction"] == CORRECTION
        assert feedback["claim_review"][0]["evidence_ids"] == [source.id]
        assert resumed_payload["evidence"][0]["claim"] == text
        saved = await service.repo.get_goal(OWNER, goal.id)
        assert saved.prepared_text == CORRECTED and saved.prepared_sources == [source.id]
        assert target.status == "succeeded"
        assert current_plan.steps[0].model_dump() == original_read
        assert not saved.requires_user_input and not saved.requires_user_authority
        assert await db.agent_evidence.count_documents({"owner_id": OWNER, "goal_id": goal.id,
            "provenance.capability": "information.read"}) == 1
        assert await db.agent_action_attempts.count_documents({}) == 0
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 5
        assert not probe.blocked_effects and not probe.network.blocked
        records = await db.agent_journal.find({"owner_id": OWNER, "goal_id": goal.id,
            "kind": preparation._FEEDBACK_KIND}).sort("at", 1).to_list(3)
        assert records[-1]["detail"]["feedback"] is None, "A successful correction retires the old diagnosis."
        recorded = json.dumps(records[0]["detail"], ensure_ascii=False)
        assert text not in recorded and UNSUPPORTED not in recorded
        assert len(records[0]["detail"]["context_scope"]) == 64


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["owner", "goal", "expired", "requirements", "source_version"])
async def test_persisted_feedback_is_not_reused_outside_its_current_owned_context(monkeypatch, change):
    db, goal, plan, source, text = await seed_recovery()
    observation = await preparation.remember_preparation_feedback(db, OWNER, goal,
        reason=REASON, claim_review=rejected_review(source)["claim_review"], origin="goal_verification")
    assert observation and len(observation) <= 600
    service = AgentService(db)
    if change in ("owner", "goal", "expired"):
        changes = {"owner": {"owner_id": "other-synthetic-owner"},
                   "goal": {"goal_id": "other-synthetic-goal"},
                   "expired": {"expires_at": datetime(2000, 1, 1, tzinfo=timezone.utc)}}
        await db.agent_journal.update_one({"kind": preparation._FEEDBACK_KIND}, {"$set": changes[change]})
    elif change == "requirements":
        goal.success_criteria.append("Distinguere un requisito nuovo dalla vecchia interpretazione.")
        await service.repo.save_goal(goal)
    else:
        from agent.source_refresh import refresh
        await db.memories.update_one({"id": MEMORY, "user_id": OWNER}, {
            "$set": {"statement": text + " Le condizioni di interruzione restano da verificare."},
            "$inc": {"revision": 1},
        })
        assert await refresh(service, goal)
        read = ActionStep(step_type="inspect", capability_needed="information.read",
            intent="Leggere la nota corretta.", input_refs=[MEMORY])
        assert (await StepExecutor(db).run(OWNER, goal, read, may_touch_the_world=False)).status == "succeeded"
        source, = await EvidenceStore(db).for_goal(OWNER, goal.id)

    transported = fake_gemini(monkeypatch, lambda _system, payload: {
        "verified": True, "content": CORRECTED, "evidence_ids": [source.id],
        "claim_review": comparison_claim_review(source.id),
    })
    with gate.isolated_engine(db, mode="live") as probe:
        current = await AgentService(db).repo.get_goal(OWNER, goal.id)
        result = await StepExecutor(db).run(OWNER, current, plan.steps[1], may_touch_the_world=False)
        assert result.status == "succeeded"
        assert all(FEEDBACK not in request["payload"] for request in transported)
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 2
        assert not probe.blocked_effects and not probe.network.blocked


@pytest.mark.asyncio
async def test_feedback_wrapper_rejects_foreign_goal_and_revoked_memory_without_persisting():
    db, goal, _, _, _ = await seed_recovery()
    assert await preparation.remember_preparation_feedback(db, "other-synthetic-owner", goal,
        reason=REASON, origin="goal_verification") is None
    await db.memories.update_one({"id": MEMORY, "user_id": OWNER}, {"$set": {"status": "forgotten"}})
    assert await preparation.remember_preparation_feedback(db, OWNER, goal,
        reason=REASON, origin="goal_verification") is None
    assert await db.agent_journal.count_documents({"kind": preparation._FEEDBACK_KIND}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", ["string_verdict", "malformed_fields", "no_object"])
async def test_diagnostic_fields_never_coerce_the_verdict_or_save_a_rejected_draft(monkeypatch, shape):
    db, goal, plan, source, _ = await seed_recovery()
    checked = rejected_review(source)
    if shape == "string_verdict":
        checked["verified"] = "true"
    elif shape == "malformed_fields":
        checked.update(reason={"private": "must not be stringified"}, claim_review=[
            False, {"claim": {"private": "not a sentence"}, "premises": 17,
                    "correction": ["not a sentence"], "support": ["unsupported"], "evidence_ids": True},
        ])
    else:
        checked = None
    original = deepcopy(checked)
    transported = fake_gemini(monkeypatch, lambda _system, payload: checked if "draft" in payload else {
        "content": UNSUPPORTED, "evidence_ids": [source.id],
    })
    with gate.isolated_engine(db, mode="live") as probe:
        result = await StepExecutor(db).run(OWNER, goal, plan.steps[1], may_touch_the_world=False)
        assert result.status == "unavailable" and result.error_type == "preparation_not_supported"
        assert not result.evidence_refs and not goal.prepared_text and not goal.prepared_sources
        assert await db.agent_evidence.count_documents({}) == 1
        assert checked == original
        assert "private" not in result.observation and "not a sentence" not in result.observation
        if shape != "string_verdict":
            assert await db.agent_journal.count_documents({"kind": preparation._FEEDBACK_KIND}) == 0
        # A JSON null already uses the research parser's existing second
        # transport attempt; diagnostic collection adds no attempt of its own.
        expected_calls = 3 if shape == "no_object" else 2
        assert len(transported) == probe.model_attempts == probe.model_http_requests == expected_calls
        assert not probe.network.blocked and not probe.blocked_effects


@pytest.mark.asyncio
async def test_feedback_is_bounded_prioritizes_the_actual_critique_and_never_copies_the_draft(monkeypatch):
    db, goal, plan, source, text = await seed_recovery()
    checked = rejected_review(source)
    checked.update(content="REJECTED_DRAFT_NEVER_PERSISTED" * 100,
                   raw_prompt="PRIVATE_PROMPT_NEVER_PERSISTED", source_context=text,
                   reason='Motivo "con virgolette". ' * 100)
    checked["claim_review"] = [{"claim": "Un totale sostenuto.", "support": "derived", "correction": ""}] * 8 + [
        {"claim": "Un vantaggio senza premesse.", "premises": "La premessa non compare. " * 100,
         "support": "unsupported", "correction": "Eliminare la conclusione non sostenuta. " * 100,
         "evidence_ids": [source.id, "foreign-evidence", {"private": "invalid-ref"}]},
    ]
    original = deepcopy(checked)
    transported = fake_gemini(monkeypatch, lambda _system, payload: checked if "draft" in payload else {
        "content": UNSUPPORTED, "evidence_ids": [source.id],
    })
    with gate.isolated_engine(db, mode="live"):
        result = await StepExecutor(db).run(OWNER, goal, plan.steps[1], may_touch_the_world=False)
    assert result.status == "unavailable" and checked == original
    assert result.observation.startswith(preparation._FEEDBACK_PREFIX) and len(result.observation) <= 600
    immediate = json.loads(result.observation[len(preparation._FEEDBACK_PREFIX):])
    assert immediate["truncated"] is True
    record = await db.agent_journal.find_one({"kind": preparation._FEEDBACK_KIND})
    feedback = record["detail"]["feedback"]
    assert len(preparation._json(feedback)) <= 1400 and feedback["truncated"] is True
    assert feedback["claim_review"][0]["support"] == "unsupported"
    assert "Eliminare la conclusione" in feedback["claim_review"][0]["correction"]
    assert all(ref == source.id for row in feedback["claim_review"] for ref in row.get("evidence_ids", []))
    encoded = json.dumps(record["detail"], ensure_ascii=False)
    assert "REJECTED_DRAFT_NEVER_PERSISTED" not in encoded and "PRIVATE_PROMPT_NEVER_PERSISTED" not in encoded
    assert text not in encoded and not result.evidence_refs
    assert len(transported) == 2 and await db.agent_action_attempts.count_documents({}) == 0


@pytest.mark.asyncio
async def test_optional_journal_failure_does_not_erase_the_immediate_criticism(monkeypatch):
    db, goal, plan, source, _ = await seed_recovery()
    collection_type = type(db.agent_journal)
    original_read, original_write = collection_type.find_one, collection_type.insert_one

    async def find_one(collection, *args, **kwargs):
        if collection.name == "agent_journal":
            raise TimeoutError("synthetic optional journal unavailable")
        return await original_read(collection, *args, **kwargs)

    async def insert_one(collection, *args, **kwargs):
        if collection.name == "agent_journal":
            raise TimeoutError("synthetic optional journal unavailable")
        return await original_write(collection, *args, **kwargs)

    monkeypatch.setattr(collection_type, "find_one", find_one)
    monkeypatch.setattr(collection_type, "insert_one", insert_one)
    transported = fake_gemini(monkeypatch, lambda _system, payload: rejected_review(source) if "draft" in payload else {
        "content": UNSUPPORTED, "evidence_ids": [source.id],
    })
    with gate.isolated_engine(db, mode="live"):
        result = await StepExecutor(db).run(OWNER, goal, plan.steps[1], may_touch_the_world=False)
    assert result.error_type == "preparation_not_supported" and REASON in result.observation
    assert CORRECTION in result.observation and not result.evidence_refs
    assert not goal.prepared_text and len(transported) == 2


@pytest.mark.asyncio
async def test_full_preparation_context_omits_optional_feedback_before_any_source(monkeypatch):
    db, goal, plan, source, text = await seed_recovery()
    # Fill an actual generation payload close to the existing bound. The
    # source and requirements fit whole; adding history must not evict them.
    goal.source_situation["synthetic_context"] = ""
    base = {"goal": goal.for_ai(), "step": plan.steps[1].for_ai(),
            "evidence": preparation._source_rows([source]), "evidence_truncated": False}
    goal.source_situation["synthetic_context"] = "x" * (8850 - len(json.dumps(base, ensure_ascii=False, default=str)))
    await AgentService(db).repo.save_goal(goal)
    assert await preparation.remember_preparation_feedback(db, OWNER, goal,
        reason=REASON * 4, claim_review=rejected_review(source)["claim_review"], origin="goal_verification")
    transported = fake_gemini(monkeypatch, lambda _system, payload: {
        "verified": True, "content": CORRECTED, "evidence_ids": [source.id],
        "claim_review": comparison_claim_review(source.id),
    })
    with gate.isolated_engine(db, mode="live"):
        result = await StepExecutor(db).run(OWNER, goal, plan.steps[1], may_touch_the_world=False)
    assert result.status == "succeeded" and len(transported) == 2
    generation = transported[0]["payload"]
    assert FEEDBACK not in generation and generation["preparation_feedback_truncated"] is True
    assert generation["goal"] == {
        **goal.for_ai(), "goal_origin": goal.origin,
        "previous_interpretation_may_be_obsolete": False,
    }
    assert generation["evidence"][0]["claim"] == text and generation["evidence_truncated"] is False
    assert transported[1]["payload"][FEEDBACK]["origin"] == "goal_verification"


@pytest.mark.asyncio
@pytest.mark.parametrize("protected_overflow", [False, True])
async def test_reconsider_declares_omitted_feedback_and_preserves_the_model_decision(monkeypatch, protected_overflow):
    diagnosis = preparation._FEEDBACK_PREFIX + json.dumps({"reason": REASON * 6})
    diagnosis = diagnosis[:600]
    current = {"ref": MEMORY, "statement": "Current material " * 480}
    if protected_overflow:
        current = {"ref": "source:" + "x" * 12000, "statement": "The handle must not be silently cut."}
    goal = {"desired_outcome": "A useful comparison", "current_source_context": {"sources": [current]}}
    happened = {"result": {"status": "unavailable", "problem": "preparation_not_supported",
                           "what_happened": diagnosis, "worth_retrying": True}}
    if not protected_overflow:
        plain = {"goal": goal, "plan": {}, "what_happened": {"result": {**happened["result"],
            "what_happened": "La diagnosi del controllo è riportata separatamente come contesto non autorevole."}},
            "local_clock": {}, "what_ora_can_do": []}
        current["statement"] += "x" * (8850 - len(preparation._json(plain)))
    before = deepcopy((goal, happened))
    response = {"decision": "wait", "wait_minutes": 13, "reasoning": "Controlled decision, not a live verdict."}
    transported = fake_gemini(monkeypatch, lambda _system, payload: response)
    from mongomock_motor import AsyncMongoMockClient
    with gate.isolated_engine(AsyncMongoMockClient().feedback_context_v162, mode="live"):
        actual = await reasoning.reconsider(goal, plan={}, what_happened=happened, capabilities=[])
    assert actual == response and (goal, happened) == before and len(transported) == 1
    payload = transported[0]["payload"]
    assert FEEDBACK not in payload and payload["preparation_feedback_truncated"] is True
    if protected_overflow:
        assert payload["source_context_unavailable"] is True
    else:
        assert payload["goal"] == goal
        assert payload["what_happened"]["result"]["problem"] == "preparation_not_supported"
