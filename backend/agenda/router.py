"""L'agenda come superficie HTTP — GET /api/agenda."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from agenda.service import AgendaService, DEFAULT_DAYS, MAX_DAYS
from deps import db, get_current_user

router = APIRouter(prefix="/agenda", tags=["agenda"])


@router.get("")
async def get_agenda(
    days: int = Query(default=DEFAULT_DAYS, ge=1, le=MAX_DAYS),
    user=Depends(get_current_user),
):
    return await AgendaService(db).days_ahead(user["user_id"], days=days)


@router.get("/month")
async def get_calendar_month(
    month: str = Query(..., min_length=7, max_length=7),
    user=Depends(get_current_user),
):
    """A native ORA calendar always exists; linked sources are optional."""
    try:
        return await AgendaService(db).month_view(user["user_id"], month=month)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
