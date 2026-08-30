"""Provider Manager — unit tests (no secrets logged)."""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("LLM_PROVIDER", "auto")
os.environ.setdefault("OLLAMA_ENABLED", "0")


def _run(coro):
    return asyncio.run(coro)


def test_priority_order_default():
    from llm.manager import DEFAULT_PRIORITY, get_manager

    assert DEFAULT_PRIORITY[0] == "gemini"
    # The order is the contract: two Gemini accounts first, because a second
    # account is a second set of quotas rather than a second way of reasoning,
    # then the other families, then whatever is local.
    assert list(DEFAULT_PRIORITY) == [
        "gemini", "gemini2", "groq", "mistral", "openai", "ollama", "emergent",
    ]
    mgr = get_manager()
    assert mgr.ordered_names(None)[0] == "gemini"


def test_preferred_provider_reorders():
    from llm.manager import get_manager

    order = get_manager().ordered_names("openai")
    assert order[0] == "openai"
    assert "gemini" in order


def test_failover_on_quota():
    from llm.base import LLMResult
    from llm.errors import LLMQuotaError
    from llm.manager import ProviderManager

    mgr = ProviderManager()

    async def body():
        gemini = mgr.get("gemini")
        openai = mgr.get("openai")
        with patch.object(gemini, "is_configured", return_value=True), \
             patch.object(openai, "is_configured", return_value=True), \
             patch.object(mgr.get("ollama"), "is_configured", return_value=False), \
             patch.object(mgr.get("emergent"), "is_configured", return_value=False), \
             patch.object(gemini, "chat", new=AsyncMock(side_effect=LLMQuotaError("quota"))), \
             patch.object(
                 openai,
                 "chat",
                 new=AsyncMock(return_value=LLMResult(text='{"ok":true}', provider="openai", model="gpt-4o-mini")),
             ):
            res = await mgr.chat(system="s", user="u", json_mode=True, user_preference="gemini")
            assert res.provider == "openai"
            assert res.text

    _run(body())


def test_no_provider_raises_not_configured():
    from contextlib import ExitStack

    from llm.errors import LLMNotConfigured
    from llm.manager import DEFAULT_PRIORITY, ProviderManager

    mgr = ProviderManager()

    async def body():
        with ExitStack() as stack:
            for name in DEFAULT_PRIORITY:
                stack.enter_context(
                    patch.object(mgr.get(name), "is_configured", return_value=False)
                )
            with pytest.raises(LLMNotConfigured) as caught:
                await mgr.chat(system="s", user="u")
        assert type(caught.value) is LLMNotConfigured

    _run(body())


def _configured_chain(mgr, enabled=("gemini", "openai")):
    """
    Patch configuration only; callers still own chat mocks.

    Every provider in the chain, not a list written down once: a test about
    what happens when two providers fail should not quietly start being a test
    about three the day a third is added.
    """
    from llm.manager import DEFAULT_PRIORITY

    return [
        patch.object(mgr.get(name), "is_configured", return_value=name in enabled)
        for name in DEFAULT_PRIORITY
    ]


def test_all_configured_quota_raises_provider_unavailable_with_safe_causes():
    from contextlib import ExitStack

    from llm.errors import LLMProviderUnavailable, LLMQuotaError
    from llm.manager import ProviderManager

    mgr = ProviderManager()

    async def body():
        with ExitStack() as stack:
            for ctx in _configured_chain(mgr):
                stack.enter_context(ctx)
            stack.enter_context(
                patch.object(mgr.get("gemini"), "chat", new=AsyncMock(side_effect=LLMQuotaError("sensitive-a")))
            )
            stack.enter_context(
                patch.object(mgr.get("openai"), "chat", new=AsyncMock(side_effect=LLMQuotaError("sensitive-b")))
            )
            with pytest.raises(LLMProviderUnavailable) as caught:
                await mgr.chat(system="private prompt", user="private user text")
        assert [x["failure_kind"] for x in caught.value.attempts] == ["quota", "quota"]
        serialized = repr(caught.value.attempts)
        assert "sensitive" not in serialized and "private" not in serialized

    _run(body())


@pytest.mark.parametrize(
    "failure_type",
    [
        "LLMTimeoutError",
        "LLMNetworkError",
        "LLMAuthenticationError",
        "LLMModelUnavailableError",
    ],
)
def test_typed_provider_failures_fail_over(failure_type):
    from contextlib import ExitStack

    from llm import errors
    from llm.base import LLMResult
    from llm.manager import ProviderManager

    mgr = ProviderManager()
    failure = getattr(errors, failure_type)("sanitized")

    async def body():
        with ExitStack() as stack:
            for ctx in _configured_chain(mgr):
                stack.enter_context(ctx)
            stack.enter_context(patch.object(mgr.get("gemini"), "chat", new=AsyncMock(side_effect=failure)))
            openai = AsyncMock(return_value=LLMResult(text="ok", provider="openai"))
            stack.enter_context(patch.object(mgr.get("openai"), "chat", new=openai))
            result = await mgr.chat(system="s", user="u")
        assert result.provider == "openai"
        openai.assert_awaited_once()

    _run(body())


