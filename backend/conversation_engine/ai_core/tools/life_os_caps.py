"""AI Core capabilities wrapping Life OS execution (no domain flows)."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from conversation_engine.ai_core.models import Observation
from life_os.evidence import (
    calibration_note_for_ai,
    classify_evidence_refs,
    conversational_evidence_ref,
)
from life_os.service import LifeOsService

logger = logging.getLogger("ora.ai_core.life_os_caps")


def _svc(db) -> LifeOsService:
    return LifeOsService(db)


async def create_plan(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    if not uid or db is None:
        return _fail("create_plan", "NOT_CONFIGURED")
    try:
        plan = await _svc(db).create_plan(
            uid,
            summary=str(arguments.get("goal") or arguments.get("summary") or ""),
            desired_outcome=str(arguments.get("desired_outcome") or ""),
            target_date=arguments.get("target_date"),
            target=arguments.get("target"),
            constraints=list(arguments.get("constraints") or []),
            strategy=str(arguments.get("strategy") or ""),
            items=list(arguments.get("items") or []),
            evidence_refs=list(arguments.get("evidence_refs") or []),
            conversation_session_id=runtime.get("session_id"),
            resolve_relative_days=_as_int(arguments.get("resolve_relative_days")),
        )
        return Observation(
            kind="tool",
            name="create_plan",
            status="ok",
            payload={
                "capability": "create_plan",
                "status": "success",
                "created_refs": [plan.id, plan.goal_id],
                "plan_id": plan.id,
                "goal_id": plan.goal_id,
                "item_count": len(plan.items),
                "target_date": plan.target_date,
                "workspace_route": f"/goal-workspace/{plan.id}",
                "summary": f"Created {len(plan.items)}-item plan",
                "evidence_quality": classify_evidence_refs(plan.evidence_refs),
                "memory_eligible": False,
            },
            provenance=[plan.id],
        )
    except Exception as e:
        logger.info("create_plan fail: %s", type(e).__name__)
        return _fail("create_plan", "PROVIDER_ERROR", detail=type(e).__name__)


async def update_plan(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    plan_id = str(arguments.get("plan_id") or "")
    if not uid or db is None or not plan_id:
        return _fail("update_plan", "INVALID_RESPONSE")
    replace_items = arguments.get("replace_items")
    if replace_items is not None and not isinstance(replace_items, list):
        replace_items = None
    remove_item_ids = arguments.get("remove_item_ids")
    if not isinstance(remove_item_ids, list):
        remove_item_ids = None
    mode = str(arguments.get("reconciliation_mode") or "") or None
    prior = await _svc(db).repo.get_plan(uid, plan_id)
    prior_titles = [i.title for i in (prior.items if prior else [])]
    prior_target = prior.target_date if prior else None
    prior_goal = prior.goal_id if prior else None
    prior_sess = prior.conversation_session_id if prior else None
    patch = dict(arguments.get("patch") or {})
    evidence = list(arguments.get("evidence_refs") or [])
    if isinstance(patch.get("evidence_refs"), list):
        evidence = list(patch.get("evidence_refs") or []) + evidence
    fact = str(
        arguments.get("user_fact_summary")
        or arguments.get("conversational_fact")
        or ""
    ).strip()
    if fact:
        evidence.append(
            conversational_evidence_ref(
                summary=fact,
                session_id=str(runtime.get("session_id") or ""),
                turn_or_epoch=str(runtime.get("reasoning_epoch") or ""),
            )
        )
    if evidence:
        patch["evidence_refs"] = evidence
    plan = await _svc(db).update_plan(
        uid,
        plan_id,
        patch=patch,
        item_updates=list(arguments.get("item_updates") or []),
        add_items=list(arguments.get("add_items") or []),
        replace_items=replace_items,
        remove_item_ids=remove_item_ids,
        reconciliation_mode=mode,
        preserve_compatible_progress=arguments.get("preserve_compatible_progress", True)
        is not False,
    )
    if not plan:
        return _fail("update_plan", "UNSUPPORTED", detail="plan_not_found")
    mut = (plan.meta or {}).get("last_mutation") or {}
    op = mut.get("op") or (
        "replace_items" if replace_items is not None else "patch"
    )
    return Observation(
        kind="tool",
        name="update_plan",
        status="ok",
        payload={
            "capability": "update_plan",
            "status": "success",
            "operation": op,
            "reconciliation_mode": mut.get("reconciliation_mode") or mode,
            "plan_id": plan.id,
            "item_count": len(plan.items),
            "progress_ratio": plan.progress_ratio(),
            "retained": mut.get("retained") or [],
            "removed": mut.get("removed") or [],
            "added": mut.get("added") or [],
            "identity_preserved": {
                "plan_id": True,
                "target_date": plan.target_date == prior_target,
                "goal_id": plan.goal_id == prior_goal,
                "conversation_session_id": plan.conversation_session_id == prior_sess,
            },
            "prior_item_count": len(prior_titles),
            "summary": "Plan updated",
            "memory_eligible": False,
            "honesty": "Only claim plan changes that appear in this observation.",
        },
        provenance=[plan.id],
    )


async def create_actions(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    plan_id = str(arguments.get("plan_id") or "")
    if not uid or db is None or not plan_id:
        return _fail("create_actions", "INVALID_RESPONSE")
    res = await _svc(db).create_actions_from_plan(
        uid,
        plan_id,
        item_ids=list(arguments.get("item_ids") or []) or None,
        horizon_days=int(arguments.get("horizon_days") or 1),
    )
    if not res.get("ok"):
        return _fail("create_actions", "UNSUPPORTED", detail=str(res.get("error")))
    return Observation(
        kind="tool",
        name="create_actions",
        status="ok",
        payload={
            "capability": "create_actions",
            "status": "success",
            "created_refs": res.get("created_decision_ids") or [],
            "plan_id": plan_id,
            "item_ids": res.get("item_ids") or [],
            "workspace_route": f"/goal-workspace/{plan_id}",
            "summary": f"Created {len(res.get('created_decision_ids') or [])} Home actions",
            "memory_eligible": False,
            "note": "Actions open Goal Workspace — not legacy Action Engine.",
        },
        provenance=[plan_id],
    )


async def create_object(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    """Persist an AI-authored GenerativeObject (declarative UI blocks)."""
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    if not uid or db is None:
        return _fail("create_object", "NOT_CONFIGURED")

    # Accept either nested `spec` or flat fields
    spec = dict(arguments.get("spec") or {})
    for k in (
        "title",
        "purpose",
        "object_kind",
        "content",
        "content_schema",
        "interaction_schema",
        "presentation_hints",
        "generation_reason",
    ):
        if k in arguments and k not in spec:
            spec[k] = arguments[k]

    plan_id = str(
        arguments.get("plan_ref") or arguments.get("plan_id") or spec.get("plan_id") or ""
    ) or None
    try:
        obj = await _svc(db).create_object(
            uid,
            spec=spec,
            plan_id=plan_id,
            goal_id=str(arguments.get("goal_ref") or arguments.get("goal_id") or "") or None,
            conversation_session_id=runtime.get("session_id"),
            evidence_refs=list(arguments.get("evidence_refs") or []),
        )
    except ValueError as e:
        msg = str(e)
        code = msg.split(":", 1)[0] if ":" in msg else "INVALID_RESPONSE"
        return Observation(
            kind="error",
            name="create_object",
            status="failed",
            payload={
                "capability": "create_object",
                "status": "failed",
                "failure_code": code,
                "detail": msg,
                "repair_hint": (
                    "Fix the declarative content.blocks using only allowed UI primitives "
                    "(text, heading, section, card_deck, timeline, task_group, "
                    "relation_graph, question, …). No executable code."
                ),
                "memory_eligible": False,
            },
        )
    except Exception as e:
        logger.info("create_object fail: %s", type(e).__name__)
        return _fail("create_object", "PROVIDER_ERROR", detail=type(e).__name__)

    blocks = (obj.content or {}).get("blocks") or []
    return Observation(
        kind="tool",
        name="create_object",
        status="ok",
        payload={
            "capability": "create_object",
            "status": "success",
            "created_refs": [obj.id],
            "object_id": obj.id,
            "plan_id": obj.plan_id,
            "goal_id": obj.goal_id,
            "object_kind": obj.object_kind,
            "title": obj.title,
            "blocks_n": len(blocks),
            "workspace_route": (
                f"/goal-workspace/{obj.plan_id}" if obj.plan_id else None
            ),
            "calibration_note": calibration_note_for_ai(
                (obj.provenance or {}).get("evidence_quality") or {}
            ),
            "summary": f"Created generative object ({len(blocks)} blocks)",
            "memory_eligible": False,
        },
        provenance=[obj.id],
    )


async def update_object(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    object_id = str(arguments.get("object_id") or arguments.get("id") or "")
    if not uid or db is None or not object_id:
        return _fail("update_object", "INVALID_RESPONSE")
    append_blocks = arguments.get("append_blocks")
    if not isinstance(append_blocks, list):
        append_blocks = None
    remove_block_ids = arguments.get("remove_block_ids")
    if not isinstance(remove_block_ids, list):
        remove_block_ids = None
    evidence_refs = (
        list(arguments.get("evidence_refs") or [])
        if isinstance(arguments.get("evidence_refs"), list)
        else None
    )
    fact = str(
        arguments.get("user_fact_summary")
        or arguments.get("conversational_fact")
        or ""
    ).strip()
    if fact:
        ce = conversational_evidence_ref(
            summary=fact,
            session_id=str(runtime.get("session_id") or ""),
            turn_or_epoch=str(runtime.get("reasoning_epoch") or ""),
        )
        evidence_refs = list(evidence_refs or []) + [ce]
    try:
        obj = await _svc(db).update_object(
            uid,
            object_id,
            patch=dict(arguments.get("patch") or {}),
            replace_content=arguments.get("content")
            if isinstance(arguments.get("content"), dict)
            else None,
            replace_spec=arguments.get("spec")
            if isinstance(arguments.get("spec"), dict)
            else None,
            append_blocks=append_blocks,
            remove_block_ids=[str(x) for x in (remove_block_ids or [])],
            evidence_refs=evidence_refs,
            adaptation_note=str(arguments.get("adaptation_note") or "")[:240] or None,
            interaction_ref=str(arguments.get("interaction_ref") or "")[:80] or None,
            preserve_evidence=arguments.get("preserve_evidence", True) is not False,
        )
    except ValueError as e:
        msg = str(e)
        code = msg.split(":", 1)[0] if ":" in msg else "INVALID_RESPONSE"
        return _fail("update_object", code, detail=msg)
    if not obj:
        return _fail("update_object", "UNSUPPORTED", detail="not_found")
    blocks = (obj.content or {}).get("blocks") or []
    return Observation(
        kind="tool",
        name="update_object",
        status="ok",
        payload={
            "capability": "update_object",
            "status": "success",
            "object_id": obj.id,
            "plan_id": obj.plan_id,
            "object_kind": obj.object_kind,
            "title": obj.title,
            "revision": int(getattr(obj, "revision", 1) or 1),
            "updated_at": obj.updated_at,
            "blocks_n": len(blocks),
            "workspace_route": (
                f"/goal-workspace/{obj.plan_id}" if obj.plan_id else None
            ),
            "summary": f"Object updated (revision {getattr(obj, 'revision', 1)})",
            "memory_eligible": False,
        },
        provenance=[obj.id],
    )


async def get_object(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    object_id = str(arguments.get("object_id") or arguments.get("id") or "")
    if not uid or db is None or not object_id:
        return _fail("get_object", "INVALID_RESPONSE")
    obj = await _svc(db).repo.get_object(uid, object_id)
    if not obj:
        return _fail("get_object", "UNSUPPORTED", detail="not_found")
    return Observation(
        kind="tool",
        name="get_object",
        status="ok",
        payload={
            "capability": "get_object",
            "status": "success",
            "object": obj.public(),
            "grounding": "PERSONAL_CONTEXT",
            "memory_eligible": False,
        },
        provenance=[obj.id],
    )


async def list_goal_objects(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    if not uid or db is None:
        return _fail("list_goal_objects", "NOT_CONFIGURED")
    plan_id = str(arguments.get("plan_id") or arguments.get("plan_ref") or "") or None
    goal_id = str(arguments.get("goal_id") or arguments.get("goal_ref") or "") or None
    svc = _svc(db)
    objs = []
    if plan_id:
        objs = await svc.repo.list_objects_for_plan(uid, plan_id, limit=20)
    elif goal_id:
        objs = await svc.repo.list_objects_for_goal(uid, goal_id, limit=20)
    else:
        bundle = await svc.get_active_bundle(uid)
        objs_raw = bundle.get("objects") or []
        return Observation(
            kind="tool",
            name="list_goal_objects",
            status="ok",
            payload={
                "capability": "list_goal_objects",
                "status": "success",
                "objects": [
                    {
                        "id": o.get("id"),
                        "title": o.get("title"),
                        "object_kind": o.get("object_kind"),
                        "status": o.get("status"),
                    }
                    for o in objs_raw
                ],
                "plan_id": (bundle.get("plan") or {}).get("id"),
                "memory_eligible": False,
            },
        )
    return Observation(
        kind="tool",
        name="list_goal_objects",
        status="ok",
        payload={
            "capability": "list_goal_objects",
            "status": "success",
            "objects": [
                {
                    "id": o.id,
                    "title": o.title,
                    "object_kind": o.object_kind,
                    "status": o.status,
                    "updated_at": o.updated_at,
                }
                for o in objs
            ],
            "plan_id": plan_id,
            "goal_id": goal_id,
            "memory_eligible": False,
        },
    )


async def record_object_interaction(
    arguments: Dict[str, Any], runtime: Dict[str, Any]
) -> Observation:
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    object_id = str(arguments.get("object_id") or "")
    if not uid or db is None or not object_id:
        return _fail("record_object_interaction", "INVALID_RESPONSE")
    res = await _svc(db).record_object_interaction(
        uid,
        object_id,
        event_type=str(arguments.get("event_type") or arguments.get("type") or "interact"),
        payload=dict(arguments.get("payload") or {}),
    )
    if not res:
        return _fail("record_object_interaction", "UNSUPPORTED", detail="not_found")
    return Observation(
        kind="tool",
        name="record_object_interaction",
        status="ok",
        payload={
            "capability": "record_object_interaction",
            "status": "success",
            **res,
            "memory_eligible": False,
        },
        provenance=[object_id],
    )


async def get_active_plan(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    if not uid or db is None:
        return _fail("get_active_plan", "NOT_CONFIGURED")
    bundle = await _svc(db).get_active_bundle(
        uid, plan_id=str(arguments.get("plan_id") or "") or None
    )
    return Observation(
        kind="tool",
        name="get_active_plan",
        status="ok",
        payload={
            "capability": "get_active_plan",
            "status": "success",
            **bundle,
            "calibration_note": calibration_note_for_ai(bundle.get("evidence_quality") or {}),
            "memory_eligible": False,
            "grounding": "PERSONAL_CONTEXT",
        },
        provenance=[(bundle.get("plan") or {}).get("id")]
        if bundle.get("plan")
        else [],
    )


async def mark_plan_progress(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    plan_id = str(arguments.get("plan_id") or "")
    item_id = str(arguments.get("item_id") or "")
    status = str(arguments.get("status") or "completed")
    if not uid or db is None or not plan_id or not item_id:
        return _fail("mark_plan_progress", "INVALID_RESPONSE")
    plan = await _svc(db).mark_item(uid, plan_id, item_id, status=status)
    if not plan:
        return _fail("mark_plan_progress", "UNSUPPORTED", detail="not_found")
    return Observation(
        kind="tool",
        name="mark_plan_progress",
        status="ok",
        payload={
            "capability": "mark_plan_progress",
            "status": "success",
            "plan_id": plan.id,
            "item_id": item_id,
            "item_status": status,
            "progress_ratio": plan.progress_ratio(),
            "memory_eligible": False,
        },
        provenance=[plan.id, item_id],
    )


def _fail(name: str, code: str, detail: str = "") -> Observation:
    return Observation(
        kind="error",
        name=name,
        status="failed",
        payload={"failure_code": code, "detail": detail, "capability": name},
    )


def _as_int(v: Any) -> Optional[int]:
    try:
        if v is None or v == "":
            return None
        return int(v)
    except Exception:
        return None
