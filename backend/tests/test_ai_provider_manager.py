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
    assert list(DEFAULT_PRIORITY) == ["gemini", "openai", "ollama", "emergent"]
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
    from llm.errors import LLMNotConfigured
    from llm.manager import ProviderManager

    mgr = ProviderManager()

    async def body():
        for name in ("gemini", "openai", "ollama", "emergent"):
            p = mgr.get(name)
            with patch.object(p, "is_configured", return_value=False):
                pass
        with patch.object(mgr, "_available", new=AsyncMock(return_value=False)):
            with pytest.raises(LLMNotConfigured):
                await mgr.chat(system="s", user="u")

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

    with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}, clear=False):
        assert GeminiProvider().is_configured() is False


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
