"""Opt-in, cited OpenAI Responses web_search fallback.

Cognition already supplied a privacy-sanitized public query. This adapter is
retrieval-shaped only: never accept a model's uncited answer as source content,
and never allow automatic charged calls unless explicitly configured.
"""
from __future__ import annotations

import ipaddress
import logging
import os
import time
from urllib.parse import urlsplit

import httpx

from conversation_engine.ai_core.tools.providers.base import ProviderResult, RawHit

logger = logging.getLogger("ora.ai_core.tools.openai_search")
PROVIDER = "openai_search"
_QUOTA_RETRY_SECONDS = 300.0
_retry_after = 0.0
_clock = time.monotonic
_ENDPOINT = "https://api.openai.com/v1/responses"


def configured() -> bool:
    """A key alone never opts anyone into a paid search provider."""
    enabled = (os.environ.get("OPENAI_WEB_SEARCH_ENABLED") or "0").strip().lower()
    return enabled in ("1", "true", "yes", "on") and bool(
        (os.environ.get("OPENAI_API_KEY") or "").strip()
    )


def _public_url(value: object) -> str:
    if type(value) is not str or len(value) > 400:
        return ""
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower().rstrip(".")
        if parts.scheme not in ("https", "http") or not host or not parts.netloc:
            return ""
        if parts.username or parts.password or host in ("localhost", "localhost.localdomain"):
            return ""
        if host.endswith((".localhost", ".local", ".internal", ".test")):
            return ""
        if parts.port is not None and parts.port not in (80, 443):
            return ""
        try:
            if not ipaddress.ip_address(host).is_global:
                return ""
        except ValueError:
            pass
        return value
    except ValueError:
        return ""


def _extract_hits(response: object, *, max_results: int) -> list[RawHit]:
    """Require a completed real web_search_call and source URL annotations.

    The snippet is only the model-generated text range explicitly associated
    with a URL citation, marked grounded_model_segment; it is NOT a literal
    page quote. Uncited generated prose is discarded in all cases.
    """
    if not isinstance(response, dict) or response.get("status") != "completed":
        return []
    output = response.get("output")
    if not isinstance(output, list):
        return []
    searched = any(
        isinstance(row, dict) and row.get("type") == "web_search_call"
        and row.get("status") == "completed"
        for row in output
    )
    if not searched:
        return []
    hits = []
    seen = set()
    for row in output:
        if not isinstance(row, dict) or row.get("type") != "message":
            continue
        if row.get("status") != "completed":
            continue
        for content in row.get("content") or []:
            if not isinstance(content, dict) or content.get("type") != "output_text":
                continue
            body = content.get("text")
            if not isinstance(body, str):
                continue
            for annotation in content.get("annotations") or []:
                if not isinstance(annotation, dict) or annotation.get("type") != "url_citation":
                    continue
                details = annotation.get("url_citation", annotation)
                if not isinstance(details, dict):
                    continue
                url = _public_url(details.get("url"))
                if not url or url in seen:
                    continue
                seen.add(url)
                title = details.get("title")
                start, end = details.get("start_index"), details.get("end_index")
                segment = ""
                if (type(start) is int and type(end) is int
                        and 0 <= start < end <= len(body) and end - start <= 600):
                    segment = body[start:end].strip()[:400]
                hits.append(RawHit(
                    title=title[:200] if isinstance(title, str) else "",
                    url=url,
                    snippet=segment,
                    snippet_origin="grounded_model_segment" if segment else "unknown",
                ))
                if len(hits) >= max(1, min(8, max_results)):
                    return hits
    return hits


async def search(query: str, *, max_results: int = 5) -> ProviderResult:
    global _retry_after
    if not configured():
        return ProviderResult(ok=False, provider=PROVIDER, failure_code="NOT_CONFIGURED")
    if _clock() < _retry_after:
        return ProviderResult(ok=False, provider=PROVIDER, failure_code="QUOTA_EXHAUSTED")
    # Upstream execute_web_search has sanitized the query. Do not accept
    # unbounded payloads from direct adapter callers either.
    question = str(query or "").strip()[:240]
    if not question:
        return ProviderResult(ok=False, provider=PROVIDER, failure_code="INVALID_RESPONSE")
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    model = (os.environ.get("OPENAI_WEB_SEARCH_MODEL") or "gpt-4.1-mini").strip()[:80]
    request = {
        "model": model,
        "store": False,
        "input": question,
        "instructions": (
            "Search the public web for the question. Answer briefly and cite "
            "specific URLs for each useful claim. If uncertain, say so. "
            "Do not fabricate citations."
        ),
        "tools": [{"type": "web_search", "search_context_size": "low"}],
        "tool_choice": "required",
        "include": ["web_search_call.action.sources"],
        "max_output_tokens": 750,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                _ENDPOINT,
                headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                json=request,
            )
        status = response.status_code
        if status == 402:
            _retry_after = max(_retry_after, _clock() + _QUOTA_RETRY_SECONDS)
            return ProviderResult(ok=False, provider=PROVIDER, failure_code="QUOTA_EXHAUSTED")
        if status == 429:
            return ProviderResult(ok=False, provider=PROVIDER, failure_code="RATE_LIMITED")
        if status in (401, 403):
            return ProviderResult(ok=False, provider=PROVIDER, failure_code="AUTH")
        if status in (400, 404, 422):
            return ProviderResult(ok=False, provider=PROVIDER, failure_code="UNSUPPORTED")
        if status >= 500:
            return ProviderResult(ok=False, provider=PROVIDER, failure_code="PROVIDER_ERROR")
        if status != 200:
            return ProviderResult(ok=False, provider=PROVIDER, failure_code="UNKNOWN")
        hits = _extract_hits(response.json(), max_results=max_results)
        if not hits:
            return ProviderResult(ok=False, provider=PROVIDER, failure_code="INVALID_RESPONSE")
        return ProviderResult(ok=True, provider=PROVIDER, hits=hits)
    except httpx.TimeoutException:
        return ProviderResult(ok=False, provider=PROVIDER, failure_code="TIMEOUT")
    except httpx.HTTPError:
        return ProviderResult(ok=False, provider=PROVIDER, failure_code="NETWORK")
    except Exception as exc:
        # Never print a provider response body, query, or account credential.
        logger.info("openai_search soft-fail: %s", type(exc).__name__)
        return ProviderResult(ok=False, provider=PROVIDER, failure_code="UNKNOWN")
