"""Semantic identity / entity resolution for Life Map.

DATABASE RECORD ≠ LIFE SITUATION
SAME ≠ RELATED

Pipeline stage: candidates → resolve → canonical situations.
Derived/rebuildable — never source of truth.
"""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional, Sequence, Set, Tuple

logger = logging.getLogger("ora.life_map.identity")

Relation = Literal["same", "related", "different", "uncertain"]
ResolveSource = Literal["structured", "correlation", "gemini", "unresolved"]


@dataclass
class SituationCandidate:
    """Pre-canonical life situation evidence unit."""

    candidate_id: str
    kind: str  # study | travel | inferred | …
    title: str
    temporal: Optional[str] = None
    summary: Optional[str] = None
    href: str = ""
    source_type: str = ""  # study_plan | travel_project | inferred | …
    source_id: str = ""
    lineage_refs: List[str] = field(default_factory=list)
    entity_raw: str = ""
    temporal_anchor: Optional[str] = None  # YYYY-MM-DD or start|end
    updated_at: Optional[str] = None
    evidence_refs: List[str] = field(default_factory=list)
    life_object_ids: List[str] = field(default_factory=list)


@dataclass
class ResolutionEdge:
    a: str
    b: str
    relation: Relation
    source: ResolveSource
    evidence_refs: List[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class LifeSituationIdentity:
    """Semantic identity of a real-life situation (not a DB row)."""

    canonical_key: str
    domain: Optional[str] = None
    entity_keys: List[str] = field(default_factory=list)
    temporal_anchor: Optional[str] = None
    source_refs: List[str] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)
    life_object_ids: List[str] = field(default_factory=list)


@dataclass
class CanonicalSituation:
    identity: LifeSituationIdentity
    kind: str
    title: str
    temporal: Optional[str] = None
    summary: Optional[str] = None
    href: str = ""
    member_ids: List[str] = field(default_factory=list)
    resolution_notes: List[str] = field(default_factory=list)


_WS = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    t = unicodedata.normalize("NFKC", (value or "").strip().lower())
    t = _WS.sub(" ", t)
    return t


def entity_keys_for(label: str) -> Set[str]:
    """Open-semantic entity keys — not subject-specific rules.

    Supports presentation shapes like «Kind: Entity» by also indexing
    the post-colon segment when present (generic, not Studio-only).
    """
    n = normalize_text(label)
    if not n:
        return set()
    keys = {n}
    if ":" in n:
        alt = n.split(":", 1)[1].strip()
        if alt:
            keys.add(alt)
    return keys


def temporal_anchor_day(iso: Optional[str]) -> Optional[str]:
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00")).date()
        return d.isoformat()
    except Exception:
        try:
            return date.fromisoformat(str(iso)[:10]).isoformat()
        except Exception:
            return None


def temporal_anchor_range(start: Optional[str], end: Optional[str]) -> Optional[str]:
    a = temporal_anchor_day(start)
    b = temporal_anchor_day(end)
    if a and b:
        return f"{a}|{b}"
    return a or b


def _parse_ts(raw: Optional[str]) -> float:
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def prefer_presentation_title(candidates: Sequence[SituationCandidate]) -> str:
    """canonical entity label > human label without presentation prefix > raw."""
    scored: List[Tuple[int, int, str]] = []
    for c in candidates:
        raw = (c.entity_raw or c.title or "").strip()
        if not raw:
            continue
        keys = entity_keys_for(raw)
        # Prefer forms without ':' (cleaner entity) and shorter human labels
        has_colon = 1 if ":" in raw else 0
        # Prefer the shortest key among entity_keys as display when colon form exists
        display = raw
        if ":" in raw and keys:
            # pick non-colon key matching post-colon content for display
            after = raw.split(":", 1)[1].strip()
            if after:
                display = after
        scored.append((has_colon, len(display), display))
    if not scored:
        return (candidates[0].title if candidates else "").strip() or "Situazione"
    scored.sort(key=lambda x: (x[0], x[1], x[2]))
    return scored[0][2]


def stable_canonical_id(source_refs: Sequence[str], evidence_refs: Sequence[str]) -> str:
    """Stable ID from structured refs — never hash(label)."""
    parts = sorted({r for r in source_refs if r}) or sorted({r for r in evidence_refs if r})
    if not parts:
        return "situation:unknown"
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"situation:{digest}"


def _union_find_parent(parent: Dict[str, str], x: str) -> str:
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def _union(parent: Dict[str, str], a: str, b: str) -> None:
    ra, rb = _union_find_parent(parent, a), _union_find_parent(parent, b)
    if ra != rb:
        parent[rb] = ra


