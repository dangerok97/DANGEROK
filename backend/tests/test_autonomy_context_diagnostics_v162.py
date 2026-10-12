"""Observe the real pre-model boundary without changing choice or acceptance.

All databases, inputs and answers are synthetic. No model/provider request is
made. The service/chooser tests exercise both actual code-owned refusal causes;
the smaller wrapper tests cover privacy, retention and exception identity.
"""
import asyncio
from copy import deepcopy
import hashlib
import json
from unittest.mock import AsyncMock

import httpx
from mongomock_motor import AsyncMongoMockClient
import pytest

from agent import reasoning
from agent.models import ActionPlan, ActionStep, AgentBudget, AgentEvidence, AgentRun, AutonomousGoal
from agent.service import AgentService
from scripts import autonomy_completion_eval_v162 as gate


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    for key in gate.LLM_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(httpx.AsyncClient, "send", AsyncMock(side_effect=AssertionError("No network")))


async def marked_database():
    db = AsyncMongoMockClient().synthetic_action_context
    await db.eval_guards.insert_one({"_id": gate.VERSION, "owner": gate.OWNER})
    return db


def goal():
    return AutonomousGoal(owner_id=gate.OWNER, status="active",
        objective="Confrontare la nota sintetica.", desired_outcome="Un confronto interno.")


def use_real_chooser(monkeypatch, answer=None):
    # Only the model answer is substituted. The chooser and its reducer run.
    monkeypatch.setattr(gate.baseline, "scripted_choose", reasoning.choose_next_action)
    model = AsyncMock(return_value=answer or {"decision": "verify", "reasoning": "Risposta sintetica."})
    monkeypatch.setattr(gate.baseline, "scripted_draft", model)
    return model


def next_calls_chooser(monkeypatch, *, before=None, objective="Synthetic context only."):
    async def call(self, owner_id, current_goal, *args, **kwargs):
        if before:
            await before()
        return await reasoning.choose_next_action(
            {"objective": objective}, plan={}, candidates=[],
            evidence=[], capabilities=[],
        )
    monkeypatch.setattr(AgentService, "_next", call)


def contexts(probe):
    return gate.model_observations(probe).get("context_observations", [])


@pytest.mark.asyncio
@pytest.mark.parametrize("state,expected_reason", [
    ("available", None),
    ("missing_source", "prepared_source_missing"),
    ("overflow", "material_context_exceeds_budget"),
])
async def test_real_service_and_chooser_observe_original_refusal_before_model(monkeypatch, state, expected_reason):
    db = await marked_database()
    current_goal = goal()
    plan = ActionPlan(owner_id=gate.OWNER, goal_id=current_goal.id, steps=[
        ActionStep(step_type="prepare", intent="Preparare il confronto.", capability_needed="document.create")])
    sources = [AgentEvidence(owner_id=gate.OWNER, goal_id=current_goal.id,
        claim=((f"Fonte sintetica {i}: " + str(i % 10) * 600)[:600] if state == "overflow" else "Una nota sintetica."))
        for i in range(12 if state == "overflow" else 1)]
    if state == "missing_source":
        current_goal.prepared_text, current_goal.prepared_sources = "Una bozza sintetica.", ["evd_absent"]
    elif state == "overflow":
        current_goal.prepared_text = "Bozza sintetica " + "z" * 3800
        current_goal.prepared_sources = [item.id for item in sources]
    await db.agent_goals.insert_one(current_goal.model_dump())
    await db.agent_evidence.insert_many([item.model_dump() for item in sources])
    model = use_real_chooser(monkeypatch)
    original_dump, inputs = reasoning._action_dump, []

    def capture(payload):
        inputs.append(deepcopy(payload))
        before = deepcopy(payload)
        result = original_dump(payload)
        assert payload == before
        return result

    monkeypatch.setattr(reasoning, "_action_dump", capture)
    before_goal, before_plan = current_goal.model_dump(), plan.model_dump()
    budget = AgentBudget()
    with gate.isolated_engine(db) as probe:
        result = await AgentService(db)._next(gate.OWNER, current_goal, plan,
            AgentRun(owner_id=gate.OWNER, goal_id=current_goal.id), budget, language="it")

    assert result == (("finish", None) if state == "available" else ("stalled", None))
    assert model.await_count == (1 if state == "available" else 0)
    assert budget.cognitive_calls == 1  # the existing runtime charge is unchanged
    row, = contexts(probe)
    encoded = json.dumps(inputs[0], ensure_ascii=False, default=str)
    assert row["stage"] == "choose_next_action" and row["goal_id"] == current_goal.id
    assert row["available"] is (state == "available")
    assert row["unavailable_reason"] == expected_reason
    assert row["input_characters"] == len(encoded)
    assert row["input_sha256"] == hashlib.sha256(encoded.encode()).hexdigest()
    assert row["encoded_characters"] == (len(original_dump(inputs[0])) if state == "available" else None)
    assert row["section_characters"]["what_has_been_found"] == len(json.dumps(inputs[0]["what_has_been_found"], ensure_ascii=False))
    assert row["input_truncated"] is (state == "overflow")
    assert len(row["input"]) <= 9000
    assert row["model_attempts"] == probe.model_attempts == probe.model_http_requests == 0
    assert current_goal.model_dump() == before_goal and plan.model_dump() == before_plan
    assert await db.agent_evidence.count_documents({}) == len(sources)
    assert await db.agent_action_attempts.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("violation", ["owner", "goal_owner", "database", "missing_marker", "foreign_marker", "marker_outage"])
