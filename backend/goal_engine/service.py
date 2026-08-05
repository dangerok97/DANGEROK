"""GoalService — identity, lifecycle, shadow upsert, merge, Brain link."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from goal_engine.deduplication import GoalDeduper
from goal_engine.events import (
    EVENT_ARCHIVED,
    EVENT_CANCELLED,
    EVENT_COMPLETED,
    EVENT_CREATED,
    EVENT_MERGED,
    EVENT_UPDATED,
    GoalEventBus,
)
from goal_engine.lifecycle import apply_status
from goal_engine.models import Goal, GoalCreateBody, GoalPatchBody, now_iso
from goal_engine.progress import compute_progress
from goal_engine.repository import GoalRepository
from goal_engine.strategy import goal_from_study_plan, goal_from_travel_project

logger = logging.getLogger("ora.goal_engine")


def goal_engine_enabled() -> bool:
    """Feature flag — default ON locally (1). OFF → shadow upsert is no-op."""
    raw = (os.environ.get("GOAL_ENGINE_ENABLED") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


class GoalService:
    def __init__(self, db, *, life_graph=None, knowledge=None):
        self.db = db
        self.life_graph = life_graph
        self.knowledge = knowledge
        self.repo = GoalRepository(db)
        self.deduper = GoalDeduper(self.repo)
        self.events = GoalEventBus(db)

    async def ensure_indexes(self) -> None:
        await self.repo.ensure_indexes()
        await self.events.ensure_indexes()

    # --- CRUD --------------------------------------------------------

    async def get(self, user_id: str, goal_id: str) -> Optional[Dict[str, Any]]:
        g = await self.repo.get(user_id, goal_id)
        return g.public() if g else None

    async def list_goals(
        self,
        user_id: str,
        *,
        status: Optional[str] = None,
        goal_type: Optional[str] = None,
        limit: int = 40,
    ) -> List[Dict[str, Any]]:
        goals = await self.repo.search(
            user_id, q=None, goal_type=goal_type, status=status, limit=limit,
        )
        return [g.public() for g in goals]

    async def search(
        self,
        user_id: str,
        *,
        q: Optional[str] = None,
        goal_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 40,
    ) -> List[Dict[str, Any]]:
        goals = await self.repo.search(
            user_id, q=q, goal_type=goal_type, status=status, limit=limit,
        )
        return [g.public() for g in goals]

    async def create(self, user_id: str, body: GoalCreateBody) -> Dict[str, Any]:
        if not goal_engine_enabled():
            return {"ok": False, "error": "goal_engine_disabled", "skipped": True}
        incoming = Goal(
            user_id=user_id,
            title=body.title.strip(),
            goal_type=body.goal_type,
            goal_subtype=body.goal_subtype,  # type: ignore[arg-type]
            description=body.description,
            status=body.status,
            priority=body.priority,
            importance=body.importance,
            urgency=body.urgency,
            desired_outcome=body.desired_outcome,
            current_state=body.current_state,
            next_action=body.next_action,
            project_id=body.project_id,
            study_plan_id=body.study_plan_id,
            travel_project_id=body.travel_project_id,
            source_action_session_id=body.source_action_session_id,
            idempotency_key=body.idempotency_key,
            linked_documents=list(body.linked_documents or []),
            linked_calendar_events=list(body.linked_calendar_events or []),
            linked_decisions=list(body.linked_decisions or []),
            created_from=dict(body.created_from or {}),
            target_date=body.target_date,
            start_date=body.start_date,
            brain_node_id=body.brain_node_id,
        )
        result = await self.upsert(incoming)
        return {"ok": True, **result}

    async def patch(self, user_id: str, goal_id: str, body: GoalPatchBody) -> Dict[str, Any]:
        g = await self.repo.get(user_id, goal_id)
        if not g:
            return {"ok": False, "error": "not_found"}
        data = body.model_dump(exclude_unset=True)
        new_status = data.pop("status", None)
        for k, v in data.items():
            if v is not None:
                setattr(g, k, v)
        if new_status:
            g, err = apply_status(g, new_status)
            if err:
                return {"ok": False, "error": err}
        g.updated_at = now_iso()
        await self.repo.upsert(g)
        evt = EVENT_UPDATED
        if new_status == "completed":
            evt = EVENT_COMPLETED
        elif new_status == "cancelled":
            evt = EVENT_CANCELLED
        elif new_status == "archived":
            evt = EVENT_ARCHIVED
        await self.events.emit(user_id=user_id, goal_id=g.id, event_type=evt, payload={"patch": True})
        return {"ok": True, "goal": g.public(), "created": False}

    async def delete(self, user_id: str, goal_id: str, *, soft: bool = True) -> Dict[str, Any]:
        g = await self.repo.get(user_id, goal_id)
        if not g:
            return {"ok": False, "error": "not_found"}
        if soft:
            g, err = apply_status(g, "cancelled")
            if err:
                # force cancel
                g.status = "cancelled"  # type: ignore[assignment]
                g.cancelled_at = now_iso()
            await self.repo.upsert(g)
            await self.events.emit(
                user_id=user_id, goal_id=goal_id, event_type=EVENT_CANCELLED, payload={"soft": True},
            )
            return {"ok": True, "goal": g.public()}
        await self.repo.delete(user_id, goal_id, soft=False)
        await self.events.emit(
            user_id=user_id, goal_id=goal_id, event_type=EVENT_CANCELLED, payload={"hard": True},
        )
        return {"ok": True, "deleted": True}

    async def archive(self, user_id: str, goal_id: str) -> Dict[str, Any]:
        g = await self.repo.get(user_id, goal_id)
        if not g:
            return {"ok": False, "error": "not_found"}
        g, err = apply_status(g, "archived")
        if err:
            return {"ok": False, "error": err}
        await self.repo.upsert(g)
        await self.events.emit(user_id=user_id, goal_id=goal_id, event_type=EVENT_ARCHIVED)
        return {"ok": True, "goal": g.public()}

    async def timeline(self, user_id: str, goal_id: str) -> Dict[str, Any]:
        g = await self.repo.get(user_id, goal_id)
        if not g:
            return {"ok": False, "error": "not_found"}
        events = await self.repo.timeline(user_id, goal_id)
        return {"ok": True, "goal_id": goal_id, "events": events}

    async def merge(
        self,
        user_id: str,
        *,
        source_goal_id: str,
        target_goal_id: str,
        prefer_target_title: bool = True,
    ) -> Dict[str, Any]:
        if source_goal_id == target_goal_id:
            return {"ok": False, "error": "same_goal"}
        src = await self.repo.get(user_id, source_goal_id)
        tgt = await self.repo.get(user_id, target_goal_id)
        if not src or not tgt:
            return {"ok": False, "error": "not_found"}
        title = tgt.title if prefer_target_title else src.title
        keep_idem = tgt.idempotency_key
        merged = self.deduper.merge_fields(tgt, src)
        merged.title = title
        # Keep target idempotency — never collide with still-persisted source key
        merged.idempotency_key = keep_idem
        merged.merged_from_ids = list(set((tgt.merged_from_ids or []) + [src.id] + (src.merged_from_ids or [])))
        await self.repo.upsert(merged)
        src.status = "cancelled"  # type: ignore[assignment]
        src.merged_into_id = merged.id
        src.cancelled_at = now_iso()
        src.updated_at = now_iso()
        # Release unique idempotency slot on cancelled source
        src.idempotency_key = f"merged_into:{merged.id}:{src.id}"
        await self.repo.upsert(src)
        await self.events.emit(
            user_id=user_id,
            goal_id=merged.id,
            event_type=EVENT_MERGED,
            payload={"source_goal_id": source_goal_id, "target_goal_id": target_goal_id},
        )
        return {"ok": True, "goal": merged.public(), "merged_source_id": source_goal_id}

    # --- Core upsert -------------------------------------------------

    async def upsert(self, goal: Goal, *, link_brain: bool = True) -> Dict[str, Any]:
        """
        Create or update a Goal. Dedupes by idempotency / artifact / title.
        When GOAL_ENGINE_ENABLED is off → no-op.
        """
        if not goal_engine_enabled():
            return {"ok": True, "skipped": True, "reason": "goal_engine_disabled", "created": False}

        existing = await self.deduper.find_existing(
            goal.user_id,
            idempotency_key=goal.idempotency_key,
            study_plan_id=goal.study_plan_id,
            travel_project_id=goal.travel_project_id,
            title=goal.title,
            goal_type=goal.goal_type,
        )
        created = False
        if existing:
            merged = self.deduper.merge_fields(existing, goal)
            goal = merged
            event = EVENT_UPDATED
        else:
            created = True
            event = EVENT_CREATED

        # Refresh progress from domain when linked
        if goal.study_plan_id or goal.travel_project_id:
            prog = await compute_progress(
                self.db,
                goal.user_id,
                study_plan_id=goal.study_plan_id,
                travel_project_id=goal.travel_project_id,
            )
            if prog.source != "none":
                goal.apply_progress(prog)

        if link_brain:
            try:
                goal.brain_node_id = await self._ensure_brain_link(goal)
            except Exception:
                logger.info("goal brain link soft-fail", exc_info=True)

        # Attach goal_id onto action_project bag (Project ≠ Goal)
        if goal.project_id:
            try:
                await self.db.action_projects.update_one(
                    {"id": goal.project_id, "user_id": goal.user_id},
                    {"$set": {"goal_id": goal.id, "updated_at": now_iso()}},
                )
            except Exception:
                pass

        # Soft-link goal_id on study/travel artifacts (non-breaking)
        if goal.study_plan_id:
            try:
                await self.db.study_plans.update_one(
                    {"id": goal.study_plan_id, "user_id": goal.user_id},
                    {"$set": {"goal_id": goal.id}},
                )
            except Exception:
                pass
        if goal.travel_project_id:
            try:
                await self.db.travel_projects.update_one(
                    {"id": goal.travel_project_id, "user_id": goal.user_id},
                    {"$set": {"goal_id": goal.id}},
                )
            except Exception:
                pass

        goal.updated_at = now_iso()
        await self.repo.upsert(goal)
        await self.events.emit(
            user_id=goal.user_id,
            goal_id=goal.id,
            event_type=event,
            payload={
                "goal_type": goal.goal_type,
                "title": goal.title,
                "study_plan_id": goal.study_plan_id,
                "travel_project_id": goal.travel_project_id,
            },
        )
        return {
            "ok": True,
            "created": created,
            "goal": goal.public(),
            "goal_id": goal.id,
        }

    async def upsert_from_study_confirm(
        self,
        plan: Dict[str, Any],
        *,
        effects: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Shadow hook — called from StudyPlanService.confirm. No UX."""
        if not goal_engine_enabled():
            return {"ok": True, "skipped": True, "reason": "goal_engine_disabled"}
        try:
            goal = goal_from_study_plan(plan, effects=effects)
            return await self.upsert(goal)
        except Exception as e:
            logger.exception("study shadow upsert failed")
            return {"ok": False, "error": type(e).__name__, "soft_fail": True}

    async def upsert_from_travel_confirm(
        self,
        project: Dict[str, Any],
        *,
        effects: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Shadow hook — called from TravelProjectService.confirm. No UX."""
        if not goal_engine_enabled():
            return {"ok": True, "skipped": True, "reason": "goal_engine_disabled"}
        try:
            goal = goal_from_travel_project(project, effects=effects)
            return await self.upsert(goal)
        except Exception as e:
            logger.exception("travel shadow upsert failed")
            return {"ok": False, "error": type(e).__name__, "soft_fail": True}

    # --- Brain -------------------------------------------------------

    async def _ensure_brain_link(self, goal: Goal) -> Optional[str]:
        """Reuse artifact brain node; optionally add goal_id attribute + edges."""
        node_id = goal.brain_node_id
        if not self.life_graph:
            return node_id

        node_type = "trip" if goal.goal_type == "travel" else "goal"
        if node_id:
            found = await self.life_graph.nodes_col.find_one(
                {"id": node_id, "user_id": goal.user_id}, {"_id": 0, "id": 1},
            )
            if found:
                try:
                    await self.life_graph.nodes_col.update_one(
                        {"id": node_id, "user_id": goal.user_id},
                        {"$set": {
                            "attributes.goal_id": goal.id,
                            "attributes.goal_engine": True,
                            "updated_at": now_iso(),
                        }},
                    )
                except Exception:
                    pass
                await self._link_brain_edges(goal, node_id)
                return node_id

        # Create only if no node yet (prefer not duplicating study/travel brain_links)
        node = await self.life_graph.create_node(
            goal.user_id,
            type=node_type,
            label=goal.title[:120],
            description=goal.desired_outcome or goal.description or "",
            attributes={
                "goal_id": goal.id,
                "goal_type": goal.goal_type,
                "goal_engine": True,
                "study_plan_id": goal.study_plan_id,
                "travel_project_id": goal.travel_project_id,
                "kind": "goal_engine",
            },
            origin="goal_engine",
        )
        node_id = node["id"]
        if self.knowledge:
            try:
                await self.knowledge.merge(
                    goal.user_id,
                    node_id,
                    {
                        "summary": goal.desired_outcome or goal.title,
                        "tags": ["goal_engine", goal.goal_type],
                    },
                    source_type="goal_engine",
                    actor_type="system",
                )
            except Exception:
                pass
        await self._link_brain_edges(goal, node_id)
        return node_id

    async def _link_brain_edges(self, goal: Goal, brain_node_id: str) -> None:
        """Best-effort edges to docs/calendar/decisions without breaking existing links."""
        if not self.life_graph:
            return

        async def _edge(to_id: str, rel: str) -> None:
            if not to_id or to_id == brain_node_id:
                return
            try:
                # Avoid dupes
                existing = await self.life_graph.edges_col.find_one(
                    {
                        "user_id": goal.user_id,
                        "from_node": brain_node_id,
                        "to_node": to_id,
                        "type": rel,
                    },
                    {"_id": 0, "id": 1},
                )
                if existing:
                    return
                if hasattr(self.life_graph, "create_edge"):
                    await self.life_graph.create_edge(
                        goal.user_id,
                        from_node=brain_node_id,
                        to_node=to_id,
                        type=rel,
                        attributes={"origin": "goal_engine", "goal_id": goal.id},
                    )
            except Exception:
                logger.debug("edge soft-fail %s→%s", brain_node_id, to_id, exc_info=True)

        for doc_id in goal.linked_documents or []:
            # documents may not be life_nodes — skip if not a node
            n = await self.db.life_nodes.find_one(
                {"id": doc_id, "user_id": goal.user_id}, {"_id": 0, "id": 1},
            )
            if n:
                await _edge(doc_id, "related_to")
        for cal_id in goal.linked_calendar_events or []:
            await _edge(cal_id, "related_to")
        for dec_id in goal.linked_decisions or []:
            # decisions may have node_ids — link decision's primary node if any
            dec = await self.db.decisions.find_one(
                {"id": dec_id, "user_id": goal.user_id},
                {"_id": 0, "node_ids": 1},
            )
            for nid in (dec or {}).get("node_ids") or []:
                await _edge(nid, "related_to")


# Module-level lazy singleton for confirm hooks
_svc: Optional[GoalService] = None


def get_goal_service(db=None, *, life_graph=None, knowledge=None) -> GoalService:
    global _svc
    if _svc is not None and db is None:
        return _svc
    if db is None:
        from deps import db as _db, life_graph as _lg, knowledge as _kn
        db = _db
        life_graph = life_graph or _lg
        knowledge = knowledge or _kn
    _svc = GoalService(db, life_graph=life_graph, knowledge=knowledge)
    return _svc
