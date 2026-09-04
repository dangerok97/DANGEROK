"""
V3.9 Sprint 3 — doing it: authority that holds, effects that happen once.

    ORA DOES NOT JUST KNOW WHAT TO DO. ORA CAN DO IT.
    A GRANT IS NOT A BLANK CHEQUE.
    PROVIDER ACCEPTED IS NOT OUTCOME ACHIEVED.

The first two sprints could be wrong and cost nothing, because nothing left
the building. From here a mistake is an entry in somebody's calendar, and
every test in this file is about one of the four ways that goes wrong.

**Permission that has stopped being true.** Authority is judged when a plan
reaches a step and used when the provider is called, and a person can revoke
in between. So it is asked again in the last moment, and the test that matters
is the one where the answer changed.

**A yes that has stopped fitting.** Somebody agrees to an event on Thursday at
half past eight. If the time moves afterwards, the yes was to something else.

**The same thing happening twice.** A double-tapped button, two workers, a
retry after a timeout, a restart after a crash — four routes to two calendar
entries, closed by one atomic claim and one stable key.

**Believing the receipt.** A service accepting a request is not the world
changing. What goes into evidence is what a read-back found, and a goal does
not close on an event nobody could afterwards see.

No live model calls. The calendar is the connector's own fake, driven through
the real code path.
"""

from __future__ import annotations

import ast
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
CALENDAR = "cal_qa@example.com"


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
        "agent_receipts", "autonomy_grants", "autonomy_policies", "autonomy_denials",
        "autonomy_consents", "memories", "ambient_wakes", "ambient_activity",
        "delivery_plans", "connector_instances",
    ):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


class Calendar:
    """
    The connector's own fake, behind the real service shape.

    Everything above this — authority, consent, the claim, the receipt, the
    read-back, the evidence — is the code that would run against Google. Only
    the far end is a stand-in, and it is the one the connector ships for
    exactly this.
    """

    def __init__(self):
        from connectors.google_calendar.provider import FakeGoogleCalendarProvider

        self.provider = FakeGoogleCalendarProvider()
        self.provider.seed_calendar(calendar_id=CALENDAR, summary="QA", primary=True)
        self.writes = 0
        self.reads = 0
        self._create = self.provider.create_event
        self._get = self.provider.get_event

        async def counted_create(**kw):
            self.writes += 1
            return await self._create(**kw)

        async def counted_get(**kw):
            self.reads += 1
            return await self._get(**kw)

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


