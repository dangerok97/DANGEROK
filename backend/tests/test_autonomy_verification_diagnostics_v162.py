"""Observe a verifier's real input refusal without changing its judgement.

The 650 live report recorded two verify calls that returned None before any
model request; it did not observe this reducer. These synthetic tests exercise
the boundary now, and do not assign a historical cause to those two calls.
"""
import asyncio
from copy import deepcopy
import hashlib
import json
from unittest.mock import AsyncMock

import pytest

from agent import reasoning
from agent.models import ActionPlan, AgentBudget, AgentEvidence, AgentRun
from agent.service import AgentService
from scripts import autonomy_completion_eval_v162 as gate
from test_autonomy_context_diagnostics_v162 import (
    contexts, goal, marked_database, no_network,  # noqa: F401
)


def real_verifier(monkeypatch):
    monkeypatch.setattr(gate.baseline, "scripted_verify", reasoning.verify_goal)
    model = AsyncMock(return_value=None)
    monkeypatch.setattr(gate.baseline, "scripted_draft", model)
    return model


def finish_calls_verifier(monkeypatch, *, before=None, in_child=False):
    async def finish(self, owner_id, current_goal, *args, **kwargs):
        if before:
            await before()
        call = reasoning.verify_goal({"objective": "private-synthetic-context"}, evidence={})
        return await asyncio.create_task(call) if in_child else await call

    monkeypatch.setattr(AgentService, "_finish", finish)


@pytest.mark.asyncio
@pytest.mark.parametrize("state,reason", [
    ("available", None),
    ("missing_source", "prepared_source_missing"),
    ("overflow", "material_context_exceeds_budget"),
    ("criteria_overflow", "goal_criteria_exceed_budget"),
])
async def test_actual_finish_and_verifier_observe_the_original_boundary(monkeypatch, state, reason):
    db = await marked_database()
    current_goal = goal()
    sources = [AgentEvidence(owner_id=gate.OWNER, goal_id=current_goal.id,
        claim=(f"Fonte sintetica {i}: " + str(i % 10) * 600)[:600])
        for i in range(12 if state == "overflow" else 1)]
    if state in ("missing_source", "overflow"):
        current_goal.prepared_text = "Bozza sintetica " + "z" * (3800 if state == "overflow" else 20)
        current_goal.prepared_sources = [item.id for item in sources]
    if state == "criteria_overflow":
        current_goal.objective = "Requisito sintetico " + "r" * 11000
    await db.agent_goals.insert_one(current_goal.model_dump())
    await db.agent_evidence.insert_many([item.model_dump() for item in sources])
    model = real_verifier(monkeypatch)
    original, captured = reasoning._verification_dump, []

    def capture(payload):
        snapshot = deepcopy(payload)
        result = original(payload)
        assert payload == snapshot
        captured.append((snapshot, result))
        return result

    monkeypatch.setattr(reasoning, "_verification_dump", capture)
    sentinel = {"synthetic_pause": state}
    pause = AsyncMock(return_value=sentinel)
    monkeypatch.setattr(AgentService, "_pause", pause)
    budget = AgentBudget()
    before = current_goal.model_dump()
    service = AgentService(db)
    if state == "missing_source":
        # The owned source exists at the initial source fence, but the later
        # evidence query is unavailable. Do not bypass source refresh itself.
        monkeypatch.setattr(service.evidence, "for_goal", AsyncMock(return_value=[]))
    with gate.isolated_engine(db) as probe:
        result = await service._finish(gate.OWNER, current_goal,
            ActionPlan(owner_id=gate.OWNER, goal_id=current_goal.id),
            AgentRun(owner_id=gate.OWNER, goal_id=current_goal.id), budget, language="it")

    assert result is sentinel and pause.await_count == 1
    assert model.await_count == (1 if state == "available" else 0)
    assert budget.cognitive_calls == 1
    assert current_goal.model_dump() == before
    assert await db.agent_evidence.count_documents({}) == len(sources)
    assert await db.agent_action_attempts.count_documents({}) == 0
    payload, encoded = captured[0]
    source = json.dumps(payload, ensure_ascii=False, default=str)
    row, = contexts(probe)
    assert row["stage"] == "verify_goal" and row["goal_id"] == current_goal.id
    assert row["available"] is (state == "available")
    assert row["unavailable_reason"] == reason
    assert row["input_characters"] == len(source)
    assert row["input_sha256"] == hashlib.sha256(source.encode()).hexdigest()
    assert row["encoded_characters"] == (len(encoded) if encoded is not None else None)
    assert row["section_characters"]["what_was_done"] == len(json.dumps(payload["what_was_done"], ensure_ascii=False))
    assert len(row["input"]) <= gate.CONTEXT_TEXT_LIMIT
    assert row["input_truncated"] is (state in ("overflow", "criteria_overflow"))
    assert probe.model_attempts == probe.model_http_requests == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("violation", ["owner", "goal_owner", "database", "marker", "revoked", "child"])
