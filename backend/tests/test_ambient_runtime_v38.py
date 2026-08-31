"""
V3.8 Sprint 2 — the runtime that wakes ORA when nobody is looking.

    WAKE != NOTIFY.
    PENDING DELIVERY IS A HYPOTHESIS, NOT A PROMISE.

Sprint 1 could decide "check again at 07:15" and had no way to be there. What
is defended here is that being there changes nothing about who decides.

A wake is an alarm. Reaching one does not send anything, does not mean
anything, and usually ends in a review that concludes nothing has changed.
Every test that says "provider calls = 0" is guarding the same line: the day
a wake can reach a notification without a fresh judgement in between, the
runtime has become the product.

The other half is arithmetic the database has to get right. Two processes
racing for one due wake must produce one winner; a worker that dies must not
strand its work; a life with nothing in it must cost one indexed query and
no inference at all.

The model is stubbed throughout. The two live QAs are run separately and
reported with an exact call count.
"""

from __future__ import annotations

import ast
import asyncio
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
        "ambient_wakes", "push_endpoints", "app_presence", "delivery_plans",
        "ambient_activity", "opportunities", "opportunity_decisions",
        "meaningful_changes", "opportunity_scan_state", "calendar_events",
        "life_places", "home_snapshots",
    ):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


class FakeModel:
    def __init__(self, answers):
        self.answers = list(answers)
        self.seen = []

    async def __call__(self, system, user):
        self.seen.append({"system": system, "user": user})
        return self.answers.pop(0) if self.answers else None


def _install(monkeypatch, model):
    import delivery.reasoning as delivery_reasoning
    import opportunities.reasoning as opportunity_reasoning

    monkeypatch.setattr(delivery_reasoning, "_ask_model", model)
    monkeypatch.setattr(opportunity_reasoning, "_ask_model", model)


class Provider:
    name = "test"

    def __init__(self, ok=True, transient=False):
        self.sent = []
        self.cancelled = []
        self.ok = ok
        self.transient = transient

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        return {"ok": self.ok, "provider": self.name, "transient": self.transient}

    async def cancel(self, *, owner_id, plan_id):
        self.cancelled.append(plan_id)
        return {"ok": True, "retracted": False}


def _provider(monkeypatch, **kw) -> Provider:
    from delivery import provider as provider_module

    channel = Provider(**kw)
    monkeypatch.setattr(provider_module, "get_provider", lambda: channel)
    return channel


async def _allow_push(allowed=True):
    import delivery.context as context_module

    async def _permission(_db, _uid, _now):
        return {"push": allowed}

    context_module._permission = _permission  # noqa: SLF001


def _push(**over):
    answer = {
        "mode": "push",
        "timing": "now",
        "reason_to_interrupt": "La finestra si chiude fra poco.",
        "reason_to_open": "Ti dico cosa manca.",
        "confidence": "strong",
        "sensitivity": "ordinary",
        "copy": {"title": "C'è una cosa per domani", "body": "Manca un documento."},
    }
    answer.update(over)
    return answer


async def _an_opportunity(db, uid, **over):
    from opportunities.models import EvidenceRef, Opportunity
    from opportunities.repository import OpportunityRepository

    fields = {
        "owner_id": uid,
        "identity_key": f"cosa-{uuid.uuid4().hex[:6]}",
        "status": "active",
        "semantic_summary": "Manca il certificato per l'appuntamento.",
        "why_it_matters": "Senza, non si conclude.",
        "why_now": "L'ufficio apre solo la mattina.",
        "relevance": "high",
        "urgency": "soon",
        "confidence": "strong",
        "evidence": [EvidenceRef(kind="calendar_event", ref="evt_x")],
    }
    fields.update(over)
    opportunity = Opportunity(**fields)
    await OpportunityRepository(db).save(opportunity)
    return opportunity


async def _a_future_plan(db, uid, opportunity, *, minutes: int):
    """A plan decided for later, with its alarm, exactly as evaluate() makes one."""
    from ambient.service import AmbientService
    from delivery.models import DeliveryPlan, PushCopy

    when = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    plan = DeliveryPlan(
        owner_id=uid,
        opportunity_id=opportunity.id,
        mode="push",
        status="pending",
        not_before=when.isoformat(),
        words=PushCopy(title="Deciso ieri sera", body="Da rivalutare stamattina."),
        reason_to_open="Ti dico cosa manca.",
        deep_link=f"/ora?opportunityId={opportunity.id}&entry=notification",
    )
    from delivery.service import DeliveryService

    await DeliveryService(db).repo.save_plan(plan)
    wake = await AmbientService(db).schedule_for_plan(plan)
    return plan, wake


