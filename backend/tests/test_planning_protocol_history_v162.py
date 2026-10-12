"""Retry planning can see bounded format history without treating it as a plan."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from unittest.mock import AsyncMock

from mongomock_motor import AsyncMongoMockClient
import pytest

from agent.models import AutonomousGoal
from agent.service import AgentService
from scripts import autonomy_completion_eval_v162 as gate


ERROR = {"index": 0, "field": "effect_type", "issue": "wrong_type"}


@pytest.mark.asyncio
async def test_retry_receives_historical_format_diagnosis_and_keeps_real_completion_path(monkeypatch):
    original = gate.baseline.scripted_make_plan
    contexts = []

    async def plan(*args, **kwargs):
        contexts.append(deepcopy(kwargs["context"]))
        answer = await original(*args, **kwargs)
        if len(contexts) == 1:
            # Deliberately malformed synthetic value, not a reconstruction of
            # the live error, whose rejected value was never exported.
            answer["steps"][0]["effect_type"] = {"private": "PRIVATE_RESPONSE_VALUE"}
        return answer

    monkeypatch.setattr(gate.baseline, "scripted_make_plan", plan)
    probe = gate.Probe()
    report = await gate.run_case("completed_result", probe=probe)
    assert report["passed"] and report["result"]["state"] == "completed"
    assert len(contexts) == 2 and "planning_protocol_history" not in contexts[0]
    assert contexts[1]["planning_protocol_history"] == {
        "origin": "code_owned_format_history", "scope": "past_declaration_only",
        "validation_errors": [ERROR]}
    assert "PRIVATE_" not in json.dumps(contexts, default=str)
    assert report["result"]["home_delivered"] and report["result"]["replay_idempotent"]
    assert sum(step["capability"] == "information.read" for step in probe.steps) == 1
    assert probe.model_attempts == probe.model_http_requests == probe.blocked_effects == 0


async def history_fixture():
    db = AsyncMongoMockClient().synthetic_planning_history
    service = AgentService(db)
    goal = AutonomousGoal(owner_id="synthetic-planning-history", status="active",
        objective="Preparare un risultato sintetico.", desired_outcome="Un risultato attribuito alle fonti.",
        planning_unavailable=True, planning_attempts=2)
    row = {"owner_id": goal.owner_id, "goal_id": goal.id, "kind": "planning_protocol_invalid",
        "at": datetime.now(timezone.utc).isoformat(),
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        "note": "PRIVATE_OLD_MODEL_CONTENT", "detail": {"attempt": 1,
            "validation_errors": [{**ERROR, "value": "PRIVATE_REJECTED_VALUE"}],
            "private": "PRIVATE_PROMPT"}}
    return db, service, goal, row


@pytest.mark.asyncio
@pytest.mark.parametrize("excluded", ["foreign_owner", "foreign_goal", "expired", "first_attempt", "not_unavailable",
                                      "unknown_field", "unknown_issue", "boolean_index", "out_of_range", "wrong_shape"])
async def test_history_is_owner_scoped_bounded_and_optional(excluded):
    db, service, goal, row = await history_fixture()
    if excluded == "foreign_owner": row["owner_id"] = "someone-else"
    elif excluded == "foreign_goal": row["goal_id"] = "another-goal"
    elif excluded == "expired": row["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    elif excluded == "first_attempt": goal.planning_attempts = 1
    elif excluded == "not_unavailable": goal.planning_unavailable = False
    elif excluded == "unknown_field": row["detail"]["validation_errors"][0]["field"] = "PRIVATE_FIELD"
    elif excluded == "unknown_issue": row["detail"]["validation_errors"][0]["issue"] = "PRIVATE_ISSUE"
    elif excluded == "boolean_index": row["detail"]["validation_errors"][0]["index"] = True
    elif excluded == "out_of_range": row["detail"]["validation_errors"][0]["index"] = 12
    else: row["detail"]["validation_errors"] = {"private": "PRIVATE_PAYLOAD"}
    await db.agent_journal.insert_one(row)
    before = deepcopy(goal.model_dump())
    assert await service._planning_protocol_history(goal.owner_id, goal) is None
    assert goal.model_dump() == before


@pytest.mark.asyncio
async def test_history_excludes_values_and_does_not_claim_current_error_or_repair():
    db, service, goal, row = await history_fixture()
    row["detail"]["validation_errors"].append({"index": 1, "field": "PRIVATE_SECOND_FIELD", "issue": "PRIVATE_ISSUE"})
    await db.agent_journal.insert_one(row)
    observed = await service._planning_protocol_history(goal.owner_id, goal)
    assert observed == {"origin": "code_owned_format_history", "scope": "past_declaration_only",
                        "validation_errors": [ERROR]}
    assert "PRIVATE_" not in json.dumps(observed)
    assert await service._planning_protocol_history("other-owner", goal) is None
    assert goal.planning_attempts == 2 and goal.planning_unavailable


@pytest.mark.asyncio
async def test_optional_history_read_failure_cannot_block_or_reset_work(monkeypatch):
    db, service, goal, _ = await history_fixture()
    monkeypatch.setattr(db.agent_journal, "find_one", AsyncMock(side_effect=RuntimeError("PRIVATE_ERROR")))
    before = deepcopy(goal.model_dump())
    assert await service._planning_protocol_history(goal.owner_id, goal) is None
    assert goal.model_dump() == before
