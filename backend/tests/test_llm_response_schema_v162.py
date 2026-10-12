"""Optional schema transport through the existing chain; no model is contacted.

Real SDKs serialize requests to synthetic HTTP. These tests establish the
protocol boundary, not whether a model's statements follow from its sources.
"""
from __future__ import annotations

import copy
import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

from google import genai
from google.genai import types
import httpx
import openai
import pytest

from llm.base import LLMResult
from llm.errors import LLMConfigurationError, LLMNetworkError, LLMRateLimitError
from llm.manager import ProviderManager
from llm.providers.emergent import EmergentProvider
from llm.providers.gemini import GeminiProvider, GeminiSecondaryProvider
from llm.providers.groq_provider import GroqProvider
from llm.providers.mistral_provider import MistralProvider
from llm.providers.ollama import OllamaProvider
from llm.providers.openai_provider import OpenAIProvider
from research import reasoning


SCHEMA = {
    "type": "object",
    "properties": {
        "content": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["content", "evidence_ids"],
    "additionalProperties": False,
}
ANSWER = {"content": "Una bozza sintetica attribuita alla fonte.", "evidence_ids": ["evi_synthetic"]}
KEY = "synthetic-unused-key"
MODES = [pytest.param(False, False, id="plain-legacy"),
         pytest.param(True, False, id="json-legacy"),
         pytest.param(False, True, id="schema-without-json-flag")]


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("Unexpected real HTTP transport; nothing was sent")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", fail)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fail)
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    monkeypatch.delenv("LLM_MODEL", raising=False)


def expected_format(schema):
    return {"type": "json_schema", "json_schema": {
        "name": "ora_response", "strict": True, "schema": schema,
    }}


def openai_response():
    return {"id": "synthetic-response", "object": "chat.completion", "created": 0,
            "model": "synthetic-model", "choices": [{"index": 0, "finish_reason": "stop",
            "message": {"role": "assistant", "content": json.dumps(ANSWER)}}]}


def install_openai_http(monkeypatch, handler):
    original = openai.AsyncOpenAI
    clients = []

    def client(**kwargs):
        assert kwargs["api_key"] == KEY
        instance = original(**kwargs, max_retries=0, http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(handler), trust_env=False,
        ))
        clients.append(instance)
        return instance

    monkeypatch.setattr(openai, "AsyncOpenAI", client)
    return clients


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_cls,key_name,model_name,host", [
    (GroqProvider, "GROQ_API_KEY", "GROQ_MODEL", "api.groq.com"),
    (MistralProvider, "MISTRAL_API_KEY", "MISTRAL_MODEL", "api.mistral.ai"),
    (OpenAIProvider, "OPENAI_API_KEY", "OPENAI_MODEL", "api.openai.com"),
])
@pytest.mark.parametrize("json_mode,use_schema", MODES)
async def test_native_openai_compatible_sdk_preserves_schema_and_legacy_wire(
    monkeypatch, provider_cls, key_name, model_name, host, json_mode, use_schema,
):
    monkeypatch.setenv(key_name, KEY)
    monkeypatch.setenv(model_name, "synthetic-model")
    sent = []

    def respond(request):
        assert request.url.host == host
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=openai_response())

    clients = install_openai_http(monkeypatch, respond)
    schema = copy.deepcopy(SCHEMA) if use_schema else None
    try:
        result = await provider_cls().chat(
            system="Synthetic system", user="Synthetic input", json_mode=json_mode,
            response_schema=schema,
        )
        assert len(sent) == 1
        assert sent[0]["model"] == "synthetic-model"
        assert sent[0]["messages"] == [{"role": "system", "content": "Synthetic system"},
                                         {"role": "user", "content": "Synthetic input"}]
        assert sent[0].get("response_format") == (
            expected_format(SCHEMA) if use_schema else {"type": "json_object"} if json_mode else None
        )
        assert sent[0]["temperature"] == (0.2 if json_mode else 0.4)
        assert json.loads(result.text) == ANSWER
        if use_schema:
            assert schema == SCHEMA
    finally:
        for client in clients:
            await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_cls,key_name,model_name", [
    (GroqProvider, "GROQ_API_KEY", "GROQ_MODEL"),
    (MistralProvider, "MISTRAL_API_KEY", "MISTRAL_MODEL"),
])
@pytest.mark.parametrize("json_mode,use_schema", MODES)
async def test_sdk_absent_httpx_fallback_keeps_the_same_requested_contract(
    monkeypatch, provider_cls, key_name, model_name, json_mode, use_schema,
):
    monkeypatch.setenv(key_name, KEY)
    monkeypatch.setenv(model_name, "synthetic-model")
    monkeypatch.setattr(provider_cls, "_chat_openai_sdk", AsyncMock(side_effect=ImportError))
    original_client = httpx.AsyncClient
    sent = []

    def respond(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=openai_response())

    def client(**kwargs):
        return original_client(**kwargs, transport=httpx.MockTransport(respond), trust_env=False)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    result = await provider_cls().chat(system="system", user="input", json_mode=json_mode,
                                     response_schema=SCHEMA if use_schema else None)
    assert len(sent) == 1
    assert sent[0].get("response_format") == (
        expected_format(SCHEMA) if use_schema else {"type": "json_object"} if json_mode else None
    )
    assert json.loads(result.text) == ANSWER


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_cls", [GeminiProvider, GeminiSecondaryProvider])
@pytest.mark.parametrize("json_mode,use_schema", MODES)
async def test_current_gemini_sdk_sends_json_schema_without_endpoint_or_model_change(
    monkeypatch, provider_cls, json_mode, use_schema,
):
    monkeypatch.setenv(provider_cls.key_env, KEY)
    monkeypatch.setenv("GEMINI_MODEL", "gemini-synthetic-primary")
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "gemini-synthetic-alternate")
    original_client = genai.Client
    clients, sent = [], []

    def respond(request):
        assert request.url.host == "synthetic.invalid"
        assert request.url.path.endswith("gemini-synthetic-primary:generateContent")
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {
            "role": "model", "parts": [{"text": json.dumps(ANSWER)}],
        }}]})

    def client(*, api_key):
        assert api_key == KEY
        instance = original_client(api_key=api_key, vertexai=False, http_options=types.HttpOptions(
            base_url="https://synthetic.invalid",
            client_args={"transport": httpx.MockTransport(respond), "trust_env": False},
            async_client_args={"transport": httpx.MockTransport(respond), "trust_env": False},
            retry_options={"attempts": 1},
        ))
        clients.append(instance)
        return instance

    monkeypatch.setattr(genai, "Client", client)
    try:
        result = await provider_cls().chat(system="system", user="input", json_mode=json_mode,
                                         response_schema=SCHEMA if use_schema else None)
        assert len(sent) == 1
        config = sent[0]["generationConfig"]
        assert config.get("responseJsonSchema") == (SCHEMA if use_schema else None)
        assert config.get("responseMimeType") == ("application/json" if use_schema or json_mode else None)
        assert "responseSchema" not in config
        assert result.model == "gemini-synthetic-primary"
        assert json.loads(result.text) == ANSWER
    finally:
        for client in clients:
            await client.aio.aclose()
            client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("json_mode,use_schema", MODES)
