"""State-machine definitions for Action Center."""
from __future__ import annotations

from typing import Dict, FrozenSet

STATUS_PENDING = "pending"
STATUS_IN_PROGRESS = "in_progress"
STATUS_PARTIALLY_COMPLETED = "partially_completed"
STATUS_COMPLETED = "completed"
STATUS_POSTPONED = "postponed"
STATUS_DISMISSED = "dismissed"
STATUS_BLOCKED = "blocked"

ACTION_STATUSES = frozenset({
    STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_PARTIALLY_COMPLETED,
    STATUS_COMPLETED, STATUS_POSTPONED, STATUS_DISMISSED, STATUS_BLOCKED,
})

# Terminal statuses cannot be transitioned OUT of (append-only trail).
TERMINAL_STATUSES: FrozenSet[str] = frozenset({STATUS_COMPLETED, STATUS_DISMISSED})

# Allowed transitions: from → set of allowed next states.
ALLOWED_TRANSITIONS: Dict[str, FrozenSet[str]] = {
    STATUS_PENDING: frozenset({
        STATUS_IN_PROGRESS, STATUS_PARTIALLY_COMPLETED,
        STATUS_COMPLETED, STATUS_POSTPONED, STATUS_DISMISSED, STATUS_BLOCKED,
    }),
    STATUS_IN_PROGRESS: frozenset({
        STATUS_PARTIALLY_COMPLETED, STATUS_COMPLETED,
        STATUS_POSTPONED, STATUS_BLOCKED, STATUS_DISMISSED, STATUS_IN_PROGRESS,
    }),
    STATUS_PARTIALLY_COMPLETED: frozenset({
        STATUS_IN_PROGRESS, STATUS_PARTIALLY_COMPLETED,
        STATUS_COMPLETED, STATUS_POSTPONED, STATUS_BLOCKED, STATUS_DISMISSED,
    }),
    STATUS_POSTPONED: frozenset({
        STATUS_IN_PROGRESS, STATUS_DISMISSED, STATUS_BLOCKED, STATUS_POSTPONED,
    }),
    STATUS_BLOCKED: frozenset({
        STATUS_IN_PROGRESS, STATUS_POSTPONED, STATUS_DISMISSED,
    }),
    STATUS_COMPLETED: frozenset(),  # terminal
    STATUS_DISMISSED: frozenset(),  # terminal
}


class InvalidTransition(Exception):
    """Raised when a transition is not allowed by the state machine."""

    def __init__(self, current: str, requested: str):
        self.current = current
        self.requested = requested
        super().__init__(f"Transizione non permessa: {current} → {requested}")


def can_transition(current: str, target: str) -> bool:
    if current not in ACTION_STATUSES:
        return False
    if target not in ACTION_STATUSES:
        return False
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


# Mapping from Action Center statuses to the legacy Decision.status field
# (which only knows open/in_progress/completed/dismissed). This preserves
# backward compatibility with older clients.
def legacy_status_for(action_status: str) -> str:
    return {
        STATUS_PENDING: "open",
        STATUS_IN_PROGRESS: "in_progress",
        STATUS_PARTIALLY_COMPLETED: "in_progress",
        STATUS_COMPLETED: "completed",
        STATUS_POSTPONED: "open",
        STATUS_DISMISSED: "dismissed",
        STATUS_BLOCKED: "open",
    }.get(action_status, "open")
