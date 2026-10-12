"""Acceptance for the isolated, connected source-to-Home evaluator.

These are scripted decisions over real internal services. Passing them never
attests a real model, third-party facts, a process restart or device receipt.
"""
import json

import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

from scripts import autonomy_completion_eval_v162 as gate


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", gate.SCENARIOS)
async def test_connected_autonomy_contract(scenario):
    report = await gate.run_case(scenario)
    assert report["passed"] is True
    assert report["real_model_executed"] is False
    assert report["model_attempts"] == report["model_http_requests"] == 0
    assert report["live_provider_reads"] == 0
    assert report["external_effects"] == 0
    assert report["storage"] == "in_memory"
    assert report["process_restart_tested"] is False
    if scenario == "irrelevant":
        assert report["worker_ticks"] == []
        assert report["executed_capabilities"] == []
        assert report["result"]["state"] == "no_goal"
    elif scenario not in ("source_revoked", "memory_revoked"):
        assert len(report["worker_ticks"]) >= 2
        assert report["result"]["home_delivered"]
        assert report["result"]["replay_idempotent"]
        assert report["result"]["owner_isolation"]
        assert report["result"]["semantic_review"]["human_review_still_required"]


@pytest.mark.asyncio
async def test_canonical_governed_memory_reaches_the_real_worker_reader():
    db = AsyncMongoMockClient().v162_canonical
    with gate.isolated_engine(db) as probe:
        await gate.seed_case(db, "completed_result")
        memory = await db.memories.find_one({"user_id": gate.OWNER})
        assert memory["statement"] == gate.baseline.FACT
        assert memory["content"] == gate.baseline.FACT
        assert "summary" not in memory  # legacy fixtures must not hide drift
        goal_id = await gate.admit(db, "completed_result")
        await gate.first_read(db, goal_id, probe)
        evidence = await db.agent_evidence.find_one({
            "owner_id": gate.OWNER, "goal_id": goal_id,
            "provenance.capability": "information.read",
        })
        assert evidence and evidence["claim"] == gate.baseline.FACT
        assert memory["id"] in evidence["provenance"]["source_refs"]
        assert evidence["provenance"]["source_versions"].get(memory["id"])


@pytest.mark.asyncio
async def test_harness_cannot_repair_a_missing_durable_continuation():
    db = AsyncMongoMockClient().v162_lost_checkpoint
    with gate.isolated_engine(db) as probe:
        await gate.seed_case(db, "completed_result")
        goal_id = await gate.admit(db, "completed_result")
        await gate.first_read(db, goal_id, probe)
        await db.agent_goals.update_one({"id": goal_id}, {"$set": {"next_run_at": None}})
        with pytest.raises(gate.EvaluationFailure, match="DURABLE_CONTINUATION_MISSING"):
            await gate.fire_due(db, goal_id, probe)


@pytest.mark.asyncio
async def test_missing_home_handoff_does_not_count_as_completed_acceptance(monkeypatch):
    from agent.visibility import VisibilityService

    async def lose_handoff(*args, **kwargs):
        return None

    monkeypatch.setattr(VisibilityService, "show", lose_handoff)
    with pytest.raises(gate.EvaluationFailure, match="HOME_OUTBOX_NOT_DELIVERED"):
        await gate.run_case("completed_result")


@pytest.mark.asyncio
async def test_independent_result_gate_rejects_empty_substance_even_if_model_approves(monkeypatch):
    monkeypatch.setattr(gate.baseline, "DRAFT", "Ho preparato il confronto richiesto.")
    with pytest.raises(gate.EvaluationFailure, match="SEMANTIC_RESULT_REJECTED"):
        await gate.run_case("completed_result")


@pytest.mark.asyncio
@pytest.mark.parametrize("home_failed", [False, True])
async def test_memory_forgotten_after_completion_invalidates_visible_or_pending_home(home_failed):
    from delivery.service import DeliveryService

    db = AsyncMongoMockClient().v162_completed_memory_withdrawal
    scenario = "home_write_retry" if home_failed else "completed_result"
    with gate.isolated_engine(db, scenario=scenario) as probe:
        await gate.seed_case(db, scenario)
        goal_id = await gate.admit(db, scenario)
        await gate.first_read(db, goal_id, probe)
        await gate.fire_due(db, goal_id, probe)
        if home_failed:
            assert await db.agent_updates.count_documents({"home_pending": True}) == 1
        else:
            assert (await gate.verify_result(db, goal_id, probe))["home_delivered"]
        await gate.change_memory(db, goal_id)
        await gate.recover_home(db)
        assert await DeliveryService(db).ambient_line(gate.OWNER) is None
        assert await db.agent_updates.count_documents({"home_pending": True}) == 0
        if home_failed:
            assert await db.ambient_activity.count_documents({
                "cognitive_provenance.agent": "visibility", "cognitive_provenance.goal": goal_id,
            }) == 0


def test_model_cannot_claim_provider_verification_from_an_internal_note():
    invented = gate.baseline.DRAFT.replace("non verificata", "verificata").replace(
        "sono da verificare", "ho verificato")
    result = gate.review_comparison(invented)
    assert not result["passed"]
    assert "SOURCE_VERIFICATION_LIMIT_MISSING" in result["reasons"]


