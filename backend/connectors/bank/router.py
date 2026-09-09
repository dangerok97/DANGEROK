"""
La porta di ritorno dal sito della banca.

    CHI ARRIVA QUI NON E' AUTENTICATO, ED E' NORMALE.

E' il browser di una persona che torna da un'altra parte del mondo: porta un
codice e uno `state`, e nient'altro. Non c'e' un token di ORA, non c'e' una
sessione applicativa, e non ci puo' essere — il salto e' passato dal sito
della banca.

Quindi l'identita' la stabilisce lo `state`, che ORA ha creato all'inizio del
percorso e conserva legato alla persona che lo ha cominciato: imprevedibile,
usa e getta, con una scadenza. E' l'unica cosa che impedisce a un estraneo di
far finire il proprio conto — o di far finire quello di qualcun altro —
dentro l'account sbagliato.

Quello che questa porta restituisce e' un redirect all'app, con una parola
sola che dice com'e' andata. Il codice della banca non compare mai
nell'indirizzo di ritorno: e' stato speso qui, ed e' finito il suo lavoro.
"""

from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

logger = logging.getLogger("ora.connectors.bank.router")

router = APIRouter(prefix="/connectors/bank/enablebanking", tags=["bank"])


def _back_to_app(outcome: str, where: str = "") -> str:
    """
    Dove torna la persona, e cosa le si dice appena arriva.

    L'indirizzo proposto passa comunque dal filtro degli origini consentiti:
    arriva da una riga di database scritta all'inizio del percorso, e una
    riga di database non e' un motivo sufficiente per mandare qualcuno
    ovunque.
    """
    from connectors.google_calendar.oauth import (
        allowed_frontend_origins, sanitize_redirect_after,
    )

    safe = sanitize_redirect_after(where) if where else None
    base = (safe or (allowed_frontend_origins()[0].rstrip("/") + "/conti-e-denaro"))
    joiner = "&" if "?" in base else "?"
    return f"{base}{joiner}collegamento={quote(outcome)}"


@router.get("/callback")
async def callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
):
    """
    Il ritorno: uno state, un codice, e una sessione da aprire.

    Non risponde mai con del JSON: qui ci arriva un essere umano dentro un
    browser, e quello che deve succedere e' ritrovarsi nell'app.
    """
    import deps
    from connectors.bank.link import complete_with_code
    from connectors.bank.service import BankReadService

    if error or not code or not state:
        # La persona ha annullato, o la banca ha rifiutato. Non e' un guasto
        # e non merita una pagina d'errore: si torna indietro e si dice che
        # non e' andata.
        logger.info("bank callback without a code")
        return RedirectResponse(_back_to_app("annullato"), status_code=302)

    svc = BankReadService(
        db=deps.db, permissions=deps.get_permissions_service(),
        vault=deps.get_token_vault(),
    )
    try:
        done = await complete_with_code(svc, state=state, code=code)
    except Exception as e:
        logger.info("bank callback failed: %s", type(e).__name__)
        return RedirectResponse(_back_to_app("non_riuscito"), status_code=302)

    return RedirectResponse(
        _back_to_app(
            "collegato" if done.get("ok") else "non_riuscito",
            str(done.get("redirect_after") or ""),
        ),
        status_code=302,
    )
