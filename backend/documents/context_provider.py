"""Documents Context Provider (Iterazione 19 — placeholder).

Attivabile via `DOCUMENT_CONTEXT_ENABLED=true`. Quando disattivato è un
NO-OP stretto: zero segnali, zero letture DB. Predispone i segnali di
tipo "document.*" per il ContextAssembler, ma NON viene ancora
consumato dal Decision Engine né dal Ranking (vietato in Iter19).
"""
from __future__ import annotations

import os
import time
from typing import List

from context_assembler.types import (
    ProviderResult,
    Signal,
)

_SENS_PUBLIC = "public"


def _flag_enabled() -> bool:
    return os.environ.get("DOCUMENT_CONTEXT_ENABLED", "false").lower() in ("1", "true", "yes", "on")


async def documents_provider(db, user_id: str) -> ProviderResult:
    if not _flag_enabled():
        return ProviderResult(name="documents", signals=[], duration_ms=0.0)
    t0 = time.perf_counter()
    signals: List[Signal] = []
    try:
        cursor = db.documents.find(
            {"user_id": user_id, "deleted": {"$ne": True}, "archived": {"$ne": True}},
            {"_id": 0, "id": 1, "filename": 1, "mime_type": 1, "tags": 1,
             "created_at": 1, "size": 1, "pages": 1, "detected_language": 1,
             "text_extracted": 1, "ocr_used": 1, "extracted_text": 1},
        ).sort("created_at", -1).limit(50)
        docs = await cursor.to_list(length=50)
        signals.append(Signal(
            key="document.active_count",
            value=len(docs),
            source_module="documents",
            reliability_tier="official",
            sensitivity=_SENS_PUBLIC,
            verified=True,
        ))
        for d in docs[:20]:
            excerpt = (d.get("extracted_text") or "")[:1200]
            signals.append(Signal(
                key=f"document.item.{d['id']}",
                value={
                    "filename": d.get("filename"),
                    "mime_type": d.get("mime_type"),
                    "tags": d.get("tags") or [],
                    "size": d.get("size"),
                    "pages": d.get("pages"),
                    "language": d.get("detected_language"),
                    "text_extracted": bool(d.get("text_extracted")),
                    "ocr_used": bool(d.get("ocr_used")),
                    "excerpt": excerpt,
                },
                source_module="documents",
                reliability_tier="official",
                sensitivity=_SENS_PUBLIC,
                verified=True,
            ))
    except Exception as e:
        return ProviderResult(name="documents", signals=[], error=f"{type(e).__name__}", duration_ms=(time.perf_counter() - t0) * 1000)
    return ProviderResult(name="documents", signals=signals, duration_ms=(time.perf_counter() - t0) * 1000)
