"""MEMORY router (AI-backed personal memory Q&A).

Iterazione 18.2 — wiring additivo con Knowledge Layer + Life Graph.

Comportamento retro-compatibile:
  * `POST /memory`        → insert in `db.memories` (invariato) +
                            crea life_node (type=generic, subtype=memory)
                            + attacca `notes`+`tags` via KnowledgeService.merge
  * `POST /memory/ask`    → contesto LLM = memories (invariato) UNITE ai
                            knowledge facts di nodi memoria (append-only).
  * `GET /memory`         → invariato, legge solo `db.memories`.

Se un passaggio (life-graph o knowledge) fallisce, il ricordo resta
comunque salvato in `db.memories`: il fallback preserva la funzionalità
originale e viene loggato per debug.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps import (
    db,
    get_current_user,
    knowledge,
    life_graph,
)
from llm import LLMNotConfigured, chat_completion

logger = logging.getLogger("ora.memory")

router = APIRouter(prefix="/memory", tags=["memory"])

# Attribute used to identify memory nodes inside the `generic` node-type
# vocabulary (we intentionally do NOT extend NodeType enum to avoid any
# schema/test regression; a memory node is a `generic` node with
# `attributes.subtype == "memory"`).
_MEMORY_SUBTYPE = "memory"
_MEMORY_LABEL_MAX = 60
_MEMORY_NOTES_MAX = 2000


class MemoryIn(BaseModel):
    content: str
    tags: Optional[List[str]] = None


class MemoryAskIn(BaseModel):
    question: str


def _short_label(text: str, limit: int = _MEMORY_LABEL_MAX) -> str:
    s = " ".join((text or "").split())
    if len(s) <= limit:
        return s or "Ricordo"
    return s[: limit - 1].rstrip() + "…"


def _clip(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


async def _mirror_to_graph(
    *,
    user_id: str,
    memory_id: str,
    content: str,
    tags: Optional[List[str]],
    created_at: str,
) -> Dict[str, Any]:
    """Best-effort mirror of a memory into Life Graph + Knowledge Layer.

    Never raises: exceptions are logged and returned inside the result so
    the calling endpoint can still respond 200 with the primary
    `db.memories` insert. Returns a dict with `node_id` (if created) and
    optional `error`.
    """
    label = _short_label(content)
    try:
        node = await life_graph.create_node(
            user_id,
            type="generic",
            label=label,
            description=None,
            attributes={
                "subtype": _MEMORY_SUBTYPE,
                "memory_id": memory_id,
                "source": "user_memory",
                "created_at": created_at,
            },
            origin="user_memory",
        )
    except Exception as e:
        logger.exception("memory mirror: life_graph.create_node failed")
        return {"node_id": None, "error": f"life_graph:{type(e).__name__}"}

    node_id = node["id"]
    try:
        await knowledge.merge(
            user_id,
            node_id,
            {
                "summary": label,
                "notes": _clip(content, _MEMORY_NOTES_MAX),
                "tags": list(tags or []),
            },
            source_type="user_memory",
            actor_type="user",
            actor_id=user_id,
            reason=f"memory:{memory_id}",
        )
    except Exception as e:
        logger.exception("memory mirror: knowledge.merge failed")
        return {"node_id": node_id, "error": f"knowledge:{type(e).__name__}"}

    return {"node_id": node_id, "error": None}


async def _list_knowledge_memory_facts(user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Return knowledge facts belonging to memory nodes for the user.

    Read-only, defensive: any failure returns an empty list so /ask
    behaves EXACTLY like before this iteration (zero regression).
    """
    try:
        cursor = db.life_nodes.find(
            {
                "user_id": user_id,
                "type": "generic",
                "attributes.subtype": _MEMORY_SUBTYPE,
                "status": "active",
            },
            {"_id": 0, "id": 1, "label": 1, "created_at": 1},
        ).sort("created_at", -1).limit(max(1, min(limit, 500)))
        nodes = await cursor.to_list(length=500)
    except Exception:
        logger.debug("memory ask: life_nodes query failed", exc_info=True)
        return []

    if not nodes:
        return []

    node_ids = [n["id"] for n in nodes]
    try:
        cursor = db.node_knowledge.find(
            {"user_id": user_id, "node_id": {"$in": node_ids}},
            {"_id": 0, "node_id": 1, "properties": 1, "updated_at": 1},
        )
        docs = await cursor.to_list(length=500)
    except Exception:
        logger.debug("memory ask: node_knowledge query failed", exc_info=True)
        return []

    facts: List[Dict[str, Any]] = []
    for d in docs:
        props = d.get("properties") or {}
        notes_env = props.get("notes") or {}
        notes_val = notes_env.get("value") if isinstance(notes_env, dict) else None
        summary_env = props.get("summary") or {}
        summary_val = summary_env.get("value") if isinstance(summary_env, dict) else None
        text = notes_val or summary_val
        if not text:
            continue
        facts.append({
            "node_id": d["node_id"],
            "text": str(text),
            "updated_at": d.get("updated_at"),
            "source": "knowledge_layer",
        })
    return facts


