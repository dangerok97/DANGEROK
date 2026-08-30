"""
V3.2 — Life Guidance: the constitution, enforced rather than hoped for.

Every scenario here is a way ORA stops being a guide and becomes a form. They
are tested against the deterministic layer, not the model, on purpose: whether
a person is asked something they already told ORA cannot be left to whichever
sentence the reasoning happened to produce.

The mortgage example is a fixture. Scenario G runs the identical code over a
completely different goal, and the domain-neutrality test checks that no name
in the module knows what a mortgage is.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import _loop_harness  # tests/_loop_harness.py: the one place a loop is chosen

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")

from guidance.bridge import (  # noqa: E402
    blocking_ask_payload,
    resolution_observation,
    variables_from_missing,
)
from guidance.models import GoalState, Milestone, Variable  # noqa: E402
from guidance.questioning import MAX_BUNDLE, compose_question, select_bundle  # noqa: E402
from guidance.service import GuidanceService  # noqa: E402


def _run(coro):
    # The session's own loop, not whatever the policy currently points at:
    # a suite that used asyncio.run() before this one has cleared that slot.
    return _loop_harness.run(coro)


def is_meta(text: str) -> bool:
    from guidance.wording import is_meta_choice

    return is_meta_choice(text)


def _uid() -> str:
    return f"u_g32_{uuid.uuid4().hex[:8]}"


def _v(ref, label="", necessity="required", sensitivity="normal", purpose=""):
    return Variable(
        ref=ref, label=label or ref, necessity=necessity,
        sensitivity=sensitivity, purpose=purpose,
    )


class _NoKnowledge(GuidanceService):
    """A service whose sources know nothing — the worst case for asking."""

    async def _lookup(self, *a, **k):  # pragma: no cover - not used
        return 0


@pytest.fixture()
def svc():
    """Guidance with no database: knowledge lookup finds nothing and says so."""
    return GuidanceService(db=None)


# ---------------------------------------------------------------------------
# A — an advanced goal is not restarted from the beginning
# ---------------------------------------------------------------------------

def test_state_reconstruction_keeps_only_what_remains():
    state = GoalState.model_validate({
        "objective": "Acquistare l'immobile individuato",
        "stage": "Compromesso firmato, manca il finanziamento",
        "milestones": [
            {"ref": "search", "title": "Individuare l'immobile", "state": "done",
             "basis": "inference", "evidence_refs": ["turn:1"]},
            {"ref": "offer", "title": "Accordo con la controparte", "state": "done",
             "basis": "fact", "evidence_refs": ["turn:1"]},
            {"ref": "financing", "title": "Definire il finanziamento", "state": "active",
             "basis": "unknown"},
            {"ref": "deed", "title": "Rogito", "state": "upcoming", "basis": "unknown"},
        ],
    })
    residual = [m.ref for m in state.residual()]
    # What is behind the person is not work: it is state.
    assert residual == ["financing", "deed"]
    assert state.active().ref == "financing"
    # And how ORA knows is preserved, so "why do you think that?" is answerable.
    done = {m.ref: m for m in state.milestones if m.state == "done"}
    assert done["offer"].basis == "fact"
    assert done["search"].basis == "inference"


def test_a_correction_beats_an_inference():
    """E — the user says a step is not done. That wins, without argument."""
    before = GoalState(milestones=[
        Milestone(ref="survey", title="Perizia", state="done", basis="inference"),
    ])
    after = GuidanceService.reconstruct(
        {"objective": "x", "milestones": [
            {"ref": "survey", "title": "Perizia", "state": "done", "basis": "inference"},
        ]},
        previous=before,
        corrections={"survey": "active"},
    )
    m = after.milestones[0]
    assert m.state == "active"
    assert m.basis == "fact", "a correction is something the person said, not a guess"
    assert m.evidence_refs == ["user_correction"]


def test_a_stated_fact_is_not_downgraded_by_a_later_inference():
    before = GoalState(milestones=[
        Milestone(ref="offer", title="Accordo", state="done", basis="fact",
                  evidence_refs=["turn:1"]),
    ])
    after = GuidanceService.reconstruct(
        {"objective": "x", "milestones": [
            {"ref": "offer", "title": "Accordo", "state": "upcoming", "basis": "inference"},
        ]},
        previous=before,
    )
    assert after.milestones[0].state == "done"
    assert after.milestones[0].basis == "fact"


def test_identity_survives_a_revision():
    """Workspace, Attività and any open question still point at the same thing."""
    before = GoalState(milestones=[
        Milestone(ref="financing", title="Finanziamento", state="active",
                  plan_item_id="lpi_7"),
    ])
    after = GuidanceService.reconstruct(
        {"objective": "x", "milestones": [
            {"ref": "financing", "title": "Definire il finanziamento", "state": "active"},
            {"ref": "deed", "title": "Rogito", "state": "upcoming"},
        ]},
        previous=before,
    )
    kept = {m.ref: m for m in after.milestones}
    assert kept["financing"].plan_item_id == "lpi_7"
    assert after.revision == before.revision + 1


def test_invalid_reconstruction_leaves_the_previous_state_standing():
    """A plan rebuilt from malformed output is worse than an update lost."""
    before = GoalState(milestones=[Milestone(ref="a", title="A", state="active")])
    for bad in (None, {}, {"milestones": "not a list"}, {"objective": "x", "milestones": []}):
        after = GuidanceService.reconstruct(bad, previous=before)
        assert [m.ref for m in after.milestones] == ["a"]
        assert after.revision == before.revision


# ---------------------------------------------------------------------------
# B / H / I — what ORA knows never becomes a question
# ---------------------------------------------------------------------------

def test_known_information_is_not_re_asked(svc):
    """B — three of five already known: only the other two are asked."""
    variables = [
        _v("age", "età"),
        _v("income", "reddito netto mensile", sensitivity="sensitive"),
        _v("employment", "tipo di contratto"),
        _v("amount", "importo da finanziare"),
        _v("energy_class", "classe energetica"),
    ]
    out = _run(svc.evaluate(
        user_id=_uid(),
        variables=variables,
        answered_refs=["age", "income", "employment"],
        state=GoalState(milestones=[
            Milestone(ref="financing", title="valutare il finanziamento", state="active"),
        ]),
    ))
    assert out.next_step.kind == "ask"
    asked = {v.ref for v in out.next_step.requested}
    assert asked == {"amount", "energy_class"}
    assert out.avoided == 3
    # ...and the ones ORA had are recorded as known, not silently dropped.
    assert {v.ref for v in out.sufficiency.resolved()} == {"age", "income", "employment"}


def test_nothing_required_missing_means_no_question(svc):
    """H — the most important test: ORA proceeds instead of asking."""
    out = _run(svc.evaluate(
        user_id=_uid(),
        variables=[_v("amount", "importo")],
        answered_refs=["amount"],
    ))
    assert out.next_step.kind == "proceed"
    assert out.next_step.question == ""
    assert out.asked == 0
    assert out.reason == "nothing_required_missing"


def test_useful_information_never_becomes_a_question(svc):
    """I — required is known; useful and optional wait, however interesting."""
    out = _run(svc.evaluate(
        user_id=_uid(),
        variables=[
            _v("a", "quello che serve", necessity="required"),
            _v("b", "sarebbe utile", necessity="useful"),
            _v("c", "curiosità", necessity="optional"),
        ],
        answered_refs=["a"],
    ))
    assert out.next_step.kind == "proceed"
    assert {v.ref for v in out.sufficiency.deferred()} == {"b", "c"}


def test_what_the_user_just_said_is_not_asked_back(svc):
    out = _run(svc.evaluate(
        user_id=_uid(),
        variables=[_v("energy_class", "classe energetica"), _v("amount", "importo")],
        user_message="La classe energetica dell'immobile è la C.",
    ))
    resolved = {v.ref for v in out.sufficiency.resolved()}
    assert "energy_class" in resolved, "asking for what was just said is not listening"
    assert {v.ref for v in out.next_step.requested} == {"amount"}


def test_an_elided_article_does_not_hide_the_word(svc):
    """
    Italian glues its articles on: "l'importo". Left glued, the person says
    exactly the thing ORA is missing and ORA asks for it anyway — the most
    visible way a system can fail to listen.
    """
    out = _run(svc.evaluate(
        user_id=_uid(),
        variables=[_v("amount", "importo")],
        user_message="L'importo che voglio finanziare è 200.000 euro.",
    ))
    assert {v.ref for v in out.sufficiency.resolved()} == {"amount"}
    assert not out.next_step.requested, "it was just said"


def test_the_question_a_person_reads_is_a_sentence(svc):
    """
    Found live: the persisted question read "Per necessario per creare l'evento
    in agenda e fissare correttamente il rogito: data e ora del rogito?" — the
    reasoning's own prose grafted into a template. That text is what Home and
    Attività show.
    """
    asked = _v("notary_appointment_datetime", "Data e ora del rogito")
    asked.purpose = "Necessario per creare l'evento in agenda."
    out = _run(svc.evaluate(
        user_id=_uid(),
        variables=[asked],
        user_message="Fissa l'appuntamento dal notaio.",
        fallback_question="Hai già una data e un orario concordati con il notaio?",
    ))
    q = out.next_step.question
    assert q == "Hai già una data e un orario concordati con il notaio?", (
        "nothing was resolved, so the model's own wording still fits"
    )
    assert "Per necessario" not in q

    # With no wording from the model, what is composed is still readable.
    out2 = _run(svc.evaluate(
        user_id=_uid(),
        variables=[_v("notary_appointment_datetime", "Data e ora del rogito")],
        user_message="Fissa l'appuntamento dal notaio.",
    ))
    assert out2.next_step.question == "Data e ora del rogito?"


def test_a_ref_that_appears_in_full_is_evidence():
    """
    Found live: ORA held "la durata del mutuo preferita è 25 anni" and asked
    for it anyway, because the label it had chosen — "durata del piano di
    rimborso" — shares one word with that sentence. The machine name does not
    drift: two words or more, present in full, is about that and nothing else.
    """
    from guidance import resolution

    class _Fact:
        def __init__(self, source, statement):
            self.source, self.statement = source, statement

    known = _Fact("memory", "La durata del mutuo preferita è 25 anni")
    v = _v("durata_mutuo", "durata del piano di rimborso")
    assert resolution.resolve_from_facts([v], [known]) == 1
    assert v.resolved

    # A single-word ref stays too weak to carry a match on its own.
    weak = _v("amount", "importo")
    assert resolution.resolve_from_facts(
        [weak], [_Fact("memory", "Amount of coffee bought last week")]
    ) == 0


def test_oras_own_restatement_of_the_work_is_not_evidence():
    """
    Found live. The broker returned ORA's own situation record — "…in attesa di
    specificare data e ora" — and the matcher, seeing "data", "ora" and
    "rogito", declared the date known. Reading the question back to yourself is
    not an answer.
    """
    from guidance import resolution

    class _Fact:
        def __init__(self, source, statement):
            self.source, self.statement = source, statement

    work = _Fact(
        "situations",
        "Situation: richiesta di fissare l'appuntamento dal notaio per il "
        "rogito, in attesa di specificare data e ora.",
    )
    v = _v("rogito_datetime", "data e ora del rogito")
    assert resolution.resolve_from_facts([v], [work]) == 0
    assert not v.resolved

    stated = _Fact("memory", "La data e l'ora del rogito sono il 12 marzo alle 10.")
    assert resolution.resolve_from_facts([v], [stated]) == 1
    assert v.origin == "memory"


def test_one_shared_word_is_not_knowledge(svc):
    """
    Found live: "fissa l'appuntamento dal notaio" made ORA believe it knew
    *when*. A false "already known" is the one error here nobody ever sees —
    the person is simply never asked.
    """
    out = _run(svc.evaluate(
        user_id=_uid(),
        variables=[_v("notary_appointment_datetime",
                      "data e ora dell'appuntamento dal notaio")],
        user_message=("Procedi tu: fissa l'appuntamento dal notaio per il "
                      "rogito e mettilo in agenda."),
    ))
    assert {v.ref for v in out.next_step.requested} == {"notary_appointment_datetime"}
    assert not out.sufficiency.resolved(), "naming a thing is not stating its value"


# ---------------------------------------------------------------------------
# C / D — one question, and only the part still missing
# ---------------------------------------------------------------------------

def test_related_variables_are_asked_once(svc):
    """C — six things the same step needs is one question, not six turns."""
    variables = [
        _v("age", "età"), _v("income", "reddito netto", sensitivity="sensitive"),
        _v("employment", "tipo di contratto"), _v("loans", "finanziamenti in corso"),
        _v("price", "prezzo dell'immobile"), _v("amount", "importo da finanziare"),
    ]
    out = _run(svc.evaluate(
        user_id=_uid(),
        variables=variables,
        state=GoalState(milestones=[
            Milestone(ref="f", title="capire quali soluzioni sono adatte a te", state="active"),
        ]),
    ))
    assert out.next_step.kind == "ask"
    assert len(out.next_step.requested) == 6
    q = out.next_step.question
    assert q.count("?") <= 1, "a bundle is one request, not six questions in a row"
    for label in ("età", "reddito netto", "importo da finanziare"):
        assert label in q.lower()
    # A long or personal request explains itself once.
    assert out.next_step.why_needed


def test_a_bundle_stays_a_question_and_not_a_form():
    many = [_v(f"v{i}", f"variabile {i}") for i in range(12)]
    assert len(select_bundle(many)) == MAX_BUNDLE


def test_the_least_personal_things_are_asked_first():
    bundle = select_bundle([
        _v("income", "reddito", sensitivity="high"),
        _v("age", "età"),
        _v("health", "salute", sensitivity="sensitive"),
    ])
    assert bundle[0].ref == "age"
    assert bundle[-1].ref == "income"


def test_a_partial_answer_only_leaves_what_is_still_missing():
    """D — asked for four, given two: the next question contains two."""
    requested = [_v("a"), _v("b"), _v("c"), _v("d")]
    left = GuidanceService.remaining_after_answer(requested, answered_refs=["a", "b"])
    assert [v.ref for v in left] == ["c", "d"]


def test_a_declined_variable_is_not_asked_again():
    """J — a refusal is an answer. Re-asking it is the loop this forbids."""
    requested = [_v("a"), _v("income", sensitivity="high"), _v("c")]
    left = GuidanceService.remaining_after_answer(
        requested, answered_refs=["a"], declined_refs=["income"],
    )
    assert [v.ref for v in left] == ["c"]


def test_a_refusal_does_not_block_the_next_step(svc):
    out = _run(svc.evaluate(
        user_id=_uid(),
        variables=[_v("income", "reddito", sensitivity="high")],
        declined_refs=["income"],
    ))
    assert out.next_step.kind == "proceed", "a refusal must not become a loop"
    declined = [v for v in out.sufficiency.variables if v.origin == "declined"]
    assert declined and declined[0].resolved_note == "preferisce non dirlo"


# ---------------------------------------------------------------------------
# G — a completely different goal, the same code
# ---------------------------------------------------------------------------

def test_the_same_engine_guides_an_unrelated_goal(svc):
    """G — career, not property. Nothing branches on the domain."""
    state = GoalState.model_validate({
        "objective": "Valutare la nuova offerta di lavoro",
        "stage": "Offerta ricevuta, manca la decisione",
        "milestones": [
            {"ref": "search", "title": "Cercare posizioni", "state": "done",
             "basis": "inference"},
            {"ref": "interview", "title": "Colloqui", "state": "done", "basis": "inference"},
            {"ref": "offer", "title": "Ricevere un'offerta", "state": "done", "basis": "fact"},
            {"ref": "compare", "title": "Confrontare con la posizione attuale",
             "state": "active"},
            {"ref": "notice", "title": "Preavviso", "state": "upcoming"},
        ],
    })
    assert [m.ref for m in state.residual()] == ["compare", "notice"]

    out = _run(svc.evaluate(
        user_id=_uid(),
        variables=[
            _v("current_salary", "retribuzione attuale", sensitivity="sensitive"),
            _v("offered_salary", "retribuzione offerta", sensitivity="sensitive"),
            _v("notice_period", "preavviso contrattuale"),
            _v("commute", "come ti muoveresti", necessity="useful"),
        ],
        state=state,
        answered_refs=["current_salary"],
    ))
    assert out.next_step.kind == "ask"
    asked = {v.ref for v in out.next_step.requested}
    assert asked == {"offered_salary", "notice_period"}
    assert "commute" not in asked, "useful is not required, in any domain"
    assert out.avoided == 1


# ---------------------------------------------------------------------------
# The bridge to the reasoning, and to V3.1
# ---------------------------------------------------------------------------

def test_only_required_needs_can_reach_a_person():
    from conversation_engine.ai_core.models import MissingInformation

    items = [
        MissingInformation(ref="a", description="A", necessity="required"),
        MissingInformation(ref="b", description="B", necessity="useful"),
        # Written before `necessity` existed: blocking + ask meant required.
        MissingInformation(ref="c", description="C", blocking=True, strategy="ask"),
        MissingInformation(ref="d", description="D", strategy="retrieve"),
    ]
    vars_ = variables_from_missing(items)
    by_ref = {v.ref: v for v in vars_}
    assert by_ref["a"].necessity == "required"
    assert by_ref["b"].necessity == "useful"
    assert by_ref["c"].necessity == "required", "legacy blocking asks stay blocking"
    assert by_ref["d"].necessity == "useful"


def test_the_ask_handed_to_v31_carries_what_it_asked_for(svc):
    out = _run(svc.evaluate(
        user_id=_uid(),
        variables=[_v("amount", "importo"), _v("energy_class", "classe energetica")],
        state=GoalState(milestones=[Milestone(ref="f", title="proseguire", state="active")]),
    ))
    payload = blocking_ask_payload(out)
    assert payload["answer_kind"] == "bundle"
    assert set(payload["asked_refs"]) == {"amount", "energy_class"}
    assert [v["ref"] for v in payload["requested_variables"]] == payload["asked_refs"]
    assert all(v["required"] for v in payload["requested_variables"])
    assert payload["question"]


def test_a_resolved_sensitive_value_never_reaches_a_prompt_or_a_log(svc):
    out = _run(svc.evaluate(
        user_id=_uid(),
        variables=[_v("income", "reddito netto", sensitivity="high")],
        user_message="Il mio reddito netto è 2000 euro al mese.",
    ))
    obs = resolution_observation(out)
    blob = str(obs)
    assert "2000" not in blob, "a sensitive value must not be quoted back into reasoning"
    assert "già noto" in blob
    # ...and the trace says how much was avoided without saying what.
    trace = out.public_trace()
    assert "2000" not in str(trace)


def test_the_trace_says_what_it_did_without_saying_what_it_knows(svc):
    out = _run(svc.evaluate(
        user_id=_uid(),
        variables=[_v("a", "alpha"), _v("b", "beta")],
        answered_refs=["a"],
    ))
    trace = out.public_trace()
    assert trace["avoided"] == 1
    assert trace["asked"] == 1
    assert trace["next_step"] == "ask"


# ---------------------------------------------------------------------------
# The gate, inside the real loop
#
# The tests above prove the constitution. These prove it is actually wired into
# the turn: a decision that asks for five things, three of which ORA already
# has, must reach the person as a question about two — and a decision that asks
# for something already known must not reach them at all.
#
# The reasoning is stubbed on purpose. What is under test is the integration,
# not the model's willingness to fill in a field.
# ---------------------------------------------------------------------------

def _decision(missing, *, question="Mi servono alcune informazioni.", blocking=True):
    from conversation_engine.ai_core.models import (
        CognitiveDecision,
        MissingInformation,
        UncertaintyState,
    )

    return CognitiveDecision(
        response_mode="ask",
        user_intent_summary="test",
        reasoning_status="needs_user_input",
        message_to_user=question,
        question=question,
        uncertainty=UncertaintyState(
            level=0.6,
            blocking=blocking,
            missing_information=[MissingInformation(**m) for m in missing],
            operational_reason="serve per procedere",
        ),
    )


def _session_for(uid: str):
    from conversation_engine.models import ConversationSession, new_session_id

    return ConversationSession(
        id=new_session_id(),
        user_id=uid,
        origin="text",
        input="...",
        status="waiting_user",
        engine_version="ai-core-1.0",
        meta={"ui_mode": "ai_core", "ai_core": {}},
    )


def _required(ref, label, purpose="valutare le soluzioni adatte"):
    return {
        "ref": ref,
        "description": label,
        "label": label,
        "purpose": purpose,
        "necessity": "required",
        "blocking": True,
        "strategy": "ask",
    }


def test_the_loop_asks_only_for_what_it_could_not_resolve(monkeypatch):
    """B, inside the turn: three known, two asked, one question."""
    import asyncio as _aio

    from conversation_engine.ai_core import loop as loop_mod

    uid = _uid()
    sess = _session_for(uid)
    # Three of the five are already answered — recorded the way the loop
    # records them, on the session's own clarification history.
    sess.meta["ai_core"] = {"resolved_refs": ["age", "income", "employment"]}

    # The same decision every time: the loop may take more than one pass for
    # reasons of its own, and the gate must behave the same on each of them.
    decision = _decision([
        _required("age", "età"),
        _required("income", "reddito netto mensile"),
        _required("employment", "tipo di contratto"),
        _required("amount", "importo da finanziare"),
        _required("energy_class", "classe energetica"),
    ])

    async def decision_fn(*a, **k):
        return decision.model_dump()

    result = _run(loop_mod.run_cognitive_loop(
        sess=sess, user_message="Aiutami a capire quali soluzioni sono adatte a me.",
        db=None, decision_fn=decision_fn,
    ))

    ask = result.blocking_ask
    assert ask, "a blocking ask must survive the gate when something is genuinely missing"
    assert set(ask["asked_refs"]) == {"amount", "energy_class"}
    assert ask["answer_kind"] == "bundle"
    assert [v["ref"] for v in ask["requested_variables"]] == ask["asked_refs"]
    assert ask["avoided"] == 3, "three things ORA already knew, not asked"
    # One request, not two questions in a row.
    assert ask["question"].count("?") <= 1
    assert "età" not in ask["question"].lower()


def test_the_loop_does_not_ask_what_it_already_knows(monkeypatch):
    """H, inside the turn: the question is answered, not suppressed."""
    from conversation_engine.ai_core import loop as loop_mod
    from conversation_engine.ai_core.models import ActiveGoal, CognitiveDecision

    uid = _uid()
    sess = _session_for(uid)
    sess.meta["ai_core"] = {"resolved_refs": ["amount"]}

    seen = {"calls": 0, "observations": []}

    async def decision_fn(*a, **k):
        seen["calls"] += 1
        if seen["calls"] == 1:
            return _decision([_required("amount", "importo da finanziare")]).model_dump()
        # Second pass: the loop has told the model what it already knows.
        # Whatever the call signature, the nudge is somewhere in what the
        # model was given — that is the whole point of it.
        seen["observations"].append(str(a) + str(k))
        return CognitiveDecision(
            response_mode="answer",
            user_intent_summary="test",
            reasoning_status="enough_information",
            message_to_user="Procedo con quello che so.",
        ).model_dump()

    result = _run(loop_mod.run_cognitive_loop(
        sess=sess, user_message="Vai avanti.", db=None, decision_fn=decision_fn,
    ))

    assert seen["calls"] == 2, "the model must be given a second chance with what ORA knows"
    assert result.blocking_ask is None, "nothing was missing, so nothing may be asked"
    assert result.mode == "answer"
    # The nudge carried the resolution, so the model could actually proceed.
    blob = " ".join(seen["observations"])
    assert "INFORMATION_ALREADY_KNOWN" in blob


def test_a_useful_only_need_never_reaches_the_person():
    """I, inside the turn."""
    from conversation_engine.ai_core import loop as loop_mod
    from conversation_engine.ai_core.models import CognitiveDecision

    sess = _session_for(_uid())
    calls = {"n": 0}

    async def decision_fn(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return _decision([
                {"ref": "nice", "description": "sarebbe utile", "necessity": "useful",
                 "blocking": False, "strategy": "ask"},
            ], blocking=True).model_dump()
        return CognitiveDecision(
            response_mode="answer", user_intent_summary="t",
            reasoning_status="enough_information", message_to_user="Procedo.",
        ).model_dump()

    result = _run(loop_mod.run_cognitive_loop(
        sess=sess, user_message="Vai avanti.", db=None, decision_fn=decision_fn,
    ))
    assert result.blocking_ask is None


def test_the_gate_never_costs_a_turn_when_it_cannot_run(monkeypatch):
    """Guidance improves an ask. It is never a dependency of one."""
    from conversation_engine.ai_core import loop as loop_mod

    def explode(*a, **k):
        raise RuntimeError("guidance is unavailable")

    monkeypatch.setattr("guidance.service.GuidanceService.evaluate", explode, raising=True)

    sess = _session_for(_uid())

    async def decision_fn(*a, **k):
        return _decision([_required("amount", "importo")]).model_dump()

    result = _run(loop_mod.run_cognitive_loop(
        sess=sess, user_message="Aiutami.", db=None, decision_fn=decision_fn,
    ))
    # The question the model wrote is still a legitimate question.
    assert result.mode == "ask"
    assert result.blocking_ask is not None
    assert result.blocking_ask["asked_refs"] == ["amount"]


def test_the_reconstruction_is_carried_across_turns():
    """The state survives the turn that produced it, and keeps its identity."""
    from conversation_engine.ai_core import loop as loop_mod
    from conversation_engine.ai_core.models import CognitiveDecision

    sess = _session_for(_uid())

    async def decision_fn(*a, **k):
        return CognitiveDecision(
            response_mode="answer",
            user_intent_summary="t",
            reasoning_status="enough_information",
            message_to_user="Ok.",
            goal_state={
                "objective": "Portare a termine l'operazione",
                "stage": "Fase avanzata",
                "milestones": [
                    {"ref": "a", "title": "Primo passo", "state": "done", "basis": "fact"},
                    {"ref": "b", "title": "Passo corrente", "state": "active"},
                    {"ref": "c", "title": "Passo futuro", "state": "upcoming"},
                ],
            },
        ).model_dump()

    _run(loop_mod.run_cognitive_loop(
        sess=sess, user_message="Ci sono quasi.", db=None, decision_fn=decision_fn,
    ))

    stored = (sess.meta or {}).get("ai_core", {}).get("guidance_state")
    assert stored, "the reconstruction must outlive the turn that produced it"
    assert stored["revision"] == 1
    residual = [m for m in stored["milestones"] if m["state"] not in ("done", "not_applicable")]
    assert [m["ref"] for m in residual] == ["b", "c"], "only what remains is the path"


# ---------------------------------------------------------------------------
# Domain neutrality
# ---------------------------------------------------------------------------

def test_a_blocked_action_asks_instead_of_apologising():
    """
    Found live: "fissa l'appuntamento dal notaio e mettilo in agenda" produced
    "Mi manca un'informazione necessaria per procedere in modo affidabile."
    The reasoning had written the exact question; refusing the side effect threw
    it away, so the person was told there was a problem and not told what would
    solve it — and nothing recorded what ORA was waiting for.
    """
    from conversation_engine.ai_core.governance import validate_decision
    from conversation_engine.ai_core.tools import ToolRegistry

    out = validate_decision(
        {
            "response_mode": "act",
            "user_intent_summary": "fissare un appuntamento",
            "reasoning_status": "needs_user_input",
            "message_to_user": None,
            "question": "Hai già una data e un orario per l'appuntamento dal notaio?",
            "uncertainty": {
                "level": 0.8,
                "blocking": True,
                "operational_reason": "serve la data",
                "missing_information": [{
                    "ref": "notary_appointment_datetime",
                    "description": "Data e ora dell'appuntamento",
                    "label": "data e ora dell'appuntamento dal notaio",
                    "purpose": "creare l'evento in agenda",
                    "necessity": "required",
                    "blocking": True,
                    "strategy": "ask",
                }],
            },
        },
        tools=ToolRegistry(),
    )

    assert out.decision.response_mode == "ask", "a blocked action is an ask"
    assert "blocking_uncertainty_for_action" in out.errors, "the refusal still stands"
    assert "Mi manca un" not in (out.decision.message_to_user or "")
    assert "notaio" in (out.decision.message_to_user or "").lower()

    # The same is true of a blocked *write*, which reached the person as
    # "Mi manca un'informazione necessaria per eseguire questa azione in modo
    # affidabile." on the very first turn of a live QA run.
    blocked_write = validate_decision(
        {
            "response_mode": "tool",
            "user_intent_summary": "creare il piano",
            "reasoning_status": "needs_user_input",
            "message_to_user": None,
            "question": "Finanzierai l'acquisto con un mutuo o con risparmi?",
            "tool_call": {"name": "create_plan", "arguments": {}},
            "uncertainty": {
                "level": 0.8,
                "blocking": True,
                "operational_reason": "serve la modalità",
                "missing_information": [{
                    "ref": "financing_mode",
                    "description": "Come viene finanziato l'acquisto",
                    "label": "modalità di finanziamento",
                    "purpose": "il percorso cambia di conseguenza",
                    "necessity": "required",
                    "blocking": True,
                    "strategy": "ask",
                }],
            },
        },
        tools=ToolRegistry(),
    )
    if "blocking_uncertainty_for_write" in blocked_write.errors:
        assert blocked_write.decision.response_mode == "ask"
        assert "Mi manca un" not in (blocked_write.decision.message_to_user or "")


# ---------------------------------------------------------------------------
# ORA chooses the step; the person chooses their life
#
# These are about intent, not phrasing. Nothing here asserts the sentence a
# model produced — only that a turn which hands the process back is recognised
# as such, and that one which asks about the person's own life is not.
# ---------------------------------------------------------------------------

def test_handing_the_process_back_is_recognised():
    from guidance.wording import is_meta_choice

    handing_back = [
        # Every one of these is a sentence a live model actually produced.
        "Possiamo procedere passo dopo passo: hai già in programma le scadenze "
        "principali o ci sono aspetti specifici, come la gestione di un mutuo, "
        "su cui vuoi concentrarti?",
        "C'è qualche aspetto in particolare su cui vuoi concentrarti adesso?",
        "Come vuoi procedere con le date di uscita e di inizio?",
        "Vuoi che approfondiamo la parte documentale oppure quella del mutuo?",
        "Vuoi che approfondiamo subito la parte relativa al finanziamento o "
        "alle scadenze del compromesso?",
        "Posso aiutarti a impostare un confronto tra i principali istituti o "
        "i requisiti necessari?",
        "Hai già una banca di riferimento o un'offerta in corso, oppure "
        "preferisci valutare le opzioni disponibili?",
        "Possiamo procedere subito a impostare i contatti o preferisci "
        "verificare prima qualche aspetto in particolare?",
        "Preferisci concentrarti sulle verifiche oppure sul notaio?",
        "Da dove vuoi partire?",
        "Cosa preferisci fare adesso?",
        "How would you like to proceed?",
    ]
    for text in handing_back:
        assert is_meta_choice(text), text


def test_a_real_life_choice_is_not_a_process_choice():
    """The person's own decisions must survive this untouched."""
    from guidance.wording import is_meta_choice

    theirs = [
        "Preferisci un tasso fisso o variabile?",
        "Vuoi che lo inserisca in agenda?",          # consent for a chosen action
        "Qual è la data del rogito?",
        "Accetti l'offerta o preferisci negoziare?",  # the life decision itself
        "Il mutuo o i risparmi?",
        "Finanzierai l'acquisto con un mutuo o con risparmi personali?",
        "Vuoi che ti prenoti l'appuntamento dal notaio?",
        "Posso aiutarti a impostare il confronto tra le offerte?",
        "Hai già avviato la richiesta di mutuo con una banca o procedi con "
        "fondi propri?",
        "Vuoi il tasso fisso oppure preferisci il variabile?",
        "Possiamo procedere con la richiesta di mutuo?",
        "Possiamo fissare lunedì o martedì?",
        "Ho impostato le verifiche catastali: procedo con la richiesta al Comune.",
    ]
    for text in theirs:
        assert not is_meta_choice(text), text


