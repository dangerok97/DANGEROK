"""Orchestrates pipeline, persistence, brain merge, event confirmations."""
from __future__ import annotations

import logging
import re
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
            await phase("understanding", provider="local")
            result = await analyze_document(doc, user=user, force_local=force_local)
            analysis = result["analysis"]
            events = result["event_candidates"]
            for i, ev in enumerate(events):
                events[i] = {**ev, **enrich_maps(ev)}

            await phase("generating_actions", provider=analysis.get("model") or "local")

            # Preserve user title and confirmed event overrides
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
            has_proposed = any(e.get("status") == "proposed" for e in merged_events)
            terminal = "awaiting_confirmation" if (
                analysis.get("requires_review") or has_proposed
            ) else "completed"
            if analysis.get("requires_review") and not merged_events:
                terminal = "needs_review"

            provider = analysis.get("model")
            await phase(terminal, provider=provider)

            brain = await self._merge_brain(doc, analysis, merged_events, result.get("education_analysis"))

            # Preserve user field corrections / confirmed titles across reanalyze
            provenance = dict(doc.get("field_provenance") or {})
            # Seed extracted provenance for key fields (do not clobber confirmed/corrected)
            for fk, val in (
                ("title", analysis.get("suggested_title")),
                ("summary", analysis.get("summary")),
                ("macro_category", analysis.get("macro_category")),
            ):
                if val is None:
                    continue
                cur = provenance.get(fk) or {}
                if cur.get("status") in ("confirmed", "corrected"):
                    continue
                provenance[fk] = {
                    "field_key": fk,
                    "extracted": val,
                    "suggested": val,
                    "status": "extracted",
                    "source": analysis.get("model") or "local",
                    "confidence": analysis.get("confidence"),
                }
            if doc.get("user_title"):
                display_title = doc["user_title"]
                provenance.setdefault("title", {})
                provenance["title"] = {
                    **(provenance.get("title") or {}),
                    "corrected": doc["user_title"],
                    "status": "corrected",
                    "source": "user",
                }

            edu_out = result.get("education_analysis")
            admin_out = result.get("admin_analysis")
            edu_out = _apply_corrected_fields(
                edu_out, doc.get("education_analysis"), provenance, prefix="edu.",
            )
            admin_out = _apply_corrected_fields(
                admin_out, doc.get("admin_analysis"), provenance, prefix="admin.",
            )
            # Never overwrite confirmed/corrected analysis scalars
            for key, meta in list(provenance.items()):
                if not isinstance(meta, dict):
                    continue
                if meta.get("status") not in ("confirmed", "corrected"):
                    continue
                locked = meta.get("corrected") if meta.get("corrected") is not None else meta.get("confirmed")
                if key in ("summary", "short_description", "keywords", "macro_category", "subcategory"):
                    if locked is not None:
                        analysis[key] = locked

            payload = {
                "analysis": analysis,
                "event_candidates": merged_events,
                "education_analysis": edu_out,
                "admin_analysis": admin_out,
                "generic_actions": _merge_generic_actions(
                    doc.get("generic_actions") or [],
                    result.get("generic_actions") or [],
                ),
                "insights_snapshot": result.get("insights_snapshot"),
                "display_title": display_title,
                "brain_synced": brain,
                "field_provenance": provenance,
                "analysis_version": "2.0",
                "document_schema_version": "2.0",
                "processing_version": "intel-docs-2.0",
                "updated_at": _now(),
            }

            await self.db.documents.update_one(
                {"id": doc_id, "user_id": user_id},
                {"$set": payload},
            )

            auto = await self._maybe_auto_add_calendar(
                user_id=user_id,
                doc_id=doc_id,
                events=merged_events,
                analysis=analysis,
                user=user,
            )
            return {
                "ok": True,
                "status": terminal,
                "document_id": doc_id,
                "auto_calendar": auto,
            }
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
            "admin_analysis": doc.get("admin_analysis"),
            "generic_actions": doc.get("generic_actions") or [],
            "flashcards": doc.get("flashcards") or [],
            "quiz_session": doc.get("quiz_session"),
            "field_provenance": doc.get("field_provenance") or {},
            "ai_consent_required_note": (
                None
                if (doc.get("analysis") or {}).get("ai_used")
                else "Analisi locale; AI esterna non usata o non disponibile."
            ),
        }

    async def patch_analysis(self, *, user_id: str, doc_id: str, body: dict) -> dict:
        doc = await self.docs.get(user_id=user_id, doc_id=doc_id)
        updates: dict[str, Any] = {"updated_at": _now()}
        provenance = dict(doc.get("field_provenance") or {})
        if "user_title" in body and body["user_title"] is not None:
            updates["user_title"] = str(body["user_title"])[:200]
            updates["display_title"] = updates["user_title"]
            provenance["title"] = {
                "field_key": "title",
                "extracted": (doc.get("analysis") or {}).get("suggested_title"),
                "corrected": updates["user_title"],
                "status": "corrected",
                "source": "user",
                "confidence": 1.0,
            }
        if "analysis" in body and isinstance(body["analysis"], dict):
            analysis = dict(doc.get("analysis") or {})
            # Do not overwrite confirmed/corrected title via reanalyze-style patches
            for k in ("summary", "short_description", "keywords", "macro_category", "subcategory"):
                if k in body["analysis"]:
                    analysis[k] = body["analysis"][k]
                    provenance[k] = {
                        "field_key": k,
                        "extracted": (doc.get("analysis") or {}).get(k),
                        "corrected": body["analysis"][k],
                        "status": "corrected",
                        "source": "user",
                        "confidence": 1.0,
                    }
            updates["analysis"] = analysis
        if "admin_analysis" in body and isinstance(body["admin_analysis"], dict):
            admin = dict(doc.get("admin_analysis") or {})
            for k, v in body["admin_analysis"].items():
                admin[k] = v
                provenance[f"admin.{k}"] = {
                    "field_key": f"admin.{k}",
                    "corrected": v,
                    "status": "corrected",
                    "source": "user",
                    "confidence": 1.0,
                }
            updates["admin_analysis"] = admin
        if "education_analysis" in body and isinstance(body["education_analysis"], dict):
            edu = dict(doc.get("education_analysis") or {})
            for k, v in body["education_analysis"].items():
                edu[k] = v
                provenance[f"edu.{k}"] = {
                    "field_key": f"edu.{k}",
                    "corrected": v,
                    "status": "corrected",
                    "source": "user",
                    "confidence": 1.0,
                }
            updates["education_analysis"] = edu
        updates["field_provenance"] = provenance
        await self.db.documents.update_one({"id": doc_id, "user_id": user_id}, {"$set": updates})
        return await self.get_analysis(user_id=user_id, doc_id=doc_id)

    async def study_action(self, *, user_id: str, doc_id: str, action: str) -> dict:
        """Generate study artifacts grounded on document content."""
        from documents.intelligence.study_tools import (
            build_flashcards,
            enrich_education,
            start_quiz,
            build_simple_explanation,
            build_outline,
            build_exam_questions,
        )
        doc = await self.docs.get(user_id=user_id, doc_id=doc_id)
        text = doc.get("extracted_text") or ""
        edu = enrich_education(dict(doc.get("education_analysis") or {}), text)
        updates: dict[str, Any] = {"education_analysis": edu, "updated_at": _now()}
        out: dict[str, Any] = {"ok": True, "action": action, "education_analysis": edu}
        if action == "explain_simple":
            edu["simple_explanation"] = build_simple_explanation(edu, text)
            updates["education_analysis"] = edu
            out["result"] = edu["simple_explanation"]
        elif action == "summary_short":
            out["result"] = edu.get("summary_short") or (text[:280] if text else "")
        elif action == "summary_detailed":
            out["result"] = edu.get("summary_detailed") or (text[:1200] if text else "")
        elif action == "outline":
            edu["outline"] = build_outline(edu, text)
            updates["education_analysis"] = edu
            out["result"] = edu["outline"]
        elif action == "questions":
            out["result"] = edu.get("questions_for_review") or []
        elif action == "exam_questions":
            edu["exam_questions"] = build_exam_questions(edu)
            updates["education_analysis"] = edu
            out["result"] = edu["exam_questions"]
        elif action == "flashcards":
            cards = build_flashcards(edu, text)
            updates["flashcards"] = cards
            out["result"] = cards
            out["flashcards"] = cards
        elif action == "quiz_start":
            sess = start_quiz(doc_id, edu, text)
            updates["quiz_session"] = sess
            out["quiz_session"] = sess
            out["result"] = sess
        else:
            raise ValueError(f"azione studio non supportata: {action}")
        await self.db.documents.update_one({"id": doc_id, "user_id": user_id}, {"$set": updates})
        return out

    async def quiz_answer(self, *, user_id: str, doc_id: str, answer: str) -> dict:
        from documents.intelligence.study_tools import answer_quiz
        doc = await self.docs.get(user_id=user_id, doc_id=doc_id)
        sess = doc.get("quiz_session")
        if not sess:
            raise ValueError("Nessuna sessione Interrogami attiva")
        updated = answer_quiz(sess, answer, doc.get("extracted_text") or "")
        await self.db.documents.update_one(
            {"id": doc_id, "user_id": user_id},
            {"$set": {"quiz_session": updated, "updated_at": _now()}},
        )
        return {"ok": True, "quiz_session": updated}

    async def complete_admin_action(self, *, user_id: str, doc_id: str, index: int, completed: bool = True) -> dict:
        doc = await self.docs.get(user_id=user_id, doc_id=doc_id)
        actions = list(doc.get("generic_actions") or [])
        if index < 0 or index >= len(actions):
            raise LookupError("action_not_found")
        actions[index]["completed"] = bool(completed)
        admin = dict(doc.get("admin_analysis") or {})
        if completed and all(a.get("completed") for a in actions):
            admin["completed"] = True
        await self.db.documents.update_one(
            {"id": doc_id, "user_id": user_id},
            {"$set": {"generic_actions": actions, "admin_analysis": admin, "updated_at": _now()}},
        )
        return await self.get_analysis(user_id=user_id, doc_id=doc_id)

    async def add_admin_deadline_calendar(self, *, user_id: str, doc_id: str, sync_to_google: bool = False) -> dict:
        """Create calendar draft from admin due_date (requires confirmation path via sync flag)."""
        doc = await self.docs.get(user_id=user_id, doc_id=doc_id)
        admin = doc.get("admin_analysis") or {}
        due = admin.get("due_date")
        if not due:
            raise ValueError("Nessuna scadenza estratta")
        from documents.intelligence.analyzer import _parse_italian_datetime
        due_dt, _, amb = _parse_italian_datetime(str(due))
        if not due_dt or amb:
            raise ValueError("Scadenza ambigua: conferma manualmente la data")
        candidate = {
            "id": f"evc_admin_{doc_id[-8:]}",
            "source_document_id": doc_id,
            "title": (admin.get("subject") or "Scadenza documento")[:160],
            "description": (admin.get("simple_explanation") or "")[:400],
            "start_datetime": due_dt.isoformat(),
            "end_datetime": due_dt.isoformat(),
            "timezone": "Europe/Rome",
            "all_day": True,
            "status": "proposed",
            "confidence": float(admin.get("confidence") or 0.6),
            "priority": admin.get("priority") or "high",
            "urgency": admin.get("urgency") or "soon",
        }
        # Inject as candidate then confirm
        events = list(doc.get("event_candidates") or [])
        if not any(e.get("id") == candidate["id"] for e in events):
            events.append(candidate)
            await self.db.documents.update_one(
                {"id": doc_id, "user_id": user_id},
                {"$set": {"event_candidates": events, "updated_at": _now()}},
            )
        return await self.confirm_event(
            user_id=user_id,
            doc_id=doc_id,
            event_id=candidate["id"],
            sync_to_google=sync_to_google,
        )

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

    async def _calendar_auto_prefs(self, user: Optional[dict]) -> dict[str, Any]:
        prefs = ((user or {}).get("preferences") or {})
        enabled = bool(prefs.get("calendar_auto_add_enabled", False))
        try:
            threshold = float(prefs.get("calendar_auto_add_threshold", 0.90))
        except (TypeError, ValueError):
            threshold = 0.90
        threshold = max(0.5, min(1.0, threshold))
        return {"enabled": enabled, "threshold": threshold}

    async def get_document_prefs(self, user_id: str) -> dict[str, Any]:
        user = await self.db.users.find_one({"user_id": user_id}, {"_id": 0, "preferences": 1})
        prefs = (user or {}).get("preferences") or {}
        auto = await self._calendar_auto_prefs(user)
        return {
            "document_ai_analysis": prefs.get("document_ai_analysis", True) is not False,
            "calendar_auto_add_enabled": auto["enabled"],
            "calendar_auto_add_threshold": auto["threshold"],
        }

    async def set_document_prefs(self, user_id: str, body: dict) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        if "document_ai_analysis" in body:
            updates["preferences.document_ai_analysis"] = bool(body["document_ai_analysis"])
        if "calendar_auto_add_enabled" in body:
            updates["preferences.calendar_auto_add_enabled"] = bool(body["calendar_auto_add_enabled"])
        if "calendar_auto_add_threshold" in body:
            try:
                t = float(body["calendar_auto_add_threshold"])
            except (TypeError, ValueError):
                t = 0.90
            updates["preferences.calendar_auto_add_threshold"] = max(0.5, min(1.0, t))
        if updates:
            await self.db.users.update_one({"user_id": user_id}, {"$set": updates})
        return await self.get_document_prefs(user_id)

    async def _maybe_auto_add_calendar(
        self,
        *,
        user_id: str,
        doc_id: str,
        events: list,
        analysis: dict,
        user: Optional[dict],
    ) -> dict[str, Any]:
        """Safe default off. Auto-confirm + Google sync only for a single high-confidence event."""
        auto = await self._calendar_auto_prefs(user)
        if not auto["enabled"]:
            return {"attempted": False, "reason": "disabled"}
        proposed = [e for e in events if e.get("status") == "proposed"]
        if len(proposed) != 1:
            return {"attempted": False, "reason": "multiple_or_none"}
        if analysis.get("requires_review"):
            return {"attempted": False, "reason": "requires_review"}
        ev = proposed[0]
        conf = float(ev.get("confidence") or 0)
        # Spec: auto-add only when confidence > threshold (default 0.90 ⇒ 0.89 never auto-adds).
        if conf <= float(auto["threshold"]):
            return {"attempted": False, "reason": "low_confidence", "confidence": conf}
        if ev.get("ambiguous_date") or not ev.get("start_datetime"):
            return {"attempted": False, "reason": "ambiguous_or_missing_datetime"}
        critical_missing = [
            f for f in (ev.get("missing_fields") or [])
            if f in ("start_datetime", "date", "time", "title")
        ]
        if critical_missing:
            return {"attempted": False, "reason": "critical_missing", "missing": critical_missing}
        if not (ev.get("timezone") or "Europe/Rome"):
            return {"attempted": False, "reason": "invalid_timezone"}
        # Dedupe: already confirmed calendar draft for this candidate
        existing = await self.db.calendar_event_drafts.find_one({
            "user_id": user_id,
            "source_document_id": doc_id,
            "source_event_candidate_id": ev["id"],
            "status": {"$ne": "cancelled"},
        })
        if existing:
            return {"attempted": False, "reason": "already_exists", "calendar_event_id": existing.get("id")}
        try:
            res = await self.confirm_event(
                user_id=user_id,
                doc_id=doc_id,
                event_id=ev["id"],
                sync_to_google=True,
            )
            return {
                "attempted": True,
                "ok": True,
                "event_id": ev["id"],
                "calendar_event_id": (res.get("calendar_event") or {}).get("id"),
                "google_sync": res.get("google_sync"),
            }
        except Exception as e:
            logger.warning("auto_add calendar failed type=%s", type(e).__name__)
            return {"attempted": True, "ok": False, "error": type(e).__name__}

    async def hub(self, *, user_id: str, limit: int = 40) -> dict:
        """Documents home aggregates for V2 UI."""
        base = {"user_id": user_id, "deleted": {"$ne": True}, "archived": {"$ne": True}}
        proj = {"_id": 0, "extracted_text": 0}

        async def _fetch(extra: dict, lim: int = limit):
            cur = self.db.documents.find({**base, **extra}, proj).sort("updated_at", -1).limit(lim)
            return await cur.to_list(lim)

        recent = await _fetch({})
        needs_review = await _fetch({
            "pipeline_status": {"$in": [
                "needs_review", "awaiting_confirmation", "action_required", "failed",
            ]},
        })
        events_found = await _fetch({
            "event_candidates": {"$elemMatch": {"status": "proposed"}},
        })
        study = await _fetch({"analysis.macro_category": "education"})
        admin = await _fetch({
            "analysis.macro_category": {"$in": ["administrative", "financial", "receipt", "contract"]},
        })
        medical = await _fetch({"analysis.macro_category": "medical"})
        failed = await _fetch({"pipeline_status": "failed"})
        with_actions = await _fetch({
            "$or": [
                {"event_candidates": {"$elemMatch": {"status": "proposed"}}},
                {"generic_actions.0": {"$exists": True}},
            ],
        })

        def _card(d: dict) -> dict:
            a = d.get("analysis") or {}
            evs = d.get("event_candidates") or []
            open_ev = next((e for e in evs if e.get("status") == "proposed"), None)
            return {
                "id": d.get("id"),
                "display_title": d.get("display_title") or d.get("user_title") or a.get("suggested_title") or d.get("filename"),
                "original_filename": d.get("original_filename") or d.get("filename"),
                "macro_category": a.get("macro_category") or "generic",
                "subcategory": a.get("subcategory"),
                "short_description": a.get("short_description") or (a.get("summary") or "")[:160],
                "pipeline_status": d.get("pipeline_status"),
                "pipeline_status_label": d.get("pipeline_status_label"),
                "confidence": a.get("confidence"),
                "utility": _utility_label(a, evs, d.get("education_analysis")),
                "event_start": (open_ev or {}).get("start_datetime") or (evs[0].get("start_datetime") if evs else None),
                "event_location": (open_ev or {}).get("venue_name") or (open_ev or {}).get("city"),
                "open_actions": sum(1 for e in evs if e.get("status") == "proposed"),
                "updated_at": d.get("updated_at") or d.get("created_at"),
                "mime_type": d.get("mime_type"),
            }

        return {
            "recent": [_card(d) for d in recent],
            "needs_review": [_card(d) for d in needs_review],
            "events_found": [_card(d) for d in events_found],
            "study": [_card(d) for d in study],
            "administrative": [_card(d) for d in admin],
            "medical": [_card(d) for d in medical],
            "failed": [_card(d) for d in failed],
            "with_actions": [_card(d) for d in with_actions],
            "counts": {
                "recent": len(recent),
                "needs_review": len(needs_review),
                "events_found": len(events_found),
                "study": len(study),
                "administrative": len(admin),
                "medical": len(medical),
                "failed": len(failed),
                "with_actions": len(with_actions),
            },
            "prefs": await self.get_document_prefs(user_id),
        }

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
            ql = q.strip().lower()
            if ql in ("azioni aperte", "open actions"):
                query["generic_actions"] = {"$elemMatch": {"completed": {"$ne": True}}}
            elif ql in ("da verificare", "needs review", "needs_review"):
                query["pipeline_status"] = {
                    "$in": ["needs_review", "awaiting_confirmation", "action_required"],
                }
            else:
                # Multi-token: require all tokens via AND of regexes on text fields
                tokens = [t for t in re.split(r"\s+", q.strip()) if t]
                fields = [
                    "filename", "original_filename", "display_title", "user_title",
                    "analysis.suggested_title", "analysis.keywords", "analysis.summary",
                    "extracted_text", "analysis.macro_category", "analysis.subcategory",
                    "event_candidates.venue_name", "event_candidates.city",
                    "education_analysis.subject", "education_analysis.topic",
                    "education_analysis.key_concepts", "education_analysis.definitions",
                    "admin_analysis.subject", "admin_analysis.sender",
                    "admin_analysis.document_number",
                ]
                if len(tokens) <= 1:
                    rx = {"$regex": q, "$options": "i"}
                    query["$or"] = [{f: rx} for f in fields]
                else:
                    and_clauses = []
                    for tok in tokens:
                        rx = {"$regex": tok, "$options": "i"}
                        and_clauses.append({"$or": [{f: rx} for f in fields]})
                    query["$and"] = and_clauses
        cur = self.db.documents.find(query, {"_id": 0, "extracted_text": 0}).sort("created_at", -1).skip(offset).limit(limit)
        items = await cur.to_list(limit)
        total = await self.db.documents.count_documents(query)
        return {"items": items, "total": total, "limit": limit, "offset": offset}


