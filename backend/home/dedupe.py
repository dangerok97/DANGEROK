"""Canonical Home presentation dedupe keys."""
from __future__ import annotations

import re
from typing import Optional


def canonical_title_time_key(
    title: str,
    when: Optional[str],
    *,
    goal_id: Optional[str] = None,
) -> str:
    """Build an exact title/hour key, scoped by Goal identity when present."""
    normalized_title = re.sub(r"\s+", " ", (title or "").strip().casefold())
    time_bucket = str(when or "")[:13]
    scope = f"goal:{goal_id}" if goal_id else "legacy"
    return f"{scope}|{normalized_title}|{time_bucket}"
