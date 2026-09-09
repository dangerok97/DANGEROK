"""
Cosa contiene questa vita, detto in poche righe.

    IL MODELLO NON DEVE LEGGERE IL DATABASE PER CAPIRE UNA DOMANDA.

Deve sapere *cosa esiste*: come si chiamano le situazioni aperte di questa
persona, cosa ORA sa dei suoi soldi, quali strumenti sono collegati, quante
cose ci sono di ciascun tipo. Con questo davanti, «notaio» porta all'acquisto
della casa senza che nessuno abbia scritto da nessuna parte che un notaio ha
a che fare con una casa — ed e' esattamente la differenza fra capire una
domanda e cercare una parola.

L'indice e' piccolo per costruzione: nomi, non contenuti. Qualche centinaio
di parole per una vita intera, che e' il punto — un indice che cresce con i
documenti sarebbe l'archivio da cui si stava scappando.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger("ora.lifesearch.index")

# Quante voci per tipo entrano nell'indice. Non e' un limite di verita': e'
# il confine oltre il quale un indice smette di essere un indice.
MOST = 12


async def life_index(db, owner_id: str) -> Dict[str, Any]:
    """
    L'indice della vita di questa persona: nomi e conteggi, nessun contenuto.
    """
    situations = await _situations(db, owner_id)
    money = await _money(db, owner_id)

    return {
        # Le parti della vita che esistono davvero, con il loro nome.
        "situations_in_this_life": situations,
        # Quello che ORA sa e quello che ha solo letto, per nome.
        "what_ora_knows_about_their_money": money["knows"],
        "what_ora_only_read_about_their_money": money["read"],
        "money_questions_still_open": money["asking"],
        # Cosa c'e' da guardare, e quanto ce n'e'.
        "what_else_exists": await _volumes(db, owner_id),
        "how_to_use_this": (
            "These are the parts of this person's life and what ORA already "
            "knows. A question is usually about one of them even when it does "
            "not name it: a notary belongs to buying a house, a salary to "
            "work. Name the ones the question is about."
        ),
    }


async def _situations(db, owner_id: str) -> List[Dict[str, Any]]:
    """Le situazioni aperte: id, nome, che cosa sono."""
    try:
        rows = await db.life_objects.find(
            {"user_id": owner_id, "status": {"$ne": "archived"}},
            {"_id": 0, "id": 1, "title": 1, "type": 1, "ai_summary": 1},
        ).sort("updated_at", -1).to_list(30)
    except Exception as e:
        logger.info("situation read soft-fail: %s", type(e).__name__)
        return []
    out = []
    for row in rows:
        if not row.get("title"):
            continue
        out.append({
            "id": row["id"],
            "what_it_is": str(row["title"])[:80],
            "kind": row.get("type") or "",
            # Una riga sola di contesto: serve a distinguere due situazioni
            # che si chiamano quasi uguale, non a raccontarle.
            "in_a_line": str(row.get("ai_summary") or "")[:160],
        })
    return out[:MOST]


async def _money(db, owner_id: str) -> Dict[str, List[str]]:
    """
    I nomi di quello che ORA sa dei soldi — dal modello governato, non dal
    registro grezzo.
    """
    try:
        from financial.knowledge import what_ora_knows

        said = await what_ora_knows(db, owner_id)
    except Exception as e:
        logger.info("money read soft-fail: %s", type(e).__name__)
        return {"knows": [], "read": [], "asking": []}
    return {
        "knows": [str(r["cosa"])[:60] for r in said["so"]][:MOST],
        "read": [str(r["cosa"])[:60] for r in said["ho_letto"]][:MOST],
        "asking": [str(r["cosa"])[:60] for r in said["devo_chiederti"]][:MOST],
    }


async def _volumes(db, owner_id: str) -> Dict[str, int]:
    """
    Quanto c'e' di ciascuna cosa. Conteggi, non contenuti.

    Servono al modello per sapere se una domanda ha qualche speranza: chiedere
    «i documenti del mutuo» a una vita senza documenti e' una risposta che si
    puo' dare prima di cercare.
    """
    out: Dict[str, int] = {}
    for name, query in (
        ("documents", {"user_id": owner_id, "deleted": {"$ne": True}}),
        ("appointments_and_messages", {"user_id": owner_id}),
        ("bank_movements", {"owner_id": owner_id}),
        ("things_that_changed", {"owner_id": owner_id}),
    ):
        collection = {
            "documents": "documents",
            "appointments_and_messages": "ingestion_events",
            "bank_movements": "financial_observations",
            "things_that_changed": "connected_signals",
        }[name]
        try:
            out[name] = await db[collection].count_documents(query)
        except Exception:
            out[name] = 0
    return out
