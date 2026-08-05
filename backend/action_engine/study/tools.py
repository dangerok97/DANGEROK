"""Flashcards / Interrogami — link existing, generate new only on confirm, no dupes."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ora.action_engine.study.tools")


async def prepare_study_tools(
    *,
    user_id: str,
    document_ids: List[str],
    tools: List[str],
    db,
) -> Dict[str, Any]:
    """On confirm: link or generate flashcards/quiz grounded on selected docs."""
    result: Dict[str, Any] = {
        "flashcard_document_ids": [],
        "interrogami_document_ids": [],
        "actions": [],
        "blocked": [],
    }
    if not document_ids:
        if "flashcards" in tools or "interrogami" in tools or "exam_questions" in tools:
            result["blocked"].append({
                "kind": "no_documents",
                "message": "Nessun documento selezionato — strumenti saltati.",
            })
        return result

    try:
        from deps import get_intelligence_service
        intel = get_intelligence_service()
    except Exception as e:
        logger.info("intel unavailable: %s", type(e).__name__)
        result["blocked"].append({"kind": "intel_unavailable", "message": "Strumenti studio non disponibili ora."})
        return result

    for doc_id in document_ids:
        doc = await db.documents.find_one(
            {"id": doc_id, "user_id": user_id, "deleted": {"$ne": True}},
            {"_id": 0, "id": 1, "flashcards": 1, "quiz_session": 1},
        )
        if not doc:
            continue

        if "flashcards" in tools:
            existing = doc.get("flashcards") or []
            if existing:
                result["flashcard_document_ids"].append(doc_id)
                result["actions"].append({
                    "kind": "flashcards", "status": "linked", "document_id": doc_id,
                    "count": len(existing),
                })
            else:
                try:
                    res = await intel.study_action(
                        user_id=user_id, doc_id=doc_id, action="flashcards",
                    )
                    ok = bool(res)
                    result["flashcard_document_ids"].append(doc_id)
                    result["actions"].append({
                        "kind": "flashcards",
                        "status": "generated" if ok else "blocked",
                        "document_id": doc_id,
                    })
                except Exception as e:
                    logger.info("flashcards blocked: %s", type(e).__name__)
                    result["blocked"].append({
                        "kind": "flashcards", "document_id": doc_id,
                        "message": "Generazione flashcard non riuscita.",
                    })

        if "interrogami" in tools or "exam_questions" in tools:
            quiz = doc.get("quiz_session")
            if quiz and quiz.get("status") == "active":
                result["interrogami_document_ids"].append(doc_id)
                result["actions"].append({
                    "kind": "interrogami", "status": "linked", "document_id": doc_id,
                })
            else:
                try:
                    res = await intel.study_action(
                        user_id=user_id, doc_id=doc_id, action="quiz_start",
                    )
                    ok = bool(res)
                    result["interrogami_document_ids"].append(doc_id)
                    result["actions"].append({
                        "kind": "interrogami",
                        "status": "generated" if ok else "blocked",
                        "document_id": doc_id,
                    })
                except Exception as e:
                    logger.info("quiz blocked: %s", type(e).__name__)
                    result["blocked"].append({
                        "kind": "interrogami", "document_id": doc_id,
                        "message": "Interrogami non disponibile ora.",
                    })

    # Dedupe ids
    result["flashcard_document_ids"] = list(dict.fromkeys(result["flashcard_document_ids"]))
    result["interrogami_document_ids"] = list(dict.fromkeys(result["interrogami_document_ids"]))
    return result
