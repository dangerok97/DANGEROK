"""Real pinned Gemini SDK and production adapter, fake HTTP only.

These checks attest the evaluator's transport boundary and request budget;
they do not execute or attest a real model response, provider or account.
"""
from contextlib import ExitStack
import json

import aiohttp
from google import genai
from google.genai import _api_client, types
import httpx
from mongomock_motor import AsyncMongoMockClient
import pytest

from scripts import autonomy_completion_eval_v162 as autonomy
from scripts import phase1_read_provider_eval as public_reads


SYNTHETIC_KEY = "synthetic-eval-unused-credential"
REPLY = {
    "candidates": [{"content": {"role": "model", "parts": [{"text": "Synthetic response"}]},
                    "finishReason": "STOP"}],
    "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 2, "totalTokenCount": 6},
}


@pytest.fixture(autouse=True)
def no_uncontrolled_transport(monkeypatch):
    # No actual key or account discovery, even if a developer has local config.
    monkeypatch.setenv("GEMINI_API_KEY", SYNTHETIC_KEY)
    monkeypatch.setenv("GEMINI_MODEL", "gemini-evaluation-primary")
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "gemini-evaluation-alternate")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "false")
    monkeypatch.setenv("DOCUMENT_AI_TIMEOUT_S", "8")
    for name in ("GOOGLE_GEMINI_BASE_URL", "GOOGLE_VERTEX_BASE_URL", "GOOGLE_API_KEY",
                 "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)

    def fail_before_network(*args, **kwargs):
        pytest.fail("SDK attempted an uncontrolled transport; no network request was sent")

    monkeypatch.setattr(aiohttp.ClientSession, "request", fail_before_network)
    monkeypatch.setattr(httpx.Client, "send", fail_before_network)


def install_fake_transport(monkeypatch, handler):
    transports = []

    class ObservedTransport(httpx.MockTransport):
        closed = False

        async def aclose(self):
            self.closed = True
            await super().aclose()

    def factory(*args, **kwargs):
        transport = ObservedTransport(handler)
        transports.append(transport)
        return transport

    # The runner still has to select the public transport option itself.
    # Substituting its default transport is the only fake below the real SDK.
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", factory)
    return transports


@pytest.mark.asyncio
@pytest.mark.parametrize("as_dict", [False, True])
async def test_runner_selects_httpx_with_aiohttp_installed_and_preserves_options(monkeypatch, as_dict):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=REPLY)

    transports = install_fake_transport(monkeypatch, respond)
    assert _api_client.has_aiohttp is True  # Reproduces the installed SDK default.
    supplied = {
        "timeout": 12345, "api_version": "v1beta", "headers": {"x-eval-marker": "synthetic"},
        "async_client_args": {"trust_env": False, "follow_redirects": True},
        "retry_options": {"attempts": 1},
    }
    options = supplied if as_dict else types.HttpOptions(**supplied)
    before = dict(supplied["async_client_args"])
    original_client = genai.Client
    boundary = public_reads._ReadBoundary(model_live=True, provider_reply=None)
    with ExitStack() as stack:
        boundary.install(stack)
        client = genai.Client(api_key=SYNTHETIC_KEY, http_options=options)
        try:
            assert client._api_client._use_aiohttp() is False
            token = boundary.scope.set("model")
            try:
                result = await client.aio.models.generate_content(
                    model="gemini-evaluation-primary", contents="Synthetic source only",
                )
            finally:
                boundary.scope.reset(token)
            assert result.text == "Synthetic response"
        finally:
            await client.aio.aclose()
            client.close()
    assert genai.Client is original_client
    assert len(requests) == 1 and requests[0].url.host == "generativelanguage.googleapis.com"
    assert requests[0].extensions["timeout"]["read"] == pytest.approx(12.345)
    assert requests[0].headers["x-eval-marker"] == "synthetic"
    assert supplied["async_client_args"] == before
    if not as_dict:
        assert options.async_client_args == before and options.timeout == 12345
    assert transports and all(transport.closed for transport in transports)
    assert boundary.blocked == boundary.reads == []