def test_a_question_written_for_another_reader_is_not_shown():
    from guidance.wording import looks_english

    assert looks_english("Have you finalized the date for the property deed signing?")
    assert looks_english("Check mortgage status before signing the preliminary contract")
    assert not looks_english("Qual è la data e l'ora del rogito?")
    assert not looks_english("Hai già definito il budget per il mutuo?")


def test_the_ask_refuses_wording_that_hands_the_process_back():
    """
    The model writes the question when it can. A meta-choice is the one case
    where its words cannot stand: guidance knows exactly what is missing.
    """
    from guidance.questioning import build_ask

    step = build_ask(
        [_v("last_day", "ultimo giorno nell'azienda attuale"),
         _v("start_date", "data di inizio della nuova")],
        asked_refs=["last_day", "start_date"],
        fallback_question="Come vuoi procedere con le date di uscita e di inizio?",
    )
    assert not is_meta(step.question), step.question
    assert "ultimo giorno" in step.question.lower()
    assert "data di inizio" in step.question.lower()


def test_the_ask_refuses_wording_in_another_language():
    from guidance.questioning import build_ask

    step = build_ask(
        [_v("deed_date", "data del rogito")],
        asked_refs=["deed_date"],
        fallback_question="Have you finalized the date for the property deed signing?",
    )
    assert step.question == "data del rogito?".capitalize() or "rogito" in step.question.lower()
    assert "Have you" not in step.question


