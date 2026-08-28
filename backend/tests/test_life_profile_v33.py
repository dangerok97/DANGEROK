"""
V3.3 — Progressive Life Setup, and what the percentage is allowed to mean.

The number on the screen is the part of this sprint a person will read
literally, so these are mostly about arithmetic that has to stay honest:

  - progress is knowledge, not questions dismissed;
  - a life without a car is not an incomplete life;
  - privacy is not progress;
  - "later" leaves the hole exactly where it was;
  - nobody can set the figure from outside.

The rest is about the model being a model rather than a questionnaire: which
objectives are live depends on the answers, so two people in the same area get
different ones.
"""

from __future__ import annotations

import ast
import re
import uuid
from pathlib import Path

import pytest

from life_profile.areas import LIFE_AREAS, all_areas, area, area_for_domain
from life_profile.completeness import area_completeness, profile_completeness
from life_profile.objectives import (
    applicable,
    objectives_for_area,
    resolve,
)

HERE = Path(__file__).resolve().parents[1]


def _code_only(path: Path) -> str:
    """
    The file with its prose removed.

    These guards are about what the code does, and every one of them names the
    thing it forbids in its own explanation. Stripping docstrings and comments
    is what keeps a guard from failing on the sentence describing it.
    """
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc)
    out = src
    for doc in docstrings:
        out = out.replace(doc, "")
    return "\n".join(
        line for line in out.splitlines() if not line.strip().startswith("#")
    )


def _uid() -> str:
    return f"u_lp33_{uuid.uuid4().hex[:8]}"


def _casa():
    return area("casa")


def _refs(objs):
    return {o.ref for o in objs}


# ---------------------------------------------------------------------------
# The areas are a grouping, not a taxonomy anybody has to live with
# ---------------------------------------------------------------------------

def test_the_areas_are_a_short_list_a_person_would_recognise():
    areas = all_areas()
    assert 5 <= len(areas) <= 10, "not 25 categories, and not a single bucket"
    assert len({a.id for a in areas}) == len(areas)
    assert [a.order for a in areas] == sorted(a.order for a in areas)
    for a in areas:
        assert a.title and a.description
        assert a.domains, f"{a.id} draws from nothing"


def test_areas_draw_from_the_existing_catalogue_and_do_not_restate_it():
    """
    The knowledge worth having was declared long before this sprint. A second
    catalogue would be a second truth, and they would drift within a month.
    """
    from ai_life_strategist.knowledge_gap import DOMAIN_GAPS

    for a in all_areas():
        for domain in a.domains:
            assert domain in DOMAIN_GAPS, f"{a.id} claims an unknown domain {domain}"
        assert objectives_for_area(a), f"{a.id} has no objectives"

    # And the mapping is a function: no domain feeds two areas.
    seen = {}
    for a in all_areas():
        for d in a.domains:
            assert d not in seen, f"{d} claimed by {seen.get(d)} and {a.id}"
            seen[d] = a.id


def test_a_domain_that_is_not_a_part_of_a_life_stays_out():
    """
    `documenti` is a surface, not a part of someone's life: its gaps are
    prompts to upload things, and counting them would make the profile look
    emptier the more ORA already knows.
    """
    assert area_for_domain("documenti") is None
    assert area_for_domain("viaggi") is None


def test_what_somebody_owns_is_represented():
    """
    §6. The vision names patrimonio explicitly — other property, loans still
    running, savings — and none of it existed: `finanze` carried a single
    objective about monthly outgoings. Absorbing wealth into it would have been
    a taxonomy hiding a gap.
    """
    from life_profile.areas import area as find_area

    wealth = find_area("patrimonio")
    assert wealth is not None, "patrimonio is a part of a life, not a footnote"
    assert wealth.sensitivity == "sensitive"

    objs = objectives_for_area(wealth)
    labels = " ".join(o.label.lower() for o in objs)
    assert len(objs) >= 3
    for expected in ("immobil", "finanziament", "risparmi"):
        assert expected in labels, f"nothing represents {expected}"

    # And it is genuinely separate from Finanze rather than a relabelling.
    money = find_area("finanze")
    assert set(money.domains).isdisjoint(set(wealth.domains))


# ---------------------------------------------------------------------------
# Progress is knowledge
# ---------------------------------------------------------------------------

def test_an_untouched_area_is_zero_and_says_so():
    out = area_completeness(_casa(), facts={})
    assert out.percent == 0
    assert out.state == "not_started"
    assert out.known_count == 0
    assert out.open_objectives, "it should still be able to say what would help"


