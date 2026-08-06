"""Persist document understanding into Brain + Knowledge (best-effort, no dupes).

Life Profile updates stay in ``life_setup.service.consume_document`` via
``document_mapping`` — this module handles Brain/Knowledge side-effects only,
always scoped by ``user_id``.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("ora.documents.document_memory")


def _memory_fingerprint(reasoning: Dict[str, Any]) -> str:
    return "|".join([
        str(reasoning.get("document_type") or ""),
        str(reasoning.get("content_hash") or "")[:32],
        str(reasoning.get("title") or "")[:80],
        str(reasoning.get("confidence") or ""),
    ])


async def persist_document_understanding(
    *,
    db: Any,
    user_id: str,
    doc: Dict[str, Any],
    reasoning: Dict[str, Any],
    knowledge: Any = None,
) -> Dict[str, Any]:
    """Best-effort write of understanding into life_nodes / knowledge.

    Returns a small telemetry dict (no content). Never raises to the caller.
    """
    result = {"brain": False, "knowledge": False, "skipped_duplicate": False}
    try:
        fp = _memory_fingerprint(reasoning)
        prev_fp = (doc.get("life_reasoning_memory") or {}).get("fingerprint")
        if prev_fp and prev_fp == fp:
            result["skipped_duplicate"] = True
            return result

        node_id = doc.get("life_node_id")
        summary = (reasoning.get("summary") or reasoning.get("purpose") or "")[:1000]
        tags = []
        for e in (reasoning.get("entities") or [])[:10]:
            v = e.get("value")
            if v:
                tags.append(str(v)[:40])
        for kw in (reasoning.get("knowledge") or {}).get("keywords") or []:
            tags.append(str(kw)[:40])
        tags = list(dict.fromkeys(tags))[:20]

        patch = {
            "doc_type": reasoning.get("document_type"),
            "category": reasoning.get("domain"),
            "notes": summary,
            "tags": tags,
            "life_understanding": {
                "document_type": reasoning.get("document_type"),
                "title": reasoning.get("title"),
                "benefit": reasoning.get("benefit"),
                "priority": reasoning.get("priority"),
                "criticality": reasoning.get("criticality"),
                "confidence": reasoning.get("confidence"),
                "ai_used": reasoning.get("ai_used"),
                "reason_summary": (reasoning.get("reason_summary") or "")[:300],
            },
        }

        if knowledge is not None and node_id:
            try:
                await knowledge.merge(
                    user_id,
                    node_id,
                    patch,
                    source_type="document_understanding",
                    actor_type="system",
                    actor_id="ora.documents.reasoner",
                    reason=f"life_reasoning:{doc.get('id')}",
                )
                result["knowledge"] = True
            except Exception:
                logger.debug("knowledge merge skipped", exc_info=True)

        if node_id and db is not None:
            try:
                await db.life_nodes.update_one(
                    {"id": node_id, "user_id": user_id},
                    {"$set": {
                        "notes": summary,
                        "tags": tags,
                        "doc_type": reasoning.get("document_type"),
                        "category": reasoning.get("domain"),
                        "updated_at": reasoning.get("created_at"),
                    }},
                    upsert=False,
                )
                result["brain"] = True
            except Exception:
                logger.debug("brain node update skipped", exc_info=True)

        if db is not None and doc.get("id"):
            await db.documents.update_one(
                {"id": doc["id"], "user_id": user_id},
                {"$set": {"life_reasoning_memory": {
                    "fingerprint": fp,
                    "brain": result["brain"],
                    "knowledge": result["knowledge"],
                }}},
            )
    except Exception:
        logger.warning("persist_document_understanding failed (best-effort)", exc_info=True)
    return result
