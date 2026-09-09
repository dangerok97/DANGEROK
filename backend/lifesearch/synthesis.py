"""
Una risposta, quando l'elenco non e' una risposta.

    «COSA SAI SULLA CASA?» NON SI RISPONDE CON DELLE SCHEDE.

Ci sono domande che chiedono di sapere, non di navigare. A quelle, sei gruppi
di risultati sono materiale grezzo consegnato a chi aveva fatto una domanda:
la persona deve leggerli tutti e fare da sola la sintesi che aveva chiesto.

E ce ne sono altre — «documenti della casa» — dove una sintesi e' un paragrafo
fra chi cerca e quello che cercava. Il giudizio dice a quale delle due
categorie appartiene una domanda; questo file scrive solo la prima.

**Cosa vede il modello.** Quello che il recupero ha gia' portato, con i gradi
addosso: quello che ORA sa, quello che ha solo letto, quello che ha visto e
non ha capito. Niente di piu': non si rilegge il database per scrivere un
paragrafo.

**Cosa non puo' fare.** Aggiungere. Il paragrafo puo' solo dire quello che c'e'
nei risultati, e dire cosa manca — che e' spesso la parte piu' utile: «non ho
ancora niente sul rogito» e' un'informazione che nessuna scheda mostra.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from research.reasoning import _ask_model

logger = logging.getLogger("ora.lifesearch.synthesis")

_DISCIPLINE = (
    "You are ORA, answering a person about their own life. You are given what "
    "was found for their question, already grouped and already marked with how "
    "each thing is known:\n\n"
    "    SO — governed knowledge, you may state it\n"
    "    PENSO — read but not confirmed, say how you know it\n"
    "    HO VISTO — observed, nobody has worked out what it is\n"
    "    DA CHIARIRE — waiting on their word\n\n"
    "Write a short paragraph — three or four sentences — that says what you "
    "know about this. Keep those distinctions: stating a PENSO as a fact is "
    "the one mistake that matters here.\n\n"
    "Say what is missing when it is worth knowing: a house purchase with no "
    "deed and no dates is worth a sentence.\n\n"
    "Add nothing that is not in what you were given. No advice unless they "
    "asked, no encouragement, no summary of your own capabilities.\n\n"
    "Answer with JSON only. No markdown fences."
)


async def in_a_few_lines(
    query: str, *, sections: List[Dict[str, Any]], language: str = "it",
) -> Optional[str]:
    """
    Il paragrafo sopra i risultati, o `None` se non c'e' niente da dire.

    Torna `None` anche quando il giudizio non risponde: i gruppi sotto
    restano, e sono comunque la risposta piu' onesta.
    """
    if not sections:
        return None

    data = await _ask_model(
        _DISCIPLINE,
        json.dumps({
            "they_asked": query,
            "what_was_found": sections,
            "answer_in": language,
            "return": {"answer": "the paragraph"},
        }, ensure_ascii=False, default=str)[:9000],
    )
    if not isinstance(data, dict):
        return None
    said = str(data.get("answer") or "").strip()
    return said[:900] or None
