"""Goal type / status vocabulary for the Goal Engine."""
from __future__ import annotations

from typing import Literal

# Aligns with Action Engine flows / Intent kinds (product Goal types).
GoalType = Literal[
    "study",
    "travel",
    "event",
    "medical",
    "admin",
    "generic",
    "project",
    "other",
]

GoalSubtype = Literal[
    "exam_preparation",
    "vacation",
    "trip",
    "appointment",
    "habit",
    "generic",
    "other",
]

# Product lifecycle (shadow phase uses planning → active on confirm).
GoalStatus = Literal[
    "idea",
    "planning",
    "active",
    "waiting",
    "blocked",
    "paused",
    "completed",
    "cancelled",
    "archived",
]

GOAL_STATUSES: tuple[str, ...] = (
    "idea",
    "planning",
    "active",
    "waiting",
    "blocked",
    "paused",
    "completed",
    "cancelled",
    "archived",
)

ACTIVE_LIKE: tuple[str, ...] = (
    "idea",
    "planning",
    "active",
    "waiting",
    "blocked",
    "paused",
)

TERMINAL: tuple[str, ...] = ("completed", "cancelled", "archived")
