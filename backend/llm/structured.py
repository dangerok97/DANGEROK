"""Validated structured LLM calls — JSON schema + cost controls."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from llm.errors import (
    LLMInvalidResponseError,
    LLMNotConfigured,
    LLMQuotaError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from llm.provider import chat_completion, llm_status

logger = logging.getLogger("ora.llm.structured")

T = TypeVar("T", bound=BaseModel)

# Cost / size controls
MAX_CHARS_PER_CHUNK = int(os.environ.get("DOCUMENT_AI_MAX_CHARS", "12000"))
MAX_CHUNKS = int(os.environ.get("DOCUMENT_AI_MAX_CHUNKS", "3"))
LLM_TIMEOUT_S = float(os.environ.get("DOCUMENT_AI_TIMEOUT_S", "60"))
LLM_MAX_RETRIES = int(os.environ.get("DOCUMENT_AI_MAX_RETRIES", "2"))


def chunk_text(text: str, *, max_chars: int = MAX_CHARS_PER_CHUNK, max_chunks: int = MAX_CHUNKS) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    # Drop near-empty pages
    parts = [p.strip() for p in re.split(r"\n{2,}", raw) if len(p.strip()) >= 40]
    if not parts:
        parts = [raw]
    chunks: list[str] = []
    buf = ""
    for p in parts:
        if len(buf) + len(p) + 2 <= max_chars:
            buf = f"{buf}\n\n{p}".strip() if buf else p
        else:
            if buf:
                chunks.append(buf)
            if len(chunks) >= max_chunks:
                break
            buf = p[:max_chars]
    if buf and len(chunks) < max_chunks:
        chunks.append(buf[:max_chars])
    # Deduplicate identical chunks
    out: list[str] = []
    seen: set[str] = set()
    for c in chunks:
        key = c[:200]
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out[:max_chunks]


def _strip_fences(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


async def chat_json(
    *,
    system: str,
    user: str,
    model_cls: Type[T],
    session_id: Optional[str] = None,
) -> tuple[T, dict[str, Any]]:
    """Call LLM and validate JSON against a Pydantic model.

    Returns (parsed, usage_meta). Never logs secrets or document body.
    """
    status = llm_status()
    if not status.get("configured"):
        raise LLMNotConfigured("LLM non configurato")

    last_err: Optional[Exception] = None
    for attempt in range(LLM_MAX_RETRIES + 1):
        try:
            raw = await chat_completion(
                system=system, user=user, session_id=session_id, json_mode=True,
            )
            data = json.loads(_strip_fences(raw))
            if not isinstance(data, dict):
                raise LLMInvalidResponseError("JSON non oggetto")
            parsed = model_cls.model_validate(data)
            meta = {
                "provider": status.get("provider"),
                "model": status.get("model"),
                "attempt": attempt + 1,
                "prompt_chars": len(system) + len(user),
                # Token counts unavailable without response headers in adapter;
                # approximate with chars/4 for observability only.
                "approx_tokens_in": (len(system) + len(user)) // 4,
                "approx_tokens_out": len(raw) // 4,
            }
            return parsed, meta
        except LLMNotConfigured:
            raise
        except ValidationError as e:
            last_err = LLMInvalidResponseError(f"schema_invalid:{e.error_count()}")
            logger.warning("LLM JSON schema invalid (attempt %s)", attempt + 1)
        except json.JSONDecodeError:
            last_err = LLMInvalidResponseError("json_decode")
            logger.warning("LLM JSON decode failed (attempt %s)", attempt + 1)
        except Exception as e:
            name = type(e).__name__
            msg = str(e).lower()
            # Map common openai errors without echoing bodies/keys
            if "rate" in msg or name in ("RateLimitError",):
                last_err = LLMRateLimitError("rate_limit")
            elif "timeout" in msg or name in ("APITimeoutError", "TimeoutError"):
                last_err = LLMTimeoutError("timeout")
            elif "quota" in msg or "insufficient" in msg:
                last_err = LLMQuotaError("quota")
            else:
                last_err = e
            logger.warning("LLM call failed type=%s attempt=%s", name, attempt + 1)
    assert last_err is not None
    raise last_err
