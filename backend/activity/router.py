"""Attività HTTP API — one aggregated read, never a source of truth."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from deps import db, get_current_user
from activity.presentation import build_activity

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("")
async def get_activity(user=Depends(get_current_user)):
    """Everything Attività shows, in one request.

    One endpoint rather than the page fanning out across half a dozen stores:
    the sections are read together, bounded together, and stay consistent with
    each other because they come from a single moment.
    """
    return await build_activity(db, user["user_id"])
