"""Real internal admission/discovery with structured stubs and zero provider I/O."""
import asyncio
from copy import deepcopy
import json

import pytest
from mongomock.collection import Collection
from mongomock_motor import AsyncMongoMockClient

from agent import reasoning as agent_reasoning
from opportunities import reasoning as opportunity_reasoning
from opportunities.models import ScanResult
from opportunities.service import OpportunityService
from scripts import autonomy_completion_eval_v162 as gate


@pytest.fixture(autouse=True)
def no_model_credentials(monkeypatch):
    for key in gate.LLM_KEYS:
        monkeypatch.delenv(key, raising=False)


def install_admission_answers(monkeypatch, answers):
    calls = []

    async def answer(system, user):
        calls.append(json.loads(user))
        return deepcopy(answers[min(len(calls) - 1, len(answers) - 1)])

    monkeypatch.setattr(agent_reasoning, "_ask_model", answer)
    return calls


def invalid_goal():
    value = deepcopy(gate.baseline.scripted_goal())
    del value["desired_outcome"]
    value["outcome_assessment"] = {"desired_outcome": "This is not the required goal field."}
    return value


@pytest.mark.asyncio
@pytest.mark.parametrize("unavailable_attempts", [0, 1, 2])
async def test_admission_uses_only_existing_retries_and_keeps_first_success_unchanged(
    monkeypatch, unavailable_attempts,
):
    calls = install_admission_answers(monkeypatch, [invalid_goal()] * unavailable_attempts
                                      + [gate.baseline.scripted_goal()])
    db = AsyncMongoMockClient().v162_admission_recovery
    with gate.isolated_engine(db, mode="live") as probe:
        source_id = await gate.seed_case(db, "completed_result")
        await db.opportunities.update_one({"id": source_id}, {"$set": {
            "agent_review_answers": ["Synthetic answer must survive unchanged."],
        }})
        before = await db.opportunities.find_one({"id": source_id})
        goal_id = await gate.admit(db, "completed_result", probe)
        after = await db.opportunities.find_one({"id": source_id})

    assert len(calls) == unavailable_attempts + 1
    assert after["agent_review_attempts"] == unavailable_attempts + 1
    assert after["agent_review_state"] == "settled" and after["agent_review_outcome"] == "create_goal"
    assert after["agent_review_invalid_fields"] == []
    assert after["agent_review_revision"] == before["agent_review_revision"]
    for key in ("semantic_summary", "evidence", "agent_review_answers", "agent_review_fingerprint"):
        assert after[key] == before[key]
    assert await db.agent_goals.count_documents({"owner_id": gate.OWNER, "id": goal_id}) == 1
    assert await db.ambient_wakes.count_documents({
        "owner_id": gate.OWNER, "source_ref": "goal:" + goal_id, "status": "pending",
    }) == 1
    observations = probe.admission_observations
    assert [row["attempts"] for row in observations] == list(range(1, unavailable_attempts + 2))
    assert all(row["state"] == "pending" and row["outcome"] == "unavailable"
               and row["has_due"] and row["error_kind"] == "invalid_goal_decision"
               and row["invalid_fields"] == ["desired_outcome"] for row in observations[:-1])
    assert observations[-1]["state"] == "settled" and observations[-1]["invalid_fields"] == []
    assert probe.model_attempts == probe.model_http_requests == 0


