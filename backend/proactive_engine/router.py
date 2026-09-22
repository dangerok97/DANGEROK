"""HTTP API for Proactive Engine suggestions."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field
from types import SimpleNamespace
import json

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


class PreparationReply(BaseModel):
    reply: str = Field(default="", max_length=2000)


async def _preparation_work(user_id, suggestion_id, *, start=False, reply=""):
    from opportunities.work import update_work
    svc = _svc()
    suggestion = await svc.repo.get(user_id, suggestion_id)
    if suggestion is None:
        raise HTTPException(404, "not_found")
    if not suggestion.action or suggestion.action.kind != "prepare_change":
        raise HTTPException(409, "Nessuna preparazione disponibile per questo aggiornamento.")
    if start and suggestion.status not in ("active", "snoozed"):
        raise HTTPException(409, "La segnalazione è superata. Riapri gli aggiornamenti.")
    if start and suggestion.type == "calendar":
        await svc.refresh_calendar(user_id)
        suggestion = await svc.repo.get(user_id, suggestion_id)
        if suggestion.status not in ("active", "snoozed"):
            raise HTTPException(409, "La segnalazione è superata. Riapri gli aggiornamenti.")
    prep = suggestion.meta.get("preparation") or {}
    context = SimpleNamespace(id=suggestion.id, semantic_summary=suggestion.description or suggestion.title,
        what_ora_can_do="Prepara una proposta di spostamento, senza eseguirla. Chiedi quale impegno si può spostare. "
            "Ricontrolla gli eventi attuali prima di proporre una modifica. Queste alternative sono indicative: "
            + json.dumps(prep, ensure_ascii=False), evidence=[])
    return await update_work(db, user_id, context, start=start, reply=reply, source_kind="suggestion")


@router.get("/{suggestion_id}/work")
async def get_preparation_work(suggestion_id: str, user=Depends(get_current_user)):
    return await _preparation_work(user["user_id"], suggestion_id)


@router.post("/{suggestion_id}/work")
async def start_preparation_work(suggestion_id: str, body: PreparationReply, user=Depends(get_current_user)):
    return await _preparation_work(user["user_id"], suggestion_id, start=True, reply=body.reply)
