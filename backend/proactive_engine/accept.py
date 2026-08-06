"""Accept handlers — do something real when possible; never fake completion."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from proactive_engine.models import Suggestion, now_iso

logger = logging.getLogger("ora.proactive_engine.accept")


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


async def handle_accept(db, user_id: str, suggestion: Suggestion) -> Dict[str, Any]:
    kind = (suggestion.action.kind if suggestion.action else "") or ""
    if suggestion.type == "study" or kind == "recover_session":
        return await _accept_study_recovery(db, user_id, suggestion)
    if suggestion.type == "travel" or kind == "prep":
        return await _accept_travel_prep(db, user_id, suggestion)
    if suggestion.type == "documents" or kind == "flashcards":
        return await _accept_documents_flashcards(db, user_id, suggestion)
    if suggestion.type == "calendar" or kind == "modify_event":
        return await _accept_calendar_modify(db, user_id, suggestion)
    return {
        "ok": True,
        "effect": "marked_accepted",
        "next_action": (suggestion.action.route if suggestion.action else None),
        "honesty": "No typed handler — accepted + route preserved; nothing fabricated.",
    }


async def _accept_study_recovery(db, user_id: str, suggestion: Suggestion) -> Dict[str, Any]:
    plan_id = suggestion.study_plan_id or (suggestion.action.params or {}).get("plan_id")
    if not plan_id:
        return {
            "ok": True,
            "effect": "marked_accepted",
            "honesty": "No plan_id — cannot create recovery session.",
        }
    plan = await db.study_plans.find_one({"id": plan_id, "user_id": user_id}, {"_id": 0})
    if not plan:
        return {"ok": False, "error": "plan_not_found"}

    # Schedule recovery tomorrow in preferred range or 18:00 Europe/Rome (~16:00 UTC)
    now = datetime.now(timezone.utc)
    start = (now + timedelta(days=1)).replace(hour=16, minute=0, second=0, microsecond=0)
    ranges = plan.get("preferred_ranges") or []
    if ranges and isinstance(ranges[0], dict):
        try:
            hh, mm = str(ranges[0].get("start") or "18:00").split(":")
            # preferred is local; approximate as UTC+2 → subtract 2h
            local_h = int(hh)
            start = (now + timedelta(days=1)).replace(
                hour=max(0, local_h - 2), minute=int(mm or 0), second=0, microsecond=0,
            )
        except Exception:
            pass
    dur = int(plan.get("daily_minutes") or 60)
    end = start + timedelta(minutes=dur)
    exam = plan.get("exam_name") or "studio"
    session = {
        "id": _uid("ssn"),
        "plan_id": plan_id,
        "user_id": user_id,
        "session_type": "study",
        "status": "planned",
        "title": f"Recupero — {exam}",
        "topic": "Recupero sessioni saltate",
        "starts_at": start.isoformat(),
        "ends_at": end.isoformat(),
        "duration_minutes": dur,
        "document_ids": list(plan.get("document_ids") or []),
        "meta": {
            "recovery": True,
            "from_suggestion_id": suggestion.id,
            "skipped_session_ids": (
                (suggestion.action.params or {}).get("skipped_session_ids")
                or ((suggestion.meta or {}).get("evidence") or {}).get("skipped_session_ids")
                or []
            ),
        },
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.study_sessions.update_one(
        {"id": session["id"]}, {"$set": session}, upsert=True,
    )
    # Append to plan.sessions if present
    sessions = list(plan.get("sessions") or [])
    sessions.append(session)
    await db.study_plans.update_one(
        {"id": plan_id, "user_id": user_id},
        {
            "$set": {
                "sessions": sessions,
                "updated_at": now_iso(),
                "next_recovery_session_id": session["id"],
            },
        },
    )
    if suggestion.goal_id:
        await db.goals.update_one(
            {"id": suggestion.goal_id, "user_id": user_id},
            {
                "$set": {
                    "next_action": f"Sessione di recupero: {session['title']}",
                    "updated_at": now_iso(),
                },
            },
        )
    return {
        "ok": True,
        "effect": "recovery_session_created",
        "session_id": session["id"],
        "plan_id": plan_id,
        "starts_at": session["starts_at"],
        "route": f"/study-plan/{plan_id}",
        "honesty": "Created a planned recovery study session; did not mark skipped sessions completed.",
    }


async def _accept_travel_prep(db, user_id: str, suggestion: Suggestion) -> Dict[str, Any]:
    tp_id = suggestion.travel_project_id or (suggestion.action.params or {}).get("travel_project_id")
    if not tp_id:
        return {
            "ok": True,
            "effect": "marked_accepted",
            "route": suggestion.action.route if suggestion.action else None,
            "honesty": "No travel_project_id — open route only.",
        }
    next_label = "Completa preparativi viaggio (valigia / documenti)"
    await db.travel_projects.update_one(
        {"id": tp_id, "user_id": user_id},
        {"$set": {"next_action": next_label, "updated_at": now_iso()}},
    )
    if suggestion.goal_id:
        await db.goals.update_one(
            {"id": suggestion.goal_id, "user_id": user_id},
            {"$set": {"next_action": next_label, "updated_at": now_iso()}},
        )
    return {
        "ok": True,
        "effect": "travel_prep_next_action",
        "travel_project_id": tp_id,
        "route": f"/travel-project/{tp_id}",
        "honesty": "Set next_action on travel project/goal; did not invent weather or bookings.",
    }


async def _accept_documents_flashcards(db, user_id: str, suggestion: Suggestion) -> Dict[str, Any]:
    doc_id = suggestion.document_id or (suggestion.action.params or {}).get("document_id")
    if not doc_id:
        return {"ok": True, "effect": "marked_accepted", "honesty": "No document_id."}
    # Schedule concrete next action — do not fake flashcard generation without AI path
    await db.documents.update_one(
        {"id": doc_id, "user_id": user_id},
        {
            "$set": {
                "suggested_action": "flashcards",
                "proactive_accepted_at": now_iso(),
                "updated_at": now_iso(),
            },
        },
    )
    if suggestion.goal_id:
        await db.goals.update_one(
            {"id": suggestion.goal_id, "user_id": user_id},
            {
                "$set": {
                    "next_action": f"Genera flashcard dal documento {doc_id}",
                    "updated_at": now_iso(),
                },
            },
        )
    return {
        "ok": True,
        "effect": "flashcards_path_scheduled",
        "document_id": doc_id,
        "route": f"/document/{doc_id}",
        "params": {"mode": "flashcards"},
        "honesty": "Marked document for flashcards path; generation happens in Documents UI/API, not faked here.",
    }


async def _accept_calendar_modify(db, user_id: str, suggestion: Suggestion) -> Dict[str, Any]:
    params = (suggestion.action.params if suggestion.action else {}) or {}
    return {
        "ok": True,
        "effect": "open_modify_path",
        "route": (suggestion.action.route if suggestion.action else "/situazione"),
        "params": params,
        "honesty": "Accept opens conflict review path; does not auto-edit calendar events.",
    }
