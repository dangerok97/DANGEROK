"""ActionCenterService — the ONLY writer of decision action state.

Every mutation:
  1. reads the current action_state (default: pending),
  2. validates the requested transition against the state machine,
  3. writes an immutable row into `decision_action_history`,
  4. patches the decision doc with the new `action_state`.

Never generates Decisions. Never emits notifications. Never uses an LLM.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .history import ActionHistoryRepository
from .state_machine import (
    ALLOWED_TRANSITIONS,
    InvalidTransition,
    STATUS_BLOCKED,
    STATUS_COMPLETED,
    STATUS_DISMISSED,
    STATUS_IN_PROGRESS,
    STATUS_PARTIALLY_COMPLETED,
    STATUS_PENDING,
    STATUS_POSTPONED,
    can_transition,
    legacy_status_for,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ActionCenterService:
    def __init__(self, db):
        self.db = db
        self.history = ActionHistoryRepository(db)

    # ------------------------------------------------------------------
    def _current_status(self, decision: Dict[str, Any]) -> str:
        action_state = decision.get("action_state") or {}
        s = action_state.get("status")
        if s in ALLOWED_TRANSITIONS:
            return s
        # Backfill from legacy Decision.status if action_state is empty.
        legacy = decision.get("status") or "open"
        return {
            "open": STATUS_PENDING,
            "in_progress": STATUS_IN_PROGRESS,
            "completed": STATUS_COMPLETED,
            "dismissed": STATUS_DISMISSED,
        }.get(legacy, STATUS_PENDING)

    async def _load(self, user_id: str, decision_id: str) -> Optional[Dict[str, Any]]:
        return await self.db.decisions.find_one(
            {"id": decision_id, "user_id": user_id}, {"_id": 0},
        )

    async def _apply(
        self,
        *,
        user_id: str,
        decision_id: str,
        target: str,
        user_action: str,
        completion_percentage: Optional[int] = None,
        remaining_minutes: Optional[int] = None,
        postponed_until: Optional[str] = None,
        reason: Optional[str] = None,
        note: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        d = await self._load(user_id, decision_id)
        if not d:
            raise LookupError("decision_not_found")
        current = self._current_status(d)
        if not can_transition(current, target):
            raise InvalidTransition(current, target)

        now = _now_iso()
        new_action_state: Dict[str, Any] = {
            "status": target,
            "last_action": user_action,
            "last_action_at": now,
            "completion_percentage": completion_percentage,
            "remaining_minutes": remaining_minutes,
            "postponed_until": postponed_until,
            "blocked_reason": reason if target == STATUS_BLOCKED else None,
        }
        # Preserve existing percentages when transitioning to in_progress
        # without a new number (e.g. resuming after postpone).
        if target == STATUS_IN_PROGRESS and completion_percentage is None:
            new_action_state["completion_percentage"] = (
                (d.get("action_state") or {}).get("completion_percentage")
            )

        # Also update the legacy `status` field for backward compat.
        legacy = legacy_status_for(target)

        # History-first: write the immutable audit line BEFORE the mutation.
        await self.history.append(
            user_id=user_id,
            decision_id=decision_id,
            old_status=current,
            new_status=target,
            user_action=user_action,
            completion_percentage=completion_percentage,
            remaining_minutes=remaining_minutes,
            postponed_until=postponed_until,
            reason=reason,
            note=note,
            correlation_id=correlation_id,
        )

        await self.db.decisions.update_one(
            {"id": decision_id, "user_id": user_id},
            {"$set": {
                "action_state": new_action_state,
                "status": legacy,
                "updated_at": now,
            }, "$push": {
                "history": {
                    "at": now,
                    "event": f"action_center.{user_action}",
                    "data": {
                        "from": current, "to": target,
                        "completion_percentage": completion_percentage,
                        "remaining_minutes": remaining_minutes,
                        "postponed_until": postponed_until,
                        "reason": reason,
                    },
                },
            }},
        )
        return await self._load(user_id, decision_id)

    # ------------------------------------------------------------------
    # Public transitions
    # ------------------------------------------------------------------
    async def start(self, user_id: str, decision_id: str) -> Dict[str, Any]:
        return await self._apply(
            user_id=user_id, decision_id=decision_id,
            target=STATUS_IN_PROGRESS, user_action="start",
        )

    async def complete(self, user_id: str, decision_id: str, *, note: Optional[str] = None) -> Dict[str, Any]:
        return await self._apply(
            user_id=user_id, decision_id=decision_id,
            target=STATUS_COMPLETED, user_action="complete",
            completion_percentage=100, remaining_minutes=0, note=note,
        )

    async def partial(
        self,
        user_id: str,
        decision_id: str,
        *,
        completion_percentage: int,
        remaining_minutes: Optional[int] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        pct = max(0, min(100, int(completion_percentage)))
        return await self._apply(
            user_id=user_id, decision_id=decision_id,
            target=STATUS_PARTIALLY_COMPLETED, user_action="partial",
            completion_percentage=pct,
            remaining_minutes=remaining_minutes,
            note=note,
        )

    async def postpone(
        self,
        user_id: str,
        decision_id: str,
        *,
        until_datetime: str,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self._apply(
            user_id=user_id, decision_id=decision_id,
            target=STATUS_POSTPONED, user_action="postpone",
            postponed_until=until_datetime, reason=reason,
        )

    async def dismiss(
        self,
        user_id: str,
        decision_id: str,
        *,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self._apply(
            user_id=user_id, decision_id=decision_id,
            target=STATUS_DISMISSED, user_action="dismiss", reason=reason,
        )

    async def block(
        self,
        user_id: str,
        decision_id: str,
        *,
        reason: str,
    ) -> Dict[str, Any]:
        return await self._apply(
            user_id=user_id, decision_id=decision_id,
            target=STATUS_BLOCKED, user_action="block", reason=reason,
        )

    async def get_history(self, user_id: str, decision_id: str) -> list:
        return await self.history.list_for_decision(user_id, decision_id)