# ---------------------------------------------------------------------------
# A wake is an alarm
# ---------------------------------------------------------------------------

def test_a_future_plan_is_processed_without_anybody_opening_the_app(monkeypatch):
    """
    §54: the debt Sprint 1 left behind, paid.

    A plan decided for later used to sit in the collection hoping a request
    would come along. Here the moment arrives, the runtime claims the wake and
    the decision is re-examined — no HTTP call anywhere in this test.
    """
    async def body():
        client, db = await _db()
        uid = f"a38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.runtime import tick

            channel = _provider(monkeypatch)
            await _allow_push(True)
            opportunity = await _an_opportunity(db, uid)
            plan, wake = await _a_future_plan(db, uid, opportunity, minutes=45)

            assert wake is not None, "il piano futuro non ha una sveglia"
            assert wake.reason == "delivery_recheck"

            # Before the moment: this wake is not due, so nothing happens to
            # it and nothing is sent for this plan.
            await tick(db)
            still_waiting = await db.ambient_wakes.find_one({"id": wake.id}, {"_id": 0})
            assert still_waiting["status"] == "pending"
            assert channel.sent == []

            # The moment arrives. The runtime serves everybody, so this asserts
            # on its own wake rather than on global counts — another test's
            # leftovers being claimed in the same pass is the runtime working,
            # not a failure.
            _install(monkeypatch, FakeModel([_push()]))
            later = datetime.now(timezone.utc) + timedelta(minutes=50)
            await tick(db, now=later, limit=20)

            refreshed = await db.ambient_wakes.find_one({"id": wake.id}, {"_id": 0})
            assert refreshed["status"] == "completed"

            mine = [s for s in channel.sent if s["plan_id"] == plan.id]
            assert len(mine) == 1, "il piano non è stato eseguito dal runtime"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_recheck_leaves_its_stamp(monkeypatch):
    """
    §37: a plan sent without a recheck and one sent after must not look alike.

    Without this, `last_rechecked_at` stays null on a plan the runtime really
    did re-examine — and the one field that proves the guarantee was honoured
    says it was not.
    """
    async def body():
        client, db = await _db()
        uid = f"a38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.runtime import tick
            from delivery.service import DeliveryService

            _provider(monkeypatch)
            await _allow_push(True)
            opportunity = await _an_opportunity(db, uid)
            plan, _ = await _a_future_plan(db, uid, opportunity, minutes=10)

            _install(monkeypatch, FakeModel([{
                "mode": "in_app", "reason_to_interrupt": "basta lo schermo",
            }]))
            await tick(db, now=datetime.now(timezone.utc) + timedelta(minutes=15))

            stored = await DeliveryService(db).repo.get_plan(uid, plan.id)
            assert stored is not None
            assert stored.last_rechecked_at, "il ricontrollo non ha lasciato traccia"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_reaching_a_wake_is_not_permission_to_send(monkeypatch):
    """
    §12/§13: the plan is re-judged, and the model may change its mind.

    Last night it said push. This morning it says the screen is enough — and
    that is what happens, because the earlier decision was a hypothesis.
    """
    async def body():
        client, db = await _db()
        uid = f"a38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.runtime import tick

            channel = _provider(monkeypatch)
            await _allow_push(True)
            opportunity = await _an_opportunity(db, uid)
            await _a_future_plan(db, uid, opportunity, minutes=30)

            _install(monkeypatch, FakeModel([{
                "mode": "in_app",
                "reason_to_interrupt": "Stamattina basta che lo veda quando apre.",
            }]))
            done = await tick(db, now=datetime.now(timezone.utc) + timedelta(minutes=35))

            assert done["completed"] == 1
            assert channel.sent == [], "ha inviato malgrado il nuovo giudizio"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_concern_settled_overnight_is_never_announced(monkeypatch):
    """§55: resolve before wake. The provider is never reached."""
    async def body():
        client, db = await _db()
        uid = f"a38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.runtime import tick
            from opportunities.repository import OpportunityRepository

            channel = _provider(monkeypatch)
            await _allow_push(True)
            opportunity = await _an_opportunity(db, uid)
            plan, _ = await _a_future_plan(db, uid, opportunity, minutes=40)

            # The document arrives during the night.
            opportunity.status = "resolved"
            await OpportunityRepository(db).save(opportunity)

            model = FakeModel([_push()])
            _install(monkeypatch, model)
            done = await tick(db, now=datetime.now(timezone.utc) + timedelta(minutes=45))

            assert done["completed"] == 1
            assert channel.sent == [], "ha notificato una cosa già risolta"
            assert model.seen == [], "ha speso una chiamata per una cosa chiusa"

            stored = await db.delivery_plans.find_one({"id": plan.id}, {"_id": 0})
            assert stored["status"] == "cancelled"
            assert stored["decision_provenance"] == "code_cancel"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_closing_an_opportunity_cancels_its_arranged_moments(monkeypatch):
    """§16: the alarm goes with the plan, so nothing wakes up to find nothing."""
    async def body():
        client, db = await _db()
        uid = f"a38_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.service import OpportunityService

            _provider(monkeypatch)
            await _allow_push(True)
            opportunity = await _an_opportunity(db, uid)
            _, wake = await _a_future_plan(db, uid, opportunity, minutes=60)
            assert wake is not None

            await OpportunityService(db).dismiss(uid, opportunity.id)

            refreshed = await db.ambient_wakes.find_one({"id": wake.id}, {"_id": 0})
            assert refreshed["status"] == "cancelled"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Arithmetic the database has to get right
