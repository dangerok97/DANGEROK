"""Isolated v126 acceptance: real handlers/loop, stubbed HTTP, no live accounts."""
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from scripts import phase1_read_provider_eval as runner


@pytest.mark.asyncio
async def test_scripted_vertical_calls_real_handlers_and_reads_back_provenance(monkeypatch):
    from conversation_engine.ai_core.tools import weather_caps
    from places import caps
    import llm.manager

    original_route, original_weather = caps.get_route, weather_caps.get_weather_forecast
    runtime_seen = []

    async def route(arguments, runtime):
        runtime_seen.append(("route", runtime))
        return await original_route(arguments, runtime)

    async def weather(arguments, runtime):
        runtime_seen.append(("weather", runtime))
        return await original_weather(arguments, runtime)

    def no_model():
        raise AssertionError("scripted evaluation must not construct a live model")

    monkeypatch.setattr(caps, "get_route", route)
    monkeypatch.setattr(weather_caps, "get_weather_forecast", weather)
    monkeypatch.setattr(llm.manager, "get_manager", no_model)
    result = await runner.run_case(mode="scripted", max_steps=5)

    assert result["verdict"]["passed"] is True, result
    assert result["verdict"]["tool_calls"] == 2
    assert result["verdict"]["model_decisions"] == 3
    assert [name for name, _ in runtime_seen] == ["route", "weather"]
    assert all(runtime["user_id"] == runner.OWNER for _, runtime in runtime_seen)
    assert runtime_seen[0][1]["db"] is runtime_seen[1][1]["db"]
    assert result["owner"] == "synthetic_isolated_no_real_account"
    assert result["model_mode"] == "scripted_decisions"
    assert result["provider_mode"] == "stubbed_provider_http"
    assert result["real_model_executed"] is False
    assert result["live_provider_reads"] == 0
    assert result["model_calls"] == []
    assert result["blocked_operations"] == []
    assert len(result["http_reads"]) == 2
    assert all(row["source"] == "stubbed_provider_http" for row in result["http_reads"])
    assert all(row["production_handler_used"] and row["session_readback_verified"]
               for row in result["observations"])
    assert all(row["provenance"] for row in result["observations"])
    weather = next(row for row in result["observations"] if row["capability"] == "get_weather_forecast")
    assert weather["payload"]["timezone"] == "Europe/Rome"
    assert "T" in weather["payload"]["observed_at"]
    assert all("T" in row["datetime"] for row in weather["payload"]["hours"])
    assert result["final_answer"]
    assert result["semantic_review"]["automatically_accepted"] is False
    assert result["verdict"]["semantic_acceptance"] == "pending_human_review"


@pytest.mark.asyncio
async def test_live_request_with_injected_decisions_and_http_remains_honestly_scripted(monkeypatch):
    monkeypatch.setenv("ROUTING_PROVIDER", "mapbox")
    monkeypatch.setenv("ROUTING_API_KEY", "synthetic-mapbox-unused")
    monkeypatch.setenv("WEATHER_PROVIDER", "open_meteo")
    result = await runner.run_case(
        mode="live", decide=await runner._scripted_model_factory(),
        provider_reply=runner._scripted_reply, max_steps=5,
    )
    assert result["verdict"]["passed"] is True, result
    assert result["requested_mode"] == "live"
    assert result["model_mode"] == "scripted_decisions"
    assert result["provider_mode"] == "stubbed_provider_http"
    assert result["real_model_executed"] is False
    assert result["live_provider_reads"] == 0
    assert result["http_reads"][0]["provider"] == "mapbox"


@pytest.mark.asyncio
async def test_provider_failure_cannot_be_certified_from_model_success_prose():
    def provider_reply(request):
        if request.url.host == "routes.googleapis.com":
            return httpx.Response(503, json={"error": "service unavailable"}, request=request)
        return runner._scripted_reply(request)

    result = await runner.run_case(mode="scripted", provider_reply=provider_reply, max_steps=5)
    assert result["verdict"]["passed"] is False
    assert "missing_usable_dated_provider_read:get_route" in result["verdict"]["reasons"]
    assert "get_weather_forecast" in result["verdict"]["verified_reads"]
    route = next(row for row in result["observations"] if row["capability"] == "get_route")
    assert route["payload"]["available"] is False
    assert route["payload"]["retryable"] is True
    assert route["session_readback_verified"] is True
    assert result["http_reads"][0]["http_status"] == 503
    assert result["semantic_review"]["automatically_accepted"] is False


