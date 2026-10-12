"""Synthetic execution of local preparation and non-invasive bounded tracing."""
import asyncio
from copy import deepcopy
import json

import httpx
from mongomock_motor import AsyncMongoMockClient
import pytest

from agent import preparation, reasoning
from agent.execution import StepExecutor
from agent.models import ActionPlan, ActionStep, AgentBudget, AgentRun, AutonomousGoal, ExecutionResult
from agent.service import AgentService
from scripts import autonomy_completion_eval_v162 as gate
from scripts.phase1_read_provider_eval import EvaluationBoundaryError


@pytest.fixture(autouse=True)
def no_provider_credentials(monkeypatch):
    for key in gate.LLM_KEYS:
        monkeypatch.delenv(key, raising=False)


async def seed(db, *, marked=True, source=False):
    if marked:
        await db.eval_guards.insert_one({"_id": gate.VERSION, "owner": gate.OWNER})
    goal = AutonomousGoal(
        owner_id=gate.OWNER, status="active", objective="Confrontare le condizioni annotate.",
        desired_outcome="Un confronto scritto con premesse e limiti.",
        source_kind="memory" if source else "", source_refs=["mem_preparation_trace"] if source else [],
    )
    await db.agent_goals.insert_one(goal.model_dump())
    if source:
        await db.memories.insert_one({
            "id": "mem_preparation_trace", "user_id": gate.OWNER, "status": "known", "revision": 1,
            "statement": gate.FIXTURE_NOTE, "authority": "user_stated", "epistemic_status": "known",
            "created_at": "2020-01-01T00:00:00+00:00",
        })
    return goal


def prepare_step(*, capability=""):
    return ActionStep(step_type="prepare", capability_needed=capability,
                      intent="Produrre il confronto basato sulla nota.")


