from __future__ import annotations

from typing import List, Tuple

from home.models import ConnectionWarning, HomeItem

from ._util import looks_like_concert, looks_like_visit, now_iso, parse_amount, stable_id
from .document_uncertainty import blocking_uncertainty


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
        # A document ORA could not finish reading is the only pipeline state
        # that is about the person at all.
        #
        # `awaiting_confirmation` is not: it means ORA proposed something to
        # itself — an event candidate exists — and a proposal of ORA's own is
        # not work somebody has to do. That state alone was turning a policy
        # read at 0.95 confidence, with no warnings and `requires_review`
        # false, into a card titled with the document's own name and a
        # "Verifica" button. Reading a document well is not a reason to ask
        # anybody anything.
        # One decider, and it is the only thing that can produce a question:
        # did ORA actually fail to resolve something? Filtering on the pipeline
        # state first was a second gate that could only ever disagree with this
        # one — a document can carry a real ambiguity and a proposed event at
        # the same time, and the ambiguity is no less real for it.
        uncertainty = blocking_uncertainty(d)
        if uncertainty:
            items.append(HomeItem(
                id=stable_id("doc_review", user_id, d["id"]),
                type="verify",
                subtype=status,
                # The question, not the document's name. "Polizza Assicurativa
                # Auto - Generali Italia → Verifica" tells somebody nothing
                # about what ORA needs from them.
                title=uncertainty["question"],
                description=(d.get("analysis") or {}).get("short_description"),
                source_type="document",
                source_id=d["id"],
                confidence=(d.get("analysis") or {}).get("confidence"),
                status="open",
                created_at=d.get("created_at") or now_iso(),
                updated_at=d.get("updated_at") or now_iso(),
                meta={
                    "dedupe_key": f"doc_review:{d['id']}",
                    "pipeline_status": status,
                    "work_reason": "confirmation_required",
                    "uncertain_field": uncertainty["field"],
                },
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
                    # A deadline read out of a document is a fact from the
                    # moment it is extracted, and work only once it is close.
                    "work_reason": "deadline",
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
                    meta={
                        "dedupe_key": f"doc_eventish:{d['id']}",
                        "work_reason": "deadline",
                    },
                ))
    return items, []
