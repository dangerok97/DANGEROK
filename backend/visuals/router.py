"""Serving generated card visuals."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from deps import db, get_current_user
from visuals.service import VisualService

router = APIRouter(prefix="/visuals", tags=["visuals"])


@router.get("/{visual_key}")
async def get_visual(visual_key: str, user=Depends(get_current_user)):
    """Serve one generated visual belonging to the caller.

    User-scoped twice: the record must be this user's, and the blob is read
    from their own storage directory. Someone else's key is a 404 here.
    """
    try:
        content, mime = await VisualService(db).read_bytes(
            user_id=user["user_id"], key=visual_key,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="not_found")
    return Response(
        content=content,
        media_type=mime,
        # Immutable by construction: the key changes when the meaning does.
        headers={"Cache-Control": "private, max-age=86400, immutable"},
    )
