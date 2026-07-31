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

from emergentintegrations.llm.chat import LlmChat, UserMessage
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps import (
    EMERGENT_LLM_KEY,
    db,
    get_current_user,
    knowledge,
    life_graph,
)

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

    if not items and not extra_lines:
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
    parts: List[str] = []
    if memory_block:
        parts.append(memory_block)
    if extra_lines:
        parts.append("\n".join(extra_lines))
    context_block = "\n".join(parts)

    system = (
        "Sei la memoria personale di ORA. "
        "Rispondi SOLO usando le informazioni fornite nel contesto. "
        "Se la risposta non è presente, dì onestamente: 'Non risulta nella tua memoria.' "
        "Rispondi in italiano, breve e diretto. Max 2 frasi."
    )
    prompt = f"Contesto (memoria dell'utente):\n{context_block}\n\nDomanda: {body.question}"
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"mem-{user['user_id']}",
            system_message=system,
        ).with_model("openai", "gpt-5.2")
        result = await chat.send_message(UserMessage(text=prompt))
        answer = result if isinstance(result, str) else str(result)
    except Exception as e:
        logger.exception("AI memory failed")
        raise HTTPException(status_code=502, detail=f"AI non disponibile: {e}")

    # sources includes primary memories + additional knowledge facts (max 5 total).
    combined_sources: List[Dict[str, Any]] = list(items[:5])
    if len(combined_sources) < 5:
        for f in kl_facts[: 5 - len(combined_sources)]:
            combined_sources.append({
                "id": f["node_id"],
                "content": f["text"],
                "source": "knowledge_layer",
                "created_at": f.get("updated_at"),
            })
    return {"answer": answer, "sources": combined_sources}
