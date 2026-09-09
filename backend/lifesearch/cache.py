"""
La stessa domanda, due volte, non si paga due volte — finche' la vita e' ferma.

    UNA RISPOSTA VECCHIA SU UNA VITA CAMBIATA E' PEGGIO DI NESSUNA RISPOSTA.

Quindi la chiave non e' la domanda: e' la domanda *piu' com'era la vita quando
si e' risposto*. Se nel frattempo e' arrivato un documento, e' cambiata una
situazione o la governance ha promosso un fatto, l'impronta cambia e la
risposta di prima non vale piu' — che e' esattamente il caso in cui una cache
farebbe il danno peggiore: rispondere «non ho documenti sul mutuo» a chi lo ha
appena caricato.

Cosa si tiene: solo l'interpretazione della domanda, che e' la parte cara. I
risultati no — quelli si ricalcolano ogni volta, costano zero e sono sempre
freschi. Una cache dei risultati sarebbe una seconda verita' con una scadenza.

Sta in memoria e non nel database, di proposito: e' un risparmio, non un
fatto, e il modello della vita non deve avere niente da tenere in fila con
qualcosa che vive in un processo.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("ora.lifesearch.cache")

# Quanto vale un'interpretazione, al massimo. L'impronta la invalida prima se
# la vita cambia; questo e' il tetto per tutto il resto — un modello nuovo,
# un'istruzione riscritta, una giornata che passa.
FOR_SECONDS = 900

# Quante domande diverse si ricordano. Piccolo: una persona in una sessione ne
# fa poche, e una cache che cresce senza limite e' una perdita di memoria con
# un buon proposito.
AT_MOST = 200

_kept: Dict[Tuple[str, str, str], Tuple[float, Dict[str, Any]]] = {}


def _normalized(query: str) -> str:
    """La domanda senza le differenze che non cambiano cosa vuol dire."""
    return " ".join((query or "").strip().lower().split())


async def fingerprint(db, owner_id: str) -> str:
    """
    Com'e' fatta questa vita adesso, in poche cifre.

    Non un conteggio di righe: quello cambierebbe a ogni email di spam. Le
    cose che cambiano *cosa si puo' rispondere* — quali situazioni ci sono e
    quando sono cambiate, quante carte sono collocate, cosa e' governato.
    """
    parts = []
    try:
        rows = await db.life_objects.find(
            {"user_id": owner_id, "status": {"$ne": "archived"}},
            {"_id": 0, "id": 1, "updated_at": 1},
        ).to_list(40)
        parts.append("|".join(sorted(
            f"{r.get('id')}@{str(r.get('updated_at'))[:19]}" for r in rows
        )))
    except Exception as e:
        logger.info("fingerprint soft-fail: %s", type(e).__name__)
        return "unknown"

    for collection, query in (
        ("connected_situation_links", {"owner_id": owner_id, "kind": "life_relation"}),
        ("financial_facts", {"owner_id": owner_id}),
        ("documents", {"user_id": owner_id, "deleted": {"$ne": True}}),
        ("memories", {"user_id": owner_id, "status": "active"}),
    ):
        try:
            parts.append(str(await db[collection].count_documents(query)))
        except Exception:
            parts.append("?")

    return hashlib.sha256("::".join(parts).encode()).hexdigest()[:16]


def remembered(
    owner_id: str, query: str, mark: str,
) -> Optional[Dict[str, Any]]:
    """L'interpretazione di prima, se la vita non e' cambiata da allora."""
    key = (owner_id, _normalized(query), mark)
    found = _kept.get(key)
    if not found:
        return None
    when, value = found
    if time.time() - when > FOR_SECONDS:
        _kept.pop(key, None)
        return None
    return dict(value)


def remember(owner_id: str, query: str, mark: str, value: Dict[str, Any]) -> None:
    """Tieni questa interpretazione, finche' vale."""
    if len(_kept) >= AT_MOST:
        # La piu' vecchia se ne va. Nessuna sofisticazione: e' un risparmio.
        oldest = min(_kept.items(), key=lambda kv: kv[1][0])[0]
        _kept.pop(oldest, None)
    _kept[(owner_id, _normalized(query), mark)] = (time.time(), dict(value))


def forget_everything() -> None:
    """Per i test, e per chi cambia le istruzioni al giudizio."""
    _kept.clear()
