"""Documents REST router."""
from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from deps import get_current_user

from .service import DocumentNotFound, DocumentValidationError

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentPatchIn(BaseModel):
    filename: Optional[str] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None


def _svc():
    from deps import get_document_service
    return get_document_service()


def _parse_tags(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    # Accept comma-separated string OR JSON list style
    txt = raw.strip()
    if txt.startswith("["):
        import json
        try:
            v = json.loads(txt)
            return [str(t).strip() for t in v if str(t).strip()]
        except Exception:
            pass
    return [t.strip() for t in txt.split(",") if t.strip()]


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    tags: Optional[str] = Form(default=None),
    notes: Optional[str] = Form(default=None),
    upload_source: Optional[str] = Form(default="web"),
    user=Depends(get_current_user),
):
    try:
        content = await file.read()
    except Exception:
        raise HTTPException(status_code=400, detail="Impossibile leggere il file caricato")
    try:
        result = await _svc().upload(
            user_id=user["user_id"],
            content=content,
            original_filename=file.filename or "documento",
            mime_type=file.content_type or "application/octet-stream",
            tags=_parse_tags(tags),
            notes=notes,
            upload_source=upload_source or "web",
        )
    except DocumentValidationError as e:
        raise HTTPException(status_code=400, detail={"error": e.code, "message": str(e)})
    return result


@router.get("")
async def list_documents(
    q: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
    mime: Optional[str] = Query(default=None),
    archived: Optional[bool] = Query(default=None),
    sort: str = Query(default="created_desc"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user=Depends(get_current_user),
):
    return await _svc().list(
        user_id=user["user_id"],
        q=q, tag=tag, mime=mime, archived=archived,
        sort=sort, limit=limit, offset=offset,
    )


@router.get("/{doc_id}")
async def get_document(doc_id: str, user=Depends(get_current_user)):
    try:
        return await _svc().get(user_id=user["user_id"], doc_id=doc_id)
    except DocumentNotFound:
        raise HTTPException(status_code=404, detail="Documento non trovato")


@router.get("/{doc_id}/download")
async def download_document(doc_id: str, user=Depends(get_current_user)):
    try:
        doc, blob = await _svc().read_bytes(user_id=user["user_id"], doc_id=doc_id)
    except DocumentNotFound:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    except FileNotFoundError:
        raise HTTPException(status_code=410, detail="Contenuto del documento non più disponibile")
    from urllib.parse import quote
    fname = quote(doc.get("filename") or "documento.bin")
    return Response(
        content=blob,
        media_type=doc.get("mime_type") or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.patch("/{doc_id}")
async def patch_document(doc_id: str, body: DocumentPatchIn, user=Depends(get_current_user)):
    try:
        return await _svc().patch(
            user_id=user["user_id"], doc_id=doc_id,
            filename=body.filename, tags=body.tags, notes=body.notes,
        )
    except DocumentNotFound:
        raise HTTPException(status_code=404, detail="Documento non trovato")


@router.post("/{doc_id}/archive")
async def archive_document(doc_id: str, user=Depends(get_current_user)):
    try:
        return await _svc().archive(user_id=user["user_id"], doc_id=doc_id)
    except DocumentNotFound:
        raise HTTPException(status_code=404, detail="Documento non trovato")


@router.post("/{doc_id}/restore")
async def restore_document(doc_id: str, user=Depends(get_current_user)):
    try:
        return await _svc().restore(user_id=user["user_id"], doc_id=doc_id)
    except DocumentNotFound:
        raise HTTPException(status_code=404, detail="Documento non trovato")


@router.delete("/{doc_id}")
async def delete_document(doc_id: str, hard: bool = Query(default=False), user=Depends(get_current_user)):
    try:
        return await _svc().delete(user_id=user["user_id"], doc_id=doc_id, hard=hard)
    except DocumentNotFound:
        raise HTTPException(status_code=404, detail="Documento non trovato")
