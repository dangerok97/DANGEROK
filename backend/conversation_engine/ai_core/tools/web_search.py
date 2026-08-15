"""web_search capability — cognition requests capability; providers failover below."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from conversation_engine.ai_core.grounding.authority import authority_for_url
from conversation_engine.ai_core.models import Observation
from conversation_engine.ai_core.observations.external import (
    ExternalObservation,
    ExternalSource,
)
from conversation_engine.ai_core.tools.failures import normalize_failure
from conversation_engine.ai_core.tools.providers import brave, gemini_search, tavily
from conversation_engine.ai_core.tools.providers.base import ProviderResult
from conversation_engine.ai_core.tools.sanitize import sanitize_external_query

logger = logging.getLogger("ora.ai_core.tools.web_search")


def research_enabled() -> bool:
    return (os.environ.get("RESEARCH_ENABLED") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def availability() -> str:
    if not research_enabled():
        return "disabled"
    if tavily.configured() or brave.configured() or gemini_search.configured():
        return "available"
    return "not_configured"


async def execute_web_search(
    arguments: Dict[str, Any],
    runtime: Dict[str, Any],
) -> Observation:
    query_raw = str(arguments.get("query") or "").strip()
    purpose = str(arguments.get("purpose") or "")[:120]
    max_results = int(arguments.get("max_results") or 5)
    max_results = max(1, min(8, max_results))

    if not research_enabled():
        obs = ExternalObservation(
            capability="web_search",
            query=query_raw[:180],
            status="failed",
            failure_code="NOT_CONFIGURED",
            notes=["RESEARCH_ENABLED is off"],
            freshness="n/a",
        )
        return _to_observation(obs)

    clean, reason = sanitize_external_query(query_raw)
    if not clean:
        obs = ExternalObservation(
            capability="web_search",
            query=query_raw[:180],
            status="failed",
            failure_code="INVALID_RESPONSE",
            notes=[f"query_rejected:{reason}"],
            freshness="n/a",
        )
        return _to_observation(obs)

    if availability() == "not_configured":
        obs = ExternalObservation(
            capability="web_search",
            query=clean,
            status="failed",
            failure_code="NOT_CONFIGURED",
            notes=["No search provider keys configured"],
            freshness="n/a",
        )
        return _to_observation(obs)

    result = await _failover_search(clean, max_results=max_results)
    if not result.ok:
        obs = ExternalObservation(
            capability="web_search",
            query=clean,
            status="failed",
            failure_code=normalize_failure(result.failure_code),
            provider_internal=result.provider,
            notes=[f"purpose:{purpose}"] if purpose else [],
            freshness="unknown",
        )
        return _to_observation(obs)

    sources: List[ExternalSource] = []
    findings: List[str] = []
    for hit in result.hits:
        if not (hit.url or hit.title or hit.snippet):
            continue
        auth = authority_for_url(hit.url, title=hit.title)
        sources.append(
            ExternalSource(
                title=hit.title,
                url=hit.url,
                snippet=hit.snippet,
                authority_hint=auth,
            )
        )
        if hit.snippet:
            findings.append(hit.snippet[:240])
        elif hit.title:
            findings.append(hit.title[:240])

    # Explicitly ignore provider "answer" fields if any slipped through
    _ = result.raw_answer

    status = "ok" if sources else "empty"
    obs = ExternalObservation(
        capability="web_search",
        query=clean,
        status=status,
        sources=sources,
        findings=findings[:8],
        provider_internal=result.provider,
        freshness="hours",
        notes=[
            "Evidence snippets only — not live traffic/routing APIs",
            *( [f"purpose:{purpose}"] if purpose else []),
        ],
    )
    return _to_observation(obs)


async def _failover_search(query: str, *, max_results: int) -> ProviderResult:
    """Tavily → Brave → Gemini Search. One capability call; providers below cognition."""
    chain = []
    if tavily.configured():
        chain.append(("tavily", tavily.search))
    if brave.configured():
        chain.append(("brave", brave.search))
    if gemini_search.configured():
        chain.append(("gemini_search", gemini_search.search))

    last: Optional[ProviderResult] = None
    for name, fn in chain:
        try:
            res = await fn(query, max_results=max_results)
        except Exception as e:
            logger.info("provider %s exception: %s", name, type(e).__name__)
            last = ProviderResult(ok=False, provider=name, failure_code="UNKNOWN")
            continue
        last = res
        if res.ok and res.hits:
            return res
        if res.ok and not res.hits:
            # empty but ok — try next for better evidence
            continue
        # hard fail codes that should failover
        if res.failure_code in (
            "NOT_CONFIGURED",
            "AUTH",
            "RATE_LIMITED",
            "QUOTA_EXHAUSTED",
            "TIMEOUT",
            "NETWORK",
            "PROVIDER_ERROR",
            "UNSUPPORTED",
            "INVALID_RESPONSE",
            "UNKNOWN",
        ):
            continue
    return last or ProviderResult(
        ok=False, provider="none", failure_code="NOT_CONFIGURED"
    )


def _to_observation(ext: ExternalObservation) -> Observation:
    return Observation(
        kind="tool",
        name="web_search",
        status=ext.status if ext.status in ("ok", "empty") else "failed",
        payload={
            "external": ext.to_loop_payload(),
            "public_sources": ext.public_sources_for_ui(),
            # Never auto-promote to Memory
            "memory_eligible": False,
        },
        provenance=[s.source_id for s in ext.sources],
    )
