"""
AccessGuard — thin FastAPI-dependency wrapper around PermissionService.

Usage:

    from permissions.guard import require_capability

    @router.get("/foo")
    async def foo(
        _=Depends(require_capability("calendar.read", connector_id="calendar_google"))
    ):
        ...

The guard REJECTS the request with 403 if consent is missing OR the
capability is disabled. Everything is audited via PermissionService.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request

from deps import get_current_user, get_permissions_service

from .errors import CapabilityDisabled, CapabilityUnknown, ConsentDenied
from .models import INSTANCE_WILDCARD


def require_capability(
    capability_id: str,
    *,
    connector_id: str,
    connector_instance_id: str = INSTANCE_WILDCARD,
    purpose_id: Optional[str] = None,
):
    """FastAPI dependency factory."""

    async def _dep(
        request: Request,
        user=Depends(get_current_user),
    ):
        permissions = get_permissions_service()
        instance = connector_instance_id
        try:
            await permissions.require_access(
                user_id=user["user_id"],
                capability_id=capability_id,
                connector_id=connector_id,
                connector_instance_id=instance,
                purpose_id=purpose_id,
                request_id=request.headers.get("x-request-id"),
                correlation_id=request.headers.get("x-correlation-id"),
            )
        except CapabilityUnknown:
            raise HTTPException(status_code=404, detail=f"Capability sconosciuta: {capability_id}")
        except CapabilityDisabled:
            raise HTTPException(status_code=403, detail=f"Capability disabilitata: {capability_id}")
        except ConsentDenied:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "consent_denied",
                    "capability_id": capability_id,
                    "connector_id": connector_id,
                    "connector_instance_id": instance,
                },
            )
        return {"user": user, "capability_id": capability_id, "connector_id": connector_id}

    return _dep
