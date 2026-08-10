"""Optional Gemini wording polish — shared Provider Manager; never invents memories."""
from __future__ import annotations

import json
import logging
import os
from typing import List, Optional, Sequence, Tuple

from life_memory.models import EvidenceRef, GeminiMemoryPayload, MemoryItem

logger = logging.getLogger("ora.life_memory.gemini")

SYSTEM = """Sei il cognition layer di ORA per la Memoria personale.

Compito: migliorare SOLO la formulazione italiana di ricordi GIÀ forniti.
NON inventare ricordi. NON aggiungere fatti. NON cambiare il significato.

Regole:
- Output JSON: { "wordings": [ { "memory_id": "...", "statement": "..." } ] }
- Usa solo memory_id presenti nell'input.
- Statement breve (≤120), calmo, in italiano, seconda persona dove naturale.
- Non esporre chiavi schema, confidence, enum.
- Se un ricordo è ambiguous, non renderlo come fatto certo.
- Niente chain-of-thought.
"""


def life_memory_gemini_enabled() -> bool:
    raw = (os.environ.get("MEMORY_GEMINI") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


async def polish_with_gemini(
    *,
    memories: Sequence[MemoryItem],
    evidence: Sequence[EvidenceRef],
) -> Optional[List[Tuple[str, str]]]:
    if not life_memory_gemini_enabled():
        return None
    if not memories:
        return None
    try:
        from llm.structured import chat_json
    except Exception as e:
        logger.info("life_memory gemini unavailable: %s", type(e).__name__)
        return None

    evid_ids = {e.id for e in evidence}
    payload = {
        "memories": [
            {
                "memory_id": m.id,
                "statement": m.statement,
                "status": m.status,
                "domain": m.domain,
                "evidence_refs": [r for r in m.evidence_refs if r in evid_ids][:4],
            }
            for m in memories[:40]
        ]
    }
    try:
        result, _meta = await chat_json(
            system=SYSTEM,
            user=json.dumps(payload, ensure_ascii=False),
            model_cls=GeminiMemoryPayload,
            user_preference="gemini",
        )
    except Exception as e:
        logger.info("life_memory gemini soft-fail: %s", type(e).__name__)
        return None

    if not result:
        return None
    out: List[Tuple[str, str]] = []
    known = {m.id for m in memories}
    for w in result.wordings or []:
        mid = (w.memory_id or "").strip()
        stmt = (w.statement or "").strip()
        if mid in known and stmt:
            out.append((mid, stmt))
    return out or None
