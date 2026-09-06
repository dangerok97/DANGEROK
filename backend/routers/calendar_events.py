"""L'appuntamento visto da vicino, e il pulsante per toglierlo."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from deps import db, get_current_user
from home.calendar_event import delete_event, event_detail

router = APIRouter(prefix="/calendar/events", tags=["calendar_event"])


class DeleteBody(BaseModel):
    # Il titolo che la persona aveva davanti quando ha confermato. Serve a
    # legare il «sì» a *quell'* appuntamento: senza, una conferma varrebbe per
    # qualunque evento, che e' esattamente il modo in cui si cancella la cosa
    # sbagliata.
    confirmed_title: str = Field(default="", max_length=300)


@router.get("/{item_id}")
async def get_event(item_id: str, user=Depends(get_current_user)):
    found = await event_detail(db, user["user_id"], item_id)
    if not found:
        raise HTTPException(status_code=404, detail="event_not_found")
    return found


@router.post("/{item_id}/delete")
async def remove_event(
    item_id: str, body: DeleteBody, user=Depends(get_current_user),
):
    out = await delete_event(
        db, user["user_id"], item_id, confirmed_title=body.confirmed_title,
    )
    if not out.get("ok"):
        reason = str(out.get("reason") or "delete_failed")
        raise HTTPException(
            status_code=404 if reason == "not_found" else 409, detail=reason,
        )
    return out
