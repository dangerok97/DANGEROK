"""
Le porte dei propositi verso la persona.

    UN CICLO CHE NESSUNO VEDE NON È UN CICLO: È UN PROCESSO.

La differenza sta tutta in questa manciata di endpoint. Finché quello che ORA
sta facendo vive solo in un database, una persona può soltanto fidarsi; da qui
in poi può guardare — che cosa ha in mano, a che punto è, che cosa aspetta da
lei, e che cosa è finito male.

Non c'è una porta che fa partire un piano. Il sì passa da dove è sempre
passato — `/telephone/{id}/place` per le telefonate — perché un secondo
percorso per dire di sì sarebbe un secondo posto in cui dimenticarsi di
chiederlo.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException

from deps import db, get_current_user

logger = logging.getLogger("ora.autonomy.router")

router = APIRouter(prefix="/autonomy", tags=["autonomy"])


@router.get("/plans")
async def plans(
    only_open: bool = True, user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Quello che ORA ha in mano, come lo legge chi l'ha chiesto.

    Di default solo quello che è ancora in giro: un elenco che comincia dai
    propositi finiti settimane fa risponde a una domanda che nessuno ha fatto.
    """
    from autonomy.plan import open_plans, recent
    from autonomy.presentation import as_a_card

    uid = user["user_id"]
    piani = await (open_plans(db, uid) if only_open else recent(db, uid))
    schede = [as_a_card(p) for p in piani]
    return {
        "ok": True,
        "plans": schede,
        "how_many": len(schede),
        #     QUANTI ASPETTANO TE È LA SOLA COSA CHE SI GUARDA DI FRETTA.
        "waiting_for_you": sum(1 for s in schede if s["needs_you"]),
    }


@router.get("/plans/{plan_id}")
async def plan_detail(
    plan_id: str, user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Un proposito per intero, con la sua storia in italiano."""
    from autonomy.plan import by_id
    from autonomy.presentation import in_full, what_you_can_answer

    plan = await by_id(db, user["user_id"], plan_id)
    if plan is None:
        raise HTTPException(404, "questo proposito non esiste")
    return {
        "ok": True,
        "plan": in_full(plan),
        "you_can_answer": what_you_can_answer(plan),
    }


@router.post("/plans/{plan_id}/cancel")
async def cancel_plan(
    plan_id: str,
    payload: Dict[str, Any] = Body(default={}),
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Lascia perdere un proposito.

        FERMARE NON È DISFARE.

    Un piano fermato smette di andare avanti; non torna indietro su quello che
    ha già fatto. Se la telefonata è partita è partita, e se il calendario è
    già cambiato resta cambiato — annullare una cosa fatta è un'altra
    operazione, con la sua autorità, e non si nasconde dentro un pulsante che
    dice «lascia perdere».
    """
    from autonomy.orchestrator import cancel
    from autonomy.plan import by_id
    from autonomy.presentation import as_a_card

    plan = await by_id(db, user["user_id"], plan_id)
    if plan is None:
        raise HTTPException(404, "questo proposito non esiste")
    if not plan.is_open():
        #     GIÀ CHIUSO NON È UN ERRORE: È LA RISPOSTA.
        return {"ok": True, "plan": as_a_card(plan), "already_closed": True}

    plan = await cancel(
        db, plan, why=str(payload.get("why") or "")[:200] or "Hai detto di lasciar perdere.",
    )
    return {"ok": True, "plan": as_a_card(plan), "already_closed": False}