def test_internal_error_is_not_masked_by_failover():
    from contextlib import ExitStack

    from llm.errors import LLMInternalError
    from llm.manager import ProviderManager

    mgr = ProviderManager()

    async def body():
        with ExitStack() as stack:
            for ctx in _configured_chain(mgr):
                stack.enter_context(ctx)
            stack.enter_context(patch.object(mgr.get("gemini"), "chat", new=AsyncMock(side_effect=ValueError("bug"))))
            openai = AsyncMock()
            stack.enter_context(patch.object(mgr.get("openai"), "chat", new=openai))
            with pytest.raises(LLMInternalError):
                await mgr.chat(system="s", user="u")
        openai.assert_not_awaited()

    _run(body())


def test_invalid_provider_response_has_explicit_failover_policy():
    from contextlib import ExitStack

    from llm.base import LLMResult
    from llm.errors import LLMInvalidResponseError
    from llm.manager import ProviderManager

    mgr = ProviderManager()

    async def body():
        with ExitStack() as stack:
            for ctx in _configured_chain(mgr):
                stack.enter_context(ctx)
            stack.enter_context(
                patch.object(mgr.get("gemini"), "chat", new=AsyncMock(side_effect=LLMInvalidResponseError("malformed")))
            )
            stack.enter_context(
                patch.object(mgr.get("openai"), "chat", new=AsyncMock(return_value=LLMResult(text="ok", provider="openai")))
            )
            result = await mgr.chat(system="s", user="u")
        assert result.provider == "openai"

    _run(body())


def test_circuit_breaker_skips_then_retries_after_expiry_and_status_is_passive():
    from contextlib import ExitStack

    from llm.base import LLMResult
    from llm.errors import LLMQuotaError
    from llm.manager import ProviderManager

    mgr = ProviderManager()
    now = [100.0]
    mgr._clock = lambda: now[0]

    async def body():
        gemini = AsyncMock(side_effect=[LLMQuotaError("quota"), LLMResult(text="g", provider="gemini")])
        openai = AsyncMock(return_value=LLMResult(text="o", provider="openai"))
        with ExitStack() as stack:
            for ctx in _configured_chain(mgr):
                stack.enter_context(ctx)
            stack.enter_context(patch.object(mgr.get("gemini"), "chat", new=gemini))
            stack.enter_context(patch.object(mgr.get("openai"), "chat", new=openai))
            assert (await mgr.chat(system="s", user="u")).provider == "openai"
            status = await mgr.status()
            gemini_status = next(p for p in status["providers"] if p["id"] == "gemini")
            assert gemini_status["runtime_state"] == "cooldown"
            assert (await mgr.chat(system="s", user="u")).provider == "openai"
            assert gemini.await_count == 1
            now[0] += 61.0
            assert (await mgr.chat(system="s", user="u")).provider == "gemini"
            assert gemini.await_count == 2

    _run(body())


def test_retry_after_extends_cooldown_without_sleeping():
    from llm.errors import LLMRateLimitError
    from llm.manager import ProviderManager

    mgr = ProviderManager()
    now = [10.0]
    mgr._clock = lambda: now[0]

    async def body():
        await mgr._record_failure("gemini", LLMRateLimitError("rate", retry_after=120))
        assert mgr._runtime["gemini"].cooldown_until == 130.0
        assert await mgr._available("gemini") is False

    with patch.object(mgr.get("gemini"), "is_configured", return_value=True):
        _run(body())


def test_disabled_provider_is_skipped():
    from contextlib import ExitStack

    from llm.base import LLMResult
    from llm.manager import ProviderManager

    mgr = ProviderManager()

    async def body():
        gemini = AsyncMock()
        openai = AsyncMock(return_value=LLMResult(text="ok", provider="openai"))
        with ExitStack() as stack:
            for ctx in _configured_chain(mgr, enabled=("openai",)):
                stack.enter_context(ctx)
            stack.enter_context(patch.object(mgr.get("gemini"), "chat", new=gemini))
            stack.enter_context(patch.object(mgr.get("openai"), "chat", new=openai))
            assert (await mgr.chat(system="s", user="u")).provider == "openai"
        gemini.assert_not_awaited()

    _run(body())


def test_gemini_connector_failure_maps_to_network_error():
    from llm.errors import LLMNetworkError
    from llm.providers.gemini import _map_api_error

    ClientConnectorError = type("ClientConnectorError", (RuntimeError,), {})
    mapped = _map_api_error(ClientConnectorError("Cannot connect to provider"))
    assert isinstance(mapped, LLMNetworkError)


