"""A rejected synthetic result never becomes a PASS through delivery checks.

The real worker, storage, Home handoff and existing semantic oracle are used.
Only scripted model content or the boundary under test is deliberately faulty.
No model, push or external effect is performed.
"""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.service import AgentService
from agent.visibility import VisibilityService
from scripts import autonomy_completion_eval_v162 as gate


CHECKS = {"preconditions", "semantic", "home", "replay", "owner_isolation", "isolation"}


@pytest.fixture
def missing_comparison(monkeypatch):
    # A deliberately incomplete model answer, with the original source and
    # review_comparison untouched. It remains an audited, saved string.
    text = gate.baseline.DRAFT.replace("60 euro", "un importo non esplicitato")
    assert gate.review_comparison(text)["reasons"] == ["MISSING_COMPARISON_VALUE_60"]
    monkeypatch.setattr(gate.baseline, "DRAFT", text)
    return text


@pytest.mark.asyncio
async def test_semantic_failure_still_recovers_home_and_checks_replay_owner(
    monkeypatch, tmp_path, missing_comparison,
):
    observed = {}
    calls = []
    original_run, original_advance = gate.run_case, AgentService.advance

    async def retain_probe(scenario, *, mode, probe):
        observed["probe"] = probe
        return await original_run(scenario, mode=mode, probe=probe)

    async def advance(self, owner_id, goal_id, **kwargs):
        calls.append((owner_id, kwargs.get("worker_id")))
        return await original_advance(self, owner_id, goal_id, **kwargs)

    monkeypatch.setattr(gate, "run_case", retain_probe)
    monkeypatch.setattr(AgentService, "advance", advance)
    output = tmp_path / "semantic-failure.json"
    assert await gate.main(scenario="home_write_retry", output=str(output)) == 1
    report = json.loads(output.read_text())
    case = report["cases"][0]
    assert not report["passed"] and not case["passed"]
    assert case["reason"] == "SEMANTIC_RESULT_REJECTED:MISSING_COMPARISON_VALUE_60"
    probe = observed["probe"]
    db = probe.database
    assert probe.faults == ["home_write_failed_once"]
    assert await db.agent_updates.count_documents({"owner_id": gate.OWNER, "home_pending": True}) == 0
    assert await db.ambient_activity.count_documents({"owner_id": gate.OWNER,
        "cognitive_provenance.agent": "visibility"}) == 1
    assert calls.count((gate.OWNER, "ambient:v162-replay")) == 1
    assert calls.count(("another-synthetic-owner", None)) == 1
    checks = case["result_checks"]
    assert set(checks) == CHECKS
    assert checks["semantic"] == {"status": "failed", "review": gate.review_comparison(missing_comparison)}
    assert all(checks[name]["status"] == "passed" for name in CHECKS - {"semantic"})
    goal = await db.agent_goals.find_one({"owner_id": gate.OWNER})
    assert goal["status"] == "completed" and goal["prepared_text"] == missing_comparison
    assert case["failure_state"]["goals"][0]["prepared_text"] == missing_comparison
    assert probe.model_attempts == probe.model_http_requests == probe.blocked_effects == probe.push_attempts == 0
    assert await db.agent_action_attempts.count_documents({}) == await db.action_intents.count_documents({}) == 0


@pytest.mark.asyncio
async def test_later_home_failure_preserves_both_diagnostics_and_unrun_checks(
    monkeypatch, tmp_path, missing_comparison,
):
    monkeypatch.setattr(VisibilityService, "show", AsyncMock(return_value=None))
    output = tmp_path / "home-failure.json"
    assert await gate.main(scenario="completed_result", output=str(output)) == 1
    case = json.loads(output.read_text())["cases"][0]
    assert not case["passed"] and case["reason"] == "HOME_OUTBOX_NOT_DELIVERED"
    checks = case["result_checks"]
    assert checks["semantic"]["review"] == gate.review_comparison(missing_comparison)
    assert checks["semantic"]["status"] == "failed"
    assert checks["home"] == {"status": "failed", "reason": "HOME_OUTBOX_NOT_DELIVERED"}
    assert all(checks[name]["status"] == "not_run" for name in ("replay", "owner_isolation", "isolation"))


