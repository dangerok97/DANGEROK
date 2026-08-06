"""LifeObjectService — CRUD, upsert from sources, merge, reason (shadow mode)."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from life_objects.deduplication import LifeObjectDeduper, extract_identity_keys_from_reasoning
from life_objects.linking import (
    add_relationship,
    ensure_brain_node,
    ensure_object_doc_edge,
    link_document,
    link_goal,
)
from life_objects.memory import append_history, basic_utility_trend
from life_objects.models import (
    AI_REASONING_VERSION,
    LifeObject,
    LifeObjectCreateBody,
    LifeObjectHealth,
    LifeObjectHistoryEntry,
    LifeObjectPatchBody,
    PendingQuestion,
    SuggestedAction,
    now_iso,
)
from life_objects.reasoner import (
    infer_object_type_for_goal,
    reason_from_document,
    reason_from_study,
    reason_from_travel,
)
from life_objects.repository import LifeObjectRepository

logger = logging.getLogger("ora.life_objects")

_SERVICE: Optional["LifeObjectService"] = None


def life_object_engine_enabled() -> bool:
    """Shadow writes ON by default. OFF → all upserts are no-ops."""
    raw = (os.environ.get("LIFE_OBJECT_ENGINE_ENABLED") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def life_object_home_ui_enabled() -> bool:
    """Home V3 Life Objects view — default OFF (UX unchanged)."""
    raw = (os.environ.get("LIFE_OBJECT_HOME_UI_ENABLED") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def get_life_object_service(db=None, *, life_graph=None, knowledge=None) -> "LifeObjectService":
    global _SERVICE
    if _SERVICE is None:
        if db is None:
            from deps import db as _db
            db = _db
        _SERVICE = LifeObjectService(db, life_graph=life_graph, knowledge=knowledge)
    else:
        if life_graph is not None:
            _SERVICE.life_graph = life_graph
        if knowledge is not None:
            _SERVICE.knowledge = knowledge
    return _SERVICE


class LifeObjectService:
    def __init__(self, db, *, life_graph=None, knowledge=None):
        self.db = db
        self.life_graph = life_graph
        self.knowledge = knowledge
        self.repo = LifeObjectRepository(db)
        self.deduper = LifeObjectDeduper(self.repo)

    async def ensure_indexes(self) -> None:
        await self.repo.ensure_indexes()

    # --- CRUD --------------------------------------------------------

    async def get(self, user_id: str, object_id: str) -> Optional[Dict[str, Any]]:
        obj = await self.repo.get(user_id, object_id)
        return obj.public() if obj else None

    async def list_objects(
        self,
        user_id: str,
        *,
        object_type: Optional[str] = None,
        status: Optional[str] = "active",
        limit: int = 40,
    ) -> List[Dict[str, Any]]:
        objs = await self.repo.list_by_type(
            user_id, object_type=object_type, status=status, limit=limit,
        )
        return [o.public() for o in objs]

    async def search(
        self,
        user_id: str,
        *,
        q: Optional[str] = None,
        object_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 40,
    ) -> List[Dict[str, Any]]:
        objs = await self.repo.search(
            user_id, q=q, object_type=object_type, status=status, limit=limit,
        )
        return [o.public() for o in objs]

    async def create(self, user_id: str, body: LifeObjectCreateBody) -> Dict[str, Any]:
        if not life_object_engine_enabled():
            return {"ok": False, "error": "life_object_engine_disabled", "skipped": True}
        obj = LifeObject(
            user_id=user_id,
            type=body.type,
            title=body.title.strip(),
            summary=body.summary or "",
            properties=dict(body.properties or {}),
            identity_keys=dict(body.identity_keys or {}),
            origin=body.origin or "api",
            confidence=body.confidence,
        )
        # Dedup before create
        match, key, candidates = await self.deduper.find_match(
            user_id, object_type=obj.type, identity_keys=obj.identity_keys,
        )
        if match:
            return await self._apply_update(
                match,
                title=obj.title,
                summary=obj.summary,
                properties=obj.properties,
                identity_keys=obj.identity_keys,
                source="api_create",
                decision_meta={"matched_key": key, "candidates": len(candidates)},
            )
        append_history(obj, event="created", source="api", summary="Created via API")
        await self.repo.upsert(obj)
        try:
            await ensure_brain_node(life_graph=self.life_graph, obj=obj)
            await self.repo.upsert(obj)
        except Exception:
            pass
        return {"ok": True, "object": obj.public(), "created": True}

    async def patch(self, user_id: str, object_id: str, body: LifeObjectPatchBody) -> Dict[str, Any]:
        obj = await self.repo.get(user_id, object_id)
        if not obj:
            return {"ok": False, "error": "not_found"}
        data = body.model_dump(exclude_unset=True)
        for k, v in data.items():
            if v is not None:
                setattr(obj, k, v)
        append_history(obj, event="patched", source="api", summary="Patched via API", delta=data)
        await self.repo.upsert(obj)
        return {"ok": True, "object": obj.public(), "created": False}

    async def delete(self, user_id: str, object_id: str, *, soft: bool = True) -> Dict[str, Any]:
        ok = await self.repo.delete(user_id, object_id, soft=soft)
        if not ok:
            return {"ok": False, "error": "not_found"}
        return {"ok": True, "deleted": True, "soft": soft}

    async def link(
        self,
        user_id: str,
        object_id: str,
        *,
        target_id: str,
        relation: str = "related_to",
        confidence: float = 0.7,
    ) -> Dict[str, Any]:
        obj = await self.repo.get(user_id, object_id)
        target = await self.repo.get(user_id, target_id)
        if not obj or not target:
            return {"ok": False, "error": "not_found"}
        add_relationship(obj, target_id, relation, confidence)
        add_relationship(target, object_id, relation, confidence)
        await self.repo.upsert(obj)
        await self.repo.upsert(target)
        try:
            from life_objects.linking import ensure_object_object_edge
            await ensure_object_object_edge(
                life_graph=self.life_graph, db=self.db, a=obj, b=target, relation=relation,
            )
        except Exception:
            pass
        return {"ok": True, "object": obj.public(), "target": target.public()}

    async def merge(
        self,
        user_id: str,
        *,
        source_id: str,
        target_id: str,
        prefer_target_title: bool = True,
    ) -> Dict[str, Any]:
        if source_id == target_id:
            return {"ok": False, "error": "same_object"}
        src = await self.repo.get(user_id, source_id)
        tgt = await self.repo.get(user_id, target_id)
        if not src or not tgt:
            return {"ok": False, "error": "not_found"}
        title = tgt.title if prefer_target_title else src.title
        merged = self.deduper.merge_fields(tgt, src)
        merged.title = title
        merged.merged_from_ids = list(
            set((tgt.merged_from_ids or []) + [src.id] + (src.merged_from_ids or []))
        )
        append_history(
            merged,
            event="merged",
            source="api_merge",
            source_id=source_id,
            summary=f"Merged {source_id} into {target_id}",
        )
        await self.repo.upsert(merged)
        src.status = "merged"  # type: ignore[assignment]
        src.merged_into_id = merged.id
        src.updated_at = now_iso()
        append_history(src, event="merged_away", source="api_merge", source_id=target_id)
        await self.repo.upsert(src)
        return {"ok": True, "object": merged.public(), "merged_source_id": source_id}

    async def reason(
        self,
        user_id: str,
        *,
        document_id: Optional[str] = None,
        force: bool = False,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if document_id:
            doc = await self.db.documents.find_one(
                {"id": document_id, "user_id": user_id}, {"_id": 0},
            )
            if not doc:
                return {"ok": False, "error": "document_not_found"}
            reasoning = doc.get("life_reasoning") or {}
            if not reasoning:
                return {"ok": False, "error": "no_life_reasoning"}
            return await self.upsert_from_document(user_id, doc, reasoning)

        # Re-reason a bare context payload (tests / admin)
        ctx = context or {}
        decision = await reason_from_document(reasoning=ctx, existing_candidates=[])
        return {"ok": True, "decision": decision.model_dump(), "applied": False}

    async def trend(self, user_id: str, object_id: str, *, utility_type: Optional[str] = None) -> Dict[str, Any]:
        obj = await self.repo.get(user_id, object_id)
        if not obj:
            return {"ok": False, "error": "not_found"}
        return {"ok": True, "object_id": object_id, **basic_utility_trend(obj, utility_type=utility_type)}

    # --- Shadow upserts ----------------------------------------------

    async def upsert_from_document(
        self,
        user_id: str,
        doc: Dict[str, Any],
        reasoning: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Primary shadow hook after Documents V2 / Life Experience consume."""
        if not life_object_engine_enabled():
            return {"ok": True, "skipped": True, "reason": "life_object_engine_disabled"}

        document_id = doc.get("id") or reasoning.get("document_id") or ""
        # Prefetch candidates for reasoner (by domain mapping type)
        from life_objects.types import DOC_TYPE_TO_OBJECT, DOMAIN_TO_OBJECT

        hint_type = DOC_TYPE_TO_OBJECT.get(str(reasoning.get("document_type") or "")) or DOMAIN_TO_OBJECT.get(
            str(reasoning.get("domain") or "")
        )
        candidates_objs = []
        if hint_type:
            candidates_objs = await self.repo.list_by_type(user_id, object_type=hint_type, limit=20)
        # Also include any object already linked to this document
        if document_id:
            linked = await self.repo.search(user_id, q=None, limit=20)
            for o in linked:
                if document_id in (o.documents or []) and o.id not in {c.id for c in candidates_objs}:
                    candidates_objs.append(o)

        decision = await reason_from_document(
            reasoning=reasoning,
            existing_candidates=[c.public() for c in candidates_objs],
        )

        # Re-check with repository deduper using identity keys (authoritative)
        identity_keys = dict(decision.identity_keys or {})
        if not identity_keys:
            identity_keys = extract_identity_keys_from_reasoning(
                object_type=decision.object_type, reasoning=reasoning,
            )
            decision.identity_keys = identity_keys

        match, match_key, all_cands = await self.deduper.find_match(
            user_id, object_type=decision.object_type, identity_keys=identity_keys,
        )

        if decision.action == "skip":
            return {"ok": True, "skipped": True, "reason": "reasoner_skip", "decision": decision.model_dump()}

        # Conflict / weak identity with existing same-type → propose merge, never silent Casa 2
        merge_pool = list(all_cands) or list(candidates_objs)
        if decision.object_id and not any(c.id == decision.object_id for c in merge_pool):
            by_id = await self.repo.get(user_id, decision.object_id)
            if by_id:
                merge_pool.append(by_id)
        if len(all_cands) > 1 or decision.action == "propose_merge":
            primary = match
            if not primary and merge_pool:
                primary = merge_pool[0]
            if primary:
                cand_ids = [c.id for c in merge_pool] or [primary.id]
                proposal = {
                    "at": now_iso(),
                    "document_id": document_id,
                    "candidate_ids": cand_ids,
                    "incoming_keys": identity_keys,
                    "reason": decision.reason_summary or "identity conflict",
                }
                primary.merge_proposals = list(primary.merge_proposals or []) + [proposal]
                # Still update primary with non-conflicting data when safe
                if match and not self.deduper.has_identity_conflict(match, identity_keys):
                    result = await self._apply_update(
                        match,
                        title=decision.title or match.title,
                        summary=decision.summary or match.summary,
                        properties=decision.properties_delta,
                        identity_keys=identity_keys,
                        source="document",
                        source_id=document_id,
                        improves=decision.improves,
                        worsens=decision.worsens,
                        decision=decision,
                    )
                    result["merge_proposed"] = True
                    result["candidates"] = cand_ids
                    return result
                append_history(
                    primary,
                    event="merge_proposed",
                    source="document",
                    source_id=document_id,
                    summary=proposal["reason"],
                    delta={"incoming_keys": identity_keys},
                )
                if document_id:
                    link_document(primary, document_id)
                await self.repo.upsert(primary)
                return {
                    "ok": True,
                    "created": False,
                    "merge_proposed": True,
                    "object": primary.public(),
                    "candidates": cand_ids,
                    "decision": decision.model_dump(),
                }
            # propose_merge with no pool at all → uncertain, do not invent active HOME
            decision.action = "uncertain"  # type: ignore[assignment]

        if decision.action == "uncertain" and not match:
            # Create as uncertain status — visible via API, not silent second home as active
            obj = LifeObject(
                user_id=user_id,
                type=decision.object_type,
                title=decision.title or decision.object_type,
                status="uncertain",
                summary=decision.summary or "",
                properties=dict(decision.properties_delta or {}),
                identity_keys=identity_keys,
                origin="document",
                confidence=min(float(decision.confidence or 0.3), 0.4),
                ai_summary=decision.summary or "",
                ai_reasoning_version=AI_REASONING_VERSION,
                ai_confidence=float(decision.confidence or 0),
                last_reasoning=decision.model_dump(),
            )
            if document_id:
                link_document(obj, document_id)
            self._apply_decision_side_effects(obj, decision)
            append_history(
                obj, event="created_uncertain", source="document", source_id=document_id,
                summary=decision.reason_summary,
                improves=decision.improves, worsens=decision.worsens,
                delta={"properties": decision.properties_delta},
            )
            await self.repo.upsert(obj)
            return {
                "ok": True,
                "created": True,
                "uncertain": True,
                "object": obj.public(),
                "decision": decision.model_dump(),
            }

        if match or decision.action == "update":
            target = match
            if not target and decision.object_id:
                target = await self.repo.get(user_id, decision.object_id)
            if target:
                return await self._apply_update(
                    target,
                    title=decision.title or target.title,
                    summary=decision.summary or target.summary,
                    properties=decision.properties_delta,
                    identity_keys=identity_keys,
                    source="document",
                    source_id=document_id,
                    improves=decision.improves,
                    worsens=decision.worsens,
                    decision=decision,
                )

        # Create new
        obj = LifeObject(
            user_id=user_id,
            type=decision.object_type,
            title=decision.title or decision.object_type,
            summary=decision.summary or "",
            properties=dict(decision.properties_delta or {}),
            identity_keys=identity_keys,
            origin="document",
            confidence=float(decision.confidence or 0.5),
            ai_summary=decision.summary or "",
            ai_reasoning_version=AI_REASONING_VERSION,
            ai_confidence=float(decision.confidence or 0),
            last_reasoning=decision.model_dump(),
            next_reasoning=decision.next_question,
        )
        if document_id:
            link_document(obj, document_id)
        self._apply_decision_side_effects(obj, decision)
        self._refresh_health(obj)
        append_history(
            obj,
            event="created",
            source="document",
            source_id=document_id,
            summary=decision.reason_summary or "Created from document",
            improves=decision.improves,
            worsens=decision.worsens,
            delta={
                "properties": decision.properties_delta,
                "amount": (decision.properties_delta or {}).get("amount_total"),
                "utility_type": (decision.properties_delta or {}).get("utility_type"),
            },
        )
        await self.repo.upsert(obj)
        try:
            await ensure_brain_node(life_graph=self.life_graph, obj=obj)
            if document_id:
                await ensure_object_doc_edge(
                    life_graph=self.life_graph, db=self.db, obj=obj, document_id=document_id,
                )
            await self.repo.upsert(obj)
        except Exception:
            pass
        return {
            "ok": True,
            "created": True,
            "object": obj.public(),
            "decision": decision.model_dump(),
            "matched_key": match_key,
        }

    async def attach_goal(
        self,
        user_id: str,
        goal: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Shadow: ensure goal links to ≥1 life_object_id (non-breaking)."""
        if not life_object_engine_enabled():
            return {"ok": True, "skipped": True, "reason": "life_object_engine_disabled"}

        goal_id = goal.get("id")
        if not goal_id:
            return {"ok": False, "error": "no_goal_id"}

        # Already linked?
        existing_loid = goal.get("life_object_id")
        if existing_loid:
            obj = await self.repo.get(user_id, existing_loid)
            if obj:
                link_goal(obj, goal_id)
                await self.repo.upsert(obj)
                return {"ok": True, "life_object_id": obj.id, "created": False, "linked": True}

        # Prefer travel/study artifact links
        if goal.get("travel_project_id"):
            objs = await self.repo.list_by_type(user_id, object_type="TRAVEL", limit=20)
            for o in objs:
                if (o.properties or {}).get("travel_project_id") == goal["travel_project_id"]:
                    link_goal(o, goal_id)
                    await self.repo.upsert(o)
                    await self._write_goal_life_object_id(user_id, goal_id, o.id)
                    return {"ok": True, "life_object_id": o.id, "created": False}

        if goal.get("study_plan_id"):
            for t in ("COURSE", "UNIVERSITY"):
                objs = await self.repo.list_by_type(user_id, object_type=t, limit=20)
                for o in objs:
                    if (o.properties or {}).get("study_plan_id") == goal["study_plan_id"]:
                        link_goal(o, goal_id)
                        await self.repo.upsert(o)
                        await self._write_goal_life_object_id(user_id, goal_id, o.id)
                        return {"ok": True, "life_object_id": o.id, "created": False}

        inferred = infer_object_type_for_goal(goal)
        if inferred:
            objs = await self.repo.list_by_type(user_id, object_type=inferred, limit=5)
            if len(objs) == 1:
                o = objs[0]
                link_goal(o, goal_id)
                await self.repo.upsert(o)
                await self._write_goal_life_object_id(user_id, goal_id, o.id)
                return {"ok": True, "life_object_id": o.id, "created": False, "inferred": inferred}

            # Create a lightweight object for the goal when none exist
            obj = LifeObject(
                user_id=user_id,
                type=inferred,  # type: ignore[arg-type]
                title=str(goal.get("title") or inferred)[:120],
                summary=str(goal.get("description") or goal.get("desired_outcome") or "")[:400],
                origin="goal",
                confidence=0.45,
                properties={"goal_id": goal_id, "goal_type": goal.get("goal_type")},
            )
            link_goal(obj, goal_id)
            append_history(obj, event="created", source="goal", source_id=goal_id, summary="From Goal Engine")
            await self.repo.upsert(obj)
            await self._write_goal_life_object_id(user_id, goal_id, obj.id)
            return {"ok": True, "life_object_id": obj.id, "created": True}

        return {"ok": True, "skipped": True, "reason": "no_inferable_object"}

    async def upsert_from_travel(
        self,
        user_id: str,
        project: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not life_object_engine_enabled():
            return {"ok": True, "skipped": True, "reason": "life_object_engine_disabled"}
        decision = reason_from_travel(project)
        match, _, _ = await self.deduper.find_match(
            user_id, object_type="TRAVEL", identity_keys=decision.identity_keys,
        )
        project_id = project.get("id")
        if match:
            res = await self._apply_update(
                match,
                title=decision.title,
                summary=decision.summary,
                properties=decision.properties_delta,
                identity_keys=decision.identity_keys,
                source="travel_project",
                source_id=project_id,
                improves=decision.improves,
                decision=decision,
            )
        else:
            obj = LifeObject(
                user_id=user_id,
                type="TRAVEL",
                title=decision.title,
                summary=decision.summary,
                properties=dict(decision.properties_delta or {}),
                identity_keys=dict(decision.identity_keys or {}),
                origin="travel_project",
                confidence=float(decision.confidence or 0.7),
                ai_summary=decision.summary,
                last_reasoning=decision.model_dump(),
            )
            if project_id and project_id not in obj.projects:
                obj.projects.append(project_id)
            append_history(
                obj, event="created", source="travel_project", source_id=project_id,
                summary="TRAVEL from Travel Project confirm",
            )
            await self.repo.upsert(obj)
            res = {"ok": True, "created": True, "object": obj.public(), "decision": decision.model_dump()}

        # Soft write-back on travel project
        lo_id = (res.get("object") or {}).get("id")
        if lo_id and project_id:
            try:
                await self.db.travel_projects.update_one(
                    {"id": project_id, "user_id": user_id},
                    {"$set": {"life_object_id": lo_id, "updated_at": now_iso()}},
                )
            except Exception:
                pass
        return res

    async def upsert_from_study(
        self,
        user_id: str,
        plan: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not life_object_engine_enabled():
            return {"ok": True, "skipped": True, "reason": "life_object_engine_disabled"}
        decision = reason_from_study(plan)
        match, _, _ = await self.deduper.find_match(
            user_id, object_type=decision.object_type, identity_keys=decision.identity_keys,
        )
        plan_id = plan.get("id")
        # Also try UNIVERSITY if COURSE miss with institution
        if not match and decision.identity_keys.get("institution"):
            match, _, _ = await self.deduper.find_match(
                user_id, object_type="UNIVERSITY", identity_keys=decision.identity_keys,
            )
            if match:
                decision.object_type = "UNIVERSITY"  # type: ignore[assignment]

        if match:
            res = await self._apply_update(
                match,
                title=decision.title or match.title,
                summary=decision.summary,
                properties=decision.properties_delta,
                identity_keys=decision.identity_keys,
                source="study_plan",
                source_id=plan_id,
                improves=decision.improves,
                decision=decision,
            )
        else:
            obj = LifeObject(
                user_id=user_id,
                type=decision.object_type,
                title=decision.title,
                summary=decision.summary,
                properties=dict(decision.properties_delta or {}),
                identity_keys=dict(decision.identity_keys or {}),
                origin="study_plan",
                confidence=float(decision.confidence or 0.7),
                last_reasoning=decision.model_dump(),
            )
            if plan_id and plan_id not in obj.projects:
                obj.projects.append(plan_id)
            append_history(
                obj, event="created", source="study_plan", source_id=plan_id,
                summary="UNIVERSITY/COURSE from Study Plan confirm",
            )
            await self.repo.upsert(obj)
            res = {"ok": True, "created": True, "object": obj.public(), "decision": decision.model_dump()}

        lo_id = (res.get("object") or {}).get("id")
        if lo_id and plan_id:
            try:
                await self.db.study_plans.update_one(
                    {"id": plan_id, "user_id": user_id},
                    {"$set": {"life_object_id": lo_id, "updated_at": now_iso()}},
                )
            except Exception:
                pass
        return res

    # --- Internals ---------------------------------------------------

    async def _write_goal_life_object_id(self, user_id: str, goal_id: str, life_object_id: str) -> None:
        try:
            await self.db.goals.update_one(
                {"id": goal_id, "user_id": user_id},
                {"$set": {"life_object_id": life_object_id, "updated_at": now_iso()}},
            )
        except Exception:
            logger.info("goal life_object_id write-back soft-fail", exc_info=True)

    def _apply_decision_side_effects(self, obj: LifeObject, decision) -> None:
        if decision.next_question:
            # Avoid duplicate pending questions
            texts = {q.question for q in (obj.pending_questions or [])}
            if decision.next_question not in texts:
                obj.pending_questions.append(
                    PendingQuestion(
                        question=decision.next_question,
                        why=decision.next_question_why or "",
                        priority="medium",
                    )
                )
            obj.next_reasoning = decision.next_question
        for title in (decision.suggested_actions or [])[:5]:
            titles = {a.title for a in (obj.suggested_actions or [])}
            if title not in titles:
                obj.suggested_actions.append(SuggestedAction(title=title, kind="from_document"))
        obj.last_reasoning = decision.model_dump()
        obj.ai_summary = decision.summary or obj.ai_summary
        obj.ai_confidence = float(decision.confidence or obj.ai_confidence)
        obj.ai_reasoning_version = AI_REASONING_VERSION

    def _refresh_health(self, obj: LifeObject) -> None:
        issues = []
        score = 0.5
        if obj.identity_keys:
            score += 0.2
        if obj.documents:
            score += min(0.2, 0.05 * len(obj.documents))
        if obj.status == "uncertain":
            issues.append("uncertain_identity")
            score -= 0.2
        if obj.merge_proposals:
            issues.append("pending_merge")
            score -= 0.1
        for w in (obj.last_reasoning or {}).get("worsens") or []:
            issues.append(str(w))
            score -= 0.05
        score = max(0.0, min(1.0, score))
        label = "healthy" if score >= 0.7 else ("ok" if score >= 0.45 else "attention")
        obj.health = LifeObjectHealth(score=score, label=label, issues=issues, updated_at=now_iso())

    async def _apply_update(
        self,
        obj: LifeObject,
        *,
        title: str,
        summary: str,
        properties: Optional[Dict[str, Any]],
        identity_keys: Dict[str, str],
        source: str,
        source_id: Optional[str] = None,
        improves: Optional[List[str]] = None,
        worsens: Optional[List[str]] = None,
        decision=None,
        decision_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if title and (not obj.title or obj.title == obj.type):
            obj.title = title
        if summary:
            obj.summary = summary
        props = dict(obj.properties or {})
        for k, v in (properties or {}).items():
            if v not in (None, "", [], {}):
                props[k] = v
        obj.properties = props
        ik = dict(obj.identity_keys or {})
        for k, v in (identity_keys or {}).items():
            if v and k not in ik:
                ik[k] = v
            elif v and k in ik and self.deduper.has_identity_conflict(obj, {k: v}):
                # Keep existing; record conflict in merge proposals
                obj.merge_proposals = list(obj.merge_proposals or []) + [{
                    "at": now_iso(),
                    "key": k,
                    "existing": ik.get(k),
                    "incoming": v,
                    "source": source,
                    "source_id": source_id,
                }]
            elif v:
                ik[k] = v
        obj.identity_keys = ik
        if source == "document" and source_id:
            link_document(obj, source_id)
        if source == "travel_project" and source_id and source_id not in obj.projects:
            obj.projects.append(source_id)
        if source == "study_plan" and source_id and source_id not in obj.projects:
            obj.projects.append(source_id)
        if decision is not None:
            self._apply_decision_side_effects(obj, decision)
        self._refresh_health(obj)
        append_history(
            obj,
            event="updated",
            source=source,
            source_id=source_id,
            summary=(decision.reason_summary if decision else "Updated") or "Updated",
            improves=list(improves or []),
            worsens=list(worsens or []),
            delta={
                "properties": properties or {},
                "amount": (properties or {}).get("amount_total"),
                "utility_type": (properties or {}).get("utility_type"),
                "meta": decision_meta or {},
            },
        )
        await self.repo.upsert(obj)
        try:
            await ensure_brain_node(life_graph=self.life_graph, obj=obj)
            if source == "document" and source_id:
                await ensure_object_doc_edge(
                    life_graph=self.life_graph, db=self.db, obj=obj, document_id=source_id,
                )
            await self.repo.upsert(obj)
        except Exception:
            pass
        out: Dict[str, Any] = {
            "ok": True,
            "created": False,
            "object": obj.public(),
        }
        if decision is not None:
            out["decision"] = decision.model_dump()
        return out
