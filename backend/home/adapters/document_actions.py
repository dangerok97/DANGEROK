from __future__ import annotations

from typing import List, Tuple

from home.models import ConnectionWarning, HomeItem

from ._util import now_iso, stable_id

# Action types the analyzer generates for itself rather than for anybody.
_ORA_BOOKKEEPING = frozenset({"create_reminder", "needs_review"})


async def load_document_actions(
    db, user_id: str,
) -> Tuple[List[HomeItem], List[ConnectionWarning]]:
    cur = db.documents.find(
        {
            "user_id": user_id,
            "deleted": {"$ne": True},
            "generic_actions": {"$elemMatch": {"completed": {"$ne": True}}},
        },
        {"_id": 0, "id": 1, "display_title": 1, "generic_actions": 1, "analysis": 1, "created_at": 1, "updated_at": 1},
    ).limit(40)
    docs = await cur.to_list(40)
    items: List[HomeItem] = []
    for d in docs:
        for act in d.get("generic_actions") or []:
            if act.get("completed"):
                continue
            # ORA's own bookkeeping is not somebody's to do.
            #
            # The analyzer writes two kinds of thing here. One comes out of the
            # document — "azione richiesta", something the sender is asking
            # for. The other is ORA noting to itself that a deadline it just
            # extracted could have a reminder, or that a category of document
            # is often worth a second look: "Promemoria scadenza", "Revisione
            # richiesta", produced for a policy nobody had asked anything
            # about. Those stay in the record and out of the day.
            if (act.get("action_type") or "") in _ORA_BOOKKEEPING:
                continue
            label = act.get("label") or act.get("title") or "Azione documento"
            kind = (act.get("kind") or act.get("type") or "").lower()
            itype = "activity"
            if "pag" in kind or "pay" in kind or "pagare" in label.lower():
                itype = "payment"
            elif "rispond" in label.lower() or kind == "reply":
                itype = "reply"
            elif "verific" in label.lower() or kind in ("review", "verify"):
                itype = "verify"
            items.append(HomeItem(
                id=stable_id("gact", user_id, d["id"], act.get("id", label)),
                type=itype,
                subtype=kind or "document_action",
                title=label,
                description=act.get("description"),
                source_type="document_action",
                source_id=d["id"],
                due_at=act.get("due_at") or act.get("due_date"),
                status="waiting" if act.get("deferred") else "open",
                confidence=(d.get("analysis") or {}).get("confidence"),
                created_at=d.get("created_at") or now_iso(),
                updated_at=d.get("updated_at") or now_iso(),
                meta={
                    "dedupe_key": f"gact:{d['id']}:{act.get('id') or label}",
                    "action_id": act.get("id"),
                    "deferred": bool(act.get("deferred")),
                    # Something the document itself asks of the person.
                    "work_reason": "decision",
                },
            ))
    return items, []
