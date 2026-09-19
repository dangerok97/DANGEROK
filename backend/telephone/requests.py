"""
Leggere una richiesta scritta: c'è una frase da portare a qualcuno?

Sta da sola, e non conosce né la missione né il runtime: la usano la chat,
per capire che cosa le si chiede, e la missione, per decidere che tipo di
telefonata è. Due lettori, una regola sola.
"""

from __future__ import annotations

import re

#     «DILLE CHE…» E' UN MESSAGGIO. «DIGLI DI SPOSTARE» NO.
# La differenza sta in una parola: dopo «dille» viene «che» quando c'è una
# frase da portare, e «di» quando c'è una cosa da fare. Si guarda solo quello.
_A_MESSAGE = re.compile(
    r"\b(?:dille|digli|dirle|dirgli|diglielo|riferisci(?:le|gli)?|"
    r"avvisa(?:la|lo)?|comunica(?:le|gli)?|fagli sapere|falle sapere)\s+che\b",
    re.IGNORECASE,
)


def is_a_message(testo: str) -> bool:
    """Se la richiesta è portare una frase a qualcuno."""
    return bool(_A_MESSAGE.search(testo or ""))


def the_message_in(testo: str) -> str:
    """
    La frase da portare, con le parole di chi l'ha chiesta.

    «Chiama Giulia e dille che la amo» → «la amo». Non si riscrive niente:
    è la versione che fa fede.
    """
    trovato = _A_MESSAGE.search(testo or "")
    if not trovato:
        return ""
    return (testo or "")[trovato.end():].strip().rstrip(".!").strip()[:400]
