"""
V3.9 Sprint 1 — the authority ceiling: what ORA is allowed to actually do.

    AI MAY RECOMMEND AUTONOMY.
    CODE MAY DENY IT.
    AI MAY NOT OVERRIDE POLICY.

The asymmetry is the whole safety story, and most of this file is one
assertion said many ways: the model's judgement can only ever be made more
cautious, never less. A model that has been talked into enthusiasm — by a
crafted document, a persuasive email, or simply by being wrong — can return
`proceed_autonomously` all day. It will not get past the ceiling without a
grant a person actually made.

The other half is that Sprint 1 deliberately cannot cross into the world at
all. Nothing here sends an email, writes a calendar, books anything or spends
money — and the tests check that by watching for effects rather than by
trusting that nobody wired one up.
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
        "autonomy_grants", "autonomy_policies", "permission_grants",
        "ambient_wakes", "ambient_activity", "calendar_events",
    ):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


class FakeModel:
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


def _next_action(decision="execute", **over):
    """What the model says when asked which step is worth doing now."""
    answer = {
        "decision": decision,
        "reasoning": "Il passo successivo ha ancora senso.",
        "step_id": "",
    }
    answer.update(over)
    return answer


def _install(monkeypatch, model):
    import agent.reasoning as reasoning

    monkeypatch.setattr(reasoning, "_ask_model", model)


def _goal(**over):
    answer = {
        "outcome": "create_goal",
        "objective": "Fare in modo che la richiesta arrivi a destinazione.",
        "desired_outcome": "La richiesta è stata ricevuta.",
        "why_now": "La finestra si chiude domani.",
        "success_criteria": ["La richiesta risulta ricevuta."],
        "stop_conditions": ["La finestra si chiude."],
    }
    answer.update(over)
    return answer


def _plan_with_write(capability="calendar.write", **over):
    answer = {
        "plan_summary": "Preparare e poi agire.",
        "expected_outcome": "Fatto.",
        "steps": [
            {
                "intent": "Guardare cosa c'è già.",
                "step_type": "inspect",
                "capability_needed": "information.read",
            },
            {
                "intent": "Fare la cosa nel mondo.",
                "step_type": "execute",
                "capability_needed": capability,
                "external_effect": True,
                "reversibility": "easily",
            },
        ],
    }
    answer.update(over)
    return answer


def _authority(outcome="proceed_autonomously", **over):
    answer = {
        "outcome": outcome,
        "reasoning": "Sembra una cosa ordinaria.",
        "reversibility": "easily",
        "financial_effect": False,
        "external_communication": False,
        "third_party_impact": False,
        "privacy_disclosure": False,
        "legal_effect": False,
        "security_effect": False,
    }
    answer.update(over)
    return answer


async def _service(db):
    from agent.service import AgentService

    service = AgentService(db)
    await service.ensure_indexes()
    return service


async def _allow_capability(db, uid, capability):
    """Grant the underlying permission, which is a different thing from a grant."""
    from permissions.service import PermissionService

    # The connector the resolver actually asks about, taken from the same map
    # it reads. Guessing it from the capability's prefix is what let the two
    # drift apart in the first place: the fixture granted `calendar` while the
    # registry has always called that connector `calendar_google`, so every
    # real person resolved as "not permitted" and only the tests were green.
    from agent.capabilities import _CONNECTOR

    connector = _CONNECTOR.get(capability, capability.split(".")[0])
    await PermissionService(db).grant(
        user_id=uid, capability_id=capability, connector_id=connector
    )


# ---------------------------------------------------------------------------
# The ceiling
# ---------------------------------------------------------------------------

def test_code_can_narrow_what_the_model_concluded(monkeypatch):
    """
    §19: the model recommends; code decides.

    Here it says "go ahead" about something that changes the world with no
    grant behind it — and gets `prepare_then_confirm` instead.
    """
    async def body():
        client, db = await _db()
        uid = f"u39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import AuthorityService
            from agent.models import AuthorityAssessment

            await _allow_capability(db, uid, "calendar.write")
            service = AuthorityService(db)

            assessment = await service.apply_ceiling(
                uid,
                AuthorityAssessment(
                    capability="calendar.write",
                    model_outcome="proceed_autonomously",
                    reasoning="mi sembra normale",
                ),
            )

            assert assessment.model_outcome == "proceed_autonomously"
            assert assessment.effective_outcome != "proceed_autonomously"
            assert assessment.narrowed_by_code is True
            assert assessment.code_reason
            assert await service.may_execute(uid, assessment) is False
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_code_never_makes_the_answer_more_permissive(monkeypatch):
    """
    The asymmetry, checked in every direction.

    Whatever the model says, and whatever grants exist, the effective outcome
    is never further along the permissive end than what was recommended.
    """
    async def body():
        client, db = await _db()
        uid = f"u39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import _LADDER, AuthorityService
            from agent.models import AuthorityAssessment

            service = AuthorityService(db)
            await _allow_capability(db, uid, "calendar.write")
            await service.grant(uid, "calendar.write", by="user")
            await service.set_mode(uid, "act_within_grants")

            for said in _LADDER:
                assessment = await service.apply_ceiling(
                    uid,
                    AuthorityAssessment(capability="calendar.write", model_outcome=said),
                )
                assert _LADDER.index(assessment.effective_outcome) >= _LADDER.index(said), (
                    f"il codice ha allargato «{said}» a «{assessment.effective_outcome}»"
                )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_model_cannot_create_authority_for_itself(monkeypatch):
    """
    §42/§59: AI DOES NOT INVENT GRANTS.

    Saying it would be convenient to proceed is not a grant, and there is no
    path from a model answer to one.
    """
    async def body():
        client, db = await _db()
        uid = f"u39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import AuthorityService

            service = AuthorityService(db)
            refused = await service.grant(uid, "mail.send", by="model")
            assert refused["ok"] is False
            assert await service.has_grant(uid, "mail.send") is False

            # Only a person or code reaches this.
            allowed = await service.grant(uid, "calendar.write", by="user")
            assert allowed["ok"] is True
            assert await service.has_grant(uid, "calendar.write") is True
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_grant_belongs_to_one_person(monkeypatch):
    async def body():
        client, db = await _db()
        mine = f"u39_{uuid.uuid4().hex[:8]}"
        theirs = f"u39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import AuthorityService

            service = AuthorityService(db)
            await service.grant(mine, "calendar.write", by="user")

            assert await service.has_grant(mine, "calendar.write") is True
            assert await service.has_grant(theirs, "calendar.write") is False
            assert await service.grants(theirs) == []
        finally:
            for uid in (mine, theirs):
                await _clean(db, uid)
            client.close()

    _run(body())


def test_revoking_takes_the_authority_back(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"u39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import AuthorityService

            service = AuthorityService(db)
            await service.grant(uid, "calendar.write", by="user")
            await service.revoke(uid, "calendar.write")
            assert await service.has_grant(uid, "calendar.write") is False
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_some_effects_never_proceed_on_a_models_word(monkeypatch):
    """
    §38/§50/§65: money, contracts and messages to other people.

    Not even with a grant. Sprint 1 does not cross these at all, and the list
    is in code rather than in a prompt because a prompt can be argued with.
    """
    async def body():
        client, db = await _db()
        uid = f"u39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import AuthorityService, _NEVER_AUTONOMOUS
            from agent.models import AuthorityAssessment

            service = AuthorityService(db)
            for capability in _NEVER_AUTONOMOUS:
                await service.grant(uid, capability, by="user")
                assessment = await service.apply_ceiling(
                    uid,
                    AuthorityAssessment(
                        capability=capability, model_outcome="proceed_autonomously"
                    ),
                )
                assert await service.may_execute(uid, assessment) is False, (
                    f"«{capability}» è partita da sola"
                )

            assert {"payment.execute", "mail.send"}.issubset(_NEVER_AUTONOMOUS)
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_what_the_person_asked_for_can_only_tighten_things(monkeypatch):
    """§39: a conservative default, and a mode that narrows rather than opens."""
    async def body():
        client, db = await _db()
        uid = f"u39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import AuthorityService
            from agent.models import AuthorityAssessment

            service = AuthorityService(db)
            policy = await service.policy(uid)
            assert policy.mode == "prepare", "il default non è conservativo"
            assert policy.chosen_by_user is False, "un default non è una scelta"

            await _allow_capability(db, uid, "calendar.write")
            await service.grant(uid, "calendar.write", by="user")
            await service.set_mode(uid, "observe")

            assessment = await service.apply_ceiling(
                uid,
                AuthorityAssessment(
                    capability="calendar.write", model_outcome="proceed_autonomously"
                ),
            )
            assert assessment.effective_outcome == "ask_before_execution"
            assert "osservi soltanto" in assessment.code_reason
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# What happens in a plan
# ---------------------------------------------------------------------------

def test_everything_is_prepared_before_the_question_is_asked(monkeypatch):
    """
    §23/§57: «è tutto pronto, procedo?» — never «cosa vuoi che faccia?».

    The reading happens, the preparation happens, and only then does ORA
    stop. That order is the difference between an agent and a form.
    """
    async def body():
        client, db = await _db()
        uid = f"u39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            await _allow_capability(db, uid, "calendar.write")

            _install(monkeypatch, FakeModel([_goal()]))
            created = await service.consider(uid, situation={"what": "x"})

            _install(monkeypatch, FakeModel([
                _plan_with_write(),
                _next_action(),
                _authority("proceed_autonomously"),
            ]))
            result = await service.advance(uid, created["goal_id"])

            assert result["state"] == "awaiting_authority"
            assert result["kind"] == "authority"

            plan = await service.repo.plan_for(uid, created["goal_id"])
            # The work before the boundary is done.
            assert plan.steps[0].status == "succeeded"
            assert plan.steps[1].status == "blocked"

            # And the intent was written down before stopping.
            intents = await service.executor.intents_for(uid, created["goal_id"])
            assert len(intents) == 1
            assert intents[0]["capability"] == "calendar.write"

            goal = await service.repo.get_goal(uid, created["goal_id"])
            assert goal.requires_user_authority is True
            assert goal.requires_user_input is False
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_existing_grant_removes_the_question_but_not_the_boundary(monkeypatch):
    """
    §58: with a grant, ORA does not ask again.

    It still does not cross into the world, because in Sprint 1 nothing is
    wired behind that door — and the observation says so rather than
    pretending something happened.
    """
    async def body():
        client, db = await _db()
        uid = f"u39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import AuthorityService

            service = await _service(db)
            # `navigation.open` is the one world-changing capability with a
            # stub behind it, so this path can actually be observed.
            await AuthorityService(db).grant(uid, "navigation.open", by="user")
            await AuthorityService(db).set_mode(uid, "act_within_grants")

            _install(monkeypatch, FakeModel([_goal()]))
            created = await service.consider(uid, situation={"what": "x"})

            _install(monkeypatch, FakeModel([
                _plan_with_write(capability="navigation.open"),
                _next_action(),
                _authority("proceed_autonomously"),
                {"outcome": "achieved", "reasoning": "fatto"},
            ]))
            result = await service.advance(uid, created["goal_id"])

            # Not blocked on a question any more.
            assert result["state"] != "awaiting_authority"
            goal = await service.repo.get_goal(uid, created["goal_id"])
            assert goal.requires_user_authority is False

            journal = await service.repo.history(uid, created["goal_id"])
            assessed = [j for j in journal if j["kind"] == "authority_assessed"]
            assert assessed, "l'autorità non è stata valutata"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_saying_yes_is_a_yes_to_this_and_not_a_standing_permission(monkeypatch):
    """
    §25/§41: one-time approval is not a blank cheque.

    Sprint 1 turned every yes into a grant, which was convenient and wrong:
    somebody agreeing to one thing has not agreed to everything that shape.
    A plain approval now records a consent bound to that effect; a standing
    permission only exists because somebody asked for one.
    """
    async def body():
        client, db = await _db()
        uid = f"u39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import AuthorityService

            service = await _service(db)
            authority = AuthorityService(db)

            _install(monkeypatch, FakeModel([_goal()]))
            created = await service.consider(uid, situation={"what": "x"})
            _install(monkeypatch, FakeModel([
                _plan_with_write(capability="navigation.open"),
                _next_action(),
                _authority("prepare_then_confirm"),
            ]))
            await service.advance(uid, created["goal_id"])
            assert await authority.has_grant(uid, "navigation.open") is False

            _install(monkeypatch, FakeModel([
                _next_action(),
                _authority("proceed_autonomously"),
                {"outcome": "achieved", "reasoning": "fatto"},
            ], default={"outcome": "silent", "headline": "", "about": "niente"}))
            result = await service.authorise(uid, created["goal_id"])

            # A yes, and only to this: no standing permission was created.
            assert await authority.has_grant(uid, "navigation.open") is False, (
                "un sì una volta è diventato un permesso permanente"
            )
            assert await db.autonomy_consents.count_documents(
                {"owner_id": uid, "decision": "approved"}
            ) == 1
            goal = await service.repo.get_goal(uid, created["goal_id"])
            assert goal.requires_user_authority is False
            assert result["ok"] is True
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_standing_permission_exists_only_because_somebody_asked_for_one(monkeypatch):
    """
    §24/§25/§49: "puoi farlo anche in futuro" is a separate decision.

    And it is scoped to what was approved: the same shape of act, for this
    person alone. Nothing about approving once widens it.
    """
    async def body():
        client, db = await _db()
        uid = f"u39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import AuthorityService

            service = await _service(db)
            authority = AuthorityService(db)

            _install(monkeypatch, FakeModel([_goal()]))
            created = await service.consider(uid, situation={"what": "x"})
            _install(monkeypatch, FakeModel([
                _plan_with_write(capability="navigation.open"),
                _next_action(),
                _authority("prepare_then_confirm"),
            ]))
            await service.advance(uid, created["goal_id"])

            _install(monkeypatch, FakeModel([
                _next_action(),
                _authority("proceed_autonomously"),
                {"outcome": "achieved", "reasoning": "fatto"},
            ], default={"outcome": "silent", "headline": "", "about": "niente"}))
            await service.authorise(uid, created["goal_id"], persistent=True)

            assert await authority.has_grant(uid, "navigation.open") is True
            grants = await authority.grants(uid)
            assert grants and grants[0]["granted_by"] == "user"

            row = await db.autonomy_grants.find_one({"owner_id": uid}, {"_id": 0})
            # Scoped to the shape that was approved, and no wider.
            assert row["effect_scope"] == ["create"]
            assert row["allows_external_party"] is False
            assert row["allows_financial"] is False
            assert row["allows_destructive"] is False
            assert row["human_summary"], "il permesso non si sa raccontare"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_same_effect_attempted_twice_is_one_effect(monkeypatch):
    """
    §43: idempotency, keyed on what the effect is rather than when it was tried.

    A retry after a timeout has to match the attempt that may already have
    gone through.
    """
    async def body():
        client, db = await _db()
        uid = f"u39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.models import ActionIntent, ActionStep, AutonomousGoal
            from agent.execution import StepExecutor

            executor = StepExecutor(db)
            await executor.ensure_indexes()
            await _allow_capability(db, uid, "calendar.write")

            goal = AutonomousGoal(
                owner_id=uid, objective="o", desired_outcome="d", status="active"
            )
            step = ActionStep(
                intent="Fare la cosa.", step_type="execute",
                capability_needed="calendar.write", external_effect=True,
            )

            first = await executor.run(uid, goal, step, may_touch_the_world=False)
            second = await executor.run(uid, goal, step, may_touch_the_world=False)

            assert first.idempotency_key == second.idempotency_key
            assert await db.agent_action_attempts.count_documents(
                {"owner_id": uid}
            ) == 1, "lo stesso effetto è stato registrato due volte"
            # Prepared twice is still prepared once, and still not done: the
            # second attempt reports the same state rather than claiming a
            # success it never had.
            assert second.status == "partial"
            assert second.error_type == "authority_required"

            # And once something has actually gone through, the same intent
            # tried again is recognised instead of repeated. This is the half
            # that matters: a retry after a timeout must not produce the
            # effect twice.
            done_step = ActionStep(
                intent="Aprire la mappa.", step_type="execute",
                capability_needed="navigation.open", external_effect=True,
            )
            went = await executor.run(uid, goal, done_step, may_touch_the_world=True)
            assert went.status == "succeeded"
            assert went.provenance.source_class == "simulated", (
                "un'esecuzione simulata si è dichiarata reale"
            )

            again = await executor.run(uid, goal, done_step, may_touch_the_world=True)
            assert again.error_type == "already_done"
            assert "già" in again.observation
            assert await db.agent_action_attempts.count_documents(
                {"owner_id": uid, "capability": "navigation.open"}
            ) == 1, "lo stesso effetto è stato eseguito due volte"

            # The key does not move with the clock.
            a = ActionIntent(owner_id=uid, goal_id=goal.id, step_id=step.id,
                             capability="calendar.write")
            b = ActionIntent(owner_id=uid, goal_id=goal.id, step_id=step.id,
                             capability="calendar.write")
            assert a.idempotency_key == b.idempotency_key
            assert a.id != b.id
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_boundary_moved_by_exactly_one_capability(monkeypatch):
    """
    §51/§52/§54: what still never happens, whatever anybody authorised.

    Sprint 3 crosses the line once, deliberately, on the mildest write there
    is. This is the test that says everything else is still on the other side
    — and it asks with a grant in hand, because "we did not wire it" is a
    weaker promise than "it is authorised and still does not happen".
    """
    async def body():
        client, db = await _db()
        uid = f"u39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import AuthorityService
            from agent.execution import StepExecutor
            from agent.models import ActionStep, AutonomousGoal

            executor = StepExecutor(db)
            await executor.ensure_indexes()
            goal = AutonomousGoal(
                owner_id=uid, objective="o", desired_outcome="d", status="active"
            )
            authority = AuthorityService(db)

            for capability in ("mail.send", "external.booking", "payment.execute"):
                # No registry grant: the registry does not even know these,
                # which is itself one of the reasons they cannot run. The
                # autonomy grant is given anyway, so that what stops them is
                # not merely "nobody allowed it".
                await authority.grant(uid, capability, by="user")
                step = ActionStep(
                    intent="Fare la cosa nel mondo.", step_type="execute",
                    capability_needed=capability, external_effect=True,
                )
                result = await executor.run(uid, goal, step, may_touch_the_world=True)

                assert result.status != "succeeded", f"{capability} è partita"
                assert result.error_type in (
                    "execution_not_wired", "requires_connection", "not_permitted",
                ), f"{capability}: {result.error_type}"

            # And nothing reached a provider, so nothing was recorded as done.
            assert await db.agent_receipts.count_documents({"owner_id": uid}) == 0
            assert await db.agent_action_attempts.count_documents(
                {"owner_id": uid, "status": {"$in": ["executed", "verified"]}}
            ) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_without_the_underlying_permission_nothing_proceeds(monkeypatch):
    """A grant is not a substitute for being allowed to touch the thing."""
    async def body():
        client, db = await _db()
        uid = f"u39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import AuthorityService
            from agent.models import AuthorityAssessment

            service = AuthorityService(db)
            # A grant, but no permission behind it.
            await service.grant(uid, "calendar.write", by="user")

            assessment = await service.apply_ceiling(
                uid,
                AuthorityAssessment(
                    capability="calendar.write", model_outcome="proceed_autonomously"
                ),
            )
            assert assessment.effective_outcome == "cannot_proceed"
            assert "accesso non concesso" in assessment.code_reason
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_reading_and_thinking_need_no_permission_and_no_question(monkeypatch):
    """
    §20: do not ask permission to think.

    Reading what ORA already holds, researching, comparing and drafting cost
    the person nothing. A plan that stopped for them would be a quiz.
    """
    async def body():
        client, db = await _db()
        uid = f"u39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.capabilities import CapabilityResolver

            resolver = CapabilityResolver(db)
            for capability in (
                "information.read", "web.research", "document.read",
                "document.create", "mail.draft",
            ):
                resolution = await resolver.resolve(uid, capability)
                assert resolution.permitted is True, f"{capability} chiede il permesso"
                assert resolution.writes is False, f"{capability} tocca il mondo"
                assert resolution.usable is True
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_drafting_and_sending_are_not_the_same_capability():
    """§48: ORA may often draft. Sending is a different question."""
    from agent.capabilities import capability_facts

    draft = capability_facts("mail.draft")
    send = capability_facts("mail.send")

    assert draft.writes is False
    assert send.writes is True
    assert send.reaches_third_party is True
    assert send.reversibility == "irreversible"


def test_reading_and_writing_a_calendar_are_not_the_same_capability():
    """§49: read may be allowed where write is not."""
    from agent.capabilities import capability_facts

    assert capability_facts("calendar.read").writes is False
    assert capability_facts("calendar.write").writes is True


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def _source(*parts) -> str:
    return HERE.joinpath(*parts).read_text(encoding="utf-8")


def _code_only(text: str) -> str:
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


def test_only_one_function_decides_whether_a_step_may_run():
    """
    §19: one door, and it is not in the executor.

    If anything other than the ceiling could produce permission, the ceiling
    would be advisory — and nothing in a test would necessarily notice.
    """
    execution = _code_only(_source("agent", "execution.py"))
    # The executor takes the answer; it never works it out.
    assert "may_touch_the_world" in execution
    for deciding in ("has_grant", "apply_ceiling", "AuthorityService", "policy("):
        assert deciding not in execution, f"l'esecutore decide da sé: {deciding}"

    service = _code_only(_source("agent", "service.py"))
    assert service.count("may_execute") == 1


def test_the_model_answer_is_never_used_without_the_ceiling():
    """`model_outcome` must not reach an execution decision on its own."""
    service = _code_only(_source("agent", "service.py"))
    assert "apply_ceiling" in service

    # `may_touch` may only ever be assigned a literal or the ceiling's answer.
    for match in re.finditer(r"may_touch\s*=\s*(.+)", service):
        assigned = match.group(1).strip()
        assert assigned in ("True", "False") or "may_execute" in assigned, (
            f"may_touch assegnato da qualcos'altro: {assigned}"
        )
    assert "model_outcome ==" not in service, "il verdetto del modello usato direttamente"


def test_grants_can_only_be_made_by_a_person_or_by_code():
    """§42, structurally: there is no third value and no path from a model."""
    from agent.models import AutonomyGrant
    import typing

    granters = set(typing.get_args(AutonomyGrant.model_fields["granted_by"].annotation))
    assert granters == {"user", "code"}

    # Read from source: `ast.unparse` normalises quotes, so a literal match
    # would fail for a reason that has nothing to do with the rule.
    authority = _source("agent", "authority.py")
    assert re.search(r"by not in \(.user., .code.\)", authority), (
        "chiunque può creare un grant"
    )

    # And nothing in the reasoning path can reach the grant function.
    reasoning = _code_only(_source("agent", "reasoning.py"))
    for reach in ("grant", "AuthorityService", "has_grant"):
        assert reach not in reasoning, f"il ragionatore raggiunge {reach}"


def test_no_secret_or_token_ever_reaches_the_model():
    """§47: minimum necessary disclosure, and tokens are never necessary."""
    for module in ("reasoning.py", "service.py", "execution.py"):
        code = _code_only(_source("agent", module))
        for secret in ("token", "api_key", "password", "secret", "authorization"):
            assert secret not in code.lower(), f"{module} tocca {secret}"

    # An intent carries references and, since a real write needs a time in
    # it, bounded values — but a credential cannot survive being put in one.
    # The older rule was "no values at all", which stopped being possible the
    # moment anything real was wired; this is narrower and harder to get past.
    from agent.models import ActionIntent

    fields = set(ActionIntent.model_fields)
    assert "parameter_refs" in fields
    for value in ("payload", "body", "credentials", "headers", "auth"):
        assert value not in fields, f"l'intento porta {value}"

    smuggled = ActionIntent(
        owner_id="u", goal_id="g", step_id="s", capability="calendar.write",
        parameters={
            "title": "Ritiro certificato",
            "starts_at": "2026-09-03T08:30:00+00:00",
            "access_token": "FINTO-non-e-una-chiave",
            "Authorization": "FINTO-portatore",
            "api_key": "FINTO-chiave-api",
            "refresh_token": "FINTO-rinnovo",
            "nested": {"token": "x"},
        },
    )
    kept = set(smuggled.parameters)
    assert kept == {"title", "starts_at"}, f"e' passato qualcosa: {kept}"
    serialised = str(smuggled.model_dump())
    for leaked in ("FINTO-non-e-una-chiave", "FINTO-portatore",
               "FINTO-chiave-api", "FINTO-rinnovo"):
        assert leaked not in serialised, f"un segreto e' sopravvissuto: {leaked}"

    # And it cannot grow without bound, because an unbounded dictionary
    # reaches a prompt eventually.
    wide = ActionIntent(
        owner_id="u", goal_id="g", step_id="s", capability="calendar.write",
        parameters={f"k{n}": "v" for n in range(40)},
    )
    assert len(wide.parameters) <= 12


def test_a_notification_is_not_a_way_to_authorise_something():
    """
    §73: no notification used as authority.

    A push is a way of telling somebody; it is not a way of them telling ORA
    yes, and the two must not share a path.
    """
    for module in ("service.py", "authority.py", "execution.py"):
        code = _code_only(_source("agent", module))
        for delivery in ("DeliveryService(", "send(", "push"):
            if delivery == "DeliveryService(":
                # Allowed for one thing only: recording that work happened.
                for line in code.splitlines():
                    if delivery in line:
                        assert "note_activity" in code.split(delivery)[1][:200], (
                            f"{module} usa la consegna per qualcosa d'altro"
                        )
            else:
                assert delivery not in code, f"{module} notifica per autorizzare"
