"""Orchestrates pipeline, persistence, brain merge, event confirmations."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from documents.intelligence.analyzer import analyze_document
from documents.intelligence.calendar_adapter import CalendarGateway, enrich_maps
from documents.intelligence.pipeline import PipelineState
from documents.service import DocumentNotFound

logger = logging.getLogger("ora.documents.intel")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class IntelligenceService:
    def __init__(self, db, document_service):
        self.db = db
        self.docs = document_service
        self.calendar = CalendarGateway(db)

    async def ensure_ready(self) -> None:
        try:
            await self.db.documents.create_index(
                [("user_id", 1), ("pipeline_status", 1)], name="user_pipeline"
            )
            await self.db.documents.create_index(
                [("user_id", 1), ("analysis.macro_category", 1)], name="user_macro"
            )
            await self.db.calendar_event_drafts.create_index("id", unique=True)
            await self.db.calendar_event_drafts.create_index(
                [("user_id", 1), ("start_datetime", 1)], name="user_cal_start"
            )
        except Exception:
            logger.debug("intel indexes soft-fail", exc_info=True)

    async def mark_uploaded_and_queue(self, *, user_id: str, doc_id: str) -> None:
        doc = await self.docs.get(user_id=user_id, doc_id=doc_id)
        base = PipelineState.initial()
        await self.db.documents.update_one(
            {"id": doc_id, "user_id": user_id},
            {"$set": {**base, **PipelineState.set_status({**doc, **base}, "queued")}},
        )
        from documents.intelligence.worker import enqueue_document_job
        await enqueue_document_job(user_id, doc_id, reason="upload")

    async def run_pipeline(self, *, user_id: str, doc_id: str, force_local: bool = False) -> dict:
        try:
            doc = await self.docs.get(user_id=user_id, doc_id=doc_id)
        except DocumentNotFound:
            return {"ok": False, "error": "not_found"}

        user = await self.db.users.find_one({"user_id": user_id}, {"_id": 0, "preferences": 1})

        async def phase(status: str, **kwargs):
            d = await self.docs.get(user_id=user_id, doc_id=doc_id)
            upd = PipelineState.set_status(d, status, **kwargs)
            await self.db.documents.update_one({"id": doc_id, "user_id": user_id}, {"$set": upd})

        try:
            await phase("extracting")
            # Extraction already done at upload; re-run only if empty text and blob available
            if not (doc.get("extracted_text") or "").strip():
                try:
                    blob = await self.docs.storage.read(user_id=user_id, key=doc["storage_key"])
                    await self.docs._extract_and_persist(
                        user_id=user_id,
                        doc_id=doc_id,
                        blob=blob,
                        mime_type=doc.get("mime_type") or "application/octet-stream",
                        life_node_id=doc.get("life_node_id"),
                    )
                    doc = await self.docs.get(user_id=user_id, doc_id=doc_id)
                except Exception:
                    logger.debug("re-extract soft-fail", exc_info=True)

            await phase("classifying")
            await phase("analyzing", provider="local")
            result = await analyze_document(doc, user=user, force_local=force_local)
            analysis = result["analysis"]
            events = result["event_candidates"]
            for i, ev in enumerate(events):
                events[i] = {**ev, **enrich_maps(ev)}

            # Preserve user title and confirmed event overrides
            prev = doc.get("analysis") or {}
            if doc.get("user_title"):
                analysis["suggested_title"] = doc["user_title"]
                analysis["title_locked"] = True
            else:
                analysis["title_locked"] = False

            prev_events = {e.get("id"): e for e in (doc.get("event_candidates") or []) if e.get("status") != "proposed"}
            merged_events = []
            for ev in events:
                # keep confirmed/dismissed from previous by matching booking/title+start
                keep = None
                for pe in prev_events.values():
                    if pe.get("status") in ("confirmed", "dismissed", "remind_later"):
                        if pe.get("booking_reference") and pe.get("booking_reference") == ev.get("booking_reference"):
                            keep = pe
                            break
                        if pe.get("title") == ev.get("title") and pe.get("start_datetime") == ev.get("start_datetime"):
                            keep = pe
                            break
                if keep:
                    merged = {**ev, **{k: keep[k] for k in ("status", "user_overrides", "priority", "urgency") if k in keep}}
                    if keep.get("user_overrides"):
                        merged.update({k: v for k, v in keep["user_overrides"].items() if v is not None})
                    merged_events.append(merged)
                else:
                    merged_events.append(ev)

            display_title = doc.get("user_title") or analysis.get("suggested_title") or doc.get("filename")
            terminal = "action_required" if (analysis.get("requires_review") or any(
                e.get("status") == "proposed" for e in merged_events
            )) else "completed"
            if analysis.get("requires_review") and not merged_events:
                terminal = "needs_review"

            provider = analysis.get("model")
            await phase(terminal, provider=provider)

            brain = await self._merge_brain(doc, analysis, merged_events, result.get("education_analysis"))

            payload = {
                "analysis": analysis,
                "event_candidates": merged_events,
                "education_analysis": result.get("education_analysis"),
                "generic_actions": result.get("generic_actions") or [],
                "insights_snapshot": result.get("insights_snapshot"),
                "display_title": display_title,
                "brain_synced": brain,
                "updated_at": _now(),
            }
            # Optionally update filename display only if not user-locked
            if not doc.get("user_title") and analysis.get("suggested_title"):
                # keep filename as original storage name; store suggested separately
                pass

            await self.db.documents.update_one(
                {"id": doc_id, "user_id": user_id},
                {"$set": payload},
            )
            return {"ok": True, "status": terminal, "document_id": doc_id}
        except Exception as e:
            logger.exception("pipeline failed")
            await phase("failed", error=str(e)[:300])
            return {"ok": False, "error": "pipeline_failed"}

    async def _merge_brain(
        self,
        doc: dict,
        analysis: dict,
        events: list,
        education: Optional[dict],
    ) -> bool:
        if not doc.get("life_node_id") or self.docs.knowledge is None:
            return False
        try:
            patch: dict[str, Any] = {
                "doc_type": analysis.get("subcategory") or analysis.get("macro_category"),
                "category": analysis.get("macro_category"),
                "notes": (analysis.get("summary") or "")[:1000],
                "tags": list(dict.fromkeys((doc.get("tags") or []) + (analysis.get("keywords") or [])))[:30],
            }
            await self.docs.knowledge.merge(
                doc["user_id"],
                doc["life_node_id"],
                patch,
                source_type="document_intelligence",
                actor_type="system",
                actor_id="ora.documents.intel",
                reason=f"document_intel:{doc['id']}",
            )
            # Relations via life graph edges (best-effort, idempotent on reanalyze)
            if self.docs.life_graph is not None:
                existing_ids: set[str] = set()
                try:
                    # Prefer attribute lookup when available; fallback soft
                    nodes = await self.docs.life_graph.list_nodes(doc["user_id"], node_type="event")
                    for n in nodes or []:
                        attrs = n.get("attributes") or {}
                        if attrs.get("source_document_id") == doc["id"] and attrs.get("event_candidate_id"):
                            existing_ids.add(str(attrs["event_candidate_id"]))
                except Exception:
                    existing_ids = set()
                for ev in events:
                    if ev.get("status") == "dismissed":
                        continue
                    eid = str(ev.get("id") or "")
                    if eid and eid in existing_ids:
                        continue
                    try:
                        enode = await self.docs.life_graph.create_node(
                            doc["user_id"],
                            type="event",
                            label=(ev.get("title") or "Evento")[:120],
                            description=(ev.get("description") or "")[:280],
                            attributes={
                                "source_document_id": doc["id"],
                                "event_candidate_id": ev.get("id"),
                                "starts_at": ev.get("start_datetime"),
                                "ends_at": ev.get("end_datetime"),
                                "location": ev.get("venue_name") or ev.get("address"),
                                "relation": "document_has_event",
                            },
                            origin="document_intelligence",
                        )
                        await self.docs.life_graph.create_edge(
                            doc["user_id"],
                            from_node=doc["life_node_id"],
                            to_node=enode["id"],
                            type="documents",
                            attributes={"kind": "document_has_event"},
                        )
                        if eid:
                            existing_ids.add(eid)
                    except Exception:
                        logger.debug("brain event node soft-fail", exc_info=True)
                if education and education.get("subject"):
                    # Subject stored on knowledge/analysis — avoid self-edge (LG forbids)
                    pass
            return True
        except Exception:
            logger.debug("brain merge soft-fail", exc_info=True)
            return False

    async def get_analysis(self, *, user_id: str, doc_id: str) -> dict:
        doc = await self.docs.get(user_id=user_id, doc_id=doc_id)
        events = [ {**e, **enrich_maps(e)} for e in (doc.get("event_candidates") or []) ]
        return {
            "document_id": doc_id,
            "pipeline_status": doc.get("pipeline_status") or "uploaded",
            "pipeline_status_label": doc.get("pipeline_status_label"),
            "pipeline_error": doc.get("pipeline_error"),
            "pipeline_provider": doc.get("pipeline_provider"),
            "pipeline_attempts": doc.get("pipeline_attempts"),
            "pipeline_duration_ms": doc.get("pipeline_duration_ms"),
            "display_title": doc.get("display_title") or doc.get("user_title") or doc.get("filename"),
            "user_title": doc.get("user_title"),
            "analysis": doc.get("analysis"),
            "event_candidates": events,
            "education_analysis": doc.get("education_analysis"),
            "generic_actions": doc.get("generic_actions") or [],
            "ai_consent_required_note": (
                None
                if (doc.get("analysis") or {}).get("ai_used")
                else "Analisi locale; AI esterna non usata o non disponibile."
            ),
        }

    async def patch_analysis(self, *, user_id: str, doc_id: str, body: dict) -> dict:
        doc = await self.docs.get(user_id=user_id, doc_id=doc_id)
        updates: dict[str, Any] = {"updated_at": _now()}
        if "user_title" in body and body["user_title"] is not None:
            updates["user_title"] = str(body["user_title"])[:200]
            updates["display_title"] = updates["user_title"]
        if "analysis" in body and isinstance(body["analysis"], dict):
            analysis = dict(doc.get("analysis") or {})
            for k in ("summary", "short_description", "keywords", "macro_category", "subcategory"):
                if k in body["analysis"]:
                    analysis[k] = body["analysis"][k]
            updates["analysis"] = analysis
        await self.db.documents.update_one({"id": doc_id, "user_id": user_id}, {"$set": updates})
        return await self.get_analysis(user_id=user_id, doc_id=doc_id)

    async def update_event_candidate(
        self, *, user_id: str, doc_id: str, event_id: str, patch: dict
    ) -> dict:
        doc = await self.docs.get(user_id=user_id, doc_id=doc_id)
        events = list(doc.get("event_candidates") or [])
        found = False
        for i, ev in enumerate(events):
            if ev.get("id") == event_id:
                overrides = dict(ev.get("user_overrides") or {})
                for k in (
                    "title", "start_datetime", "end_datetime", "venue_name", "address",
                    "city", "priority", "urgency", "description", "timezone", "all_day",
                ):
                    if k in patch:
                        ev[k] = patch[k]
                        overrides[k] = patch[k]
                ev["user_overrides"] = overrides
                events[i] = {**ev, **enrich_maps(ev)}
                found = True
                break
        if not found:
            raise DocumentNotFound()
        await self.db.documents.update_one(
            {"id": doc_id, "user_id": user_id},
            {"$set": {"event_candidates": events, "updated_at": _now()}},
        )
        return await self.get_analysis(user_id=user_id, doc_id=doc_id)

    async def confirm_event(
        self,
        *,
        user_id: str,
        doc_id: str,
        event_id: str,
        overrides: Optional[dict] = None,
        sync_to_google: bool = False,
    ) -> dict:
        doc = await self.docs.get(user_id=user_id, doc_id=doc_id)
        events = list(doc.get("event_candidates") or [])
        target = None
        target_idx = -1
        for i, ev in enumerate(events):
            if ev.get("id") == event_id:
                target = ev
                target_idx = i
                break
        if not target:
            raise DocumentNotFound()

        # Idempotent double-confirm: return existing draft, no duplicate insert
        existing = await self.db.calendar_event_drafts.find_one(
            {
                "user_id": user_id,
                "source_document_id": doc_id,
                "source_event_candidate_id": event_id,
                "status": {"$ne": "cancelled"},
            },
            {"_id": 0},
        )
        if existing and target.get("status") == "confirmed":
            cal = existing
            dedup = True
        else:
            if overrides:
                target = {
                    **target,
                    **overrides,
                    "user_overrides": {**(target.get("user_overrides") or {}), **overrides},
                }
            if target.get("ambiguous_date") and not (overrides or {}).get("start_datetime") and not target.get("start_datetime"):
                raise ValueError("Data ambigua: fornisci start_datetime prima di confermare")
            if not target.get("start_datetime") and not (overrides or {}).get("start_datetime"):
                raise ValueError("Data/ora mancante: non posso creare l'evento")
            target["status"] = "confirmed"
            events[target_idx] = target
            cal = await self.calendar.get("internal").create_from_candidate(
                user_id=user_id, candidate=target, overrides=overrides,
            )
            await self.db.documents.update_one(
                {"id": doc_id, "user_id": user_id},
                {"$set": {
                    "event_candidates": events,
                    "pipeline_status": "completed",
                    "pipeline_status_label": "Analisi completata",
                    "updated_at": _now(),
                }},
            )
            dedup = False

        google_result = None
        if sync_to_google:
            try:
                from deps import get_google_calendar_service
                from documents.intelligence.google_sync import GoogleCalendarSyncService
                sync = GoogleCalendarSyncService(db=self.db, google_calendar_service=get_google_calendar_service())
                macro = (doc.get("analysis") or {}).get("macro_category")
                maps = target.get("maps_url")
                google_result = await sync.sync_draft(
                    user_id=user_id,
                    draft_id=cal["id"],
                    macro_category=macro,
                    maps_url=maps,
                )
                cal = google_result
            except Exception as e:
                logger.warning("google sync after confirm failed type=%s", type(e).__name__)
                google_result = {
                    "ok": False,
                    "sync_status": "failed",
                    "sync_error": type(e).__name__,
                    "error": str(e)[:240] or type(e).__name__,
                }
            else:
                if isinstance(google_result, dict):
                    google_result = {
                        **google_result,
                        "ok": google_result.get("sync_status") == "synced",
                    }

        return {
            "ok": True,
            "event_candidate": target,
            "calendar_event": cal,
            "deduplicated": dedup,
            "google_sync": google_result,
        }

    async def dismiss_event(self, *, user_id: str, doc_id: str, event_id: str, remind_later: bool = False) -> dict:
        doc = await self.docs.get(user_id=user_id, doc_id=doc_id)
        events = list(doc.get("event_candidates") or [])
        found = False
        for i, ev in enumerate(events):
            if ev.get("id") == event_id:
                ev["status"] = "remind_later" if remind_later else "dismissed"
                events[i] = ev
                found = True
                break
        if not found:
            raise DocumentNotFound()
        await self.db.documents.update_one(
            {"id": doc_id, "user_id": user_id},
            {"$set": {"event_candidates": events, "updated_at": _now()}},
        )
        return {"ok": True, "status": events}

    async def clear_analysis(self, *, user_id: str, doc_id: str) -> dict:
        await self.docs.get(user_id=user_id, doc_id=doc_id)
        await self.db.documents.update_one(
            {"id": doc_id, "user_id": user_id},
            {"$set": {
                "analysis": None,
                "event_candidates": [],
                "education_analysis": None,
                "generic_actions": [],
                "pipeline_status": "uploaded",
                "pipeline_status_label": "Documento caricato",
                "updated_at": _now(),
            }},
        )
        return {"ok": True}

    async def ask_document(self, *, user_id: str, doc_id: str, question: str) -> dict:
        doc = await self.docs.get(user_id=user_id, doc_id=doc_id)
        text = (doc.get("extracted_text") or "")[:12000]
        analysis = doc.get("analysis") or {}
        if not text.strip():
            return {
                "answer": "Nel documento non è disponibile testo estraibile.",
                "grounding": "not_found",
                "ai_used": False,
            }
        from llm import LLMNotConfigured
        from llm.manager import get_manager

        user_doc = await self.db.users.find_one(
            {"user_id": user_id}, {"_id": 0, "preferences": 1}
        )
        pref = ((user_doc or {}).get("preferences") or {}).get("llm_provider")

        def _local_ask():
            import re as _re
            tokens = [
                w for w in _re.findall(r"[a-zA-Zàèéìòù]{4,}", question.lower())
                if w not in {"come", "dove", "quando", "quale", "quali", "questo", "questa", "documento"}
            ]
            hits = [
                ln for ln in text.splitlines()
                if any(w in ln.lower() for w in tokens)
            ][:5]
            if hits:
                return {
                    "answer": "[CONTENUTO] Dal testo del documento:\n" + "\n".join(hits),
                    "grounding": "document_content",
                    "ai_used": False,
                }
            if analysis.get("summary") and tokens:
                return {
                    "answer": "[SINTESI] " + str(analysis.get("summary"))[:400],
                    "grounding": "summary",
                    "ai_used": False,
                }
            return {
                "answer": "[NON TROVATO] Informazione non presente nel testo estratto (AI non configurata).",
                "grounding": "not_found",
                "ai_used": False,
            }

        try:
            result = await get_manager().ask_document(
                text=f"Titolo: {analysis.get('suggested_title')}\n\n{text}",
                question=question,
                user_preference=pref,
            )
            answer = result.text
            grounding = "document_content"
            if answer.strip().startswith("[NON TROVATO]"):
                grounding = "not_found"
            elif answer.strip().startswith("[SINTESI]"):
                grounding = "summary"
            return {
                "answer": answer,
                "grounding": grounding,
                "ai_used": True,
                "provider": result.provider,
                "model": result.model,
            }
        except LLMNotConfigured:
            return _local_ask()
        except Exception:
            logger.warning("ask_document provider failed; local fallback")
            return _local_ask()

    async def search(
        self,
        *,
        user_id: str,
        q: Optional[str] = None,
        macro_category: Optional[str] = None,
        subcategory: Optional[str] = None,
        pipeline_status: Optional[str] = None,
        has_open_actions: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        query: dict[str, Any] = {"user_id": user_id, "deleted": {"$ne": True}}
        if macro_category:
            query["analysis.macro_category"] = macro_category
        if subcategory:
            query["analysis.subcategory"] = subcategory
        if pipeline_status:
            query["pipeline_status"] = pipeline_status
        if has_open_actions:
            query["event_candidates"] = {"$elemMatch": {"status": "proposed"}}
        if q:
            rx = {"$regex": q, "$options": "i"}
            query["$or"] = [
                {"filename": rx},
                {"original_filename": rx},
                {"display_title": rx},
                {"user_title": rx},
                {"analysis.suggested_title": rx},
                {"analysis.keywords": rx},
                {"analysis.summary": rx},
                {"extracted_text": rx},
                {"analysis.macro_category": rx},
                {"analysis.subcategory": rx},
                {"event_candidates.venue_name": rx},
                {"event_candidates.city": rx},
                {"education_analysis.subject": rx},
            ]
        cur = self.db.documents.find(query, {"_id": 0, "extracted_text": 0}).sort("created_at", -1).skip(offset).limit(limit)
        items = await cur.to_list(limit)
        total = await self.db.documents.count_documents(query)
        return {"items": items, "total": total, "limit": limit, "offset": offset}
