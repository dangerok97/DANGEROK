"""Action projects — lightweight multi-step aggregators (no separate Projects domain)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from action_engine.models import ProjectLink, now_iso


def _pid() -> str:
    return f"aproj_{uuid.uuid4().hex[:12]}"


async def create_or_link_project(
    db,
    *,
    user_id: str,
    title: str,
    flow: str,
    session_id: str,
    brain_node_id: Optional[str],
    source_type: Optional[str],
    source_id: Optional[str],
    similar: Optional[dict],
    answers: Dict[str, Any],
) -> tuple[ProjectLink, dict]:
    """Create action_project or propose merge with similar."""
    merge_meta = None
    if similar and similar.get("id"):
        # Do not auto-merge: propose, create new linked project unless user merges later
        merge_meta = {
            "merge_candidate_id": similar["id"],
            "merge_candidate_title": similar.get("title") or similar.get("label"),
        }

    doc = {
        "id": _pid(),
        "user_id": user_id,
        "title": title[:160],
        "flow": flow,
        "status": "active",
        "session_ids": [session_id],
        "brain_node_id": brain_node_id,
        "source_type": source_type,
        "source_id": source_id,
        "answers": dict(answers or {}),
        "linked": {
            "documents": [source_id] if source_type in ("document", "study", "document_action", "admin") and source_id else [],
            "calendar_event_ids": [],
            "reminder_ids": [],
            "decision_ids": [],
            "task_ids": [],
            "flashcard_doc_ids": [],
        },
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "merge_proposal": merge_meta,
    }
    await db.action_projects.insert_one(doc)
    link = ProjectLink(
        project_id=doc["id"],
        title=doc["title"],
        created=True,
        merge_candidate_id=(merge_meta or {}).get("merge_candidate_id"),
        merge_candidate_title=(merge_meta or {}).get("merge_candidate_title"),
    )
    return link, doc


async def update_project_links(
    db,
    project_id: str,
    user_id: str,
    *,
    calendar_event_ids: Optional[List[str]] = None,
    reminder_ids: Optional[List[str]] = None,
    decision_ids: Optional[List[str]] = None,
    task_ids: Optional[List[str]] = None,
    flashcard_doc_ids: Optional[List[str]] = None,
    answers: Optional[Dict[str, Any]] = None,
    next_focus_hint: Optional[str] = None,
) -> Optional[dict]:
    q = {"id": project_id, "user_id": user_id}
    doc = await db.action_projects.find_one(q, {"_id": 0})
    if not doc:
        return None
    linked = doc.get("linked") or {}
    def _extend(key, vals):
        if not vals:
            return
        cur = list(linked.get(key) or [])
        for v in vals:
            if v and v not in cur:
                cur.append(v)
        linked[key] = cur

    _extend("calendar_event_ids", calendar_event_ids)
    _extend("reminder_ids", reminder_ids)
    _extend("decision_ids", decision_ids)
    _extend("task_ids", task_ids)
    _extend("flashcard_doc_ids", flashcard_doc_ids)

    updates: Dict[str, Any] = {
        "linked": linked,
        "updated_at": now_iso(),
    }
    if answers is not None:
        updates["answers"] = {**(doc.get("answers") or {}), **answers}
    if next_focus_hint:
        updates["next_focus_hint"] = next_focus_hint

    await db.action_projects.update_one(q, {"$set": updates})
    doc.update(updates)
    return doc


async def merge_projects(db, *, user_id: str, source_id: str, target_id: str) -> dict:
    src = await db.action_projects.find_one({"id": source_id, "user_id": user_id}, {"_id": 0})
    tgt = await db.action_projects.find_one({"id": target_id, "user_id": user_id}, {"_id": 0})
    if not src or not tgt:
        return {"ok": False, "error": "project_not_found"}
    linked = tgt.get("linked") or {}
    for key, vals in (src.get("linked") or {}).items():
        cur = list(linked.get(key) or [])
        for v in vals or []:
            if v and v not in cur:
                cur.append(v)
        linked[key] = cur
    sessions = list(dict.fromkeys((tgt.get("session_ids") or []) + (src.get("session_ids") or [])))
    await db.action_projects.update_one(
        {"id": target_id, "user_id": user_id},
        {"$set": {
            "linked": linked,
            "session_ids": sessions,
            "updated_at": now_iso(),
            "merged_from": list(dict.fromkeys((tgt.get("merged_from") or []) + [source_id])),
        }},
    )
    await db.action_projects.update_one(
        {"id": source_id, "user_id": user_id},
        {"$set": {"status": "merged", "merged_into": target_id, "updated_at": now_iso()}},
    )
    return {"ok": True, "project_id": target_id, "merged_from": source_id}