def test_status_is_passive_and_does_not_probe_ollama():
    from contextlib import ExitStack

    from llm.manager import ProviderManager

    mgr = ProviderManager()

    async def body():
        probe = AsyncMock()
        with ExitStack() as stack:
            for ctx in _configured_chain(mgr, enabled=("ollama",)):
                stack.enter_context(ctx)
            stack.enter_context(patch.object(mgr.get("ollama"), "probe", new=probe))
            status = await mgr.status()
        assert next(p for p in status["providers"] if p["id"] == "ollama")[
            "runtime_state"
        ] == "unknown"
        probe.assert_not_awaited()

    _run(body())


def test_retry_after_header_is_sanitized_and_bounded():
    from llm.errors import retry_after_seconds

    response = type("Response", (), {"headers": {"Retry-After": "9999"}})()
    error = type("ProviderError", (RuntimeError,), {"response": response})()
    assert retry_after_seconds(error) == 300.0


def test_auth_failure_reports_config_error_after_cooldown():
    from llm.errors import LLMAuthenticationError
    from llm.manager import ProviderManager

    mgr = ProviderManager()
    now = [10.0]
    mgr._clock = lambda: now[0]

    async def body():
        await mgr._record_failure("gemini", LLMAuthenticationError("auth"))
        assert mgr.runtime_snapshot("gemini")["runtime_state"] == "cooldown"
        now[0] += 301.0
        assert mgr.runtime_snapshot("gemini")["runtime_state"] == "config_error"

    _run(body())


def test_chat_json_validates_schema():
    from llm.base import LLMResult
    from llm.structured import chat_json
    from documents.intelligence.schemas import LLMDocumentEnrichment

    fake = LLMResult(
        text='{"suggested_title":"T","summary":"S","summary_detailed":"D","keywords":["k"],"education":null,"notes":null}',
        provider="gemini",
        model="gemini-2.0-flash",
    )

    async def body():
        with patch("llm.structured.get_manager") as gm:
            gm.return_value.chat = AsyncMock(return_value=fake)
            parsed, meta = await chat_json(
                system="s", user="u", model_cls=LLMDocumentEnrichment,
            )
            assert parsed.suggested_title == "T"
            assert meta["provider"] == "gemini"

    _run(body())


def test_gemini_not_configured_without_key():
    from llm.providers.gemini import GeminiProvider

    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
        assert GeminiProvider().is_configured() is False


def test_gemini_uses_google_genai_not_generativeai():
    """Adapter must import google.genai Client, not deprecated google.generativeai."""
    import ast
    from pathlib import Path

    src = Path("llm/providers/gemini.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    joined = " ".join(imports)
    assert "google.generativeai" not in joined
    assert "google.genai" in src or "from google import genai" in src
    assert "GenerativeModel" not in src
    assert "genai.configure" not in src


def test_gemini_chat_mock_google_genai():
    """Unit mock of google.genai Client.aio.models.generate_content."""
    from llm.providers.gemini import GeminiProvider
    import google.genai as genai_mod

    class _Resp:
        text = '{"ok": true}'
        usage_metadata = None

    async def fake_generate_content(**kwargs):
        assert kwargs.get("model")
        assert kwargs.get("contents")
        return _Resp()

    class _Models:
        generate_content = staticmethod(fake_generate_content)

    class _Aio:
        models = _Models()

        async def aclose(self):
            return None

    class _Client:
        def __init__(self, *a, **k):
            assert k.get("api_key"), "Client must receive api_key"
            self.aio = _Aio()

    async def body():
        with patch.dict(
            os.environ,
            {
                "GEMINI_API_KEY": "test-key-not-real",
                "GEMINI_MODEL": "gemini-flash-lite-latest",
            },
            clear=False,
        ), patch.object(genai_mod, "Client", _Client):
            p = GeminiProvider()
            res = await p.chat(system="s", user="u", json_mode=True)
            assert res.provider == "gemini"
            assert res.text
            assert res.usage.get("outcome") == "success"
            assert res.usage.get("fallback_used") is False
            assert "models_tried" in res.usage

    _run(body())


@pytest.mark.skipif(
    not (os.environ.get("GEMINI_API_KEY") or "").strip(),
    reason="GEMINI_API_KEY absent — real Gemini not verified",
)
def test_real_gemini_enrichment_optional():
    async def body():
        os.environ["LLM_PROVIDER"] = "gemini"
        os.environ["DOCUMENT_AI_ENABLED"] = "1"
        os.environ["OLLAMA_ENABLED"] = "0"
        from documents.intelligence.analyzer import analyze_document
        from pathlib import Path

        text = Path("tests/fixtures/intel_docs/caso_b_concerto.txt").read_text(encoding="utf-8")
        res = await analyze_document(
            {
                "id": "doc_gemini_real",
                "filename": "concerto.txt",
                "original_filename": "concerto.txt",
                "extracted_text": text,
            },
            force_ai=True,
        )
        assert res["analysis"]["ai_used"] is True
        assert (res["analysis"].get("usage") or {}).get("provider") == "gemini" or \
            res["analysis"].get("model")

    _run(body())
