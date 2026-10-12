"""Gemini's real SDK, synthetic HTTP errors, and the unchanged cooldown policy.

No account or model is contacted. These cases establish how observed protocol
metadata is classified; they do not diagnose an unrecorded live failure.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import AsyncMock

from google import genai
from google.genai import errors as sdk_errors, types
import httpx
import pytest

from llm.base import LLMResult
from llm.errors import (
    LLMAuthenticationError,
    LLMModelUnavailableError,
    LLMNetworkError,
    LLMQuotaError,
    LLMRateLimitError,
    retry_after_seconds,
)
from llm.manager import DEFAULT_PRIORITY, ProviderManager
from llm.providers.gemini import GeminiProvider, _map_api_error


QUOTA_TYPE = "type.googleapis.com/google.rpc.QuotaFailure"
RETRY_TYPE = "type.googleapis.com/google.rpc.RetryInfo"
RAW_MARKER = "synthetic-private-error-marker"
SYNTHETIC_KEY = "synthetic-gemini-key-unused"


def violation(quota_id=None, *, metric=None):
    value = {"description": RAW_MARKER}
    if quota_id is not None:
        value["quotaId"] = quota_id
    if metric is not None:
        value["quotaMetric"] = metric
    return value


def quota(*violations):
    return {"@type": QUOTA_TYPE, "violations": list(violations)}


def retry(delay):
    return {"@type": RETRY_TYPE, "retryDelay": delay}


def payload(details=(), *, code=429, status="RESOURCE_EXHAUSTED", message=None):
    return {"error": {
        "code": code,
        "status": status,
        "message": message or f"Quota exceeded; check billing. {RAW_MARKER}",
        "details": list(details),
    }}


async def sdk_error(body, *, code=429, headers=None):
    # Exercise the SDK's real body/wrapper normalization, without a client or
    # socket. A hand-written exception would miss its .details representation.
    response = httpx.Response(
        code, json=body, headers=headers,
        request=httpx.Request("POST", "https://synthetic.invalid/generate"),
    )
    with pytest.raises(sdk_errors.APIError) as caught:
        await sdk_errors.APIError.raise_for_async_response(response)
    return caught.value


@pytest.mark.asyncio
@pytest.mark.parametrize("details,expected_type,expected_retry", [
    pytest.param([
        quota(violation("GenerateRequestsPerMinutePerProjectPerModel")), retry("9s"),
    ], LLMRateLimitError, 9.0, id="requests-per-minute"),
    pytest.param([
        quota(violation("GenerateContentInputTokensPerModelPerMinute")), retry("90s"),
    ], LLMRateLimitError, 90.0, id="tokens-per-minute-90-seconds"),
    pytest.param([
        quota(violation("GenerateRequestsPerSecondPerProject")), retry("1.5s"),
    ], LLMRateLimitError, 1.5, id="requests-per-second"),
    pytest.param([
        quota(violation("GenerateRequestsPerDayPerProjectPerModel")), retry("9s"),
    ], LLMQuotaError, 9.0, id="day-prevails-over-short-retry"),
    pytest.param([
        quota(violation(metric="generativelanguage.googleapis.com/generate_requests_per_day")),
    ], LLMQuotaError, None, id="explicit-day-metric"),
    pytest.param([
        quota(violation("GenerateRequestsPerMinute"), violation("GenerateRequestsPerDay")),
        retry("90s"),
    ], LLMQuotaError, 90.0, id="mixed-minute-then-day"),
    pytest.param([
        quota(violation("GenerateRequestsPerDay")),
        quota(violation("GenerateRequestsPerMinute")), retry("9s"),
    ], LLMQuotaError, 9.0, id="mixed-day-then-minute"),
    pytest.param([], LLMRateLimitError, None, id="generic-quota-wording-is-not-daily"),
    pytest.param([retry("12s")], LLMRateLimitError, 12.0, id="retry-without-quota-detail"),
    pytest.param([
        {"@type": "type.googleapis.com/other.QuotaFailure", "violations": [
            violation("GenerateRequestsPerDay"),
        ]},
    ], LLMRateLimitError, None, id="unrecognized-detail-type"),
    pytest.param([
        quota({"description": "Daily quota exceeded", "subject": "GenerateRequestsPerDay"}),
    ], LLMRateLimitError, None, id="description-is-not-period-metadata"),
    pytest.param([
        quota(violation("GenerateRequestsPerDaysUnknown")),
    ], LLMRateLimitError, None, id="period-must-be-a-complete-token"),
    pytest.param([
        None, "GenerateRequestsPerDay", {"@type": QUOTA_TYPE, "violations": {}},
        quota(None, "GenerateRequestsPerDay", violation(["GenerateRequestsPerDay"])),
    ], LLMRateLimitError, None, id="malformed-violations-are-not-daily"),
])
async def test_sdk_quota_metadata_controls_429_without_message_inference(
    details, expected_type, expected_retry,
):
    error = await sdk_error(payload(details))
    mapped = _map_api_error(error)
    assert type(mapped) is expected_type
    assert mapped.retry_after == expected_retry
    assert str(mapped) == mapped.kind
    assert vars(mapped) == {"retry_after": expected_retry}
    assert RAW_MARKER not in str(mapped)


@pytest.mark.asyncio
@pytest.mark.parametrize("wrapper", ["direct", "error", "singleton-list"])
async def test_sdk_supported_wrappers_preserve_typed_details(wrapper):
    body = payload([
        quota(violation("GenerateRequestsPerDay")), retry("12.25s"),
    ])
    if wrapper == "direct":
        body = body["error"]
    elif wrapper == "singleton-list":
        body = [body]
    error = await sdk_error(body)
    assert isinstance(error.details, dict)  # The SDK unwraps its singleton list.
    mapped = _map_api_error(error)
    assert type(mapped) is LLMQuotaError
    assert mapped.retry_after == 12.25


@pytest.mark.asyncio
@pytest.mark.parametrize("delay,expected", [
    ("0s", 0.0), ("9s", 9.0), ("90s", 90.0),
    ("1.123456789s", 1.123456789), ("9999s", 300.0),
    ("-1s", None), ("NaNs", None), ("Infinitys", None),
    ("1e2s", None), ("1.1234567890s", None), ("90", None),
    (" 9s", None), ("9s\n", None), (9, None), (True, None),
    ({"seconds": 9}, None), (None, None), ("9" * 400 + "s", None),
])
async def test_retry_info_requires_a_finite_nonnegative_json_duration(delay, expected):
    error = await sdk_error(payload([retry(delay)]))
    assert retry_after_seconds(error) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("detail", [
    {"retryDelay": "90s"},
    {"@type": "google.rpc.RetryInfo", "retryDelay": "90s"},
    {"@type": "type.googleapis.com/other.RetryInfo", "retryDelay": "90s"},
    {"@type": RETRY_TYPE, "retry_delay": "90s"},
    {"@type": RETRY_TYPE},
])
async def test_untyped_or_malformed_retry_details_are_ignored(detail):
    error = await sdk_error(payload([detail]))
    assert retry_after_seconds(error) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("details,header,expected", [
    ([retry("90s")], "12", 90.0),
    ([retry("9s")], "12", 12.0),
    ([retry("90s")], "not-a-delay", 90.0),
    ([retry("not-a-duration")], "12", 12.0),
    ([retry("9s"), retry("90s")], None, 90.0),
    ([retry("90s")], "9999", 300.0),
    ([], "12", 12.0),
    ([], "-2", 0.0),
])
async def test_header_and_retry_info_keep_the_longest_valid_bounded_hint(details, header, expected):
    error = await sdk_error(payload(details), headers={"Retry-After": header} if header else None)
    assert retry_after_seconds(error) == expected


@pytest.mark.asyncio
async def test_http_date_and_header_only_errors_keep_the_existing_contract():
    target = datetime.now(timezone.utc) + timedelta(seconds=60)
    error = await sdk_error(payload(), headers={"Retry-After": format_datetime(target, usegmt=True)})
    assert 58 <= retry_after_seconds(error) <= 60
    # Other adapters also call this helper with an ordinary exception + headers.
    header_only = RuntimeError("synthetic")
    header_only.headers = {"Retry-After": "45"}
    assert retry_after_seconds(header_only) == 45.0
    assert retry_after_seconds(header_only, maximum=20.0) == 20.0
    rpc_only = await sdk_error(payload([retry("90s")]))
    assert retry_after_seconds(rpc_only, maximum=20.0) == 20.0


@pytest.mark.asyncio
@pytest.mark.parametrize("code,status,message,expected_type", [
    (401, "UNAUTHENTICATED", "Unauthenticated", LLMAuthenticationError),
    (403, "PERMISSION_DENIED", "Permission denied: quota", LLMAuthenticationError),
    (404, "NOT_FOUND", "Model not found", LLMModelUnavailableError),
    (503, "UNAVAILABLE", "Temporarily unavailable", LLMNetworkError),
    (400, "RESOURCE_EXHAUSTED", "Quota exhausted", LLMQuotaError),
])
async def test_non_429_and_auth_classification_is_unchanged(code, status, message, expected_type):
    error = await sdk_error(payload(code=code, status=status, message=message), code=code)
    assert type(_map_api_error(error)) is expected_type


def install_sdk_http(monkeypatch, handler):
    """Keep SDK parsing and adapter control flow real; replace HTTP only."""
    real_client = genai.Client
    clients = []
    monkeypatch.setenv("GEMINI_API_KEY", SYNTHETIC_KEY)
    monkeypatch.setenv("GEMINI_MODEL", "gemini-synthetic-primary")
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "gemini-synthetic-alternate")

    def fail_before_network(*args, **kwargs):
        pytest.fail("Unexpected real HTTP transport; nothing was sent")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", fail_before_network)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fail_before_network)

    def create_client(*, api_key):
        assert api_key == SYNTHETIC_KEY
        client = real_client(api_key=api_key, vertexai=False, http_options=types.HttpOptions(
            base_url="https://synthetic.invalid",
            client_args={"transport": httpx.MockTransport(handler), "trust_env": False},
            async_client_args={"transport": httpx.MockTransport(handler), "trust_env": False},
            retry_options={"attempts": 1},
        ))
        clients.append(client)
        return client

    monkeypatch.setattr(genai, "Client", create_client)
    return clients


@pytest.mark.asyncio
@pytest.mark.parametrize("override", [None, "gemini-explicit-alternate"])
async def test_real_sdk_404_uses_current_default_alternate_or_explicit_override(monkeypatch, override):
    requested_models = []

    def respond(request):
        assert request.url.host == "synthetic.invalid"
        model = request.url.path.rsplit("/", 1)[-1].removesuffix(":generateContent")
        requested_models.append(model)
        if len(requested_models) == 1:
            return httpx.Response(404, json=payload(
                code=404, status="NOT_FOUND", message="Synthetic model not found",
            ))
        return httpx.Response(200, json={"candidates": [{
            "content": {"parts": [{"text": "Synthetic alternate answer"}], "role": "model"},
            "finishReason": "STOP",
        }]})

    clients = install_sdk_http(monkeypatch, respond)
    if override:
        monkeypatch.setenv("GEMINI_FALLBACK_MODEL", override)
    else:
        monkeypatch.delenv("GEMINI_FALLBACK_MODEL")
    try:
        result = await GeminiProvider().chat(system="Synthetic system", user="Synthetic input")
        expected = override or "gemini-3.6-flash"
        assert requested_models == ["gemini-synthetic-primary", expected]
        assert result.provider == "gemini" and result.model == expected
        assert result.text == "Synthetic alternate answer"
        assert result.usage["fallback_used"] is True
        assert result.usage["models_tried"] == requested_models
    finally:
        for client in clients:
            await client.aio.aclose()
            client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("period,delay,expected_cooldowns", [
    ("Minute", "9s", [9, 9, 9, 9, 9]),
    ("Minute", "90s", [90, 90, 90, 90, 90]),
    ("Day", "9s", [60, 240, 960, 3840, 7200]),
])
async def test_real_adapter_and_manager_observe_retry_without_inventing_daily_escalation(
    monkeypatch, caplog, period, delay, expected_cooldowns,
):
    requests = []
    allow_success = [False]

    def respond(request):
        requests.append(request)
        assert request.url.host == "synthetic.invalid"
        if allow_success[0]:
            return httpx.Response(200, json={"candidates": [{
                "content": {"parts": [{"text": "Synthetic answer"}], "role": "model"},
                "finishReason": "STOP",
            }]})
        return httpx.Response(429, json=payload([
            quota(violation(f"GenerateRequestsPer{period}PerProjectPerModel")), retry(delay),
        ]))

    clients = install_sdk_http(monkeypatch, respond)
    manager = ProviderManager()
    now = [100.0]
    manager._clock = lambda: now[0]
    for name in DEFAULT_PRIORITY:
        monkeypatch.setattr(manager.get(name), "is_configured", lambda name=name: name in {"gemini", "groq"})
    fallback = AsyncMock(return_value=LLMResult(text="Synthetic fallback", provider="groq"))
    monkeypatch.setattr(manager.get("groq"), "chat", fallback)
    assert isinstance(manager.get("gemini"), GeminiProvider)

    try:
        for attempt, expected in enumerate(expected_cooldowns, start=1):
            result = await manager.chat(system="Synthetic system", user="Synthetic input", user_preference="gemini")
            assert result.provider == "groq"
            assert len(requests) == attempt  # No alternate model or SDK retry on 429.
            runtime = manager._runtime["gemini"]
            assert runtime.cooldown_until - now[0] == expected
            assert runtime.consecutive_failures == attempt
            assert runtime.failure_kind == ("quota" if period == "Day" else "rate_limit")
            again = await manager.chat(system="Synthetic system", user="Synthetic input", user_preference="gemini")
            assert again.provider == "groq" and len(requests) == attempt
            now[0] = runtime.cooldown_until - 0.001
            assert await manager._available("gemini") is False
            now[0] = runtime.cooldown_until
            assert await manager._available("gemini") is True

        allow_success[0] = True
        result = await manager.chat(system="Synthetic system", user="Synthetic input", user_preference="gemini")
        assert result.provider == "gemini" and result.text == "Synthetic answer"
        assert len(requests) == len(expected_cooldowns) + 1
        assert manager._runtime["gemini"].consecutive_failures == 0
        assert manager.runtime_snapshot("gemini") == {"runtime_state": "healthy", "failure_kind": None}
        assert RAW_MARKER not in caplog.text and SYNTHETIC_KEY not in caplog.text
    finally:
        for client in clients:
            await client.aio.aclose()
            client.close()