def test_the_loop_will_not_let_ora_ask_which_step_to_work_on():
    """
    Inside the turn: ORA reconstructed the goal, then ended by asking the
    person which part to work on. It is given one more pass to choose.
    """
    from conversation_engine.ai_core import loop as loop_mod
    from conversation_engine.ai_core.models import CognitiveDecision

    sess = _session_for(_uid())
    seen = {"calls": 0, "payloads": []}

    def _answer(text, **extra):
        return CognitiveDecision(
            response_mode="answer",
            user_intent_summary="t",
            reasoning_status="enough_information",
            message_to_user=text,
            **extra,
        ).model_dump()

    async def decision_fn(*a, **k):
        seen["calls"] += 1
        if seen["calls"] == 1:
            return _answer(
                "Il primo passo è ormai alle spalle. C'è qualche aspetto in "
                "particolare su cui vuoi concentrarti adesso?",
                goal_state={
                    "objective": "Portare a termine l'operazione",
                    "stage": "Fase intermedia",
                    "milestones": [
                        {"ref": "a", "title": "Primo passo", "state": "done", "basis": "fact"},
                        {"ref": "b", "title": "Passo corrente", "state": "active"},
                    ],
                },
            )
        seen["payloads"].append(str(a) + str(k))
        return _answer("Procedo con le verifiche: ho bisogno del documento X.")

    result = _run(loop_mod.run_cognitive_loop(
        sess=sess, user_message="Ho già firmato.", db=None, decision_fn=decision_fn,
    ))

    assert seen["calls"] == 2, "the model gets one pass to choose the step itself"
    assert "META_CHOICE_NOT_ALLOWED" in " ".join(seen["payloads"])
    assert not is_meta(result.ora_text or "")


