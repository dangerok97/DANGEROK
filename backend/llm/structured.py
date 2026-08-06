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
from llm.manager import get_manager
from llm.provider import llm_status

logger = logging.getLogger("ora.llm.structured")

T = TypeVar("T", bound=BaseModel)

MAX_CHARS_PER_CHUNK = int(os.environ.get("DOCUMENT_AI_MAX_CHARS", "12000"))
MAX_CHUNKS = int(os.environ.get("DOCUMENT_AI_MAX_CHUNKS", "3"))
LLM_MAX_RETRIES = int(os.environ.get("DOCUMENT_AI_MAX_RETRIES", "2"))


def chunk_text(text: str, *, max_chars: int = MAX_CHARS_PER_CHUNK, max_chunks: int = MAX_CHUNKS) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
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
    user_preference: Optional[str] = None,
) -> tuple[T, dict[str, Any]]:
    """Call Provider Manager and validate JSON against a Pydantic model."""
    last_err: Optional[Exception] = None
    for attempt in range(LLM_MAX_RETRIES + 1):
        try:
            result = await get_manager().chat(
                system=system,
                user=user,
                session_id=session_id,
                json_mode=True,
                user_preference=user_preference,
            )
            data = json.loads(_strip_fences(result.text))
            if not isinstance(data, dict):
                raise LLMInvalidResponseError("JSON non oggetto")
            parsed = model_cls.model_validate(data)
            meta = {
                "provider": result.provider,
                "model": result.model,
                "attempt": attempt + 1,
                "prompt_chars": len(system) + len(user),
                "approx_tokens_in": (len(system) + len(user)) // 4,
                "approx_tokens_out": len(result.text) // 4,
                **(result.usage or {}),
            }
            return parsed, meta
        except LLMNotConfigured:
            raise
        except ValidationError as e:
            last_err = LLMInvalidResponseError(f"schema_invalid:{e.error_count()}")
            first = e.errors()[0] if e.errors() else {}
            logger.warning(
                "LLM JSON schema invalid (attempt %s) count=%s loc=%s type=%s",
                attempt + 1, e.error_count(), first.get("loc"), first.get("type"),
            )
        except json.JSONDecodeError:
            last_err = LLMInvalidResponseError("json_decode")
            logger.warning("LLM JSON decode failed (attempt %s)", attempt + 1)
        except (LLMRateLimitError, LLMTimeoutError, LLMQuotaError):
            # Manager already tried failover; surface for caller soft-fail
            raise
        except Exception as e:
            last_err = e
            logger.warning("LLM call failed type=%s attempt=%s", type(e).__name__, attempt + 1)
    assert last_err is not None
    raise last_err
