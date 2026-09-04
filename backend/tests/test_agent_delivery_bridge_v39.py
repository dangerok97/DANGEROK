"""
V3.9 Sprint 2 close-out — the bridge: an agent that needs you can reach you.

    ORA MAY NEED THE USER WITHOUT WAITING FOR THE USER TO RETURN.
    A NEED FOR THE USER IS NOT AUTOMATICALLY A PUSH.
    REQUIRES_ATTENTION IS NOT PUSH. ASK_USER IS NOT A NOTIFICATION.
    NO PUSH IS NOT NEED RESOLVED.

Two failures, again opposite, and this time both are architectural.

The first is the one that made this necessary: an agent that gets stuck can
only be *seen*, by somebody who happens to open the app. Fine for "I found
something useful", wrong for "everything is ready and I need one word" — the
agent that manages the work ends up managed by the user's habits.

The second is the shortcut that fixes the first and ruins everything else:
invent an Opportunity so the delivery path carries it, or wire
`requires_attention` straight to a push. Both are three lines, both work on
the day they are written, and both end the judgement that decides whether
anybody deserves to be interrupted. Several tests here exist only to fail the
day somebody writes one.

Underneath all of it is one distinction the whole file defends: a message is
not the work. Sent, delivered, opened, ignored — none of those change whether
ORA is still blocked, and none of them are consent.

Every model call is recorded. No live calls.
"""

from __future__ import annotations

import ast
import asyncio
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
        "agent_evidence", "agent_runs", "agent_updates", "agent_needs",
        "autonomy_grants", "autonomy_policies", "autonomy_denials", "memories",
        "ambient_wakes", "ambient_activity", "delivery_plans", "opportunities",
        "notification_preferences", "users",
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
    """Both reasoning modules bind the helper at import, so both are patched."""
    import agent.reasoning as agent_reasoning
    import delivery.reasoning as delivery_reasoning

    monkeypatch.setattr(agent_reasoning, "_ask_model", model)
    monkeypatch.setattr(delivery_reasoning, "_ask_model", model)


class Provider:
    """A notification channel that records instead of sending."""

    name = "test"

    def __init__(self):
        self.sent = []
        self.cancelled = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        return {"ok": True, "provider": self.name, "external_id": "test"}

    async def cancel(self, *, owner_id, plan_id):
        self.cancelled.append(plan_id)
        return {"ok": True}


def _provider(monkeypatch) -> Provider:
    from delivery import provider as provider_module

    channel = Provider()
    monkeypatch.setattr(provider_module, "get_provider", lambda: channel)
    return channel


async def _allow_push(allowed=True):
    import delivery.context as context_module

    async def _permission(_db, _uid, _now):
        return {"push": allowed}

    context_module._permission = _permission  # noqa: SLF001


def _delivery(mode="in_app", **over):
    answer = {
        "mode": mode,
        "timing": "now",
        "reason_to_interrupt": "Ha preparato tutto e serve solo una conferma.",
        "reason_to_open": "Ti mostro cosa ha già fatto e cosa manca.",
        "what_decided_the_mode": "registrato",
        "copy_intent": "dire cosa manca",
        "confidence": "reasonable",
        "sensitivity": "ordinary",
        "copy": {"title": "Manca solo una conferma", "body": "È tutto pronto."},
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
        "objective": "Avere il certificato prima dell'appuntamento di giovedì.",
        "desired_outcome": "Il certificato è in mano giovedì mattina.",
        "success_criteria": ["Il certificato è in mano."],
    }
    fields.update(over)
    return AutonomousGoal(**fields)


def _need(uid, goal, kind="needs_authority", **over):
    from agent.models import CommunicationNeed

    fields = {
        "owner_id": uid,
        "goal_id": goal.id,
        "kind": kind,
        "summary": "Ho preparato tutto: mi serve solo il tuo via libera.",
        "reason": "Senza la conferma non si va avanti.",
        "source_refs": ["journal:1"],
        "work_already_done": ["Ho guardato cosa risulta.", "Ho trovato gli orari."],
        "what_is_missing": "Serve il tuo via libera.",
    }
    fields.update(over)
    return CommunicationNeed(**fields)


# ---------------------------------------------------------------------------
# The bridge itself
# ---------------------------------------------------------------------------

