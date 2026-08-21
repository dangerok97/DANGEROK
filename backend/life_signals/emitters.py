"""Per-subsystem adapters: persisted mutation outcome → LifeChangeSignal.

Every rule about WHICH mutations qualify lives here, in one reviewable place,
rather than scattered across the cognitive loop. Each adapter takes the exact
outcome shape the owning subsystem already returns — none of them is modified
to serve this layer.

Three invariants hold for every adapter:

* PERSIST-BEFORE-SIGNAL — only outcomes the subsystem itself reports as
  persisted produce a signal. A proposal, a rejection, a clarification
  request, a failure or a no-op produces nothing.
* IDEMPOTENT — the dedupe key derives from the stable identity of the
  mutation (entity ref + revision, or reasoning epoch + capability), never
  from a timestamp or a fresh random value. A replayed turn is silently
  deduped at the storage layer.
* TERMINAL — emitting never mutates anything else and never emits again.
  There is no signal → mutation → signal path.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from life_signals.service import LifeSignalService

# Calendar capabilities and the technical change they represent. Mirrors
# loop.py's `_CALENDAR_WRITE_CAPS` without importing it (that module imports
# heavy AI Core wiring); kept in sync by test Z.
_CALENDAR_CAP_KINDS = {
    "create_calendar_event": "created",
    "update_calendar_event": "updated",
    "cancel_calendar_event": "cancelled",
}

# Life OS persistence capabilities → (ref field, ref prefix, change kind).
_LIFE_OS_CAP_SPECS = {
    "create_plan": ("plan_id", "plan", "created"),
    "update_plan": ("plan_id", "plan", "updated"),
    "mark_plan_progress": ("plan_id", "plan", "updated"),
    "create_actions": ("plan_id", "plan", "updated"),
    "create_object": ("object_id", "object", "created"),
    "update_object": ("object_id", "object", "updated"),
}

# Situation operations → technical change kind.
_SITUATION_KINDS = {
    "create": "created",
    "update": "updated",
    "cancel": "cancelled",
    "resolve": "completed",
}

# Memory governance decisions that actually persisted a durable change.
_MEMORY_KINDS = {
    "PROMOTE": "created",
    "SUPERSEDE": "superseded",
    "FORGET_ALLOWED": "cancelled",
}

# Context Graph decisions that actually persisted an edge change.
_GRAPH_KINDS = {
    "CREATED": "linked",
    "UPDATED": "updated",
    "SUPERSEDED": "superseded",
    "DEACTIVATED": "unlinked",
}


async def emit_situation_signal(
    db,
    *,
    user_id: str,
    session_id: str,
    reasoning_epoch: str,
    operation: str,
    result: Dict[str, Any],
) -> Optional[str]:
    """`SituationService.apply` outcome. Skips replays (`deduped`) and any
    non-success result."""
    if (result or {}).get("status") != "success":
        return None
    if (result or {}).get("deduped"):
        return None
    change_kind = _SITUATION_KINDS.get(str(operation))
    if not change_kind:
        return None
    situation = (result or {}).get("situation") or {}
    sid = str(situation.get("id") or "")
    if not sid:
        return None
    revision = situation.get("revision")

    affected: List[str] = []
    linked_plan = situation.get("linked_plan_id")
    if linked_plan:
        affected.append(f"plan:{linked_plan}")
    affected.extend(str(r) for r in (situation.get("linked_object_refs") or []))

    return await LifeSignalService(db).emit(
        user_id=user_id,
        source_ref=f"situation:{sid}",
        source_system="situation",
        change_kind=change_kind,
        dedupe_key=f"situation:{sid}:r{revision}",
        affected_refs=affected,
        revision=revision if isinstance(revision, int) else None,
        occurred_at=situation.get("updated_at"),
        session_id=session_id,
        reasoning_epoch=reasoning_epoch,
    )


async def emit_memory_signals(
    db,
    *,
    user_id: str,
    session_id: str,
    reasoning_epoch: str,
    outcomes: List[Any],
) -> List[str]:
    """`MemoryGovernanceService.process` outcomes. CLARIFY/REJECT/FORGET_DENIED
    never persisted anything, and an IDEMPOTENT_REPLAY is a retry of a change
    that already produced its signal."""
    emitted: List[str] = []
    service = LifeSignalService(db)
    for index, outcome in enumerate(outcomes or []):
        if not getattr(outcome, "persisted", False):
            continue
        if getattr(outcome, "code", "") == "IDEMPOTENT_REPLAY":
            continue
        decision = str(getattr(outcome, "decision", ""))
        change_kind = _MEMORY_KINDS.get(decision)
        memory_id = str(getattr(outcome, "memory_id", "") or "")
        if not change_kind or not memory_id:
            continue
        signal_id = await service.emit(
            user_id=user_id,
            source_ref=memory_id,
            source_system="life_memory",
            change_kind=change_kind,
            dedupe_key=f"life_memory:{memory_id}:{decision}:{reasoning_epoch}:{index}",
            authority=decision,
            session_id=session_id,
            reasoning_epoch=reasoning_epoch,
        )
        if signal_id:
            emitted.append(signal_id)
    return emitted


async def emit_context_graph_signals(
    db,
    *,
    user_id: str,
    session_id: str,
    reasoning_epoch: str,
    results: List[Dict[str, Any]],
) -> List[str]:
    """`ContextGraphService.apply` results.

    The edge id (`lce_...`) is not part of the canonical ref namespace, and
    V2.9.1 deliberately does not invent a second one: the signal points at the
    edge's SUBJECT — the entity whose relationships changed — and carries the
    object in `affected_refs`. That is a deterministic fact from the mutation
    result itself, not graph expansion.
    """
    emitted: List[str] = []
    service = LifeSignalService(db)
    for result in results or []:
        if not (result or {}).get("persisted"):
            continue
        decision = str((result or {}).get("decision") or "")
        change_kind = _GRAPH_KINDS.get(decision)
        if not change_kind:
            continue
        edge = (result or {}).get("edge") or {}
        edge_id = str((result or {}).get("edge_id") or "")
        subject_ref = str(edge.get("subject_ref") or "")
        if not edge_id or not subject_ref:
            continue
        revision = edge.get("revision")
        object_ref = edge.get("object_ref")
        signal_id = await service.emit(
            user_id=user_id,
            source_ref=subject_ref,
            source_system="context_graph",
            change_kind=change_kind,
            dedupe_key=f"context_graph:{edge_id}:r{revision}",
            affected_refs=[str(object_ref)] if object_ref else [],
            revision=revision if isinstance(revision, int) else None,
            authority=edge.get("authority"),
            occurred_at=edge.get("updated_at"),
            session_id=session_id,
            reasoning_epoch=reasoning_epoch,
        )
        if signal_id:
            emitted.append(signal_id)
    return emitted


async def emit_calendar_signal(
    db,
    *,
    user_id: str,
    session_id: str,
    reasoning_epoch: str,
    capability: str,
    observation_status: str,
    payload: Dict[str, Any],
) -> Optional[str]:
    """V2.8.6b Calendar capability observation.

    Emits for BOTH "ok" and "partial": partial means ORA's own local calendar
    state really was persisted while the Google-side sync stayed unconfirmed,
    so the user's life state genuinely changed. `source_status` carries that
    distinction forward so a future reasoner never assumes Google agrees.

    Emits for NOTHING else — a proposal awaiting confirmation
    (response_mode=act) never reaches a capability handler at all, and
    consent_required / not_found / rejected / failed / error all mean no local
    state changed. `already_cancelled` is a no-op replay.
    """
    change_kind = _CALENDAR_CAP_KINDS.get(str(capability))
    if not change_kind:
        return None
    status = str((payload or {}).get("status") or observation_status or "")
    if status not in ("ok", "partial"):
        return None
    if (payload or {}).get("operation") == "already_cancelled":
        return None
    calendar_ref = str((payload or {}).get("calendar_ref") or "")
    if not calendar_ref:
        return None
    if not reasoning_epoch:
        # Without a stable discriminator the dedupe key would degrade to a
        # timestamp/random value; fail closed rather than risk a duplicate
        # storm on retry.
        return None

    return await LifeSignalService(db).emit(
        user_id=user_id,
        source_ref=calendar_ref,
        source_system="calendar",
        change_kind=change_kind,
        dedupe_key=f"calendar:{calendar_ref}:{reasoning_epoch}:{capability}",
        source_status=status,
        session_id=session_id,
        reasoning_epoch=reasoning_epoch,
    )


async def emit_life_os_signal(
    db,
    *,
    user_id: str,
    session_id: str,
    reasoning_epoch: str,
    capability: str,
    payload: Dict[str, Any],
) -> Optional[str]:
    """Life OS plan/object persistence capability observation."""
    spec = _LIFE_OS_CAP_SPECS.get(str(capability))
    if not spec:
        return None
    id_field, prefix, change_kind = spec
    if str((payload or {}).get("status") or "") != "success":
        return None
    entity_id = str((payload or {}).get(id_field) or "")
    if not entity_id or not reasoning_epoch:
        return None

    affected: List[str] = []
    if prefix == "object":
        plan_id = (payload or {}).get("plan_id")
        if plan_id:
            affected.append(f"plan:{plan_id}")
        goal_id = (payload or {}).get("goal_id")
        if goal_id:
            affected.append(f"goal:{goal_id}")

    return await LifeSignalService(db).emit(
        user_id=user_id,
        source_ref=f"{prefix}:{entity_id}",
        source_system="life_os",
        change_kind=change_kind,
        dedupe_key=f"life_os:{prefix}:{entity_id}:{reasoning_epoch}:{capability}",
        affected_refs=affected,
        session_id=session_id,
        reasoning_epoch=reasoning_epoch,
    )
