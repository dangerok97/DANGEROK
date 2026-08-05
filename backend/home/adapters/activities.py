from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Tuple

from home.models import ConnectionWarning, HomeItem

from ._util import now_iso, stable_id


async def load_activities(
    db, user_id: str,
) -> Tuple[List[HomeItem], List[ConnectionWarning]]:
    """Legacy tasks + open non-seed decisions that look like activities."""
    items: List[HomeItem] = []
    now = datetime.now(timezone.utc)

    # Legacy tasks collection (if present)
    try:
        cur = db.tasks.find(
            {"user_id": user_id, "status": {"$in": ["open", "pending", "active"]}},
            {"_id": 0},
        ).sort("score", -1).limit(20)
        tasks = await cur.to_list(20)
    except Exception:
        tasks = []

    for t in tasks:
        due = t.get("deadline") or t.get("due_at")
        overdue = False
        if due:
            try:
                dt = datetime.fromisoformat(str(due).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                overdue = dt < now
            except Exception:
                pass
        items.append(HomeItem(
            id=stable_id("task", user_id, t.get("id", "")),
            type="activity",
            subtype=t.get("category") or "task",
            title=t.get("title") or "Attività",
            description=t.get("description"),
            source_type="task",
            source_id=t.get("id") or "",
            due_at=due,
            status="open",
            created_at=t.get("created_at") or now_iso(),
            updated_at=t.get("updated_at") or now_iso(),
            meta={"dedupe_key": f"task:{t.get('id')}", "overdue_activity": overdue},
        ))
    return items, []
