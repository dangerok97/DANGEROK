from __future__ import annotations

from typing import List, Tuple

from home.models import ConnectionWarning, HomeItem

from ._util import now_iso, stable_id


async def load_brain_signals(
    db, user_id: str,
) -> Tuple[List[HomeItem], List[ConnectionWarning]]:
    """Lightweight signals from memory / life graph / behavioral patterns — no fluff."""
    items: List[HomeItem] = []

    # Recent unresolved link proposals (auto-link) as verify items
    try:
        cur = db.link_proposals.find(
            {"user_id": user_id, "status": "proposed"},
            {"_id": 0},
        ).sort("created_at", -1).limit(5)
        props = await cur.to_list(5)
        for p in props:
            items.append(HomeItem(
                id=stable_id("link", user_id, p.get("id", "")),
                type="verify",
                subtype="auto_link",
                title="Collegamento da confermare",
                description=p.get("reason") or "ORA ha proposto un collegamento nel grafo",
                source_type="life_graph",
                source_id=p.get("decision_id") or p.get("id") or "",
                confidence=p.get("confidence"),
                status="open",
                created_at=p.get("created_at") or now_iso(),
                updated_at=p.get("created_at") or now_iso(),
                meta={"dedupe_key": f"link:{p.get('id')}", "proposal_id": p.get("id")},
            ))
    except Exception:
        pass

    return items, []
