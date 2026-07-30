"""PERMISSIONS router — capability registry + consent + audit endpoints."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from deps import DEMO_EMAILS, get_current_user, get_permissions_service
from permissions import (
    CAPABILITY_REGISTRY_VERSION,
    CapabilityDisabled,
    CapabilityUnknown,
    capability_by_id,
)
from permissions.capabilities import as_dict as _cap_as_dict
from permissions.models import INSTANCE_WILDCARD

router = APIRouter(prefix="/permissions", tags=["permissions"])


class GrantIn(BaseModel):
    capability_id: str
    connector_id: str
    connector_instance_id: str = INSTANCE_WILDCARD
    purpose_id: Optional[str] = None
    scopes: Optional[List[str]] = None
    expires_at: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class RevokeIn(BaseModel):
    capability_id: str
    connector_id: str
    connector_instance_id: str = INSTANCE_WILDCARD
    reason: Optional[str] = None


class RevokeAllIn(BaseModel):
    connector_id: str
    reason: Optional[str] = None


class AdminToggleIn(BaseModel):
    enabled: bool


@router.get("/registry")
async def get_registry():
    """Public catalog of capabilities (structural, from the frozen registry)."""
    perms = get_permissions_service()
    items = await perms.list_capabilities_with_meta()
    return {
        "capability_registry_version": CAPABILITY_REGISTRY_VERSION,
        "items": items,
    }


@router.get("/registry/{capability_id}")
async def get_capability(capability_id: str):
    cap = capability_by_id(capability_id)
    if not cap:
        raise HTTPException(status_code=404, detail="Capability sconosciuta")
    perms = get_permissions_service()
    meta = await perms.get_meta(capability_id) or {}
    data = _cap_as_dict(cap)
    data["enabled"] = bool(meta.get("enabled", cap["default_status"] != "disabled"))
    data["rollout_notes"] = meta.get("rollout_notes")
    return data


@router.get("/consents")
async def list_consents(
    status: Optional[str] = None,
    connector_id: Optional[str] = None,
    capability_id: Optional[str] = None,
    user=Depends(get_current_user),
):
    perms = get_permissions_service()
    items = await perms.consents.list_for_user(
        user["user_id"], status=status, connector_id=connector_id, capability_id=capability_id,
    )
    return {"items": items}


@router.post("/consents/grant")
async def grant_consent(body: GrantIn, request: Request, user=Depends(get_current_user)):
    perms = get_permissions_service()
    try:
        doc = await perms.grant(
            user_id=user["user_id"],
            capability_id=body.capability_id,
            connector_id=body.connector_id,
            connector_instance_id=body.connector_instance_id,
            purpose_id=body.purpose_id,
            scopes=body.scopes,
            expires_at=body.expires_at,
            metadata=body.metadata,
            correlation_id=request.headers.get("x-correlation-id"),
            request_id=request.headers.get("x-request-id"),
        )
    except CapabilityUnknown:
        raise HTTPException(status_code=404, detail=f"Capability sconosciuta: {body.capability_id}")
    except CapabilityDisabled:
        raise HTTPException(status_code=403, detail=f"Capability disabilitata: {body.capability_id}")
    return doc


@router.post("/consents/revoke")
async def revoke_consent(body: RevokeIn, request: Request, user=Depends(get_current_user)):
    perms = get_permissions_service()
    doc = await perms.revoke(
        user_id=user["user_id"],
        capability_id=body.capability_id,
        connector_id=body.connector_id,
        connector_instance_id=body.connector_instance_id,
        reason=body.reason,
        correlation_id=request.headers.get("x-correlation-id"),
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Nessun consenso attivo per questa combinazione")
    return doc


@router.post("/consents/revoke-all")
async def revoke_all(body: RevokeAllIn, user=Depends(get_current_user)):
    perms = get_permissions_service()
    count = await perms.revoke_all_for_connector(
        user["user_id"], body.connector_id, reason=body.reason,
    )
    return {"revoked_count": count, "connector_id": body.connector_id}


@router.get("/audit")
async def list_audit(
    limit: int = 100,
    capability_id: Optional[str] = None,
    connector_id: Optional[str] = None,
    event_type: Optional[str] = None,
    user=Depends(get_current_user),
):
    perms = get_permissions_service()
    items = await perms.audit.list_for_user(
        user["user_id"], limit=limit,
        capability_id=capability_id, connector_id=connector_id, event_type=event_type,
    )
    return {"items": items}


# --- Admin (demo-guarded) ------------------------------------------
@router.post("/admin/registry/sync")
async def admin_sync(user=Depends(get_current_user)):
    """Re-run registry sync. Demo-guarded (structural fields are always
    written from code; ops metadata is preserved)."""
    if user["email"] not in DEMO_EMAILS:
        raise HTTPException(status_code=403, detail="Endpoint riservato agli utenti demo")
    perms = get_permissions_service()
    return await perms.sync_registry()


@router.patch("/admin/registry/{capability_id}")
async def admin_toggle(capability_id: str, body: AdminToggleIn, user=Depends(get_current_user)):
    if user["email"] not in DEMO_EMAILS:
        raise HTTPException(status_code=403, detail="Endpoint riservato agli utenti demo")
    perms = get_permissions_service()
    try:
        doc = await perms.set_enabled(capability_id, body.enabled, admin_actor=user["email"])
    except CapabilityUnknown:
        raise HTTPException(status_code=404, detail="Capability sconosciuta")
    if not doc:
        raise HTTPException(status_code=404, detail="Capability non ancora sincronizzata")
    return doc
