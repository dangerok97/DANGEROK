"""Hypothesis store — ORA beliefs that are NOT Facts until confirmed."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from life_objects.knowledge_model.facts import add_fact
from life_objects.knowledge_model.models import (
    KnowledgeFact,
    KnowledgeHypothesis,
    now_iso,
)


def list_hypotheses(
    hypotheses: List[KnowledgeHypothesis],
    *,
    status: Optional[str] = None,
    hyp_type: Optional[str] = None,
) -> List[KnowledgeHypothesis]:
    out: List[KnowledgeHypothesis] = []
    for h in hypotheses or []:
        if status and h.status != status:
            continue
        if hyp_type and h.type != hyp_type:
            continue
        out.append(h)
    return out


def find_hypothesis(
    hypotheses: List[KnowledgeHypothesis], hypothesis_id: str,
) -> Optional[KnowledgeHypothesis]:
    for h in hypotheses or []:
        if h.id == hypothesis_id:
            return h
    return None


def add_hypothesis(
    hypotheses: List[KnowledgeHypothesis],
    hyp: KnowledgeHypothesis,
    *,
    dedupe: bool = True,
) -> List[KnowledgeHypothesis]:
    bag = list(hypotheses or [])
    if dedupe and hyp.type:
        for existing in bag:
            if (
                existing.status == "active"
                and existing.type == hyp.type
                and _values_equal(existing.value, hyp.value)
            ):
                existing.confidence = max(
                    float(existing.confidence or 0), float(hyp.confidence or 0),
                )
                existing.updated_at = now_iso()
                if hyp.evidence:
                    ev = list(existing.evidence or [])
                    for e in hyp.evidence:
                        if e not in ev:
                            ev.append(e)
                    existing.evidence = ev
                return bag
    bag.append(hyp)
    return bag


def confirm_hypothesis(
    *,
    hypotheses: List[KnowledgeHypothesis],
    facts: List[KnowledgeFact],
    hypothesis_id: str,
    verified_by: str = "user",
    life_object_id: Optional[str] = None,
) -> Dict[str, Any]:
    """User/system confirms → create Fact (supersede if needed). Never auto."""
    bag_h = list(hypotheses or [])
    bag_f = list(facts or [])
    hyp = find_hypothesis(bag_h, hypothesis_id)
    if hyp is None:
        return {"ok": False, "error": "hypothesis_not_found"}
    if hyp.status == "rejected":
        return {"ok": False, "error": "hypothesis_rejected"}
    if hyp.status == "confirmed" and hyp.confirmed_fact_id:
        return {
            "ok": True,
            "already_confirmed": True,
            "fact_id": hyp.confirmed_fact_id,
            "hypotheses": bag_h,
            "facts": bag_f,
        }

    fact = KnowledgeFact(
        type=hyp.type,
        value=hyp.value,
        source="user" if verified_by == "user" else hyp.source or "manual",
        source_id=hyp.source_id,
        confidence=max(float(hyp.confidence or 0.5), 0.9),
        verified=True,
        verified_by=verified_by,
        verified_at=now_iso(),
        origin="hypothesis_confirm",
        explanation=hyp.reason or "Confermato dall'utente",
        ai_summary=hyp.question_to_confirm or "",
        life_object_id=life_object_id or hyp.life_object_id,
        status="current",
        active=True,
    )
    bag_f = add_fact(bag_f, fact, supersede_same_type=True)
    hyp.status = "confirmed"
    hyp.confirmed_fact_id = fact.id
    hyp.updated_at = now_iso()
    return {
        "ok": True,
        "fact": fact,
        "hypothesis": hyp,
        "hypotheses": bag_h,
        "facts": bag_f,
    }


def reject_hypothesis(
    hypotheses: List[KnowledgeHypothesis],
    hypothesis_id: str,
    *,
    reason: str = "",
) -> Dict[str, Any]:
    bag = list(hypotheses or [])
    hyp = find_hypothesis(bag, hypothesis_id)
    if hyp is None:
        return {"ok": False, "error": "hypothesis_not_found"}
    hyp.status = "rejected"
    hyp.updated_at = now_iso()
    if reason:
        hyp.reason = (hyp.reason + " | rejected: " + reason).strip(" |")
    return {"ok": True, "hypothesis": hyp, "hypotheses": bag}


def expire_hypothesis(
    hypotheses: List[KnowledgeHypothesis], hypothesis_id: str,
) -> List[KnowledgeHypothesis]:
    bag = list(hypotheses or [])
    hyp = find_hypothesis(bag, hypothesis_id)
    if hyp and hyp.status == "active":
        hyp.status = "expired"
        hyp.updated_at = now_iso()
    return bag


def _values_equal(a: Any, b: Any) -> bool:
    if a is None and b is None:
        return True
    return str(a).strip().lower() == str(b).strip().lower()


def serialize_hypotheses(hypotheses: List[KnowledgeHypothesis]) -> List[Dict[str, Any]]:
    return [h.model_dump() for h in (hypotheses or [])]
