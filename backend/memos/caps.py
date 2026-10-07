"""Cognitive capability for explicit recurring personal memos."""
from __future__ import annotations

from typing import Any, Dict

from conversation_engine.ai_core.models import Observation
from memos.service import RecurringMemoService


async def save_recurring_memo(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    db = runtime.get("db")
    owner = str(runtime.get("user_id") or "")
    if db is None or not owner:
        return Observation(
            kind="tool", name="save_recurring_memo", status="error",
            payload={"ok": False, "error": "runtime_unavailable"},
        )
    service = RecurringMemoService(db)
    try:
        result = await service.save_annual(
            owner,
            memory_ref=str(arguments.get("memory_ref") or ""),
            category=str(arguments.get("category") or "annual_memo"),
            label=str(arguments.get("label") or ""),
            person=str(arguments.get("person") or ""),
            month=int(arguments.get("month")),
            day=int(arguments.get("day")),
            timezone_name=str(arguments.get("timezone") or "Europe/Rome"),
            remind_hour_local=int(arguments.get("remind_hour_local") or 9),
        )
    except (TypeError, ValueError):
        result = {"ok": False, "error": "invalid_annual_date"}
    return Observation(
        kind="tool",
        name="save_recurring_memo",
        status="ok" if result.get("ok") else "error",
        payload=result,
        provenance=[str(arguments.get("memory_ref") or "")] if result.get("ok") else [],
    )
