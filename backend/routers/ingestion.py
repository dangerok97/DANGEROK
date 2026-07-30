"""INGESTION router — read-only endpoints on ingestion events."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from deps import get_current_user, get_ingestion_service

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.get("/events")
async def list_events(
    connector_id: Optional[str] = None,
    connector_instance_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    user=Depends(get_current_user),
):
    svc = get_ingestion_service()
    items = await svc.list_events(
        user["user_id"],
        connector_id=connector_id,
        connector_instance_id=connector_instance_id,
        status=status,
        limit=limit,
    )
    return {"items": items}


@router.get("/events/{event_id}")
async def get_event(event_id: str, user=Depends(get_current_user)):
    svc = get_ingestion_service()
    doc = await svc.get_event(user["user_id"], event_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Evento di ingestion non trovato")
    return doc


@router.get("/stats")
async def get_stats(user=Depends(get_current_user)):
    svc = get_ingestion_service()
    return await svc.stats(user["user_id"])