@pytest.mark.asyncio
async def test_exhausted_admission_is_failure_with_persisted_reason_and_no_reset(monkeypatch):
    calls = install_admission_answers(monkeypatch, [invalid_goal()])
    db = AsyncMongoMockClient().v162_admission_exhausted
    probe = gate.Probe(database=db)
    with gate.isolated_engine(db, mode="live", probe=probe):
        source_id = await gate.seed_case(db, "completed_result")
        with pytest.raises(gate.EvaluationFailure, match="ADMISSION_RETRIES_EXHAUSTED"):
            await gate.admit(db, "completed_result", probe)
    source = await db.opportunities.find_one({"id": source_id})
    assert len(calls) == source["agent_review_attempts"] == 3
    assert source["agent_review_state"] == "paused" and source["agent_review_due"] is None
    assert await db.agent_goals.count_documents({}) == await db.ambient_wakes.count_documents({}) == 0
    state = await gate.failure_state(probe)
    assert state["admission_sources_count"] == 1
    assert state["admission_sources"][0]["invalid_fields"] == ["desired_outcome"]
    assert state["admission_sources"][0]["attempts"] == 3
    assert not state["admission_sources"][0]["has_due"]


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["no_goal", "wait", "clarify"])
@pytest.mark.parametrize("retry_first", [False, True])
async def test_decline_question_and_model_wait_are_never_accelerated(monkeypatch, outcome, retry_first):
    calls = install_admission_answers(monkeypatch, ([invalid_goal()] if retry_first else []) + [{
        "outcome": outcome, "reasoning": "Synthetic legitimate decision.",
        "question": "Which personal outcome remains?",
    }])
    db = AsyncMongoMockClient().v162_admission_nonretry
    with gate.isolated_engine(db, mode="live") as probe:
        await gate.seed_case(db, "completed_result")
        with pytest.raises(gate.EvaluationFailure, match="ONE_ACTIVE_GOAL_REQUIRED"):
            await gate.admit(db, "completed_result", probe)
    source = await db.opportunities.find_one({"owner_id": gate.OWNER})
    assert len(calls) == source["agent_review_attempts"] == len(probe.admission_observations) == 1 + retry_first
    assert source["agent_review_outcome"] == outcome
    if outcome == "wait":
        from datetime import datetime, timezone
        assert (datetime.fromisoformat(source["agent_review_due"]) - datetime.now(timezone.utc)).total_seconds() > 3500
    assert not any(row.get("source_ref", "").startswith("goal:")
                   for row in await db.ambient_wakes.find({}).to_list(10))


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_due", [None, "not-a-date"])
async def test_harness_does_not_repair_erased_or_invalid_retry_due(monkeypatch, bad_due):
    from agent import admission
    calls = install_admission_answers(monkeypatch, [invalid_goal()])
    original = admission.drain

    async def lose_due(db, **kwargs):
        result = await original(db, **kwargs)
        await db.opportunities.update_one({"owner_id": gate.OWNER}, {"$set": {"agent_review_due": bad_due}})
        return result

    monkeypatch.setattr(admission, "drain", lose_due)
    db = AsyncMongoMockClient().v162_missing_admission_due
    with gate.isolated_engine(db, mode="live") as probe:
        await gate.seed_case(db, "completed_result")
        with pytest.raises(gate.EvaluationFailure, match="DURABLE_ADMISSION_RETRY_MISSING"):
            await gate.admit(db, "completed_result", probe)
    source = await db.opportunities.find_one({"owner_id": gate.OWNER})
    assert len(calls) == source["agent_review_attempts"] == 1 and source["agent_review_due"] == bad_due


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_field", ["owner_id", "agent_review_revision"])
async def test_retry_clock_update_is_atomic_for_owner_source_and_revision(monkeypatch, changed_field):
    calls = install_admission_answers(monkeypatch, [invalid_goal(), gate.baseline.scripted_goal()])
    original = Collection.update_one
    observed_updates = []

    def change_source_before_clock_write(self, query, update, *args, **kwargs):
        if self.name == "opportunities" and set(update.get("$set", {})) == {"agent_review_due"}:
            observed_updates.append((deepcopy(query), deepcopy(update)))
            original(self, {"id": query["id"]}, {"$set": {changed_field: "changed-synthetic-value"}})
        return original(self, query, update, *args, **kwargs)

    monkeypatch.setattr(Collection, "update_one", change_source_before_clock_write)
    db = AsyncMongoMockClient().v162_admission_revision_race
    with gate.isolated_engine(db, mode="live") as probe:
        source_id = await gate.seed_case(db, "completed_result")
        before = await db.opportunities.find_one({"id": source_id})
        with pytest.raises(gate.EvaluationFailure, match="ADMISSION_RETRY_SOURCE_CHANGED"):
            await gate.admit(db, "completed_result", probe)
    source = await db.opportunities.find_one({"id": source_id})
    assert len(calls) == len(observed_updates) == source["agent_review_attempts"] == 1
    query, update = observed_updates[0]
    assert query["owner_id"] == gate.OWNER and query["id"] == source_id
    assert query["agent_review_revision"] == before["agent_review_revision"]
    assert source["agent_review_due"] == query["agent_review_due"]
    assert set(update) == {"$set"} and set(update["$set"]) == {"agent_review_due"}
    assert await db.agent_goals.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("guard_owner", [None, "another-synthetic-owner"])