def test_an_agent_need_reaches_delivery_without_inventing_an_opportunity(monkeypatch):
    """
    §1/§38/QA A: the whole point, and the shortcut it refuses.

    A need goes to the same judgement an opportunity goes to, as itself. No
    opportunity is created — which is checked in the data, because "we would
    never do that" is not a guarantee.
    """
    async def body():
        client, db = await _db()
        uid = f"b39_{uuid.uuid4().hex[:8]}"
        try:
            _provider(monkeypatch)
            await _allow_push(True)
            service = await _service(db)
            goal = _goal(uid)
            await service.repo.create_goal(goal)
            need = await service.needs.raise_need(_need(uid, goal, kind="useful_result"))

            _install(monkeypatch, FakeModel([_delivery("in_app")]))
            result = await service.needs.offer_to_delivery(uid, need)

            assert result is not None
            assert result.mode == "in_app"
            # Quiet: no intention to arrive anywhere.
            assert await db.delivery_plans.count_documents({"owner_id": uid}) == 0
            # And nothing was invented to make it possible.
            assert await db.opportunities.count_documents({"owner_id": uid}) == 0, (
                "è stata creata un'opportunity finta per passare da Delivery"
            )

            still = await service.needs.get(uid, need.id)
            assert still.is_open is True
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_plan_for_a_need_is_filed_under_the_need(monkeypatch):
    """
    §6/§8: source identity, not an opportunity id with the wrong thing in it.

    A plan about an agent need must not claim to be about an opportunity —
    the history, the fatigue counting and the suppression all read that field.
    """
    async def body():
        client, db = await _db()
        uid = f"b39_{uuid.uuid4().hex[:8]}"
        try:
            _provider(monkeypatch)
            await _allow_push(True)
            service = await _service(db)
            goal = _goal(uid)
            await service.repo.create_goal(goal)
            need = await service.needs.raise_need(_need(uid, goal))

            _install(monkeypatch, FakeModel([_delivery("push", timing="at",
                                                       not_before=None)]))
            result = await service.needs.offer_to_delivery(uid, need)

            assert result.mode == "push"
            plan = await db.delivery_plans.find_one({"owner_id": uid}, {"_id": 0})
            assert plan is not None
            assert plan["source_type"] == "agent_need"
            assert plan["source_id"] == need.id
            assert plan["opportunity_id"] == "", (
                "un piano per un bisogno si è dichiarato di un'opportunity"
            )
            # And a tap lands on the blocker, with both handles.
            assert f"needId={need.id}" in plan["deep_link"]
            assert f"goalId={goal.id}" in plan["deep_link"]
            assert "entry=agent_need" in plan["deep_link"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_delivery_staying_silent_does_not_resolve_the_need(monkeypatch):
    """
    §12/§13/§28/QA D: no push is not need resolved.

    This is the failure that would be invisible: a need quietly closed
    because delivery declined to interrupt, an agent still blocked, and
    nobody ever finding out. `requires_attention` gets silence here, and the
    need is still open afterwards.
    """
    async def body():
        client, db = await _db()
        uid = f"b39_{uuid.uuid4().hex[:8]}"
        try:
            _provider(monkeypatch)
            await _allow_push(True)
            service = await _service(db)
            goal = _goal(uid, status="waiting", requires_user_authority=True)
            await service.repo.create_goal(goal)
            need = await service.needs.raise_need(
                _need(uid, goal, visibility="requires_attention")
            )

            _install(monkeypatch, FakeModel([_delivery("silence")]))
            result = await service.needs.offer_to_delivery(uid, need)

            assert result.mode == "silence"
            assert await db.delivery_plans.count_documents({"owner_id": uid}) == 0

            still = await service.needs.get(uid, need.id)
            assert still.is_open is True, "il silenzio ha chiuso il bisogno"
            assert still.requires_response is True
            assert still.status == "open"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_held_plan_is_not_a_settled_need(monkeypatch):
    """§15: a DeliveryPlan is an attempt to say something. The need is the thing."""
    async def body():
        client, db = await _db()
        uid = f"b39_{uuid.uuid4().hex[:8]}"
        try:
            _provider(monkeypatch)
            # Push not permitted: the judgement stands, the channel does not.
            await _allow_push(False)
            service = await _service(db)
            goal = _goal(uid, status="waiting", requires_user_authority=True)
            await service.repo.create_goal(goal)
            need = await service.needs.raise_need(_need(uid, goal))

            _install(monkeypatch, FakeModel([_delivery("push")]))
            result = await service.needs.offer_to_delivery(uid, need)

            assert result.blocked_by == "no_notification_permission"
            assert (await service.needs.get(uid, need.id)).is_open is True
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# A message is not the work
# ---------------------------------------------------------------------------

def test_opening_a_notification_is_neither_an_answer_nor_consent(monkeypatch):
    """
    §33/§34/QA K: the two things a tap is not.

    Somebody may open a notification on a bus and put the phone away. Treating
    that as an answer loses the question; treating it as consent executes
    something nobody agreed to.
    """
    async def body():
        client, db = await _db()
        uid = f"b39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import AuthorityService
            from delivery.service import DeliveryService

            _provider(monkeypatch)
            await _allow_push(True)
            service = await _service(db)
            goal = _goal(uid, status="waiting", requires_user_authority=True)
            await service.repo.create_goal(goal)
            need = await service.needs.raise_need(_need(uid, goal))

            _install(monkeypatch, FakeModel([_delivery("push")]))
            await service.needs.offer_to_delivery(uid, need)
            plan = await db.delivery_plans.find_one({"owner_id": uid}, {"_id": 0})
            assert plan is not None

            outcome = await DeliveryService(db).record_outcome(uid, plan["id"], "opened")
            assert outcome["ok"] is True

            still = await service.needs.get(uid, need.id)
            assert still.is_open is True, "aprire una notifica ha risposto per la persona"

            # No authority was granted, and nothing was executed.
            assert await AuthorityService(db).has_grant(uid, "navigation.open") is False
            assert await db.autonomy_grants.count_documents({"owner_id": uid}) == 0
            assert await db.agent_action_attempts.count_documents(
                {"owner_id": uid, "status": {"$in": ["executed", "verified"]}}
            ) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_delivering_a_push_does_not_move_the_work(monkeypatch):
    """§35/QA L: delivery is communication. The goal is where it was."""
    async def body():
        client, db = await _db()
        uid = f"b39_{uuid.uuid4().hex[:8]}"
        try:
            channel = _provider(monkeypatch)
            await _allow_push(True)
            service = await _service(db)
            goal = _goal(uid, status="waiting", requires_user_authority=True)
            await service.repo.create_goal(goal)
            need = await service.needs.raise_need(_need(uid, goal))

            _install(monkeypatch, FakeModel([_delivery("push")]))
            await service.needs.offer_to_delivery(uid, need)
            assert channel.sent, "la push non è partita, il test non prova niente"

            after = await service.repo.get_goal(uid, goal.id)
            assert after.status == goal.status
            assert after.requires_user_authority is True
            assert (await service.needs.get(uid, need.id)).is_open is True
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Answering
# ---------------------------------------------------------------------------

def test_an_answer_settles_the_need_and_the_same_goal_carries_on(monkeypatch):
    """§19/QA B: response resolves the need, and no new goal is born."""
    async def body():
        client, db = await _db()
        uid = f"b39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.models import ActionPlan, ActionStep

            service = await _service(db)
            goal = _goal(uid, status="waiting", requires_user_input=True)
            await service.repo.create_goal(goal)
            asked = ActionStep(ordinal=0, intent="Sapere quale indirizzo.",
                               step_type="ask_user", asks="Quale indirizzo?",
                               ask_kind="knowledge", status="blocked")
            plan = ActionPlan(goal_id=goal.id, owner_id=uid, status="waiting",
                              steps=[asked])
            await service.repo.save_plan(plan)
            before = plan.id
            need = await service.needs.raise_need(
                _need(uid, goal, kind="needs_information",
                      summary="Mi manca solo l'indirizzo.",
                      what_is_missing="Quale indirizzo indicare.")
            )

            _install(monkeypatch, FakeModel(
                [{"outcome": "uncertain", "reasoning": "reg."}],
                default={"outcome": "silent", "headline": "", "about": "niente"},
            ))
            await service.answer(uid, goal.id, reply="Quello di via Roma.")

            settled = await service.needs.get(uid, need.id)
            assert settled.status == "satisfied"
            assert settled.provenance == "user"

            assert await db.agent_goals.count_documents({"owner_id": uid}) == 1
            resumed = await service.repo.plan_for(uid, goal.id)
            assert resumed.id == before
            assert resumed.steps[0].status == "succeeded"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_approving_settles_the_need_and_resumes_the_same_intent(monkeypatch):
    """
    §20/QA C: authority approval is not a new plan.

    The `ActionIntent` prepared before the question was asked is the one that
    goes through — recognised by its idempotency key, which is built from what
    the effect is and not from when it was tried.
    """
    async def body():
        client, db = await _db()
        uid = f"b39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.models import ActionPlan, ActionStep

            service = await _service(db)
            goal = _goal(uid, status="waiting", requires_user_authority=True)
            await service.repo.create_goal(goal)
            blocked = ActionStep(ordinal=0, intent="Aprire la mappa.",
                                 step_type="execute",
                                 capability_needed="navigation.open",
                                 external_effect=True, status="blocked")
            plan = ActionPlan(goal_id=goal.id, owner_id=uid, status="waiting",
                              steps=[blocked])
            await service.repo.save_plan(plan)
            need = await service.needs.raise_need(_need(uid, goal))

            # The intent as it was prepared before anybody was asked.
            await service.executor.run(
                uid, goal, blocked, may_touch_the_world=False
            )
            prepared = await db.agent_action_attempts.find_one(
                {"owner_id": uid}, {"_id": 0}
            )
            assert prepared["status"] == "prepared"

            _install(monkeypatch, FakeModel(
                [
                    {"outcome": "proceed_autonomously", "reasoning": "reg.",
                     "reversibility": "easily"},
                    {"outcome": "uncertain", "reasoning": "reg."},
                ],
                default={"outcome": "silent", "headline": "", "about": "niente"},
            ))
            await service.authorise(uid, goal.id)

            settled = await service.needs.get(uid, need.id)
            assert settled.status == "satisfied"

            # One intent, the same one, now carried out.
            assert await db.agent_action_attempts.count_documents(
                {"owner_id": uid}
            ) == 1, "l'approvazione ha creato un secondo ActionIntent"
            after = await db.agent_action_attempts.find_one({"owner_id": uid}, {"_id": 0})
            assert after["id"] == prepared["id"]
            assert after["idempotency_key"] == prepared["idempotency_key"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_refusing_settles_the_need_and_executes_nothing(monkeypatch):
    """§21: a no is an answer. It closes the need and runs nothing."""
    async def body():
        client, db = await _db()
        uid = f"b39_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import AuthorityService
            from agent.models import ActionPlan, ActionStep

            service = await _service(db)
            goal = _goal(uid, status="waiting", requires_user_authority=True)
            await service.repo.create_goal(goal)
            await service.repo.save_plan(ActionPlan(
                goal_id=goal.id, owner_id=uid, status="waiting",
                steps=[ActionStep(ordinal=0, intent="Aprire la mappa.",
                                  step_type="execute",
                                  capability_needed="navigation.open",
                                  external_effect=True, status="blocked")],
            ))
            need = await service.needs.raise_need(_need(uid, goal))

            _install(monkeypatch, FakeModel(
                [{"decision": "abandon", "reasoning": "reg."}],
                default={"outcome": "silent", "headline": "", "about": "niente"},
            ))
            await service.deny(uid, goal.id, reason="la apro io")

            settled = await service.needs.get(uid, need.id)
            assert settled.status == "satisfied"
            assert await db.agent_action_attempts.count_documents(
                {"owner_id": uid, "status": {"$in": ["executed", "verified"]}}
            ) == 0
            assert await AuthorityService(db).is_denied(uid, "navigation.open") is True
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Saying it once, and stopping when it stops mattering
# ---------------------------------------------------------------------------

def test_the_same_blocker_raises_one_need(monkeypatch):
    """
    §24/QA E: «mi serve il comune» four times is the failure.

    Keyed on what is blocked, not on the wording — the same question asked
    four times is phrased four ways.
    """
    async def body():
        client, db = await _db()
        uid = f"b39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            goal = _goal(uid)
            await service.repo.create_goal(goal)

            ids = set()
            for wording in (
                "Mi serve sapere il comune.",
                "Qual è il tuo comune?",
                "Mi manca il comune di residenza.",
                "Per andare avanti mi serve il comune.",
            ):
                raised = await service.needs.raise_need(_need(
                    uid, goal, kind="needs_information", summary=wording,
                    what_is_missing="il comune di residenza",
                ))
                ids.add(raised.id)

            assert len(ids) == 1, f"{len(ids)} bisogni per lo stesso blocco"
            assert await db.agent_needs.count_documents(
                {"owner_id": uid, "status": "open"}
            ) == 1
            # The wording that is kept is the newest one.
            kept = await service.needs.get(uid, ids.pop())
            assert kept.summary == "Per andare avanti mi serve il comune."
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_two_workers_raise_one_need():
    """§47/QA J: the index decides, not a check that races."""
    async def body():
        client, db = await _db()
        uid = f"b39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            goal = _goal(uid)
            await service.repo.create_goal(goal)

            raised = await asyncio.gather(*[
                service.needs.raise_need(_need(
                    uid, goal, kind="needs_information",
                    summary=f"Serve il comune ({n}).",
                    what_is_missing="il comune di residenza",
                ))
                for n in range(5)
            ])
            assert len({r.id for r in raised}) == 1, "cinque worker, cinque bisogni"
            assert await db.agent_needs.count_documents(
                {"owner_id": uid, "status": "open"}
            ) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_cancelling_a_goal_takes_the_need_and_the_plan_with_it(monkeypatch):
    """§22/QA G: nobody has to answer a question about something abandoned."""
    async def body():
        client, db = await _db()
        uid = f"b39_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.repository import AmbientRepository

            _provider(monkeypatch)
            await _allow_push(True)
            await AmbientRepository(db).ensure_indexes()
            service = await _service(db)
            goal = _goal(uid, status="waiting", requires_user_authority=True)
            await service.repo.create_goal(goal)
            need = await service.needs.raise_need(_need(uid, goal))

            _install(monkeypatch, FakeModel([_delivery("push")]))
            await service.needs.offer_to_delivery(uid, need)
            assert await db.delivery_plans.count_documents({"owner_id": uid}) == 1

            await service.cancel(uid, goal.id, reason="lascia perdere")

            settled = await service.needs.get(uid, need.id)
            assert settled.status == "cancelled"
            assert settled.status != "satisfied", "un abbandono si è finto una risposta"
            assert await db.delivery_plans.count_documents(
                {"owner_id": uid, "status": {"$in": ["pending", "held"]}}
            ) == 0
            assert await AmbientRepository(db).open_wakes(uid) == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_finished_goal_drops_the_question_and_keeps_the_report(monkeypatch):
    """
    §23: two kinds of need, settled differently.

    A goal that ended has no use for the question it was going to ask. What it
    already told somebody is history and stays.
    """
    async def body():
        client, db = await _db()
        uid = f"b39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            goal = _goal(uid)
            await service.repo.create_goal(goal)
            asking = await service.needs.raise_need(_need(
                uid, goal, kind="needs_information", summary="Serve l'indirizzo.",
                what_is_missing="l'indirizzo",
            ))
            told = await service.needs.raise_need(_need(
                uid, goal, kind="useful_result", summary="Ho trovato gli orari.",
                what_is_missing="",
            ))

            await service.needs.close_for_goal(
                uid, goal.id, why="l'obiettivo si è chiuso",
                kinds={"needs_information", "needs_authority"},
            )

            assert (await service.needs.get(uid, asking.id)).status == "cancelled"
            assert (await service.needs.get(uid, told.id)).status == "open"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_being_told_not_to_interrupt_does_not_delete_the_need(monkeypatch):
    """
    §27/§45/QA H: suppression silences the channel, not the work.

    "Non avvisarmi per questa cosa" is about interruption. ORA is still
    blocked, and a person who opens the app should still find out.
    """
    async def body():
        client, db = await _db()
        uid = f"b39_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.preferences import PreferenceService

            _provider(monkeypatch)
            await _allow_push(True)
            service = await _service(db)
            goal = _goal(uid, status="waiting", requires_user_authority=True)
            await service.repo.create_goal(goal)
            need = await service.needs.raise_need(_need(uid, goal))

            await PreferenceService(db).suppress(uid, need.id)

            model = FakeModel([_delivery("push")])
            _install(monkeypatch, model)
            result = await service.needs.offer_to_delivery(uid, need)

            assert result.blocked_by == "muted_by_user"
            assert model.seen == [], "ha pagato un giudizio già deciso"
            assert await db.delivery_plans.count_documents(
                {"owner_id": uid, "status": {"$in": ["pending", "held"]}}
            ) == 0

            still = await service.needs.get(uid, need.id)
            assert still.is_open is True, "il silenzio richiesto ha cancellato il bisogno"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# The old path
# ---------------------------------------------------------------------------

def test_the_opportunity_path_is_exactly_what_it_was(monkeypatch):
    """
    §7/§46/QA I: V3.7 → V3.8 unchanged.

    The bridge generalised a shape; it must not have moved anything the
    existing path stands on.
    """
    async def body():
        client, db = await _db()
        uid = f"b39_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService
            from opportunities.models import EvidenceRef, Opportunity
            from opportunities.repository import OpportunityRepository

            _provider(monkeypatch)
            await _allow_push(True)
            opportunity = Opportunity(
                owner_id=uid, identity_key=f"k-{uuid.uuid4().hex[:6]}",
                status="active",
                semantic_summary="Manca il certificato per domani.",
                why_it_matters="Senza, l'appuntamento non si conclude.",
                why_now="L'ufficio apre solo la mattina.",
                relevance="high", urgency="soon", confidence="strong",
                evidence=[EvidenceRef(kind="calendar_event", ref="evt_x")],
            )
            await OpportunityRepository(db).save(opportunity)

            _install(monkeypatch, FakeModel([_delivery("push")]))
            result = await DeliveryService(db).evaluate(uid, opportunity.id)

            assert result.mode == "push"
            plan = await db.delivery_plans.find_one({"owner_id": uid}, {"_id": 0})
            assert plan["opportunity_id"] == opportunity.id, (
                "il campo su cui poggia tutto V3.8 non è più popolato"
            )
            assert plan["source_type"] == "opportunity"
            assert plan["source_id"] == opportunity.id
            assert f"opportunityId={opportunity.id}" in plan["deep_link"]
            assert "entry=notification" in plan["deep_link"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_plan_written_before_the_bridge_is_still_found():
    """
    §8: the compatibility seam, tested rather than asserted in a comment.

    Rows written by V3.8 carry `opportunity_id` and no `source_id`. They are
    still the plan for that opportunity.
    """
    async def body():
        client, db = await _db()
        uid = f"b39_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.repository import DeliveryRepository

            await db.delivery_plans.insert_one({
                "id": "pln_legacy", "owner_id": uid, "opportunity_id": "opp_old",
                "mode": "push", "status": "pending", "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00", "words": {},
            })
            repo = DeliveryRepository(db)
            found = await repo.open_plan_for(uid, "opp_old")
            assert found is not None, "un piano scritto prima del ponte è sparito"
            assert found.source_id == "opp_old"
            assert found.source_type == "opportunity"
            assert len(await repo.plans_for(uid, "opp_old")) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def _code_only(source: str) -> str:
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


def test_the_agent_cannot_create_an_opportunity():
    """
    §1: the shortcut, refused structurally.

    Raising a fake concern so the existing path would carry it is three lines
    and a lie. Walked rather than grepped, so a comment promising not to is
    not mistaken for not doing it.
    """
    for module in ("needs.py", "service.py", "visibility.py"):
        code = _code_only(HERE.joinpath("agent", module).read_text(encoding="utf-8"))
        for shortcut in ("Opportunity(", "OpportunityRepository", "opportunities.models",
                         "identity_key", "raise_opportunity"):
            assert shortcut not in code, f"{module} inventa un'opportunity: {shortcut}"

        for write in ("insert_one", "update_one", "update_many"):
            assert f"opportunities.{write}" not in code, (
                f"{module} scrive nelle opportunity"
            )


def test_nothing_in_the_agent_chooses_a_channel():
    """
    §5/§11: visibility enables a judgement. It does not make one.

    `if requires_attention: push()` is the line this test exists to fail on,
    and so are its quieter relatives.
    """
    for module in ("needs.py", "service.py", "visibility.py"):
        code = _code_only(HERE.joinpath("agent", module).read_text(encoding="utf-8"))
        for channel in ("push", "quiet_presence", "in_app", "DeliveryPlan",
                        "DeliveryDecision", "deliver_due", "PushCopy", "send("):
            assert channel not in code, f"{module} sceglie un canale: {channel}"

    # And no branch on a visibility or a need kind produces a delivery mode.
    tree = ast.parse(_code_only(
        HERE.joinpath("agent", "needs.py").read_text(encoding="utf-8")
    ))
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            assert "mode" not in ast.unparse(node.body), (
                f"needs.py:{node.lineno} decide una modalità di consegna"
            )


def test_delivery_remains_the_only_engine():
    """§11/§51: one judgement about interrupting, in one place."""
    agent_code = "\n".join(
        _code_only(HERE.joinpath("agent", m).read_text(encoding="utf-8"))
        for m in ("needs.py", "service.py", "visibility.py")
    )
    for engine in ("decide_delivery", "agent_delivery_decision", "agent_push_decision",
                   "delivery.reasoning"):
        assert engine not in agent_code, f"l'agente ha un suo motore di consegna: {engine}"

    # The bridge asks, and does not read the answer to decide anything.
    tree = ast.parse(_code_only(
        HERE.joinpath("agent", "needs.py").read_text(encoding="utf-8")
    ))
    offer = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "offer_to_delivery"
    )
    body = ast.unparse(offer)
    for reading in ("result.mode", "verdict.mode", ".mode ==", "blocked_by"):
        assert reading not in body, f"il ponte guarda cosa ha deciso Delivery: {reading}"


def test_only_a_person_or_the_agent_can_settle_a_need():
    """
    §14/§33: not a delivery event.

    The lifecycle is about the work. If `satisfy` were ever reachable from
    delivery, a notification nobody read would close a question nobody
    answered.
    """
    delivery_code = "\n".join(
        _code_only(HERE.joinpath("delivery", m).read_text(encoding="utf-8"))
        for m in ("service.py", "repository.py", "context.py")
    )
    for reach in ("NeedService", "agent_needs", "satisfy(", "CommunicationNeed"):
        assert reach not in delivery_code, f"Delivery tocca il bisogno: {reach}"

    code = _code_only(HERE.joinpath("agent", "needs.py").read_text(encoding="utf-8"))
    settle = code.split("async def _settle")[1].split("async def")[0]
    for event in ("opened", "delivered", "outcome", "record_outcome"):
        assert event not in settle, f"un evento di consegna chiude un bisogno: {event}"


def test_a_need_shows_a_sentence_and_no_workflow():
    """§29: what a person may see."""
    from agent.models import CommunicationNeed

    need = CommunicationNeed(
        owner_id="u", goal_id="gol_1", kind="needs_authority",
        summary="È tutto pronto, mi serve solo il tuo via libera.",
        requires_response=True, source_refs=["evd_1"], fingerprint="abc",
    )
    shown = need.for_human()
    assert set(shown) == {"says", "needs_you"}
    for leak in ("kind", "status", "goal_id", "fingerprint", "source_refs",
                 "capability", "step", "authority_requirement", "provenance"):
        assert leak not in shown


def test_everything_about_one_need_belongs_to_one_person():
    """§36: owner boundary, fail closed."""
    async def body():
        client, db = await _db()
        mine = f"b39_{uuid.uuid4().hex[:8]}"
        yours = f"b39_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            goal = _goal(mine)
            await service.repo.create_goal(goal)
            need = await service.needs.raise_need(_need(mine, goal))

            assert await service.needs.get(yours, need.id) is None
            assert await service.needs.open_for_goal(yours, goal.id) == []
            # And settling somebody else's need does nothing.
            assert await service.needs.satisfy(yours, need.id, how="x") is None
            assert (await service.needs.get(mine, need.id)).is_open is True
        finally:
            await _clean(db, mine)
            await _clean(db, yours)
            client.close()

    _run(body())