def test_knowing_things_moves_the_number_and_weights_matter():
    """
    A life is not evenly weighted. Where someone lives explains more than which
    streaming services they pay for, and the figure has to reflect that or it
    is a count of answers wearing a percentage sign.
    """
    objs = objectives_for_area(_casa())
    heaviest = max(objs, key=lambda o: o.weight)
    lightest = min(objs, key=lambda o: o.weight)
    assert heaviest.weight > lightest.weight, "the fixture needs unequal weights"

    heavy = area_completeness(_casa(), facts={heaviest.ref: "sì"})
    light = area_completeness(_casa(), facts={lightest.ref: "sì"})
    assert heavy.percent > light.percent


def test_answering_everything_that_applies_reads_as_finished():
    objs = objectives_for_area(_casa())
    facts = {o.ref: "risposta" for o in objs}
    out = area_completeness(_casa(), facts=facts)
    assert out.percent == 100
    assert out.state == "known_enough"
    assert not out.open_objectives


def test_one_thing_left_is_never_rounded_up_to_finished():
    objs = objectives_for_area(_casa())
    facts = {o.ref: "risposta" for o in objs}
    # Drop the lightest thing there is: rounding would happily call this 100.
    lightest = min(objs, key=lambda o: o.weight)
    facts.pop(lightest.ref)
    out = area_completeness(_casa(), facts=facts)
    assert out.percent < 100, "something is still missing and the number must say so"


# ---------------------------------------------------------------------------
# Skipped, declined, not applicable — three different things
# ---------------------------------------------------------------------------

def test_skipping_leaves_the_hole_where_it_was():
    """
    "Più tardi" is not an answer. If the figure moved for it, it would be
    measuring how many questions someone dismissed.
    """
    objs = objectives_for_area(_casa())
    target = objs[0]
    before = area_completeness(_casa(), facts={})
    # Skipping is recorded on the setup session as `postponed`, and is
    # deliberately absent from every input this function takes.
    after = area_completeness(_casa(), facts={})
    assert after.percent == before.percent
    resolved = resolve(objs, facts={})
    assert next(o for o in resolved if o.ref == target.ref).state == "unknown"


def test_declining_is_an_answer_but_never_progress():
    """
    Someone who would rather not discuss their savings has told ORA something
    about themselves — but not the thing. ORA still does not know it, so the
    objective stays in the reckoning and contributes nothing. A percentage that
    rose because somebody refused would be the one reading of this number that
    is a lie.
    """
    objs = objectives_for_area(_casa())
    target = max(objs, key=lambda o: o.weight)

    resolved = resolve(objs, facts={}, declined_refs=[target.ref])
    assert next(o for o in resolved if o.ref == target.ref).state == "declined"

    with_decline = area_completeness(_casa(), facts={}, declined_refs=[target.ref])
    assert with_decline.percent == 0, "declining is not knowing"
    assert with_decline.declined_count == 1
    assert target.ref not in {o["ref"] for o in with_decline.open_objectives}, (
        "and it is never offered again in the ordinary run of things"
    )


def test_declining_is_not_the_same_as_not_applying():
    """
    Three different things, and only one of them leaves the reckoning.

      skipped         not now — still missing, still counted
      declined        I would rather not — still missing, still counted
      not applicable  there is nothing to know — gone from the denominator
    """
    objs = objectives_for_area(_casa())
    # Something that always applies, so the comparison is only about state.
    target = next(o for o in objs if not o.depends_on and not o.satisfied_by)

    skipped = area_completeness(_casa(), facts={})
    declined = area_completeness(_casa(), facts={}, declined_refs=[target.ref])
    absent = area_completeness(_casa(), facts={}, not_applicable_refs=[target.ref])

    assert declined.applicable_count == skipped.applicable_count, (
        "a refusal does not reduce what ORA is missing"
    )
    assert absent.applicable_count == skipped.applicable_count - 1, (
        "something that does not exist is not missing"
    )
    assert declined.percent == skipped.percent == 0


def test_a_refusal_cannot_finish_an_area():
    """
    Everything else answered, one thing declined: the area is not complete,
    because ORA genuinely does not know that one thing.
    """
    objs = objectives_for_area(_casa())
    declined = next(o for o in objs if not o.depends_on and not o.satisfied_by)
    facts = {o.ref: "risposta" for o in objs if o.ref != declined.ref}
    out = area_completeness(_casa(), facts=facts, declined_refs=[declined.ref])
    assert out.percent < 100, "a refusal is not an answer"
    assert out.declined_count == 1

    # Whereas something that does not apply genuinely finishes it.
    absent = area_completeness(_casa(), facts=facts, not_applicable_refs=[declined.ref])
    assert absent.percent == 100