async def read_source(db, goal):
    step = ActionStep(step_type="inspect", capability_needed="information.read",
                      intent="Leggere la nota citata.", input_refs=goal.source_refs)
    result = await StepExecutor(db).run(gate.OWNER, goal, step, may_touch_the_world=False)
    assert result.status == "succeeded" and result.evidence_refs
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["completed_result", "source_change_crash"])
async def test_empty_capability_prepare_finishes_the_real_owned_chain(monkeypatch, scenario):
    original = gate.baseline.scripted_make_plan

    async def plan(*args, **kwargs):
        result = deepcopy(await original(*args, **kwargs))
        for step in result["steps"]:
            if step["step_type"] == "prepare":
                step["capability_needed"] = ""
        return result

    monkeypatch.setattr(gate.baseline, "scripted_make_plan", plan)
    report = await gate.run_case(scenario)
    assert report["passed"] and report["result"]["home_delivered"]
    assert report["result"]["replay_idempotent"] and report["result"]["owner_isolation"]
    assert any(row["capability"] == "" and row["status"] == "succeeded"
               for row in report["executed_capabilities"])
    assert report["model_attempts"] == report["model_http_requests"] == report["external_effects"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("step_type,capability", [
    *[(kind, "") for kind in ("inspect", "research", "compare", "verify", "ask_user", "wait", "execute")],
    ("prepare", " "), ("prepare", "calendar.write"), ("execute", "document.create"),
])
async def test_only_exact_empty_local_prepare_crosses_the_step_guard(monkeypatch, step_type, capability):
    calls = []

    async def unreachable(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("executor must remain outside the boundary")

    monkeypatch.setattr(StepExecutor, "run", unreachable)
    db = AsyncMongoMockClient().preparation_forbidden_step
    goal = await seed(db)
    item = ActionStep(step_type=step_type, capability_needed=capability, intent="Synthetic forbidden step")
    with gate.isolated_engine(db) as probe:
        with pytest.raises(gate.EvaluationFailure, match="STEP_EFFECT_OR_OWNER_BOUNDARY"):
            await StepExecutor(db).run(gate.OWNER, goal, item, may_touch_the_world=True)
    assert calls == [] and probe.blocked_effects == 1
    row, = gate.model_observations(probe)["executed_capabilities"]
    assert row["capability"] == capability and row["step_id"] == item.id and row["step_type"] == step_type
    assert row["error_type"] == "STEP_EFFECT_OR_OWNER_BOUNDARY" and row["retryable"] is False
    assert row["status"] == "blocked" and probe.model_attempts == probe.model_http_requests == 0
    assert await db.agent_action_attempts.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("violation", ["marker_missing", "marker_foreign", "owner", "goal_owner", "database"])
async def test_empty_prepare_requires_exact_owner_database_and_marker(monkeypatch, violation):
    calls = []

    async def unreachable(*args, **kwargs):
        calls.append(True)

    monkeypatch.setattr(StepExecutor, "run", unreachable)
    db = AsyncMongoMockClient().preparation_owner_guard
    goal = await seed(db, marked=violation != "marker_missing")
    if violation == "marker_foreign":
        await db.eval_guards.update_one({"_id": gate.VERSION}, {"$set": {"owner": "foreign-owner"}})
    owner = "foreign-owner" if violation == "owner" else gate.OWNER
    if violation == "goal_owner":
        goal.owner_id = "foreign-owner"
    executor_db = AsyncMongoMockClient().foreign_database if violation == "database" else db
    if violation == "database":
        await executor_db.eval_guards.insert_one({"_id": gate.VERSION, "owner": gate.OWNER})
    item = prepare_step()
    item.id = "private_step_identifier_must_not_export"
    with gate.isolated_engine(db) as probe:
        with pytest.raises(gate.EvaluationFailure, match="STEP_EFFECT_OR_OWNER_BOUNDARY"):
            await StepExecutor(executor_db).run(owner, goal, item, may_touch_the_world=False)
    report = gate.model_observations(probe)
    assert calls == [] and report["structured_decisions"] == []
    assert "private_step_identifier" not in json.dumps(report) and "foreign-owner" not in json.dumps(report)
    assert report["executed_capabilities"][0]["error_type"] == "STEP_EFFECT_OR_OWNER_BOUNDARY"


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome,expected_error,retryable", [
    ("missing_sources", "preparation_sources_required", False),
    ("generation_unavailable", "preparation_model_unavailable", True),
    ("audit_rejected", "preparation_not_supported", True),
    ("audit_string_false", "preparation_not_supported", True),
])
async def test_real_executor_error_and_preparation_decisions_are_preserved(
    monkeypatch, outcome, expected_error, retryable,
):
    calls, responses = [], []

    async def answer(system, user, *, response_schema=None):
        payload = json.loads(user)
        calls.append((system, user, payload))
        if outcome == "generation_unavailable":
            value = None
        elif "draft" in payload:
            value = {"verified": "false" if outcome == "audit_string_false" else False,
                     "content": "Synthetic audit refuses the unsupported clause.",
                     "evidence_ids": [payload["evidence"][0]["id"]],
                     "reason": "A stated consequence lacks a supplied premise.",
                     "claim_review": "malformed review" if outcome == "audit_string_false" else [{
                         "claim": "The draft asserts an unsupported consequence.",
                         "evidence_ids": [], "premises": "The required premise is unknown.",
                         "support": "unsupported", "correction": "Remove the consequence.",
                     }]}
        else:
            value = {"content": gate.baseline.DRAFT, "evidence_ids": [payload["evidence"][0]["id"]]}
        responses.append(value)
        return value

    monkeypatch.setattr(gate.baseline, "scripted_draft", answer)
    db = AsyncMongoMockClient().preparation_error_trace
    goal = await seed(db, source=outcome != "missing_sources")
    with gate.isolated_engine(db) as probe:
        if outcome != "missing_sources":
            await read_source(db, goal)
        item, budget = prepare_step(), AgentBudget()
        result = await StepExecutor(db).run(gate.OWNER, goal, item, may_touch_the_world=False, budget=budget)
    assert result.status == "unavailable" and result.error_type == expected_error and result.retryable is retryable
    assert budget.capability_calls == 1 and budget.cognitive_calls == 2
    row = gate.model_observations(probe)["executed_capabilities"][-1]
    assert row["step_id"] == item.id and row["step_type"] == "prepare" and row["capability"] == ""
    assert row["error_type"] == expected_error and row["retryable"] is retryable
    assert not (await db.agent_goals.find_one({"id": goal.id}))["prepared_text"]
    decisions = probe.structured_decisions
    assert [row["stage"] for row in decisions] == (["preparation_generation", "preparation_audit"]
        if outcome.startswith("audit_") else ["preparation_generation"]
        if outcome == "generation_unavailable" else [])
    assert len(calls) == len(decisions)
    if outcome.startswith("audit_"):
        assert calls[1][2]["draft"] == responses[0]["content"] == decisions[1]["input"]["draft"]
        assert decisions[1]["content"] == responses[1]["content"]
        assert decisions[1]["reason"] == responses[1]["reason"]
        if outcome == "audit_string_false":
            assert decisions[1]["verified_kind"] == "text" and "verified" not in decisions[1]
            assert decisions[1]["claim_review_kind"] == "text" and "claim_review" not in decisions[1]
            assert responses[1]["claim_review"] == "malformed review"
        else:
            assert decisions[1]["verified"] is False
            assert decisions[1]["claim_review"][0]["support"] == "unsupported"
            assert decisions[1]["claim_review"][0]["correction"] == "Remove the consequence."
    assert probe.model_attempts == probe.model_http_requests == 0 and not probe.blocked_effects