def test_what_the_model_called_useful_may_not_be_asked_in_prose():
    """
    Found live. The reasoning marked a need `useful`, `blocking: false` — and
    then asked for it anyway inside the sentence it wrote, where the guidance
    gate, which sits on `response_mode=ask`, never sees it. Nothing here judges
    whether the question was worth asking: the model is held to its own word.
    """
    from conversation_engine.ai_core import loop as loop_mod
    from conversation_engine.ai_core.models import (
        CognitiveDecision,
        MissingInformation,
        UncertaintyState,
    )

    sess = _session_for(_uid())
    seen = {"calls": 0, "payloads": []}

    def _answer(text, missing=None, **extra):
        return CognitiveDecision(
            response_mode="answer",
            user_intent_summary="t",
            reasoning_status="enough_information",
            message_to_user=text,
            uncertainty=UncertaintyState(
                level=0.3,
                blocking=False,
                missing_information=[MissingInformation(**m) for m in (missing or [])],
                operational_reason="—",
            ) if missing else None,
            **extra,
        ).model_dump()

    async def decision_fn(*a, **k):
        seen["calls"] += 1
        if seen["calls"] == 1:
            return _answer(
                "Ho aggiornato il percorso. Hai già un riferimento oppure lo cerchiamo?",
                missing=[{
                    "ref": "some_reference", "description": "un riferimento",
                    "label": "riferimento", "purpose": "orientare i tempi",
                    "necessity": "useful", "blocking": False, "strategy": "ask",
                }],
                goal_state={
                    "objective": "Portare a termine l'operazione",
                    "stage": "In corso",
                    "milestones": [
                        {"ref": "a", "title": "Fatto", "state": "done", "basis": "fact"},
                        {"ref": "b", "title": "Passo corrente", "state": "active"},
                    ],
                },
            )
        seen["payloads"].append(str(a) + str(k))
        return _answer("Procedo con il passo corrente.")

    result = _run(loop_mod.run_cognitive_loop(
        sess=sess, user_message="Vai avanti.", db=None, decision_fn=decision_fn,
    ))

    assert seen["calls"] == 2
    assert "ASKED_FOR_WHAT_IS_NOT_REQUIRED" in " ".join(seen["payloads"])
    assert "?" not in (result.ora_text or ""), "nothing required was missing"


