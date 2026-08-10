"""Governance — reject Gemini inventions without evidence."""
from __future__ import annotations

import re
from typing import Iterable, List, Optional, Set

from life_map.governance import stable_inferred_situation_id
from life_map.models import (
    ConfidenceBand,
    EvidenceRef,
    GeminiLifeMapPayload,
    LifeAreaInterpretation,
    LifeMapAmbiguity,
    LifeMapInterpretation,
    LifeRelationshipInterpretation,
    LifeSituationInterpretation,
    now_iso,
)

_JUDGY = re.compile(
    r"\b(emozionante|sfida|fantastico|incredibile|magnifico|epico)\b",
    re.IGNORECASE,
)


def _clean_label(raw: str) -> Optional[str]:
    t = (raw or "").strip()
    if not t or len(t) > 80:
        return None
    if _JUDGY.search(t):
        return None
    return t


def _band(raw: object) -> ConfidenceBand:
    s = str(raw or "likely").strip().lower()
    if s in ("known", "likely", "ambiguous"):
        return s  # type: ignore[return-value]
    return "likely"


def validate_gemini_payload(
    payload: GeminiLifeMapPayload,
    *,
    evidence: Iterable[EvidenceRef],
    known_area_ids: Set[str],
    known_situation_ids: Set[str],
) -> LifeMapInterpretation:
    """Map Gemini payload → LifeMapInterpretation; drop ungrounded items."""
    evid_ids = {e.id for e in evidence}
    interpretation = LifeMapInterpretation(
        ai_used=True,
        generated_at=now_iso(),
    )

    for item in payload.area_label_overrides or []:
        if not isinstance(item, dict):
            continue
        area_id = str(item.get("area_id") or "").strip()
        if area_id not in known_area_ids:
            continue
        refs = [str(r) for r in (item.get("evidence_refs") or []) if str(r) in evid_ids]
        if not refs:
            domain = area_id.replace("area:", "", 1)
            refs = [e for e in evid_ids if e.startswith(f"profile:{domain}:")]
        if not refs:
            continue
        label = _clean_label(str(item.get("label") or ""))
        identity = _clean_label(str(item.get("identity") or "")) if item.get("identity") else None
        if not label and not identity:
            continue
        domain = area_id.replace("area:", "", 1) if area_id.startswith("area:") else None
        interpretation.areas.append(
            LifeAreaInterpretation(
                id=area_id,
                label=label or "",
                identity=identity,
                domain_key=domain,
                evidence_refs=refs[:8],
                confidence=_band(item.get("confidence") or "known"),
                source="inferred",
            )
        )

    for item in payload.novel_situations or []:
        if not isinstance(item, dict):
            continue
        label = _clean_label(str(item.get("label") or ""))
        if not label:
            continue
        refs = [str(r) for r in (item.get("evidence_refs") or []) if str(r) in evid_ids]
        if not refs:
            continue  # hallucinated / missing evidence → drop
        conf = _band(item.get("confidence") or "likely")
        if conf == "ambiguous":
            q = _clean_label(
                str(item.get("ambiguity_question") or f"Cosa significa «{label}» per te?")
            )
            if q:
                interpretation.ambiguities.append(
                    LifeMapAmbiguity(
                        id=f"amb:{stable_inferred_situation_id(refs)[9:]}",
                        question=q,
                        evidence_refs=refs[:8],
                    )
                )
            continue
        # Stable identity from evidence — ignore Gemini label churn / arbitrary ids
        sid = stable_inferred_situation_id(refs)
        if sid in known_situation_ids:
            continue
        related = [
            str(a)
            for a in (item.get("related_area_ids") or [])
            if str(a) in known_area_ids
        ]
        temporal = (
            _clean_label(str(item.get("temporal_state") or ""))
            if item.get("temporal_state")
            else None
        )
        summary = (
            _clean_label(str(item.get("summary") or "")) if item.get("summary") else None
        )
        # Never attach fake detail routes
        href = None
        interpretation.situations.append(
            LifeSituationInterpretation(
                id=sid,
                label=label,
                temporal_state=temporal,
                summary=summary,
                kind="inferred",
                href=href,
                related_area_ids=related,
                evidence_refs=refs[:8],
                confidence=conf,
                source="inferred",
            )
        )

    for item in payload.relationships or []:
        if not isinstance(item, dict):
            continue
        src = str(item.get("source_id") or item.get("source") or "").strip()
        tgt = str(item.get("target_id") or item.get("target") or "").strip()
        if not src or not tgt:
            continue
        known_nodes = known_area_ids | known_situation_ids
        inferred_ids = {s.id for s in interpretation.situations}
        if src not in known_nodes and src not in inferred_ids:
            continue
        if tgt not in known_nodes and tgt not in inferred_ids:
            continue
        refs = [str(r) for r in (item.get("evidence_refs") or []) if str(r) in evid_ids]
        if not refs:
            continue
        conf = _band(item.get("confidence") or "likely")
        if conf == "ambiguous":
            q = _clean_label(
                str(
                    item.get("ambiguity_question")
                    or "Come sono collegate queste parti della tua vita?"
                )
            )
            if q:
                interpretation.ambiguities.append(
                    LifeMapAmbiguity(
                        id=f"amb:rel:{stable_inferred_situation_id(refs)[9:]}",
                        question=q,
                        about_ids=[src, tgt],
                        evidence_refs=refs[:8],
                    )
                )
            continue
        rel = str(item.get("relation") or "related_to")
        if rel not in (
            "related_to",
            "involves_person",
            "uses",
            "occurs_at",
            "part_of",
            "other",
        ):
            rel = "related_to"
        interpretation.relationships.append(
            LifeRelationshipInterpretation(
                source_id=src,
                target_id=tgt,
                relation=rel,  # type: ignore[arg-type]
                evidence_refs=refs[:8],
                confidence=conf,
            )
        )

    for item in payload.ambiguities or []:
        if not isinstance(item, dict):
            continue
        q = _clean_label(str(item.get("question") or ""))
        if not q:
            continue
        refs = [str(r) for r in (item.get("evidence_refs") or []) if str(r) in evid_ids]
        interpretation.ambiguities.append(
            LifeMapAmbiguity(
                id=str(item.get("id") or f"amb:{hash(q) & 0xFFFFFFFF:x}"),
                question=q,
                about_ids=[str(a) for a in (item.get("about_ids") or [])][:8],
                evidence_refs=refs[:8],
            )
        )

    return interpretation