# ---------------------------------------------------------------------------

def test_two_workers_racing_for_one_wake_produce_one_winner(monkeypatch):
    """
    §7/§8/§57: the multi-instance debt from V3.7, paid in the database.

    Find-then-update has a window between the read and the write in which both
    processes see the same row. `find_one_and_update` closes it: one process
    matches, the other gets nothing.
    """
    async def body():
        client, db = await _db()
        uid = f"a38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.models import AmbientWake
            from ambient.repository import AmbientRepository

            repo = AmbientRepository(db)
            await repo.ensure_indexes()
            past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
            await repo.schedule(AmbientWake(
                owner_id=uid, reason="ambient_review", scheduled_for=past
            ))

            claims = await asyncio.gather(*[
                repo.claim_due(worker_id=f"worker_{n}") for n in range(6)
            ])
            winners = [c for c in claims if c is not None]
            assert len(winners) == 1, f"{len(winners)} worker hanno preso lo stesso wake"
            assert winners[0].worker_id.startswith("worker_")
            assert winners[0].attempts == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_worker_that_dies_does_not_strand_the_work(monkeypatch):
    """The lease, not a flag somebody has to remember to clear."""
    async def body():
        client, db = await _db()
        uid = f"a38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.models import AmbientWake
            from ambient.repository import AmbientRepository, LEASE_SECONDS

            repo = AmbientRepository(db)
            await repo.ensure_indexes()
            past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
            await repo.schedule(AmbientWake(
                owner_id=uid, reason="ambient_review", scheduled_for=past
            ))

            first = await repo.claim_due(worker_id="doomed")
            assert first is not None
            # Nobody else can take it while the lease holds.
            assert await repo.claim_due(worker_id="other") is None

            # That worker dies. Time passes.
            after_lease = datetime.now(timezone.utc) + timedelta(seconds=LEASE_SECONDS + 5)
            recovered = await repo.claim_due(worker_id="other", now=after_lease)
            assert recovered is not None, "il lavoro è rimasto bloccato"
            assert recovered.id == first.id
            assert recovered.attempts == 2
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_plan_that_keeps_being_put_off_does_not_spin(monkeypatch):
    """
    §15: hold, wake, hold, wake is a loop that looks like attentiveness.

    The model is free to keep deciding "a bit later". How soon it may be asked
    again is not its call — a floor applies once a plan has already been round
    once, so a judgement that never settles costs a few looks a day rather
    than one every thirty seconds.
    """
    async def body():
        client, db = await _db()
        uid = f"a38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.repository import AmbientRepository
            from ambient.service import MIN_HOLD_MINUTES, AmbientService
            from delivery.models import DeliveryPlan, PushCopy
            from delivery.service import DeliveryService

            await AmbientRepository(db).ensure_indexes()
            opportunity = await _an_opportunity(db, uid)
            soon = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()

            plan = DeliveryPlan(
                owner_id=uid, opportunity_id=opportunity.id, mode="push",
                status="pending", not_before=soon,
                words=PushCopy(title="t", body="b"),
                # Already re-examined once.
                last_rechecked_at=datetime.now(timezone.utc).isoformat(),
            )
            await DeliveryService(db).repo.save_plan(plan)

            wake = await AmbientService(db).schedule_for_plan(plan)
            assert wake is not None
            gap = (
                datetime.fromisoformat(wake.scheduled_for)
                - datetime.now(timezone.utc)
            ).total_seconds() / 60
            assert gap >= MIN_HOLD_MINUTES - 1, f"riprova fra {gap:.0f} minuti: è un ciclo"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_same_alarm_is_not_set_three_times(monkeypatch):
    """§5: three updates to one concern are one moment to look again."""
    async def body():
        client, db = await _db()
        uid = f"a38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.repository import AmbientRepository
            from ambient.service import AmbientService

            await AmbientRepository(db).ensure_indexes()
            service = AmbientService(db)
            when = datetime.now(timezone.utc) + timedelta(hours=2)

            created = [
                await service.schedule(
                    uid, reason="opportunity_revisit", when=when, opportunity_id="opp_same"
                )
                for _ in range(3)
            ]
            assert sum(1 for c in created if c is not None) == 1
            assert await db.ambient_wakes.count_documents(
                {"owner_id": uid, "status": "pending"}
            ) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_empty_life_costs_one_query_and_no_inference(monkeypatch):
    """
    §65/§51: an autonomous runtime that thinks about everybody constantly is
    an autonomous runtime nobody can afford.
    """
    async def body():
        client, db = await _db()
        uid = f"a38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.runtime import tick

            model = FakeModel([_push(), _push()])
            _install(monkeypatch, model)
            channel = _provider(monkeypatch)

            for _ in range(3):
                result = await tick(db)
                assert result["claimed"] == 0

            assert model.seen == [], "ha pensato a qualcuno che non aveva niente"
            assert channel.sent == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# When something is unreachable
