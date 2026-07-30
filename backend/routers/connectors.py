"""CONNECTORS router — stub listing + per-user consent status.

In this iteration there are NO endpoints that actually connect to a
third-party service. This router intentionally exposes ONLY:
    - registry listing / detail;
    - per-user consent state.
Real `connect`, `oauth`, `sync`, `webhook`, `poll` endpoints will land
in subsequent iterations, one connector at a time.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from connectors import CONNECTOR_REGISTRY_VERSION
from deps import get_connectors_service, get_current_user

router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.get("/registry")
async def list_registry(platform: Optional[str] = None):
    svc = get_connectors_service()
    return {
        "connector_registry_version": CONNECTOR_REGISTRY_VERSION,
        "items": svc.list_all(platform=platform),
    }


@router.get("/registry/{connector_id}")
async def get_registry_item(connector_id: str):
    svc = get_connectors_service()
    item = svc.get(connector_id)
    if not item:
        raise HTTPException(status_code=404, detail="Connector sconosciuto")
    return item


@router.get("/status")
async def status_for_user(connector_id: Optional[str] = None, user=Depends(get_current_user)):
    svc = get_connectors_service()
    items = await svc.status_for_user(user["user_id"], connector_id=connector_id)
    if connector_id and not items:
        raise HTTPException(status_code=404, detail="Connector sconosciuto")
    return {"items": items}
