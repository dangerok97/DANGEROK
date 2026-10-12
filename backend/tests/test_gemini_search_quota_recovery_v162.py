"""Search quota is a technical outage, not an absence of public evidence.

All SDK responses and search results are synthetic; no network request, real
provider credential, user content or time wait is needed by these tests.
"""
import logging
import sys
import types
from types import SimpleNamespace

import pytest

from conversation_engine.ai_core.tools import web_search
from conversation_engine.ai_core.tools.providers import gemini_search
from conversation_engine.ai_core.tools.providers.base import ProviderResult, RawHit


@pytest.mark.parametrize(("problem", "expected"), [
    ("402 Payment Required: balance exhausted", "QUOTA_EXHAUSTED"),
    ("RESOURCE_EXHAUSTED", "QUOTA_EXHAUSTED"),
    ("insufficient credit balance", "QUOTA_EXHAUSTED"),
    ("quota exhausted", "QUOTA_EXHAUSTED"),
    ("429 Too Many Requests", "RATE_LIMITED"),
    ("provider timed out", "TIMEOUT"),
    ("403 permission denied", "AUTH"),
    ("500 upstream temporarily unavailable", "PROVIDER_ERROR"),
])
def test_search_failure_classification_preserves_provider_outage_kind(problem, expected):
    assert gemini_search._failure_code(RuntimeError(problem)) == expected


def sdk_fixture(monkeypatch, results, call_log):
    """Install fake SDK modules for just one test; no real google SDK call."""
    google = types.ModuleType("google")
    genai = types.ModuleType("google.genai")
    schema = types.ModuleType("google.genai.types")

    schema.GoogleSearch = lambda: object()
    schema.GoogleSearchRetrieval = lambda: object()
    schema.Tool = lambda **fields: SimpleNamespace(**fields)
    schema.GenerateContentConfig = lambda **fields: SimpleNamespace(**fields)

    async def generate_content(**kwargs):
        call_log.append(kwargs)
        value = results.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    class FakeClient:
        def __init__(self, *, api_key):
            assert api_key == "synthetic-not-a-provider-key"
            self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))

    genai.Client, genai.types, google.genai = FakeClient, schema, genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", schema)


def grounded_response():
    return SimpleNamespace(candidates=[SimpleNamespace(grounding_metadata=SimpleNamespace(
        grounding_chunks=[SimpleNamespace(
            web=SimpleNamespace(title="Synthetic public source", uri="https://example.invalid/weather")
        )],
        grounding_supports=[],
    ))])


@pytest.mark.asyncio
async def test_402_cools_down_only_the_failed_provider_and_recovers_without_leaking_key(monkeypatch, caplog):
    monkeypatch.setenv("GEMINI_SEARCH_ENABLED", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-not-a-provider-key")
    clock = [1000.0]
    monkeypatch.setattr(gemini_search, "_clock", lambda: clock[0])
    monkeypatch.setattr(gemini_search, "_quota_retry_after", 0.0)
    calls = []
    sdk_fixture(monkeypatch, [RuntimeError("402 Payment Required PRIVATE_SECRET"), grounded_response()], calls)

    with caplog.at_level(logging.INFO):
        first = await gemini_search.search("synthetic outdoor drying conditions")
        repeated = await gemini_search.search("a different synthetic public question")
        clock[0] += gemini_search._QUOTA_RETRY_SECONDS - 0.001
        still_cooling = await gemini_search.search("another synthetic question")
        clock[0] += 0.002
        recovered = await gemini_search.search("synthetic public evidence again")

    assert [first.failure_code, repeated.failure_code, still_cooling.failure_code] == [
        "QUOTA_EXHAUSTED", "QUOTA_EXHAUSTED", "QUOTA_EXHAUSTED",
    ]
    assert len(calls) == 2
    assert recovered.ok and len(recovered.hits) == 1
    assert recovered.hits[0].url == "https://example.invalid/weather"
    assert "PRIVATE_SECRET" not in caplog.text
    assert gemini_search.configured() is True  # Configured != working.
    monkeypatch.setattr(gemini_search, "_quota_retry_after", 0.0)


@pytest.mark.asyncio
async def test_nonquota_errors_remain_immediately_retryable(monkeypatch):
    monkeypatch.setenv("GEMINI_SEARCH_ENABLED", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-not-a-provider-key")
    monkeypatch.setattr(gemini_search, "_clock", lambda: 1000.0)
    monkeypatch.setattr(gemini_search, "_quota_retry_after", 0.0)
    calls = []
    sdk_fixture(monkeypatch, [RuntimeError("429 Too Many Requests"), grounded_response()], calls)
    first = await gemini_search.search("synthetic research")
    second = await gemini_search.search("synthetic research")
    assert first.failure_code == "RATE_LIMITED"
    assert second.ok and len(calls) == 2  # No hard quota conclusion from a 429.


@pytest.mark.asyncio
async def test_search_chain_remains_free_first_and_does_not_invent_results_on_quota(monkeypatch):
    monkeypatch.setattr(web_search.tavily, "configured", lambda: True)
    monkeypatch.setattr(web_search.brave, "configured", lambda: True)
    monkeypatch.setattr(web_search.gemini_search, "configured", lambda: True)
    called = []

    async def not_configured(query, *, max_results):
        called.append("tavily")
        return ProviderResult(ok=False, provider="tavily", failure_code="NOT_CONFIGURED")

    async def brave_ok(query, *, max_results):
        called.append("brave")
        return ProviderResult(ok=True, provider="brave", hits=[
            RawHit(title="Synthetic result", url="https://example.invalid/secondary")
        ])

    async def should_not_call(query, *, max_results):
        raise AssertionError("Gemini should not be tried after a valid Brave hit")

    monkeypatch.setattr(web_search.tavily, "search", not_configured)
    monkeypatch.setattr(web_search.brave, "search", brave_ok)
    monkeypatch.setattr(web_search.gemini_search, "search", should_not_call)
    result = await web_search._failover_search("synthetic public query", max_results=2)
    assert result.ok and result.provider == "brave"
    assert called == ["tavily", "brave"]


@pytest.mark.asyncio
async def test_exhausted_only_provider_remains_an_explicit_failure_not_a_source(monkeypatch):
    monkeypatch.setattr(web_search.tavily, "configured", lambda: False)
    monkeypatch.setattr(web_search.brave, "configured", lambda: False)
    monkeypatch.setattr(web_search.gemini_search, "configured", lambda: True)

    async def quota(query, *, max_results):
        return ProviderResult(ok=False, provider="gemini_search", failure_code="QUOTA_EXHAUSTED")

    monkeypatch.setattr(web_search.gemini_search, "search", quota)
    answer = await web_search._failover_search("synthetic public question", max_results=5)
    assert not answer.ok and answer.hits == []
    assert answer.failure_code == "QUOTA_EXHAUSTED"
