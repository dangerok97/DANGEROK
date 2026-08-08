"""Life Setup HTTP API — conversation endpoints, never a wizard form API."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from deps import get_current_user
from life_setup.models import (
    AnswerBody,
    AttachDocumentBody,
    ConfirmFieldBody,
    ConfirmLocationBody,
    CorrectFieldBody,
    ExplainBody,
    RejectFieldBody,
    ResolveConfirmationBody,
    ReverseGeocodeBody,
    SkipBody,
    StartBody,
    UploadDocBody,
)
from life_setup.profile_service import LifeProfileService
from life_setup.service import get_life_setup_service, life_setup_enabled

router = APIRouter(prefix="/life-setup", tags=["life-setup"])


class CorrectFactBody(BaseModel):
    domain: str
    key: str
    value: Any


class DeleteFactBody(BaseModel):
    domain: str
    key: str


@router.get("/status")
async def status(user=Depends(get_current_user)):
    svc = get_life_setup_service()
    return await svc.status(user["user_id"])


@router.post("/start")
async def start(body: StartBody = StartBody(), user=Depends(get_current_user)):
    if not life_setup_enabled():
        raise HTTPException(status_code=503, detail="life_setup_disabled")
    svc = get_life_setup_service()
    return await svc.start(user["user_id"], force=body.force)


@router.post("/answer")
async def answer(body: AnswerBody, user=Depends(get_current_user)):
    if not life_setup_enabled():
        raise HTTPException(status_code=503, detail="life_setup_disabled")
    svc = get_life_setup_service()
    return await svc.answer(user["user_id"], body.text, skip_domain=body.skip_domain)


@router.post("/skip")
async def skip(body: SkipBody = SkipBody(), user=Depends(get_current_user)):
    if not life_setup_enabled():
        raise HTTPException(status_code=503, detail="life_setup_disabled")
    svc = get_life_setup_service()
    return await svc.skip(user["user_id"], domain=body.domain, postpone_all=body.postpone_all)


@router.post("/upload-doc")
async def upload_doc(body: UploadDocBody, user=Depends(get_current_user)):
    if not life_setup_enabled():
        raise HTTPException(status_code=503, detail="life_setup_disabled")
    svc = get_life_setup_service()
    return await svc.upload_doc(user["user_id"], body.model_dump())


@router.post("/explain")
async def explain(body: ExplainBody = ExplainBody(), user=Depends(get_current_user)):
    svc = get_life_setup_service()
    return await svc.explain(user["user_id"], plan=body.plan)


@router.post("/complete")
async def complete(user=Depends(get_current_user)):
    if not life_setup_enabled():
        raise HTTPException(status_code=503, detail="life_setup_disabled")
    svc = get_life_setup_service()
    return await svc.complete(user["user_id"])


@router.post("/cancel")
async def cancel(user=Depends(get_current_user)):
    if not life_setup_enabled():
        raise HTTPException(status_code=503, detail="life_setup_disabled")
    svc = get_life_setup_service()
    return await svc.cancel(user["user_id"])


@router.post("/reverse-geocode")
async def reverse_geocode(body: ReverseGeocodeBody, user=Depends(get_current_user)):
    """Coarse city from lat/lon via Nominatim — auth required; coords not persisted."""
    if not life_setup_enabled():
        raise HTTPException(status_code=503, detail="life_setup_disabled")
    svc = get_life_setup_service()
    return await svc.reverse_geocode(user["user_id"], body.lat, body.lon)


@router.post("/confirm-location")
async def confirm_location(body: ConfirmLocationBody, user=Depends(get_current_user)):
    """Confirm/reject suggested city for mlc.life_places — no coordinate storage."""
    if not life_setup_enabled():
        raise HTTPException(status_code=503, detail="life_setup_disabled")
    svc = get_life_setup_service()
    return await svc.confirm_location(
        user["user_id"], body.city, confirmed=body.confirmed
    )


@router.get("/profile")
async def get_profile(user=Depends(get_current_user)):
    """User may view Life Profile — not a Life Setup settings form."""
    from deps import db
    ps = LifeProfileService(db)
    p = await ps.get_or_create(user["user_id"])
    return {"ok": True, "profile": p.public()}


@router.post("/profile/correct")
async def correct_fact(body: CorrectFactBody, user=Depends(get_current_user)):
    from deps import db
    ps = LifeProfileService(db)
    p = await ps.correct_fact(user["user_id"], body.domain, body.key, body.value)
    return {"ok": True, "profile": p.public()}


@router.post("/profile/delete-fact")
async def delete_fact(body: DeleteFactBody, user=Depends(get_current_user)):
    """User delete only — AI cannot call this path meaningfully."""
    from deps import db
    ps = LifeProfileService(db)
    p = await ps.delete_fact(user["user_id"], body.domain, body.key)
    return {"ok": True, "profile": p.public()}


@router.get("/stubs/{name}")
async def stub_adapter(name: str, user=Depends(get_current_user)):
    svc = get_life_setup_service()
    return await svc.stub_adapter(name)


# --- Real Documents V2 attach / poll / consume ----------------------------
# Life Experience never re-implements upload, validation, storage, OCR or
# base classification: files always go through `POST /api/documents/upload`
# first. These endpoints only link, poll and consume the SAME document.

@router.post("/documents/attach")
async def attach_document(body: AttachDocumentBody, user=Depends(get_current_user)):
    if not life_setup_enabled():
        raise HTTPException(status_code=503, detail="life_setup_disabled")
    svc = get_life_setup_service()
    res = await svc.attach_document(user["user_id"], body.document_id, body.doc_type)
    if not res.get("ok") and res.get("error") == "document_not_found":
        raise HTTPException(status_code=404, detail="Documento non trovato")
    return res


@router.get("/documents/{document_id}/status")
async def document_status(document_id: str, user=Depends(get_current_user)):
    svc = get_life_setup_service()
    res = await svc.document_status(user["user_id"], document_id)
    if not res.get("ok") and res.get("error") == "document_not_found":
        raise HTTPException(status_code=404, detail="Documento non trovato")
    return res


class ConsumeDocumentBody(BaseModel):
    force: bool = False


@router.post("/documents/{document_id}/consume")
async def consume_document(
    document_id: str, body: ConsumeDocumentBody = ConsumeDocumentBody(), user=Depends(get_current_user),
):
    if not life_setup_enabled():
        raise HTTPException(status_code=503, detail="life_setup_disabled")
    svc = get_life_setup_service()
    res = await svc.consume_document(user["user_id"], document_id, force=body.force)
    if not res.get("ok") and res.get("error") == "document_not_found":
        raise HTTPException(status_code=404, detail="Documento non trovato")
    return res


@router.post("/documents/{document_id}/retry")
async def retry_document(document_id: str, user=Depends(get_current_user)):
    if not life_setup_enabled():
        raise HTTPException(status_code=503, detail="life_setup_disabled")
    svc = get_life_setup_service()
    res = await svc.retry_document(user["user_id"], document_id)
    if not res.get("ok") and res.get("error") == "document_not_found":
        raise HTTPException(status_code=404, detail="Documento non trovato")
    return res


@router.post("/documents/{document_id}/detach")
async def detach_document(document_id: str, user=Depends(get_current_user)):
    svc = get_life_setup_service()
    return await svc.detach_document(user["user_id"], document_id)


@router.post("/documents/confirm-field")
async def confirm_document_field(body: ConfirmFieldBody, user=Depends(get_current_user)):
    svc = get_life_setup_service()
    return await svc.confirm_field(user["user_id"], body.domain, body.key)


@router.post("/documents/correct-field")
async def correct_document_field(body: CorrectFieldBody, user=Depends(get_current_user)):
    svc = get_life_setup_service()
    return await svc.correct_field(user["user_id"], body.domain, body.key, body.value)


@router.post("/documents/reject-field")
async def reject_document_field(body: RejectFieldBody, user=Depends(get_current_user)):
    svc = get_life_setup_service()
    return await svc.reject_field(user["user_id"], body.domain, body.key)


@router.post("/documents/resolve-confirmation")
async def resolve_document_confirmation(body: ResolveConfirmationBody, user=Depends(get_current_user)):
    svc = get_life_setup_service()
    return await svc.resolve_confirmation(user["user_id"], body.domain, body.key, body.resolution)
