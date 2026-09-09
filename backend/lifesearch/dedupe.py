"""
Quattro righe che sembrano lo stesso appuntamento sono un errore, non un elenco.

    LA STESSA COSA, VISTA PIU' VOLTE, RESTA UNA COSA.

Sulla ricerca vera di «dentista» uscivano sei righe: «QA ORA — Visita
dentistica», «Visita dentistica QA ORA», «Visita dentistica — Studio Bianchi»
due volte, e altre due. Sono lo stesso pomeriggio letto da calendari diversi,
o la stessa riga rimasta dopo una prova. Chi legge non ha modo di saperlo, e
conta sei impegni dove ce n'e' uno.

Il raggruppamento e' deterministico e non decide significati: stesso giorno,
stessa ora, e titoli che condividono abbastanza parole. Sono conti su stringhe
e su date — non «questi due eventi parlano della stessa cosa», che sarebbe un
giudizio e vivrebbe altrove.

Quello che si vede e' la versione corrente. Le altre restano dietro, contate:
«visto anche in altri 3 calendari» e' un'informazione, «6 appuntamenti» e' una
bugia.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

# Quanto due titoli devono somigliarsi per essere la stessa cosa. Non e' una
# soglia sul significato: e' la frazione di parole in comune sopra la quale
# due righe sono, quasi sempre, la stessa riga scritta due volte.
ENOUGH = 0.6

# Le parole che non distinguono niente. Nessun elenco di categorie: sono
# articoli e preposizioni, piu' i marcatori che le prove lasciano in giro.
_NOISE = {"il", "lo", "la", "i", "gli", "le", "di", "da", "a", "e", "con",
          "per", "del", "della", "dei", "delle", "qa", "ora", "test"}


def _words(title: str) -> set:
    found = re.findall(r"[a-zàèéìòùA-Z0-9]+", (title or "").lower())
    return {w for w in found if len(w) > 2 and w not in _NOISE}


def _same_thing(one: Dict[str, Any], other: Dict[str, Any]) -> bool:
    """
    Due righe sono la stessa cosa? Solo aritmetica su parole e su quando.
    """
    if (one.get("quando") or "") != (other.get("quando") or ""):
        return False
    here, there = _words(one.get("cosa", "")), _words(other.get("cosa", ""))
    if not here or not there:
        return False
    shared = len(here & there) / min(len(here), len(there))
    return shared >= ENOUGH


def collapse(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Una riga per cosa, con dietro il conto di quante volte si e' vista.

    Si tiene la piu' descrittiva — quella con piu' parole che dicono qualcosa
    — perche' fra «Visita dentistica» e «Visita dentistica — Studio Bianchi»
    la seconda e' la stessa informazione piu' il posto.
    """
    kept: List[Dict[str, Any]] = []
    for row in rows:
        for already in kept:
            if not _same_thing(already, row):
                continue
            already["_visto_volte"] = already.get("_visto_volte", 1) + 1
            if len(_words(row.get("cosa", ""))) > len(_words(already.get("cosa", ""))):
                # La versione piu' completa prende il posto, e il conto resta.
                times = already["_visto_volte"]
                already.update(row)
                already["_visto_volte"] = times
            break
        else:
            kept.append(dict(row))

    for row in kept:
        times = row.pop("_visto_volte", 1)
        if times > 1:
            # Detto come lo direbbe qualcuno, e solo quando aggiunge qualcosa.
            row["anche_altrove"] = f"lo vedo in {times} calendari"
    return kept
