"""ORA Goal Engine — thin identity/lifecycle layer (shadow foundation).

Pipeline: Input → Intent → Goal Engine → Action Engine → Study/Travel → Projects → Brain → Home

This phase: backend-only, invisible. No Goal UX. Home unchanged.
Study/Travel remain typed artifacts; action_projects remain link bags.
"""
from goal_engine.models import Goal, GoalCreateBody, GoalPatchBody
from goal_engine.service import GoalService, get_goal_service, goal_engine_enabled
from goal_engine.router import router as goal_engine_router

__all__ = [
    "Goal",
    "GoalCreateBody",
    "GoalPatchBody",
    "GoalService",
    "get_goal_service",
    "goal_engine_enabled",
    "goal_engine_router",
]
