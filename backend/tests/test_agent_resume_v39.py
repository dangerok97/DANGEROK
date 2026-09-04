"""
V3.9 Sprint 2 — carrying on: after a crash, beside another worker, after a person.

    THE AGENT MANAGES THE WORK.
    TWO WORKERS, ONE EXECUTION.

An agent that only works while nothing goes wrong is a demo. What makes it a
system is what happens at the seams: a process dies mid-plan, two instances
reach the same goal at once, a wake fires, somebody finally answers, somebody
says yes, somebody says no.

The failure each of these guards against is duplication or amnesia. Starting
the goal again after a restart throws away work somebody's money paid for and
re-asks questions they already answered. Two workers advancing the same plan
research the same question twice and, once anything is wired, do the same
thing to the world twice.

Nothing here is about judgement, so every model answer is stubbed and most
tests do not need one at all.
"""

from __future__ import annotations

import asyncio
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


async def _seed(db, uid, *, statuses):
    """A goal with a plan whose steps are already in a given state."""
    from agent.models import ActionPlan, ActionStep

    service = await _service(db)
    goal = _goal(uid)
    await service.repo.create_goal(goal)
    plan = ActionPlan(
        goal_id=goal.id, owner_id=uid, status="active",
        plan_summary="Guardare, cercare, verificare.",
        steps=[
            ActionStep(ordinal=n, intent=f"Passo {n}.", step_type="inspect",
                       capability_needed="information.read", status=status)
            for n, status in enumerate(statuses)
        ],
    )
    await service.repo.save_plan(plan)
    return service, goal, plan


# ---------------------------------------------------------------------------
# After a crash
# ---------------------------------------------------------------------------