@pytest.mark.asyncio
@pytest.mark.parametrize("scope,live,base_url", [
    ("blocked", True, None),
    ("model", False, None),
    ("model", True, "https://example.invalid"),
])
async def test_real_sdk_disallowed_request_is_blocked_before_transport(
    monkeypatch, caplog, scope, live, base_url,
):
    transported = []

    def respond(request):
        transported.append(request.url.host)
        return httpx.Response(200, json=REPLY)

    install_fake_transport(monkeypatch, respond)
    boundary = public_reads._ReadBoundary(model_live=live, provider_reply=None)
    with ExitStack() as stack:
        boundary.install(stack)
        client = genai.Client(api_key=SYNTHETIC_KEY, http_options={"base_url": base_url})
        try:
            assert client._api_client._use_aiohttp() is False
            token = boundary.scope.set(scope)
            try:
                with pytest.raises(public_reads.EvaluationBoundaryError, match="^EVAL_HTTP_NOT_ALLOWLISTED$") as caught:
                    await client.aio.models.generate_content(
                        model="gemini-evaluation-primary", contents="Synthetic source only",
                    )
            finally:
                boundary.scope.reset(token)
        finally:
            await client.aio.aclose()
            client.close()
    assert transported == [] and boundary.reads == []
    assert boundary.blocked == ["EVAL_HTTP_NOT_ALLOWLISTED"]
    assert SYNTHETIC_KEY not in str(caught.value) + caplog.text + json.dumps(boundary.blocked)


@pytest.mark.asyncio
async def test_real_sdk_cannot_follow_an_allowed_endpoint_redirect(monkeypatch):
    transported = []

    def redirect(request):
        transported.append(request.url.host)
        return httpx.Response(302, headers={"location": "https://example.invalid/forbidden"},
                              json={"error": {"code": 302, "message": "Synthetic redirect"}})

    install_fake_transport(monkeypatch, redirect)
    boundary = public_reads._ReadBoundary(model_live=True, provider_reply=None)
    with ExitStack() as stack:
        boundary.install(stack)
        client = genai.Client(api_key=SYNTHETIC_KEY, http_options={
            "async_client_args": {"follow_redirects": True},
        })
        try:
            token = boundary.scope.set("model")
            try:
                with pytest.raises(genai.errors.APIError) as caught:
                    await client.aio.models.generate_content(
                        model="gemini-evaluation-primary", contents="Synthetic source only",
                    )
                assert caught.value.code == 302
            finally:
                boundary.scope.reset(token)
        finally:
            await client.aio.aclose()
            client.close()
    assert transported == ["generativelanguage.googleapis.com"]


@pytest.mark.asyncio
@pytest.mark.parametrize("fallback", [False, True])
async def test_production_gemini_adapter_uses_the_autonomy_http_counter_and_budget(
    monkeypatch, caplog, fallback,
):
    from llm.manager import ProviderManager
    from llm.providers.gemini import GeminiProvider

    transported = []

    def respond(request):
        transported.append(request.url.host)
        if fallback:
            return httpx.Response(503, json={"error": {
                "code": 503, "status": "UNAVAILABLE", "message": SYNTHETIC_KEY,
            }})
        return httpx.Response(200, json=REPLY)

    transports = install_fake_transport(monkeypatch, respond)

    async def real_adapter(self, **kwargs):
        return await GeminiProvider().chat(**kwargs)

    # Choose the real production adapter without invoking unrelated configured
    # providers. Its SDK, request, alternate-model loop and close are unchanged.
    monkeypatch.setattr(ProviderManager, "chat", real_adapter)
    monkeypatch.setattr(autonomy, "MAX_MODEL_HTTP_REQUESTS", 1)
    db = AsyncMongoMockClient().v162_gemini_transport_only
    with autonomy.isolated_engine(db, mode="live") as probe:
        if fallback:
            with pytest.raises(autonomy.EvaluationFailure, match="^MODEL_HTTP_BOUND_EXCEEDED$"):
                await ProviderManager.chat(object(), system="Synthetic test", user="Synthetic source")
            assert probe.network.blocked == ["MODEL_HTTP_BOUND_EXCEEDED"]
            assert probe.model_calls == []
        else:
            result = await ProviderManager.chat(object(), system="Synthetic test", user="Synthetic source")
            assert result.text == "Synthetic response"
            assert probe.model_calls[0]["provider"] == "gemini"
            assert probe.model_calls[0]["usage"]["total_tokens"] == 6
            assert probe.network.blocked == []
        assert probe.model_http_requests == probe.model_attempts == 1
        assert probe.network.scope.get() == "blocked"
        diagnostic = json.dumps(autonomy.model_observations(probe))
        assert SYNTHETIC_KEY not in diagnostic + caplog.text
    assert transported == ["generativelanguage.googleapis.com"]
    assert transports and all(transport.closed for transport in transports)
