"""DocumentService — business logic layer.

Responsabilità:
    * validazione (mime, size)
    * persistenza metadata su `documents` collection
    * chiama storage.put(...) per il blob
    * deduplica (per lo stesso utente) via hash SHA-256
    * mirror in Life Graph (nodo `document`) + Knowledge Layer
    * soft delete + archive/restore
    * ricerca su nome / tag / note / tipo
    * download con controllo ownership

Non chiama mai il Decision Engine né il Behavior Engine (vietato in
Iterazione 19). Non estrae contenuto (né OCR né AI).
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .extraction import ExtractionPipeline, ExtractionResult, now_iso as _ext_now
from .storage import DocumentStorageProvider, StoredObject

logger = logging.getLogger("ora.documents")


DEFAULT_MAX_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB

# Whitelist minimale ma flessibile. Vietiamo eseguibili & script.
DEFAULT_ALLOWED_MIMES = frozenset({
    # PDF / office
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    # Testo
    "text/plain", "text/csv", "text/markdown", "text/rtf",
    # Immagini
    "image/png", "image/jpeg", "image/webp", "image/heic", "image/heif", "image/gif",
    # Archivi (metadata only, non estraiamo)
    "application/zip",
    # Generic binary — accettato ma flaggato
    "application/octet-stream",
})


class DocumentValidationError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class DocumentNotFound(Exception):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return f"doc_{uuid.uuid4().hex[:12]}"


def _max_size_bytes() -> int:
    try:
        return int(os.environ.get("DOCUMENT_MAX_SIZE_BYTES", str(DEFAULT_MAX_SIZE_BYTES)))
    except Exception:
        return DEFAULT_MAX_SIZE_BYTES


def _allowed_mimes() -> frozenset:
    raw = os.environ.get("DOCUMENT_ALLOWED_MIMES")
    if not raw:
        return DEFAULT_ALLOWED_MIMES
    return frozenset(m.strip() for m in raw.split(",") if m.strip())


class DocumentService:
    def __init__(self, *, db, storage: DocumentStorageProvider, life_graph=None, knowledge=None):
        self.db = db
        self.storage = storage
        self.life_graph = life_graph
        self.knowledge = knowledge
        self.pipeline = ExtractionPipeline()

    # ------------------------------------------------------------------
    # Bootstrap: ensure indexes idempotently.
    # ------------------------------------------------------------------
    async def ensure_ready(self) -> None:
        col = self.db.documents
        try:
            await col.create_index([("user_id", 1), ("hash", 1)], name="user_hash")
            await col.create_index([("user_id", 1), ("created_at", -1)], name="user_created")
            await col.create_index([("user_id", 1), ("archived", 1), ("deleted", 1)], name="user_state")
            await col.create_index([("user_id", 1), ("filename", "text"), ("notes", "text"), ("tags", "text"), ("extracted_text", "text")], name="user_text")
            await col.create_index([("user_id", 1), ("pipeline_status", 1)], name="user_pipeline")
        except Exception:
            logger.debug("documents index creation swallowed", exc_info=True)

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------
    async def upload(
        self,
        *,
        user_id: str,
        content: bytes,
        original_filename: str,
        mime_type: str,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
        upload_source: str = "web",
    ) -> Dict[str, Any]:
        # Validazione
        if not original_filename:
            raise DocumentValidationError("missing_filename", "Il nome file è obbligatorio.")
        if not content:
            raise DocumentValidationError("empty_content", "Il file è vuoto.")
        size = len(content)
        if size > _max_size_bytes():
            raise DocumentValidationError(
                "file_too_large",
                f"Il file supera {_max_size_bytes() // (1024 * 1024)} MB.",
            )
        mime = (mime_type or "application/octet-stream").lower().split(";")[0].strip()
        if mime not in _allowed_mimes():
            raise DocumentValidationError("mime_not_allowed", f"Tipo file non supportato: {mime}")

        # Storage put (calcola hash)
        stored: StoredObject = await self.storage.put(
            user_id=user_id, content=content,
            original_filename=original_filename, mime_type=mime,
        )

        # Deduplica DB: se esiste già un documento attivo per lo stesso
        # utente con lo stesso hash → non ricreare, ma restituirlo
        # marcato come "duplicate" (upload contract).
        existing = await self.db.documents.find_one(
            {"user_id": user_id, "hash": stored.hash, "deleted": {"$ne": True}},
            {"_id": 0},
        )
        if existing:
            # Se stava in archivio lo lasciamo dov'è ma segnaliamo il duplicato.
            return {"duplicate": True, "document": existing}

        # Sanifica nome file (basename, no path traversal)
        safe_name = os.path.basename(original_filename)[:255] or "documento.bin"

        now = _now_iso()
        doc_id = _new_id()
        life_node_id: Optional[str] = None
        knowledge_synced = False

        # 1. Crea nodo Life Graph (type=document)
        if self.life_graph is not None:
            try:
                node = await self.life_graph.create_node(
                    user_id,
                    type="document",
                    label=safe_name[:120],
                    description=notes[:280] if notes else None,
                    attributes={
                        "document_id": doc_id,
                        "mime_type": mime,
                        "size": size,
                        "hash": stored.hash,
                        "source": "user_upload",
                        "upload_source": upload_source,
                        "created_at": now,
                    },
                    origin="user_upload",
                )
                life_node_id = node["id"]
            except Exception:
                logger.exception("documents: life_graph.create_node failed (soft-fail)")

        # 2. Knowledge Fact minimale (solo se node esiste)
        if life_node_id and self.knowledge is not None:
            try:
                await self.knowledge.merge(
                    user_id,
                    life_node_id,
                    {
                        "filename": safe_name,
                        "mime_type": mime,
                        "tags": list(tags or []),
                        "notes": (notes or "")[:1000],
                    },
                    source_type="user_upload",
                    actor_type="user",
                    actor_id=user_id,
                    reason=f"document:{doc_id}",
                )
                knowledge_synced = True
            except Exception:
                logger.exception("documents: knowledge.merge failed (soft-fail)")

        # 3. Doc principale
        doc = {
            "id": doc_id,
            "user_id": user_id,
            "filename": safe_name,
            "original_filename": original_filename[:512],
            "mime_type": mime,
            "size": size,
            "hash": stored.hash,
            "storage_provider": stored.provider,
            "storage_key": stored.key,
            "upload_source": upload_source,
            "tags": list(tags or []),
            "notes": (notes or "")[:2000],
            "archived": False,
            "deleted": False,
            "life_node_id": life_node_id,
            "knowledge_synced": knowledge_synced,
            "version": 1,
            "created_at": now,
            "updated_at": now,
        }
        await self.db.documents.insert_one(doc)
        doc.pop("_id", None)

        # Iterazione 20: text extraction pipeline. Sync (blocking) so
        # the freshly-uploaded doc is immediately searchable and the
        # response carries the flag `text_extracted`. Duplicate cache is
        # handled higher up (identical hash → we return existing doc
        # without re-running extraction).
        try:
            extracted = await self._extract_and_persist(
                user_id=user_id, doc_id=doc_id, blob=content, mime_type=mime,
                life_node_id=life_node_id,
            )
            if extracted:
                doc.update({
                    "text_extracted": True,
                    "ocr_used": extracted.get("ocr_used", False),
                    "extraction_engine": extracted.get("engine"),
                    "pages": extracted.get("pages"),
                    "language": extracted.get("language"),
                    "confidence": extracted.get("confidence"),
                    "extracted_at": extracted.get("extracted_at"),
                })
        except Exception:
            logger.exception("documents: extraction pipeline failed (soft-fail)")

        # Intelligent documents: enqueue async analysis (does not block upload).
        try:
            from documents.intelligence.pipeline import PipelineState
            from documents.intelligence.worker import enqueue_document_job

            init = PipelineState.initial()
            queued = PipelineState.set_status({**doc, **init}, "queued")
            await self.db.documents.update_one(
                {"id": doc_id, "user_id": user_id},
                {"$set": {**init, **queued}},
            )
            doc.update({**init, **queued})
            await enqueue_document_job(user_id, doc_id, reason="upload")
        except Exception:
            logger.exception("documents: intelligence enqueue soft-fail")

        return {"duplicate": False, "document": doc}

    # ------------------------------------------------------------------
    # Extraction (Iterazione 20)
    # ------------------------------------------------------------------
    _EXTRACTED_TEXT_LIMIT = 500_000  # 500 KB cap on stored text

    async def _extract_and_persist(
        self, *, user_id: str, doc_id: str, blob: bytes, mime_type: str,
        life_node_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        result: ExtractionResult = self.pipeline.run(blob=blob, mime_type=mime_type)
        extracted_text = (result.text or "")[: self._EXTRACTED_TEXT_LIMIT]
        payload = {
            "text_extracted": bool(extracted_text),
            "extracted_text": extracted_text,
            "extraction_engine": result.engine,
            "ocr_used": result.ocr_used,
            "pages": result.pages,
            "detected_language": result.language,
            "confidence": result.confidence,
            "extraction_error_code": result.error_code,
            "extraction_warnings": result.warnings[:20],
            "extraction_duration_ms": round(result.duration_ms, 1),
            "extracted_at": _ext_now(),
            "updated_at": _ext_now(),
        }
        await self.db.documents.update_one(
            {"id": doc_id, "user_id": user_id}, {"$set": payload},
        )
        # Life Graph: aggiorna attributi del nodo documento (best-effort).
        if life_node_id and self.life_graph is not None:
            try:
                node = await self.db.life_nodes.find_one(
                    {"id": life_node_id, "user_id": user_id}, {"_id": 0, "attributes": 1},
                )
                if node:
                    attrs = dict(node.get("attributes") or {})
                    attrs.update({
                        "text_extracted": payload["text_extracted"],
                        "ocr_used": payload["ocr_used"],
                        "pages": payload["pages"],
                        "language": payload["detected_language"],
                        "confidence": payload["confidence"],
                    })
                    await self.life_graph.update_node(user_id, life_node_id, {"attributes": attrs})
            except Exception:
                logger.debug("documents: life-graph attrs update soft-fail", exc_info=True)
        # Knowledge Layer: merge testo, pages, lingua, confidence.
        if life_node_id and self.knowledge is not None:
            try:
                await self.knowledge.merge(
                    user_id, life_node_id,
                    {
                        "notes": (extracted_text or "")[:1000],
                        # Additional fields piggyback under a generic
                        # keyed pattern; schema `document` welcomes them
                        # only when defined. Fall back gracefully.
                    },
                    source_type="document_extraction",
                    actor_type="system",
                    actor_id="ora.documents.extraction",
                    reason=f"document_extract:{doc_id}",
                )
            except Exception:
                logger.debug("documents: knowledge extraction merge soft-fail", exc_info=True)
        return payload

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    async def get(self, *, user_id: str, doc_id: str, include_deleted: bool = False) -> Dict[str, Any]:
        q: Dict[str, Any] = {"id": doc_id, "user_id": user_id}
        if not include_deleted:
            q["deleted"] = {"$ne": True}
        doc = await self.db.documents.find_one(q, {"_id": 0})
        if not doc:
            raise DocumentNotFound()
        try:
            from documents.intelligence.migration import stamp_document_versions, with_versions
            patch = stamp_document_versions(doc)
            if patch:
                await self.db.documents.update_one(
                    {"id": doc_id, "user_id": user_id}, {"$set": patch},
                )
                doc = {**doc, **patch}
            return with_versions(doc)
        except Exception:
            return doc

    async def list(
        self,
        *,
        user_id: str,
        q: Optional[str] = None,
        tag: Optional[str] = None,
        mime: Optional[str] = None,
        archived: Optional[bool] = None,
        sort: str = "created_desc",
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        query: Dict[str, Any] = {"user_id": user_id, "deleted": {"$ne": True}}
        if archived is not None:
            query["archived"] = archived
        if mime:
            query["mime_type"] = mime.lower()
        if tag:
            query["tags"] = tag
        if q:
            # Case-insensitive OR: filename/notes/tags/mime + extracted_text + intel fields
            rx = {"$regex": q, "$options": "i"}
            query["$or"] = [
                {"filename": rx},
                {"original_filename": rx},
                {"notes": rx},
                {"tags": rx},
                {"mime_type": rx},
                {"extracted_text": rx},
                {"display_title": rx},
                {"user_title": rx},
                {"analysis.suggested_title": rx},
                {"analysis.keywords": rx},
                {"analysis.macro_category": rx},
                {"analysis.subcategory": rx},
                {"education_analysis.subject": rx},
                {"event_candidates.venue_name": rx},
                {"event_candidates.city": rx},
            ]
        sort_map = {
            "created_desc": [("created_at", -1)],
            "created_asc": [("created_at", 1)],
            "name_asc": [("filename", 1)],
            "name_desc": [("filename", -1)],
            "size_desc": [("size", -1)],
            "size_asc": [("size", 1)],
        }
        sort_by = sort_map.get(sort, sort_map["created_desc"])
        limit = max(1, min(500, int(limit)))
        offset = max(0, int(offset))
        cursor = self.db.documents.find(query, {"_id": 0}).sort(sort_by).skip(offset).limit(limit)
        items = await cursor.to_list(length=limit)
        total = await self.db.documents.count_documents(query)
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    # ------------------------------------------------------------------
    # Update / archive / restore / delete
    # ------------------------------------------------------------------
    async def patch(
        self,
        *,
        user_id: str,
        doc_id: str,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        doc = await self.get(user_id=user_id, doc_id=doc_id)
        updates: Dict[str, Any] = {"updated_at": _now_iso()}
        if tags is not None:
            updates["tags"] = list(tags)
        if notes is not None:
            updates["notes"] = notes[:2000]
        if filename is not None:
            safe = os.path.basename(filename)[:255]
            if safe:
                updates["filename"] = safe
        await self.db.documents.update_one(
            {"id": doc_id, "user_id": user_id}, {"$set": updates},
        )
        # Best-effort: keep Knowledge in sync
        if doc.get("life_node_id") and self.knowledge is not None:
            try:
                await self.knowledge.merge(
                    user_id, doc["life_node_id"],
                    {k: v for k, v in {
                        "filename": updates.get("filename"),
                        "tags": updates.get("tags"),
                        "notes": updates.get("notes"),
                    }.items() if v is not None},
                    source_type="user_upload",
                    actor_type="user", actor_id=user_id,
                    reason=f"document_patch:{doc_id}",
                )
            except Exception:
                logger.debug("documents: knowledge patch soft-fail", exc_info=True)
        return await self.get(user_id=user_id, doc_id=doc_id)

    async def archive(self, *, user_id: str, doc_id: str) -> Dict[str, Any]:
        await self.get(user_id=user_id, doc_id=doc_id)  # ownership check
        await self.db.documents.update_one(
            {"id": doc_id, "user_id": user_id},
            {"$set": {"archived": True, "updated_at": _now_iso()}},
        )
        return await self.get(user_id=user_id, doc_id=doc_id)

    async def restore(self, *, user_id: str, doc_id: str) -> Dict[str, Any]:
        await self.get(user_id=user_id, doc_id=doc_id, include_deleted=True)
        await self.db.documents.update_one(
            {"id": doc_id, "user_id": user_id},
            {"$set": {"archived": False, "deleted": False, "updated_at": _now_iso()},
             "$unset": {"deleted_at": ""}},
        )
        return await self.get(user_id=user_id, doc_id=doc_id, include_deleted=True)

    async def delete(self, *, user_id: str, doc_id: str, hard: bool = False) -> Dict[str, Any]:
        doc = await self.get(user_id=user_id, doc_id=doc_id, include_deleted=True)
        now = _now_iso()
        if hard:
            # Rimozione fisica del blob + doc
            try:
                await self.storage.delete(user_id=user_id, key=doc["storage_key"])
            except Exception:
                logger.debug("documents: storage.delete soft-fail", exc_info=True)
            await self.db.documents.delete_one({"id": doc_id, "user_id": user_id})
            # Marca il nodo life-graph come detached (non lo elimina)
            if doc.get("life_node_id"):
                try:
                    await self.db.life_nodes.update_one(
                        {"id": doc["life_node_id"], "user_id": user_id},
                        {"$set": {"status": "detached", "updated_at": now}},
                    )
                except Exception:
                    pass
            return {"ok": True, "hard": True, "id": doc_id}
        # Soft delete
        await self.db.documents.update_one(
            {"id": doc_id, "user_id": user_id},
            {"$set": {"deleted": True, "deleted_at": now, "updated_at": now}},
        )
        return {"ok": True, "hard": False, "id": doc_id}

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------
    async def read_bytes(self, *, user_id: str, doc_id: str) -> Tuple[Dict[str, Any], bytes]:
        doc = await self.get(user_id=user_id, doc_id=doc_id)
        if doc.get("deleted"):
            raise DocumentNotFound()
        blob = await self.storage.read(user_id=user_id, key=doc["storage_key"])
        return doc, blob
