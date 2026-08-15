"""Tavily web search adapter — retrieval only."""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from conversation_engine.ai_core.tools.providers.base import ProviderResult, RawHit

logger = logging.getLogger("ora.ai_core.tools.tavily")


def configured() -> bool:
    return bool((os.environ.get("TAVILY_API_KEY") or "").strip())


async def search(query: str, *, max_results: int = 5) -> ProviderResult:
    key = (os.environ.get("TAVILY_API_KEY") or "").strip()
    if not key:
        return ProviderResult(ok=False, provider="tavily", failure_code="NOT_CONFIGURED")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": key,
                    "query": query,
                    "max_results": max(1, min(8, max_results)),
                    "include_answer": False,
                    "search_depth": "basic",
                },
            )
        if r.status_code in (401, 403):
            return ProviderResult(ok=False, provider="tavily", failure_code="AUTH")
        if r.status_code == 429:
            return ProviderResult(ok=False, provider="tavily", failure_code="RATE_LIMITED")
        if r.status_code >= 500:
            return ProviderResult(ok=False, provider="tavily", failure_code="PROVIDER_ERROR")
        if r.status_code != 200:
            return ProviderResult(ok=False, provider="tavily", failure_code="PROVIDER_ERROR")
        data = r.json()
        hits = []
        for item in (data.get("results") or [])[:max_results]:
            if not isinstance(item, dict):
                continue
            hits.append(
                RawHit(
                    title=str(item.get("title") or "")[:200],
                    url=str(item.get("url") or "")[:400],
                    snippet=str(item.get("content") or item.get("snippet") or "")[:400],
                )
            )
        if not hits:
            return ProviderResult(ok=True, provider="tavily", hits=[], failure_code=None)
        return ProviderResult(ok=True, provider="tavily", hits=hits)
    except httpx.TimeoutException:
        return ProviderResult(ok=False, provider="tavily", failure_code="TIMEOUT")
    except httpx.HTTPError:
        return ProviderResult(ok=False, provider="tavily", failure_code="NETWORK")
    except Exception as e:
        logger.info("tavily soft-fail: %s", type(e).__name__)
        return ProviderResult(ok=False, provider="tavily", failure_code="UNKNOWN")
