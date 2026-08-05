"""Goal dedupe — never create identical Goals; prefer update / merge candidate."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from goal_engine.goal_types import ACTIVE_LIKE
from goal_engine.models import Goal
from goal_engine.repository import GoalRepository


def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"\s+", " ", s)
    # Light Italian noise strip for exam/vacation titles
    for noise in ("preparare esame", "preparazione esame", "esame di", "esame", "vacanza", "viaggio a", "viaggio"):
        if s.startswith(noise + " "):
            s = s[len(noise) + 1 :].strip()
    return s


def titles_equivalent(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    return False


class GoalDeduper:
    def __init__(self, repo: GoalRepository):
        self.repo = repo

    async def find_existing(
        self,
        user_id: str,
        *,
        idempotency_key: Optional[str] = None,
        study_plan_id: Optional[str] = None,
        travel_project_id: Optional[str] = None,
        title: Optional[str] = None,
        goal_type: Optional[str] = None,
    ) -> Optional[Goal]:
        """Ordered lookup: idempotency → artifact link → same-type title match."""
        if idempotency_key:
            hit = await self.repo.find_by_idempotency(user_id, idempotency_key)
            if hit and hit.status not in ("cancelled", "archived"):
                return hit
        if study_plan_id:
            hit = await self.repo.find_by_study_plan(user_id, study_plan_id)
            if hit:
                return hit
        if travel_project_id:
            hit = await self.repo.find_by_travel_project(user_id, travel_project_id)
            if hit:
                return hit
        if title and goal_type:
            active = await self.repo.list_active(user_id)
            for g in active:
                if g.goal_type != goal_type:
                    continue
                if titles_equivalent(g.title, title):
                    return g
        return None

    def merge_fields(self, existing: Goal, incoming: Goal) -> Goal:
        """Internal merge of non-empty incoming fields onto existing (keep id)."""
        keep_id = existing.id
        keep_created = existing.created_at
        data = existing.model_dump()
        inc = incoming.model_dump()
        for key, val in inc.items():
            if key in ("id", "user_id", "created_at", "merged_into_id"):
                continue
            if val is None or val == "" or val == [] or val == {}:
                continue
            if key == "progress" and isinstance(val, dict):
                # Prefer richer progress (higher total_units or newer)
                old = data.get("progress") or {}
                if (val.get("total_units") or 0) >= (old.get("total_units") or 0):
                    data["progress"] = val
                continue
            if key.startswith("linked_") and isinstance(val, list):
                prev = list(data.get(key) or [])
                for item in val:
                    if item not in prev:
                        prev.append(item)
                data[key] = prev
                continue
            if key == "created_from" and isinstance(val, dict):
                merged = dict(data.get("created_from") or {})
                merged.update({k: v for k, v in val.items() if v is not None})
                data["created_from"] = merged
                continue
            data[key] = val
        data["id"] = keep_id
        data["created_at"] = keep_created
        out = Goal(**data)
        # Re-derive completion %
        ratio = float((out.progress.ratio if out.progress else 0.0) or 0.0)
        out.completion_percentage = round(max(0.0, min(1.0, ratio)) * 100.0, 2)
        return out

    async def candidates_for_merge(
        self, user_id: str, goal: Goal, *, limit: int = 10,
    ) -> List[Dict[str, Any]]:
        active = await self.repo.list_active(user_id)
        out: List[Dict[str, Any]] = []
        for g in active:
            if g.id == goal.id:
                continue
            if g.goal_type != goal.goal_type:
                continue
            if titles_equivalent(g.title, goal.title):
                out.append({"id": g.id, "title": g.title, "status": g.status, "reason": "title"})
            elif goal.study_plan_id and g.study_plan_id == goal.study_plan_id:
                out.append({"id": g.id, "title": g.title, "status": g.status, "reason": "study_plan"})
            elif goal.travel_project_id and g.travel_project_id == goal.travel_project_id:
                out.append({"id": g.id, "title": g.title, "status": g.status, "reason": "travel_project"})
            if len(out) >= limit:
                break
        return out
