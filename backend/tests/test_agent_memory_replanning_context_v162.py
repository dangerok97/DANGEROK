"""Current Memory reaches replanning without rewriting the person's requirements."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent import reasoning
from agent.models import AutonomousGoal
from agent.service import AgentService
from scripts import autonomy_completion_eval_v162 as gate
from situations.models import SituationState
from situations.repository import SituationRepository


OWNER = gate.OWNER
HUMAN_CONSTRAINT = "Non cambiare contratto e non effettuare pagamenti."


def generic_plan(refs):
    """The scripted planner does not repair obsolete numbers in the contract."""
    return {
        "plan_summary": "Rileggere la nota e confrontare le condizioni correnti.",
        "expected_outcome": "Un confronto informativo con limiti espliciti.",
        "steps": [
            {"step_type": "inspect", "intent": "Leggere la nota corrente.",
             "capability_needed": "information.read", "input_refs": list(refs),
             "expected_result": "I dati attuali della nota con la loro provenienza."},
            {"step_type": "prepare", "intent": "Preparare il confronto delle condizioni lette.",
             "capability_needed": "document.create", "input_refs": list(refs),
             "expected_result": "Il confronto dei costi e dei limiti sostenuto dalle fonti."},
        ],
    }


@pytest.mark.asyncio
async def test_worker_correction_gives_planner_and_verifier_current_facts_and_preserves_requirements():
    db = AsyncMongoMockClient().memory_replanning_worker
    plans, verifications = [], []

    async def plan(goal, **kwargs):
        plans.append(deepcopy({"goal": goal, "context": kwargs["context"]}))
        return generic_plan(goal["source_refs"])

    async def verify(goal, **kwargs):
        verifications.append(deepcopy({"goal": goal, "evidence": kwargs["evidence"]}))
        return {"outcome": "uncertain", "reasoning": "Osservazione sintetica del contesto corrente.",
                "what_is_missing": "La prova osserva il passaggio dei dati, non approva il confronto."}

    with gate.isolated_engine(db, scenario="memory_corrected") as probe:
        await gate.seed_case(db, "memory_corrected")
        goal_id = await gate.admit(db, "memory_corrected")
        service = AgentService(db)
        goal = await service.repo.get_goal(OWNER, goal_id)
        # The runtime must not silently rewrite either a prior interpretation
        # or an explicit human requirement. The model receives both, separately.
        goal.desired_outcome = "Verificare se la differenza riferita di 60 euro resta valida."
        goal.success_criteria = ["Confrontare dodici mesi e indicare i limiti.", HUMAN_CONSTRAINT]
        goal.clarifications = [{"question": "Quali limiti devo rispettare?", "answer": HUMAN_CONSTRAINT}]
        await service.repo.save_goal(goal)
        original_contract = goal.for_ai()

        with patch.object(reasoning, "make_plan", plan), patch.object(reasoning, "verify_goal", verify):
            await gate.first_read(db, goal_id, probe)
            old_plan = await service.repo.plan_for(OWNER, goal_id)
            old_read = old_plan.steps[0].model_dump()
            changed = await gate.change_memory(db, goal_id, correction=True)
            for _ in range(3):
                await gate.fire_due(db, goal_id, probe)
                if verifications:
                    break

        assert len(plans) == 2 and len(verifications) == 1
        first_context = plans[0]["context"]["current_source_context"]
        current_context = plans[1]["context"]["current_source_context"]
        assert "120 euro" in first_context["sources"][0]["statement"]
        assert first_context["previous_interpretation_may_be_obsolete"] is False
        assert first_context["source_update_reason"] is None
        assert current_context["unavailable"] is False
        assert current_context["goal_origin"] == "agent_initiated"
        assert current_context["previous_interpretation_may_be_obsolete"] is True
        assert "nuova lettura" in current_context["source_update_reason"]
        note = current_context["sources"][0]
        assert note["ref"] == changed["current"]
        assert "150 euro" in note["statement"] and "120 euro" not in note["statement"]
        assert note["freshness"] == "unknown" and note["authority"] == "user_stated"
        assert note["excerpt_truncated"] is False
        assert "source_context" not in plans[1]["context"]
        assert verifications[0]["goal"]["current_source_context"] == current_context

        for payload in (plans[1]["goal"], verifications[0]["goal"]):
            assert payload["source_refs"] == [changed["current"]]
            for key in ("objective", "desired_outcome", "success_criteria", "stop_conditions",
                        "user_clarifications_not_authority"):
                assert payload[key] == original_contract[key]
        verified_facts = str(verifications[0]["evidence"]["what_was_found"])
        assert "150 euro" in verified_facts and "120 euro" not in verified_facts
        assert changed["old"] not in verified_facts
        retired = await db.agent_plans.find_one({"owner_id": OWNER, "id": old_plan.id})
        assert retired["status"] == "cancelled"
        assert retired["steps"][0] == old_read
        assert retired["steps"][1]["status"] == "skipped"
        current_plan = await service.repo.plan_for(OWNER, goal_id)
        assert current_plan.id != old_plan.id
        assert all(changed["old"] not in step.input_refs for step in current_plan.steps)
        records = await db.agent_evidence.find({"owner_id": OWNER, "goal_id": goal_id,
            "provenance.capability": "information.read"}).to_list(3)
        assert len(records) == 2  # Previews never create agent evidence.
        original = next(row for row in records if changed["old"] in row["provenance"]["source_refs"])
        current = next(row for row in records if changed["current"] in row["provenance"]["source_refs"])
        assert original["superseded"] is True and not current.get("superseded")
        assert (await service.repo.get_goal(OWNER, goal_id)).is_open
        assert probe.model_attempts == 0 and not probe.blocked_effects


@pytest.mark.asyncio
async def test_user_requested_goal_keeps_human_criteria_and_a_bounded_persisted_update_marker():
    db = AsyncMongoMockClient().memory_replanning_user
    ref = "mem_current"
    await db.memories.insert_one({"id": ref, "user_id": OWNER, "status": "active",
                                 "statement": "L'opzione corrente costa 150 euro.", "authority": "user_stated"})
    marker = "Fonte modificata: " + "x" * 400
    goal = AutonomousGoal(owner_id=OWNER, origin="user_requested", source_refs=[ref],
        objective="Controllare la mia ipotesi di risparmio.",
        desired_outcome="Verificare se il risparmio supera 60 euro.",
        success_criteria=["Confrontare dodici mesi.", HUMAN_CONSTRAINT],
        stop_conditions=["Fermati se ritiro la richiesta."],
        clarifications=[{"question": "Come procedere?", "answer": HUMAN_CONSTRAINT}],
        source_situation={"memory_refresh_reason": marker})
    original = goal.model_dump()

    payload = await AgentService(db)._reasoning_goal(OWNER, goal)

    assert payload["current_source_context"]["sources"][0]["statement"] == "L'opzione corrente costa 150 euro."
    assert payload["current_source_context"]["goal_origin"] == "user_requested"
    assert payload["current_source_context"]["source_update_reason"] == marker[:300]
    assert payload["current_source_context"]["previous_interpretation_may_be_obsolete"] is True
    assert payload["desired_outcome"] == original["desired_outcome"]
    assert payload["success_criteria"] == original["success_criteria"]
    assert payload["user_clarifications_not_authority"] == original["clarifications"]
    assert goal.model_dump() == original
    assert await db.agent_evidence.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["missing", "forgotten", "superseded", "foreign", "empty"])
async def test_unreadable_current_source_is_explicit_without_an_unrelated_fallback(condition):
    db = AsyncMongoMockClient().memory_replanning_unavailable
    ref = "mem_unreadable"
    if condition != "missing":
        await db.memories.insert_one({"id": ref,
            "user_id": "someone-else" if condition == "foreign" else OWNER,
            "status": condition if condition in ("forgotten", "superseded") else "active",
            "statement": "" if condition == "empty" else "UNREADABLE-PRIVATE"})
    await db.memories.insert_one({"id": "mem_uncited", "user_id": OWNER, "status": "active",
                                 "statement": "UNCITED-PRIVATE"})
    goal = AutonomousGoal(owner_id=OWNER, source_refs=[ref], objective="Rileggere la nota.",
                          desired_outcome="Un confronto sostenuto dalla nota citata.")

    payload = await AgentService(db)._reasoning_goal(OWNER, goal)

    assert payload["current_source_context"]["sources"] == []
    assert payload["current_source_context"]["unavailable"] is True
    assert "UNREADABLE-PRIVATE" not in str(payload) and "UNCITED-PRIVATE" not in str(payload)
    assert await db.agent_evidence.count_documents({}) == 0


@pytest.mark.asyncio
async def test_database_failure_is_explicit_unavailability_without_error_content():
    failure = Mock(side_effect=ConnectionError("PRIVATE-DATABASE-ERROR"))
    db = SimpleNamespace(memories=SimpleNamespace(find=failure))
    goal = AutonomousGoal(owner_id=OWNER, source_refs=["mem_current"], objective="Rileggere la nota.",
                          desired_outcome="Un confronto sostenuto dalla nota citata.")

    payload = await AgentService(db)._reasoning_goal(OWNER, goal)

    assert payload["current_source_context"]["sources"] == []
    assert payload["current_source_context"]["unavailable"] is True
    assert "PRIVATE-DATABASE-ERROR" not in str(payload)


@pytest.mark.asyncio
async def test_memory_and_situation_contexts_remain_distinct_without_duplicate_notes():
    db = AsyncMongoMockClient().memory_replanning_mixed
    await db.memories.insert_one({"id": "mem_current", "user_id": OWNER, "status": "active",
                                 "statement": "Nota corrente citata."})
    await SituationRepository(db).insert(SituationState(
        id="sit_current", user_id=OWNER, summary="La situazione attuale citata."))
    goal = AutonomousGoal(owner_id=OWNER, source_refs=["situation:sit_current", "mem_current"],
                          objective="Rileggere le fonti.", desired_outcome="Un risultato corrente.")

    payload = await AgentService(db)._reasoning_goal(OWNER, goal)

    assert len(payload["source_context"]) == 1
    assert payload["source_context"][0]["source"] == "situation"
    assert payload["source_context_unavailable"] is False
    assert len(payload["current_source_context"]["sources"]) == 1
    assert payload["current_source_context"]["sources"][0]["source"] == "memory"
    assert str(payload).count("Nota corrente citata.") == 1


@pytest.mark.asyncio
async def test_withdrawn_memory_stops_the_worker_before_replanning_or_preparing():
    db = AsyncMongoMockClient().memory_replanning_revoked
    with gate.isolated_engine(db, scenario="memory_revoked") as probe:
        await gate.seed_case(db, "memory_revoked")
        goal_id = await gate.admit(db, "memory_revoked")
        await gate.first_read(db, goal_id, probe)
        await gate.change_memory(db, goal_id)
        planner = AsyncMock(side_effect=AssertionError("A withdrawn source must stop before planning"))

        with patch.object(reasoning, "make_plan", planner):
            await gate.fire_due(db, goal_id, probe)

        goal = await AgentService(db).repo.get_goal(OWNER, goal_id)
        assert goal.status == "abandoned" and not goal.next_run_at
        assert not goal.prepared_text and not goal.prepared_sources
        assert [row["capability"] for row in probe.steps] == ["information.read"]
        planner.assert_not_awaited()
        assert probe.model_attempts == 0


@pytest.mark.asyncio
async def test_partial_legacy_goal_without_refs_keeps_its_original_reasoning_payload():
    payload = {"objective": "Proseguire il lavoro già avviato."}
    goal = SimpleNamespace(id="legacy_goal", owner_id=OWNER, for_ai=lambda: payload)
    service = AgentService(SimpleNamespace())
    context = AsyncMock(side_effect=AssertionError("A goal without source refs requires no source query"))
    with patch.object(service, "_planning_source_context", context):
        assert await service._reasoning_goal(OWNER, goal) is payload
    context.assert_not_awaited()
