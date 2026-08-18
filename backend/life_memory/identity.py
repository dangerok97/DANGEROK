"""Memory identity + contradiction governance.

DATABASE RECORD ≠ MEMORY. SAME ≠ RELATED.
Structured slot identity first → value correlation → safe no-merge.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from life_memory.assemble import MemoryCandidate
from life_memory.authority import needs_clarification
from life_memory.models import MemoryGroup, MemoryItem, ProfileWriteTarget
from life_memory.present import present_statement
from life_memory.statements import group_label_for_domain

logger = logging.getLogger("ora.life_memory.identity")


def _parse_ts(raw: Optional[str]) -> float:
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def stable_memory_id(source_refs: Sequence[str], slot: str) -> str:
    payload = "|".join(sorted(source_refs) + [slot or ""])
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"memory:{digest}"


def _union_find_parent(parent: Dict[str, str], x: str) -> str:
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def _union(parent: Dict[str, str], a: str, b: str) -> None:
    ra, rb = _union_find_parent(parent, a), _union_find_parent(parent, b)
    if ra != rb:
        parent[rb] = ra


@dataclass
class ResolutionNote:
    a: str
    b: str
    relation: str
    reason: str


def resolve_memory_candidates(
    candidates: Sequence[MemoryCandidate],
) -> Tuple[List[MemoryItem], List[MemoryGroup], List[ResolutionNote]]:
    if not candidates:
        return [], [], []

    parent = {c.candidate_id: c.candidate_id for c in candidates}
    by_id = {c.candidate_id: c for c in candidates}
    notes: List[ResolutionNote] = []

    ids = [c.candidate_id for c in candidates]
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = by_id[ids[i]], by_id[ids[j]]
            rel = _pair_relation(a, b)
            if rel is None:
                continue
            notes.append(rel)
            if rel.relation == "same":
                _union(parent, a.candidate_id, b.candidate_id)
                logger.info(
                    "life_memory.identity same reason=%s a=%s b=%s",
                    rel.reason,
                    a.candidate_id,
                    b.candidate_id,
                )

    groups: Dict[str, List[MemoryCandidate]] = {}
    for c in candidates:
        root = _union_find_parent(parent, c.candidate_id)
        groups.setdefault(root, []).append(c)

    memories: List[MemoryItem] = []
    for members in groups.values():
        memories.append(_build_canonical(members))

    # Drop superseded after group resolve
    memories = [m for m in memories if m.status != "superseded" and m.statement]

    memories.sort(
        key=lambda m: (
            0 if m.status == "known" else 1 if m.status == "likely" else 2,
            m.group_label or "",
            m.statement,
        )
    )

    group_map: Dict[str, MemoryGroup] = {}
    for m in memories:
        gid = m.domain or "altro"
        if gid not in group_map:
            group_map[gid] = MemoryGroup(
                id=f"group:{gid}",
                label=m.group_label or group_label_for_domain(m.domain),
                domain=m.domain,
                memory_ids=[],
            )
        group_map[gid].memory_ids.append(m.id)

    # Stable group order — only groups with content
    order = [
        "identity",
        "lavoro",
        "studio",
        "casa",
        "auto",
        "famiglia",
        "salute",
        "finanze",
        "note",
    ]
    ordered_groups: List[MemoryGroup] = []
    seen = set()
    for d in order:
        if d in group_map:
            ordered_groups.append(group_map[d])
            seen.add(d)
    for d, g in group_map.items():
        if d not in seen:
            ordered_groups.append(g)

    return memories, ordered_groups, notes


def _pair_relation(a: MemoryCandidate, b: MemoryCandidate) -> Optional[ResolutionNote]:
    # Same authoritative source id
    if a.source_refs and a.source_refs == b.source_refs:
        return ResolutionNote(
            a.candidate_id, b.candidate_id, "same", "same_source_refs"
        )

    # Same slot → identity family (city, role, …)
    if a.slot and a.slot == b.slot and not a.slot.startswith("note:"):
        if a.value_norm and b.value_norm and a.value_norm == b.value_norm:
            return ResolutionNote(
                a.candidate_id, b.candidate_id, "same", "same_slot_value"
            )
        # Contradiction handled at build time within slot group — still merge slot
        return ResolutionNote(
            a.candidate_id, b.candidate_id, "same", "same_slot_family"
        )

    # Study subject entity overlap
    if a.kind == "study_subject" and b.kind == "study_subject":
        if set(a.entity_keys) & set(b.entity_keys):
            return ResolutionNote(
                a.candidate_id, b.candidate_id, "same", "same_study_entity"
            )

    # Strong statement correlation (same domain + high entity overlap)
    if a.domain and a.domain == b.domain and a.kind == b.kind == "fact":
        ea, eb = set(a.entity_keys), set(b.entity_keys)
        if ea and eb and ea == eb and a.value_norm == b.value_norm:
            return ResolutionNote(
                a.candidate_id, b.candidate_id, "same", "entity_value_match"
            )

    return None


def _build_canonical(members: Sequence[MemoryCandidate]) -> MemoryItem:
    # Authority: lower source_priority, then freshest updated_at
    ordered = sorted(
        members,
        key=lambda m: (m.source_priority, -_parse_ts(m.updated_at)),
    )
    winner = ordered[0]

    values = {m.value_norm for m in members if m.value_norm}
    status = winner.status
    statement = winner.statement
    resolution = "structured"

    if len(values) > 1:
        # Contradiction within same slot family
        confirmed = [
            m for m in ordered if m.source_priority <= 20 or m.status == "known"
        ]
        if confirmed:
            # Explicit user correction / strong source wins — others superseded
            winner = confirmed[0]
            statement = winner.statement
            status = "known"
            resolution = "contradiction_supersede"
            logger.info(
                "life_memory.contradiction supersede slot=%s winner=%s values=%s",
                winner.slot,
                winner.candidate_id,
                sorted(values),
            )
        else:
            status = "ambiguous"
            statement = winner.statement
            resolution = "contradiction_ambiguous"
            logger.info(
                "life_memory.contradiction ambiguous slot=%s values=%s",
                winner.slot,
                sorted(values),
            )

    source_refs = sorted({r for m in members for r in m.source_refs})
    evidence_refs = sorted({r for m in members for r in m.evidence_refs})
    mid = stable_memory_id(source_refs, winner.slot)

    profile_targets: List[ProfileWriteTarget] = []
    for ref in source_refs:
        if ref.startswith("life_profile:"):
            parts = ref.split(":", 2)
            if len(parts) == 3 and parts[1] and parts[2]:
                profile_targets.append(
                    ProfileWriteTarget(domain=parts[1], key=parts[2])
                )
    # Dedupe targets
    seen_t = set()
    uniq_targets: List[ProfileWriteTarget] = []
    for t in profile_targets:
        k = (t.domain, t.key)
        if k not in seen_t:
            seen_t.add(k)
            uniq_targets.append(t)

    cand_vals = sorted({m.value_norm for m in members if m.value_norm})
    # Winner authority — strongest among members
    auth_rank = {
        "user_confirmed": 0,
        "user_stated": 1,
        "structured_account": 2,
        "authoritative_document": 3,
        "structured_system": 4,
        "suggested": 5,
        "ai_inferred": 6,
        "device_signal": 7,
    }
    authority = min(
        (getattr(m, "authority", "suggested") for m in members),
        key=lambda a: auth_rank.get(a, 9),
    )
    # If any member is strong authority with same value → known
    if (
        authority
        in (
            "user_confirmed",
            "user_stated",
            "structured_account",
            "authoritative_document",
            "structured_system",
        )
        and status != "superseded"
    ):
        if len(values) <= 1:
            status = "known"

    presented, belief = present_statement(statement, status)
    clarifiable = needs_clarification(
        status=status,
        authority=authority,
        has_profile_targets=bool(uniq_targets),
        sensitivity=winner.sensitivity,
    )
    goal = None
    if clarifiable:
        goal = (
            "Determine whether this belief about the user is accurate "
            "and what the durable fact should be."
        )

    return MemoryItem(
        id=mid,
        kind=winner.kind,
        statement=presented,
        belief_statement=belief,
        domain=winner.domain,
        group_label=winner.group_label,
        status=status,  # type: ignore[arg-type]
        evidence_refs=evidence_refs,
        source_refs=source_refs,
        provenance_label=winner.provenance_label,
        learned_at=winner.learned_at,
        updated_at=winner.updated_at,
        editable=False,
        sensitivity=winner.sensitivity,  # type: ignore[arg-type]
        slot=winner.slot,
        candidate_values=cand_vals,
        profile_targets=uniq_targets,
        clarification_goal=goal,
        clarifiable=clarifiable,
        resolution_source=resolution,
        member_ids=[m.candidate_id for m in members],
    )


def apply_gemini_wordings(
    memories: Sequence[MemoryItem],
    wordings: Sequence[Tuple[str, str]],
) -> List[MemoryItem]:
    """Fill-only statement polish when Gemini returns wording for existing ids."""
    by_id = {m.id: m.model_copy(deep=True) for m in memories}
    for mid, statement in wordings:
        item = by_id.get(mid)
        if not item or not statement:
            continue
        s = " ".join(statement.split()).strip()
        if 3 <= len(s) <= 160:
            item.statement = s if s.endswith((".", "!", "?")) else f"{s}."
    return list(by_id.values())
