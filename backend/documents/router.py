"""Documents REST router."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from deps import get_current_user

from .service import DocumentNotFound, DocumentValidationError

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentPatchIn(BaseModel):
    filename: Optional[str] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None


class AnalysisPatchIn(BaseModel):
    user_title: Optional[str] = None
    analysis: Optional[Dict[str, Any]] = None


class EventPatchIn(BaseModel):
    title: Optional[str] = None
    start_datetime: Optional[str] = None
    end_datetime: Optional[str] = None
    venue_name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    priority: Optional[str] = None
    urgency: Optional[str] = None
    description: Optional[str] = None
    timezone: Optional[str] = None
    all_day: Optional[bool] = None


class EventConfirmIn(BaseModel):
    overrides: Optional[Dict[str, Any]] = None
    sync_to_google: bool = False


class CalendarDefaultIn(BaseModel):
    calendar_id: str = Field(..., min_length=1, max_length=512)


class ConflictResolveIn(BaseModel):
    resolution: str = Field(..., pattern="^(keep_google|overwrite_ora|unlink)$")


class DeleteSyncedIn(BaseModel):
    also_delete_google: bool = False


class AskDocumentIn(BaseModel):
    question: str = Field(..., min_length=2, max_length=2000)


def _svc():
    from deps import get_document_service
    return get_document_service()


def _intel():
    from deps import get_intelligence_service
    return get_intelligence_service()


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


@router.get("/search/intelligent")
async def search_intelligent_documents(
    q: Optional[str] = Query(default=None),
    macro_category: Optional[str] = Query(default=None),
    subcategory: Optional[str] = Query(default=None),
    pipeline_status: Optional[str] = Query(default=None),
    has_open_actions: Optional[bool] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user=Depends(get_current_user),
):
    return await _intel().search(
        user_id=user["user_id"],
        q=q,
        macro_category=macro_category,
        subcategory=subcategory,
        pipeline_status=pipeline_status,
        has_open_actions=has_open_actions,
        limit=limit,
        offset=offset,
    )


@router.get("/calendar/drafts")
async def list_calendar_drafts(user=Depends(get_current_user)):
    return {"items": await _intel().calendar.list_for_user(user["user_id"])}


@router.get("/calendar/google/status")
async def google_calendar_write_status(user=Depends(get_current_user)):
    from deps import get_google_calendar_service
    from documents.intelligence.google_sync import GoogleCalendarSyncService
    sync = GoogleCalendarSyncService(db=_intel().db, google_calendar_service=get_google_calendar_service())
    return await sync.connection_status(user["user_id"])


@router.get("/calendar/google/calendars")
async def google_calendar_list_for_write(user=Depends(get_current_user)):
    """List Google calendars for the active connector instance (write UI)."""
    from deps import get_google_calendar_service
    from documents.intelligence.google_sync import GoogleCalendarSyncService
    gcal = get_google_calendar_service()
    sync = GoogleCalendarSyncService(db=_intel().db, google_calendar_service=gcal)
    status = await sync.connection_status(user["user_id"])
    if not status.get("connected") or not status.get("instance_id"):
        raise HTTPException(status_code=400, detail="Google Calendar non collegato")
    try:
        items = await gcal.list_calendars_for_instance(
            user_id=user["user_id"], instance_id=status["instance_id"],
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)[:240])
    return {
        "items": items,
        "default_calendar_id": status.get("default_calendar_id"),
        "account_email": status.get("account_email"),
        "write_capable": status.get("write_capable"),
        "needs_reconnect": status.get("needs_reconnect"),
    }


@router.patch("/calendar/google/default")
async def google_calendar_set_default(body: CalendarDefaultIn, user=Depends(get_current_user)):
    from deps import get_google_calendar_service
    from documents.intelligence.google_sync import GoogleCalendarSyncService
    sync = GoogleCalendarSyncService(db=_intel().db, google_calendar_service=get_google_calendar_service())
    try:
        return await sync.set_default_calendar(user_id=user["user_id"], calendar_id=body.calendar_id)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/calendar/events/{draft_id}/sync")
async def sync_calendar_draft(draft_id: str, user=Depends(get_current_user)):
    from deps import get_google_calendar_service
    from documents.intelligence.google_sync import GoogleCalendarSyncService
    sync = GoogleCalendarSyncService(db=_intel().db, google_calendar_service=get_google_calendar_service())
    try:
        return await sync.sync_draft(user_id=user["user_id"], draft_id=draft_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/calendar/events/{draft_id}/retry")
async def retry_calendar_draft(draft_id: str, user=Depends(get_current_user)):
    return await sync_calendar_draft(draft_id, user)


@router.post("/calendar/events/{draft_id}/resolve-conflict")
async def resolve_calendar_conflict(
    draft_id: str, body: ConflictResolveIn, user=Depends(get_current_user),
):
    from deps import get_google_calendar_service
    from documents.intelligence.google_sync import GoogleCalendarSyncService
    sync = GoogleCalendarSyncService(db=_intel().db, google_calendar_service=get_google_calendar_service())
    try:
        return await sync.resolve_conflict(
            user_id=user["user_id"], draft_id=draft_id, resolution=body.resolution,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/calendar/events/{draft_id}")
async def delete_calendar_draft(
    draft_id: str,
    also_delete_google: bool = Query(default=False),
    user=Depends(get_current_user),
):
    from deps import get_google_calendar_service
    from documents.intelligence.google_sync import GoogleCalendarSyncService
    sync = GoogleCalendarSyncService(db=_intel().db, google_calendar_service=get_google_calendar_service())
    try:
        return await sync.delete_remote(
            user_id=user["user_id"],
            draft_id=draft_id,
            also_delete_google=also_delete_google,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Evento non trovato")


@router.get("/{doc_id}")
async def get_document(doc_id: str, user=Depends(get_current_user)):
    try:
        return await _svc().get(user_id=user["user_id"], doc_id=doc_id)
    except DocumentNotFound:
        raise HTTPException(status_code=404, detail="Documento non trovato")


@router.get("/{doc_id}/insights")
async def get_document_insights(doc_id: str, user=Depends(get_current_user)):
    """Iter21: deterministic insights. NO LLM, NO re-OCR."""
    try:
        doc = await _svc().get(user_id=user["user_id"], doc_id=doc_id)
    except DocumentNotFound:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    from .insights import compute_insights
    return compute_insights(doc)


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


# --- Intelligent analysis -------------------------------------------------
@router.post("/{doc_id}/analyze")
async def analyze_document(doc_id: str, user=Depends(get_current_user)):
    try:
        await _svc().get(user_id=user["user_id"], doc_id=doc_id)
    except DocumentNotFound:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    from documents.intelligence.pipeline import PipelineState
    from documents.intelligence.worker import enqueue_document_job
    doc = await _svc().get(user_id=user["user_id"], doc_id=doc_id)
    upd = PipelineState.set_status(doc, "queued")
    await _svc().db.documents.update_one(
        {"id": doc_id, "user_id": user["user_id"]}, {"$set": upd},
    )
    await enqueue_document_job(user["user_id"], doc_id, reason="manual")
    return {"ok": True, "pipeline_status": "queued"}


@router.post("/{doc_id}/reanalyze")
async def reanalyze_document(doc_id: str, user=Depends(get_current_user)):
    return await analyze_document(doc_id, user)


@router.get("/{doc_id}/analysis")
async def get_document_analysis(doc_id: str, user=Depends(get_current_user)):
    try:
        return await _intel().get_analysis(user_id=user["user_id"], doc_id=doc_id)
    except DocumentNotFound:
        raise HTTPException(status_code=404, detail="Documento non trovato")


@router.patch("/{doc_id}/analysis")
async def patch_document_analysis(doc_id: str, body: AnalysisPatchIn, user=Depends(get_current_user)):
    try:
        return await _intel().patch_analysis(
            user_id=user["user_id"],
            doc_id=doc_id,
            body=body.model_dump(exclude_unset=True),
        )
    except DocumentNotFound:
        raise HTTPException(status_code=404, detail="Documento non trovato")


@router.delete("/{doc_id}/analysis")
async def clear_document_analysis(doc_id: str, user=Depends(get_current_user)):
    try:
        return await _intel().clear_analysis(user_id=user["user_id"], doc_id=doc_id)
    except DocumentNotFound:
        raise HTTPException(status_code=404, detail="Documento non trovato")


@router.patch("/{doc_id}/events/{event_id}")
async def patch_event_candidate(
    doc_id: str, event_id: str, body: EventPatchIn, user=Depends(get_current_user),
):
    try:
        return await _intel().update_event_candidate(
            user_id=user["user_id"],
            doc_id=doc_id,
            event_id=event_id,
            patch=body.model_dump(exclude_unset=True),
        )
    except DocumentNotFound:
        raise HTTPException(status_code=404, detail="Evento o documento non trovato")


@router.post("/{doc_id}/events/{event_id}/confirm")
async def confirm_event_candidate(
    doc_id: str, event_id: str, body: EventConfirmIn = EventConfirmIn(), user=Depends(get_current_user),
):
    try:
        return await _intel().confirm_event(
            user_id=user["user_id"],
            doc_id=doc_id,
            event_id=event_id,
            overrides=body.overrides,
            sync_to_google=bool(body.sync_to_google),
        )
    except DocumentNotFound:
        raise HTTPException(status_code=404, detail="Evento o documento non trovato")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{doc_id}/events/{event_id}/dismiss")
async def dismiss_event_candidate(doc_id: str, event_id: str, user=Depends(get_current_user)):
    try:
        return await _intel().dismiss_event(
            user_id=user["user_id"], doc_id=doc_id, event_id=event_id, remind_later=False,
        )
    except DocumentNotFound:
        raise HTTPException(status_code=404, detail="Evento o documento non trovato")


@router.post("/{doc_id}/events/{event_id}/remind-later")
async def remind_event_candidate(doc_id: str, event_id: str, user=Depends(get_current_user)):
    try:
        return await _intel().dismiss_event(
            user_id=user["user_id"], doc_id=doc_id, event_id=event_id, remind_later=True,
        )
    except DocumentNotFound:
        raise HTTPException(status_code=404, detail="Evento o documento non trovato")


@router.post("/{doc_id}/events/{event_id}/calendar")
async def event_to_calendar(
    doc_id: str, event_id: str, body: EventConfirmIn = EventConfirmIn(), user=Depends(get_current_user),
):
    """Confirm candidate; optional Google sync via body.sync_to_google."""
    return await confirm_event_candidate(doc_id, event_id, body, user)


@router.post("/{doc_id}/ask")
async def ask_document_brain(doc_id: str, body: AskDocumentIn, user=Depends(get_current_user)):
    try:
        return await _intel().ask_document(
            user_id=user["user_id"], doc_id=doc_id, question=body.question,
        )
    except DocumentNotFound:
        raise HTTPException(status_code=404, detail="Documento non trovato")
