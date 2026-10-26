"""
How long ordinary things usually take, when the person did not say.

"Ho messo la lavastoviglie" says nothing about the programme. Until now the
only baseline was a web search chosen by the model, and with a weak model the
watch either guessed or stayed silent. These are conservative, commonly
published ranges for household processes; they are a starting point, never a
measurement of this person's machine. Their own past (situations.experience)
or the words they say (situations.stated_time) always come first.

Two uses:
* a cited baseline for the watch's own estimate (capability situation.typical);
* a fallback reminder at the usual end, sent by code, so that the person hears
  something even if the model never answers. It steps aside if the watch
  already announced the result, exactly like a stated moment.

Matching is on whole words in the Situation's own summary and the person's
words. Processes that depend on the weather (things drying outdoors) are not
here: their duration is not a property of the process, and the watch reads
the weather for them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Typical:
    key: str
    label: str
    low: int        # minutes
    high: int       # minutes
    likely: int     # minutes, when the fallback reminder is sent
    source_note: str


# Word patterns are deliberately specific: a false match would send a wrong
# reminder, a missed one only leaves the ordinary watch in charge.
TABLE: tuple[tuple[re.Pattern, Typical], ...] = (
    (re.compile(r"\blavastoviglie\b"),
     Typical("dishwasher", "lavastoviglie", 60, 240, 150,
             "Programmi tipici: rapido 30-60 min, normale 2-3 ore, eco fino a 4 ore.")),
    (re.compile(r"\basciugatrice\b"),
     Typical("dryer", "asciugatrice", 45, 180, 120,
             "Cicli tipici di asciugatura: 1-3 ore secondo carico e programma.")),
    (re.compile(r"\blavatrice\b"),
     Typical("washer", "lavatrice", 30, 210, 120,
             "Programmi tipici: rapido 15-40 min, cotone 1,5-3 ore, eco fino a 3,5 ore.")),
    (re.compile(r"\b(?:acqua|pentola)\b[^.]{0,30}\b(?:bollire|bolle|sul fuoco)\b"),
     Typical("water_boil", "acqua a bollire", 6, 15, 10,
             "Qualche litro d'acqua su un fornello domestico: circa 8-12 minuti.")),
    (re.compile(r"\b(?:moka|caffettiera)\b"),
     Typical("moka", "moka sul fuoco", 3, 8, 5, "Una moka sul fuoco: circa 4-6 minuti.")),
    (re.compile(r"\b(?:butto|buttato|cuoce|cuocendo|calata|calato)\b[^.]{0,20}\bpasta\b|\bpasta\b[^.]{0,20}\b(?:cuoce|in pentola|buttata)\b"),
     Typical("pasta", "pasta in cottura", 7, 14, 10, "Pasta secca: di solito 8-12 minuti, come indicato sulla confezione.")),
    (re.compile(r"\blievit"),
     Typical("rising", "impasto a lievitare", 60, 240, 120,
             "Lievitazione a temperatura ambiente: di solito 1-3 ore, fino al raddoppio.")),
    (re.compile(r"\b(?:in carica|sotto carica|a caricare|ricarica)\b"),
     Typical("charging", "dispositivo in carica", 30, 180, 90,
             "Ricarica di un telefono o un piccolo dispositivo: di solito 1-2 ore.")),
)


def _clean(text: str) -> str:
    return " ".join((text or "").casefold().replace("’", "'").split())


def match(*texts: str) -> Optional[Typical]:
    joined = " . ".join(_clean(t) for t in texts if t)
    if not joined or "?" in joined:
        return None
    for pattern, typical in TABLE:
        if pattern.search(joined):
            return typical
    return None


def describe(t: Typical) -> str:
    def span(m: int) -> str:
        return f"{m} min" if m < 90 else f"{m / 60:.1f} ore".replace(".0 ", " ").replace(".", ",")
    return (f"Durata tipica per {t.label}: tra {span(t.low)} e {span(t.high)}. {t.source_note} "
            "È un valore di riferimento generale, non una misura della situazione di questa persona.")
