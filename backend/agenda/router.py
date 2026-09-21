"""L'agenda come superficie HTTP — GET /api/agenda."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from agenda.service import AgendaService, DEFAULT_DAYS, MAX_DAYS
from deps import db, get_current_user

router = APIRouter(prefix="/agenda", tags=["agenda"])


@router.get("")
async def get_agenda(
    days: int = Query(default=DEFAULT_DAYS, ge=1, le=MAX_DAYS),
    user=Depends(get_current_user),
):
    return await AgendaService(db).days_ahead(user["user_id"], days=days)
