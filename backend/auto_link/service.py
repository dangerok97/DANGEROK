"""
AutoLinkService — orchestrator.

Public methods:
  analyze(user_id, decision_id, force=False) → list of proposals
  reanalyze(user_id, decision_id)            → list of proposals (force=True + supersede)
  list_proposals(user_id, decision_id, include_all=False)
  get_proposal(user_id, proposal_id)
  accept(user_id, proposal_id, reason=None)
  reject(user_id, proposal_id, reason=None)

Everything is deterministic; no GPT, no external calls.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .candidate_finder import find_candidates
from .confidence import apply_confidence, can_auto_accept, mark_ambiguity
from .matcher import decision_text as compute_decision_text, evaluate_pair, s_graph_direct
from .repository import AutoLinkRepository
from .types import (
    MATCHER_VERSION,
    Candidate,
    MatchSignal,
    ProposalStatus,
    Thresholds,
    VERIFIABLE_TAGS,
)


logger = logging.getLogger("ora.auto_link")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return f"prop_{uuid.uuid4().hex[:12]}"


def _decision_signature(decision: Dict[str, Any]) -> str:
    """Stable hash of the Decision fields that affect matching. Any change
    invalidates prior proposals (they get `superseded` on re-analyze)."""
    payload = {
        "title": decision.get("title"),
        "description": decision.get("description"),
        "category": decision.get("category"),
        "metadata": decision.get("metadata") or {},
        "node_ids": sorted(decision.get("node_ids") or []),
        "linked_to": sorted(decision.get("linked_to") or []),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _reason_for(candidate: Candidate) -> str:
    """Compose a compact human explanation from the strongest signals."""
    if not candidate.signals:
        return "Nessuna correlazione rilevante."
    # Sort by contribution descending, cap at 3.
    top = sorted(candidate.signals, key=lambda s: -s.contribution)[:3]
    return " · ".join(s.description for s in top) + "."


class AutoLinkService:
    def __init__(self, db, life_graph, thresholds: Optional[Thresholds] = None):
        self.repo = AutoLinkRepository(db, life_graph)
        self.life_graph = life_graph
        self.thresholds = thresholds or Thresholds()

    # ==================================================================
    # main entry: analyze
    # ==================================================================
    async def analyze(
        self,
        user_id: str,
        decision_id: str,
        *,
        force: bool = False,
        actor_type: str = "system",
    ) -> Dict[str, Any]:
        decision = await self.repo.get_decision(user_id, decision_id)
        if not decision:
            return {"error": "decision_not_found"}

        dsig = _decision_signature(decision)
        dtext = compute_decision_text(decision)

        # Discover + score candidates.
        candidates = await find_candidates(self.repo, user_id, decision)
        if not candidates:
            await self.repo.supersede_others(user_id, decision_id, keep_ids=[], reason="no_candidates")
            return {"decision_id": decision_id, "matcher_version": MATCHER_VERSION, "decision_signature": dsig, "proposals": [], "auto_accepted": []}

        # Fetch knowledge for all candidates in one call.
        knowledge_map = await self.repo.get_knowledge_bulk(user_id, [c.node_id for c in candidates])

        # Pass 1: base signals (per-pair, no graph).
        for c in candidates:
            k = knowledge_map.get(c.node_id)
            c.node_knowledge_version = int((k or {}).get("version") or 0)
            c.signals = evaluate_pair(decision, self._min_node(c), k, dtext)
        apply_confidence(candidates)

        # Pass 2: graph propagation — nodes adjacent to strong matches get a bump.
        # Bounded traversal depth 1 to keep it explainable.
        strong = {c.node_id: c.confidence for c in candidates if c.confidence >= self.thresholds.ambiguity_floor}
        if strong:
            neighbors = await self.repo.neighbors(user_id, list(strong.keys()), depth=1)
            # invert: node -> which strong neighbors is it connected to
            adj: Dict[str, Dict[str, float]] = {}
            for src, nbrs in neighbors.items():
                src_conf = strong.get(src, 0.0)
                for n in nbrs:
                    adj.setdefault(n, {})[src] = src_conf
            for c in candidates:
                extras = adj.get(c.node_id)
                if extras:
                    c.signals.extend(s_graph_direct({"id": c.node_id}, extras))
            apply_confidence(candidates)

        # Filter below diagnostic threshold entirely.
        candidates = [c for c in candidates if c.confidence >= self.thresholds.diagnostic]

        # Sort by confidence desc, then by node_id for determinism.
        candidates.sort(key=lambda c: (-c.confidence, c.node_id))

        # Ambiguity marking.
        mark_ambiguity(candidates, self.thresholds)

        # Persist proposals idempotently.
        created: List[Dict[str, Any]] = []
        auto_accepted: List[Dict[str, Any]] = []
        keep_ids: List[str] = []

        for c in candidates:
            # Suppress if a rejected proposal exists with the SAME decision signature.
            if not force:
                suppressed = await self.repo.find_rejected_still_valid(user_id, decision_id, c.node_id, dsig)
                if suppressed:
                    continue

            # Idempotence: reuse existing proposed/accepted proposal if the signature matches.
            existing = await self.repo.find_active(user_id, decision_id, c.node_id)
            if existing and existing.get("decision_signature") == dsig and existing.get("node_knowledge_version") == c.node_knowledge_version and existing.get("matcher_version") == MATCHER_VERSION and not force:
                keep_ids.append(existing["id"])
                created.append(existing)
                continue

            # If existing but stale, supersede it (unless already accepted).
            if existing and existing.get("status") == "proposed":
                await self.repo.update_proposal(user_id, existing["id"], {
                    "status": ProposalStatus.SUPERSEDED.value,
                    "superseded_at": _now(),
                    "superseded_reason": "data_changed",
                })

            confidence_below_propose = c.confidence < self.thresholds.propose

            proposal_doc = {
                "id": _new_id(),
                "user_id": user_id,
                "decision_id": decision_id,
                "node_id": c.node_id,
                "node_type": c.node_type,
                "node_label_safe": (c.node_label or "")[:64],
                "status": ProposalStatus.PROPOSED.value,
                "confidence": c.confidence,
                "ambiguous": c.ambiguous,
                "matching_signals": [
                    {
                        "tag": s.tag,
                        "description": s.description,
                        "contribution": s.contribution,
                        "verifiable": s.verifiable,
                    }
                    for s in c.signals
                ],
                "reason": _reason_for(c),
                "matcher_version": MATCHER_VERSION,
                "decision_signature": dsig,
                "node_knowledge_version": c.node_knowledge_version,
                "provenance": {
                    "source_type": "system",
                    "actor_type": actor_type,
                    "confidence": c.confidence,
                    "verified_by_user": False,
                    "extracted_at": _now(),
                },
                "diagnostic_only": confidence_below_propose,
                "created_at": _now(),
                "updated_at": _now(),
                "accepted_at": None,
                "rejected_at": None,
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            }

            if confidence_below_propose:
                # Keep as diagnostic only; do not persist to avoid noise.
                continue

            await self.repo.insert_proposal(proposal_doc)
            proposal_doc.pop("_id", None)  # insert_one mutated the dict
            keep_ids.append(proposal_doc["id"])
            created.append(proposal_doc)

            # Auto-accept only when unambiguous verifiable match.
            if can_auto_accept(c, self.thresholds):
                accepted = await self._apply_accept(user_id, proposal_doc["id"], actor_type="system", reason="auto_accept: verifiable match")
                if accepted:
                    auto_accepted.append(accepted)

        # Anything else previously proposed on this decision but not in keep_ids is stale.
        superseded_count = await self.repo.supersede_others(user_id, decision_id, keep_ids=keep_ids, reason="reanalysis")

        logger.info(
            "auto_link.analyze user=%s decision=%s candidates=%d proposals=%d auto_accepted=%d superseded=%d",
            user_id, decision_id, len(candidates), len(created), len(auto_accepted), superseded_count,
        )

        # Never return the raw internal Candidate objects.
        return {
            "decision_id": decision_id,
            "matcher_version": MATCHER_VERSION,
            "decision_signature": dsig,
            "proposals": created,
            "auto_accepted": auto_accepted,
            "superseded": superseded_count,
        }

    async def reanalyze(self, user_id: str, decision_id: str) -> Dict[str, Any]:
        return await self.analyze(user_id, decision_id, force=True, actor_type="user")

    # ==================================================================
    # read
    # ==================================================================
    async def list_proposals(self, user_id: str, decision_id: str, include_all: bool = False) -> List[Dict[str, Any]]:
        return await self.repo.list_by_decision(user_id, decision_id, include_all_statuses=include_all)

    async def get_proposal(self, user_id: str, proposal_id: str) -> Optional[Dict[str, Any]]:
        return await self.repo.get_proposal(user_id, proposal_id)

    # ==================================================================
    # accept
    # ==================================================================
    async def accept(self, user_id: str, proposal_id: str, *, reason: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return await self._apply_accept(user_id, proposal_id, actor_type="user", reason=reason or "user_accept")

    async def _apply_accept(self, user_id: str, proposal_id: str, *, actor_type: str, reason: Optional[str]) -> Optional[Dict[str, Any]]:
        prop = await self.repo.get_proposal(user_id, proposal_id)
        if not prop:
            return None
        if prop["status"] == ProposalStatus.ACCEPTED.value:
            # Idempotent: same proposal already accepted → no-op, return current.
            return prop
        if prop["status"] not in (ProposalStatus.PROPOSED.value,):
            return None

        # Verify decision + node still exist and belong to user.
        decision = await self.repo.get_decision(user_id, prop["decision_id"])
        node = await self.repo.get_node(user_id, prop["node_id"])
        if not decision or not node:
            await self.repo.update_proposal(user_id, proposal_id, {
                "status": ProposalStatus.EXPIRED.value,
                "expired_at": _now(),
                "expired_reason": "target_missing",
            })
            return None

        # Perform the link via LifeGraphService (the only external write).
        try:
            await self.life_graph.link_decision(user_id, prop["decision_id"], [prop["node_id"]])
        except Exception as e:
            logger.exception("link_decision failed during auto-link accept")
            await self.repo.update_proposal(user_id, proposal_id, {
                "status": ProposalStatus.EXPIRED.value,
                "expired_at": _now(),
                "expired_reason": f"link_failed:{type(e).__name__}",
            })
            return None

        updates = {
            "status": ProposalStatus.ACCEPTED.value,
            "accepted_at": _now(),
            "accepted_by": user_id,
            "accepted_by_user": actor_type == "user",
            "accepted_by_system": actor_type == "system",
            "acceptance_reason": (reason or "")[:256],
        }
        await self.repo.update_proposal(user_id, proposal_id, updates)
        return await self.repo.get_proposal(user_id, proposal_id)

    # ==================================================================
    # reject
    # ==================================================================
    async def reject(self, user_id: str, proposal_id: str, *, reason: Optional[str] = None) -> Optional[Dict[str, Any]]:
        prop = await self.repo.get_proposal(user_id, proposal_id)
        if not prop:
            return None
        if prop["status"] == ProposalStatus.REJECTED.value:
            return prop
        if prop["status"] != ProposalStatus.PROPOSED.value:
            return None
        updates = {
            "status": ProposalStatus.REJECTED.value,
            "rejected_at": _now(),
            "rejected_by": user_id,
            "rejected_by_user": True,
            "correction_reason": (reason or "")[:256],
            "previous_node_id": None,
        }
        await self.repo.update_proposal(user_id, proposal_id, updates)
        return await self.repo.get_proposal(user_id, proposal_id)

    # ==================================================================
    # helpers
    # ==================================================================
    @staticmethod
    def _min_node(c: Candidate) -> Dict[str, Any]:
        """Adapter: matcher strategies expect a dict shape."""
        return {"id": c.node_id, "type": c.node_type, "label": c.node_label}
