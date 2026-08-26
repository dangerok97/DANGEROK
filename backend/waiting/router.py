"""HTTP surface for open questions.

Deliberately small. A client may read what it is being asked, answer it, or say
it does not want to. It may never say where the answer should resume — that
comes from the pointer the server wrote when it asked.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from deps import get_current_user, db
from waiting.service import get_waiting_service

router = APIRouter(prefix="/questions", tags=["questions"])


class AnswerIn(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)
    # Where the person was standing when they answered. Provenance for the
    # transcript and the logs; it never decides anything.
    source: Optional[Literal["ora", "home", "activity"]] = None


class CancelIn(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=120)


@router.get("/open")
async def list_open_questions(user=Depends(get_current_user)):
    items = await get_waiting_service(db).list_open(user["user_id"])
    return {"ok": True, "items": items}


@router.post("/{question_id}/answer")
async def answer_question(question_id: str, body: AnswerIn, user=Depends(get_current_user)):
    out = await get_waiting_service(db).answer(
        user["user_id"],
        question_id[:64],
        answer=body.answer,
        source=body.source or "unknown",
    )
    if not out.get("ok") and out.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Domanda non trovata")
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail="Risposta non valida")
    return out


@router.post("/{question_id}/retry")
async def retry_question_continuation(question_id: str, user=Depends(get_current_user)):
    """The answer was accepted; the work that followed it was not finished."""
    out = await get_waiting_service(db).retry_continuation(user["user_id"], question_id[:64])
    if not out.get("ok"):
        raise HTTPException(status_code=404, detail="Nulla da riprendere")
    return out


@router.post("/{question_id}/cancel")
async def cancel_question(question_id: str, body: CancelIn, user=Depends(get_current_user)):
    ok = await get_waiting_service(db).cancel(
        user["user_id"], question_id[:64], reason=(body.reason or "user_cancelled")
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Domanda non trovata")
    return {"ok": True}
