from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from home.models import ConnectionWarning, HomeItem

from ._util import now_iso, stable_id


async def google_connection_state(db, user_id: str) -> Dict[str, Any]:
    inst = await db.connector_instances.find_one(
        {
            "user_id": user_id,
            "connector_id": "calendar_google",
            "status": {"$in": ["connected", "syncing"]},
        },
        {"_id": 0},
    )
    return {
        "connected": bool(inst),
        "instance": inst,
        "last_sync_at": (inst or {}).get("last_sync_at"),
    }


async def load_google_calendar_events(
    db, user_id: str,
) -> Tuple[List[HomeItem], List[ConnectionWarning]]:
    state = await google_connection_state(db, user_id)
    if not state["connected"]:
        return [], []

    now = datetime.now(timezone.utc)
    window_end = now + timedelta(days=14)
    cur = db.ingestion_events.find(
        {
            "user_id": user_id,
            "connector_id": "calendar_google",
            "ingestion_status": {"$nin": ["superseded", "quarantined"]},
            "source_record_type": {"$in": ["event", "calendar_event", "google_event"]},
        },
        {"_id": 0},
    ).sort("source_updated_at", -1).limit(80)
    docs = await cur.to_list(80)
    items: List[HomeItem] = []
    for d in docs:
        payload = d.get("normalized_payload") or {}
        start = payload.get("starts_at") or payload.get("start") or payload.get("start_datetime")
        end = payload.get("ends_at") or payload.get("end") or payload.get("end_datetime")
        title = payload.get("title") or payload.get("summary") or "Evento calendario"
        if not start:
            continue
        try:
            st = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
            if st.tzinfo is None:
                st = st.replace(tzinfo=timezone.utc)
            if st < now - timedelta(hours=2) or st > window_end:
                continue
        except Exception:
            continue
        loc = payload.get("location")
        eid = d.get("id") or d.get("external_id") or title
        items.append(HomeItem(
            id=stable_id("gcal", user_id, str(eid)),
            type="event",
            subtype="google_calendar",
            title=title,
            description=payload.get("description"),
            source_type="google_calendar",
            source_id=str(eid),
            start_at=str(start),
            end_at=str(end) if end else None,
            location=loc,
            status="open",
            confidence=0.9,
            created_at=d.get("ingested_at") or now_iso(),
            updated_at=d.get("source_updated_at") or now_iso(),
            meta={"dedupe_key": f"gcal:{eid}", "external_id": d.get("external_id")},
        ))
    return items, []
