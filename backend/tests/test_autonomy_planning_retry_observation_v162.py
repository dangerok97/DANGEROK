"""Observe real persisted planning retries without repairing model decisions.

All model answers are scripted, with one deliberately malformed declaration.
The synthetic worker, source reads, persistence and Home outbox remain real.
The malformed field is a test input, not a reconstruction of the live report.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import re
from unittest.mock import AsyncMock

from mongomock_motor import AsyncMongoMockClient
import pytest

from agent.service import AgentService, MAX_PLANNING_ATTEMPTS
from scripts import autonomy_completion_eval_v162 as gate


ERROR = {"index": 0, "field": "effect_type", "issue": "wrong_type"}
SECRET = "synthetic-sensitive-plan-value"
RUN_ID = "run_0123456789abcdef"


@pytest.fixture(autouse=True)
def no_model_credentials(monkeypatch):
    for key in gate.LLM_KEYS:
        monkeypatch.delenv(key, raising=False)


def malformed_plans(monkeypatch, count):
    original = gate.baseline.scripted_make_plan
    calls = []

    async def plan(*args, **kwargs):
        answer = await original(*args, **kwargs)
        if len(calls) < count:
            answer["steps"][0]["effect_type"] = {"token": SECRET}
        calls.append(deepcopy(answer))
        return answer

    monkeypatch.setattr(gate.baseline, "scripted_make_plan", plan)
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["completed_result", "home_write_retry", "source_change_crash"])
async def test_malformed_initial_plan_recovers_through_owned_worker_and_keeps_faults(monkeypatch, scenario):
    calls = malformed_plans(monkeypatch, 1)
    probe = gate.Probe()
    report = await gate.run_case(scenario, probe=probe)
    assert report["passed"] and report["result"]["state"] == "completed"
    assert report["result"]["home_delivered"] and report["result"]["replay_idempotent"]
    assert report["result"]["owner_isolation"]
    assert len(calls) == 2
    assert sum(step["capability"] == "information.read" for step in probe.steps) == 1
    assert report["planning_observations"] == [{
        "attempt": 1, "has_due": True, "validation_errors": [ERROR],
    }]
    assert report["planning_observations_omitted"] == 0
    if scenario == "home_write_retry":
        assert report["injected_faults"].count("home_write_failed_once") == 1
    if scenario == "source_change_crash":
        assert report["injected_faults"].count("source_scan_cancelled_once") == 1
    goal = await probe.database.agent_goals.find_one({"owner_id": gate.OWNER})
    assert goal["background_runs"] == 2 and goal["planning_attempts"] == 0
    assert await probe.database.agent_goals.count_documents({}) == 1
    assert await probe.database.agent_action_attempts.count_documents({}) == 0
    assert await probe.database.action_intents.count_documents({}) == 0
    assert probe.model_attempts == probe.model_http_requests == probe.blocked_effects == 0
    assert SECRET not in json.dumps(report)


@pytest.mark.asyncio
async def test_last_allowed_planning_attempt_can_read_without_resetting_the_budget(monkeypatch):
    calls = malformed_plans(monkeypatch, MAX_PLANNING_ATTEMPTS - 1)
    db = AsyncMongoMockClient().v162_planning_last_attempt
    with gate.isolated_engine(db) as probe:
        await gate.seed_case(db, "completed_result")
        goal_id = await gate.admit(db, "completed_result", probe)
        await gate.first_read(db, goal_id, probe)
    goal = await db.agent_goals.find_one({"id": goal_id, "owner_id": gate.OWNER})
    assert len(calls) == MAX_PLANNING_ATTEMPTS
    assert goal["status"] == "active" and goal["next_run_at"]
    assert goal["planning_attempts"] == 0 and not goal["planning_unavailable"]
    assert goal["background_runs"] == 1 and not goal["prepared_text"]
    assert [row["attempt"] for row in probe.planning_observations] == list(range(1, MAX_PLANNING_ATTEMPTS))
    assert await db.agent_evidence.count_documents({"goal_id": goal_id,
        "provenance.capability": "information.read"}) == 1


@pytest.mark.asyncio
async def test_reused_attempt_after_source_correction_does_not_inherit_old_protocol_error(monkeypatch):
    original = gate.baseline.scripted_make_plan
    calls = []

    async def plan(*args, **kwargs):
        calls.append(True)
        if len(calls) == 3:
            return None
        answer = await original(*args, **kwargs)
        if len(calls) == 1:
            answer["steps"][0]["effect_type"] = {"token": SECRET}
        return answer

    monkeypatch.setattr(gate.baseline, "scripted_make_plan", plan)
    db = AsyncMongoMockClient().v162_planning_new_cycle
    with gate.isolated_engine(db, probe=gate.Probe(database=db)) as probe:
        await gate.seed_case(db, "completed_result")
        goal_id = await gate.admit(db, "completed_result", probe)
        await gate.first_read(db, goal_id, probe)
        assert len(probe.planning_observations) == 1
        changed = await gate.change_memory(db, goal_id, correction=True)
        current = await gate.fire_due(db, goal_id, probe)
        state = await gate.failure_state(probe)
    assert len(calls) == 3 and current["planning_attempts"] == 1
    assert current["planning_unavailable"] and current["status"] == "active" and current["next_run_at"]
    assert changed["current"] in current["source_refs"] and changed["old"] not in current["source_refs"]
    assert await db.agent_goals.count_documents({}) == 1
    assert await db.agent_journal.count_documents({"kind": "planning_protocol_invalid"}) == 1
    assert len(probe.planning_observations) == 1
    assert state["available"] and "planning_error" not in state["goals"][0]
    assert probe.model_attempts == probe.model_http_requests == probe.blocked_effects == 0


@pytest.mark.asyncio
async def test_persistent_malformed_plan_stops_at_durable_cap_and_reports_safe_error(monkeypatch):
    calls = malformed_plans(monkeypatch, 100)
    probe = gate.Probe()
    with pytest.raises(gate.EvaluationFailure):
        await gate.run_case("completed_result", probe=probe)
    db = probe.database
    goal = await db.agent_goals.find_one({"owner_id": gate.OWNER})
    assert len(calls) == goal["planning_attempts"] == MAX_PLANNING_ATTEMPTS
    assert goal["status"] == "active" and goal["planning_unavailable"]
    assert goal["next_run_at"] is None and goal["background_runs"] == 0
    assert not goal["prepared_text"] and not goal["requires_user_input"] and not goal["requires_user_authority"]
    assert await db.agent_goals.count_documents({}) == 1
    assert await db.agent_plans.count_documents({}) == await db.agent_evidence.count_documents({}) == 0
    journal = await db.agent_journal.find({"owner_id": gate.OWNER, "goal_id": goal["id"],
        "kind": "planning_protocol_invalid"}, {"_id": 0}).sort("at", 1).to_list(10)
    assert all(set(row["detail"]) == {"run_id", "attempt", "validation_errors"} for row in journal)
    assert all(re.fullmatch(r"run_[0-9a-f]{16}", row["detail"]["run_id"]) for row in journal)
    assert len({row["detail"]["run_id"] for row in journal}) == MAX_PLANNING_ATTEMPTS
    assert [{key: value for key, value in row["detail"].items() if key != "run_id"} for row in journal] == [
        {"attempt": attempt, "validation_errors": [ERROR]}
        for attempt in range(1, MAX_PLANNING_ATTEMPTS + 1)
    ]
    observed = gate.model_observations(probe)
    assert [row["attempt"] for row in observed["planning_observations"]] == list(range(1, MAX_PLANNING_ATTEMPTS + 1))
    assert observed["planning_observations"][-1]["has_due"] is False
    assert observed["planning_observations_omitted"] == 0
    state = await gate.failure_state(probe)
    assert state["goals"][0]["planning_error"] == observed["planning_observations"][-1]
    assert SECRET not in json.dumps([journal, observed, state], default=str)
    assert probe.model_attempts == probe.model_http_requests == probe.blocked_effects == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["completed", "cancelled", "memory_revoked"])
async def test_retry_never_reopens_closed_or_revoked_work(monkeypatch, change):
    calls = malformed_plans(monkeypatch, 100)
    original_fire = gate.fire_due
    changed = []

    async def fire(db, goal_id, probe):
        current = await original_fire(db, goal_id, probe)
        if not changed:
            changed.append(True)
            if change == "memory_revoked":
                await gate.change_memory(db, goal_id)
            elif change == "cancelled":
                await AgentService(db).cancel(gate.OWNER, goal_id)
            else:
                await db.agent_goals.update_one({"owner_id": gate.OWNER, "id": goal_id},
                    {"$set": {"status": "completed", "next_run_at": None}})
            current = await db.agent_goals.find_one({"owner_id": gate.OWNER, "id": goal_id})
        return current

    monkeypatch.setattr(gate, "fire_due", fire)
    probe = gate.Probe()
    with pytest.raises(gate.EvaluationFailure):
        await gate.run_case("completed_result", probe=probe)
    goal = await probe.database.agent_goals.find_one({"owner_id": gate.OWNER})
    assert len(calls) == 1
    assert goal["status"] == ("abandoned" if change == "memory_revoked" else change)
    assert goal["next_run_at"] is None and not goal["prepared_text"]
    assert await probe.database.agent_goals.count_documents({}) == 1
    assert await probe.database.agent_plans.count_documents({}) == 0
    assert probe.steps == [] and probe.model_attempts == probe.model_http_requests == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {"status": "waiting"}, {"requires_user_input": True}, {"requires_user_authority": True},
    {"user_deferred_until": "2099-01-01T00:00:00+00:00"},
])
async def test_planning_retry_does_not_accelerate_a_new_decision(monkeypatch, change):
    calls = malformed_plans(monkeypatch, 100)
    original_fire = gate.fire_due
    snapshots = []

    async def fire(db, goal_id, probe):
        assert not snapshots, "A new decision cannot be accelerated as a planning retry"
        await original_fire(db, goal_id, probe)
        await db.agent_goals.update_one({"owner_id": gate.OWNER, "id": goal_id}, {"$set": change})
        current = await db.agent_goals.find_one({"owner_id": gate.OWNER, "id": goal_id})
        snapshots.append(deepcopy(current))
        return current

    monkeypatch.setattr(gate, "fire_due", fire)
    probe = gate.Probe()
    with pytest.raises(gate.EvaluationFailure):
        await gate.run_case("completed_result", probe=probe)
    after = await probe.database.agent_goals.find_one({"owner_id": gate.OWNER})
    assert after == snapshots[0] and len(calls) == 1


@pytest.mark.asyncio
async def test_missing_synthetic_guard_does_not_read_or_expedite_work(monkeypatch):
    db = AsyncMongoMockClient().v162_planning_unmarked
    probe = gate.Probe(database=db)
    await db.agent_goals.insert_one({"id": "private-goal", "owner_id": gate.OWNER,
        "status": "active", "planning_unavailable": True, "planning_attempts": 1,
        "next_run_at": "2099-01-01T00:00:00+00:00"})
    before = await db.agent_goals.find_one({"id": "private-goal"})
    with pytest.raises(gate.EvaluationFailure, match="SYNTHETIC_CLOCK_GUARD_MISSING"):
        await gate.first_read(db, "private-goal", probe)
    assert await db.agent_goals.find_one({"id": "private-goal"}) == before
    assert (await gate.failure_state(probe))["available"] is False


@pytest.mark.asyncio
async def test_optional_journal_read_failure_does_not_change_the_retry_or_first_read(monkeypatch):
    calls = malformed_plans(monkeypatch, 1)
    db = AsyncMongoMockClient().v162_planning_diagnostic_unavailable
    unavailable = AsyncMock(side_effect=RuntimeError(SECRET))
    collection = type(db.agent_journal)
    original_find = collection.find_one

    async def find_one(self, *args, **kwargs):
        if self.name == "agent_journal":
            return await unavailable(*args, **kwargs)
        return await original_find(self, *args, **kwargs)

    monkeypatch.setattr(collection, "find_one", find_one)
    original_fire = gate.fire_due
    observed = []

    async def fire(db, goal_id, probe):
        current = await original_fire(db, goal_id, probe)
        state = await gate.failure_state(probe)
        assert state["available"] and "planning_error" not in state["goals"][0]
        observed.append(state)
        return current

    monkeypatch.setattr(gate, "fire_due", fire)
    with gate.isolated_engine(db, probe=gate.Probe(database=db)) as probe:
        await gate.seed_case(db, "completed_result")
        goal_id = await gate.admit(db, "completed_result", probe)
        await gate.first_read(db, goal_id, probe)
    assert len(calls) == len(observed) == 2
    assert unavailable.await_count >= 2
    assert probe.planning_observations == [] and probe.planning_observations_omitted == 0
    assert await db.agent_evidence.count_documents({"owner_id": gate.OWNER, "goal_id": goal_id,
        "provenance.capability": "information.read"}) == 1
    assert SECRET not in json.dumps(observed)


@pytest.mark.asyncio
async def test_planning_observation_retention_is_bounded_without_affecting_current_attempt(monkeypatch):
    malformed_plans(monkeypatch, 1)
    db = AsyncMongoMockClient().v162_planning_diagnostic_retention
    with gate.isolated_engine(db) as probe:
        await gate.seed_case(db, "completed_result")
        goal_id = await gate.admit(db, "completed_result", probe)
        # Retention pressure only; this does not add or reset worker attempts.
        history = [{"attempt": 1, "has_due": True, "validation_errors": [deepcopy(ERROR)]}
                   for _ in range(gate.MAX_DIAGNOSTIC_PLANNING)]
        probe.planning_observations = deepcopy(history)
        current = await gate.fire_due(db, goal_id, probe)
    assert current["planning_attempts"] == 1 and current["next_run_at"]
    assert probe.planning_observations == history and probe.planning_observations_omitted == 1
    assert await db.agent_evidence.count_documents({}) == 0


@pytest.mark.asyncio
async def test_planning_diagnostic_requires_current_owned_guarded_unexpired_journal():
    db = AsyncMongoMockClient().v162_planning_diagnostic_privacy
    await db.eval_guards.insert_one({"_id": gate.VERSION, "owner": gate.OWNER})
    now = datetime.now(timezone.utc)
    goal = {"id": "synthetic-goal", "owner_id": gate.OWNER, "planning_attempts": 1,
        "planning_unavailable": True, "next_run_at": now.isoformat()}
    base = {"owner_id": gate.OWNER, "goal_id": goal["id"], "kind": "planning_protocol_invalid",
        "at": now.isoformat(), "expires_at": now + timedelta(hours=1),
        "detail": {"run_id": RUN_ID, "attempt": 1, "validation_errors": [{**ERROR, "raw": SECRET}]}}
    await db.agent_journal.insert_many([
        {**deepcopy(base), "owner_id": "foreign"},
        {**deepcopy(base), "goal_id": "another-goal"},
        {**deepcopy(base), "detail": {"run_id": RUN_ID, "attempt": 2, "validation_errors": [ERROR]}},
        {**deepcopy(base), "expires_at": now - timedelta(seconds=1)},
    ])
    binding = (goal["id"], RUN_ID)
    assert await gate._planning_error(db, goal, observed_run=binding) is None
    await db.agent_journal.insert_one(deepcopy(base))
    assert await gate._planning_error(db, goal, observed_run=binding) == {
        "attempt": 1, "has_due": True, "validation_errors": [ERROR],
    }
    assert await gate._planning_error(db, goal) is None  # No inferred binding for legacy/restarted probes.
    assert await gate._planning_error(db, goal, observed_run=(goal["id"], "run_fedcba9876543210")) is None
    assert await gate._planning_error(db, {**goal, "owner_id": "foreign"}, observed_run=binding) is None
    assert await gate._planning_error(db, {**goal, "planning_unavailable": False}, observed_run=binding) is None
    await db.eval_guards.delete_many({})
    assert await gate._planning_error(db, goal, observed_run=binding) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [
    {**ERROR, "index": True}, {**ERROR, "index": 12},
    {**ERROR, "field": SECRET}, {**ERROR, "issue": SECRET},
])
async def test_planning_diagnostic_does_not_export_arbitrary_names_or_invalid_indexes(error):
    db = AsyncMongoMockClient().v162_planning_diagnostic_allowlist
    await db.eval_guards.insert_one({"_id": gate.VERSION, "owner": gate.OWNER})
    goal = {"id": "synthetic-goal", "owner_id": gate.OWNER, "planning_attempts": 1,
        "planning_unavailable": True, "next_run_at": None}
    await db.agent_journal.insert_one({"owner_id": gate.OWNER, "goal_id": goal["id"],
        "kind": "planning_protocol_invalid", "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        "detail": {"run_id": RUN_ID, "attempt": 1, "validation_errors": [error]}})
    assert await gate._planning_error(db, goal, observed_run=(goal["id"], RUN_ID)) is None


@pytest.mark.parametrize("verified", [True, False])
def test_quote_diagnostics_preserve_rejected_passages_with_bounds_redaction_and_no_mutation(monkeypatch, verified):
    secret = "abcdefgh"
    monkeypatch.setenv("GEMINI_API_KEY_2", secret)
    # Redaction expands these strings past the bounds even though the raw
    # versions fit. False passages stay visible as observations, not proof.
    quote = (secret + " ") * 30
    ref = (secret + " ") * 17
    item = {"claim": "Synthetic claim", "support": "stated", "evidence_ids": ["ev_synthetic"],
        "source_quotes": [
            {"evidence_id": ref, "quote": quote, "raw": SECRET},
            {"evidence_id": "ev_synthetic", "quote": "This passage was not in the source."},
            {"evidence_id": {"raw": SECRET}, "quote": [SECRET]},
            {"evidence_id": "ev_omitted", "quote": "Omitted passage"},
        ]}
    response = {"verified": verified, "claim_review": [deepcopy(item) for _ in range(13)]}
    original = deepcopy(response)
    observed = gate._decision_result("preparation_audit", response)
    assert observed["verified"] is verified and response == original
    assert observed["claim_review_count"] == 13 and observed["claim_review_omitted"] == 1
    assert len(observed["claim_review"]) == 12
    for claim in observed["claim_review"]:
        assert claim["source_quotes_count"] == 4 and claim["source_quotes_omitted"] == 1
        assert len(claim["source_quotes"]) == 3
        first, second, malformed = claim["source_quotes"]
        assert len(first["evidence_id"]) == 160 and first["evidence_id_truncated"] is True
        assert first["evidence_id_characters"] == len(ref)
        assert len(first["quote"]) == 280 and first["quote_truncated"] is True
        assert first["quote_characters"] == len(quote)
        assert second["quote"] == "This passage was not in the source." and not second["quote_truncated"]
        assert malformed == {"response_kind": "object"}
        assert "raw" not in first
    assert secret not in json.dumps(observed) and SECRET not in json.dumps(observed)
