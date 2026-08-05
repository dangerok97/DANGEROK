from __future__ import annotations

from typing import List, Tuple

from home.models import ConnectionWarning, HomeItem

from ._util import now_iso, stable_id


_TYPE_MAP = {
    "bill": "bill",
    "travel": "travel",
    "travel_prep": "travel",
    "exam": "study",
    "study": "study",
    "fitness": "activity",
    "leisure": "activity",
    "hobby": "activity",
    "work_deadline": "activity",
    "event": "event",
    "medical": "visit",
}


async def load_decisions(
    db, user_id: str,
) -> Tuple[List[HomeItem], List[ConnectionWarning]]:
    """Include real user decisions; skip demo seed origins for non-demo users."""
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1})
    is_demo = (user or {}).get("email") == "demo@ora.app"

    cur = db.decisions.find(
        {"user_id": user_id, "status": {"$in": ["open", "in_progress", "partially_completed", "postponed"]}},
        {"_id": 0},
    ).limit(40)
    docs = await cur.to_list(40)
    items: List[HomeItem] = []
    for d in docs:
        origin = d.get("origin") or ""
        if not is_demo and str(origin).startswith("seed"):
            continue
        cat = d.get("category") or "generic"
        itype = _TYPE_MAP.get(cat, "generic")
        st = d.get("status") or "open"
        items.append(HomeItem(
            id=stable_id("dec", user_id, d.get("id", "")),
            type=itype,  # type: ignore[arg-type]
            subtype=cat,
            title=d.get("title") or "Decisione",
            description=d.get("description"),
            source_type="decision",
            source_id=d.get("id") or "",
            due_at=d.get("deadline"),
            start_at=d.get("starts_at"),
            duration_minutes=d.get("time_required_min"),
            location=d.get("place"),
            status="waiting" if st == "postponed" else "open",
            confidence=0.75,
            created_at=d.get("created_at") or now_iso(),
            updated_at=d.get("updated_at") or now_iso(),
            meta={
                "dedupe_key": f"dec:{d.get('id')}",
                "decision_status": st,
                "origin": origin,
            },
        ))
    return items, []
