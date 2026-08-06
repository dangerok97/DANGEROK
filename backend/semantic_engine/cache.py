"""Input+context hash cache for semantic extraction — cost / privacy aware."""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, Optional, Tuple

_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_DEFAULT_TTL = int(os.environ.get("SEMANTIC_CACHE_TTL_SEC", "600"))
_MAX_ENTRIES = int(os.environ.get("SEMANTIC_CACHE_MAX", "256"))


def cache_key(text: str, context: Optional[Dict[str, Any]], *, intent: Optional[str], timezone: str) -> str:
    payload = {
        "t": (text or "").strip().lower(),
        "i": intent or "",
        "tz": timezone,
        # Minimal context — never hash secrets / full docs / health / bank dumps
        "c": _minimize_context(context),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _minimize_context(context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not context:
        return {}
    allow = {
        "prior_slots", "confirmed_entities", "flow", "intent",
        "destination", "subject", "departure_date", "return_date",
    }
    out = {}
    for k, v in context.items():
        if k in allow:
            out[k] = v
        if k in ("document", "documents", "health", "bank", "secrets", "token", "password"):
            continue
    return out


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
        # drop oldest
        oldest = sorted(_CACHE.items(), key=lambda kv: kv[1][0])[: max(1, _MAX_ENTRIES // 4)]
        for k, _ in oldest:
            _CACHE.pop(k, None)
    _CACHE[key] = (time.time(), data)


def clear() -> None:
    _CACHE.clear()
