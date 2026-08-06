"""HTTP API for Proactive Engine suggestions."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from deps import db, get_current_user
from proactive_engine.models import SearchBody, SnoozeBody
from proactive_engine.service import ProactiveEngineService, proactive_engine_enabled

router = APIRouter(prefix="/suggestions", tags=["proactive_engine"])


def _svc() -> ProactiveEngineService:
    return ProactiveEngineService(db)


@router.get("")
async def list_suggestions(
    status: Optional[str] = Query(None),
    type: Optional[str] = Query(None, alias="type"),
    limit: int = Query(40, ge=1, le=100),
    regenerate_if_empty: bool = Query(False),
    user=Depends(get_current_user),
):
    return await _svc().list_suggestions(
        user["user_id"],
        status=status,
        suggestion_type=type,
        limit=limit,
        regenerate_if_empty=regenerate_if_empty,
    )


@router.post("/regenerate")
async def regenerate(user=Depends(get_current_user)):
    return await _svc().regenerate(user["user_id"])


@router.post("/search")
async def search(body: SearchBody, user=Depends(get_current_user)):
    return await _svc().search(
        user["user_id"],
        q=body.q,
        suggestion_type=body.type,
        status=body.status,
        limit=body.limit,
    )


@router.get("/{suggestion_id}")
async def get_suggestion(suggestion_id: str, user=Depends(get_current_user)):
    s = await _svc().repo.get(user["user_id"], suggestion_id)
    if not s:
        raise HTTPException(status_code=404, detail="not_found")
    return {"suggestion": s.public(), "enabled": proactive_engine_enabled()}


@router.get("/{suggestion_id}/explain")
async def explain_suggestion(suggestion_id: str, user=Depends(get_current_user)):
    res = await _svc().explain(user["user_id"], suggestion_id)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res


@router.post("/{suggestion_id}/dismiss")
async def dismiss(suggestion_id: str, user=Depends(get_current_user)):
    res = await _svc().dismiss(user["user_id"], suggestion_id)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res


@router.post("/{suggestion_id}/accept")
async def accept(suggestion_id: str, user=Depends(get_current_user)):
    res = await _svc().accept(user["user_id"], suggestion_id)
    if not res.get("ok"):
        code = 404 if res.get("error") == "not_found" else 400
        raise HTTPException(status_code=code, detail=res.get("error") or "accept_failed")
    return res


@router.post("/{suggestion_id}/complete")
async def complete(suggestion_id: str, user=Depends(get_current_user)):
    res = await _svc().complete(user["user_id"], suggestion_id)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res


@router.post("/{suggestion_id}/snooze")
async def snooze(suggestion_id: str, body: SnoozeBody, user=Depends(get_current_user)):
    res = await _svc().snooze(
        user["user_id"], suggestion_id, preset=body.preset, until=body.until,
    )
    if not res.get("ok"):
        code = 404 if res.get("error") == "not_found" else 400
        raise HTTPException(status_code=code, detail=res.get("error") or "snooze_failed")
    return res


@router.get("/{suggestion_id}/notification-policy")
async def notification_policy(suggestion_id: str, user=Depends(get_current_user)):
    res = await _svc().notification_preview(user["user_id"], suggestion_id)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res
