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
    # Voice transcripts sometimes leave a discourse marker attached to a
    # relationship: "chiama la mia ragazza quindi e dille...". "Quindi" is
    # not a contact name there. Keep the relationship phrase so the contacts
    # resolver can map it to the actual person.
    if re.search(
        r"(?i)\b(?:mia|mio)\s+(?:ragazza|ragazzo|fidanzata|fidanzato|moglie|marito|compagna|compagno)\s+quindi$",
        chi,
    ):
        chi = re.sub(r"(?i)\s+quindi$", "", chi).strip()
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


#     «DILLE CHE LA AMO» SI CONSEGNA COME «FRANCESCO MI HA CHIESTO DI DIRTI CHE TI AMA».
# 7/11: la chat rileggeva il messaggio come «la amo», e sembrava che ORA
# l'avrebbe detto così, in prima persona. Il messaggio è scritto da chi lo
# manda e parla di chi lo riceve in terza persona: a lei va detto in seconda,
# attribuito a lui. Code, not judgement: si trasforma solo la forma più
# comune (un pronome per lei, un verbo in prima persona, il resto neutro);
# per tutto il resto `None`, e si citano le parole fra virgolette.
_TERZA = {
    "sono": "è", "ho": "ha", "vado": "va", "faccio": "fa", "posso": "può", "devo": "deve",
    "so": "sa", "sto": "sta", "vengo": "viene", "voglio": "vuole", "esco": "esce",
    "do": "dà", "dico": "dice", "tengo": "tiene", "torno": "torna", "rimango": "rimane",
    "resto": "resta", "muoio": "muore", "salgo": "sale", "scelgo": "sceglie",
}
_PER_LEI = {"la": "ti", "lo": "ti", "le": "ti", "gli": "ti"}
_NON_NEUTRE = {
    "io", "me", "mi", "mio", "mia", "miei", "mie", "noi", "ci", "ce", "nostro", "nostra",
    "tu", "te", "ti", "tuo", "tua", "tuoi", "tue", "lei", "lui", "sua", "suo", "suoi", "sue",
    "la", "lo", "le", "gli", "l", "ne", "si", "se", "vi", "voi", "che", "perché", "quando",
    "ma", "e", "o", "non", "anche",
}


_ARE = {
    "amo": "ama", "adoro": "adora", "arrivo": "arriva", "penso": "pensa", "aspetto": "aspetta",
    "chiamo": "chiama", "passo": "passa", "ringrazio": "ringrazia", "abbraccio": "abbraccia",
    "bacio": "bacia", "porto": "porta", "compro": "compra", "lavoro": "lavora", "ritardo": "ritarda",
    "cerco": "cerca", "richiamo": "richiama", "scrivo": "scrive", "leggo": "legge",
    "prendo": "prende", "sento": "sente", "vedo": "vede", "credo": "crede", "parto": "parte",
    "finisco": "finisce", "capisco": "capisce", "perdono": "perdona", "rispetto": "rispetta",
    "stimo": "stima", "ammiro": "ammira", "sposo": "sposa", "festeggio": "festeggia",
}


def as_said_to(message: str, sender: str) -> "str | None":
    """
    Il messaggio come lo si dice a chi lo riceve: «<sender> mi ha chiesto di
    dirti che ti ama». `None` quando la frase non è della forma semplice.
    """
    words = re.findall(r"[^\W\d_]+'?|\d+(?:[.:]\d+)?", " ".join((message or "").split()))
    nome = (sender or "").split()[0] if (sender or "").strip() else ""
    if not words or not nome:
        return None
    out: list[str] = []
    i = 0
    first = words[0].casefold()
    if first in _PER_LEI or first == "l'":
        out.append(_PER_LEI.get(first, "ti"))
        i = 1
    if i >= len(words):
        return None
    verbo = words[i].casefold()
    terza = _TERZA.get(verbo) or _ARE.get(verbo)
    if not terza:
        return None
    out.append(terza)
    for w in words[i + 1:]:
        lw = w.casefold().rstrip("'")
        if lw in _NON_NEUTRE:
            return None
        if re.fullmatch(r"\w+r(?:la|lo|le|gli)", lw):
            out.append(re.sub(r"(?:la|lo|le|gli)$", "ti", w))
            continue
        out.append(w)
    return f"{nome} mi ha chiesto di dirti che {' '.join(out)}"