def test_a_life_without_a_car_is_not_an_incomplete_life():
    """
    G / §46. "Non ho un'auto" resolves the question it answers *and* removes
    everything that depended on it. Anything else leaves Mobilità permanently
    at a low number for a person who has nothing to tell it.
    """
    mob = area("mobilita")
    objs = objectives_for_area(mob)
    gate = next((o for o in objs if not o.depends_on), None)
    dependent = next((o for o in objs if o.depends_on), None)
    assert gate and dependent, "the fixture needs a gate and something behind it"

    resolved = resolve(objs, facts={gate.ref: False})
    by_ref = {o.ref: o for o in resolved}
    assert by_ref[gate.ref].state == "known", "a stated no is knowledge"
    if gate.ref in dependent.depends_on and len(dependent.depends_on) == 1:
        assert by_ref[dependent.ref].state == "not_applicable"

    out = area_completeness(mob, facts={gate.ref: False})
    assert out.percent > 0, "the person answered; the number has to move"


def test_not_applicable_can_also_be_recorded_directly():
    objs = objectives_for_area(_casa())
    target = objs[0]
    resolved = resolve(objs, facts={}, not_applicable_refs=[target.ref])
    assert next(o for o in resolved if o.ref == target.ref).state == "not_applicable"
    out = area_completeness(_casa(), facts={}, not_applicable_refs=[target.ref])
    assert out.not_applicable_count == 1
    assert target.ref not in {o["ref"] for o in out.open_objectives}


# ---------------------------------------------------------------------------
# The shape of an area changes with the answers
# ---------------------------------------------------------------------------

def test_an_objective_waits_for_the_thing_it_depends_on():
    """
    §47/§48. ORA does not know whether there is a mortgage to ask about until
    it knows the place is owned. Counting it as missing in the meantime holds
    the number down for a question nobody should be asked.
    """
    objs = objectives_for_area(_casa())
    dependent = next(o for o in objs if o.depends_on)
    gate = dependent.depends_on[0]

    latent = applicable(resolve(objs, facts={}), facts={})
    assert dependent.ref not in _refs(latent)

    awake = applicable(resolve(objs, facts={gate: "sì"}), facts={gate: "sì"})
    assert dependent.ref in _refs(awake)


def test_two_people_in_the_same_area_are_asked_different_things():
    """
    I / §49. Same engine, same area, different lives — so a different set of
    objectives is live, and therefore a different next question.
    """
    objs = objectives_for_area(_casa())
    dependent = next(o for o in objs if o.depends_on)
    gate = dependent.depends_on[0]

    owner = area_completeness(_casa(), facts={gate: "sì"})
    renter = area_completeness(_casa(), facts={gate: False})

    owner_open = {o["ref"] for o in owner.open_objectives}
    renter_open = {o["ref"] for o in renter.open_objectives}
    assert owner_open != renter_open, "the same questions for two different lives"
    assert dependent.ref not in renter_open


# ---------------------------------------------------------------------------
# The overall figure, and where to go next
# ---------------------------------------------------------------------------

def test_the_overall_figure_is_weighted_by_what_each_area_explains():
    empty = profile_completeness(facts={})
    assert empty.percent == 0
    assert len(empty.areas) == len(LIFE_AREAS)

    casa_objs = objectives_for_area(_casa())
    full_casa = profile_completeness(facts={o.ref: "x" for o in casa_objs})
    assert 0 < full_casa.percent < 100, "one area of a life is not a whole life"


def test_where_to_continue_comes_from_the_profile_and_never_from_a_default():
    """
    §7. Not everyone should start at Casa. The suggestion is whichever area has
    the most left to learn — and an area already begun wins, because finishing
    a thought beats starting a new one.
    """
    casa_objs = objectives_for_area(_casa())
    known_casa = {o.ref: "x" for o in casa_objs}

    out = profile_completeness(facts=known_casa)
    assert out.suggested_area_id != "casa", "there is nothing left to learn there"

    partial = {casa_objs[0].ref: "x"}
    resumed = profile_completeness(facts=partial, touched_area_ids=["casa"])
    assert resumed.suggested_area_id == "casa", "a thought already begun"


