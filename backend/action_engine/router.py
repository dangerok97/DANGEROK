"""Action Engine HTTP API under /api/action-engine."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from action_engine.models import AnswerBody, MergeProjectBody, OpenBody
from action_engine.service import ActionEngineService
from deps import db, decisions, get_current_user, knowledge, life_graph

router = APIRouter(prefix="/action-engine", tags=["action_engine"])

_svc: ActionEngineService | None = None


def get_action_engine() -> ActionEngineService:
    global _svc
    if _svc is None:
        _svc = ActionEngineService(
            db, life_graph=life_graph, knowledge=knowledge, decisions=decisions,
        )
    return _svc


@router.post("/open")
async def open_flow(body: OpenBody, user=Depends(get_current_user)):
    svc = get_action_engine()
    # Guard: never open without a resolvable title/context
    item = body.home_item or {}
    if not (body.title or item.get("title") or body.source_id or item.get("source_id") or body.home_item_id or item.get("id")):
        raise HTTPException(status_code=400, detail="Provide home_item or title/source refs")
    result = await svc.open(user["user_id"], body)
    session = result.get("session") or {}
    if session.get("status") == "active" and not session.get("current_turn"):
        # Hard fail-safe: never return empty guided UI
        raise HTTPException(status_code=500, detail="Flow produced no question")
    return result


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, user=Depends(get_current_user)):
    svc = get_action_engine()
    session = await svc.get_session(user["user_id"], session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": session}


@router.post("/sessions/{session_id}/answer")
async def answer_turn(session_id: str, body: AnswerBody, user=Depends(get_current_user)):
    svc = get_action_engine()
    result = await svc.answer(user["user_id"], session_id, body)
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Session not found")
    if result.get("error") == "answer_required":
        raise HTTPException(status_code=400, detail="Answer required")
    return result


@router.post("/sessions/{session_id}/complete")
async def complete_session(session_id: str, user=Depends(get_current_user)):
    svc = get_action_engine()
    result = await svc.complete(user["user_id"], session_id)
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Session not found")
    return result


@router.post("/sessions/{session_id}/cancel")
async def cancel_session(session_id: str, user=Depends(get_current_user)):
    svc = get_action_engine()
    result = await svc.cancel(user["user_id"], session_id)
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Session not found")
    return result


@router.post("/sessions/{session_id}/merge-project")
async def merge_project(session_id: str, body: MergeProjectBody, user=Depends(get_current_user)):
    svc = get_action_engine()
    result = await svc.merge_project(user["user_id"], session_id, body.target_project_id)
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Session not found")
    if result.get("error") == "project_not_found":
        raise HTTPException(status_code=404, detail="Project not found")
    if result.get("error") == "no_project":
        raise HTTPException(status_code=400, detail="Session has no project")
    return result
