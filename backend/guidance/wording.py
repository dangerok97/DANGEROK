"""
Two things a question is not allowed to be.

Both are deterministic checks over text that is about to reach a person, and
both exist because the reasoning is free to write whatever it likes and the
product is not. They decide nothing about *what* is asked — that is settled
long before — only whether the sentence the model wrote may stand as it is.

**It may not hand the process back.** "Su cosa vuoi concentrarti?" is not a
question about the person's life; it is ORA asking to be told how to work. The
person decides what they want — mutuo or risparmi, accept or decline, which
date, what budget. ORA decides which step comes next and what that step needs.
A turn that ends by offering a choice of steps has moved the plan back onto
the person, which is the one thing guidance exists to stop.

**It may not arrive in another language.** The product speaks Italian. A
question composed from the variables is Italian by construction; one written by
the reasoning is Italian almost always, and when it is not it must not be shown
because it was written for a different reader.

Both are word-level and domain-neutral: no topic, no vertical, nothing that
would have to be extended for a new kind of goal.
"""

from __future__ import annotations

import re
from typing import Sequence

# ---------------------------------------------------------------------------
# Meta-choice
#
# What is matched is the *process* vocabulary — proceeding, focusing, starting,
# going deeper, dealing with — asked as a choice. Substance questions survive
# untouched: "preferisci tasso fisso o variabile?" names no step, and neither
# does "vuoi che lo inserisca in agenda?", which is consent for an action ORA
# has already chosen and must keep asking.
# ---------------------------------------------------------------------------
_PROCESS = r"(?:proceder|procedi|proced|concentr|approfond|partir|inizi|comincia|affront|occupar|impost|analizz|valut|confront|esplor|guard|ved)"

_META_CHOICE = [
    # "come vuoi procedere?", "come preferisci procedere?"
    rf"\bcome\s+(?:vuoi|preferisci|vorresti|desideri)\s+\w*\s*{_PROCESS}",
    # "su cosa vuoi concentrarti?", "su quale aspetto vuoi concentrarti?"
    rf"\b(?:su\s+)?(?:cosa|che\s+cosa|quale|quali|quale\s+aspetto|dove)\b[^?]{{0,60}}\b(?:vuoi|preferisci|vorresti|desideri)\b[^?]{{0,40}}{_PROCESS}",
    # "da dove vuoi partire?", "da cosa iniziamo?"
    rf"\bda\s+(?:dove|cosa|quale)\b[^?]{{0,40}}(?:{_PROCESS}|vuoi|preferisci)",
    # "vuoi che approfondiamo X o preferisci Y?" — a choice between steps
    rf"\b(?:vuoi|preferisci|vorresti|ti\s+va)\b[^?]{{0,80}}{_PROCESS}\w*[^?]{{0,80}}\b(?:oppure|o\s+preferisci|o\s+vuoi|o\s+ti)\b",
    # "vuoi che approfondiamo il finanziamento o le scadenze?" — the same
    # choice-of-step with a bare "o" instead of "oppure", which is how the
    # model most often writes it.
    rf"\b(?:vuoi|preferisci|vorresti|possiamo|procediamo|posso\s+aiutarti|ti\s+aiuto)\b[^?]{{0,40}}{_PROCESS}\w*[^?]{{0,100}}\s+o\s+[^?]{{0,60}}",
    # "preferisci concentrarti su X oppure Y?"
    rf"\b(?:preferisci|vuoi)\b[^?]{{0,20}}{_PROCESS}\w*[^?]{{0,80}}\boppure\b",
    # "…, oppure preferisci valutare le opzioni?" — the same offer with
    # the alternative leading instead of trailing.
    rf"\boppure\b[^?]{{0,20}}(?:preferisci|vuoi|vorresti)\b[^?]{{0,20}}{_PROCESS}",
    # "c'è qualche aspetto in particolare su cui vuoi concentrarti?"
    rf"\b(?:aspett|part|punt|argoment|tem|are|fas|passagg)[aeio]\b[^?]{{0,90}}\b(?:vuoi|preferisci|desideri|vorresti)\b[^?]{{0,40}}{_PROCESS}",
    # "su cui vuoi concentrarti?", "su cosa preferisci procedere?"
    rf"\bsu\s+(?:cui|cosa|quale|quali)\b[^?]{{0,40}}\b(?:vuoi|preferisci|desideri|vorresti)\b[^?]{{0,40}}{_PROCESS}",
    # "cosa vuoi fare adesso?", "cosa preferisci fare prima?"
    r"\b(?:cosa|che\s+cosa)\s+(?:vuoi|preferisci|vorresti)\s+fare\b[^?]{0,30}\b(?:adesso|ora|prima|per\s+prim)",
    # English mirrors, for the same reason the language guard exists.
    r"\b(?:what|where)\s+(?:would\s+you\s+like|do\s+you\s+want)\s+to\s+(?:start|focus|begin|proceed)",
    r"\bhow\s+(?:would\s+you\s+like|do\s+you\s+want)\s+to\s+proceed\b",
]

_META_RE = [re.compile(p, re.IGNORECASE) for p in _META_CHOICE]