def test_an_area_with_nothing_applicable_does_not_drag_the_total_down():
    mob = area("mobilita")
    objs = objectives_for_area(mob)
    na = [o.ref for o in objs]
    out = profile_completeness(facts={}, not_applicable_refs=na)
    mobility = next(a for a in out.areas if a.area_id == "mobilita")
    assert mobility.applicable_count == 0
    assert mobility.state == "not_applicable"


# ---------------------------------------------------------------------------
# The guided first setup
#
# Structured choices, one area at a time, and every branch decided on the
# server. A branch implemented in a component is a branch nobody can test.
# ---------------------------------------------------------------------------

def test_every_question_can_be_answered_by_choosing():
    """
    §5. During the first setup a person answers by picking, not by composing
    sentences. The only free text is behind "Altro", and the handful of things
    that genuinely are values — a town, an amount, a date.
    """
    from life_profile.guided import GUIDED_OBJECTIVES

    typed_controls = {"currency", "number", "date", "location", "text"}
    for obj in GUIDED_OBJECTIVES:
        if obj.control in typed_controls or obj.control == "document_upload":
            continue
        assert obj.options, f"{obj.id} has no options to choose from"
        assert obj.control in ("single", "multi", "yes_no"), obj.control

    # And the ones that are typed are values, never open questions.
    for obj in GUIDED_OBJECTIVES:
        if obj.control == "text":
            assert obj.area_id in ("lavoro", "studio"), (
                f"{obj.id} is free text outside the two places a name for a job "
                "or a field of study genuinely is one"
            )


def test_an_answer_can_mean_there_is_none():
    """
    §22. "Non lavoro" is not a skip. It resolves the question it answers and
    retires everything that depended on it — which is why the area can read
    100% for somebody with nothing to tell it.
    """
    from life_profile.guided import objective

    work = objective("lavoro.active")
    no = next(o for o in work.options if o.id == "no")
    assert no.sets == {"lavoro.active": False}
    assert "lavoro.tipo" in no.not_applicable
    assert "lavoro.ruolo" in no.not_applicable

    study = objective("studio.active")
    no_study = next(o for o in study.options if o.id == "no")
    for retired in ("studio.tipo", "studio.universita", "doc.piano_di_studi"):
        assert retired in no_study.not_applicable, retired


def test_a_branch_opens_only_when_it_applies():
    """§47. There is no mortgage question for somebody who rents."""
    from life_profile.guided import objective

    rata = objective("casa.mutuo_rata")
    assert rata.depends_on and rata.depends_on[0].key == "casa.mutuo"
    assert not rata.relevant({}), "nothing to ask before the gate is answered"
    assert not rata.relevant({"casa.mutuo": False}), "and nothing after a no"
    assert rata.relevant({"casa.mutuo": "si"})

    canone = objective("casa.affitto_canone")
    assert canone.relevant({"casa.situazione": "affitto"})
    assert not canone.relevant({"casa.situazione": "proprieta"})


def test_casa_is_deep_enough_to_be_worth_doing():
    """
    §8/§10. A town and "di proprietà" is not a picture of where somebody
    lives. Casa has to cover the situation, the place, who is there, what it
    costs, the car space, the utilities and the cover.
    """
    from life_profile.guided import for_area

    casa = for_area("casa")
    assert len(casa) >= 8, f"Casa asks only {len(casa)} things"
    ids = {o.id for o in casa}
    for expected in (
        "casa.situazione", "casa.citta", "casa.convivenza", "casa.mutuo",
        "casa.spazio_auto", "casa.utenze", "casa.assicurazione",
    ):
        assert expected in ids, f"Casa never asks about {expected}"
    # And one of them is better read than typed.
    assert any(o.control == "document_upload" for o in casa)


def test_a_document_step_is_an_action_not_a_field():
    """
    §5/§9, found in the video: the bill step rendered as a text box with "La
    tua risposta" — nothing to write, and no way forward. A document is handed
    over, and the schema has to say so.
    """
    from life_profile.guided import GUIDED_OBJECTIVES, objective

    bill = objective("doc.bolletta")
    assert bill.control == "document_upload"
    assert bill.document_type == "bolletta"
    assert bill.allow_skip, "and it can always be left for later"

    for obj in GUIDED_OBJECTIVES:
        if obj.id.startswith("doc."):
            assert obj.control == "document_upload", f"{obj.id} is not a field"
            assert obj.document_type, f"{obj.id} says nothing about what it is"