@pytest.mark.asyncio
async def test_real_preparation_exports_separate_redacted_generation_and_audit_without_mutating_them(monkeypatch):
    secret = "synthetic-preparation-api-key-alias"
    monkeypatch.setenv("GEMINI_API_KEY_2", secret)
    draft, audited = "Provisional clause " + secret, gate.baseline.DRAFT + " " + secret
    calls, responses = [], []

    async def answer(system, user, *, response_schema=None):
        payload = json.loads(user)
        calls.append((system, user, payload))
        value = {"content": audited if "draft" in payload else draft,
                 "evidence_ids": [payload["evidence"][0]["id"]],
                 "provider_headers": "private-header-must-not-export"}
        if "draft" in payload:
            value["verified"] = True
            value["reason"] = "The corrected comparison follows the synthetic evidence. " + secret
            value["claim_review"] = [{
                "claim": "The 12-month totals are 180 and 120.",
                "evidence_ids": value["evidence_ids"], "premises": "Same 12-month period. " + secret,
                "support": "derived", "correction": "State the source limitation.",
                "source_quotes": [
                    {"evidence_id": value["evidence_ids"][0],
                     "quote": "il piano dell'archivio digitale costa 15 euro mensili; 12 mesi costano 180 euro."},
                    {"evidence_id": value["evidence_ids"][0],
                     "quote": "La seconda opzione indicata nella nota costa 120 euro anticipati per 12 mesi."},
                ],
                "private_unknown_field": "private-claim-field-must-not-export",
            }]
        responses.append(value)
        return value

    monkeypatch.setattr(gate.baseline, "scripted_draft", answer)
    db = AsyncMongoMockClient().preparation_success_trace
    goal = await seed(db, source=True)
    with gate.isolated_engine(db) as probe:
        source = await read_source(db, goal)
        item, budget = prepare_step(), AgentBudget()
        result = await StepExecutor(db).run(gate.OWNER, goal, item, may_touch_the_world=False, budget=budget)
    assert result.status == "succeeded" and goal.prepared_text == audited
    assert (await db.agent_goals.find_one({"id": goal.id}))["prepared_text"] == audited
    assert len(calls) == 2 and calls[1][2]["draft"] == responses[0]["content"] == draft
    assert responses[1]["content"] == audited and responses[1]["verified"] is True
    generated, checked = probe.structured_decisions
    assert generated["stage"] == "preparation_generation" and checked["stage"] == "preparation_audit"
    assert checked["verified"] is True and checked["input"]["draft"] == generated["content"]
    assert generated["content"] != checked["content"] and generated["content_characters"] == len(draft)
    assert checked["claim_review_count"] == 1 and checked["claim_review_omitted"] == 0
    assert checked["claim_review"][0]["support"] == "derived"
    assert checked["claim_review"][0]["evidence_ids"] == source.evidence_refs
    assert secret in responses[1]["claim_review"][0]["premises"] and secret in responses[1]["reason"]
    for row in (generated, checked):
        assert row["input"]["goal_id"] == goal.id and row["input"]["step_id"] == item.id
        assert row["input"]["evidence_count"] == 1 and row["input"]["evidence_ids"] == source.evidence_refs
        assert row["evidence_ids"] == source.evidence_refs and row["content_truncated"] is False
        assert row["model_attempts_before"] == row["model_attempts_after"] == 0
    exported = json.dumps(gate.model_observations(probe))
    assert secret not in exported and "private-header-must-not-export" not in exported
    assert "private-claim-field-must-not-export" not in exported
    assert gate.FIXTURE_NOTE not in exported and "[credential redacted]" in exported
    assert budget.capability_calls == 1 and budget.cognitive_calls == 2
    assert probe.model_attempts == probe.model_http_requests == probe.blocked_effects == probe.push_attempts == 0
    assert not probe.network.blocked and await db.agent_action_attempts.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("violation", ["marker_missing", "goal_owner", "database", "outside_prepare"])