# ---------------------------------------------------------------------------

def test_an_unreachable_model_retries_and_invents_nothing(monkeypatch):
    """§46/§58: no push, no false silence, no fabricated proof of work."""
    async def body():
        client, db = await _db()
        uid = f"a38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.runtime import tick

            channel = _provider(monkeypatch)
            await _allow_push(True)
            opportunity = await _an_opportunity(db, uid)
            plan, wake = await _a_future_plan(db, uid, opportunity, minutes=20)

            _install(monkeypatch, FakeModel([]))  # unreachable
            done = await tick(db, now=datetime.now(timezone.utc) + timedelta(minutes=25))

            assert done["retried"] == 1
            assert done["completed"] == 0
            assert channel.sent == []

            refreshed = await db.ambient_wakes.find_one({"id": wake.id}, {"_id": 0})
            assert refreshed["status"] == "pending", "il risveglio è andato perso"
            assert refreshed["provenance"] == "technical_retry"
            assert refreshed["scheduled_for"] > datetime.now(timezone.utc).isoformat()

            # The plan is untouched: nothing was decided about it.
            stored = await db.delivery_plans.find_one({"id": plan.id}, {"_id": 0})
            assert stored["status"] == "pending"
            assert stored["delivered_at"] is None

            # And nothing claims a review happened.
            assert await db.ambient_activity.count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_channel_that_is_down_does_not_lose_the_decision(monkeypatch):
    """§47/§59: the plan stays open, and nothing is reclassified as silence."""
    async def body():
        client, db = await _db()
        uid = f"a38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.runtime import tick

            channel = _provider(monkeypatch, ok=False, transient=True)
            await _allow_push(True)
            opportunity = await _an_opportunity(db, uid)
            plan, _ = await _a_future_plan(db, uid, opportunity, minutes=15)

            _install(monkeypatch, FakeModel([_push()]))
            await tick(db, now=datetime.now(timezone.utc) + timedelta(minutes=20))

            stored = await db.delivery_plans.find_one({"id": plan.id}, {"_id": 0})
            assert stored["status"] == "held", "la decisione è stata persa"
            assert stored["delivered_at"] is None
            assert stored["mode"] == "push", "riclassificata come qualcos'altro"
            assert len(channel.sent) == 1, "un solo tentativo, non un ciclo"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_retry_backoff_grows_and_stops_growing():
    """§45: code's business entirely, and capped."""
    from ambient.runtime import RETRY_BASE_SECONDS, RETRY_MAX_SECONDS

    delays = [
        min(RETRY_MAX_SECONDS, RETRY_BASE_SECONDS * (2 ** n)) for n in range(10)
    ]
    assert delays[0] == RETRY_BASE_SECONDS
    assert delays == sorted(delays), "il backoff non cresce"
    assert delays[-1] == RETRY_MAX_SECONDS, "il backoff non ha un tetto"
    assert RETRY_MAX_SECONDS <= 3600


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------

