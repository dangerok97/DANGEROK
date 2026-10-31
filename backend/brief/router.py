"""The morning brief preference: on/off and the hour, per person."""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from deps import db, get_current_user
from brief.morning import preference, set_preference

router = APIRouter(prefix="/brief", tags=["brief"])


class MorningIn(BaseModel):
    enabled: Optional[bool] = None
    hour: Optional[int] = Field(default=None, ge=5, le=11)


@router.get("/morning")
async def get_morning(user=Depends(get_current_user)):
    return await preference(db, user["user_id"])


@router.put("/morning")
async def put_morning(body: MorningIn, user=Depends(get_current_user)):
    return await set_preference(db, user["user_id"], enabled=body.enabled, hour=body.hour)


@router.get("/morning/today")
async def morning_today(user=Depends(get_current_user)):
    """The whole brief, built now: the page behind the morning notification."""
    from datetime import datetime
    from brief.morning import full
    from timezone_service import user_clock_context
    clock = await user_clock_context(db, user["user_id"])
    return await full(db, user["user_id"], datetime.fromisoformat(clock["local_datetime"]))


@router.get("/evening")
async def get_evening(user=Depends(get_current_user)):
    from brief.evening import preference as evening
    return await evening(db, user["user_id"])


class EveningIn(BaseModel):
    enabled: Optional[bool] = None
    hour: Optional[int] = Field(default=None, ge=18, le=22)


@router.put("/evening")
async def put_evening(body: EveningIn, user=Depends(get_current_user)):
    from brief.evening import set_preference as set_evening
    return await set_evening(db, user["user_id"], enabled=body.enabled, hour=body.hour)


class TravelIn(BaseModel):
    mode: str


@router.get("/travel-mode")
async def get_travel(user=Depends(get_current_user)):
    from places.travel_mode import LABELS, get
    mode = await get(db, user["user_id"])
    return {"mode": mode, "label": LABELS[mode]}


@router.put("/travel-mode")
async def put_travel(body: TravelIn, user=Depends(get_current_user)):
    from fastapi import HTTPException
    from places.travel_mode import set_mode
    out = await set_mode(db, user["user_id"], body.mode)
    if not out["ok"]:
        raise HTTPException(status_code=400, detail="Modo non valido")
    return out


@router.get("/setup")
async def setup_status(user=Depends(get_current_user)):
    """What ORA still needs from a new person to work on its own (first-run guide)."""
    from brief.morning import preference
    from places.travel_mode import get as travel

    uid = user["user_id"]
    notifications = bool(await db.push_endpoints.count_documents(
        {"$or": [{"owner_id": uid}, {"user_id": uid}], "status": "active"}, limit=1))
    try:
        from location.service import LocationService
        location = (await LocationService(db).get_preference(uid)) == "while_using"
    except Exception:
        location = False
    home = bool(await db.life_places.count_documents(
        {"user_id": uid, "role": "home", "state": "confirmed", "coordinates": {"$ne": None}}, limit=1))
    row = await db.users.find_one({"user_id": uid}, {"_id": 0, "preferences": 1}) or {}
    prefs = row.get("preferences") or {}
    steps = {"notifications": notifications, "location": location, "home": home,
             "travel_mode": "travel_mode" in prefs, "morning_brief": "morning_brief" in prefs}
    return {**steps, "travel": await travel(db, uid), "brief": await preference(db, uid),
            "done": all(steps.values()), "dismissed": bool(prefs.get("setup_dismissed")),
            "missing": [k for k, v in steps.items() if not v]}


@router.post("/setup/dismiss")
async def setup_dismiss(user=Depends(get_current_user)):
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"preferences.setup_dismissed": True}})
    return {"ok": True}