async def test_local_ollama_uses_native_format_and_only_the_existing_probe(monkeypatch, json_mode, use_schema):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://synthetic.invalid:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "synthetic-model")
    original_client = httpx.AsyncClient
    sent = []

    def respond(request):
        sent.append((request.method, request.url.path, json.loads(request.content) if request.content else None))
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": []})
        assert request.url.path == "/api/chat"
        return httpx.Response(200, json={"message": {"content": json.dumps(ANSWER)}})

    def client(**kwargs):
        return original_client(**kwargs, transport=httpx.MockTransport(respond), trust_env=False)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    result = await OllamaProvider().chat(system="system", user="input", json_mode=json_mode,
                                      response_schema=SCHEMA if use_schema else None)
    assert [(method, path) for method, path, _ in sent] == [("GET", "/api/tags"), ("POST", "/api/chat")]
    assert sent[1][2].get("format") == (SCHEMA if use_schema else "json" if json_mode else None)
    assert sent[1][2]["stream"] is False
    assert json.loads(result.text) == ANSWER


@pytest.mark.asyncio
async def test_unsupported_emergent_schema_fails_before_sdk_or_http_and_legacy_stays_available(monkeypatch):
    monkeypatch.setenv("EMERGENT_LLM_KEY", KEY)
    sent = []

    class Chat:
        def __init__(self, **kwargs):
            sent.append(kwargs)

        def with_model(self, *args):
            return self

        async def send_message(self, message):
            sent.append(message.text)
            return json.dumps(ANSWER)

    monkeypatch.setitem(sys.modules, "emergentintegrations.llm.chat", SimpleNamespace(
        LlmChat=Chat, UserMessage=lambda **kwargs: SimpleNamespace(**kwargs),
    ))
    with pytest.raises(LLMConfigurationError, match="^response_schema_unsupported$"):
        await EmergentProvider().chat(system="system", user="input", json_mode=True, response_schema=SCHEMA)
    assert sent == []
    result = await EmergentProvider().chat(system="system", user="input", json_mode=True, response_schema=None)
    assert len(sent) == 2
    assert json.loads(result.text) == ANSWER


class RecordingProvider:
    def __init__(self, name, replies):
        self.name, self.replies, self.calls = name, list(replies), []

    def is_configured(self):
        return True

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        result = self.replies.pop(0)
        if isinstance(result, Exception):
            raise result
        return LLMResult(text=json.dumps(result), provider=self.name)


def manager_with(monkeypatch, *providers):
    manager = ProviderManager()
    manager._providers = {provider.name: provider for provider in providers}
    monkeypatch.setattr(manager, "ordered_names", lambda *args: list(manager._providers))
    return manager


