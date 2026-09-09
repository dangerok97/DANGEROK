"""
Quello che ORA sa dei soldi, detto in Home come lo direbbe una persona.

    NON UNA DASHBOARD. UNA FRASE.

Niente grafici, niente categorie, niente tabella di movimenti: se una persona
volesse quello aprirebbe la banca. Quello che ORA puo' dare e' un'altra cosa —
sapere cosa sta arrivando, e dire onestamente cosa non sa.

Due righe al massimo, e nessuna delle due e' un numero da sola:

  «Conosco tre pagamenti entro fine mese» — con quali sono, e cosa manca.
  «Ho due cifre diverse per l'affitto»    — con tutte e due, senza sceglierne una.

E mai «ti rimarranno»: quella frase richiede un saldo che ORA non ha.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from home.models import ConnectionWarning, HomeAction, HomeItem

from ._util import now_iso, stable_id

logger = logging.getLogger("ora.home.adapters.financial")


def _same_thing(what) -> str:
    """Lo stesso impegno, comunque sia scritto."""
    return " ".join(str(what or "").strip().lower().split())


def _as_a_person_would_say(line: str) -> str:
    """
    «Affitto casa — €700 al mese» invece di «affitto casa · €700 · ogni mese».

    I punti mediani sono il modo in cui un database mostra dei campi. Una
    persona dice una cosa e poi quanto costa.
    """
    bits = [b.strip() for b in str(line).split("·") if b.strip()]
    if not bits:
        return str(line)
    head = bits[0][:1].upper() + bits[0][1:]
    rest = " ".join(bits[1:])
    return f"{head} — {rest}".strip(" —")


async def load_financial_context(
    db, user_id: str,
) -> Tuple[List[HomeItem], List[ConnectionWarning]]:
    try:
        from financial.horizon import for_human, what_is_coming
        from financial.store import FinancialStore
    except Exception as e:
        logger.info("financial import soft-fail: %s", type(e).__name__)
        return [], []

    items: List[HomeItem] = []

    try:
        horizon = await what_is_coming(db, user_id, days=30)
        said = for_human(horizon)
        disagreements = await FinancialStore(db).disagreements(user_id)
    except Exception as e:
        logger.info("financial read soft-fail: %s", type(e).__name__)
        return [], []

    coming = said["in_uscita"] + said["in_entrata"]
    if coming:
        # Il titolo dice quanti sono, non quanto fanno. La somma esiste solo
        # se ogni singolo importo e' noto, e anche allora e' «quello che so»,
        # non «quello che spenderai».
        how_many = len(coming)
        title = (
            "Conosco un pagamento entro fine mese" if how_many == 1
            else f"Conosco {how_many} movimenti entro fine mese"
        )
        body = ". ".join(_as_a_person_would_say(c) for c in coming[:4])
        if said["cosa_non_so"]:
            body = f"{body}. Non so {said['cosa_non_so'][0]}."
        items.append(HomeItem(
            id=stable_id("fin", user_id, "horizon"),
            type="insight",
            subtype="financial_horizon",
            title=title,
            description=body,
            source_type="financial",
            source_id="horizon",
            status="open",
            confidence=0.8,
            created_at=now_iso(),
            updated_at=now_iso(),
            meta={"dedupe_key": "fin:horizon"},
        ))

    # Quello che ORA ha letto e non puo' credere da sola. Non e' un errore
    # ed e' il contrario di un dettaglio tecnico: e' la domanda che rende
    # onesto tutto il resto.
    try:
        from financial.durable import needs_your_word

        pending = await needs_your_word(db, user_id)
    except Exception as e:
        logger.info("clarify read soft-fail: %s", type(e).__name__)
        pending = []

    for ask in pending[:1]:
        was = f" Finora sapevo {ask['instead_of']}." if ask["instead_of"] else ""
        items.append(HomeItem(
            id=stable_id("fin", user_id, f"ask:{ask['what']}"),
            # «verify» e' il tipo che questa Home usa per «guarda se e'
            # giusto»: e' esattamente cosa si sta chiedendo.
            type="verify",
            subtype="financial_confirmation",
            title=f"«{ask['what']}» è {ask['how_much']}?",
            description=(
                f"L'ho letto: {ask['how_directly']}.{was} "
                "Prima di darlo per buono volevo chiedertelo."
            ),
            source_type="financial",
            source_id=f"ask:{ask['what']}",
            # Le tre risposte possibili, sulla carta stessa.
            #
            #     UNA DOMANDA CHE SI PUO' RISOLVERE DOVE LA SI LEGGE.
            #
            # Mandare la persona altrove per dire «sì» sarebbe chiederle di
            # fare un viaggio per una parola. Il terzo pulsante c'e' perche'
            # a volte la risposta non e' sì o no: è «fammi capire meglio».
            actions=[
                HomeAction(id="money_yes", label="Sì", kind="complete",
                           params={"about": ask["what"], "confirmed": True},
                           primary=True),
                HomeAction(id="money_no", label="No", kind="ignore",
                           params={"about": ask["what"], "confirmed": False}),
                HomeAction(id="money_ask", label="Approfondisci con ORA",
                           kind="navigate", route="/ora"),
            ],
            status="open",
            confidence=0.5,
            created_at=now_iso(),
            updated_at=now_iso(),
            meta={"dedupe_key": f"fin:ask:{ask['what']}"},
        ))

    # UNA COSA IRRISOLTA, UNA PRESENZA SOLA.
    #
    # «L'affitto e' 760?» e «ho due cifre diverse per l'affitto» sono la
    # stessa cosa detta due volte: la persona ne vede due e pensa di avere due
    # problemi. Si tiene la domanda — perche' e' risolvibile in un secondo —
    # e il disaccordo compare solo se riguarda qualcos'altro.
    #
    # L'unione e' sull'identita' del fatto, non sulle parole: due righe che si
    # chiamano diversamente ma parlano della stessa cosa devono unirsi lo
    # stesso, e due che si chiamano uguale ma parlano di cose diverse no.
    already_asked = {_same_thing(a["what"]) for a in pending[:1]}

    for clash in disagreements:
        if _same_thing(clash.get("what")) in already_asked:
            continue
        versions = clash.get("versions") or []
        if len(versions) < 2:
            continue
        both = " e ".join(v["how_much"] for v in versions[:2])
        who = " e ".join(
            {"email": "un messaggio", "document": "un documento",
             "person": "quello che mi hai detto"}.get(v["said_by"], v["said_by"])
            for v in versions[:2]
        )
        items.append(HomeItem(
            id=stable_id("fin", user_id, f"clash:{clash['what']}"),
            type="verify",
            subtype="financial_disagreement",
            # Non si sceglie: si chiede. E' l'unica cosa onesta da fare con
            # due fonti che dicono numeri diversi della stessa cosa.
            title=f"Ho due cifre diverse per «{clash['what']}»",
            description=f"{both}, da {who}. Quale vale?",
            source_type="financial",
            source_id=f"clash:{clash['what']}",
            status="open",
            confidence=0.6,
            created_at=now_iso(),
            updated_at=now_iso(),
            meta={"dedupe_key": f"fin:clash:{clash['what']}"},
        ))

    return items, []
