"""Action Engine service — Intent → Flow → open / answer / complete / cancel."""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

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
    TurnAnswer,
    now_iso,
)
from action_engine.projects import create_or_link_project, merge_projects
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
            "title": display_title if intent.intent == "study" and entities.get("subject") else ctx.get("title"),
            "original_title": ctx.get("title"),
        }
        return out

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

        turns = build_flow_turns(flow, ctx)
        first = turns[0] if turns else None

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

    async def complete(self, user_id: str, session_id: str) -> Dict[str, Any]:
        doc = await self.col.find_one({"id": session_id, "user_id": user_id}, {"_id": 0})
        if not doc:
            return {"ok": False, "error": "not_found"}
        sess = ActionSession(**doc)
        if sess.status == "completed":
            return {"ok": True, "session": sess.public(), "completed": True}

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
