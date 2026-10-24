"""HTTP surface for Siri: key management for the signed-in app, one door for the shortcut."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from deps import get_current_user
from siri import service

router = APIRouter(prefix="/siri", tags=["siri"])


def _db():
    from deps import db

    return db


@router.get("/key")
async def key_status(user=Depends(get_current_user)):
    return await service.status(_db(), user["user_id"])


@router.post("/key")
async def key_issue(user=Depends(get_current_user)):
    """The key is in this response and nowhere else, ever."""
    return await service.issue(_db(), user["user_id"])


@router.delete("/key")
async def key_revoke(user=Depends(get_current_user)):
    return await service.revoke(_db(), user["user_id"])


def _coord(value: Any, low: float, high: float) -> Optional[float]:
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return number if low <= number <= high else None


async def _read_body(request: Request) -> Dict[str, Any]:
    raw = (await request.body())[:20000]
    if not raw:
        return {}
    kind = (request.headers.get("content-type") or "").lower()
    text = raw.decode("utf-8", errors="replace")
    if "json" in kind or text.lstrip().startswith("{"):
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else {"text": str(data)}
        except ValueError:
            return {"text": text}
    if "form" in kind:
        return {k: v[0] for k, v in parse_qs(text).items() if v}
    return {"text": text}


def _where(body: Dict[str, Any]) -> Optional[dict]:
    lat = _coord(body.get("latitude", body.get("lat")), -90, 90)
    lon = _coord(body.get("longitude", body.get("lon")), -180, 180)
    if lat is None or lon is None:
        return None
    accuracy = _coord(body.get("accuracy"), 0, 100000)
    return {"latitude": lat, "longitude": lon, "accuracy": accuracy}


@router.post("/ask")
async def ask(
    request: Request,
    authorization: Optional[str] = Header(None),
    format: str = Query("text", pattern="^(text|json)$"),
):
    """
    What the shortcut calls. The answer is the response body, ready for
    "Mostra risultato" — so a failure is also a sentence Siri can say, with
    the status code carrying the rest for anything that is not Siri.
    """
    raw = ""
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization.split(" ", 1)[1].strip()
    record = await service.key_record(_db(), raw)
    if not record:
        out = {"ok": False, "reply": service.UNKNOWN_KEY}
        code = 401
    else:
        body = await _read_body(request)
        text = str(body.get("text") or body.get("testo") or "")
        out = await service.SiriTurns(_db()).handle(record, text, _where(body))
        code = 429 if out.get("reply") == service.TOO_MANY else 200
    if format == "json":
        return JSONResponse(out, status_code=code)
    # Shortcuts shows the body whatever the status, but a 200 keeps Siri from
    # adding its own error sentence on top of ours.
    return PlainTextResponse(out["reply"], status_code=200)
