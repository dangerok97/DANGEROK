"""
Le porte della preparazione verso la persona.

    QUESTO È IL POSTO IN CUI ORA CHIEDE, E ASPETTA.

Quattro gesti e nient'altro: dire cosa si vuole, scegliere fra più contatti,
confermare un numero, rispondere a una domanda. Non c'è una porta che fa
partire una telefonata — quella resta dov'è sempre stata, e il sì su una
chiamata continua a essere un gesto a sé.

    E QUELLO CHE ESCE DA QUI È GIÀ IN ITALIANO.

Nessun endpoint restituisce lo stato interno: `as_a_card` traduce, e quello
che non si sa tradurre non esce. È la stessa disciplina della scheda delle
telefonate, per la stessa ragione — il giorno in cui uno stato tecnico finisce
davanti a una persona è perché qualcuno ha avuto fretta.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException

from deps import db, get_current_user

logger = logging.getLogger("ora.preparation.router")

router = APIRouter(prefix="/preparation", tags=["preparation"])


async def _mine(user: dict, preparation_id: str):
    from preparation.preparation import by_id

    prep = await by_id(db, user["user_id"], preparation_id)
    if prep is None:
        raise HTTPException(404, "questa preparazione non esiste")
    return prep


@router.post("/start")
async def start_one(
    payload: Dict[str, Any] = Body(...),
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    «Chiama Lorenzo e sposta il calcetto.»

    Apre il proposito e la preparazione insieme, cerca chi chiamare, guarda
    che cosa ORA sa già, e risponde con la prima cosa che serve sapere. Non
    squilla niente, e non può squillare niente da qui.
    """
    from autonomy.orchestrator import plan_a_request
    from preparation.service import as_a_card

    richiesta = str(payload.get("request") or "").strip()
    if not richiesta:
        raise HTTPException(400, "non mi hai detto cosa fare")

    plan, prep, perche = await plan_a_request(
        db,
        owner_id=user["user_id"],
        user_request=richiesta,
        counterparty=str(payload.get("counterparty") or ""),
        operation=str(payload.get("operation") or ""),
        goal=str(payload.get("goal") or ""),
    )
    if prep is None:
        raise HTTPException(400, perche or "non sono riuscita a preparare niente")
    return {
        "ok": True,
        "plan_id": plan.plan_id if plan is not None else "",
        "preparation": as_a_card(prep),
    }