async def test_verifier_diagnostics_cannot_borrow_another_scope(monkeypatch, violation):
    db = await marked_database()
    target_db, owner, current_goal = db, gate.OWNER, goal()
    if violation == "owner":
        owner = "foreign-owner"
    elif violation == "goal_owner":
        current_goal.owner_id = "foreign-owner"
    elif violation == "database":
        target_db = await marked_database()
    elif violation == "marker":
        await db.eval_guards.delete_many({})
    finish_calls_verifier(monkeypatch, in_child=violation == "child",
        before=(lambda: db.eval_guards.delete_many({})) if violation == "revoked" else None)
    model = real_verifier(monkeypatch)
    with gate.isolated_engine(db) as probe:
        assert await AgentService(target_db)._finish(owner, current_goal) is None
    assert model.await_count == 1 and contexts(probe) == []
    assert "private-synthetic-context" not in json.dumps(gate.model_observations(probe))


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RuntimeError("private failure"), asyncio.CancelledError("private cancellation")])
async def test_verifier_error_and_scope_restoration_keep_original_identity(monkeypatch, error):
    db = await marked_database()
    finish_calls_verifier(monkeypatch)
    real_verifier(monkeypatch)
    original_logger, calls = reasoning.logger.info, []

    def failing(payload):
        calls.append(payload)
        raise error

    monkeypatch.setattr(reasoning, "_verification_dump", failing)
    with gate.isolated_engine(db) as probe:
        with pytest.raises(type(error)) as caught:
            await AgentService(db)._finish(gate.OWNER, goal())
        assert caught.value is error
        assert reasoning.logger.info == original_logger
        with pytest.raises(type(error)) as direct:
            await reasoning.verify_goal({}, evidence={})
        assert direct.value is error
    assert len(calls) == 2 and contexts(probe) == []
    assert "private failure" not in json.dumps(gate.model_observations(probe))
    assert "private cancellation" not in json.dumps(gate.model_observations(probe))


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["child", "thread"])
async def test_an_inherited_active_verifier_scope_cannot_export_a_foreign_reducer(monkeypatch, surface):
    db = await marked_database()
    finish_calls_verifier(monkeypatch)
    calls = []

    def direct():
        result = reasoning._verification_dump({"goal": {"objective": "private-foreign-reducer"}, "what_was_done": {}})
        calls.append(result)
        return result

    async def child():
        return direct()

    async def verify(*args, **kwargs):
        return await asyncio.create_task(child()) if surface == "child" else await asyncio.to_thread(direct)

    monkeypatch.setattr(gate.baseline, "scripted_verify", verify)
    with gate.isolated_engine(db) as probe:
        result = await AgentService(db)._finish(gate.OWNER, goal())
    assert result == calls[0] and contexts(probe) == []
    assert "private-foreign-reducer" not in json.dumps(gate.model_observations(probe))


@pytest.mark.asyncio
async def test_verifier_observation_is_best_effort_and_shares_the_existing_cap(monkeypatch):
    db = await marked_database()
    finish_calls_verifier(monkeypatch)
    model = real_verifier(monkeypatch)
    count = gate.MAX_DECISION_OBSERVATIONS + 3
    with gate.isolated_engine(db) as probe:
        for _ in range(count):
            assert await AgentService(db)._finish(gate.OWNER, goal()) is None
        assert len(contexts(probe)) == gate.MAX_DECISION_OBSERVATIONS
        assert [row["sequence"] for row in contexts(probe)] == [1, 2, *range(6, count + 1)]
        assert probe.context_observations_omitted == 3
        monkeypatch.setattr(gate, "_action_context_observation", lambda *a, **k: (_ for _ in ()).throw(ValueError("private")))
        assert await AgentService(db)._finish(gate.OWNER, goal()) is None
        assert len(contexts(probe)) == gate.MAX_DECISION_OBSERVATIONS
    assert model.await_count == count + 1
    assert probe.model_attempts == probe.model_http_requests == 0
