"""Minimal privacy-safe context for AI Document Understanding.

Assembles a compact JSON payload for Gemini: OCR text + metadata + estimated
category + known docs summary + Life Profile slice + Goals + Calendar summary
+ Brain summary + doc history. Never includes secrets, full dumps, passwords,
PIN/OTP, full IBAN, or payment-card data.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_SECRET_RE = re.compile(
    r"(?i)\b(password|passwd|pin|otp|cvv|cvc|iban|carta\s*di\s*credito|"
    r"credit\s*card|secret|token|api[_-]?key)\b"
)


def _scrub(value: Any, *, max_len: int = 200) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if _SECRET_RE.search(s):
        return "[omesso]"
    # Redact long digit sequences that look like IBAN/PAN
    s = re.sub(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b", "[iban-omesso]", s)
    s = re.sub(r"\b\d{12,19}\b", "[numero-omesso]", s)
    return s[:max_len]


def _profile_slice(profile: Optional[Dict[str, Any]], *, max_facts: int = 24) -> Dict[str, Any]:
    if not profile:
        return {}
    domains = profile.get("domains") or {}
    out: Dict[str, Any] = {}
    count = 0
    for dname, dom in domains.items():
        if count >= max_facts:
            break
        objects = (dom or {}).get("objects") or {}
        slim: Dict[str, Any] = {}
        for key, obj in objects.items():
            if count >= max_facts:
                break
            if not isinstance(obj, dict):
                continue
            status = obj.get("status") or "extracted"
            val = _scrub(obj.get("value"), max_len=120)
            if val is None:
                continue
            # Skip rejected; keep suggested/extracted/confirmed with status tag
            if status == "rejected":
                continue
            slim[key] = {"value": val, "status": status, "confidence": obj.get("confidence")}
            count += 1
        if slim:
            out[dname] = slim
    return out


def _goals_summary(goals: Optional[List[Dict[str, Any]]], *, limit: int = 5) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for g in (goals or [])[:limit]:
        title = _scrub(g.get("title") or g.get("name") or g.get("goal_type"), max_len=80)
        if not title:
            continue
        out.append({
            "title": title,
            "status": str(g.get("status") or "")[:40],
            "domain": str(g.get("domain") or g.get("area") or "")[:40],
        })
    return out


def _calendar_summary(events: Optional[List[Dict[str, Any]]], *, limit: int = 5) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for ev in (events or [])[:limit]:
        title = _scrub(ev.get("title"), max_len=80)
        if not title:
            continue
        out.append({
            "title": title,
            "start": str(ev.get("start_datetime") or "")[:40],
            "status": str(ev.get("status") or "")[:30],
        })
    return out


def _brain_summary(brain: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not brain:
        return {}
    return {
        "notes": _scrub(brain.get("notes") or brain.get("summary"), max_len=240) or "",
        "tags": [str(t)[:40] for t in (brain.get("tags") or [])[:8]],
        "doc_type": _scrub(brain.get("doc_type") or brain.get("category"), max_len=60) or "",
    }


def _known_docs_summary(docs: Optional[List[Dict[str, Any]]], *, limit: int = 8) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for d in (docs or [])[:limit]:
        lr = d.get("life_reasoning") or {}
        out.append({
            "id": str(d.get("id") or "")[:40],
            "filename": _scrub(d.get("original_filename") or d.get("filename"), max_len=80) or "",
            "type": str(lr.get("document_type") or (d.get("analysis") or {}).get("subcategory") or "")[:40],
            "title": _scrub(lr.get("title") or (d.get("analysis") or {}).get("suggested_title"), max_len=80) or "",
            "domain": str(lr.get("domain") or "")[:30],
        })
    return out


def _doc_history_summary(doc: Dict[str, Any]) -> Dict[str, Any]:
    telemetry = doc.get("life_reasoning_telemetry") or {}
    prev = doc.get("life_reasoning") or {}
    return {
        "prior_type": str(prev.get("document_type") or "")[:40],
        "prior_ai_used": bool(prev.get("ai_used")),
        "prior_confidence": prev.get("confidence"),
        "analysis_revision": prev.get("analysis_version"),
        "last_provider": str(telemetry.get("provider") or prev.get("provider") or "")[:40],
    }


async def assemble_document_context(
    doc: Dict[str, Any],
    *,
    user: Optional[Dict[str, Any]] = None,
    db: Any = None,
    doc_type_hint: Optional[str] = None,
    estimated_category: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the privacy-safe context dict sent to Gemini (metadata only + text)."""
    analysis = doc.get("analysis") or {}
    user_id = doc.get("user_id") or (user or {}).get("user_id")

    profile_public: Optional[Dict[str, Any]] = None
    goals: List[Dict[str, Any]] = []
    calendar: List[Dict[str, Any]] = []
    known_docs: List[Dict[str, Any]] = []
    brain: Optional[Dict[str, Any]] = None

    if db is not None and user_id:
        try:
            prof = await db.life_profiles.find_one({"user_id": user_id}, {"_id": 0})
            profile_public = prof
        except Exception:
            profile_public = None
        try:
            cursor = db.goals.find(
                {"user_id": user_id, "status": {"$nin": ["cancelled", "archived"]}},
                {"_id": 0, "title": 1, "name": 1, "status": 1, "domain": 1, "area": 1, "goal_type": 1},
            ).limit(5)
            goals = await cursor.to_list(length=5)
        except Exception:
            goals = []
        try:
            cursor = db.calendar_event_drafts.find(
                {"user_id": user_id, "status": {"$ne": "cancelled"}},
                {"_id": 0, "title": 1, "start_datetime": 1, "status": 1},
            ).sort("start_datetime", -1).limit(5)
            calendar = await cursor.to_list(length=5)
        except Exception:
            calendar = []
        try:
            cursor = db.documents.find(
                {"user_id": user_id, "id": {"$ne": doc.get("id")}},
                {
                    "_id": 0, "id": 1, "filename": 1, "original_filename": 1,
                    "analysis.suggested_title": 1, "analysis.subcategory": 1,
                    "life_reasoning.document_type": 1, "life_reasoning.title": 1,
                    "life_reasoning.domain": 1,
                },
            ).sort("updated_at", -1).limit(8)
            known_docs = await cursor.to_list(length=8)
        except Exception:
            known_docs = []
        try:
            node_id = doc.get("life_node_id")
            if node_id:
                brain = await db.life_nodes.find_one(
                    {"id": node_id, "user_id": user_id},
                    {"_id": 0, "notes": 1, "tags": 1, "doc_type": 1, "category": 1, "summary": 1},
                )
        except Exception:
            brain = None

    return {
        "document_type_hint": doc_type_hint,
        "estimated_category": estimated_category or analysis.get("macro_category"),
        "macro_category": analysis.get("macro_category"),
        "subcategory": analysis.get("subcategory"),
        "filename": _scrub(doc.get("original_filename") or doc.get("filename"), max_len=120),
        "language": doc.get("detected_language") or doc.get("language"),
        "life_profile": _profile_slice(profile_public),
        "goals": _goals_summary(goals),
        "calendar_summary": _calendar_summary(calendar),
        "brain_summary": _brain_summary(brain),
        "known_documents": _known_docs_summary(known_docs),
        "document_history": _doc_history_summary(doc),
        "privacy_note": (
            "Non inventare date/importi/scadenze assenti dal testo. "
            "Non riportare password, PIN, OTP, IBAN completi o dati carta."
        ),
    }