async def test_admission_never_mutates_an_unmarked_database(monkeypatch, guard_owner):
    calls = install_admission_answers(monkeypatch, [gate.baseline.scripted_goal()])
    db = AsyncMongoMockClient().v162_admission_guard
    with gate.isolated_engine(db, mode="live") as probe:
        source_id = await gate.seed_case(db, "completed_result")
        await db.eval_guards.delete_many({})
        if guard_owner:
            await db.eval_guards.insert_one({"_id": gate.VERSION, "owner": guard_owner})
        before = await db.opportunities.find_one({"id": source_id})
        with pytest.raises(gate.EvaluationFailure, match="SYNTHETIC_CLOCK_GUARD_MISSING"):
            await gate.admit(db, "completed_result", probe)
    assert not calls and probe.admission_observations == []
    assert await db.opportunities.find_one({"id": source_id}) == before


@pytest.mark.asyncio
async def test_failure_metadata_is_bounded_redacted_owned_and_read_only(monkeypatch):
    credential = "synthetic-diagnostic-alias-credential"
    monkeypatch.setenv("GEMINI_API_KEY_2", credential)
    db = AsyncMongoMockClient().v162_failure_metadata
    await db.eval_guards.insert_one({"_id": gate.VERSION, "owner": gate.OWNER})
    await db.opportunities.insert_many([
        {"id": "synthetic-source", "owner_id": gate.OWNER, "agent_review_revision": "synthetic-revision",
         "agent_review_state": "pending", "agent_review_outcome": "unavailable", "agent_review_attempts": 2,
         "agent_review_error_kind": "invalid_goal_decision", "agent_review_due": "synthetic-present-due",
         "agent_review_invalid_fields": ["desired_outcome", "desired_outcome", credential, "raw_prompt"],
         "agent_review_reason": "PRIVATE_RAW_REASON_NOT_EXPORTED", "agent_review_answers": [credential]},
        {"id": "FOREIGN_SOURCE_MUST_NOT_BE_EXPORTED", "owner_id": "another-synthetic-owner"},
    ])
    await db.agent_goals.insert_one({
        "owner_id": gate.OWNER, "id": "synthetic-goal", "status": "active",
        "success_criteria": [credential + " " + "x" * 220] * 12,
        "source_refs": [credential] * 12, "prepared_sources": ["ev_synthetic"],
    })
    before = await db.opportunities.find({}).to_list(10)
    state = await gate.failure_state(gate.Probe(database=db))
    assert state["admission_sources_count"] == 1 and len(state["admission_sources"]) == 1
    source = state["admission_sources"][0]
    assert source["attempts"] == 2 and source["has_due"]
    assert source["invalid_fields"] == ["desired_outcome"]
    goal = state["goals"][0]
    assert len(goal["success_criteria"]) == 8 and goal["success_criteria_omitted"] == 4
    assert all(len(item) <= 160 for item in goal["success_criteria"])
    assert goal["prepared_sources"] == ["ev_synthetic"]
    encoded = json.dumps(state)
    assert credential not in encoded and "PRIVATE_RAW" not in encoded and "FOREIGN_SOURCE" not in encoded
    assert await db.opportunities.find({}).to_list(10) == before
    await db.eval_guards.delete_many({})
    assert (await gate.failure_state(gate.Probe(database=db)))["available"] is False