def test_the_same_phone_registering_twice_is_one_device(monkeypatch):
    """§24: idempotent, or every launch adds a row."""
    async def body():
        client, db = await _db()
        uid = f"a38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.push import PushEndpointService

            service = PushEndpointService(db)
            for _ in range(3):
                await service.register(
                    uid, token="ExponentPushToken[abc]", platform="ios", device="iphone-1"
                )
            assert await db.push_endpoints.count_documents({"owner_id": uid}) == 1
        finally:
            await db.push_endpoints.delete_many({"owner_id": uid})
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_token_never_travels_back_out(monkeypatch):
    """
    §23/§52: a token is a capability to write on somebody's lock screen.

    Written once, never returned, never logged, never in a report.
    """
    async def body():
        client, db = await _db()
        uid = f"a38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.push import PushEndpointService

            secret = "ExponentPushToken[SEGRETISSIMO]"
            service = PushEndpointService(db)
            result = await service.register(uid, token=secret, platform="ios", device="d1")

            import json

            assert secret not in json.dumps(result, ensure_ascii=False)
            assert secret not in json.dumps(await service.endpoints(uid), ensure_ascii=False)

            # And the device's own identifier is not kept, only its hash.
            stored = await db.push_endpoints.find_one({"owner_id": uid}, {"_id": 0})
            assert stored["device_hash"] != "d1"
            assert len(stored["device_hash"]) == 32
        finally:
            await db.push_endpoints.delete_many({"owner_id": uid})
            await _clean(db, uid)
            client.close()

    _run(body())


def test_signing_in_as_somebody_else_releases_the_phone(monkeypatch):
    """
    §49/§50: the failure this prevents is the worst one in the phase.

    A token left active for the previous account is how one person's
    notification arrives on another person's phone.
    """
    async def body():
        client, db = await _db()
        first = f"a38_{uuid.uuid4().hex[:8]}"
        second = f"a38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.push import PushEndpointService

            service = PushEndpointService(db)
            await service.register(first, token="ExponentPushToken[x]", device="same-phone")
            assert len(await service.endpoints(first)) == 1

            # Same phone, different person.
            await service.register(second, token="ExponentPushToken[y]", device="same-phone")

            assert await service.endpoints(first) == [], "il telefono è ancora del primo"
            assert len(await service.endpoints(second)) == 1
        finally:
            for uid in (first, second):
                await db.push_endpoints.delete_many({"owner_id": uid})
                await _clean(db, uid)
            client.close()

    _run(body())


