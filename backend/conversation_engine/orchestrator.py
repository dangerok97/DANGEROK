"""Orchestrator — Intent → Goal (shadow) → Action Engine → artifact tracking.

Conversation Engine never duplicates study/travel domain logic.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from conversation_engine.adapters.action import ActionAdapter
from conversation_engine.adapters.brain import BrainAdapter
from conversation_engine.adapters.calendar import CalendarAdapter
from conversation_engine.adapters.documents import DocumentsAdapter
from conversation_engine.adapters.goal import GoalAdapter
from conversation_engine.adapters.intent import IntentAdapter
from conversation_engine.adapters.maps import MapsAdapter
from conversation_engine.adapters.projects import ProjectsAdapter
from conversation_engine.adapters.stubs import StubOriginAdapter
from conversation_engine.adapters.suggestions import SuggestionsAdapter
from conversation_engine.memory import entities_to_slots, merge_slots, slots_from_ae_answers
from conversation_engine.models import ConversationSession, new_resume_token
from conversation_engine.repository import ConversationRepository

logger = logging.getLogger("ora.conversation_engine")


def synthetic_prompt_for_intent(intent_name: str, entities: Dict[str, Any]) -> Optional[str]:
    """Short ORA line — never a ChatGPT essay."""
    if intent_name == "travel":
        if entities.get("destination") or entities.get("travel") or entities.get("place"):
            return "Perfetto. Organizziamo il viaggio."
        if entities.get("departure_date") or entities.get("start_date"):
            return "Perfetto. Dove andrai?"
        return "Perfetto. Organizziamo il viaggio."
    if intent_name == "study":
        subj = entities.get("subject")
        if subj:
            return f"Ok — prepariamo {subj}."
        return "Ok. Quale esame vuoi preparare?"
    if intent_name == "clarify":
        return "Dimmi in una frase cosa vuoi organizzare."
    return None


def build_summary(session: ConversationSession) -> str:
    intent = (session.intent or {}).get("intent") if session.intent else None
    if session.status == "paused":
        if intent == "travel":
            return "Stavamo organizzando la tua vacanza."
        if intent == "study":
            return "Stavamo preparando il tuo esame."
        return "Hai interrotto una guida ORA."
    if session.status == "completed":
        if intent == "travel":
            return "Viaggio organizzato con ORA."
        if intent == "study":
            return "Piano di studio creato con ORA."
        return "Guida ORA completata."
    if intent == "travel":
        return "Stiamo organizzando la tua vacanza."
    if intent == "study":
        return "Stiamo preparando il tuo esame."
    if session.input:
        t = session.input.strip()
        return f"In corso: {t[:60]}{'…' if len(t) > 60 else ''}"
    return "Collaborazione ORA in corso."


class ConversationOrchestrator:
    def __init__(
        self,
        db,
        *,
        life_graph=None,
        knowledge=None,
        decisions=None,
    ):
        self.db = db
        self.repo = ConversationRepository(db)
        self.intent = IntentAdapter()
        self.goal = GoalAdapter(db, life_graph=life_graph, knowledge=knowledge)
        self.action = ActionAdapter(
            db, life_graph=life_graph, knowledge=knowledge, decisions=decisions,
        )
        self.projects = ProjectsAdapter(db)
        self.documents = DocumentsAdapter(db)
        self.calendar = CalendarAdapter(db)
        self.brain = BrainAdapter(db, knowledge=knowledge)
        self.maps = MapsAdapter()
        self.suggestions = SuggestionsAdapter(db)

    async def start(
        self,
        user_id: str,
        *,
        text: Optional[str],
        origin: str = "text",
        voice_meta: Optional[Dict[str, Any]] = None,
        suggestion_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        force_new: bool = False,
    ) -> Dict[str, Any]:
        # Stub origins — honest no-op structure
        if StubOriginAdapter.is_stub(origin):
            sess = ConversationSession(
                user_id=user_id,
                origin=origin,  # type: ignore[arg-type]
                input=text,
                status="cancelled",
                summary=StubOriginAdapter.acknowledge(origin)["honesty"],
                meta={"stub_origin": True, "ui_mode": "none"},
            )
            sess.append_history(role="system", kind="status", text="stub_origin_not_implemented")
            await self.repo.insert(sess)
            return {
                "ok": True,
                "session": sess.public(include_history=True),
                "stub": True,
                "honesty": StubOriginAdapter.acknowledge(origin)["honesty"],
                "route": None,
            }

        # Proactive / notifications: resume existing if linked
        if suggestion_id and not force_new:
            existing = await self.repo.find_resumable_for_suggestion(user_id, suggestion_id)
            if existing:
                return await self.resume_session(user_id, existing)

        ctx = dict(context or {})
        if suggestion_id and "suggestion" not in ctx:
            sug = await self.suggestions.get_suggestion(user_id, suggestion_id)
            if sug:
                ctx["proactive"] = self.suggestions.conversational_context(sug)
                if not text:
                    text = sug.get("title") or sug.get("description")

        text = (text or "").strip()
        if not text and not ctx.get("proactive"):
            return {"ok": False, "error": "text_required"}

        # Classify
        intent_result = await self.intent.classify(
            text or (ctx.get("proactive") or {}).get("title") or "",
            source_type=f"conversation:{origin}",
            meta={"origin": origin, "suggestion_id": suggestion_id},
        )
        intent_dict = IntentAdapter.to_dict(intent_result)
        entities = intent_dict.get("entities") or {}
        if not isinstance(entities, dict):
            # IntentEntities model dump may nest
            entities = entities if isinstance(entities, dict) else {}
        # Normalize entities if pydantic nested
        if hasattr(intent_result, "entities") and hasattr(intent_result.entities, "as_dict"):
            entities = intent_result.entities.as_dict()
            intent_dict["entities"] = entities

        # === Semantic Extraction → Gap Analyzer (before Action Engine) ===
        extraction_pub: Dict[str, Any] = {}
        gap_pub: Dict[str, Any] = {}
        try:
            from semantic_engine.service import get_semantic_engine
            sem = get_semantic_engine()
            extraction = await sem.extract(
                text or "",
                intent=intent_dict.get("intent"),
                flow=intent_dict.get("intent"),
                confirmed_entities=ctx.get("confirmed_entities"),
                prior_entities=ctx.get("prior_entities") or ctx.get("known_slots"),
                context={"proactive": ctx.get("proactive")},
                use_gemini=False,  # deterministic first; Gemini optional via API/flag
            )
            extraction_pub = extraction.public()
            gaps_res = await sem.gaps(
                flow=extraction.flow_hint or intent_dict.get("intent"),
                intent=intent_dict.get("intent"),
                entities=extraction.known_slots,
                confirmed_entities=ctx.get("confirmed_entities"),
                use_gemini=False,
            )
            gap_pub = (gaps_res.get("gaps") or {}) if isinstance(gaps_res, dict) else {}
            # Merge semantic known into intent entities for AE
            for k, v in (extraction.known_slots or {}).items():
                if v is not None and k not in entities:
                    entities[k] = v
                elif v is not None and entities.get(k) in (None, "", []):
                    entities[k] = v
            intent_dict["entities"] = entities
            # If Intent asked to clarify but Semantic already has a clear travel/study domain, prefer it
            flow_hint = (extraction.flow_hint or "").lower()
            intent_name = (intent_dict.get("intent") or "").lower()
            needs_clarify = bool(intent_dict.get("needs_clarify")) or intent_name in ("clarify", "generic", "")
            strong_travel = flow_hint in ("travel", "vacation") and (
                entities.get("destination") or entities.get("departure_date") or entities.get("period")
            )
            strong_study = flow_hint in ("study", "exam_preparation") and entities.get("subject")
            if needs_clarify and (strong_travel or strong_study):
                intent_dict["intent"] = "travel" if strong_travel else "study"
                intent_dict["needs_clarify"] = False
                intent_dict["confidence"] = max(float(intent_dict.get("confidence") or 0), 0.86)
                intent_dict["reason"] = "semantic_flow_override"
        except Exception as e:
            logger.info("semantic extraction soft-fail: %s", type(e).__name__)

        known = merge_slots(
            entities_to_slots(entities),
            entities_to_slots(extraction_pub.get("entities") if extraction_pub else None),
            extraction_pub.get("known_slots") if extraction_pub else None,
            ctx.get("known_slots"),
        )

        # Dynamic first question from Gap Analyzer — never static "Quando parti e quando torni?"
        dynamic_q = gap_pub.get("next_best_question")
        if dynamic_q and "quando parti e quando torni" in dynamic_q.lower():
            # Hard guard — should never happen with travel schema
            dynamic_q = "Dove andrai?" if known.get("departure_date") else "Quando parti?"

        sess = ConversationSession(
            user_id=user_id,
            origin=origin,  # type: ignore[arg-type]
            input=text or None,
            intent=intent_dict,
            status="running_action",
            voice_meta=voice_meta,
            suggestion_id=suggestion_id,
            known_slots=known,
            extracted_entities=extraction_pub.get("entities") or {},
            confirmed_entities=dict(ctx.get("confirmed_entities") or {}),
            missing_slots=list(gap_pub.get("missing_required") or extraction_pub.get("missing_slots") or []),
            ambiguous_slots=list(gap_pub.get("ambiguous_slots") or extraction_pub.get("ambiguous_slots") or []),
            extraction_version=extraction_pub.get("extraction_version"),
            last_extraction_at=extraction_pub.get("extracted_at"),
            meta={
                "ui_mode": "action_engine",
                "proactive_context": ctx.get("proactive"),
                "synthetic_prompt": synthetic_prompt_for_intent(
                    intent_dict.get("intent") or "", entities,
                ),
                "gap": gap_pub,
                "reason_summary": extraction_pub.get("reason_summary") or gap_pub.get("reason_summary"),
            },
        )
        sess.append_history(role="user", kind="start", text=text)
        sess.append_history(
            role="ora",
            kind="intent",
            text=intent_dict.get("intent"),
            meta={"confidence": intent_dict.get("confidence")},
        )
        if extraction_pub:
            sess.append_history(
                role="ora",
                kind="extraction",
                text=extraction_pub.get("reason_summary"),
                meta={"known": list(known.keys())[:12], "next_slot": gap_pub.get("next_slot")},
            )

        # Open Action Engine flow (domain) — receives structured entities + gap next question
        ae_res = await self.action.open_from_text(
            user_id,
            text=text or sess.meta.get("synthetic_prompt") or "Parla con ORA",
            intent=intent_dict,
            origin=origin,
            conversation_session_id=sess.id,
            known_slots=known,
            gap=gap_pub,
            force_new=force_new,
        )
        ae = ae_res.get("session") or {}
        action_id = ae.get("id")
        if not action_id:
            sess.status = "cancelled"
            sess.summary = "Impossibile aprire la guida Action Engine."
            await self.repo.insert(sess)
            return {"ok": False, "error": "action_open_failed", "session": sess.public()}

        sess.action_session_id = action_id
        sess.add_artifact("action_session", action_id, label=ae.get("title"))
        sess.meta["action_flow"] = ae.get("flow")
        sess.meta["route"] = f"/action/{action_id}"
        turn = ae.get("current_turn") or {}
        sess.current_step = turn.get("id")
        first_q = turn.get("question") or dynamic_q
        # Prefer Gap Analyzer question when AE still shows the banned combined-dates prompt
        if first_q and "quando parti e quando torni" in str(first_q).lower():
            first_q = dynamic_q or ("Dove andrai?" if known.get("departure_date") else "Quando parti?")
            if turn:
                turn = {**turn, "question": first_q}
        if first_q:
            sess.meta["first_question"] = first_q
            sess.append_history(
                role="ora",
                kind="question",
                text=first_q,
                step_id=turn.get("id") if turn else gap_pub.get("next_slot"),
            )
        sess.status = "waiting_user"
        sess.known_slots = merge_slots(known, slots_from_ae_answers(ae.get("answers")))

        # Shadow Goal
        goal_res = await self.goal.shadow_from_intent(
            user_id,
            text=text or ae.get("title") or "Obiettivo",
            intent=intent_dict,
            action_session_id=action_id,
            conversation_session_id=sess.id,
        )
        if goal_res.get("ok") and not goal_res.get("skipped"):
            goal = goal_res.get("goal") if isinstance(goal_res.get("goal"), dict) else {}
            gid = goal_res.get("goal_id") or (goal or {}).get("id")
            if gid:
                sess.goal_id = gid
                sess.add_artifact("goal", gid, label=(goal or {}).get("title"))
                sess.append_history(role="system", kind="goal", text=gid)

        # Project link if AE already created one (via Projects adapter)
        for pref in self.projects.refs_from_ae_session(ae):
            if pref["kind"] == "project":
                sess.project_id = pref["id"]
            sess.add_artifact(pref["kind"], pref["id"], label=pref.get("label"))

        self._sync_artifacts_from_ae(sess, ae)
        sess.summary = build_summary(sess)
        await self.repo.insert(sess)

        return {
            "ok": True,
            "session": sess.public(include_history=True),
            "action_session": ae,
            "route": sess.meta.get("route"),
            "first_question": sess.meta.get("first_question"),
            "synthetic_prompt": sess.meta.get("synthetic_prompt"),
            "ui_mode": "action_engine",
            "resumed": bool(ae_res.get("resumed")),
        }

    async def message(
        self,
        user_id: str,
        session_id: str,
        *,
        text: Optional[str] = None,
        option_id: Optional[str] = None,
        value: Any = None,
        skip: bool = False,
    ) -> Dict[str, Any]:
        sess = await self.repo.get(user_id, session_id)
        if not sess:
            return {"ok": False, "error": "not_found"}
        if sess.status in ("completed", "cancelled"):
            return {"ok": False, "error": "session_closed", "session": sess.public()}
        if not sess.action_session_id:
            return {"ok": False, "error": "no_action_session", "session": sess.public()}

        sess.append_history(
            role="user",
            kind="answer",
            text=text or option_id or (str(value) if value is not None else None),
            step_id=sess.current_step,
        )
        sess.status = "running_action"

        # Re-run Semantic on the answer for the current slot — no free-text flow selection
        if text and sess.current_step:
            try:
                from semantic_engine.service import get_semantic_engine
                from semantic_engine.context_merge import apply_confirmation
                from semantic_engine.normalizer import normalize_entity, entities_to_known_slots
                sem = get_semantic_engine()
                slot = sess.current_step
                # Map AE step ids to semantic slots
                slot_map = {
                    "destination": "destination",
                    "departure_date": "departure_date",
                    "return_date": "return_date",
                    "period": "period",
                    "transport": "transport",
                    "lodging": "lodging",
                    "confirm_subject": "subject",
                    "exam_date": "exam_date",
                }
                sem_slot = slot_map.get(slot, slot)
                patched = sem.confirm_entity(
                    sess.extracted_entities or {},
                    sem_slot,
                    text or value,
                )
                sess.extracted_entities = patched.get("entities") or sess.extracted_entities
                sess.confirmed_entities = {
                    **(sess.confirmed_entities or {}),
                    sem_slot: text or value,
                }
                sess.known_slots = merge_slots(
                    sess.known_slots,
                    patched.get("known_slots"),
                    {sem_slot: text or value},
                )
                gaps_res = await sem.gaps(
                    flow=(sess.intent or {}).get("intent"),
                    intent=(sess.intent or {}).get("intent"),
                    entities=sess.known_slots,
                    confirmed_entities=sess.confirmed_entities,
                    use_gemini=False,
                )
                gap_pub = gaps_res.get("gaps") or {}
                sess.missing_slots = list(gap_pub.get("missing_required") or [])
                sess.ambiguous_slots = list(gap_pub.get("ambiguous_slots") or [])
                sess.meta["gap"] = gap_pub
            except Exception as e:
                logger.info("semantic answer merge soft-fail: %s", type(e).__name__)

        await self.repo.replace(sess)

        ae_res = await self.action.answer(
            user_id,
            sess.action_session_id,
            option_id=option_id,
            value=value,
            text=text,
            skip=skip,
        )
        ae = ae_res.get("session") or {}
        return await self._after_ae(sess, ae, ae_res)

    async def continue_session(self, user_id: str, session_id: str, *, note: Optional[str] = None) -> Dict[str, Any]:
        """Refresh AE state and return next question — no multi-question dump."""
        sess = await self.repo.get(user_id, session_id)
        if not sess:
            return {"ok": False, "error": "not_found"}
        if not sess.action_session_id:
            return {"ok": False, "error": "no_action_session", "session": sess.public()}
        ae = await self.action.get(user_id, sess.action_session_id)
        if not ae:
            return {"ok": False, "error": "action_not_found", "session": sess.public()}
        if note:
            sess.append_history(role="system", kind="continue", text=note)
        return await self._after_ae(sess, ae, {"ok": True, "session": ae})

    async def cancel(
        self, user_id: str, session_id: str, *, reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        sess = await self.repo.get(user_id, session_id)
        if not sess:
            return {"ok": False, "error": "not_found"}
        if sess.action_session_id:
            try:
                await self.action.cancel(user_id, sess.action_session_id)
            except Exception:
                logger.info("AE cancel soft-fail for %s", sess.action_session_id)
        sess.status = "cancelled"
        sess.append_history(role="system", kind="cancel", text=reason)
        sess.summary = build_summary(sess)
        await self.repo.replace(sess)
        return {"ok": True, "session": sess.public(include_history=True)}

    async def pause(self, user_id: str, session_id: str) -> Dict[str, Any]:
        sess = await self.repo.get(user_id, session_id)
        if not sess:
            return {"ok": False, "error": "not_found"}
        sess.status = "paused"
        sess.resume_token = new_resume_token()
        sess.summary = build_summary(sess)
        sess.append_history(role="system", kind="status", text="paused")
        await self.repo.replace(sess)
        return {"ok": True, "session": sess.public(), "resume_token": sess.resume_token}

    async def resume(
        self,
        user_id: str,
        *,
        session_id: Optional[str] = None,
        resume_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        sess = None
        if resume_token:
            sess = await self.repo.get_by_resume_token(user_id, resume_token)
        elif session_id:
            sess = await self.repo.get(user_id, session_id)
        if not sess:
            return {"ok": False, "error": "not_found"}
        return await self.resume_session(user_id, sess)

    async def resume_session(self, user_id: str, sess: ConversationSession) -> Dict[str, Any]:
        if sess.user_id != user_id:
            return {"ok": False, "error": "forbidden"}
        sess.append_history(role="system", kind="resume", text="resume")
        ae = None
        if sess.action_session_id:
            ae = await self.action.get(user_id, sess.action_session_id)
        if ae and ae.get("status") == "active":
            sess.status = "waiting_user"
            turn = ae.get("current_turn") or {}
            sess.current_step = turn.get("id")
            if turn.get("question"):
                sess.meta["first_question"] = turn["question"]
            sess.meta["route"] = f"/action/{sess.action_session_id}"
            sess.summary = build_summary(sess)
            await self.repo.replace(sess)
            return {
                "ok": True,
                "session": sess.public(include_history=True),
                "action_session": ae,
                "route": sess.meta.get("route"),
                "first_question": sess.meta.get("first_question"),
                "ui_mode": "action_engine",
                "resumed": True,
            }
        # No active AE — restart orchestration from original input
        return await self.start(
            user_id,
            text=sess.input or sess.summary or "Continua",
            origin=sess.origin,
            suggestion_id=sess.suggestion_id,
            context={"known_slots": sess.known_slots, "resume_of": sess.id},
            force_new=True,
        )

    async def history(self, user_id: str, session_id: str) -> Dict[str, Any]:
        sess = await self.repo.get(user_id, session_id)
        if not sess:
            return {"ok": False, "error": "not_found"}
        # Compact steps — not chat bubbles
        steps = [
            {
                "at": h.at,
                "kind": h.kind,
                "step_id": h.step_id,
                "text": h.text,
                "role": h.role,
            }
            for h in sess.history
            if h.kind in ("start", "intent", "goal", "question", "answer", "artifact", "status", "resume", "cancel")
        ]
        return {
            "ok": True,
            "session_id": sess.id,
            "steps": steps,
            "ui_mode": "guided_steps",
            "not_chat": True,
        }

    async def summary(self, user_id: str, session_id: str) -> Dict[str, Any]:
        sess = await self.repo.get(user_id, session_id)
        if not sess:
            return {"ok": False, "error": "not_found"}
        sess.summary = build_summary(sess)
        await self.repo.replace(sess)
        return {
            "ok": True,
            "session_id": sess.id,
            "summary": sess.summary,
            "status": sess.status,
            "resume_token": sess.resume_token,
            "goal_id": sess.goal_id,
            "project_id": sess.project_id,
            "action_session_id": sess.action_session_id,
            "artifacts": [a.model_dump() for a in sess.artifacts],
        }

    async def get(self, user_id: str, session_id: str) -> Dict[str, Any]:
        sess = await self.repo.get(user_id, session_id)
        if not sess:
            return {"ok": False, "error": "not_found"}
        ae = None
        if sess.action_session_id:
            ae = await self.action.get(user_id, sess.action_session_id)
        return {
            "ok": True,
            "session": sess.public(include_history=True),
            "action_session": ae,
            "route": (sess.meta or {}).get("route") or (
                f"/action/{sess.action_session_id}" if sess.action_session_id else None
            ),
        }

    async def _after_ae(
        self, sess: ConversationSession, ae: Dict[str, Any], ae_res: Dict[str, Any],
    ) -> Dict[str, Any]:
        sess.known_slots = merge_slots(sess.known_slots, slots_from_ae_answers(ae.get("answers")))
        turn = ae.get("current_turn")
        if ae.get("done") or ae.get("status") == "completed":
            sess.status = "completed"
            sess.current_step = None
            sess.append_history(role="system", kind="status", text="completed")
        elif turn:
            sess.status = "waiting_user"
            sess.current_step = turn.get("id")
            sess.meta["first_question"] = turn.get("question")
            sess.append_history(
                role="ora",
                kind="question",
                text=turn.get("question"),
                step_id=turn.get("id"),
            )
        else:
            sess.status = "running_action"

        proj = ae.get("project") or {}
        if proj.get("project_id"):
            sess.project_id = proj["project_id"]
            sess.add_artifact("project", proj["project_id"], label=proj.get("title"))

        meta = ae.get("meta") or {}
        if meta.get("study_plan_id"):
            sess.add_artifact("study_plan", meta["study_plan_id"], label="Piano di studio")
        if meta.get("travel_project_id"):
            sess.add_artifact("travel_project", meta["travel_project_id"], label="Progetto viaggio")
            if not sess.project_id:
                sess.project_id = meta["travel_project_id"]

        if ae.get("brain_node_id"):
            sess.add_artifact("brain", ae["brain_node_id"])

        self._sync_artifacts_from_ae(sess, ae)
        sess.summary = build_summary(sess)
        if sess.action_session_id:
            sess.meta["route"] = f"/action/{sess.action_session_id}"
        await self.repo.replace(sess)

        return {
            "ok": ae_res.get("ok", True) is not False,
            "session": sess.public(include_history=True),
            "action_session": ae,
            "route": sess.meta.get("route"),
            "first_question": (turn or {}).get("question") if turn else None,
            "completed": sess.status == "completed",
            "ui_mode": "action_engine",
            "error": ae_res.get("error"),
            "message": ae_res.get("message"),
        }

    def _sync_artifacts_from_ae(self, sess: ConversationSession, ae: Dict[str, Any]) -> None:
        for ref in self.calendar.artifacts_from_ae_session(ae):
            sess.add_artifact(ref["kind"], ref["id"], label=ref.get("label"))
        for ref in self.documents.artifacts_from_ae_session(ae):
            sess.add_artifact(ref["kind"], ref["id"], label=ref.get("label"))
        for ref in self.maps.artifacts_from_ae_session(ae):
            sess.add_artifact(ref["kind"], ref["id"], label=ref.get("label"))
