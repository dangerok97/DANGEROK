"""Home V2 HTTP surface — GET /api/home + actions."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from deps import db, get_current_user
from home.models import HomeActionBody
from home.service import HomeService

router = APIRouter(prefix="/home", tags=["home_v2"])

_svc: HomeService | None = None


def get_home_service() -> HomeService:
    global _svc
    if _svc is None:
        _svc = HomeService(db)
    return _svc


@router.get("")
async def get_home(user=Depends(get_current_user)):
    svc = get_home_service()
    result = await svc.build_home(user["user_id"])
    return result.model_dump()


@router.get("/situation")
async def get_situation(user=Depends(get_current_user)):
    svc = get_home_service()
    return await svc.full_situation(user["user_id"])


@router.post("/actions")
async def home_action(body: HomeActionBody, user=Depends(get_current_user)):
    svc = get_home_service()
    return await svc.apply_action(
        user["user_id"],
        item_id=body.item_id,
        action=body.action,
        until=body.until,
        reason=body.reason,
        priority=body.priority,
        note=body.note,
    )


@router.post("/refresh")
async def home_refresh(user=Depends(get_current_user)):
    svc = get_home_service()
    result = await svc.build_home(user["user_id"])
    return result.model_dump()
