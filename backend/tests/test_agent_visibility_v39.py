"""
V3.9 Sprint 2 close-out — useful expression: speaking without interrupting.

    SILENCE IS A VALID DECISION, NOT A DEFAULT PERSONALITY.
    DO NOT CONFUSE AVOIDING INTERRUPTION WITH HIDING USEFUL WORK.
    USEFUL EXPRESSION, NOT CHATTER.

Two failures, and they are opposite, which is why both are tested here.

The first is the one a well-built quiet system falls into. Having learned not
to interrupt, it learns not to speak; having learned that most things do not
deserve a notification, it concludes that most things do not deserve
mentioning. What comes out the other side is an assistant that works hard and
appears to do nothing — indistinguishable, from the outside, from one that
does nothing.

The second is cheaper to reach and much easier to spot: an assistant that
narrates. A line per step, "sto lavorando" with nothing behind it, the same
news three times because it was reconsidered three times.

Everything below sits between those two. And underneath it all, the rule that
keeps this from becoming a second notification system: visibility says how
much the work is worth showing, and V3.8 still owns whether anything
interrupts.

Every model call here is recorded. The two live calls this gate allows are
spent on judgement, not on this.
"""

from __future__ import annotations

import ast
import os
import re
import sys
import uuid
from pathlib import Path

import pytest

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import _loop_harness

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")
HERE = Path(_BACKEND)


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, uid):
    for coll in (
        "agent_goals", "agent_plans", "agent_journal", "agent_action_attempts",
        "agent_evidence", "agent_runs", "agent_updates", "autonomy_grants",
        "autonomy_policies", "autonomy_denials", "memories", "ambient_wakes",
        "ambient_activity", "delivery_plans",
    ):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


class FakeModel:
    def __init__(self, answers, default=None):
        self.answers = list(answers)
        self.default = default
        self.seen = []

    async def __call__(self, system, user):
        self.seen.append({"system": system, "user": user})
        if self.answers:
            return self.answers.pop(0)
        return dict(self.default) if isinstance(self.default, dict) else self.default


def _install(monkeypatch, model):
    import agent.reasoning as reasoning

    monkeypatch.setattr(reasoning, "_ask_model", model)


def _says(outcome="quiet_update", headline="Ho controllato quello che serviva.",
          about="certificato di residenza", **over):
    answer = {
        "outcome": outcome,
        "headline": headline,
        "about": about,
        "reasoning": "Vale la pena che lo sappia senza essere interrotto.",
    }
    answer.update(over)
    return answer


async def _service(db):
    from agent.service import AgentService

    service = AgentService(db)
    await service.ensure_indexes()
    return service


def _goal(uid, **over):
    from agent.models import AutonomousGoal

    fields = {
        "owner_id": uid,
        "status": "active",
        "objective": "Fare in modo che il certificato sia in mano prima di giovedì.",
        "desired_outcome": "Il certificato è disponibile giovedì mattina.",
        "success_criteria": ["Il certificato è in mano."],
    }
    fields.update(over)
    return AutonomousGoal(**fields)


async def _worked(service, uid, goal, *, claim="Lo sportello apre alle 8:30."):
    """A goal that has genuinely done something, with the trace to prove it."""
    from agent.models import AgentEvidence, ResultProvenance

    await service.evidence.record(AgentEvidence(
        owner_id=uid, goal_id=goal.id, claim=claim,
        provenance=ResultProvenance(
            source_class="external_research", capability="web.research",
            freshness="fresh",
        ),
    ))
    await service.repo.journal(
        uid, goal.id, kind="step_done", note="Ho cercato gli orari.",
        detail={"came_from": "external_research", "really_happened": True},
    )


def _facts(refs=("journal:1",), **over):
    facts = {
        "what_ora_did_this_time": [{"what": "Ho cercato gli orari.",
                                    "really_happened": True}],
        "what_it_found": [{"what_was_found": "Apre alle 8:30."}],
        "how_it_stands": {"still_going": True, "finished": False},
        "is_there_something_for_them_to_do": False,
        "refs": list(refs),
    }
    facts.update(over)
    return facts


# ---------------------------------------------------------------------------
# The distinction the gate exists for
# ---------------------------------------------------------------------------

