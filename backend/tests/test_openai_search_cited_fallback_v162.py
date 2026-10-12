"""Optional Responses web search fallback: simulated HTTP only, no real billing."""
import copy
import logging
from unittest.mock import AsyncMock

import httpx
import pytest

from conversation_engine.ai_core.tools import web_search
from conversation_engine.ai_core.tools.providers import openai_search
from conversation_engine.ai_core.tools.providers.base import ProviderResult


def fixture_response():
    return {
        "status": "completed",
        "output": [
            {"type": "web_search_call", "status": "completed",
             "action": {"type": "search", "sources": [{"type": "url", "url": "https://example.org/source"}]}},
            {"type": "message", "status": "completed", "content": [{
                "type": "output_text",
                "text": "Cited factual segment. UNCITED_MODEL_PROSE",
                "annotations": [
                    {"type": "url_citation", "start_index": 0, "end_index": 22,
                     "url": "https://example.org/source", "title": "Synthetic public source"},
                    {"type": "url_citation", "start_index": 23, "end_index": 43,
                     "url": "https://localhost/private", "title": "Forbidden"},
                ],
            }]},
        ],
    }


def enable(monkeypatch):
    monkeypatch.setenv("OPENAI_WEB_SEARCH_ENABLED", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-provider-key")
    monkeypatch.setenv("OPENAI_WEB_SEARCH_MODEL", "gpt-4.1-mini")
    monkeypatch.setattr(openai_search, "_retry_after", 0.0)


def mock_http(monkeypatch, *, status_code=200, json_payload=None, seen=None):
    calls = seen if seen is not None else []
    async def post(client, url, **kwargs):
        calls.append({"url": url, **kwargs})
        req = httpx.Request("POST", url)
        return httpx.Response(status_code, json=json_payload or {}, request=req)
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    return calls


def test_provider_is_not_enabled_by_a_key_alone(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-provider-key")
    monkeypatch.delenv("OPENAI_WEB_SEARCH_ENABLED", raising=False)
    assert not openai_search.configured()
    monkeypatch.setenv("OPENAI_WEB_SEARCH_ENABLED", "0")
    assert not openai_search.configured()
    monkeypatch.setenv("OPENAI_WEB_SEARCH_ENABLED", "1")
    assert openai_search.configured()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert not openai_search.configured()


def test_cited_response_returns_only_attached_grounded_segments_and_safe_urls():
    original = fixture_response()
    payload = copy.deepcopy(original)
    hits = openai_search._extract_hits(payload, max_results=5)
    assert [hit.url for hit in hits] == ["https://example.org/source"]
    assert hits[0].snippet == "Cited factual segment."
    assert hits[0].snippet_origin == "grounded_model_segment"
    assert "UNCITED_MODEL_PROSE" not in str(hits)
    assert original == payload
    payload["output"][0]["status"] = "in_progress"
    assert openai_search._extract_hits(payload, max_results=5) == []
    payload["output"][0]["status"] = "completed"
    payload["status"] = "incomplete"
    assert openai_search._extract_hits(payload, max_results=5) == []


@pytest.mark.parametrize("url", [
    "http://localhost/admin", "https://127.0.0.1/private",
    "https://192.168.1.5/secret", "https://user:password@example.org/path",
    "file:///etc/passwd", "https://example.internal/x",
    "https://example.org:4444/internal",
])
def test_private_or_credential_bearing_citations_are_rejected(url):
    assert not openai_search._public_url(url)


@pytest.mark.asyncio
async def test_api_contract_and_provenance_are_bounded_by_annotated_citations(monkeypatch):
    enable(monkeypatch)
    seen = mock_http(monkeypatch, json_payload=fixture_response())
    result = await openai_search.search("Synthetic public research.", max_results=2)
    assert result.ok and result.provider == "openai_search"
    assert len(result.hits) == 1 and result.raw_answer is None
    assert len(seen) == 1 and seen[0]["url"] == "https://api.openai.com/v1/responses"
    payload = seen[0]["json"]
    assert payload["store"] is False
    assert payload["tool_choice"] == "required"
    assert payload["tools"] == [{"type": "web_search", "search_context_size": "low"}]
    assert payload["include"] == ["web_search_call.action.sources"]
    assert payload["max_output_tokens"] <= 750
    assert payload["model"] == "gpt-4.1-mini"
    assert seen[0]["headers"]["Authorization"] == "Bearer synthetic-provider-key"


@pytest.mark.asyncio
async def test_model_only_answer_and_uncited_sources_are_not_invented_as_evidence(monkeypatch):
    enable(monkeypatch)
    payload = fixture_response()
    payload["output"][1]["content"][0]["annotations"] = []
    mock_http(monkeypatch, json_payload=payload)
    result = await openai_search.search("Synthetic question")
    assert not result.ok and result.hits == [] and result.failure_code == "INVALID_RESPONSE"


@pytest.mark.asyncio
async def test_402_uses_provider_only_cooldown_without_leaking_secrets(monkeypatch, caplog):
    enable(monkeypatch)
    clock = [100.0]
    monkeypatch.setattr(openai_search, "_clock", lambda: clock[0])
    seen = mock_http(monkeypatch, status_code=402, json_payload={"error": "PRIVATE_TOKEN_SHOULD_NOT_APPEAR"})
    with caplog.at_level(logging.INFO):
        first = await openai_search.search("Synthetic")
        blocked = await openai_search.search("Another synthetic")
        clock[0] += openai_search._QUOTA_RETRY_SECONDS + 1
        third = await openai_search.search("Synthetic")
    assert [first.failure_code, blocked.failure_code, third.failure_code] == [
        "QUOTA_EXHAUSTED", "QUOTA_EXHAUSTED", "QUOTA_EXHAUSTED",
    ]
    assert len(seen) == 2
    assert "PRIVATE_TOKEN" not in caplog.text


@pytest.mark.asyncio
async def test_existing_search_providers_win_without_billed_fallback(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setattr(web_search.tavily, "configured", lambda: True)
    monkeypatch.setattr(web_search.brave, "configured", lambda: False)
    monkeypatch.setattr(web_search.gemini_search, "configured", lambda: True)
    calls = []

    async def free_ok(query, *, max_results):
        calls.append("tavily")
        from conversation_engine.ai_core.tools.providers.base import RawHit
        return ProviderResult(ok=True, provider="tavily",
                              hits=[RawHit(url="https://example.org/first")])
    monkeypatch.setattr(web_search.tavily, "search", free_ok)
    monkeypatch.setattr(web_search.gemini_search, "search", AsyncMock(
        side_effect=AssertionError("Gemini should not run")))
    monkeypatch.setattr(openai_search, "search", AsyncMock(
        side_effect=AssertionError("Billed fallback must not run")))
    result = await web_search._failover_search("Synthetic query", max_results=3)
    assert result.ok and result.provider == "tavily" and calls == ["tavily"]


@pytest.mark.asyncio
async def test_quota_exhaustion_fails_over_to_cited_openai_search_only_when_opted_in(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setattr(web_search.tavily, "configured", lambda: False)
    monkeypatch.setattr(web_search.brave, "configured", lambda: False)
    monkeypatch.setattr(web_search.gemini_search, "configured", lambda: True)
    monkeypatch.setattr(web_search.gemini_search, "search", AsyncMock(return_value=ProviderResult(
        ok=False, provider="gemini_search", failure_code="QUOTA_EXHAUSTED")))
    fallback = AsyncMock(return_value=ProviderResult(
        ok=True, provider="openai_search", hits=openai_search._extract_hits(
            fixture_response(), max_results=2)))
    monkeypatch.setattr(openai_search, "search", fallback)
    result = await web_search._failover_search("Public synthetic query", max_results=2)
    assert result.ok and result.provider == "openai_search"
    fallback.assert_awaited_once_with("Public synthetic query", max_results=2)
    monkeypatch.setenv("OPENAI_WEB_SEARCH_ENABLED", "0")
    fallback.reset_mock()
    failure = await web_search._failover_search("Public synthetic query", max_results=2)
    assert not failure.ok and failure.failure_code == "QUOTA_EXHAUSTED"
    fallback.assert_not_awaited()
