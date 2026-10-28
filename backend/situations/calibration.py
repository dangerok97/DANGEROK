"""
The person's own times correct the general ones.

The drying computation and the usual durations are general. This person's
clothes, balcony and dishwasher are not. The clearest signal they give is on
the reminder itself: «Tra 10 minuti» / «Tra un'ora» on "dovrebbero essere
asciutti" means "not yet", and how much later they asked is how much longer
it takes. Only that explicit signal is used: when somebody closes a
Situation says when it was convenient for them, not when the thing was ready.

One factor per person and per kind of process ("drying", "typical:<key>"),
moved halfway towards what the last answer showed, never beyond 0.6-2.0.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

COLLECTION = "situation_calibration"
LOW, HIGH = 0.6, 2.0


def key_of(meta: dict) -> Optional[str]:
    kind = (meta or {}).get("kind")
    if kind == "drying_end":
        return "drying"
    if kind == "typical_end" and meta.get("typical_key"):
        return f"typical:{meta['typical_key']}"
    return None


async def factor(db, owner: str, key: Optional[str]) -> float:
    if not key:
        return 1.0
    row = await db[COLLECTION].find_one({"owner_id": owner, "key": key}, {"_id": 0, "factor": 1})
    try:
        return max(LOW, min(HIGH, float((row or {}).get("factor") or 1.0)))
    except (TypeError, ValueError):
        return 1.0


async def learn_not_yet(db, owner: str, meta: dict, *, planned_minutes: float, extra_minutes: float) -> Optional[float]:
    """«Non ancora» after `planned_minutes`: it needed at least `extra_minutes` more."""
    key = key_of(meta)
    if not key or planned_minutes <= 0:
        return None
    old = await factor(db, owner, key)
    shown = old * (planned_minutes + extra_minutes) / planned_minutes
    new = max(LOW, min(HIGH, old + (shown - old) / 2))
    await db[COLLECTION].update_one(
        {"owner_id": owner, "key": key},
        {"$set": {"factor": round(new, 3), "updated_at": datetime.now(timezone.utc).isoformat()},
         "$inc": {"answers": 1}},
        upsert=True)
    return new
