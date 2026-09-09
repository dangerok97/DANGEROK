"""
Capire cosa sta cercando una persona. Una chiamata, e nessun elenco di parole.

    IL SIGNIFICATO DI UNA DOMANDA NON STA NELLE SUE PAROLE.

«Mutuo» non e' una categoria. «Vibo Marina» non e' un tipo di risultato.
«Cosa so sul mio affitto» e «quanto pagavo prima» sono la stessa parola e due
domande diverse. Un instradamento a parole chiave le sbaglia entrambe, e ogni
volta che qualcuno se ne accorge la cura e' aggiungere una parola all'elenco —
finche' l'elenco diventa il prodotto.

Qui il modello riceve l'indice della vita — i nomi delle situazioni, quello
che ORA sa — e dice tre cose: che tipo di domanda e', a quali parti della vita
si riferisce, e in che finestra di tempo guardare. Il codice non gli crede
sulla parola: gli id che nomina devono esistere davvero, e le parole che
propone servono solo come ultima risorsa.

Cosa il codice non delega mai: i confini. Quali collezioni si possono leggere,
di chi sono le righe, quanto se ne prende. Quello e' un permesso, e un
permesso non si chiede a un modello.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from research.reasoning import _ask_model

logger = logging.getLogger("ora.lifesearch.interpret")

# Cosa la persona sta *facendo*, che e' diverso da cosa sta nominando.
#
#     «MUTUO» E «QUANTO PAGO DI MUTUO» NON SONO LA STESSA RICHIESTA.
#
# Il primo vuole arrivare da qualche parte, il secondo vuole una risposta. Il
# modo decide se serve una sintesi, se serve la storia, se servono i soldi —
# ed e' una lettura della domanda, non una sua classificazione lessicale.
MODES = (
    "navigate",    # portami li'
    "answer",      # rispondimi
    "explore",     # fammi vedere cosa c'e'
    "compare",     # mettili uno accanto all'altro
    "timeline",    # cosa e' cambiato, cosa arriva
    "provenance",  # da dove lo sai
)

# Quali fonti vale la pena aprire. Il codice decide se puo', il giudizio dice
# se serve: chiedere i movimenti bancari per «quando ho il dentista» e' un
# costo senza una ragione.
SOURCES = (
    "situations", "knowledge", "documents", "messages", "appointments",
    "money", "changes",
)

# Che tipo di domanda e'. Non sono categorie di risultati: sono modi diversi
# di guardare la stessa vita, e cambiano cosa vale la pena raccogliere.
KINDS = (
    "entity_lookup",        # una cosa precisa: «Studio Bianchi»
    "situation_lookup",     # una parte della vita: «casa»
    "relationship_lookup",  # cosa c'entra con cosa: «spese collegate alla casa»
    "timeline_lookup",      # quando: «cosa ho a settembre»
    "financial_lookup",     # soldi: «quanto pago di affitto»
    "document_lookup",      # carte: «documenti del mutuo»
    "broad_life_query",     # tutto quello che riguarda qualcosa
    "uncertain",            # e va bene: si cerca largo e si dice poco
)

_DISCIPLINE = (
    "You are ORA, and someone is looking for something inside their own life. "
    "You are given an index of that life — the situations they have open, what "
    "ORA already knows about their money, how much of each kind of thing "
    "exists — and their query.\n\n"
    "Your job is to say what they are looking for, and which parts of their "
    "life the question is about. The connection is often not in the words: a "
    "notary belongs to buying a house, a salary belongs to work, a dentist to "
    "an appointment. Use what you know about how lives work, not string "
    "matching.\n\n"
    "Name a situation only if the question really is about it. Naming all of "
    "them is the same as naming none.\n\n"
    "If the question asks how ORA knows something, or what it used to be, say "
    "so — those change what must be shown, not merely what is found.\n\n"
    "Answer with JSON only. No markdown fences."
)


async def what_are_they_looking_for(
    query: str, *, index: Dict[str, Any], language: str = "it",
) -> Optional[Dict[str, Any]]:
    """
    Cosa cerca questa persona, e in quale parte della sua vita.

    Torna `None` se il giudizio non arriva: chi chiama cerca largo e lo dice,
    invece di fingere di aver capito.
    """
    instruction = (
        f"Return JSON: {{\"kind\": one of {list(KINDS)}, "
        f"\"mode\": one of {list(MODES)}, "
        "\"about_situations\": [ids from the index, most relevant first], "
        "\"concepts\": [\"the things this question is really about, in "
        "their language — a notary, a mortgage, a rent — whether or not they "
        "were typed\"], "
        f"\"sources_worth_opening\": [any of {list(SOURCES)}], "
        "\"relation_hypotheses\": [{{\"from\": \"one thing\", "
        "\"to\": \"another\", \"why_it_might_hold\": \"…\"}}], "
        "\"needs_synthesis\": false, "
        "\"uncertainty\": \"low\" | \"medium\" | \"high\", "
        "\"what_they_want\": \"one line, in their language\", "
        "\"time_window_days\": null or a number of days back they mean, "
        "\"looking_forward\": false, "
        "\"wants_history\": false, "
        "\"wants_to_know_how_ora_knows\": false, "
        "\"words_worth_looking_for\": [\"…\"]}\n\n"
        "`needs_synthesis` is true when the question is broad enough that a "
        "list of cards would not answer it — «what do you know about the "
        "house» — and false when they are navigating: «house documents» wants "
        "the documents, not a paragraph.\n\n"
        "`relation_hypotheses` are connections you think probably hold but "
        "that nobody has recorded. They are guesses, they are treated as "
        "guesses, and nothing is written down because of them.\n\n"
        "`words_worth_looking_for` is a last resort for things that have no "
        "recorded relation — a name written on a document, a place. Include "
        "the words a bank or a calendar would actually have written, not "
        "synonyms you would like to exist."
    )

    data = await _ask_model(
        _DISCIPLINE + "\n\n" + instruction,
        json.dumps({
            "they_typed": query,
            "their_life": index,
            "answer_in": language,
        }, ensure_ascii=False, default=str)[:8000],
    )
    if not isinstance(data, dict):
        return None

    kind = str(data.get("kind") or "").strip()
    if kind not in KINDS:
        kind = "uncertain"

    # Gli id nominati dal modello valgono solo se esistono in questa vita.
    #
    #     UN RIFERIMENTO INVENTATO E' UN RISULTATO CHE APPARTIENE A NESSUNO.
    known = {s["id"] for s in index.get("situations_in_this_life") or []}
    about = [str(x) for x in (data.get("about_situations") or []) if str(x) in known]

    mode = str(data.get("mode") or "").strip()
    if mode not in MODES:
        mode = "explore"

    return {
        "kind": kind,
        "mode": mode,
        "concepts": [
            str(c).strip()[:60] for c in (data.get("concepts") or []) if str(c).strip()
        ][:6],
        "sources": [
            str(x) for x in (data.get("sources_worth_opening") or []) if str(x) in SOURCES
        ],
        # Ipotesi, e restano tali: nessuna di queste diventa una riga scritta.
        "relation_hypotheses": [
            {
                "from": str(h.get("from") or "")[:80],
                "to": str(h.get("to") or "")[:80],
                "why": str(h.get("why_it_might_hold") or "")[:160],
            }
            for h in (data.get("relation_hypotheses") or [])
            if isinstance(h, dict)
        ][:4],
        "needs_synthesis": bool(data.get("needs_synthesis")),
        "uncertainty": str(data.get("uncertainty") or "medium"),
        "about_situations": about[:4],
        "what_they_want": str(data.get("what_they_want") or "")[:200],
        "since": _since(data.get("time_window_days")),
        "looking_forward": bool(data.get("looking_forward")),
        "wants_history": bool(data.get("wants_history")),
        "wants_provenance": bool(data.get("wants_to_know_how_ora_knows")),
        "words": [
            str(w).strip().lower() for w in (data.get("words_worth_looking_for") or [])
            if str(w).strip()
        ][:6],
    }


def _since(days: Any) -> Optional[str]:
    """La finestra, in una data. Aritmetica: il modello dice quanti giorni."""
    try:
        n = int(days)
    except (TypeError, ValueError):
        return None
    if n <= 0 or n > 3650:
        return None
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


def fall_back(query: str) -> Dict[str, Any]:
    """
    Cosa fare quando il giudizio non risponde.

    Non un instradamento a parole camuffato: si cerca largo, con le parole che
    la persona ha scritto, e la risposta lo dira' — «ho cercato le tue parole»
    e' onesto, «ho capito cosa cerchi» non lo sarebbe.
    """
    words = [w for w in query.lower().split() if len(w) > 2][:6]
    return {
        "kind": "uncertain",
        "mode": "explore",
        "concepts": [],
        "sources": [],
        "relation_hypotheses": [],
        "needs_synthesis": False,
        "uncertainty": "high",
        "about_situations": [],
        "what_they_want": "",
        "since": None,
        "looking_forward": False,
        "wants_history": False,
        "wants_provenance": False,
        "words": words,
        "the_judgement_did_not_answer": True,
    }
