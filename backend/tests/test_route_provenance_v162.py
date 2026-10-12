"""Route estimates keep retrieval time distinct from the provider's traffic time."""
from datetime import datetime, timezone
import json

import httpx
import pytest

from places import routing
from scripts import phase1_read_provider_eval as runner


PROVENANCE_KEYS = {
    "duration_kind", "retrieved_at", "retrieval_time_source", "provider_as_of",
}


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["google_routes", "mapbox"])
async def test_estimate_and_local_retrieval_clock_reach_model_and_saved_observation(
    monkeypatch, provider,
):
    """Exercise real HTTP adapters, capability, loop payload and session readback.

    HTTP and model decisions are isolated fixtures; no claim is made here about
    a live model following the provenance it receives.
    """
    monkeypatch.setenv("ROUTING_PROVIDER", provider)
    monkeypatch.setenv("ROUTING_API_KEY", "synthetic-route-provenance")
    monkeypatch.setenv("WEATHER_PROVIDER", "open_meteo")
    scripted = await runner._scripted_model_factory()
    seen = []
    started = datetime.now(timezone.utc)

    async def inspect_decision(system, user):
        payload = json.loads(user)
        for row in payload["observations"]:
            if row.get("name") != "get_route" or row.get("status") != "ok":
                continue
            route = row["payload"]
            assert route["duration_kind"] == "estimate"
            assert route["provider_as_of"] is None
            assert route["retrieval_time_source"] == "ora_clock_not_provider_observation_time"
            retrieved = datetime.fromisoformat(route["retrieved_at"])
            assert retrieved.utcoffset().total_seconds() == 0
            assert started <= retrieved <= datetime.now(timezone.utc)
            assert route["duration_seconds"] == 900
            assert route["distance_meters"] == 3800
            assert route["reflects_current_traffic"] is True
            assert route["provider"] == provider
            assert "observed_at" not in route
            seen.append({key: route[key] for key in PROVENANCE_KEYS})
        return await scripted(system, user)

    result = await runner.run_case(
        mode="live", decide=inspect_decision,
        provider_reply=runner._scripted_reply, max_steps=5,
    )
    assert result["verdict"]["passed"] is True, result["verdict"]
    assert len(seen) == 2
    assert seen[0] == seen[1]
    route = next(row for row in result["observations"] if row["capability"] == "get_route")
    assert route["production_handler_used"] is True
    assert route["session_readback_verified"] is True
    assert {key: route["payload"][key] for key in PROVENANCE_KEYS} == seen[0]
    read = next(row for row in result["http_reads"] if row["capability"] == "get_route")
    retrieved = datetime.fromisoformat(route["payload"]["retrieved_at"])
    received = datetime.fromisoformat(read["received_at"])
    assert 0 <= (retrieved - received).total_seconds() <= 10
    assert result["real_model_executed"] is False
    assert result["live_provider_reads"] == 0
    assert result["blocked_operations"] == []
    assert result["semantic_review"]["automatically_accepted"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["google_routes", "mapbox"])
@pytest.mark.parametrize("mode", ["walk", "bicycle"])
async def test_nontraffic_routes_are_estimates_without_a_traffic_timestamp(
    monkeypatch, provider, mode,
):
    monkeypatch.setenv("ROUTING_PROVIDER", provider)
    monkeypatch.setenv("ROUTING_API_KEY", "synthetic-route-provenance")
    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(runner._scripted_reply), **kwargs),
    )
    route = await routing.get_route(
        origin=runner.ORIGIN, destination=runner.DESTINATION, travel_mode=mode,
    )
    assert route["available"] is True
    assert route["duration_seconds"] == 900
    assert route["duration_kind"] == "estimate"
    assert route["provider_as_of"] is None
    assert route["reflects_current_traffic"] is False
    assert route["retrieval_time_source"] == "ora_clock_not_provider_observation_time"
    assert datetime.fromisoformat(route["retrieved_at"]).utcoffset().total_seconds() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["google_routes", "mapbox"])
async def test_failed_provider_read_does_not_acquire_success_provenance(monkeypatch, provider):
    monkeypatch.setenv("ROUTING_PROVIDER", provider)
    monkeypatch.setenv("ROUTING_API_KEY", "synthetic-route-provenance")
    client = httpx.AsyncClient
    requests = []

    def unavailable(request):
        requests.append(request)
        return httpx.Response(503, json={"error": "synthetic unavailable"}, request=request)

    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(unavailable), **kwargs),
    )
    route = await routing.get_route(origin=runner.ORIGIN, destination=runner.DESTINATION)
    assert route["available"] is False
    assert route["failure_code"] == "ROUTING_HTTP_503"
    assert route["retryable"] is True
    assert not PROVENANCE_KEYS.intersection(route)
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_no_configured_provider_has_no_estimate_or_retrieval_timestamp(monkeypatch):
    monkeypatch.delenv("ROUTING_PROVIDER", raising=False)
    monkeypatch.delenv("ROUTING_API_KEY", raising=False)
    route = await routing.get_route(origin=runner.ORIGIN, destination=runner.DESTINATION)
    assert route["available"] is False
    assert route["failure_code"] == "ROUTING_NOT_CONFIGURED"
    assert not PROVENANCE_KEYS.intersection(route)
