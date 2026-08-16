"""HTTP surface for foreground location signals + preference."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from deps import get_current_user
from location.service import LocationService, runtime_location_capabilities

router = APIRouter(prefix="/location", tags=["location"])


def _svc():
    from deps import db

    return LocationService(db)


class SignalIn(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy_meters: Optional[float] = Field(None, ge=0, le=100000)
    session_id: Optional[str] = Field(None, max_length=64)
    goal_ref: Optional[str] = Field(None, max_length=64)
    reverse_geocode: bool = True


class PreferenceIn(BaseModel):
    mode: Literal["off", "while_using"]


@router.get("/preference")
async def get_preference(user=Depends(get_current_user)):
    svc = _svc()
    pref = await svc.get_preference(user["user_id"])
    return {
        "ok": True,
        "mode": pref,
        "background_available": False,
        "native_available": False,
        "runtime_capabilities": runtime_location_capabilities(
            preference=pref, platform="web"
        ),
    }


@router.put("/preference")
async def put_preference(body: PreferenceIn, user=Depends(get_current_user)):
    svc = _svc()
    pref = await svc.set_preference(user["user_id"], body.mode)
    return {
        "ok": True,
        "mode": pref,
        "background_available": False,
        "native_available": False,
    }


@router.post("/signal")
async def post_signal(body: SignalIn, user=Depends(get_current_user)):
    """Ingest a foreground device location signal (auth + user-scoped)."""
    svc = _svc()
    res = await svc.ingest_foreground_signal(
        user["user_id"],
        latitude=body.latitude,
        longitude=body.longitude,
        accuracy_meters=body.accuracy_meters,
        session_id=body.session_id,
        goal_ref=body.goal_ref,
        reverse_geocode=body.reverse_geocode,
    )
    if not res.get("ok"):
        code = res.get("error") or "signal_failed"
        if code == "location_disabled":
            raise HTTPException(status_code=403, detail=code)
        raise HTTPException(status_code=400, detail=code)
    return res


@router.post("/permission-outcome")
async def permission_outcome(
    body: dict,
    user=Depends(get_current_user),
):
    """Record denied/unavailable browser permission — no invented coordinates."""
    state = str((body or {}).get("state") or "").strip().lower()
    if state not in (
        "denied",
        "unavailable",
        "not_requested",
        "timeout",
        "position_unavailable",
    ):
        raise HTTPException(status_code=400, detail="invalid_state")
    svc = _svc()
    return await svc.record_permission_outcome(user["user_id"], state=state)


@router.get("/presence")
async def get_presence(user=Depends(get_current_user)):
    svc = _svc()
    presence = await svc.build_presence(user["user_id"], platform="web")
    return {"ok": True, "presence": presence.for_ai()}