def test_logging_out_stops_notifications_to_that_phone(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"a38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.push import PushEndpointService

            service = PushEndpointService(db)
            await service.register(uid, token="ExponentPushToken[z]", device="phone")
            await service.release_device(uid, "phone")
            assert await service.endpoints(uid) == []
        finally:
            await db.push_endpoints.delete_many({"owner_id": uid})
            await _clean(db, uid)
            client.close()

    _run(body())


def test_one_dead_token_does_not_silence_the_other_devices(monkeypatch):
    """§28/§29/§60: partial failure is the normal case with two devices."""
    async def body():
        client, db = await _db()
        uid = f"a38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.push import ExpoNotificationProvider, PushEndpointService

            service = PushEndpointService(db)
            await service.register(uid, token="ExponentPushToken[iphone]", platform="ios", device="a")
            await service.register(uid, token="ExponentPushToken[android]", platform="android", device="b")

            provider = ExpoNotificationProvider(db)

            async def _tickets(messages):
                # Expo's own shape: one ticket per message, in order.
                return [
                    {"status": "ok", "id": "ticket-1"},
                    {"status": "error", "details": {"error": "DeviceNotRegistered"}},
                ]

            provider._post = _tickets  # noqa: SLF001

            result = await provider.send(
                owner_id=uid, plan_id="dlv_1", title="t", body="b", deep_link="/",
            )
            assert result["ok"] is True, "un token morto ha zittito tutto"
            assert result["provider_accepted"] == 1

            active = await service.endpoints(uid)
            assert len(active) == 1, "il dispositivo sano è stato disabilitato"

            disabled = await db.push_endpoints.find_one(
                {"owner_id": uid, "status": "disabled"}, {"_id": 0}
            )
            assert disabled["disabled_reason"] == "DeviceNotRegistered"
        finally:
            await db.push_endpoints.delete_many({"owner_id": uid})
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_delivered_notification_is_never_claimed_to_be_recallable():
    """§27: a plan can be cancelled; a phone that already buzzed cannot."""
    async def body():
        client, db = await _db()
        try:
            from ambient.push import ExpoNotificationProvider

            outcome = await ExpoNotificationProvider(db).cancel(
                owner_id="u", plan_id="dlv_1"
            )
            assert outcome["retracted"] is False
        finally:
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Whether anybody is looking
# ---------------------------------------------------------------------------

def test_stale_evidence_about_the_app_resolves_to_unknown(monkeypatch):
    """
    §33: a flag written forty minutes ago is not evidence anybody is here.

    Trusting it would silence notifications for somebody who left, which is
    the failure that looks like the system working.
    """
    async def body():
        client, db = await _db()
        uid = f"a38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.models import AppPresence
            from ambient.repository import AmbientRepository
            from ambient.service import AmbientService

            repo = AmbientRepository(db)
            stale = (datetime.now(timezone.utc) - timedelta(minutes=40)).isoformat()
            await repo.record_presence(AppPresence(
                owner_id=uid, state="foreground",
                last_foreground_at=stale, updated_at=stale,
            ))

            assert await AmbientService(db).app_state(uid) == "unknown"

            await AmbientService(db).record_app_state(uid, "foreground")
            assert await AmbientService(db).app_state(uid) == "foreground"
        finally:
            await db.app_presence.delete_many({"owner_id": uid})
            await _clean(db, uid)
            client.close()

    _run(body())


def test_being_in_the_app_and_being_at_home_are_different_facts():
    """§34: two models, two names, no blur."""
    from ambient.models import AppPresence

    fields = set(AppPresence.model_fields)
    for life in ("place", "latitude", "longitude", "role", "at_a_known_place"):
        assert life not in fields, f"la presenza nell'app conosce {life}"
    assert "last_foreground_at" in fields


# ---------------------------------------------------------------------------
# Proof of work
# ---------------------------------------------------------------------------

def test_a_background_review_leaves_a_real_trace(monkeypatch):
    """§42/§64: what a person reads on Home came from a wake that happened."""
    async def body():
        client, db = await _db()
        uid = f"a38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.models import AmbientWake
            from ambient.repository import AmbientRepository
            from ambient.runtime import tick
            from delivery.service import DeliveryService

            await AmbientRepository(db).ensure_indexes()
            await db.calendar_events.insert_one({
                "user_id": uid, "id": "evt_a", "title": "Cena",
                "start_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
                "all_day": False,
            })
            from opportunities.discovery import OpportunityDiscovery

            await OpportunityDiscovery(db).changes.record(
                uid, source="calendar", kind="event.updated", entity_ref="evt_a"
            )
            past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
            await AmbientRepository(db).schedule(AmbientWake(
                owner_id=uid, reason="ambient_review", scheduled_for=past
            ))

            _install(monkeypatch, FakeModel([
                {"opportunities": [], "reason_for_silence": "niente di nuovo"},
                {"worth_saying": True, "line": "Ho ricontrollato quello che stai seguendo."},
            ]))
            _provider(monkeypatch)

            done = await tick(db)
            assert done["completed"] == 1

            line = await DeliveryService(db).ambient_line(uid)
            assert line is not None
            assert line["text"] == "Ho ricontrollato quello che stai seguendo."

            written = await db.ambient_activity.find_one(
                {"owner_id": uid, "visibility": "ambient"}, {"_id": 0}
            )
            assert written["cognitive_provenance"]["written_from"], "nessuna provenienza"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_loop_being_alive_is_not_something_ora_did(monkeypatch):
    """
    §43: NO FAKE HEARTBEAT.

    Ticks with nothing to do must leave no trace at all — a record saying "ORA
    è attiva" would be the runtime reporting on itself, dressed as work.
    """
    async def body():
        client, db = await _db()
        uid = f"a38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.runtime import tick
            from delivery.service import DeliveryService

            _install(monkeypatch, FakeModel([{"worth_saying": True, "line": "Sono attiva."}]))

            # Counted across everybody, not just this test's user: a loop
            # inventing proof of work would not necessarily do it under the
            # id the test happens to be watching.
            before = await db.ambient_activity.count_documents({})
            for _ in range(5):
                await tick(db)
            after = await db.ambient_activity.count_documents({})

            assert after == before, "un tick vuoto ha lasciato una traccia"
            assert await DeliveryService(db).ambient_line(uid) is None
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Time is a fact
# ---------------------------------------------------------------------------

def test_the_passing_of_time_changes_the_fingerprint(monkeypatch):
    """
    §20/§21: nothing has to change for the meaning to change.

    An event two days away yesterday is tomorrow today, and a fingerprint
    built only from stored values would keep answering "nothing new" on the
    morning it started to matter.
    """
    async def body():
        client, db = await _db()
        uid = f"a38_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities import snapshot as life_snapshot
            from opportunities.changes import fingerprint

            when = datetime.now(timezone.utc) + timedelta(hours=30)
            await db.calendar_events.insert_one({
                "user_id": uid, "id": "evt_t", "title": "Appuntamento",
                "start_at": when.isoformat(), "all_day": False,
            })

            snap = await life_snapshot.build(db, uid)
            assert "temporal" in snap
            assert snap["temporal"]["minutes_to_next_commitment"] in (
                "today", "later", "within_four_hours"
            )
            first = fingerprint(snap)

            # The same life, later. Nothing stored has changed.
            drifted = dict(snap)
            drifted["temporal"] = dict(snap["temporal"])
            drifted["temporal"]["minutes_to_next_commitment"] = "within_the_hour"
            drifted["temporal"]["something_within_the_hour"] = True
            assert fingerprint(drifted) != first, (
                "il tempo passa e l'impronta non se ne accorge"
            )

            # And two identical moments still hash identically.
            assert fingerprint(dict(snap)) == first
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_temporal_facts_are_bands_and_not_a_clock():
    """A value precise to the minute would make every snapshot unique."""
    from opportunities.snapshot import _bucket

    assert _bucket(3) == _bucket(12) == "within_15_minutes"
    assert _bucket(41) == _bucket(43) == "within_the_hour"
    assert _bucket(None) is None
    assert _bucket(5000) == "later"


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


def test_the_runtime_cannot_reach_a_notification_on_its_own():
    """
    §70: WAKE != NOTIFY, structurally.

    The loop dispatches by reason and knows nothing else. If it could call a
    provider, a scheduler would be able to interrupt somebody — and no
    behavioural test would necessarily notice, because the notification would
    look exactly like a correct one.
    """
    runtime = _code_only(_source("ambient", "runtime.py"))
    for forbidden in ("get_provider", "send(", "PushEndpoint", "_ask_model", "reasoning"):
        assert forbidden not in runtime, f"il runtime conosce {forbidden}"

    # Dispatch only: the reasons it knows are the reasons, and nothing else.
    from ambient.models import AmbientWake
    import typing

    reasons = set(typing.get_args(AmbientWake.model_fields["reason"].annotation))
    assert reasons == {
        "state_changed", "delivery_recheck", "opportunity_revisit",
        "ambient_review", "retry",
    }
    for domain in ("flight", "bill", "document", "calendar", "home", "work"):
        assert not any(domain in r for r in reasons), f"un motivo conosce {domain}"


def test_no_wake_reason_or_schedule_is_derived_from_a_domain():
    """§3/§70: a scheduler that knows what a flight is has taken the judgement."""
    domains = {
        "calendar", "places", "presence", "documents", "document",
        "conversation", "comparison", "research", "flight", "bill",
    }
    for module in ("runtime.py", "service.py", "repository.py", "models.py"):
        tree = ast.parse(_source("ambient", module))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            if not any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
                continue
            for side in [node.left, *node.comparators]:
                if isinstance(side, ast.Constant) and isinstance(side.value, str):
                    assert side.value.strip().lower() not in domains, (
                        f"{module}:{node.lineno} decide in base a «{side.value}»"
                    )


def test_nothing_is_sent_without_a_fresh_judgement():
    """§12: every path from a wake to a send goes through evaluate()."""
    service = _code_only(_source("ambient", "service.py"))
    recheck = service.split("async def recheck_delivery")[1].split("async def")[0]
    assert "delivery.evaluate" in recheck, "il recheck non chiede di nuovo"
    for shortcut in ("_send", "get_provider", "provider.send"):
        assert shortcut not in recheck, f"il recheck invia direttamente: {shortcut}"


def test_a_token_is_never_logged():
    """§52: not in a log line, not in an exception, not anywhere."""
    push = _code_only(_source("ambient", "push.py"))
    for line in push.splitlines():
        if "logger." in line:
            assert "token" not in line.lower(), f"un token finisce nei log: {line.strip()}"

    router = _code_only(_source("ambient", "router.py"))
    assert "token" not in router.split("async def endpoints")[1].split("async def")[0]


def test_the_runtime_creates_no_work_and_executes_nothing():
    """§74."""
    for module in ("runtime.py", "service.py", "push.py", "repository.py"):
        code = _code_only(_source("ambient", module))
        for banned in (
            "action_engine", "execute_action", "attention_items",
            "work_items", "send_email", "calendar_events.insert",
        ):
            # `create_task` is deliberately absent: asyncio's is not the kind
            # of task this forbids, and a guard that cannot tell them apart
            # would be removed the first time it fired for the wrong reason.
            assert banned not in code, f"{module} fa {banned}"

        for write in ("insert_one", "update_one", "update_many", "delete_many"):
            for target in re.findall(rf"db\[?['\"]?(\w+)['\"]?\]?\.{write}", code):
                assert target in (
                    "ambient_wakes", "push_endpoints", "app_presence",
                    "WAKES", "ENDPOINTS", "PRESENCE",
                ), f"{module} scrive su {target}"


def test_the_runtime_is_off_unless_asked_for(monkeypatch):
    """A loop that starts itself in every test run will surprise somebody."""
    from ambient.runtime import runtime_enabled

    monkeypatch.delenv("AMBIENT_RUNTIME", raising=False)
    assert runtime_enabled() is False
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    assert runtime_enabled() is True


def test_the_application_lifecycle_owns_the_loop():
    """§9: start at startup, stop at shutdown, and never its own client."""
    server = _source("server.py")
    assert "start_runtime()" in server
    assert "stop_runtime()" in server

    runtime = _code_only(_source("ambient", "runtime.py"))
    assert "AsyncIOMotorClient" not in runtime, "il runtime apre una connessione sua"
    assert "from deps import db" in runtime


def test_expo_notifications_is_configured_without_native_folders():
    """§22/§72: CNG — the native project is derived, never committed."""
    import json

    frontend = HERE.parent / "frontend"
    package = json.loads((frontend / "package.json").read_text(encoding="utf-8"))
    assert package["dependencies"]["expo-notifications"].startswith("~0.32"), (
        "versione non allineata a Expo SDK 54"
    )

    app_config = json.loads((frontend / "app.json").read_text(encoding="utf-8"))
    plugins = [p[0] if isinstance(p, list) else p for p in app_config["expo"]["plugins"]]
    assert "expo-notifications" in plugins

    for native in ("android", "ios"):
        assert not (frontend / native).exists(), f"cartella nativa {native} nel repo"


def test_the_web_does_not_pretend_to_have_native_push():
    """§25: a browser asking for permission and registering nothing is theatre."""
    frontend = HERE.parent / "frontend"
    registration = (frontend / "src" / "ambient" / "pushRegistration.ts").read_text(
        encoding="utf-8"
    )
    assert "capability()" in registration
    assert "'unsupported'" in registration
    # And the token is never persisted on the device by us.
    for stored in ("AsyncStorage", "secureSet", "localStorage"):
        assert stored not in registration, f"il token finisce in {stored}"
