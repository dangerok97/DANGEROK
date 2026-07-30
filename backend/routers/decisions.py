"""DECISIONS router: canonical decision endpoints + AI resolve."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from emergentintegrations.llm.chat import LlmChat, UserMessage
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps import (
    EMERGENT_LLM_KEY,
    db,
    decisions,
    get_current_user,
    life_graph,
)

logger = logging.getLogger("ora.decisions")

router = APIRouter(prefix="/decisions", tags=["decisions"])


class DecisionIn(BaseModel):
    title: str
    description: Optional[str] = None
    category: Optional[str] = "generic"
    urgency: int = 5
    importance: int = 5
    risk: int = 3
    time_required_min: int = 15
    place: Optional[str] = None
    people: Optional[List[str]] = None
    energy: int = 3
    economic_impact: int = 3
    personal_impact: int = 5
    starts_at: Optional[str] = None
    deadline: Optional[str] = None
    linked_to: Optional[List[str]] = None
    node_ids: Optional[List[str]] = None
    metadata: Optional[dict] = None


async def create_decision_with_nodes(
    user_id: str,
    payload: Dict[str, Any],
    *,
    origin: str = "user",
) -> Dict[str, Any]:
    """Atomic composition:
      1. validate node ownership BEFORE insert (fast fail);
      2. create the Decision via DecisionService (repo does NOT touch node_ids);
      3. delegate the link to LifeGraphService.link_decision;
      4. on any link failure, roll back the decision to keep the DB consistent.
    """
    node_ids = list(dict.fromkeys(payload.pop("node_ids", None) or []))
    if node_ids:
        found = await db.life_nodes.count_documents({
            "user_id": user_id,
            "id": {"$in": node_ids},
            "status": "active",
        })
        if found != len(node_ids):
            raise HTTPException(status_code=400, detail="Uno o più nodi non appartengono all'utente o non sono attivi")

    doc = await decisions.create(user_id, payload, origin=origin)

    if not node_ids:
        return doc

    try:
        updated = await life_graph.link_decision(user_id, doc["id"], node_ids)
    except LookupError as e:
        await db.decisions.delete_one({"id": doc["id"], "user_id": user_id})
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        await db.decisions.delete_one({"id": doc["id"], "user_id": user_id})
        raise
    if updated is None:
        # Should never happen (we just inserted); guard anyway.
        await db.decisions.delete_one({"id": doc["id"], "user_id": user_id})
        raise HTTPException(status_code=500, detail="Impossibile collegare i nodi alla Decision")
    return updated


@router.get("")
async def list_decisions(user=Depends(get_current_user)):
    """All ranked decisions (any status)."""
    items = await decisions.ranked(user["user_id"])
    all_docs = await decisions.list_all(user["user_id"])
    ranked_ids = {d["id"] for d in items}
    tail = [d for d in all_docs if d["id"] not in ranked_ids]
    return {"items": items + tail}


@router.get("/top")
async def top_decisions(limit: int = 3, user=Depends(get_current_user)):
    limit = max(1, min(limit, 20))
    items = await decisions.top(user["user_id"], limit=limit)
    return {"items": items}


@router.get("/{decision_id}")
async def get_decision(decision_id: str, user=Depends(get_current_user)):
    d = await decisions.get(user["user_id"], decision_id)
    if not d:
        raise HTTPException(status_code=404, detail="Decision non trovata")
    return d


@router.post("")
async def create_decision(body: DecisionIn, user=Depends(get_current_user)):
    payload = body.model_dump()
    return await create_decision_with_nodes(user["user_id"], payload, origin="user")


@router.post("/{decision_id}/dismiss")
async def dismiss_decision(decision_id: str, user=Depends(get_current_user)):
    ok = await decisions.dismiss(user["user_id"], decision_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Decision non trovata")
    return {"ok": True}


@router.post("/{decision_id}/complete")
async def complete_decision(decision_id: str, user=Depends(get_current_user)):
    ok = await decisions.complete(user["user_id"], decision_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Decision non trovata")
    return {"ok": True}


@router.post("/{decision_id}/resolve")
async def resolve_decision(decision_id: str, user=Depends(get_current_user)):
    d = await decisions.get(user["user_id"], decision_id)
    if not d:
        raise HTTPException(status_code=404, detail="Decision non trovata")

    system = (
        "Sei ORA, un sistema operativo della vita quotidiana. "
        "Il tuo compito è ridurre il carico mentale dell'utente. "
        "Data una situazione, proponi UNA soluzione concreta, immediata, azionabile. "
        "Rispondi SEMPRE in italiano. Formato risposta:\n"
        "1) Una frase che dice esattamente cosa fare adesso (max 15 parole).\n"
        "2) 2-3 passi pratici, numerati, senza fronzoli.\n"
        "3) Se serve, un'app da aprire (es: Google Maps, WhatsApp, home banking).\n"
        "Nessun preambolo. Nessuna scusa. Nessuna domanda. Sii diretto."
    )
    prompt = (
        f"Situazione: {d['title']}\n"
        f"Contesto: {d.get('description') or '-'}\n"
        f"Categoria: {d.get('category')}\n"
        f"Deadline: {d.get('deadline') or '-'}\n"
        f"Inizio: {d.get('starts_at') or '-'}\n"
        f"Persone: {', '.join(d.get('people') or []) or '-'}\n"
        f"Dati: {d.get('metadata') or {}}"
    )
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"resolve-{decision_id}",
            system_message=system,
        ).with_model("openai", "gpt-5.2")
        result = await chat.send_message(UserMessage(text=prompt))
        solution = result if isinstance(result, str) else str(result)
    except Exception as e:
        logger.exception("AI resolve failed")
        raise HTTPException(status_code=502, detail=f"AI non disponibile: {e}")

    await decisions.attach_resolution(user["user_id"], decision_id, solution)
    return {"solution": solution, "decision_id": decision_id, "task_id": decision_id}
