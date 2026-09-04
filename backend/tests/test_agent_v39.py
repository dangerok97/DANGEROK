"""
V3.9 Sprint 1 — the agentic core: goals, plans, replanning, verification.

    THE USER DOES NOT MANAGE THE AGENT. THE AGENT MANAGES THE WORK.
    AUTONOMY DOES NOT MEAN ACTIVITY.

Two failures shape almost every test here.

The first is busywork. Give a model a life and the ability to plan and it will
find something to plan; a system that rewards it for that fills somebody's
week with errands nobody asked for. So `no_goal` has to be comfortable, an
opportunity must not become a goal by any mechanical route, and a quiet life
must produce nothing at all.

The second is an assistant that asks permission to think. Reading,
researching, comparing and drafting cost a person nothing, and a plan that
stops to ask about them has turned help into a quiz. What ORA may stop for is
narrow and named: something only they know, or something only they may
authorise.

Every model call here is stubbed. The live QAs are run separately and reported
with an exact count.
"""

from __future__ import annotations

import ast
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
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
        "autonomy_grants", "autonomy_policies", "ambient_wakes", "ambient_activity",
        "opportunities", "opportunity_decisions", "delivery_plans", "calendar_events",
    ):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


class FakeModel:
    """The model, saying what a test needs it to say."""

    def __init__(self, answers, default=None):
        self.answers = list(answers)
        # V3.9 Sprint 2 - the loop now asks which of the remaining steps is
        # worth doing, once anything has been found out. Tests that are not
        # about that judgement say so here: `default` is what the model
        # answers when the queue runs dry, and «carry on» is the answer that
        # keeps a test about something else about that something else.
        # Tests that DO care leave it None, so an unexpected call returns
        # nothing and the loop stalls visibly instead of walking on.
        self.default = default
        self.seen = []

    async def __call__(self, system, user):
        self.seen.append({"system": system, "user": user})
        if self.answers:
            return self.answers.pop(0)
        return dict(self.default) if isinstance(self.default, dict) else self.default


def _stub_research(monkeypatch, *, claim="Si fa così.", status="succeeded"):
    """
    Stand in for the research engine, at the capability boundary.

    V3.9 Sprint 2 wires `web.research` to V3.4 for real, which is the point of
    the phase and also a live network call. Tests replace the capability and
    leave everything above it — the loop, the evidence, the provenance, the
    completion gate — running for real.
    """
    import agent.providers as providers

    async def fake(db, owner_id, goal, step, **kw):
        return providers.CapabilityOutcome(
            status=status,
            observation="Ho cercato e ho trovato.",
            provenance=providers.ResultProvenance(
                source_class="external_research",
                capability="web.research",
                provider="research",
                source_refs=["res_fake"],
                freshness="fresh",
            ),
            claims=[providers.Claim(text=claim, supports="la domanda posta")],
            data_ref="res_fake",
        )

    monkeypatch.setattr(providers, "do_research", fake)


def _install(monkeypatch, model):
    # Bound into the module at import: patching the shared helper's home
    # would leave this one pointing at the real provider.
    import agent.reasoning as reasoning

    monkeypatch.setattr(reasoning, "_ask_model", model)


def _goal(**over):
    answer = {
        "outcome": "create_goal",
        "reasoning": "C'è un risultato concreto da raggiungere.",
        "objective": "Fare in modo che il certificato sia in mano prima dell'appuntamento.",
        "desired_outcome": "Il certificato è disponibile la mattina dell'appuntamento.",
        "why_now": "L'ufficio che lo rilascia apre solo la mattina.",
        "success_criteria": ["Il certificato è in mano."],
        "stop_conditions": ["L'appuntamento viene annullato."],
    }
    answer.update(over)
    return answer


def _next_action(decision="execute", **over):
    """
    What the model says when asked which step is worth doing now.

    `execute` with no step id means «the next thing still to do», which is
    what a test that is about something else wants the loop to do.
    """
    answer = {
        "decision": decision,
        "reasoning": "Il passo successivo ha ancora senso.",
        "step_id": "",
    }
    answer.update(over)
    return answer


