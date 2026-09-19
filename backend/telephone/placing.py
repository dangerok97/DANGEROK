"""
Comporre il numero: un gesto solo, con una porta sola.

    LA CHAT E IL TASTO PASSANO DALLO STESSO PUNTO.

Prima c'era soltanto la route `place`, e chi diceva «sì, chiamala» in chat
arrivava a una telefonata preparata che nessuno poteva far partire. Adesso la
route e la chat chiamano questa funzione: le stesse verifiche, lo stesso
operatore, lo stesso piano che viene a sapere del sì.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from telephone import carrier
from telephone.service import TelephoneService

logger = logging.getLogger("ora.telephone.placing")


async def dial(
    db, owner_id: str, call, *, authority_ref: str = "explicit_yes",
) -> Tuple[Optional[object], str]:
    """
    Compone `call`, che deve essere ancora `authorised`.

    Torna (telefonata, "") se è partita, (None|telefonata, perché) se no. Non
    solleva: chi chiama decide come dirlo — la route con un codice HTTP, la
    chat con una frase.
    """
    service = TelephoneService(db)
    if call.state != "authorised":
        return call, f"questa chiamata è già {call.state}"

    permission = await service.may_i_call(owner_id)
    if permission["denied"]:
        return None, "aveva già detto di no alle telefonate"
    if not permission["provider_ready"]:
        return None, permission["why_not"] or "non c'è modo di telefonare"

    opened = await carrier.place(
        to_number=call.to_number,
        call_id=call.id,
        minutes=call.mandate.minutes,
    )
    if opened is None or not opened.get("call_ref"):
        await service.mark(call, "failed", how_it_ended="failed")
        why = (opened or {}).get("error") or "l'operatore non ha risposto"
        return None, f"la chiamata non è partita — {why}"

    call = await service.mark(
        call, "dialling",
        provider_ref=opened["call_ref"],
        authority_ref=str(authority_ref or "explicit_yes")[:64],
    )
    await the_plan_can_go(db, call)
    return call, ""


async def the_plan_can_go(db, call) -> None:
    """
    Registra sul piano il sì che è appena stato dato sulla telefonata.

        IL SÌ È UNO SOLO, E VALE PER TUTTE E DUE LE COSE.

    La persona ha detto di sì a questa telefonata con questo mandato, ed è
    esattamente l'autorità che il piano aspettava.
    """
    try:
        from autonomy.orchestrator import advance, grant
        from autonomy.plan import for_call

        plan = await for_call(db, call.id)
        if plan is None:
            return
        plan = await grant(db, plan, authority_ref=call.authority_ref)
        await advance(db, plan)
    except Exception as e:  # pragma: no cover
        logger.info("piano non autorizzato: %s", type(e).__name__)
