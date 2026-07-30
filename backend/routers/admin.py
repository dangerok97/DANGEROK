"""ADMIN router (demo-only endpoints)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from deps import DEMO_EMAILS, get_current_user

from ._seed import _ensure_live_imminent, _refresh_time_anchors

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/demo/refresh")
async def admin_demo_refresh(user=Depends(get_current_user)):
    """Manually re-run demo maintenance (anchor refresh + ensure imminent).
    Reserved to demo accounts."""
    if user["email"] not in DEMO_EMAILS:
        raise HTTPException(status_code=403, detail="Endpoint riservato agli utenti demo")
    await _refresh_time_anchors(user["user_id"])
    await _ensure_live_imminent(user["user_id"])
    return {"ok": True, "email": user["email"]}
