"""Google Calendar router — OAuth + instance management endpoints."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from deps import get_current_user, get_google_calendar_service
from permissions import ConsentDenied

from .oauth import OAuthConfigError, OAuthStateInvalid
from .provider import ProviderNotConfigured

router = APIRouter(prefix="/connectors/google-calendar", tags=["google_calendar"])


class OAuthStartIn(BaseModel):
    redirect_after: Optional[str] = None


class OAuthCallbackFakeIn(BaseModel):
    state: str
    code: Optional[str] = "fake-code"
    fake_account: Dict[str, Any]


class SelectCalendarsIn(BaseModel):
    calendar_ids: List[str]


@router.post("/oauth/start")
async def oauth_start(body: OAuthStartIn, user=Depends(get_current_user)):
    svc = get_google_calendar_service()
    try:
        return await svc.start_oauth(user_id=user["user_id"], redirect_after=body.redirect_after)
    except ProviderNotConfigured as e:
        raise HTTPException(status_code=503, detail={"error": "provider_not_configured", "message": str(e)})
    except OAuthConfigError as e:
        raise HTTPException(status_code=503, detail={"error": "oauth_config_error", "message": str(e)})


@router.get("/oauth/callback")
async def oauth_callback(request: Request, state: str = Query(...), code: str = Query(...)):
    """Real OAuth callback — hit by Google after the user authorizes.
    Requires no auth header (Google-provided state binds the flow to the
    user that started it)."""
    svc = get_google_calendar_service()
    try:
        instance = await svc.handle_oauth_callback(state=state, code=code)
    except OAuthStateInvalid as e:
        raise HTTPException(status_code=400, detail={"error": "oauth_state_invalid", "message": str(e)})
    except OAuthConfigError as e:
        raise HTTPException(status_code=503, detail={"error": "oauth_config_error", "message": str(e)})
    except ProviderNotConfigured as e:
        raise HTTPException(status_code=503, detail={"error": "provider_not_configured", "message": str(e)})
    return {"ok": True, "instance": instance}


@router.post("/oauth/callback-fake")
async def oauth_callback_fake(body: OAuthCallbackFakeIn):
    """Test-only callback. Rejected unless CALENDAR_PROVIDER_MODE=fake."""
    import os
    if os.environ.get("CALENDAR_PROVIDER_MODE", "real").lower() != "fake":
        raise HTTPException(status_code=404, detail="Fake callback disabled")
    svc = get_google_calendar_service()
    try:
        instance = await svc.handle_oauth_callback(
            state=body.state, code=body.code or "fake-code", fake_account=body.fake_account,
        )
    except OAuthStateInvalid as e:
        raise HTTPException(status_code=400, detail={"error": "oauth_state_invalid", "message": str(e)})
    return {"ok": True, "instance": instance}


@router.get("/instances")
async def list_instances(user=Depends(get_current_user)):
    svc = get_google_calendar_service()
    return {"items": await svc.list_instances(user["user_id"])}


@router.get("/instances/{instance_id}")
async def get_instance(instance_id: str, user=Depends(get_current_user)):
    svc = get_google_calendar_service()
    inst = await svc.get_instance(user["user_id"], instance_id)
    if not inst:
        raise HTTPException(status_code=404, detail="Istanza connector non trovata")
    return inst


@router.get("/instances/{instance_id}/calendars")
async def list_calendars(instance_id: str, user=Depends(get_current_user)):
    svc = get_google_calendar_service()
    try:
        return {"items": await svc.list_calendars_for_instance(user_id=user["user_id"], instance_id=instance_id)}
    except LookupError:
        raise HTTPException(status_code=404, detail="Istanza connector non trovata")
    except ConsentDenied as e:
        raise HTTPException(status_code=403, detail={"error": "consent_denied", "capability_id": e.capability_id})
    except ProviderNotConfigured as e:
        raise HTTPException(status_code=503, detail={"error": "provider_not_configured", "message": str(e)})


@router.post("/instances/{instance_id}/select-calendars")
async def select_calendars(instance_id: str, body: SelectCalendarsIn, user=Depends(get_current_user)):
    svc = get_google_calendar_service()
    try:
        return await svc.select_calendars(
            user_id=user["user_id"], instance_id=instance_id, calendar_ids=body.calendar_ids,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Istanza connector non trovata")


@router.post("/instances/{instance_id}/sync")
async def sync_instance(instance_id: str, user=Depends(get_current_user)):
    svc = get_google_calendar_service()
    try:
        return await svc.sync(user_id=user["user_id"], instance_id=instance_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Istanza connector non trovata")
    except ConsentDenied as e:
        raise HTTPException(status_code=403, detail={"error": "consent_denied", "capability_id": e.capability_id})
    except ProviderNotConfigured as e:
        raise HTTPException(status_code=503, detail={"error": "provider_not_configured", "message": str(e)})


@router.post("/instances/{instance_id}/refresh")
async def refresh_instance(instance_id: str, user=Depends(get_current_user)):
    svc = get_google_calendar_service()
    try:
        return await svc.refresh(user_id=user["user_id"], instance_id=instance_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Istanza connector non trovata")
    except ConsentDenied as e:
        raise HTTPException(status_code=403, detail={"error": "consent_denied", "capability_id": e.capability_id})
    except ProviderNotConfigured as e:
        raise HTTPException(status_code=503, detail={"error": "provider_not_configured", "message": str(e)})


@router.post("/instances/{instance_id}/revoke")
async def revoke_instance(instance_id: str, user=Depends(get_current_user)):
    svc = get_google_calendar_service()
    try:
        return await svc.revoke(user_id=user["user_id"], instance_id=instance_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Istanza connector non trovata")


@router.get("/instances/{instance_id}/status")
async def get_status(instance_id: str, user=Depends(get_current_user)):
    svc = get_google_calendar_service()
    try:
        return await svc.status(user_id=user["user_id"], instance_id=instance_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Istanza connector non trovata")