async def test_preparation_trace_does_not_export_unmarked_or_foreign_model_payloads(monkeypatch, violation):
    payload = {"goal": {"private": "foreign-source-text"}, "step": {}, "evidence": []}
    user = json.dumps(payload, indent=3)
    response = {"content": "foreign-generated-content", "evidence_ids": ["foreign-source-id"]}
    calls = []

    async def answer(system, forwarded, *, response_schema=None):
        calls.append((system, forwarded))
        return response

    async def original_prepare(db, owner, goal, item):
        return await reasoning._ask_model("unchanged-system", user)

    monkeypatch.setattr(gate.baseline, "scripted_draft", answer)
    monkeypatch.setattr(preparation, "prepare", original_prepare)
    db = AsyncMongoMockClient().preparation_trace_scope
    goal = await seed(db, marked=violation != "marker_missing")
    if violation == "goal_owner":
        goal.owner_id = "foreign-owner"
    other = AsyncMongoMockClient().foreign_preparation_scope
    with gate.isolated_engine(db) as probe:
        if violation == "outside_prepare":
            returned = await reasoning._ask_model("unchanged-system", user)
        else:
            returned = await preparation.prepare(other if violation == "database" else db,
                                                 gate.OWNER, goal, prepare_step())
    assert returned is response and calls == [("unchanged-system", user)]
    assert probe.structured_decisions == [] and probe.model_attempts == probe.model_http_requests == 0
    assert "foreign" not in json.dumps(gate.model_observations(probe))


@pytest.mark.asyncio
async def test_preparation_observations_are_bounded_redacted_and_return_identity_is_preserved(monkeypatch):
    secret = "abcdefgh"
    monkeypatch.setenv("GEMINI_API_KEY_2", secret)
    content = (secret + " ") * 440  # <4000 originally; redaction expands past the bound.
    user = json.dumps({"draft": "synthetic original draft", "evidence": [{"id": "ev_synthetic"}]}, indent=2)
    refs = ["ev_" + str(i) + "x" * 180 for i in range(10)]
    response = {"content": content, "evidence_ids": refs, "verified": True, "reason": content,
                "claim_review": [{
                    "claim": content, "premises": content, "support": "conditional", "correction": content,
                    "evidence_ids": refs, "unknown": "private-field",
                } for _ in range(15)]}
    original = deepcopy(response)
    calls = []

    async def answer(system, forwarded, *, response_schema=None):
        calls.append((system, forwarded))
        return response

    async def original_prepare(db, owner, goal, item):
        return await reasoning._ask_model("opaque instruction without stage keywords", user)

    monkeypatch.setattr(gate.baseline, "scripted_draft", answer)
    monkeypatch.setattr(preparation, "prepare", original_prepare)
    db = AsyncMongoMockClient().preparation_trace_bounds
    goal = await seed(db)
    with gate.isolated_engine(db) as probe:
        for _ in range(15):
            assert await preparation.prepare(db, gate.OWNER, goal, prepare_step()) is response
    assert response == original and len(calls) == 15
    assert all(call == ("opaque instruction without stage keywords", user) for call in calls)
    assert len(probe.structured_decisions) == 12 and probe.structured_decisions_omitted == 3
    assert [row["sequence"] for row in probe.structured_decisions] == [1, 2] + list(range(6, 16))
    for row in probe.structured_decisions:
        assert row["stage"] == "preparation_audit" and row["content_characters"] == len(content)
        assert len(row["content"]) == 4000 and row["content_truncated"] is True
        assert len(row["reason"]) == 400 and row["verified"] is True
        assert len(row["evidence_ids"]) == 8 and row["evidence_ids_count"] == 10 and row["evidence_ids_omitted"] == 2
        assert all(len(ref) == 160 for ref in row["evidence_ids"])
        assert len(row["claim_review"]) == 12 and row["claim_review_count"] == 15 and row["claim_review_omitted"] == 3
        for check in row["claim_review"]:
            assert len(check["claim"]) == len(check["premises"]) == len(check["correction"]) == 280
            assert check["support"] == "conditional" and len(check["evidence_ids"]) == 8
            assert all(len(ref) == 160 for ref in check["evidence_ids"])
            assert "unknown" not in check
    assert secret not in json.dumps(gate.model_observations(probe))
    assert probe.model_attempts == probe.model_http_requests == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [5, 12])