@pytest.mark.asyncio
async def test_isolation_failure_after_semantic_failure_is_not_masked(
    monkeypatch, tmp_path, missing_comparison,
):
    original = gate.verify_result

    async def observed_boundary(db, goal_id, probe, **kwargs):
        result = await original(db, goal_id, probe, **kwargs)
        # Attest an attempted effect was blocked; perform no effect.
        probe.blocked_effects += 1
        return result

    monkeypatch.setattr(gate, "verify_result", observed_boundary)
    output = tmp_path / "boundary-failure.json"
    assert await gate.main(scenario="completed_result", output=str(output)) == 1
    case = json.loads(output.read_text())["cases"][0]
    assert not case["passed"] and case["reason"] == "ISOLATION_BOUNDARY_ATTEMPTED"
    checks = case["result_checks"]
    assert checks["semantic"]["status"] == "failed"
    assert checks["isolation"] == {"status": "failed", "reason": "ISOLATION_BOUNDARY_ATTEMPTED"}
    assert all(checks[name]["status"] == "passed" for name in ("preconditions", "home", "replay", "owner_isolation"))


async def completed_with_pending_home(db, probe):
    await gate.seed_case(db, "home_write_retry")
    goal_id = await gate.admit(db, "home_write_retry", probe)
    await gate.first_read(db, goal_id, probe)
    await gate.complete_due_work(db, goal_id, probe)
    assert await db.agent_updates.count_documents({"owner_id": gate.OWNER, "home_pending": True}) == 1
    return goal_id


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary,reason", [
    ("owner", "GOAL_NOT_COMPLETED"),
    ("marker", "SYNTHETIC_RESULT_GUARD_MISSING"),
])
async def test_invalid_preconditions_do_not_run_semantics_or_home(monkeypatch, boundary, reason):
    db = AsyncMongoMockClient().v162_result_preconditions
    probe = gate.Probe(database=db)
    with gate.isolated_engine(db, scenario="home_write_retry", probe=probe):
        goal_id = await completed_with_pending_home(db, probe)
        if boundary == "owner":
            await db.agent_goals.update_one({"owner_id": gate.OWNER, "id": goal_id},
                                           {"$set": {"owner_id": "another-synthetic-owner"}})
        else:
            await db.eval_guards.delete_one({"_id": gate.VERSION})
        recovery = AsyncMock(side_effect=AssertionError("Recovery must not run"))
        monkeypatch.setattr(gate, "recover_home", recovery)
        with pytest.raises(gate.EvaluationFailure, match="^" + reason + "$"):
            await gate.verify_result(db, goal_id, probe)
    recovery.assert_not_awaited()
    assert probe.result_checks["preconditions"] == {"status": "failed", "reason": reason}
    assert all(probe.result_checks[name]["status"] == "not_run" for name in CHECKS - {"preconditions"})
    assert await db.agent_updates.count_documents({"owner_id": gate.OWNER, "home_pending": True}) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("raised,expected_status", [
    (RuntimeError("PRIVATE_ERROR_PAYLOAD_MUST_NOT_APPEAR"), "failed"),
    (asyncio.CancelledError(), "interrupted"),
])
async def test_recovery_exception_is_not_swallowed_or_exported_raw(
    monkeypatch, missing_comparison, raised, expected_status,
):
    db = AsyncMongoMockClient().v162_result_interrupted
    probe = gate.Probe(database=db)
    with gate.isolated_engine(db, scenario="home_write_retry", probe=probe):
        goal_id = await completed_with_pending_home(db, probe)
        monkeypatch.setattr(gate, "recover_home", AsyncMock(side_effect=raised))
        with pytest.raises(type(raised)) as caught:
            await gate.verify_result(db, goal_id, probe)
    assert caught.value is raised
    assert probe.result_checks["semantic"]["status"] == "failed"
    assert probe.result_checks["home"] == {"status": expected_status, "reason": type(raised).__name__}
    assert all(probe.result_checks[name]["status"] == "not_run" for name in ("replay", "owner_isolation", "isolation"))
    assert "PRIVATE_ERROR_PAYLOAD" not in json.dumps(probe.result_checks)


@pytest.mark.asyncio
async def test_direct_verification_still_raises_the_semantic_failure_after_checks(missing_comparison):
    db = AsyncMongoMockClient().v162_direct_result
    probe = gate.Probe(database=db)
    with gate.isolated_engine(db, scenario="home_write_retry", probe=probe):
        goal_id = await completed_with_pending_home(db, probe)
        with pytest.raises(gate.EvaluationFailure, match="^SEMANTIC_RESULT_REJECTED:MISSING_COMPARISON_VALUE_60$"):
            await gate.verify_result(db, goal_id, probe)
    assert all(probe.result_checks[name]["status"] == "passed" for name in ("preconditions", "home", "replay", "owner_isolation"))
    assert probe.result_checks["semantic"]["status"] == "failed"
    assert probe.result_checks["isolation"]["status"] == "not_run"
