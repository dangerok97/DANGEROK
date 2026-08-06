"""Normalize AI-recommended document actions for Documents V2 / Life Experience.

Actions come primarily from AI reasoning (motivo, beneficio, confidence,
origine, documento, spiegazione). Regex/admin extraction is assist-only
fallback when AI did not propose actions.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _from_recommended(reasoning: Dict[str, Any], document_id: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for a in reasoning.get("recommended_actions") or []:
        if not isinstance(a, dict):
            continue
        title = (a.get("title") or "").strip()
        if not title:
            continue
        out.append({
            "action_type": a.get("action_type") or "generic_action",
            "title": title[:160],
            "description": (a.get("description") or a.get("spiegazione") or "")[:400],
            "motivo": (a.get("motivo") or a.get("reason") or "")[:240],
            "beneficio": (a.get("beneficio") or a.get("benefit") or "")[:240],
            "confidence": float(a.get("confidence") if a.get("confidence") is not None else reasoning.get("confidence") or 0.5),
            "origine": a.get("origine") or ("ai" if reasoning.get("ai_used") else "local"),
            "documento": a.get("documento") or document_id,
            "spiegazione": (a.get("spiegazione") or a.get("description") or "")[:400],
            "requires_consent": bool(a.get("requires_consent", True)),
            "requires_confirmation": bool(a.get("requires_consent", True)),
            "priority": a.get("priority") or reasoning.get("priority") or "medium",
        })
    return out


def _fallback_from_admin(doc: Dict[str, Any], reasoning: Dict[str, Any]) -> List[Dict[str, Any]]:
    admin = doc.get("admin_analysis") or {}
    if not (admin.get("due_date") or admin.get("amount")):
        return []
    sender = admin.get("sender") or ""
    doc_type = reasoning.get("document_type") or ""
    if doc_type == "bolletta" or "bolletta" in (reasoning.get("title") or "").lower():
        title = f"Promemoria pagamento bolletta{(' ' + sender) if sender else ''}".strip()
    elif doc_type == "mutuo":
        title = f"Promemoria rata mutuo{(' ' + sender) if sender else ''}".strip()
    else:
        title = "Promemoria scadenza documento"
    return [{
        "action_type": "draft_calendar_event",
        "title": title[:160],
        "description": (admin.get("simple_explanation") or "")[:400],
        "motivo": "Scadenza o importo rilevati dal documento",
        "beneficio": "Non dimenticare il pagamento / adempimento",
        "confidence": float(admin.get("confidence") or 0.45),
        "origine": "local-assist",
        "documento": doc.get("id") or "",
        "spiegazione": "Analisi locale (AI non disponibile o senza azioni proposte).",
        "requires_consent": True,
        "requires_confirmation": True,
        "priority": "high",
    }]


def build_document_actions(
    *,
    doc: Dict[str, Any],
    reasoning: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """AI-first action list for Life Experience «Cosa posso fare»."""
    document_id = doc.get("id") or reasoning.get("document_id") or ""
    actions = _from_recommended(reasoning, document_id)
    if not actions:
        actions = _fallback_from_admin(doc, reasoning)
    # Deduplicate by title
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for a in actions:
        key = (a.get("action_type"), (a.get("title") or "").lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(a)
    return deduped[:12]
