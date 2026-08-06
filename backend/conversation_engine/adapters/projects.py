"""Projects adapter — read/link Action Engine projects only (no domain logic)."""
from __future__ import annotations

from typing import Any, Dict, Optional


class ProjectsAdapter:
    """Surface project artifacts created by Action Engine / Study / Travel."""

    def __init__(self, db):
        self.db = db

    async def get_action_project(self, user_id: str, project_id: str) -> Optional[Dict[str, Any]]:
        if not project_id:
            return None
        return await self.db.action_projects.find_one(
            {"id": project_id, "user_id": user_id},
            {"_id": 0},
        )

    async def get_study_plan(self, user_id: str, plan_id: str) -> Optional[Dict[str, Any]]:
        if not plan_id:
            return None
        return await self.db.study_plans.find_one(
            {"id": plan_id, "user_id": user_id},
            {"_id": 0},
        )

    async def get_travel_project(self, user_id: str, project_id: str) -> Optional[Dict[str, Any]]:
        if not project_id:
            return None
        return await self.db.travel_projects.find_one(
            {"id": project_id, "user_id": user_id},
            {"_id": 0},
        )

    @staticmethod
    def refs_from_ae_session(ae: Optional[Dict[str, Any]]) -> list[Dict[str, Any]]:
        """Extract project-like refs from an AE session public payload."""
        if not ae:
            return []
        out: list[Dict[str, Any]] = []
        proj = ae.get("project") or {}
        if proj.get("project_id"):
            out.append({
                "kind": "project",
                "id": proj["project_id"],
                "label": proj.get("title") or "Progetto",
            })
        meta = ae.get("meta") or {}
        if meta.get("study_plan_id"):
            out.append({
                "kind": "study_plan",
                "id": meta["study_plan_id"],
                "label": "Piano di studio",
            })
        if meta.get("travel_project_id"):
            out.append({
                "kind": "travel_project",
                "id": meta["travel_project_id"],
                "label": "Progetto viaggio",
            })
        return out