@pytest.mark.asyncio
async def test_live_requested_without_credentials_is_blocked_and_nonzero(monkeypatch, tmp_path, capsys):
    for key in gate.LLM_KEYS:
        monkeypatch.delenv(key, raising=False)
    entered = []

    async def forbidden_run(*args, **kwargs):
        entered.append(True)
        raise AssertionError("preflight must precede a model attempt")

    monkeypatch.setattr(gate, "run_case", forbidden_run)
    output = tmp_path / "blocked-live.json"
    code = await gate.main(mode="live", output=str(output))
    report = json.loads(output.read_text())
    assert code == 3
    assert report["status"] == "blocked" and report["passed"] is False
    assert report["real_model_executed"] is False and report["cases"] == []
    assert not entered
    assert "LIVE_MODEL_CREDENTIALS_UNAVAILABLE" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_failed_case_has_a_nonzero_verdict_and_sanitized_exception(monkeypatch, tmp_path, capsys):
    async def broken(*args, **kwargs):
        probe = kwargs["probe"]
        probe.model_calls.append({"provider": "synthetic", "model": "synthetic",
                                  "usage": {"prompt_tokens": 7, "completion_tokens": 3}})
        probe.model_attempts = probe.model_http_requests = 1
        raise RuntimeError("synthetic private error content must not enter the report")

    monkeypatch.setattr(gate, "run_case", broken)
    output = tmp_path / "failed.json"
    assert await gate.main(scenario="completed_result", output=str(output)) == 1
    report = json.loads(output.read_text())
    assert report["status"] == "failed" and not report["passed"]
    assert report["cases"][0]["reason"] == "RuntimeError"
    assert report["cases"][0]["model_http_requests"] == 1
    assert report["cases"][0]["model_calls"][0]["usage"]["completion_tokens"] == 3
    assert "private error" not in output.read_text() + capsys.readouterr().out


@pytest.mark.asyncio
async def test_world_action_is_blocked_before_the_executor_can_act():
    from agent.execution import StepExecutor
    from agent.models import ActionStep, AutonomousGoal

    db = AsyncMongoMockClient().v162_effect_boundary
    with gate.isolated_engine(db) as probe:
        goal = AutonomousGoal(owner_id=gate.OWNER, objective="Synthetic boundary", desired_outcome="No effects")
        step = ActionStep(intent="Attempt forbidden action", step_type="execute", capability_needed="calendar.create")
        with pytest.raises(gate.EvaluationFailure, match="STEP_EFFECT_OR_OWNER_BOUNDARY"):
            await StepExecutor(db).run(gate.OWNER, goal, step, may_touch_the_world=True)
        assert probe.blocked_effects == 1
        assert await db.agent_action_attempts.count_documents({}) == 0


@pytest.mark.asyncio
async def test_unscoped_external_http_is_blocked_before_transport():
    from scripts.phase1_read_provider_eval import EvaluationBoundaryError

    db = AsyncMongoMockClient().v162_network_boundary
    with gate.isolated_engine(db) as probe:
        async with httpx.AsyncClient(trust_env=False) as client:
            with pytest.raises(EvaluationBoundaryError, match="EVAL_HTTP_NOT_ALLOWLISTED"):
                await client.get("https://example.invalid/forbidden")
        assert probe.network.blocked == ["EVAL_HTTP_NOT_ALLOWLISTED"]
        assert probe.network.reads == []


@pytest.mark.asyncio
async def test_model_fallbacks_share_a_transport_budget_before_network_spending(monkeypatch):
    from llm.manager import ProviderManager

    transported = []

    def fake_transport(request):
        transported.append(request.url.host)
        return httpx.Response(503, json={"error": "synthetic transient failure"})

    async def fallback_chat(*args, **kwargs):
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake_transport), trust_env=False) as client:
            for _ in range(3):
                await client.post("https://api.openai.com/v1/chat/completions", json={"synthetic": True})
        raise AssertionError("third transport attempt must not happen")

    monkeypatch.setattr(ProviderManager, "chat", fallback_chat)
    monkeypatch.setattr(gate, "MAX_MODEL_HTTP_REQUESTS", 2)
    db = AsyncMongoMockClient().v162_model_transport_budget
    with gate.isolated_engine(db, mode="live") as probe:
        with pytest.raises(gate.EvaluationFailure, match="MODEL_HTTP_BOUND_EXCEEDED"):
            await ProviderManager.chat(object())
        assert transported == ["api.openai.com", "api.openai.com"]
        assert probe.model_http_requests == 2 and probe.model_attempts == 1
        assert probe.network.blocked == ["MODEL_HTTP_BOUND_EXCEEDED"]
        assert probe.network.scope.get() == "blocked"


@pytest.mark.asyncio
async def test_unmarked_database_cannot_be_given_synthetic_clock_changes():
    db = AsyncMongoMockClient().v162_unmarked
    with pytest.raises(gate.EvaluationFailure, match="SYNTHETIC_CLOCK_GUARD_MISSING"):
        await gate.recover_home(db)


@pytest.mark.asyncio
async def test_existing_user_database_is_not_seeded():
    db = AsyncMongoMockClient().v162_existing
    await db.users.insert_one({"user_id": "another-fictional-owner"})
    with pytest.raises(gate.EvaluationFailure, match="EVALUATOR_DATABASE_NOT_EMPTY"):
        await gate.seed_case(db, "completed_result")
    assert await db.memories.count_documents({}) == 0
    assert await db.eval_guards.count_documents({}) == 0