@pytest.mark.asyncio
async def test_success_status_without_weather_dates_fails_the_temporal_gate():
    def provider_reply(request):
        response = runner._scripted_reply(request)
        if request.url.host == "api.open-meteo.com":
            data = response.json()
            data.pop("timezone")
            data["current"].pop("time")
            return httpx.Response(200, json=data, request=request)
        return response

    result = await runner.run_case(mode="scripted", provider_reply=provider_reply, max_steps=5)
    assert result["verdict"]["passed"] is False
    assert "missing_usable_dated_provider_read:get_weather_forecast" in result["verdict"]["reasons"]
    weather = next(row for row in result["observations"] if row["capability"] == "get_weather_forecast")
    assert weather["outer_status"] == "ok"
    assert weather["payload"]["status"] == "ok"
    assert weather["payload"].get("observed_at") is None


@pytest.mark.asyncio
async def test_boundary_blocks_world_writes_other_reads_and_external_runtime(monkeypatch):
    from conversation_engine.ai_core import loop
    from conversation_engine.ai_core.tools.registry import ToolRegistry
    from places import caps

    dangerous_db = object()
    original_route = caps.get_route
    runtimes = []

    async def route(arguments, runtime):
        runtimes.append(runtime)
        assert runtime["db"] is not dangerous_db
        assert runtime["user_id"] == runner.OWNER
        assert "access_token" not in runtime
        return await original_route(arguments, runtime)

    monkeypatch.setattr(caps, "get_route", route)
    requested = ["create_calendar_event", "prepare_a_phone_call", "web_search",
                 "get_calendar_events", "open_navigation"]

    async def forced_calls(*, db, sess, **_kwargs):
        registry = ToolRegistry(db)
        saved = []
        for capability in requested + ["get_route"]:
            observation = await registry.execute(capability, {
                "destination": runner.DESTINATION["label"], "travel_mode": "drive",
            }, runtime={"db": dangerous_db, "user_id": "not-the-synthetic-owner",
                        "access_token": "must-not-reach-a-handler"})
            saved.append(observation.model_dump())
        sess.meta["ai_core"] = {"observations": saved}
        return SimpleNamespace(ok=True, ora_text="Synthetic boundary check", ai_calls=0,
                               tool_calls=len(saved), mode="answer", elapsed_ms=1)

    monkeypatch.setattr(loop, "run_cognitive_loop", forced_calls)
    result = await runner.run_case(mode="scripted")
    assert len(runtimes) == 1
    assert result["verdict"]["passed"] is False
    assert "isolation_boundary_attempted" in result["verdict"]["reasons"]
    blocked = [row["capability"] for row in result["observations"] if row["source"] == "blocked"]
    assert blocked == requested
    assert all(not row["production_handler_used"] for row in result["observations"][:-1])
    assert len(result["http_reads"]) == 1


@pytest.mark.asyncio
async def test_http_allowlist_rejects_unknown_endpoints_and_private_coordinates(monkeypatch):
    network = AsyncMock(side_effect=AssertionError("no network allowed in this test"))
    monkeypatch.setattr(httpx.AsyncClient, "send", network)
    boundary = runner._ReadBoundary(model_live=False, provider_reply=runner._scripted_reply)
    with ExitStack() as stack:
        boundary.install(stack)
        token = boundary.scope.set("get_weather_forecast")
        try:
            async with httpx.AsyncClient() as client:
                for url in (
                    "https://api.open-meteo.com/v1/forecast?latitude=10&longitude=20",
                    "https://mail.example.test/send",
                    "https://api.open-meteo.com/not-a-forecast",
                ):
                    with pytest.raises(runner.EvaluationBoundaryError):
                        await client.get(url)
        finally:
            boundary.scope.reset(token)
    network.assert_not_awaited()
    assert len(boundary.blocked) == 3
    assert boundary.reads == []


