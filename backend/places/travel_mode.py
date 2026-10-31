"""How the person usually moves: the first mode tried for a leave time."""
from __future__ import annotations

from typing import Any, Dict

MODES = ("drive", "walk", "transit", "bicycle")
LABELS = {"drive": "in auto", "walk": "a piedi", "transit": "con i mezzi", "bicycle": "in bici"}
DEFAULT = "drive"


async def get(db, owner: str) -> str:
    row = await db.users.find_one({"user_id": owner}, {"_id": 0, "preferences.travel_mode": 1})
    mode = ((row or {}).get("preferences") or {}).get("travel_mode")
    return mode if mode in MODES else DEFAULT


async def set_mode(db, owner: str, mode: str) -> Dict[str, Any]:
    if mode not in MODES:
        return {"ok": False, "error": "invalid_mode", "allowed": list(MODES)}
    await db.users.update_one({"user_id": owner}, {"$set": {"preferences.travel_mode": mode}})
    # Every upcoming leave notice is recomputed with the new mode at once.
    await db.reminders.update_many(
        {"user_id": owner, "origin": "leave_notice", "status": "open", "notified_state": {"$exists": False}},
        {"$set": {"meta.planned_at": "1970-01-01T00:00:00+00:00"}})
    return {"ok": True, "mode": mode, "label": LABELS[mode]}


def order(preferred: str) -> tuple:
    rest = [m for m in ("drive", "transit", "walk", "bicycle") if m != preferred]
    return (preferred, *rest)


async def set_travel_mode_cap(arguments: Dict[str, Any], runtime: Dict[str, Any]):
    from conversation_engine.ai_core.models import Observation

    db, owner = runtime.get("db"), str(runtime.get("user_id") or "")
    if db is None or not owner:
        return Observation(kind="tool", name="set_travel_mode", status="error", payload={"ok": False})
    out = await set_mode(db, owner, str(arguments.get("mode") or ""))
    return Observation(kind="tool", name="set_travel_mode", status="ok" if out["ok"] else "error", payload=out)
