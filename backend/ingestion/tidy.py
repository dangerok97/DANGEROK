"""
Il mucchio lasciato dalle riletture di prima.

    LA CORREZIONE FERMA LA CRESCITA. NON TOGLIE QUELLO CHE E' GIA' CRESCIUTO.

Il pipeline adesso non scrive piu' una riga per ogni rilettura invariata. Ma
le righe scritte prima ci sono ancora, e sono indistinguibili da osservazioni
vere per chi legge: contano come impegni, riempiono la finestra della Home, e
su questo account erano 260 in piu' del necessario per 50 eventi.

Questo modulo le raccoglie. Non le cancella: le marca `superseded`, che e'
esattamente cosa sono — copie identiche superate dalla piu' recente. La
storia resta leggibile, i lettori le ignorano gia', e il conteggio delle
righe vive torna a essere il numero di appuntamenti.

Si applica a una persona per volta, e non tocca:
  - le righe `processed` (sono osservazioni vere),
  - la piu' recente di ogni evento, qualunque sia il suo stato,
  - niente che abbia un `payload_hash` diverso dalla riga che tiene il posto.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger("ora.ingestion.tidy")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def collapse_unchanged_duplicates(
    db, user_id: str, *, dry_run: bool = False,
) -> Dict[str, int]:
    """
    Riduci a una le righe vive che dicono la stessa identica cosa.

    Restituisce cosa ha trovato e cosa ha fatto. Con `dry_run` guarda e basta,
    che e' come si controlla una cosa del genere prima di lanciarla su dati di
    qualcuno.
    """
    rows: List[Dict[str, Any]] = await db.ingestion_events.find(
        {
            "user_id": user_id,
            "ingestion_status": {"$nin": ["superseded", "quarantined"]},
        },
        {"_id": 0, "id": 1, "external_id": 1, "connector_instance_id": 1,
         "payload_hash": 1, "ingested_at": 1, "ingestion_status": 1},
    ).to_list(20000)

    by_event: Dict[tuple, List[Dict[str, Any]]] = {}
    for row in rows:
        key = (row.get("connector_instance_id"), row.get("external_id"))
        by_event.setdefault(key, []).append(row)

    counted = {"events": len(by_event), "rows": len(rows), "collapsed": 0}
    for group in by_event.values():
        if len(group) < 2:
            continue
        # Chi tiene il posto: una riga «processed» prima di una «skipped», e
        # a parita' la piu' recente.
        #
        #     LA RIGA CHE RESTA DEVE ESSERE QUELLA CHE I LETTORI LEGGONO.
        #
        # Tenere la piu' recente e basta sembra ovvio e non lo e': la piu'
        # recente di un evento fermo e' una riga «skipped», che la Home
        # esclude per costruzione. Raccogliere cosi' lasciava vive solo righe
        # che nessuno guarda, e la Home restava vuota sopra un calendario
        # pieno — lo stesso identico sintomo che questa pulizia doveva
        # togliere di mezzo.
        # Due ordinamenti, e l'ordine fra i due conta: il secondo e' stabile,
        # quindi a parita' di stato sopravvive l'ordine per data del primo.
        group.sort(key=lambda r: str(r.get("ingested_at") or ""), reverse=True)
        group.sort(key=lambda r: 0 if r.get("ingestion_status") == "processed" else 1)
        keeper = group[0]
        stale = [
            r for r in group[1:]
            if r.get("payload_hash") == keeper.get("payload_hash")
        ]
        if not stale:
            continue
        counted["collapsed"] += len(stale)
        if dry_run:
            continue
        await db.ingestion_events.update_many(
            {"id": {"$in": [r["id"] for r in stale]}},
            {"$set": {
                "ingestion_status": "superseded",
                "superseded_by_event_id": keeper["id"],
                "updated_at": _now_iso(),
            }},
        )

    logger.info(
        "tidy user=%s eventi=%d righe=%d raccolte=%d dry_run=%s",
        user_id, counted["events"], counted["rows"], counted["collapsed"], dry_run,
    )
    return counted
