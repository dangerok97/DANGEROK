"""
A debug surface, and the two things a real client needs.

The evaluation endpoints exist so the judgement can be run and inspected. The
two that are not debug are `GET /delivery/ambient` — the one line Home may
show — and `POST /delivery/{id}/outcome`, which records what somebody did
with a notification that was actually sent.

There is no endpoint that sends a notification directly. Sending is something
that happens to a plan when its moment arrives and the facts still hold, and
an endpoint that skipped that would be a way to make ORA interrupt somebody
without anybody having decided to.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from deps import get_current_user

router = APIRouter(prefix="/delivery", tags=["delivery"])


class EvaluateIn(BaseModel):
    opportunity_id: str = Field(max_length=64)
    # foreground | background | unknown. A fact about the moment, not a rule:
    # the judgement is free to push to somebody who has the app open.
    app_state: str = Field(default="unknown", max_length=20)


class OutcomeIn(BaseModel):
    outcome: str = Field(max_length=20)


@router.get("/ambient")
async def ambient(user=Depends(get_current_user)):
    """
    What ORA can honestly say it has been doing. Usually nothing.

    Reads a record written by work that actually ran. If none exists this
    returns nothing at all, which is the whole point: there is no path from
    "the screen would like a line" to a line appearing.
    """
    from delivery.service import DeliveryService
    from deps import db

    return {"ambient": await DeliveryService(db).ambient_line(user["user_id"])}


@router.post("/evaluate")
async def evaluate(body: EvaluateIn, user=Depends(get_current_user)):
    """Silence, a quiet line, a card, or an interruption — and why."""
    from delivery.service import DeliveryService
    from deps import db

    result = await DeliveryService(db).evaluate(
        user["user_id"], body.opportunity_id, app_state=body.app_state
    )
    return result.public()


@router.post("/due")
async def deliver_due(user=Depends(get_current_user)):
    """
    Send what is due, having re-checked that it is still true.

    The recheck is the reason this exists as a separate step rather than a
    timer attached to each decision: between deciding and arriving, the thing
    it was about may have been dealt with.
    """
    from delivery.service import DeliveryService
    from deps import db

    return await DeliveryService(db).deliver_due(user["user_id"])


@router.get("/plans")
async def plans(user=Depends(get_current_user)):
    """Everything currently intending to arrive."""
    from delivery.service import DeliveryService
    from deps import db

    svc = DeliveryService(db)
    return {"plans": [p.public() for p in await svc.repo.open_plans(user["user_id"])]}


@router.post("/{plan_id}/outcome")
async def outcome(plan_id: str, body: OutcomeIn, user=Depends(get_current_user)):
    """Opened, ignored, gone. A fact about what happened, never a score."""
    from delivery.service import DeliveryService
    from deps import db

    result = await DeliveryService(db).record_outcome(
        user["user_id"], plan_id, body.outcome
    )
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("reason"))
    return result
