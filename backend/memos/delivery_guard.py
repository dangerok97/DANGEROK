"""Owner-scoped last-mile verification for recurring Memo opportunities.

An Opportunity is a snapshot. A birthday Memory can be forgotten or corrected
after that snapshot was created but before Expo accepts a notification.
Delivery must re-read the source before planning and again before sending.
No mutation or notification is made by this gate.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "Europe/Rome")
    except Exception:
        return ZoneInfo("Europe/Rome")


async def memo_opportunity_current(db: Any, subject: Any) -> bool:
    if str(getattr(subject, "source_context", "") or "") != "recurring_memo":
        return True

    owner = str(getattr(subject, "owner_id", "") or "")
    parts = str(getattr(subject, "identity_key", "") or "").split(":")
    if not owner or len(parts) != 3 or parts[0] != "recurring_memo":
        return False
    memo_id, year_token = parts[1], parts[2]
    if not memo_id.startswith("rmm_") or not year_token.isdecimal():
        return False

    try:
        memo = await db.recurring_memos.find_one({
            "owner_id": owner, "id": memo_id, "status": "active",
        }, {"_id": 0})
        if not memo:
            return False
        memory_ref = str(memo.get("memory_ref") or "")
        refs = {
            str(item.ref)
            for item in (getattr(subject, "evidence", None) or [])
            if getattr(item, "kind", "") == "memory"
        }
        if not memory_ref or memory_ref not in refs:
            return False
        memory = await db.memories.find_one({
            "user_id": owner, "id": memory_ref, "status": "active",
        }, {"_id": 0, "value": 1})
        if not memory:
            return False
        value = memory.get("value") if isinstance(memory.get("value"), dict) else {}
        month, day = int(memo.get("month")), int(memo.get("day"))
        if value.get("month") is not None and int(value["month"]) != month:
            return False
        if value.get("day") is not None and int(value["day"]) != day:
            return False
        local = datetime.now(timezone.utc).astimezone(
            _zone(str(memo.get("timezone") or "Europe/Rome"))
        )
        if (local.year, local.month, local.day) != (
            int(year_token), month, day,
        ):
            return False
        valid_until = getattr(subject, "valid_until", None)
        if valid_until:
            parsed = datetime.fromisoformat(str(valid_until).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return False
            if parsed <= datetime.now(timezone.utc):
                return False
        return True
    except (TypeError, ValueError, AttributeError):
        return False
    except Exception:
        # Fail closed on an unavailable or inconsistent data source.
        return False
