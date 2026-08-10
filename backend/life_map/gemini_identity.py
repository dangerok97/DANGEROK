"""Optional Gemini identity consultant — SAME/RELATED/DIFFERENT/UNCERTAIN.

Never overrides structured DIFFERENT temporal. Minimized candidate packs only.
"""
from __future__ import annotations

import json
import logging
from typing import List, Optional, Sequence

from pydantic import BaseModel, Field

from life_map.gemini_interpret import life_map_gemini_enabled
from life_map.identity import (
    ResolutionEdge,
    SituationCandidate,
    unresolved_pairs_for_gemini,
)

logger = logging.getLogger("ora.life_map.identity.gemini")

SYSTEM = """Sei il consultant di identity resolution per ORA Life Map.
Confronta SOLO le due situazioni candidate fornite.
Rispondi JSON: relation = same|related|different|uncertain.
Regole:
- same = stessa situazione di vita reale (non solo label simili)
- related = collegate ma non la stessa (es. stesso soggetto, date distinte)
- different = situazioni distinte
- uncertain = non abbastanza evidenza
Non inventare date, ID o fatti. Non decidere UI.
"""


class GeminiIdentityVerdict(BaseModel):
    relation: str = "uncertain"
    reason: str = ""
    evidence_refs: List[str] = Field(default_factory=list)


def _pack_candidate(c: SituationCandidate) -> dict:
    return {
        "id": c.candidate_id,
        "kind": c.kind,
        "entity": (c.entity_raw or c.title)[:80],
        "temporal_anchor": c.temporal_anchor,
        "source": f"{c.source_type}:{c.source_id}" if c.source_id else c.source_type,
        "lineage_refs": c.lineage_refs[:4],
        "evidence_refs": c.evidence_refs[:6],
        "updated_at": c.updated_at,
    }


async def resolve_identity_with_gemini(
    candidates: Sequence[SituationCandidate],
    edges: Sequence[ResolutionEdge],
    *,
    max_pairs: int = 8,
) -> List[ResolutionEdge]:
    if not life_map_gemini_enabled():
        return []
    pairs = unresolved_pairs_for_gemini(candidates, edges, max_pairs=max_pairs)
    if not pairs:
        return []
    try:
        from llm.structured import chat_json
    except Exception as e:
        logger.info("life_map identity gemini unavailable: %s", type(e).__name__)
        return []

    out: List[ResolutionEdge] = []
    for a, b in pairs:
        user = {
            "candidate_a": _pack_candidate(a),
            "candidate_b": _pack_candidate(b),
            "task": "Sono la stessa situazione di vita, related, different o uncertain?",
        }
        try:
            parsed, _meta = await chat_json(
                system=SYSTEM,
                user=json.dumps(user, ensure_ascii=False),
                model_cls=GeminiIdentityVerdict,
                user_preference="gemini",
            )
        except Exception as e:
            logger.info("life_map identity gemini pair soft-fail: %s", type(e).__name__)
            continue
        rel = (parsed.relation or "uncertain").strip().lower()
        if rel not in ("same", "related", "different", "uncertain"):
            rel = "uncertain"
        refs = [
            r
            for r in (parsed.evidence_refs or [])
            if r in set(a.evidence_refs + b.evidence_refs)
        ]
        out.append(
            ResolutionEdge(
                a=a.candidate_id,
                b=b.candidate_id,
                relation=rel,  # type: ignore[arg-type]
                source="gemini",
                evidence_refs=refs or sorted(set(a.evidence_refs + b.evidence_refs))[:8],
                reason=(parsed.reason or "")[:160],
            )
        )
    return out
