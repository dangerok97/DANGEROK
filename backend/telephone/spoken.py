"""
La stessa frase, detta invece che scritta.

    STESSO SIGNIFICATO, ALTRA FORMA.

ORA scrive per uno schermo. Al telefono quello che ha scritto viene letto ad
alta voce, e allora si sente tutto quello che sullo schermo non si vedeva:

    «Domani, domenica 14 settembre 2026, hai in programma l'evento
    "QA ORA — latenza" dalle 16:00 alle 17:00.»

Letta così suona come un annuncio di stazione. Nessuno, al telefono, dice
«sedici zero zero», non pronuncia le virgolette, non mette un trattino lungo
in mezzo a una frase e non detta un indirizzo web.

    QUI NON SI CAMBIA QUELLO CHE ORA HA DECISO DI DIRE.

Non si tolgono informazioni, non si aggiunge niente, non si ammorbidisce
niente. Si cambia la forma dei pezzi che esistono solo perché una cosa va
letta. Quello che resta è la stessa frase, in bocca a una persona.
"""

from __future__ import annotations

import re

# Le ore, senza articolo: l'articolo dipende da cosa viene prima, ed è quello
# che rendeva «dalle le quattro» invece di «dalle quattro».
_ORE = (
    "mezzanotte", "una", "due", "tre", "quattro", "cinque", "sei",
    "sette", "otto", "nove", "dieci", "undici", "mezzogiorno",
)

# I minuti che hanno un modo di dirsi. Gli altri si leggono come numeri, che
# è esattamente quello che fa chi parla.
_MINUTI = {0: "", 15: " e un quarto", 30: " e mezza", 45: " e tre quarti"}

_QUANDO = (
    (5, 12, " di mattina"),
    (13, 17, " del pomeriggio"),
    (18, 21, " di sera"),
    (22, 23, " di notte"),
    (0, 4, " di notte"),
)
_PARTI = (" di mattina", " del pomeriggio", " di sera", " di notte")

_MESI = (
    "", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
)

#     «A MEZZOGIORNO», NON «ALLE MEZZOGIORNO».
# Per ogni preposizione ci sono tre forme: davanti a mezzogiorno e mezzanotte,
# davanti all'una, e davanti a tutto il resto. Sbagliarne una si sente subito.
_PREPOSIZIONI = {
    "alle": ("a", "all'", "alle"),
    "all'": ("a", "all'", "alle"),
    "alla": ("a", "all'", "alle"),
    "dalle": ("da", "dall'", "dalle"),
    "dall'": ("da", "dall'", "dalle"),
    "dalla": ("da", "dall'", "dalle"),
    "le": ("", "l'", "le"),
    "entro le": ("entro", "entro l'", "entro le"),
    "entro l'": ("entro", "entro l'", "entro le"),
    "verso le": ("verso", "verso l'", "verso le"),
    "verso l'": ("verso", "verso l'", "verso le"),
    "fino alle": ("fino a", "fino all'", "fino alle"),
    "fino all'": ("fino a", "fino all'", "fino alle"),
}
_PREP_RE = "|".join(sorted((re.escape(p) for p in _PREPOSIZIONI), key=len, reverse=True))

_TIME = re.compile(
    rf"\b(?:(?P<prep>{_PREP_RE})\s*)?(?P<h>[0-2]?\d)[:.](?P<m>[0-5]\d)\b",
    re.IGNORECASE,
)
#     LA FORBICE SI DICE UNA VOLTA SOLA.
# Si lavora sul testo già reso a voce, non sulle cifre: si cercano due orari
# che cadono nello stesso momento della giornata, separati soltanto da
# «alle». Il riferimento all'indietro impone che il momento sia lo stesso —
# «dalle nove di mattina alle sei di sera» resta intero, perché non lo è.
_RANGE = re.compile(
    r"\b(dalle|dall'|tra le|fra le|da)\s*"
    r"([a-zà-ù'0-9 ]+?)"
    r"( di mattina| del pomeriggio| di sera| di notte)\s+"
    r"(alle|all'|a|e le)\s*"
    r"([a-zà-ù'0-9 ]+?)\3\b",
    re.IGNORECASE,
)
_TWICE = re.compile(
    r"(di notte|di mattina|del pomeriggio|di sera)(?:,?\s+(?:di notte|di mattina|"
    r"del pomeriggio|di sera))+",
)
#     «ALLE SEDICI» LO DICE UN ALTOPARLANTE, NON UNA PERSONA.
# Quando il core scrive già le ore in lettere, le scrive sulle ventiquattro:
# corretto, e da annuncio di stazione. Al telefono si dicono sulle dodici, col
# momento della giornata. Si tocca solo quello che viene dopo una
# preposizione oraria, così «i sedici euro» resta quello che è.
_ORE_SCRITTE = {
    "tredici": 13, "quattordici": 14, "quindici": 15, "sedici": 16,
    "diciassette": 17, "diciotto": 18, "diciannove": 19, "venti": 20,
    "ventuno": 21, "ventidue": 22, "ventitre": 23, "ventitré": 23,
}
_ORA_SCRITTA = re.compile(
    rf"\b(?P<prep>{_PREP_RE})\s+(?P<ora>" + "|".join(_ORE_SCRITTE) + r")\b"
    r"(?P<coda>\s+e\s+(?:un quarto|mezza|tre quarti))?",
    re.IGNORECASE,
)
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_URL = re.compile(
    r"(?:\b(?:su|a|in|al|allo|alla|presso|qui|qua)\s+)?(?:https?://\S+|\bwww\.\S+)",
    re.IGNORECASE,
)
_MARKDOWN = re.compile(r"(\*\*|__|\*|_|`|~~)")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_BULLET = re.compile(r"^\s*[-–—•*]\s+", re.MULTILINE)
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)
_QUOTES = re.compile(r"[«»\"“”„]")
_DASH = re.compile(r"\s+[–—]\s+")
_PARENS = re.compile(r"\s*\(([^()]{1,120})\)")
_ELISION = re.compile(r"\b(il|Il)\s+(8|11)\b")
_SPACES = re.compile(r"[ \t]{2,}")
_BLANK = re.compile(r"\n{2,}")


