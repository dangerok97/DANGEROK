"""HTTP surface for Life OS plans & GenerativeObjects (Goal Workspace)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from deps import db, get_current_user
from life_os.service import LifeOsService

router = APIRouter(prefix="/life-os", tags=["life-os"])


class InteractBody(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=80)
    payload: Dict[str, Any] = Field(default_factory=dict)


class SessionFocusBody(BaseModel):
    """Conversational focus for linked AI Core session (generic refs)."""

    session_id: str = Field(..., min_length=4, max_length=80)
    object_id: Optional[str] = Field(default=None, max_length=80)
    plan_id: Optional[str] = Field(default=None, max_length=80)
    plan_item_id: Optional[str] = Field(default=None, max_length=80)
    event_type: Optional[str] = Field(default="object_opened", max_length=80)


@router.get("/plans/{plan_id}")
async def get_plan_workspace(
    plan_id: str,
    user=Depends(get_current_user),
):
    uid = user["user_id"]
    svc = LifeOsService(db)
    bundle = await svc.get_active_bundle(uid, plan_id=plan_id)
    if not bundle.get("plan"):
        raise HTTPException(status_code=404, detail="plan_not_found")
    # Soft-bind conversational focus when workspace is opened
    plan = bundle.get("plan") or {}
    sess = plan.get("conversation_session_id")
    objs = bundle.get("objects") or []
    if sess and objs:
        try:
            await svc.bind_session_object_focus(
                uid,
                session_id=str(sess),
                object_id=str(objs[0].get("id") or "") or None,
                plan_id=plan_id,
                plan_item_id=(bundle.get("next_item") or {}).get("id"),
                event_type="object_opened",
            )
        except Exception:
            pass
    return {"ok": True, **bundle}


@router.get("/objects/{object_id}")
async def get_object(
    object_id: str,
    user=Depends(get_current_user),
):
    svc = LifeOsService(db)
    obj = await svc.repo.get_object(user["user_id"], object_id)
    if not obj:
        raise HTTPException(status_code=404, detail="object_not_found")
    return {"ok": True, "object": obj.public()}


@router.post("/objects/{object_id}/interact")
async def interact_object(
    object_id: str,
    body: InteractBody,
    user=Depends(get_current_user),
):
    svc = LifeOsService(db)
    res = await svc.record_object_interaction(
        user["user_id"],
        object_id,
        event_type=body.event_type,
        payload=body.payload,
    )
    if not res:
        raise HTTPException(status_code=404, detail="object_not_found")
    return {"ok": True, **res}


@router.post("/session-focus")
async def set_session_focus(
    body: SessionFocusBody,
    user=Depends(get_current_user),
):
    """Workspace → AI continuity: set active_object_ref / plan item on session."""
    svc = LifeOsService(db)
    res = await svc.bind_session_object_focus(
        user["user_id"],
        session_id=body.session_id,
        object_id=body.object_id,
        plan_id=body.plan_id,
        plan_item_id=body.plan_item_id,
        event_type=body.event_type or "object_opened",
    )
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("reason") or "not_found")
    return res
