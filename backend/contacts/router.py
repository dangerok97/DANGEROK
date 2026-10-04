from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException

from deps import db, get_current_user
from contacts.service import (
    device_contacts_state,
    revoke_device_contacts,
    sync_device_contacts,
)

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("/device")
async def status(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    state = await device_contacts_state(db, user["user_id"])
    return {
        "ok": True,
        "status": state.get("status", "disconnected"),
        "synced_at": state.get("synced_at") or "",
        "contact_count": int(state.get("contact_count") or 0),
    }


@router.post("/device")
async def sync(
    payload: Dict[str, Any] = Body(...),
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    permission = str(payload.get("permission") or "").lower().strip()
    if permission not in ("granted", "denied"):
        raise HTTPException(400, "permission deve essere granted o denied")
    if permission == "denied":
        return {"ok": True, **(await revoke_device_contacts(db, user["user_id"]))}

    contacts = payload.get("contacts")
    if not isinstance(contacts, list):
        raise HTTPException(400, "contacts deve essere una lista")
    return {"ok": True, **(await sync_device_contacts(
        db, user["user_id"], contacts=contacts
    ))}


@router.delete("/device")
async def revoke(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    return {"ok": True, **(await revoke_device_contacts(db, user["user_id"]))}
