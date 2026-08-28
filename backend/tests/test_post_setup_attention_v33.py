"""
V3.3 — what a fact learned in the setup is allowed to become.

Three things came out of one real recording, and they are the same mistake at
three depths:

  ORA said "adesso posso monitorare la polizza casa e la scadenza" to somebody
  who had told it a policy exists and nothing else. It made that the first
  thing on Home. And when they tapped it, ORA asked them whether they meant to
  prepare an exam or create an event.

So: a capability claim needs the knowledge it rests on; knowing something is
not a reason to open the day with it; and a card ORA generated must never
arrive at a classifier that has to guess what ORA meant.

None of the production rules know what insurance is. The word appears here, in
fixtures, because that is where the bug was found.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]


def _code_only(path: Path) -> str:
    """The file with its prose removed — guards must not fail on their own explanations."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    return "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))


# ---------------------------------------------------------------------------
# A capability claim needs its grounding
# ---------------------------------------------------------------------------

def test_existence_alone_does_not_let_ora_claim_it_can_watch_something():
    """
    "Ho una polizza" gives ORA a boolean. It does not give it a company, a
    premium or a date, so "posso monitorare la polizza e la scadenza" is a
    promise it cannot keep.
    """
    from ai_life_strategist.benefit_engine import active_benefits, available_benefits

    exists_only = {"casa.owned", "casa.assicurazione"}
    claimed = {b.code for b in active_benefits(exists_only)}
    assert "casa_assicurazione" not in claimed, (
        "ORA claimed it could watch something it knows one boolean about"
    )
    # It is still worth offering — that is a different sentence.
    assert "casa_assicurazione" in {b.code for b in available_benefits(exists_only)}


def test_the_same_claim_is_true_once_the_knowledge_is_there():
    from ai_life_strategist.benefit_engine import active_benefits

    with_document = {"casa.owned", "casa.assicurazione", "doc.polizza_casa"}
    assert "casa_assicurazione" in {b.code for b in active_benefits(with_document)}

    with_date = {"casa.owned", "casa.assicurazione", "casa.assicurazione_scadenza"}
    assert "casa_assicurazione" in {b.code for b in active_benefits(with_date)}


def test_every_claim_about_watching_something_declares_what_it_rests_on():
    """
    The rule is a property of the catalogue, not of one entry: anything whose
    Home copy promises to follow, watch or remind has to say what would make
    that true.
    """
    from ai_life_strategist.benefit_engine import BENEFITS

    promises = ("monitor", "seguire", "tenere d", "ricordarti", "scadenz")
    for code, b in BENEFITS.items():
        signal = (b.home_signal or "").lower()
        if not any(p in signal for p in promises):
            continue
        assert b.grounded_by, (
            f"{code} promises to watch something without saying what that needs"
        )


def test_the_grounding_rule_is_not_written_for_one_subject():
    """
    §28. No `if insurance`, no string matching on a domain. The rule reads a
    declared field; the catalogue says which keys count.
    """
    src = _code_only(HERE / "ai_life_strategist" / "benefit_engine.py")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            low = node.name.lower()
            for word in ("insurance", "polizza", "mortgage", "mutuo", "car", "auto_"):
                assert not re.search(rf"\b{word}", low), f"{node.name} knows a subject"
    assert "grounded_by" in src


# ---------------------------------------------------------------------------
# Knowing something is not a reason to open the day with it
# ---------------------------------------------------------------------------

def test_knowledge_availability_never_becomes_the_first_thing_on_home():
    """
    §26/§29. "What can I accomplish by tapping this right now?" — an item that
    only reports what ORA has become able to do answers nothing.
    """
    src = _code_only(HERE / "home" / "service.py")
    assert 'knowledge_only' in src, "Home must be able to tell that kind of item apart"
    # And the rule sits in the eligibility for the top slot, not in a filter
    # somewhere that only hides it.
    at = src.index("def _focus_eligible")
    body = src[at:at + 1200]
    assert "knowledge_only" in body

    adapter = _code_only(HERE / "home" / "adapters" / "life_setup.py")
    assert '"knowledge_only": True' in adapter
    assert 'priority="later"' in adapter, "and it is not today's business either"


def test_the_fallback_cannot_resurrect_what_eligibility_removed():
    """
    Found live, after the first fix: the hero came back anyway. Eligibility
    rejected the card, and then the fallback — which exists so a stale but real
    item can still open the day — picked the first thing in the pool regardless.
    A rule that only holds while something else is present is not a rule.
    """
    src = _code_only(HERE / "home" / "service.py")
    assert "fallback_pool = [" in src
    assert 'not (i.meta or {}).get("knowledge_only")' in src
    assert "fallback_pool[0] if fallback_pool else None" in src
    assert "focus_pool[0] if focus_pool else None" not in src, (
        "the unfiltered fallback is what brought it back"
    )


def test_a_quiet_home_is_a_legitimate_answer():
    """
    §39. If nothing matters yet, nothing is invented to fill the space. This is
    the shape of the code: eligibility can return an empty list and Home is
    built from it without a fallback that manufactures a hero.
    """
    src = _code_only(HERE / "home" / "service.py")
    assert "eligible = [i for i in focus_pool if _focus_eligible(i)]" in src
    assert "primary = (eligible[0] if eligible else None)" in src


