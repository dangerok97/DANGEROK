"""LifeObjectService — CRUD, upsert from sources, merge, reason (shadow mode)."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from life_objects.assimilation import document_assimilates_into_home
from life_objects.deduplication import LifeObjectDeduper, extract_identity_keys_from_reasoning
from life_objects.enrichment import refresh_enrichment
from life_objects.identity_state import apply_identity_state_migration, apply_properties_delta
from life_objects.link_states import should_assimilate, should_propose_merge
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
    LifeObjectPatchBody,
    PendingQuestion,
    SuggestedAction,
    now_iso,
)
from life_objects.provenance import ensure_provenance_fields
from life_objects.reasoner import (
    infer_object_type_for_goal,
    reason_from_document,
    reason_from_study,
    reason_from_travel,
)
from life_objects.repository import LifeObjectRepository
from life_objects.semantic_validator import validate_before_persist, validate_decision_consultant
from life_objects.title_generator import generate_canonical_title

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
            identity=dict(body.identity or {}),
            state=dict(body.state or {}),
            identity_keys=dict(body.identity_keys or {}),
            origin=body.origin or "api",
            confidence=body.confidence,
        )
        apply_identity_state_migration(obj)
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
        existing_titles = [o.title for o in await self.repo.list_by_type(user_id, object_type=obj.type, limit=50)]
        vr = validate_before_persist(
            obj,
            properties_delta=obj.properties,
            incoming_identity_keys=obj.identity_keys,
            existing_titles=existing_titles,
            ai_suggested_title=body.title,
            ai_suggested_type=body.type,
        )
        obj = vr.obj
        obj.last_validation = {
            "corrections": vr.corrections,
            "link_state": vr.link_state,
            "title": vr.title,
        }
        ensure_provenance_fields(obj)
        append_history(obj, event="created", source="api", summary="Created via API")
        await self._best_effort_enrich(obj)
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
        apply_identity_state_migration(obj)
        append_history(obj, event="patched", source="api", summary="Patched via API", delta=data)
        await self._best_effort_enrich(obj)
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

    # --- Enrichment API helpers --------------------------------------

    async def get_history(self, user_id: str, object_id: str) -> Dict[str, Any]:
        obj = await self.repo.get(user_id, object_id)
        if not obj:
            return {"ok": False, "error": "not_found"}
        return {
            "ok": True,
            "object_id": object_id,
            "history": [h.model_dump() for h in (obj.history or [])],
            "count": len(obj.history or []),
        }

    async def get_relationships(self, user_id: str, object_id: str) -> Dict[str, Any]:
        obj = await self.repo.get(user_id, object_id)
        if not obj:
            return {"ok": False, "error": "not_found"}
        return {
            "ok": True,
            "object_id": object_id,
            "relationships": [r.model_dump() for r in (obj.relationships or [])],
            "count": len(obj.relationships or []),
        }

    async def refresh_section(
        self,
        user_id: str,
        object_id: str,
        *,
        sections: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        obj = await self.repo.get(user_id, object_id)
        if not obj:
            return {"ok": False, "error": "not_found"}
        await refresh_enrichment(obj, sections=sections)
        await self.repo.upsert(obj)
        return {"ok": True, "object": obj.public(), "sections": sections or ["all"]}

    async def get_narrative(self, user_id: str, object_id: str, *, refresh: bool = False) -> Dict[str, Any]:
        if refresh:
            res = await self.refresh_section(user_id, object_id, sections=["narrative"])
            if not res.get("ok"):
                return res
            obj = res["object"]
        else:
            obj = await self.get(user_id, object_id)
            if not obj:
                return {"ok": False, "error": "not_found"}
        return {"ok": True, "object_id": object_id, "narrative": obj.get("narrative") or {}}

    async def get_questions(self, user_id: str, object_id: str, *, refresh: bool = False) -> Dict[str, Any]:
        if refresh:
            res = await self.refresh_section(user_id, object_id, sections=["questions"])
            if not res.get("ok"):
                return res
            obj = res["object"]
        else:
            obj = await self.get(user_id, object_id)
            if not obj:
                return {"ok": False, "error": "not_found"}
        return {
            "ok": True,
            "object_id": object_id,
            "pending_questions": obj.get("pending_questions") or [],
        }

    async def get_insights(self, user_id: str, object_id: str, *, refresh: bool = False) -> Dict[str, Any]:
        if refresh:
            res = await self.refresh_section(user_id, object_id, sections=["insights", "temporal"])
            if not res.get("ok"):
                return res
            obj = res["object"]
        else:
            obj = await self.get(user_id, object_id)
            if not obj:
                return {"ok": False, "error": "not_found"}
        return {
            "ok": True,
            "object_id": object_id,
            "insights": obj.get("insights") or [],
            "temporal": obj.get("temporal"),
        }

    async def get_health(self, user_id: str, object_id: str, *, refresh: bool = False) -> Dict[str, Any]:
        if refresh:
            res = await self.refresh_section(user_id, object_id, sections=["health"])
            if not res.get("ok"):
                return res
            obj = res["object"]
        else:
            obj = await self.get(user_id, object_id)
            if not obj:
                return {"ok": False, "error": "not_found"}
        return {"ok": True, "object_id": object_id, "health": obj.get("health") or {}}

    async def home_v3_feed(self, user_id: str, *, limit: int = 20) -> Dict[str, Any]:
        from life_objects.home_v3 import serialize_home_v3_feed

        objs = await self.list_objects(user_id, status="active", limit=limit)
        feed = serialize_home_v3_feed(objs)
        return feed or {"enabled": False, "cards": []}

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
        decision = validate_decision_consultant(
            decision,
            document_type=str(reasoning.get("document_type") or ""),
            domain=str(reasoning.get("domain") or ""),
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

        from life_objects.link_states import classify_link_state

        doc_type = str(reasoning.get("document_type") or "").lower()
        merge_pool = list(all_cands) or list(candidates_objs)
        if decision.object_id and not any(c.id == decision.object_id for c in merge_pool):
            by_id = await self.repo.get(user_id, decision.object_id)
            if by_id:
                merge_pool.append(by_id)

        # Soft-address assimilate home docs into the single existing HOME
        if (
            not match
            and document_assimilates_into_home(doc_type)
            and decision.object_type == "HOME"
        ):
            same_homes = [c for c in candidates_objs if c.type == "HOME" and c.status == "active"]
            if len(same_homes) == 1 and identity_keys.get("address_norm"):
                only = same_homes[0]
                old_addr = (only.identity_keys or {}).get("address_norm") or ""
                new_addr = identity_keys.get("address_norm") or ""
                if old_addr and new_addr and (old_addr in new_addr or new_addr in old_addr):
                    match = only

        # REAL_CONFLICT → user-facing; LINK_PROBABLE/CONFIRMED → quiet assimilate
        if match or decision.action in ("propose_merge", "update"):
            primary = match or (merge_pool[0] if merge_pool else None)
            if primary:
                link_state = classify_link_state(
                    object_type=decision.object_type,
                    existing_keys=dict(primary.identity_keys or {}),
                    incoming_keys=identity_keys,
                )
                hard_conflict = link_state == "REAL_CONFLICT" or (
                    len(all_cands) > 1
                    and any(self.deduper.has_identity_conflict(c, identity_keys) for c in all_cands)
                )
                if hard_conflict and should_propose_merge(link_state):
                    cand_ids = [c.id for c in merge_pool] or [primary.id]
                    proposal = {
                        "at": now_iso(),
                        "document_id": document_id,
                        "candidate_ids": cand_ids,
                        "incoming_keys": identity_keys,
                        "reason": decision.reason_summary or "REAL_CONFLICT",
                        "link_state": "REAL_CONFLICT",
                        "conflict": True,
                    }
                    primary.merge_proposals = list(primary.merge_proposals or []) + [proposal]
                    append_history(
                        primary,
                        event="merge_proposed",
                        source="document",
                        source_id=document_id,
                        summary=proposal["reason"],
                        delta={"incoming_keys": identity_keys, "link_state": "REAL_CONFLICT"},
                    )
                    if document_id:
                        link_document(primary, document_id)
                    await self._run_semantic_validate(
                        primary,
                        decision=decision,
                        document_type=doc_type,
                        document_id=document_id,
                        existing_match=primary,
                        identity_keys=identity_keys,
                        properties_delta=decision.properties_delta,
                    )
                    await self._best_effort_enrich(primary)
                    await self.repo.upsert(primary)
                    return {
                        "ok": True,
                        "created": False,
                        "merge_proposed": True,
                        "link_state": "REAL_CONFLICT",
                        "object": primary.public(),
                        "candidates": cand_ids,
                        "decision": decision.model_dump(),
                    }
                if should_assimilate(link_state) or match:
                    target = match or primary
                    result = await self._apply_update(
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
                        document_type=doc_type,
                        link_state=link_state,
                    )
                    result["link_state"] = link_state
                    result["assimilated"] = True
                    return result
                if decision.action == "propose_merge" and not match:
                    primary.pending_links = list(primary.pending_links or []) + [{
                        "at": now_iso(),
                        "document_id": document_id,
                        "link_state": link_state,
                        "incoming_keys": identity_keys,
                    }]
                    result = await self._apply_update(
                        primary,
                        title=decision.title or primary.title,
                        summary=decision.summary or primary.summary,
                        properties=decision.properties_delta,
                        identity_keys=identity_keys,
                        source="document",
                        source_id=document_id,
                        improves=decision.improves,
                        worsens=decision.worsens,
                        decision=decision,
                        document_type=doc_type,
                        link_state=link_state,
                    )
                    result["link_state"] = link_state
                    if link_state == "LINK_UNCERTAIN":
                        result["merge_proposed"] = True
                    return result
                decision.action = "uncertain"  # type: ignore[assignment]

        if decision.action == "uncertain" and not match:
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
            apply_properties_delta(obj, decision.properties_delta or {})
            await self._run_semantic_validate(
                obj,
                decision=decision,
                document_type=doc_type,
                document_id=document_id,
                identity_keys=identity_keys,
                properties_delta=decision.properties_delta,
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
            await self._best_effort_enrich(obj)
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
                    document_type=doc_type,
                )

        # Create new — validator ALWAYS before persist
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
        apply_properties_delta(obj, decision.properties_delta or {})
        await self._run_semantic_validate(
            obj,
            decision=decision,
            document_type=doc_type,
            document_id=document_id,
            identity_keys=identity_keys,
            properties_delta=decision.properties_delta,
        )
        if document_id:
            link_document(obj, document_id)
        self._apply_decision_side_effects(obj, decision)
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
                "amount": (decision.properties_delta or {}).get("amount_total")
                or (decision.properties_delta or {}).get("utility_amount"),
                "utility_type": (decision.properties_delta or {}).get("utility_type"),
            },
        )
        await self._best_effort_enrich(obj)
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
            apply_properties_delta(obj, obj.properties)
            link_goal(obj, goal_id)
            append_history(obj, event="created", source="goal", source_id=goal_id, summary="From Goal Engine")
            await self._best_effort_enrich(obj)
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
            apply_properties_delta(obj, decision.properties_delta or {})
            await self._run_semantic_validate(
                obj,
                decision=decision,
                identity_keys=decision.identity_keys,
                properties_delta=decision.properties_delta,
            )
            if project_id and project_id not in obj.projects:
                obj.projects.append(project_id)
            append_history(
                obj, event="created", source="travel_project", source_id=project_id,
                summary="TRAVEL from Travel Project confirm",
            )
            await self._best_effort_enrich(obj)
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
            apply_properties_delta(obj, decision.properties_delta or {})
            await self._run_semantic_validate(
                obj,
                decision=decision,
                identity_keys=decision.identity_keys,
                properties_delta=decision.properties_delta,
            )
            if plan_id and plan_id not in obj.projects:
                obj.projects.append(plan_id)
            append_history(
                obj, event="created", source="study_plan", source_id=plan_id,
                summary="UNIVERSITY/COURSE from Study Plan confirm",
            )
            await self._best_effort_enrich(obj)
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
        from life_objects.assimilation import mortgage_assimilated
        from life_objects.knowledge_gaps import concept_satisfied

        if decision.next_question:
            qtext = (decision.next_question or "").strip().lower()
            ban = False
            if concept_satisfied(obj, "cadastral") and (
                "catastale" in qtext or "catasto" in qtext or "foglio" in qtext
            ):
                ban = True
            if (mortgage_assimilated(obj) or concept_satisfied(obj, "mortgage")) and (
                "hai un mutuo" in qtext or "mutuo su questa casa" in qtext
            ):
                ban = True
            texts = {q.question for q in (obj.pending_questions or [])}
            if not ban and decision.next_question not in texts:
                obj.pending_questions.append(
                    PendingQuestion(
                        question=decision.next_question,
                        why=decision.next_question_why or "",
                        priority="medium",
                        category="missing_info",
                        source="reasoner",
                    )
                )
            if not ban:
                obj.next_reasoning = decision.next_question
        for title in (decision.suggested_actions or [])[:5]:
            titles = {a.title for a in (obj.suggested_actions or [])}
            if title not in titles:
                obj.suggested_actions.append(SuggestedAction(title=title, kind="from_document"))
        obj.last_reasoning = decision.model_dump()
        obj.ai_summary = decision.summary or obj.ai_summary
        obj.ai_confidence = float(decision.confidence or obj.ai_confidence)
        obj.ai_reasoning_version = AI_REASONING_VERSION

    async def _best_effort_enrich(self, obj: LifeObject) -> None:
        """Refresh narrative/questions/insights/health — never break consume path."""
        try:
            await refresh_enrichment(obj)
        except Exception as e:
            logger.info("life_object enrichment soft-fail: %s", type(e).__name__)

    async def _run_semantic_validate(
        self,
        obj: LifeObject,
        *,
        decision=None,
        document_type: str = "",
        document_id: Optional[str] = None,
        existing_match: Optional[LifeObject] = None,
        identity_keys: Optional[Dict[str, str]] = None,
        properties_delta: Optional[Dict[str, Any]] = None,
        link_state: Optional[str] = None,
    ) -> LifeObject:
        """Semantic Validator ALWAYS before persist — backend final authority."""
        existing_titles: List[str] = []
        try:
            peers = await self.repo.list_by_type(obj.user_id, object_type=obj.type, limit=40)
            existing_titles = [p.title for p in peers if p.id != obj.id]
        except Exception:
            pass
        vr = validate_before_persist(
            obj,
            decision=decision,
            document_type=document_type,
            document_id=document_id,
            existing_match=existing_match,
            incoming_identity_keys=identity_keys,
            properties_delta=properties_delta,
            existing_titles=existing_titles,
            ai_suggested_title=(decision.title if decision else obj.title),
            ai_suggested_type=(decision.object_type if decision else obj.type),
        )
        obj = vr.obj
        kind = (vr.assimilation or {}).get("kind")
        if kind and kind not in (obj.assimilated_kinds or []):
            obj.assimilated_kinds = list(obj.assimilated_kinds or []) + [kind]
        obj.last_validation = {
            "corrections": vr.corrections,
            "link_state": link_state or vr.link_state,
            "title": vr.title,
            "assimilation": vr.assimilation,
            "user_facing_conflict": vr.user_facing_conflict,
        }
        ensure_provenance_fields(obj)
        return obj

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
        document_type: str = "",
        link_state: Optional[str] = None,
    ) -> Dict[str, Any]:
        if summary:
            obj.summary = summary
        apply_properties_delta(obj, properties or {})
        ik = dict(obj.identity_keys or {})
        for k, v in (identity_keys or {}).items():
            if not v:
                continue
            old = ik.get(k)
            if not old:
                ik[k] = v
                continue
            if old == v:
                continue
            # Soft address variants: keep richer (longer) form, never REAL_CONFLICT
            if k == "address_norm" and self.deduper._address_soft_equal(old, v):
                ik[k] = old if len(old) >= len(v) else v
                continue
            if self.deduper.has_identity_conflict(obj, {k: v}):
                obj.merge_proposals = list(obj.merge_proposals or []) + [{
                    "at": now_iso(),
                    "key": k,
                    "existing": old,
                    "incoming": v,
                    "source": source,
                    "source_id": source_id,
                    "link_state": "REAL_CONFLICT",
                    "conflict": True,
                }]
            else:
                ik[k] = v
        obj.identity_keys = ik

        doc_type = document_type or str((properties or {}).get("document_type") or "")
        obj = await self._run_semantic_validate(
            obj,
            decision=decision,
            document_type=doc_type,
            document_id=source_id if source == "document" else None,
            existing_match=obj,
            identity_keys=identity_keys,
            properties_delta=properties,
            link_state=link_state,
        )
        # Validator owns title; hard-block HOME+Lavoro
        if obj.type == "HOME" and (obj.title or "").strip().lower() in ("lavoro", "job", "work"):
            obj.title = generate_canonical_title(
                "HOME",
                identity=obj.identity,
                state=obj.state,
                properties=obj.properties,
                identity_keys=obj.identity_keys,
            )
        elif not obj.title or obj.title == obj.type:
            obj.title = generate_canonical_title(
                obj.type,
                identity=obj.identity,
                state=obj.state,
                properties=obj.properties,
                identity_keys=obj.identity_keys,
            )
        # Ignore AI title for HOME (already regenerated); for others only if still empty
        _ = title

        if source == "document" and source_id:
            link_document(obj, source_id)
        if source == "travel_project" and source_id and source_id not in obj.projects:
            obj.projects.append(source_id)
        if source == "study_plan" and source_id and source_id not in obj.projects:
            obj.projects.append(source_id)
        if decision is not None:
            self._apply_decision_side_effects(obj, decision)
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
                "amount": (properties or {}).get("amount_total")
                or (properties or {}).get("utility_amount"),
                "utility_type": (properties or {}).get("utility_type"),
                "meta": decision_meta or {},
                "link_state": (obj.last_validation or {}).get("link_state"),
                "assimilation": (obj.last_validation or {}).get("assimilation"),
            },
        )
        await self._best_effort_enrich(obj)
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
        if obj.last_validation:
            out["validation"] = obj.last_validation
        return out