@router.get("/{preparation_id}")
async def read_one(
    preparation_id: str, user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """A che punto è questa preparazione, come la legge una persona."""
    from preparation.service import as_a_card

    return {"ok": True, "preparation": as_a_card(await _mine(user, preparation_id))}


@router.post("/{preparation_id}/choose")
async def choose_one(
    preparation_id: str,
    payload: Dict[str, Any] = Body(default={}),
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Quale dei contatti trovati è quello giusto. Scegliere non è confermare."""
    from preparation.service import as_a_card, choose_contact

    prep = await _mine(user, preparation_id)
    prep, perche = await choose_contact(
        db, prep,
        number=str(payload.get("number") or ""),
        index=int(payload.get("index", -1)),
        operation=str(payload.get("operation") or ""),
    )
    if perche:
        raise HTTPException(400, perche)
    return {"ok": True, "preparation": as_a_card(prep)}


@router.post("/{preparation_id}/confirm-number")
async def confirm(
    preparation_id: str,
    payload: Dict[str, Any] = Body(default={}),
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Il sì o il no su un numero.

        È IL CANCELLO, E LO APRE SOLO UN GESTO ESPLICITO.

    Due porte scrivono la fiducia: questa, con un sì su un numero mostrato, e
    `set-contact-number`, con una frase che nomina insieme persona e numero.
    Nessun'altra — un permesso che si può concedere da un posto in più è un
    permesso che prima o poi qualcuno concede senza accorgersene.
    """
    from preparation.service import as_a_card, confirm_number

    prep = await _mine(user, preparation_id)
    prep, perche = await confirm_number(
        db, prep,
        yes=bool(payload.get("yes")),
        instead=str(payload.get("number") or ""),
        operation=str(payload.get("operation") or ""),
    )
    if perche:
        raise HTTPException(400, perche)
    await _tell_the_plan(prep)
    return {"ok": True, "preparation": as_a_card(prep)}


@router.post("/{preparation_id}/change-number")
async def change_it(
    preparation_id: str,
    payload: Dict[str, Any] = Body(default={}),
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    «Usa questo numero invece.» Il vecchio diventa vecchio, il nuovo aspetta.

    Non si ricomincia la missione: si cambia il numero e basta. Quello di
    prima non si cancella e non si ripropone; quello nuovo si usa solo dopo
    il suo sì — a meno che non fosse già confermato per la stessa persona.
    """
    from preparation.service import as_a_card, change_number

    prep = await _mine(user, preparation_id)
    prep, perche = await change_number(
        db, prep, number=str(payload.get("number") or ""),
        operation=str(payload.get("operation") or ""),
    )
    if perche:
        raise HTTPException(400, perche)
    await _tell_the_plan(prep)
    return {"ok": True, "preparation": as_a_card(prep)}


@router.post("/{preparation_id}/set-contact-number")
async def set_it(
    preparation_id: str,
    payload: Dict[str, Any] = Body(default={}),
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    «Il numero di Lorenzo è questo.» Detto per quella persona, vale già.

    È l'unica porta in cui un numero scritto da chi risponde diventa
    affidabile senza una seconda domanda, perché nomina insieme la persona e
    il numero. Il vecchio, se c'era, diventa vecchio.
    """
    from preparation.service import as_a_card, set_contact_number

    prep = await _mine(user, preparation_id)
    prep, perche = await set_contact_number(
        db, prep, number=str(payload.get("number") or ""),
        operation=str(payload.get("operation") or ""),
    )
    if perche:
        raise HTTPException(400, perche)
    await _tell_the_plan(prep)
    return {"ok": True, "preparation": as_a_card(prep)}


@router.post("/{preparation_id}/answer")
async def answer(
    preparation_id: str,
    payload: Dict[str, Any] = Body(default={}),
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """La risposta a quello che mancava. Una per volta, e poi si ricalcola."""
    from preparation.service import answer_question, as_a_card

    prep = await _mine(user, preparation_id)
    prep, perche = await answer_question(
        db, prep,
        field=str(payload.get("field") or ""),
        text=str(payload.get("text") or ""),
        operation=str(payload.get("operation") or ""),
    )
    if perche:
        raise HTTPException(400, perche)
    await _tell_the_plan(prep)
    return {"ok": True, "preparation": as_a_card(prep)}


@router.post("/{preparation_id}/prepare-call")
async def prepare_call(
    preparation_id: str,
    payload: Dict[str, Any] = Body(default={}),
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Trasforma la preparazione in una telefonata **preparata**.

        PREPARARE NON È CHIAMARE, E QUI NON CAMBIA.

    Quello che esce è una chiamata che aspetta ancora un sì esplicito su
    `/telephone/{id}/place`. Il cancello di questa porta ne chiede due — numero
    confermato e conversazione possibile — e senza entrambi risponde 409 e non
    prepara niente.
    """
    from preparation.service import as_a_card, turn_into_a_call

    prep = await _mine(user, preparation_id)
    call, perche = await turn_into_a_call(
        db, prep,
        operation=str(payload.get("operation") or "reschedule"),
        minutes=int(payload.get("minutes") or 5),
    )
    if call is None:
        #     NON È UN ERRORE DEL CHIAMANTE: È IL CANCELLO CHE FA IL SUO LAVORO.
        raise HTTPException(409, perche or "questa missione non è ancora pronta")
    return {
        "ok": True,
        "call_id": call.id,
        "preparation": as_a_card(prep),
        "nothing_has_happened_yet": True,
    }


@router.get("")
async def waiting(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Le preparazioni che aspettano una risposta da questa persona."""
    from preparation.preparation import waiting_for_you
    from preparation.service import as_a_card

    preps = await waiting_for_you(db, user["user_id"])
    return {
        "ok": True,
        "preparations": [as_a_card(p) for p in preps],
        "how_many": len(preps),
    }


async def _tell_the_plan(prep) -> None:
    """Il proposito racconta dove è arrivata la preparazione. Non solleva."""
    try:
        from autonomy.orchestrator import on_preparation_progress

        await on_preparation_progress(db, prep)
    except Exception as e:  # pragma: no cover
        logger.info("piano non aggiornato: %s", type(e).__name__)
