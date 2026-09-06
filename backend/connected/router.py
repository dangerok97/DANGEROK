"""
What a person may ask about the things ORA is connected to.

Three endpoints, and the restraint is the design. There is no connector
marketplace here, no global sync switch and no dashboard: a connection is
either working or it is not, and everything else — cursors, tokens, sync
states, error codes — is our plumbing and stays ours.

`for_human()` is what leaves the building. It carries three things: what the
connection is, whether it is working, and when it was last read. A person
looking at this screen is asking "does ORA know what's in my calendar?", and
those three answer it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from deps import get_current_user

router = APIRouter(prefix="/connected-sources", tags=["connected"])


@router.get("")
async def sources(user=Depends(get_current_user)):
    """The things ORA can see this life through, in human terms."""
    from connected.service import ConnectedLifeService
    from deps import db

    found = await ConnectedLifeService(db).sources.list(user["user_id"])
    return {"sources": [s.for_human() | {"id": s.id} for s in found]}


@router.get("/{source_id}/health")
async def health(source_id: str, user=Depends(get_current_user)):
    """
    Whether what ORA knows through this source is still worth leaning on.

    Two facts and no codes. `can_be_leaned_on` is the one that matters and
    the one nothing else could answer: a connection can be perfectly healthy
    and still hold a picture two days old, and a system that reported only
    "connected" would let a reasoning step state a stale day as the current
    one.
    """
    from connected.service import ConnectedLifeService
    from deps import db

    source = await ConnectedLifeService(db).sources.get(user["user_id"], source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="unknown_source")
    return {
        **source.for_human(),
        "can_be_leaned_on": source.can_be_leaned_on,
    }


@router.post("/{source_id}/sync")
async def sync(source_id: str, user=Depends(get_current_user)):
    """
    Look again, now.

    Returns what happened to the reading, never what it means. Meaning is a
    judgement made elsewhere, on its own schedule, and an endpoint that
    returned it would be an endpoint that could be polled into making them.
    """
    from connected.service import ConnectedLifeService
    from deps import db

    result = await ConnectedLifeService(db).sync(user["user_id"], source_id)
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("reason"))
    return result
