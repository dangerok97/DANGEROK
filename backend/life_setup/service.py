"""Life Setup service — first-launch conversation orchestration (NOT a wizard)."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from ai_life_strategist.document_strategy import document_keys_from_upload
from ai_life_strategist.knowledge_gap import infer_domain_from_text, infer_known_from_text
from ai_life_strategist.policy import user_text_is_credential_dump
from ai_life_strategist.service import get_strategist_service
from life_setup.adapters_stubs import STUBS
from life_setup.models import LifeSetupSession, now_iso
from life_setup.profile_service import LifeProfileService
from life_setup.repository import LifeSetupRepository
from life_setup.sync import (
    emit_proactive_resume_if_needed,
    link_document_knowledge,
    sync_domain_goal,
    sync_domain_to_life_graph,
)

logger = logging.getLogger("ora.life_setup")

# Documents V2 ends in awaiting_confirmation whenever proposed event
# candidates exist (e.g. a bolletta due_date → deadline draft). That is a
# terminal analysis state for Life Experience: the Document Result UI is
# where the user confirms "Salva promemoria su ORA". action_required is the
# legacy alias of awaiting_confirmation.
DOC_PIPELINE_TERMINAL = (
    "completed",
    "needs_review",
    "failed",
    "awaiting_confirmation",
    "action_required",
)
DOC_PIPELINE_LABELS_IT = {
    "rogito": "il rogito",
    "contratto_locazione": "il contratto di locazione",
    "mutuo": "il contratto di mutuo",
    "bolletta": "la bolletta",
    "libretto": "il libretto di circolazione",
    "polizza_auto": "la polizza auto",
    "polizza_casa": "la polizza casa",
    "polizza": "la polizza",
    "prestito_auto": "il finanziamento auto",
    "piano_di_studi": "il piano di studi",
    "dispensa": "la dispensa",
    "calendario_esami": "il calendario esami",
}

_SERVICE: Optional["LifeSetupService"] = None


def life_setup_enabled() -> bool:
    raw = (os.environ.get("LIFE_SETUP_ENABLED") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def get_life_setup_service(db=None) -> "LifeSetupService":
    global _SERVICE
    if _SERVICE is None:
        if db is None:
            from deps import db as _db
            db = _db
        _SERVICE = LifeSetupService(db)
    return _SERVICE


class LifeSetupService:
    def __init__(self, db, *, life_graph=None, knowledge=None):
        self.db = db
        self.repo = LifeSetupRepository(db)
        self.profiles = LifeProfileService(db)
        self.life_graph = life_graph
        self.knowledge = knowledge

    async def ensure_indexes(self) -> None:
        await self.repo.ensure_indexes()

    def _disabled(self) -> Dict[str, Any]:
        return {
            "ok": False,
            "error": "life_setup_disabled",
            "enabled": False,
            "honesty": "LIFE_SETUP_ENABLED is off.",
        }

    def _terminal(self, status: str) -> bool:
        return status in ("completed", "skipped", "cancelled", "interrupted")

    async def status(self, user_id: str) -> Dict[str, Any]:
        if not life_setup_enabled():
            return {**self._disabled(), "should_show": False}
        sess = await self.repo.latest_session(user_id)
        profile = await self.profiles.get(user_id)
        # First launch eligible only if never completed/skipped/cancelled/interrupted
        should_show = False
        if sess is None:
            should_show = True
        elif sess.status == "active":
            should_show = True
        elif sess.status == "not_started":
            should_show = True
        # interrupted/skipped/completed → NEVER show wizard/module again
        return {
            "ok": True,
            "enabled": True,
            "should_show": should_show,
            "module_visible": False,  # never a permanent section
            "session": sess.public() if sess else None,
            "profile_summary": {
                "domains": list((profile.domains if profile else {}).keys()),
                "updated_at": profile.updated_at if profile else None,
            } if profile else None,
            "ui_mode": "natural_conversation",
            "wizard": False,
        }

    async def start(self, user_id: str, *, force: bool = False) -> Dict[str, Any]:
        if not life_setup_enabled():
            return self._disabled()
        existing = await self.repo.latest_session(user_id)
        if existing and self._terminal(existing.status) and not force:
            # Invisible forever — offer soft resume only via proactive, not module
            return {
                "ok": True,
                "already_finished": True,
                "should_show": False,
                "module_visible": False,
                "session": existing.public(),
                "resume_hint": get_strategist_service().resume_suggestion(),
                "wizard": False,
            }
        if existing and existing.status == "active" and not force:
            turn = existing.last_turn
            if not turn:
                turn = await self._plan_turn(existing)
                existing.last_turn = turn
                await self.repo.save_session(existing)
            pending_doc = await self._pending_document_resume(existing)
            return {
                "ok": True,
                "session": existing.public(),
                "turn": turn,
                "resumed": True,
                "pending_document": pending_doc,
                "wizard": False,
            }

        sess = LifeSetupSession(user_id=user_id, status="active", phase="greeting")
        # Optional CE origin=life_setup bridge
        try:
            from conversation_engine.service import ConversationEngineService, conversation_engine_enabled
            if conversation_engine_enabled():
                from deps import decisions, knowledge, life_graph
                ce = ConversationEngineService(
                    self.db, life_graph=life_graph, knowledge=knowledge, decisions=decisions,
                )
                started = await ce.start(
                    user_id,
                    text="Inizio conversazione Life Experience con ORA",
                    origin="life_setup",
                    context={
                        "life_setup": True,
                        "life_experience": True,
                        "ui_mode": "natural_conversation",
                    },
                    force_new=True,
                )
                if started.get("ok") and started.get("session"):
                    sess.conversation_session_id = started["session"].get("id")
                    sess.meta["conversation_bridge"] = True
        except Exception:
            logger.info("CE life_setup bridge skipped", exc_info=True)

        turn = await self._plan_turn(sess)
        sess.last_turn = turn
        sess.last_plan = (turn.get("plan") if turn else None)
        await self.repo.insert_session(sess)
        return {
            "ok": True,
            "session": sess.public(),
            "turn": turn,
            "wizard": False,
            "ui_mode": "natural_conversation",
            "philosophy": turn.get("text") if turn else None,
        }

    async def _plan_turn(self, sess: LifeSetupSession, *, ack: Optional[str] = None) -> Dict[str, Any]:
        strategist = get_strategist_service()
        strategist.db = self.db
        profile = await self.profiles.get(sess.user_id)
        facts = dict(sess.known_facts)
        if profile:
            facts.update(self.profiles.flat_known(profile))
        turn = await strategist.plan_turn(
            sess.user_id,
            known_facts=facts,
            asked_questions=sess.asked_questions,
            asked_keys=sess.asked_keys,
            refused_keys=sess.refused_keys,
            postponed_keys=sess.postponed_keys,
            linked_doc_types=sess.linked_doc_types,
            last_user_text=sess.meta.get("last_user_text"),
            session_phase=sess.phase,
            domains_touched=sess.domains_touched,
            force_fallback=not strategist.enabled() or bool(sess.meta.get("force_fallback")),
            ack=ack,
            last_bridge=sess.meta.get("last_bridge"),
            db=self.db,
        )
        used_bridge = (turn.get("meta") or {}).get("used_bridge")
        if used_bridge:
            sess.meta["last_bridge"] = used_bridge
        # Refresh active benefits after each plan (for Home after complete)
        try:
            from ai_life_strategist.benefit_engine import active_benefits

            known = {k for k, v in facts.items() if v not in (None, False, "", [])}
            sess.benefits_active = [b.code for b in active_benefits(known)]
        except Exception:
            pass
        if turn.get("plan"):
            sess.last_plan = turn["plan"]
            gap_key = (turn["plan"].get("meta") or {}).get("gap_key")
            q = turn["plan"].get("next_best_question")
            if q and q not in sess.asked_questions:
                # Record when presented
                pass
            if gap_key and gap_key not in sess.asked_keys and sess.phase != "greeting":
                pass
        if sess.phase == "greeting":
            sess.phase = "active"
        return turn

    async def answer(self, user_id: str, text: str, *, skip_domain: bool = False) -> Dict[str, Any]:
        if not life_setup_enabled():
            return self._disabled()
        sess = await self.repo.latest_session(user_id)
        if not sess or sess.status != "active":
            return {"ok": False, "error": "no_active_session"}

        if user_text_is_credential_dump(text):
            return {
                "ok": True,
                "privacy_refusal": True,
                "message": (
                    "Non memorizzo password, PIN, OTP o dati di carte. "
                    "Raccontami pure in modo generale, o carica un documento non sensibile."
                ),
                "session": sess.public(),
                "turn": sess.last_turn,
                "wizard": False,
            }

        ack: Optional[str] = None
        if skip_domain:
            domain = infer_domain_from_text(text) or (
                (sess.last_plan or {}).get("domain") if sess.last_plan else None
            )
            gap_key = (sess.last_plan or {}).get("meta", {}).get("gap_key") if sess.last_plan else None
            if gap_key and gap_key not in sess.refused_keys:
                sess.refused_keys.append(gap_key)
            if domain:
                sess.known_facts[f"{domain}._skipped"] = True
                if f"{domain}._skipped" not in sess.asked_keys:
                    sess.asked_keys.append(f"{domain}._skipped")
                if f"{domain}._skipped" not in sess.postponed_keys:
                    sess.postponed_keys.append(f"{domain}._skipped")
            ack = "Ok, saltiamo questo tema."
        else:
            sess.meta["last_user_text"] = text
            # Heuristic NLP → lower trust via FactSource "inferred" (confidence_manager)
            nlp_inferred = infer_known_from_text(text)
            soft_refuse = nlp_inferred.pop("_soft_refuse_signal", None)
            domain = infer_domain_from_text(text)
            if domain and domain not in sess.domains_touched:
                sess.domains_touched.append(domain)

            extraction_facts: Dict[str, Any] = {}
            extraction_pub: Dict[str, Any] = {}
            try:
                from semantic_engine.service import get_semantic_engine
                sem = get_semantic_engine()
                extraction = await sem.extract(
                    text,
                    intent=domain,
                    flow=domain or "generic",
                    use_gemini=False,
                )
                extraction_pub = extraction.public() if hasattr(extraction, "public") else {}
                for k, v in (getattr(extraction, "known_slots", None) or {}).items():
                    if v is not None:
                        extraction_facts[k] = v
                        if domain and "." not in k:
                            extraction_facts[f"{domain}.{k}"] = v
            except Exception:
                logger.info("semantic extract in life_setup skipped", exc_info=True)

            # Soft refuse / postpone from natural language (semantic refuse — no fact save)
            low = (text or "").lower()
            gap_key = (sess.last_plan.get("meta") or {}).get("gap_key") if sess.last_plan else None
            refuse_signals = (
                "non voglio",
                "preferisco non",
                "non te lo dico",
                "niente di questo",
                "non voglio dirlo",
                "preferisco non parlarne",
                "non voglio parlarne",
            )
            if gap_key and any(x in low for x in refuse_signals):
                if gap_key not in sess.refused_keys:
                    sess.refused_keys.append(gap_key)
                ack = "Va bene, rispetto la tua scelta — non insisto su questo punto."
                soft_refuse = True
            if soft_refuse:
                # No fake fact save on semantic refuse
                nlp_inferred = {}
                extraction_facts = {}
            if gap_key and any(x in low for x in ("più tardi", "dopo", "non ora", "rimandiamo")):
                if gap_key not in sess.postponed_keys:
                    sess.postponed_keys.append(gap_key)
                ack = "Ok, riprendiamo più avanti."

            user_answer_facts: Dict[str, Any] = {}
            # Direct answer to the open gap — always user authority (even if NLP also saw it)
            if gap_key and (text or "").strip() and not soft_refuse:
                user_answer_facts[str(gap_key)] = (text or "").strip()[:500]

            # First-person NLP from THIS user utterance is USER_STATED, not AI_INFERRED.
            # (Bug root: inferred+suggested made confirmed Life Setup facts look ambiguous.)
            volunteered_nlp: Dict[str, Any] = {}
            if not soft_refuse:
                volunteered_nlp = {
                    k: v
                    for k, v in (nlp_inferred or {}).items()
                    if not str(k).startswith("_")
                }

            merged = {**volunteered_nlp, **extraction_facts, **user_answer_facts}
            sess.known_facts.update(merged)
            if volunteered_nlp:
                await self.profiles.apply_facts(
                    user_id, volunteered_nlp, source="user_said", domain_hint=domain
                )
            if extraction_facts:
                await self.profiles.apply_facts(
                    user_id, extraction_facts, source="semantic_extract", domain_hint=domain
                )
            if user_answer_facts:
                await self.profiles.apply_facts(
                    user_id, user_answer_facts, source="user_said", domain_hint=domain
                )

            if sess.last_plan:
                q = sess.last_plan.get("next_best_question")
                if q and q not in sess.asked_questions:
                    sess.asked_questions.append(q)
                if gap_key and gap_key not in sess.asked_keys:
                    sess.asked_keys.append(gap_key)

            if domain:
                await self._sync_domain(sess, domain)
            if domain == "casa" and merged.get("casa.purchased") and not ack:
                ack = "Hai comprato casa — ottimo punto di partenza."

            # Free-text turns: do NOT override with rich build_acknowledgement.
            # Gemini acknowledgement (same StrategistPlan call) owns meaning-preserving
            # ack; render_conversational_turn falls back to SAFE "Capito." + question.
            # Keep system/refusal/skip/doc acks above as explicit overrides only.

            sess.meta["last_extraction"] = {
                "ok": bool(extraction_pub),
                "keys": list(merged.keys())[:20],
            }

        if ack:
            sess.meta["last_ack"] = ack

        turn = await self._plan_turn(sess, ack=ack)
        sess.last_turn = turn
        if turn.get("plan"):
            gap_key = (turn["plan"].get("meta") or {}).get("gap_key")
            q = turn["plan"].get("next_best_question")
            if q and q not in sess.asked_questions:
                sess.asked_questions.append(q)
            if gap_key and gap_key not in sess.asked_keys:
                sess.asked_keys.append(gap_key)
            sess.last_plan = turn["plan"]
            mlc_meta = (turn["plan"].get("meta") or {}).get("mlc")
            if mlc_meta:
                sess.meta["mlc_coverage"] = mlc_meta
            if turn.get("ui", {}).get("done") or (turn.get("plan") or {}).get("meta", {}).get("phase") == "wrap":
                sess.phase = "wrap"
        await self.repo.save_session(sess)
        profile = await self.profiles.get(user_id)
        return {
            "ok": True,
            "session": sess.public(),
            "turn": turn,
            "wizard": False,
            "profile": profile.public() if profile else None,
        }

    async def _sync_domain(self, sess: LifeSetupSession, domain: str) -> None:
        from deps import life_graph as lg, knowledge as kn

        life_graph = self.life_graph or lg
        knowledge = self.knowledge or kn
        profile = await self.profiles.get(sess.user_id)
        dom = profile.domains.get(domain) if profile else None
        node_id = await sync_domain_to_life_graph(
            life_graph,
            sess.user_id,
            domain,
            attributes={"facts": {k: o.value for k, o in (dom.objects if dom else {}).items()}},
            existing_node_id=dom.life_node_id if dom else None,
        )
        goal_id = await sync_domain_goal(
            self.db,
            sess.user_id,
            domain,
            brain_node_id=node_id,
            linked_documents=list(sess.linked_doc_ids),
            existing_goal_id=dom.goal_id if dom else None,
        )
        if profile and domain in profile.domains:
            if node_id:
                profile.domains[domain].life_node_id = node_id
            if goal_id:
                profile.domains[domain].goal_id = goal_id
            await self.profiles.repo.save_profile(profile)
            await link_document_knowledge(
                knowledge,
                sess.user_id,
                node_id,
                facts=self.profiles.flat_known(profile),
            )
        sess.meta.setdefault("sync", {})[domain] = {
            "life_node_id": node_id,
            "goal_id": goal_id,
        }

    async def upload_doc(self, user_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        if not life_setup_enabled():
            return self._disabled()
        sess = await self.repo.latest_session(user_id)
        if not sess or sess.status != "active":
            return {"ok": False, "error": "no_active_session"}

        doc_type = body.get("doc_type") or "documento"
        doc_id = body.get("document_id")
        synthetic = body.get("synthetic_text")
        filename = body.get("filename") or f"{doc_type}.txt"

        # Local/e2e force path: synthetic text → semantic extract without real storage
        extraction_keys: Dict[str, Any] = {}
        if synthetic:
            try:
                from semantic_engine.service import get_semantic_engine
                sem = get_semantic_engine()
                extraction = await sem.extract(synthetic, flow="generic", use_gemini=False)
                for k, v in (getattr(extraction, "known_slots", None) or {}).items():
                    if v is not None:
                        extraction_keys[k] = v
            except Exception:
                logger.info("synthetic extract failed", exc_info=True)
            # Mark document keys known
            for k in document_keys_from_upload(doc_type):
                extraction_keys[k] = True
            if not doc_id:
                doc_id = f"synth_{doc_type}_{sess.id}"
            # Persist a lightweight document stub for e2e (not claiming Documents V2 full pipeline)
            try:
                await self.db.documents.update_one(
                    {"id": doc_id, "user_id": user_id},
                    {
                        "$set": {
                            "id": doc_id,
                            "user_id": user_id,
                            "filename": filename,
                            "title": filename,
                            "doc_type": doc_type,
                            "source": "life_setup_synthetic",
                            "text_preview": (synthetic or "")[:500],
                            "updated_at": now_iso(),
                            "created_at": now_iso(),
                        }
                    },
                    upsert=True,
                )
            except Exception:
                pass

        if doc_id and doc_id not in sess.linked_doc_ids:
            sess.linked_doc_ids.append(doc_id)
        if doc_type and doc_type not in sess.linked_doc_types:
            sess.linked_doc_types.append(doc_type)

        for k in document_keys_from_upload(doc_type):
            sess.known_facts[k] = True
            extraction_keys.setdefault(k, True)

        domain = "casa" if doc_type in ("rogito", "bolletta", "polizza_casa") else (
            "auto" if doc_type in ("libretto", "polizza_auto") else (
                "studio" if doc_type == "dispensa" else "documenti"
            )
        )
        if domain not in sess.domains_touched:
            sess.domains_touched.append(domain)

        await self.profiles.apply_facts(
            user_id,
            extraction_keys,
            source="document_extract",
            domain_hint=domain,
        )
        # Link doc ids on domain
        profile = await self.profiles.get(user_id)
        if profile and domain in profile.domains and doc_id:
            if doc_id not in profile.domains[domain].linked_docs:
                profile.domains[domain].linked_docs.append(doc_id)
            await self.profiles.repo.save_profile(profile)

        await self._sync_domain(sess, domain)

        if sess.last_plan:
            q = sess.last_plan.get("next_best_question")
            if q and q not in sess.asked_questions:
                sess.asked_questions.append(q)
            gap_key = (sess.last_plan.get("meta") or {}).get("gap_key")
            if gap_key and gap_key not in sess.asked_keys:
                sess.asked_keys.append(gap_key)

        sess.meta["last_user_text"] = f"[upload:{doc_type}]"
        turn = await self._plan_turn(
            sess,
            ack="Ho ricevuto il documento. Lo uso per capire meglio il tuo contesto, senza farti ripetere tutto.",
        )
        sess.last_turn = turn
        if turn.get("plan"):
            sess.last_plan = turn["plan"]
            gap_key = (turn["plan"].get("meta") or {}).get("gap_key")
            q = turn["plan"].get("next_best_question")
            if q and q not in sess.asked_questions:
                sess.asked_questions.append(q)
            if gap_key and gap_key not in sess.asked_keys:
                sess.asked_keys.append(gap_key)
        await self.repo.save_session(sess)
        return {
            "ok": True,
            "session": sess.public(),
            "turn": turn,
            "document_id": doc_id,
            "doc_type": doc_type,
            "extracted_keys": list(extraction_keys.keys()),
            "wizard": False,
            "profile": (await self.profiles.get(user_id)).public() if await self.profiles.get(user_id) else None,
        }

    async def skip(self, user_id: str, *, domain: Optional[str] = None, postpone_all: bool = False) -> Dict[str, Any]:
        if not life_setup_enabled():
            return self._disabled()
        sess = await self.repo.latest_session(user_id)
        if not sess:
            return {"ok": False, "error": "no_session"}
        if postpone_all or not domain:
            sess.status = "skipped"
            sess.show_wizard_later = False
            sess.interrupted_at = now_iso()
            await self.repo.save_session(sess)
            sug = get_strategist_service().resume_suggestion()
            await emit_proactive_resume_if_needed(self.db, user_id, sug)
            sess.resume_suggestion_emitted = True
            await self.repo.save_session(sess)
            return {
                "ok": True,
                "session": sess.public(),
                "should_show": False,
                "module_visible": False,
                "resume_suggestion": sug,
                "wizard": False,
            }
        return await self.answer(user_id, domain or "", skip_domain=True)

    async def explain(self, user_id: str, plan: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        sess = await self.repo.latest_session(user_id)
        p = plan or (sess.last_plan if sess else None)
        if not p:
            return {"ok": False, "error": "no_plan"}
        return {"ok": True, "explain": get_strategist_service().explain_plan(p), "wizard": False}

    async def complete(self, user_id: str) -> Dict[str, Any]:
        if not life_setup_enabled():
            return self._disabled()
        sess = await self.repo.latest_session(user_id)
        if not sess:
            return {"ok": False, "error": "no_session"}
        sess.status = "completed"
        sess.completed_at = now_iso()
        sess.show_wizard_later = False
        sess.phase = "done"
        # Final sync for touched domains
        for d in sess.domains_touched:
            await self._sync_domain(sess, d)
        # Dismiss interrupt soft-resume suggestions — Home shows benefits now
        try:
            await self.db.proactive_suggestions.update_many(
                {
                    "user_id": user_id,
                    "source": {"$in": ["life_setup_interrupt", "life_experience_interrupt"]},
                    "status": "active",
                },
                {"$set": {"status": "dismissed", "dismissed": True, "updated_at": now_iso()}},
            )
        except Exception:
            pass
        # Close CE bridge session so Home resume is not «completa la guida»
        if sess.conversation_session_id:
            try:
                await self.db.conversation_sessions.update_one(
                    {"id": sess.conversation_session_id, "user_id": user_id},
                    {"$set": {"status": "completed", "updated_at": now_iso()}},
                )
                await self.db.action_sessions.update_many(
                    {"user_id": user_id, "conversation_session_id": sess.conversation_session_id},
                    {"$set": {"status": "completed", "updated_at": now_iso()}},
                )
            except Exception:
                pass
        # Persist active benefits on profile for Home / Proactive
        try:
            from ai_life_strategist.benefit_engine import active_benefits, home_benefit_cards

            profile = await self.profiles.get(user_id)
            facts = dict(sess.known_facts)
            if profile:
                facts.update(self.profiles.flat_known(profile))
            known = {k for k, v in facts.items() if v not in (None, False, "", [])}
            active = active_benefits(known)
            sess.benefits_active = [b.code for b in active]
            if profile:
                for b in active:
                    if b.domain not in profile.domains:
                        from life_setup.models import DomainProfile

                        profile.domains[b.domain] = DomainProfile(domain=b.domain)
                    profile.domains[b.domain].benefits_active = list(
                        {*(profile.domains[b.domain].benefits_active or []), b.code}
                    )
                await self.profiles.repo.save_profile(profile)
            sess.meta["home_benefits"] = [
                {"code": b.code, "home_signal": b.home_signal, "domain": b.domain}
                for b in home_benefit_cards(known)
            ]
        except Exception:
            logger.info("benefit persistence on complete skipped", exc_info=True)
        await self.repo.save_session(sess)
        return {
            "ok": True,
            "session": sess.public(),
            "should_show": False,
            "module_visible": False,
            "wizard": False,
            "benefits_active": sess.benefits_active,
            "profile": (await self.profiles.get(user_id)).public() if await self.profiles.get(user_id) else None,
        }

    async def cancel(self, user_id: str) -> Dict[str, Any]:
        """Interrupt/exit — do NOT show wizard later; emit ONE soft suggestion."""
        if not life_setup_enabled():
            return self._disabled()
        sess = await self.repo.latest_session(user_id)
        if not sess:
            return {"ok": False, "error": "no_session"}
        sess.status = "interrupted"
        sess.interrupted_at = now_iso()
        sess.show_wizard_later = False
        sug = get_strategist_service().resume_suggestion()
        await emit_proactive_resume_if_needed(self.db, user_id, sug)
        sess.resume_suggestion_emitted = True
        await self.repo.save_session(sess)
        return {
            "ok": True,
            "session": sess.public(),
            "should_show": False,
            "module_visible": False,
            "resume_suggestion": sug,
            "wizard": False,
            "message": sug.get("title"),
        }

    async def stub_adapter(self, name: str) -> Dict[str, Any]:
        stub = STUBS.get(name)
        if not stub:
            return {"ok": False, "error": "unknown_stub"}
        return await stub.fetch()

    # ------------------------------------------------------------------
    # Real Documents V2 attach / poll / consume / confirm / correct / reject
    #
    # Life Experience NEVER creates a second document pipeline. Upload,
    # MIME/size validation, storage, OCR/extraction, classification and the
    # base Gemini analysis all happen exclusively in Documents V2
    # (`documents.service.DocumentService` + `documents.intelligence`).
    # This layer only: links a real document_id to the conversation, polls
    # its pipeline status, runs ONE additional structured "life reasoning"
    # step on top of the existing analysis, maps the result into the Life
    # Profile, and re-runs the AI Reasoning Loop.
    # ------------------------------------------------------------------
    def _doc_label(self, doc_type: Optional[str]) -> str:
        return DOC_PIPELINE_LABELS_IT.get(doc_type or "", "il documento")

    async def _pending_document_resume(self, sess: LifeSetupSession) -> Optional[Dict[str, Any]]:
        """Never lose document_id / pipeline status across restarts or reopen."""
        if not sess.pending_document_id:
            return None
        from deps import get_document_service
        from documents.service import DocumentNotFound

        try:
            doc = await get_document_service().get(user_id=sess.user_id, doc_id=sess.pending_document_id)
        except DocumentNotFound:
            return None
        status = doc.get("pipeline_status") or "uploaded"
        label = self._doc_label(sess.pending_document_type)
        if status in DOC_PIPELINE_TERMINAL:
            message = f"Ho finito di leggere {label}. Vuoi vedere cosa ho capito?"
        else:
            message = f"Stavo ancora analizzando {label}… ({doc.get('pipeline_status_label') or status})"
        return {
            "document_id": sess.pending_document_id,
            "doc_type": sess.pending_document_type,
            "pipeline_status": status,
            "pipeline_status_label": doc.get("pipeline_status_label"),
            "ready_for_consume": status in DOC_PIPELINE_TERMINAL,
            "message": message,
        }

    async def attach_document(
        self, user_id: str, document_id: str, doc_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not life_setup_enabled():
            return self._disabled()
        sess = await self.repo.latest_session(user_id)
        if not sess or sess.status != "active":
            return {"ok": False, "error": "no_active_session"}

        from deps import get_document_service
        from documents.service import DocumentNotFound

        try:
            doc = await get_document_service().get(user_id=user_id, doc_id=document_id)
        except DocumentNotFound:
            return {"ok": False, "error": "document_not_found"}

        from documents.intelligence.life_reasoning import guess_document_type

        resolved_type = guess_document_type(doc, doc_type)
        if document_id not in sess.linked_doc_ids:
            sess.linked_doc_ids.append(document_id)
        if resolved_type and resolved_type not in sess.linked_doc_types:
            sess.linked_doc_types.append(resolved_type)
        sess.pending_document_id = document_id
        sess.pending_document_type = resolved_type
        sess.meta["last_user_text"] = f"[upload:{resolved_type}]"

        # Documents V2 auto-enqueues on upload; ensure it is queued in case
        # the client attaches an already-existing document (re-attach flow).
        if doc.get("pipeline_status") in (None, "uploaded"):
            try:
                from deps import get_intelligence_service
                await get_intelligence_service().mark_uploaded_and_queue(
                    user_id=user_id, doc_id=document_id,
                )
                doc["pipeline_status"] = "queued"
            except Exception:
                logger.exception("life_setup: failed to enqueue attached document")

        await self.repo.save_session(sess)
        label = self._doc_label(resolved_type)
        return {
            "ok": True,
            "session": sess.public(),
            "document_id": document_id,
            "doc_type": resolved_type,
            "pipeline_status": doc.get("pipeline_status"),
            "pipeline_status_label": doc.get("pipeline_status_label"),
            "message": f"Documento ricevuto. Sto leggendo {label}…",
            "wizard": False,
        }

    async def document_status(self, user_id: str, document_id: str) -> Dict[str, Any]:
        from deps import get_document_service
        from documents.service import DocumentNotFound

        try:
            doc = await get_document_service().get(user_id=user_id, doc_id=document_id)
        except DocumentNotFound:
            return {"ok": False, "error": "document_not_found"}
        status = doc.get("pipeline_status") or "uploaded"
        return {
            "ok": True,
            "document_id": document_id,
            "pipeline_status": status,
            "pipeline_status_label": doc.get("pipeline_status_label"),
            "ready_for_consume": status in DOC_PIPELINE_TERMINAL,
            "failed": status == "failed",
            "life_reasoning_ready": bool(doc.get("life_reasoning")),
            "requires_review": bool((doc.get("analysis") or {}).get("requires_review")),
        }

    async def consume_document(
        self, user_id: str, document_id: str, *, force: bool = False,
    ) -> Dict[str, Any]:
        if not life_setup_enabled():
            return self._disabled()
        sess = await self.repo.latest_session(user_id)
        if not sess or sess.status != "active":
            return {"ok": False, "error": "no_active_session"}

        from deps import get_document_service
        from documents.service import DocumentNotFound

        try:
            doc = await get_document_service().get(user_id=user_id, doc_id=document_id)
        except DocumentNotFound:
            return {"ok": False, "error": "document_not_found"}

        status = doc.get("pipeline_status") or "uploaded"
        if status not in DOC_PIPELINE_TERMINAL:
            return {
                "ok": False,
                "error": "pipeline_not_ready",
                "pipeline_status": status,
                "pipeline_status_label": doc.get("pipeline_status_label"),
            }
        if status == "failed" and not force:
            return {
                "ok": False,
                "error": "analysis_failed",
                "pipeline_status": status,
                "resumable": True,
            }

        from documents.intelligence.life_reasoning import run_life_document_reasoning
        from documents.intelligence.document_actions import build_document_actions
        from documents.intelligence.document_memory import persist_document_understanding
        from documents.intelligence.versions import coerce_analysis_revision
        from life_setup.document_mapping import map_document_reasoning
        from life_setup.cross_document import detect_conflicts, find_related_documents

        user_doc = await self.db.users.find_one({"user_id": user_id}, {"_id": 0, "preferences": 1})
        result = await run_life_document_reasoning(
            doc, user=user_doc, doc_type_hint=sess.pending_document_type, force=force,
            db=self.db,
        )
        reasoning = result["reasoning"]
        # Ensure analysis_version is a safe int (never leave a "2.0" string)
        reasoning["analysis_version"] = coerce_analysis_revision(reasoning.get("analysis_version")) or 1
        ai_actions = build_document_actions(doc=doc, reasoning=reasoning)
        await self.db.documents.update_one(
            {"id": document_id, "user_id": user_id},
            {"$set": {
                "life_reasoning": reasoning,
                "life_reasoning_telemetry": result.get("telemetry"),
                "life_actions": ai_actions,
                "updated_at": now_iso(),
            }},
        )
        # Best-effort Brain/Knowledge memory (user-isolated, no dupes)
        try:
            from deps import get_document_service
            knowledge = getattr(get_document_service(), "knowledge", None)
        except Exception:
            knowledge = None
        await persist_document_understanding(
            db=self.db, user_id=user_id, doc=doc, reasoning=reasoning, knowledge=knowledge,
        )

        # Life Object Engine shadow upsert (parallel; does not replace profile/goals)
        life_object_shadow: Dict[str, Any] = {"skipped": True}
        try:
            from life_objects.shadow import shadow_upsert_from_document
            life_object_shadow = await shadow_upsert_from_document(
                self.db,
                user_id=user_id,
                doc=doc,
                reasoning=reasoning,
                life_graph=self.life_graph,
            )
        except Exception as e:
            logger.info("life_object document shadow soft-fail: %s", type(e).__name__)
            life_object_shadow = {"ok": False, "soft_fail": True, "error": type(e).__name__}

        domain = reasoning.get("domain") or "documenti"
        mapped_fields = map_document_reasoning(reasoning)

        profile = await self.profiles.get(user_id)
        conflicts = detect_conflicts(
            profile, domain=domain, mapped_fields=mapped_fields, source_document_id=document_id,
        )
        conflict_keys = {c.key for c in conflicts}
        clean_fields = [mf for mf in mapped_fields if mf.key not in conflict_keys]

        await self.profiles.apply_mapped_fields(
            user_id,
            clean_fields,
            source_document_id=document_id,
            provider=reasoning.get("provider"),
            model=reasoning.get("model"),
            analysis_version=coerce_analysis_revision(reasoning.get("analysis_version")) or 1,
        )
        for c in conflicts:
            await self.profiles.add_pending_confirmation(user_id, domain, {
                "domain": c.domain, "key": c.key, "label": c.label,
                "existing_value": c.existing_value, "new_value": c.new_value,
                "new_confidence": c.new_confidence, "source_document_id": c.source_document_id,
                "kind": c.kind, "field": c.field, "created_at": now_iso(),
            })

        related_links = find_related_documents(
            profile, domain=domain, reasoning=reasoning, new_document_id=document_id,
        )
        if related_links:
            await self.profiles.add_related_documents(user_id, domain, related_links)

        if domain not in sess.domains_touched:
            sess.domains_touched.append(domain)
        doc_type = reasoning.get("document_type")
        if doc_type and doc_type not in sess.linked_doc_types:
            sess.linked_doc_types.append(doc_type)
        for k in document_keys_from_upload(doc_type or ""):
            sess.known_facts[k] = True
        if sess.pending_document_id == document_id:
            sess.pending_document_id = None
            sess.pending_document_type = None

        await self._sync_domain(sess, domain)

        # Benefit delta — before/after — for the immediate concrete-benefit message.
        from ai_life_strategist.benefit_engine import active_benefits

        profile = await self.profiles.get(user_id)
        facts = dict(sess.known_facts)
        if profile:
            facts.update(self.profiles.flat_known(profile))
        known = {k for k, v in facts.items() if v not in (None, False, "", [])}
        new_benefits = active_benefits(known, domain=domain)
        benefit_message = new_benefits[0].home_signal if new_benefits else None

        label = self._doc_label(doc_type)
        ack = f"Ho letto {label}. " + (
            benefit_message or "Ho ricavato le informazioni utili — senza farti inserire tutto a mano."
        )

        # Deadlines found in the SAME Documents V2 document analysis (never a
        # new pipeline) — surfaced as draft-only; confirm goes through the
        # existing Documents V2 event-candidate confirm endpoint.
        # Prefer AI / type-aware reminder titles when supplier/name is known.
        preferred_title = None
        for a in ai_actions:
            if a.get("action_type") in ("draft_calendar_event", "create_reminder") and a.get("title"):
                preferred_title = a["title"]
                break
        ts = reasoning.get("type_specific") or {}
        if not preferred_title and ts.get("supplier") and (reasoning.get("document_type") == "bolletta"):
            preferred_title = f"Pagamento bolletta {ts['supplier']}"
        if not preferred_title and ts.get("lender") and (reasoning.get("document_type") == "mutuo"):
            preferred_title = f"Pagamento rata mutuo {ts['lender']}"

        draft_events = []
        for ev in (doc.get("event_candidates") or []):
            if ev.get("status") != "proposed":
                continue
            title = preferred_title or ev.get("title")
            draft_events.append({
                "event_id": ev.get("id"),
                "title": title,
                "start_datetime": ev.get("start_datetime"),
                "confidence": ev.get("confidence"),
                "confirm_endpoint": f"/api/documents/{document_id}/events/{ev.get('id')}/confirm",
            })
            # Persist improved title on the candidate (best-effort, draft only)
            if preferred_title and preferred_title != ev.get("title"):
                try:
                    await self.db.documents.update_one(
                        {"id": document_id, "user_id": user_id, "event_candidates.id": ev.get("id")},
                        {"$set": {"event_candidates.$.title": preferred_title}},
                    )
                except Exception:
                    pass

        document_result = {
            "document_id": document_id,
            "doc_type": doc_type,
            "domain": domain,
            "cosa_ho_capito": reasoning.get("summary") or reasoning.get("purpose") or "",
            "reason_summary": reasoning.get("reason_summary"),
            "dati_trovati": [
                {"key": mf.key, "label": mf.label, "value": mf.value, "confidence": mf.confidence}
                for mf in clean_fields if mf.status == "extracted"
            ],
            "dati_da_verificare": [
                {"key": mf.key, "label": mf.label, "value": mf.value, "confidence": mf.confidence}
                for mf in clean_fields if mf.status == "suggested"
            ] + [
                {
                    "key": c.key, "label": c.label, "existing_value": c.existing_value,
                    "new_value": c.new_value, "kind": c.kind, "needs_confirmation": True,
                }
                for c in conflicts
            ],
            "ambiguities": reasoning.get("ambiguities") or [],
            "cosa_posso_fare": ai_actions or reasoning.get("recommended_actions") or [],
            "draft_events": draft_events,
            "related_documents": related_links and [
                {"document_id": l.document_id, "reason": l.reason} for l in related_links
            ] or [],
            "documento_originale": {
                "document_id": document_id,
                "filename": doc.get("filename"),
                "mime_type": doc.get("mime_type"),
                "download_url": f"/api/documents/{document_id}/download",
            },
            "ai_used": reasoning.get("ai_used"),
            "provider": reasoning.get("provider"),
            "model": reasoning.get("model"),
        }

        turn = await self._plan_turn(sess, ack=ack)
        sess.last_turn = turn
        if turn.get("plan"):
            sess.last_plan = turn["plan"]
            gap_key = (turn["plan"].get("meta") or {}).get("gap_key")
            q = turn["plan"].get("next_best_question")
            if q and q not in sess.asked_questions:
                sess.asked_questions.append(q)
            if gap_key and gap_key not in sess.asked_keys:
                sess.asked_keys.append(gap_key)
        await self.repo.save_session(sess)

        return {
            "ok": True,
            "session": sess.public(),
            "turn": turn,
            "document_result": document_result,
            "profile": profile.public() if profile else None,
            "life_object": life_object_shadow,
            "wizard": False,
        }

    async def confirm_field(self, user_id: str, domain: str, key: str) -> Dict[str, Any]:
        profile = await self.profiles.confirm_field(user_id, domain, key)
        sess = await self.repo.latest_session(user_id)
        turn = None
        if sess and sess.status == "active":
            turn = await self._plan_turn(sess)
            sess.last_turn = turn
            await self.repo.save_session(sess)
        return {"ok": True, "profile": profile.public(), "turn": turn, "wizard": False}

    async def correct_field(self, user_id: str, domain: str, key: str, value: Any) -> Dict[str, Any]:
        profile = await self.profiles.correct_fact(user_id, domain, key, value)
        sess = await self.repo.latest_session(user_id)
        turn = None
        if sess and sess.status == "active":
            turn = await self._plan_turn(sess)
            sess.last_turn = turn
            await self.repo.save_session(sess)
        return {"ok": True, "profile": profile.public(), "turn": turn, "wizard": False}

    async def reject_field(self, user_id: str, domain: str, key: str) -> Dict[str, Any]:
        profile = await self.profiles.reject_field(user_id, domain, key)
        sess = await self.repo.latest_session(user_id)
        turn = None
        if sess and sess.status == "active":
            turn = await self._plan_turn(sess)
            sess.last_turn = turn
            await self.repo.save_session(sess)
        return {"ok": True, "profile": profile.public(), "turn": turn, "wizard": False}

    async def resolve_confirmation(
        self, user_id: str, domain: str, key: str, resolution: str,
    ) -> Dict[str, Any]:
        profile = await self.profiles.resolve_pending_confirmation(user_id, domain, key, resolution)
        return {"ok": True, "profile": profile.public(), "wizard": False}

    async def retry_document(self, user_id: str, document_id: str) -> Dict[str, Any]:
        from deps import get_document_service, get_intelligence_service
        from documents.service import DocumentNotFound

        try:
            await get_document_service().get(user_id=user_id, doc_id=document_id)
        except DocumentNotFound:
            return {"ok": False, "error": "document_not_found"}
        await self.db.documents.update_one(
            {"id": document_id, "user_id": user_id},
            {"$unset": {"life_reasoning": "", "life_reasoning_telemetry": ""}},
        )
        await get_intelligence_service().mark_uploaded_and_queue(user_id=user_id, doc_id=document_id)
        sess = await self.repo.latest_session(user_id)
        if sess:
            sess.pending_document_id = document_id
            await self.repo.save_session(sess)
        return {"ok": True, "pipeline_status": "queued", "wizard": False}

    async def detach_document(self, user_id: str, document_id: str) -> Dict[str, Any]:
        """Remove the document from Life Experience knowledge — the file and
        its Documents V2 record are NEVER deleted by this call."""
        sess = await self.repo.latest_session(user_id)
        if sess:
            sess.linked_doc_ids = [d for d in sess.linked_doc_ids if d != document_id]
            if sess.pending_document_id == document_id:
                sess.pending_document_id = None
                sess.pending_document_type = None
            await self.repo.save_session(sess)
        profile = await self.profiles.get(user_id)
        if profile:
            for dom in profile.domains.values():
                dom.linked_docs = [d for d in dom.linked_docs if d != document_id]
                for obj in dom.objects.values():
                    if document_id in obj.linked_doc_ids:
                        obj.linked_doc_ids = [d for d in obj.linked_doc_ids if d != document_id]
                dom.related_documents = [
                    r for r in dom.related_documents if r.get("document_id") != document_id
                ]
            await self.profiles.repo.save_profile(profile)
        return {"ok": True, "document_id": document_id, "wizard": False}

    async def reverse_geocode(self, user_id: str, lat: float, lon: float) -> Dict[str, Any]:
        """City label only — never store precise coordinates on the session/profile."""
        _ = user_id
        from action_engine.travel.maps import nominatim_reverse_city
        from ai_life_strategist.conversational_voice import location_confirm_prompt

        city = await nominatim_reverse_city(lat, lon)
        if not city:
            return {
                "ok": False,
                "error": "geocode_unavailable",
                "message": "Non riesco a capire la città da qui — puoi scriverla tu?",
                "wizard": False,
            }
        return {
            "ok": True,
            "city": city,
            "confirm_prompt": location_confirm_prompt(city),
            "wizard": False,
            # Honesty: coarse city only; coords are not persisted
            "persists_coordinates": False,
        }

    async def confirm_location(
        self, user_id: str, city: str, *, confirmed: bool
    ) -> Dict[str, Any]:
        """
        On confirm → save city as life_places home via normal fact path.
        On reject → replan with a normal city question (no place saved).
        """
        if not life_setup_enabled():
            return self._disabled()
        sess = await self.repo.latest_session(user_id)
        if not sess or sess.status != "active":
            return {"ok": False, "error": "no_active_session", "wizard": False}

        city_clean = (city or "").strip()[:80]
        if confirmed and city_clean:
            facts = {
                "mlc.life_places.home": city_clean,
                "casa.citta": city_clean,
            }
            sess.known_facts.update(facts)
            await self.profiles.apply_facts(
                user_id, facts, source="user_confirmed", domain_hint="casa"
            )
            gap_key = (sess.last_plan or {}).get("meta", {}).get("gap_key") if sess.last_plan else None
            if gap_key and gap_key not in sess.asked_keys:
                sess.asked_keys.append(gap_key)
            ack = f"Ok, segno {city_clean} come luogo principale."
            turn = await self._plan_turn(sess, ack=ack)
        else:
            ack = "Nessun problema — in quale città vivi principalmente?"
            # Keep gap open; just replan with ack as the city ask
            turn = await self._plan_turn(sess, ack=ack)
            # Ensure text still asks for city if planner moved on oddly
            if turn and not (turn.get("question") or "").strip():
                turn = dict(turn)
                turn["text"] = ack
                turn["question"] = "Dove vivi principalmente in questo periodo? Basta la città."

        sess.last_turn = turn
        if turn.get("plan"):
            sess.last_plan = turn["plan"]
            if turn.get("ui", {}).get("done"):
                sess.phase = "wrap"
        sess.meta["last_ack"] = ack
        # Never store lat/lon
        sess.meta.pop("pending_lat", None)
        sess.meta.pop("pending_lon", None)
        await self.repo.save_session(sess)
        profile = await self.profiles.get(user_id)
        return {
            "ok": True,
            "session": sess.public(),
            "turn": turn,
            "wizard": False,
            "profile": profile.public() if profile else None,
            "location_confirmed": bool(confirmed and city_clean),
        }
