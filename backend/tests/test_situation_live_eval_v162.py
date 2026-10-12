"""Offline contracts for the optional Tarquinia first-cycle probe.

The one integration case waits for the actual initial wake. All model replies
and provider HTTP are fixtures; no test claims live source fitness or dryness.
"""
import copy
from contextlib import ExitStack
from datetime import timedelta
import hashlib
import json
import time
from unittest.mock import AsyncMock

import httpx
from mongomock_motor import AsyncMongoMockClient
import pytest

from scripts import situation_live_eval_v162 as runner


@pytest.fixture(autouse=True)
def no_local_proxy_for_fake_transport(monkeypatch):
    # The real SDK is tested with fake HTTP; a workspace proxy is irrelevant.
    for name in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.delenv(name, raising=False)
    for name in ("no_proxy", "NO_PROXY"):
        monkeypatch.setenv(name, "*")


@pytest.mark.asyncio
async def test_scripted_first_cycle_uses_real_worker_sources_and_a_future_check(monkeypatch, tmp_path):
    import agent.background
    import agent.reasoning
    import weather as weather_service
    from research.service import ResearchService

    network = AsyncMock(side_effect=AssertionError("No external HTTP in this test"))
    monkeypatch.setattr(httpx.AsyncClient, "send", network)
    wake = AsyncMock(wraps=agent.background.advance_wake)
    weather = AsyncMock(wraps=weather_service.forecast_at)
    monkeypatch.setattr(agent.background, "advance_wake", wake)
    monkeypatch.setattr(weather_service, "forecast_at", weather)
    # A regular wrapper preserves the ResearchService descriptor binding.
    original_research = ResearchService.run
    research_calls = []

    async def read_research(self, *args, **kwargs):
        research_calls.append((args, kwargs))
        return await original_research(self, *args, **kwargs)

    monkeypatch.setattr(ResearchService, "run", read_research)
    original_dump = agent.reasoning._action_dump
    full_contexts = []

    def capture_context(payload):
        full_contexts.append(json.dumps(payload, ensure_ascii=False, default=str))
        (tmp_path / f"situation-action-context-{len(full_contexts)}.json").write_text(
            full_contexts[-1], encoding="utf-8")
        return original_dump(payload)

    monkeypatch.setattr(agent.reasoning, "_action_dump", capture_context)
    before = runner.now()
    report = await runner.run_case()
    (tmp_path / "situation-first-cycle.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    assert full_contexts, report
    (tmp_path / "situation-action-context.json").write_text(full_contexts[0], encoding="utf-8")
    # The same seven weather records originally exceeded the action limit.
    # Their lossless production table must now reach the scripted model;
    # neither the fixture weather nor its physical clock is shortened.
    assert report["passed"], {key: report.get(key) for key in (
        "error", "diagnosis", "phases", "steps", "state_after_initial_worker", "blocked_operations")}
    assert report["mode"] == "scripted"
    assert report["overall_outcome"] == "followup_pending"
    assert report["full_laundry_outcome_passed"] is False
    assert report["source_appropriateness_accepted"] is False
    assert report["physical_clock_advanced"] is False
    assert report["process_restart_tested"] is False
    assert report["logical_model_calls"] == report["model_http_requests"] == report["live_provider_reads"] == 0
    assert report["real_notifications_sent"] == 0
    assert report["real_model_executed"] is False
    assert report["model_calls"] == report["intercepted_notification_attempts"] == []
    assert report["blocked_operations"] == []
    assert report["scripted_model_calls"] > 0
    assert wake.await_count == weather.await_count == 1
    assert len(research_calls) == 1
    network.assert_not_awaited()

    context = report["context_observations"][0]
    assert context["available"] is True and context["model_input_characters"] <= 9000
    assert context["input_characters"] == len(full_contexts[0]) > 9000
    assert context["input_sha256"] == hashlib.sha256(full_contexts[0].encode()).hexdigest()
    assert context["input_truncated"] is True
    actual_choices = [json.loads(row["input"]) for row in report["model_observations"]
                      if row["stage"] == "choose_next_action"]
    assert actual_choices
    rows = runner.scripted_records(actual_choices[0]["what_has_been_found"])
    expected = json.loads(full_contexts[0])["what_has_been_found"]
    assert json.dumps(rows, sort_keys=True, ensure_ascii=False) == json.dumps(expected, sort_keys=True, ensure_ascii=False)
    assert len(rows) == 7

    dispatch = runner.moment(report["initial_dispatch_at"])
    started = runner.moment(report["fixture_started_at"])
    assert before <= started <= dispatch <= runner.now()
    assert dispatch >= runner.moment(report["initial_wake"]["scheduled_for"])
    assert (dispatch - started).total_seconds() >= 30
    state = report["state_after_initial_worker"]
    assert report["situation_before_worker"]["started_at"] == report["fixture_started_at"]
    assert state["outcome"]["status"] == "estimated" and state["outcome"]["basis"] == "estimate"
    assert state["goal_status"] != "completed"
    assert state["weather_http_current"] is state["weather_binding_current"] is True
    assert state["source_revision"] == "1"
    assert runner.moment(state["next_run_at"]) > dispatch
    assert any(row["scheduled_for"] == state["next_run_at"] for row in state["future_wakes"])
    assert runner.moment(state["next_run_at"]) < runner.moment(state["outcome"]["valid_until"])
    assert state["research"][0]["sources"][0]["snippet"] == runner.SCRIPTED_BASELINE
    assert state["research"][0]["sources"][0]["snippet_origin"] == "unknown"
    assert state["needs"] == []
    assert report["semantic_review"] == {"status": "pending_human_review", "automatically_accepted": False}
    for phase in ("future_check", "useful_action", "device_receipt"):
        assert report["phases"][phase] == {"status": "not_run"}
    assert report["phases"]["cancellation"] == {"status": "passed", "pending_wakes": 0,
        "replay_admission": "no_attention", "physical_collection_claimed": False}
    assert report["persistence"] == "in_memory_only_cancelled_after_snapshot"
    assert all(row["source"] == "stubbed_provider_http" for row in report["provider_reads"])
    assert {row["provider"] for row in report["provider_reads"]} == {"open_meteo", "tavily"}


@pytest.mark.asyncio
async def test_waiter_does_not_move_a_saved_future_checkpoint_or_use_a_foreign_wake(monkeypatch):
    db = AsyncMongoMockClient().wait_contract
    due = runner.now() + timedelta(minutes=5)
    saved = {"id": "own-wake", "owner_id": runner.OWNER, "source_ref": "goal:own",
             "status": "pending", "scheduled_for": due.isoformat()}
    await db.ambient_wakes.insert_one(copy.deepcopy(saved))
    await db.ambient_wakes.insert_one({**saved, "id": "foreign-wake", "owner_id": "foreign",
                                     "scheduled_for": (due - timedelta(hours=1)).isoformat()})
    sleep = AsyncMock(side_effect=AssertionError("Outside the bounded initial run"))
    monkeypatch.setattr(runner.asyncio, "sleep", sleep)
    assert await runner.wait_for_initial_wake(db, "own", deadline=time.monotonic() + 1) is None
    assert await db.ambient_wakes.find_one({"id": "own-wake"}, {"_id": 0}) == saved
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_waiter_awaits_the_persisted_clock_without_writing_it(monkeypatch):
    db = AsyncMongoMockClient().wait_clock
    first = runner.now()
    due = first + timedelta(seconds=30)
    await db.ambient_wakes.insert_one({"id": "w", "owner_id": runner.OWNER, "source_ref": "goal:g",
        "status": "pending", "scheduled_for": due.isoformat()})
    clock = {"at": first}
    waits = []

    async def sleep(delay):
        waits.append(delay)
        clock["at"] = due

    monkeypatch.setattr(runner, "now", lambda: clock["at"])
    monkeypatch.setattr(runner.asyncio, "sleep", sleep)
    actual = await runner.wait_for_initial_wake(db, "g", deadline=time.monotonic() + 40)
    assert waits == [30.0]
    assert actual["scheduled_for"] == due.isoformat() and actual["status"] == "pending"
    assert await db.ambient_wakes.count_documents({"scheduled_for": due.isoformat()}) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("url,scope", [
    ("https://api.open-meteo.com/v1/forecast?latitude=10&longitude=20", "weather"),
    ("http://api.open-meteo.com/v1/forecast?latitude=42.249&longitude=11.756", "weather"),
    ("https://api.tavily.com/search", "blocked"),
    ("https://api.tavily.com/other", "research"),
    ("https://mail.example.test/send", "research"),
])
async def test_http_boundary_never_falls_back_to_other_hosts_points_or_scopes(monkeypatch, url, scope):
    network = AsyncMock(side_effect=AssertionError("No network"))
    monkeypatch.setattr(httpx.AsyncClient, "send", network)
    probe = runner.Probe("scripted")
    boundary = runner.SituationReadBoundary(probe)
    with ExitStack() as stack:
        boundary.install(stack)
        token = boundary.scope.set(scope)
        try:
            async with httpx.AsyncClient() as client:
                with pytest.raises(runner.EvaluationFailure, match="EVAL_HTTP_NOT_ALLOWLISTED"):
                    await client.get(url)
        finally:
            boundary.scope.reset(token)
    assert probe.blocked == ["EVAL_HTTP_NOT_ALLOWLISTED"]
    assert boundary.reads == [] and probe.model_http == 0
    network.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_reads_share_the_existing_twelve_request_limit(monkeypatch):
    network = AsyncMock(side_effect=AssertionError("No external HTTP"))
    monkeypatch.setattr(httpx.AsyncClient, "send", network)
    probe = runner.Probe("scripted")
    boundary = runner.SituationReadBoundary(probe)
    with ExitStack() as stack:
        boundary.install(stack)
        async with httpx.AsyncClient() as client:
            token = boundary.scope.set("weather")
            for _ in range(6):
                await client.get("https://api.open-meteo.com/v1/forecast?latitude=42.249&longitude=11.756")
            boundary.scope.reset(token)
            token = boundary.scope.set("research")
            for _ in range(6):
                await client.post("https://api.tavily.com/search", json={"query": "synthetic"})
            with pytest.raises(runner.EvaluationFailure, match="PROVIDER_READ_BOUND_EXCEEDED"):
                await client.post("https://api.tavily.com/search", json={"query": "synthetic"})
            boundary.scope.reset(token)
    assert len(boundary.reads) == 12 and probe.model_http == 0
    network.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_sdk_grounded_search_and_manager_share_model_limits_without_live_http(monkeypatch):
    from conversation_engine.ai_core.tools.providers import gemini_search
    from llm.base import LLMResult
    from llm.manager import ProviderManager
    calls = []

    async def transport(client, request, **kwargs):
        calls.append((request.url.host, kwargs.get("follow_redirects")))
        if request.url.host == "generativelanguage.googleapis.com":
            return httpx.Response(200, request=request, json={"candidates": [{
                "content": {"role": "model", "parts": [{"text": "Synthetic source."}]},
                "groundingMetadata": {"groundingChunks": [{"web": {
                    "uri": "https://example.org/source", "title": "Synthetic source"}}]},
            }]})
        return httpx.Response(200, request=request, json={})

    async def chat(self, **kwargs):
        async with httpx.AsyncClient() as client:
            await client.post("https://api.groq.com/openai/v1/chat/completions", json={})
        return LLMResult(text="{}", provider="groq", model="synthetic_transport")

    monkeypatch.setattr(httpx.AsyncClient, "send", transport)
    monkeypatch.setattr(ProviderManager, "chat", chat)
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-grounding-test-key")
    monkeypatch.setenv("GEMINI_SEARCH_ENABLED", "1")
    db = AsyncMongoMockClient().sdk_contract
    probe = runner.Probe("live")  # only the real SDK is live; transport is above
    await runner.seed_world(db, runner.now())
    with runner.isolated_engine(db, probe, runner.now()) as boundary:
        await ProviderManager.__new__(ProviderManager).chat(system="synthetic", user="{}")
        found = await gemini_search.search("public synthetic evidence")
        assert found.ok and found.hits
        assert probe.logical_calls == 2 and probe.manager_calls == probe.grounded_search_calls == 1
        assert probe.model_http == 2
        assert len(boundary.reads) == 1 and boundary.reads[0]["provider"] == "gemini_search"
        for _ in range(runner.MAX_MODEL_CALLS - 2):
            probe.reserve_model("manager")
        with pytest.raises(runner.EvaluationFailure, match="MODEL_CALL_BOUND_EXCEEDED"):
            await gemini_search.search("must not leave")
    assert calls == [("api.groq.com", False), ("generativelanguage.googleapis.com", False)]


@pytest.mark.asyncio
async def test_http_model_limit_blocks_before_a_grounded_search_request(monkeypatch):
    network = AsyncMock(side_effect=AssertionError("No request past the cap"))
    monkeypatch.setattr(httpx.AsyncClient, "send", network)
    probe = runner.Probe("live", model_http=runner.MAX_MODEL_HTTP_REQUESTS)
    boundary = runner.SituationReadBoundary(probe)
    with ExitStack() as stack:
        boundary.install(stack)
        token = boundary.scope.set("grounded_search")
        try:
            async with httpx.AsyncClient() as client:
                with pytest.raises(runner.EvaluationFailure, match="MODEL_HTTP_BOUND_EXCEEDED"):
                    await client.post("https://generativelanguage.googleapis.com/v1beta/models/model:generateContent", json={})
        finally:
            boundary.scope.reset(token)
    assert boundary.reads == [] and probe.model_http == runner.MAX_MODEL_HTTP_REQUESTS
    network.assert_not_awaited()


@pytest.mark.asyncio
async def test_device_boundary_does_not_return_a_delivery_receipt():
    probe = runner.Probe("scripted")
    provider = runner.BlockedNotification(probe)
    with pytest.raises(runner.EvaluationFailure, match="DEVICE_SEND_FORBIDDEN"):
        await provider.send(owner_id=runner.OWNER, plan_id="p", title="Synthetic", body="Estimated action.", deep_link="/ora")
    assert probe.push_attempts == [{"plan_id": "p", "title": "Synthetic", "body": "Estimated action.", "deep_link": "/ora"}]
    with pytest.raises(runner.EvaluationFailure, match="NOTIFICATION_OWNER_BOUNDARY"):
        await provider.send(owner_id="foreign", plan_id="x")
    assert len(probe.push_attempts) == 1


def test_observations_bound_and_redact_sources_without_certifying_appropriateness(monkeypatch):
    secret = "synthetic-sensitive-search-key"
    monkeypatch.setenv("TAVILY_API_KEY", secret)
    probe = runner.Probe("scripted")
    for _ in range(runner.MAX_DECISION_OBSERVATIONS + 2):
        probe.observe_model("system", secret + "x" * 9500)
    assert len(probe.decisions) == runner.MAX_DECISION_OBSERVATIONS
    assert probe.decisions_omitted == 2
    assert all(row["input_truncated"] and len(row["input"]) <= 9000 for row in probe.decisions)
    assert secret not in json.dumps(probe.decisions)
    assert runner.public_url("https://example.org/source?key=" + secret) == "https://example.org/source"
    assert runner.public_url("https://user:password@example.org/private") == ""
    nested = {"source": {"reason": "read " + secret}}
    assert secret not in json.dumps(runner.redact_report(nested))
    assert runner.observed_json(nested)["source"]["reason"] == "read [credential redacted]"
    large = runner.observed_json({"source": "x" * 6100})
    assert large["truncated"] is True and len(large["excerpt"]) <= 6000


def test_scripted_table_reader_preserves_metadata_nulls_types_and_absence():
    table = {"common": {"source_refs": ["source:à"], "observed_at": "2026-10-12T00:00:00+00:00"},
        "columns": ["evidence_id", "what_was_found", "bears_on", "value"],
        "rows": [["e1", "Temperatura riferita, non misurata dal telefono.", None, False],
                 ["e2", "Previsione del vento.", None, 0],
                 ["e3", "Limiti invariati."]], "missing": {"1": [2]}}
    before = copy.deepcopy(table)
    actual = runner.scripted_records(table)
    assert actual == [
        {**table["common"], "evidence_id": "e1", "what_was_found": table["rows"][0][1], "bears_on": None, "value": False},
        {**table["common"], "evidence_id": "e2", "what_was_found": table["rows"][1][1], "value": 0},
        {**table["common"], "evidence_id": "e3", "what_was_found": table["rows"][2][1]},
    ]
    assert type(actual[0]["value"]) is bool and type(actual[1]["value"]) is int
    assert table == before and runner.scripted_records(actual) is actual
    singleton = {"evidence_id": "research", "source_refs": ["run:other"], "what_was_found": "Condizione esplicita."}
    grouped = {"record_groups": [table, [singleton], {"record_groups": [[{"value": None}]]}]}
    assert runner.scripted_records(grouped) == actual + [singleton, {"value": None}]
    with pytest.raises(runner.EvaluationFailure, match="SCRIPTED_RECORD_TABLE_INVALID"):
        runner.scripted_records({**table, "missing": {"1": [True]}})


@pytest.mark.asyncio
async def test_absent_model_response_fails_before_inventing_situation_sources_or_monitoring(monkeypatch):
    async def unavailable(self, **kwargs):
        raise runner.EvaluationFailure("SCRIPTED_MODEL_UNAVAILABLE")

    monkeypatch.setattr(runner.ScriptedModel, "chat", unavailable)
    report = await runner.run_case()
    assert report["passed"] is False and report["full_laundry_outcome_passed"] is False
    assert report["provider_reads"] == [] and report["real_notifications_sent"] == 0
    assert report["phases"]["initial_worker"] == report["phases"]["future_check"] == {"status": "not_run"}
    assert report["phases"]["monitoring"] == {"status": "not_run"}
    assert report["semantic_review"]["automatically_accepted"] is False


def monitoring_state():
    """An already source-validated projection, not a seeded production result."""
    due = runner.now() + timedelta(minutes=30)
    return {"goal_id": "synthetic-goal", "weather_http_current": True,
        "weather_binding_current": True, "next_run_at": due.isoformat(),
        "future_wakes": [{"source_ref": "goal:synthetic-goal", "scheduled_for": due.isoformat()}],
        "outcome": {"status": "estimated", "basis": "estimate",
                    "valid_until": (due + timedelta(minutes=15)).isoformat(),
                    "evidence_ids": ["weather-evidence", "research-evidence"]},
        "research_http_runs": ["research-run"],
        "evidence": [{"id": "research-evidence", "provenance": {"capability": "web.research",
            "research_sufficient": True, "source_refs": ["research-run"]}}]}


def test_recorded_monitoring_has_separate_manual_and_future_acceptance():
    state = monitoring_state()
    before = copy.deepcopy(state)
    result = runner.assess_monitoring(state)
    assert result == {"status": "passed", "reasons": [],
                      "semantic_appropriateness": "pending_human_review"}
    assert state == before
    assert "full_laundry_outcome_passed" not in result


@pytest.mark.parametrize("change,reason", [
    ({"outcome": None}, "GROUNDED_ESTIMATE_NOT_RECORDED"),
    ({"evidence": []}, "CITED_EMPIRICAL_RESEARCH_NOT_VALIDATED"),
    ({"research_http_runs": []}, "CITED_RESEARCH_HTTP_NOT_OBSERVED"),
    ({"research_http_runs": ["different-run"]}, "CITED_RESEARCH_HTTP_NOT_OBSERVED"),
    ({"weather_http_current": False}, "CURRENT_BOUND_WEATHER_NOT_OBSERVED"),
    ({"weather_binding_current": False}, "CURRENT_BOUND_WEATHER_NOT_OBSERVED"),
    ({"next_run_at": None}, "FUTURE_CHECK_BEFORE_EXPIRY_NOT_RECORDED"),
    ({"future_wakes": []}, "DURABLE_FUTURE_WAKE_NOT_RECORDED"),
])
def test_missing_source_or_monitoring_binding_never_passes_as_a_future_followup(change, reason):
    state = monitoring_state()
    state.update(change)
    result = runner.assess_monitoring(state)
    assert result["status"] == "failed" and reason in result["reasons"]
    assert result["semantic_appropriateness"] == "pending_human_review"


@pytest.mark.asyncio
async def test_isolation_rejects_non_mock_database_foreign_research_and_external_steps(monkeypatch):
    from types import SimpleNamespace
    from agent.execution import StepExecutor
    from research.models import ResearchNeed
    from research.service import ResearchService

    class PretendDatabase:
        __module__ = "motor.motor_asyncio"

    with pytest.raises(runner.EvaluationFailure, match="SYNTHETIC_DATABASE_REQUIRED"):
        runner.require_synthetic_database(PretendDatabase())
    db = AsyncMongoMockClient().isolated_read_contract
    other = AsyncMongoMockClient().other_database
    probe = runner.Probe("scripted")
    model = AsyncMock(side_effect=AssertionError("No model for a forbidden operation"))
    network = AsyncMock(side_effect=AssertionError("No HTTP for a forbidden operation"))
    monkeypatch.setattr(httpx.AsyncClient, "send", network)
    monkeypatch.setattr(runner.ScriptedModel, "chat", model)
    await runner.seed_world(db, runner.now())
    with runner.isolated_engine(db, probe, runner.now()):
        for research_db, owner in ((db, "foreign"), (other, runner.OWNER)):
            with pytest.raises(runner.EvaluationFailure, match="RESEARCH_OWNER_BOUNDARY"):
                await ResearchService(research_db).run(owner, ResearchNeed(question="Synthetic"))
        with pytest.raises(runner.EvaluationFailure, match="STEP_EFFECT_OR_OWNER_BOUNDARY"):
            await StepExecutor(db).run(runner.OWNER, SimpleNamespace(owner_id=runner.OWNER),
                SimpleNamespace(step_type="execute", capability_needed="message.send"))
    model.assert_not_awaited()
    network.assert_not_awaited()
    assert probe.logical_calls == probe.model_http == 0
