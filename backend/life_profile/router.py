"""
Life Profile HTTP surface — read-mostly, and never a way to set a number.

There is deliberately no endpoint that accepts a completeness value. A client
can say what a person did — this does not apply to me, I would rather not say —
and the server works out what that means. A percentage a client could set is a
percentage that means nothing.
"""

from __future__ import annotations

from typing import Any, List, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from deps import db, get_current_user
from life_profile.service import get_life_profile_service
from life_profile.setup import get_guided_setup_service

router = APIRouter(prefix="/life-profile", tags=["life-profile"])


class NotApplicableBody(BaseModel):
    """What does not apply to this life. References, never values."""

    refs: List[str] = Field(default_factory=list, max_length=32)


@router.get("")
async def profile(user=Depends(get_current_user)):
    """Overall completeness, every area, and where it would help to continue."""
    return await get_life_profile_service(db).public(user["user_id"])


@router.get("/areas/{area_id}")
async def area_detail(area_id: str, user=Depends(get_current_user)):
    return await get_life_profile_service(db).area_detail(user["user_id"], area_id)


# ---------------------------------------------------------------------------
# The guided first setup
#
# One question at a time. The client sends what the person chose — an option, a
# value, a refusal, a skip — and receives the next question. It never decides
# which one that is.
# ---------------------------------------------------------------------------


class AnswerBody(BaseModel):
    objective_id: str = Field(max_length=120)
    option_ids: List[str] = Field(default_factory=list, max_length=12)
    value: Optional[Any] = None
    other_text: Optional[str] = Field(default=None, max_length=500)
    action: Literal["answer", "skip", "decline"] = "answer"


class AreaBody(BaseModel):
    area_id: str = Field(max_length=60)


@router.get("/setup")
async def setup_state(user=Depends(get_current_user)):
    """The current area, the current question, and every area's state."""
    return await get_guided_setup_service(db).state(user["user_id"])


@router.post("/setup/answer")
async def setup_answer(body: AnswerBody, user=Depends(get_current_user)):
    return await get_guided_setup_service(db).answer(
        user["user_id"],
        objective_id=body.objective_id,
        option_ids=body.option_ids,
        value=body.value,
        other_text=body.other_text,
        action=body.action,
    )


@router.post("/setup/skip-area")
async def setup_skip_area(body: AreaBody, user=Depends(get_current_user)):
    return await get_guided_setup_service(db).skip_area(user["user_id"], body.area_id)


@router.post("/setup/go-to-area")
async def setup_go_to_area(body: AreaBody, user=Depends(get_current_user)):
    """An explicit move to the next part of a life — never automatic."""
    return await get_guided_setup_service(db).go_to_area(user["user_id"], body.area_id)


@router.post("/setup/finish")
async def setup_finish(user=Depends(get_current_user)):
    """The first run is over because the person said so, not because of a number."""
    return await get_guided_setup_service(db).finish(user["user_id"])


@router.post("/not-applicable")
async def not_applicable(body: NotApplicableBody, user=Depends(get_current_user)):
    """
    Record that something does not apply — no car, no mortgage.

    This is the one write here, and it still does not set a figure: it records
    a fact about a life, and the figure follows from it.
    """
    return await get_life_profile_service(db).mark_not_applicable(
        user["user_id"], body.refs
    )
