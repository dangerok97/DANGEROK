"""Progress projection from Study sessions / Travel prep — never fake fixed %."""
from __future__ import annotations

from typing import Any, Dict, Optional

from goal_engine.models import GoalProgress, now_iso


def progress_from_study_plan(plan: Dict[str, Any]) -> GoalProgress:
    sessions = plan.get("sessions") or []
    total = len(sessions)
    completed = sum(1 for s in sessions if (s.get("status") if isinstance(s, dict) else getattr(s, "status", None)) == "completed")
    ratio = (completed / total) if total else 0.0
    # Prefer nested progress if plan.public() already computed
    nested = plan.get("progress") or {}
    if isinstance(nested, dict) and nested.get("total_sessions") is not None:
        total = int(nested.get("total_sessions") or total)
        completed = int(nested.get("completed_sessions") or completed)
        ratio = float(nested.get("ratio") if nested.get("ratio") is not None else ((completed / total) if total else 0.0))
    label = None
    if total:
        label = f"{completed}/{total} sessioni"
    next_s = nested.get("next_session") if isinstance(nested, dict) else None
    phase = None
    if plan.get("status") == "completed":
        phase = "completed"
        ratio = 1.0
    elif plan.get("status") == "paused":
        phase = "paused"
    elif total and completed == 0:
        phase = "not_started"
    elif total and completed < total:
        phase = "in_progress"
    elif total and completed >= total:
        phase = "sessions_done"
        ratio = 1.0
    return GoalProgress(
        ratio=max(0.0, min(1.0, ratio)),
        label=label,
        phase=phase,
        completed_units=completed,
        total_units=total,
        source="study_sessions",
        updated_at=now_iso(),
        details={"next_session": next_s, "exam_date": plan.get("exam_date")},
    )


def progress_from_travel_project(project: Dict[str, Any]) -> GoalProgress:
    prep = project.get("prep_items") or []
    total = len(prep)
    # Prep items have no done flag in v1 — use phase as qualitative progress only
    phase = project.get("phase") or "upcoming"
    # Map phases to soft ratios (honest, not fake session %); 0 when no prep and upcoming
    phase_ratio = {
        "upcoming": 0.05 if total else 0.0,
        "days_until": 0.15 if total else 0.1,
        "departure_day": 0.5,
        "during": 0.75,
        "welcome_back": 1.0,
    }.get(phase, 0.0)
    # If prep items later gain completion flags, prefer that:
    done = sum(
        1 for p in prep
        if isinstance(p, dict) and p.get("done") is True
    )
    if total and done:
        ratio = done / total
        label = f"{done}/{total} prep"
        source = "travel_prep"
    else:
        ratio = phase_ratio
        label = f"fase: {phase}"
        source = "travel_phase"
        # Do not invent a mid-progress % without evidence — cap upcoming at low
        if phase == "upcoming" and not total:
            ratio = 0.0
            label = "in preparazione"
    if project.get("status") == "completed" or phase == "welcome_back":
        ratio = 1.0
        label = "completato"
    return GoalProgress(
        ratio=max(0.0, min(1.0, float(ratio))),
        label=label,
        phase=phase,
        completed_units=done,
        total_units=total,
        source=source,
        updated_at=now_iso(),
        details={
            "destination": project.get("destination"),
            "start_date": project.get("start_date"),
            "end_date": project.get("end_date"),
        },
    )


async def compute_progress(
    db,
    user_id: str,
    *,
    study_plan_id: Optional[str] = None,
    travel_project_id: Optional[str] = None,
) -> GoalProgress:
    if study_plan_id:
        plan = await db.study_plans.find_one(
            {"id": study_plan_id, "user_id": user_id}, {"_id": 0},
        )
        if plan:
            # Prefer live sessions collection when present
            sessions = await db.study_sessions.find(
                {"plan_id": study_plan_id, "user_id": user_id}, {"_id": 0},
            ).to_list(200)
            if sessions:
                plan = {**plan, "sessions": sessions}
            return progress_from_study_plan(plan)
    if travel_project_id:
        proj = await db.travel_projects.find_one(
            {"id": travel_project_id, "user_id": user_id}, {"_id": 0},
        )
        if proj:
            return progress_from_travel_project(proj)
    return GoalProgress(source="none", updated_at=now_iso())