@router.post("")
async def add_memory(body: MemoryIn, user=Depends(get_current_user)):
    now_iso = datetime.now(timezone.utc).isoformat()
    memory_id = f"mem_{uuid.uuid4().hex[:12]}"
    doc = {
        "id": memory_id,
        "user_id": user["user_id"],
        "content": body.content,
        "tags": body.tags or [],
        "created_at": now_iso,
    }
    await db.memories.insert_one(doc)
    doc.pop("_id", None)

    # Additive wiring: mirror into Life Graph + Knowledge Layer. Never
    # blocks the response — if it fails, the memory is still saved.
    mirror = await _mirror_to_graph(
        user_id=user["user_id"],
        memory_id=memory_id,
        content=body.content,
        tags=body.tags,
        created_at=now_iso,
    )
    if mirror.get("node_id"):
        # Attach the graph node id back to the memory document so the
        # relationship is inspectable in db.memories too.
        try:
            await db.memories.update_one(
                {"id": memory_id, "user_id": user["user_id"]},
                {"$set": {
                    "life_node_id": mirror["node_id"],
                    "knowledge_synced": mirror.get("error") is None,
                }},
            )
            doc["life_node_id"] = mirror["node_id"]
            doc["knowledge_synced"] = mirror.get("error") is None
        except Exception:
            logger.debug("memory mirror: back-reference update failed", exc_info=True)

    return doc


@router.get("")
async def list_memory(user=Depends(get_current_user)):
    cursor = db.memories.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1)
    memories = await cursor.to_list(length=500)
    # Additive: la schermata Memoria vede anche i documenti (Iter19).
    # Ritorniamo la stessa forma sotto `items` (retrocompat) + un campo
    # `documents` con titolo/tipo/data/tag (nessun contenuto).
    try:
        cur2 = db.documents.find(
            {"user_id": user["user_id"], "deleted": {"$ne": True}, "archived": {"$ne": True}},
            {"_id": 0, "id": 1, "filename": 1, "mime_type": 1, "tags": 1, "created_at": 1},
        ).sort("created_at", -1).limit(200)
        docs = await cur2.to_list(length=200)
    except Exception:
        docs = []
    return {"items": memories, "documents": docs}


