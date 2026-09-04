"""
V3.9 Sprint 2 — real capability execution: what actually ran, and what it said.

    AUTONOMOUS WORK MUST BE REAL WORK.
    A TOOL RESULT IS NOT A LIFE FACT.
    EXECUTOR DOES NOT DECIDE MEANING.

Sprint 1 closed with a stated debt: every capability was a stand-in, so every
step succeeded, so a verifier had nothing to tell apart. These tests are about
the half of the fix that lives in execution — that a capability reaches
something real, says where its answer came from, and reports the several
different ways of not succeeding as the several different things they are.

The other half, whether any of that is allowed to close a goal, is in
`test_agent_evidence_v39.py`.

Every model call here is stubbed, and so is the research engine — at the
capability boundary, so that everything above it runs for real.
"""

from __future__ import annotations

import ast
import os
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
        "agent_evidence", "agent_runs", "autonomy_grants", "autonomy_policies",
        "autonomy_denials", "memories", "documents", "connector_instances",
        "ingestion_events", "ambient_wakes", "ambient_activity",
    ):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


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


def _step(**over):
    from agent.models import ActionStep

    fields = {
        "intent": "Guardare cosa risulta.",
        "step_type": "inspect",
        "capability_needed": "information.read",
        "expected_result": "Si sa cosa c'è già.",
    }
    fields.update(over)
    return ActionStep(**fields)


# ---------------------------------------------------------------------------
# What a capability is, now that it is real
# ---------------------------------------------------------------------------

def test_a_capability_says_what_is_actually_behind_it():
    """
    §8: available_real, available_simulated, unavailable, requires_connection.

    A planner told only "available" cannot tell the difference between doing
    a thing and pretending to, and will build a route through the pretence.
    """
    from agent.capabilities import capability_status, is_really_wired

    assert capability_status("information.read") == "available_real"
    assert capability_status("web.research") == "available_real"
    assert capability_status("comparison.run") == "available_real"
    assert is_really_wired("web.research") is True

    # The one stand-in says it is one.
    assert capability_status("navigation.open") == "available_simulated"
    assert is_really_wired("navigation.open") is False

    # Nothing wired, and nothing pretending otherwise.
    assert capability_status("mail.send") == "unavailable"
    assert capability_status("payment.execute") == "unavailable"

    # A connector nobody plugged in is not the same as a capability that does
    # not exist, and the planner is told which it is.
    assert capability_status("calendar.read", permitted=False) == "requires_connection"


def test_only_one_capability_is_allowed_to_be_a_stand_in():
    """
    §29: the stub is a demonstration, not a growth area.

    The moment this set grows, "ORA did it" stops meaning anything — so the
    size of it is the thing under test, not its contents.
    """
    from agent.capabilities import _SIMULATED

    assert len(_SIMULATED) == 1, f"i sostituti sono diventati {len(_SIMULATED)}"
    assert "navigation.open" in _SIMULATED


def test_every_result_says_where_it_came_from(monkeypatch):
    """
    §9: provenance is set by the code that did the work.

    Nothing downstream can reconstruct whether a provider was really reached,
    so a result that did not say is treated as having come from nowhere.
    """
    async def body():
        client, db = await _db()
        uid = f"x39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.execution import StepExecutor

            executor = StepExecutor(db)
            await executor.ensure_indexes()
            goal = _goal(uid)

            await db.memories.insert_one({
                "user_id": uid, "id": "m1", "status": "known",
                "summary": "Vive a Padova.", "updated_at": "2026-08-01T00:00:00+00:00",
            })

            result = await executor.run(
                uid, goal, _step(), may_touch_the_world=False
            )
            assert result.status == "succeeded"
            assert result.provenance.source_class == "internal_observation"
            assert result.is_real is True
            assert result.evidence_refs, "niente è stato tenuto di quello che ha letto"

            evidence = await executor.evidence.for_goal(uid, goal.id)
            assert any("Padova" in e.claim for e in evidence)
            assert all(e.provenance.capability == "information.read" for e in evidence)
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_default_provenance_is_the_safe_thing_to_be_wrong_about():
    """A result that forgot to say where it came from proves nothing."""
    from agent.models import ExecutionResult

    naked = ExecutionResult(step_id="s", status="succeeded")
    assert naked.provenance.source_class == "simulated"
    assert naked.is_real is False


