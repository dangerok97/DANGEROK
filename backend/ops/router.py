"""What ORA found when it last checked its own work, for the person it works for."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from deps import db, get_current_user
from ops import selfcheck

router = APIRouter(prefix="/ops", tags=["ops"])

WORDS = {
    "watch_without_alarm": "Una cosa che seguivo era rimasta senza controllo programmato",
    "watch_overdue": "Un controllo è in ritardo",
    "delivery_late": "Un avviso non è ancora partito all'ora prevista",
    "delivery_missed_while_stopped": "Un avviso è scaduto mentre ero ferma",
    "no_device_for_notifications": "Nessun telefono può ricevere le mie notifiche",
}


@router.get("/self-check")
async def self_check(user=Depends(get_current_user)):
    report = await selfcheck.latest(db, user["user_id"])
    if not report:
        return {"checked": False}
    return {
        "checked": True, "at": report["at"], "watches": report.get("watches", 0),
        "healthy": report.get("healthy", True),
        "items": [{"code": f["code"], "text": WORDS.get(f["code"], f["code"]),
                   "repaired": bool(f.get("repaired"))} for f in report.get("findings", [])],
    }
