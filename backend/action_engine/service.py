"""Action Engine service — Intent → Flow → open / answer / complete / cancel."""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from action_engine.brain import (
    ensure_brain_node,
    find_similar_goal,
    record_answer,
    upsert_summary,
)
from action_engine.effects import apply_completion_effects
from action_engine.flows import build_flow_turns, resolve_flow_from_intent
from action_engine.flows.base import next_unanswered
from action_engine.models import (
    ENGINE_VERSION,
    ActionSession,
    AnswerBody,
    OpenBody,
    ProjectLink,
    ProposedAction,
    QuestionTurn,
    TurnAnswer,
    now_iso,
)
from action_engine.projects import create_or_link_project, merge_projects
from action_engine.study.documents import search_study_documents
from action_engine.study.flow import (
    STEP_AVAILABLE_DAYS,
    STEP_CALENDAR_SYNC,
    STEP_CONFIRM,
    STEP_CONFIRM_SUBJECT,
    STEP_DAILY_TIME,
    STEP_DUPLICATE,
    STEP_EXAM_DATE,
    STEP_EXAM_DATE_CONFIRM,
    STEP_INTENSITY,
    STEP_PREFERRED_RANGES,
    STEP_PREVIEW,
    STEP_SELECT_MATERIALS,
    STEP_TOOLS,
    inject_ambiguous_date_turn,
    inject_duplicate_turn,
    jump_target,
    normalize_answer,
    rebuild_material_turn,
)
from action_engine.study.google_sync import is_google_connected
from action_engine.study.models import DEFAULT_TZ, PlanModifyBody
from action_engine.study.plan_service import StudyPlanService
from action_engine.travel.documents import search_travel_documents
from action_engine.travel.flow import (
    STEP_BOOKINGS as T_BOOKINGS,
    STEP_CALENDAR_SYNC as T_CALENDAR_SYNC,
    STEP_COMPANIONS as T_COMPANIONS,
    STEP_CONFIRM as T_CONFIRM,
    STEP_DEPARTURE as T_DEPARTURE,
    STEP_DEPARTURE_DATE as T_DEPARTURE_DATE,
    STEP_DESTINATION as T_DESTINATION,
    STEP_LODGING as T_LODGING,
    STEP_PERIOD as T_PERIOD,
    STEP_PREP as T_PREP,
    STEP_PREVIEW as T_PREVIEW,
    STEP_RETURN_DATE as T_RETURN_DATE,
    STEP_TRANSPORT as T_TRANSPORT,
    jump_target as travel_jump_target,
    known_departure,
    known_departure_date,
    known_destination,
    known_lodging,
    known_period,
    known_return_date,
    known_transport,
    normalize_answer as normalize_travel_answer,
    preview_explanation as travel_preview_explanation,
)
from action_engine.travel.models import TravelModifyBody
from action_engine.travel.project_service import TravelProjectService
from intent_engine import classify_text, get_intent_engine
from intent_engine.models import IntentResult

logger = logging.getLogger("ora.action_engine")


def _sid() -> str:
    return f"aes_{uuid.uuid4().hex[:14]}"


