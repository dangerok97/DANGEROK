"""
Le porte della telefonata verso la persona.

    PREPARARE E CHIAMARE SONO DUE MOMENTI.

`prepare` scrive cosa ORA direbbe e a chi; `place` compone il numero. Fra i
due c'è una persona che legge e dice di sì. Un solo endpoint che prepara e
chiama avrebbe reso quel sì un dettaglio implementativo — e il sì non è un
attrito da ridurre: è il punto.

Tutto qui sta dietro l'autenticazione di sempre. Le porte che l'operatore
telefonico usa sono un'altra cosa e stanno altrove, fuori da `/api`.

Quale sia l'operatore, qui, non si vede: sta tutto in `carrier`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException

from deps import db, get_current_user
from telephone import carrier
from telephone.models import Mandate
from telephone.service import TelephoneService

logger = logging.getLogger("ora.telephone.router")

router = APIRouter(prefix="/telephone", tags=["telephone"])


# ---------------------------------------------------------------------------
# Verso la persona
# ---------------------------------------------------------------------------

@router.get("/available")
async def available(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Se ORA può telefonare, e cosa manca quando non può."""
    return await TelephoneService(db).may_i_call(user["user_id"])


@router.post("/prepare")
async def prepare(
    payload: Dict[str, Any] = Body(...),
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Scrive la telefonata che ORA farebbe: a chi, perché, cosa può accettare.

    Non squilla niente. Quello che torna è fatto per essere letto da una
    persona prima di dire di sì.
    """
    try:
        mandate = Mandate.model_validate(payload.get("mandate") or {})
    except Exception as e:
        raise HTTPException(400, f"mandato non valido: {type(e).__name__}")

    service = TelephoneService(db)
    call = await service.prepare(
        user["user_id"],
        to_number=str(payload.get("to_number") or ""),
        calling_whom=str(payload.get("calling_whom") or ""),
        mandate=mandate,
        session_ref=str(payload.get("session_id") or ""),
    )
    if not call.to_number:
        raise HTTPException(
            400, "numero non italiano: questo pilota chiama solo numeri nazionali"
        )

    from telephone.briefing import disclosure

    return {
        "ok": True,
        "call_id": call.id,
        "chiamerei": call.calling_whom or call.to_number,
        "numero": call.to_number,
        "direi_per_prima_cosa": disclosure(
            user.get("name") or ""
        ),
        "perche": mandate.why_calling,
        "posso_accettare": mandate.may_agree_to,
        "riporterei_indietro": mandate.must_bring_back,
        "durata_massima_minuti": mandate.minutes,
    }


@router.post("/{call_id}/place")
async def place(
    call_id: str,
    payload: Dict[str, Any] = Body(default={}),
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Compone il numero, dopo un sì esplicito su *questa* chiamata.

        UNA TELEFONATA NON PARTE MAI DA SOLA.

    `phone.call` sta fra le capacità che non partono da sole, e un permesso
    generale non basta: serve il sì su questa chiamata, con questo mandato,
    verso questo numero.
    """
    service = TelephoneService(db)
    call = await service.get(user["user_id"], call_id)
    if call is None:
        raise HTTPException(404, "chiamata sconosciuta")
    if call.state != "authorised":
        raise HTTPException(409, f"questa chiamata è già {call.state}")

    if not bool(payload.get("confirmed")):
        raise HTTPException(428, "serve un sì esplicito su questa chiamata")

    permission = await service.may_i_call(user["user_id"])
    if permission["denied"]:
        raise HTTPException(403, "aveva già detto di no alle telefonate")
    if not permission["provider_ready"]:
        raise HTTPException(503, permission["why_not"] or "non c'è modo di telefonare")

    opened = await carrier.place(
        to_number=call.to_number,
        call_id=call.id,
        minutes=call.mandate.minutes,
    )
    if opened is None or not opened.get("call_ref"):
        await service.mark(call, "failed", how_it_ended="failed")
        # Quello che ha detto l'operatore, per intero: chi legge deve poter
        # capire cosa sistemare, non solo che è andata male.
        why = (opened or {}).get("error") or "l'operatore non ha risposto"
        raise HTTPException(502, f"la chiamata non è partita — {why}")

    call = await service.mark(
        call, "dialling",
        provider_ref=opened["call_ref"],
        authority_ref=str(payload.get("authority_ref") or "explicit_yes")[:64],
    )
    return {"ok": True, "call_id": call.id, "state": call.state}


@router.post("/{call_id}/hangup")
async def hangup(
    call_id: str, user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Chiude una chiamata in corso.

    Esiste perché una persona che ha autorizzato una telefonata deve poterla
    fermare mentre succede, senza dover spegnere il server.
    """
    service = TelephoneService(db)
    call = await service.get(user["user_id"], call_id)
    if call is None:
        raise HTTPException(404, "chiamata sconosciuta")
    closed = await carrier.hang_up(call.provider_ref)
    if closed:
        await service.mark(call, "ended", how_it_ended="we_hung_up")
    return {"ok": True, "closed": closed, "state": call.state}


#     QUESTE TRE STANNO SOPRA `/{call_id}`, E NON E' UNA QUESTIONE DI ORDINE
#     ESTETICO: `/{call_id}` COMBACIA ANCHE CON LA PAROLA «calls».

@router.get("/calls")
async def call_history(
    limit: int = 20,
    offset: int = 0,
    status: str = "",
    days: int = 0,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Le telefonate fatte da ORA, le piu' recenti per prime.

        QUESTA NON E' UNA CONSOLE. E' IL RESOCONTO DI UNA COMMISSIONE.

    Esce solo quello che serve a capire com'e andata: chi, quando, quanto, e
    l'esito in una riga. Niente identificativi dell'operatore, niente nomi di
    modelli, niente token.
    """
    from telephone.application import applications_for
    from telephone.history import as_a_card

    service = TelephoneService(db)
    chiamate, in_tutto = await service.recent(
        user["user_id"], limit=limit, offset=offset, status=status, days=days,
    )
    #     LA RIGA DEVE POTER DIRE SE IL CALENDARIO E' CAMBIATO DAVVERO.
    # Senza questo, «Appuntamento spostato alle 18:00» sarebbe la stessa frase
    # sia quando lo e' sia quando ORA non ce l'ha fatta — e la persona si
    # fiderebbe di un calendario rimasto alle sedici.
    applicazioni = await applications_for(db, [c.id for c in chiamate])
    return {
        "ok": True,
        "calls": [as_a_card(c, applicazioni.get(c.id)) for c in chiamate],
        # Quante sono in tutto, per poter dire «mostrati dieci di quarantadue»
        # invece di lasciare qualcuno a indovinare se ce ne sono altre.
        "total": in_tutto,
        "offset": max(0, int(offset)),
        "limit": max(1, min(int(limit), 100)),
    }


@router.get("/calls/{call_id}")
async def call_detail(
    call_id: str, user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Una telefonata aperta, col numero che e' stato davvero composto."""
    from telephone.application import application_for
    from telephone.history import in_full

    service = TelephoneService(db)
    call = await service.get(user["user_id"], call_id)
    if call is None:
        raise HTTPException(404, "chiamata sconosciuta")
    from telephone.continuation import as_a_question, continuation_for

    scheda = in_full(
        call,
        kept_the_mandate=service.kept_the_mandate(call),
        application=await application_for(db, call.id),
    )
    #     SE LA COMMISSIONE E' FERMA, LA DOMANDA STA QUI.
    # E' la pagina che qualcuno apre dopo aver letto «serve una tua decisione»:
    # la decisione deve poterla prendere da qui, non da un altro posto.
    ferma = await continuation_for(db, call.id)
    if ferma is not None:
        scheda["continuation"] = as_a_question(ferma)
    return {"ok": True, "call": scheda}


@router.get("/continuations")
async def waiting_decisions(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Le commissioni ferme che aspettano una risposta.

        UNA DOMANDA CHE NESSUNO VEDE NON E' UNA DOMANDA.

    Leggerle le segna come mostrate: da quel momento, se restano senza
    risposta, e' perche' nessuno ha risposto — non perche' nessuno ha chiesto.
    """
    from telephone.continuation import as_a_question, mark_shown, waiting_for

    ferme = await waiting_for(db, user["user_id"])
    fuori = []
    for c in ferme:
        fuori.append(as_a_question(await mark_shown(db, c)))
    return {"ok": True, "waiting": fuori, "how_many": len(fuori)}


@router.post("/continuations/{continuation_id}/decide")
async def decide_continuation(
    continuation_id: str,
    payload: Dict[str, Any] = Body(default={}),
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    La risposta di chi aveva chiesto la telefonata.

        LA DECISIONE E' L'AUTORITA'. LA TELEFONATA NON PARTE DA SOLA.

    Accettare una proposta crea la seconda chiamata e la lascia **autorizzata**:
    perche' squilli serve ancora il si' esplicito su quella chiamata, come per
    ogni altra. Questa porta allarga il mandato, non compone un numero.
    """
    from telephone.continuation import as_a_question, by_id, decide

    continuazione = await by_id(db, continuation_id, user["user_id"])
    if continuazione is None:
        raise HTTPException(404, "questa decisione non esiste")

    esito = await decide(
        db,
        continuation=continuazione,
        decision=str(payload.get("decision") or ""),
        alternative=str(payload.get("alternative") or ""),
    )
    if not esito.ok:
        raise HTTPException(400, esito.why)
    return {
        "ok": True,
        "continuation": as_a_question(esito.continuation),
        # La telefonata che ne nasce, se ne nasce una. Autorizzata, non partita.
        "next_call_id": esito.call.id if esito.call else "",
        "already_decided": esito.why,
    }


@router.get("/calls/{call_id}/transcript")
async def call_transcript(
    call_id: str, user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Quello che si sono detti.

        IL TESTO C'ERA GIA'. L'AUDIO NON C'E' MAI STATO.

    Non si trascrive niente adesso: si apre una cosa raccolta mentre si
    parlava. Una telefonata senza battute — nessuna risposta, occupato — torna
    un elenco vuoto, non un errore: non aver parlato con nessuno e' un esito,
    non un guasto.
    """
    from telephone.history import the_transcript

    service = TelephoneService(db)
    call = await service.get(user["user_id"], call_id)
    if call is None:
        raise HTTPException(404, "chiamata sconosciuta")
    battute = the_transcript(call)
    return {
        "ok": True,
        "entries": battute,
        "available": bool(battute),
        # Perche' non c'e', quando non c'e'. Serve a scrivere la frase giusta.
        "why_empty": "" if battute else _why_nobody_spoke(call),
    }


def _why_nobody_spoke(call) -> str:
    """Perche' non c'e' niente da leggere."""
    from telephone.history import how_it_reads

    stato = how_it_reads(call)
    if stato == "nessuna_risposta":
        return "Non ha risposto nessuno."
    if stato == "occupato":
        return "La linea era occupata."
    if stato == "in_corso":
        return "La chiamata è ancora in corso."
    return "Di questa chiamata non è rimasto nulla da leggere."


@router.get("/{call_id}")
async def read(call_id: str, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Com'è andata, in italiano, più il controllo del mandato."""
    service = TelephoneService(db)
    call = await service.get(user["user_id"], call_id)
    if call is None:
        raise HTTPException(404, "chiamata sconosciuta")
    return {
        "ok": True,
        "state": call.state,
        "racconto": call.for_human(),
        "esito": call.outcome.model_dump() if call.outcome else None,
        "mandato_rispettato": service.kept_the_mandate(call),
        "ho_scritto": call.wrote,
        "come_lo_so": call.how_ora_knows(),
    }


# ---------------------------------------------------------------------------
# Verso l'operatore
# ---------------------------------------------------------------------------
#
# Non qui. Le porte che l'operatore telefonico usa — il copione, gli stati,
# l'audio — stanno in `vonage_router.py` e sono montate **fuori da `/api`:
# non hanno una sessione, non hanno un JWT di ORA, e i loro indirizzi sono
# già scritti nel pannello del fornitore. Tenerle qui dentro avrebbe
# significato o spostarle sotto `/api` e rompere quella configurazione, o
# montare due volte lo stesso router.
