"""
The four things a person can do with a mailbox connection, and no fifth.

    /connectors/gmail/oauth/start      begin connecting (authenticated)
    /connectors/gmail/oauth/callback   where Google comes back
    /connectors/gmail/instances        what is connected
    /connectors/gmail/instances/{id}/sync    read it now
    /connectors/gmail/instances/{id}/revoke  disconnect it

Shaped after the calendar's router because the shapes should match: start is
a POST because it mints state, the callback is a GET because Google performs
it as a browser redirect and carries no credentials of ours, and everything
else is owner-scoped through the same dependency.

There is deliberately no endpoint that returns a message, a list of messages,
a count, or a mailbox. Reading somebody's mail is what the sensor does on the
way to a judgement; it is not a thing this API offers.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from deps import get_current_user, get_gmail_service
from permissions import ConsentDenied

from connectors.google_calendar.oauth import (
    OAuthConfigError,
    OAuthStateInvalid,
    sanitize_redirect_after,
)

router = APIRouter(prefix="/connectors/gmail", tags=["gmail"])


class OAuthStartIn(BaseModel):
    redirect_after: Optional[str] = None
    # An explicit backend callback, which still has to be one of the
    # registered ones. Offered for the same reason the calendar offers it: a
    # person who reached the app on 127.0.0.1 must come back to 127.0.0.1.
    redirect_uri: Optional[str] = None


def _request_base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _append_query(url: str, **params: str) -> str:
    parsed = urlparse(url)
    q = dict(parse_qsl(parsed.query, keep_blank_values=True))
    q.update({k: v for k, v in params.items() if v is not None})
    return urlunparse(parsed._replace(query=urlencode(q)))


@router.post("/oauth/start")
async def oauth_start(
    body: OAuthStartIn, request: Request, user=Depends(get_current_user),
):
    """Where to send this person so Google can ask them about their mailbox."""
    try:
        return await get_gmail_service().start_oauth(
            user_id=user["user_id"],
            redirect_after=body.redirect_after,
            request_base=_request_base(request),
            preferred_redirect_uri=body.redirect_uri,
        )
    except OAuthConfigError as e:
        raise HTTPException(
            status_code=503,
            detail={"error": "oauth_config_error", "message": str(e)},
        )


@router.get("/oauth/callback")
async def oauth_callback(
    request: Request,
    state: str = Query(...),
    code: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    """
    Where Google comes back. Unauthenticated by necessity, closed by default.

    There is no auth header on this request — Google performs it — so the
    state is the only thing binding it to the person who started, which is
    why it is one-shot, short-lived, owner-bound and flow-bound. A callback
    without a valid state fails and creates nothing.

    `error` is what Google sends when somebody says no. It is not an
    exception: they made a choice, and the honest response is to take them
    back where they were.
    """
    if error:
        return {"ok": False, "reason": "declined"}
    if not code:
        raise HTTPException(
            status_code=400,
            detail={"error": "oauth_code_missing", "message": "no code returned"},
        )
    try:
        result = await get_gmail_service().handle_oauth_callback(
            state=state, code=code,
        )
    except OAuthStateInvalid as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "oauth_state_invalid", "message": str(e)},
        )
    except OAuthConfigError as e:
        raise HTTPException(
            status_code=503,
            detail={"error": "oauth_config_error", "message": str(e)},
        )

    instance = result["instance"]
    redirect_after = sanitize_redirect_after(result.get("redirect_after"))
    if redirect_after:
        return RedirectResponse(
            url=_append_query(
                redirect_after, gmail="connected",
                instance_id=instance.get("id") or "",
            ),
            status_code=302,
        )
    return {"ok": True, "instance": instance}


@router.get("/instances")
async def list_instances(user=Depends(get_current_user)):
    return {"items": await get_gmail_service().list_instances(user["user_id"])}


@router.post("/instances/{instance_id}/sync")
async def sync_instance(instance_id: str, user=Depends(get_current_user)):
    """Read the mailbox now. Returns counts, never content."""
    try:
        return await get_gmail_service().sync(
            user_id=user["user_id"], instance_id=instance_id,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Istanza connector non trovata")
    except ConsentDenied as e:
        raise HTTPException(
            status_code=403,
            detail={"error": "consent_denied", "capability_id": e.capability_id},
        )


@router.post("/instances/{instance_id}/revoke")
async def revoke_instance(instance_id: str, user=Depends(get_current_user)):
    try:
        return await get_gmail_service().revoke(
            user_id=user["user_id"], instance_id=instance_id,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Istanza connector non trovata")


@router.get("/config-status")
async def config_status(user=Depends(get_current_user)):
    """Whether a mailbox could be connected. Booleans, never values."""
    return get_gmail_service().config_status()