def test_a_required_need_is_still_allowed_to_be_asked():
    """The guard must not turn into 'never ask anything'."""
    from conversation_engine.ai_core import loop as loop_mod

    sess = _session_for(_uid())
    calls = {"n": 0}

    async def decision_fn(*a, **k):
        calls["n"] += 1
        return _decision([_required("amount", "importo da finanziare")]).model_dump()

    result = _run(loop_mod.run_cognitive_loop(
        sess=sess, user_message="Aiutami.", db=None, decision_fn=decision_fn,
    ))
    assert result.mode == "ask"
    assert result.blocking_ask is not None


def test_offering_a_direction_is_allowed_when_ora_knows_nothing_yet():
    """
    The nudge must not fire without a reconstruction behind it: with no idea of
    the goal, asking where to start is honest rather than lazy.
    """
    from conversation_engine.ai_core import loop as loop_mod
    from conversation_engine.ai_core.models import CognitiveDecision

    sess = _session_for(_uid())
    calls = {"n": 0}

    async def decision_fn(*a, **k):
        calls["n"] += 1
        return CognitiveDecision(
            response_mode="answer",
            user_intent_summary="t",
            reasoning_status="enough_information",
            message_to_user="Da dove vuoi partire?",
        ).model_dump()

    _run(loop_mod.run_cognitive_loop(
        sess=sess, user_message="Ciao.", db=None, decision_fn=decision_fn,
    ))
    assert calls["n"] == 1, "nothing to choose from means nothing to correct"


