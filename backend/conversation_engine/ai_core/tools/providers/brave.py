"""Brave Search adapter — retrieval only."""
from __future__ import annotations

import logging
import os

import httpx

from conversation_engine.ai_core.tools.providers.base import ProviderResult, RawHit

logger = logging.getLogger("ora.ai_core.tools.brave")


def configured() -> bool:
    return bool(
        (os.environ.get("BRAVE_SEARCH_API_KEY") or os.environ.get("BRAVE_API_KEY") or "").strip()
    )


async def search(query: str, *, max_results: int = 5) -> ProviderResult:
    key = (
        os.environ.get("BRAVE_SEARCH_API_KEY") or os.environ.get("BRAVE_API_KEY") or ""
    ).strip()
    if not key:
        return ProviderResult(ok=False, provider="brave", failure_code="NOT_CONFIGURED")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": max(1, min(8, max_results))},
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": key,
                },
            )
        if r.status_code in (401, 403):
            return ProviderResult(ok=False, provider="brave", failure_code="AUTH")
        if r.status_code == 429:
            return ProviderResult(ok=False, provider="brave", failure_code="RATE_LIMITED")
        if r.status_code != 200:
            return ProviderResult(ok=False, provider="brave", failure_code="PROVIDER_ERROR")
        data = r.json()
        web = (data.get("web") or {}).get("results") or []
        hits = []
        for item in web[:max_results]:
            if not isinstance(item, dict):
                continue
            hits.append(
                RawHit(
                    title=str(item.get("title") or "")[:200],
                    url=str(item.get("url") or "")[:400],
                    snippet=str(item.get("description") or "")[:400],
                )
            )
        return ProviderResult(ok=True, provider="brave", hits=hits)
    except httpx.TimeoutException:
        return ProviderResult(ok=False, provider="brave", failure_code="TIMEOUT")
    except httpx.HTTPError:
        return ProviderResult(ok=False, provider="brave", failure_code="NETWORK")
    except Exception as e:
        logger.info("brave soft-fail: %s", type(e).__name__)
        return ProviderResult(ok=False, provider="brave", failure_code="UNKNOWN")
