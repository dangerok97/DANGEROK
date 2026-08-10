"""Life Map governance — presentability, stable IDs, merge, dedup.

Life Map snapshots are DERIVED / REBUILDABLE cache — never source of truth.
DETERMINISTIC STRUCTURED REALITY > AI INTERPRETATION.
"""
from __future__ import annotations

import hashlib
from typing import Iterable, List, Optional, Sequence, Set

from life_map.models import (
    LifeMapInterpretation,
    LifeSituationInterpretation,
    PresentationArea,
    PresentationSituation,
)


def stable_inferred_situation_id(evidence_refs: Sequence[str]) -> str:
    """Identity from evidence, not Gemini label — stable across label paraphrase."""
    key = "|".join(sorted({str(r).strip() for r in evidence_refs if str(r).strip()}))
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return f"inferred:{digest}"


def is_presentable_life_map_item(
    *,
    confidence: str,
    evidence_refs: Sequence[str],
    valid_evidence_ids: Set[str],
    source: str = "inferred",
) -> bool:
    """Contesti may show AI items only when grounded and not ambiguous."""
    if source == "structured":
        return True
    band = (confidence or "").strip().lower()
    if band not in ("known", "likely"):
        return False
    refs = [str(r) for r in evidence_refs if str(r) in valid_evidence_ids]
    return len(refs) >= 1


def shares_structured_evidence(
    ai_refs: Sequence[str],
    structured_situation_ids: Set[str],
) -> bool:
    """Dedup: AI situation grounded on same study/travel evidence as a structured row."""
    for r in ai_refs:
        if r in structured_situation_ids:
            return True
        # profile evidence alone does not collide with study/travel ids
    return False


def merge_presentation(
    *,
    areas: List[PresentationArea],
    situations: List[PresentationSituation],
    interpretation: Optional[LifeMapInterpretation],
    valid_evidence_ids: Optional[Set[str]] = None,
) -> tuple[List[PresentationArea], List[PresentationSituation]]:
    """Merge AI into presentation. Structured rows never lose title/temporal/href."""
    if not interpretation or not interpretation.ai_used:
        return areas, situations

    structured_ids = {s.id for s in situations}

    def _ok(confidence: str, refs: Sequence[str], source: str) -> bool:
        # None → trust refs already validated; explicit set → enforce pack membership
        pack = set(refs) if valid_evidence_ids is None else valid_evidence_ids
        return is_presentable_life_map_item(
            confidence=confidence,
            evidence_refs=refs,
            valid_evidence_ids=pack,
            source=source,
        )

    # Identity fill-only on areas — never overwrite structured identity
    area_by_id = {a.id: a for a in areas}
    for ai_area in interpretation.areas:
        base = area_by_id.get(ai_area.id)
        if not base:
            continue
        if not _ok(ai_area.confidence, ai_area.evidence_refs, ai_area.source):
            continue
        if ai_area.identity and not base.identity:
            base.identity = ai_area.identity

    out_situations = list(situations)
    seen_stable: Set[str] = {s.id for s in out_situations}

    for ai_sit in interpretation.situations:
        if not _ok(ai_sit.confidence, ai_sit.evidence_refs, ai_sit.source):
            continue
        if shares_structured_evidence(ai_sit.evidence_refs, structured_ids):
            # Deterministic study/travel wins — drop AI paraphrase
            continue
        sid = ai_sit.id or stable_inferred_situation_id(ai_sit.evidence_refs)
        if sid in seen_stable:
            continue
        # Never invent navigation
        href = (ai_sit.href or "").strip()
        out_situations.append(
            PresentationSituation(
                id=sid,
                kind=ai_sit.kind or "inferred",
                title=ai_sit.label,
                temporal=ai_sit.temporal_state,
                summary=ai_sit.summary,
                href=href,
            )
        )
        seen_stable.add(sid)

    return areas, out_situations