async def test_late_reconsideration_keeps_latest_preparation_stages_without_pairing_them(monkeypatch, limit):
    """Real scoped wrappers with fake replies; retention never changes execution."""
    monkeypatch.setattr(gate, "MAX_DECISION_OBSERVATIONS", limit)
    secret = "synthetic-retention-api-key"
    monkeypatch.setenv("GEMINI_API_KEY_2", secret)
    generated = {"content": "Provisional draft " + secret, "evidence_ids": ["ev_synthetic"]}
    audited = {"content": "Corrected draft " + secret, "evidence_ids": ["ev_synthetic"],
               "verified": True, "reason": "Synthetic correction " + secret}
    verified = {"outcome": "partially_achieved", "reasoning": "A supplied premise remains unclear."}
    reconsidered = {"decision": "modify", "reasoning": "Revisit the unsupported clause.", "revised_steps": []}
    originals = deepcopy((generated, audited, verified, reconsidered))
    calls = []
    first_step, later_step = prepare_step(), prepare_step()

    async def answer(system, user, **kwargs):
        payload = json.loads(user)
        stage = "audit" if "draft" in payload else "generation"
        calls.append(stage)
        assert system == "opaque synthetic instruction"
        assert payload["evidence"] == [{"id": "ev_synthetic"}]
        return audited if stage == "audit" else generated

    async def original_prepare(db, owner, goal, item):
        payload = {"goal": goal.for_ai(), "step": item.for_ai(), "evidence": [{"id": "ev_synthetic"}]}
        result = await reasoning._ask_model("opaque synthetic instruction", json.dumps(payload))
        assert result is generated
        if item.id == first_step.id:
            return await reasoning._ask_model("opaque synthetic instruction", json.dumps({
                "draft": result["content"], "evidence": payload["evidence"],
            }))
        return result  # A newer generation does not imply that a newer audit exists.

    async def original_verify(*args, **kwargs):
        calls.append("verify")
        return verified

    async def original_reconsider(*args, **kwargs):
        calls.append("reconsider")
        return reconsidered

    async def original_service(self, owner, goal):
        return await reasoning.reconsider(goal.for_ai(), plan={}, what_happened={}, capabilities=[])

    monkeypatch.setattr(gate.baseline, "scripted_draft", answer)
    monkeypatch.setattr(gate.baseline, "scripted_verify", original_verify)
    monkeypatch.setattr(preparation, "prepare", original_prepare)
    monkeypatch.setattr(reasoning, "reconsider", original_reconsider)
    monkeypatch.setattr(AgentService, "_reconsider", original_service)
    db = AsyncMongoMockClient().preparation_trace_retention
    goal = await seed(db)
    with gate.isolated_engine(db) as probe:
        for _ in range(2):
            assert await reasoning.verify_goal(goal.for_ai(), evidence={}) is verified
        assert await preparation.prepare(db, gate.OWNER, goal, first_step) is audited
        for _ in range(7):
            assert await reasoning.verify_goal(goal.for_ai(), evidence={}) is verified
            assert await AgentService(db)._reconsider(gate.OWNER, goal) is reconsidered
        assert len(probe.structured_decisions) == limit
        assert probe.structured_decisions_omitted == 18 - limit
        assert [row["sequence"] for row in probe.structured_decisions] == [1, 2, 3, 4] + list(range(23 - limit, 19))

        assert await preparation.prepare(db, gate.OWNER, goal, later_step) is generated
        for _ in range(7):
            assert await reasoning.verify_goal(goal.for_ai(), evidence={}) is verified
            assert await AgentService(db)._reconsider(gate.OWNER, goal) is reconsidered
    assert calls == ["verify", "verify", "generation", "audit"] + ["verify", "reconsider"] * 7 + [
        "generation"] + ["verify", "reconsider"] * 7
    assert (generated, audited, verified, reconsidered) == originals
    assert len(probe.structured_decisions) == limit and probe.structured_decisions_omitted == 33 - limit
    assert [row["sequence"] for row in probe.structured_decisions] == [1, 2, 4, 19] + list(range(38 - limit, 34))
    latest_generation, = [row for row in probe.structured_decisions if row["stage"] == "preparation_generation"]
    latest_audit, = [row for row in probe.structured_decisions if row["stage"] == "preparation_audit"]
    assert latest_generation["input"]["step_id"] == later_step.id
    assert latest_audit["input"]["step_id"] == first_step.id
    assert latest_generation["input"]["goal_id"] == latest_audit["input"]["goal_id"] == goal.id
    assert probe.structured_decisions[-1]["stage"] == "reconsider"
    assert secret not in json.dumps(gate.model_observations(probe))
    assert all(row["model_attempts_before"] == row["model_attempts_after"] == 0 for row in probe.structured_decisions)
    assert probe.model_attempts == probe.model_http_requests == probe.blocked_effects == probe.push_attempts == 0
    assert not probe.network.blocked and await db.agent_action_attempts.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("exception", [RuntimeError("private-provider-error"), asyncio.CancelledError("private-cancel")])