async def test_context_export_requires_exact_owner_database_and_marker(monkeypatch, violation):
    db = await marked_database()
    current_goal, owner, target_db = goal(), gate.OWNER, db
    failed_read = None
    if violation == "owner":
        owner = "foreign-owner"
    elif violation == "goal_owner":
        current_goal.owner_id = "foreign-owner"
    elif violation == "database":
        target_db = await marked_database()
    elif violation == "missing_marker":
        await db.eval_guards.delete_many({})
    elif violation == "foreign_marker":
        await db.eval_guards.update_one({"_id": gate.VERSION}, {"$set": {"owner": "foreign-owner"}})
    else:
        # This adapter constructs a new collection wrapper on each access.
        failed_read = AsyncMock(side_effect=TimeoutError("private failure"))
        monkeypatch.setattr(type(db.eval_guards), "find_one", failed_read)
    next_calls_chooser(monkeypatch, objective="private-context-must-not-export")
    model = use_real_chooser(monkeypatch)
    with gate.isolated_engine(db) as probe:
        result = await AgentService(target_db)._next(owner, current_goal)
    assert result["decision"] == "verify" and model.await_count == 1
    assert contexts(probe) == []
    assert "private-context-must-not-export" not in json.dumps(gate.model_observations(probe))
    if failed_read is not None:
        failed_read.assert_awaited_once()


@pytest.mark.asyncio
async def test_direct_chooser_and_revoked_marker_do_not_borrow_a_service_scope(monkeypatch):
    db = await marked_database()
    current_goal = goal()
    next_calls_chooser(monkeypatch, before=lambda: db.eval_guards.delete_many({}))
    model = use_real_chooser(monkeypatch)
    with gate.isolated_engine(db) as probe:
        await reasoning.choose_next_action({}, plan={}, candidates=[], evidence=[], capabilities=[])
        await AgentService(db)._next(gate.OWNER, current_goal)
    assert model.await_count == 2 and contexts(probe) == []


