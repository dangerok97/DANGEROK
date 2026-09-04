"""
V3.9 final gate — a standing permission, and an agent that uses it.

    A PERSISTENT GRANT MUST BE EXPLICIT.
    AGENT-INITIATED ACTIONS MAY EXECUTE WITHOUT A NEW QUESTION
    ONLY WHEN A VALID GRANT ALREADY EXISTS.
    EXECUTED != VERIFIED.

Three things are being closed here and they pull in opposite directions,
which is why they are tested together.

**A permission somebody can give.** Until now the engine could hold a standing
grant and nobody could create one, so «puoi farlo anche in futuro» was a
capability with no door. The door exists now, and every test below is about
it not being wider than the sentence next to it: scoped to the effect that was
approved, offered only for effects small enough to decide in two seconds,
never produced by approving twice.

**A permission somebody can take back.** Revocation is forwards only, it is
rechecked where the effect happens rather than where it was planned, and the
next goal asks again.

**An agent that uses it without asking.** The whole point: a goal ORA started
by itself, a grant that already existed, a real write, a read-back, and a
verdict that could still have said no. If any of the safeguards had to be
loosened to make that happen, the wrong thing was built.

No live model calls. The calendar is the connector's own fake, driven through
the real executor, the real authority layer and the real effect.
"""

from __future__ import annotations

import ast
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
CALENDAR = "cal_gate@example.com"


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
        "agent_receipts", "autonomy_grants", "autonomy_policies",
        "autonomy_denials", "autonomy_consents", "connector_instances",
        "memories", "ambient_activity", "ambient_wakes", "delivery_plans",
        "permission_consents", "permission_audit",
    ):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


class Calendar:
    """The connector's own fake, behind the real service shape."""

    def __init__(self):
        from connectors.google_calendar.provider import FakeGoogleCalendarProvider

        self.provider = FakeGoogleCalendarProvider()
        self.provider.seed_calendar(calendar_id=CALENDAR, summary="QA", primary=True)
        self.writes = 0
        self.reads = 0
        create, get = self.provider.create_event, self.provider.get_event

        async def counted_create(**kw):
            self.writes += 1
            return await create(**kw)

        async def counted_get(**kw):
            self.reads += 1
            return await get(**kw)

        self.provider.create_event = counted_create
        self.provider.get_event = counted_get

    async def _get_access_token(self, *, user_id, instance):
        return "fake-access"

    async def list_calendars_for_instance(self, *, user_id, instance_id):
        return [{"id": CALENDAR, "primary": True}]

    @property
    def events(self):
        return self.provider.events.get(CALENDAR, {})


def _calendar(monkeypatch) -> Calendar:
    import agent.effects as effects

    channel = Calendar()
    monkeypatch.setattr(effects, "_calendar_service", lambda db: channel)
    return channel


# Which question is being asked, read off the instruction the reasoning sends.
# Keyed on the question rather than on the order the calls happen to arrive in:
# a recorded judgement belongs to the thing it judged, and a queue that depends
# on call order breaks the moment a plan has one more step than the last one.
_ASKS = {
    "say what kind of act": "authority",
    "whether the outcome is actually": "verification",
    "what is worth doing next": "next_action",
    "worth them knowing": "visibility",
    "what to do with the rest of the plan": "reconsider",
    "outcome worth bringing about": "goal",
    "how to reach this outcome": "plan",
}


class Recorded:
    """Judgements that were made, replayed. Never a live call in this suite."""

    def __init__(self, by_question=None, default=None):
        self.by_question = dict(by_question or {})
        self.default = default
        self.asked = {}

    async def __call__(self, system, user):
        head = " ".join(str(system or "").split()).lower()
        kind = next(
            (name for phrase, name in _ASKS.items() if phrase in head), "unknown"
        )
        self.asked[kind] = self.asked.get(kind, 0) + 1
        answer = self.by_question.get(kind, self.default)
        return dict(answer) if isinstance(answer, dict) else answer


def _install(monkeypatch, agent_model, delivery_model=None):
    import agent.reasoning as reasoning
    import delivery.reasoning as delivery

    monkeypatch.setattr(reasoning, "_ask_model", agent_model)
    monkeypatch.setattr(delivery, "_ask_model", delivery_model or agent_model)


