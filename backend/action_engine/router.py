"""Action Engine HTTP API under /api/action-engine."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from action_engine.models import (
    AnswerBody,
    BackBody,
    ConfirmStudyBody,
    DraftBody,
    MergeProjectBody,
    OpenBody,
)
from action_engine.service import ActionEngineService
from action_engine.study.models import PlanModifyBody, SessionActionBody
from action_engine.study.google_sync import retry_sync
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


def _http_err(result: dict, *, default_status: int = 400):
    err = result.get("error")
    if err == "not_found":
        raise HTTPException(status_code=404, detail=result.get("message") or "Not found")
    if err == "answer_required":
        raise HTTPException(status_code=400, detail="Answer required")
    if err in ("ambiguous_date", "validation", "impossible_plan", "confirm_required", "duplicate"):
        raise HTTPException(
            status_code=400,
            detail={
                "error": err,
                "message": result.get("message"),
                "candidates": result.get("candidates"),
                "duplicate": result.get("duplicate"),
            },
        )
    if err:
        raise HTTPException(status_code=default_status, detail=result.get("message") or err)


@router.post("/open")
async def open_flow(body: OpenBody, user=Depends(get_current_user)):
    svc = get_action_engine()
    item = body.home_item or {}
    if not (body.title or item.get("title") or body.source_id or item.get("source_id") or body.home_item_id or item.get("id")):
        raise HTTPException(status_code=400, detail="Provide home_item or title/source refs")
    result = await svc.open(user["user_id"], body)
    session = result.get("session") or {}
    if session.get("status") == "active" and not session.get("current_turn"):
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
    # Soft validation errors still return session for UI recovery
    if result.get("ok") is False and result.get("error") in (
        "ambiguous_date", "validation", "impossible_plan", "duplicate",
        "past_date", "invalid_date", "unparsed", "no_days", "too_short",
        "subject_required",
    ):
        return result
    return result


@router.post("/sessions/{session_id}/back")
async def back_turn(session_id: str, body: BackBody = BackBody(), user=Depends(get_current_user)):
    svc = get_action_engine()
    result = await svc.back(user["user_id"], session_id, body.to_turn_id)
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Session not found")
    return result


@router.post("/sessions/{session_id}/draft")
async def save_draft(session_id: str, body: DraftBody = DraftBody(), user=Depends(get_current_user)):
    svc = get_action_engine()
    if body.answers:
        # merge answers then save
        session = await svc.get_session(user["user_id"], session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        doc = await svc.col.find_one({"id": session_id, "user_id": user["user_id"]}, {"_id": 0})
        from action_engine.models import ActionSession
        sess = ActionSession(**doc)
        sess.answers.update(body.answers)
        await svc.col.replace_one({"id": session_id}, sess.model_dump())
    result = await svc.save_draft(user["user_id"], session_id)
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


@router.post("/sessions/{session_id}/complete")
async def complete_session(session_id: str, user=Depends(get_current_user)):
    svc = get_action_engine()
    result = await svc.complete(user["user_id"], session_id)
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Session not found")
    if result.get("error") == "confirm_required":
        raise HTTPException(status_code=400, detail=result.get("message") or "Confirm required")
    return result


@router.post("/sessions/{session_id}/search-docs")
async def search_docs(session_id: str, user=Depends(get_current_user)):
    svc = get_action_engine()
    result = await svc.search_docs(user["user_id"], session_id)
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Session not found")
    return result


@router.get("/sessions/{session_id}/preview")
@router.post("/sessions/{session_id}/preview")
async def preview_plan(session_id: str, user=Depends(get_current_user)):
    svc = get_action_engine()
    result = await svc.preview_study(user["user_id"], session_id)
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Session not found")
    return result


@router.post("/sessions/{session_id}/modify")
async def modify_preview(session_id: str, body: PlanModifyBody, user=Depends(get_current_user)):
    svc = get_action_engine()
    result = await svc.modify_preview(user["user_id"], session_id, body)
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Session not found")
    return result


@router.post("/sessions/{session_id}/confirm")
async def confirm_study(session_id: str, body: ConfirmStudyBody = ConfirmStudyBody(), user=Depends(get_current_user)):
    """Confirm study plan — same as answering confirm chip (UI-primary)."""
    svc = get_action_engine()
    from action_engine.models import AnswerBody as AB
    # Set duplicate action on session meta via draft path if provided
    if body.duplicate_action:
        doc = await svc.col.find_one({"id": session_id, "user_id": user["user_id"]}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Session not found")
        from action_engine.models import ActionSession
        sess = ActionSession(**doc)
        sess.meta["duplicate_action"] = body.duplicate_action
        sess.answers["duplicate_resolution"] = body.duplicate_action
        sess.answers["confirm"] = "confirm"
        await svc.col.replace_one({"id": session_id}, sess.model_dump())
        result = await svc._confirm_study_session(user["user_id"], sess)
    else:
        result = await svc.answer(
            user["user_id"], session_id,
            AB(option_id="confirm", value="confirm"),
        )
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


# --- Study plans (read/manage after confirm) ---

study_router = APIRouter(prefix="/study-plans", tags=["study_plans"])


@study_router.get("")
async def list_plans(status: Optional[str] = None, user=Depends(get_current_user)):
    svc = get_action_engine()
    items = await svc.study_plans.list_plans(user["user_id"], status=status)
    return {"items": items}


@study_router.get("/{plan_id}")
async def get_plan(plan_id: str, user=Depends(get_current_user)):
    svc = get_action_engine()
    plan = await svc.study_plans.get_plan(user["user_id"], plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"plan": plan}


@study_router.get("/{plan_id}/sessions")
async def list_sessions(plan_id: str, user=Depends(get_current_user)):
    svc = get_action_engine()
    plan = await svc.study_plans.get_plan(user["user_id"], plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"sessions": plan.get("sessions") or []}


@study_router.post("/{plan_id}/sessions/{session_id}/action")
async def session_action(
    plan_id: str, session_id: str, body: SessionActionBody, user=Depends(get_current_user),
):
    svc = get_action_engine()
    result = await svc.study_plans.session_action(
        user["user_id"], session_id, body.action,
        snooze_minutes=body.snooze_minutes or 60,
    )
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Session not found")
    return result


@study_router.post("/sessions/{session_id}/complete")
async def complete_session_shortcut(session_id: str, user=Depends(get_current_user)):
    svc = get_action_engine()
    return await svc.study_plans.session_action(user["user_id"], session_id, "complete")


@study_router.post("/sessions/{session_id}/postpone")
async def postpone_session(session_id: str, body: SessionActionBody = SessionActionBody(action="snooze"), user=Depends(get_current_user)):
    svc = get_action_engine()
    return await svc.study_plans.session_action(
        user["user_id"], session_id, "snooze", snooze_minutes=body.snooze_minutes or 60,
    )


@study_router.post("/{plan_id}/sync")
async def sync_plan(plan_id: str, user=Depends(get_current_user)):
    return await retry_sync(db, user["user_id"], plan_id)


@study_router.post("/{plan_id}/retry-sync")
async def retry_plan_sync(plan_id: str, user=Depends(get_current_user)):
    return await retry_sync(db, user["user_id"], plan_id)


class PlanUpdateBody(BaseModel):
    daily_minutes: Optional[int] = None
    available_days: Optional[list] = None
    intensity: Optional[str] = None
    document_ids: Optional[list] = None
    calendar_sync: Optional[bool] = None
    tools: Optional[list] = None
    status: Optional[str] = None
    exam_date: Optional[str] = None
    regenerate_future: bool = False


@study_router.patch("/{plan_id}")
@study_router.post("/{plan_id}/update")
async def update_plan(plan_id: str, body: PlanUpdateBody, user=Depends(get_current_user)):
    svc = get_action_engine()
    result = await svc.study_plans.update_plan(
        user["user_id"], plan_id, body.model_dump(exclude_none=True),
    )
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Plan not found")
    return result


@study_router.delete("/{plan_id}")
async def delete_plan(plan_id: str, user=Depends(get_current_user)):
    svc = get_action_engine()
    result = await svc.study_plans.delete_plan(user["user_id"], plan_id, soft=True)
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Plan not found")
    return result
