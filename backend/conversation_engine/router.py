"""HTTP API under /api/conversation — orchestration only, not a chatbot."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from conversation_engine.models import (
    CancelBody,
    ContinueBody,
    MessageBody,
    ResumeBody,
    StartBody,
)
from conversation_engine.service import ConversationEngineService, conversation_engine_enabled
from deps import db, decisions, get_current_user, knowledge, life_graph

router = APIRouter(prefix="/conversation", tags=["conversation_engine"])

_svc: ConversationEngineService | None = None


def get_conversation_engine() -> ConversationEngineService:
    global _svc
    if _svc is None:
        _svc = ConversationEngineService(
            db, life_graph=life_graph, knowledge=knowledge, decisions=decisions,
        )
    return _svc


def _raise(res: dict):
    err = res.get("error")
    if err == "not_found":
        raise HTTPException(status_code=404, detail=err)
    if err == "conversation_engine_disabled":
        raise HTTPException(status_code=503, detail=res)
    if err == "text_required":
        raise HTTPException(status_code=400, detail=err)
    if err == "forbidden":
        raise HTTPException(status_code=403, detail=err)
    if err == "session_closed":
        raise HTTPException(status_code=400, detail=err)
    # The reasoning produced a blocking question and the store would not take
    # it. Nothing is wrong with the request, so this is not a 4xx: the same
    # message sent again is expected to work, and the client already retries.
    if err == "blocking_question_not_durable":
        raise HTTPException(status_code=503, detail=err)
    if err:
        raise HTTPException(status_code=400, detail=res.get("message") or err)


@router.get("")
async def conversation_list(
    limit: int = Query(10, ge=1, le=40),
    user=Depends(get_current_user),
):
    sessions = await get_conversation_engine().list_resumable(user["user_id"], limit=limit)
    return {"ok": True, "sessions": sessions, "enabled": conversation_engine_enabled()}


@router.post("/start")
async def conversation_start(body: StartBody, user=Depends(get_current_user)):
    svc = get_conversation_engine()
    res = await svc.start(
        user["user_id"],
        text=body.text,
        origin=body.origin,
        voice_meta=body.voice_meta,
        suggestion_id=body.suggestion_id,
        context=body.context,
        force_new=body.force_new,
    )
    if not res.get("ok") and res.get("error"):
        _raise(res)
    return {**res, "enabled": conversation_engine_enabled()}


@router.post("/resume")
async def conversation_resume(body: ResumeBody, user=Depends(get_current_user)):
    if not body.session_id and not body.resume_token:
        raise HTTPException(status_code=400, detail="session_id or resume_token required")
    res = await get_conversation_engine().resume(
        user["user_id"],
        session_id=body.session_id,
        resume_token=body.resume_token,
    )
    if not res.get("ok"):
        _raise(res)
    return res


@router.get("/resume-token/{token}")
async def conversation_by_resume_token(token: str, user=Depends(get_current_user)):
    res = await get_conversation_engine().resume(
        user["user_id"], resume_token=token,
    )
    if not res.get("ok"):
        _raise(res)
    return res


@router.get("/sessions/{session_id}")
async def conversation_get(session_id: str, user=Depends(get_current_user)):
    res = await get_conversation_engine().get(user["user_id"], session_id)
    if not res.get("ok"):
        _raise(res)
    return res


# --- Prompt 7 V2 AI-Native Cognitive Core (static paths before /{session_id}) ---

@router.post("/ai-core/files/upload")
async def ai_core_file_upload(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    user=Depends(get_current_user),
):
    """Upload user file for ORA context (Documents V2 storage + ContextFile bind)."""
    from conversation_engine.ai_core.files.service import ContextFileService

    raw = await file.read()
    svc = ContextFileService(db)
    await svc.ensure_indexes()
    res = await svc.upload_and_bind(
        user_id=user["user_id"],
        content=raw,
        filename=file.filename or "file.bin",
        mime_type=file.content_type or "application/octet-stream",
        session_id=session_id,
    )
    if not res.get("ok"):
        code = res.get("error") or "upload_failed"
        status = 400
        if code in ("file_too_large",):
            status = 413
        if code in ("mime_not_allowed",):
            status = 415
        raise HTTPException(status_code=status, detail=res)
    return res


@router.post("/ai-core/start")
async def ai_core_start(body: StartBody, user=Depends(get_current_user)):
    from conversation_engine.ai_core.orchestrator import AICoreOrchestrator

    orch = AICoreOrchestrator(db)
    res = await orch.start(
        user["user_id"],
        text=body.text or "",
        origin=body.origin or "text",
        entry_point=body.entry_point,
        plan_id=body.plan_id,
        object_id=body.object_id,
        opportunity_id=body.opportunity_id,
        attachments=list(body.attachments or []),
    )
    if not res.get("ok") and res.get("error"):
        _raise(res)
    return res


@router.post("/ai-core/{session_id}/message")
async def ai_core_message(session_id: str, body: MessageBody, user=Depends(get_current_user)):
    from conversation_engine.ai_core.orchestrator import AICoreOrchestrator

    orch = AICoreOrchestrator(db)
    res = await orch.message(
        user["user_id"],
        session_id,
        text=body.text or "",
        attachments=list(body.attachments or []),
        client_message_id=getattr(body, "client_message_id", None),
    )
    if not res.get("ok") and res.get("error"):
        _raise(res)
    return res


@router.post("/ai-core/{session_id}/client-resume")
async def ai_core_client_resume(
    session_id: str,
    body: dict | None = None,
    user=Depends(get_current_user),
):
    """Resume cognition after a client capability (foreground location)."""
    from conversation_engine.ai_core.orchestrator import AICoreOrchestrator

    orch = AICoreOrchestrator(db)
    completed = list((body or {}).get("completed") or [])
    res = await orch.client_resume(
        user["user_id"],
        session_id,
        completed=completed,
    )
    if not res.get("ok") and res.get("error"):
        _raise(res)
    return res


@router.get("/ai-core/{session_id}")
async def ai_core_get(session_id: str, user=Depends(get_current_user)):
    from conversation_engine.ai_core.orchestrator import AICoreOrchestrator

    orch = AICoreOrchestrator(db)
    res = await orch.get(user["user_id"], session_id)
    if not res.get("ok") and res.get("error"):
        _raise(res)
    return res


@router.post("/{session_id}/message")
async def conversation_message(
    session_id: str, body: MessageBody, user=Depends(get_current_user),
):
    res = await get_conversation_engine().message(
        user["user_id"],
        session_id,
        text=body.text,
        option_id=body.option_id,
        value=body.value,
        skip=body.skip,
    )
    if not res.get("ok") and res.get("error") in (
        "not_found", "conversation_engine_disabled", "session_closed", "no_action_session",
    ):
        _raise(res)
    return res


@router.post("/{session_id}/continue")
async def conversation_continue(
    session_id: str, body: ContinueBody = ContinueBody(), user=Depends(get_current_user),
):
    res = await get_conversation_engine().continue_session(
        user["user_id"], session_id, note=body.note,
    )
    if not res.get("ok"):
        _raise(res)
    return res


@router.post("/{session_id}/cancel")
async def conversation_cancel(
    session_id: str, body: CancelBody = CancelBody(), user=Depends(get_current_user),
):
    res = await get_conversation_engine().cancel(
        user["user_id"], session_id, reason=body.reason,
    )
    if not res.get("ok"):
        _raise(res)
    return res


@router.post("/{session_id}/pause")
async def conversation_pause(session_id: str, user=Depends(get_current_user)):
    res = await get_conversation_engine().pause(user["user_id"], session_id)
    if not res.get("ok"):
        _raise(res)
    return res


@router.get("/{session_id}/history")
async def conversation_history(session_id: str, user=Depends(get_current_user)):
    res = await get_conversation_engine().history(user["user_id"], session_id)
    if not res.get("ok"):
        _raise(res)
    return res


@router.get("/{session_id}/summary")
async def conversation_summary(session_id: str, user=Depends(get_current_user)):
    res = await get_conversation_engine().summary(user["user_id"], session_id)
    if not res.get("ok"):
        _raise(res)
    return res