def test_the_place_can_be_asked_or_detected():
    """§1/§2. A location step offers the device, and always accepts typing."""
    from life_profile.guided import objective

    where = objective("casa.citta")
    assert where.control == "location"
    assert "casa" in where.question.lower(), where.question


def test_every_option_says_what_it_means_on_its_own():
    """
    §3, found in the video: "Utenze intestate a…" cut off mid-phrase told a
    person nothing. An option that needs a tooltip is a form.
    """
    from life_profile.guided import GUIDED_OBJECTIVES

    for obj in GUIDED_OBJECTIVES:
        for opt in obj.options:
            label = opt.label.strip()
            assert label, f"{obj.id} has a nameless option"
            assert not label.endswith(("...", "…")), f"{obj.id}/{opt.id} trails off"
            # Short enough to read at a glance, long enough to be a sentence
            # where the meaning needs one.
            assert len(label) <= 46, f"{obj.id}/{opt.id} is too long to sit on a card"

    utenze = next(o for o in GUIDED_OBJECTIVES if o.id == "casa.utenze")
    labels = [o.label for o in utenze.options]
    assert all(len(l.split()) >= 3 for l in labels), (
        f"each option has to be a phrase somebody can understand alone: {labels}"
    )


def test_the_areas_are_the_agreed_path():
    """§31. The first run has a visible order, and it is this one."""
    from life_profile.areas import all_areas

    assert [a.id for a in all_areas()] == [
        "casa", "lavoro", "studio", "mobilita", "famiglia",
        "patrimonio", "finanze", "assicurazioni", "servizi", "salute",
    ]


def test_what_is_learned_elsewhere_still_lands_where_it_belongs():
    """
    §4. "Vivo con il partner" is recorded for Famiglia as well as Casa —
    knowledge belongs wherever it is true. What must never move is the
    question.
    """
    from life_profile.guided import option_of

    partner = option_of("casa.convivenza", "partner")
    assert partner.sets.get("famiglia.partner") is True

    car = option_of("mobilita.mezzi", "auto")
    assert car.sets.get("auto.owned") is True


def test_the_name_is_asked_before_the_areas_and_never_inside_one():
    """
    §29/§30. It belongs to no part of a life, so it cannot live inside one:
    asked in the middle of Casa it reads as a form changing subject.
    """
    from life_profile.guided import GUIDED_OBJECTIVES, IDENTITY_OBJECTIVE, for_area

    assert IDENTITY_OBJECTIVE.area_id == ""
    assert IDENTITY_OBJECTIVE not in GUIDED_OBJECTIVES
    for area_id in ("casa", "lavoro", "studio", "mobilita"):
        assert all("preferred_name" not in o.id for o in for_area(area_id))


def test_the_setup_writes_a_name_to_the_one_identity_there_is():
    """
    §29, found live: somebody said their name and Home went on greeting them
    as "Test", because the setup's copy lived in its own session while every
    surface reads the account.
    """
    src = _code_only(HERE / "life_profile" / "setup.py")
    assert "db.users.update_one" in src, (
        "the preferred name has to reach the canonical identity"
    )
    assert '"name": clean' in src


# ---------------------------------------------------------------------------
# One life model, and a number nobody can set
# ---------------------------------------------------------------------------

def test_the_projection_never_writes_a_fact():
    """
    §22/§23. Every fact here was written by somebody else, into the store that
    owns it. Two copies of where somebody lives is how a system starts
    contradicting itself.
    """
    src = _code_only(HERE / "life_profile" / "service.py")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in (
            "insert_one", "update_one", "replace_one", "insert_many", "update_many",
        ):
            raise AssertionError("the projection must not write to a collection")
    # The one write it does have goes through the setup session's own repository.
    assert "save_session" in src
    assert "life_profile_answers" not in src and "onboarding_answers" not in src


def test_no_endpoint_accepts_a_completeness_value():
    """§81. A percentage a client could set is a percentage that means nothing."""
    src = _code_only(HERE / "life_profile" / "router.py")
    for forbidden in ("percent", "completeness=", "completion"):
        assert forbidden not in src, forbidden
    tree = ast.parse(src)
    fields = [
        t.target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        for t in node.body
        if isinstance(t, ast.AnnAssign) and isinstance(t.target, ast.Name)
    ]
    # A client may say what a person *chose* — a reference, an option, a value,
    # a refusal. There is nothing here through which it could state a figure.
    allowed = {
        "refs", "objective_id", "option_ids", "value", "other_text", "action",
        "area_id",
    }
    assert set(fields) <= allowed, f"unexpected client-supplied field: {fields}"


