"""
Il lato economico di una cosa che sta succedendo nella vita di qualcuno.

    NON UN «PROGETTO FINANZIARIO». UN ASPETTO DELLA CASA.

Comprare casa non e' un progetto finanziario con dentro una casa: e' una cosa
che una persona sta facendo, e i soldi sono uno dei suoi lati. Se questo
modulo creasse un oggetto a parte — un budget, un piano di spesa — la stessa
casa esisterebbe in due posti e nel giro di un mese direbbero cose diverse.

Quindi qui non si crea niente: si legge. Quali fatti economici, fra quelli che
ORA sa, sono stati collegati a questa situazione — e si dice cosa se ne sa e
cosa no, in parole.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from financial.durable import governed_facts
from financial.store import FinancialStore

logger = logging.getLogger("ora.financial.situation")


async def money_side_of(db, owner_id: str, situation_id: str) -> Dict[str, Any]:
    """
    Cosa ORA sa del lato economico di questa situazione.

    Torna una cosa fatta di frasi. Niente id, niente confidenze, niente stati:
    la schermata che la mostra deve poterla stampare cosi' com'e'.

    Quando non si sa niente torna vuoto, e chi chiama non deve mostrare
    nulla — una sezione «Cosa so sul lato economico» che dice «niente» e'
    peggio della sua assenza.
    """
    known = await governed_facts(db, owner_id)
    observed = await FinancialStore(db).known(owner_id)

    # Un fatto appartiene a questa situazione se qualcuno — il giudizio — ce
    # lo ha messo. Non per somiglianza di parole: «casa» dentro «bolletta di
    # casa» non fa di una bolletta un pezzo dell'acquisto.
    mine = [f for f in known + observed if situation_id in (f.about_refs or [])]

    lines: List[str] = []
    missing: List[str] = []
    seen: set = set()
    for fact in mine:
        key = " ".join(str(fact.what).lower().split())
        if key in seen:
            continue
        seen.add(key)
        if fact.money.is_known:
            lines.append(f"{fact.what} · {fact.money.for_human()}")
        else:
            lines.append(f"{fact.what} · importo ancora non definito")
        for unknown in fact.unknowns:
            missing.append(f"{fact.what}: {unknown}")

    # Le cose su cui ci sono due versioni: si dicono tutte e due.
    unsure: List[str] = []
    by_thing: Dict[str, List[Any]] = {}
    for fact in mine:
        if fact.status == "disputed":
            by_thing.setdefault(" ".join(str(fact.what).lower().split()), []).append(fact)
    for versions in by_thing.values():
        if len(versions) < 2:
            continue
        amounts = " e ".join(v.money.for_human() for v in versions[:2])
        unsure.append(
            f"Ho due importi diversi per «{versions[0].what}»: {amounts}. "
            "Devo ancora capire quale è quello attuale."
        )

    return {
        "cosa_so": lines,
        "cosa_non_so": list(dict.fromkeys(missing))[:4],
        "cosa_devo_chiarire": unsure,
        "vale_la_pena_mostrarlo": bool(lines or unsure),
    }
