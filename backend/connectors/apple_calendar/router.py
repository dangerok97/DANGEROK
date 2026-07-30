"""Apple Calendar router — device-side sync endpoints.

Endpoints (all authenticated, prefix `/connectors/apple-calendar`):

    GET  /config-status                              feature-flag view
    POST /connect                                    creates/refreshes a
                                                     ConnectorInstance
                                                     for the device
    GET  /instances                                  list of instances
    GET  /instances/{id}                             fetch one
    GET  /instances/{id}/status                      diagnostic view
    POST /instances/{id}/select-calendars            {calendar_ids: []}
    POST /instances/{id}/sync                        {events: [...]}
    POST /instances/{id}/disconnect                  soft revoke

The connector never touches Apple's servers — the iOS client feeds the
events via `sync`. All endpoints reject the call with 403/404-like
errors when `APPLE_CALENDAR_ENABLED=false`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from deps import get_current_user
from permissions import ConsentDenied

from .service import AppleCalendarFeatureDisabled

router = APIRouter(prefix="/connectors/apple-calendar", tags=["apple_calendar"])


# ---------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------
class AppleCalendarInfo(BaseModel):
    id: str
    title: Optional[str] = None
    color: Optional[str] = None
    allowsModifications: Optional[bool] = None
    source: Optional[str] = None


class ConnectDeviceIn(BaseModel):
    device_id: str = Field(..., min_length=4, max_length=128)
    device_name: Optional[str] = None
    platform: Optional[str] = Field(default=None, description="ios | ipados")
    calendars: Optional[List[AppleCalendarInfo]] = None


class SelectCalendarsIn(BaseModel):
    calendar_ids: List[str]


class AppleRawEventIn(BaseModel):
    id: str
    calendarId: Optional[str] = None
    calendarTitle: Optional[str] = None
    title: Optional[str] = None
    notes: Optional[str] = None
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    allDay: Optional[bool] = False
    location: Optional[str] = None
    timeZone: Optional[str] = None
    status: Optional[str] = "confirmed"
    organizer: Optional[str] = None
    attendees: Optional[List[str]] = None
    recurrenceRule: Optional[str] = None
    lastModified: Optional[str] = None
    availability: Optional[str] = None
    recurrenceInstanceId: Optional[str] = None

    class Config:
        extra = "ignore"


class SyncEventsIn(BaseModel):
    events: List[Dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------
def _svc():
    # Local import to keep top-level import cycle-free at bootstrap.
    from deps import get_apple_calendar_service
    return get_apple_calendar_service()


@router.get("/config-status")
async def config_status(user=Depends(get_current_user)):
    return await _svc().config_status()


@router.post("/connect")
async def connect_device(body: ConnectDeviceIn, user=Depends(get_current_user)):
    try:
        instance = await _svc().connect_device(
            user_id=user["user_id"],
            device_id=body.device_id,
            device_name=body.device_name,
            platform=body.platform,
            calendars=[c.model_dump() for c in (body.calendars or [])],
        )
    except AppleCalendarFeatureDisabled as e:
        raise HTTPException(status_code=503, detail={"error": "feature_disabled", "message": str(e)})
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": "bad_request", "message": str(e)})
    return {"ok": True, "instance": instance}


@router.get("/instances")
async def list_instances(user=Depends(get_current_user)):
    return {"items": await _svc().list_instances(user["user_id"])}


@router.get("/instances/{instance_id}")
async def get_instance(instance_id: str, user=Depends(get_current_user)):
    inst = await _svc().get_instance(user["user_id"], instance_id)
    if not inst:
        raise HTTPException(status_code=404, detail="Istanza connector non trovata")
    return inst


@router.get("/instances/{instance_id}/status")
async def get_status(instance_id: str, user=Depends(get_current_user)):
    try:
        return await _svc().status(user_id=user["user_id"], instance_id=instance_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Istanza connector non trovata")


@router.post("/instances/{instance_id}/select-calendars")
async def select_calendars(instance_id: str, body: SelectCalendarsIn, user=Depends(get_current_user)):
    try:
        return await _svc().select_calendars(
            user_id=user["user_id"], instance_id=instance_id, calendar_ids=body.calendar_ids,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Istanza connector non trovata")


@router.post("/instances/{instance_id}/sync")
async def sync_events(instance_id: str, body: SyncEventsIn, user=Depends(get_current_user)):
    try:
        return await _svc().sync(
            user_id=user["user_id"], instance_id=instance_id, events=body.events or [],
        )
    except AppleCalendarFeatureDisabled as e:
        raise HTTPException(status_code=503, detail={"error": "feature_disabled", "message": str(e)})
    except LookupError:
        raise HTTPException(status_code=404, detail="Istanza connector non trovata")
    except ConsentDenied as e:
        raise HTTPException(status_code=403, detail={"error": "consent_denied", "capability_id": e.capability_id})


@router.post("/instances/{instance_id}/disconnect")
async def disconnect(instance_id: str, user=Depends(get_current_user)):
    try:
        return await _svc().disconnect(user_id=user["user_id"], instance_id=instance_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Istanza connector non trovata")