# ---------------------------------------------------------------------------
# One question, one meaning
#
# "Domande per te" showed three rows for one blocker: the real question, the
# same thing again as an English suggestion, and a third notice about the same
# work. Two of them could not be answered in any way that moved anything.
# ---------------------------------------------------------------------------

def _home_with(open_questions, suggestions):
    return {
        "open_questions": open_questions,
        "ora_ti_consiglia": suggestions,
        "priorities": [],
        "primary_focus": None,
    }


def test_a_real_blocker_is_the_only_question_on_its_page():
    from activity import presentation as ap

    home = _home_with(
        [{
            "id": "q_1",
            "question": "Qual è la data del rogito?",
            "why_needed": "Serve per fissare l'appuntamento.",
            "session_id": "ces_1",
        }],
        [
            {"id": "s_1", "title": "Have you finalized the deed date?",
             "description": "…", "meta": {"delivery": "ask_user"}},
            {"id": "s_2", "title": "Avvio verifiche per la casa",
             "description": "…", "meta": {"delivery": "propose_action"}},
        ],
    )

    open_rows = ap._open_question_rows(home["open_questions"])
    asked_rows = ap._question_rows(home)
    assert len(open_rows) == 1 and len(asked_rows) == 2, "the fixture is the real shape"

    # The rule itself, as the page applies it.
    questions = open_rows
    demoted = ap._demoted_rows(asked_rows)
    assert [r["kind"] for r in questions] == ["question"]
    assert all(r["kind"] == "update" for r in demoted), "a notice is not a blocker"
    assert len(demoted) == 2, "nothing is discarded — it moves"

    # And that this is what the page actually does, not just what it could do.
    import inspect

    src = inspect.getsource(ap)
    src = " ".join(
        line for line in src.splitlines() if not line.strip().startswith("#")
    )
    assert "if open_rows:" in src and "asked_rows = []" in src, (
        "a real blocker must clear the suggestion rows from the question section"
    )
    assert "_demoted_rows(demoted)" in src, "and they must land in updates"


def test_without_a_blocker_the_suggestions_are_still_the_section():
    """Attention keeps its place when no work has actually stopped."""
    from activity import presentation as ap

    home = _home_with([], [
        {"id": "s_1", "title": "Controlla lo stato del mutuo",
         "description": "…", "meta": {"delivery": "ask_user"}},
    ])
    assert ap._open_question_rows(home["open_questions"]) == []
    assert len(ap._question_rows(home)) == 1


def test_the_page_counts_what_it_shows():
    """
    `todo` is what the summary strip says. It must be countable from the rows
    above it, which is only true if it counts the same list.
    """
    import inspect

    from activity import presentation as ap

    src = inspect.getsource(ap.build_activity_payload) if hasattr(
        ap, "build_activity_payload"
    ) else inspect.getsource(ap)
    assert "todo = len(questions)" in src, (
        "the count must derive from the rendered question list, not a second aggregation"
    )


# ---------------------------------------------------------------------------
# The product invariant
#
#   GUIDANCE MUST EITHER ADVANCE THE WORK OR ASK FOR WHAT BLOCKS ADVANCEMENT.
#   It must not merely describe what advancement would look like.
#
# This is the whole of V3.2 in one sentence, and the failure it names is the
# quiet one: ORA reconstructs the path perfectly, says what the next step would
# be, and stops — leaving the person to work out what it needs and volunteer
# it, which is the arrangement guidance exists to end.
# ---------------------------------------------------------------------------

def test_a_described_plan_is_not_a_finished_turn():
    from conversation_engine.ai_core import loop as loop_mod
    from conversation_engine.ai_core.models import CognitiveDecision

    sess = _session_for(_uid())
    seen = {"calls": 0, "payloads": []}

    async def decision_fn(*a, **k):
        seen["calls"] += 1
        if seen["calls"] == 1:
            return CognitiveDecision(
                response_mode="answer",
                user_intent_summary="t",
                reasoning_status="enough_information",
                message_to_user=(
                    # Both live phrasings of the same dead end.
                    "Ho aggiornato il piano. Adesso procediamo con i primi "
                    "passi: la verifica della documentazione e la scelta del "
                    "notaio."
                ),
                goal_state={
                    "objective": "Portare a termine l'operazione",
                    "stage": "In corso",
                    "milestones": [
                        {"ref": "a", "title": "Fatto", "state": "done", "basis": "fact"},
                        {"ref": "b", "title": "Passo corrente", "state": "active"},
                    ],
                },
            ).model_dump()
        seen["payloads"].append(str(a) + str(k))
        return _decision([_required("doc", "documentazione catastale")]).model_dump()

    result = _run(loop_mod.run_cognitive_loop(
        sess=sess, user_message="Ho firmato.", db=None, decision_fn=decision_fn,
    ))

    assert seen["calls"] == 2, "a described plan must not end the turn"
    assert "DESCRIBED_INSTEAD_OF_ADVANCING" in " ".join(seen["payloads"])
    # It ended as the thing the invariant demands: a question about what blocks.
    assert result.mode == "ask"
    assert result.blocking_ask is not None
    assert result.blocking_ask["asked_refs"] == ["doc"]


def test_a_conclusion_about_the_person_needs_sufficiency_behind_it():
    """
    Found live: from an age, a contract type and a price, ORA said "hai ottimi
    requisiti" and moved on to comparing the market. Whether that was true is
    not the point — nothing established what it rested on.
    """
    from conversation_engine.ai_core import loop as loop_mod
    from conversation_engine.ai_core.models import CognitiveDecision

    sess = _session_for(_uid())
    seen = {"calls": 0, "payloads": []}

    async def decision_fn(*a, **k):
        seen["calls"] += 1
        if seen["calls"] == 1:
            return CognitiveDecision(
                response_mode="answer",
                user_intent_summary="t",
                reasoning_status="enough_information",
                message_to_user="Con questi elementi hai ottimi requisiti.",
                goal_state={
                    "objective": "Scegliere",
                    "stage": "In corso",
                    "milestones": [{"ref": "b", "title": "Passo corrente", "state": "active"}],
                },
            ).model_dump()
        seen["payloads"].append(str(a) + str(k))
        return _decision([_required("amount", "importo da finanziare")]).model_dump()

    _run(loop_mod.run_cognitive_loop(
        sess=sess, user_message="Aiutami a scegliere.", db=None, decision_fn=decision_fn,
    ))
    assert seen["calls"] == 2
    assert "CONCLUSION_WITHOUT_SUFFICIENCY" in " ".join(seen["payloads"])


