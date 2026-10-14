"""Authenticated wallet endpoints; no card data in URLs, logs or public media."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from starlette.concurrency import run_in_threadpool

from deps import db, get_current_user
from loyalty_wallet import CardInput, FORMATS, MAX_UPLOAD, WalletCipher, WalletError, WalletService, decode_image, render_code


def _private(response: Response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"


router = APIRouter(prefix="/wallet", tags=["loyalty-wallet"], dependencies=[Depends(_private)])


def _service():
    try:
        return WalletService(db, WalletCipher.configured())
    except WalletError as exc:
        raise HTTPException(exc.status, str(exc)) from None


async def _call(operation):
    try:
        return await operation
    except WalletError as exc:
        raise HTTPException(exc.status, str(exc)) from None


def _decode_preview(raw: bytes) -> list[dict]:
    """Add deterministic, exact-read-back PNG previews; never retain input photo.

    `image` is additive to the existing candidates contract. Older clients
    still work; newer ones collapse physically equivalent EAN/UPC readings.
    Both decoding and preview rendering run off the async event loop.
    """
    return [{**candidate, "image": render_code(candidate["format"], candidate["code"])}
            for candidate in decode_image(raw)]


@router.get("/cards")
async def list_cards(user=Depends(get_current_user)):
    return {"cards": await _call(_service().list_cards(user["user_id"])), "formats": list(FORMATS)}


@router.put("/cards")
async def save_card(body: CardInput, user=Depends(get_current_user)):
    return {"card": await _call(_service().save(user["user_id"], body))}


@router.delete("/cards/{card_id}")
async def delete_card(card_id: str, revision: int = Query(..., ge=1), user=Depends(get_current_user)):
    import re
    if not re.fullmatch(r"[0-9a-f]{32}", card_id):
        raise HTTPException(422, "Identificativo tessera non valido.")
    await _call(_service().delete(user["user_id"], card_id, revision))
    return {"deleted": True}


@router.post("/decode")
async def scan_card(request: Request, user=Depends(get_current_user)):
    # Explicit foreground upload only. No URL fetching, no image persistence.
    if request.headers.get("content-type", "").split(";")[0].lower() not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(415, "Usa una foto JPEG, PNG o WebP.")
    raw = bytearray()
    try:
        async for chunk in request.stream():
            if len(raw) + len(chunk) > MAX_UPLOAD:
                raise HTTPException(413, "La foto supera 8 MB: ritaglia il codice.")
            raw.extend(chunk)
        candidates = await run_in_threadpool(_decode_preview, bytes(raw))
        return {"candidates": candidates, "saved": False}
    except WalletError as exc:
        raise HTTPException(exc.status, str(exc)) from None
    finally:
        raw.clear()
