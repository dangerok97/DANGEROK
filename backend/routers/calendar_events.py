"""L'appuntamento visto da vicino, e il pulsante per toglierlo."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from life_graph.service import LifeGraphService
from home.manual_event import home_event_times

from deps import db, get_current_user
from home.calendar_event import delete_event, event_detail

router = APIRouter(prefix="/calendar/events", tags=["calendar_event"])


class HomeEventBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    day: str
    time: str


@router.post("/home")
async def create_home_event(body: HomeEventBody, user=Depends(get_current_user)):
    """A deliberate user tap creates an ORA-local commitment, never a Google write."""
    from timezone_service import resolve_user_timezone

    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="title_required")
    try:
        zone = (await resolve_user_timezone(db, user["user_id"])).tz_name
        starts, ends = home_event_times(body.day, body.time, zone)
    except (ValueError, KeyError):
        raise HTTPException(status_code=422, detail="invalid_day_or_time")
    node = await LifeGraphService(db).create_node(
        user["user_id"], type="event", label=title,
        attributes={"starts_at": starts, "ends_at": ends,
                    "timezone": zone, "kind": "home_manual"},
        origin="home_calendar",
    )
    return {"id": node["id"], "title": title, "starts_at": node["attributes"]["starts_at"],
            "source": "ora"}


@router.get("/home/day")
async def home_day_events(day: str, user=Depends(get_current_user)):
    try:
        if len(day) != 10:
            raise ValueError("format")
        first = datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid_day")
    next_day = (first + timedelta(days=1)).strftime("%Y-%m-%d")
    rows = await db.life_nodes.find(
        {"user_id": user["user_id"], "type": "event", "status": "active",
         "attributes.kind": "home_manual", "attributes.starts_at": {"$gte": day, "$lt": next_day}},
        {"_id": 0, "id": 1, "label": 1, "attributes": 1},
    ).sort("attributes.starts_at", 1).to_list(length=100)
    return [{"id": r["id"], "title": r["label"], "starts_at": r["attributes"]["starts_at"]} for r in rows]


@router.get("/home/month")
async def home_month_days(month: str, user=Depends(get_current_user)):
    try:
        if len(month) != 7:
            raise ValueError("format")
        first = datetime.strptime(month, "%Y-%m")
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid_month")
    next_month = datetime(first.year + (first.month == 12), first.month % 12 + 1, 1).strftime("%Y-%m")
    rows = await db.life_nodes.find(
        {"user_id": user["user_id"], "type": "event", "status": "active",
         "attributes.kind": "home_manual", "attributes.starts_at": {"$gte": month + "-01", "$lt": next_month + "-01"}},
        {"_id": 0, "attributes.starts_at": 1},
    ).to_list(length=500)
    return sorted({str(r["attributes"]["starts_at"])[8:10] for r in rows})


class DeleteBody(BaseModel):
    # Il titolo che la persona aveva davanti quando ha confermato. Serve a
    # legare il «sì» a *quell'* appuntamento: senza, una conferma varrebbe per
    # qualunque evento, che e' esattamente il modo in cui si cancella la cosa
    # sbagliata.
    confirmed_title: str = Field(default="", max_length=300)


@router.get("/{item_id}")
async def get_event(item_id: str, user=Depends(get_current_user)):
    node = await db.life_nodes.find_one(
        {"id": item_id, "user_id": user["user_id"], "type": "event", "attributes.kind": "home_manual"},
        {"_id": 0},
    )
    if node:
        attrs = node.get("attributes") or {}
        cancelled = node.get("status") != "active"
        return {"id": item_id, "title": node.get("label"), "starts_at": attrs.get("starts_at"),
                "ends_at": attrs.get("ends_at"), "all_day": False, "location": None,
                "description": None, "where_it_comes_from": "Calendario ORA", "provider": "ORA",
                "state": "annullato" if cancelled else "in calendario", "cancelled": cancelled,
                "can_be_changed": not cancelled}
    found = await event_detail(db, user["user_id"], item_id)
    if not found:
        raise HTTPException(status_code=404, detail="event_not_found")
    return found


@router.post("/{item_id}/delete")
async def remove_event(
    item_id: str, body: DeleteBody, user=Depends(get_current_user),
):
    node = await db.life_nodes.find_one(
        {"id": item_id, "user_id": user["user_id"], "type": "event", "attributes.kind": "home_manual"},
        {"_id": 0, "label": 1, "status": 1},
    )
    if node:
        if body.confirmed_title.strip() != node["label"]:
            raise HTTPException(status_code=409, detail="confirmation_does_not_match")
        await db.life_nodes.update_one(
            {"id": item_id, "user_id": user["user_id"], "status": "active"},
            {"$set": {"status": "archived"}},
        )
        return {"ok": True, "verified": True, "operation": "deleted", "title": node["label"]}
    out = await delete_event(
        db, user["user_id"], item_id, confirmed_title=body.confirmed_title,
    )
    if not out.get("ok"):
        reason = str(out.get("reason") or "delete_failed")
        raise HTTPException(
            status_code=404 if reason == "not_found" else 409, detail=reason,
        )
    return out