def _valid_gate_samples():
    now = datetime.now(timezone.utc)
    local = now.astimezone(runner.ZoneInfo(runner.TIMEZONE))
    observed = local.replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    future = (local + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    result = SimpleNamespace(ok=True, ora_text="Evidence summary", ai_calls=3,
                             tool_calls=2, mode="answer", elapsed_ms=5)
    observations = [{
        "capability": capability, "outer_status": "ok", "production_handler_used": True,
        "session_readback_verified": True, "http_refs": [f"http:{index}"],
        "source": "stubbed_provider_http", "payload": {"status": "ok"},
    } for index, capability in enumerate(sorted(runner.REQUIRED_READS))]
    observations[0]["payload"].update({
        "available": True, "duration_seconds": 900, "distance_meters": 3800,
        "reflects_current_traffic": True, "provider": "google_routes",
    })
    observations[1]["payload"].update({
        "provider": "open_meteo", "observed_at": observed,
        "retrieved_at": now.isoformat(), "timezone": runner.TIMEZONE,
        "current": {"temperature_c": 21, "condition": "Poco nuvoloso"},
        "hours": [{"datetime": future, "time": future[11:16], "temperature_c": 21}],
    })
    reads = [{
        "id": f"http:{index}", "capability": capability, "http_status": 200,
        "provider": "google_routes" if capability == "get_route" else "open_meteo",
        "request_started_at": (now - timedelta(seconds=1)).isoformat(),
        "received_at": now.isoformat(), "provider_timezone": runner.TIMEZONE,
        "provider_current_time": observed, "provider_hour_times": [future],
    } for index, capability in enumerate(sorted(runner.REQUIRED_READS))]
    return result, observations, reads, now


@pytest.mark.parametrize("invalid", [True, 0, -1, float("nan"), float("inf"), "900"])
def test_route_gate_requires_a_positive_finite_numeric_eta(invalid):
    result, observations, reads, now = _valid_gate_samples()
    observations[0]["payload"]["duration_seconds"] = invalid
    verdict = runner._verdict(result, [{}], observations, reads, [], now=now)
    assert verdict["passed"] is False
    assert "missing_usable_dated_provider_read:get_route" in verdict["reasons"]


def test_prose_or_http_success_without_session_provenance_does_not_pass():
    result, observations, reads, now = _valid_gate_samples()
    assert runner._verdict(result, [{}], observations, reads, [], now=now)["passed"]
    observations[0]["session_readback_verified"] = False
    verdict = runner._verdict(result, [{}], observations, reads, [], now=now)
    assert verdict["passed"] is False
    assert "get_route" not in verdict["verified_reads"]


def test_stale_weather_or_swapped_date_cannot_pass_with_current_fetch_timestamp():
    result, observations, reads, now = _valid_gate_samples()
    stale = (now - timedelta(days=1)).astimezone(runner.ZoneInfo(runner.TIMEZONE))
    observations[1]["payload"]["observed_at"] = stale.strftime("%Y-%m-%dT%H:%M")
    reads[1]["provider_current_time"] = observations[1]["payload"]["observed_at"]
    verdict = runner._verdict(result, [{}], observations, reads, [], now=now)
    assert verdict["passed"] is False
    assert "get_weather_forecast" not in verdict["verified_reads"]
    result, observations, reads, now = _valid_gate_samples()
    observations[1]["payload"]["hours"][0]["datetime"] = "2020-01-01T12:00"
    assert not runner._verdict(result, [{}], observations, reads, [], now=now)["passed"]


@pytest.mark.asyncio
async def test_live_preflight_fails_without_keys_before_model_or_provider_calls(monkeypatch, capsys):
    for key in runner.LLM_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("ROUTING_API_KEY", raising=False)
    run = AsyncMock(side_effect=AssertionError("preflight must not run case"))
    monkeypatch.setattr(runner, "run_case", run)
    assert await runner.main("live") == 3
    run.assert_not_awaited()
    output = capsys.readouterr().out
    assert '"real_model_executed": false' in output
    assert "live_llm_credentials_unavailable" in output
    assert "live_routing_configuration_unavailable" in output


def test_exact_secondary_key_supported_and_credentials_redacted(monkeypatch):
    for key in runner.LLM_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GEMINI2_API_KEY", "synthetic-secret-redact-me")
    monkeypatch.setenv("ROUTING_PROVIDER", "google_routes")
    monkeypatch.setenv("ROUTING_API_KEY", "synthetic-route-secret")
    monkeypatch.setenv("WEATHER_PROVIDER", "open_meteo")
    assert runner._preflight() == []
    assert runner._safe_text("Answer synthetic-secret-redact-me", 500) == "Answer [credential redacted]"
