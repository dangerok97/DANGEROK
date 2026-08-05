"""Documents V2 search for study materials (title/subject/topic/keywords/Brain/education)."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ora.action_engine.study.documents")


async def search_study_documents(
    db,
    *,
    user_id: str,
    subject: Optional[str] = None,
    exam_name: Optional[str] = None,
    keywords: Optional[List[str]] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """Search Documents V2 for education materials matching subject/exam."""
    q_parts = [p for p in [subject, exam_name] if p]
    if keywords:
        q_parts.extend(keywords[:5])
    q = " ".join(q_parts).strip() or (exam_name or subject or "")

    items: List[dict] = []
    try:
        from deps import get_intelligence_service
        intel = get_intelligence_service()
        res = await intel.search(
            user_id=user_id,
            q=q or None,
            macro_category="education",
            limit=limit,
        )
        items = list(res.get("items") or [])
    except Exception as e:
        logger.info("intel search fallback: %s", type(e).__name__)
        items = await _fallback_search(db, user_id=user_id, q=q, limit=limit)

    # Also pull Brain-linked education docs if few results
    if len(items) < 3 and subject:
        extras = await _brain_linked_docs(db, user_id=user_id, subject=subject, limit=limit)
        seen = {d.get("id") for d in items}
        for d in extras:
            if d.get("id") not in seen:
                items.append(d)
                seen.add(d.get("id"))

    # Score & shape for UI chips
    shaped = [_shape(d, subject=subject, exam_name=exam_name) for d in items[:limit]]
    shaped.sort(key=lambda x: x.get("score") or 0, reverse=True)
    return {
        "ok": True,
        "query": q,
        "items": shaped,
        "total": len(shaped),
        "empty": len(shaped) == 0,
    }


async def _fallback_search(db, *, user_id: str, q: str, limit: int) -> List[dict]:
    query: Dict[str, Any] = {
        "user_id": user_id,
        "deleted": {"$ne": True},
        "$or": [
            {"analysis.macro_category": "education"},
            {"education_analysis": {"$exists": True}},
        ],
    }
    if q:
        import re
        tokens = [t for t in re.split(r"\s+", q.strip()) if t]
        fields = [
            "filename", "display_title", "user_title",
            "education_analysis.subject", "education_analysis.topic",
            "analysis.keywords", "analysis.suggested_title",
        ]
        if tokens:
            and_clauses = []
            for tok in tokens:
                rx = {"$regex": tok, "$options": "i"}
                and_clauses.append({"$or": [{f: rx} for f in fields]})
            query["$and"] = and_clauses
    cur = db.documents.find(query, {"_id": 0, "extracted_text": 0}).sort("updated_at", -1).limit(limit)
    return await cur.to_list(limit)


async def _brain_linked_docs(db, *, user_id: str, subject: str, limit: int) -> List[dict]:
    try:
        nodes = await db.life_nodes.find(
            {
                "user_id": user_id,
                "status": {"$ne": "deleted"},
                "$or": [
                    {"label": {"$regex": subject, "$options": "i"}},
                    {"attributes.subject": {"$regex": subject, "$options": "i"}},
                ],
            },
            {"_id": 0, "id": 1, "attributes": 1},
        ).limit(20).to_list(20)
        doc_ids = []
        for n in nodes:
            attrs = n.get("attributes") or {}
            for key in ("document_id", "source_id"):
                if attrs.get(key):
                    doc_ids.append(attrs[key])
        if not doc_ids:
            return []
        cur = db.documents.find(
            {"user_id": user_id, "id": {"$in": doc_ids}, "deleted": {"$ne": True}},
            {"_id": 0, "extracted_text": 0},
        ).limit(limit)
        return await cur.to_list(limit)
    except Exception:
        return []


def _shape(d: dict, *, subject: Optional[str], exam_name: Optional[str]) -> dict:
    edu = d.get("education_analysis") or {}
    analysis = d.get("analysis") or {}
    title = (
        d.get("user_title")
        or d.get("display_title")
        or edu.get("suggested_title")
        or edu.get("topic")
        or analysis.get("suggested_title")
        or d.get("filename")
        or "Documento"
    )
    score = 0.4
    blob = " ".join([
        str(title),
        str(edu.get("subject") or ""),
        str(edu.get("topic") or ""),
        " ".join(analysis.get("keywords") or []),
    ]).lower()
    for term in filter(None, [subject, exam_name]):
        if term.lower() in blob:
            score += 0.25
    if analysis.get("macro_category") == "education" or edu:
        score += 0.15
    return {
        "id": d.get("id"),
        "title": title,
        "subject": edu.get("subject"),
        "topic": edu.get("topic"),
        "macro_category": analysis.get("macro_category"),
        "has_flashcards": bool(d.get("flashcards")),
        "has_quiz": bool(d.get("quiz_session")),
        "score": min(1.0, score),
    }