async def test_preparation_rethrows_same_exception_and_clears_context(monkeypatch, exception):
    user = json.dumps({"draft": "synthetic draft", "evidence": []})
    calls = []

    async def answer(system, payload, *, response_schema=None):
        calls.append((system, payload))
        if len(calls) == 1:
            raise exception
        return {"content": "outside-preparation-content"}

    async def original_prepare(db, owner, goal, item):
        return await reasoning._ask_model("opaque-system", user)

    monkeypatch.setattr(gate.baseline, "scripted_draft", answer)
    monkeypatch.setattr(preparation, "prepare", original_prepare)
    db = AsyncMongoMockClient().preparation_trace_cancellation
    goal = await seed(db)
    with gate.isolated_engine(db) as probe:
        with pytest.raises(type(exception)) as caught:
            await StepExecutor(db).run(gate.OWNER, goal, prepare_step(), may_touch_the_world=False)
        assert caught.value is exception
        await reasoning._ask_model("outside-system", user)
    decision, = probe.structured_decisions
    assert decision["stage"] == "preparation_audit" and decision["response_kind"] == "raised"
    assert decision["exception_type"] == type(exception).__name__
    row, = probe.steps
    assert row["status"] == "raised" and row["error_type"] == type(exception).__name__
    exported = json.dumps(gate.model_observations(probe))
    assert "private-provider-error" not in exported and "private-cancel" not in exported
    assert "outside-preparation-content" not in exported and len(calls) == 2


@pytest.mark.asyncio
async def test_local_prepare_keeps_http_blocked_before_transport(monkeypatch):
    transported = []

    def transport(request):
        transported.append(request)
        return httpx.Response(200)

    async def original_prepare(db, owner, goal, item):
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport), trust_env=False) as client:
            await client.get("https://example.invalid/forbidden")

    monkeypatch.setattr(preparation, "prepare", original_prepare)
    db = AsyncMongoMockClient().preparation_http_boundary
    goal = await seed(db)
    with gate.isolated_engine(db) as probe:
        with pytest.raises(EvaluationBoundaryError, match="EVAL_HTTP_NOT_ALLOWLISTED"):
            await StepExecutor(db).run(gate.OWNER, goal, prepare_step(), may_touch_the_world=False)
    assert transported == [] and probe.network.blocked == ["EVAL_HTTP_NOT_ALLOWLISTED"]
    assert probe.steps[0]["error_type"] == "EvaluationBoundaryError" and probe.model_http_requests == 0


@pytest.mark.asyncio
async def test_failed_cli_report_retains_executor_error_and_rejected_audit(monkeypatch, tmp_path, capsys):
    original = gate.baseline.scripted_draft

    async def reject_audit(system, user, *, response_schema=None):
        payload = json.loads(user)
        if "draft" in payload:
            return {"verified": False, "content": "Synthetic unsupported clause was rejected.",
                    "evidence_ids": [payload["evidence"][0]["id"]]}
        return await original(system, user)

    monkeypatch.setattr(gate.baseline, "scripted_draft", reject_audit)
    output = tmp_path / "rejected-preparation.json"
    assert await gate.main(scenario="completed_result", output=str(output)) == 1
    report = json.loads(output.read_text())
    case, = report["cases"]
    assert not case["passed"] and case["failure_state"]["available"]
    assert any(row["error_type"] == "preparation_not_supported" and row["retryable"] is True
               for row in case["executed_capabilities"])
    assert any(row["stage"] == "preparation_audit" and row["verified"] is False
               and row["content"] == "Synthetic unsupported clause was rejected."
               for row in case["structured_decisions"])
    assert case["model_attempts"] == case["model_http_requests"] == 0
    assert report["limits"]["preparation_text_characters"] == 4000
    assert report["limits"]["preparation_claims_per_audit"] == 12
    assert report["limits"]["preparation_claim_text_characters"] == 280
    assert report["limits"]["executor_observations_per_case"] == 12
    capsys.readouterr()


