"""Life OS plan/artifact service — execution infrastructure, not conversation brain."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from life_os.evidence import classify_evidence_refs, normalize_evidence_list
from life_os.models import (
    LifeOsArtifact,
    LifeOsPlan,
    PlanItem,
    new_item_id,
    now_iso,
)
from life_os.repository import LifeOsRepository

logger = logging.getLogger("ora.life_os")


class LifeOsService:
    def __init__(self, db):
        self.db = db
        self.repo = LifeOsRepository(db)

    async def ensure_indexes(self) -> None:
        await self.repo.ensure_indexes()

    async def create_plan(
        self,
        user_id: str,
        *,
        summary: str,
        desired_outcome: str = "",
        target_date: Optional[str] = None,
        constraints: Optional[List[str]] = None,
        strategy: str = "",
        items: Optional[List[Dict[str, Any]]] = None,
        evidence_refs: Optional[List[Any]] = None,
        conversation_session_id: Optional[str] = None,
        resolve_relative_days: Optional[int] = None,
    ) -> LifeOsPlan:
        td = _normalize_date(target_date)
        if td is None and resolve_relative_days is not None:
            td = (
                datetime.now(timezone.utc).date()
                + timedelta(days=int(resolve_relative_days))
            ).isoformat()

        plan_items = _parse_items(items or [])
        # Cap outline size — staged generation expects outline not full dump
        plan_items = plan_items[:21]
        # Default provenance: model assumptions unless caller set origin
        for it in plan_items:
            if not it.origin or it.origin == "generated":
                it.origin = "model_assumption"  # type: ignore[assignment]

        plan = LifeOsPlan(
            user_id=user_id,
            summary=(summary or "").strip()[:240] or "Piano",
            desired_outcome=(desired_outcome or "").strip()[:240],
            target_date=td,
            strategy=(strategy or "").strip()[:400],
            constraints=[str(c)[:120] for c in (constraints or [])][:12],
            items=plan_items,
            evidence_refs=normalize_evidence_list(evidence_refs),
            conversation_session_id=conversation_session_id,
            status="active",
        )
        goal_id = await self._upsert_goal(user_id, plan)
        plan.goal_id = goal_id
        await self.repo.insert_plan(plan)
        return plan

    async def update_plan(
        self,
        user_id: str,
        plan_id: str,
        *,
        patch: Optional[Dict[str, Any]] = None,
        item_updates: Optional[List[Dict[str, Any]]] = None,
        add_items: Optional[List[Dict[str, Any]]] = None,
        replace_items: Optional[List[Dict[str, Any]]] = None,
        remove_item_ids: Optional[List[str]] = None,
        reconciliation_mode: Optional[str] = None,
        preserve_compatible_progress: bool = True,
    ) -> Optional[LifeOsPlan]:
        """Update plan metadata and/or items.

        Mutation semantics (AI chooses via args):
        - add_items: append
        - item_updates / remove_item_ids: patch
        - replace_items: canonical item-set replacement (same plan id)
        reconciliation_mode is observational (preserve|patch|replace_scope|rebuild_from_evidence).
        """
        from life_os.evidence import merge_evidence_refs

        plan = await self.repo.get_plan(user_id, plan_id)
        if not plan:
            return None
        patch = patch or {}
        mode = str(reconciliation_mode or "").strip() or None
        if mode and mode not in (
            "preserve",
            "patch",
            "replace_scope",
            "rebuild_from_evidence",
        ):
            mode = "patch"

        retained: List[str] = []
        removed: List[str] = []
        added: List[str] = []

        if "summary" in patch and patch["summary"]:
            plan.summary = str(patch["summary"])[:240]
        if "desired_outcome" in patch:
            plan.desired_outcome = str(patch.get("desired_outcome") or "")[:240]
        if "strategy" in patch:
            plan.strategy = str(patch.get("strategy") or "")[:400]
        if "status" in patch and patch["status"] in (
            "active",
            "paused",
            "completed",
            "cancelled",
        ):
            plan.status = patch["status"]
        # Intentionally do NOT clear target_date / session / goal unless patch sets them
        if "target_date" in patch:
            plan.target_date = _normalize_date(patch.get("target_date"))
        if "constraints" in patch and isinstance(patch["constraints"], list):
            plan.constraints = [str(c)[:120] for c in patch["constraints"]][:12]
        if "evidence_refs" in patch:
            plan.evidence_refs = merge_evidence_refs(
                plan.evidence_refs,
                patch.get("evidence_refs") or [],
                supersede_prior_user_files=mode
                in ("replace_scope", "rebuild_from_evidence"),
            )

        by_id = {i.id: i for i in plan.items}

        # Canonical replace — keep same plan identity; optionally map progress by title
        if replace_items is not None:
            prior = list(plan.items)
            prior_by_title = {
                (i.title or "").strip().lower(): i for i in prior if (i.title or "").strip()
            }
            new_items = _parse_items(list(replace_items or []))
            # Prefer evidence-grounded origin when rebuilding
            default_origin = (
                "user_file"
                if mode in ("replace_scope", "rebuild_from_evidence")
                else "generated"
            )
            for it in new_items:
                if not it.origin or it.origin == "generated":
                    it.origin = default_origin  # type: ignore[assignment]
                if preserve_compatible_progress:
                    old = prior_by_title.get((it.title or "").strip().lower())
                    if old and old.status in ("completed", "in_progress", "skipped"):
                        it.status = old.status
                        if old.artifact_refs and not it.artifact_refs:
                            it.artifact_refs = list(old.artifact_refs)[:8]
                        retained.append(it.title)
                added.append(it.title)
            removed = [
                i.title
                for i in prior
                if (i.title or "").strip().lower()
                not in {(n.title or "").strip().lower() for n in new_items}
            ]
            # Preserve user_stated items not present in replace set unless rebuild
            if mode != "rebuild_from_evidence":
                keep_user = [
                    i
                    for i in prior
                    if i.origin == "user_stated"
                    and (i.title or "").strip().lower()
                    not in {(n.title or "").strip().lower() for n in new_items}
                ]
                if keep_user:
                    new_items = new_items + keep_user
                    for i in keep_user:
                        if i.title in removed:
                            removed.remove(i.title)
                        retained.append(i.title)
            plan.items = new_items[:40]
            op = "replace_items"
        else:
            op = "patch"
            for u in item_updates or []:
                if not isinstance(u, dict):
                    continue
                iid = str(u.get("id") or "")
                it = by_id.get(iid)
                if not it:
                    continue
                if u.get("title"):
                    it.title = str(u["title"])[:200]
                if "description" in u:
                    it.description = str(u.get("description") or "")[:600]
                if "due_date" in u:
                    it.due_date = _normalize_date(u.get("due_date"))
                if u.get("status") in (
                    "not_started",
                    "in_progress",
                    "completed",
                    "skipped",
                ):
                    it.status = u["status"]
                if isinstance(u.get("artifact_refs"), list):
                    it.artifact_refs = [str(x) for x in u["artifact_refs"]][:12]
                if u.get("origin") in (
                    "user_stated",
                    "user_file",
                    "external_evidence",
                    "model_assumption",
                    "inherited",
                    "generated",
                ):
                    it.origin = u["origin"]
                retained.append(it.title)

            drop = {str(x) for x in (remove_item_ids or []) if x}
            if drop:
                kept = []
                for i in plan.items:
                    if i.id in drop:
                        # Do not silently drop user_stated unless explicit rebuild intent
                        if i.origin == "user_stated" and mode != "rebuild_from_evidence":
                            kept.append(i)
                            retained.append(i.title)
                        else:
                            removed.append(i.title)
                    else:
                        kept.append(i)
                plan.items = kept

            for raw in add_items or []:
                if not isinstance(raw, dict) or not raw.get("title"):
                    continue
                origin = str(raw.get("origin") or "generated")
                if origin not in (
                    "user_stated",
                    "user_file",
                    "external_evidence",
                    "model_assumption",
                    "inherited",
                    "generated",
                ):
                    origin = "generated"
                plan.items.append(
                    PlanItem(
                        title=str(raw["title"])[:200],
                        description=str(raw.get("description") or "")[:600],
                        due_date=_normalize_date(raw.get("due_date")),
                        order=int(raw.get("order") or (len(plan.items) + 1)),
                        status="not_started",
                        origin=origin,  # type: ignore[arg-type]
                    )
                )
                added.append(str(raw["title"])[:200])
            plan.items = plan.items[:40]

        # Record last mutation for observability (not user-facing)
        meta = dict(plan.meta or {})
        meta["last_mutation"] = {
            "op": op,
            "reconciliation_mode": mode,
            "retained": retained[:20],
            "removed": removed[:20],
            "added": added[:20],
            "at": now_iso(),
        }
        plan.meta = meta
        plan.touch()
        await self.repo.save_plan(plan)
        await self._upsert_goal(user_id, plan)
        await self._close_orphaned_questions(user_id, plan)
        return plan

    async def _close_orphaned_questions(self, user_id: str, plan) -> None:
        """Work that has ended cannot still be waiting for something.

        A plan that is completed or cancelled — and an item that is finished or
        skipped — leaves any blocker attached to it with nothing left to
        unblock. Left alone those questions keep appearing on Home, asking
        someone to decide something that no longer has a decision in it.

        Soft-failing: a question that could not be closed is a stale row, and a
        stale row must never cost a plan its save.
        """
        try:
            from waiting.service import get_waiting_service

            svc = get_waiting_service(self.db)
            if plan.status in ("completed", "cancelled"):
                await svc.close_for_work(
                    user_id, plan_id=plan.id, reason=f"plan_{plan.status}"
                )
                return
            for it in plan.items or []:
                if it.status in ("completed", "skipped"):
                    await svc.close_for_work(
                        user_id, plan_item_id=it.id, reason=f"item_{it.status}"
                    )
        except Exception:
            logger.info("close orphaned questions soft-fail", exc_info=True)

    async def mark_item(
        self,
        user_id: str,
        plan_id: str,
        item_id: str,
        *,
        status: str,
    ) -> Optional[LifeOsPlan]:
        if status not in ("not_started", "in_progress", "completed", "skipped"):
            return None
        return await self.update_plan(
            user_id,
            plan_id,
            item_updates=[{"id": item_id, "status": status}],
        )

    async def create_actions_from_plan(
        self,
        user_id: str,
        plan_id: str,
        *,
        item_ids: Optional[List[str]] = None,
        horizon_days: int = 1,
    ) -> Dict[str, Any]:
        """Surface today's (or near) plan items as Decision actions for Home."""
        plan = await self.repo.get_plan(user_id, plan_id)
        if not plan:
            return {"ok": False, "error": "plan_not_found", "created": []}

        today = datetime.now(timezone.utc).date()
        selected: List[PlanItem] = []
        if item_ids:
            wanted = set(item_ids)
            selected = [i for i in plan.items if i.id in wanted]
        else:
            for i in sorted(plan.items, key=lambda x: (x.order, x.due_date or "")):
                if i.status not in ("not_started", "in_progress"):
                    continue
                if i.due_date:
                    try:
                        d = datetime.fromisoformat(i.due_date[:10]).date()
                    except Exception:
                        d = today
                    if 0 <= (d - today).days <= max(0, horizon_days):
                        selected.append(i)
                elif not selected:
                    selected.append(i)
                if len(selected) >= 3:
                    break

        created: List[str] = []
        try:
            from decision_engine.service import DecisionService

            ds = DecisionService(self.db)
            for it in selected[:3]:
                due = it.due_date or today.isoformat()
                workspace = f"/goal-workspace/{plan.id}"
                dec = await ds.create(
                    user_id,
                    {
                        "title": it.title[:160],
                        "description": (it.description or plan.summary)[:400],
                        "category": "generic",
                        "deadline": due if "T" in str(due) else f"{due}T12:00:00+00:00",
                        "metadata": {
                            "life_os_plan_id": plan.id,
                            "plan_item_id": it.id,
                            "goal_id": plan.goal_id,
                            "source": "life_os_plan",
                            "resume_kind": "life_os_plan",
                            "route": workspace,
                            "avoid_action_engine": True,
                            "conversation_session_id": plan.conversation_session_id,
                        },
                    },
                    origin="life_os",
                )
                did = (dec or {}).get("id") if isinstance(dec, dict) else None
                if did:
                    created.append(str(did))
                    linked = list(plan.meta.get("linked_decision_ids") or [])
                    if did not in linked:
                        linked.append(str(did))
                        plan.meta["linked_decision_ids"] = linked[-20:]
        except Exception as e:
            logger.info("create_actions soft-fail: %s", type(e).__name__)

        # Mark first selected as in_progress
        if selected and selected[0].status == "not_started":
            selected[0].status = "in_progress"
        await self.repo.save_plan(plan)
        await self._upsert_goal(user_id, plan)
        return {
            "ok": True,
            "plan_id": plan.id,
            "created_decision_ids": created,
            "item_ids": [i.id for i in selected],
        }

    async def save_artifact(self, art: LifeOsArtifact) -> LifeOsArtifact:
        """V2.3 legacy persist — prefer create_object / GenerativeObject."""
        await self.repo.save_artifact(art)
        if art.plan_id and art.plan_item_id:
            plan = await self.repo.get_plan(art.user_id, art.plan_id)
            if plan:
                for it in plan.items:
                    if it.id == art.plan_item_id and art.id not in it.artifact_refs:
                        it.artifact_refs.append(art.id)
                await self.repo.save_plan(plan)
        return art

    async def create_object(
        self,
        user_id: str,
        *,
        spec: Dict[str, Any],
        plan_id: Optional[str] = None,
        goal_id: Optional[str] = None,
        conversation_session_id: Optional[str] = None,
        evidence_refs: Optional[List[Any]] = None,
    ):
        from life_os.generative_models import GenerativeObject
        from life_os.generative_schema import (
            GenerativeValidationError,
            validate_generative_spec,
        )

        try:
            norm = validate_generative_spec(spec, require_content=True)
        except GenerativeValidationError as e:
            raise ValueError(f"{e.code}:{e.detail}") from e

        plan = None
        if plan_id:
            plan = await self.repo.get_plan(user_id, plan_id)
            if plan and not goal_id:
                goal_id = plan.goal_id
            if plan and not conversation_session_id:
                conversation_session_id = plan.conversation_session_id

        obj = GenerativeObject(
            user_id=user_id,
            plan_id=plan_id,
            goal_id=goal_id,
            conversation_session_id=conversation_session_id,
            title=norm["title"],
            purpose=norm["purpose"],
            object_kind=norm["object_kind"],
            content_schema=norm.get("content_schema") or {},
            content=norm["content"],
            interaction_schema=norm.get("interaction_schema") or {},
            presentation_hints=norm.get("presentation_hints") or {},
            evidence_refs=normalize_evidence_list(evidence_refs),
            provenance={
                "source": "ai_core",
                "evidence_quality": classify_evidence_refs(
                    normalize_evidence_list(evidence_refs)
                ),
            },
            generation_reason=norm.get("generation_reason") or "",
            status="ready",
        )
        await self.repo.insert_object(obj)
        if plan:
            refs = list(plan.meta.get("object_ids") or [])
            if obj.id not in refs:
                refs.append(obj.id)
                plan.meta["object_ids"] = refs[-40:]
                await self.repo.save_plan(plan)
        return obj

    async def update_object(
        self,
        user_id: str,
        object_id: str,
        *,
        patch: Optional[Dict[str, Any]] = None,
        replace_content: Optional[Dict[str, Any]] = None,
        replace_spec: Optional[Dict[str, Any]] = None,
        append_blocks: Optional[List[Dict[str, Any]]] = None,
        remove_block_ids: Optional[List[str]] = None,
        evidence_refs: Optional[List[Any]] = None,
        adaptation_note: Optional[str] = None,
        interaction_ref: Optional[str] = None,
        preserve_evidence: bool = True,
    ):
        from life_os.generative_schema import (
            GenerativeValidationError,
            validate_generative_spec,
        )

        obj = await self.repo.get_object(user_id, object_id)
        if not obj:
            return None
        patch = patch or {}
        prior_evidence = list(obj.evidence_refs or [])
        prior_prov = dict(obj.provenance or {})
        op_kind = "noop"

        # Block-level edits (compose into replace_content)
        if append_blocks or remove_block_ids:
            blocks = list((obj.content or {}).get("blocks") or [])
            if remove_block_ids:
                drop = {str(x) for x in remove_block_ids}
                blocks = [b for b in blocks if str(b.get("id") or "") not in drop]
                op_kind = "remove_blocks"
            if append_blocks:
                for b in append_blocks:
                    if isinstance(b, dict):
                        blocks.append(b)
                op_kind = "append_blocks" if op_kind == "noop" else "edit_blocks"
            replace_content = {
                **(obj.content or {}),
                "blocks": blocks,
                "schema_version": (obj.content or {}).get("schema_version") or 1,
            }

        if replace_spec and isinstance(replace_spec, dict):
            try:
                norm = validate_generative_spec(
                    {**obj.model_dump(), **replace_spec},
                    require_content=True,
                )
            except GenerativeValidationError as e:
                raise ValueError(f"{e.code}:{e.detail}") from e
            obj.title = norm["title"]
            obj.purpose = norm["purpose"]
            obj.object_kind = norm["object_kind"]
            obj.content = norm["content"]
            obj.interaction_schema = norm.get("interaction_schema") or {}
            obj.presentation_hints = norm.get("presentation_hints") or {}
            obj.generation_reason = norm.get("generation_reason") or obj.generation_reason
            op_kind = "replace_spec"
        elif replace_content and isinstance(replace_content, dict):
            try:
                norm = validate_generative_spec(
                    {
                        "title": obj.title,
                        "purpose": obj.purpose,
                        "object_kind": obj.object_kind,
                        "content": replace_content,
                    },
                    require_content=True,
                )
            except GenerativeValidationError as e:
                raise ValueError(f"{e.code}:{e.detail}") from e
            obj.content = norm["content"]
            if op_kind == "noop":
                op_kind = "replace_content"
        if patch.get("title"):
            obj.title = str(patch["title"])[:200]
            if op_kind == "noop":
                op_kind = "patch"
        if "purpose" in patch:
            obj.purpose = str(patch.get("purpose") or "")[:400]
            if op_kind == "noop":
                op_kind = "patch"
        if patch.get("status") in ("ready", "failed", "pending", "archived"):
            obj.status = patch["status"]
            if op_kind == "noop":
                op_kind = "patch"

        # Evidence: never strip silently; merge when provided
        if evidence_refs is not None:
            from life_os.evidence import merge_evidence_refs

            obj.evidence_refs = merge_evidence_refs(
                prior_evidence,
                evidence_refs,
                supersede_prior_user_files=True,
            )
        elif preserve_evidence and prior_evidence:
            obj.evidence_refs = prior_evidence

        content_changed = op_kind != "noop"
        if content_changed:
            prev = list((prior_prov.get("update_refs") or []))[-8:]
            prev.append({
                "at": now_iso(),
                "kind": op_kind,
                "adaptation_note": str(adaptation_note or "")[:240] or None,
                "interaction_ref": str(interaction_ref or "")[:80] or None,
                "from_revision": int(getattr(obj, "revision", None) or 1),
            })
            obj.provenance = {
                **prior_prov,
                "update_refs": prev,
                "source": prior_prov.get("source") or "ai_core",
                "evidence_quality": prior_prov.get("evidence_quality")
                or classify_evidence_refs(obj.evidence_refs),
            }
            if adaptation_note:
                obj.provenance["last_adaptation_note"] = str(adaptation_note)[:240]
            obj.touch(bump_revision=True)
        else:
            obj.touch()
        await self.repo.save_object(obj)
        return obj

    async def record_object_interaction(
        self,
        user_id: str,
        object_id: str,
        *,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        set_active_in_session: bool = True,
    ) -> Optional[Dict[str, Any]]:
        obj = await self.repo.get_object(user_id, object_id)
        if not obj:
            return None
        # Normalize common workspace signals (generic — not domain scoring)
        et = str(event_type or "interact")[:80]
        aliases = {
            "open": "object_opened",
            "opened": "object_opened",
            "view": "object_opened",
            "difficult": "marked_difficult",
            "easy": "marked_easy",
            "explain": "requested_explanation",
            "revise": "requested_revision",
            "simplify": "requested_revision",
        }
        et = aliases.get(et.lower(), et)
        ev = {
            "type": et,
            "payload": {
                str(k)[:40]: (
                    str(v)[:400] if not isinstance(v, (int, float, bool)) else v
                )
                for k, v in list((payload or {}).items())[:12]
            },
            "at": now_iso(),
        }
        events = list(obj.interaction_events or [])
        events.append(ev)
        obj.interaction_events = events[-40:]
        obj.touch()
        await self.repo.save_object(obj)

        session_id = obj.conversation_session_id
        if not session_id and obj.plan_id:
            plan = await self.repo.get_plan(user_id, obj.plan_id)
            if plan:
                session_id = plan.conversation_session_id
        if set_active_in_session and session_id:
            try:
                await self.bind_session_object_focus(
                    user_id,
                    session_id=session_id,
                    object_id=obj.id,
                    plan_id=obj.plan_id,
                    event_type=et,
                )
            except Exception as e:
                logger.info("session focus bind soft-fail: %s", type(e).__name__)

        return {
            "ok": True,
            "object_id": obj.id,
            "event": ev,
            "revision": getattr(obj, "revision", 1),
            "conversation_session_id": session_id,
        }

    async def bind_session_object_focus(
        self,
        user_id: str,
        *,
        session_id: str,
        object_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        plan_item_id: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update linked AI Core session conversational focus refs (non-domain)."""
        from conversation_engine.ai_core import state as state_mod
        from conversation_engine.ai_core.life_os_context import (
            object_ref,
            set_active_object_ref,
        )
        from conversation_engine.repository import ConversationRepository

        repo = ConversationRepository(self.db)
        sess = await repo.get(user_id, session_id)
        if not sess:
            return {"ok": False, "reason": "session_not_found"}
        st = state_mod.get_ai_state(sess)
        if plan_id:
            st["active_plan_id"] = plan_id
            plan = await self.repo.get_plan(user_id, plan_id)
            if plan:
                if plan.goal_id:
                    st["active_goal_id"] = plan.goal_id
                if plan_item_id:
                    item = next(
                        (i for i in (plan.items or []) if i.id == plan_item_id),
                        None,
                    )
                    if item:
                        st["current_plan_item_ref"] = {
                            "id": item.id,
                            "title": (item.title or "")[:120],
                            "due_date": item.due_date,
                            "status": item.status,
                        }
                elif not st.get("current_plan_item_ref"):
                    nxt = plan.next_open_item()
                    if nxt:
                        st["current_plan_item_ref"] = {
                            "id": nxt.id,
                            "title": (nxt.title or "")[:120],
                            "due_date": nxt.due_date,
                            "status": nxt.status,
                        }
        if object_id:
            obj = await self.repo.get_object(user_id, object_id)
            if obj:
                set_active_object_ref(st, object_ref(obj))
                if event_type:
                    notes = list(st.get("recent_object_interactions") or [])
                    notes.insert(
                        0,
                        {
                            "type": event_type,
                            "object_id": object_id,
                            "at": now_iso(),
                        },
                    )
                    st["recent_object_interactions"] = notes[:12]
        state_mod.save_ai_state(sess, st)
        await repo.replace(sess)
        return {
            "ok": True,
            "session_id": session_id,
            "active_object_ref": st.get("active_object_ref"),
            "active_plan_id": st.get("active_plan_id"),
            "current_plan_item_ref": st.get("current_plan_item_ref"),
        }

    async def get_plan(self, user_id: str, plan_id: str) -> Optional[LifeOsPlan]:
        return await self.repo.get_plan(user_id, plan_id)

    async def get_active_bundle(
        self, user_id: str, *, plan_id: Optional[str] = None
    ) -> Dict[str, Any]:
        if plan_id:
            plan = await self.repo.get_plan(user_id, plan_id)
            plans = [plan] if plan else []
        else:
            plans = await self.repo.list_active_plans(user_id, limit=5)
        if not plans:
            return {"ok": True, "plan": None, "objects": [], "artifacts": []}
        plan = plans[0]
        objs = await self.repo.list_objects_for_plan(user_id, plan.id, limit=20)
        # Legacy V2.3 artifacts — read-only surface for QA data
        arts = await self.repo.list_artifacts_for_plan(user_id, plan.id, limit=10)
        quality = classify_evidence_refs(plan.evidence_refs)
        from life_os.evidence import public_evidence_sources

        combined_ev = list(plan.evidence_refs or [])
        for o in objs:
            combined_ev.extend(list(getattr(o, "evidence_refs", None) or []))
        return {
            "ok": True,
            "plan": plan.public(),
            "next_item": (plan.next_open_item().model_dump() if plan.next_open_item() else None),
            "today_items": [i.model_dump() for i in plan.today_items()],
            "objects": [o.public() for o in objs],
            "artifacts": [a.public() for a in arts],
            "evidence_quality": quality,
            "public_sources": public_evidence_sources(combined_ev),
            "progress_ratio": plan.progress_ratio(),
            "workspace_route": f"/goal-workspace/{plan.id}",
        }

    async def _upsert_goal(self, user_id: str, plan: LifeOsPlan) -> Optional[str]:
        try:
            from goal_engine.models import GoalCreateBody, GoalPatchBody
            from goal_engine.service import GoalService

            gs = GoalService(self.db)
            next_it = plan.next_open_item()
            next_action = (next_it.title if next_it else None) or plan.summary
            if plan.goal_id:
                await gs.patch(
                    user_id,
                    plan.goal_id,
                    GoalPatchBody(
                        title=plan.summary[:160],
                        description=plan.desired_outcome[:400] or None,
                        status="active" if plan.status == "active" else "paused",
                        next_action=next_action[:200],
                        target_date=plan.target_date,
                        desired_outcome=plan.desired_outcome[:240] or None,
                    ),
                )
                return plan.goal_id
            g = await gs.create(
                user_id,
                GoalCreateBody(
                    title=plan.summary[:160],
                    goal_type="generic",
                    description=plan.desired_outcome[:400] or None,
                    status="active",
                    desired_outcome=plan.desired_outcome[:240] or None,
                    next_action=next_action[:200],
                    target_date=plan.target_date,
                    idempotency_key=f"life_os_plan:{plan.id}",
                    created_from={
                        "source_type": "life_os_plan",
                        "source_id": plan.id,
                        "artifact": "life_os_plan",
                    },
                ),
            )
            gid = getattr(g, "id", None) or (g.get("id") if isinstance(g, dict) else None)
            return str(gid) if gid else None
        except Exception as e:
            logger.info("goal upsert soft-fail: %s", type(e).__name__)
            return plan.goal_id


def _normalize_date(raw: Any) -> Optional[str]:
    if raw is None or raw == "":
        return None
    s = str(raw).strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    # relative like "+10d" not invented — only ISO
    return None


def _parse_items(raw_items: List[Dict[str, Any]]) -> List[PlanItem]:
    out: List[PlanItem] = []
    for idx, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "").strip()
        if not title:
            continue
        origin = str(raw.get("origin") or "generated")
        if origin not in (
            "user_stated",
            "user_file",
            "external_evidence",
            "model_assumption",
            "inherited",
            "generated",
        ):
            origin = "generated"
        out.append(
            PlanItem(
                id=str(raw.get("id") or new_item_id()),
                title=title[:200],
                description=str(raw.get("description") or "")[:600],
                due_date=_normalize_date(raw.get("due_date") or raw.get("date")),
                order=int(raw.get("order") if raw.get("order") is not None else idx),
                status=(
                    raw["status"]
                    if raw.get("status")
                    in ("not_started", "in_progress", "completed", "skipped")
                    else "not_started"
                ),
                artifact_refs=[str(x) for x in (raw.get("artifact_refs") or [])][:8],
                evidence_refs=[str(x) for x in (raw.get("evidence_refs") or [])][:8],
                origin=origin,  # type: ignore[arg-type]
                meta=dict(raw.get("meta") or {}) if isinstance(raw.get("meta"), dict) else {},
            )
        )
    return out
