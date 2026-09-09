"""
Tenere in ordine le relazioni senza che nessuno lo chieda.

    UN SISTEMA CHE COLLEGA SOLO QUANDO LO INTERROGHI NON HA CAPITO NIENTE
    FINCHE' NON GLI PARLI.

Le carte e i messaggi arrivano quando arrivano. Se la loro collocazione
avviene solo mentre qualcuno cerca, la prima ricerca dopo una settimana di
posta paga il conto di quella settimana — e fino ad allora ORA non sapeva
niente di quello che aveva gia' ricevuto.

Quindi il lavoro si sposta dove sta gia' tutto il resto: dentro il giro
dell'ambient runtime, che gia' tocca, gia' sopravvive a un riavvio, gia'
tollera che un passaggio fallisca. Nessuno scheduler nuovo. Il giro chiama
questa funzione ogni tanto, lei guarda se c'e' qualcosa di nuovo, e quasi
sempre non c'e' — e allora non costa niente.

**Solo quello che non ha ancora una risposta.** Un documento gia' collocato
non si rigiudica; un messaggio che qualcuno ha gia' deciso non appartenere a
niente resta deciso. Il secondo passaggio su una vita ferma fa zero chiamate,
scrive zero righe, e questo e' verificato da un test — perche' e' la
differenza fra un lavoro di manutenzione e una fattura ricorrente.

**Poche persone per giro.** Un arretrato si smaltisce in piu' passaggi. Un
giro che prova a sistemare tutti quelli che hanno posta e' un giro che dura
piu' del giro.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger("ora.lifesearch.maintenance")

# Quante persone per passaggio. Piccolo: e' manutenzione, non una migrazione.
PEOPLE_PER_PASS = 2


async def keep_relations_current(
    db, *, owners: List[str] | None = None, limit: int = PEOPLE_PER_PASS,
) -> Dict[str, Any]:
    """
    Colloca quello che e' arrivato e non e' ancora stato guardato.

    Torna sempre il conto delle chiamate: e' il numero che dice se questa
    manutenzione sta diventando un costo invece di un servizio.
    """
    from lifesearch.messages import file_the_messages
    from lifesearch.papers import file_the_papers

    people = owners if owners is not None else await _who_has_something(db, limit)
    done = {"persone": 0, "carte": 0, "messaggi": 0, "chiamate": 0}

    for owner_id in people[:limit]:
        done["persone"] += 1
        for what, run in (("carte", file_the_papers), ("messaggi", file_the_messages)):
            try:
                out = await run(db, owner_id)
            except Exception as e:
                logger.info("%s soft-fail: %s", what, type(e).__name__)
                continue
            done[what] += int(out.get("collegate") or 0)
            done["chiamate"] += int(out.get("chiamate") or 0)

    if done["chiamate"]:
        logger.info("relation maintenance %s", done)
    return done


async def _who_has_something(db, limit: int) -> List[str]:
    """
    Chi potrebbe avere qualcosa da collocare, senza scandire nessuno.

    Le persone con qualcosa di recente, prese dalle collezioni che gia'
    esistono. Non e' una selezione precisa e non deve esserlo: chi non ha
    niente da fare costa una query e nient'altro, e chi resta fuori tocca al
    giro dopo.
    """
    out: List[str] = []
    for collection, field in (
        ("documents", "user_id"),
        ("ingestion_events", "user_id"),
    ):
        try:
            rows = await db[collection].find(
                {}, {"_id": 0, field: 1},
            ).sort("created_at", -1).to_list(60)
        except Exception as e:
            logger.info("owner scan soft-fail: %s", type(e).__name__)
            continue
        for row in rows:
            owner = str(row.get(field) or "")
            if owner and owner not in out:
                out.append(owner)
            if len(out) >= limit * 4:
                break
    return out[: limit * 4]
