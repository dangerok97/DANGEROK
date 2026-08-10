"""Optional Gemini cognition pass for Life Map — shared Provider Manager only."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Set

from life_map.models import (
    EvidenceRef,
    GeminiLifeMapPayload,
    LifeMapInterpretation,
    PresentationArea,
    PresentationSituation,
)
from life_map.validate import validate_gemini_payload

logger = logging.getLogger("ora.life_map.gemini")

SYSTEM = """Sei il cognition layer di ORA per la Life Map (Contesti).

Compito: interpreta semanticamente le evidenze fornite per individuare
ambiti persistenti, situazioni vive, relazioni utili e ambiguità.
NON creare categorie/taxonomy. NON aggiungere fatti non supportati.

Regole assolute:
- Usa SOLO le evidenze fornite. Non inventare fatti (auto, casa, persone, date, luoghi).
- Output JSON strutturato conforme allo schema. Niente prosa libera.
- Label brevi (≤80), factual, italiane, calme — mai giudicanti, motivational o creative.
- OPEN SEMANTICS: situazioni novel (es. palestra, matrimonio, volontariato) senza enum.
- Non inventare ID di evidenza. Ogni novel_situation DEVE citare evidence_refs esistenti.
- confidence: known | likely | ambiguous — se incerto usa ambiguities[], non fatti.
- Non suggerire UI, colori, layout, icone, badge.
- Non ripetere date/status già presenti nelle presentation_situations strutturate.
- Non mutare fatti strutturati (date esame, destinazioni viaggio, ecc.).
"""


def life_map_gemini_enabled() -> bool:
    raw = (os.environ.get("LIFE_MAP_GEMINI") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _minimize_evidence(evidence: List[EvidenceRef], *, limit: int = 40) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for e in evidence[:limit]:
        out.append(
            {
                "id": e.id,
                "kind": e.kind,
                "label": (e.label or "")[:80],
                "summary": (e.summary or "")[:120],
            }
        )
    return out


async def interpret_with_gemini(
    *,
    areas: List[PresentationArea],
    situations: List[PresentationSituation],
    evidence: List[EvidenceRef],
) -> Optional[LifeMapInterpretation]:
    """Return validated interpretation or None on any failure / flag off."""
    if not life_map_gemini_enabled():
        return None
    if not evidence:
        return None
    try:
        from llm.structured import chat_json
    except Exception as e:
        logger.info("life_map gemini unavailable: %s", type(e).__name__)
        return None

    user_payload = {
        "presentation_areas": [
            {"id": a.id, "domain": a.domain, "title": a.title, "identity": a.identity}
            for a in areas
        ],
        "presentation_situations": [
            {
                "id": s.id,
                "kind": s.kind,
                "title": s.title,
                "temporal": s.temporal,
                "summary": s.summary,
            }
            for s in situations
        ],
        "evidence": _minimize_evidence(evidence),
        "schema": {
            "area_label_overrides": [
                {"area_id": "area:lavoro", "identity": "…", "evidence_refs": ["…"], "confidence": "likely"}
            ],
            "novel_situations": [
                {
                    "id": "inferred:…",
                    "label": "…",
                    "temporal_state": "…",
                    "summary": "…",
                    "evidence_refs": ["…"],
                    "related_area_ids": ["area:…"],
                    "confidence": "likely",
                }
            ],
            "relationships": [
                {
                    "source_id": "…",
                    "target_id": "…",
                    "relation": "related_to",
                    "evidence_refs": ["…"],
                    "confidence": "likely",
                }
            ],
            "ambiguities": [
                {"id": "amb:…", "question": "…", "about_ids": [], "evidence_refs": ["…"]}
            ],
        },
        "task": (
            "Interpreta le evidenze: situazioni vive non coperte da study/travel, "
            "identità mancanti, relazioni grounded, ambiguità. "
            "Se non c'è nulla di nuovo da capire, restituisci liste vuote."
        ),
    }

    try:
        parsed, meta = await chat_json(
            system=SYSTEM,
            user=json.dumps(user_payload, ensure_ascii=False),
            model_cls=GeminiLifeMapPayload,
            user_preference="gemini",
        )
    except Exception as e:
        logger.info("life_map gemini soft-fail: %s", type(e).__name__)
        return None

    known_areas: Set[str] = {a.id for a in areas}
    known_sits: Set[str] = {s.id for s in situations}
    interpretation = validate_gemini_payload(
        parsed,
        evidence=evidence,
        known_area_ids=known_areas,
        known_situation_ids=known_sits,
    )
    interpretation.provider = str((meta or {}).get("provider") or "gemini")
    interpretation.model = str((meta or {}).get("model") or "") or None
    return interpretation
