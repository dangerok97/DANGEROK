"""Optional Gemini Google Search grounding — retrieval-shaped evidence only."""
from __future__ import annotations

import logging
import os
import time
from typing import Any, List

from conversation_engine.ai_core.tools.providers.base import ProviderResult, RawHit

logger = logging.getLogger("ora.ai_core.tools.gemini_search")

# A shared search API key can be exhausted across many user requests. Do not
# re-send the same known-unavailable request on every conversation turn. This
# is a short, process-local retry interval, not a durable quota assumption or
# evidence that another provider returned any facts.
_QUOTA_RETRY_SECONDS = 300.0
_quota_retry_after = 0.0
_clock = time.monotonic


def _failure_code(exc: Exception) -> str:
    """Normalize technical failures without logging provider bodies or keys."""
    message = str(exc).lower()
    if "timeout" in message or "timed out" in message:
        return "TIMEOUT"
    if any(value in message for value in (
        "quota", "resource_exhausted", "402", "payment required",
        "billing", "insufficient credit", "credit balance",
    )):
        return "QUOTA_EXHAUSTED"
    if "429" in message or "rate limit" in message or "too many requests" in message:
        return "RATE_LIMITED"
    if any(value in message for value in ("auth", "permission", "401", "403")):
        return "AUTH"
    return "PROVIDER_ERROR"


def configured() -> bool:
    flag = (os.environ.get("GEMINI_SEARCH_ENABLED") or "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    return bool((os.environ.get("GEMINI_API_KEY") or "").strip())


async def search(query: str, *, max_results: int = 5) -> ProviderResult:
    global _quota_retry_after
    if not configured():
        return ProviderResult(ok=False, provider="gemini_search", failure_code="NOT_CONFIGURED")
    if _clock() < _quota_retry_after:
        return ProviderResult(ok=False, provider="gemini_search", failure_code="QUOTA_EXHAUSTED")
    try:
        from google import genai
        from google.genai import types
    except Exception:
        return ProviderResult(ok=False, provider="gemini_search", failure_code="UNSUPPORTED")

    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    model = (os.environ.get("GEMINI_MODEL") or "gemini-flash-lite-latest").strip()

    try:
        client = genai.Client(api_key=key)
        # google-genai Google Search tool (API shape may vary by SDK version)
        tool = None
        for factory in (
            lambda: types.Tool(google_search=types.GoogleSearch()),
            lambda: types.Tool(google_search_retrieval=types.GoogleSearchRetrieval()),
        ):
            try:
                tool = factory()
                break
            except Exception:
                continue
        if tool is None:
            return ProviderResult(
                ok=False, provider="gemini_search", failure_code="UNSUPPORTED"
            )

        resp = await client.aio.models.generate_content(
            model=model,
            contents=(
                "Retrieve current public web evidence for this query. "
                "Do not invent sources.\n\nQuery: " + query
            ),
            config=types.GenerateContentConfig(tools=[tool]),
        )
        hits = _extract_hits(resp, max_results=max_results)
        # Never trust model prose as authoritative — only grounding chunks/URIs
        if not hits:
            return ProviderResult(
                ok=False, provider="gemini_search", failure_code="INVALID_RESPONSE"
            )
        return ProviderResult(ok=True, provider="gemini_search", hits=hits)
    except Exception as e:
        code = _failure_code(e)
        if code == "QUOTA_EXHAUSTED":
            _quota_retry_after = max(_quota_retry_after, _clock() + _QUOTA_RETRY_SECONDS)
        # Log the class, never a provider error body that may contain a key.
        logger.info("gemini_search soft-fail: %s", type(e).__name__)
        return ProviderResult(ok=False, provider="gemini_search", failure_code=code)


def _extract_hits(resp: Any, *, max_results: int) -> List[RawHit]:
    hits: List[RawHit] = []
    if max_results <= 0:
        return hits
    try:
        cands = getattr(resp, "candidates", None) or []
        for cand in cands:
            gm = getattr(cand, "grounding_metadata", None)
            if not gm:
                continue
            chunks = getattr(gm, "grounding_chunks", None) or []
            indexed_hits = {}
            for index, ch in enumerate(chunks):
                web = getattr(ch, "web", None)
                if not web:
                    continue
                uri = str(getattr(web, "uri", None) or getattr(web, "url", None) or "")
                title = str(getattr(web, "title", None) or "")
                if uri or title:
                    hit = RawHit(title=title[:200], url=uri[:400], snippet="")
                    hits.append(hit)
                    indexed_hits[index] = hit
                if len(hits) >= max_results:
                    break
            supports = getattr(gm, "grounding_supports", None) or []
            for sup in supports:
                seg = getattr(sup, "segment", None)
                text = getattr(seg, "text", None)
                indices = getattr(sup, "grounding_chunk_indices", None)
                if type(text) is not str or not text or not isinstance(indices, list):
                    continue
                for index in indices:
                    if type(index) is not int:
                        continue
                    # Indices address this candidate's original chunks, even
                    # when a non-web/empty chunk was excluded from the hits.
                    hit = indexed_hits.get(index)
                    if hit is not None and not hit.snippet:
                        hit.snippet = text[:400]
                        # Grounded model output, not a literal page quotation.
                        hit.snippet_origin = "grounded_model_segment"
            if len(hits) >= max_results:
                return hits
    except Exception:
        return hits
    return hits[:max_results]