@pytest.mark.asyncio
async def test_real_sdk_rejection_uses_existing_failover_without_schema_downgrade(monkeypatch):
    for name in ("GROQ_API_KEY", "MISTRAL_API_KEY"):
        monkeypatch.setenv(name, KEY)
    for name in ("GROQ_MODEL", "MISTRAL_MODEL"):
        monkeypatch.setenv(name, "synthetic-model")
    sent = []

    def respond(request):
        sent.append((request.url.host, json.loads(request.content)))
        if request.url.host == "api.groq.com":
            return httpx.Response(400, json={"error": {"message": "Synthetic protocol rejection",
                                                       "type": "invalid_request_error"}})
        assert request.url.host == "api.mistral.ai"
        return httpx.Response(200, json=openai_response())

    clients = install_openai_http(monkeypatch, respond)
    manager = manager_with(monkeypatch, GroqProvider(), MistralProvider())
    try:
        result = await manager.chat(system="system", user="input", json_mode=True, response_schema=SCHEMA)
        assert [host for host, _ in sent] == ["api.groq.com", "api.mistral.ai"]
        assert all(body["response_format"] == expected_format(SCHEMA) for _, body in sent)
        assert json.loads(result.text) == ANSWER
        assert result.provider == "mistral"
        assert result.usage["failover_errors"] == ["groq:network"]  # Existing 400 classification.
    finally:
        for client in clients:
            await client.close()


@pytest.mark.asyncio
async def test_research_to_manager_forwards_identical_schema_across_existing_failover(monkeypatch):
    from llm import manager as manager_module

    first = RecordingProvider("gemini", [LLMNetworkError("network")])
    second = RecordingProvider("mistral", [ANSWER])
    manager = manager_with(monkeypatch, first, second)
    monkeypatch.setattr(manager_module, "get_manager", lambda: manager)
    schema = copy.deepcopy(SCHEMA)
    result = await reasoning._ask_model("system", "input", response_schema=schema)
    assert result == ANSWER
    assert len(first.calls) == len(second.calls) == 1
    assert first.calls[0] == second.calls[0] == {
        "system": "system", "user": "input", "session_id": None,
        "json_mode": True, "response_schema": SCHEMA,
    }
    assert schema == SCHEMA


@pytest.mark.asyncio
async def test_existing_pacing_pass_preserves_schema_without_another_loop(monkeypatch):
    from llm import manager as manager_module

    provider = RecordingProvider("groq", [LLMRateLimitError("rate_limit"), ANSWER])
    manager = manager_with(monkeypatch, provider)
    clock, sleeps = [0.0], []
    manager._clock = lambda: clock[0]

    async def wait(delay):
        sleeps.append(delay)
        clock[0] += delay

    monkeypatch.setattr(manager_module.asyncio, "sleep", wait)
    result = await manager.chat(system="system", user="input", response_schema=SCHEMA)
    assert json.loads(result.text) == ANSWER
    assert len(provider.calls) == 2 and len(sleeps) == 1
    assert provider.calls[0] == provider.calls[1]
    assert provider.calls[1]["response_schema"] == SCHEMA


@pytest.mark.asyncio
async def test_absent_schema_is_not_passed_to_legacy_manager_or_provider(monkeypatch):
    from llm import manager as manager_module

    class LegacyProvider:
        name = "groq"

        def is_configured(self):
            return True

        async def chat(self, *, system, user, session_id=None, json_mode=False):
            assert (system, user, session_id, json_mode) == ("system", "input", None, True)
            return LLMResult(text=json.dumps(ANSWER), provider=self.name)

    manager = manager_with(monkeypatch, LegacyProvider())
    result = await manager.chat(system="system", user="input", json_mode=True, response_schema=None)
    assert json.loads(result.text) == ANSWER

    class LegacyManager:
        async def chat(self, *, system, user, json_mode=False):
            assert (system, user, json_mode) == ("system", "input", True)
            return LLMResult(text=json.dumps(ANSWER), provider="groq")

    monkeypatch.setattr(manager_module, "get_manager", LegacyManager)
    assert await reasoning._ask_model("system", "input", response_schema=None) == ANSWER


@pytest.mark.asyncio
async def test_requested_schema_does_not_add_validation_or_coerce_provider_content(monkeypatch):
    # Native protocol constraints complement, rather than replace, the
    # preparation parser. A nonconforming remote response remains observable.
    from llm import manager as manager_module

    malformed = {"content": {"unexpected": "object"}, "evidence_ids": ["evi_synthetic"]}
    provider = RecordingProvider("mistral", [malformed])
    manager = manager_with(monkeypatch, provider)
    monkeypatch.setattr(manager_module, "get_manager", lambda: manager)
    result = await reasoning._ask_model("system", "input", response_schema=SCHEMA)
    assert result == malformed
    assert isinstance(result["content"], dict)
    assert len(provider.calls) == 1