async def _list_user_documents(user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Return non-deleted documents owned by the user. Includes archived
    ones (marked explicitly) so ask can answer "quali documenti ho".
    Ownership check via `user_id` field. Never raises. From Iter20 the
    projection also returns `extracted_text` (truncated) so /ask can
    answer questions about document CONTENT.
    """
    try:
        cursor = db.documents.find(
            {"user_id": user_id, "deleted": {"$ne": True}},
            {
                "_id": 0, "id": 1, "filename": 1, "original_filename": 1,
                "mime_type": 1, "tags": 1, "notes": 1, "created_at": 1,
                "archived": 1, "extracted_text": 1, "pages": 1,
                "detected_language": 1, "text_extracted": 1, "ocr_used": 1,
            },
        ).sort("created_at", -1).limit(max(1, min(limit, 500)))
        return await cursor.to_list(length=500)
    except Exception:
        logger.debug("memory ask: documents query failed", exc_info=True)
        return []


@router.post("/ask")
async def ask_memory(body: MemoryAskIn, user=Depends(get_current_user)):
    # 1) Primary source: db.memories (behavior identical to previous iter).
    cursor = db.memories.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).limit(200)
    items = await cursor.to_list(length=200)

    # 2) Additive source: Knowledge Layer facts on memory-typed graph
    # nodes. Deduplicated by content against `items` to avoid double
    # feeding the LLM. If empty, prompt is unchanged from previous iter.
    kl_facts = await _list_knowledge_memory_facts(user["user_id"])
    seen_texts = {(m.get("content") or "").strip().lower() for m in items}
    extra_lines: List[str] = []
    for f in kl_facts:
        t = (f.get("text") or "").strip()
        if not t:
            continue
        if t.lower() in seen_texts:
            continue
        seen_texts.add(t.lower())
        extra_lines.append(f"- (knowledge) {t}")

    # 3) Additive source: Documents. Ownership already enforced by the
    # query filter. Soft-deleted docs are excluded; archived ones are
    # kept but tagged so the LLM can mention their status.
    documents = await _list_user_documents(user["user_id"])
    doc_lines: List[str] = []
    _DOC_TEXT_CTX_MAX = 2500  # per-doc excerpt cap fed to the LLM
    for d in documents:
        state = " (archiviato)" if d.get("archived") else ""
        parts = [
            f"- (documento{state}) {d.get('filename') or d.get('original_filename') or 'documento'}",
            f"tipo: {d.get('mime_type') or 'n/d'}",
            f"caricato: {(d.get('created_at') or '')[:10]}",
        ]
        if d.get("pages"):
            parts.append(f"pagine: {d['pages']}")
        if d.get("detected_language"):
            parts.append(f"lingua: {d['detected_language']}")
        if d.get("tags"):
            parts.append(f"tag: {', '.join(d['tags'])}")
        if d.get("notes"):
            parts.append(f"note: {d['notes'][:200]}")
        extracted = (d.get("extracted_text") or "").strip()
        if extracted:
            parts.append(f"contenuto: {extracted[:_DOC_TEXT_CTX_MAX]}")
        doc_lines.append(" | ".join(parts))

    if not items and not extra_lines and not doc_lines:
        return {
            "answer": (
                "Non ho ancora nulla salvato nella tua memoria. Aggiungi "
                "qualcosa dalla scheda Aggiungi e ti risponderò all'istante."
            ),
            "sources": [],
        }

    memory_block = "\n".join(
        [f"- ({m.get('created_at','')[:10]}) {m['content']}" for m in items]
    )
    parts_ctx: List[str] = []
    if memory_block:
        parts_ctx.append("Ricordi:\n" + memory_block)
    if extra_lines:
        parts_ctx.append("Knowledge:\n" + "\n".join(extra_lines))
    if doc_lines:
        parts_ctx.append(f"Documenti dell'utente ({len(documents)} totali):\n" + "\n".join(doc_lines))
    context_block = "\n\n".join(parts_ctx)

    system = (
        "Sei la memoria personale di ORA. "
        "Rispondi SOLO usando le informazioni fornite nel contesto. "
        "Il contesto può includere ricordi testuali, fatti di knowledge e "
        "documenti caricati dall'utente (con nome file, tipo, data, tag, note). "
        "Se la domanda riguarda documenti, cita esplicitamente i nomi file "
        "e usa 'Sì, hai caricato ...' oppure 'Non risultano documenti caricati.' "
        "Se la risposta non è presente, dì onestamente: 'Non risulta nella tua memoria.' "
        "Rispondi in italiano, breve e diretto. Max 3 frasi."
    )
    prompt = f"Contesto:\n{context_block}\n\nDomanda: {body.question}"
    try:
        answer = await chat_completion(
            system=system,
            user=prompt,
            session_id=f"mem-{user['user_id']}",
        )
    except LLMNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        logger.exception("AI memory failed")
        raise HTTPException(status_code=502, detail=f"AI non disponibile: {e}") from e

    # sources includes primary memories + additional knowledge facts +
    # documents (max 8 total, cap ensures the response stays lean).
    combined_sources: List[Dict[str, Any]] = list(items[:5])
    remaining = 8 - len(combined_sources)
    if remaining > 0:
        for f in kl_facts[: min(remaining, 3)]:
            combined_sources.append({
                "id": f["node_id"],
                "content": f["text"],
                "source": "knowledge_layer",
                "created_at": f.get("updated_at"),
            })
        remaining = 8 - len(combined_sources)
    if remaining > 0:
        for d in documents[:remaining]:
            combined_sources.append({
                "id": d["id"],
                "filename": d.get("filename"),
                "mime_type": d.get("mime_type"),
                "tags": d.get("tags") or [],
                "archived": bool(d.get("archived")),
                "source": "document",
                "created_at": d.get("created_at"),
            })
    return {"answer": answer, "sources": combined_sources}
