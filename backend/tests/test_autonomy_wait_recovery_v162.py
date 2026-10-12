"""A due wait keeps its existing technical retry when judgement is unavailable.

The reader, source fences, service, durable goal and wake recovery are real
internal code over synthetic Mongo. Only model replies and unrelated surface
work are replaced; no real model, provider or external effect is used.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from unittest.mock import AsyncMock

import pytest

from agent import background, reasoning
from agent.background import advance_wake, recover_due
from agent.service import AgentService
from ambient.models import AmbientWake
from test_preparation_recovery_v162 import OWNER, RESULT, seed_recovery


@pytest.fixture
def clock(monkeypatch):
    import agent.repository as repository
    import agent.service as service

    now = [datetime.now(timezone.utc)]

    class ClockDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now[0].astimezone(tz) if tz else now[0].replace(tzinfo=None)

    monkeypatch.setattr(service, "_now", lambda: now[0])
    monkeypatch.setattr(repository, "_now", lambda: now[0])
    monkeypatch.setattr(background, "datetime", ClockDateTime)
    monkeypatch.setattr(AgentService, "_consider_visibility", AsyncMock())
    monkeypatch.setattr(AgentService, "_note_ambient", AsyncMock())
    monkeypatch.setattr(AgentService, "_observe_life_change", AsyncMock())
    return now


async def waiting_after_rejected_preparation(clock):
    db, goal, plan, source, _ = await seed_recovery()
    await AgentService(db).repo.ensure_indexes()
    goal.status = plan.status = "waiting"
    goal.next_run_at = (clock[0] - timedelta(seconds=1)).isoformat()
    plan.steps[1].status = "failed"
    plan.steps[1].attempts = 1
    plan.steps[1].note = "La preparazione precedente non era sostenuta dalle fonti."
    await AgentService(db).repo.save_goal(goal)
    await AgentService(db).repo.save_plan(plan)
    return db, goal, plan, source


def successful_reply(payload, source):
    if "draft" in payload:
        return {"verified": True, "content": RESULT, "evidence_ids": [source.id]}
    if "step" in payload and "evidence" in payload:
        return {"content": RESULT, "evidence_ids": [source.id]}
    if isinstance(payload.get("what_was_done"), dict):
        return {"outcome": "achieved", "reasoning": "Il confronto è stato preparato dalle fonti correnti."}
    raise AssertionError("Unexpected synthetic model call")


@pytest.mark.asyncio
@pytest.mark.parametrize("unavailable", [None, {"decision": "not_a_decision"}])
async def test_due_wait_keeps_retry_after_missing_or_invalid_judgement(monkeypatch, clock, unavailable):
    db, goal, plan, source = await waiting_after_rejected_preparation(clock)
    failed_history = deepcopy(plan.steps[1].model_dump())
    calls = []

    async def answer(_system, encoded, *, response_schema=None):
        payload = json.loads(encoded)
        calls.append(payload)
        if "what_happened" in payload:
            assert payload["what_happened"]["problem"] == "scheduled_external_checkpoint"
            return unavailable
        return successful_reply(payload, source)

    monkeypatch.setattr(reasoning, "_ask_model", answer)
    first = await AgentService(db).advance(OWNER, goal.id, worker_id="ambient:first-wait")
    assert first["state"] == "in_progress" and len(calls) == 1
    reloaded = await AgentService(db).repo.get_goal(OWNER, goal.id)
    assert reloaded.status == "active" and reloaded.background_runs == 1
    assert reloaded.next_run_at == (clock[0] + timedelta(minutes=5)).isoformat()
    assert not reloaded.requires_user_input and not reloaded.requires_user_authority
    assert not reloaded.prepared_text

    clock[0] = datetime.fromisoformat(reloaded.next_run_at) + timedelta(seconds=1)
    assert await recover_due(db, now=clock[0], admit=False) == 1
    wake_doc = await db.ambient_wakes.find_one({
        "owner_id": OWNER, "source_ref": f"goal:{goal.id}", "status": "pending",
    })
    assert wake_doc is not None
    result = await advance_wake(db, AmbientWake.model_validate(wake_doc))
    current = await AgentService(db).repo.get_goal(OWNER, goal.id)
    current_plan = await AgentService(db).repo.plan_for(OWNER, goal.id)
    assert result.result == current.status == current_plan.status == "completed"
    assert current.next_run_at is None and current.background_runs == 2
    assert current.prepared_text == RESULT and current.prepared_sources == [source.id]
    assert current_plan.steps[1].model_dump() == failed_history
    assert await db.agent_evidence.count_documents({
        "owner_id": OWNER, "goal_id": goal.id, "provenance.capability": "information.read",
    }) == 1
    assert await db.agent_action_attempts.count_documents({}) == 0
    assert await recover_due(db, now=clock[0], admit=False) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["wait", "ask_knowledge", "ask_authority", "complete"])
async def test_new_decision_replaces_or_clears_the_preserved_retry(monkeypatch, clock, decision):
    db, goal, _plan, source = await waiting_after_rejected_preparation(clock)

    async def answer(_system, encoded, *, response_schema=None):
        payload = json.loads(encoded)
        if "what_happened" not in payload:
            return successful_reply(payload, source)
        if decision.startswith("ask_"):
            return {"decision": "ask", "asks": "Quale condizione vuoi applicare?",
                    "ask_kind": decision.removeprefix("ask_"), "reasoning": "Serve una scelta della persona."}
        return {"decision": decision, "wait_minutes": 37,
                "reasoning": "Decisione sintetica dopo il checkpoint."}

    monkeypatch.setattr(reasoning, "_ask_model", answer)
    result = await AgentService(db).advance(OWNER, goal.id, worker_id="ambient:new-decision")
    current = await AgentService(db).repo.get_goal(OWNER, goal.id)
    if decision == "wait":
        assert result["state"] == current.status == "waiting"
        assert current.next_run_at == (clock[0] + timedelta(minutes=37)).isoformat()
        assert not current.requires_user_input and not current.requires_user_authority
    elif decision.startswith("ask_"):
        assert result["state"] == "waiting_for_person" and current.status == "waiting"
        assert current.requires_user_input is (decision == "ask_knowledge")
        assert current.requires_user_authority is (decision == "ask_authority")
        assert current.next_run_at is None and not current.prepared_text
        assert await recover_due(db, now=clock[0] + timedelta(hours=1), admit=False) == 0
    else:
        assert result["state"] == current.status == "completed"
        assert current.next_run_at is None and current.prepared_text == RESULT
        assert current.prepared_sources == [source.id]


@pytest.mark.asyncio
async def test_technical_recovery_remains_bounded_by_existing_background_cap(monkeypatch, clock):
    db, goal, _plan, _source = await waiting_after_rejected_preparation(clock)
    unavailable = AsyncMock(return_value=None)
    monkeypatch.setattr(reasoning, "_ask_model", unavailable)

    for attempts in (1, 2, 3):
        result = await AgentService(db).advance(OWNER, goal.id, worker_id=f"ambient:retry-{attempts}")
        current = await AgentService(db).repo.get_goal(OWNER, goal.id)
        assert result["state"] == "in_progress" and current.status == "active"
        assert current.background_runs == attempts
        assert not current.prepared_text and not current.requires_user_input and not current.requires_user_authority
        if attempts < 3:
            assert current.next_run_at == (clock[0] + timedelta(minutes=5)).isoformat()
            clock[0] = datetime.fromisoformat(current.next_run_at) + timedelta(seconds=1)
        else:
            assert current.next_run_at is None
    prior_calls = unavailable.await_count
    result = await AgentService(db).advance(OWNER, goal.id, worker_id="ambient:cap")
    assert result["state"] == "background_paused" and unavailable.await_count == prior_calls
    assert await recover_due(db, now=clock[0], admit=False) == 0
    assert await db.agent_evidence.count_documents({
        "owner_id": OWNER, "goal_id": goal.id, "provenance.capability": "information.read",
    }) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["owner", "input", "authority", "defer", "cancelled"])
async def test_wait_recovery_does_not_override_existing_person_or_owner_boundaries(monkeypatch, clock, boundary):
    db, goal, _plan, _source = await waiting_after_rejected_preparation(clock)
    if boundary in ("input", "authority"):
        await db.agent_goals.update_one({"owner_id": OWNER, "id": goal.id},
            {"$set": {"requires_user_input" if boundary == "input" else "requires_user_authority": True}})
    elif boundary == "defer":
        await AgentService(db).repo.defer_goal(OWNER, goal.id, until=(clock[0] + timedelta(minutes=45)).isoformat())
    elif boundary == "cancelled":
        await AgentService(db).cancel(OWNER, goal.id)
    before = await db.agent_goals.find_one({"owner_id": OWNER, "id": goal.id}, {"_id": 0})
    forbidden = AsyncMock(side_effect=AssertionError("This wake may not consult a model"))
    monkeypatch.setattr(reasoning, "_ask_model", forbidden)
    wake = AmbientWake(owner_id="foreign-owner" if boundary == "owner" else OWNER,
                       reason="opportunity_revisit", source_ref=f"goal:{goal.id}")
    result = await advance_wake(db, wake)
    assert result.result == {"owner": "goal_closed", "input": "waiting_for_person",
                            "authority": "waiting_for_person", "defer": "goal_not_due",
                            "cancelled": "goal_closed"}[boundary]
    assert await db.agent_goals.find_one({"owner_id": OWNER, "id": goal.id}, {"_id": 0}) == before
    forbidden.assert_not_awaited()
    if boundary != "owner":
        assert await recover_due(db, now=clock[0], admit=False) == 0


@pytest.mark.asyncio
async def test_user_defer_arriving_during_unavailable_judgement_wins_over_retry(monkeypatch, clock):
    db, goal, _plan, _source = await waiting_after_rejected_preparation(clock)
    chosen_due = (clock[0] + timedelta(minutes=45)).isoformat()

    async def unavailable_after_defer(_system, _encoded, *, response_schema=None):
        assert await AgentService(db).repo.defer_goal(OWNER, goal.id, until=chosen_due)
        return None

    monkeypatch.setattr(reasoning, "_ask_model", unavailable_after_defer)
    await AgentService(db).advance(OWNER, goal.id, worker_id="ambient:deferred-during-judgement")
    current = await AgentService(db).repo.get_goal(OWNER, goal.id)
    assert current.status == "waiting"
    assert current.next_run_at == current.user_deferred_until == chosen_due
    assert not current.prepared_text and not current.requires_user_input and not current.requires_user_authority
    assert await recover_due(db, now=clock[0] + timedelta(minutes=6), admit=False) == 0


@pytest.mark.asyncio
async def test_source_withdrawal_during_reconsideration_prevents_completion_and_retry(monkeypatch, clock):
    db, goal, _plan, _source = await waiting_after_rejected_preparation(clock)
    calls = []

    async def withdraw_before_complete(_system, encoded, *, response_schema=None):
        calls.append(json.loads(encoded))
        await db.memories.delete_one({"user_id": OWNER, "id": goal.source_refs[0]})
        return {"decision": "complete", "reasoning": "Obsolete decision returned after withdrawal."}

    monkeypatch.setattr(reasoning, "_ask_model", withdraw_before_complete)
    result = await AgentService(db).advance(OWNER, goal.id, worker_id="ambient:source-withdrawn")
    current = await AgentService(db).repo.get_goal(OWNER, goal.id)
    assert result["state"] == current.status == "abandoned" and len(calls) == 1
    assert current.next_run_at is None and not current.prepared_text and not current.prepared_sources
    assert not current.requires_user_input and not current.requires_user_authority
    assert await recover_due(db, now=clock[0], admit=False) == 0
    assert await db.agent_action_attempts.count_documents({}) == 0
