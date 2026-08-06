"""Cache for strategist reasoning / question planning / benefit / gap / confidence."""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, Optional, Tuple

_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_DEFAULT_TTL = int(os.environ.get("AI_LIFE_STRATEGIST_CACHE_TTL_SEC", "600"))
_MAX_ENTRIES = int(os.environ.get("AI_LIFE_STRATEGIST_CACHE_MAX", "256"))


def _minimize(ctx: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not ctx:
        return {}
    allow = {
        "domains_touched", "missing_keys", "asked_questions", "linked_doc_types",
        "session_phase", "benefits_available", "benefits_active", "focus_domain",
        "known_keys", "last_user_text_hash",
    }
    out = {}
    for k, v in ctx.items():
        if k in allow:
            out[k] = v
    # Never cache secrets / full documents
    return out


def make_key(kind: str, user_id: str, payload: Dict[str, Any]) -> str:
    body = {
        "k": kind,
        "u": user_id,
        "p": _minimize(payload),
    }
    raw = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def text_hash(text: Optional[str]) -> str:
    t = (text or "").strip().lower()
    return hashlib.sha256(t.encode("utf-8")).hexdigest()[:16]


def get(key: str) -> Optional[Dict[str, Any]]:
    item = _CACHE.get(key)
    if not item:
        return None
    ts, data = item
    if time.time() - ts > _DEFAULT_TTL:
        _CACHE.pop(key, None)
        return None
    return data


def set(key: str, data: Dict[str, Any]) -> None:
    if len(_CACHE) >= _MAX_ENTRIES:
        oldest = sorted(_CACHE.items(), key=lambda kv: kv[1][0])[: max(1, _MAX_ENTRIES // 4)]
        for k, _ in oldest:
            _CACHE.pop(k, None)
    _CACHE[key] = (time.time(), data)


def clear() -> None:
    _CACHE.clear()