def discovery_proposal():
    return {"outcome_assessment": {"outcome_state": "open", "completion_refs": []},
            "opportunities": [{"identity_key": "synthetic-comparison", "what": "Un confronto manca.",
                               "why_it_matters": "La scelta personale è ancora aperta.",
                               "initiative": "prepare", "evidence_refs": ["mem_synthetic"],
                               "what_i_can_do": "Preparare il confronto."}]}


@pytest.mark.asyncio
async def test_real_discovery_separates_proposal_audit_and_structural_rejection(monkeypatch):
    proposal = discovery_proposal()
    reviewed = deepcopy(proposal)
    reviewed["verified"] = True
    reviewed["outcome_assessment"]["outcome_state"] = "resolved"
    del reviewed["opportunities"][0]["evidence_refs"]
    responses = [proposal, reviewed]
    calls = []

    async def decide(system, user):
        calls.append(json.loads(user))
        return responses[len(calls) - 1]

    monkeypatch.setattr(opportunity_reasoning, "_ask_model", decide)
    db = AsyncMongoMockClient().v162_discovery_audit
    await db.eval_guards.insert_one({"_id": gate.VERSION, "owner": gate.OWNER})
    before = deepcopy(responses)
    with gate.isolated_engine(db, mode="live") as probe:
        result = await OpportunityService(db).scan(gate.OWNER, prepared_snapshot={
            "memories": [{"ref": "mem_synthetic", "statement": "Synthetic open need."}],
        })
    assert len(calls) == 2 and responses == before
    assert result.silence and not result.unavailable and not result.created
    assert result.skipped == [{"reason": "nessun fatto reale a sostegno"}]
    audit = next(row for row in probe.structured_decisions if row["stage"] == "opportunity_audit")
    assert audit["input"]["proposed"]["outcome_assessment"]["outcome_state"] == "open"
    assert audit["input"]["proposed"]["opportunities"][0]["evidence_refs"] == ["mem_synthetic"]
    assert audit["verified"] is True and audit["outcome_assessment"]["outcome_state"] == "resolved"
    assert audit["opportunities"][0]["evidence_refs_kind"] == "none"
    assert probe.discovery_results[0]["skipped"] == result.skipped
    assert probe.model_attempts == probe.model_http_requests == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("verdict", [None, False, True])
async def test_audit_observation_preserves_return_and_redacts_bounded_refs(monkeypatch, verdict):
    credential = "synthetic-audit-alias-credential"
    monkeypatch.setenv("GEMINI_API_KEY_2", credential)
    proposal = discovery_proposal()
    proposal["opportunities"][0]["evidence_refs"] = [credential + "r" * 190] * 12
    proposal["opportunities"][0]["raw_provider_body"] = "PRIVATE_PROVIDER_BODY"
    response = {**deepcopy(proposal), "verified": verdict} if verdict is not None else None
    calls = []

    async def audit(snapshot, proposed):
        assert proposed is proposal
        calls.append(True)
        return response

    async def scan(*args, **kwargs):
        returned = await opportunity_reasoning.audit_proposals({}, proposal)
        assert returned is response
        return ScanResult(silence=True, unavailable=verdict is not True)

    monkeypatch.setattr(opportunity_reasoning, "audit_proposals", audit)
    monkeypatch.setattr(OpportunityService, "scan", scan)
    db = AsyncMongoMockClient().v162_audit_identity
    await db.eval_guards.insert_one({"_id": gate.VERSION, "owner": gate.OWNER})
    with gate.isolated_engine(db, mode="live") as probe:
        await OpportunityService(db).scan(gate.OWNER)
    assert calls == [True]
    observed = probe.structured_decisions[0]
    refs = observed["input"]["proposed"]["opportunities"][0]
    assert len(refs["evidence_refs"]) == 8 and refs["evidence_refs_omitted"] == 4
    assert all(len(ref) <= 160 for ref in refs["evidence_refs"])
    if verdict is None:
        assert observed["response_kind"] == "none" and "verified" not in observed
    else:
        assert observed["verified"] is verdict and observed["verified_kind"] == "boolean"
    encoded = json.dumps(gate.model_observations(probe))
    assert credential not in encoded and "PRIVATE_PROVIDER_BODY" not in encoded
    assert len(proposal["opportunities"][0]["evidence_refs"]) == 12


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [asyncio.CancelledError, RuntimeError])
async def test_audit_and_scan_keep_exception_identity_without_exporting_message(monkeypatch, error_type):
    calls = []
    error = error_type("PRIVATE_EXCEPTION_MESSAGE")

    async def decide(*args, **kwargs):
        calls.append(True)
        if len(calls) == 1:
            return discovery_proposal()
        raise error

    monkeypatch.setattr(opportunity_reasoning, "_ask_model", decide)
    db = AsyncMongoMockClient().v162_discovery_error
    await db.eval_guards.insert_one({"_id": gate.VERSION, "owner": gate.OWNER})
    with gate.isolated_engine(db, mode="live") as probe:
        with pytest.raises(error_type) as caught:
            await OpportunityService(db).scan(gate.OWNER, prepared_snapshot={})
    assert caught.value is error and len(calls) == 2
    audit = next(row for row in probe.structured_decisions if row["stage"] == "opportunity_audit")
    assert audit["response_kind"] == "raised" and audit["exception_type"] == error_type.__name__
    assert probe.discovery_results == [{"response_kind": "raised", "exception_type": error_type.__name__}]
    assert "PRIVATE_EXCEPTION_MESSAGE" not in json.dumps(gate.model_observations(probe))