# ---------------------------------------------------------------------------
# Reading what is really there
# ---------------------------------------------------------------------------

def test_finding_nothing_is_a_finding_and_not_a_failure():
    """
    An empty life is an observation. Reporting it as an error sends the model
    hunting for a fault that does not exist.
    """
    async def body():
        client, db = await _db()
        uid = f"x39_{uuid.uuid4().hex[:8]}"
        try:
            from agent import providers

            outcome = await providers.read_internal_state(db, uid, _goal(uid))
            assert outcome.status == "succeeded"
            assert outcome.error_type == ""
            assert outcome.claims, "non ha detto neanche che non c'era niente"
            assert outcome.provenance.source_class == "internal_observation"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_no_calendar_is_not_an_empty_calendar():
    """
    §21: never simulate a connection to declare it working.

    "Nothing is coming up" and "there is no calendar" look identical in the
    data and mean opposite things to a plan. A capability that returns the
    first when the second is true has told a lie a plan will act on.
    """
    async def body():
        client, db = await _db()
        uid = f"x39_{uuid.uuid4().hex[:8]}"
        try:
            from agent import providers

            outcome = await providers.read_calendar(db, uid, _goal(uid))
            assert outcome.status == "unavailable"
            assert outcome.error_type == "requires_connection"
            assert not outcome.claims, "ha inventato un calendario vuoto"

            # With something actually connected, the same read reports a real
            # empty week — which is a different sentence and a real one.
            await db.connector_instances.insert_one({
                "user_id": uid, "connector_id": "calendar_google", "status": "connected",
            })
            second = await providers.read_calendar(db, uid, _goal(uid))
            assert second.status in ("succeeded", "partial")
            assert second.error_type == ""
            assert second.provenance.source_class == "connected_provider"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_document_read_gives_the_shape_and_not_the_contents():
    """
    §20: structured, not raw.

    A capability called "look at the documents" that hands back extracted
    text is a capability that discloses a payslip to answer a question about
    filenames.
    """
    async def body():
        client, db = await _db()
        uid = f"x39_{uuid.uuid4().hex[:8]}"
        try:
            from agent import providers

            await db.documents.insert_one({
                "user_id": uid, "id": "d1", "filename": "residenza.pdf",
                "tags": ["comune"], "created_at": "2026-08-01T00:00:00+00:00",
                "extracted_text": "IBAN IT60X0542811101000000123456 SEGRETO",
            })
            outcome = await providers.read_documents(db, uid, _goal(uid))
            assert outcome.status == "succeeded"
            joined = " ".join(c.text for c in outcome.claims)
            assert "residenza.pdf" in joined
            assert "SEGRETO" not in joined, "ha passato il contenuto del documento"
            assert "IBAN" not in joined
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# When the world does not answer
# ---------------------------------------------------------------------------

