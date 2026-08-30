"""
A long answer must arrive whole.

The failure this prevents was real and shipped: ORA weighed two internet
offers, recommended one, and started the clause that carried the condition —
"…con un esborso iniziale quasi identico. Se invece sei sicuro di restare" —
and stopped there. Persisted at exactly 799 characters. It was not the model
running out of room; it was an `[:800]` in our own code, applied in three
places, cutting mid-word.

A ceiling is fine. A ceiling that lands mid-sentence is not: it reads as a
bug, and in a recommendation it removes precisely the half that says when the
advice does not hold.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from conversation_engine.ai_core.governance import (  # noqa: E402
    MAX_USER_TEXT_CHARS,
    _sanitize_copy,
    whole_sentences,
)
from conversation_engine.ai_core.loop import _compose_user_text  # noqa: E402
from conversation_engine.ai_core.models import CognitiveDecision  # noqa: E402


def _long_answer() -> str:
    """Over 800 characters, ending on a conclusion that must survive."""
    body = (
        "Offerta A costa 29,90 euro al mese piu 39 euro di attivazione, quindi "
        "nei primi dodici mesi spendi 397,80 euro in tutto. "
    ) * 8
    return body + "Se invece sei sicuro di restare almeno due anni, conviene A."


def test_a_long_answer_keeps_its_conclusion():
    text = _long_answer()
    assert len(text) > 800, "il caso di prova non supera il vecchio cap"

    kept = _sanitize_copy(text)
    assert kept == text
    assert kept.endswith("conviene A."), "la conclusione e' stata tagliata via"
    assert len(kept) > 800


def test_the_same_answer_survives_composition():
    text = _long_answer()
    decision = CognitiveDecision(
        response_mode="answer",
        reasoning_status="enough_information",
        message_to_user=text,
    )
    composed = _compose_user_text(decision)
    assert composed.endswith("conviene A.")
    assert len(composed) > 800


def test_no_answer_is_ever_cut_mid_word():
    """
    The property, at every length around the ceiling. Whatever comes out is
    either the whole thing or something that ends where a sentence ended.
    """
    sentence = "Questa e una frase intera di lunghezza nota e regolare. "
    for repeats in (1, 15, 70, 90, 200):
        text = (sentence * repeats).strip()
        out = whole_sentences(text)
        assert out, "una risposta e' stata svuotata"
        assert out.endswith("."), f"tagliata a meta' frase: {out[-40:]!r}"
        assert text.startswith(out)


def test_the_ceiling_is_high_enough_to_be_about_runaway_output():
    """
    Not a new low limit dressed up. It is there so nothing unbounded reaches a
    person or the database, and ORA's real answers are nowhere near it.
    """
    assert MAX_USER_TEXT_CHARS >= 3000


def test_a_ceiling_that_would_have_to_butcher_a_sentence_is_not_enforced():
    """
    One enormous sentence with no boundary to fall back on: better whole than
    beheaded. This is the case that would otherwise reintroduce the bug.
    """
    runaway = "parola " * 2000
    out = whole_sentences(runaway)
    assert out == runaway
    assert not out.endswith("paro"), "tagliata a meta' parola"


def test_the_old_cap_is_gone_from_the_places_it_was_applied():
    for name in ("governance.py", "loop.py"):
        source = (Path(_BACKEND) / "conversation_engine" / "ai_core" / name).read_text(
            encoding="utf-8"
        )
        code = "\n".join(
            line for line in source.splitlines() if not line.strip().startswith("#")
        )
        assert "[:800]" not in code, f"{name} taglia ancora a 800 caratteri"


def test_the_question_half_of_an_ask_is_not_lost_either():
    """
    `ask` composes preamble + question and the old cap fell on the join, so a
    long preamble could swallow the question entirely — leaving a turn that
    asks the person nothing.
    """
    decision = CognitiveDecision(
        response_mode="ask",
        reasoning_status="needs_user_input",
        message_to_user="Un preambolo piuttosto lungo che spiega il contesto. " * 20,
        question="Conosci le penali di recesso anticipato dell'offerta A?",
    )
    composed = _compose_user_text(decision)
    assert len(composed) > 800, "il caso di prova non supera il vecchio cap"
    assert composed.endswith("offerta A?"), "la domanda e' stata tagliata via"