@pytest.mark.asyncio
async def test_payload_redaction_bounds_sections_and_unknown_cause_do_not_mutate_inputs(monkeypatch):
    db = await marked_database()
    current_goal = goal()
    secret = "synthetic-context-credential-only"
    monkeypatch.setenv("GEMINI_API_KEY_2", secret)
    payload = {"goal": {"objective": secret + "x" * 9500}, "plan": {"steps": []},
        "what_has_been_found": [{"value": False, "missing": None}], "not_a_section": 99}
    original = deepcopy(payload)
    next_calls_chooser(monkeypatch)

    async def choose(*args, **kwargs):
        return reasoning._action_dump(payload)

    monkeypatch.setattr(gate.baseline, "scripted_choose", choose)

    def unavailable(_payload):
        reasoning.logger.info("Unrecognised cause with private credential %s", secret)
        return None

    monkeypatch.setattr(reasoning, "_action_dump", unavailable)
    with gate.isolated_engine(db) as probe:
        assert await AgentService(db)._next(gate.OWNER, current_goal) is None
    row, = contexts(probe)
    assert row["available"] is False and row["unavailable_reason"] is None
    assert row["encoded_characters"] is None and row["input_truncated"] is True
    assert len(row["input"]) == 9000
    assert secret not in json.dumps(row) and "[credential redacted]" in row["input"]
    assert set(row["section_characters"]) == {"goal", "plan", "what_has_been_found"}
    assert payload == original and probe.model_attempts == probe.model_http_requests == 0


@pytest.mark.asyncio
async def test_bounded_context_retention_preserves_first_and_last_without_new_calls(monkeypatch):
    db = await marked_database()
    current_goal = goal()
    next_calls_chooser(monkeypatch)
    model = use_real_chooser(monkeypatch)
    count = gate.MAX_DECISION_OBSERVATIONS + 3
    with gate.isolated_engine(db) as probe:
        for _ in range(count):
            assert (await AgentService(db)._next(gate.OWNER, current_goal))["decision"] == "verify"
    rows = contexts(probe)
    assert len(rows) == gate.MAX_DECISION_OBSERVATIONS
    assert [row["sequence"] for row in rows] == [1, 2, *range(6, count + 1)]
    report = gate.model_observations(probe)
    assert report["context_observations_omitted"] == 3
    assert "_action_dump" in report["context_observations_scope"]
    assert model.await_count == count and probe.model_attempts == probe.model_http_requests == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("exception", [RuntimeError("private failure"), asyncio.CancelledError("private cancellation")])
async def test_original_exception_identity_and_scope_reset_are_preserved(monkeypatch, exception):
    db = await marked_database()
    current_goal = goal()
    next_calls_chooser(monkeypatch)
    use_real_chooser(monkeypatch)
    original_logger = reasoning.logger.info
    calls = 0

    def failing_then_valid(payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise exception
        return "{}"

    monkeypatch.setattr(reasoning, "_action_dump", failing_then_valid)
    with gate.isolated_engine(db) as probe:
        with pytest.raises(type(exception)) as caught:
            await AgentService(db)._next(gate.OWNER, current_goal)
        assert caught.value is exception
        assert reasoning.logger.info == original_logger
        assert reasoning._action_dump({"private": "outside-service-scope"}) == "{}"
    assert contexts(probe) == [] and calls == 2
    assert "private failure" not in json.dumps(gate.model_observations(probe))
    assert "private cancellation" not in json.dumps(gate.model_observations(probe))


@pytest.mark.asyncio
async def test_observation_failure_cannot_change_return_identity(monkeypatch):
    db = await marked_database()
    current_goal = goal()
    next_calls_chooser(monkeypatch)
    result = {"decision": "verify", "reasoning": "Risposta invariata."}
    opaque_encoding = object()
    model = use_real_chooser(monkeypatch, result)
    monkeypatch.setattr(reasoning, "_action_dump", lambda payload: opaque_encoding)
    monkeypatch.setattr(gate, "_action_context_observation", lambda *args: (_ for _ in ()).throw(ValueError("private observer error")), raising=False)
    with gate.isolated_engine(db) as probe:
        returned = await AgentService(db)._next(gate.OWNER, current_goal)
    assert returned is result
    assert model.call_args.args[1] is opaque_encoding
    assert contexts(probe) == [] and probe.model_attempts == probe.model_http_requests == 0
