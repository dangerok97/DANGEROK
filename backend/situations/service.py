"""Validated Situation mutations. AI supplies meaning; runtime guarantees state."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from situations.models import SituationEvent, SituationState, SituationUpdate, now_iso
from situations.repository import SituationRepository

logger = logging.getLogger(__name__)


class SituationMutationError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class SituationService:
    def __init__(self, db):
        self.db = db
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
        user_message: str = "",
    ) -> Dict[str, Any]:
        if update.operation == "none":
            return {"status": "noop"}

        update = await self._govern_linked_refs(user_id, update)
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
                attention_intent=update.attention_intent,
                desired_outcome=update.desired_outcome,
                started_at=update.started_at,
                icon_key=(update.icon_key or "other"),
                tracking_summary=update.tracking_summary,
                location_label=update.location_label,
                current_state_summary=update.current_state_summary,
                expected_outcome_summary=update.expected_outcome_summary,
                next_check_summary=update.next_check_summary,
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
            await self._note_opportunity_change(user_id, situation, operation="create")
            out = {
                "status": "success",
                "operation": "create",
                "situation": situation.context_preview(),
            }
            stated = await self._arm_stated_time(user_id, situation, user_message)
            if stated:
                out["stated_reminder"] = stated
            return out

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
        if update.operation == "update" and user_message:
            from situations.episode_identity import fresh_declared_episode
            replacement = fresh_declared_episode(
                old=situation, update=update, user_message=user_message,
            )
            if replacement is not None:
                # A current-turn declaration has established a new event.
                # Never rewrite the physical start, journal or user-owned
                # source of a previous event. The standard create path
                # deduplicates by this exact reasoning epoch.
                created = await self.apply(
                    user_id=user_id, session_id=session_id,
                    update=replacement, reasoning_epoch=reasoning_epoch,
                )
                created["new_episode"] = True
                created["previous_situation_id"] = situation.id
                logger.info("Situation new user episode created from old id (owner-scoped)")
                return created
        # Only modifications to the existing event require its current
        # revision. A separately declared new event does not mutate the
        # old record and cannot be blocked by an unrelated old edit.
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
        if update.attention_intent is not None:
            situation.attention_intent = update.attention_intent.strip() or None
        if update.started_at is not None:
            situation.started_at = update.started_at or None
        for field in (
            "desired_outcome",
            "icon_key",
            "tracking_summary",
            "location_label",
            "current_state_summary",
            "expected_outcome_summary",
            "next_check_summary",
        ):
            incoming = getattr(update, field)
            if incoming is not None:
                cleaned = " ".join(str(incoming).split()).strip()
                setattr(situation, field, cleaned or None)
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
        await self._note_opportunity_change(user_id, situation, operation=update.operation)
        out = {
            "status": "success",
            "operation": update.operation,
            "situation": situation.context_preview(),
        }
        if update.operation == "update":
            stated = await self._arm_stated_time(user_id, situation, user_message)
            if stated:
                out["stated_reminder"] = stated
        return out

    async def _arm_stated_time(self, user_id: str, situation, user_message: str):
        """A moment the person stated becomes a reminder sent by code."""
        if not user_message:
            return None
        from situations.stated_time import arm
        return await arm(self.db, user_id, situation, user_message)

    async def _govern_linked_refs(
        self, user_id: str, update: SituationUpdate
    ) -> SituationUpdate:
        """Persist only canonical linked refs that the runtime can trust.

        Place refs are identity-bearing personal data, so prefix validity is
        not enough: the referenced Life Place must exist for this exact user.
        Other canonical refs keep their existing ownership checks at the
        capability that consumes them, but malformed strings never enter the
        Situation graph. Dropping one bad link must not discard the user's
        underlying Situation statement.
        """
        incoming = list(update.linked_object_refs or [])
        if not incoming:
            return update

        try:
            from context_graph.models import is_recognized_ref
        except Exception:
            is_recognized_ref = lambda ref: False  # type: ignore[assignment]

        out: List[str] = []
        for raw in incoming:
            ref = str(raw or "").strip()[:160]
            if not ref or not is_recognized_ref(ref):
                continue

            if ref.startswith("place:"):
                place_id = ref.split(":", 1)[1].strip()
                if not place_id:
                    continue
                try:
                    found = await self.db.life_places.find_one(
                        {
                            "user_id": user_id,
                            "id": place_id,
                            "state": {"$ne": "dismissed"},
                        },
                        {"_id": 0, "id": 1},
                    )
                except Exception:
                    found = None
                if not found:
                    continue

            if ref not in out:
                out.append(ref)
            if len(out) >= 20:
                break

        return update.model_copy(update={"linked_object_refs": out})

    async def _note_opportunity_change(
        self, user_id: str, situation: SituationState, *, operation: str
    ) -> None:
        """Bridge persisted conversational state into the ordinary autonomy queue.

        Meaning remains with the AI. This records only THAT the governed
        Situation changed, using its canonical ref and revision; the private
        summary/facts stay in the Situation store and are read later through
        the bounded snapshot. A failed review bridge never rolls back the
        Situation the user just established.
        """
        kind = {
            "create": "situation.created",
            "update": "situation.updated",
            "cancel": "situation.cancelled",
            "resolve": "situation.resolved",
        }.get(str(operation or ""))
        if not kind:
            return
        if operation in ("create", "update") and (
            situation.attention_intent or situation.next_check_summary
        ):
            # A stored Situation is NOT an executable checkpoint. When the
            # cognitive decision explicitly asked for future attention, admit
            # an initial source-reading goal now. Its first recheck time must
            # still be chosen by the Agent after evidence; never guess one.
            try:
                from situations.admission import ensure_initial_review
                result = await ensure_initial_review(self.db, user_id, situation.id)
                if result["status"] in ("persistence_failed", "recovery_pending"):
                    logger.warning("Situation attention admission state=%s", result["status"])
            except Exception as exc:
                logger.warning(
                    "situation attention admission soft-fail: %s", type(exc).__name__
                )
        latest_changes = situation.history[-1].changes if situation.history else {}
        if operation in ("create", "update"):
            # Something drying outdoors gets its computed plan whatever path
            # created it, without waiting for the model to mark it as watched.
            from situations.outdoor_drying import ensure_planned
            await ensure_planned(self.db, user_id, situation)
        if operation in ("resolve", "cancel"):
            # Before the watch is closed: what was estimated and when it ended
            # become evidence for the next similar Situation.
            from situations.experience import record as remember
            await remember(self.db, user_id, situation, operation=operation)
        if operation in ("resolve", "cancel") or (
            operation == "update"
            and not (situation.attention_intent or situation.next_check_summary)
            and any(field in latest_changes for field in ("attention_intent", "next_check_summary"))
        ):
            # An explicit withdrawal of the attention obligation is just as
            # binding as closing the Situation. Do not let a stale initial
            # review wake resurrect the old intent.
            from situations.stated_time import disarm
            await disarm(self.db, user_id, situation.id)
            try:
                from situations.followup import cancel_dedicated_followup
                await cancel_dedicated_followup(self.db, user_id, situation.id)
            except Exception as exc:
                logger.warning("situation follow-up close failed: %s", type(exc).__name__)
        try:
            from opportunities.discovery import OpportunityDiscovery

            await OpportunityDiscovery(self.db).note(
                user_id,
                source="situations",
                kind=kind,
                entity_ref=f"situation:{situation.id}",
                entity_kind="situation",
                after=f"revision:{situation.revision}",
                occurred_at=situation.updated_at,
            )
        except Exception as exc:
            logger.warning(
                "situation opportunity bridge soft-fail id=%s error=%s",
                situation.id,
                type(exc).__name__,
            )


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