@pytest.mark.asyncio
@pytest.mark.parametrize("unavailable", [False, True])
async def test_scan_observation_keeps_return_identity_and_bounded_known_skips(monkeypatch, unavailable):
    returned = ScanResult(silence=True, unavailable=unavailable, skipped=[
        {"reason": "PRIVATE_UNKNOWN_REASON"}, {"reason": "nessun fatto reale a sostegno"},
    ] * 9)

    async def scan(*args, **kwargs):
        return returned

    monkeypatch.setattr(OpportunityService, "scan", scan)
    db = AsyncMongoMockClient().v162_scan_identity
    await db.eval_guards.insert_one({"_id": gate.VERSION, "owner": gate.OWNER})
    with gate.isolated_engine(db, mode="live") as probe:
        assert await OpportunityService(db).scan(gate.OWNER) is returned
    observed = probe.discovery_results[0]
    assert observed["silence"] and observed["unavailable"] is unavailable
    assert observed["skipped_count"] == 18 and len(observed["skipped"]) == 8
    assert observed["skipped_omitted"] == 10
    assert observed["skipped"][0]["reason"] == "unrecognized_reason"
    assert observed["skipped"][1]["reason"] == "nessun fatto reale a sostegno"
    assert "PRIVATE_UNKNOWN_REASON" not in json.dumps(gate.model_observations(probe))
    assert returned.skipped[0]["reason"] == "PRIVATE_UNKNOWN_REASON"


@pytest.mark.asyncio
@pytest.mark.parametrize("guard_owner,scan_owner", [
    (None, gate.OWNER), ("another-synthetic-owner", gate.OWNER), (gate.OWNER, "another-synthetic-owner"),
])
async def test_discovery_diagnostics_do_not_export_unmarked_or_foreign_context(monkeypatch, guard_owner, scan_owner):
    proposal = discovery_proposal()
    proposal["opportunities"][0]["what"] = "PRIVATE_FOREIGN_OR_UNMARKED_CONTEXT"
    reviewed = {**proposal, "verified": True}
    replies = iter([proposal, reviewed])

    async def decide(*args, **kwargs):
        return next(replies)

    monkeypatch.setattr(opportunity_reasoning, "_ask_model", decide)
    db = AsyncMongoMockClient().v162_discovery_guard
    if guard_owner:
        await db.eval_guards.insert_one({"_id": gate.VERSION, "owner": guard_owner})
    with gate.isolated_engine(db, mode="live") as probe:
        await OpportunityService(db).scan(scan_owner, prepared_snapshot={})
    assert probe.structured_decisions == probe.discovery_results == []
    assert "PRIVATE_FOREIGN_OR_UNMARKED_CONTEXT" not in json.dumps(gate.model_observations(probe))
