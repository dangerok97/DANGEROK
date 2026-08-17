from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Tuple

from home.models import ConnectionWarning, HomeItem
from home.dedupe import canonical_title_time_key

from ._util import now_iso, stable_id


async def load_internal_calendar(
    db, user_id: str,
) -> Tuple[List[HomeItem], List[ConnectionWarning]]:
    now = datetime.now(timezone.utc)
    day_start = (now - timedelta(hours=2)).isoformat()
    day_end = (now + timedelta(days=14)).isoformat()
    cur = db.life_nodes.find(
        {
            "user_id": user_id,
            "type": "event",
            "status": "active",
            "attributes.starts_at": {"$gte": day_start, "$lte": day_end},
        },
        {"_id": 0},
    ).sort("attributes.starts_at", 1).limit(80)
    docs = await cur.to_list(80)
    items: List[HomeItem] = []
    for d in docs:
        attrs = d.get("attributes") or {}
        # Skip pure Google mirrors already covered if tagged
        if attrs.get("connector_id") == "calendar_google":
            continue
        title = d.get("label") or "Impegno"
        start = attrs.get("starts_at")
        end = attrs.get("ends_at")
        loc = attrs.get("location")
        nid = d.get("id")
        subtype = "internal"
        itype = "event"
        low = title.lower()
        if any(k in low for k in ("viaggio", "treno", "volo", "partenza")):
            itype = "travel"
            subtype = "travel"
        elif any(k in low for k in ("visita", "medico", "dentista")):
            itype = "visit"
            subtype = "medical"
        items.append(HomeItem(
            id=stable_id("life", user_id, str(nid)),
            type=itype,
            subtype=subtype,
            title=title,
            source_type="life_node",
            source_id=str(nid),
            start_at=start,
            end_at=end,
            location=loc,
            status="open",
            confidence=0.85,
            created_at=d.get("created_at") or now_iso(),
            updated_at=d.get("updated_at") or now_iso(),
            meta={
                "dedupe_key": f"life:{nid}",
                "title_dedupe": canonical_title_time_key(
                    title,
                    start,
                    goal_id=attrs.get("goal_id"),
                ),
                "study_plan_id": attrs.get("study_plan_id"),
                "study_session_id": attrs.get("study_session_id"),
                "travel_project_id": attrs.get("travel_project_id"),
                "action_session_id": attrs.get("action_session_id"),
                "goal_id": attrs.get("goal_id"),
                "kind": attrs.get("kind"),
                "calendar_node_id": str(nid),
            },
        ))
    return items, []