class ActionEngineService:
    def __init__(self, db, *, life_graph=None, knowledge=None, decisions=None):
        self.db = db
        self.life_graph = life_graph
        self.knowledge = knowledge
        self.decisions = decisions
        self.study_plans = StudyPlanService(
            db, life_graph=life_graph, knowledge=knowledge, decisions=decisions,
        )
        self.travel_projects = TravelProjectService(
            db, life_graph=life_graph, knowledge=knowledge, decisions=decisions,
        )

    @property
    def col(self):
        return self.db.action_sessions

    async def ensure_indexes(self) -> None:
        await self.col.create_index("id", unique=True)
        await self.col.create_index([("user_id", 1), ("status", 1), ("updated_at", -1)])
        await self.col.create_index([("user_id", 1), ("home_item_id", 1), ("status", 1)])
        await self.db.action_projects.create_index("id", unique=True)
        await self.db.action_projects.create_index([("user_id", 1), ("status", 1), ("updated_at", -1)])
        await self.db.action_projects.create_index([("user_id", 1), ("flow", 1), ("title", 1)])
        try:
            await self.db.reminders.create_index([("user_id", 1), ("status", 1), ("due_at", 1)])
        except Exception:
            pass
        await self.study_plans.ensure_indexes()
        await self.travel_projects.ensure_indexes()

    def _ctx_from_open(self, body: OpenBody) -> Dict[str, Any]:
        item = body.home_item or {}
        return {
            "title": body.title or item.get("title") or "Priorità",
            "description": body.description or item.get("description"),
            "location": body.location or item.get("location"),
            "due_at": body.due_at or item.get("due_at"),
            "start_at": body.start_at or item.get("start_at"),
            "amount": item.get("amount") or (body.meta or {}).get("amount"),
            "source_type": body.source_type or item.get("source_type"),
            "source_id": body.source_id or item.get("source_id"),
            "item_type": body.item_type or item.get("type"),
            "home_item_id": body.home_item_id or item.get("id"),
            "meta": {**(item.get("meta") or {}), **(body.meta or {})},
        }

    def _intent_from_body(self, body: OpenBody, ctx: Dict[str, Any]) -> IntentResult:
        """Resolve Intent object — never raw title heuristics inside AE for flow choice."""
        # 1) Explicit precomputed Intent on body
        if body.intent and isinstance(body.intent, dict) and body.intent.get("intent"):
            try:
                return IntentResult(**{
                    k: v for k, v in body.intent.items()
                    if k in IntentResult.model_fields
                })
            except Exception:
                pass

        # 2) Persisted intent on home item / meta
        item = body.home_item or {}
        meta = ctx.get("meta") or {}
        persisted = item.get("intent") or meta.get("intent_result") or meta.get("classified_intent")
        if isinstance(persisted, dict) and persisted.get("intent"):
            try:
                ir = IntentResult(**{
                    k: v for k, v in persisted.items()
                    if k in IntentResult.model_fields
                })
                if ir.confidence >= 0.62 and not ir.needs_clarify:
                    return ir
            except Exception:
                pass
        # Compact persisted fields on home item
        if item.get("intent") and isinstance(item.get("intent"), str):
            from intent_engine.models import IntentEntities
            ent_raw = item.get("intent_entities") or meta.get("intent_entities") or {}
            try:
                ents = IntentEntities(**ent_raw) if isinstance(ent_raw, dict) else IntentEntities()
            except Exception:
                ents = IntentEntities()
            conf = float(item.get("intent_confidence") or meta.get("intent_confidence") or 0.9)
            if conf >= 0.62:
                return IntentResult(
                    intent=item["intent"],  # type: ignore[arg-type]
                    subtype=item.get("intent_subtype") or meta.get("intent_subtype"),
                    confidence=conf,
                    reason="persisted_on_item",
                    entities=ents,
                    needs_clarify=False,
                )

        # 3) Classify via Intent Engine (deterministic; Action Engine does not parse text for flow)
        return classify_text(
            ctx.get("title") or "",
            description=ctx.get("description"),
            source_type=ctx.get("source_type"),
            item_type=None,  # do not trust erroneous home type for routing
            meta={"source_item_type": ctx.get("item_type")},
        )

    def _ctx_with_intent(self, ctx: Dict[str, Any], intent: IntentResult) -> Dict[str, Any]:
        entities = intent.entities.as_dict() if hasattr(intent.entities, "as_dict") else dict(intent.entities or {})
        display_title = ctx.get("title") or "Priorità"
        # Study: prefer subject in questions
        if intent.intent == "study" and entities.get("subject"):
            display_title = entities["subject"]
        if intent.intent == "travel" and (entities.get("travel") or entities.get("place")):
            display_title = entities.get("travel") or entities.get("place")
        out = {
            **ctx,
            "intent": intent.intent,
            "intent_subtype": intent.subtype,
            "intent_confidence": intent.confidence,
            "intent_entities": entities,
            "clarify_options": (
                [c.model_dump() if hasattr(c, "model_dump") else c for c in (intent.clarify_options or [])]
            ),
            "display_title": display_title,
            "title": (
                display_title if intent.intent == "study" and entities.get("subject")
                else display_title if intent.intent == "travel" and (entities.get("travel") or entities.get("place"))
                else ctx.get("title")
            ),
            "original_title": ctx.get("title"),
        }
        return out

    async def _resolve_home_place(self, user_id: str) -> Optional[str]:
        """Best-effort Brain / profile departure place (e.g. Tarquinia)."""
        try:
            node = await self.db.life_nodes.find_one(
                {
                    "user_id": user_id,
                    "type": {"$in": ["home", "generic", "place"]},
                    "status": {"$ne": "deleted"},
                    "$or": [
                        {"type": "home"},
                        {"attributes.kind": "home"},
                        {"attributes.is_home": True},
                        {"label": {"$regex": "tarquinia", "$options": "i"}},
                    ],
                },
                {"_id": 0, "label": 1},
            )
            if node and node.get("label"):
                return str(node["label"])
        except Exception:
            pass
        try:
            user = await self.db.users.find_one(
                {"user_id": user_id}, {"_id": 0, "profile": 1, "home_place": 1, "city": 1},
            )
            if user:
                for key in ("home_place", "city"):
                    if user.get(key):
                        return str(user[key])
                profile = user.get("profile") or {}
                if profile.get("home_place") or profile.get("city"):
                    return str(profile.get("home_place") or profile.get("city"))
        except Exception:
            pass
        return None

    async def _persist_intent_on_source(self, user_id: str, ctx: Dict[str, Any], intent: IntentResult) -> None:
        """Best-effort: store Intent on decision so Home labels stay correct."""
        if ctx.get("source_type") != "decision" or not ctx.get("source_id"):
            return
        try:
            from intent_engine.mapping import decision_category_for_intent
            patch: Dict[str, Any] = {
                "intent": intent.intent,
                "intent_subtype": intent.subtype,
                "intent_confidence": intent.confidence,
                "intent_entities": intent.entities.as_dict(),
                "intent_reason": intent.reason,
                "classifier_version": intent.classifier_version,
            }
            if not intent.needs_clarify:
                patch["category"] = decision_category_for_intent(intent.intent)
            await self.db.decisions.update_one(
                {"id": ctx["source_id"], "user_id": user_id},
                {"$set": patch},
            )
        except Exception as e:
            logger.debug("persist intent skipped: %s", type(e).__name__)

    async def open(self, user_id: str, body: OpenBody) -> Dict[str, Any]:
        ctx = self._ctx_from_open(body)
        home_item_id = ctx.get("home_item_id")

        # Resume active session for same home item (unless force_new)
        if home_item_id and not body.force_new:
            existing = await self.col.find_one(
                {"user_id": user_id, "home_item_id": home_item_id, "status": "active"},
                {"_id": 0},
            )
            if existing:
                sess = ActionSession(**existing)
                return {"session": sess.public(), "resumed": True}

        # === Intent Classification Engine (mandatory brain for flow choice) ===
        intent = self._intent_from_body(body, ctx)
        # Allow async path with optional LLM only if client asked via meta
        if (body.meta or {}).get("use_llm_intent"):
            intent = await get_intent_engine().classify(
                ctx.get("title") or "",
                description=ctx.get("description"),
                source_type=ctx.get("source_type"),
                item_type=None,
                use_llm=True,
            )

        flow = resolve_flow_from_intent(
            intent.intent,
            intent.subtype,
            needs_clarify=intent.needs_clarify,
        )
        ctx = self._ctx_with_intent(ctx, intent)
        await self._persist_intent_on_source(user_id, ctx, intent)

        google_ok = False
        if flow in ("study", "travel"):
            google_ok = await is_google_connected(self.db, user_id)
            ctx["google_connected"] = google_ok
            ctx["timezone"] = DEFAULT_TZ

        if flow == "travel":
            home_place = await self._resolve_home_place(user_id)
            if home_place:
                ctx["home_place"] = home_place
                ctx["brain_home"] = home_place

        turns = build_flow_turns(flow, ctx)
        answers: Dict[str, Any] = {}
        # Skip confirm_subject when Intent already extracted subject
        if flow == "study":
            entities = ctx.get("intent_entities") or {}
            subject = entities.get("subject")
            if subject and not any(t.id == STEP_CONFIRM_SUBJECT for t in turns):
                answers[STEP_CONFIRM_SUBJECT] = subject
            # Pre-search docs for materials step
            try:
                docs_res = await search_study_documents(
                    self.db,
                    user_id=user_id,
                    subject=subject or ctx.get("display_title"),
                    exam_name=ctx.get("original_title") or ctx.get("title"),
                )
                turns = rebuild_material_turn(turns, docs_res.get("items") or [])
                ctx["study_documents"] = docs_res.get("items") or []
            except Exception as e:
                logger.info("study doc search on open: %s", type(e).__name__)

        if flow == "travel":
            # Pass known_slots + gap into ctx for turn builders
            known_slots_meta = (body.meta or {}).get("known_slots") or {}
            if isinstance(known_slots_meta, dict):
                ctx["known_slots"] = known_slots_meta
            if (body.meta or {}).get("gap"):
                ctx["gap"] = body.meta["gap"]
            # Rebuild turns with enriched ctx (departure/return/dest/transport)
            turns = build_flow_turns(flow, ctx)

            period = known_period(ctx)
            dep_d = known_departure_date(ctx)
            ret_d = known_return_date(ctx)
            if period:
                answers[T_PERIOD] = period
                answers[T_DEPARTURE_DATE] = {
                    "departure_date": period["start_date"],
                    "start_date": period["start_date"],
                    "return_date": period["end_date"],
                    "end_date": period["end_date"],
                }
                answers[T_RETURN_DATE] = {
                    "return_date": period["end_date"],
                    "end_date": period["end_date"],
                }
            elif dep_d:
                answers[T_DEPARTURE_DATE] = {
                    "departure_date": dep_d,
                    "start_date": dep_d,
                }
                if ret_d:
                    answers[T_DEPARTURE_DATE]["return_date"] = ret_d
                    answers[T_DEPARTURE_DATE]["end_date"] = ret_d
                    answers[T_RETURN_DATE] = {"return_date": ret_d, "end_date": ret_d}
                    answers[T_PERIOD] = {"start_date": dep_d, "end_date": ret_d}
            dest = known_destination(ctx)
            if dest and not any(t.id == T_DESTINATION for t in turns):
                answers[T_DESTINATION] = dest
            if dest and T_DESTINATION not in answers and not any(t.id == T_DESTINATION for t in turns):
                answers[T_DESTINATION] = dest
            tr = known_transport(ctx)
            if tr and not any(t.id == T_TRANSPORT for t in turns):
                answers[T_TRANSPORT] = tr
            lod = known_lodging(ctx)
            if lod and not any(t.id == T_LODGING for t in turns):
                answers[T_LODGING] = lod
            try:
                docs_res = await search_travel_documents(
                    self.db,
                    user_id=user_id,
                    destination=dest or ctx.get("display_title"),
                )
                ctx["travel_documents"] = docs_res.get("items") or []
            except Exception as e:
                logger.info("travel doc search on open: %s", type(e).__name__)

        # Conversation Engine memory: never re-ask answered slots
        known_slots = (body.meta or {}).get("known_slots") or {}
        if isinstance(known_slots, dict):
            alias = {
                "subject": STEP_CONFIRM_SUBJECT if flow == "study" else None,
                "confirm_subject": STEP_CONFIRM_SUBJECT if flow == "study" else None,
                "period": T_PERIOD if flow == "travel" else None,
                "departure_date": T_DEPARTURE_DATE if flow == "travel" else None,
                "return_date": T_RETURN_DATE if flow == "travel" else None,
                "start_date": T_DEPARTURE_DATE if flow == "travel" else None,
                "end_date": T_RETURN_DATE if flow == "travel" else None,
                "destination": T_DESTINATION if flow == "travel" else None,
                "transport": T_TRANSPORT if flow == "travel" else None,
                "lodging": T_LODGING if flow == "travel" else None,
                "departure": "departure_place" if flow == "travel" else None,
                "departure_place": "departure_place" if flow == "travel" else None,
                "exam_date": "exam_date" if flow == "study" else None,
            }
            for key, val in known_slots.items():
                if val in (None, "", []):
                    continue
                target = alias.get(key, key)
                if not target or target in answers:
                    continue
                # Seed only when the turn was omitted (already known) or value is structured
                turn_present = any(t.id == target for t in turns)
                if not turn_present:
                    if target == T_DEPARTURE_DATE and not isinstance(val, dict):
                        answers[target] = {"departure_date": str(val)[:10], "start_date": str(val)[:10]}
                    elif target == T_RETURN_DATE and not isinstance(val, dict):
                        answers[target] = {"return_date": str(val)[:10], "end_date": str(val)[:10]}
                    else:
                        answers[target] = val

        first = next_unanswered(turns, answers) or (turns[0] if turns else None)

        brain_node_id = None
        similar = None
        if self.life_graph and self.knowledge:
            similar = await find_similar_goal(
                self.db, user_id, ctx.get("original_title") or ctx["title"], flow=flow,
            )
            brain_node_id = await ensure_brain_node(
                self.life_graph,
                self.knowledge,
                user_id=user_id,
                title=ctx.get("original_title") or ctx["title"],
                flow=flow,
                source_type=ctx.get("source_type"),
                source_id=ctx.get("source_id"),
            )

        # Compact understood summary for UI (human labels)
        _ent = ctx.get("intent_entities") or {}
        _ks = ctx.get("known_slots") or (body.meta or {}).get("known_slots") or {}
        understood = {}
        def _u(label, *keys):
            for k in keys:
                v = _ks.get(k) if isinstance(_ks, dict) else None
                if v is None:
                    v = _ent.get(k)
                if isinstance(v, dict):
                    v = v.get("label") or v.get("normalized") or v.get("date")
                if v not in (None, "", []):
                    understood[label] = str(v)
                    return
        _u("Partenza", "departure_date", "start_date")
        _u("Destinazione", "destination", "travel", "place")
        _u("Ritorno", "return_date", "end_date")
        _u("Trasporto", "transport")
        _u("Materia", "subject")
        _u("Data esame", "exam_date")

        session = ActionSession(
            id=_sid(),
            user_id=user_id,
            flow=flow,  # type: ignore[arg-type]
            title=ctx.get("original_title") or ctx["title"],
            description=ctx.get("description"),
            source_type=ctx.get("source_type"),
            source_id=ctx.get("source_id"),
            home_item_id=home_item_id,
            home_item_type=ctx.get("item_type"),
            turns=turns,
            answers=answers,
            current_turn_id=first.id if first else None,
            brain_node_id=brain_node_id,
            engine_version=ENGINE_VERSION,
            meta={
                "location": ctx.get("location"),
                "due_at": ctx.get("due_at"),
                "start_at": ctx.get("start_at"),
                "amount": ctx.get("amount"),
                "intent": intent.intent,
                "intent_subtype": intent.subtype,
                "intent_confidence": intent.confidence,
                "intent_entities": ctx.get("intent_entities") or {},
                "classifier_version": intent.classifier_version,
                "needs_clarify": intent.needs_clarify,
                "intent_reason": intent.reason,
                "google_connected": google_ok,
                "timezone": DEFAULT_TZ,
                "study_documents": ctx.get("study_documents") or [],
                "travel_documents": ctx.get("travel_documents") or [],
                "home_place": ctx.get("home_place"),
                "known_slots": _ks if isinstance(_ks, dict) else {},
                "gap": (body.meta or {}).get("gap") or ctx.get("gap") or {},
                "understood_summary": understood,
                **{k: v for k, v in (ctx.get("meta") or {}).items() if k not in ("intent_result",)},
            },
        )

        # Multi-step → create project early (skip for clarify)
        if flow != "clarify" and len(turns) >= 2:
            link, _proj = await create_or_link_project(
                self.db,
                user_id=user_id,
                title=session.title,
                flow=flow,
                session_id=session.id,
                brain_node_id=brain_node_id,
                source_type=ctx.get("source_type"),
                source_id=ctx.get("source_id"),
                similar=similar,
                answers={},
            )
            session.project = link
            if link.merge_candidate_id:
                session.meta["merge_proposal"] = {
                    "project_id": link.merge_candidate_id,
                    "title": link.merge_candidate_title,
                }

        doc = session.model_dump()
        await self.col.insert_one(doc)
        return {
            "session": session.public(),
            "resumed": False,
            "merge_proposal": session.meta.get("merge_proposal"),
            "intent": intent.public(),
        }

    async def get_session(self, user_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        doc = await self.col.find_one({"id": session_id, "user_id": user_id}, {"_id": 0})
        if not doc:
            return None
        return ActionSession(**doc).public()

    async def _apply_clarified_intent(
        self, sess: ActionSession, intent_name: str, subtype: Optional[str],
    ) -> ActionSession:
        """After clarify answer — rebuild real flow turns from chosen Intent."""
        from intent_engine.models import IntentEntities
        intent = IntentResult(
            intent=intent_name,  # type: ignore[arg-type]
            subtype=subtype,
            confidence=0.99,
            reason="user_clarified",
            needs_clarify=False,
            entities=IntentEntities(**(sess.meta.get("intent_entities") or {})),
        )
        # Re-extract if we have title
        if sess.title:
            fresh = classify_text(sess.title, description=sess.description)
            if fresh.intent == intent_name:
                intent.entities = fresh.entities
                intent.subtype = subtype or fresh.subtype

        flow = resolve_flow_from_intent(intent.intent, intent.subtype, needs_clarify=False)
        ctx = {
            "title": (intent.entities.subject if intent.intent == "study" and intent.entities.subject else sess.title),
            "original_title": sess.title,
            "description": sess.description,
            "source_type": sess.source_type,
            "source_id": sess.source_id,
            "location": sess.meta.get("location"),
            "due_at": sess.meta.get("due_at"),
            "start_at": sess.meta.get("start_at"),
            "amount": sess.meta.get("amount"),
            "intent_entities": intent.entities.as_dict(),
            **{k: v for k, v in sess.meta.items()},
        }
        turns = build_flow_turns(flow, ctx)
        sess.flow = flow  # type: ignore[assignment]
        sess.turns = turns
        sess.answers = {}
        sess.turn_history = []
        sess.current_turn_id = turns[0].id if turns else None
        sess.meta["intent"] = intent.intent
        sess.meta["intent_subtype"] = intent.subtype
        sess.meta["intent_confidence"] = intent.confidence
        sess.meta["intent_entities"] = intent.entities.as_dict()
        sess.meta["needs_clarify"] = False
        sess.meta["clarified"] = True
        sess.updated_at = now_iso()

        if flow != "clarify" and len(turns) >= 2 and not sess.project:
            link, _ = await create_or_link_project(
                self.db,
                user_id=sess.user_id,
                title=sess.title,
                flow=flow,
                session_id=sess.id,
                brain_node_id=sess.brain_node_id,
                source_type=sess.source_type,
                source_id=sess.source_id,
                similar=None,
                answers={},
            )
            sess.project = link
        return sess

    async def answer(self, user_id: str, session_id: str, body: AnswerBody) -> Dict[str, Any]:
        doc = await self.col.find_one({"id": session_id, "user_id": user_id}, {"_id": 0})
        if not doc:
            return {"ok": False, "error": "not_found"}
        sess = ActionSession(**doc)
        if sess.status != "active":
            return {"ok": False, "error": "not_active", "session": sess.public()}

        turn = None
        for t in sess.turns:
            if t.id == sess.current_turn_id:
                turn = t
                break
        if not turn:
            return await self.complete(user_id, session_id)

        if body.skip and turn.allow_skip:
            value = None
            option_id = "__skip__"
        else:
            option_id = body.option_id
            value = body.value
            if option_id and value is None:
                for o in turn.options:
                    if o.id == option_id:
                        value = o.value if o.value is not None else o.id
                        break
            if value is None and body.text:
                value = body.text.strip()
            if value is None and turn.required and not body.skip:
                return {"ok": False, "error": "answer_required", "session": sess.public()}

        # Clarify branch → rebuild flow from chosen Intent
        if turn.id == "clarify_intent" and sess.flow == "clarify":
            chosen_intent = None
            chosen_subtype = None
            if isinstance(value, dict):
                chosen_intent = value.get("intent")
                chosen_subtype = value.get("subtype")
            elif isinstance(value, str) and value in (
                "study", "event", "travel", "medical", "payment", "task", "generic",
            ):
                chosen_intent = value
            if not chosen_intent and option_id:
                for o in turn.options:
                    if o.id == option_id and isinstance(o.value, dict):
                        chosen_intent = o.value.get("intent")
                        chosen_subtype = o.value.get("subtype")
                        break
            if not chosen_intent:
                chosen_intent = "generic"
            sess.turn_history.append(TurnAnswer(
                turn_id=turn.id, option_id=option_id, value=value, text=body.text,
            ))
            sess = await self._apply_clarified_intent(sess, chosen_intent, chosen_subtype)
            await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
            return {"ok": True, "session": sess.public(), "completed": False, "clarified": True}

        # === Study flow: validate, preview, confirm (no silent side effects) ===
        if sess.flow == "study":
            return await self._answer_study(user_id, sess, turn, option_id, value, body)

        # === Travel flow: validate, preview, confirm (no silent calendar create) ===
        if sess.flow == "travel":
            return await self._answer_travel(user_id, sess, turn, option_id, value, body)

        sess.answers[turn.id] = value
        sess.turn_history.append(TurnAnswer(
            turn_id=turn.id,
            option_id=option_id,
            value=value,
            text=body.text,
        ))

        if self.knowledge and sess.brain_node_id:
            await record_answer(
                self.knowledge,
                user_id=user_id,
                node_id=sess.brain_node_id,
                brain_key=turn.brain_key,
                value=value,
                turn_id=turn.id,
            )

        nxt = next_unanswered(sess.turns, sess.answers)
        sess.updated_at = now_iso()
        if nxt:
            sess.current_turn_id = nxt.id
            await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
            return {"ok": True, "session": sess.public(), "completed": False}

        sess.current_turn_id = None
        await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
        return await self.complete(user_id, session_id)

    async def _answer_study(
        self,
        user_id: str,
        sess: ActionSession,
        turn: QuestionTurn,
        option_id: Optional[str],
        value: Any,
        body: AnswerBody,
    ) -> Dict[str, Any]:
        sess.meta.pop("validation_error", None)
        norm, err = normalize_answer(turn.id, value, body.text)
        if err:
            if err.get("error") == "ambiguous" and turn.id == STEP_EXAM_DATE:
                sess.turns = inject_ambiguous_date_turn(sess.turns, err.get("candidates") or [])
                sess.current_turn_id = STEP_EXAM_DATE_CONFIRM
                sess.meta["validation_error"] = err
                sess.updated_at = now_iso()
                await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
                return {
                    "ok": False,
                    "error": "ambiguous_date",
                    "message": err.get("message"),
                    "candidates": err.get("candidates"),
                    "session": sess.public(),
                }
            sess.meta["validation_error"] = err
            sess.updated_at = now_iso()
            await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
            return {
                "ok": False,
                "error": err.get("error") or "validation",
                "message": err.get("message") or "Risposta non valida.",
                "session": sess.public(),
            }

        # Upload mid-flow — pause answers, keep draft
        if turn.id == STEP_SELECT_MATERIALS and isinstance(norm, dict) and norm.get("action") == "upload":
            await self.save_draft(user_id, sess.id)
            sess.meta["awaiting_upload"] = True
            sess.updated_at = now_iso()
            await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
            return {
                "ok": True,
                "session": sess.public(),
                "completed": False,
                "upload_required": True,
                "upload_route": "/documents",
                "message": "Carica il documento, poi riprendi da Home — le risposte restano salvate.",
            }

        # Preview edit jumps
        if turn.id == STEP_PREVIEW and norm in (
            "edit_time", "edit_intensity", "edit_materials", "edit_calendar",
        ):
            target = jump_target(str(norm))
            if target:
                sess.answers.pop(target, None)
                # Clear downstream so preview regenerates
                for tid in (
                    STEP_PREVIEW, STEP_CONFIRM, STEP_DUPLICATE,
                    STEP_DAILY_TIME, STEP_AVAILABLE_DAYS, STEP_PREFERRED_RANGES,
                    STEP_INTENSITY, STEP_TOOLS, STEP_CALENDAR_SYNC, STEP_SELECT_MATERIALS,
                ):
                    if tid == target:
                        break
                    # keep prior
                # Remove answers from target onward for re-ask
                order = [t.id for t in sess.turns]
                if target in order:
                    for tid in order[order.index(target):]:
                        sess.answers.pop(tid, None)
                sess.current_turn_id = target
                sess.updated_at = now_iso()
                await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
                return {"ok": True, "session": sess.public(), "completed": False, "edited": True}

        if turn.id == STEP_CONFIRM and norm == "back":
            sess.answers.pop(STEP_CONFIRM, None)
            sess.answers.pop(STEP_PREVIEW, None)
            sess.current_turn_id = STEP_PREVIEW
            sess.updated_at = now_iso()
            await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
            return {"ok": True, "session": sess.public(), "completed": False}

        sess.answers[turn.id] = norm
        sess.turn_history.append(TurnAnswer(
            turn_id=turn.id, option_id=option_id, value=norm, text=body.text,
        ))

        if self.knowledge and sess.brain_node_id:
            await record_answer(
                self.knowledge,
                user_id=user_id,
                node_id=sess.brain_node_id,
                brain_key=turn.brain_key,
                value=norm,
                turn_id=turn.id,
            )

        # Refresh materials search after subject/date known
        if turn.id in (STEP_CONFIRM_SUBJECT, STEP_EXAM_DATE, STEP_EXAM_DATE_CONFIRM):
            subject = sess.answers.get(STEP_CONFIRM_SUBJECT) or (
                (sess.meta.get("intent_entities") or {}).get("subject")
            )
            try:
                docs_res = await search_study_documents(
                    self.db,
                    user_id=user_id,
                    subject=str(subject) if subject else None,
                    exam_name=sess.title,
                )
                sess.turns = rebuild_material_turn(sess.turns, docs_res.get("items") or [])
                sess.meta["study_documents"] = docs_res.get("items") or []
            except Exception:
                pass

        # Entering preview — build draft plan
        nxt = next_unanswered(sess.turns, sess.answers)
        if nxt and nxt.id == STEP_PREVIEW:
            draft = self.study_plans.build_draft_from_answers(
                user_id=user_id, answers=sess.answers, session=sess.model_dump(),
                meta=sess.meta,
            )
            similar = await self.study_plans.find_similar(
                user_id,
                exam_name=draft.exam_name,
                exam_date=draft.exam_date,
                source_priority_id=draft.source_priority_id,
            )
            if similar and similar.get("status") == "active" and STEP_DUPLICATE not in sess.answers:
                if not any(t.id == STEP_DUPLICATE for t in sess.turns):
                    sess.turns = inject_duplicate_turn(sess.turns, similar)
                sess.meta["duplicate_plan"] = {
                    "id": similar.get("id"),
                    "exam_name": similar.get("exam_name"),
                    "status": similar.get("status"),
                }
                sess.current_turn_id = STEP_DUPLICATE
                sess.updated_at = now_iso()
                await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
                return {"ok": True, "session": sess.public(), "completed": False, "duplicate": True}

            await self.study_plans.upsert_draft(draft)
            titles = [
                d.get("title") for d in (sess.meta.get("study_documents") or [])
                if d.get("id") in (draft.document_ids or [])
            ]
            prev = await self.study_plans.build_preview(draft, doc_titles=titles)
            if not prev.get("ok"):
                sess.meta["validation_error"] = prev
                # Send user back to fix constraints
                sess.answers.pop(STEP_AVAILABLE_DAYS, None)
                sess.current_turn_id = STEP_AVAILABLE_DAYS
                sess.updated_at = now_iso()
                await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
                return {
                    "ok": False,
                    "error": prev.get("error") or "impossible_plan",
                    "message": prev.get("message") or "Piano impossibile con questi vincoli.",
                    "session": sess.public(),
                }
            sess.meta["study_plan_id"] = draft.id
            sess.meta["study_preview"] = prev.get("preview") or draft.preview
            # Attach preview summary onto turn meta for UI
            for i, t in enumerate(sess.turns):
                if t.id == STEP_PREVIEW:
                    sess.turns[i] = QuestionTurn(
                        **{
                            **t.model_dump(),
                            "explanation": self._preview_explanation(prev.get("preview") or {}),
                            "meta": {"preview": prev.get("preview")},
                        }
                    )
                    break

        # Duplicate resolution
        if turn.id == STEP_DUPLICATE:
            sess.meta["duplicate_action"] = norm
            if norm == "open":
                dup = sess.meta.get("duplicate_plan") or {}
                sess.status = "cancelled"
                sess.updated_at = now_iso()
                await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
                plan = await self.study_plans.get_plan(user_id, dup.get("id"))
                return {
                    "ok": True,
                    "session": sess.public(),
                    "completed": True,
                    "opened_plan_id": dup.get("id"),
                    "plan": plan,
                }

        # Confirm → real create
        if turn.id == STEP_CONFIRM and norm == "confirm":
            return await self._confirm_study_session(user_id, sess)

        sess.updated_at = now_iso()
        nxt = next_unanswered(sess.turns, sess.answers)
        if nxt:
            sess.current_turn_id = nxt.id
            # Auto-save draft after each answer
            try:
                await self.save_draft(user_id, sess.id, sess=sess)
            except Exception:
                pass
            await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
            pub = sess.public()
            if sess.meta.get("study_preview"):
                pub["meta"]["study_preview"] = sess.meta["study_preview"]
            return {"ok": True, "session": pub, "completed": False}

        # Safety: should not complete study without confirm
        sess.current_turn_id = STEP_CONFIRM
        await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
        return {"ok": True, "session": sess.public(), "completed": False}

    def _preview_explanation(self, preview: dict) -> str:
        if not preview:
            return "Riepilogo piano."
        return (
            f"{preview.get('session_count', 0)} sessioni · "
            f"{preview.get('total_hours', 0)}h totali · "
            f"esame {preview.get('exam_label') or ''} · "
            f"intensità {preview.get('intensity')} · "
            f"{preview.get('daily_minutes')} min/giorno"
        )

    async def _confirm_study_session(self, user_id: str, sess: ActionSession) -> Dict[str, Any]:
        plan_id = sess.meta.get("study_plan_id")
        if not plan_id:
            draft = self.study_plans.build_draft_from_answers(
                user_id=user_id, answers=sess.answers, session=sess.model_dump(), meta=sess.meta,
            )
            await self.study_plans.upsert_draft(draft)
            await self.study_plans.build_preview(draft)
            plan_id = draft.id
            sess.meta["study_plan_id"] = plan_id

        dup_action = sess.answers.get(STEP_DUPLICATE) or sess.meta.get("duplicate_action")
        result = await self.study_plans.confirm(
            user_id, plan_id,
            duplicate_action=str(dup_action) if dup_action else None,
            force=dup_action == "create_anyway",
        )
        if not result.get("ok"):
            if result.get("error") == "duplicate":
                sess.meta["duplicate_plan"] = result.get("duplicate")
                if not any(t.id == STEP_DUPLICATE for t in sess.turns):
                    sess.turns = inject_duplicate_turn(sess.turns, result.get("duplicate") or {})
                sess.answers.pop(STEP_CONFIRM, None)
                sess.current_turn_id = STEP_DUPLICATE
                await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
                return {
                    "ok": False,
                    "error": "duplicate",
                    "message": "Esiste già un piano simile.",
                    "session": sess.public(),
                    "duplicate": result.get("duplicate"),
                }
            sess.meta["validation_error"] = result
            await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
            return {
                "ok": False,
                "error": result.get("error") or "confirm_failed",
                "message": result.get("message") or "Conferma non riuscita. Riprova.",
                "session": sess.public(),
            }

        effects = result.get("effects") or {}
        actions_raw = result.get("actions") or []
        sess.proposed_actions = [
            ProposedAction(**a) if isinstance(a, dict) else a for a in actions_raw
        ]
        sess.effects = effects
        sess.status = "completed"
        sess.completed_at = now_iso()
        sess.updated_at = sess.completed_at
        sess.current_turn_id = None
        sess.meta["next_focus_hint"] = result.get("next_focus_hint") or effects.get("next_focus_hint")
        sess.meta["home_invalidate"] = True
        sess.meta["study_plan_id"] = plan_id
        if effects.get("google_sync", {}).get("banner"):
            sess.meta["google_banner"] = effects["google_sync"]["banner"]

        if self.knowledge and sess.brain_node_id:
            await upsert_summary(
                self.knowledge,
                user_id=user_id,
                node_id=sess.brain_node_id,
                summary=f"Piano studio confermato: {sess.title}. {sess.meta.get('next_focus_hint')}",
                tags=["action_engine", "study", "confirmed"],
            )

        await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
        return {
            "ok": True,
            "session": sess.public(),
            "completed": True,
            "plan": result.get("plan"),
            "home_invalidate": True,
            "next_focus_hint": sess.meta.get("next_focus_hint"),
        }

    async def _answer_travel(
        self,
        user_id: str,
        sess: ActionSession,
        turn: QuestionTurn,
        option_id: Optional[str],
        value: Any,
        body: AnswerBody,
    ) -> Dict[str, Any]:
        sess.meta.pop("validation_error", None)
        # Skip prep when allow_skip
        if turn.id == T_PREP and (body.skip or option_id == "skip" or value in ("__skip__", "skip")):
            norm: Any = []
        else:
            norm, err = normalize_travel_answer(turn.id, value, body.text)
            if err:
                sess.meta["validation_error"] = err
                sess.updated_at = now_iso()
                await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
                return {
                    "ok": False,
                    "error": err.get("error") or "validation",
                    "message": err.get("message") or "Risposta non valida.",
                    "session": sess.public(),
                }

        if turn.id == T_PREVIEW and norm in ("edit_dest", "edit_period", "edit_calendar"):
            target = travel_jump_target(str(norm))
            if target:
                order = [t.id for t in sess.turns]
                if target in order:
                    for tid in order[order.index(target):]:
                        sess.answers.pop(tid, None)
                sess.current_turn_id = target
                sess.updated_at = now_iso()
                await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
                return {"ok": True, "session": sess.public(), "completed": False, "edited": True}

        if turn.id == T_CONFIRM and norm == "back":
            sess.answers.pop(T_CONFIRM, None)
            sess.answers.pop(T_PREVIEW, None)
            sess.current_turn_id = T_PREVIEW
            sess.updated_at = now_iso()
            await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
            return {"ok": True, "session": sess.public(), "completed": False}

        # Resolve return_offset_days against known departure
        if turn.id == T_RETURN_DATE and isinstance(norm, dict) and norm.get("return_offset_days"):
            from datetime import date as date_cls, timedelta
            dep_ans = sess.answers.get(T_DEPARTURE_DATE) or {}
            dep_s = None
            if isinstance(dep_ans, dict):
                dep_s = dep_ans.get("departure_date") or dep_ans.get("start_date")
            if not dep_s:
                dep_s = known_departure_date({
                    "intent_entities": sess.meta.get("intent_entities") or {},
                    "known_slots": sess.meta.get("known_slots") or {},
                })
            if dep_s:
                end = date_cls.fromisoformat(str(dep_s)[:10]) + timedelta(days=int(norm["return_offset_days"]))
                norm = {"return_date": end.isoformat(), "end_date": end.isoformat()}

        sess.answers[turn.id] = norm
        # Keep period in sync when both dates known
        if turn.id in (T_DEPARTURE_DATE, T_RETURN_DATE):
            dep_ans = sess.answers.get(T_DEPARTURE_DATE) or {}
            ret_ans = sess.answers.get(T_RETURN_DATE) or {}
            start = None
            end = None
            if isinstance(dep_ans, dict):
                start = dep_ans.get("departure_date") or dep_ans.get("start_date")
                end = dep_ans.get("return_date") or dep_ans.get("end_date") or end
            if isinstance(ret_ans, dict):
                end = ret_ans.get("return_date") or ret_ans.get("end_date") or end
            if start and end:
                sess.answers[T_PERIOD] = {"start_date": str(start)[:10], "end_date": str(end)[:10]}

        sess.turn_history.append(TurnAnswer(
            turn_id=turn.id, option_id=option_id, value=norm, text=body.text,
        ))

        if self.knowledge and sess.brain_node_id:
            await record_answer(
                self.knowledge,
                user_id=user_id,
                node_id=sess.brain_node_id,
                brain_key=turn.brain_key,
                value=norm,
                turn_id=turn.id,
            )

        # Entering preview — build Travel Project draft
        nxt = next_unanswered(sess.turns, sess.answers)
        if nxt and nxt.id == T_PREVIEW:
            # Ensure period/destination seeded from intent if answered via skip path
            if T_PERIOD not in sess.answers:
                period = known_period({
                    **sess.meta,
                    "intent_entities": sess.meta.get("intent_entities") or {},
                    "known_slots": sess.meta.get("known_slots") or {},
                    "title": sess.title,
                    "description": sess.description,
                    "original_title": sess.title,
                })
                if period:
                    sess.answers[T_PERIOD] = period
                else:
                    dep_ans = sess.answers.get(T_DEPARTURE_DATE) or {}
                    ret_ans = sess.answers.get(T_RETURN_DATE) or {}
                    start = (dep_ans or {}).get("departure_date") or (dep_ans or {}).get("start_date") if isinstance(dep_ans, dict) else None
                    end = (ret_ans or {}).get("return_date") or (ret_ans or {}).get("end_date") if isinstance(ret_ans, dict) else None
                    if start and end:
                        sess.answers[T_PERIOD] = {"start_date": str(start)[:10], "end_date": str(end)[:10]}
            if T_DESTINATION not in sess.answers:
                dest = known_destination({
                    "intent_entities": sess.meta.get("intent_entities") or {},
                    "known_slots": sess.meta.get("known_slots") or {},
                    "location": sess.meta.get("location"),
                    "title": sess.title,
                })
                if dest:
                    sess.answers[T_DESTINATION] = dest

            draft = self.travel_projects.build_draft_from_answers(
                user_id=user_id, answers=sess.answers, session=sess.model_dump(),
                meta=sess.meta,
            )
            await self.travel_projects.upsert_draft(draft)
            # Tests / offline: skip Nominatim when meta says so
            allow_net = not sess.meta.get("skip_maps_network")
            prev = await self.travel_projects.build_preview(draft, allow_network_maps=allow_net)
            if not prev.get("ok"):
                sess.meta["validation_error"] = prev
                if prev.get("error") == "missing_period":
                    sess.answers.pop(T_PERIOD, None)
                    sess.current_turn_id = T_RETURN_DATE if T_DEPARTURE_DATE in sess.answers else T_DEPARTURE_DATE
                else:
                    sess.answers.pop(T_DESTINATION, None)
                    sess.current_turn_id = T_DESTINATION
                sess.updated_at = now_iso()
                await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
                return {
                    "ok": False,
                    "error": prev.get("error") or "preview_failed",
                    "message": prev.get("message") or "Anteprima non disponibile.",
                    "session": sess.public(),
                }
            sess.meta["travel_project_id"] = draft.id
            sess.meta["travel_preview"] = prev.get("preview") or draft.preview
            for i, t in enumerate(sess.turns):
                if t.id == T_PREVIEW:
                    sess.turns[i] = QuestionTurn(
                        **{
                            **t.model_dump(),
                            "explanation": travel_preview_explanation(prev.get("preview") or {}),
                            "meta": {"preview": prev.get("preview")},
                        }
                    )
                    break

        if turn.id == T_CONFIRM and norm == "confirm":
            return await self._confirm_travel_session(user_id, sess)

        sess.updated_at = now_iso()
        nxt = next_unanswered(sess.turns, sess.answers)
        if nxt:
            sess.current_turn_id = nxt.id
            try:
                await self.save_draft(user_id, sess.id, sess=sess)
            except Exception:
                pass
            await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
            pub = sess.public()
            if sess.meta.get("travel_preview"):
                pub["meta"]["travel_preview"] = sess.meta["travel_preview"]
            return {"ok": True, "session": pub, "completed": False}

        sess.current_turn_id = T_CONFIRM
        await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
        return {"ok": True, "session": sess.public(), "completed": False}

    async def _confirm_travel_session(self, user_id: str, sess: ActionSession) -> Dict[str, Any]:
        plan_id = sess.meta.get("travel_project_id")
        if not plan_id:
            draft = self.travel_projects.build_draft_from_answers(
                user_id=user_id, answers=sess.answers, session=sess.model_dump(), meta=sess.meta,
            )
            await self.travel_projects.upsert_draft(draft)
            await self.travel_projects.build_preview(
                draft, allow_network_maps=not sess.meta.get("skip_maps_network"),
            )
            plan_id = draft.id
            sess.meta["travel_project_id"] = plan_id

        result = await self.travel_projects.confirm(user_id, plan_id)
        if not result.get("ok"):
            sess.meta["validation_error"] = result
            await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
            return {
                "ok": False,
                "error": result.get("error") or "confirm_failed",
                "message": result.get("message") or "Conferma non riuscita.",
                "session": sess.public(),
                "duplicate": result.get("duplicate"),
            }

        effects = result.get("effects") or {}
        actions_raw = result.get("actions") or []
        sess.proposed_actions = [
            ProposedAction(**a) if isinstance(a, dict) else a for a in actions_raw
        ]
        sess.effects = effects
        sess.status = "completed"
        sess.completed_at = now_iso()
        sess.updated_at = sess.completed_at
        sess.current_turn_id = None
        sess.meta["next_focus_hint"] = result.get("next_focus_hint") or effects.get("next_focus_hint")
        sess.meta["home_invalidate"] = True
        sess.meta["travel_project_id"] = plan_id
        if effects.get("google_sync", {}).get("banner"):
            sess.meta["google_banner"] = effects["google_sync"]["banner"]

        if self.knowledge and sess.brain_node_id:
            await upsert_summary(
                self.knowledge,
                user_id=user_id,
                node_id=sess.brain_node_id,
                summary=f"Travel Project confermato: {sess.title}. {sess.meta.get('next_focus_hint')}",
                tags=["action_engine", "travel", "confirmed"],
            )

        if sess.project and sess.project.project_id:
            try:
                await self.db.action_projects.update_one(
                    {"id": sess.project.project_id, "user_id": user_id},
                    {"$set": {
                        "next_focus_hint": sess.meta.get("next_focus_hint"),
                        "travel_project_id": plan_id,
                        "updated_at": now_iso(),
                        "status": "active",
                    }},
                )
            except Exception:
                pass

        await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
        return {
            "ok": True,
            "session": sess.public(),
            "completed": True,
            "plan": result.get("plan"),
            "home_invalidate": True,
            "next_focus_hint": sess.meta.get("next_focus_hint"),
        }

    async def save_draft(
        self, user_id: str, session_id: str, *, sess: Optional[ActionSession] = None,
    ) -> Dict[str, Any]:
        if sess is None:
            doc = await self.col.find_one({"id": session_id, "user_id": user_id}, {"_id": 0})
            if not doc:
                return {"ok": False, "error": "not_found"}
            sess = ActionSession(**doc)
        if sess.flow == "travel":
            draft = self.travel_projects.build_draft_from_answers(
                user_id=user_id, answers=sess.answers, session=sess.model_dump(), meta=sess.meta,
            )
            await self.travel_projects.upsert_draft(draft)
            sess.meta["travel_project_id"] = draft.id
            sess.updated_at = now_iso()
            await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
            return {"ok": True, "session": sess.public(), "plan_id": draft.id, "draft": True}
        if sess.flow != "study":
            sess.updated_at = now_iso()
            await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
            return {"ok": True, "session": sess.public(), "draft": True}
        draft = self.study_plans.build_draft_from_answers(
            user_id=user_id, answers=sess.answers, session=sess.model_dump(), meta=sess.meta,
        )
        await self.study_plans.upsert_draft(draft)
        sess.meta["study_plan_id"] = draft.id
        sess.updated_at = now_iso()
        await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
        return {"ok": True, "session": sess.public(), "plan_id": draft.id, "draft": True}

    async def back(
        self, user_id: str, session_id: str, to_turn_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        doc = await self.col.find_one({"id": session_id, "user_id": user_id}, {"_id": 0})
        if not doc:
            return {"ok": False, "error": "not_found"}
        sess = ActionSession(**doc)
        if sess.status != "active":
            return {"ok": False, "error": "not_active", "session": sess.public()}
        order = [t.id for t in sess.turns]
        current = sess.current_turn_id
        if to_turn_id and to_turn_id in order:
            target = to_turn_id
        else:
            if not current or current not in order:
                return {"ok": False, "error": "no_back", "session": sess.public()}
            idx = order.index(current)
            if idx <= 0:
                return {"ok": False, "error": "no_back", "session": sess.public()}
            target = order[idx - 1]
        # Clear answers from target onward
        for tid in order[order.index(target):]:
            sess.answers.pop(tid, None)
        sess.current_turn_id = target
        sess.updated_at = now_iso()
        await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
        return {"ok": True, "session": sess.public()}

    async def search_docs(self, user_id: str, session_id: str) -> Dict[str, Any]:
        doc = await self.col.find_one({"id": session_id, "user_id": user_id}, {"_id": 0})
        if not doc:
            return {"ok": False, "error": "not_found"}
        sess = ActionSession(**doc)
        subject = sess.answers.get(STEP_CONFIRM_SUBJECT) or (
            (sess.meta.get("intent_entities") or {}).get("subject")
        )
        res = await search_study_documents(
            self.db, user_id=user_id, subject=str(subject) if subject else None, exam_name=sess.title,
        )
        sess.turns = rebuild_material_turn(sess.turns, res.get("items") or [])
        sess.meta["study_documents"] = res.get("items") or []
        # Resume after upload
        if sess.meta.get("awaiting_upload"):
            sess.meta["awaiting_upload"] = False
            if sess.current_turn_id != STEP_SELECT_MATERIALS:
                sess.current_turn_id = STEP_SELECT_MATERIALS
                sess.answers.pop(STEP_SELECT_MATERIALS, None)
        sess.updated_at = now_iso()
        await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
        return {"ok": True, "session": sess.public(), "documents": res}

    async def preview_study(self, user_id: str, session_id: str) -> Dict[str, Any]:
        doc = await self.col.find_one({"id": session_id, "user_id": user_id}, {"_id": 0})
        if not doc:
            return {"ok": False, "error": "not_found"}
        sess = ActionSession(**doc)
        draft = self.study_plans.build_draft_from_answers(
            user_id=user_id, answers=sess.answers, session=sess.model_dump(), meta=sess.meta,
        )
        await self.study_plans.upsert_draft(draft)
        prev = await self.study_plans.build_preview(draft)
        if prev.get("ok"):
            sess.meta["study_plan_id"] = draft.id
            sess.meta["study_preview"] = prev.get("preview")
            await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
        return {**prev, "session": sess.public()}

    async def preview_travel(self, user_id: str, session_id: str) -> Dict[str, Any]:
        doc = await self.col.find_one({"id": session_id, "user_id": user_id}, {"_id": 0})
        if not doc:
            return {"ok": False, "error": "not_found"}
        sess = ActionSession(**doc)
        draft = self.travel_projects.build_draft_from_answers(
            user_id=user_id, answers=sess.answers, session=sess.model_dump(), meta=sess.meta,
        )
        await self.travel_projects.upsert_draft(draft)
        prev = await self.travel_projects.build_preview(
            draft, allow_network_maps=not sess.meta.get("skip_maps_network"),
        )
        if prev.get("ok"):
            sess.meta["travel_project_id"] = draft.id
            sess.meta["travel_preview"] = prev.get("preview")
            await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
        return {**prev, "session": sess.public()}

    async def modify_travel_preview(
        self, user_id: str, session_id: str, body: TravelModifyBody,
    ) -> Dict[str, Any]:
        doc = await self.col.find_one({"id": session_id, "user_id": user_id}, {"_id": 0})
        if not doc:
            return {"ok": False, "error": "not_found"}
        sess = ActionSession(**doc)
        plan_id = sess.meta.get("travel_project_id")
        if not plan_id:
            draft = self.travel_projects.build_draft_from_answers(
                user_id=user_id, answers=sess.answers, session=sess.model_dump(), meta=sess.meta,
            )
            await self.travel_projects.upsert_draft(draft)
            plan_id = draft.id
            sess.meta["travel_project_id"] = plan_id
        res = await self.travel_projects.modify_draft(user_id, plan_id, body)
        if res.get("ok"):
            sess.meta["travel_preview"] = res.get("preview")
            if body.destination is not None:
                sess.answers[T_DESTINATION] = body.destination
            if body.departure_place is not None:
                sess.answers[T_DEPARTURE] = body.departure_place
            if body.start_date is not None and body.end_date is not None:
                sess.answers[T_PERIOD] = {
                    "start_date": body.start_date, "end_date": body.end_date,
                }
            if body.transport is not None:
                sess.answers[T_TRANSPORT] = body.transport
            if body.bookings is not None:
                sess.answers[T_BOOKINGS] = body.bookings
            if body.companions is not None:
                sess.answers[T_COMPANIONS] = body.companions
            if body.calendar_sync is not None:
                sess.answers[T_CALENDAR_SYNC] = body.calendar_sync
            sess.updated_at = now_iso()
            await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
        return {**res, "session": sess.public()}

    async def modify_preview(
        self, user_id: str, session_id: str, body: PlanModifyBody,
    ) -> Dict[str, Any]:
        doc = await self.col.find_one({"id": session_id, "user_id": user_id}, {"_id": 0})
        if not doc:
            return {"ok": False, "error": "not_found"}
        sess = ActionSession(**doc)
        plan_id = sess.meta.get("study_plan_id")
        if not plan_id:
            draft = self.study_plans.build_draft_from_answers(
                user_id=user_id, answers=sess.answers, session=sess.model_dump(), meta=sess.meta,
            )
            await self.study_plans.upsert_draft(draft)
            plan_id = draft.id
            sess.meta["study_plan_id"] = plan_id
        res = await self.study_plans.modify_draft(user_id, plan_id, body)
        if res.get("ok"):
            sess.meta["study_preview"] = res.get("preview")
            # Sync answers from modify
            if body.daily_minutes is not None:
                sess.answers[STEP_DAILY_TIME] = body.daily_minutes
            if body.available_days is not None:
                sess.answers[STEP_AVAILABLE_DAYS] = body.available_days
            if body.intensity is not None:
                sess.answers[STEP_INTENSITY] = body.intensity
            if body.document_ids is not None:
                sess.answers[STEP_SELECT_MATERIALS] = body.document_ids
            if body.calendar_sync is not None:
                sess.answers[STEP_CALENDAR_SYNC] = body.calendar_sync
            if body.tools is not None:
                sess.answers[STEP_TOOLS] = body.tools
            if body.preferred_ranges is not None:
                sess.answers[STEP_PREFERRED_RANGES] = [r.model_dump() for r in body.preferred_ranges]
            sess.updated_at = now_iso()
            await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
        return {**res, "session": sess.public()}

    async def complete(self, user_id: str, session_id: str) -> Dict[str, Any]:
        doc = await self.col.find_one({"id": session_id, "user_id": user_id}, {"_id": 0})
        if not doc:
            return {"ok": False, "error": "not_found"}
        sess = ActionSession(**doc)
        if sess.status == "completed":
            return {"ok": True, "session": sess.public(), "completed": True}

        # Study: complete only via confirm path (prevents API-only silent create)
        if sess.flow == "study":
            if sess.answers.get(STEP_CONFIRM) == "confirm" or sess.meta.get("study_plan_id"):
                # Require explicit confirm answer
                if sess.answers.get(STEP_CONFIRM) != "confirm":
                    sess.current_turn_id = STEP_CONFIRM
                    await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
                    return {
                        "ok": False,
                        "error": "confirm_required",
                        "message": "Conferma il piano per crearlo.",
                        "session": sess.public(),
                    }
                return await self._confirm_study_session(user_id, sess)
            sess.current_turn_id = sess.current_turn_id or STEP_CONFIRM
            await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
            return {
                "ok": False,
                "error": "confirm_required",
                "message": "Completa le domande e conferma il piano.",
                "session": sess.public(),
            }

        # Travel: same confirm gate — never silent Google Calendar create
        if sess.flow == "travel":
            if sess.answers.get(T_CONFIRM) == "confirm":
                return await self._confirm_travel_session(user_id, sess)
            sess.current_turn_id = sess.current_turn_id or T_CONFIRM
            await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
            return {
                "ok": False,
                "error": "confirm_required",
                "message": "Conferma il Travel Project per crearlo.",
                "session": sess.public(),
            }

        actions, effects = await apply_completion_effects(
            db=self.db,
            life_graph=self.life_graph,
            knowledge=self.knowledge,
            decisions=self.decisions,
            session=sess.model_dump(),
        )
        sess.proposed_actions = list(sess.proposed_actions) + actions
        sess.effects = effects
        sess.status = "completed"
        sess.completed_at = now_iso()
        sess.updated_at = sess.completed_at
        sess.current_turn_id = None
        sess.meta["next_focus_hint"] = effects.get("next_focus_hint")
        sess.meta["home_invalidate"] = True

        if self.knowledge and sess.brain_node_id:
            await upsert_summary(
                self.knowledge,
                user_id=user_id,
                node_id=sess.brain_node_id,
                summary=f"Completato flusso {sess.flow}: {sess.title}. Hint: {effects.get('next_focus_hint') or '—'}",
                tags=["action_engine", sess.flow, "completed"],
            )

        await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
        return {
            "ok": True,
            "session": sess.public(),
            "completed": True,
            "home_invalidate": True,
            "next_focus_hint": effects.get("next_focus_hint"),
        }

    async def cancel(self, user_id: str, session_id: str) -> Dict[str, Any]:
        doc = await self.col.find_one({"id": session_id, "user_id": user_id}, {"_id": 0})
        if not doc:
            return {"ok": False, "error": "not_found"}
        sess = ActionSession(**doc)
        sess.status = "cancelled"
        sess.updated_at = now_iso()
        sess.current_turn_id = None
        await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
        return {"ok": True, "session": sess.public()}

    async def merge_project(
        self, user_id: str, session_id: str, target_project_id: str,
    ) -> Dict[str, Any]:
        doc = await self.col.find_one({"id": session_id, "user_id": user_id}, {"_id": 0})
        if not doc:
            return {"ok": False, "error": "not_found"}
        sess = ActionSession(**doc)
        if not sess.project:
            return {"ok": False, "error": "no_project"}
        result = await merge_projects(
            self.db,
            user_id=user_id,
            source_id=sess.project.project_id,
            target_id=target_project_id,
        )
        if result.get("ok"):
            sess.project = ProjectLink(
                project_id=target_project_id,
                title=sess.project.title,
                created=False,
            )
            sess.meta.pop("merge_proposal", None)
            sess.updated_at = now_iso()
            await self.col.replace_one({"id": sess.id, "user_id": user_id}, sess.model_dump())
        return {**result, "session": sess.public()}
