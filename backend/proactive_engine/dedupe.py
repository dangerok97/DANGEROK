"""Dedupe — same goal / source / action window → one suggestion."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Set

from proactive_engine.models import Suggestion, SuggestionCandidate


def make_dedupe_key(
    *,
    suggestion_type: str,
    source: str,
    goal_id: Optional[str] = None,
    action_kind: Optional[str] = None,
    entity_id: Optional[str] = None,
    window: str = "day",
) -> str:
    raw = "|".join([
        suggestion_type or "",
        source or "",
        goal_id or "",
        action_kind or "",
        entity_id or "",
        window or "",
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def window_label(now: Optional[datetime] = None, hours: int = 24) -> str:
    now = now or datetime.now(timezone.utc)
    bucket = int(now.timestamp() // (hours * 3600))
    return f"w{hours}_{bucket}"


def filter_duplicate_candidates(
    candidates: Iterable[SuggestionCandidate],
    existing_keys: Set[str],
) -> List[SuggestionCandidate]:
    seen: Set[str] = set(existing_keys)
    out: List[SuggestionCandidate] = []
    for c in candidates:
        key = c.dedupe_key
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def collapse_home_list(items: List[Suggestion], *, limit: int = 3) -> List[Suggestion]:
    """Ordered, max N, no duplicate dedupe_key / goal+action."""
    seen: Set[str] = set()
    out: List[Suggestion] = []
    for s in sorted(items, key=lambda x: float(x.score or 0), reverse=True):
        if s.status not in ("active", "snoozed"):
            continue
        if s.dismissed or s.accepted or s.completed:
            continue
        keys = {s.dedupe_key}
        if s.goal_id and s.action:
            keys.add(f"g:{s.goal_id}:{s.action.kind}")
        if any(k in seen for k in keys if k):
            continue
        for k in keys:
            if k:
                seen.add(k)
        out.append(s)
        if len(out) >= limit:
            break
    return out


def is_expired(s: Suggestion, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    if not s.expires_at:
        return False
    try:
        exp = datetime.fromisoformat(s.expires_at.replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp <= now
    except Exception:
        return False


def is_snoozed(s: Suggestion, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    if not s.snooze_until:
        return False
    try:
        until = datetime.fromisoformat(s.snooze_until.replace("Z", "+00:00"))
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        return until > now
    except Exception:
        return False
