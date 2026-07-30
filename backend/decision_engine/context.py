"""
DecisionContext — snapshot of the world at evaluation time.

Every input the engine can reason on lives here. Rules read from context;
they never call databases directly. This makes the engine easy to test:
you build a context, hand it to the engine, and inspect the output.

We keep it PURPOSEFULLY schemaless-ish (extra fields tolerated) so that
future signals (weather, calendar, wearables) can be added without a
migration. Rules gracefully ignore missing keys.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class DecisionContext:
    """A read-only snapshot the engine reasons on."""

    now: datetime
    user_id: str
    decisions: List[Dict[str, Any]] = field(default_factory=list)
    # Extensible signal bag — hooks for future integrations.
    # Populate any of these with real data later; rules will pick them up.
    signals: Dict[str, Any] = field(default_factory=dict)

    # --- helpers ---------------------------------------------------------
    @classmethod
    def build(cls, user_id: str, decisions: List[Dict[str, Any]], signals: Optional[Dict[str, Any]] = None) -> "DecisionContext":
        return cls(
            now=datetime.now(timezone.utc),
            user_id=user_id,
            decisions=list(decisions),
            signals=signals or {},
        )

    def other_open(self, self_id: str) -> List[Dict[str, Any]]:
        return [d for d in self.decisions if d.get("id") != self_id and d.get("status", "open") == "open"]

    def any_category_within(self, category: str, hours: float, self_id: Optional[str] = None) -> bool:
        """Does any other OPEN decision of a given category have a deadline within `hours`?"""
        for d in self.decisions:
            if self_id and d.get("id") == self_id:
                continue
            if d.get("status", "open") != "open":
                continue
            if d.get("category") != category:
                continue
            hrs = _hours_until(d.get("deadline"), self.now)
            if hrs is not None and 0 <= hrs <= hours:
                return True
        return False


def _hours_until(iso_str: Optional[str], now: datetime) -> Optional[float]:
    """Parse ISO datetime, return hours until it (negative if past). None if missing/invalid."""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (dt - now).total_seconds() / 3600.0


# Exposed so rules can share the same parser.
hours_until = _hours_until
