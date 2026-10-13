"""A source preview must not be mistaken for a performed read in planning."""
import json

import pytest

from agent import reasoning


@pytest.mark.asyncio
async def test_planner_instruction_requires_owned_read_before_grounded_draft(monkeypatch):
    observed = {}

    async def model(system, user, **_kwargs):
        observed["system"] = system
        observed["payload"] = json.loads(user)
        return {
            "planning_outcome": "plan",
            "reasoning": "Read the referenced note first",
            "steps": [{"intent": "Read the owned note", "step_type": "inspect",
                       "capability_needed": "information.read"}],
        }

    monkeypatch.setattr(reasoning, "_ask_model", model)
    plan = await reasoning.make_plan(
        goal={"source_refs": ["mem_synthetic"], "desired_outcome": "A comparison"},
        capabilities=[{"name": "information.read"}, {"name": "document.create"}],
        context={"current_source_context": {"sources": [{"ref": "mem_synthetic"}]}},
    )
    assert plan["planning_outcome"] == "plan"
    prompt = observed["system"]
    assert "the plan must contain a separate inspect/read step" in prompt
    assert "a source_context preview, stored Memory reference" in prompt
    assert "Do not replace an available owned-source read with speculative web research" in prompt
    assert "never send a wrong-type effect_type" in prompt
    assert "real effect_type, target, external impact and authority requirements" in prompt
    assert observed["payload"]["goal"]["source_refs"] == ["mem_synthetic"]


from unittest.mock import AsyncMock

from mongomock_motor import AsyncMongoMockClient

from agent.models import ActionStep, AgentBudget, AgentRun, AutonomousGoal
from agent.service import AgentService, _source_read_prerequisite


SYNTHETIC_OWNER = "owned-source-prerequisite-v162"
SYNTHETIC_MEMORY = "mem_9a5f77a1b92c4e5581a4"


def _draft():
    return ActionStep(ordinal=0, step_type="prepare",
        capability_needed="document.create",
        intent="Preparare un confronto da una nota non ancora letta.")


def _available_read():
    return [{"capability": "information.read", "can_be_used_now": True}]


def test_preparations_from_governed_memory_require_real_read_without_fabricated_facts():
    goal = AutonomousGoal(owner_id=SYNTHETIC_OWNER,
        objective="Confrontare le opzioni", desired_outcome="Confronto scritto",
        source_refs=[SYNTHETIC_MEMORY, "unobserved:foreign-source"])
    draft = _draft()
    after = ActionStep(ordinal=1, step_type="verify", capability_needed="information.read",
        intent="Controllare la bozza dopo averla scritta.")
    steps, reason = _source_read_prerequisite(goal, [draft, after], [], _available_read())
    assert reason == "added_owned_memory_read"
    assert len(steps) == 3 and [s.ordinal for s in steps] == [0, 1, 2]
    first = steps[0]
    assert first.step_type == "inspect"
    assert first.capability_needed == "information.read"
    assert first.input_refs == [SYNTHETIC_MEMORY]
    assert first.external_effect is False
    assert steps[1] is draft and steps[2] is after
    assert not any(s.status == "succeeded" for s in steps)


def test_valid_source_read_is_never_duplicated_and_nonmemory_not_guessed():
    goal = AutonomousGoal(owner_id=SYNTHETIC_OWNER,
        source_refs=[SYNTHETIC_MEMORY], objective="Leggere e confrontare",
        desired_outcome="Confronto")
    read = ActionStep(ordinal=0, step_type="inspect",
        capability_needed="information.read", input_refs=[SYNTHETIC_MEMORY],
        intent="Leggere la nota autorizzata.")
    draft = _draft()
    draft.ordinal = 1
    steps, reason = _source_read_prerequisite(goal, [read, draft], [], _available_read())
    assert reason == "" and steps == [read, draft]
    another = goal.model_copy(update={"source_refs": ["calendar:unknown"]})
    steps, reason = _source_read_prerequisite(another, [draft], [], _available_read())
    assert reason == "source_read_required"
    assert steps == [draft]
    steps, reason = _source_read_prerequisite(goal, [draft], [], [])
    assert reason == "source_read_required" and steps == [draft]


