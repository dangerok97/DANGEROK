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


#     «CHIAMA ASIA E DILLE CHE ARRIVO TARDI» — CHI E' «ASIA».
# La chat lo ricava dal modello; chi scrive nella schermata della preparazione
# non ha un modello davanti, e prima restava senza contatto. Le parole sono
# quelle: quello che sta fra «chiama» e la prima congiunzione.
_CHI = re.compile(
    r"\bchiam(?:a|are|ami)\s+(?:a\s+)?(.+?)"
    r"(?=\s+e\s+|\s+per\b|\s+dille\b|\s+digli\b|\s+di\b|[,.;!?]|$)",
    re.I,
)


def who_in(testo: str) -> str:
    """Chi va chiamato, dalle parole della richiesta. Vuoto se non si capisce."""
    trovato = _CHI.search(" ".join((testo or "").split()))
    if not trovato:
        return ""
    chi = trovato.group(1).strip(" ,.;:!?\"«»")
    return chi[:120] if len(chi) >= 2 else ""


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
