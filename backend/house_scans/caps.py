"""Shared ORA AI Core / WhatsApp read of the person's saved house plans.

Answers "quanto è grande il soggiorno?" or "quanta pittura per la camera?"
from what was scanned or measured — never from a guess. No geometry, ids or
transforms leave here: only rooms and their sizes.
"""
from __future__ import annotations

from typing import Any

from conversation_engine.ai_core.models import Observation

CAPABILITY = "read_house_measurements"


def _observation(status: str, payload: dict) -> Observation:
    return Observation(
        kind="tool", name=CAPABILITY, status=status,
        payload={**payload, "grounding": "PERSONAL_CONTEXT", "memory_eligible": False},
    )


async def read_house_measurements(arguments: dict[str, Any], runtime: dict[str, Any]) -> Observation:
    from .service import HouseScanService
    from .stats import scan_overview

    owner = str(runtime.get("user_id") or "")
    db = runtime.get("db")
    if not owner or db is None:
        return _observation("error", {"status": "NOT_AUTHENTICATED"})
    service = HouseScanService(db)
    listing = await service.list_scans(owner, limit=5)
    if not listing["scans"]:
        return _observation("partial", {
            "status": "NO_HOUSE_PLAN",
            "reason": "Non ci sono ancora piante o misure della casa salvate.",
            "ui_actions": [{"kind": "ora_screen", "path": "/casa",
                            "label": "Aggiungi le stanze in Casa"}],
        })
    plans = []
    for summary in listing["scans"][:3]:
        plans.append(scan_overview(await service.get(owner, summary["id"])))
    return _observation("ok", {
        "status": "ok", "plans": plans,
        "notice": ("Le superfici da pittura escludono porte e finestre. Le misure da "
                   "scansione sono stime: per tagli e mobili su misura vanno verificate col metro."),
        "ui_actions": [{"kind": "ora_screen", "path": "/casa", "label": "Apri Casa in ORA"}],
    })