def test_being_stopped_from_re_asking_is_not_a_dead_end():
    """
    Found live. Governance refuses a repeated clarification — correctly — and
    the turn ended "Non ti richiedo di nuovo lo stesso dettaglio. Posso
    continuare con un'ipotesi prudente, oppure fermarmi qui." Nothing moved,
    nothing was asked, and the person was handed a choice they cannot evaluate.
    """
    from conversation_engine.ai_core import loop as loop_mod
    from conversation_engine.ai_core.models import CognitiveDecision

    sess = _session_for(_uid())
    # The ref has been asked once already, which is what governance counts.
    sess.meta["ai_core"] = {
        "clarification_history": [{"key": "bank", "attempts": 1}],
        # A reconstruction already exists — this is a turn inside real work.
        "guidance_state": {
            "objective": "Portare a termine l'operazione",
            "stage": "In corso",
            "milestones": [{"ref": "b", "title": "Passo corrente", "state": "active"}],
            "revision": 1,
        },
    }
    seen = {"calls": 0, "payloads": []}

    async def decision_fn(*a, **k):
        seen["calls"] += 1
        if seen["calls"] == 1:
            return _decision(
                [_required("bank", "istituto di credito")],
                question="Hai già scelto la banca?",
            ).model_dump()
        seen["payloads"].append(str(a) + str(k))
        return CognitiveDecision(
            response_mode="answer",
            user_intent_summary="t",
            reasoning_status="enough_information",
            message_to_user="Procedo con le verifiche catastali intanto.",
            goal_state={
                "objective": "O", "stage": "S",
                "milestones": [{"ref": "b", "title": "Passo", "state": "active"}],
            },
        ).model_dump()

    result = _run(loop_mod.run_cognitive_loop(
        sess=sess, user_message="Non ancora.", db=None, decision_fn=decision_fn,
    ))

    assert seen["calls"] == 2, "being blocked from re-asking must not end the turn"
    assert "ALREADY_ASKED_THAT" in " ".join(seen["payloads"])
    assert "fermarmi qui" not in (result.ora_text or "")


def test_a_refused_action_without_a_question_is_a_dead_end():
    """
    Found live, on the very first turn: the reasoning tried to write the plan,
    governance refused it because something required was missing, and the
    person read "Mi manca un'informazione necessaria per eseguire questa
    azione in modo affidabile." True, useless, and nothing recorded about what
    ORA was waiting for. This one does not need a reconstruction to be wrong.
    """
    from conversation_engine.ai_core import loop as loop_mod
    from conversation_engine.ai_core.models import (
        CognitiveDecision,
        MissingInformation,
        UncertaintyState,
    )

    sess = _session_for(_uid())
    seen = {"calls": 0, "payloads": []}

    async def decision_fn(*a, **k):
        seen["calls"] += 1
        if seen["calls"] == 1:
            return CognitiveDecision(
                response_mode="act",
                user_intent_summary="impostare il piano",
                reasoning_status="needs_user_input",
                message_to_user=None,
                question=None,
                uncertainty=UncertaintyState(
                    level=0.8,
                    blocking=True,
                    operational_reason="manca la modalità",
                    missing_information=[MissingInformation(**{
                        "ref": "financing_mode",
                        "description": "come viene finanziato l'acquisto",
                        "label": "modalità di finanziamento",
                        "purpose": "il percorso cambia di conseguenza",
                        "necessity": "required",
                        "blocking": True,
                        "strategy": "ask",
                    })],
                ),
            ).model_dump()
        seen["payloads"].append(str(a) + str(k))
        return _decision(
            [_required("financing_mode", "modalità di finanziamento")],
            question="Finanzierai con un mutuo o con mezzi propri?",
        ).model_dump()

    result = _run(loop_mod.run_cognitive_loop(
        sess=sess, user_message="Ho firmato il compromesso.", db=None,
        decision_fn=decision_fn,
    ))

    assert seen["calls"] == 2
    assert "BLOCKED_WITHOUT_A_QUESTION" in " ".join(seen["payloads"])
    assert "Mi manca un" not in (result.ora_text or "")
    assert result.mode == "ask" and result.blocking_ask is not None


def test_the_replacement_question_is_what_the_person_reads():
    """
    Guidance refuses wording that hands the process back — but it was refusing
    it only on the stored question. The chat bubble still showed the sentence
    that had been rejected, which is where the question is actually asked.
    """
    from conversation_engine.ai_core import loop as loop_mod

    sess = _session_for(_uid())

    async def decision_fn(*a, **k):
        return _decision(
            [_required("documents", "documenti catastali")],
            question=(
                "Hai già i documenti catastali, oppure preferisci che "
                "impostiamo una checklist dei controlli?"
            ),
        ).model_dump()

    result = _run(loop_mod.run_cognitive_loop(
        sess=sess, user_message="Ho firmato.", db=None, decision_fn=decision_fn,
    ))

    assert result.mode == "ask"
    assert not is_meta(result.ora_text or ""), result.ora_text
    assert result.ora_text == result.blocking_ask["question"], (
        "the stored question and the visible one must be the same question"
    )


def test_what_ora_already_knows_is_not_asked_on_screen_either():
    """
    Found live: guidance stored "importo del mutuo?" — one variable, the other
    dropped because ORA already knew it — while the chat asked "qual è
    l'importo … e per quanti anni vorresti dilazionarlo?". The guarantee has to
    hold where the person reads the question, or it is not a guarantee.
    """
    from conversation_engine.ai_core import loop as loop_mod

    sess = _session_for(_uid())
    # ORA already knows the duration — resolved on an earlier pass.
    sess.meta["ai_core"] = {"resolved_refs": ["duration"]}

    async def decision_fn(*a, **k):
        return _decision(
            [_required("amount", "importo del mutuo"),
             _required("duration", "durata del mutuo")],
            question="Qual è l'importo e per quanti anni vorresti dilazionarlo?",
        ).model_dump()

    result = _run(loop_mod.run_cognitive_loop(
        sess=sess, user_message="Aiutami con il mutuo.", db=None,
        decision_fn=decision_fn,
    ))

    assert result.blocking_ask["asked_refs"] == ["amount"]
    assert result.blocking_ask["avoided"] == 1
    assert "anni" not in (result.ora_text or "").lower(), result.ora_text
    assert result.ora_text == result.blocking_ask["question"]


def test_an_ordinary_answer_is_left_alone():
    """
    The invariant must not become "always ask". A turn that actually answers
    something, or that does something, is movement and is finished.
    """
    from conversation_engine.ai_core import loop as loop_mod
    from conversation_engine.ai_core.models import CognitiveDecision

    for text in (
        "Il notaio costa in media tra 1.500 e 2.500 euro.",
        "Ti confermo che il rogito può essere fissato anche di sabato.",
    ):
        sess = _session_for(_uid())
        calls = {"n": 0}

        async def decision_fn(*a, **k):
            calls["n"] += 1
            return CognitiveDecision(
                response_mode="answer",
                user_intent_summary="t",
                reasoning_status="enough_information",
                message_to_user=text,
                goal_state={
                    "objective": "O",
                    "stage": "S",
                    "milestones": [{"ref": "b", "title": "Passo", "state": "active"}],
                },
            ).model_dump()

        _run(loop_mod.run_cognitive_loop(
            sess=sess, user_message="Quanto costa?", db=None, decision_fn=decision_fn,
        ))
        assert calls["n"] == 1, f"an answer is movement: {text}"


def test_when_everything_required_is_known_nothing_useful_is_asked(svc):
    """
    The second invariant, at service level: sufficiency reached means the turn
    proceeds. `useful` and `optional` do not get a second chance to become a
    question just because a question was going to be asked anyway.
    """
    known = _v("amount", "importo")
    interesting = _v("energy_class", "classe energetica", necessity="useful")
    nice = _v("agency", "agenzia", necessity="optional")

    out = _run(svc.evaluate(
        user_id=_uid(),
        variables=[known, interesting, nice],
        user_message="L'importo è 150.000 euro.",
    ))
    assert out.next_step.kind == "proceed", "nothing required is missing"
    assert not out.next_step.requested
    assert {v.ref for v in out.sufficiency.deferred()} == {"energy_class", "agency"}


# ---------------------------------------------------------------------------
# One turn, one question, one meaning
#
# A question is generated, stored, shown in the thread, and projected onto two
# other surfaces. Every one of those is a chance for it to become a slightly
# different question — and it did: the thread said one thing, Home said
# another, and the work it was filed under belonged to a third step.
# ---------------------------------------------------------------------------

