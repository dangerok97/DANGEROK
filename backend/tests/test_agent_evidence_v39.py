"""
V3.9 Sprint 2 — evidence, and what may be concluded from it.

    EVIDENCE PRECEDES BELIEF.
    SIMULATED IS NOT OBSERVED.
    EXECUTION SUCCESS IS NOT OUTCOME SUCCESS.
    NO COMPLETION THEATRE.

This suite is the debt Sprint 1 closed with, paid.

The failure it exists against is specific and quiet: a stand-in returns
success, the verifier sees a plan where every step finished, and a goal is
closed on the strength of nothing having happened. No prompt fixes that,
because a prompt is the thing being fooled. So the question "may this be
called done" is asked of code, on a source class the executing code wrote
down, and the answer is never shown to a model.

The rest is the loop around it: verification is given what was found rather
than which steps finished, what was found survives being written to a
database, and a verified outcome may propose something to the life model —
propose, through governance that can refuse, and never write.
"""

from __future__ import annotations

import os
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
        "agent_evidence", "agent_runs", "autonomy_grants", "autonomy_policies",
        "autonomy_denials", "memories", "ambient_wakes", "ambient_activity",
        "research_runs",
    ):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


class FakeModel:
    """The model, saying what a test needs it to say."""

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


def _next_action(decision="execute", **over):
    answer = {"decision": decision, "reasoning": "Ha ancora senso.", "step_id": ""}
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


def _evidence(uid, goal_id, source_class, claim="Risulta così."):
    from agent.models import AgentEvidence, ResultProvenance

    return AgentEvidence(
        owner_id=uid,
        goal_id=goal_id,
        claim=claim,
        provenance=ResultProvenance(source_class=source_class, capability="x"),
    )


def _plan_answer(steps, **over):
    answer = {
        "plan_summary": "Guardare e poi fare.",
        "expected_outcome": "Fatto.",
        "steps": steps,
    }
    answer.update(over)
    return answer


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def test_simulated_evidence_says_nothing_about_the_world():
    """
    §10: the distinction the whole sprint rests on.

    Not a lower confidence — a different kind of thing. `real_support` is
    deterministic and never reaches a model, so nothing can talk it round.
    """
    from agent.evidence import real_support, simulated_only

    uid, gid = "u", "g"
    only_pretend = [_evidence(uid, gid, "simulated")]
    assert real_support(only_pretend) is False
    assert simulated_only(only_pretend) is True

    for real in (
        "internal_observation", "connected_provider",
        "external_research", "deterministic_computation",
    ):
        assert real_support([_evidence(uid, gid, real)]) is True, real

    # Somebody saying they will do a thing is not the thing being done.
    assert real_support([_evidence(uid, gid, "user_statement")]) is False

    # Mixed: one real thing is enough to be talking about the world at all.
    assert real_support(only_pretend + [_evidence(uid, gid, "external_research")]) is True


