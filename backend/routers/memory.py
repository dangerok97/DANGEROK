"""MEMORY router (AI-backed personal memory Q&A)."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from emergentintegrations.llm.chat import LlmChat, UserMessage
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps import EMERGENT_LLM_KEY, db, get_current_user

logger = logging.getLogger("ora.memory")

router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryIn(BaseModel):
    content: str
    tags: Optional[List[str]] = None


class MemoryAskIn(BaseModel):
    question: str


@router.post("")
async def add_memory(body: MemoryIn, user=Depends(get_current_user)):
    doc = {
        "id": f"mem_{uuid.uuid4().hex[:12]}",
        "user_id": user["user_id"],
        "content": body.content,
        "tags": body.tags or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.memories.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("")
async def list_memory(user=Depends(get_current_user)):
    cursor = db.memories.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1)
    items = await cursor.to_list(length=500)
    return {"items": items}


@router.post("/ask")
async def ask_memory(body: MemoryAskIn, user=Depends(get_current_user)):
    cursor = db.memories.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).limit(200)
    items = await cursor.to_list(length=200)

    if not items:
        return {
            "answer": "Non ho ancora nulla salvato nella tua memoria. Aggiungi qualcosa dalla scheda Aggiungi e ti risponderò all'istante.",
            "sources": [],
        }

    context_block = "\n".join([f"- ({m.get('created_at','')[:10]}) {m['content']}" for m in items])
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

    return {"answer": answer, "sources": items[:5]}
