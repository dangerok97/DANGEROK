"""Calendar entry points; persistence and conversation share domain services."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from deps import db, get_current_user
from home.calendar_event import delete_event, event_detail
from home.manual_event import (
    create_manual_event, home_event_times, manual_events_between, update_manual_event,
)
from timezone_service import is_valid_iana_timezone, resolve_user_timezone

router = APIRouter(prefix="/calendar/events", tags=["calendar_event"])


class HomeEventBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    day: str = Field(min_length=10, max_length=10)
    time: str = Field(min_length=5, max_length=5)
    duration_minutes: int = Field(default=60, ge=5, le=1440)
    location: str = Field(default="", max_length=300)
    description: str = Field(default="", max_length=800)
    timezone: str | None = Field(default=None, max_length=80)
    request_id: str | None = Field(default=None, min_length=8, max_length=80)


class UpdateHomeEventBody(HomeEventBody):
    expected_updated_at: str = Field(min_length=10, max_length=80)


async def _zone(user_id, requested=None):
    if requested:
        if not is_valid_iana_timezone(requested):
            raise HTTPException(status_code=422, detail="invalid_timezone")
        return requested
    return (await resolve_user_timezone(db, user_id)).tz_name


def _error(exc):
    reason = str(exc)
    status = 404 if reason == "event_not_found" else 409 if reason in (
        "event_changed", "request_conflict", "event_cancelled",
    ) else 422
    return HTTPException(status_code=status, detail=reason)


@router.post("/home")
async def create_home_event(body: HomeEventBody, user=Depends(get_current_user)):
    zone = await _zone(user["user_id"], body.timezone)
    try:
        start, end = home_event_times(body.day, body.time, zone, body.duration_minutes)
        return await create_manual_event(
            db, user["user_id"], title=body.title, start=start, end=end, tz_name=zone,
            request_id=body.request_id, location=body.location, description=body.description,
        )
    except ValueError as exc:
        raise _error(exc)


@router.get("/home/day")
async def home_day_events(day: str, timezone: str | None = None, user=Depends(get_current_user)):
    zone = ZoneInfo(await _zone(user["user_id"], timezone))
    try:
        if len(day) != 10:
            raise ValueError("invalid_day")
        first = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=zone)
        end = first + timedelta(days=1)
    except (ValueError, OverflowError):
        raise HTTPException(status_code=422, detail="invalid_day")
    return await manual_events_between(db, user["user_id"], first, end)


@router.get("/home/month")
async def home_month_days(month: str, timezone: str | None = None, user=Depends(get_current_user)):
    zone = ZoneInfo(await _zone(user["user_id"], timezone))
    try:
        if len(month) != 7:
            raise ValueError("invalid_month")
        first = datetime.strptime(month, "%Y-%m").replace(tzinfo=zone)
        end = datetime(first.year + (first.month == 12), first.month % 12 + 1, 1, tzinfo=zone)
    except (ValueError, OverflowError):
        raise HTTPException(status_code=422, detail="invalid_month")
    rows = await manual_events_between(db, user["user_id"], first, end, limit=2000)
    return sorted({datetime.fromisoformat(row["starts_at"]).astimezone(zone).strftime("%d") for row in rows})


class DeleteBody(BaseModel):
    confirmed_title: str = Field(default="", max_length=300)


@router.get("/{item_id}")
async def get_event(item_id: str, user=Depends(get_current_user)):
    found = await event_detail(db, user["user_id"], item_id)
    if not found:
        raise HTTPException(status_code=404, detail="event_not_found")
    return found


@router.patch("/{item_id}")
async def edit_home_event(item_id: str, body: UpdateHomeEventBody, user=Depends(get_current_user)):
    zone = await _zone(user["user_id"], body.timezone)
    try:
        start, end = home_event_times(body.day, body.time, zone, body.duration_minutes)
        await update_manual_event(
            db, user["user_id"], item_id,
            {"title": body.title, "start_datetime": start, "end_datetime": end,
             "timezone": zone, "location": body.location, "description": body.description},
            expected_updated_at=body.expected_updated_at,
        )
    except ValueError as exc:
        raise _error(exc)
    return await event_detail(db, user["user_id"], item_id)


@router.post("/{item_id}/delete")
async def remove_event(item_id: str, body: DeleteBody, user=Depends(get_current_user)):
    out = await delete_event(db, user["user_id"], item_id, confirmed_title=body.confirmed_title)
    if not out.get("ok"):
        reason = str(out.get("reason") or "delete_failed")
        raise HTTPException(status_code=404 if reason == "not_found" else 409, detail=reason)
    return out
