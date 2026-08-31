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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from deps import get_current_user

router = APIRouter(prefix="/ambient", tags=["ambient"])


class RegisterIn(BaseModel):
    # An Expo push token. Written once, never read back out.
    token: str = Field(max_length=400)
    platform: str = Field(default="unknown", max_length=12)
    # An opaque device string; only its hash is stored.
    device: str = Field(default="", max_length=200)
    permission_state: str = Field(default="granted", max_length=16)


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
async def register(body: RegisterIn, user=Depends(get_current_user)):
    """
    This device can be reached, and it belongs to this account.

    Idempotent, and it releases the device from whoever had it before.
    """
    from ambient.push import PushEndpointService
    from deps import db

    result = await PushEndpointService(db).register(
        user["user_id"],
        token=body.token,
        platform=body.platform,
        device=body.device,
        permission_state=body.permission_state,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("reason"))
    return result


@router.post("/push/release")
async def release(body: ReleaseIn, user=Depends(get_current_user)):
    """Logout: nothing arrives on this phone for this account again."""
    from ambient.push import PushEndpointService
    from deps import db

    return await PushEndpointService(db).release_device(user["user_id"], body.device)


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