# ---------------------------------------------------------------------------
# A card ORA generated keeps its meaning all the way to the destination
# ---------------------------------------------------------------------------

def test_a_card_that_knows_where_it_leads_keeps_its_own_way_there():
    """
    §30–§34, found live: ranking replaced every card's actions with the generic
    entry point, so a card ORA had generated arrived at the intent classifier
    with only its title — and the person was asked what ORA had meant.
    """
    from home.models import HomeAction, HomeItem
    from home.ranking import GENERIC_ENTRY

    src = _code_only(HERE / "home" / "ranking.py")
    assert "declared" in src and "GENERIC_ENTRY" in src
    assert "item.actions = generic" in src, "a card with nothing declared still gets the default"

    # And it actually survives ranking, which is where it used to be lost.
    from home.ranking import rank_items

    declared_item = HomeItem(
        id="x",
        type="insight",
        title="qualcosa che ORA ha proposto",
        source_type="life_experience",
        source_id="fixture_code",
        actions=[
            HomeAction(id="own", label="Continua", kind="navigate", route="/vita/x", primary=True)
        ],
    )
    ranked = rank_items([declared_item])
    routes = [a.route for a in (ranked[0].actions or [])]
    assert "/vita/x" in routes, f"the card's own destination was thrown away: {routes}"
    assert routes[0] == "/vita/x", "and it is still the primary way on"

    # A card that declares nothing still gets the guided entry: this is not a
    # rule against the classifier, only against overruling a card that knew.
    plain = HomeItem(id="y", type="insight", title="qualcosa", source_type="home", source_id="y")
    plain_routes = [a.route for a in (rank_items([plain])[0].actions or [])]
    assert GENERIC_ENTRY in plain_routes


def test_the_generic_entry_is_only_for_what_a_person_typed():
    """
    §33. The clarifier exists for genuinely ambiguous input from a person. ORA
    asking a person to explain ORA's own proposal is the failure this prevents.
    """
    src = _code_only(HERE / "home" / "ranking.py")
    at = src.index("declared = [")
    window = src[max(0, at - 400):at + 600]
    assert "actions_for(item)" in window
    assert 'a.route != GENERIC_ENTRY' in window


def test_a_card_that_names_what_ora_holds_never_reaches_the_clarifier():
    """
    The second half of the same failure, reproduced live on a real document:
    a card ORA had generated for a policy it had just read opened the guided
    flow, the classifier weighed the words of "Polizza Assicurativa Auto -
    Generali Italia", recognised nothing, and asked the person "vuoi preparare
    un esame oppure creare un evento?".

    `needs_review` is not an inference. The item exists because a document was
    read and is waiting to be confirmed, so there is nothing to work out.
    """
    from action_engine.flows import resolve_flow_from_intent
    from action_engine.service import _intent_declared_by_card_type

    declared = _intent_declared_by_card_type("needs_review")
    assert declared is not None, "ORA asked the person what ORA meant"
    assert declared.intent == "document_review"
    assert not declared.needs_clarify
    flow = resolve_flow_from_intent(
        declared.intent, declared.subtype, needs_clarify=declared.needs_clarify
    )
    assert flow != "clarify", "the card still lands where ORA has to ask what it meant"


def test_the_rule_is_wired_into_the_path_the_card_actually_takes():
    """
    The helper being right is not the fix. What matters is that opening a card
    goes through it, which is where the bug lived: the resolver reached the
    classifier and the classifier had only a title to go on.
    """
    from action_engine.models import OpenBody
    from action_engine.service import ActionEngineService

    service = ActionEngineService.__new__(ActionEngineService)
    body = OpenBody(
        home_item={
            "id": "hi_x",
            "type": "needs_review",
            "title": "Polizza Assicurativa Auto - Generali Italia",
            "source_type": "document",
            "source_id": "doc_x",
        }
    )
    ctx = service._ctx_from_open(body)
    intent = service._intent_from_body(body, ctx)
    assert intent.intent == "document_review", (
        f"opening the card still asks what ORA meant (got {intent.intent!r}, "
        f"clarify={intent.needs_clarify})"
    )
    assert not intent.needs_clarify


def test_a_type_that_was_itself_a_guess_still_goes_to_the_classifier():
    """
    The boundary of the rule, and the reason it is a short list rather than the
    whole vocabulary: a card typed `event` whose title says "devo studiare
    l'esame di psicologia" has to reach the study flow. That type is the output
    of a classification, and repeating a guess is not the same as trusting a
    fact.
    """
    from action_engine.service import _intent_declared_by_card_type

    for guessed in ("event", "study", "travel", "activity", "generic", "", None):
        assert _intent_declared_by_card_type(guessed) is None, guessed


def test_the_rule_reads_the_mapping_that_already_exists():
    """
    §28 again: no second table to drift out of step with the first, and nothing
    that knows what a policy or a bill is.
    """
    src = _code_only(HERE / "action_engine" / "service.py")
    at = src.index("_CARD_TYPES_THAT_NAME_AN_ARTIFACT")
    window = src[at:at + 1500]
    assert "HOME_TYPE_BY_INTENT" in window
    for word in ("polizza", "insurance", "bolletta", "mutuo"):
        assert word not in window.lower()