def test_the_completeness_module_never_reaches_for_a_model():
    """
    §83. Opening Vita must not cost fifty LLM calls. The figure is arithmetic
    over structured state; the model writes questions, not counts.
    """
    for name in ("completeness.py", "objectives.py", "areas.py"):
        src = _code_only(HERE / "life_profile" / name).lower()
        for forbidden in ("llm", "gemini", "openai", "complete_json", "plan_turn"):
            assert forbidden not in src, f"{name} reaches for a model"


def test_a_subject_is_not_abandoned_mid_thought():
    """
    §3, found live. Somebody described their home — town, who they live with,
    ownership, no mortgage — and the next question was "come preferisci che ti
    chiami?". The name is worth knowing; asking it *there* is what makes the
    conversation feel like a form being processed.

    The two nuclei that belong to no subject in particular wait. The ones that
    are what the area is made of do not: asking where somebody lives while
    talking about their home is staying on the subject.
    """
    from ai_life_strategist.minimum_life_context import compute_mlc_gaps
    from ai_life_strategist.question_planner import plan_next
    from ai_life_strategist.models import ReasoningContext

    settled = {
        "casa.citta": "Tarquinia",
        "casa.owned": True,
        "casa.mutuo": False,
        "mlc.responsibilities": "casa",
    }
    # Left to itself, the nucleus order opens with the person's name.
    assert compute_mlc_gaps(settled)[0].key.startswith("mlc.identity")

    plan = plan_next(
        ReasoningContext(
            user_id=_uid(),
            known_facts=settled,
            last_user_text="La casa è di proprietà e non ho un mutuo.",
            domains_touched=["casa"],
        )
    )
    asked = str((plan.meta or {}).get("gap_key") or "")
    assert not asked.startswith("mlc.identity"), (
        f"asked for a name in the middle of the house: {plan.next_best_question}"
    )
    assert not asked.startswith("mlc.immediate_priority")


def test_a_passing_mention_does_not_lock_the_subject():
    """
    The rule has to be narrow. Somebody who mentioned a subject once has not
    settled into it, and the opening turns still establish who ORA is talking
    to before it settles anywhere.
    """
    from ai_life_strategist.question_planner import plan_next
    from ai_life_strategist.models import ReasoningContext

    plan = plan_next(
        ReasoningContext(
            user_id=_uid(),
            known_facts={"casa.owned": True},
            last_user_text="Ho una casa.",
        )
    )
    assert str((plan.meta or {}).get("gap_key") or "").startswith("mlc."), (
        "one fact is a mention, not a subject"
    )


def test_ora_does_not_claim_documents_it_does_not_have():
    """
    §7, found in a real screenshot. Home said "adesso posso usare i documenti
    della tua casa" to somebody who had never uploaded one — the benefit fired
    on owning a home rather than on having a document. Owning makes it worth
    offering; only the document makes it true.
    """
    from ai_life_strategist.benefit_engine import active_benefits, available_benefits

    owner = {"casa.owned"}
    assert "casa_documenti" not in {b.code for b in active_benefits(owner)}, (
        "no document, no claim"
    )
    assert "casa_documenti" in {b.code for b in available_benefits(owner)}, (
        "but it is still worth offering"
    )

    with_document = {"casa.owned", "doc.rogito"}
    assert "casa_documenti" in {b.code for b in active_benefits(with_document)}

    # And what is said before the document exists is an invitation.
    from ai_life_strategist.benefit_engine import BENEFITS

    invite = BENEFITS["casa_documenti"].proactive_signal or ""
    assert invite.lower().startswith("se vuoi"), invite


def test_setup_questions_never_become_blockers():
    """
    §13/§74. A setup question is an offer, not a blocker: nothing in a life is
    stopped because somebody has not said which energy supplier they use. If
    these turned into `OpenQuestion`s, ten skipped offers would fill "Domande
    per te" with things nobody can act on, and the one row that means "work has
    stopped" would stop meaning it.
    """
    setup = _code_only(HERE / "life_setup" / "service.py")
    profile = _code_only(HERE / "life_profile" / "service.py")
    for src, name in ((setup, "life_setup"), (profile, "life_profile")):
        for forbidden in (
            "record_blocking_question",
            "OpenQuestion",
            "blocking_ask",
            "waiting.service",
        ):
            assert forbidden not in src, f"{name} must not create blockers: {forbidden}"