def _apply_corrected_fields(
    fresh: Optional[dict],
    previous: Optional[dict],
    provenance: dict,
    *,
    prefix: str,
) -> Optional[dict]:
    """Re-apply user confirmed/corrected values after reanalyze; never overwrite them."""
    if fresh is None and previous is None:
        return None
    out = dict(fresh or previous or {})
    prev = previous or {}
    for key, meta in provenance.items():
        if not isinstance(meta, dict) or not str(key).startswith(prefix):
            continue
        if meta.get("status") not in ("confirmed", "corrected"):
            continue
        field = str(key)[len(prefix):]
        locked = meta.get("corrected") if meta.get("corrected") is not None else meta.get("confirmed")
        if field and locked is not None:
            out[field] = locked
        elif field in prev:
            out[field] = prev[field]
    # Preserve completed flag if user already completed
    if prev.get("completed") and "completed" not in {
        str(k)[len(prefix):] for k, m in provenance.items()
        if isinstance(m, dict) and str(k).startswith(prefix) and m.get("status") == "corrected"
    }:
        if prev.get("completed"):
            out["completed"] = True
    return out


def _merge_generic_actions(previous: list, fresh: list) -> list:
    """Keep completed flags for matching action titles across reanalyze."""
    if not previous:
        return list(fresh or [])
    if not fresh:
        return list(previous)
    prev_by_title = {str(a.get("title") or ""): a for a in previous}
    out = []
    for a in fresh:
        title = str(a.get("title") or "")
        merged = dict(a)
        old = prev_by_title.get(title)
        if old and old.get("completed"):
            merged["completed"] = True
        out.append(merged)
    return out


def _utility_label(analysis: dict, events: list, education: Optional[dict]) -> str:
    macro = analysis.get("macro_category") or "generic"
    proposed = [e for e in events if e.get("status") == "proposed"]
    confirmed = [e for e in events if e.get("status") == "confirmed"]
    if proposed:
        return f"{len(proposed)} evento/i da confermare"
    if confirmed:
        return "Evento in calendario"
    if macro == "education":
        subj = (education or {}).get("subject") or "Studio"
        return f"Materiale di studio · {subj}"
    if macro in ("administrative", "financial", "receipt", "contract"):
        return "Scadenze / azioni amministrative"
    if macro == "medical":
        return "Documento sanitario (sintesi discreta)"
    if analysis.get("summary"):
        return "Riepilogo disponibile"
    return "In elaborazione" if not analysis else "Informazioni estratte"
