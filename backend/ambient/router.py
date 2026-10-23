"""
What a client needs, and a debug surface for everything else.

Three of these are real: registering a device so it can be reached, releasing
it on logout, and telling the backend whether somebody is looking at the app.
The rest exist so a wake can be inspected or forced during development, and
none of them sends anything — sending is what happens to a plan whose moment
arrives and whose facts still hold.

No endpoint here ever returns a push token.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from deps import get_current_user

router = APIRouter(prefix="/ambient", tags=["ambient"])


class RegisterIn(BaseModel):
    # An Expo push token, or a browser PushSubscription serialised as JSON.
    # Written once, never read back out.
    token: str = Field(max_length=1200)
    platform: str = Field(default="unknown", max_length=12)
    # An opaque device string; only its hash is stored.
    device: str = Field(default="", max_length=200)
    permission_state: str = Field(default="granted", max_length=16)
    device_revision: int = Field(default=0, ge=0, le=9007199254740991)
    # Only the explicit notification enable action requests account consent.
    # A foreground/token refresh must not undo a deliberate revocation.
    request_delivery_permission: bool = False


class ReleaseIn(BaseModel):
    device: str = Field(default="", max_length=200)


class LevelIn(BaseModel):
    # minimal | balanced | proactive. A fact for the judgement, never a switch.
    level: str = Field(max_length=16)


class QuietHoursIn(BaseModel):
    enabled: bool = False
    start_hour: int = Field(default=22, ge=0, le=23)
    end_hour: int = Field(default=7, ge=0, le=23)


class SuppressIn(BaseModel):
    # The concern to stop being reached about. Not the same as dismissing it.
    opportunity_id: str = Field(max_length=64)


class AppStateIn(BaseModel):
    # foreground | background. A fact about where somebody is looking, with a
    # timestamp — never a rule about what may be sent.
    state: str = Field(max_length=16)


def _dev_only() -> None:
    if os.environ.get("DEV", "").strip().lower() not in ("1", "true", "on"):
        raise HTTPException(status_code=404, detail="not_found")


@router.post("/push/register")
async def register(body: RegisterIn, user=Depends(get_current_user),
                   authorization: str = Header(...)):
    """
    This device can be reached, and it belongs to this account.

    Idempotent, and it releases the device from whoever had it before.
    """
    from ambient.push import PushEndpointService
    from deps import db, pyjwt, JWT_SECRET, JWT_ALGO
    from session_revocation import token_digest

    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        expires_at = datetime.fromtimestamp(claims["exp"], timezone.utc).isoformat()
    except (pyjwt.PyJWTError, KeyError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid token")

    push_token = body.token
    if body.platform == "web":
        from ambient.webpush import subscription_token

        push_token = subscription_token(body.token) or ""
        if not push_token:
            raise HTTPException(status_code=400, detail="invalid_subscription")
    result = await PushEndpointService(db).register(
        user["user_id"],
        token=push_token,
        platform=body.platform,
        device=body.device,
        permission_state=body.permission_state,
        session_digest=token_digest(token),
        session_expires_at=expires_at,
        device_revision=body.device_revision,
    )
    if not result.get("ok"):
        raise HTTPException(
            status_code=401 if result.get("reason") == "session_inactive" else 400,
            detail=result.get("reason"),
        )
    from permissions.errors import CapabilityDisabled
    from permissions.service import PermissionService

    permissions = PermissionService(db)
    capability = "notifications.deliver"
    available = await permissions.is_capability_enabled(capability)
    if body.request_delivery_permission and body.permission_state == "granted" and available:
        try:
            await permissions.grant(
                user_id=user["user_id"], capability_id=capability,
                connector_id="notifications", purpose_id="delivery",
                metadata={"source": "native_notification_enable"},
            )
        except CapabilityDisabled:
            # A capability switch may race this request. Do not call the
            # account unauthenticated or claim delivery was enabled.
            available = False
    result["delivery_available"] = available
    result["delivery_allowed"] = available and await permissions.check_access(
        user_id=user["user_id"], capability_id=capability,
        connector_id="notifications", audit=False,
    )
    return result


@router.get("/push/web-config")
async def web_config(user=Depends(get_current_user)):
    """The public application-server key a browser subscribes with."""
    from ambient.webpush import vapid_public_key

    key = vapid_public_key()
    return {"available": bool(key), "public_key": key}


_last_test: dict = {}


@router.post("/push/test")
async def send_test(user=Depends(get_current_user)):
    """
    A notification the person asked for, to their own devices, right now.

    The only send that skips the delivery judgement — because the person
    tapped "Prova" — and it carries no content from their life. The result
    says what each push service accepted; acceptance is not "seen".
    """
    import time as _time

    from delivery.provider import get_provider

    owner = user["user_id"]
    now = _time.monotonic()
    if now - _last_test.get(owner, -1e9) < 20:
        raise HTTPException(status_code=429, detail="test_too_soon")
    _last_test[owner] = now
    words = {"title": "ORA", "body": "Le notifiche funzionano. Ti avviso così quando serve."}
    outcome = await get_provider().send(
        owner_id=owner, plan_id=f"dlv_test{int(_time.time())}",
        title=words["title"], body=words["body"], deep_link="/",
        public_title=words["title"], public_body=words["body"],
    )
    return {
        "ok": bool(outcome.get("ok")),
        "provider": outcome.get("provider"),
        "accepted": int(outcome.get("provider_accepted") or 0),
        "reason": outcome.get("reason"),
    }


@router.post("/push/release")
async def release(body: ReleaseIn, user=Depends(get_current_user),
                  authorization: str = Header(...)):
    """Logout: nothing arrives on this phone for this account again."""
    from ambient.push import PushEndpointService
    from deps import db
    from session_revocation import token_digest

    return await PushEndpointService(db).release_device(
        user["user_id"], body.device,
        session_digest=token_digest(authorization.split(" ", 1)[1].strip()),
    )


@router.get("/push/endpoints")
async def endpoints(user=Depends(get_current_user)):
    """Which devices are reachable. Tokens are absent by construction."""
    from ambient.push import PushEndpointService
    from deps import db

    return {"endpoints": await PushEndpointService(db).endpoints(user["user_id"])}


@router.post("/app-state")
async def app_state(body: AppStateIn, user=Depends(get_current_user)):
    """
    Whether somebody is looking at ORA right now.

    App presence, not life presence: this says nothing about where they are.
    Recorded with a timestamp so a stale flag resolves to `unknown` rather
    than to a guess that gets less true every minute.
    """
    from ambient.service import AmbientService
    from deps import db

    result = await AmbientService(db).record_app_state(user["user_id"], body.state)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("reason"))
    return result


@router.get("/wakes")
async def wakes(user=Depends(get_current_user)):
    """Arranged moments for this person. Handles only, never content."""
    from ambient.repository import AmbientRepository
    from deps import db

    found = await AmbientRepository(db).open_wakes(user["user_id"])
    return {"wakes": [w.public() for w in found]}


@router.post("/tick")
async def force_tick(user=Depends(get_current_user)):
    """
    Run one runtime pass by hand. Development only.

    The runtime does this on its own; this exists so a wake can be watched
    rather than waited for.
    """
    _dev_only()
    from ambient.runtime import tick
    from deps import db

    return await tick(db)


@router.get("/runtime")
async def runtime_status(user=Depends(get_current_user)):
    """Whether the loop is alive, and what it has been doing. Counts only."""
    _dev_only()
    from ambient.runtime import runtime_stats

    return runtime_stats()


@router.get("/preferences")
async def preferences(user=Depends(get_current_user)):
    """What they have said about being interrupted. Default until they choose."""
    from ambient.preferences import PreferenceService
    from deps import db

    prefs = await PreferenceService(db).get(user["user_id"])
    return {
        "preferences": prefs.public(),
        "muted": len(await PreferenceService(db).suppressed_targets(user["user_id"])),
    }


@router.post("/preferences/level")
async def set_level(body: LevelIn, user=Depends(get_current_user)):
    """
    How much they want to be reached.

    Stored as a fact and handed to the judgement. Nothing downstream branches
    on it: somebody who asked for less noise has not asked to be kept in the
    dark about the one thing that would have mattered.
    """
    from ambient.preferences import PreferenceService
    from deps import db

    result = await PreferenceService(db).set_level(user["user_id"], body.level)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("reason"))
    return result


@router.post("/preferences/quiet-hours")
async def set_quiet_hours(body: QuietHoursIn, user=Depends(get_current_user)):
    """When they would rather not hear from anybody. Off unless set."""
    from ambient.preferences import PreferenceService
    from deps import db

    return await PreferenceService(db).set_quiet_hours(
        user["user_id"],
        enabled=body.enabled,
        start_hour=body.start_hour,
        end_hour=body.end_hour,
    )


@router.post("/preferences/mute")
async def mute(body: SuppressIn, user=Depends(get_current_user)):
    """
    "Non notificarmi per questa cosa."

    Owner-bound, and deliberately not a dismissal: the concern stays exactly
    as active and as visible as it was. Only the pocket goes quiet.
    """
    from ambient.preferences import PreferenceService
    from deps import db

    result = await PreferenceService(db).suppress(user["user_id"], body.opportunity_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("reason"))
    return result


@router.post("/preferences/unmute")
async def unmute(body: SuppressIn, user=Depends(get_current_user)):
    from ambient.preferences import PreferenceService
    from deps import db

    return await PreferenceService(db).unsuppress(user["user_id"], body.opportunity_id)


@router.post("/fallback")
async def fallback(user=Depends(get_current_user)):
    """
    Cast the safety net by hand. Development only.

    Deterministic and cheap: it answers whether there is any concrete reason
    to look again, and arranges a wake if there is. It never reaches a model.
    """
    _dev_only()
    from ambient.eligibility import EligibilityService
    from deps import db

    return await EligibilityService(db).sweep()
