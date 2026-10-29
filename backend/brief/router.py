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
