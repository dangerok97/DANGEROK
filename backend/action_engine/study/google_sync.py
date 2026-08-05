"""Google Calendar sync for study sessions — real events if connected; partial OK."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ora.action_engine.study.google")


async def is_google_connected(db, user_id: str) -> bool:
    try:
        inst = await db.connector_instances.find_one({
            "user_id": user_id,
            "connector_id": "google_calendar",
            "status": {"$in": ["connected", "active", "authorized"]},
        })
        return bool(inst)
    except Exception:
        return False


async def free_windows_hint(
    db, user_id: str, *, days: int = 14,
) -> List[Dict[str, Any]]:
    """Best-effort free windows from upcoming Google events (no invent)."""
    if not await is_google_connected(db, user_id):
        return []
    try:
        from connectors.google_calendar.service import GoogleCalendarService
        # Soft: list next events if service available
        svc = GoogleCalendarService(db)
        if hasattr(svc, "list_upcoming"):
            events = await svc.list_upcoming(user_id, days=days)
        else:
            return []
        busy = []
        for ev in (events or [])[:40]:
            busy.append({
                "start": ev.get("start") or ev.get("start_at"),
                "end": ev.get("end") or ev.get("end_at"),
                "title": ev.get("title") or ev.get("summary"),
            })
        return [{"kind": "busy", "events": busy[:20]}]
    except Exception as e:
        logger.info("free windows unavailable: %s", type(e).__name__)
        return []


async def sync_plan_sessions(
    *,
    db,
    user_id: str,
    plan: dict,
    sessions: List[dict],
) -> Dict[str, Any]:
    """Create Google events for planned sessions. Partial failure OK."""
    result: Dict[str, Any] = {
        "connected": False,
        "synced": [],
        "failed": [],
        "skipped": [],
        "banner": None,
    }
    if not plan.get("calendar_sync"):
        result["skipped"].append("sync_disabled")
        return result

    connected = await is_google_connected(db, user_id)
    result["connected"] = connected
    if not connected:
        result["banner"] = {
            "level": "info",
            "message": "Google Calendar non collegato — piano attivo su ORA. Collega Google per sincronizzare.",
        }
        result["skipped"].append("not_connected")
        return result

    try:
        from documents.intelligence.google_sync import (
            GoogleCalendarSyncService,
            build_google_event_body,
        )
    except Exception:
        GoogleCalendarSyncService = None  # type: ignore

    # Prefer connector create_event path
    provider = None
    try:
        from connectors.google_calendar.provider import get_provider_for_user
        provider = await get_provider_for_user(db, user_id)
    except Exception:
        try:
            from connectors.google_calendar.service import GoogleCalendarService
            gsvc = GoogleCalendarService(db)
            if hasattr(gsvc, "create_event"):
                provider = gsvc
        except Exception as e:
            logger.info("google provider missing: %s", type(e).__name__)

    if provider is None and GoogleCalendarSyncService is None:
        result["banner"] = {
            "level": "warning",
            "message": "Sync Google temporaneamente non disponibile. Riprova più tardi.",
        }
        result["failed"].append({"error": "provider_unavailable"})
        return result

    for s in sessions:
        if s.get("status") not in ("planned", "in_progress", None):
            continue
        if s.get("google_event_id"):
            result["synced"].append({"session_id": s.get("id"), "event_id": s["google_event_id"], "status": "exists"})
            continue
        draft = {
            "title": s.get("title") or f"Studio: {plan.get('exam_name')}",
            "description": f"Sessione {(s.get('session_type') or 'study')} — {s.get('topic') or ''}",
            "start_datetime": s.get("starts_at"),
            "end_datetime": s.get("ends_at"),
            "timezone": plan.get("timezone") or "Europe/Rome",
            "source_document_id": (plan.get("document_ids") or [None])[0],
        }
        try:
            if provider and hasattr(provider, "create_event"):
                body = {
                    "summary": draft["title"][:200],
                    "description": (draft["description"] or "")[:500],
                    "start": {"dateTime": draft["start_datetime"]},
                    "end": {"dateTime": draft["end_datetime"]},
                }
                created = await provider.create_event(user_id, body) if "user_id" in provider.create_event.__code__.co_varnames else await provider.create_event(body)
                eid = (created or {}).get("id") if isinstance(created, dict) else None
            else:
                body = build_google_event_body(draft, macro_category="education")
                # Sync service may need draft id — mark failed honestly
                raise RuntimeError("no_direct_create")
            if eid:
                result["synced"].append({"session_id": s.get("id"), "event_id": eid})
                await db.study_sessions.update_one(
                    {"id": s["id"], "user_id": user_id},
                    {"$set": {"google_event_id": eid, "google_sync_status": "synced", "updated_at": datetime.now(timezone.utc).isoformat()}},
                )
            else:
                result["failed"].append({"session_id": s.get("id"), "error": "no_event_id"})
                await db.study_sessions.update_one(
                    {"id": s["id"], "user_id": user_id},
                    {"$set": {"google_sync_status": "failed"}},
                )
        except Exception as e:
            logger.info("google sync session fail: %s", type(e).__name__)
            result["failed"].append({"session_id": s.get("id"), "error": type(e).__name__})
            try:
                await db.study_sessions.update_one(
                    {"id": s["id"], "user_id": user_id},
                    {"$set": {"google_sync_status": "failed"}},
                )
            except Exception:
                pass

    if result["failed"] and result["synced"]:
        result["banner"] = {
            "level": "warning",
            "message": f"Sync parziale: {len(result['synced'])} ok, {len(result['failed'])} fallite. Puoi riprovare.",
        }
    elif result["failed"] and not result["synced"]:
        result["banner"] = {
            "level": "warning",
            "message": "Sync Google non riuscita. Il piano resta attivo su ORA — riprova.",
        }
    return result


async def retry_sync(db, user_id: str, plan_id: str) -> Dict[str, Any]:
    plan = await db.study_plans.find_one({"id": plan_id, "user_id": user_id}, {"_id": 0})
    if not plan:
        return {"ok": False, "error": "not_found"}
    sessions = await db.study_sessions.find(
        {"plan_id": plan_id, "user_id": user_id, "status": {"$in": ["planned", "in_progress"]}},
        {"_id": 0},
    ).to_list(50)
    plan["calendar_sync"] = True
    sync = await sync_plan_sessions(db=db, user_id=user_id, plan=plan, sessions=sessions)
    await db.study_plans.update_one(
        {"id": plan_id, "user_id": user_id},
        {"$set": {"google_sync": sync, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True, "google_sync": sync}