def test_learning_outside_the_setup_moves_the_number():
    """
    §24/§25/§58. Someone mentions their mortgage payment in an ordinary
    conversation, or uploads a policy a week later. The profile is a
    projection: the moment the fact lands in the store that owns it, the figure
    follows. Nobody has to reopen a form.
    """
    objs = objectives_for_area(_casa())
    gate = next(o for o in objs if not o.depends_on and not o.satisfied_by)
    # With the gate already answered the shape of the area is settled, so the
    # comparison is about knowledge arriving and nothing else.
    settled = {gate.ref: "di proprietà"}
    later = next(o for o in objs if o.depends_on and gate.ref in o.depends_on)

    before = area_completeness(_casa(), facts=dict(settled))
    after = area_completeness(
        _casa(),
        # Arrived later, from anywhere at all — a document, a passing remark.
        facts={**settled, later.ref: "estratto da un documento"},
    )
    assert after.percent > before.percent
    assert after.known_count == before.known_count + 1


def test_learning_something_can_widen_an_area_and_that_is_honest():
    """
    Telling ORA the place is owned opens questions that did not exist a moment
    earlier — the deed, the mortgage, the insurance. The share ORA knows can
    therefore fall, and it should: the figure is how much of what would help is
    known, not a reward for answering. Inventing monotonicity here would mean
    inventing a number.
    """
    objs = objectives_for_area(_casa())
    gate = next(o for o in objs if not o.depends_on and not o.satisfied_by)
    assert any(gate.ref in o.depends_on for o in objs), "the fixture needs a real gate"

    before = area_completeness(_casa(), facts={})
    after = area_completeness(_casa(), facts={gate.ref: "di proprietà"})

    assert after.known_count > before.known_count, "the answer was recorded"
    assert after.applicable_count > before.applicable_count, (
        "and it revealed things that only apply now"
    )


def test_a_foundation_is_recognised_under_any_of_its_names():
    """
    Found live: someone said "vivo a Tarquinia con la mia compagna" and the
    profile stayed at zero, because the sentence was filed as `casa.citta`
    while the objective was looking for `mlc.life_places.home`. Both are the
    same thing, and the existing engine already says so.
    """
    casa_objs = objectives_for_area(_casa())
    foundation = next((o for o in casa_objs if o.satisfied_by), None)
    assert foundation is not None, "Casa must have a foundation objective"
    assert "casa.citta" in foundation.satisfied_by

    out = area_completeness(_casa(), facts={"casa.citta": "Tarquinia"})
    assert out.percent > 0
    # The town resolves both the foundation and the guided objective that asks
    # for it: one thing worth knowing, arriving under two names.
    assert out.known_count >= 1


def test_a_denial_is_not_recorded_as_a_possession():
    """
    Found live. "La casa è di mia proprietà, senza mutuo" was filed as *having*
    a mortgage, because the word appears in the sentence that denies it. A
    profile that believes the opposite of what somebody said is worse than an
    empty one, and every number built on it inherits the mistake.
    """
    from ai_life_strategist.knowledge_gap import infer_known_from_text

    denied = infer_known_from_text("La casa è di mia proprietà, senza mutuo.")
    assert denied.get("casa.mutuo") is False

    assert infer_known_from_text("Non ho la macchina.").get("auto.owned") is False

    # And a plain statement still means what it says.
    stated = infer_known_from_text("Ho un mutuo da 620 euro al mese.")
    assert stated.get("casa.mutuo") is True
    assert infer_known_from_text("Ho una macchina, una Panda.").get("auto.owned") is True


def test_knowledge_that_arrives_early_still_counts():
    """
    Found live. A bill was uploaded, the pipeline genuinely read the supplier
    and the amount — and the profile did not move, because the objective it
    answered was still waiting behind a question about home ownership that
    nobody had asked. Something ORA knows evidently applies, whatever its gate
    says.
    """
    objs = objectives_for_area(_casa())
    gated = next(o for o in objs if o.depends_on)

    # The gate is unanswered, so the objective would normally be latent.
    latent = applicable(resolve(objs, facts={}), facts={})
    assert gated.ref not in _refs(latent)

    # But the answer arrived anyway, from a document.
    facts = {gated.ref: True}
    live = applicable(resolve(objs, facts=facts), facts=facts)
    assert gated.ref in _refs(live)

    out = area_completeness(_casa(), facts=facts)
    assert out.percent > 0, "the document taught ORA something and it must show"
    assert out.known_count == 1