def _plan(steps=None, **over):
    answer = {
        "plan_summary": "Verificare cosa serve e prepararlo.",
        "expected_outcome": "Il certificato è disponibile.",
        "assumptions": ["L'ufficio è aperto la mattina."],
        "known_constraints": [],
        "steps": steps if steps is not None else [
            {
                "intent": "Guardare cosa risulta già agli atti.",
                "step_type": "inspect",
                "capability_needed": "information.read",
                "expected_result": "Si sa se il certificato c'è già.",
            },
            {
                "intent": "Verificare che il risultato regga.",
                "step_type": "verify",
                "capability_needed": "information.read",
                "expected_result": "Conferma.",
            },
        ],
    }
    answer.update(over)
    return answer


def _verify(outcome="achieved", **over):
    answer = {
        "outcome": outcome,
        "reasoning": "Il risultato è quello che serviva.",
        "what_is_missing": "",
    }
    answer.update(over)
    return answer


async def _service(db):
    from agent.service import AgentService

    service = AgentService(db)
    await service.ensure_indexes()
    return service


# ---------------------------------------------------------------------------
# Whether there is anything worth doing
# ---------------------------------------------------------------------------

def test_ora_can_decide_to_pursue_something_nobody_asked_for(monkeypatch):
    """
    §53: initiative, which is the whole point of the phase.

    No command, no request. A situation, and a decision that there is an
    outcome worth reaching — with the outcome written as a state of affairs
    rather than a chore.
    """
    async def body():
        client, db = await _db()
        uid = f"a39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            _install(monkeypatch, FakeModel([_goal()]))

            result = await service.consider(
                uid,
                situation={"what": "Manca il certificato per giovedì."},
                origin="agent_initiated",
            )

            assert result["outcome"] == "create_goal"
            goal = await service.repo.get_goal(uid, result["goal_id"])
            assert goal.origin == "agent_initiated"
            assert goal.status == "active"
            assert goal.success_criteria, "un obiettivo senza modo di dire se è riuscito"
            assert goal.stop_conditions, "un obiettivo che non sa quando arrendersi"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_no_goal_is_an_ordinary_answer(monkeypatch):
    """
    §54/§66: AUTONOMY DOES NOT MEAN ACTIVITY.

    Something can be true, and worth knowing, and still not be worth doing
    anything about. Nothing is written, and nothing claims work happened.
    """
    async def body():
        client, db = await _db()
        uid = f"a39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            _install(monkeypatch, FakeModel([{
                "outcome": "no_goal",
                "reasoning": "È solo un'informazione: non c'è niente da fare.",
            }]))

            result = await service.consider(
                uid, situation={"what": "Domani piove."}, origin="agent_initiated"
            )

            assert result["outcome"] == "no_goal"
            assert await db.agent_goals.count_documents({"owner_id": uid}) == 0
            assert await db.agent_plans.count_documents({"owner_id": uid}) == 0
            assert await db.ambient_activity.count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_outage_is_not_a_decision_that_there_was_nothing(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"a39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            _install(monkeypatch, FakeModel([]))  # unreachable

            result = await service.consider(uid, situation={"what": "x"})
            assert result["outcome"] == "unavailable"
            assert await db.agent_goals.count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_same_concern_is_not_pursued_twice(monkeypatch):
    """§32: two goals chasing one concern is the same work done twice."""
    async def body():
        client, db = await _db()
        uid = f"a39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            ids = set()
            for _ in range(3):
                _install(monkeypatch, FakeModel([_goal()]))
                result = await service.consider(
                    uid, situation={"what": "x"}, opportunity_id="opp_same"
                )
                ids.add(result.get("goal_id") or "already")

            assert await db.agent_goals.count_documents(
                {"owner_id": uid, "status": {"$in": ["proposed", "active", "waiting"]}}
            ) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_request_and_a_noticing_take_the_same_path(monkeypatch):
    """
    §64: one engine, two doors.

    The day there are two paths, one of them stops being maintained — and it
    will be the autonomous one, because nobody is watching it.
    """
    async def body():
        client, db = await _db()
        asked = f"a39_{uuid.uuid4().hex[:8]}"
        noticed = f"a39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            situation = {"what": "Manca il certificato per giovedì."}
            goals = {}

            for uid, origin in ((asked, "user_requested"), (noticed, "agent_initiated")):
                _install(monkeypatch, FakeModel([_goal()]))
                result = await service.consider(uid, situation=situation, origin=origin)
                goals[origin] = await service.repo.get_goal(uid, result["goal_id"])

            a, b = goals["user_requested"], goals["agent_initiated"]
            assert a.origin != b.origin, "l'origine non è registrata"
            # Everything else about them is the same shape.
            assert a.objective == b.objective
            assert a.status == b.status
            assert a.success_criteria == b.success_criteria
        finally:
            for uid in (asked, noticed):
                await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

def test_the_plan_is_the_models_and_nothing_is_asked_about_thinking(monkeypatch):
    """
    §55: ORA does the work rather than proposing it.

    A plan of reading and comparing runs start to finish with nobody
    consulted, because none of it costs the person anything.
    """
    async def body():
        client, db = await _db()
        uid = f"a39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            _install(monkeypatch, FakeModel([_goal()]))
            created = await service.consider(uid, situation={"what": "x"})

            _install(monkeypatch, FakeModel([_plan(), _next_action(), _verify()]))
            result = await service.advance(uid, created["goal_id"])

            assert result["state"] == "completed"
            plan = await service.repo.plan_for(uid, created["goal_id"])
            assert plan.plan_summary
            assert all(s.status == "succeeded" for s in plan.steps)
            # Nobody was asked anything.
            goal = await service.repo.get_goal(uid, created["goal_id"])
            assert goal.requires_user_input is False
            assert goal.requires_user_authority is False
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_step_says_what_it_needs_and_never_what_to_call():
    """
    §13: the model names a capability; code finds the tool.

    A model reasoning about function signatures produces plans that break
    when the plumbing changes, and invents tools that do not exist.
    """
    from agent.models import ActionStep

    fields = set(ActionStep.model_fields)
    assert "capability_needed" in fields
    for plumbing in ("tool", "function", "endpoint", "client", "api_call", "arguments"):
        assert plumbing not in fields, f"lo step conosce {plumbing}"

    prompt = _rendered("make_plan")
    assert "never which service to call" in prompt
    assert "capability_needed" in prompt


def test_an_unknown_capability_is_reported_rather_than_pretended(monkeypatch):
    """§15: do not fake a tool. Say it is not there so the plan can change."""
    async def body():
        client, db = await _db()
        uid = f"a39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.capabilities import CapabilityResolver

            resolution = await CapabilityResolver(db).resolve(uid, "teleport.execute")
            assert resolution.known is False
            assert resolution.usable is False
            assert resolution.reason == "capability_unknown"

            # And an unknown capability is treated as world-changing: failing
            # closed on something nobody described is the only safe direction.
            from agent.capabilities import is_world_changing

            assert is_world_changing("teleport.execute") is True
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Asking, and not asking
# ---------------------------------------------------------------------------

def test_ora_asks_one_specific_thing_and_not_how_to_proceed(monkeypatch):
    """
    §56: the minimal question.

    "Come vuoi procedere?" is the agent handing the workflow back. What is
    allowed is the one fact only this person has.
    """
    async def body():
        client, db = await _db()
        uid = f"a39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            _install(monkeypatch, FakeModel([_goal()]))
            created = await service.consider(uid, situation={"what": "x"})

            _install(monkeypatch, FakeModel([_plan(steps=[
                {
                    "intent": "Guardare cosa risulta agli atti.",
                    "step_type": "inspect",
                    "capability_needed": "information.read",
                },
                {
                    "intent": "Sapere quale dei due indirizzi è quello giusto.",
                    "step_type": "ask_user",
                    "asks": "Quale dei due indirizzi è quello corretto?",
                    "ask_kind": "knowledge",
                },
            ])], default=_next_action()))
            result = await service.advance(uid, created["goal_id"])

            assert result["state"] == "waiting_for_person"
            assert result["kind"] == "knowledge"
            assert result["asks"] == "Quale dei due indirizzi è quello corretto?"

            goal = await service.repo.get_goal(uid, created["goal_id"])
            assert goal.requires_user_input is True
            assert goal.requires_user_authority is False, (
                "sapere una cosa e poterla fare sono state confuse"
            )

            # The reading happened first: the question comes after the work.
            plan = await service.repo.plan_for(uid, created["goal_id"])
            assert plan.steps[0].status == "succeeded"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_knowledge_and_authority_are_never_the_same_thing():
    """
    §21: "only you know this" and "only you may allow this" are different.

    Confusing them produces an assistant that asks permission to think.
    """
    from agent.models import ActionStep, AutonomousGoal

    goal_fields = set(AutonomousGoal.model_fields)
    assert "requires_user_input" in goal_fields
    assert "requires_user_authority" in goal_fields

    import typing

    # The field is Optional, so the literals sit one level in.
    kinds: set = set()
    for arg in typing.get_args(ActionStep.model_fields["ask_kind"].annotation):
        kinds.update(k for k in typing.get_args(arg) if isinstance(k, str))
    assert kinds == {"knowledge", "authority"}, f"vocabolario inatteso: {kinds}"

    prompt = _rendered("decide_goal")
    assert "something only they know, or something only they may authorise" in prompt


def test_answering_carries_on_from_where_it_stopped(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"a39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            _install(monkeypatch, FakeModel([_goal()]))
            created = await service.consider(uid, situation={"what": "x"})

            _install(monkeypatch, FakeModel([_plan(steps=[
                {"intent": "Chiedere.", "step_type": "ask_user",
                 "asks": "Quale indirizzo?", "ask_kind": "knowledge"},
                {"intent": "Verificare.", "step_type": "verify",
                 "capability_needed": "information.read"},
            ])]))
            await service.advance(uid, created["goal_id"])

            _install(monkeypatch, FakeModel([_next_action(), _verify()]))
            result = await service.answer(uid, created["goal_id"], reply="Quello di via Roma.")

            assert result["state"] == "completed"
            goal = await service.repo.get_goal(uid, created["goal_id"])
            assert goal.requires_user_input is False
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Replanning and verification
# ---------------------------------------------------------------------------

def test_a_failed_step_changes_the_route_rather_than_starting_over(monkeypatch):
    """
    §60: the smallest change that accounts for what happened.

    Rewriting a plan from scratch throws away everything already learned and
    costs a full generation each time.
    """
    async def body():
        client, db = await _db()
        uid = f"a39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            _stub_research(monkeypatch)
            _install(monkeypatch, FakeModel([_goal()]))
            created = await service.consider(uid, situation={"what": "x"})

            _install(monkeypatch, FakeModel([
                _plan(steps=[
                    {"intent": "Provare una strada che non esiste.",
                     "step_type": "research", "capability_needed": "teleport.execute"},
                ]),
                {
                    "decision": "modify",
                    "reasoning": "Quella strada non c'è: se ne prende un'altra.",
                    "revised_steps": [
                        {"intent": "Cercare in un altro modo.", "step_type": "research",
                         "capability_needed": "web.research"},
                    ],
                },
                _verify(),
            ]))
            result = await service.advance(uid, created["goal_id"])

            plan = await service.repo.plan_for(uid, created["goal_id"])
            assert plan.revisions == 1
            # The failed step is still there: history is not rewritten.
            assert len(plan.steps) == 2
            assert plan.steps[0].status == "failed"
            assert plan.steps[1].capability_needed == "web.research"
            assert result["state"] == "completed"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_steps_finishing_is_not_the_goal_being_achieved(monkeypatch):
    """
    §61: the failure this whole verification step exists to prevent.

    An email accepted by a server has not been read. A form submitted is not
    a booking. A plan whose steps all succeeded is not a solved problem.
    """
    async def body():
        client, db = await _db()
        uid = f"a39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            _install(monkeypatch, FakeModel([_goal()]))
            created = await service.consider(uid, situation={"what": "x"})

            _install(monkeypatch, FakeModel([
                _plan(),
                _next_action(),
                _verify(
                    "not_achieved",
                    reasoning="I passi sono andati, ma il certificato non c'è.",
                ),
            ]))
            result = await service.advance(uid, created["goal_id"])

            assert result["state"] == "failed", "il goal si è chiuso da solo"
            goal = await service.repo.get_goal(uid, created["goal_id"])
            assert goal.status == "failed"
            assert "non c'è" in goal.rationale
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_waiting_borrows_the_ambient_runtime_instead_of_polling(monkeypatch):
    """§62: something has to be somewhere at a time. That already exists."""
    async def body():
        client, db = await _db()
        uid = f"a39_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.repository import AmbientRepository

            await AmbientRepository(db).ensure_indexes()
            service = await _service(db)
            _install(monkeypatch, FakeModel([_goal()]))
            created = await service.consider(uid, situation={"what": "x"})

            _install(monkeypatch, FakeModel([
                _plan(),
                _next_action(),
                _verify("waiting_for_external_result", revisit_in_hours=8,
                        reasoning="Dipende da una risposta che non è arrivata."),
            ]))
            result = await service.advance(uid, created["goal_id"])

            assert result["state"] == "waiting"
            goal = await service.repo.get_goal(uid, created["goal_id"])
            assert goal.status == "waiting"

            wakes = await AmbientRepository(db).open_wakes(uid)
            assert len(wakes) == 1, "nessuna sveglia: resterebbe fermo per sempre"
            assert wakes[0].reason == "opportunity_revisit"
            assert f"goal:{goal.id}" in wakes[0].source_ref
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# What a person can do about it
# ---------------------------------------------------------------------------

def test_stop_ends_future_work_and_the_alarms_with_it(monkeypatch):
    """§63: «lascia perdere» has to actually stop things."""
    async def body():
        client, db = await _db()
        uid = f"a39_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.repository import AmbientRepository

            await AmbientRepository(db).ensure_indexes()
            service = await _service(db)
            _install(monkeypatch, FakeModel([_goal()]))
            created = await service.consider(uid, situation={"what": "x"})

            _install(monkeypatch, FakeModel([
                _plan(),
                _next_action(),
                _verify("waiting_for_external_result", revisit_in_hours=8),
            ]))
            await service.advance(uid, created["goal_id"])
            assert len(await AmbientRepository(db).open_wakes(uid)) == 1

            result = await service.cancel(uid, created["goal_id"], reason="lascia perdere")
            assert result["state"] == "cancelled"

            goal = await service.repo.get_goal(uid, created["goal_id"])
            assert goal.status == "cancelled"
            assert goal.decision_provenance == "user"
            # `plan_for` deliberately skips cancelled plans, so the state is
            # read straight from storage.
            stored = await db.agent_plans.find_one(
                {"goal_id": created["goal_id"]}, {"_id": 0, "status": 1}
            )
            assert stored["status"] == "cancelled"
            assert await AmbientRepository(db).open_wakes(uid) == [], (
                "una sveglia per un obiettivo abbandonato"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_person_sees_an_outcome_and_never_a_workflow(monkeypatch):
    """
    §34/§67: NEVER EXPOSE IMPLEMENTATION STATE WHEN A HUMAN STATE EXISTS.

    Checked on the payload rather than in a component: a screen can only
    render what it was given, so if step counts never leave the backend, no
    future card can accidentally show them.
    """
    async def body():
        client, db = await _db()
        uid = f"a39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            _install(monkeypatch, FakeModel([_goal()]))
            created = await service.consider(uid, situation={"what": "x"})

            _install(monkeypatch, FakeModel([_plan(steps=[
                {"intent": f"Passo {n}", "step_type": "inspect",
                 "capability_needed": "information.read"} for n in range(5)
            ] + [
                {"intent": "Chiedere.", "step_type": "ask_user",
                 "asks": "Quale indirizzo?", "ask_kind": "knowledge"},
            ])], default=_next_action()))
            await service.advance(uid, created["goal_id"])

            import json

            shown = json.dumps(await service.for_home(uid), ensure_ascii=False)
            for leak in (
                "step", "plan", "capability", "ordinal", "status", "authority",
                "information.read", "inspect", "ask_user",
            ):
                assert leak not in shown, f"la superficie mostra {leak}"

            visible = await service.for_home(uid)
            assert visible[0]["state"] == "Mi manca una cosa che sai solo tu."
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_human_state_of_waiting_says_which_kind_of_waiting():
    """Waiting on the world and waiting on you are different things to read."""
    from agent.models import AutonomousGoal
    from agent.service import _human_state

    def goal(**over):
        fields = {
            "owner_id": "u", "objective": "o", "desired_outcome": "d",
            "status": "waiting",
        }
        fields.update(over)
        return AutonomousGoal(**fields)

    assert _human_state(goal(requires_user_authority=True)) == (
        "È tutto pronto, mi serve solo il tuo via libera."
    )
    assert _human_state(goal(requires_user_input=True)) == (
        "Mi manca una cosa che sai solo tu."
    )
    assert _human_state(goal()) == "Sto aspettando una risposta."
    assert _human_state(goal(status="completed")) == "Fatto."
    assert _human_state(goal(status="active")) == "Me ne sto occupando."


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------

def test_a_run_cannot_think_for_ever(monkeypatch):
    """
    §45: an agent loop without a ceiling is a bill without a ceiling.

    A model that keeps saying "carry on" must run out of turns, not budget.
    """
    async def body():
        client, db = await _db()
        uid = f"a39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.service import MAX_ITERATIONS, MAX_MODEL_CALLS

            assert MAX_ITERATIONS <= 10
            assert MAX_MODEL_CALLS <= 12

            service = await _service(db)
            _install(monkeypatch, FakeModel([_goal()]))
            created = await service.consider(uid, situation={"what": "x"})

            # A step that always fails, and a model that always says carry on.
            failing = {"intent": "Provare l'impossibile.", "step_type": "research",
                       "capability_needed": "teleport.execute"}
            model = FakeModel(
                [_plan(steps=[failing])]
                + [{"decision": "continue", "reasoning": "riprova"}] * 20
            )
            _install(monkeypatch, model)
            result = await service.advance(uid, created["goal_id"])

            assert result["ok"] is True
            assert len(model.seen) <= MAX_MODEL_CALLS + 1, (
                f"{len(model.seen)} chiamate: il giro non si ferma"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_step_is_not_retried_for_ever(monkeypatch):
    from agent.execution import MAX_STEP_ATTEMPTS

    assert 1 <= MAX_STEP_ATTEMPTS <= 5


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def _source(*parts) -> str:
    return HERE.joinpath(*parts).read_text(encoding="utf-8")


def _code_only(text: str) -> str:
    """Strip docstrings and comments: a guard must read code, not prose."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if ast.get_docstring(node, clean=False):
                node.body = node.body[1:]
    stripped = ast.unparse(tree)
    return "\n".join(
        "" if line.strip().startswith("#") else line.split("#")[0]
        for line in stripped.splitlines()
    )


def _rendered(which: str) -> str:
    """A prompt as the model receives it, not as it is written in source."""
    import agent.reasoning as reasoning

    captured = {}

    async def capture(system, user):
        captured["system"] = system
        return None

    original = reasoning._ask_model  # noqa: SLF001
    reasoning._ask_model = capture  # noqa: SLF001
    try:
        if which == "decide_goal":
            _run(reasoning.decide_goal({}))
        elif which == "make_plan":
            _run(reasoning.make_plan({}, capabilities=[], context={}))
        elif which == "assess_authority":
            _run(reasoning.assess_authority({}, goal={}, facts={}))
        elif which == "reconsider":
            _run(reasoning.reconsider({}, plan={}, what_happened={}, capabilities=[]))
        else:
            _run(reasoning.verify_goal({}, evidence={}))
    finally:
        reasoning._ask_model = original  # noqa: SLF001
    return captured.get("system", "")


def test_no_rule_anywhere_turns_an_opportunity_into_a_goal():
    """
    §3/§73: OPPORTUNITY != GOAL.

    `if opportunity.active: create_goal()` is one line, reads as helpful, and
    would end the judgement. The bridge may only ever ask.
    """
    scheduler = _code_only(_source("life_orchestration", "scheduler.py"))
    bridge = scheduler.split("_consider_goals")[-1]

    assert "consider(" in bridge, "il ponte non chiede"
    for shortcut in ("create_goal", "AutonomousGoal(", "save_goal", "create_goal("):
        assert shortcut not in bridge, f"il ponte crea un goal: {shortcut}"

    # And nothing outside the agent package writes a goal at all.
    for path in HERE.rglob("*.py"):
        if "agent" in path.parts or "tests" in path.parts or "scripts" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert "AgentRepository(" not in text, f"{path.name} scrive goal"


def test_no_plan_template_lives_in_code():
    """
    §11/§73: no `calendar goal -> these steps`.

    A template is a plan the model did not make, and it will be wrong for
    every case that is not the one somebody had in mind when writing it.
    """
    domains = {
        "calendar", "email", "mail", "booking", "flight", "invoice",
        "payment", "document", "insurance",
    }
    for module in ("service.py", "execution.py", "capabilities.py"):
        tree = ast.parse(_source("agent", module))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            if not any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
                continue
            for side in [node.left, *node.comparators]:
                if isinstance(side, ast.Constant) and isinstance(side.value, str):
                    head = side.value.split(".")[0].strip().lower()
                    assert head not in domains, (
                        f"{module}:{node.lineno} decide in base a «{side.value}»"
                    )


def test_the_reasoner_never_learns_about_tools():
    """§13: the model reasons about capabilities, not clients."""
    reasoning = _code_only(_source("agent", "reasoning.py"))
    for plumbing in (
        "httpx", "requests", "GoogleCalendar", "gmail", "client.", "endpoint",
        "api_key", "oauth",
    ):
        assert plumbing not in reasoning, f"il ragionatore conosce {plumbing}"


def test_the_agent_creates_no_visible_work_and_executes_nothing_outside_itself():
    """§33/§76: an internal goal is not a task on somebody's list."""
    for module in (
        "service.py", "execution.py", "repository.py", "authority.py",
        "evidence.py", "providers.py", "visibility.py", "needs.py", "effects.py",
    ):
        code = _code_only(_source("agent", module))
        for banned in (
            "attention_items", "work_items", "home_snapshots", "send_email",
            "action_engine", "execute_action",
        ):
            assert banned not in code, f"{module} fa {banned}"

        for write in ("insert_one", "update_one", "update_many", "delete_many"):
            for target in re.findall(rf"db\[?['\"]?(\w+)['\"]?\]?\.{write}", code):
                assert target in (
                    "agent_goals", "agent_plans", "agent_journal",
                    "agent_action_attempts", "autonomy_grants", "autonomy_policies",
                    "agent_runs", "autonomy_denials", "agent_evidence",
                    "agent_updates", "agent_needs", "agent_receipts",
                    "GOALS", "PLANS", "JOURNAL", "ATTEMPTS", "GRANTS", "POLICIES",
                    "RUNS", "DENIALS", "EVIDENCE", "UPDATES", "NEEDS", "RECEIPTS",
                    "CONSENTS",
                ), f"{module} scrive su {target}"

    # V3.9 Sprint 2 — the agent may propose a life fact and may not write one.
    # `memories` is the life model's own collection, and the only way in is
    # the governance that already owns durable learning.
    for module in ("service.py", "execution.py", "providers.py", "evidence.py",
                   "visibility.py"):
        code = _code_only(_source("agent", module))
        for write in ("insert_one", "update_one", "update_many", "delete_many"):
            assert f"memories.{write}" not in code, (
                f"{module} scrive direttamente nel modello di vita"
            )


def test_the_prompt_forbids_busywork_and_permission_to_think():
    """§8/§20: the two failures the discipline block exists to name."""
    prompt = _rendered("decide_goal")

    assert "Nobody is paying you to be busy" in prompt
    assert "saying so is the correct answer" in prompt
    assert "Do not ask permission to think" in prompt
    assert "no sponsors, no products to prefer" in prompt
    # A goal is an outcome.
    assert "An objective is an OUTCOME, not a task" in prompt