def test_a_goal_cannot_be_completed_on_a_stand_in(monkeypatch):
    """
    §65: the QA that pays the Sprint 1 debt, as a deterministic test.

    The model is made to say `achieved` — emphatically, with every step
    succeeded — and the goal still does not close, because nothing that
    happened touched the world.
    """
    async def body():
        client, db = await _db()
        uid = f"e39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            goal = _goal(uid)
            await service.repo.create_goal(goal)

            # Everything this goal did was a stand-in.
            await service.evidence.record(_evidence(uid, goal.id, "simulated"))

            from agent.models import ActionPlan, ActionStep

            plan = ActionPlan(
                goal_id=goal.id, owner_id=uid, status="active",
                steps=[ActionStep(intent="Fatto.", step_type="prepare",
                                  status="succeeded")],
            )
            await service.repo.save_plan(plan)

            _install(monkeypatch, FakeModel([
                {"outcome": "achieved", "reasoning": "Tutti i passi sono andati."},
            ]))
            result = await service.advance(uid, goal.id)

            assert result["state"] != "completed", "chiuso su una simulazione"
            after = await service.repo.get_goal(uid, goal.id)
            assert after.status != "completed"
            assert after.completed_at is None

            journal = await service.repo.history(uid, goal.id)
            refused = [j for j in journal if j["kind"] == "completion_refused"]
            assert refused, "il rifiuto non è stato registrato"
            assert "reale" in refused[0]["note"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_real_read_around_a_simulated_act_still_does_not_close_the_goal(monkeypatch):
    """
    §15: the subtler half of no completion theatre.

    Plenty of genuine reading happened; the thing that was supposed to change
    the world was a stand-in. Reading is not doing, and an outcome that
    depended on an act is not true because the act was convincingly imitated.
    """
    async def body():
        client, db = await _db()
        uid = f"e39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            goal = _goal(uid)
            await service.repo.create_goal(goal)
            await service.evidence.record(
                _evidence(uid, goal.id, "internal_observation", "Ho letto sul serio.")
            )

            from agent.models import ActionPlan, ActionStep

            plan = ActionPlan(
                goal_id=goal.id, owner_id=uid, status="active",
                steps=[ActionStep(intent="Fatto.", step_type="prepare",
                                  status="succeeded")],
            )
            await service.repo.save_plan(plan)

            # An effect that went through, and was a stand-in.
            await db.agent_action_attempts.insert_one({
                "id": "int_1", "owner_id": uid, "goal_id": goal.id, "step_id": "s",
                "capability": "navigation.open", "status": "executed",
                "idempotency_key": f"k_{uuid.uuid4().hex[:8]}",
            })

            _install(monkeypatch, FakeModel([
                {"outcome": "achieved", "reasoning": "Sembra tutto a posto."},
            ]))
            result = await service.advance(uid, goal.id)

            assert result["state"] != "completed"
            journal = await service.repo.history(uid, goal.id)
            refused = [j for j in journal if j["kind"] == "completion_refused"]
            assert refused
            assert "simulata" in refused[0]["note"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_real_outcome_with_real_evidence_does_close(monkeypatch):
    """
    §66: the gate refuses what it should and nothing else.

    A guard that never lets anything through is not a guard, it is a wall,
    and this is the test that stops the previous two from being satisfied by
    breaking completion altogether.
    """
    async def body():
        client, db = await _db()
        uid = f"e39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            goal = _goal(uid)
            await service.repo.create_goal(goal)
            await service.evidence.record(_evidence(
                uid, goal.id, "external_research",
                "Il certificato si richiede allo sportello, senza appuntamento.",
            ))

            from agent.models import ActionPlan, ActionStep

            plan = ActionPlan(
                goal_id=goal.id, owner_id=uid, status="active",
                steps=[ActionStep(intent="Cercare.", step_type="research",
                                  status="succeeded")],
            )
            await service.repo.save_plan(plan)

            _install(monkeypatch, FakeModel([
                {"outcome": "achieved", "reasoning": "Le fonti lo dicono chiaramente."},
            ]))
            result = await service.advance(uid, goal.id)

            assert result["state"] == "completed"
            after = await service.repo.get_goal(uid, goal.id)
            assert after.status == "completed"
            assert after.completed_at
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_gate_is_code_and_never_asks_anybody():
    """
    §14: `_why_not_complete` reads a source class and returns a string.

    If this ever grew a model call it would stop being a guarantee and start
    being an opinion, so the shape of the function is the thing under test.
    """
    import ast

    source = HERE.joinpath("agent", "service.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    gate = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_why_not_complete"
    )
    assert not isinstance(gate, ast.AsyncFunctionDef), "il cancello può aspettare qualcuno"
    body = ast.unparse(gate)
    for reach in ("_ask_model", "await", "reasoning", "verify_goal", "db"):
        assert reach not in body, f"il cancello raggiunge {reach}"


# ---------------------------------------------------------------------------
# What verification is given
# ---------------------------------------------------------------------------

def test_verification_is_shown_what_was_found_and_not_which_steps_finished(monkeypatch):
    """
    §13: evidence, with provenance, and the simulated part marked.

    Not filtered — hiding it would leave the model wondering why a step it
    can see finished has nothing behind it. Marked, so leaning on it is a
    visible choice rather than a silent mistake.
    """
    async def body():
        client, db = await _db()
        uid = f"e39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            goal = _goal(uid)
            await service.repo.create_goal(goal)
            await service.evidence.record(_evidence(
                uid, goal.id, "external_research", "Lo sportello apre alle 8:30."
            ))
            await service.evidence.record(_evidence(
                uid, goal.id, "simulated", "Ho finto di aprire la mappa."
            ))

            from agent.models import ActionPlan, ActionStep

            plan = ActionPlan(
                goal_id=goal.id, owner_id=uid, status="active",
                steps=[ActionStep(intent="x", step_type="research", status="succeeded")],
            )
            await service.repo.save_plan(plan)

            model = FakeModel([{"outcome": "uncertain", "reasoning": "Non basta."}])
            _install(monkeypatch, model)
            await service.advance(uid, goal.id)

            # The verification call, found by what it asks rather than by
            # being last: the run also asks whether any of this is worth
            # showing, and that question comes after.
            asked = [
                c for c in model.seen
                if "whether the outcome is actually" in c["system"]
            ]
            assert asked, "la verifica non e stata chiesta"
            shown = asked[-1]["user"]
            assert "Lo sportello apre alle 8:30" in shown
            assert "Ho finto di aprire la mappa" in shown
            assert "simulazione" in shown, "la simulazione non è marcata"
            assert "really_happened" in shown

            system = asked[-1]["system"]
            assert "did not happen" in system
            assert "proves nothing" in system
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_what_was_found_survives_being_written_down():
    """
    §82: real and simulated stay apart across persistence.

    A distinction that only exists in memory is a distinction that stops
    existing at the first restart, which is exactly when it matters.
    """
    async def body():
        client, db = await _db()
        uid = f"e39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.evidence import EvidenceStore, real_support

            store = EvidenceStore(db)
            await store.ensure_indexes()
            gid = f"gol_{uuid.uuid4().hex[:8]}"

            await store.record(_evidence(uid, gid, "simulated", "Finto."))
            back = await store.for_goal(uid, gid)
            assert len(back) == 1
            assert back[0].provenance.source_class == "simulated"
            assert back[0].is_real is False
            assert real_support(back) is False

            await store.record(_evidence(uid, gid, "connected_provider", "Vero."))
            both = await store.for_goal(uid, gid)
            assert real_support(both) is True
            assert sorted(e.provenance.source_class for e in both) == [
                "connected_provider", "simulated"
            ]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_how_old_something_is_is_a_fact_and_not_a_verdict():
    """
    §43: stale does not mean unusable.

    Yesterday's opening hours are usually still right, and deciding whether
    they are is a judgement about a case — which is the model's, not code's.
    """
    from agent.evidence import freshness_of

    now = datetime.now(timezone.utc)
    assert freshness_of(now.isoformat()) == "fresh"
    assert freshness_of((now - timedelta(hours=20)).isoformat()) == "recent"
    assert freshness_of((now - timedelta(days=30)).isoformat()) == "stale"
    assert freshness_of("non è una data") == "unknown"

    # And nothing in the store drops anything for being old.
    import ast

    source = HERE.joinpath("agent", "evidence.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "real_support":
            assert "stale" not in ast.unparse(node), (
                "la freschezza è entrata nel giudizio su cosa è reale"
            )


# ---------------------------------------------------------------------------
# Reuse
# ---------------------------------------------------------------------------

def test_research_already_done_is_not_done_again(monkeypatch):
    """
    §41/§72: the research engine already knows how to reuse. Ask it.

    Duplicating that judgement here would mean two places deciding whether
    two questions are the same question, and they would drift.
    """
    async def body():
        client, db = await _db()
        uid = f"e39_{uuid.uuid4().hex[:8]}"
        try:
            from agent import providers
            from agent.models import ActionStep

            calls = {"n": 0, "reuse": []}

            class FakeResearch:
                def __init__(self, db_):
                    pass

                async def run(self, owner, need, **kw):
                    calls["n"] += 1
                    calls["reuse"].append(kw.get("allow_reuse"))

                    class Run:
                        id = "res_1"
                        status = "ok"
                        synthesis = type("S", (), {"answer": "Si fa così.", "claims": []})()
                        assessments = []
                        outcome_note = ""

                    return Run()

            import research.service as rs

            monkeypatch.setattr(rs, "ResearchService", FakeResearch)

            step = ActionStep(intent="Cercare come si fa.", step_type="research",
                              capability_needed="web.research",
                              expected_result="Come si richiede.")
            outcome = await providers.do_research(db, uid, _goal(uid), step)

            assert calls["n"] == 1
            assert calls["reuse"] == [True], "la ricerca è stata forzata a rifare tutto"
            assert outcome.provenance.source_class == "external_research"
            assert "res_1" in outcome.provenance.source_refs
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_comparison_is_fed_what_research_already_found():
    """
    §18/§42: the comparison engine gets the research runs, not a fresh search.

    And with nothing to compare it says so, rather than comparing nothing and
    recommending the first thing it thought of.
    """
    async def body():
        client, db = await _db()
        uid = f"e39_{uuid.uuid4().hex[:8]}"
        try:
            from agent import providers
            from agent.evidence import EvidenceStore
            from agent.models import ActionStep, AgentEvidence, ResultProvenance

            store = EvidenceStore(db)
            await store.ensure_indexes()
            goal = _goal(uid)

            await store.record(AgentEvidence(
                owner_id=uid, goal_id=goal.id, claim="Trovato.",
                provenance=ResultProvenance(
                    source_class="external_research", capability="web.research",
                    source_refs=["res_7"],
                ),
            ))
            assert await store.research_refs(uid, goal.id) == ["res_7"]

            step = ActionStep(intent="Confrontare.", step_type="compare",
                              capability_needed="comparison.run")
            nothing = await providers.do_comparison(
                db, uid, goal, step, research_refs=[]
            )
            assert nothing.status == "partial"
            assert nothing.error_type == "nothing_to_compare"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# The life model
# ---------------------------------------------------------------------------

def test_a_verified_outcome_proposes_a_life_fact_and_never_writes_one(monkeypatch):
    """
    §54/§55/§56: result → observation → validation → life update.

    The agent proposes, through the governance that already owns durable
    learning. It never writes to the life model itself, and the proposal
    carries handles back to what it rests on.
    """
    async def body():
        client, db = await _db()
        uid = f"e39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            goal = _goal(uid)
            await service.repo.create_goal(goal)
            await service.evidence.record(_evidence(
                uid, goal.id, "external_research", "Il certificato si ritira allo sportello."
            ))

            from agent.models import ActionPlan, ActionStep

            plan = ActionPlan(
                goal_id=goal.id, owner_id=uid, status="active",
                steps=[ActionStep(intent="x", step_type="research", status="succeeded")],
            )
            await service.repo.save_plan(plan)

            seen = {}

            class FakeGovernance:
                def __init__(self, db_):
                    pass

                async def apply(self, *, user_id, session_id, reasoning_epoch,
                                candidate, candidate_index):
                    seen["user_id"] = user_id
                    seen["epoch"] = reasoning_epoch
                    seen["candidate"] = candidate

                    class Outcome:
                        decision = "PROMOTE"
                        persisted = True

                    return Outcome()

            import life_memory.governance as governance

            monkeypatch.setattr(governance, "MemoryGovernanceService", FakeGovernance)

            _install(monkeypatch, FakeModel([
                {"outcome": "achieved", "reasoning": "Le fonti lo dicono."},
            ]))
            result = await service.advance(uid, goal.id)
            assert result["state"] == "completed"

            assert seen, "nessuna osservazione di vita è stata proposta"
            candidate = seen["candidate"]
            assert candidate.operation == "propose", "ha scritto invece di proporre"
            assert goal.id in seen["epoch"], "la proposta non è tracciabile al goal"
            assert any(goal.id in p for p in candidate.provenance)
            assert candidate.evidence_refs, "una proposta senza niente dietro"

            journal = await service.repo.history(uid, goal.id)
            assert [j for j in journal if j["kind"] == "life_observation"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_unverified_result_never_reaches_the_life_model(monkeypatch):
    """
    §55: no canonical fact from something that was not established.

    Two ways of not being established, and both are refused before anything
    is proposed: the outcome was not verified, or it was verified on a
    stand-in.
    """
    async def body():
        client, db = await _db()
        uid = f"e39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            goal = _goal(uid)
            await service.repo.create_goal(goal)

            proposals = {"n": 0}

            class FakeGovernance:
                def __init__(self, db_):
                    pass

                async def apply(self, **kw):
                    proposals["n"] += 1
                    raise AssertionError("ha proposto un fatto non verificato")

            import life_memory.governance as governance

            monkeypatch.setattr(governance, "MemoryGovernanceService", FakeGovernance)

            from agent.models import GoalVerification

            # Verified, but not achieved.
            await service._observe_life_change(
                uid, goal,
                GoalVerification(goal_id=goal.id, outcome="partially_achieved"),
                [_evidence(uid, goal.id, "external_research")],
            )

            # Achieved, on nothing real.
            await service._observe_life_change(
                uid, goal,
                GoalVerification(goal_id=goal.id, outcome="achieved"),
                [_evidence(uid, goal.id, "simulated")],
            )

            assert proposals["n"] == 0
            assert await db.memories.count_documents({"user_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# What a person is told while it happens
# ---------------------------------------------------------------------------

def test_progress_comes_from_what_happened_and_not_from_a_placeholder():
    """
    §50/§51: no fake presence.

    «Sto lavorando…» is what a system says when it has nothing to report and
    would rather not admit it. A goal that has done nothing says so.
    """
    async def body():
        client, db = await _db()
        uid = f"e39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            goal = _goal(uid)
            await service.repo.create_goal(goal)

            visible = await service.for_home(uid)
            assert visible[0]["state"] == "Non ho ancora cominciato."

            await service.repo.journal(
                uid, goal.id, kind="step_done", note="Ho cercato.",
                detail={"came_from": "external_research", "really_happened": True},
            )
            after = await service.for_home(uid)
            assert after[0]["state"] == "Ho cercato quello che serviva."

            # A step that did not really happen does not become progress.
            other = _goal(uid, objective="Un'altra cosa.", desired_outcome="Un altro esito.")
            await service.repo.create_goal(other)
            await service.repo.journal(
                uid, other.id, kind="step_done", note="Finta.",
                detail={"came_from": "simulated", "really_happened": False},
            )
            states = {g["what"]: g["state"] for g in await service.for_home(uid)}
            assert states["Un'altra cosa."] == "Non ho ancora cominciato."
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_surface_never_shows_the_workflow_behind_the_progress():
    """§52: no capability names, no step counts, no lease owner."""
    async def body():
        client, db = await _db()
        uid = f"e39_{uuid.uuid4().hex[:8]}"
        try:
            import json

            service = await _service(db)
            goal = _goal(uid)
            await service.repo.create_goal(goal)
            await service.repo.journal(
                uid, goal.id, kind="step_done", note="Ho letto.",
                detail={"came_from": "internal_observation", "really_happened": True},
            )

            shown = json.dumps(await service.for_home(uid), ensure_ascii=False)
            for leak in (
                "capability", "information.read", "web.research", "step",
                "iteration", "lease", "worker", "provenance", "evidence",
                "internal_observation",
            ):
                assert leak not in shown, f"la superficie mostra {leak}"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())
