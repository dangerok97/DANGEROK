"""
In che lingua è stata detta una frase — quando lo si può dire.

    «SÌ» NON È UNA LINGUA.

Misurato sul vero: a metà di una telefonata italiana la controparte è stata
trascritta in portoghese — «Sim, ver qual é a data de disponibilidade». Una
parola sola, un nome proprio, un «ok» non dicono niente sulla lingua di una
frase, e un rilevatore che li contasse griderebbe alla deriva a ogni «sì».

Quindi qui si decide solo quando c'è abbastanza testo, e la risposta per tutto
il resto è `None`: non «italiano», non «straniero» — «non si può dire».

    E NON SI CHIEDE A UN MODELLO.

Parole funzionali contate, deterministico, niente rete. Serve a una cosa sola:
scrivere nel resoconto della telefonata che la lingua è scivolata, e dove. Non
interrompe niente e non corregge niente — una parola straniera non chiude una
telefonata.
"""

from __future__ import annotations

import re
from typing import Dict, FrozenSet, Optional

# Le parole brevi e frequenti che una lingua usa e le altre no. Si sceglie
# apposta chi distingue: «de», «a», «e» stanno in troppe lingue per servire.
PAROLE: Dict[str, FrozenSet[str]] = {
    "it": frozenset({
        "il", "che", "non", "per", "sono", "della", "questo", "anche", "come",
        "gli", "ci", "mi", "ho", "sì", "è", "nel", "alle", "del", "una",
        "vorrei", "grazie", "buongiorno", "perfetto", "allora", "quindi",
        "appuntamento", "confermo", "arrivederci", "posso", "orario", "va",
    }),
    "pt": frozenset({
        "não", "sim", "você", "qual", "uma", "obrigado", "obrigada", "então",
        "também", "ele", "ela", "isso", "está", "estou", "para", "com", "ver",
        "data", "disponibilidade", "bom", "dia", "tudo", "muito", "é", "são",
    }),
    "es": frozenset({
        "el", "los", "las", "que", "sí", "está", "estoy", "gracias", "pero",
        "también", "usted", "muy", "hola", "vale", "bueno", "entonces", "cita",
    }),
    "en": frozenset({
        "the", "and", "you", "is", "are", "yes", "thanks", "thank", "what",
        "this", "that", "with", "have", "will", "can", "hello", "okay", "please",
    }),
    "fr": frozenset({
        "le", "les", "est", "oui", "merci", "vous", "je", "pas", "avec", "pour",
        "bonjour", "c'est", "très", "rendez-vous",
    }),
    "de": frozenset({
        "der", "die", "das", "und", "ist", "ja", "danke", "nicht", "sie", "ich",
        "mit", "guten", "tag", "bitte", "termin",
    }),
}

# Sotto queste parole non si giudica. Tre è il minimo per non contare un
# «sì grazie» come una frase.
MINIMO_PAROLE = 3
# Quante parole funzionali servono, e di quanto una lingua deve staccare le
# altre, per dire che una frase è in quella lingua.
MINIMO_INDIZI = 2


def guess(testo: str) -> Optional[str]:
    """
    La lingua della frase, o `None` se non si può dire con onestà.
    """
    parole = [p for p in re.split(r"[^\wàèéìòóùç'-]+", (testo or "").lower()) if p]
    if len(parole) < MINIMO_PAROLE:
        return None
    punti = {
        lingua: sum(1 for p in parole if p in vocabolario)
        for lingua, vocabolario in PAROLE.items()
    }
    ordinati = sorted(punti.items(), key=lambda kv: -kv[1])
    (prima, quanti), (_, secondi) = ordinati[0], ordinati[1]
    if quanti < MINIMO_INDIZI or quanti <= secondi:
        return None
    return prima


def drifted(testo: str, attesa: str) -> Optional[str]:
    """
    La lingua in cui è scivolata la frase, se è scivolata. Altrimenti `None`.

    Solo quando la frase è abbastanza lunga da dirlo e dice un'altra lingua:
    un «ok», un nome, una frase ambigua non sono una deriva.
    """
    trovata = guess(testo)
    base = (attesa or "it").split("-")[0].lower()
    if trovata is None or trovata == base:
        return None
    return trovata