@pytest.mark.asyncio
async def test_invalid_live_style_plan_becomes_owned_memory_read_before_document_create(monkeypatch):
    """The actual planner/persistence/read path fixes the ordering of a real-style invalid plan."""
    from agent.execution import StepExecutor
    from agent.evidence import EvidenceStore

    db = AsyncMongoMockClient().owned_source_read_prerequisite_v162
    goal = AutonomousGoal(owner_id=SYNTHETIC_OWNER, origin="agent_initiated",
        objective="Confrontare i costi", desired_outcome="Un confronto scritto fondato sulla nota",
        source_refs=[SYNTHETIC_MEMORY], status="active")
    await db.memories.insert_one({
        "id": SYNTHETIC_MEMORY, "user_id": SYNTHETIC_OWNER, "status": "active",
        "statement": "Fonte dichiarata dalla persona: mensile 15 euro, annuale 120 euro.",
        "authority": "user_stated", "epistemic_status": "confirmed",
    })
    service = AgentService(db)
    await service.repo.save_goal(goal)
    monkeypatch.setattr(service.capabilities, "available", AsyncMock(return_value=_available_read()))
    monkeypatch.setattr(service, "_planning_source_context", AsyncMock(return_value=([], False)))
    monkeypatch.setattr(service, "_planning_evidence_inventory", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_planning_fence", AsyncMock())
    planner = AsyncMock(return_value={
        "planning_outcome": "plan",
        "plan_summary": "Confrontare la nota",
        "steps": [
            {"step_type": "prepare", "capability_needed": "document.create",
             "intent": "Preparare il confronto dalla nota."},
            {"step_type": "verify", "capability_needed": "information.read",
             "intent": "Controllare il confronto già pronto."},
        ],
    })
    monkeypatch.setattr(reasoning, "make_plan", planner)
    plan = await service._build_plan(
        SYNTHETIC_OWNER, goal, AgentRun(owner_id=SYNTHETIC_OWNER, goal_id=goal.id),
        AgentBudget(), language="it",
    )
    assert plan is not None
    assert [s.step_type for s in plan.steps] == ["inspect", "prepare", "verify"]
    saved = await service.repo.plan_for(SYNTHETIC_OWNER, goal.id)
    assert saved.steps[0].input_refs == [SYNTHETIC_MEMORY]
    assert await EvidenceStore(db).for_goal(SYNTHETIC_OWNER, goal.id) == []
    result = await StepExecutor(db).run(
        SYNTHETIC_OWNER, goal, saved.steps[0], may_touch_the_world=False,
    )
    assert result.status == "succeeded"
    evidence = await EvidenceStore(db).for_goal(SYNTHETIC_OWNER, goal.id)
    assert len(evidence) == 1
    assert evidence[0].provenance.capability == "information.read"
    assert SYNTHETIC_MEMORY in evidence[0].provenance.source_refs
    assert not goal.prepared_text
    recorded = await db.agent_journal.find_one({
        "owner_id": SYNTHETIC_OWNER, "goal_id": goal.id,
        "kind": "planning_read_prerequisite_inserted",
    })
    assert recorded is not None
    assert recorded["detail"]["source_type"] == "governed_memory"


@pytest.mark.asyncio
async def test_nonmemory_plan_without_prior_read_is_rejected_without_persistence(monkeypatch):
    db = AsyncMongoMockClient().owned_nonmemory_prerequisite_v162
    goal = AutonomousGoal(owner_id=SYNTHETIC_OWNER, origin="agent_initiated",
        objective="Confrontare da una fonte esterna", desired_outcome="Confronto fondato",
        source_refs=["calendar:unknown"], status="active")
    service = AgentService(db)
    await service.repo.save_goal(goal)
    monkeypatch.setattr(service.capabilities, "available", AsyncMock(return_value=_available_read()))
    monkeypatch.setattr(service, "_planning_source_context", AsyncMock(return_value=([], False)))
    monkeypatch.setattr(service, "_planning_evidence_inventory", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_planning_fence", AsyncMock())
    planner = AsyncMock(return_value={
        "planning_outcome": "plan", "steps": [
            {"step_type": "prepare", "capability_needed": "document.create",
             "intent": "Senza fonte realizzata non creare documenti."},
        ],
    })
    monkeypatch.setattr(reasoning, "make_plan", planner)
    run = AgentRun(owner_id=SYNTHETIC_OWNER, goal_id=goal.id)
    result = await service._build_plan(
        SYNTHETIC_OWNER, goal, run, AgentBudget(), language="it",
    )
    assert result is None and run.stopped_because == "source_read_required"
    assert await service.repo.plan_for(SYNTHETIC_OWNER, goal.id) is None
    assert goal.planning_unavailable and goal.planning_attempts == 1
    journal = await db.agent_journal.find_one({
        "owner_id": SYNTHETIC_OWNER, "goal_id": goal.id,
        "kind": "planning_protocol_invalid",
    })
    assert journal["detail"]["validation_errors"][0] == {
        "index": 0, "field": "step_type", "issue": "source_read_required",
    }


def test_unrelated_real_evidence_is_not_a_memory_read():
    from agent.models import AgentEvidence, ResultProvenance

    goal = AutonomousGoal(owner_id=SYNTHETIC_OWNER, source_refs=[SYNTHETIC_MEMORY],
        objective="Confronto da nota", desired_outcome="Documento fondato")
    weather = AgentEvidence(owner_id=SYNTHETIC_OWNER, goal_id=goal.id,
        claim="La temperatura odierna è rilevata dal meteo.",
        provenance=ResultProvenance(source_class="internal_observation",
            capability="weather.read", source_refs=["weather:synthetic"]))
    assert weather.is_real
    steps, reason = _source_read_prerequisite(goal, [_draft()], [weather], _available_read())
    assert reason == "added_owned_memory_read"
    assert steps[0].capability_needed == "information.read"
    assert steps[0].input_refs == [SYNTHETIC_MEMORY]

    matching = AgentEvidence(owner_id=SYNTHETIC_OWNER, goal_id=goal.id,
        claim="La nota governata è stata letta nel contesto dell'obiettivo.",
        provenance=ResultProvenance(source_class="internal_observation",
            capability="information.read", source_refs=[SYNTHETIC_MEMORY]))
    only_draft = _draft()
    steps, reason = _source_read_prerequisite(goal, [only_draft], [weather, matching], _available_read())
    assert reason == "" and steps == [only_draft]


@pytest.mark.asyncio
async def test_unrelated_wait_plan_survives_evidence_store_outage(monkeypatch):
    """The added evidence query is restricted to document preparation."""
    db = AsyncMongoMockClient().unrelated_wait_plan_v162
    goal = AutonomousGoal(owner_id=SYNTHETIC_OWNER, status="active",
        objective="Aspettare il momento previsto",
        desired_outcome="Controllare quando una fonte tornerà disponibile",
        source_refs=["calendar:synthetic"])
    service = AgentService(db)
    await service.repo.save_goal(goal)
    monkeypatch.setattr(service.capabilities, "available", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_planning_source_context", AsyncMock(return_value=([], False)))
    monkeypatch.setattr(service, "_planning_fence", AsyncMock())
    service.evidence.for_goal = AsyncMock(side_effect=TimeoutError("synthetic store outage"))
    monkeypatch.setattr(reasoning, "make_plan", AsyncMock(return_value={
        "planning_outcome": "plan", "steps": [
            {"step_type": "wait", "intent": "Ricontrollare più tardi",
             "parameters": {"wait_minutes": 20}},
        ],
    }))
    plan = await service._build_plan(
        SYNTHETIC_OWNER, goal, AgentRun(owner_id=SYNTHETIC_OWNER, goal_id=goal.id),
        AgentBudget(), language="it",
    )
    assert plan is not None
    assert len(plan.steps) == 1 and plan.steps[0].step_type == "wait"
    assert not goal.planning_unavailable
    assert service.evidence.for_goal.await_count == 1  # Existing bounded inventory only.