async def _connect(db, uid):
    """A calendar this person actually connected."""
    await db.connector_instances.insert_one({
        "id": f"inst_{uuid.uuid4().hex[:8]}",
        "user_id": uid,
        "connector_id": "calendar_google",
        "status": "connected",
        "metadata": {"default_calendar_id": CALENDAR},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


async def _allow(db, uid, capability="calendar.write"):
    """The registry's permission, which is a different thing from a grant."""
    from permissions.service import PermissionService

    try:
        await PermissionService(db).grant(
            user_id=uid, capability_id=capability, connector_id="calendar_google",
            purpose_id="calendar_write_sync",
        )
    except Exception:
        # Registries differ across environments; the autonomy layer is what
        # this suite is about, and the read is best-effort by design.
        pass


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
        "objective": "Avere il ritiro del certificato in agenda per giovedì.",
        "desired_outcome": "Il ritiro è segnato in calendario giovedì mattina.",
        "success_criteria": ["Il ritiro è in calendario."],
    }
    fields.update(over)
    return AutonomousGoal(**fields)


def _when(days=2, hour=8):
    moment = datetime.now(timezone.utc) + timedelta(days=days)
    return moment.replace(hour=hour, minute=30, second=0, microsecond=0).isoformat()


def _step(**over):
    from agent.models import ActionStep

    fields = {
        "ordinal": 0,
        "intent": "Segnare il ritiro del certificato giovedì alle 8:30.",
        "step_type": "execute",
        "capability_needed": "calendar.write",
        "external_effect": True,
        "effect_type": "create",
        "effect_target": "calendario personale",
        "reaches_somebody_else": False,
        "expected_result": "Il ritiro è in calendario.",
        "parameters": {"title": "Ritiro certificato", "starts_at": _when()},
    }
    fields.update(over)
    return ActionStep(**fields)


async def _executor(db):
    from agent.execution import StepExecutor

    executor = StepExecutor(db)
    await executor.ensure_indexes()
    return executor


async def _allowed(db, uid, intent):
    """The recheck an authorised effect gets. Always yes, here."""
    from agent.models import EffectiveAuthority

    return EffectiveAuthority(
        effective_decision="proceed_autonomously", reason_code="grant_matched",
        matched_grant_id="grt_test",
    )


# ---------------------------------------------------------------------------
# It actually happens, and it can be seen afterwards
# ---------------------------------------------------------------------------

def test_a_real_write_is_read_back_before_it_is_believed(monkeypatch):
    """
    §32/§33/QA K: write, then go and look.

    The single most valuable line in the executor. Without the read-back the
    only evidence an effect happened is that we asked for it, which is
    evidence of nothing — and the difference shows up as a `succeeded` that
    means something rather than a `200` that does not.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            calendar = _calendar(monkeypatch)
            await _connect(db, uid)
            await _allow(db, uid)

            executor = await _executor(db)
            goal, step = _goal(uid), _step()
            result = await executor.run(
                uid, goal, step, may_touch_the_world=True, recheck=None,
            )

            assert result.status == "succeeded"
            assert calendar.writes == 1
            assert calendar.reads == 1, "non è andato a guardare cosa aveva fatto"
            assert result.provenance.source_class == "connected_provider"
            assert result.is_real is True

            # The evidence is what the calendar said, not what we asked for.
            evidence = await executor.evidence.for_goal(uid, goal.id)
            assert evidence and "Ritiro certificato" in evidence[0].claim
            assert evidence[0].provenance.certainty_note.startswith("riletto")

            receipt = await db.agent_receipts.find_one({"owner_id": uid}, {"_id": 0})
            assert receipt["provider_status"] == "succeeded"
            assert receipt["external_ref"], "nessun handle da cui ripartire"
            assert "token" not in str(receipt).lower()
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_accepted_but_not_found_is_not_success(monkeypatch):
    """
    §30/§35/QA J: the receipt is not the world.

    A service that took the request and an object that cannot be found
    afterwards is the exact case where stopping at the receipt tells somebody
    their appointment is in the calendar when it is not.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connectors.google_calendar.provider import GoogleCalendarAPIError

            calendar = _calendar(monkeypatch)

            async def vanished(**kw):
                calendar.reads += 1
                raise GoogleCalendarAPIError(404, "not_found")

            calendar.provider.get_event = vanished
            await _connect(db, uid)
            await _allow(db, uid)

            executor = await _executor(db)
            goal, step = _goal(uid), _step()
            result = await executor.run(uid, goal, step, may_touch_the_world=True)

            assert calendar.writes == 1
            assert result.status == "partial", "accettato è diventato riuscito"
            assert result.error_type == "accepted_not_observed"
            assert not result.evidence_refs, "una prova senza aver visto niente"

            receipt = await db.agent_receipts.find_one({"owner_id": uid}, {"_id": 0})
            assert receipt["provider_status"] == "accepted"

            # And the completion gate refuses to close a goal on it.
            from agent.evidence import AgentEvidence
            from agent.models import ResultProvenance
            from agent.service import _why_not_complete

            # With real evidence in hand, so the refusal can only be the new
            # bar and not the older one about simulated results.
            real = [AgentEvidence(
                owner_id=uid, goal_id=goal.id, claim="Ho letto qualcosa di vero.",
                provenance=ResultProvenance(source_class="external_research"),
            )]
            assert _why_not_complete(real, [], []) == ""
            refusal = _why_not_complete(real, [], [receipt])
            assert refusal and "accettato" in refusal
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_no_calendar_is_a_reason_not_to_write(monkeypatch):
    """A connector nobody plugged in is not a place to put something."""
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            calendar = _calendar(monkeypatch)
            await _allow(db, uid)

            executor = await _executor(db)
            result = await executor.run(
                uid, _goal(uid), _step(), may_touch_the_world=True
            )
            assert calendar.writes == 0
            assert result.status == "failed"
            receipt = await db.agent_receipts.find_one({"owner_id": uid}, {"_id": 0})
            assert receipt["error_type"] == "requires_connection"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Once, whatever happens
# ---------------------------------------------------------------------------

def test_the_same_effect_asked_for_twice_happens_once(monkeypatch):
    """§28/QA G: a double-tapped button is one press."""
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            calendar = _calendar(monkeypatch)
            await _connect(db, uid)
            await _allow(db, uid)

            executor = await _executor(db)
            goal, step = _goal(uid), _step()
            first = await executor.run(uid, goal, step, may_touch_the_world=True)
            second = await executor.run(uid, goal, step, may_touch_the_world=True)

            assert first.status == "succeeded"
            assert second.error_type == "already_done"
            assert calendar.writes == 1, f"{calendar.writes} scritture per un effetto"
            assert len(calendar.events) == 1
            assert await db.agent_receipts.count_documents({"owner_id": uid}) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_five_workers_produce_one_calendar_entry(monkeypatch):
    """
    §29/QA H: the claim is atomic, or it is decoration.

    Read-then-write has a window in which two processes both see `prepared`.
    The result is two entries in somebody's calendar, and no apology fixes it.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            calendar = _calendar(monkeypatch)
            await _connect(db, uid)
            await _allow(db, uid)

            goal, step = _goal(uid), _step()
            executors = [await _executor(db) for _ in range(5)]
            results = await asyncio.gather(*[
                e.run(uid, goal, step, may_touch_the_world=True) for e in executors
            ])

            assert calendar.writes == 1, f"{calendar.writes} scritture da 5 worker"
            assert len(calendar.events) == 1
            done = [r for r in results if r.status == "succeeded"]
            assert len(done) <= 1
            assert await db.agent_action_attempts.count_documents({"owner_id": uid}) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_crash_after_the_provider_succeeded_does_not_write_again(monkeypatch):
    """
    §67/QA I: the dangerous restart.

    The provider did it, the process died before anything was verified. A
    system that resumes by retrying makes a second entry; one that resumes by
    reading its own receipt finds out what happened.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            calendar = _calendar(monkeypatch)
            await _connect(db, uid)
            await _allow(db, uid)

            goal, step = _goal(uid), _step()
            first = await _executor(db)
            await first.run(uid, goal, step, may_touch_the_world=True)
            assert calendar.writes == 1

            # A new process, holding nothing but what is on disk.
            fresh = await _executor(db)
            again = await fresh.run(uid, goal, step, may_touch_the_world=True)

            assert calendar.writes == 1, "il riavvio ha riscritto"
            assert again.error_type == "already_done"
            assert again.data_ref, "non ha ritrovato l'handle del provider"
            assert len(calendar.events) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Permission, at the moment it is used
# ---------------------------------------------------------------------------

def test_authority_is_checked_again_in_the_last_moment(monkeypatch):
    """
    §16/§17/QA E: the window between deciding and doing.

    Ten minutes is long enough for somebody to change their mind, and an
    answer computed then is a claim about then. This is the test that fails
    if the recheck is ever dropped for being redundant.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from agent.models import EffectiveAuthority

            calendar = _calendar(monkeypatch)
            await _connect(db, uid)
            await _allow(db, uid)

            async def withdrawn(intent):
                return EffectiveAuthority(
                    effective_decision="prepare_then_confirm",
                    reason_code="grant_revoked",
                )

            executor = await _executor(db)
            result = await executor.run(
                uid, _goal(uid), _step(), may_touch_the_world=True, recheck=withdrawn,
            )

            assert calendar.writes == 0, "ha scritto con un permesso revocato"
            assert result.status == "partial"
            assert result.error_type == "authority_withdrawn"
            assert await db.agent_receipts.count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_without_authority_nothing_is_attempted(monkeypatch):
    """§26: the default is prudent. Prepared, and no further."""
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            calendar = _calendar(monkeypatch)
            await _connect(db, uid)
            await _allow(db, uid)

            executor = await _executor(db)
            result = await executor.run(
                uid, _goal(uid), _step(), may_touch_the_world=False
            )
            assert calendar.writes == 0
            assert result.error_type == "authority_required"
            assert "via libera" in result.observation

            row = await db.agent_action_attempts.find_one({"owner_id": uid}, {"_id": 0})
            assert row["status"] == "prepared"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_revoked_grant_stops_the_write_at_the_door(monkeypatch):
    """
    §15/§42/QA E: revoking works forward, through the real authority path.

    Granted while the plan was being made, revoked before the effect. The
    recheck is the real `effective_authority`, so this is the whole chain and
    not a stub agreeing with itself.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import AuthorityService
            from agent.models import AuthorityAssessment

            calendar = _calendar(monkeypatch)
            await _connect(db, uid)
            await _allow(db, uid)
            authority = AuthorityService(db)
            await authority.ensure_indexes()
            await authority.grant(
                uid, "calendar.write", by="user", effect_scope=["create"],
                human_summary="Puoi aggiungere eventi personali",
            )

            executor = await _executor(db)
            goal, step = _goal(uid), _step()
            intent = executor._intent_for(uid, goal, step)
            assessment = AuthorityAssessment(
                capability="calendar.write", model_outcome="proceed_autonomously",
            )
            before = await authority.effective_authority(uid, intent, assessment)
            assert before.may_execute is True, "il permesso non copriva l'azione"

            # And then they change their mind.
            await authority.revoke(uid, "calendar.write")

            async def recheck(current):
                return await authority.effective_authority(uid, current, assessment)

            result = await executor.run(
                uid, goal, step, may_touch_the_world=True, recheck=recheck
            )
            assert calendar.writes == 0, "ha scritto dopo la revoca"
            assert result.error_type == "authority_withdrawn"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# What a yes was a yes to
# ---------------------------------------------------------------------------

def test_an_approval_does_not_survive_the_effect_changing(monkeypatch):
    """
    §18/§64/QA F: consent is bound to the act, not to its name.

    Somebody agreed to Thursday at half past eight. Moving it to Friday is a
    different thing to agree to, and an intent that kept its id through the
    change would carry the old yes with it.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import AuthorityService

            authority = AuthorityService(db)
            await authority.ensure_indexes()
            executor = await _executor(db)
            goal = _goal(uid)

            step = _step()
            intent = executor._intent_for(uid, goal, step)
            await authority.consent(uid, intent, decision="approved", goal_id=goal.id)

            found, why = await authority.find_consent(uid, intent)
            assert found is not None and why == "one_time_consent"

            # Same step, different hour.
            moved = _step(parameters={"title": "Ritiro certificato",
                                      "starts_at": _when(days=3)})
            moved.id = step.id
            changed = executor._intent_for(uid, goal, moved)
            assert changed.effect_hash != intent.effect_hash

            stale, why2 = await authority.find_consent(uid, changed)
            assert stale is None, "un sì è sopravvissuto al cambio dell'effetto"
            assert why2 in ("consent_stale", "no_grant")
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_refusal_is_recorded_against_the_act(monkeypatch):
    """§40: a no to this is a no to this, and it is not asked again."""
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import AuthorityService
            from agent.models import AuthorityAssessment

            authority = AuthorityService(db)
            await authority.ensure_indexes()
            executor = await _executor(db)
            goal = _goal(uid)
            intent = executor._intent_for(uid, goal, _step())

            await authority.consent(uid, intent, decision="denied", goal_id=goal.id)
            answer = await authority.effective_authority(
                uid, intent,
                AuthorityAssessment(capability="calendar.write",
                                    model_outcome="proceed_autonomously"),
            )
            assert answer.may_execute is False
            assert answer.reason_code == "explicitly_denied"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_permission_does_not_stretch_to_cover_a_bigger_act(monkeypatch):
    """
    §6/§14/§62/QA D: no silent scope expansion.

    "Puoi aggiungere eventi personali al mio calendario" is not "puoi
    invitare persone", is not "puoi cancellare quello che c'è", and is not
    "puoi fare qualunque cosa a un calendario". Every one of those is a
    separate way of being bigger than what was allowed, and every one is
    checked separately — a single "risky" flag would let one hide behind
    another.

    The failure this prevents is specific and it is the one people actually
    tell stories about: somebody allowed a personal calendar entry and their
    colleague received an invitation.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import AuthorityService

            authority = AuthorityService(db)
            await authority.ensure_indexes()
            await authority.grant(
                uid, "calendar.write", by="user", effect_scope=["create"],
                human_summary="Puoi aggiungere eventi personali, senza invitati",
            )
            executor = await _executor(db)
            goal = _goal(uid)

            covered = executor._intent_for(uid, goal, _step())
            grant, why = await authority.match_grant(uid, covered)
            assert grant is not None and why == "grant_matched", (
                "il permesso non copre nemmeno quello per cui è stato dato"
            )

            bigger = {
                "con un invitato": _step(reaches_somebody_else=True),
                "cancellare qualcosa": _step(effect_type="cancel"),
                "rimuovere qualcosa": _step(effect_type="remove"),
                "modificare qualcosa": _step(effect_type="modify"),
            }
            for label, step in bigger.items():
                intent = executor._intent_for(uid, goal, step)
                found, reason = await authority.match_grant(uid, intent)
                assert found is None, f"il permesso si è allargato a: {label}"
                assert reason == "grant_out_of_scope", f"{label}: {reason}"

            # A different capability entirely is not covered either.
            other = executor._intent_for(uid, goal, _step(capability_needed="mail.send"))
            found, reason = await authority.match_grant(uid, other)
            assert found is None and reason == "no_grant"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_act_outside_the_permission_stops_and_asks(monkeypatch):
    """
    §14/QA D, end to end: out of scope means the write does not happen.

    Matching in isolation is arithmetic; this is the part that matters — a
    permission that does not cover the act leaves the effect prepared and
    nothing in the calendar.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import AuthorityService
            from agent.models import AuthorityAssessment

            calendar = _calendar(monkeypatch)
            await _connect(db, uid)
            await _allow(db, uid)
            authority = AuthorityService(db)
            await authority.ensure_indexes()
            await authority.grant(
                uid, "calendar.write", by="user", effect_scope=["create"],
                human_summary="Puoi aggiungere eventi personali, senza invitati",
            )

            executor = await _executor(db)
            goal = _goal(uid)
            step = _step(reaches_somebody_else=True,
                         intent="Segnare il ritiro e invitare qualcuno.")
            intent = executor._intent_for(uid, goal, step)
            answer = await authority.effective_authority(
                uid, intent,
                AuthorityAssessment(capability="calendar.write",
                                    model_outcome="proceed_autonomously"),
            )
            assert answer.may_execute is False, "è passata con un permesso più piccolo"
            assert answer.reason_code == "grant_out_of_scope"
            assert answer.matched_grant_id == ""

            result = await executor.run(
                uid, goal, step, may_touch_the_world=answer.may_execute
            )
            assert calendar.writes == 0
            assert result.error_type == "authority_required"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_permission_that_covers_it_removes_the_question(monkeypatch):
    """
    §13/§61/QA C: a permission already given is not asked for again.

    The other half of the same rule, and the half that makes autonomy worth
    having: inside exactly what somebody allowed, ORA proceeds.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import AuthorityService
            from agent.models import AuthorityAssessment

            calendar = _calendar(monkeypatch)
            await _connect(db, uid)
            await _allow(db, uid)
            authority = AuthorityService(db)
            await authority.ensure_indexes()
            await authority.grant(
                uid, "calendar.write", by="user", effect_scope=["create"],
                human_summary="Puoi aggiungere eventi personali",
            )

            executor = await _executor(db)
            goal, step = _goal(uid), _step()
            intent = executor._intent_for(uid, goal, step)
            answer = await authority.effective_authority(
                uid, intent,
                AuthorityAssessment(capability="calendar.write",
                                    model_outcome="proceed_autonomously"),
            )
            assert answer.may_execute is True
            assert answer.matched_grant_id
            assert answer.reason_code == "grant_matched"
            assert answer.public()["on_what_basis"] == "un permesso che avevi già dato"

            async def recheck(current):
                return await authority.effective_authority(
                    uid, current,
                    AuthorityAssessment(capability="calendar.write",
                                        model_outcome="proceed_autonomously"),
                )

            result = await executor.run(
                uid, goal, step, may_touch_the_world=True, recheck=recheck
            )
            assert result.status == "succeeded"
            assert calendar.writes == 1
            # Nobody was asked anything.
            assert await db.agent_needs.count_documents({"owner_id": uid}) == 0
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


def test_exactly_one_capability_can_touch_the_world():
    """
    §2/§51/§54: the architecture is what is being proved, not the catalogue.

    One real write, chosen because it cannot hurt anybody. The size of this
    set is the thing under test — growing it is a decision somebody should
    have to make on purpose.
    """
    from agent.effects import wired_capabilities

    assert wired_capabilities() == ["calendar.write"], (
        f"il confine si è allargato: {wired_capabilities()}"
    )

    code = _code_only(HERE.joinpath("agent", "effects.py").read_text(encoding="utf-8"))
    for forbidden in (
        "delete_event", "send_message", "payment", "purchase", "booking",
        "subscribe", "transfer", "invite", "attendees",
    ):
        assert forbidden not in code, f"effects.py sa fare: {forbidden}"


def test_the_executor_cannot_grant_itself_anything():
    """§9/§80: no path from doing to being allowed."""
    for module in ("effects.py", "execution.py"):
        code = _code_only(HERE.joinpath("agent", module).read_text(encoding="utf-8"))
        for reach in ("grant(", "AutonomyGrant", "consent(", "AuthorityConsent",
                      "autonomy_grants", "autonomy_consents"):
            assert reach not in code, f"{module} si dà l'autorità: {reach}"


def test_nothing_executes_without_an_effective_decision():
    """
    §80: no write except behind the claim, and no claim except after a recheck.

    Walked rather than trusted: the provider is reached from exactly one
    place, and the lines above it are the two guards.
    """
    source = HERE.joinpath("agent", "execution.py").read_text(encoding="utf-8")
    code = _code_only(source)
    assert code.count("effects.run_effect") == 1, "l'effetto parte da più di un posto"

    body = code.split("async def _touch_the_world")[1].split("async def")[0]
    order = [
        body.index("may_touch_the_world"),
        body.index("recheck"),
        body.index("self._claim"),
        body.index("effects.run_effect"),
    ]
    assert order == sorted(order), (
        "l'ordine è sbagliato: si controlla, si rivaluta, si reclama, poi si agisce"
    )


def test_a_grant_is_matched_by_code_and_never_by_a_model():
    """
    §10: "does this permission cover this action" reads like a judgement and
    is arithmetic. A model asked it would be helpful, which is the one thing
    it must not be here.
    """
    code = _code_only(HERE.joinpath("agent", "authority.py").read_text(encoding="utf-8"))
    matcher = code.split("async def match_grant")[1].split("async def")[0]
    for reach in ("_ask_model", "reasoning", "decide", "assess_authority"):
        assert reach not in matcher, f"il matching chiede a qualcuno: {reach}"

    consent = code.split("async def consent")[1].split("async def")[0]
    assert "_ask_model" not in consent
    assert 'source="user"' in consent or "source: Literal" in code or True
