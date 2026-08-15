"""Optional Gemini Google Search grounding — retrieval-shaped evidence only."""
from __future__ import annotations

import logging
import os
from typing import Any, List

from conversation_engine.ai_core.tools.providers.base import ProviderResult, RawHit

logger = logging.getLogger("ora.ai_core.tools.gemini_search")


def configured() -> bool:
    flag = (os.environ.get("GEMINI_SEARCH_ENABLED") or "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    return bool((os.environ.get("GEMINI_API_KEY") or "").strip())


async def search(query: str, *, max_results: int = 5) -> ProviderResult:
    if not configured():
        return ProviderResult(ok=False, provider="gemini_search", failure_code="NOT_CONFIGURED")
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
        name = type(e).__name__.lower()
        msg = str(e).lower()
        if "timeout" in msg:
            code = "TIMEOUT"
        elif "quota" in msg or "resource_exhausted" in msg:
            code = "QUOTA_EXHAUSTED"
        elif "429" in msg or "rate" in msg:
            code = "RATE_LIMITED"
        elif "auth" in msg or "permission" in msg or "401" in msg:
            code = "AUTH"
        else:
            code = "PROVIDER_ERROR"
        logger.info("gemini_search soft-fail: %s", type(e).__name__)
        return ProviderResult(ok=False, provider="gemini_search", failure_code=code)


def _extract_hits(resp: Any, *, max_results: int) -> List[RawHit]:
    hits: List[RawHit] = []
    try:
        cands = getattr(resp, "candidates", None) or []
        for cand in cands:
            gm = getattr(cand, "grounding_metadata", None)
            if not gm:
                continue
            chunks = getattr(gm, "grounding_chunks", None) or []
            for ch in chunks:
                web = getattr(ch, "web", None)
                if not web:
                    continue
                uri = str(getattr(web, "uri", None) or getattr(web, "url", None) or "")
                title = str(getattr(web, "title", None) or "")
                if uri or title:
                    hits.append(RawHit(title=title[:200], url=uri[:400], snippet=""))
                if len(hits) >= max_results:
                    return hits
            supports = getattr(gm, "grounding_supports", None) or []
            for sup in supports:
                seg = getattr(sup, "segment", None)
                text = str(getattr(seg, "text", None) or "")[:400]
                if text and hits:
                    if not hits[0].snippet:
                        hits[0].snippet = text
    except Exception:
        return hits
    return hits[:max_results]