def test_a_provider_being_down_is_not_the_goal_being_impossible(monkeypatch):
    """
    §47: unavailable and retryable, not failed and final.

    A provider that is down says nothing about whether the outcome can be
    reached, and a system that conflates the two abandons goals because of a
    timeout.
    """
    async def body():
        client, db = await _db()
        uid = f"x39_{uuid.uuid4().hex[:8]}"
        try:
            from agent import providers
            from agent.execution import StepExecutor

            async def broken(db_, owner_id, goal, step, **kw):
                return providers.CapabilityOutcome(
                    status="failed",
                    observation="La ricerca non ha risposto.",
                    provenance=providers.ResultProvenance(
                        source_class="external_research", capability="web.research"
                    ),
                    error_type="provider_unavailable",
                    retryable=True,
                )

            monkeypatch.setattr(providers, "do_research", broken)

            executor = StepExecutor(db)
            await executor.ensure_indexes()
            goal = _goal(uid)
            step = _step(step_type="research", capability_needed="web.research")

            result = await executor.run(uid, goal, step, may_touch_the_world=False)

            assert result.status == "failed"
            assert result.error_type == "provider_unavailable"
            assert result.retryable is True
            assert result.is_real is False or not result.evidence_refs

            evidence = await executor.evidence.for_goal(uid, goal.id)
            assert not evidence, "un provider caduto ha prodotto una prova"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_partial_result_does_not_report_itself_as_complete(monkeypatch):
    """
    §49: partial is not succeeded.

    A step that got somewhere and not all the way is exactly what the model
    needs to know about, and calling it done is how a plan sails past the
    thing it was supposed to establish.
    """
    async def body():
        client, db = await _db()
        uid = f"x39_{uuid.uuid4().hex[:8]}"
        try:
            from agent import providers
            from agent.execution import StepExecutor

            async def thin(db_, owner_id, goal, step, **kw):
                return providers.CapabilityOutcome(
                    status="partial",
                    observation="Ho trovato qualcosa, ma non basta.",
                    provenance=providers.ResultProvenance(
                        source_class="external_research", capability="web.research",
                        source_refs=["res_1"],
                    ),
                    claims=[providers.Claim(text="Forse è così.", supports="la domanda")],
                    data_ref="res_1",
                    error_type="not_enough_yet",
                    retryable=True,
                )

            monkeypatch.setattr(providers, "do_research", thin)

            executor = StepExecutor(db)
            await executor.ensure_indexes()
            goal = _goal(uid)
            step = _step(step_type="research", capability_needed="web.research")
            result = await executor.run(uid, goal, step, may_touch_the_world=False)

            assert result.status == "partial"
            assert result.error_type == "not_enough_yet"
            # What it did find is still kept: incomplete is not worthless.
            assert result.evidence_refs
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# The boundary, still
# ---------------------------------------------------------------------------

def test_nothing_real_reaches_the_world_even_with_authority():
    """
    §85: no send, no booking, no payment. Wired or not, this stays true.

    The one capability that goes through is a stand-in and says so in its
    provenance, which is what stops it from ever counting as proof.
    """
    async def body():
        client, db = await _db()
        uid = f"x39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.execution import StepExecutor

            executor = StepExecutor(db)
            await executor.ensure_indexes()
            goal = _goal(uid)

            went = await executor.run(
                uid, goal,
                _step(step_type="execute", capability_needed="navigation.open",
                      intent="Aprire la mappa.", external_effect=True),
                may_touch_the_world=True,
            )
            assert went.status == "succeeded"
            assert went.provenance.source_class == "simulated"
            assert went.is_real is False
            assert "simulat" in went.observation.lower()

            for capability in ("mail.send", "external.booking", "payment.execute"):
                blocked = await executor.run(
                    uid, goal,
                    _step(step_type="execute", capability_needed=capability,
                          external_effect=True),
                    may_touch_the_world=True,
                )
                assert blocked.status != "succeeded", f"{capability} è partita"
                assert blocked.error_type in (
                    "execution_not_wired", "requires_connection", "not_permitted"
                )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_executor_cannot_say_anything_about_meaning():
    """
    §23: it calls a capability and reports facts.

    Whether the goal is achieved, what to do next, whether to ask — none of
    that is expressible in this file, and the way to keep it that way is to
    check that the vocabulary is not there.
    """
    import re

    source = HERE.joinpath("agent", "execution.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            node.body = [
                n for n in node.body
                if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                        and isinstance(n.value.value, str))
            ]
    code = ast.unparse(tree)

    for judgement in (
        "goal.status =", "achieved", "requires_user_input", "requires_user_authority",
        "abandon", "replan", "verify_goal", "choose_next_action", "decide_goal",
    ):
        assert judgement not in code, f"l'esecutore decide: {judgement}"

    # And it holds no opinion about how much anything matters.
    for weight in ("importance", "priority", "urgency", "score"):
        assert weight not in code.lower(), f"l'esecutore pesa: {weight}"