async def _connect(db, uid):
    await db.connector_instances.insert_one({
        "id": f"inst_{uuid.uuid4().hex[:8]}", "user_id": uid,
        "connector_id": "calendar_google", "status": "connected",
        "metadata": {"default_calendar_id": CALENDAR},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    from agent.capabilities import _CONNECTOR
    from permissions.service import PermissionService

    try:
        await PermissionService(db).grant(
            user_id=uid, capability_id="calendar.write",
            connector_id=_CONNECTOR["calendar.write"],
            purpose_id="calendar_write_sync",
        )
    except Exception:
        pass


async def _service(db):
    from agent.service import AgentService

    service = AgentService(db)
    await service.ensure_indexes()
    return service


def _when(days=2, hour=8):
    moment = datetime.now(timezone.utc) + timedelta(days=days)
    return moment.replace(hour=hour, minute=30, second=0, microsecond=0).isoformat()


def _goal(uid, **over):
    from agent.models import AutonomousGoal

    fields = {
        "owner_id": uid,
        "status": "active",
        "origin": "agent_initiated",
        "objective": "Avere il ritiro del certificato in agenda per giovedì.",
        "desired_outcome": "Il ritiro è segnato in calendario giovedì mattina.",
        "why_now": "L'ufficio anagrafe apre solo la mattina.",
        "success_criteria": ["Il ritiro risulta in calendario."],
    }
    fields.update(over)
    return AutonomousGoal(**fields)


async def _plan(service, goal, uid, *, blocked=False):
    """
    Look first, then act — which is what the loop actually does.

    The reading step is not decoration. Until something has been found out
    there is nothing for a judgement to be about, so the loop takes the first
    step deterministically and spends no thinking on it; the choice of what to
    do *next* is the one worth a judgement. A one-step plan would test a
    shape the agent never has.
    """
    from agent.models import ActionPlan, ActionStep

    look = ActionStep(
        ordinal=0,
        intent="Guardare cosa risulta già per giovedì.",
        step_type="inspect", capability_needed="information.read",
        expected_result="Com'è messa la mattina.",
    )
    write = ActionStep(
        ordinal=1,
        intent="Segnare il ritiro del certificato giovedì alle 8:30.",
        step_type="execute", capability_needed="calendar.write",
        external_effect=True, effect_type="create",
        effect_target="il tuo calendario", reaches_somebody_else=False,
        expected_result="Il ritiro risulta in calendario.",
        parameters={"title": "Ritiro certificato", "starts_at": _when()},
    )
    if blocked:
        look.status = "succeeded"
        write.status = "blocked"
    plan = ActionPlan(
        goal_id=goal.id, owner_id=uid, status="active",
        plan_summary="Guardare, poi segnare il ritiro.", steps=[look, write],
    )
    await service.repo.save_plan(plan)
    return plan


def _judgements(**over):
    """
    The recorded run of an autonomous write, by question rather than by turn.

    Each answer is attached to the question it answered, so the same fixture
    works whether the loop asks three times or five — and a test that stops
    passing stops for a reason about the agent rather than about arithmetic.
    """
    answers = {
        "next_action": {"decision": "execute", "reasoning": "reg.", "step_id": ""},
        "authority": {"outcome": "proceed_autonomously", "reasoning": "reg.",
                      "reversibility": "easily"},
        "verification": {"outcome": "achieved",
                         "reasoning": "reg.: risulta in calendario."},
        "visibility": {"outcome": "inform_user",
                       "headline": "Fatto: il ritiro è in calendario giovedì "
                                   "alle 8:30.",
                       "about": "ritiro in calendario", "reasoning": "reg."},
    }
    answers.update(over)
    return answers


def _delivery(mode="in_app"):
    return {"mode": mode, "timing": "now", "reason_to_interrupt": "reg.",
            "reason_to_open": "reg.", "what_decided_the_mode": "reg.",
            "copy_intent": "reg.", "confidence": "reasonable",
            "sensitivity": "ordinary",
            "copy": {"title": "Fatto", "body": "È in calendario."}}


# ---------------------------------------------------------------------------
# A — a permission somebody can give
# ---------------------------------------------------------------------------

def test_a_plain_yes_creates_no_standing_permission(monkeypatch):
    """
    §3: «Vai pure» approves this act. Nothing else.

        ONE-TIME APPROVAL IS NOT A STANDING PERMISSION.

    The failure this prevents is the one a hurried implementation makes for
    free: wiring the new control to the same call and letting a flag default
    the wrong way. Approving here must leave the person exactly as un-committed
    as before.
    """
    async def body():
        client, db = await _db()
        uid = f"gate_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            await _connect(db, uid)
            channel = _calendar(monkeypatch)
            goal = _goal(uid, status="waiting", requires_user_authority=True)
            await service.repo.create_goal(goal)
            await _plan(service, goal, uid, blocked=True)

            _install(monkeypatch, Recorded(_judgements()), Recorded(default=_delivery()))
            await service.authorise(uid, goal.id)

            assert await db.autonomy_grants.count_documents(
                {"owner_id": uid, "active": True}
            ) == 0, "un sì per questa volta è diventato un permesso"
            assert await db.autonomy_consents.count_documents({"owner_id": uid}) == 1
            assert channel.writes == 1, "e l'atto approvato deve comunque avvenire"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_allowing_it_for_the_future_creates_one_scoped_permission(monkeypatch):
    """
    §9: the control that says so, and what it produces.

    One grant, scoped to the effect that was on the screen: the kind of change
    approved, and every flag that was false still false. Not one grant per
    press either — the same choice made twice is one permission.
    """
    async def body():
        client, db = await _db()
        uid = f"gate_{uuid.uuid4().hex[:8]}"
        try:
            from agent.models import AutonomyGrant

            service = await _service(db)
            await _connect(db, uid)
            _calendar(monkeypatch)
            goal = _goal(uid, status="waiting", requires_user_authority=True)
            await service.repo.create_goal(goal)
            await _plan(service, goal, uid, blocked=True)

            _install(monkeypatch, Recorded(_judgements()), Recorded(default=_delivery()))
            out = await service.authorise(uid, goal.id, persistent=True)
            assert out.get("ok")

            docs = await db.autonomy_grants.find(
                {"owner_id": uid, "active": True}, {"_id": 0}
            ).to_list(5)
            assert len(docs) == 1, f"{len(docs)} permessi per una scelta"
            grant = AutonomyGrant.model_validate(docs[0])
            assert grant.granted_by == "user"
            assert grant.effect_scope == ["create"], "più largo di quello approvato"
            assert grant.allows_external_party is False
            assert grant.allows_financial is False
            assert grant.allows_public is False
            assert grant.allows_destructive is False
            assert grant.human_summary, "un permesso senza una frase da leggere"
            assert "calendario" in grant.human_summary.lower()
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_offer_says_what_it_would_allow(monkeypatch):
    """
    §4: the sentence next to the control, and what it must never contain.

    A permission somebody grants without having read it is one they did not
    grant. So the offer is a promise in their own language — and there is
    nowhere in it for a capability name, a scope, an id or a level, because
    the surface is never given one.
    """
    async def body():
        client, db = await _db()
        uid = f"gate_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            await _connect(db, uid)
            goal = _goal(uid, status="waiting", requires_user_authority=True)
            await service.repo.create_goal(goal)
            await _plan(service, goal, uid, blocked=True)

            says = await service.standing_offer(uid, goal.id)
            assert says, "niente da leggere accanto al bottone"
            assert "calendario" in says.lower()
            assert "senza chiedertelo ogni volta" in says
            assert "senza coinvolgere altre persone" in says
            for forbidden in (
                "calendar.write", "effect_scope", "grant", "capability",
                "authority", "{", "}", "_",
            ):
                assert forbidden not in says, f"la frase mostra «{forbidden}»"
            # And nothing that reads as everything.
            for unbounded in ("tutto", "qualsiasi", "sempre tutto", "illimitat"):
                assert unbounded not in says.lower(), "sembra un permesso globale"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_nothing_big_is_ever_offered_for_the_future(monkeypatch):
    """
    §6: what the control must refuse to appear for.

        NO GLOBAL AUTONOMY.

    «Puoi farlo anche in futuro» is a decision somebody makes in two seconds.
    It must therefore be impossible to make it about something that deserves
    longer — anything reaching a third party, costing money, committing them,
    public, or destructive. The engine can still scope a grant for those; the
    two-second control cannot reach them.
    """
    async def body():
        client, db = await _db()
        uid = f"gate_{uuid.uuid4().hex[:8]}"
        try:
            from agent.models import ActionPlan, ActionStep

            service = await _service(db)
            await _connect(db, uid)

            for kind, over in (
                ("un invitato", {"reaches_somebody_else": True}),
                ("una cancellazione", {"effect_type": "cancel"}),
            ):
                goal = _goal(uid, status="waiting", requires_user_authority=True)
                await service.repo.create_goal(goal)
                step = ActionStep(
                    ordinal=0, intent="Fare la cosa.", step_type="execute",
                    capability_needed="calendar.write", external_effect=True,
                    effect_target="il tuo calendario", status="blocked",
                    expected_result="Fatta.",
                    parameters={"title": "X", "starts_at": _when()},
                    **{"effect_type": "create", **over},
                )
                await service.repo.save_plan(ActionPlan(
                    goal_id=goal.id, owner_id=uid, status="active",
                    plan_summary="p", steps=[step],
                ))
                assert await service.standing_offer(uid, goal.id) is None, (
                    f"offre un permesso permanente per {kind}"
                )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_nothing_is_offered_twice(monkeypatch):
    """
    §9: one grant, not a duplicate.

    Somebody who has already allowed this is not asked to allow it again —
    being asked to decide something you decided reads as the system having
    forgotten you.
    """
    async def body():
        client, db = await _db()
        uid = f"gate_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            await _connect(db, uid)
            goal = _goal(uid, status="waiting", requires_user_authority=True)
            await service.repo.create_goal(goal)
            await _plan(service, goal, uid, blocked=True)

            assert await service.standing_offer(uid, goal.id) is not None
            await service.authority.grant(
                uid, "calendar.write", by="user", effect_scope=["create"],
                human_summary="Il tuo calendario: posso aggiungere quello che serve.",
            )
            assert await service.standing_offer(uid, goal.id) is None
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_yes_given_once_cannot_authorise_a_second_goal(monkeypatch):
    """
    A defect trace B found, and nothing else would have.

        A ONE-TIME YES IS ONE TIME.

    Somebody approves ORA putting Thursday's pickup in the calendar. A second
    goal later wants to make an identical entry — same title, same time, same
    calendar — and the consent from the first one matched it, because consent
    is keyed on the act while the idempotency key is keyed on the goal and
    step. Same hash, different key: the guard that was supposed to make a
    spent consent harmless did not apply, and a real event was created that
    nobody had agreed to.

    Approving twice on one goal stays harmless for a different reason: by the
    second press the effect is already `executed` and the executor recognises
    it before authority is consulted.
    """
    async def body():
        client, db = await _db()
        uid = f"gate_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            await _connect(db, uid)
            channel = _calendar(monkeypatch)

            first = _goal(uid, status="waiting", requires_user_authority=True)
            await service.repo.create_goal(first)
            await _plan(service, first, uid, blocked=True)
            _install(monkeypatch, Recorded(_judgements()), Recorded(default=_delivery()))
            await service.authorise(uid, first.id)
            assert channel.writes == 1

            consents = await db.autonomy_consents.find(
                {"owner_id": uid}, {"_id": 0}
            ).to_list(5)
            assert len(consents) == 1
            assert consents[0]["used_at"], "il sì non è stato speso da ciò che ha permesso"

            # A second goal wanting the identical act. Nobody has said yes to
            # this one.
            second = _goal(uid, objective="Segnare di nuovo lo stesso ritiro.")
            await service.repo.create_goal(second)
            await _plan(service, second, uid)
            _install(monkeypatch, Recorded(_judgements()), Recorded(default=_delivery()))
            out = await service.advance(uid, second.id)

            assert channel.writes == 1, "un sì di ieri ha autorizzato l'atto di oggi"
            assert len(channel.events) == 1
            assert out.get("state") in ("awaiting_authority", "waiting_for_person")
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_yes_is_spent_even_when_the_permission_is_what_acted(monkeypatch):
    """
    The same defect, in the shape trace B actually found it.

    Somebody who chooses «puoi farlo anche in futuro» produces two things: a
    consent for this act, and a standing permission. The permission is checked
    first, so it is what the executor proceeds on — and the consent, never
    having been the deciding basis, stayed unspent. Revoke the permission a
    week later and that forgotten yes authorises the same act again, with
    nobody asked and nothing on screen.

    What is true regardless of which basis won: they said yes to this act, and
    the act happened.
    """
    async def body():
        client, db = await _db()
        uid = f"gate_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            await _connect(db, uid)
            channel = _calendar(monkeypatch)

            first = _goal(uid, status="waiting", requires_user_authority=True)
            await service.repo.create_goal(first)
            await _plan(service, first, uid, blocked=True)
            _install(monkeypatch, Recorded(_judgements()), Recorded(default=_delivery()))
            await service.authorise(uid, first.id, persistent=True)
            assert channel.writes == 1
            assert len(await service.authority.grants(uid)) == 1

            row = await db.autonomy_consents.find_one({"owner_id": uid}, {"_id": 0})
            assert row["used_at"], (
                "il sì è rimasto intero perché ad agire era stato il permesso"
            )

            # A week later they take the permission back. The forgotten yes
            # must not still be lying there.
            await service.authority.revoke(uid, "calendar.write")
            second = _goal(uid, objective="Segnare di nuovo lo stesso ritiro.")
            await service.repo.create_goal(second)
            await _plan(service, second, uid)
            _install(monkeypatch, Recorded(_judgements()), Recorded(default=_delivery()))
            out = await service.advance(uid, second.id)

            assert channel.writes == 1, "un sì dimenticato ha aperto la porta"
            assert out.get("state") in ("awaiting_authority", "waiting_for_person")
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_taking_it_back_makes_ora_ask_again(monkeypatch):
    """
    §10: revocation, and the shape of what it does.

    Forwards only. The write that already happened stands — undoing it is a
    different act nobody asked for — and the next goal of the same kind stops
    at the door.
    """
    async def body():
        client, db = await _db()
        uid = f"gate_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            await _connect(db, uid)
            channel = _calendar(monkeypatch)
            await service.authority.grant(
                uid, "calendar.write", by="user", effect_scope=["create"],
                human_summary="Il tuo calendario: posso aggiungere quello che serve.",
            )

            first = _goal(uid)
            await service.repo.create_goal(first)
            await _plan(service, first, uid)
            _install(monkeypatch, Recorded(_judgements()), Recorded(default=_delivery()))
            await service.advance(uid, first.id)
            assert channel.writes == 1, "col permesso doveva bastare"

            await service.authority.revoke(uid, "calendar.write")
            assert await service.authority.grants(uid) == []

            second = _goal(uid, objective="Segnare anche il ritiro di ottobre.")
            await service.repo.create_goal(second)
            await _plan(service, second, uid)
            _install(monkeypatch, Recorded(_judgements()), Recorded(default=_delivery()))
            out = await service.advance(uid, second.id)

            assert channel.writes == 1, "ha scritto con un permesso revocato"
            assert out.get("state") in ("awaiting_authority", "waiting_for_person")
            # And what already happened is still there.
            assert len(channel.events) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_revoking_stops_an_effect_already_on_its_way(monkeypatch):
    """
    §8: rechecked where it is used, not where it was decided.

    The seconds between deciding and doing are enough for somebody to change
    their mind, and an authority answer computed ten minutes ago is a claim
    about ten minutes ago.
    """
    async def body():
        client, db = await _db()
        uid = f"gate_{uuid.uuid4().hex[:8]}"
        try:
            from agent.models import AuthorityAssessment

            service = await _service(db)
            await _connect(db, uid)
            channel = _calendar(monkeypatch)
            await service.authority.grant(
                uid, "calendar.write", by="user", effect_scope=["create"],
                human_summary="Il tuo calendario: posso aggiungere quello che serve.",
            )
            goal = _goal(uid)
            await service.repo.create_goal(goal)
            plan = await _plan(service, goal, uid)
            step = plan.steps[1]

            assessment = AuthorityAssessment(
                capability="calendar.write", model_outcome="proceed_autonomously",
            )

            async def recheck(intent):
                # Between the plan reaching the step and the provider being
                # touched, they took the permission back.
                await service.authority.revoke(uid, "calendar.write")
                return await service.authority.effective_authority(
                    uid, intent, assessment
                )

            result = await service.executor.run(
                uid, goal, step, may_touch_the_world=True, recheck=recheck,
            )
            assert result.error_type == "authority_withdrawn", result.error_type
            assert channel.writes == 0, "ha scritto dopo la revoca"
            assert await service.executor.receipts_for(uid, goal.id) == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# C — an agent that uses it without asking
# ---------------------------------------------------------------------------

def test_an_agent_initiated_goal_acts_on_a_permission_it_already_had(monkeypatch):
    """
    §17–§22: the proof the whole phase was for.

        THE USER DOES NOT MANAGE THE AGENT. THE AGENT MANAGES THE WORK.

    Nobody typed anything. The permission existed before the goal did, the
    goal came from ORA, the write happened, the calendar was read back, and
    the outcome was verified against what the calendar said rather than
    against the fact that a request had been sent.

    Every assertion here is a different way the sentence «ORA lo ha fatto da
    sola» could be false: a hidden question, an authority that came from
    somewhere else, a receipt believed instead of a read-back, a completion
    that outran its evidence.
    """
    async def body():
        client, db = await _db()
        uid = f"gate_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            await _connect(db, uid)
            channel = _calendar(monkeypatch)

            # The permission exists BEFORE the goal. Not goal → ask → grant.
            await service.authority.grant(
                uid, "calendar.write", by="user", effect_scope=["create"],
                human_summary="Il tuo calendario: posso aggiungere quello che serve.",
            )

            goal = _goal(uid)
            assert goal.origin == "agent_initiated"
            await service.repo.create_goal(goal)
            await _plan(service, goal, uid)

            _install(monkeypatch, Recorded(_judgements()), Recorded(default=_delivery()))
            out = await service.advance(uid, goal.id)

            # Nothing was asked of anybody.
            assert out.get("state") not in (
                "awaiting_authority", "waiting_for_person",
            ), out.get("state")
            needs = await service.needs.open_for_goal(uid, goal.id)
            assert not [n for n in needs if n.response_kind], (
                "ha chiesto qualcosa pur avendo già il permesso"
            )

            # It happened, once, and somebody looked afterwards.
            assert channel.writes == 1 and channel.reads == 1
            receipts = await service.executor.receipts_for(uid, goal.id)
            assert len(receipts) == 1
            assert receipts[0]["provider_status"] == "succeeded"
            assert receipts[0]["external_ref"]
            # The receipt says who allowed it, not just that it went through.
            # A receipt outlives the attempt row it came from, and "the
            # provider accepted this" is worth much less without "and this is
            # what said it could".
            assert receipts[0]["authority_basis"] == "grant_matched", receipts[0]

            # On what basis: a permission, not an instruction and not a yes.
            intents = await db.agent_action_attempts.find(
                {"owner_id": uid}, {"_id": 0}
            ).to_list(5)
            assert len(intents) == 1
            assert intents[0]["authority_required"] == "grant_matched", intents[0]
            assert await db.autonomy_consents.count_documents({"owner_id": uid}) == 0, (
                "un goal autonomo non deve produrre consensi"
            )

            # What went into evidence came from the calendar.
            evidence = await service.evidence.for_goal(uid, goal.id)
            assert evidence, "nessuna prova dietro l'azione"
            assert any(
                e.provenance.source_class == "connected_provider" for e in evidence
            )

            fresh = await service.repo.get_goal(uid, goal.id)
            assert fresh.status == "completed", fresh.status
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_running_it_again_does_not_write_again(monkeypatch):
    """
    §23: the loop restarted, reloaded, or woken twice.

    The same effect recognised rather than repeated — which is the whole
    reason the key is built from what the effect is instead of when it was
    tried.
    """
    async def body():
        client, db = await _db()
        uid = f"gate_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            await _connect(db, uid)
            channel = _calendar(monkeypatch)
            await service.authority.grant(
                uid, "calendar.write", by="user", effect_scope=["create"],
                human_summary="Il tuo calendario: posso aggiungere quello che serve.",
            )
            goal = _goal(uid)
            await service.repo.create_goal(goal)
            await _plan(service, goal, uid)

            _install(monkeypatch, Recorded(_judgements()), Recorded(default=_delivery()))
            await service.advance(uid, goal.id)
            assert channel.writes == 1

            # Again, from scratch, as a restart would.
            fresh = await service.repo.get_goal(uid, goal.id)
            fresh.status = "active"
            await service.repo.save_goal(fresh)
            plan = await service.repo.plan_for(uid, goal.id)
            for step in plan.steps:
                step.status = "pending"
                step.attempts = 0
            await service.repo.save_plan(plan)

            _install(monkeypatch, Recorded(_judgements()), Recorded(default=_delivery()))
            await service.advance(uid, goal.id)

            assert channel.writes == 1, f"{channel.writes} scritture per un effetto"
            assert len(channel.events) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_fatto_still_waits_for_the_calendar_to_agree(monkeypatch):
    """
    §25: the guard that must not have moved.

        EXECUTED != VERIFIED.

    The provider takes the request and the event is not there when we look.
    Everything upstream succeeded; the goal does not close, and nobody is
    told it is done.
    """
    async def body():
        client, db = await _db()
        uid = f"gate_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            await _connect(db, uid)
            channel = _calendar(monkeypatch)

            async def blind(**kw):
                # Accepted, and then nothing to see.
                channel.reads += 1
                return {}

            channel.provider.get_event = blind

            await service.authority.grant(
                uid, "calendar.write", by="user", effect_scope=["create"],
                human_summary="Il tuo calendario: posso aggiungere quello che serve.",
            )
            goal = _goal(uid)
            await service.repo.create_goal(goal)
            await _plan(service, goal, uid)

            _install(monkeypatch, Recorded(_judgements()), Recorded(default=_delivery()))
            await service.advance(uid, goal.id)

            assert channel.writes == 1
            receipts = await service.executor.receipts_for(uid, goal.id)
            assert receipts[0]["provider_status"] == "accepted", (
                "accettato è diventato riuscito"
            )
            fresh = await service.repo.get_goal(uid, goal.id)
            assert fresh.status != "completed", "ha chiuso su una cosa mai vista"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_answer_in_the_thread_still_resumes_the_goal(monkeypatch):
    """
    §27: a targeted regression, not a reopening.

    The micro-fix routed a reply in the thread back to the goal that asked.
    Nothing in this gate should have disturbed it.
    """
    async def body():
        client, db = await _db()
        uid = f"gate_{uuid.uuid4().hex[:8]}"
        try:
            from agent.models import ActionPlan, ActionStep, CommunicationNeed

            service = await _service(db)
            goal = _goal(uid, status="waiting", requires_user_input=True,
                         objective="Avere il certificato di residenza.")
            await service.repo.create_goal(goal)
            await service.repo.save_plan(ActionPlan(
                goal_id=goal.id, owner_id=uid, status="waiting", plan_summary="p",
                steps=[ActionStep(
                    ordinal=0, intent="Sapere il comune.", step_type="ask_user",
                    ask_kind="knowledge", status="blocked",
                    asks="Qual è il tuo comune di residenza?",
                    expected_result="Il comune.",
                )],
            ))
            await service.needs.raise_need(CommunicationNeed(
                owner_id=uid, goal_id=goal.id, kind="needs_information",
                summary="Mi manca il tuo comune.", requires_response=True,
                response_kind="information", source_refs=[goal.id],
                provenance="code",
            ))

            _install(monkeypatch, Recorded(), Recorded())
            out = await service.answer(uid, goal.id, reply="Padova")
            assert out.get("ok")

            needs = await service.needs.open_for_goal(uid, goal.id)
            assert not needs, "il bisogno è rimasto aperto dopo la risposta"
            evidence = await service.evidence.for_goal(uid, goal.id)
            assert any(
                e.provenance.source_class == "user_statement" and "Padova" in e.claim
                for e in evidence
            ), "quello che ha detto non è diventato una prova"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_need_for_information_is_never_offered_a_permission(monkeypatch):
    """
    §2: the offer belongs to one moment and not to the others.

    «Puoi farlo anche in futuro» under a question about somebody's home town
    would be an answer to a question nobody asked.
    """
    async def body():
        client, db = await _db()
        uid = f"gate_{uuid.uuid4().hex[:8]}"
        try:
            from agent.models import ActionPlan, ActionStep

            service = await _service(db)
            goal = _goal(uid, status="waiting", requires_user_input=True)
            await service.repo.create_goal(goal)
            await service.repo.save_plan(ActionPlan(
                goal_id=goal.id, owner_id=uid, status="waiting", plan_summary="p",
                steps=[ActionStep(
                    ordinal=0, intent="Sapere il comune.", step_type="ask_user",
                    ask_kind="knowledge", status="blocked", asks="Comune?",
                    expected_result="Il comune.",
                )],
            ))
            assert await service.standing_offer(uid, goal.id) is None
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Structure, checked by walking the code
# ---------------------------------------------------------------------------

def _tree(relative: str) -> ast.AST:
    return ast.parse((HERE / relative).read_text(encoding="utf-8"))


def _function(tree: ast.AST, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} non esiste")


def _code_only(node):
    """The function with its prose removed — a comment is not a safeguard."""
    import copy

    clone = copy.deepcopy(node)
    for inner in ast.walk(clone):
        body = getattr(inner, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            inner.body = body[1:] or [ast.Pass()]
    return clone


def test_only_the_persistent_branch_can_create_a_grant():
    """
    §3: there is one door, and it is behind the flag.

    Walks `authorise` for every call that creates a permission and checks each
    one is inside the `if persistent:` branch. A behavioural test passes the
    day somebody moves the line; this fails.
    """
    node = _function(_tree("agent/service.py"), "authorise")

    guarded = set()
    for branch in [n for n in ast.walk(node) if isinstance(n, ast.If)]:
        test = branch.test
        if isinstance(test, ast.Name) and test.id == "persistent":
            for inner in ast.walk(branch):
                if isinstance(inner, ast.Call):
                    guarded.add(id(inner))

    for call in [n for n in ast.walk(node) if isinstance(n, ast.Call)]:
        name = getattr(call.func, "attr", getattr(call.func, "id", ""))
        if name == "grant":
            assert id(call) in guarded, (
                "si può creare un permesso permanente senza che sia stato chiesto"
            )


def test_the_offer_is_gated_by_the_same_test_a_command_is():
    """
    §5/§6: one boundary, not two.

    "Is this small enough that one sentence from a person settles it" is
    asked in two places — an instruction carrying authority, and an offer of a
    standing permission — and having two answers to it would be having two
    safety boundaries, one of which nobody is watching.
    """
    node = _function(_tree("agent/service.py"), "standing_offer")
    calls = [
        getattr(n.func, "attr", getattr(n.func, "id", ""))
        for n in ast.walk(node) if isinstance(n, ast.Call)
    ]
    assert "effect_is_commandable" in calls, "l'offerta non passa dal tetto"
    assert "has_grant" in calls, "può offrire una cosa già permessa"


def test_no_sentence_in_the_code_offers_everything():
    """
    §6: there is no unbounded grant, so there is no wording for one.

    Reads the sentence builder and asserts every path ends in limits. A
    permission that could be described as «tutto» would be one nobody could
    take back knowing what they were taking back.
    """
    node = _code_only(_function(_tree("agent/service.py"), "_grant_sentence"))
    source = ast.dump(node)
    for word in ("tutto", "qualsiasi", "illimitat", "unlimited"):
        assert word not in source.lower(), f"la frase può dire «{word}»"
    assert "senza chiedertelo ogni volta" in source


def test_a_calendar_event_cannot_end_when_it_begins():
    """
    §11/§12: the shared builder, and the caller that found it.

    Structural because the failure mode is a refactor restoring `end or
    start` — which nothing downstream would notice, since the provider
    accepts it and the read-back confirms it.
    """
    body = (HERE / "documents/intelligence/google_sync.py").read_text(encoding="utf-8")
    inside = body[body.index("def build_google_event_body"):]
    inside = inside[: inside.index("def _end_from")]
    assert "end or start" not in inside, "un evento lungo zero è tornato"
    assert "_end_from(" in inside, "nessuna durata viene dedotta"

    from documents.intelligence.google_sync import DEFAULT_EVENT_MINUTES

    assert DEFAULT_EVENT_MINUTES == 60
    # One number for the whole project, not three that agree today.
    import agent.effects as effects
    import conversation_engine.ai_core.tools.calendar_caps as caps

    assert caps._DEFAULT_MINUTES == DEFAULT_EVENT_MINUTES
    assert "DEFAULT_EVENT_MINUTES" in (HERE / "agent/effects.py").read_text(
        encoding="utf-8"
    )


def test_the_agent_never_writes_the_life_model_directly():
    """
    §26: what ORA learned goes through governance, like everything else.

    A verified effect may produce an observation. It may not produce a memory:
    an agent that can edit the model of somebody's life without review is a
    system whose beliefs nobody voted on.
    """
    source = (HERE / "agent/service.py").read_text(encoding="utf-8")
    for forbidden in ("db.memories.insert", "db.memories.update", "memories.replace"):
        assert forbidden not in source, f"scrittura diretta sul modello: {forbidden}"
    assert "life_observation" in source or "observe" in source
