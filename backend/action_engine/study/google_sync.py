"""Google Calendar sync for study sessions — real create/update/delete when connected.

Uses connector id ``calendar_google`` (see connectors.google_calendar.scopes).
Partial failure is OK; tokens are never logged.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ora.action_engine.study.google")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gcal_service(db):
    # Prefer the app singleton (vault + permissions wired).
    try:
        from deps import get_google_calendar_service
        return get_google_calendar_service()
    except Exception:
        from connectors.google_calendar.service import GoogleCalendarService
        from permissions import PermissionService
        from security import get_token_vault

        return GoogleCalendarService(
            db=db,
            permissions=PermissionService(db),
            ingestion=None,
            vault=get_token_vault(),
        )


async def _instance_for_user(db, user_id: str) -> Optional[dict]:
    from connectors.google_calendar.scopes import CONNECTOR_ID

    curs = db.connector_instances.find(
        {
            "user_id": user_id,
            "connector_id": CONNECTOR_ID,
            "status": {"$in": ["connected", "active", "authorized"]},
        },
        {"_id": 0},
    ).sort("updated_at", -1)
    items = await curs.to_list(10)
    if not items:
        return None
    real = [
        i for i in items
        if (i.get("metadata") or {}).get("provider_mode") == "real"
        or not str((i.get("metadata") or {}).get("provider_mode") or "").startswith("fake")
    ]
    pool = real or items
    return pool[0]


async def is_google_connected(db, user_id: str) -> bool:
    try:
        return bool(await _instance_for_user(db, user_id))
    except Exception:
        return False


async def _resolve_calendar_id(gcal, user_id: str, inst: dict) -> Optional[str]:
    meta = inst.get("metadata") or {}
    cal_id = meta.get("default_calendar_id") or (inst.get("selected_resource_ids") or [None])[0]
    if cal_id:
        return cal_id
    try:
        cals = await gcal.list_calendars_for_instance(user_id=user_id, instance_id=inst["id"])
        primary = next((c for c in cals if c.get("primary")), None)
        pick = primary or (cals[0] if cals else None)
        return (pick or {}).get("id") or "primary"
    except Exception as e:
        logger.info("resolve calendar failed: %s — using primary", type(e).__name__)
        return "primary"


async def free_windows_hint(
    db, user_id: str, *, days: int = 14,
) -> List[Dict[str, Any]]:
    """Best-effort busy windows — soft, never invents free slots."""
    if not await is_google_connected(db, user_id):
        return []
    try:
        gcal = _gcal_service(db)
        inst = await _instance_for_user(db, user_id)
        if not inst:
            return []
        access = await gcal._get_access_token(user_id=user_id, instance=inst)
        cal_id = await _resolve_calendar_id(gcal, user_id, inst) or "primary"
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        page = await gcal.provider.list_events(
            access_token=access,
            calendar_id=cal_id,
            time_min=now.isoformat(),
            time_max=(now + timedelta(days=days)).isoformat(),
            max_results=40,
        )
        busy = []
        for ev in page.events or []:
            start = (ev.get("start") or {})
            end = (ev.get("end") or {})
            busy.append({
                "start": start.get("dateTime") or start.get("date"),
                "end": end.get("dateTime") or end.get("date"),
                "title": ev.get("summary"),
            })
        return [{"kind": "busy", "events": busy[:20]}]
    except Exception as e:
        logger.info("free windows unavailable: %s", type(e).__name__)
        return []


def _session_event_body(plan: dict, session: dict) -> Dict[str, Any]:
    from documents.intelligence.google_sync import build_google_event_body

    draft = {
        "id": session.get("id") or "study_session",
        "title": session.get("title") or f"Studio: {plan.get('exam_name')}",
        "description": f"Sessione {(session.get('session_type') or 'study')} — {session.get('topic') or ''}",
        "start_datetime": session.get("starts_at"),
        "end_datetime": session.get("ends_at"),
        "timezone": plan.get("timezone") or "Europe/Rome",
        "source_document_id": (plan.get("document_ids") or [None])[0],
    }
    return build_google_event_body(draft, macro_category="education")


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
        "calendar_id": None,
    }
    if not plan.get("calendar_sync"):
        result["skipped"].append("sync_disabled")
        return result

    inst = await _instance_for_user(db, user_id)
    connected = bool(inst)
    result["connected"] = connected
    if not connected:
        result["banner"] = {
            "level": "info",
            "message": "Google Calendar non collegato — piano attivo su ORA. Collega Google per sincronizzare.",
        }
        result["skipped"].append("not_connected")
        return result

    gcal = _gcal_service(db)
    try:
        access = await gcal._get_access_token(user_id=user_id, instance=inst)
        cal_id = await _resolve_calendar_id(gcal, user_id, inst)
        if not cal_id:
            result["failed"].append({"error": "no_calendar"})
            result["banner"] = {
                "level": "warning",
                "message": "Nessun calendario Google disponibile per la sync.",
            }
            return result
        result["calendar_id"] = cal_id
    except Exception as e:
        logger.info("google auth for sync failed: %s", type(e).__name__)
        result["failed"].append({"error": type(e).__name__})
        result["banner"] = {
            "level": "warning",
            "message": "Sync Google temporaneamente non disponibile. Riprova più tardi.",
        }
        return result

    for s in sessions:
        if s.get("status") not in ("planned", "in_progress", "snoozed", None):
            continue
        if s.get("google_event_id"):
            result["synced"].append({
                "session_id": s.get("id"),
                "event_id": s["google_event_id"],
                "calendar_id": s.get("google_calendar_id") or cal_id,
                "status": "exists",
            })
            continue
        try:
            body = _session_event_body(plan, s)
            created = await gcal.provider.create_event(
                access_token=access, calendar_id=cal_id, body=body,
            )
            eid = (created or {}).get("id")
            if eid:
                await db.study_sessions.update_one(
                    {"id": s["id"], "user_id": user_id},
                    {"$set": {
                        "google_event_id": eid,
                        "google_calendar_id": cal_id,
                        "google_sync_status": "synced",
                        "updated_at": _now_iso(),
                    }},
                )
                # Keep embedded plan.sessions in sync when present
                await db.study_plans.update_one(
                    {"id": plan["id"], "user_id": user_id, "sessions.id": s["id"]},
                    {"$set": {
                        "sessions.$.google_event_id": eid,
                        "sessions.$.google_calendar_id": cal_id,
                        "sessions.$.google_sync_status": "synced",
                        "updated_at": _now_iso(),
                    }},
                )
                result["synced"].append({
                    "session_id": s.get("id"),
                    "event_id": eid,
                    "calendar_id": cal_id,
                    "status": "created",
                })
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


async def update_session_google_event(
    db, user_id: str, session: dict, plan: Optional[dict] = None,
) -> Dict[str, Any]:
    """Patch Google event times after snooze/reschedule. No-op if not linked."""
    eid = session.get("google_event_id")
    if not eid:
        return {"ok": False, "skipped": "no_google_event"}
    inst = await _instance_for_user(db, user_id)
    if not inst:
        return {"ok": False, "skipped": "not_connected"}
    gcal = _gcal_service(db)
    try:
        access = await gcal._get_access_token(user_id=user_id, instance=inst)
        cal_id = session.get("google_calendar_id") or await _resolve_calendar_id(gcal, user_id, inst)
        if not plan:
            plan = await db.study_plans.find_one(
                {"id": session.get("plan_id"), "user_id": user_id}, {"_id": 0},
            ) or {}
        body = _session_event_body(plan, session)
        # PATCH only timing + summary fields
        patch = {
            "summary": body.get("summary"),
            "description": body.get("description"),
            "start": body.get("start"),
            "end": body.get("end"),
        }
        updated = await gcal.provider.update_event(
            access_token=access, calendar_id=cal_id, event_id=eid, body=patch,
        )
        await db.study_sessions.update_one(
            {"id": session["id"], "user_id": user_id},
            {"$set": {
                "google_sync_status": "synced",
                "google_calendar_id": cal_id,
                "updated_at": _now_iso(),
            }},
        )
        return {
            "ok": True,
            "event_id": eid,
            "calendar_id": cal_id,
            "updated_start": (updated.get("start") or {}).get("dateTime"),
            "updated_end": (updated.get("end") or {}).get("dateTime"),
        }
    except Exception as e:
        logger.info("google update session fail: %s", type(e).__name__)
        await db.study_sessions.update_one(
            {"id": session["id"], "user_id": user_id},
            {"$set": {"google_sync_status": "failed"}},
        )
        return {"ok": False, "error": type(e).__name__}


async def delete_session_google_event(db, user_id: str, session: dict) -> Dict[str, Any]:
    """Delete linked Google event. Treats 404 as success."""
    eid = session.get("google_event_id")
    if not eid:
        return {"ok": True, "skipped": "no_google_event"}
    inst = await _instance_for_user(db, user_id)
    if not inst:
        return {"ok": False, "skipped": "not_connected"}
    gcal = _gcal_service(db)
    try:
        access = await gcal._get_access_token(user_id=user_id, instance=inst)
        cal_id = session.get("google_calendar_id") or await _resolve_calendar_id(gcal, user_id, inst) or "primary"
        await gcal.provider.delete_event(
            access_token=access, calendar_id=cal_id, event_id=eid,
        )
        await db.study_sessions.update_one(
            {"id": session["id"], "user_id": user_id},
            {"$set": {
                "google_sync_status": "deleted",
                "updated_at": _now_iso(),
            }},
        )
        return {"ok": True, "event_id": eid, "calendar_id": cal_id, "deleted": True}
    except Exception as e:
        logger.info("google delete session fail: %s", type(e).__name__)
        return {"ok": False, "error": type(e).__name__, "event_id": eid}


async def delete_plan_google_events(db, user_id: str, plan_id: str) -> Dict[str, Any]:
    sessions = await db.study_sessions.find(
        {"plan_id": plan_id, "user_id": user_id, "google_event_id": {"$exists": True, "$ne": None}},
        {"_id": 0},
    ).to_list(100)
    results = []
    for s in sessions:
        results.append(await delete_session_google_event(db, user_id, s))
    return {
        "ok": all(r.get("ok") for r in results) if results else True,
        "deleted": [r for r in results if r.get("deleted")],
        "results": results,
    }


async def retry_sync(db, user_id: str, plan_id: str) -> Dict[str, Any]:
    plan = await db.study_plans.find_one({"id": plan_id, "user_id": user_id}, {"_id": 0})
    if not plan:
        return {"ok": False, "error": "not_found"}
    sessions = await db.study_sessions.find(
        {"plan_id": plan_id, "user_id": user_id, "status": {"$in": ["planned", "in_progress", "snoozed"]}},
        {"_id": 0},
    ).to_list(50)
    plan["calendar_sync"] = True
    sync = await sync_plan_sessions(db=db, user_id=user_id, plan=plan, sessions=sessions)
    await db.study_plans.update_one(
        {"id": plan_id, "user_id": user_id},
        {"$set": {"google_sync": sync, "calendar_sync": True, "updated_at": _now_iso()}},
    )
    return {"ok": True, "google_sync": sync}


async def fetch_google_event(db, user_id: str, *, calendar_id: str, event_id: str) -> Optional[dict]:
    """Read-back helper for verification (no secrets in return)."""
    inst = await _instance_for_user(db, user_id)
    if not inst:
        return None
    gcal = _gcal_service(db)
    access = await gcal._get_access_token(user_id=user_id, instance=inst)
    try:
        return await gcal.provider.get_event(
            access_token=access, calendar_id=calendar_id, event_id=event_id,
        )
    except Exception:
        return None