def structured_same(a: SituationCandidate, b: SituationCandidate) -> Optional[ResolutionEdge]:
    """LEVEL 1 — authoritative structured identity."""
    if (
        a.source_type
        and a.source_type == b.source_type
        and a.source_id
        and a.source_id == b.source_id
    ):
        return ResolutionEdge(
            a=a.candidate_id,
            b=b.candidate_id,
            relation="same",
            source="structured",
            evidence_refs=sorted(set(a.evidence_refs + b.evidence_refs)),
            reason="same_source_id",
        )
    # Shared lineage (e.g. same Home priority that spawned multiple plans)
    shared_lineage = set(a.lineage_refs) & set(b.lineage_refs)
    if shared_lineage and a.source_type == b.source_type and a.source_type:
        return ResolutionEdge(
            a=a.candidate_id,
            b=b.candidate_id,
            relation="same",
            source="structured",
            evidence_refs=sorted(set(a.evidence_refs + b.evidence_refs) | shared_lineage),
            reason=f"shared_lineage:{sorted(shared_lineage)[0]}",
        )
    # Future: Life Object canonical id
    shared_lo = set(a.life_object_ids) & set(b.life_object_ids)
    if shared_lo:
        return ResolutionEdge(
            a=a.candidate_id,
            b=b.candidate_id,
            relation="same",
            source="structured",
            evidence_refs=sorted(set(a.evidence_refs + b.evidence_refs)),
            reason=f"shared_life_object:{sorted(shared_lo)[0]}",
        )
    return None


def correlated_same(a: SituationCandidate, b: SituationCandidate) -> Optional[ResolutionEdge]:
    """LEVEL 2 — strong structured correlation (no Gemini)."""
    if a.source_type != b.source_type or not a.source_type:
        return None
    if a.source_type not in ("study_plan", "travel_project"):
        return None
    keys_a = entity_keys_for(a.entity_raw or a.title)
    keys_b = entity_keys_for(b.entity_raw or b.title)
    if not keys_a or not keys_b or not (keys_a & keys_b):
        return None
    # Same temporal anchor required — different exam dates must NOT merge
    if not a.temporal_anchor or not b.temporal_anchor:
        return None
    if a.temporal_anchor != b.temporal_anchor:
        return None
    return ResolutionEdge(
        a=a.candidate_id,
        b=b.candidate_id,
        relation="same",
        source="correlation",
        evidence_refs=sorted(set(a.evidence_refs + b.evidence_refs)),
        reason="entity_and_temporal_anchor",
    )


def related_but_not_same(a: SituationCandidate, b: SituationCandidate) -> Optional[ResolutionEdge]:
    """Detect RELATED (shared entity, incompatible temporal) — never auto-merge."""
    if a.source_type != b.source_type or not a.source_type:
        return None
    keys_a = entity_keys_for(a.entity_raw or a.title)
    keys_b = entity_keys_for(b.entity_raw or b.title)
    if not (keys_a & keys_b):
        return None
    if a.temporal_anchor and b.temporal_anchor and a.temporal_anchor != b.temporal_anchor:
        return ResolutionEdge(
            a=a.candidate_id,
            b=b.candidate_id,
            relation="related",
            source="correlation",
            evidence_refs=sorted(set(a.evidence_refs + b.evidence_refs)),
            reason="same_entity_different_temporal",
        )
    return None


def resolve_candidates_deterministic(
    candidates: Sequence[SituationCandidate],
) -> Tuple[List[CanonicalSituation], List[ResolutionEdge]]:
    """LEVEL 1+2 resolution. Gemini pairs are returned as related/unresolved edges."""
    edges: List[ResolutionEdge] = []
    if not candidates:
        return [], edges

    parent = {c.candidate_id: c.candidate_id for c in candidates}
    by_id = {c.candidate_id: c for c in candidates}

    # Pairwise structured + correlation (N small for Contesti; typically < 50)
    ids = [c.candidate_id for c in candidates]
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = by_id[ids[i]], by_id[ids[j]]
            edge = structured_same(a, b) or correlated_same(a, b)
            if edge and edge.relation == "same":
                edges.append(edge)
                _union(parent, a.candidate_id, b.candidate_id)
                logger.info(
                    "life_map.identity same source=%s reason=%s a=%s b=%s",
                    edge.source,
                    edge.reason,
                    a.candidate_id,
                    b.candidate_id,
                )
            else:
                rel = related_but_not_same(a, b)
                if rel:
                    edges.append(rel)
                    logger.info(
                        "life_map.identity related reason=%s a=%s b=%s",
                        rel.reason,
                        a.candidate_id,
                        b.candidate_id,
                    )

    groups: Dict[str, List[SituationCandidate]] = {}
    for c in candidates:
        root = _union_find_parent(parent, c.candidate_id)
        groups.setdefault(root, []).append(c)

    canonicals: List[CanonicalSituation] = []
    for members in groups.values():
        canonicals.append(_build_canonical(members))
    return canonicals, edges


