"""Daily Intelligence router — read-only endpoints."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from deps import get_current_user, get_daily_summary_service

router = APIRouter(prefix="/daily", tags=["daily_intelligence"])


@router.get("/today")
async def daily_today(tz: str = Query("UTC"), user=Depends(get_current_user)):
    svc = get_daily_summary_service()
    summary = await svc.today(user["user_id"], tz_name=tz)
    return summary.to_dict()


@router.get("/tomorrow")
async def daily_tomorrow(tz: str = Query("UTC"), user=Depends(get_current_user)):
    svc = get_daily_summary_service()
    summary = await svc.tomorrow(user["user_id"], tz_name=tz)
    return summary.to_dict()


@router.get("/date/{iso_date}")
async def daily_specific(iso_date: str, tz: str = Query("UTC"), user=Depends(get_current_user)):
    try:
        d = date.fromisoformat(iso_date)
    except Exception:
        raise HTTPException(status_code=400, detail="Data non valida (formato atteso YYYY-MM-DD)")
    svc = get_daily_summary_service()
    summary = await svc.compute(user["user_id"], d, tz_name=tz)
    return summary.to_dict()


@router.post("/refresh")
async def daily_refresh(tz: str = Query("UTC"), user=Depends(get_current_user)):
    svc = get_daily_summary_service()
    return await svc.refresh(user["user_id"], tz_name=tz)