def is_meta_choice(text: str) -> bool:
    """
    Does this hand the choice of *step* back to the person?

    Only sentences that ask something do: a statement describing what ORA will
    do next is exactly what should replace a meta-choice, and must not be
    mistaken for one.
    """
    t = (text or "").strip()
    if "?" not in t:
        return False
    return any(rx.search(t) for rx in _META_RE)


# ---------------------------------------------------------------------------
# Language
#
# Function words, not topic words: the vocabulary a sentence cannot avoid. A
# question can be about a mortgage in either language, but it cannot be English
# without "the", "you", "your", "do", "have", "what", "is".
# ---------------------------------------------------------------------------
_EN = {
    "the", "you", "your", "yours", "do", "does", "did", "have", "has", "what",
    "when", "which", "would", "could", "should", "please", "are", "is", "will",
    "and", "for", "with", "about", "need", "want", "already", "before",
}
_IT = {
    "il", "lo", "la", "i", "gli", "le", "un", "una", "che", "di", "del",
    "della", "per", "con", "hai", "sei", "quale", "quali", "qual", "quando",
    "vuoi", "preferisci", "mi", "ti", "serve", "servono", "già", "come",
    "cosa", "non", "sono", "è", "da", "in", "su", "al", "alla", "dal",
}


def looks_english(text: str) -> bool:
    """
    Was this written for a different reader?

    Counting function words on both sides rather than detecting one: a single
    English loanword in an Italian sentence — "budget", "meeting" — must not
    make it foreign, and a genuinely English sentence loses this comparison by
    a wide margin.
    """
    words = re.findall(r"[a-zàèéìòùA-ZÀÈÉÌÒÙ']+", (text or "").lower())
    if len(words) < 4:
        return False
    en = sum(1 for w in words if w in _EN)
    it = sum(1 for w in words if w in _IT)
    return en >= 2 and en > it


def first_sentence_words(labels: Sequence[str]) -> str:
    """Small helper kept here so callers do not re-implement list phrasing."""
    items = [l.strip() for l in labels if l and l.strip()]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} e {items[-1]}"

# ---------------------------------------------------------------------------
# Description instead of movement
#
# The failure this catches is quieter than a meta-choice and worse: ORA
# reconstructs the path correctly, says what the next step would be, and stops.
# Nothing was done and nothing was asked, so the person is left to work out
# what ORA needs and volunteer it — which is the arrangement guidance exists to
# end. Recognising it needs no topic knowledge: it is the vocabulary of a plan
# being narrated, plus the absence of anything happening.
# ---------------------------------------------------------------------------
_PLAN_TALK = [
    r"\b(?:il\s+)?(?:prossim[oi]|prim[oi]|success[io]v[oi])\s+(?:pass[oi]|tapp[ae]|step|fas[ei])",
    r"\bpass[oi]\s+(?:successiv[oi]|precedent[ei])",
    r"\b(?:le\s+)?(?:prossime|successive)\s+(?:tappe|fasi|scadenze)",
    r"\bho\s+(?:impostato|aggiornato|predisposto)\s+(?:il\s+)?(?:piano|percorso)",
    r"\b(?:il\s+)?piano\s+(?:prevede|comprende|include)",
    r"\bora\s+(?:si\s+)?(?:procede|passa)\s+(?:a|con)",
    r"\b(?:dovrai|dovrei|bisogner[àa]|occorrer[àa])\b",
]
_PLAN_RE = [re.compile(p, re.IGNORECASE) for p in _PLAN_TALK]


def describes_a_plan(text: str) -> bool:
    """Is this a narration of what would happen rather than something happening?"""
    t = (text or "").strip()
    if not t:
        return False
    return any(rx.search(t) for rx in _PLAN_RE)


# ---------------------------------------------------------------------------
# A conclusion about this person
#
# "Hai ottimi requisiti", "questa soluzione è adatta a te" are claims about
# somebody's situation, and they are only worth anything if what they rest on
# is actually known. Said from three facts and an inference they are a guess
# wearing a recommendation's clothes. The check is second-person and
# evaluative, never topical: it does not know what a mortgage is.
# ---------------------------------------------------------------------------
_PERSONAL_CLAIM = [
    r"\bhai\s+(?:ottim[ie]|buon[ie]|tutti\s+i|i)\s+requisiti",
    r"\b(?:sei|risulti)\s+(?:idone[oa]|eleggibile|in\s+regola)\b",
    r"\bpuoi\s+permetter(?:te|ti)l[oa]\b",
    r"\b(?:adatt[oa]|indicat[oa]|compatibil[ei]|giust[oa]|migliore?)\s+(?:(?:per|a)\s+te|al\s+tuo\s+(?:profilo|caso))",
    r"\b(?:le\s+)?miglior[ie]\s+(?:opzioni|soluzioni|offerte|condizioni)\s+per\s+te\b",
    r"\bti\s+conviene\b",
    r"\bnel\s+tuo\s+caso\s+(?:la\s+scelta|l'opzione)\s+miglior",
]
_CLAIM_RE = [re.compile(p, re.IGNORECASE) for p in _PERSONAL_CLAIM]


def claims_about_the_person(text: str) -> bool:
    """Did the turn conclude something about this person's own situation?"""
    return any(rx.search((text or "")) for rx in _CLAIM_RE)