def _build_canonical(members: Sequence[SituationCandidate]) -> CanonicalSituation:
    # Freshest structured member wins dates/href
    ordered = sorted(members, key=lambda m: _parse_ts(m.updated_at), reverse=True)
    winner = ordered[0]
    source_refs = sorted(
        {
            f"{m.source_type}:{m.source_id}"
            for m in members
            if m.source_type and m.source_id
        }
        | {r for m in members for r in m.lineage_refs}
    )
    evidence_refs = sorted({r for m in members for r in m.evidence_refs})
    lo_ids = sorted({i for m in members for i in m.life_object_ids})
    entity_all = sorted({k for m in members for k in entity_keys_for(m.entity_raw or m.title)})
    # Prefer winner temporal_anchor; if lineage merge across dates, freshest wins
    anchor = winner.temporal_anchor
    title = prefer_presentation_title(members)
    identity = LifeSituationIdentity(
        canonical_key=stable_canonical_id(source_refs, evidence_refs),
        domain=winner.kind if winner.kind in ("study", "travel") else None,
        entity_keys=entity_all,
        temporal_anchor=anchor,
        source_refs=source_refs,
        evidence_refs=evidence_refs,
        life_object_ids=lo_ids,
    )
    # Prefer freshest non-empty href
    href = ""
    for m in ordered:
        if m.href:
            href = m.href
            break
    return CanonicalSituation(
        identity=identity,
        kind=winner.kind,
        title=title,
        temporal=winner.temporal,
        summary=winner.summary if winner.summary and winner.summary != title else None,
        href=href,
        member_ids=[m.candidate_id for m in members],
        resolution_notes=[f"members={len(members)}"],
    )


def apply_gemini_same_edges(
    candidates: Sequence[SituationCandidate],
    edges: Sequence[ResolutionEdge],
    gemini_edges: Sequence[ResolutionEdge],
) -> List[CanonicalSituation]:
    """Merge only Gemini SAME that do not contradict structured DIFFERENT temporal.

    Structured truth wins: if deterministic said related (same entity, different
    temporal), Gemini cannot force SAME.
    """
    blocked: Set[Tuple[str, str]] = set()
    for e in edges:
        if e.relation == "related" and e.reason == "same_entity_different_temporal":
            blocked.add(tuple(sorted((e.a, e.b))))

    parent = {c.candidate_id: c.candidate_id for c in candidates}
    # Replay deterministic SAME
    for e in edges:
        if e.relation == "same":
            _union(parent, e.a, e.b)

    for e in gemini_edges:
        if e.relation != "same":
            continue
        key = tuple(sorted((e.a, e.b)))
        if key in blocked:
            logger.info(
                "life_map.identity gemini_same_blocked structured_conflict a=%s b=%s",
                e.a,
                e.b,
            )
            continue
        # Require evidence refs on both sides exist
        by_id = {c.candidate_id: c for c in candidates}
        if e.a not in by_id or e.b not in by_id:
            continue
        _union(parent, e.a, e.b)
        logger.info(
            "life_map.identity same source=gemini reason=%s a=%s b=%s",
            e.reason,
            e.a,
            e.b,
        )

    by_id = {c.candidate_id: c for c in candidates}
    groups: Dict[str, List[SituationCandidate]] = {}
    for c in candidates:
        root = _union_find_parent(parent, c.candidate_id)
        groups.setdefault(root, []).append(c)
    return [_build_canonical(m) for m in groups.values()]


def unresolved_pairs_for_gemini(
    candidates: Sequence[SituationCandidate],
    edges: Sequence[ResolutionEdge],
    *,
    max_pairs: int = 8,
) -> List[Tuple[SituationCandidate, SituationCandidate]]:
    """Candidate pairs sharing entity keys but not yet SAME/DIFFERENT — minimize Gemini."""
    already_same: Set[Tuple[str, str]] = set()
    already_related: Set[Tuple[str, str]] = set()
    for e in edges:
        key = tuple(sorted((e.a, e.b)))
        if e.relation == "same":
            already_same.add(key)
        elif e.relation in ("related", "different"):
            already_related.add(key)

    by_id = {c.candidate_id: c for c in candidates}
    # Only consider pairs not already in same union — approximate via already_same
    out: List[Tuple[SituationCandidate, SituationCandidate]] = []
    ids = [c.candidate_id for c in candidates]
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = by_id[ids[i]], by_id[ids[j]]
            key = tuple(sorted((a.candidate_id, b.candidate_id)))
            if key in already_same or key in already_related:
                continue
            keys_a = entity_keys_for(a.entity_raw or a.title)
            keys_b = entity_keys_for(b.entity_raw or b.title)
            if not (keys_a & keys_b):
                continue
            # Skip if structured already decided via lineage in already_same
            out.append((a, b))
            if len(out) >= max_pairs:
                return out
    return out


def canonical_to_presentation(c: CanonicalSituation):
    from life_map.models import PresentationSituation

    return PresentationSituation(
        id=c.identity.canonical_key,
        kind=c.kind,
        title=c.title,
        temporal=c.temporal,
        summary=c.summary,
        href=c.href or "",
    )
