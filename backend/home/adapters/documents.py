from __future__ import annotations

from typing import List, Tuple

from home.models import ConnectionWarning, HomeItem

from ._util import looks_like_concert, looks_like_visit, now_iso, parse_amount, stable_id


async def load_documents(
    db, user_id: str,
) -> Tuple[List[HomeItem], List[ConnectionWarning]]:
    cur = db.documents.find(
        {"user_id": user_id, "deleted": {"$ne": True}, "archived": {"$ne": True}},
        {"_id": 0, "extracted_text": 0},
    ).sort("updated_at", -1).limit(60)
    docs = await cur.to_list(60)
    items: List[HomeItem] = []
    for d in docs:
        status = d.get("pipeline_status") or ""
        if status in ("needs_review", "awaiting_confirmation", "action_required", "failed"):
            title = (
                d.get("display_title")
                or d.get("user_title")
                or (d.get("analysis") or {}).get("suggested_title")
                or d.get("filename")
                or "Documento da verificare"
            )
            conf = (d.get("analysis") or {}).get("confidence")
            items.append(HomeItem(
                id=stable_id("doc_review", user_id, d["id"]),
                type="needs_review",
                subtype=status,
                title=title,
                description=(d.get("analysis") or {}).get("short_description"),
                source_type="document",
                source_id=d["id"],
                confidence=conf,
                status="open",
                created_at=d.get("created_at") or now_iso(),
                updated_at=d.get("updated_at") or now_iso(),
                meta={"dedupe_key": f"doc_review:{d['id']}", "pipeline_status": status},
            ))

        admin = d.get("admin_analysis") or {}
        analysis = d.get("analysis") or {}
        macro = analysis.get("macro_category") or ""
        if admin and not admin.get("completed"):
            due = admin.get("due_date")
            amount = parse_amount(admin)
            title = (
                admin.get("subject")
                or analysis.get("suggested_title")
                or d.get("display_title")
                or "Scadenza amministrativa"
            )
            itype = "bill" if macro in ("financial", "administrative", "receipt") or amount else "activity"
            if looks_like_visit(title, analysis.get("subcategory")):
                itype = "visit"
            items.append(HomeItem(
                id=stable_id("admin", user_id, d["id"]),
                type=itype,
                subtype=macro or "admin",
                title=title,
                description=admin.get("simple_explanation") or analysis.get("short_description"),
                source_type="document",
                source_id=d["id"],
                due_at=due,
                amount=amount,
                confidence=admin.get("confidence") or analysis.get("confidence"),
                status="open" if not admin.get("deferred") else "waiting",
                created_at=d.get("created_at") or now_iso(),
                updated_at=d.get("updated_at") or now_iso(),
                meta={
                    "dedupe_key": f"admin:{d['id']}",
                    "deferred": bool(admin.get("deferred")),
                    "document_number": admin.get("document_number"),
                },
            ))

        # Ambiguous / concert-style docs without event candidates still surface lightly via analysis dates
        if looks_like_concert(analysis.get("suggested_title") or d.get("filename") or "", analysis.get("subcategory")):
            if not d.get("event_candidates"):
                items.append(HomeItem(
                    id=stable_id("doc_concert", user_id, d["id"]),
                    type="event",
                    subtype="concert",
                    title=analysis.get("suggested_title") or d.get("display_title") or "Evento da documento",
                    description=analysis.get("short_description"),
                    source_type="document",
                    source_id=d["id"],
                    confidence=analysis.get("confidence"),
                    status="open",
                    created_at=d.get("created_at") or now_iso(),
                    updated_at=d.get("updated_at") or now_iso(),
                    meta={"dedupe_key": f"doc_eventish:{d['id']}"},
                ))
    return items, []