def test_useful_work_can_be_seen_without_anybody_being_interrupted(monkeypatch):
    """
    §21/QA A: the case that made this necessary.

    ORA did something worth knowing and there is no reason to buzz a phone.
    Under one question — "should I interrupt" — that work disappears. Under
    two it lands quietly on a screen somebody looks at when they choose to.
    """
    async def body():
        client, db = await _db()
        uid = f"v39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            goal = _goal(uid)
            await service.repo.create_goal(goal)
            await _worked(service, uid, goal)

            _install(monkeypatch, FakeModel([
                _says("quiet_update", "Ho trovato gli orari: giovedì apre alle 8:30."),
            ]))
            decision = await service.visibility.consider(
                uid, goal, what_happened=_facts()
            )

            assert decision.outcome == "quiet_update"
            assert decision.is_visible is True
            assert decision.wants_a_person is False
            assert decision.headline

            # Visible, and nothing was sent: no delivery plan, no push.
            shown = await service.visibility.show(uid, goal, decision)
            assert shown is True
            assert await db.delivery_plans.count_documents({"owner_id": uid}) == 0, (
                "un aggiornamento tranquillo ha programmato una notifica"
            )

            line = await db.ambient_activity.find_one(
                {"owner_id": uid}, {"_id": 0, "summary": 1, "visibility": 1}
            )
            assert line is not None, "il lavoro utile è sparito"
            assert line["visibility"] == "ambient"
            assert "8:30" in line["summary"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_silence_is_still_available_and_costs_nothing(monkeypatch):
    """
    §22/QA B: a review that found nothing says nothing.

    The opposite failure is the easy one to fall into once speaking is
    allowed, so silence has to stay a first-class answer rather than a
    fallback nobody reaches.
    """
    async def body():
        client, db = await _db()
        uid = f"v39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            goal = _goal(uid)
            await service.repo.create_goal(goal)
            await _worked(service, uid, goal)

            _install(monkeypatch, FakeModel([
                _says("silent", headline="", about="niente di nuovo"),
            ]))
            decision = await service.visibility.consider(
                uid, goal, what_happened=_facts()
            )

            assert decision.outcome == "silent"
            assert decision.is_visible is False
            assert await db.ambient_activity.count_documents(
                {"owner_id": uid, "visibility": "ambient"}
            ) == 0
            assert await db.agent_updates.count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_finished_goal_may_be_worth_saying_and_the_model_decides(monkeypatch):
    """
    §15/§23/QA C: no `if completed: inform_user`.

    A tiny internal check finishing is not news. A problem being solved
    probably is. The difference is a judgement about the outcome's worth, and
    the same status has to be able to produce either answer.
    """
    async def body():
        client, db = await _db()
        uid = f"v39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            worth = _goal(uid, status="completed")
            trivial = _goal(uid, objective="Un controllo interno da niente.",
                            desired_outcome="Nulla è cambiato.", status="completed")
            await service.repo.create_goal(worth)
            await service.repo.create_goal(trivial)
            await _worked(service, uid, worth)
            await _worked(service, uid, trivial, claim="Non è cambiato niente.")

            _install(monkeypatch, FakeModel([
                _says("inform_user", "Fatto: il certificato è pronto, non devi fare nulla.",
                      about="certificato pronto"),
            ]))
            said = await service.visibility.consider(uid, worth, what_happened=_facts())

            _install(monkeypatch, FakeModel([
                _says("silent", headline="", about="controllo senza esito"),
            ]))
            quiet = await service.visibility.consider(
                uid, trivial, what_happened=_facts(refs=("journal:2",))
            )

            assert said.outcome == "inform_user"
            assert quiet.outcome == "silent"
            assert said.wants_a_person is False, (
                "un risultato è diventato una richiesta"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_needing_a_person_shows_the_work_and_then_the_one_thing(monkeypatch):
    """
    §17/§24/QA D: the question arrives after everything ORA could do alone.

    What a person sees is what is already done plus the single thing that is
    missing — never a request to decide how to proceed.
    """
    async def body():
        client, db = await _db()
        uid = f"v39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            goal = _goal(uid, status="waiting", requires_user_authority=True)
            await service.repo.create_goal(goal)
            await _worked(service, uid, goal)

            _install(monkeypatch, FakeModel([
                _says("requires_attention",
                      "Ho trovato tutto: mi manca solo il tuo via libera.",
                      about="serve autorizzazione"),
            ]))
            decision = await service.visibility.consider(
                uid, goal,
                what_happened=_facts(is_there_something_for_them_to_do=True),
            )

            assert decision.outcome == "requires_attention"
            assert decision.wants_a_person is True
            assert decision.for_human()["needs_you"] is True
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_same_news_is_said_once(monkeypatch):
    """
    §19/§25/QA E: three reconsiderations, one sentence.

    Keyed on what the update is *about* rather than on its wording, because a
    model asked twice will phrase it twice and two phrasings of one fact are
    still one fact.
    """
    async def body():
        client, db = await _db()
        uid = f"v39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            goal = _goal(uid)
            await service.repo.create_goal(goal)
            await _worked(service, uid, goal)

            said = []
            for headline in (
                "Ho trovato gli orari: apre alle 8:30.",
                "Gli orari li ho: dalle 8:30.",
                "Ho verificato: lo sportello apre alle 8:30.",
            ):
                _install(monkeypatch, FakeModel([
                    _says("quiet_update", headline, about="orari dello sportello"),
                ]))
                decision = await service.visibility.consider(
                    uid, goal, what_happened=_facts()
                )
                if decision.is_visible:
                    await service.visibility.show(uid, goal, decision)
                said.append(decision.outcome)

            assert said[0] == "quiet_update"
            assert said[1:] == ["silent", "silent"], f"ha parlato tre volte: {said}"
            assert await db.ambient_activity.count_documents(
                {"owner_id": uid, "visibility": "ambient"}
            ) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_two_goals_in_the_same_state_can_get_different_answers(monkeypatch):
    """
    §26/QA F: status is not the input.

    Same status, different meaning, different answer — which is only possible
    because nothing maps one to the other.
    """
    async def body():
        client, db = await _db()
        uid = f"v39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            one = _goal(uid, status="waiting")
            two = _goal(uid, objective="Un'altra cosa.",
                        desired_outcome="Un altro esito.", status="waiting")
            await service.repo.create_goal(one)
            await service.repo.create_goal(two)
            await _worked(service, uid, one)
            await _worked(service, uid, two, claim="Non risulta niente di nuovo.")

            _install(monkeypatch, FakeModel([
                _says("inform_user", "Ho trovato quello che serviva.", about="uno"),
            ]))
            first = await service.visibility.consider(uid, one, what_happened=_facts())

            _install(monkeypatch, FakeModel([
                _says("silent", headline="", about="due"),
            ]))
            second = await service.visibility.consider(
                uid, two, what_happened=_facts(refs=("journal:9",))
            )

            assert one.status == two.status
            assert first.outcome != second.outcome, (
                "lo stesso stato ha prodotto lo stesso esito: c'è una mappatura"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# What code refuses to show
# ---------------------------------------------------------------------------

def test_an_update_with_nothing_behind_it_is_refused(monkeypatch):
    """
    §20: proof of work.

    A system that can say «me ne sto occupando» with nothing behind it will
    eventually say it with nothing behind it. The refs are checked in code,
    so no prompt can talk its way past this.
    """
    async def body():
        client, db = await _db()
        uid = f"v39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            goal = _goal(uid)
            await service.repo.create_goal(goal)

            _install(monkeypatch, FakeModel([
                _says("inform_user", "Sto lavorando alla cosa.", about="niente"),
            ]))
            decision = await service.visibility.consider(
                uid, goal, what_happened=_facts(refs=())
            )

            assert decision.outcome == "silent"
            assert decision.decided_by == "code"
            assert "prova" in decision.quietened_by_code
            assert await db.ambient_activity.count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_visible_decision_with_no_sentence_shows_nothing(monkeypatch):
    """An empty line on a screen is worse than no line."""
    async def body():
        client, db = await _db()
        uid = f"v39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            goal = _goal(uid)
            await service.repo.create_goal(goal)
            await _worked(service, uid, goal)

            _install(monkeypatch, FakeModel([
                _says("quiet_update", headline="   ", about="vuoto"),
            ]))
            decision = await service.visibility.consider(
                uid, goal, what_happened=_facts()
            )
            assert decision.outcome == "silent"
            assert decision.decided_by == "code"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_no_judgement_available_means_saying_nothing(monkeypatch):
    """
    An outage is not a decision that there was nothing to say — but it is
    still a reason to say nothing, and the next run tries again.
    """
    async def body():
        client, db = await _db()
        uid = f"v39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            goal = _goal(uid)
            await service.repo.create_goal(goal)
            await _worked(service, uid, goal)

            _install(monkeypatch, FakeModel([None]))
            decision = await service.visibility.consider(
                uid, goal, what_happened=_facts()
            )
            assert decision.outcome == "silent"
            assert decision.decided_by == "code"
            assert "disponibile" in decision.quietened_by_code
            assert await db.agent_updates.count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def _code_only(source: str) -> str:
    """Source with docstrings and comments removed, so guards cannot match prose."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            node.body = [
                n for n in node.body
                if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                        and isinstance(n.value.value, str))
            ]
    return ast.unparse(tree)


def test_no_branch_turns_a_goal_status_into_a_visibility():
    """
    §10: AI-first, enforced structurally.

    `if goal.status == "completed": inform_user` is one line, reads as
    helpful, and would end the judgement this whole gate is buying. Walked
    rather than grepped, because prose about not doing it is not the same as
    not doing it.
    """
    from agent.models import OutcomeVisibility
    import typing

    verdicts = set(typing.get_args(OutcomeVisibility))

    for module in ("visibility.py", "service.py"):
        tree = ast.parse(_code_only(
            HERE.joinpath("agent", module).read_text(encoding="utf-8")
        ))
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            test = ast.unparse(node.test)
            body = ast.unparse(node.body)
            looks_at_status = any(
                word in test for word in
                ("status", "is_open", "requires_user_input", "requires_user_authority")
            )
            if not looks_at_status:
                continue
            for verdict in verdicts - {"silent"}:
                assert f'"{verdict}"' not in body and f"'{verdict}'" not in body, (
                    f"{module}:{node.lineno} mappa uno stato su «{verdict}»"
                )


def test_visibility_cannot_reach_a_notification():
    """
    §9/§18: it says how much this is worth showing. Not when, not through what.

    The moment this file can schedule or push, it has become a second
    delivery system, and there will be two policies deciding whether to
    interrupt somebody.
    """
    code = _code_only(
        HERE.joinpath("agent", "visibility.py").read_text(encoding="utf-8")
    )
    for channel in (
        "push", "send", "notify", "notification", "DeliveryPlan", "evaluate(",
        "deliver_due", "schedule", "endpoint", "expo", "quiet_presence", "in_app",
    ):
        assert channel not in code, f"la visibilità raggiunge il canale: {channel}"

    # The only surface it touches is the ambient record V3.8 already owns.
    assert "note_activity" in code


def test_delivery_staying_quiet_does_not_delete_the_update():
    """
    §6/§18: «no push» and «they must not know» are different sentences.

    The one thing that would collapse them again is a branch that discards
    the update when delivery declines to interrupt. There is nowhere for one
    to live: visibility never asks delivery anything.
    """
    code = _code_only(
        HERE.joinpath("agent", "visibility.py").read_text(encoding="utf-8")
    )
    for coupling in ("DeliveryDecision", "delivery_mode", "silence", "muted"):
        assert coupling not in code, (
            f"la visibilità dipende dalla decisione di consegna: {coupling}"
        )


def test_nothing_technical_can_reach_a_person():
    """
    §14: the sentence, and nothing that betrays how it was reached.

    Enforced on the payload rather than on the wording, because a field that
    exists is a field a future card will render.
    """
    from agent.models import VisibilityDecision

    decision = VisibilityDecision(
        goal_id="gol_x", outcome="inform_user", headline="Fatto.",
        refs=["evd_1"], fingerprint="abc", reasoning="perché sì",
    )
    shown = decision.for_human()
    assert set(shown) == {"says", "needs_you"}
    for leak in ("goal_id", "refs", "fingerprint", "reasoning", "outcome",
                 "decided_by", "capability", "step"):
        assert leak not in shown


def test_the_prompt_names_both_failures():
    """
    §12/§13: a prompt that warns against narrating produces silence, and a
    prompt that warns against silence produces narration. Both are named.
    """
    import agent.reasoning as reasoning

    # Rendered, not read off the source: the prompt is built by joining
    # string fragments, and a phrase that spans two of them is present for
    # the model and absent from the file. Asserting on the file would pass
    # while the model saw something else.
    seen = {}

    async def capture(system, user):
        seen["system"] = system
        return None

    original = reasoning._ask_model
    reasoning._ask_model = capture
    try:
        _run(reasoning.decide_visibility({}, what_happened={}, already_said=[]))
    finally:
        reasoning._ask_model = original

    block = seen.get("system", "")
    assert block, "il prompt non è stato reso"

    for principle in (
        "Do not confuse avoiding interruption with hiding useful work",
        "Silence is correct only when showing the update would add no",
        "decide whether that should be made visible",
    ):
        assert principle in block, f"manca dal prompt: {principle[:50]}"

    for chatter in (
        "that you are working, without saying what you found",
        "when nothing had changed",
        "one line per step",
        "congratulations",
    ):
        assert chatter in block, f"il chatter non è vietato: {chatter[:40]}"

    for technical in ("steps, tools, capabilities, plans, providers",):
        assert technical in block


def test_visibility_is_asked_once_per_run_and_not_once_per_step():
    """
    §13: no heartbeat.

    Asked from the end of `advance`, never from inside the step loop — a
    judgement per step is exactly the narration this gate forbids, and it
    would cost a model call each time.
    """
    tree = ast.parse(_code_only(
        HERE.joinpath("agent", "service.py").read_text(encoding="utf-8")
    ))
    callers = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if "_consider_visibility" in ast.unparse(node) and node.name != "_consider_visibility":
            callers.append(node.name)

    assert callers == ["advance"], f"la visibilità è chiesta da: {callers}"

    # And the step loop cannot reach it.
    work = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_work"
    )
    assert "visibility" not in ast.unparse(work)
