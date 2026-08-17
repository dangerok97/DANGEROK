"""Validated Situation mutations. AI supplies meaning; runtime guarantees state."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from situations.models import SituationEvent, SituationState, SituationUpdate, now_iso
from situations.repository import SituationRepository


class SituationMutationError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class SituationService:
    def __init__(self, db):
        self.repo = SituationRepository(db)

    async def ensure_indexes(self) -> None:
        await self.repo.ensure_indexes()

    async def list_context(
        self, user_id: str, *, session_id: Optional[str], limit: int = 4
    ) -> List[SituationState]:
        session_items = (
            await self.repo.list_recent(user_id, session_id=session_id, limit=2)
            if session_id
            else []
        )
        recent = await self.repo.list_recent(user_id, limit=limit)
        out: List[SituationState] = []
        for item in [*session_items, *recent]:
            if item.id not in {x.id for x in out}:
                out.append(item)
        return out[:limit]

    async def apply(
        self,
        *,
        user_id: str,
        session_id: str,
        update: SituationUpdate,
        reasoning_epoch: str,
    ) -> Dict[str, Any]:
        if update.operation == "none":
            return {"status": "noop"}
        if update.operation == "create":
            if update.situation_id:
                raise SituationMutationError("CREATE_WITH_ID")
            if not (update.summary or "").strip():
                raise SituationMutationError("SUMMARY_REQUIRED")
            prior = await self.repo.get_by_epoch(user_id, reasoning_epoch)
            if prior:
                return {
                    "status": "success",
                    "operation": "create",
                    "deduped": True,
                    "situation": prior.context_preview(),
                }
            sid = f"sit_{uuid.uuid4().hex[:16]}"
            situation = SituationState(
                id=sid,
                user_id=user_id,
                session_id=session_id,
                summary=str(update.summary).strip(),
                semantic_kind=update.semantic_kind,
                temporal_scope=update.temporal_scope,
                participants=update.participants,
                constraints=update.constraints,
                facts=update.facts,
                assumptions=update.assumptions,
                source_refs=update.source_refs,
                linked_plan_id=update.linked_plan_id,
                linked_object_refs=update.linked_object_refs,
                applied_epochs=[reasoning_epoch],
            )
            situation.history.append(
                SituationEvent(
                    revision=1,
                    operation="create",
                    source=update.source,
                    source_refs=update.source_refs,
                    changes=_changes(update),
                    reasoning_epoch=reasoning_epoch,
                )
            )
            await self.repo.insert(situation)
            return {
                "status": "success",
                "operation": "create",
                "situation": situation.context_preview(),
            }

        sid = (update.situation_id or "").strip()
        if not sid:
            raise SituationMutationError("SITUATION_ID_REQUIRED")
        situation = await self.repo.get(user_id, sid)
        if not situation:
            raise SituationMutationError("NOT_FOUND_OR_NOT_OWNED")
        if reasoning_epoch and reasoning_epoch in situation.applied_epochs:
            return {
                "status": "success",
                "operation": update.operation,
                "deduped": True,
                "situation": situation.context_preview(),
            }
        if update.expected_revision and update.expected_revision != situation.revision:
            raise SituationMutationError("REVISION_CONFLICT")
        if (
            situation.status in ("cancelled", "resolved")
            and update.operation == "update"
        ):
            raise SituationMutationError("TERMINAL_REOPEN_REQUIRES_EXPLICIT_CREATE")

        previous_revision = situation.revision
        if update.summary is not None:
            situation.summary = update.summary.strip() or situation.summary
        if update.semantic_kind is not None:
            situation.semantic_kind = update.semantic_kind
        if update.temporal_scope is not None:
            situation.temporal_scope = update.temporal_scope
        for field in (
            "participants",
            "constraints",
            "facts",
            "assumptions",
            "source_refs",
            "linked_object_refs",
        ):
            incoming = list(getattr(update, field) or [])
            current = [
                x
                for x in list(getattr(situation, field) or [])
                if x not in set(update.supersedes)
            ]
            if incoming:
                setattr(situation, field, _merge(current, incoming))
            elif update.supersedes:
                setattr(situation, field, current)
        if update.linked_plan_id is not None:
            situation.linked_plan_id = update.linked_plan_id
        if update.operation == "cancel":
            situation.status = "cancelled"
            situation.resolved_at = now_iso()
        elif update.operation == "resolve":
            situation.status = "resolved"
            situation.resolved_at = now_iso()
        else:
            situation.status = "changed"
        situation.revision += 1
        situation.updated_at = now_iso()
        situation.applied_epochs = [*situation.applied_epochs[-19:], reasoning_epoch]
        situation.history = [
            *situation.history[-49:],
            SituationEvent(
                revision=situation.revision,
                operation=update.operation,
                source=update.source,
                source_refs=update.source_refs,
                changes=_changes(update),
                reasoning_epoch=reasoning_epoch,
            ),
        ]
        if not await self.repo.save(situation, previous_revision=previous_revision):
            raise SituationMutationError("REVISION_CONFLICT")
        return {
            "status": "success",
            "operation": update.operation,
            "situation": situation.context_preview(),
        }


def _merge(current: List[str], incoming: List[str]) -> List[str]:
    out = list(current)
    for value in incoming:
        if value not in out:
            out.append(value)
    return out[:20]


def _changes(update: SituationUpdate) -> Dict[str, Any]:
    data = update.model_dump(exclude_none=True)
    data.pop("situation_id", None)
    data.pop("expected_revision", None)
    return data
