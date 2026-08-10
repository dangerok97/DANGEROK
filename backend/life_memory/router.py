"""Life Memory HTTP API — Memoria + clarification loop (Prompt 6 / 6.1)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from deps import get_current_user
from life_memory.clarify import get_clarification_service
from life_memory.models import ClarifyAnswerBody, ClarifyStartBody
from life_memory.service import get_life_memory_service

router = APIRouter(prefix="/life-memory", tags=["life_memory"])


@router.get("")
async def get_life_memory(
    force: bool = Query(False, description="Bypass AI wording cache when MEMORY_GEMINI=1"),
    enrich: Optional[bool] = Query(
        None,
        description="Override MEMORY_GEMINI for this request (None = use env flag)",
    ),
    user=Depends(get_current_user),
):
    svc = get_life_memory_service()
    result = await svc.get_life_memory(
        user["user_id"],
        force_refresh=force,
        enrich=enrich,
    )
    return result.model_dump()


@router.get("/status")
async def life_memory_status(user=Depends(get_current_user)):
    from life_memory.gemini_present import life_memory_gemini_enabled

    return {
        "ok": True,
        "enabled": True,
        "gemini": life_memory_gemini_enabled(),
        "controls": {
            "correct": False,
            "forget": False,
            "confirm": False,
            "clarify": True,
        },
        "note": (
            "Deterministic Life Memory always available. "
            "Ambiguous items open AI clarification via /life-memory/clarify/*."
        ),
    }


@router.post("/clarify/start")
async def clarify_start(body: ClarifyStartBody, user=Depends(get_current_user)):
    svc = get_clarification_service()
    result = await svc.start(user["user_id"], body.memory_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "clarify_failed")
    return result


@router.get("/clarify/{session_id}")
async def clarify_get(session_id: str, user=Depends(get_current_user)):
    svc = get_clarification_service()
    sess = await svc.get(user["user_id"], session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="session_not_found")
    return {"ok": True, "session": sess.public()}


@router.post("/clarify/{session_id}/answer")
async def clarify_answer(
    session_id: str,
    body: ClarifyAnswerBody,
    user=Depends(get_current_user),
):
    svc = get_clarification_service()
    result = await svc.answer(user["user_id"], session_id, body.text)
    if result.get("error") == "session_not_found":
        raise HTTPException(status_code=404, detail="session_not_found")
    if result.get("error") == "gemini_unavailable":
        # Recoverable — keep ambiguity; 503-like soft for FE
        return {**result, "ok": False, "status_code": 503}
    if not result.get("ok") and result.get("error"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result
