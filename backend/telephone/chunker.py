"""
Dove si può tagliare una frase senza rovinarla.

    UNA FRASE SI TAGLIA DOVE UNA PERSONA RESPIREREBBE.

Oggi il core di ORA risponde tutto insieme — misurato, fra la prima parola e
l'ultima passano cinquanta millisecondi — quindi questo file serve a poco. Ma
serve a due cose vere lo stesso.

La prima: **una risposta lunga si dice meglio a pezzi**. Mandarne quattrocento
caratteri in un colpo al fornitore della voce vuol dire aspettare che li
generi tutti prima di sentire la prima parola; mandarne una frase per volta fa
cominciare ORA quasi subito.

La seconda: il giorno che il core streammerà davvero, questo pezzo è già al
suo posto e non si riscrive niente.

Quello che non deve fare, e che è il motivo per cui non basta `split(".")`:

- **non spezzare i numeri.** «4.000 €» tagliato dopo il punto diventa «quattro»
  e poi «zero zero zero euro». «17/09/2026» diventa tre frasi.
- **non spezzare le date e le abbreviazioni.** «alle 11:00 di gio. 17» non ha
  confini dove sembra averne.
- **non lasciare pezzi di due parole.** «Certo.» va bene perché è una frase;
  «alle 11» da solo non lo è.
- **non aspettare un punto che non arriva.** Chi parla a lungo senza
  punteggiatura esiste, e va detto lo stesso.
"""

from __future__ import annotations

import re
from typing import Iterator, List

# Quanto deve essere lungo un pezzo perché valga la pena dirlo da solo.
MIN_CHARS = 12
# Oltre questo si taglia comunque, al confine migliore che si trova.
MAX_CHARS = 240

# I confini, dal più forte al più debole.
_SENTENCE = re.compile(r"(?<=[.!?…])\s+")
_CLAUSE = re.compile(r"(?<=[;:])\s+|(?<=,)\s+(?=(?:e|ma|però|quindi|allora|poi)\b)")

# Cose che sembrano confini e non lo sono.
_PROTECT = (
    # Un punto fra due cifre è un separatore di migliaia o una data.
    (re.compile(r"(?<=\d)\.(?=\d)"), "\x00"),
    # Un punto dentro un'abbreviazione comune.
    (re.compile(r"\b(sig|dott|prof|ing|avv|geom|gio|ven|sab|dom|lun|mar|mer|"
                r"gen|feb|mar|apr|giu|lug|ago|set|ott|nov|dic|ecc|es|n|p|v)\.",
                re.IGNORECASE), lambda m: m.group(0).replace(".", "\x01")),
)


def _protect(text: str) -> str:
    out = text
    for pattern, repl in _PROTECT:
        out = pattern.sub(repl, out)
    return out


def _restore(text: str) -> str:
    return text.replace("\x00", ".").replace("\x01", ".")


def speakable_pieces(text: str) -> List[str]:
    """
    Una risposta, tagliata dove si può dirla.

    Torna sempre almeno un pezzo quando c'è del testo: una frase senza
    punteggiatura è comunque una cosa da dire.
    """
    whole = (text or "").strip()
    if not whole:
        return []
    if len(whole) <= MIN_CHARS:
        return [whole]

    safe = _protect(whole)
    pieces: List[str] = []
    buffer = ""

    for sentence in _SENTENCE.split(safe):
        if not sentence.strip():
            continue
        candidate = (buffer + " " + sentence).strip() if buffer else sentence.strip()

        if len(candidate) <= MAX_CHARS:
            buffer = candidate
            # Una frase intera abbastanza lunga si può già dire.
            if len(buffer) >= MIN_CHARS and _ends_cleanly(buffer):
                pieces.append(_restore(buffer))
                buffer = ""
            continue

        # Troppo lunga: si prova a tagliarla dove respirerebbe una persona.
        if buffer:
            pieces.append(_restore(buffer))
            buffer = ""
        for clause in _split_long(sentence.strip()):
            pieces.append(_restore(clause))

    if buffer:
        pieces.append(_restore(buffer))

    # Un pezzo troppo corto non vive da solo: si attacca al precedente.
    joined: List[str] = []
    for piece in pieces:
        if joined and len(piece) < MIN_CHARS:
            joined[-1] = (joined[-1] + " " + piece).strip()
        else:
            joined.append(piece)
    return [p for p in joined if p.strip()]


def _ends_cleanly(text: str) -> bool:
    return bool(text) and text.rstrip()[-1] in ".!?…"


def _split_long(sentence: str) -> Iterator[str]:
    """Una frase lunga, tagliata alle virgole utili o, se serve, alle parole."""
    parts = [p for p in _CLAUSE.split(sentence) if p and p.strip()]
    buffer = ""
    for part in parts:
        candidate = (buffer + " " + part).strip() if buffer else part.strip()
        if len(candidate) <= MAX_CHARS:
            buffer = candidate
            continue
        if buffer:
            yield buffer
        buffer = part.strip()
        while len(buffer) > MAX_CHARS:
            # Nessun confine: si taglia fra due parole, mai dentro una.
            cut = buffer.rfind(" ", 0, MAX_CHARS)
            if cut <= 0:
                cut = MAX_CHARS
            yield buffer[:cut].strip()
            buffer = buffer[cut:].strip()
    if buffer:
        yield buffer
