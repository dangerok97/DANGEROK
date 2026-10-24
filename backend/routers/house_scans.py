"""Authenticated room-scan storage; no media URLs, raw images or remote fetches."""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError

from deps import db, get_current_user
from house_scans.models import (
    AddManualRoom, CreateHouseScan, MAX_CAPTURE_BYTES, MAX_PATCH_BYTES, UpdateHouseScan,
)
from house_scans.service import HouseScanError, HouseScanService


async def _private(response: Response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"


router = APIRouter(prefix="/house-scans", tags=["house_scans"], dependencies=[Depends(_private)])


def _service() -> HouseScanService:
    return HouseScanService(db)


def _error(status: int, message: str) -> HTTPException:
    return HTTPException(status, message, headers={"Cache-Control": "private, no-store"})


async def _call(task):
    try:
        return await task
    except HouseScanError as exc:
        raise _error(exc.status, str(exc)) from None


def _check_id(scan_id: str):
    if not re.fullmatch(r"[0-9a-f]{32}", scan_id):
        raise _error(422, "Identificativo della planimetria non valido.")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Chiave JSON duplicata.")
        result[key] = value
    return result


def _no_constant(_):
    raise ValueError("Sono ammessi soltanto numeri finiti.")


async def _read_body(request: Request, model, *, max_bytes: int):
    """Apply the byte limit while streaming, before a JSON/Pydantic allocation."""
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise _error(415, "Invia i dati della scansione in formato JSON.")
    if request.headers.get("content-encoding", "identity").lower() not in ("", "identity"):
        raise _error(415, "Il corpo della richiesta non deve essere compresso.")
    length = request.headers.get("content-length")
    if length is not None:
        try:
            size = int(length)
        except ValueError:
            raise _error(400, "Lunghezza della richiesta non valida.") from None
        if size < 0:
            raise _error(400, "Lunghezza della richiesta non valida.")
        if size > max_bytes:
            raise _error(413, "I dati superano il limite consentito per questa richiesta.")
    raw = bytearray()
    try:
        async for chunk in request.stream():
            if len(raw) + len(chunk) > max_bytes:
                raise _error(413, "I dati superano il limite consentito per questa richiesta.")
            raw.extend(chunk)
        try:
            decoded = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                                 parse_constant=_no_constant)
        except (ValueError, UnicodeError, RecursionError):
            raise _error(422, "JSON non valido: controlla struttura, chiavi e numeri della scansione.") from None
        try:
            return model.model_validate(decoded)
        except ValidationError as exc:
            errors = exc.errors(include_input=False, include_context=False, include_url=False)
            first = errors[0]
            field = ".".join(str(part) for part in first["loc"])[:120]
            raise _error(422, f"Dati non validi ({field or 'richiesta'}): {first['msg']}") from None
    finally:
        raw.clear()


@router.get("")
async def list_scans(limit: int = Query(50, ge=1, le=100),
                     offset: int = Query(0, ge=0, le=10000),
                     user=Depends(get_current_user)):
    return await _call(_service().list_scans(user["user_id"], limit=limit, offset=offset))


@router.post("")
async def create_scan(request: Request, response: Response, user=Depends(get_current_user)):
    body = await _read_body(request, CreateHouseScan, max_bytes=MAX_CAPTURE_BYTES)
    scan, created = await _call(_service().create(user["user_id"], body))
    response.status_code = 201 if created else 200
    return {"scan": scan, "created": created}


@router.post("/manual-rooms")
async def add_manual_room(request: Request, response: Response, user=Depends(get_current_user)):
    """A room measured by hand: starts a plan, or joins one made the same way."""
    body = await _read_body(request, AddManualRoom, max_bytes=MAX_PATCH_BYTES)
    scan, created = await _call(_service().add_manual_room(user["user_id"], body))
    response.status_code = 201 if created else 200
    return {"scan": scan, "created": created}


@router.delete("/{scan_id}/rooms/{room_id}")
async def remove_manual_room(scan_id: str, room_id: str,
                             revision: int = Query(..., ge=1, le=2_147_483_647),
                             user=Depends(get_current_user)):
    _check_id(scan_id)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", room_id):
        raise _error(422, "Identificativo della stanza non valido.")
    return {"scan": await _call(_service().remove_manual_room(
        user["user_id"], scan_id, room_id, revision))}


@router.get("/{scan_id}")
async def get_scan(scan_id: str, user=Depends(get_current_user)):
    _check_id(scan_id)
    return {"scan": await _call(_service().get(user["user_id"], scan_id))}


@router.patch("/{scan_id}")
async def update_scan(scan_id: str, request: Request, user=Depends(get_current_user)):
    _check_id(scan_id)
    body = await _read_body(request, UpdateHouseScan, max_bytes=MAX_PATCH_BYTES)
    return {"scan": await _call(_service().update(user["user_id"], scan_id, body))}


@router.delete("/{scan_id}")
async def delete_scan(scan_id: str, revision: int = Query(..., ge=1, le=2_147_483_647),
                      user=Depends(get_current_user)):
    _check_id(scan_id)
    await _call(_service().delete(user["user_id"], scan_id, revision))
    return {"deleted": True}
