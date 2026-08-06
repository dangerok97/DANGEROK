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
            return {
                "ok": True,
                "session": existing.public(),
                "turn": turn,
                "resumed": True,
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
            db=self.db,
        )
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
            inferred = infer_known_from_text(text)
            domain = infer_domain_from_text(text)
            if domain and domain not in sess.domains_touched:
                sess.domains_touched.append(domain)

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
                        inferred[k] = v
                        if domain and "." not in k:
                            inferred[f"{domain}.{k}"] = v
            except Exception:
                logger.info("semantic extract in life_setup skipped", exc_info=True)

            # Soft refuse / postpone from natural language
            low = (text or "").lower()
            gap_key = (sess.last_plan.get("meta") or {}).get("gap_key") if sess.last_plan else None
            if gap_key and any(
                x in low for x in ("non voglio", "preferisco non", "non te lo dico", "niente di questo")
            ):
                if gap_key not in sess.refused_keys:
                    sess.refused_keys.append(gap_key)
                ack = "Va bene, non insisto su questo punto."
            if gap_key and any(x in low for x in ("più tardi", "dopo", "non ora", "rimandiamo")):
                if gap_key not in sess.postponed_keys:
                    sess.postponed_keys.append(gap_key)
                ack = "Ok, riprendiamo più avanti."

            # Drop internal soft signals from persistence
            inferred.pop("_soft_refuse_signal", None)
            sess.known_facts.update(inferred)
            await self.profiles.apply_facts(
                user_id,
                inferred,
                source="semantic_extract" if extraction_pub else "user_said",
                domain_hint=domain,
            )

            if sess.last_plan:
                q = sess.last_plan.get("next_best_question")
                if q and q not in sess.asked_questions:
                    sess.asked_questions.append(q)
                if gap_key and gap_key not in sess.asked_keys:
                    sess.asked_keys.append(gap_key)

            if domain:
                await self._sync_domain(sess, domain)
            if domain == "casa" and inferred.get("casa.purchased") and not ack:
                ack = "Hai comprato casa — ottimo punto di partenza."

            sess.meta["last_extraction"] = {
                "ok": bool(extraction_pub),
                "keys": list(inferred.keys())[:20],
            }

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
            ack=f"Documento «{doc_type}» ricevuto. Aggiorno il tuo contesto.",
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
