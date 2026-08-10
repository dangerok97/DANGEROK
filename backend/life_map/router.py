"""Life Map HTTP API — Contesti cognition foundation."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from deps import get_current_user
from life_map.service import get_life_map_service

router = APIRouter(prefix="/life-map", tags=["life_map"])


@router.get("")
async def get_life_map(
    force: bool = Query(False, description="Bypass AI cache when LIFE_MAP_GEMINI=1"),
    enrich: Optional[bool] = Query(
        None,
        description="Override LIFE_MAP_GEMINI for this request (None = use env flag)",
    ),
    user=Depends(get_current_user),
):
    svc = get_life_map_service()
    result = await svc.get_life_map(
        user["user_id"],
        force_refresh=force,
        enrich=enrich,
    )
    return result.model_dump()


@router.get("/status")
async def life_map_status(user=Depends(get_current_user)):
    from life_map.gemini_interpret import life_map_gemini_enabled

    return {
        "ok": True,
        "enabled": True,
        "gemini": life_map_gemini_enabled(),
        "note": "Deterministic Life Map always available; Gemini enrichment optional.",
    }
