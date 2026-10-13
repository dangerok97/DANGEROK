"""Opt-in real Core/calendar acceptance, test-only synthetic accounts.

No production user, Google connector, socket server, push or third-party write.
The original cognitive loop chooses tools. Calendar handlers and governance are
unchanged. Independent DB and agenda API readbacks judge the resulting effects.
This is not a browser, process-restart or physical notification acceptance.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
import logging
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

VERSION = "calendar-core-acceptance-v163"
OWNER = "ora-v163-synthetic-calendar-only"
OTHER = "ora-v163-isolation-canary"
TITLE = "ORA COLLAUDO CAL163"
ZONE = "Europe/Rome"
CAPS = frozenset({"get_calendar_events", "create_calendar_event",
                  "update_calendar_event", "cancel_calendar_event"})


def require(condition, code):
    if not condition:
        raise AssertionError(code)


def event_view(rows):
    return [{"id": r["id"], "title": r.get("label"), "status": r.get("status"),
             "starts_at": (r.get("attributes") or {}).get("starts_at"),
             "ends_at": (r.get("attributes") or {}).get("ends_at"),
             "timezone": (r.get("attributes") or {}).get("timezone")}
            for r in rows]


def check_effect(stage, rows, first_id, start, moved):
    active = [r for r in rows if r.get("status") == "active"]
    errors = []
    if stage == "cancel":
        if active:
            errors.append("EVENT_STILL_ACTIVE")
        return errors
    if len(active) != 1:
        return ["EXPECTED_EXACTLY_ONE_ACTIVE_EVENT"]
    row = active[0]
    at = (row.get("attributes") or {}).get("starts_at")
    target = moved if stage == "move" else start
    if row.get("label") != TITLE:
        errors.append("WRONG_TITLE")
    if first_id and row.get("id") != first_id:
        errors.append("EVENT_ID_CHANGED")
    try:
        if datetime.fromisoformat(at) != target:
            errors.append("WRONG_EVENT_INSTANT")
        end = datetime.fromisoformat((row.get("attributes") or {})["ends_at"])
        if end - datetime.fromisoformat(at) != timedelta(minutes=45):
            errors.append("WRONG_EVENT_DURATION")
    except (TypeError, ValueError, KeyError):
        errors.append("INVALID_SAVED_TIME")
    if (row.get("attributes") or {}).get("timezone") != ZONE:
        errors.append("WRONG_TIMEZONE")
    return errors


def selftest():
    start = datetime(2030, 1, 3, 10, tzinfo=ZoneInfo(ZONE))
    moved = start.replace(hour=11)
    row = {"id": "fixture", "label": TITLE, "status": "active",
           "attributes": {"starts_at": start.isoformat(),
                          "ends_at": (start + timedelta(minutes=45)).isoformat(),
                          "timezone": ZONE}}
    require(check_effect("create", [row], None, start, moved) == [], "VALID_REJECTED")
    require(bool(check_effect("create", [], None, start, moved)), "EMPTY_ACCEPTED")
    require(bool(check_effect("create", [row, deepcopy(row)], None, start, moved)), "DUPLICATE_ACCEPTED")
    require(bool(check_effect("move", [row], "fixture", start, moved)), "UNMOVED_ACCEPTED")
    require(bool(check_effect("cancel", [row], "fixture", start, moved)), "UNCANCELLED_ACCEPTED")
    foreign = deepcopy(row)
    foreign["id"] = "different"
    require(bool(check_effect("replay", [foreign], "fixture", start, moved)), "IDENTITY_CHANGE_ACCEPTED")
    print("ORA_CAL163_SELFTEST " + json.dumps({"passed": True, "checks": 6}), flush=True)


async def run(output):
    import httpx
    from fastapi import FastAPI
    from mongomock_motor import AsyncMongoMockClient
    from agenda import router as agenda_routes
    from routers import calendar_events as calendar_routes
    from conversation_engine.ai_core import loop as core
    from conversation_engine.ai_core.models import Observation
    from conversation_engine.ai_core.tools.registry import ToolRegistry
    from conversation_engine.ai_core.tools import calendar_caps
    from conversation_engine.models import ConversationSession
    from llm.manager import ProviderManager
    from scripts.phase1_read_provider_eval import _ReadBoundary, _llm_endpoint, _safe_text

    db = AsyncMongoMockClient().ora_cal163_synthetic_only
    day = (datetime.now(ZoneInfo(ZONE)) + timedelta(days=2)).date()
    start = datetime(day.year, day.month, day.day, 10, tzinfo=ZoneInfo(ZONE))
    moved = start.replace(hour=11)
    await db.users.insert_one({"id": OWNER, "user_id": OWNER, "name": "Collaudo sintetico",
        "settings": {"timezone": ZONE, "notifications_enabled": False}})
    canary = {"id": "cal163-foreign", "user_id": OTHER, "type": "event",
        "label": "Evento altro account", "status": "active", "attributes": {
            "kind": "home_manual", "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(minutes=45)).isoformat(), "timezone": ZONE}}
    await db.life_nodes.insert_one(deepcopy(canary))
    sess = ConversationSession(user_id=OWNER, meta={"ui_mode": "ai_core", "ai_core": {}})
    app = FastAPI()
    app.include_router(agenda_routes.router, prefix="/api")
    app.include_router(calendar_routes.router, prefix="/api")
    identity = {"user_id": OWNER}
    app.dependency_overrides[agenda_routes.get_current_user] = lambda: identity
    boundary = _ReadBoundary(model_live=True, provider_reply=None)
    tool_calls, model_calls, rows_report = [], [], []
    model_http = 0
    stage = ""
    first_id = None
    original_execute = ToolRegistry.execute
    original_chat = ProviderManager.chat
    original_send = httpx.AsyncClient.send
    inputs = [
        ("create", f"Crea nel calendario interno ORA, senza Google, l'appuntamento '{TITLE}' il {day.isoformat()} dalle 10:00 alle 10:45, fuso Europe/Rome. Conferma solo dopo averlo salvato."),
        ("replay", f"Crea nel calendario interno ORA, senza Google, l'appuntamento '{TITLE}' il {day.isoformat()} dalle 10:00 alle 10:45, fuso Europe/Rome. Conferma solo dopo averlo salvato."),
        ("read", f"Leggi il calendario ORA del {day.isoformat()} e dimmi l'orario dell'appuntamento '{TITLE}'. Non modificare nulla."),
        ("move", f"Sposta l'appuntamento '{TITLE}' del {day.isoformat()} alle 11:00, mantenendo la durata di 45 minuti e il fuso Europe/Rome. Modifica lo stesso evento nel calendario ORA, non crearne un altro."),
        ("cancel", f"Cancella dal calendario ORA l'appuntamento '{TITLE}' del {day.isoformat()}. Non toccare altri eventi."),
    ]

    async def gated_execute(registry, capability, arguments, *, runtime=None):
        require(len(tool_calls) < 40, "TOOL_BUDGET_EXHAUSTED")
        if capability not in CAPS:
            tool_calls.append({"stage": stage, "capability": str(capability)[:80], "status": "blocked"})
            return Observation(kind="tool", name=capability, status="error", payload={
                "status": "error", "failure_kind": "SYNTHETIC_BOUNDARY",
                "detail": "Only native calendar actions exist in this isolated acceptance."})
        require(runtime is not None and runtime.get("db") is db and runtime.get("user_id") == OWNER,
                "RUNTIME_OWNER_OR_DB_MISMATCH")
        before = len(tool_calls)
        tool_calls.append({"stage": stage, "capability": capability, "status": "started"})
        result = await original_execute(registry, capability, arguments, runtime=runtime)
        payload = result.payload or {}
        tool_calls[before].update({"status": result.status,
            "failure_kind": payload.get("failure_kind"), "operation": payload.get("operation"),
            "verified": payload.get("verified"), "provider": payload.get("provider"),
            "calendar_ref": payload.get("calendar_ref"),
            "events_count": len(payload.get("events") or []),
            "arguments": {key: arguments[key] for key in (
                "title", "calendar_ref", "start_datetime", "end_datetime", "timezone",
                "calendar_target", "operation_intent", "time_min", "time_max", "when") if key in arguments}})
        return result

    async def counted_chat(manager, **kwargs):
        require(len(model_calls) < 50, "MODEL_BUDGET_EXHAUSTED")
        entry = {"stage": stage, "status": "started"}
        model_calls.append(entry)
        token = boundary.scope.set("model")
        try:
            result = await asyncio.wait_for(original_chat(manager, **kwargs), timeout=55)
            entry.update({"status": "succeeded", "provider": result.provider})
            return result
        except Exception as exc:
            entry.update({"status": "failed", "error_type": type(exc).__name__})
            raise
        finally:
            boundary.scope.reset(token)

    async def no_google(*args, **kwargs):
        boundary.blocked.append("GOOGLE_CONNECTOR_ATTEMPT")
        raise RuntimeError("GOOGLE_CONNECTOR_ATTEMPT")

    with ExitStack() as stack:
        boundary.install(stack)
        boundary_send = httpx.AsyncClient.send
        async def observed_send(client, request, **kwargs):
            nonlocal model_http
            if isinstance(client._transport, httpx.ASGITransport):
                require(request.url.host == "ora.synthetic", "ASGI_TARGET_MISMATCH")
                return await original_send(client, request, **kwargs)
            if boundary.scope.get() == "model" and _llm_endpoint(request):
                model_http += 1
                require(model_http <= 90, "HTTP_BUDGET_EXHAUSTED")
            return await boundary_send(client, request, **kwargs)
        stack.enter_context(patch.object(httpx.AsyncClient, "send", observed_send))
        stack.enter_context(patch.object(ProviderManager, "chat", counted_chat))
        stack.enter_context(patch.object(ToolRegistry, "execute", gated_execute))
        stack.enter_context(patch.object(calendar_caps, "_sync_service", no_google))
        stack.enter_context(patch.object(agenda_routes, "db", db))
        stack.enter_context(patch.object(calendar_routes, "db", db))
        stack.enter_context(patch.object(core, "report_activity", AsyncMock()))
        for stage, message in inputs:
            before_calls = len(tool_calls)
            record = {"case": stage, "status": "running", "input": message}
            rows_report.append(record)
            try:
                result = await asyncio.wait_for(core.run_cognitive_loop(
                    sess=sess, user_message=message, db=db, max_steps=8), timeout=180)
                saved = await db.life_nodes.find({"user_id": OWNER, "type": "event"}, {"_id": 0}).to_list(30)
                errors = check_effect(stage, saved, first_id, start, moved)
                if stage == "create" and not errors:
                    first_id = saved[0]["id"]
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://ora.synthetic") as client:
                    agenda = await client.get("/api/agenda/month", params={"month": day.strftime("%Y-%m")})
                    require(agenda.status_code == 200, "AGENDA_READBACK_FAILED")
                    month = agenda.json()
                    events = [event for item in month.get("days", []) for event in item.get("events", [])]
                    expected = 0 if stage == "cancel" else 1
                    if len(events) != expected or month.get("source_counts", {}).get("ora") != expected:
                        errors.append("AGENDA_EFFECT_MISMATCH")
                    identity["user_id"] = OTHER
                    other = await client.get("/api/agenda/month", params={"month": day.strftime("%Y-%m")})
                    identity["user_id"] = OWNER
                    if TITLE in other.text:
                        errors.append("CROSS_OWNER_AGENDA_LEAK")
                current_canary = await db.life_nodes.find_one({"user_id": OTHER}, {"_id": 0})
                if current_canary != canary:
                    errors.append("OTHER_ACCOUNT_CHANGED")
                if not result.ok:
                    errors.append("CORE_NOT_OK")
                if stage == "read" and not any(c["capability"] == "get_calendar_events" and c["status"] == "ok"
                                                  for c in tool_calls[before_calls:]):
                    errors.append("CORE_DID_NOT_READ_CALENDAR")
                record.update({"status": "passed" if not errors else "failed", "errors": errors,
                    "reply": _safe_text(result.ora_text, 2500), "reply_mode": result.mode,
                    "events": event_view(saved), "agenda_event_count": len(events),
                    "core_ai_calls": result.ai_calls, "core_tool_calls": result.tool_calls})
            except Exception as exc:
                code = str(exc) if isinstance(exc, AssertionError) else type(exc).__name__
                record.update({"status": "failed", "errors": [code[:100]]})
            print("ORA_CAL163_CASE " + json.dumps(record, ensure_ascii=False), flush=True)
            if record["status"] != "passed":
                break
    not_run = [name for name, _ in inputs if name not in {r["case"] for r in rows_report}]
    summary = {"version": VERSION, "revision": os.environ.get("RAILWAY_GIT_COMMIT_SHA"),
        "scope": "real_core_native_calendar_synthetic_in_memory",
        "passed": len(rows_report) == len(inputs) and all(r["status"] == "passed" for r in rows_report)
                  and not boundary.blocked and bool(model_calls),
        "cases": rows_report, "not_run": not_run, "model_calls": len(model_calls),
        "model_http_requests": model_http, "model_outcomes": model_calls,
        "tool_observations": tool_calls, "network_blocked": boundary.blocked,
        "real_user_accessed": False, "google_connected": False, "browser_tested": False,
        "notification_delivery_tested": False, "process_restart_tested": False,
        "human_semantic_review_required": True}
    Path(output).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("ORA_CAL163_SUMMARY " + json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    p = argparse.ArgumentParser()
    p.add_argument("--live", action="store_true")
    p.add_argument("--output", default="/tmp/ora-cal163-result.json")
    args = p.parse_args()
    selftest()
    if args.live:
        raise SystemExit(asyncio.run(run(args.output)))
