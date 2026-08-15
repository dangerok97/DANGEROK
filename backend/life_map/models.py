"""Structured Life Map interpretation — Gemini never returns free prose for Contesti."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

LIFE_MAP_VERSION = "life-map-1.0"

ConfidenceBand = Literal["known", "likely", "ambiguous"]
EvidenceKind = Literal[
    "life_profile_fact",
    "study_plan",
    "travel_project",
    "life_os_plan",
    "life_object",
    "document",
    "conversation_fact",
]
RelationKind = Literal[
    "related_to",
    "involves_person",
    "uses",
    "occurs_at",
    "part_of",
    "other",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvidenceRef(BaseModel):
    id: str
    kind: EvidenceKind
    label: str = ""
    # Minimized payload for grounding — never secrets
    summary: str = ""


class LifeAreaInterpretation(BaseModel):
    id: str
    label: str
    identity: Optional[str] = None
    domain_key: Optional[str] = None
    evidence_refs: List[str] = Field(default_factory=list)
    confidence: ConfidenceBand = "known"
    source: Literal["structured", "inferred"] = "structured"


class LifeSituationInterpretation(BaseModel):
    id: str
    label: str
    temporal_state: Optional[str] = None
    summary: Optional[str] = None
    kind: Optional[str] = None  # study | travel | inferred | …
    href: Optional[str] = None
    related_area_ids: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    confidence: ConfidenceBand = "known"
    source: Literal["structured", "inferred"] = "structured"


class LifeRelationshipInterpretation(BaseModel):
    source_id: str
    target_id: str
    relation: RelationKind = "related_to"
    evidence_refs: List[str] = Field(default_factory=list)
    confidence: ConfidenceBand = "likely"


class LifeMapAmbiguity(BaseModel):
    id: str
    question: str
    about_ids: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    # For future Conversation clarification — not shown as UI chrome in Contesti V1
    status: Literal["open"] = "open"


class LifeMapInterpretation(BaseModel):
    """Validated Gemini (or empty) semantic layer — never source of truth alone."""

    areas: List[LifeAreaInterpretation] = Field(default_factory=list)
    situations: List[LifeSituationInterpretation] = Field(default_factory=list)
    relationships: List[LifeRelationshipInterpretation] = Field(default_factory=list)
    ambiguities: List[LifeMapAmbiguity] = Field(default_factory=list)
    ai_used: bool = False
    provider: Optional[str] = None
    model: Optional[str] = None
    generated_at: str = Field(default_factory=now_iso)


class PresentationArea(BaseModel):
    id: str
    domain: str
    title: str
    identity: Optional[str] = None


class PresentationSituation(BaseModel):
    """Presentation row for Contesti — open `kind` (study|travel|inferred|…)."""

    id: str
    kind: str
    title: str
    temporal: Optional[str] = None
    summary: Optional[str] = None
    # Empty = informational only (no fake detail route)
    href: str = ""


class LifeMapResponse(BaseModel):
    """API payload for Contesti — presentation from structured + presentable AI.

    `life_map_snapshots` cache is DERIVED / REBUILDABLE — never source of truth.
    """

    ok: bool = True
    version: str = LIFE_MAP_VERSION
    areas: List[PresentationArea] = Field(default_factory=list)
    situations: List[PresentationSituation] = Field(default_factory=list)
    evidence: List[EvidenceRef] = Field(default_factory=list)
    interpretation: Optional[LifeMapInterpretation] = None
    fingerprint: str = ""
    deterministic: bool = True
    ai_enrichment: Literal["off", "cached", "fresh", "failed", "skipped"] = "off"
    generated_at: str = Field(default_factory=now_iso)


class GeminiLifeMapPayload(BaseModel):
    """Strict schema for chat_json — Gemini cognition output only."""

    area_label_overrides: List[Dict[str, Any]] = Field(default_factory=list)
    # [{ "area_id": "...", "label": "...", "identity": "..." }]
    novel_situations: List[Dict[str, Any]] = Field(default_factory=list)
    # [{ "id", "label", "temporal_state?", "summary?", "evidence_refs": [], "related_area_ids?", "confidence" }]
    relationships: List[Dict[str, Any]] = Field(default_factory=list)
    ambiguities: List[Dict[str, Any]] = Field(default_factory=list)
