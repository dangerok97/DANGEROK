"""
Che giorno della settimana è una data.

    UNA COSA CHE IL CODICE SA NON SI FA DEDURRE A UN MODELLO.

Il payload di ORA ha sempre portato la data di oggi e nient'altro:
`today: "2026-09-13"`. Da lì al giorno della settimana c'è un calcolo che un
calendario fa in un microsecondo e che un modello linguistico **indovina**.

Misurato, chiedendo sei volte «che giorno della settimana è oggi?» con la
stessa identica data nel payload:

    ministral-14b : martedì, martedì, lunedì
    ministral-8b  : mercoledì, mercoledì, martedì
    gemini2       : domenica  (giusto)

Sei risposte, sei sicurezze, un giorno diverso quasi ogni volta. E non è una
domanda di nicchia: «che giorno è oggi» e «che impegni ho domani» sono le due
cose che si chiedono di più a voce.

    NON DIPENDE DALLA LINGUA DEL SISTEMA.

I nomi stanno scritti qui, in inglese come il resto del payload, e non
arrivano da `strftime("%A")`: quello segue il locale del processo, e un
backend avviato in italiano comincerebbe a spedire «domenica» dove il resto
del payload dice «Sunday». Un valore che cambia con una variabile d'ambiente
non è deterministico.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Union

# `date.weekday()` conta da lunedì, e questo elenco comincia da lunedì.
_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def weekday_name(when: Union[date, datetime]) -> str:
    """Il nome inglese del giorno della settimana. Sempre lo stesso, ovunque."""
    if isinstance(when, datetime):
        when = when.date()
    return _NAMES[when.weekday()]