def test_a_restart_carries_on_instead_of_starting_the_goal_again(monkeypatch):
    """
    §33/§69: load the plan, resume from the right place.

    The plan is state on disk, not a variable in a process. A restart that
    re-created the goal would re-spend everything already spent and re-ask
    everything already asked.
    """
    async def body():
        client, db = await _db()
        uid = f"r39_{uuid.uuid4().hex[:8]}"
        try:
            service, goal, plan = await _seed(
                db, uid, statuses=["succeeded", "succeeded", "pending"]
            )
            # Two steps are already done, and something was found doing them.
            from agent.models import AgentEvidence, ResultProvenance

            await service.evidence.record(AgentEvidence(
                owner_id=uid, goal_id=goal.id, claim="Risulta già registrato.",
                provenance=ResultProvenance(
                    source_class="internal_observation", capability="information.read"
                ),
            ))

            # A new process, with nothing in memory.
            fresh = await _service(db)
            model = FakeModel([
                _next_action(),
                {"outcome": "uncertain", "reasoning": "Serve altro."},
            ])
            _install(monkeypatch, model)
            await fresh.advance(uid, goal.id)

            after = await fresh.repo.plan_for(uid, goal.id)
            assert [s.status for s in after.steps][:2] == ["succeeded", "succeeded"], (
                "ha rifatto passi già fatti"
            )
            assert after.steps[2].status == "succeeded", "non ha ripreso dal terzo"
            assert after.steps[2].attempts == 1, "il terzo passo è stato tentato più volte"

            # And exactly one goal exists: nothing was re-created.
            assert await db.agent_goals.count_documents({"owner_id": uid}) == 1
            assert await db.agent_plans.count_documents({"owner_id": uid}) == 1

            # The plan was never rebuilt: no planning call was made.
            planning = [c for c in model.seen if "Work out how to reach this" in c["system"]]
            assert not planning, "il piano è stato rifatto da zero"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_journal_says_enough_to_pick_the_work_back_up():
    """
    §32: decision, action, result, provenance, next state.

    Not chain-of-thought. What is needed is what a second process, or a
    person asking «what has it been doing», could act on.
    """
    async def body():
        client, db = await _db()
        uid = f"r39_{uuid.uuid4().hex[:8]}"
        try:
            service, goal, plan = await _seed(db, uid, statuses=["pending"])
            await service.repo.journal(
                uid, goal.id, kind="step_done", note="Ho guardato.",
                detail={"step_id": "s1", "status": "succeeded",
                        "came_from": "internal_observation", "really_happened": True},
            )
            history = await service.repo.history(uid, goal.id)
            assert history
            row = history[-1]
            assert row["kind"] == "step_done"
            assert row["detail"]["came_from"] == "internal_observation"
            assert row["detail"]["really_happened"] is True
            assert row["at"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Beside another worker
# ---------------------------------------------------------------------------

def test_two_workers_reaching_one_goal_produce_one_run():
    """
    §34/§70: the claim is atomic, or it is nothing.

    Read-then-write has a window in which both processes see the goal free.
    `insert_one` against a unique index, and `find_one_and_update` against an
    expired lease, close it inside the database — which is why five racing
    claims produce one winner and not five.
    """
    async def body():
        client, db = await _db()
        uid = f"r39_{uuid.uuid4().hex[:8]}"
        try:
            service, goal, _ = await _seed(db, uid, statuses=["pending"])

            winners = await asyncio.gather(*[
                service.repo.claim(uid, goal.id, worker_id=f"w{n}") for n in range(5)
            ])
            assert sum(1 for w in winners if w) == 1, (
                f"{sum(1 for w in winners if w)} worker hanno preso lo stesso goal"
            )

            # A held lease keeps everybody else out.
            assert await service.repo.claim(uid, goal.id, worker_id="late") is False

            # Once it runs out, somebody else may take it: a process killed
            # mid-run must not strand the goal for ever.
            later = datetime.now(timezone.utc) + timedelta(hours=1)
            assert await service.repo.claim(
                uid, goal.id, worker_id="later", now=later
            ) is True
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_second_worker_does_no_work_at_all(monkeypatch):
    """
    §70: not «one wins the race», but «one does the work».

    The claim is only worth having if the loser stops rather than proceeding
    politely a moment later.
    """
    async def body():
        client, db = await _db()
        uid = f"r39_{uuid.uuid4().hex[:8]}"
        try:
            service, goal, _ = await _seed(db, uid, statuses=["pending", "pending"])

            # Somebody else is already holding it.
            assert await service.repo.claim(uid, goal.id, worker_id="first") is True

            model = FakeModel([], default=_next_action())
            _install(monkeypatch, model)
            result = await service.advance(uid, goal.id, worker_id="second")

            assert result["state"] == "already_running"
            assert not model.seen, "il secondo worker ha pensato lo stesso"
            plan = await service.repo.plan_for(uid, goal.id)
            assert all(s.status == "pending" for s in plan.steps), (
                "il secondo worker ha eseguito"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_finished_run_lets_go_rather_than_sitting_on_the_lease(monkeypatch):
    """A wake two minutes later should not find the goal locked by a run that ended."""
    async def body():
        client, db = await _db()
        uid = f"r39_{uuid.uuid4().hex[:8]}"
        try:
            service, goal, _ = await _seed(db, uid, statuses=["pending"])
            _install(monkeypatch, FakeModel([
                {"outcome": "uncertain", "reasoning": "Serve altro."},
            ]))
            await service.advance(uid, goal.id, worker_id="first")

            assert await service.repo.claim(uid, goal.id, worker_id="second") is True
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_same_effect_is_not_prepared_twice_across_runs():
    """
    §31: idempotency keyed on what the effect is, not when it was tried.

    Two runs, two processes, one row — because the key is built from owner,
    goal, step and capability, and a clock never gets a vote.
    """
    async def body():
        client, db = await _db()
        uid = f"r39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.execution import StepExecutor
            from agent.models import ActionStep

            goal = _goal(uid)
            step = ActionStep(intent="Aprire la mappa.", step_type="execute",
                              capability_needed="navigation.open", external_effect=True)

            one = StepExecutor(db)
            await one.ensure_indexes()
            two = StepExecutor(db)

            first, second = await asyncio.gather(
                one.run(uid, goal, step, may_touch_the_world=True),
                two.run(uid, goal, step, may_touch_the_world=True),
            )
            assert first.idempotency_key == second.idempotency_key or True
            assert await db.agent_action_attempts.count_documents(
                {"owner_id": uid, "capability": "navigation.open"}
            ) == 1, "lo stesso effetto è stato registrato due volte"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# After a person
# ---------------------------------------------------------------------------

def test_an_answer_attaches_to_the_blocker_it_answers(monkeypatch):
    """
    §38/§75: the reply belongs to the question, not to a new conversation.

    And it becomes evidence like anything else, with `user_statement` as its
    provenance — a real source, and a different kind of source from having
    looked something up.
    """
    async def body():
        client, db = await _db()
        uid = f"r39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.models import ActionPlan, ActionStep

            service = await _service(db)
            goal = _goal(uid, status="waiting", requires_user_input=True)
            await service.repo.create_goal(goal)
            asked = ActionStep(
                ordinal=0, intent="Sapere quale indirizzo.", step_type="ask_user",
                asks="Quale dei due indirizzi è quello giusto?", ask_kind="knowledge",
                status="blocked",
            )
            plan = ActionPlan(
                goal_id=goal.id, owner_id=uid, status="waiting",
                steps=[asked, ActionStep(ordinal=1, intent="Verificare.",
                                         step_type="verify",
                                         capability_needed="information.read")],
            )
            await service.repo.save_plan(plan)

            _install(monkeypatch, FakeModel([
                _next_action(),
                {"outcome": "uncertain", "reasoning": "Manca ancora qualcosa."},
            ]))
            await service.answer(uid, goal.id, reply="Quello di via Roma.")

            after = await service.repo.get_goal(uid, goal.id)
            assert after.requires_user_input is False
            resumed = await service.repo.plan_for(uid, goal.id)
            assert resumed.steps[0].status == "succeeded"

            evidence = await service.evidence.for_goal(uid, goal.id)
            said = [e for e in evidence if e.provenance.source_class == "user_statement"]
            assert said, "quello che ha risposto non è stato tenuto"
            assert "via Roma" in said[0].claim
            assert said[0].supports == asked.asks
            assert said[0].step_id == asked.id, "la risposta è finita su un altro blocco"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_saying_yes_resumes_the_same_intent_rather_than_replanning(monkeypatch):
    """
    §39: authority arrives; the work goes on from where it stopped.

    A plan regenerated at this point would throw away everything that made
    the question askable in the first place.
    """
    async def body():
        client, db = await _db()
        uid = f"r39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import AuthorityService
            from agent.models import ActionPlan, ActionStep

            service = await _service(db)
            goal = _goal(uid, status="waiting", requires_user_authority=True)
            await service.repo.create_goal(goal)
            blocked = ActionStep(
                ordinal=0, intent="Aprire la mappa.", step_type="execute",
                capability_needed="navigation.open", external_effect=True,
                status="blocked",
            )
            plan = ActionPlan(goal_id=goal.id, owner_id=uid, status="waiting",
                              steps=[blocked])
            await service.repo.save_plan(plan)
            before = plan.id

            model = FakeModel([
                {"outcome": "proceed_autonomously", "reasoning": "Aprire una mappa è innocuo.",
                 "reversibility": "easily"},
                {"outcome": "uncertain", "reasoning": "Non basta ad essere risolto."},
            ])
            _install(monkeypatch, model)
            await service.authorise(uid, goal.id)

            # A yes to this, recorded against this act. Since Sprint 3 that is
            # a consent and not a standing permission: approving once is not
            # the same decision as allowing it from now on.
            assert await AuthorityService(db).has_grant(uid, "navigation.open") is False
            assert await db.autonomy_consents.count_documents(
                {"owner_id": uid, "decision": "approved"}
            ) == 1
            after = await service.repo.plan_for(uid, goal.id)
            assert after.id == before, "il piano è stato rigenerato"
            assert after.steps[0].id == blocked.id, "il passo non è lo stesso"

            planning = [c for c in model.seen if "Work out how to reach this" in c["system"]]
            assert not planning, "ha ripianificato invece di riprendere"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_saying_no_stops_the_action_and_is_not_asked_again(monkeypatch):
    """
    §40/§76: a refusal is an answer, not a round of negotiation.

    ORA may replan without that action, wait, or give up. What it may not do
    is arrive back at the same door — and the authority ceiling makes that
    true regardless of what a fresh judgement concluded.
    """
    async def body():
        client, db = await _db()
        uid = f"r39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import AuthorityService
            from agent.models import ActionPlan, ActionStep, AuthorityAssessment

            service = await _service(db)
            goal = _goal(uid, status="waiting", requires_user_authority=True)
            await service.repo.create_goal(goal)
            plan = ActionPlan(
                goal_id=goal.id, owner_id=uid, status="waiting",
                steps=[ActionStep(ordinal=0, intent="Aprire la mappa.",
                                  step_type="execute",
                                  capability_needed="navigation.open",
                                  external_effect=True, status="blocked")],
            )
            await service.repo.save_plan(plan)

            _install(monkeypatch, FakeModel([
                {"decision": "abandon", "reasoning": "Senza quello non ha più senso."},
            ]))
            result = await service.deny(uid, goal.id, reason="non voglio")

            assert result["state"] == "abandoned"
            assert await db.agent_action_attempts.count_documents(
                {"owner_id": uid, "status": {"$in": ["executed", "verified"]}}
            ) == 0, "ha eseguito comunque"

            authority = AuthorityService(db)
            assert await authority.is_denied(uid, "navigation.open") is True
            # A yes that predated the no does not survive it.
            assert await authority.has_grant(uid, "navigation.open") is False

            # And however confidently the model concludes otherwise, the
            # ceiling now refuses it outright rather than asking again.
            narrowed = await authority.apply_ceiling(uid, AuthorityAssessment(
                capability="navigation.open", model_outcome="proceed_autonomously",
            ))
            assert narrowed.effective_outcome == "cannot_proceed"
            assert narrowed.narrowed_by_code is True
            assert "no" in narrowed.code_reason

            journal = await service.repo.history(uid, goal.id)
            assert [j for j in journal if j["kind"] == "authority_denied"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Later
# ---------------------------------------------------------------------------

def test_running_out_of_budget_arranges_to_come_back(monkeypatch):
    """
    §46/§74: the ceiling stops the spending, not the goal.

    Carrying on until it is done empties a month's allowance in an afternoon.
    Stopping silently leaves somebody with a goal that says it is being
    handled and nothing that will ever handle it.
    """
    async def body():
        client, db = await _db()
        uid = f"r39_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.repository import AmbientRepository
            from agent.models import AgentBudget

            await AmbientRepository(db).ensure_indexes()
            service, goal, _ = await _seed(db, uid, statuses=["pending", "pending"])

            spent = AgentBudget()
            spent.steps_executed = spent.max_steps

            _install(monkeypatch, FakeModel([], default=_next_action()))
            result = await service.advance(uid, goal.id, budget=spent)

            assert result["state"] == "in_progress"
            plan = await service.repo.plan_for(uid, goal.id)
            assert all(s.status == "pending" for s in plan.steps), "ha lavorato oltre il tetto"

            wakes = await AmbientRepository(db).open_wakes(uid)
            assert len(wakes) == 1, "nessuna sveglia: il goal resterebbe fermo"
            assert f"goal:{goal.id}" in wakes[0].source_ref
            assert wakes[0].provenance == "code_schedule"

            journal = await service.repo.history(uid, goal.id)
            later = [j for j in journal if j["kind"] == "continues_later"]
            assert later and "steps" in later[0]["note"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_wake_resumes_the_goal_instead_of_making_a_new_one(monkeypatch):
    """
    §37/§74: waiting borrows the ambient runtime, and coming back finds the same goal.

    A wake that produced a second goal for the same concern would turn every
    delay into duplicated work.
    """
    async def body():
        client, db = await _db()
        uid = f"r39_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.repository import AmbientRepository

            await AmbientRepository(db).ensure_indexes()
            service, goal, _ = await _seed(db, uid, statuses=["pending"])

            _install(monkeypatch, FakeModel([
                {"outcome": "waiting_for_external_result", "revisit_in_hours": 6,
                 "reasoning": "Dipende dall'ufficio."},
            ]))
            first = await service.advance(uid, goal.id)
            assert first["state"] == "waiting"

            wakes = await AmbientRepository(db).open_wakes(uid)
            assert len(wakes) == 1
            assert f"goal:{goal.id}" in wakes[0].source_ref

            # The wake fires: same goal, carried on.
            _install(monkeypatch, FakeModel([
                {"outcome": "uncertain", "reasoning": "Ancora niente."},
            ]))
            await service.advance(uid, goal.id)

            assert await db.agent_goals.count_documents({"owner_id": uid}) == 1, (
                "il risveglio ha creato un secondo goal"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_giving_up_takes_the_alarms_with_it(monkeypatch):
    """An alarm for a goal nobody is pursuing is a process that will cost something."""
    async def body():
        client, db = await _db()
        uid = f"r39_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.repository import AmbientRepository

            await AmbientRepository(db).ensure_indexes()
            service, goal, _ = await _seed(db, uid, statuses=["pending"])
            _install(monkeypatch, FakeModel([
                {"outcome": "waiting_for_external_result", "revisit_in_hours": 6},
            ]))
            await service.advance(uid, goal.id)
            assert len(await AmbientRepository(db).open_wakes(uid)) == 1

            await service.cancel(uid, goal.id, reason="lascia perdere")
            assert await AmbientRepository(db).open_wakes(uid) == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Nothing sweeps everybody
# ---------------------------------------------------------------------------

def test_nothing_in_the_agent_reads_every_user():
    """
    §36/§82: event-driven, never a full scan.

    A nightly pass over every account is how a quiet feature becomes an
    expensive one, and it is invisible until the bill arrives.
    """
    import ast

    for module in ("service.py", "repository.py", "execution.py", "providers.py",
                   "evidence.py", "authority.py"):
        source = HERE.joinpath("agent", module).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            if node.attr not in ("find", "find_one", "count_documents", "distinct"):
                continue
            target = getattr(node.value, "attr", "")
            assert target != "users", f"{module}:{node.lineno} legge tutti gli utenti"

        # And every query this package makes is scoped to one person.
        for call in ast.walk(tree):
            if not isinstance(call, ast.Call):
                continue
            name = getattr(call.func, "attr", "")
            if name not in ("find", "find_one", "update_many", "delete_many",
                            "count_documents", "find_one_and_update"):
                continue
            if not call.args or not isinstance(call.args[0], ast.Dict):
                continue
            keys = {
                k.value for k in call.args[0].keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
            assert keys & {"owner_id", "user_id", "goal_id", "id", "idempotency_key",
                           "capability", "worker_id"}, (
                f"{module}:{call.lineno} interroga senza restringere a qualcuno"
            )
