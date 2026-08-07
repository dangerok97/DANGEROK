"""Decision store — remember outcomes; never re-propose never_ask_again."""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional, Set

from life_objects.knowledge_model.models import KnowledgeDecision, now_iso


def decision_fingerprint(title: str = "", reason: str = "", kind: str = "") -> str:
    raw = f"{kind}|{(title or '').strip().lower()}|{(reason or '').strip().lower()}"
    raw = re.sub(r"\s+", " ", raw)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def list_decisions(
    decisions: List[KnowledgeDecision],
    *,
    outcome: Optional[str] = None,
) -> List[KnowledgeDecision]:
    out: List[KnowledgeDecision] = []
    for d in decisions or []:
        if outcome and d.outcome != outcome:
            continue
        out.append(d)
    return out


def find_decision(
    decisions: List[KnowledgeDecision], decision_id: str,
) -> Optional[KnowledgeDecision]:
    for d in decisions or []:
        if d.decision_id == decision_id:
            return d
    return None


def never_ask_again_fingerprints(decisions: List[KnowledgeDecision]) -> Set[str]:
    return {
        d.fingerprint
        for d in (decisions or [])
        if d.outcome == "never_ask_again" and d.fingerprint
    }


def is_suppressed(
    decisions: List[KnowledgeDecision],
    *,
    title: str = "",
    reason: str = "",
    kind: str = "",
    fingerprint: Optional[str] = None,
) -> bool:
    fp = fingerprint or decision_fingerprint(title=title, reason=reason, kind=kind)
    blocked = never_ask_again_fingerprints(decisions)
    if fp in blocked:
        return True
    # Also match by normalized title against never_ask_again / rejected
    title_n = (title or "").strip().lower()
    if not title_n:
        return False
    for d in decisions or []:
        if d.outcome in ("never_ask_again", "rejected") and (d.title or "").strip().lower() == title_n:
            return True
    return False


def propose_decision(
    decisions: List[KnowledgeDecision],
    decision: KnowledgeDecision,
) -> Dict[str, Any]:
    """Add a decision unless suppressed by never_ask_again / rejected."""
    bag = list(decisions or [])
    if not decision.fingerprint:
        decision.fingerprint = decision_fingerprint(
            title=decision.title, reason=decision.reason, kind=decision.kind,
        )
    if is_suppressed(
        bag,
        title=decision.title,
        reason=decision.reason,
        kind=decision.kind,
        fingerprint=decision.fingerprint,
    ):
        return {"ok": True, "suppressed": True, "decisions": bag, "decision": None}
    # Dedupe pending same fingerprint
    for existing in bag:
        if existing.fingerprint == decision.fingerprint and existing.outcome == "pending":
            existing.updated_at = now_iso()
            return {"ok": True, "duplicate": True, "decision": existing, "decisions": bag}
    bag.append(decision)
    return {"ok": True, "created": True, "decision": decision, "decisions": bag}


def set_decision_outcome(
    decisions: List[KnowledgeDecision],
    decision_id: str,
    *,
    outcome: str,
    user_choice: Optional[str] = None,
) -> Dict[str, Any]:
    bag = list(decisions or [])
    d = find_decision(bag, decision_id)
    if d is None:
        return {"ok": False, "error": "decision_not_found"}
    d.outcome = outcome  # type: ignore[assignment]
    d.user_choice = user_choice
    d.updated_at = now_iso()
    if outcome == "never_ask_again" and not d.fingerprint:
        d.fingerprint = decision_fingerprint(title=d.title, reason=d.reason, kind=d.kind)
    return {"ok": True, "decision": d, "decisions": bag}


def filter_suppressed_suggestions(
    decisions: List[KnowledgeDecision],
    titles: List[str],
) -> List[str]:
    """Drop suggestion titles blocked by never_ask_again / rejected."""
    return [t for t in titles if not is_suppressed(decisions, title=t)]


def filter_suppressed_questions(
    decisions: List[KnowledgeDecision],
    questions: List[Any],
) -> List[Any]:
    """Quietly drop pending questions that match never_ask_again fingerprints."""
    out = []
    for q in questions or []:
        text = q.question if hasattr(q, "question") else (q.get("question") if isinstance(q, dict) else str(q))
        if is_suppressed(decisions, title=str(text or ""), kind="question"):
            continue
        out.append(q)
    return out


def serialize_decisions(decisions: List[KnowledgeDecision]) -> List[Dict[str, Any]]:
    return [d.model_dump() for d in (decisions or [])]