def _daypart(hour: int) -> str:
    for lo, hi, word in _QUANDO:
        if lo <= hour <= hi:
            return word
    return ""


def _bare_time(hour: int, minute: int) -> str:
    """Un orario senza articolo: «quattro del pomeriggio», «mezzogiorno»."""
    if hour in (0, 12) and minute == 0:
        return _ORE[0] if hour == 0 else _ORE[12]
    said = _ORE[hour % 12] if hour % 12 else _ORE[12]
    return said + _MINUTI.get(minute, f" e {minute}") + _daypart(hour)


def _with_article(prep: str, bare: str) -> str:
    special = bare.startswith(("mezzogiorno", "mezzanotte"))
    una = bare.startswith("una")
    which = 0 if special else (1 if una else 2)
    form = _PREPOSIZIONI.get(prep.lower().strip(), ("", "l'", "le"))[which]
    if not form:
        return bare
    return form + ("" if form.endswith("'") else " ") + bare


def _times(text: str) -> str:
    def one(m):
        hour, minute = int(m.group("h")), int(m.group("m"))
        if hour > 23:
            return m.group(0)
        said = _with_article(m.group("prep") or "", _bare_time(hour, minute))
        # «Alle 12:00 hai pranzo» comincia una frase: «a mezzogiorno» deve
        # cominciarla anche lui.
        if m.group(0)[:1].isupper() and said[:1].islower():
            said = said[0].upper() + said[1:]
        return said

    said = _TIME.sub(one, text)

    def written(m):
        hour = _ORE_SCRITTE[m.group("ora").lower()]
        bare = _ORE[hour % 12] + (m.group("coda") or "") + _daypart(hour)
        out = _with_article(m.group("prep"), bare)
        if m.group(0)[:1].isupper() and out[:1].islower():
            out = out[0].upper() + out[1:]
        return out

    said = _ORA_SCRITTA.sub(written, said)

    #     «ALL'UNA DI NOTTE DI NOTTE» NO.
    # Chi ha scritto la frase il momento della giornata l'aveva già detto.
    said = _TWICE.sub(r"\1", said)

    #     «DALLE QUATTRO DEL POMERIGGIO ALLE CINQUE DEL POMERIGGIO» NO.
    # Quando due orari stanno in una forbice e cadono nello stesso momento
    # della giornata, quel momento si dice una volta sola, alla fine — come
    # fa chiunque.
    def tidy(m):
        opens, first, when, joins, second = m.groups()
        gap_a = "" if opens.endswith("'") else " "
        gap_b = "" if joins.endswith("'") else " "
        return (
            f"{opens}{gap_a}{first.strip()} {joins}{gap_b}{second.strip()}{when}"
        )

    return _RANGE.sub(tidy, said)


def _dates(text: str) -> str:
    def one(m):
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not 1 <= month <= 12:
            return m.group(0)
        return f"{day} {_MESI[month]} {year}"

    return _ISO_DATE.sub(one, text)


def for_the_ear(text: str) -> str:
    """
    La frase pronta per essere detta.

    Se dopo la pulizia non resta niente, torna quello che c'era: meglio una
    frase scritta male detta male, che una telefonata in cui ORA tace senza
    che nessuno sappia perché.
    """
    if not text or not text.strip():
        return text or ""

    said = text

    #     GLI INDIRIZZI WEB NON SI DICONO A VOCE.
    # Nessuno detta un URL al telefono e chi ascolta non può cliccarlo. Se
    # ne va anche la preposizione che lo reggeva, se no resta una frase
    # monca: «puoi vedere il dettaglio su» e poi niente.
    said = _URL.sub("", said)

    # Quello che esiste solo perché una cosa va letta.
    said = _HEADING.sub("", said)
    said = _BULLET.sub("", said)
    said = _NUMBERED.sub("", said)
    said = _MARKDOWN.sub("", said)
    said = _QUOTES.sub("", said)

    # Un trattino lungo è una pausa che a voce si fa con una virgola; una
    # parentesi è un inciso, e a voce gli incisi stanno fra due virgole.
    said = _DASH.sub(", ", said)
    said = _PARENS.sub(r", \1,", said)

    # I simboli che si leggono come parole.
    said = said.replace("€", "euro").replace("%", " per cento")
    said = said.replace("&", " e ")

    said = _dates(said)
    said = _times(said)
    said = _ELISION.sub(lambda m: ("l'" if m.group(1) == "il" else "L'") + m.group(2), said)

    # Un elenco andato a capo diventa una frase: a voce non esistono i punti
    # elenco, esistono le pause.
    said = _BLANK.sub(". ", said)
    said = said.replace("\n", ", ")

    said = _SPACES.sub(" ", said)
    said = re.sub(r"\s+([,.;:!?])", r"\1", said)
    said = re.sub(r"([:;])\s*,", r"\1", said)
    said = re.sub(r",\s*,+", ",", said)
    said = re.sub(r"\.\s*\.+", ".", said)
    said = re.sub(r",\s*\.", ".", said)
    said = _SPACES.sub(" ", said)
    said = said.strip().strip(",").strip()

    return said or text