def test_a_turn_on_live_work_ends_in_something_real():
    """A: the plan described, nothing asked, nothing done, is not an ending."""
    from conversation_engine.ai_core import loop as loop_mod
    from conversation_engine.ai_core.models import CognitiveDecision

    sess = _session_for(_uid())
    calls = {"n": 0}

    def _narration():
        return CognitiveDecision(
            response_mode="answer",
            user_intent_summary="t",
            reasoning_status="enough_information",
            message_to_user=(
                "Ho impostato il piano e creato lo spazio di lavoro per "
                "gestire il passaggio di consegne."
            ),
            goal_state={
                "objective": "Cambiare lavoro",
                "stage": "Dimissioni date",
                "milestones": [
                    {"ref": "a", "title": "Dimissioni", "state": "done", "basis": "fact"},
                    {"ref": "b", "title": "Preavviso", "state": "active"},
                ],
            },
        ).model_dump()

    async def decision_fn(*a, **k):
        calls["n"] += 1
        if calls["n"] < 3:
            return _narration()
        return _decision([_required("last_day", "ultimo giorno di lavoro")]).model_dump()

    result = _run(loop_mod.run_cognitive_loop(
        sess=sess, user_message="Ho dato le dimissioni.", db=None,
        decision_fn=decision_fn,
    ))
    assert calls["n"] >= 3, "narration must be sent back more than once if it repeats"
    assert result.mode == "ask"
    assert result.trace.get("guidance_outcome") == "ask"


def test_a_turn_that_only_narrates_is_recorded_as_limbo():
    """
    A, the tail case: the model narrates through every correction. The turn is
    not silently accepted as fine — it is named, so it can be counted.
    """
    from conversation_engine.ai_core import loop as loop_mod
    from conversation_engine.ai_core.models import CognitiveDecision

    sess = _session_for(_uid())

    async def decision_fn(*a, **k):
        return CognitiveDecision(
            response_mode="answer",
            user_intent_summary="t",
            reasoning_status="enough_information",
            message_to_user="Ho impostato il piano. Le prossime tappe sono in corso.",
            goal_state={
                "objective": "O", "stage": "S",
                "milestones": [{"ref": "b", "title": "Passo", "state": "active"}],
            },
        ).model_dump()

    result = _run(loop_mod.run_cognitive_loop(
        sess=sess, user_message="Vai avanti.", db=None, decision_fn=decision_fn,
    ))
    assert result.trace.get("guidance_outcome") == "limbo"


def test_the_question_asked_is_the_question_stored():
    """B: an OpenQuestion that says something the thread never said is a ghost."""
    from conversation_engine.ai_core import loop as loop_mod

    sess = _session_for(_uid())

    async def decision_fn(*a, **k):
        return _decision(
            [_required("last_day", "ultimo giorno di lavoro"),
             _required("start_date", "data di inizio del nuovo impiego")],
            # Wording guidance will not let stand, so the stored question and
            # the model's sentence genuinely differ unless something makes
            # them one.
            question=("Vuoi che procediamo con il preavviso o preferisci "
                      "valutare prima l'inserimento?"),
        ).model_dump()

    result = _run(loop_mod.run_cognitive_loop(
        sess=sess, user_message="Ho dato le dimissioni.", db=None,
        decision_fn=decision_fn,
    ))
    assert result.blocking_ask is not None
    assert not is_meta(result.ora_text or ""), result.ora_text
    assert result.ora_text == result.blocking_ask["question"], (
        "the thread and the stored question are one question"
    )
    assert result.trace.get("guidance_outcome") == "ask"


def test_the_question_is_filed_under_the_step_it_came_from():
    """
    D: live, a question about scheduling a meeting was filed under "definire la
    data esatta di fine rapporto" — the plan item that happened to be in focus.
    """
    from guidance.bridge import blocking_ask_payload
    from guidance.models import GoalState, NextStep, Sufficiency, Variable
    from guidance.service import GuidanceOutcome

    state = GoalState(
        objective="Cambiare lavoro",
        stage="Preavviso",
        milestones=[
            {"ref": "m_notice", "title": "Gestione del preavviso",
             "state": "active", "plan_item_id": "item_7"},
            {"ref": "m_start", "title": "Inserimento nella nuova azienda",
             "state": "upcoming", "plan_item_id": "item_9"},
        ],
    )
    asked = Variable(ref="last_day", label="ultimo giorno di lavoro",
                     purpose="calcolare il preavviso", necessity="required")
    outcome = GuidanceOutcome(
        state=state,
        sufficiency=Sufficiency(variables=[asked]),
        next_step=NextStep(
            kind="ask",
            title="Gestione del preavviso",
            milestone_ref="m_notice",
            question="Qual è il tuo ultimo giorno di lavoro?",
            why_needed="Serve per calcolare il preavviso.",
            requested=[asked],
        ),
        avoided=0,
        reason="required_missing",
    )

    payload = blocking_ask_payload(outcome)
    assert payload["step_title"] == "Gestione del preavviso"
    assert payload["milestone_ref"] == "m_notice"
    assert payload["plan_item_id"] == "item_7", "not whichever item was in focus"
    assert [v["ref"] for v in payload["requested_variables"]] == ["last_day"]
    assert "preavviso" in payload["why_needed"].lower()


def test_both_surfaces_project_the_same_question_entity():
    """C: Home and Attività are two views of one row, by identity."""
    from activity import presentation as ap

    stored = {
        "id": "q_42",
        "question": "Qual è il tuo ultimo giorno di lavoro?",
        "why_needed": "Serve per calcolare il preavviso.",
        "context_label": "Gestione del preavviso",
        "session_id": "ces_1",
    }
    rows = ap._open_question_rows([stored])
    assert len(rows) == 1
    row = rows[0]
    assert row["question_id"] == "q_42", "the same backend entity"
    assert row["id"] == "question:q_42", "namespaced identity, not wording"
    assert row["title"] == stored["question"], "Activity shows the stored question"
    assert row["detail"] == stored["why_needed"]
    assert row["context_label"] == stored["context_label"]


def test_no_name_in_the_module_knows_a_domain():
    import ast

    banned = (
        "mutuo", "mortgage", "house", "casa", "immobile", "travel", "viaggio",
        "study", "esame", "career", "lavoro", "insurance", "assicurazione", "car", "auto",
    )
    for rel in ("guidance/models.py", "guidance/resolution.py", "guidance/questioning.py",
                "guidance/service.py", "guidance/bridge.py"):
        tree = ast.parse((Path(_BACKEND) / rel).read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                names.add(node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(node.name)
                names.update(a.arg for a in node.args.args)
                names.update(a.arg for a in node.args.kwonlyargs)
            elif isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
        # Whole words only: "carries" is not a car, and "casa" inside a
        # sentence about houses in a comment is prose, not a domain branch.
        import re

        def says(text: str, word: str) -> bool:
            return re.search(rf"\b{re.escape(word)}\b", text) is not None

        lowered = " ".join(n.lower().replace("_", " ") for n in names)
        for word in banned:
            assert not says(lowered, word), f"{rel}: {word!r} appears in a name"

        # No domain word may reach a person through a literal either.
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if len(node.value) > 200:
                    continue  # prose
                for word in banned:
                    assert not says(node.value.lower(), word), f"{rel}: {word!r} in a literal"


def test_no_external_research_was_introduced():
    """V3.2 knows what it needs. Finding it out in the world comes later."""
    import ast

    for rel in ("guidance/models.py", "guidance/resolution.py", "guidance/questioning.py",
                "guidance/service.py", "guidance/bridge.py"):
        src = (Path(_BACKEND) / rel).read_text(encoding="utf-8")
        tree = ast.parse(src)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for banned in ("httpx", "requests", "aiohttp", "urllib"):
            assert banned not in imported, f"{rel} must not reach the network"
        assert "web_search" not in src
