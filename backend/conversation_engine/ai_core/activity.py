"""Read-only UI telemetry. No prompts, arguments, evidence or execution authority."""
from __future__ import annotations

import time
from typing import Any

# Exact capability identities, never keywords in a person's words or model prose.
AREA_CAPABILITIES = {
    "memory": ("search_life_memory", "search_my_life", "get_profile_snapshot", "remember"),
    "calendar": ("get_calendar", "calendar_search", "get_calendar_events", "create_calendar_event", "update_calendar_event", "cancel_calendar_event"),
    "places": ("get_current_location", "get_current_presence", "get_recent_presence_context", "list_life_places", "get_life_place", "save_life_place", "record_location_observation", "open_navigation", "get_current_place", "get_time_at_place", "get_journeys_between_places", "get_day_patterns", "get_route", "resolve_place"),
    "documents": ("search_documents", "read_document", "list_session_files", "get_file_context", "get_file_content", "link_file_context", "look_at_image"),
    "finances": ("what_do_i_know_about_money", "confirm_money_question"),
    "calls": ("prepare_a_phone_call",),
}
CAPABILITY_AREAS = {cap: area for area, caps in AREA_CAPABILITIES.items() for cap in caps}
AREAS = frozenset((*AREA_CAPABILITIES, "people", "home"))
PHASES = frozenset(("processing", "context", "tool", "done", "error"))


def public_activity(meta: dict | None) -> dict | None:
    value = (meta or {}).get("presence_activity")
    if not isinstance(value, dict) or value.get("phase") not in PHASES:
        return None
    return {key: value.get(key) for key in ("request_id", "sequence", "phase", "area", "touched", "updated_at")}


async def report_activity(db, sess, phase: str, *, area: str | None = None, keep_area: bool = False, reset: bool = False) -> None:
    request_id = (sess.meta or {}).get("activity_request_id")
    if not request_id or phase not in PHASES:
        return
    previous = {} if reset else (public_activity(sess.meta) or {})
    area = previous.get("area") if keep_area else area
    area = area if area in AREAS else None
    touched = list(previous.get("touched") or [])
    if area and area not in touched:
        touched.append(area)
    activity = {
        "request_id": request_id,
        "sequence": int(previous.get("sequence") or 0) + 1,
        "phase": phase,
        "area": area,
        "touched": touched[-8:],
        "updated_at": time.time(),
    }
    sess.meta["presence_activity"] = activity
    if db is None:
        return
    try:
        # Owner scope is required even for presentation-only metadata.
        await db["conversation_sessions"].update_one(
            {"id": sess.id, "user_id": sess.user_id},
            {"$set": {"meta.activity_request_id": request_id, "meta.presence_activity": activity}},
        )
    except Exception:
        # The visual must never make a successful conversation fail.
        pass


async def read_activity(db, user_id: str, request_id: str) -> dict[str, Any]:
    row = await db["conversation_sessions"].find_one(
        {"user_id": user_id, "meta.activity_request_id": request_id},
        {"_id": 0, "meta.presence_activity": 1, "meta.working_on": 1},
    )
    meta = (row or {}).get("meta") or {}
    activity = public_activity(meta)
    if activity and activity.get("request_id") != request_id:
        activity = None
    # Expired workers cannot leave a heartbeat running after a lost request.
    if activity and time.time() - float(activity.get("updated_at") or 0) > 120:
        activity = None
    hint = str(meta.get("working_on") or "")[:120] if activity and activity["phase"] == "tool" else ""
    return {"ok": True, "activity": activity, "working_on": hint}
