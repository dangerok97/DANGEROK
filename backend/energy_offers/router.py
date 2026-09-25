"""Owner-scoped status and control for the ongoing energy offer watch."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from deps import db, get_current_user
from energy_offers.service import EnergyOfferService

router = APIRouter(prefix="/energy-offers", tags=["energy-offers"])


class MonitoringChoice(BaseModel):
    enabled: bool


@router.get("/monitoring")
async def monitoring_status(user=Depends(get_current_user)):
    service = EnergyOfferService(db)
    owner = user["user_id"]
    record = await db.users.find_one({"user_id": owner}, {"preferences.energy_offer_monitoring": 1})
    enabled = (record or {}).get("preferences", {}).get("energy_offer_monitoring") is not False
    return {"enabled": enabled, "supplies": await service.status(owner)}


@router.patch("/monitoring")
async def set_monitoring(body: MonitoringChoice, user=Depends(get_current_user)):
    service = EnergyOfferService(db)
    owner = user["user_id"]
    await service.set_enabled(owner, body.enabled)
    return {"enabled": body.enabled, "supplies": await service.status(owner)}
