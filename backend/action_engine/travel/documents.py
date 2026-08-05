"""Search ORA documents for hotel/ticket PDFs — soft, no invent."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ora.action_engine.travel.docs")

_TRAVEL_HINTS = re.compile(
    r"hotel|bigliett|booking|prenotaz|volo|treno|airbnb|viaggio|vacanza|"
    r"ferry|traghetto|noleggio|ticket|reservation",
    re.I,
)


async def search_travel_documents(
    db,
    *,
    user_id: str,
    destination: Optional[str] = None,
    limit: int = 12,
) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    try:
        curs = db.documents.find(
            {"user_id": user_id, "deleted": {"$ne": True}},
            {
                "_id": 0,
                "id": 1,
                "display_title": 1,
                "filename": 1,
                "analysis": 1,
                "macro_category": 1,
                "updated_at": 1,
            },
        ).sort("updated_at", -1).limit(80)
        docs = await curs.to_list(80)
    except Exception as e:
        logger.info("travel doc search failed: %s", type(e).__name__)
        return {"ok": True, "items": [], "message": "Ricerca documenti non disponibile."}

    dest_l = (destination or "").lower()
    for d in docs:
        title = d.get("display_title") or d.get("filename") or ""
        analysis = d.get("analysis") or {}
        blob = " ".join(
            str(x) for x in (
                title,
                analysis.get("suggested_title"),
                analysis.get("short_description"),
                analysis.get("macro_category"),
                d.get("macro_category"),
            ) if x
        )
        score = 0
        if _TRAVEL_HINTS.search(blob):
            score += 2
        if dest_l and dest_l in blob.lower():
            score += 3
        if score <= 0:
            continue
        items.append({
            "id": d["id"],
            "title": title,
            "score": score,
            "macro_category": analysis.get("macro_category") or d.get("macro_category"),
        })
    items.sort(key=lambda x: -x["score"])
    items = items[:limit]
    return {
        "ok": True,
        "items": items,
        "message": (
            f"Trovati {len(items)} documenti potenzialmente legati al viaggio."
            if items else
            "Nessun PDF hotel/biglietto ovvio nei tuoi documenti ORA."
        ),
        "email_auto_find": {
            "status": "not_implemented",
            "note": "Hook futuro — ricerca automatica email non attiva.",
        },
    }
