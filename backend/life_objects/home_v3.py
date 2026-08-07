"""Home V3 card DTO — PREDISPOSTO, flag OFF. No frontend Home changes.

Internal serializer for future Life Object cards. Not used by current Home UX.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


def life_object_home_ui_enabled() -> bool:
    raw = (os.environ.get("LIFE_OBJECT_HOME_UI_ENABLED") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


_DOMAIN_BY_TYPE = {
    "HOME": "casa",
    "VEHICLE": "auto",
    "JOB": "lavoro",
    "UNIVERSITY": "studio",
    "COURSE": "studio",
    "TRAVEL": "viaggio",
    "FAMILY_MEMBER": "famiglia",
    "INSURANCE": "assicurazioni",
    "BANK_ACCOUNT": "finanze",
    "MORTGAGE": "casa",
    "UTILITY": "casa",
}


def _life_domain(obj: Dict[str, Any]) -> str:
    t = str(obj.get("type") or "").upper()
    return _DOMAIN_BY_TYPE.get(t) or str((obj.get("properties") or {}).get("domain") or "altro")


def _next_action(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    questions = obj.get("pending_questions") or []
    actions = obj.get("suggested_actions") or []
    if questions and isinstance(questions[0], dict) and questions[0].get("question"):
        return {
            "kind": "answer_question",
            "title": questions[0]["question"],
            "priority": questions[0].get("priority") or "medium",
        }
    if actions and isinstance(actions[0], dict) and actions[0].get("title"):
        return {
            "kind": actions[0].get("kind") or "suggested_action",
            "title": actions[0]["title"],
            "priority": actions[0].get("priority") or "medium",
        }
    return None


def _benefits(obj: Dict[str, Any]) -> List[str]:
    """What ORA can do better when this object is healthy — never invent facts."""
    t = str(obj.get("type") or "").upper()
    health = obj.get("health") or {}
    out: List[str] = []
    if t == "HOME":
        out.append("Unificare rogito, mutuo e bollette sulla stessa casa")
        if (obj.get("state") or {}).get("lender") or (obj.get("state") or {}).get("mortgage_assimilated"):
            out.append("Monitorare rata e impegno finanziario del mutuo")
        if (obj.get("state") or {}).get("utility_supplier") or (obj.get("state") or {}).get("supplier"):
            out.append("Seguire andamento utenze e cambi fornitore")
    elif t == "VEHICLE":
        out.append("Collegare libretto e polizza senza duplicati")
    elif t in ("UNIVERSITY", "COURSE"):
        out.append("Collegare esami e scadenze allo stesso percorso")
    elif t == "JOB":
        out.append("Tenere traccia del rapporto di lavoro da documenti reali")
    elif t == "TRAVEL":
        out.append("Agganciare prenotazioni e scadenze al viaggio")
    if health.get("score") is not None and float(health.get("score") or 0) < 0.5:
        out.append("Completare le informazioni mancanti per aumentare l'affidabilità")
    return out[:5]


def _timeline(obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    hist = obj.get("history") or []
    out: List[Dict[str, Any]] = []
    for h in hist[-20:]:
        if not isinstance(h, dict):
            continue
        out.append({
            "at": h.get("at"),
            "event": h.get("event"),
            "source": h.get("source"),
            "source_id": h.get("source_id"),
            "summary": (h.get("summary") or "")[:200],
        })
    return out


def to_home_v3_card(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Home V3 DTO — never branding 'Life Object' for end users."""
    health = obj.get("health") or {}
    narrative = obj.get("narrative") or {}
    insights = obj.get("insights") or []
    questions = obj.get("pending_questions") or []
    return {
        "life_object_id": obj.get("id"),
        "life_domain": _life_domain(obj),
        # Legacy compact fields (compat)
        "id": obj.get("id"),
        "type": obj.get("type"),
        "title": obj.get("title"),
        "status": obj.get("status"),
        "narrative": (narrative.get("text") or obj.get("ai_summary") or obj.get("summary") or "")[:280],
        "health": {
            "score": health.get("score"),
            "label": health.get("label"),
            "completeness": health.get("completeness"),
            "reliability": health.get("reliability"),
            "identity_completeness": health.get("identity_completeness"),
            "state_completeness": health.get("state_completeness"),
            "source_consistency": health.get("source_consistency"),
            "temporal_confidence": health.get("temporal_confidence"),
            "pending_conflicts": health.get("pending_conflicts"),
            "pending_links": health.get("pending_links"),
            "ai_confidence": health.get("ai_confidence"),
            "reasons": health.get("reasons") or [],
            "dimensions": health.get("dimensions") or {},
        },
        "next_action": _next_action(obj),
        "benefits": _benefits(obj),
        "questions": [
            {
                "question": q.get("question"),
                "why": q.get("why"),
                "priority": q.get("priority"),
                "category": q.get("category"),
            }
            for q in questions[:5]
            if isinstance(q, dict) and q.get("question")
        ],
        "insights": [
            {
                "kind": i.get("kind"),
                "title": i.get("title"),
                "detail": i.get("detail"),
                "confidence": i.get("confidence"),
            }
            for i in insights[:5]
            if isinstance(i, dict) and (i.get("title") or i.get("detail"))
        ],
        "timeline": _timeline(obj),
        "related_documents": list(obj.get("document_sources") or obj.get("documents") or []),
        "related_goals": list(obj.get("goal_sources") or obj.get("goals") or []),
        "related_projects": list(obj.get("projects") or []),
        # Digital Twin Knowledge Model — PREDISPOSTO (no Home UX change)
        "knowledge_summary": {
            "facts_count": len(obj.get("facts") or []),
            "hypotheses_count": len(obj.get("hypotheses") or []),
            "decisions_count": len(obj.get("decisions") or []),
            "memory_count": len(obj.get("memory") or []),
            "active_facts": [
                {"type": f.get("type"), "value": f.get("value"), "status": f.get("status")}
                for f in (obj.get("facts") or [])
                if isinstance(f, dict) and f.get("status") == "current" and f.get("active")
            ][:8],
            "active_hypotheses": [
                {"type": h.get("type"), "value": h.get("value"), "confidence": h.get("confidence")}
                for h in (obj.get("hypotheses") or [])
                if isinstance(h, dict) and h.get("status") == "active"
            ][:5],
        },
        # Compact legacy
        "top_insight": (insights[0].get("title") if insights and isinstance(insights[0], dict) else None),
        "pending_question": (
            questions[0].get("question") if questions and isinstance(questions[0], dict) else None
        ),
        "documents_count": len(obj.get("documents") or []),
        "total_sources": obj.get("total_sources") or obj.get("source_count") or 0,
        "updated_at": obj.get("updated_at"),
    }


def serialize_home_v3_feed(
    objects: List[Dict[str, Any]],
    *,
    force: bool = False,
) -> Optional[Dict[str, Any]]:
    """Return Home V3 feed only when flag ON (or force for tests). Default: disabled."""
    if not force and not life_object_home_ui_enabled():
        return {
            "enabled": False,
            "home_ui_enabled": False,
            "cards": [],
            "note": "Home V3 PREDISPOSTO — LIFE_OBJECT_HOME_UI_ENABLED=0",
        }
    cards = [to_home_v3_card(o) for o in objects]
    return {
        "enabled": True,
        "home_ui_enabled": True,
        "cards": cards,
        "count": len(cards),
    }
