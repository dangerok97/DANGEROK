"""Real provider adapters must preserve explicit, read-only retry outcomes.

Only HTTP transport, synthetic places/location and model decisions are
controlled. The adapters, capability handlers, outcome classifier and the
cross-turn cognitive loop remain real; no provider credentials are used.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.loop import (
    _required_skill_plan_satisfied,
    _retryable_failed_skill_caps,
    _skill_outcome_class,
    _skill_outcome_summary,
    run_cognitive_loop,
)
from conversation_engine.ai_core.tools import weather_caps
from conversation_engine.models import ConversationSession
from location.models import PresenceContext
from places import caps, routing
import weather


OWNER = "synthetic-provider-retry-owner"
PRIVATE_DETAIL = "provider-private-detail-should-never-reach-observation"


@pytest.fixture
def runtime(monkeypatch):
    from home.service import HomeService
    from location.service import LocationService

    monkeypatch.setenv("AI_CORE_TRACE", "1")
    monkeypatch.setenv("WEATHER_PROVIDER", "open_meteo")
    monkeypatch.setenv("ROUTING_API_KEY", "synthetic-test-token")
    monkeypatch.setattr(
        HomeService, "_where_they_are",
        AsyncMock(return_value=(42.25, 11.76, "Luogo sintetico")),
    )
    monkeypatch.setattr(
        LocationService, "build_presence", AsyncMock(return_value=PresenceContext(
            user_id=OWNER, freshness="CURRENT",
            latitude=42.25, longitude=11.76,
            source="foreground_device", preference="while_using",
            permission_state="granted_foreground",
            last_seen_at=datetime.now(timezone.utc).isoformat(),
        )),
    )
    resolution = SimpleNamespace(
        resolved=True, candidates=[], reason=None,
        place=SimpleNamespace(
            label="Biblioteca sintetica",
            coordinates=SimpleNamespace(
                precise=lambda: {"latitude": 41.9, "longitude": 12.5},
            ),
        ),
    )
    monkeypatch.setattr(caps, "_service", lambda _: SimpleNamespace(
        resolve_destination=AsyncMock(return_value=resolution),
    ))
    return {
        "user_id": OWNER,
        "db": AsyncMongoMockClient().phase1_real_provider_retry,
        "platform": "web",
    }


def _transport(monkeypatch, respond):
    requests = []
    real_client = httpx.AsyncClient

    def handle(request):
        requests.append(request)
        return respond(request)

    def client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handle)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    return requests


async def _invoke(provider, runtime, monkeypatch):
    if provider == "open_meteo":
        return await weather_caps.get_weather_forecast({}, runtime)
    monkeypatch.setenv("ROUTING_PROVIDER", provider)
    return await caps.get_route(
        {"destination": "Biblioteca sintetica", "travel_mode": "drive"}, runtime,
    )


def _assert_failed(obs, *, retryable, code):
    outcome = _skill_outcome_summary(obs.name, obs)
    assert _skill_outcome_class(outcome) == "failed"
    assert outcome["failure_kind"] == code
    assert outcome["retryable"] is retryable
    assert not _required_skill_plan_satisfied([obs.name], [outcome])
    assert _retryable_failed_skill_caps([obs.name], [outcome]) == (
        [obs.name] if retryable else []
    )
    assert PRIVATE_DETAIL not in str(obs.model_dump())
    return outcome


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["google_routes", "mapbox", "open_meteo"])
@pytest.mark.parametrize("status,retryable", [
    (429, True), (500, True), (503, True),
    (400, False), (401, False), (403, False), (404, False),
])
async def test_http_failure_reaches_actual_handler_with_explicit_retry_safety(
    monkeypatch, runtime, provider, status, retryable,
):
    requests = _transport(monkeypatch, lambda _: httpx.Response(
        status, json={"error": PRIVATE_DETAIL},
    ))
    obs = await _invoke(provider, runtime, monkeypatch)
    prefix = "WEATHER" if provider == "open_meteo" else "ROUTING"
    _assert_failed(obs, retryable=retryable, code=f"{prefix}_HTTP_{status}")
    assert len(requests) == 1  # Classification never adds a hidden retry.


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["google_routes", "mapbox", "open_meteo"])
@pytest.mark.parametrize("error,code,retryable", [
    (httpx.ReadTimeout, "TIMEOUT", True),
    (httpx.ConnectError, "NETWORK_ERROR", True),
    (ValueError, "READ_FAILED", False),
])
async def test_transport_failure_is_redacted_and_only_known_transients_retry(
    monkeypatch, runtime, provider, error, code, retryable,
):
    def respond(_):
        raise error(PRIVATE_DETAIL)

    requests = _transport(monkeypatch, respond)
    obs = await _invoke(provider, runtime, monkeypatch)
    prefix = "WEATHER" if provider == "open_meteo" else "ROUTING"
    _assert_failed(obs, retryable=retryable, code=f"{prefix}_{code}")
    assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["google_routes", "mapbox", "open_meteo"])
async def test_unusable_provider_response_stays_terminal(monkeypatch, runtime, provider):
    requests = _transport(monkeypatch, lambda _: httpx.Response(
        200, json={"code": "NoRoute", "private_detail": PRIVATE_DETAIL},
    ))
    obs = await _invoke(provider, runtime, monkeypatch)
    _assert_failed(
        obs, retryable=False,
        code="WEATHER_UNAVAILABLE" if provider == "open_meteo" else "ROUTING_NO_ROUTE",
    )
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_configuration_and_unsupported_reads_never_request_retry(monkeypatch, runtime):
    def unexpected_request(_):
        pytest.fail("A disabled or unsupported provider must not make an HTTP call")

    requests = _transport(monkeypatch, unexpected_request)
    monkeypatch.delenv("ROUTING_API_KEY")
    monkeypatch.setenv("ROUTING_PROVIDER", "google_routes")
    route = await caps.get_route({"destination": "Biblioteca sintetica"}, runtime)
    _assert_failed(route, retryable=False, code="ROUTING_NOT_CONFIGURED")

    monkeypatch.setenv("WEATHER_PROVIDER", "none")
    weather_obs = await weather_caps.get_weather_forecast({}, runtime)
    _assert_failed(weather_obs, retryable=False, code="WEATHER_NOT_CONFIGURED")

    monkeypatch.setenv("ROUTING_API_KEY", "synthetic-test-token")
    monkeypatch.setenv("ROUTING_PROVIDER", "mapbox")
    route = await caps.get_route(
        {"destination": "Biblioteca sintetica", "travel_mode": "transit"}, runtime,
    )
    _assert_failed(route, retryable=False, code="ROUTING_UNSUPPORTED_MODE")
    assert not requests


@pytest.mark.asyncio
async def test_current_weather_also_exposes_transient_failure(monkeypatch):
    monkeypatch.setenv("WEATHER_PROVIDER", "open_meteo")
    requests = _transport(monkeypatch, lambda _: httpx.Response(503, text=PRIVATE_DETAIL))
    result = await weather.now_at(lat=42.25, lon=11.76)
    assert result["available"] is False
    assert result["failure_code"] == "WEATHER_HTTP_503"
    assert result["retryable"] is True
    assert PRIVATE_DETAIL not in str(result)
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_weather_keeps_dates_across_midnight_and_provider_clock(monkeypatch, runtime):
    response = {
        "timezone": "Europe/Rome", "utc_offset_seconds": 7200,
        "current": {
            "time": "2026-10-08T23:45", "weather_code": 2,
            "temperature_2m": 21,
        },
        "hourly": {
            "time": ["2026-10-08T23:00", "2026-10-09T00:00", "2026-10-09T01:00"],
            "temperature_2m": [21, 20, 19],
            "relative_humidity_2m": [65, 70, 75],
            "wind_speed_10m": [12, 11, 10],
            "precipitation_probability": [10, 30, 60],
            "weather_code": [2, 2, 3],
        },
    }
    requests = _transport(monkeypatch, lambda _: httpx.Response(200, json=response))
    started = datetime.now(timezone.utc)
    obs = await weather_caps.get_weather_forecast({}, runtime)
    ended = datetime.now(timezone.utc)
    assert obs.status == "ok"
    assert obs.payload["provider"] == "open_meteo"
    assert obs.payload["observed_at"] == "2026-10-08T23:45"
    assert obs.payload["timezone"] == "Europe/Rome"
    assert obs.payload["utc_offset_seconds"] == 7200
    retrieved = datetime.fromisoformat(obs.payload["retrieved_at"])
    assert retrieved.utcoffset().total_seconds() == 0
    assert started <= retrieved <= ended
    assert [row["time"] for row in obs.payload["hours"]] == ["00:00", "01:00"]
    assert [row["datetime"] for row in obs.payload["hours"]] == [
        "2026-10-09T00:00", "2026-10-09T01:00",
    ]
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_weather_missing_source_timestamps_are_not_replaced_with_fetch_time(
    monkeypatch, runtime,
):
    requests = _transport(monkeypatch, lambda _: httpx.Response(200, json={
        "current": {"weather_code": 2, "temperature_2m": 21},
    }))
    actual = await weather_caps.get_weather_forecast({}, runtime)
    assert actual.status == "ok"
    assert actual.payload["retrieved_at"]
    assert actual.payload["observed_at"] is None
    assert actual.payload["timezone"] is None
    assert actual.payload["utc_offset_seconds"] is None
    assert len(requests) == 1

    # Older callers/fixtures can still provide the existing display-only shape.
    monkeypatch.setattr(weather, "forecast_at", AsyncMock(return_value={
        "available": True, "condition_label": "Sereno", "temperature_c": 21,
        "hours": [{"time": "12:00", "rain_chance_pct": 15}],
    }))
    legacy = await weather_caps.get_weather_forecast({}, runtime)
    assert legacy.status == "ok"
    assert legacy.payload["current"]["temperature_c"] == 21
    assert legacy.payload["hours"][0]["time"] == "12:00"
    assert legacy.payload["hours"][0]["datetime"] is None
    assert legacy.payload["provider"] is None
    assert legacy.payload["retrieved_at"] is None
    assert legacy.payload["observed_at"] is None


def _weather_response():
    return {
        "current": {
            "time": datetime.now(timezone.utc).isoformat(),
            "weather_code": 2, "temperature_2m": 21,
            "relative_humidity_2m": 65, "wind_speed_10m": 12,
            "precipitation": 0,
        },
    }


def _tool_decision(resume_ref=""):
    return {
        "response_mode": "tool", "reasoning_status": "needs_tool",
        "tool_call": {"capability": "get_weather_forecast", "arguments": {}},
        "situation_update": {"operation": "none"},
        "skill_plan": {
            "objective": "Leggere il meteo reale",
            "required_capabilities": ["get_weather_forecast"],
            "completion_condition": "Dati meteo verificati dal provider",
            **({"resume_plan_ref": resume_ref} if resume_ref else {}),
        },
    }


def _answer(text):
    return {
        "response_mode": "answer", "reasoning_status": "enough_information",
        "message_to_user": text, "situation_update": {"operation": "none"},
    }


@pytest.mark.asyncio
async def test_real_weather_handler_transient_failure_preserves_and_resumes_plan(
    monkeypatch, runtime,
):
    from conversation_engine.ai_core.context_broker import ContextBroker

    monkeypatch.setattr(ContextBroker, "retrieve", AsyncMock(return_value=[]))
    attempts = 0

    def respond(_):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, text=PRIVATE_DETAIL)
        return httpx.Response(200, json=_weather_response())

    requests = _transport(monkeypatch, respond)
    sess = ConversationSession(
        user_id=OWNER, meta={"ui_mode": "ai_core", "ai_core": {}},
    )
    decisions = 0

    async def first_decide(system, payload):
        nonlocal decisions
        decisions += 1
        if decisions == 1:
            return _tool_decision()
        return _answer("Il servizio meteo è temporaneamente indisponibile.")

    first = await run_cognitive_loop(
        sess=sess, user_message="Controlla il meteo reale.", db=runtime["db"],
        decision_fn=first_decide, max_steps=5,
    )
    assert first.ok
    stored = sess.meta["ai_core"]["active_skill_plan"]
    assert stored is not None
    assert _retryable_failed_skill_caps(
        stored["required_capabilities"], stored["capability_outcomes"],
    ) == ["get_weather_forecast"]
    assert not _required_skill_plan_satisfied(
        stored["required_capabilities"], stored["capability_outcomes"],
    )
    assert len(requests) == 1
    plan_ref = stored["plan_ref"]
    decisions = 0

    async def resume_decide(system, payload):
        nonlocal decisions
        decisions += 1
        if decisions == 1:
            return _tool_decision(plan_ref)
        return _answer("Il meteo è stato verificato: temperatura di 21 gradi.")

    second = await run_cognitive_loop(
        sess=sess, user_message="Riprendi il controllo del meteo.", db=runtime["db"],
        decision_fn=resume_decide, max_steps=5,
    )
    assert second.ok
    assert sess.meta["ai_core"].get("active_skill_plan") is None
    assert len(requests) == 2
    assert second.trace["skill_plan_states"]["failed"] == []
    assert PRIVATE_DETAIL not in str(sess.meta)
