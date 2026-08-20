"""Life Context Graph V1 governance: AI proposes edges; this service persists
them with ownership, idempotency, revision/history and honest conflict
handling. Mirrors life_memory.governance's idempotency key and supersession
shape, and situations.service's revision/history/optimistic-concurrency shape
— deliberately reusing both proven patterns rather than inventing a third.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from context_graph.models import (
    ContextEdge,
    ContextEdgeEvent,
    ContextEdgeUpdate,
    is_recognized_ref,
    now_iso,
)
from context_graph.repository import ContextGraphRepository

Decision = Literal[
    "CREATED",
    "UPDATED",
    "SUPERSEDED",
    "DEACTIVATED",
    "REQUIRES_SUPERSESSION",
    "REJECTED",
    "NOT_FOUND_OR_NOT_OWNED",
    "IDEMPOTENT_REPLAY",
    "NOOP",
]

_PATCH_FIELDS = (
    "semantic_summary",
    "confidence",
    "authority",
    "provenance",
    "evidence_refs",
    "temporal_scope",
    "sensitivity",
    "reversible",
    "coexists_with_refs",
)


@dataclass
class ContextGraphOutcome:
    decision: Decision
    code: str
    edge_id: Optional[str] = None
    persisted: bool = False
    edge: Optional[Dict[str, Any]] = None

    def public(self) -> Dict[str, Any]:
        payload = {
            "decision": self.decision,
            "code": self.code,
            "edge_id": self.edge_id,
            "persisted": self.persisted,
        }
        if self.edge:
            payload["edge"] = self.edge
        if self.code == "EXISTING_EDGE_REQUIRES_RELATIONSHIP":
            payload["next_step"] = (
                "Decide the relationship to this exact owned edge_id. Emit operation="
                "supersede with edge_id + the new subject/predicate/object, or explicitly "
                "cite it in coexists_with_refs if both relationships remain true. Do not "
                "silently create a second active edge with the same subject and predicate."
            )
        return payload


class ContextGraphService:
    MAX_UPDATES = 2

    def __init__(self, db):
        self.db = db
        self.repo = ContextGraphRepository(db)

    async def ensure_indexes(self) -> None:
        await self.repo.ensure_indexes()

    async def relevant_edges(
        self, user_id: str, seed_refs: List[str], *, limit: int = 12
    ) -> List[ContextEdge]:
        """Bounded 1-hop lookup used by the Context Broker source (read-only)."""
        return await self.repo.find_touching(user_id, seed_refs, limit=limit)

    async def apply(
        self,
        *,
        user_id: str,
        session_id: str,
        updates: List[ContextEdgeUpdate],
        reasoning_epoch: str,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for index, update in enumerate(list(updates)[: self.MAX_UPDATES]):
            outcome = await self._apply_one(
                user_id=user_id,
                session_id=session_id,
                update=update,
                reasoning_epoch=reasoning_epoch,
                index=index,
            )
            results.append(outcome.public())
        return results

    async def _apply_one(
        self,
        *,
        user_id: str,
        session_id: str,
        update: ContextEdgeUpdate,
        reasoning_epoch: str,
        index: int,
    ) -> ContextGraphOutcome:
        if update.operation == "none":
            return ContextGraphOutcome("NOOP", "NO_OPERATION")

        key = f"{reasoning_epoch}:{index}"
        prior = await self.repo.get_by_governance_key(user_id, key)
        if prior:
            return ContextGraphOutcome(
                "IDEMPOTENT_REPLAY",
                "IDEMPOTENT_REPLAY",
                prior.id,
                True,
                prior.context_preview(),
            )

        if update.operation == "create":
            return await self._create(user_id, session_id, update, reasoning_epoch, key)
        if update.operation == "supersede":
            return await self._supersede(
                user_id, session_id, update, reasoning_epoch, key
            )
        if update.operation == "update":
            return await self._patch(user_id, update, reasoning_epoch)
        if update.operation == "deactivate":
            return await self._deactivate(user_id, update, reasoning_epoch)
        return ContextGraphOutcome("REJECTED", "UNKNOWN_OPERATION")

    async def _create(
        self,
        user_id: str,
        session_id: str,
        update: ContextEdgeUpdate,
        reasoning_epoch: str,
        governance_key: str,
    ) -> ContextGraphOutcome:
        if not (update.subject_ref and update.predicate and update.object_ref):
            return ContextGraphOutcome("REJECTED", "MISSING_REQUIRED_FIELDS")
        if not (
            is_recognized_ref(update.subject_ref)
            and is_recognized_ref(update.object_ref)
        ):
            return ContextGraphOutcome("REJECTED", "UNRECOGNIZED_REF")
        if update.subject_ref == update.object_ref:
            return ContextGraphOutcome("REJECTED", "SELF_LOOP")

        existing = await self.repo.find_active_by_identity(
            user_id, subject_ref=update.subject_ref, predicate=update.predicate
        )
        if existing and existing.object_ref == update.object_ref:
            # Same relationship proposed again — refresh evidence in place,
            # never a second active duplicate.
            return await self._patch_edge(
                existing, update, reasoning_epoch, decision="UPDATED", code="REFRESHED"
            )
        if existing and existing.id not in (update.coexists_with_refs or []):
            return ContextGraphOutcome(
                "REQUIRES_SUPERSESSION",
                "EXISTING_EDGE_REQUIRES_RELATIONSHIP",
                existing.id,
                False,
                existing.context_preview(),
            )

        edge = ContextEdge(
            id=f"lce_{uuid.uuid4().hex[:16]}",
            user_id=user_id,
            session_id=session_id,
            subject_ref=update.subject_ref,
            predicate=update.predicate,
            object_ref=update.object_ref,
            semantic_summary=update.semantic_summary,
            confidence=update.confidence,
            authority=update.authority,
            provenance=update.provenance,
            evidence_refs=update.evidence_refs,
            temporal_scope=update.temporal_scope,
            sensitivity=update.sensitivity,
            reversible=update.reversible,
            coexists_with_refs=update.coexists_with_refs,
            governance_key=governance_key,
        )
        edge.history.append(
            ContextEdgeEvent(
                revision=1,
                operation="create",
                reasoning_epoch=reasoning_epoch,
                changes=_changes(update),
            )
        )
        await self.repo.insert(edge)
        return ContextGraphOutcome(
            "CREATED", "CREATED", edge.id, True, edge.context_preview()
        )

    async def _supersede(
        self,
        user_id: str,
        session_id: str,
        update: ContextEdgeUpdate,
        reasoning_epoch: str,
        governance_key: str,
    ) -> ContextGraphOutcome:
        old_id = (update.edge_id or "").strip()
        if not old_id:
            return ContextGraphOutcome("REJECTED", "EDGE_ID_REQUIRED")
        old = await self.repo.get(user_id, old_id)
        if not old:
            return ContextGraphOutcome("NOT_FOUND_OR_NOT_OWNED", "NOT_FOUND_OR_NOT_OWNED")
        new_subject = update.subject_ref or old.subject_ref
        new_predicate = update.predicate or old.predicate
        new_object = update.object_ref or old.object_ref
        if not (
            is_recognized_ref(new_subject) and is_recognized_ref(new_object)
        ):
            return ContextGraphOutcome("REJECTED", "UNRECOGNIZED_REF")
        new_id = f"lce_{uuid.uuid4().hex[:16]}"
        now = now_iso()
        old.status = "superseded"
        old.superseded_by = new_id
        old.updated_at = now
        old.revision += 1
        old.history = [
            *old.history[-19:],
            ContextEdgeEvent(
                revision=old.revision,
                operation="supersede",
                reasoning_epoch=reasoning_epoch,
                changes={"replacement_id": new_id},
            ),
        ]
        saved = await self.repo.save(old, previous_revision=old.revision - 1)
        if not saved:
            return ContextGraphOutcome("REJECTED", "REVISION_CONFLICT")

        edge = ContextEdge(
            id=new_id,
            user_id=user_id,
            session_id=session_id,
            subject_ref=new_subject,
            predicate=new_predicate,
            object_ref=new_object,
            semantic_summary=update.semantic_summary or old.semantic_summary,
            confidence=update.confidence,
            authority=update.authority,
            provenance=update.provenance or old.provenance,
            evidence_refs=update.evidence_refs or old.evidence_refs,
            temporal_scope=update.temporal_scope,
            sensitivity=update.sensitivity,
            reversible=update.reversible,
            coexists_with_refs=update.coexists_with_refs,
            supersedes_ref=old.id,
            governance_key=governance_key,
        )
        edge.history.append(
            ContextEdgeEvent(
                revision=1,
                operation="supersede",
                reasoning_epoch=reasoning_epoch,
                changes=_changes(update),
            )
        )
        await self.repo.insert(edge)
        return ContextGraphOutcome(
            "SUPERSEDED", "SUPERSEDED", edge.id, True, edge.context_preview()
        )

    async def _patch(
        self, user_id: str, update: ContextEdgeUpdate, reasoning_epoch: str
    ) -> ContextGraphOutcome:
        eid = (update.edge_id or "").strip()
        if not eid:
            return ContextGraphOutcome("REJECTED", "EDGE_ID_REQUIRED")
        edge = await self.repo.get(user_id, eid)
        if not edge:
            return ContextGraphOutcome("NOT_FOUND_OR_NOT_OWNED", "NOT_FOUND_OR_NOT_OWNED")
        if edge.status != "active":
            return ContextGraphOutcome("REJECTED", "EDGE_NOT_ACTIVE")
        return await self._patch_edge(
            edge, update, reasoning_epoch, decision="UPDATED", code="UPDATED"
        )

    async def _patch_edge(
        self,
        edge: ContextEdge,
        update: ContextEdgeUpdate,
        reasoning_epoch: str,
        *,
        decision: Decision,
        code: str,
    ) -> ContextGraphOutcome:
        previous_revision = edge.revision
        data = update.model_dump(exclude_none=True)
        for field in _PATCH_FIELDS:
            if field in data:
                setattr(edge, field, data[field])
        edge.revision += 1
        edge.updated_at = now_iso()
        edge.history = [
            *edge.history[-19:],
            ContextEdgeEvent(
                revision=edge.revision,
                operation="update",
                reasoning_epoch=reasoning_epoch,
                changes=_changes(update),
            ),
        ]
        saved = await self.repo.save(edge, previous_revision=previous_revision)
        if not saved:
            return ContextGraphOutcome("REJECTED", "REVISION_CONFLICT")
        return ContextGraphOutcome(decision, code, edge.id, True, edge.context_preview())

    async def _deactivate(
        self, user_id: str, update: ContextEdgeUpdate, reasoning_epoch: str
    ) -> ContextGraphOutcome:
        eid = (update.edge_id or "").strip()
        if not eid:
            return ContextGraphOutcome("REJECTED", "EDGE_ID_REQUIRED")
        edge = await self.repo.get(user_id, eid)
        if not edge:
            return ContextGraphOutcome("NOT_FOUND_OR_NOT_OWNED", "NOT_FOUND_OR_NOT_OWNED")
        if edge.status != "active":
            return ContextGraphOutcome(
                "DEACTIVATED", "ALREADY_TERMINAL", edge.id, False, edge.context_preview()
            )
        previous_revision = edge.revision
        edge.status = "resolved"
        edge.revision += 1
        edge.updated_at = now_iso()
        edge.history = [
            *edge.history[-19:],
            ContextEdgeEvent(
                revision=edge.revision,
                operation="deactivate",
                reasoning_epoch=reasoning_epoch,
                changes=_changes(update),
            ),
        ]
        saved = await self.repo.save(edge, previous_revision=previous_revision)
        if not saved:
            return ContextGraphOutcome("REJECTED", "REVISION_CONFLICT")
        return ContextGraphOutcome(
            "DEACTIVATED", "DEACTIVATED", edge.id, True, edge.context_preview()
        )


def _changes(update: ContextEdgeUpdate) -> Dict[str, Any]:
    data = update.model_dump(exclude_none=True)
    data.pop("edge_id", None)
    return data
