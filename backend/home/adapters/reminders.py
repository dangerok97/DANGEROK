from __future__ import annotations

from typing import List, Tuple

from home.models import ConnectionWarning, HomeItem

from ._util import now_iso, stable_id


async def load_reminders(
    db, user_id: str,
) -> Tuple[List[HomeItem], List[ConnectionWarning]]:
    # Optional reminders collection — soft-fail if absent/empty
    try:
        cur = db.reminders.find(
            {"user_id": user_id, "status": {"$in": ["open", "active", "pending"]}},
            {"_id": 0},
        ).limit(20)
        docs = await cur.to_list(20)
    except Exception:
        return [], []
    items: List[HomeItem] = []
    for r in docs:
        rmeta = r.get("meta") or {}
        study_plan_id = rmeta.get("study_plan_id") or r.get("study_plan_id")
        travel_project_id = rmeta.get("travel_project_id") or r.get("travel_project_id")
        plan_linked = bool(study_plan_id or travel_project_id)
        meta = {
            "dedupe_key": f"rem:{r.get('id')}",
            "study_plan_id": study_plan_id,
            "travel_project_id": travel_project_id,
            "goal_id": rmeta.get("goal_id") or r.get("goal_id"),
            "kind": rmeta.get("kind"),
        }
        if plan_linked:
            # Plan-linked reminders inherit plan-shell temporal ownership
            meta["plan_shell"] = True
            meta["ownership"] = "legacy"
            meta["canonical_execution"] = False
        items.append(HomeItem(
            id=stable_id("rem", user_id, r.get("id", "")),
            type="activity",
            subtype="reminder",
            title=r.get("title") or "Promemoria",
            description=r.get("body") or r.get("description"),
            source_type="reminder",
            source_id=r.get("id") or "",
            due_at=r.get("due_at") or r.get("remind_at"),
            status="open",
            created_at=r.get("created_at") or now_iso(),
            updated_at=r.get("updated_at") or now_iso(),
            meta=meta,
        ))
    return items, []
