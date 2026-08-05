"""Goal status lifecycle transitions."""
from __future__ import annotations

from typing import Optional, Set, Tuple

from goal_engine.goal_types import GOAL_STATUSES, TERMINAL
from goal_engine.models import Goal, now_iso

# Allowed transitions (from → to). Same status is always allowed (no-op).
_ALLOWED: dict[str, Set[str]] = {
    "idea": {"planning", "active", "cancelled", "archived"},
    "planning": {"active", "paused", "waiting", "blocked", "cancelled", "archived"},
    "active": {"waiting", "blocked", "paused", "completed", "cancelled", "archived"},
    "waiting": {"active", "blocked", "paused", "cancelled", "archived"},
    "blocked": {"active", "waiting", "paused", "cancelled", "archived"},
    "paused": {"active", "planning", "cancelled", "archived"},
    "completed": {"archived", "active"},  # reopen rare
    "cancelled": {"archived", "idea", "planning"},  # revive
    "archived": set(),  # terminal sink
}


def can_transition(from_status: str, to_status: str) -> bool:
    if from_status == to_status:
        return True
    if to_status not in GOAL_STATUSES:
        return False
    return to_status in _ALLOWED.get(from_status, set())


def apply_status(goal: Goal, new_status: str) -> Tuple[Goal, Optional[str]]:
    """Apply status change; returns (goal, error)."""
    if new_status not in GOAL_STATUSES:
        return goal, f"invalid_status:{new_status}"
    if not can_transition(goal.status, new_status):
        return goal, f"illegal_transition:{goal.status}->{new_status}"
    if goal.status == new_status:
        return goal, None
    goal.status = new_status  # type: ignore[assignment]
    goal.updated_at = now_iso()
    if new_status == "completed":
        goal.completed_at = now_iso()
        goal.completion_percentage = 100.0
        if goal.progress:
            goal.progress.ratio = 1.0
            goal.progress.phase = "completed"
    elif new_status == "cancelled":
        goal.cancelled_at = now_iso()
    elif new_status == "archived":
        goal.archived_at = now_iso()
    return goal, None


def status_for_confirm(goal_type: str) -> str:
    """Status after Study/Travel confirm (shadow)."""
    return "active"


def status_for_draft(goal_type: str) -> str:
    return "planning"
