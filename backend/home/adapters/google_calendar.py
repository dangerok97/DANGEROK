from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from home.models import ConnectionWarning, HomeItem
from home.calendar_read import (
    calendar_source_key, calendar_times_in_window, connected_calendar_instances,
    selected_calendar_source,
)
from ingestion.reading import plain, where

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
    db, user_id: str, *, instances: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[HomeItem], List[ConnectionWarning]]:
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(days=14)
    window_start = now - timedelta(hours=2)
    docs = await google_calendar_records(db, user_id, window_start, window_end, instances=instances)

    items: List[HomeItem] = []
    for d in docs:
        # La busta viene tolta qui, una volta.
        #
        # Senza questa riga `starts_at` e' un dizionario: verita' per il
        # controllo `if not start` qui sotto, impossibile da leggere per
        # `fromisoformat`, e quindi ogni evento vero finiva nell'`except` e
        # spariva in silenzio. La Home diceva «nessun impegno» sopra un
        # calendario pieno, e nessun errore lo raccontava da nessuna parte.
        payload = plain(d.get("normalized_payload"))
        if str(payload.get("status") or "").lower() == "cancelled" or d.get("source_status") == "detached":
            # Cancellato su Google. La riga resta — e' la traccia di una cosa
            # che c'e' stata — ma un impegno annullato non e' un impegno, e
            # mostrarlo lo rende un appuntamento a cui qualcuno si presenta.
            continue
        start = payload.get("starts_at") or payload.get("start") or payload.get("start_datetime")
        end = payload.get("ends_at") or payload.get("end") or payload.get("end_datetime")
        title = payload.get("title") or payload.get("summary") or "Evento calendario"
        if not calendar_times_in_window(
            {**payload, "starts_at": start, "ends_at": end}, window_start, window_end,
        ):
            continue
        loc = payload.get("location")
        eid = d.get("id") or d.get("external_id") or title
        ext = payload.get("extendedProperties") or payload.get("extended_properties") or {}
        priv = (ext.get("private") or {}) if isinstance(ext, dict) else {}
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
            meta={
                "dedupe_key": f"gcal:{eid}",
                "ingestion_event_id": d.get("id"),
                "external_id": d.get("external_id"),
                "calendar_id": payload.get("calendar_id") or "primary",
                "ora_event_id": priv.get("ora_event_id") or payload.get("ora_event_id"),
                "ora_goal_id": priv.get("ora_goal_id") or payload.get("ora_goal_id"),
                "goal_id": priv.get("ora_goal_id") or priv.get("goal_id") or payload.get("goal_id"),
                "study_plan_id": priv.get("ora_study_plan_id") or priv.get("study_plan_id") or payload.get("study_plan_id"),
                "travel_project_id": priv.get("ora_travel_project_id") or priv.get("travel_project_id") or payload.get("travel_project_id"),
                "ora_document_id": priv.get("ora_document_id"),
            },
        ))
    return items, []


async def google_calendar_records(
    db, user_id: str, first: datetime, end: datetime, *,
    instances: Optional[List[Dict[str, Any]]] = None,
    external_ids: Optional[List[str]] = None,
    limit: int = 2000,
) -> List[Dict[str, Any]]:
    """Read the same normalized records for Home and the native month.

    Return cancellations and moved records too: callers must not resurrect
    an older graph mirror when the latest provider evidence moved or removed
    it. Existing node handles can extend the query beyond the visible month.
    No provider request and no persistence happens during this projection.
    """
    if instances is None:
        instances = await connected_calendar_instances(db, user_id)
    if not any(row.get("connector_id") == "calendar_google" for row in instances):
        return []
    window = {where("starts_at"): {
        "$gte": (first - timedelta(days=1)).date().isoformat(),
        "$lt": (end + timedelta(days=1)).date().isoformat(),
    }}
    query = {
        "user_id": user_id,
        "connector_id": "calendar_google",
        "ingestion_status": {"$nin": ["superseded", "quarantined", "skipped"]},
        "source_record_type": {"$in": ["event", "calendar_event", "google_event"]},
        "$or": [window, {"external_id": {"$in": external_ids}}] if external_ids else [window],
    }
    docs = await db.ingestion_events.find(query, {"_id": 0}).sort(
        where("starts_at"), 1,
    ).to_list(length=limit)
    newest: Dict[tuple, Dict[str, Any]] = {}
    for row in docs:
        attrs = google_calendar_attributes(row)
        if not selected_calendar_source(attrs, instances):
            continue
        key = calendar_source_key(attrs)
        before = newest.get(key)
        if before is None or str(row.get("ingested_at") or "") > str(before.get("ingested_at") or ""):
            newest[key] = row
    return list(newest.values())


def google_calendar_attributes(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **plain(row.get("normalized_payload")),
        "connector_id": "calendar_google",
        "connector_instance_id": row.get("connector_instance_id"),
        "external_event_id": row.get("external_id") or row.get("id"),
    }
