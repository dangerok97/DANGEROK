from __future__ import annotations

from typing import List, Tuple

from home.models import ConnectionWarning, HomeItem

from ._util import looks_like_concert, looks_like_visit, now_iso, stable_id


async def load_event_candidates(
    db, user_id: str,
) -> Tuple[List[HomeItem], List[ConnectionWarning]]:
    cur = db.documents.find(
        {
            "user_id": user_id,
            "deleted": {"$ne": True},
            "event_candidates": {"$elemMatch": {"status": {"$in": ["proposed", "remind_later"]}}},
        },
        {"_id": 0, "id": 1, "display_title": 1, "filename": 1, "event_candidates": 1, "analysis": 1, "created_at": 1, "updated_at": 1},
    ).limit(40)
    docs = await cur.to_list(40)
    items: List[HomeItem] = []
    for d in docs:
        for ev in d.get("event_candidates") or []:
            if ev.get("status") not in ("proposed", "remind_later"):
                continue
            title = ev.get("title") or d.get("display_title") or "Evento da confermare"
            loc_parts = [ev.get("venue_name"), ev.get("address"), ev.get("city")]
            loc = ", ".join(p for p in loc_parts if p)
            itype = "event"
            subtype = ev.get("category") or "event"
            if looks_like_visit(title, subtype):
                itype = "visit"
                subtype = "medical"
            elif looks_like_concert(title, subtype):
                subtype = "concert"
            if ev.get("ambiguous_date") or ev.get("missing_fields") or (ev.get("confidence") or 1) < 0.6:
                itype = "needs_review" if itype != "visit" else itype
            items.append(HomeItem(
                id=stable_id("evc", user_id, d["id"], ev.get("id", "")),
                type=itype,
                subtype=subtype,
                title=title,
                description=ev.get("description") or ev.get("extraction_notes"),
                source_type="event_candidate",
                source_id=d["id"],
                start_at=ev.get("start_datetime"),
                end_at=ev.get("end_datetime"),
                location=loc or None,
                confidence=ev.get("confidence"),
                status="waiting" if ev.get("status") == "remind_later" else "open",
                created_at=d.get("created_at") or now_iso(),
                updated_at=d.get("updated_at") or now_iso(),
                meta={
                    "dedupe_key": f"evc:{d['id']}:{ev.get('id')}",
                    "event_candidate_id": ev.get("id"),
                    "maps_query": ev.get("maps_query") or loc,
                    "ambiguous_date": bool(ev.get("ambiguous_date")),
                    "missing_fields": ev.get("missing_fields") or [],
                },
            ))
    return items, []