@pytest.mark.asyncio
async def test_unmarked_unit_executor_trace_retains_legacy_minimal_shape(monkeypatch):
    returned = ExecutionResult(status="unavailable", error_type="private_error_kind", retryable=True,
                               observation="private observation must not export")

    async def original_run(*args, **kwargs):
        return returned

    monkeypatch.setattr(StepExecutor, "run", original_run)
    db = AsyncMongoMockClient().preparation_legacy_unit_trace
    goal = await seed(db, marked=False)
    with gate.isolated_engine(db) as probe:
        result = await StepExecutor(db).run(gate.OWNER, goal, prepare_step(capability="document.create"),
                                           may_touch_the_world=False)
    assert result is returned and probe.steps == [{"capability": "document.create", "status": "unavailable"}]
    assert "private" not in json.dumps(gate.model_observations(probe))


@pytest.mark.asyncio
async def test_rejected_real_audit_records_the_actual_reconsidered_wait(monkeypatch):
    calls = []
    decision = {"decision": "wait", "reasoning": "Synthetic decision to await a changed premise.",
                "wait_minutes": 17, "wait_until": None,
                "requires_user_input": False, "requires_user_authority": False}
    original_decision = deepcopy(decision)

    async def answer(system, user, *, response_schema=None):
        payload = json.loads(user)
        calls.append(payload)
        if "what_happened" in payload:
            return decision
        if "draft" in payload:
            return {"verified": False, "content": "", "evidence_ids": [],
                    "reason": "An unsupported consequence was rejected."}
        return {"content": gate.baseline.DRAFT, "evidence_ids": [payload["evidence"][0]["id"]]}

    monkeypatch.setattr(gate.baseline, "scripted_draft", answer)
    db = AsyncMongoMockClient().preparation_reconsider_wait
    goal = await seed(db, source=True)
    with gate.isolated_engine(db) as probe:
        await read_source(db, goal)
        item, budget = prepare_step(capability="document.create"), AgentBudget()
        plan = ActionPlan(owner_id=gate.OWNER, goal_id=goal.id, steps=[item], status="active")
        service = AgentService(db)
        await service.repo.save_plan(plan)
        result = await service._do_step(gate.OWNER, goal, plan, item,
            AgentRun(owner_id=gate.OWNER, goal_id=goal.id), budget, language="it")
    assert result["state"] == "waiting" and goal.status == plan.status == "waiting"
    assert goal.next_run_at and not goal.prepared_text and item.status == "failed"
    assert len(calls) == 3 and budget.cognitive_calls == 3 and budget.capability_calls == 1
    assert decision == original_decision  # Observation does not add or rewrite decision fields.
    assert [row["stage"] for row in probe.structured_decisions] == [
        "preparation_generation", "preparation_audit", "reconsider",
    ]
    audit, rethink = probe.structured_decisions[-2:]
    assert audit["verified"] is False
    assert rethink["input"]["what_happened"] == {
        "step_id": item.id, "step_type": "prepare", "status": "unavailable",
        "error_type": "preparation_not_supported", "retryable": True,
    }
    assert calls[-1]["what_happened"]["result"]["problem"] == "preparation_not_supported"
    assert rethink["decision"] == "wait" and rethink["reasoning"] == decision["reasoning"]
    assert rethink["wait_minutes"] == 17 and rethink["wait_minutes_kind"] == "integer"
    assert rethink["wait_until_kind"] == "none" and "wait_until" not in rethink
    assert rethink["requires_user_input"] is False and rethink["requires_user_authority"] is False
    assert "Non ho ancora prodotto una bozza verificabile." not in json.dumps(rethink)
    assert all(row["model_attempts_before"] == row["model_attempts_after"] == 0
               for row in probe.structured_decisions)
    assert probe.model_attempts == probe.model_http_requests == probe.blocked_effects == probe.push_attempts == 0
    assert not probe.network.blocked and await db.agent_action_attempts.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["unmarked", "owner", "goal_owner", "database", "marker_removed", "outside_service"])
