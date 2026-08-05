"""Typed upsert strategies — Study/Travel stay domain artifacts; Goal is identity."""
from __future__ import annotations

from typing import Any, Dict, Optional

from goal_engine.lifecycle import status_for_confirm
from goal_engine.models import Goal, GoalProgress
from goal_engine.progress import progress_from_study_plan, progress_from_travel_project


def study_title(plan: Dict[str, Any]) -> str:
    exam = (plan.get("exam_name") or plan.get("subject") or "esame").strip()
    # Product example: "Preparare esame Psicologia"
    if exam.lower().startswith("prepar"):
        return exam
    return f"Preparare esame {exam}"


def travel_title(project: Dict[str, Any]) -> str:
    dest = (project.get("destination") or project.get("title") or "viaggio").strip()
    title = (project.get("title") or "").strip()
    if title and title.lower() not in ("", "viaggio", "vacanza"):
        # Prefer "Vacanza Calabria"-style if title already good
        if "vacanza" in title.lower() or "viaggio" in title.lower():
            return title
    if dest.lower().startswith("vacanza"):
        return dest
    return f"Vacanza {dest}"


def goal_from_study_plan(
    plan: Dict[str, Any],
    *,
    effects: Optional[Dict[str, Any]] = None,
) -> Goal:
    effects = effects or {}
    prog = progress_from_study_plan(plan)
    cal_ids = list(effects.get("calendar_ids") or [])
    # Also collect session calendar nodes from plan
    for s in plan.get("sessions") or []:
        if isinstance(s, dict) and s.get("calendar_node_id"):
            if s["calendar_node_id"] not in cal_ids:
                cal_ids.append(s["calendar_node_id"])
    dec_ids = list(effects.get("decision_ids") or [])
    g = Goal(
        user_id=plan["user_id"],
        goal_type="study",
        goal_subtype="exam_preparation",
        title=study_title(plan),
        description=f"Piano di studio per {plan.get('exam_name') or 'esame'}",
        status=status_for_confirm("study"),  # type: ignore[arg-type]
        importance=5,
        urgency=4,
        desired_outcome=f"Superare l'esame di {plan.get('exam_name') or 'studio'}",
        current_state="Piano attivo",
        next_action=effects.get("next_focus_hint"),
        brain_node_id=plan.get("brain_node_id") or (effects.get("brain") or {}).get("brain_node_id"),
        project_id=plan.get("project_id"),
        study_plan_id=plan.get("id"),
        source_action_session_id=plan.get("action_session_id"),
        idempotency_key=plan.get("idempotency_key"),
        linked_documents=list(plan.get("document_ids") or []),
        linked_calendar_events=cal_ids,
        linked_decisions=dec_ids,
        target_date=plan.get("exam_date"),
        created_from={
            "intent": "study",
            "intent_subtype": "exam_preparation",
            "source_type": plan.get("source_type") or "study_plan",
            "source_id": plan.get("source_id") or plan.get("source_priority_id"),
            "artifact": "study_plan",
            "study_plan_id": plan.get("id"),
        },
    )
    g.apply_progress(prog)
    return g


def goal_from_travel_project(
    project: Dict[str, Any],
    *,
    effects: Optional[Dict[str, Any]] = None,
) -> Goal:
    effects = effects or {}
    prog = progress_from_travel_project(project)
    cal_ids = list(effects.get("calendar_ids") or [])
    for ev in project.get("calendar_events") or []:
        if isinstance(ev, dict):
            nid = ev.get("life_node_id") or ev.get("google_event_id")
            if nid and nid not in cal_ids:
                cal_ids.append(nid)
    places = []
    if project.get("destination"):
        places.append(project["destination"])
    people = list(project.get("companion_names") or [])
    g = Goal(
        user_id=project["user_id"],
        goal_type="travel",
        goal_subtype="vacation",
        title=travel_title(project),
        description=f"Vacanza a {project.get('destination') or 'destinazione'}",
        status=status_for_confirm("travel"),  # type: ignore[arg-type]
        importance=3,
        urgency=3,
        desired_outcome=f"Completare la vacanza a {project.get('destination') or 'destinazione'}",
        current_state=f"Fase: {project.get('phase') or 'upcoming'}",
        next_action=effects.get("next_focus_hint"),
        brain_node_id=project.get("brain_node_id") or (effects.get("brain") or {}).get("brain_node_id"),
        project_id=project.get("project_id"),
        travel_project_id=project.get("id"),
        source_action_session_id=project.get("action_session_id"),
        idempotency_key=project.get("idempotency_key"),
        linked_documents=list(project.get("document_ids") or []),
        linked_calendar_events=cal_ids,
        linked_decisions=list(effects.get("decision_ids") or []),
        linked_places=places,
        linked_people=people,
        start_date=project.get("start_date"),
        target_date=project.get("end_date"),
        created_from={
            "intent": "travel",
            "intent_subtype": "vacation",
            "source_type": project.get("source_type") or "travel_project",
            "source_id": project.get("source_id") or project.get("source_priority_id"),
            "artifact": "travel_project",
            "travel_project_id": project.get("id"),
        },
    )
    g.apply_progress(prog)
    return g
