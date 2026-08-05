"""Action Engine service — open / answer / complete / cancel."""
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
from action_engine.flows import build_flow_turns, resolve_category
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

    async def open(self, user_id: str, body: OpenBody) -> Dict[str, Any]:
        ctx = self._ctx_from_open(body)
        category = resolve_category(ctx.get("item_type"), ctx.get("source_type"))
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

        turns = build_flow_turns(category, ctx)
        first = turns[0] if turns else None

        brain_node_id = None
        similar = None
        if self.life_graph and self.knowledge:
            similar = await find_similar_goal(
                self.db, user_id, ctx["title"], flow=category,
            )
            brain_node_id = await ensure_brain_node(
                self.life_graph,
                self.knowledge,
                user_id=user_id,
                title=ctx["title"],
                flow=category,
                source_type=ctx.get("source_type"),
                source_id=ctx.get("source_id"),
            )

        session = ActionSession(
            id=_sid(),
            user_id=user_id,
            flow=category,  # type: ignore[arg-type]
            title=ctx["title"],
            description=ctx.get("description"),
            source_type=ctx.get("source_type"),
            source_id=ctx.get("source_id"),
            home_item_id=home_item_id,
            home_item_type=ctx.get("item_type"),
            turns=turns,
            current_turn_id=first.id if first else None,
            brain_node_id=brain_node_id,
            meta={
                "location": ctx.get("location"),
                "due_at": ctx.get("due_at"),
                "start_at": ctx.get("start_at"),
                "amount": ctx.get("amount"),
                **(ctx.get("meta") or {}),
            },
        )

        # Multi-step → create project early
        if len(turns) >= 2:
            link, _proj = await create_or_link_project(
                self.db,
                user_id=user_id,
                title=ctx["title"],
                flow=category,
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
        }

    async def get_session(self, user_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        doc = await self.col.find_one({"id": session_id, "user_id": user_id}, {"_id": 0})
        if not doc:
            return None
        return ActionSession(**doc).public()

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
            # Already past questions — complete
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

        # All answered → auto-complete
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
