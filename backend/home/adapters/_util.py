"""Shared adapter helpers."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(*parts: str) -> str:
    raw = "|".join(p or "" for p in parts)
    return "hi_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def new_id(prefix: str = "hi") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def parse_amount(admin: dict) -> Optional[str]:
    amt = admin.get("amount")
    cur = admin.get("currency") or "€"
    if not amt:
        return None
    s = str(amt).strip()
    if not s:
        return None
    if any(c in s for c in ("€", "$", "EUR")):
        return s
    return f"{s} {cur}".strip()


def looks_like_visit(title: str, subcategory: str | None = None) -> bool:
    t = (title or "").lower()
    sub = (subcategory or "").lower()
    keys = ("visita", "medico", "dentista", "controllo", "ambulatorio", "ospedale", "medical")
    return any(k in t or k in sub for k in keys)


def looks_like_concert(title: str, subcategory: str | None = None) -> bool:
    t = (title or "").lower()
    sub = (subcategory or "").lower()
    keys = ("concerto", "biglietto", "ticket", "arena", "teatro", "live")
    return any(k in t or k in sub for k in keys)
