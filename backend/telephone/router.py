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