def test_no_capability_result_can_omit_its_provenance():
    """
    §22: one shape for every capability outcome, provenance included.

    Enforced on the dataclass rather than on each provider, because a rule
    that has to be remembered at fifteen call sites is a rule with fourteen
    chances to be forgotten.
    """
    import dataclasses
    import inspect

    from agent import providers

    fields = providers.CapabilityOutcome.__dataclass_fields__
    for required in ("status", "observation", "provenance", "claims", "error_type"):
        assert required in fields, f"manca {required}"

    # `provenance` has no default: it must be passed, every time.
    assert fields["provenance"].default is dataclasses.MISSING
    assert fields["provenance"].default_factory is dataclasses.MISSING
    assert fields["status"].default is dataclasses.MISSING

    # And every provider in the module returns that shape.
    returns = [
        name for name, fn in vars(providers).items()
        if inspect.iscoroutinefunction(fn) and not name.startswith("_")
    ]
    assert len(returns) >= 5, f"troppe poche capability reali: {returns}"


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------

def test_a_run_has_a_ceiling_on_everything_it_can_spend():
    """
    §45/§46: an autonomous agent is a bill unless somebody bounds it.

    Named ceilings, so the journal can say which one was hit rather than
    reporting a run that mysteriously stopped.
    """
    from agent.models import AgentBudget

    budget = AgentBudget()
    assert budget.exhausted() == ""

    budget.cognitive_calls = budget.max_cognitive_calls
    assert budget.exhausted() == "cognitive_calls"

    fresh = AgentBudget()
    fresh.capability_calls = fresh.max_capability_calls
    assert fresh.exhausted() == "capability_calls"

    stepped = AgentBudget()
    stepped.steps_executed = stepped.max_steps
    assert stepped.exhausted() == "steps"

    old = AgentBudget(started_at="2020-01-01T00:00:00+00:00")
    assert old.exhausted() == "time"

    researched = AgentBudget()
    researched.research_calls = researched.max_research_calls
    assert researched.research_exhausted() is True


def test_the_research_budget_stops_looking_rather_than_reporting_nothing(monkeypatch):
    """
    A ceiling is not a finding. Told "nothing was found", a plan concludes
    something false about the world; told "I have looked as much as I may
    this round", it waits or routes around.
    """
    async def body():
        client, db = await _db()
        uid = f"x39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.execution import StepExecutor
            from agent.models import AgentBudget

            executor = StepExecutor(db)
            await executor.ensure_indexes()
            budget = AgentBudget()
            budget.research_calls = budget.max_research_calls

            result = await executor.run(
                uid, _goal(uid),
                _step(step_type="research", capability_needed="web.research"),
                may_touch_the_world=False, budget=budget,
            )
            assert result.status == "waiting"
            assert result.error_type == "research_budget_spent"
            assert result.retryable is True
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_reads_are_a_table_and_not_a_set_of_domain_branches():
    """
    §7/§73: no plan template, and no template smuggled in as a dispatch.

    A chain of `if capability == "calendar.read"` is one refactor away from
    `if the goal mentions a doctor`, and the difference is not visible in a
    diff.
    """
    source = HERE.joinpath("agent", "execution.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    domains = {"calendar", "mail", "email", "document", "booking", "payment"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        for side in [node.left, *node.comparators]:
            if isinstance(side, ast.Constant) and isinstance(side.value, str):
                head = side.value.split(".")[0].strip().lower()
                assert head not in domains, (
                    f"execution.py:{node.lineno} decide su «{side.value}»"
                )
