"""Person / place / role blacklist for the Document Understanding Engine.

Deterministic — used by resolvers to prevent common false positives on the
"person" semantic type (e.g. `Posto Unico`, `Tribuna Rossa`, `Cliente`,
`Emittente` should never surface as a person). Keeping this list here
means the schema-driven pipeline stays generic while still avoiding
domain-obvious mistakes.
"""
from __future__ import annotations

import re
from typing import Iterable

# Case-insensitive: any candidate value whose *lowered* form equals one of
# these strings — or starts with one of them followed by a whitespace/end —
# is rejected from the "person" bucket.
_STOPWORDS = {
    # Ticket / event roles
    "posto", "posto unico", "posto numerato", "settore", "parterre",
    "tribuna", "platea", "gradinata", "curva", "fila", "ingresso",
    "biglietto", "ridotto", "intero", "adulto", "bambino", "under",
    "over", "gate",
    # Legal / invoice roles
    "cliente", "committente", "destinatario", "fornitore", "emittente",
    "cedente", "cessionario", "intestatario", "beneficiario",
    "titolare", "controparte", "contraente", "parte", "sottoscrittore",
    "prestatore", "acquirente", "venditore",
    # Generic
    "totale", "importo", "prezzo", "iva", "imponibile", "scadenza",
    "data", "ora", "orario", "codice", "numero", "riferimento",
    "documento", "originale", "copia", "pagina",
}

# Compiled regex checking "start of value equals a stopword"
_STOPWORD_PREFIX_RE = re.compile(
    r"^(?:" + "|".join(sorted(map(re.escape, _STOPWORDS), key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

# Nome/Cognome heuristic: at least 2 uppercase-prefixed words, each of
# 2..30 letters (accents included). No digits/punctuation/uppercase runs.
_NAME_HEURISTIC = re.compile(
    r"^[A-ZÀÈÉÌÒÙ][a-zà-ù'’]{1,29}"
    r"(?:\s+(?:d[aei]|di|de|van|von|le|la|dal|dello|della|di))*"
    r"(?:\s+[A-ZÀÈÉÌÒÙ][a-zà-ù'’]{1,29}){1,3}$"
)
# Also allow ALL-CAPS names (common in ID cards / passports).
_NAME_ALLCAPS = re.compile(
    r"^[A-ZÀÈÉÌÒÙ]{2,30}(?:[\s\-][A-ZÀÈÉÌÒÙ]{2,30}){1,3}$"
)


def is_person_stopword(value: str) -> bool:
    """True if the candidate value looks like a role/label, not a person."""
    v = (value or "").strip()
    if not v:
        return True
    if _STOPWORD_PREFIX_RE.match(v):
        return True
    return False


def looks_like_person(value: str) -> bool:
    """Heuristic: value looks like an italian first+last name."""
    v = (value or "").strip()
    if not v or len(v) < 3 or len(v) > 60:
        return False
    if is_person_stopword(v):
        return False
    if _NAME_HEURISTIC.match(v):
        return True
    if _NAME_ALLCAPS.match(v):
        return True
    return False


def looks_like_single_name(value: str) -> bool:
    """Weaker heuristic accepting a **single** word — used only when the
    schema field is explicitly a person's first/last name (e.g. ID cards
    where rows are ``Cognome: ROSSI`` and ``Nome: MARIO``)."""
    v = (value or "").strip()
    if not v or len(v) < 2 or len(v) > 30:
        return False
    if is_person_stopword(v):
        return False
    if re.fullmatch(r"[A-ZÀÈÉÌÒÙ][a-zà-ù'’]{1,29}", v):
        return True
    if re.fullmatch(r"[A-ZÀÈÉÌÒÙ]{2,30}", v):
        return True
    # Also accept the 2-word forms
    return looks_like_person(v)


def filter_persons(values: Iterable[str]) -> list[str]:
    seen: dict[str, str] = {}
    for v in values:
        s = (v or "").strip()
        if not s or not looks_like_person(s):
            continue
        key = re.sub(r"\s+", " ", s).lower()
        if key in seen:
            continue
        seen[key] = re.sub(r"\s+", " ", s)
    return list(seen.values())
