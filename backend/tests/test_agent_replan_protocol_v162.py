"""Plan declarations survive the exact display aliases ORA supplies to a model.

These are complete synthetic inputs, not reconstructed full historical LLM
responses. The 3b7 report exposed type/step_type; for_ai itself demonstrates
the other aliases. A display projection is partial: only supplied values may
be recovered, never omitted authority, questions or execution parameters.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from mongomock_motor import AsyncMongoMockClient
import pytest

from agent import reasoning
from agent.models import ActionPlan, ActionStep, AgentBudget, AgentRun, AutonomousGoal
from agent.service import AgentService, MAX_PLAN_STEPS
from scripts import autonomy_completion_eval_v162 as gate
from test_agent_preparation_dependency_v162 import fake_gemini
from test_pending_outcome_contract_v162 import synthetic_transport_only  # noqa: F401


OWNER = gate.OWNER
DECLARATION_FIELDS = (
    "intent", "step_type", "capability_needed", "input_refs", "expected_result",
    "external_effect", "effect_type", "effect_target", "reaches_somebody_else", "reversibility",
)


def supplied_step(kind):
    common = dict(intent="Passo sintetico con limiti espliciti", expected_result="Un riscontro qualificato",
                  status="succeeded", note="Questa è storia, non il risultato del passo nuovo.")
    if kind in ("memory", "document"):
        prefix = "memory" if kind == "memory" else "document"
        return ActionStep(**common, step_type="inspect",
            capability_needed="information.read" if kind == "memory" else "document.read",
            input_refs=["mem_synthetic" if kind == "memory" else "document:synthetic"],
            parameters={prefix + "_offset": 600, prefix + "_version": "synthetic-source-version"})
    if kind in ("calendar", "local_calendar"):
        return ActionStep(**common, step_type="execute",
            capability_needed="calendar.write" if kind == "calendar" else "calendar.local.write",
            input_refs=["calendar:synthetic-owned-target"], external_effect=True,
            effect_type="modify", effect_target="calendar:synthetic-owned-target",
            parameters={"title": "Impegno sintetico", "start_datetime": "2026-10-16T12:00:00+02:00",
                        "end_datetime": "2026-10-16T12:30:00+02:00", "timezone": "Europe/Rome",
                        "expected_revision": "synthetic-current-revision"})
    if kind == "contacts":
        return ActionStep(**common, step_type="inspect", capability_needed="contacts.read",
                          parameters={"who": "Persona sintetica già indicata"})
    if kind == "route":
        return ActionStep(**common, step_type="inspect", capability_needed="route.read",
                          input_refs=["place:synthetic"], parameters={"travel_mode": "walk"})
    return ActionStep(**common, step_type="wait", parameters={
        "wait_until": "2026-10-16T12:17:00+02:00", "wait_minutes": 17, "wait_hours": 1,
    })


@pytest.mark.parametrize("kind", ["memory", "document", "calendar", "local_calendar", "contacts", "route", "wait"])
def test_display_aliases_preserve_every_supplied_declaration_value(kind):
    source = supplied_step(kind)
    raw = source.for_ai()
    original = deepcopy(raw)
    parsed = AgentService._read_step(raw, 8)
    assert parsed is not None
    assert {key: getattr(parsed, key) for key in DECLARATION_FIELDS} == {
        key: getattr(source, key) for key in DECLARATION_FIELDS}
    # Each parameter in these fixtures is actually emitted by for_ai.
    assert json.dumps(parsed.parameters, sort_keys=True) == json.dumps(source.parameters, sort_keys=True)
    assert parsed.id != source.id and parsed.ordinal == 8 and parsed.status == "pending"
    assert not parsed.note and not parsed.authority_requirement and not parsed.actual_result_ref
    assert raw == original


@pytest.mark.parametrize("difference", ["step_type", "effect_type", "parameters", "cursor", "flag_type", "unknown_type", "parameter_shape"])
def test_ambiguous_or_unsupported_step_forms_are_rejected(difference):
    raw = {"intent": "Dichiarazione sintetica", "step_type": "inspect",
           "capability_needed": "information.read", "external_effect": False}
    if difference == "step_type":
        raw["type"] = "prepare"
    elif difference == "effect_type":
        raw.update(effect_type="modify", what_kind_of_change="create")
    elif difference == "parameters":
        raw.update(parameters={"flag": False}, execution_parameters={"flag": 0})
    elif difference == "cursor":
        raw.update(parameters={"memory_offset": 0}, memory_offset=False)
    elif difference == "flag_type":
        raw["external_effect"] = 0
    elif difference == "unknown_type":
        raw["step_type"] = "UNSUPPORTED_PRIVATE_VALUE"
    else:
        raw["parameters"] = ["PRIVATE_PARAMETER_VALUE"]
    original = deepcopy(raw)
    assert AgentService._read_step(raw, 0) is None
    assert raw == original


def test_matching_alias_objects_ignore_key_order_but_keep_value_types():
    raw = {"intent": "Dichiarazione sintetica", "step_type": "inspect", "type": "inspect",
           "parameters": {"flag": False, "offset": 0},
           "execution_parameters": {"offset": 0, "flag": False}}
    parsed = AgentService._read_step(raw, 0)
    assert parsed and parsed.parameters == {"flag": False, "offset": 0}
    assert type(parsed.parameters["flag"]) is bool and type(parsed.parameters["offset"]) is int


@pytest.mark.parametrize("kind", ["question", "hidden_write_parameters", "undeclared_effect"])
def test_partial_display_never_reconstructs_questions_parameters_or_effects(kind):
    if kind == "question":
        raw = ActionStep(intent="Serve una scelta personale", step_type="ask_user",
                         asks="Quale opzione vuoi?", ask_kind="knowledge").for_ai()
        assert "asks" not in raw and "ask_kind" not in raw
    elif kind == "hidden_write_parameters":
        raw = ActionStep(intent="Effetto sintetico", step_type="execute", capability_needed="unexposed.write",
                         external_effect=True, effect_type="modify", effect_target="synthetic-target",
                         parameters={"target": "VALUE_NOT_EXPOSED_BY_FOR_AI"}).for_ai()
        assert "VALUE_NOT_EXPOSED_BY_FOR_AI" not in json.dumps(raw)
    else:
        raw = {"intent": "Effetto sintetico", "type": "execute", "parameters": {}}
    original = deepcopy(raw)
    assert AgentService._read_step(raw, 0) is None
    assert raw == original


async def setup(monkeypatch, *, at_capacity=False):
    db = AsyncMongoMockClient().synthetic_replan_protocol
    service = AgentService(db)
    goal = AutonomousGoal(owner_id=OWNER, objective="Rivedere il risultato sintetico",
        desired_outcome="Un risultato utile e qualificato", status="active", background_runs=1,
        next_run_at=(datetime.now(timezone.utc) + timedelta(hours=2)).isoformat())
    await service.repo.save_goal(goal)
    done = ActionStep(intent="Lettura già eseguita", step_type="inspect", status="succeeded",
                      note="La fonte dichiarava soltanto i termini presenti.")
    failed = ActionStep(intent="Preparazione rifiutata", step_type="prepare", status="failed",
                        attempts=1, note="Il testo non era nel formato richiesto.")
    pending = ActionStep(intent="Percorso ancora aperto", step_type="verify")
    steps = [done, failed, pending]
    if at_capacity:
        steps.extend(ActionStep(intent=f"Storia sintetica {index}", step_type="inspect", status="skipped")
                     for index in range(MAX_PLAN_STEPS - len(steps) - 1))
    plan = ActionPlan(owner_id=OWNER, goal_id=goal.id, status="active", steps=steps)
    await service.repo.save_plan(plan)
    assessment = AsyncMock(return_value=False)
    monkeypatch.setattr(service, "_record_situation_outcome", assessment)
    monkeypatch.setattr(service.capabilities, "available", AsyncMock(return_value=[]))
    return SimpleNamespace(db=db, service=service, goal=goal, plan=plan, pending=pending,
                           assessment=assessment, budget=AgentBudget(), run=AgentRun(owner_id=OWNER, goal_id=goal.id))


@pytest.mark.asyncio
async def test_actual_sdk_replan_persists_declared_alias_step_without_rewriting_history(monkeypatch):
    h = await setup(monkeypatch)
    declaration = supplied_step("memory").for_ai()
    answer = {"decision": "modify", "reasoning": "Riprendo solo il testo ancora necessario.",
              "revised_steps": [declaration], "replace_step_ids": [h.pending.id, h.plan.steps[0].id, "foreign-step"]}
    original = deepcopy(answer)
    transported = fake_gemini(monkeypatch, lambda _system, _payload: answer)
    with gate.isolated_engine(h.db, mode="live") as probe:
        result = await h.service._reconsider(OWNER, h.goal, h.plan, h.run, h.budget,
            what_happened={"problem": "synthetic_preparation_failure"}, language="it")
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 1
        assert not probe.blocked_effects and not probe.network.blocked
    assert result is None
    reloaded = await AgentService(h.db).repo.plan_for(OWNER, h.goal.id)
    assert [step.status for step in reloaded.steps] == ["succeeded", "failed", "skipped", "pending"]
    assert reloaded.steps[0].note == h.plan.steps[0].note and reloaded.steps[1].attempts == 1
    assert reloaded.steps[-1].parameters == {"memory_offset": 600, "memory_version": "synthetic-source-version"}
    assert reloaded.steps[-1].input_refs == ["mem_synthetic"]
    assert reloaded.revisions == h.budget.cognitive_calls == h.run.replans == 1
    assert answer == original
    assert await h.db.agent_action_attempts.count_documents({}) == 0
    assert await h.db.agent_receipts.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["mixed", "object", "number", "empty", "capacity", "replace_shape"])
async def test_invalid_modify_never_applies_subset_or_publishes_a_revision(monkeypatch, invalid):
    h = await setup(monkeypatch, at_capacity=invalid == "capacity")
    valid = {"intent": "Rilettura dichiarata", "step_type": "inspect", "capability_needed": "information.read"}
    raw_steps = [valid]
    if invalid == "mixed":
        raw_steps.append({"step_type": "prepare", "intent": ""})
    elif invalid == "object":
        raw_steps = valid
    elif invalid == "number":
        raw_steps = 7
    elif invalid == "empty":
        raw_steps = []
    elif invalid == "capacity":
        raw_steps.append(dict(valid, intent="Secondo passo indispensabile"))
    answer = {"decision": "modify", "reasoning": "PRIVATE_UNTRUSTED_REASON",
        "revised_steps": raw_steps,
        "replace_step_ids": h.pending.id if invalid == "replace_shape" else [h.pending.id],
        "situation_outcome": {"headline": "PRIVATE_UNTRUSTED_OUTCOME"}}
    original = deepcopy(answer)
    monkeypatch.setattr(reasoning, "reconsider", AsyncMock(return_value=answer))
    before_plan = await h.db.agent_plans.find_one({"owner_id": OWNER, "id": h.plan.id})
    before_goal = await h.db.agent_goals.find_one({"owner_id": OWNER, "id": h.goal.id})
    result = await h.service._reconsider(OWNER, h.goal, h.plan, h.run, h.budget,
        what_happened={"problem": "synthetic_failure"}, language="it")
    assert result["state"] == "in_progress"
    current = await h.db.agent_plans.find_one({"owner_id": OWNER, "id": h.plan.id})
    assert current["steps"] == before_plan["steps"] and current["revisions"] == 0
    assert await h.db.agent_goals.find_one({"owner_id": OWNER, "id": h.goal.id}) == before_goal
    h.assessment.assert_not_awaited()
    assert await h.db.agent_journal.count_documents({"goal_id": h.goal.id, "kind": "replanned"}) == 0
    diagnostic = await h.db.agent_journal.find_one({"goal_id": h.goal.id, "kind": "replan_protocol_invalid"})
    assert diagnostic and diagnostic["detail"]["validation_errors"]
    encoded = json.dumps(diagnostic, default=str)
    assert "PRIVATE_UNTRUSTED" not in encoded
    assert h.budget.cognitive_calls == h.run.replans == 1 and answer == original
    assert await h.db.agent_action_attempts.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["plan", "reconsider"])
async def test_actual_sdk_receives_complete_canonical_step_declaration(stage, monkeypatch):
    step = {"intent": "Leggere la fonte indicata", "step_type": "inspect", "capability_needed": "information.read"}
    response = {"planning_outcome": "plan", "steps": [step]} if stage == "plan" else {
        "decision": "modify", "revised_steps": [step], "replace_step_ids": []}

    def reply(system, payload):
        schema, _ = json.JSONDecoder().raw_decode(system.split("Return JSON: ", 1)[1])
        declared = schema["steps" if stage == "plan" else "revised_steps"]
        assert len(declared) == 1 and "step_type" in declared[0]
        assert "parameters" in declared[0] and "input_refs" in declared[0]
        assert "effect_type" not in declared[0] and "ask_kind" not in declared[0]
        assert AgentService._read_step(declared[0], 0) is not None
        execute, _ = json.JSONDecoder().raw_decode(system.split("Execute declaration example: ", 1)[1])
        ask, _ = json.JSONDecoder().raw_decode(system.split("Ask declaration example: ", 1)[1])
        assert AgentService._read_step(execute, 0).step_type == "execute"
        assert AgentService._read_step(ask, 0).ask_kind == "knowledge"
        assert "effect_type" in execute and "effect_target" in execute
        assert "asks" in ask and "ask_kind" in ask
        return response

    transported = fake_gemini(monkeypatch, reply)
    db = AsyncMongoMockClient().synthetic_replan_schema
    with gate.isolated_engine(db, mode="live"):
        if stage == "plan":
            result = await reasoning.make_plan({"objective": "Obiettivo sintetico"}, capabilities=[], context={})
        else:
            result = await reasoning.reconsider({"objective": "Obiettivo sintetico"}, plan={"steps": []},
                what_happened={"problem": "synthetic_failure"}, capabilities=[])
    assert result == response and len(transported) == 1