def test_where_a_fact_came_from_travels_with_it():
    """§21. "Me lo hai detto" and "da un documento" are different claims."""
    objs = objectives_for_area(_casa())
    target = objs[0]
    resolved = resolve(
        objs,
        facts={target.ref: "via Roma 1"},
        provenance={target.ref: "Da un documento"},
    )
    item = next(o for o in resolved if o.ref == target.ref)
    assert item.state == "known"
    assert item.provenance == "Da un documento"


def test_a_stated_no_is_read_from_a_sentence_not_just_a_flag():
    """
    The setup stores a direct answer as the sentence somebody typed, so "No,
    non ho l'auto" has to be understood as a "no" — while "non lo so" must not,
    because not knowing is not an answer about a life.
    """
    from life_profile.objectives import _is_negative

    for said in ("No", "no, non ho l'auto", "Non possiedo veicoli", "Nessun mutuo"):
        assert _is_negative(said), said
    for said in ("Non lo so", "Non so ancora", "Sì, è di proprietà", "È in affitto"):
        assert not _is_negative(said), said


def test_no_class_or_function_here_knows_a_domain():
    """
    §61. Areas may be named — a person has to read them — but nothing may
    branch on one. No HouseSetupFlow, no `if area == "casa"`.
    """
    banned = ("house", "mortgage", "car", "vehicle", "wedding", "travel", "insurance_flow")
    for path in (HERE / "life_profile").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.ClassDef):
                name = node.name
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name
            if not name:
                continue
            low = name.lower()
            for word in banned:
                assert not re.search(rf"\b{word}", low), f"{path.name}:{name}"


def test_an_answer_is_recorded_whichever_branch_it_takes():
    """
    Found in the end-to-end QA: somebody answered "casa in affitto" and the
    ownership objective stayed `unknown`. Only the "proprietà" branch wrote
    anything about ownership, so for everybody else ORA went on counting as
    missing the very thing it had just been told — and no later question ever
    asks it again, which made a complete Casa unreachable for a renter.

    A negative is knowledge. The branch has to say so.
    """
    from life_profile.areas import area as find_area
    from life_profile.completeness import area_completeness
    from life_profile.guided import objective as guided_objective
    from life_profile.objectives import objectives_for_area, resolve

    question = guided_objective("casa.situazione")
    casa = find_area("casa")

    for option in question.options:
        facts = {question.id: option.id, **option.sets}
        resolved = resolve(
            objectives_for_area(casa),
            facts=facts,
            not_applicable_refs=list(option.not_applicable),
        )
        ownership = next(o for o in resolved if o.ref == "casa.owned")
        assert ownership.state != "unknown", (
            f"'{option.label}' leaves ownership unanswered forever"
        )


def test_no_branch_leaves_open_what_no_question_will_ever_ask():
    """
    The general form of it: if choosing one option resolves something and
    choosing its sibling leaves that same thing open, the setup has to be able
    to come back to it. Otherwise one answer quietly caps an area below 100%
    with no way for anybody to fix it.

    Objectives that no branch resolves at all are a different matter — an exam
    date, a medical appointment — and are deliberately outside the first setup:
    they arrive later, from a conversation or a document.
    """
    from life_profile.areas import all_areas
    from life_profile.guided import for_area
    from life_profile.objectives import objectives_for_area, resolve

    askable = set()
    for a in all_areas():
        for g in for_area(a.id):
            askable.add(g.id)
            for o in g.options:
                askable.update(o.sets.keys())

    # Known and accepted: `si, studio` opens an exam objective the setup does
    # not ask about. A first setup is not the place for a date that changes
    # every term, and the profile is honest about not knowing it.
    accepted = {("studio.active", "si", "studio.esame")}

    for a in all_areas():
        objectives = objectives_for_area(a)

        def outcome(question, option):
            facts = {question.id: option.id, **option.sets}
            return resolve(
                objectives, facts=facts, not_applicable_refs=list(option.not_applicable)
            )

        for g in for_area(a.id):
            live = [o for o in g.options if not o.declines]
            for option in live:
                open_now = {o.ref for o in outcome(g, option) if o.state == "unknown"}
                unreachable = {r for r in open_now - askable if not r.startswith("doc.")}
                siblings = set()
                for other in live:
                    if other is option:
                        continue
                    siblings |= {
                        o.ref for o in outcome(g, other)
                        if o.state in ("known", "inferred", "not_applicable")
                    }
                for ref in sorted(unreachable & siblings):
                    assert (g.id, option.id, ref) in accepted, (
                        f"{a.id}: '{option.label}' leaves {ref} open with nothing "
                        f"left to ask it"
                    )