async def test_reconsider_observation_requires_the_owned_marked_service_scope(monkeypatch, scope):
    calls = []
    response = {"decision": "wait", "reasoning": "private-reconsideration-reason", "wait_minutes": 19}
    kwargs = {"plan": {}, "what_happened": {"result": {
        "status": "unavailable", "problem": "private_problem", "what_happened": "private free observation",
    }}, "capabilities": []}

    async def original_reconsider(goal, **forwarded):
        calls.append((goal, forwarded))
        return response

    async def original_service(self, owner, goal):
        if scope == "marker_removed":
            await self.db.eval_guards.delete_many({})
        return await reasoning.reconsider(goal.for_ai(), **kwargs)

    monkeypatch.setattr(reasoning, "reconsider", original_reconsider)
    monkeypatch.setattr(AgentService, "_reconsider", original_service)
    db = AsyncMongoMockClient().reconsider_owner_boundary
    goal = await seed(db, marked=scope != "unmarked")
    if scope == "goal_owner":
        goal.owner_id = "foreign-owner"
    owner = "foreign-owner" if scope == "owner" else gate.OWNER
    other = AsyncMongoMockClient().foreign_reconsider_boundary
    await other.eval_guards.insert_one({"_id": gate.VERSION, "owner": gate.OWNER})
    with gate.isolated_engine(db) as probe:
        if scope == "outside_service":
            result = await reasoning.reconsider(goal.for_ai(), **kwargs)
        else:
            result = await AgentService(other if scope == "database" else db)._reconsider(owner, goal)
    assert result is response and calls == [(goal.for_ai(), kwargs)]
    assert probe.structured_decisions == [] and "private" not in json.dumps(gate.model_observations(probe))
    assert probe.model_attempts == probe.model_http_requests == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("exception", [RuntimeError("private-reconsider-error"), asyncio.CancelledError("private-reconsider-cancel")])
async def test_reconsider_keeps_exception_identity_and_resets_scope(monkeypatch, exception):
    calls = []
    response = {"decision": "continue", "reasoning": "outside-service-private-reason"}

    async def original_reconsider(goal, **kwargs):
        calls.append((goal, kwargs))
        if len(calls) == 1:
            raise exception
        return response

    async def original_service(self, owner, goal):
        return await reasoning.reconsider(goal.for_ai(), plan={}, what_happened={}, capabilities=[])

    monkeypatch.setattr(reasoning, "reconsider", original_reconsider)
    monkeypatch.setattr(AgentService, "_reconsider", original_service)
    db = AsyncMongoMockClient().reconsider_cancellation
    goal = await seed(db)
    with gate.isolated_engine(db) as probe:
        with pytest.raises(type(exception)) as caught:
            await AgentService(db)._reconsider(gate.OWNER, goal)
        assert caught.value is exception
        assert await reasoning.reconsider(goal.for_ai(), plan={}, what_happened={}, capabilities=[]) is response
    row, = probe.structured_decisions
    assert row["stage"] == "reconsider" and row["response_kind"] == "raised"
    assert row["exception_type"] == type(exception).__name__ and len(calls) == 2
    assert "private" not in json.dumps(gate.model_observations(probe))
    assert probe.model_attempts == probe.model_http_requests == 0


@pytest.mark.asyncio
async def test_reconsider_wait_and_authority_fields_are_observed_without_coercion(monkeypatch):
    secret = "synthetic-reconsider-api-key"
    monkeypatch.setenv("GEMINI_API_KEY_2", secret)
    response = {"decision": "wait", "reasoning": secret + "x" * 500,
                "wait_minutes": "17", "wait_until": "2099-01-01T12:34:00+01:00",
                "requires_user_authority": "false", "ask_kind": "authority", "asks": "private-request"}
    original = deepcopy(response)

    async def original_reconsider(goal, **kwargs):
        return response

    async def original_service(self, owner, goal):
        return await reasoning.reconsider(goal.for_ai(), plan={}, what_happened={}, capabilities=[])

    monkeypatch.setattr(reasoning, "reconsider", original_reconsider)
    monkeypatch.setattr(AgentService, "_reconsider", original_service)
    db = AsyncMongoMockClient().reconsider_typed_observation
    goal = await seed(db)
    with gate.isolated_engine(db) as probe:
        result = await AgentService(db)._reconsider(gate.OWNER, goal)
    assert result is response and response == original
    row, = probe.structured_decisions
    assert row["decision"] == "wait" and row["wait_minutes_kind"] == "text" and "wait_minutes" not in row
    assert row["wait_until"] == response["wait_until"] and row["wait_until_kind"] == "text"
    assert row["requires_user_authority_kind"] == "text" and "requires_user_authority" not in row
    assert "requires_user_input" not in row and "requires_user_input_kind" not in row
    assert row["ask_kind"] == "authority" and row["has_asks"] is True
    assert len(row["reasoning"]) == 400 and secret not in row["reasoning"]
    assert "private-request" not in json.dumps(gate.model_observations(probe))
    assert probe.model_attempts == probe.model_http_requests == 0
