"""Simple, owner-scoped feedback about a temporary Situation.

These actions are explicit user statements. Reporting a changed physical
state never claims the expected result was achieved; confirming completion
closes the Situation; stopping a watch archives it without asserting success.
The same autonomous change queue handles later checks where meaningful.
"""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from deps import db, get_current_user
from situations.models import SituationUpdate
from situations.repository import SituationRepository
from situations.service import SituationMutationError, SituationService

router = APIRouter(prefix="/situations", tags=["situations"])


class SituationFeedback(BaseModel):
    action: Literal["changed", "resolved", "stop_monitoring"]
    expected_revision: int = Field(ge=1)
    description: str = Field(default="", max_length=400)


@router.post("/{situation_id}/feedback")
async def update_situation_feedback(
    situation_id: str,
    body: SituationFeedback,
    user=Depends(get_current_user),
):
    owner = str(user["user_id"])
    situation = await SituationRepository(db).get(owner, situation_id)
    if situation is None:
        raise HTTPException(status_code=404, detail="situation_not_found")
    if situation.revision != body.expected_revision:
        raise HTTPException(status_code=409, detail="situation_changed_please_reload")
    if situation.status not in ("active", "changed"):
        raise HTTPException(status_code=409, detail="situation_already_closed")

    if body.action == "changed":
        description = " ".join(body.description.split())
        if len(description) < 5:
            raise HTTPException(status_code=422, detail="describe_what_changed")
        update = SituationUpdate(
            operation="update",
            situation_id=situation_id,
            expected_revision=body.expected_revision,
            current_state_summary=description,
            facts=[description],
            # The latest user's description is authoritative about the
            # CURRENT physical state. History retains every previous fact,
            # but conflicting old facts must not appear as current context.
            supersedes=list(situation.facts),
            source="user_conversation",
        )
    else:
        update = SituationUpdate(
            operation="resolve" if body.action == "resolved" else "cancel",
            situation_id=situation_id,
            expected_revision=body.expected_revision,
            source="user_conversation",
        )

    try:
        result = await SituationService(db).apply(
            user_id=owner,
            session_id=f"feedback:{situation_id}",
            update=update,
            reasoning_epoch=f"feedback:{uuid.uuid4().hex}",
        )
    except SituationMutationError as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc
    return {
        "ok": result.get("status") == "success",
        "action": body.action,
        "situation": result.get("situation"),
        "message": {
            "changed": "Ho aggiornato la situazione. Ricontrollerò sulla base delle nuove informazioni.",
            "resolved": "Situazione conclusa. Non ti invierò altri avvisi per questa attività.",
            "stop_monitoring": "Ho interrotto il monitoraggio di questa attività.",
        }[body.action],
    }
