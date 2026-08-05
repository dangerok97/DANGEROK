"""Google Calendar sync for Travel Project — create only after user confirm.

Uses connector id ``calendar_google`` (same fix as study flow).
Never creates events when calendar_sync is False or Google absent.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ora.action_engine.travel.google")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Reuse study helpers for connector resolution (calendar_google)
async def is_google_connected(db, user_id: str) -> bool:
    from action_engine.study.google_sync import is_google_connected as _study
    return await _study(db, user_id)


def _gcal_service(db):
    from action_engine.study.google_sync import _gcal_service as _s
    return _s(db)


async def _instance_for_user(db, user_id: str):
    from action_engine.study.google_sync import _instance_for_user as _i
    return await _i(db, user_id)


async def _resolve_calendar_id(gcal, user_id: str, inst: dict):
    from action_engine.study.google_sync import _resolve_calendar_id as _r
    return await _r(gcal, user_id, inst)


def _all_day_body(title: str, start_date: str, end_date: str, description: str) -> Dict[str, Any]:
    """Google all-day: end date is exclusive."""
    try:
        from datetime import date as date_cls
        ed = date_cls.fromisoformat(end_date[:10]) + timedelta(days=1)
        end_excl = ed.isoformat()
    except Exception:
        end_excl = end_date[:10]
    return {
        "summary": title,
        "description": description,
        "start": {"date": start_date[:10]},
        "end": {"date": end_excl},
    }


def _timed_body(
    title: str, starts_at: str, ends_at: str, *, timezone_name: str, description: str,
) -> Dict[str, Any]:
    return {
        "summary": title,
        "description": description,
        "start": {"dateTime": starts_at, "timeZone": timezone_name},
        "end": {"dateTime": ends_at, "timeZone": timezone_name},
    }


async def sync_travel_events(
    *,
    db,
    user_id: str,
    project: dict,
) -> Dict[str, Any]:
    """Create Google events for proposed calendar_events. Partial failure OK."""
    result: Dict[str, Any] = {
        "connected": False,
        "synced": [],
        "failed": [],
        "skipped": [],
        "banner": None,
        "calendar_id": None,
    }
    if not project.get("calendar_sync"):
        result["skipped"].append("sync_disabled")
        return result

    inst = await _instance_for_user(db, user_id)
    connected = bool(inst)
    result["connected"] = connected
    if not connected:
        result["banner"] = {
            "level": "info",
            "message": "Google Calendar non collegato — progetto attivo su ORA. Collega Google per sincronizzare.",
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
        logger.info("google auth travel sync failed: %s", type(e).__name__)
        result["failed"].append({"error": type(e).__name__})
        result["banner"] = {
            "level": "warning",
            "message": "Sync Google temporaneamente non disponibile. Riprova più tardi.",
        }
        return result

    tz_name = project.get("timezone") or "Europe/Rome"
    events = list(project.get("calendar_events") or [])
    for ev in events:
        if ev.get("google_event_id"):
            result["synced"].append({
                "event_local_id": ev.get("id"),
                "event_id": ev["google_event_id"],
                "kind": ev.get("kind"),
                "status": "exists",
            })
            continue
        try:
            if ev.get("all_day"):
                body = _all_day_body(
                    ev.get("title") or "Vacanza",
                    ev.get("starts_at") or project.get("start_date"),
                    ev.get("ends_at") or project.get("end_date"),
                    f"Travel Project ORA — {project.get('destination') or ''}",
                )
            else:
                body = _timed_body(
                    ev.get("title") or "Viaggio",
                    ev["starts_at"],
                    ev["ends_at"],
                    timezone_name=tz_name,
                    description=f"Travel Project ORA — {project.get('destination') or ''}",
                )
            created = await gcal.provider.create_event(
                access_token=access, calendar_id=cal_id, body=body,
            )
            eid = (created or {}).get("id")
            if eid:
                await db.travel_projects.update_one(
                    {"id": project["id"], "user_id": user_id, "calendar_events.id": ev["id"]},
                    {"$set": {
                        "calendar_events.$.google_event_id": eid,
                        "calendar_events.$.google_calendar_id": cal_id,
                        "calendar_events.$.google_sync_status": "synced",
                        "updated_at": _now_iso(),
                    }},
                )
                result["synced"].append({
                    "event_local_id": ev.get("id"),
                    "event_id": eid,
                    "kind": ev.get("kind"),
                    "calendar_id": cal_id,
                    "status": "created",
                })
            else:
                result["failed"].append({"event_local_id": ev.get("id"), "error": "no_event_id"})
        except Exception as e:
            logger.info("travel google sync fail: %s", type(e).__name__)
            result["failed"].append({"event_local_id": ev.get("id"), "error": type(e).__name__})

    if result["failed"] and result["synced"]:
        result["banner"] = {
            "level": "warning",
            "message": f"Sync parziale: {len(result['synced'])} ok, {len(result['failed'])} fallite.",
        }
    elif result["failed"] and not result["synced"]:
        result["banner"] = {
            "level": "warning",
            "message": "Sync Google non riuscita. Il progetto resta su ORA — riprova.",
        }
    return result


async def delete_travel_google_events(db, user_id: str, project: dict) -> Dict[str, Any]:
    """Cleanup synthetic Google events (tests / delete). Soft fail."""
    out = {"deleted": [], "failed": []}
    inst = await _instance_for_user(db, user_id)
    if not inst:
        return {**out, "skipped": "not_connected"}
    gcal = _gcal_service(db)
    try:
        access = await gcal._get_access_token(user_id=user_id, instance=inst)
    except Exception as e:
        return {**out, "failed": [{"error": type(e).__name__}]}
    for ev in project.get("calendar_events") or []:
        eid = ev.get("google_event_id")
        cal = ev.get("google_calendar_id") or "primary"
        if not eid:
            continue
        try:
            await gcal.provider.delete_event(
                access_token=access, calendar_id=cal, event_id=eid,
            )
            out["deleted"].append(eid)
        except Exception as e:
            out["failed"].append({"event_id": eid, "error": type(e).__name__})
    return out


async def retry_sync(db, user_id: str, project_id: str) -> Dict[str, Any]:
    doc = await db.travel_projects.find_one(
        {"id": project_id, "user_id": user_id}, {"_id": 0},
    )
    if not doc:
        return {"ok": False, "error": "not_found"}
    # Clear failed statuses so sync recreates
    for ev in doc.get("calendar_events") or []:
        if ev.get("google_sync_status") == "failed":
            ev["google_event_id"] = None
    res = await sync_travel_events(db=db, user_id=user_id, project=doc)
    await db.travel_projects.update_one(
        {"id": project_id, "user_id": user_id},
        {"$set": {"google_sync": res, "updated_at": _now_iso()}},
    )
    return {"ok": True, "google_sync": res}
