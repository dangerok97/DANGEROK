"""
V3.8 Sprint 1 — ambient presence, and whether an interruption is earned.

    ORA SHOULD FEEL ALIVE BECAUSE IT IS WORKING, NOT BECAUSE IT PRETENDS TO BE.
    INTERRUPTION MUST BE EARNED.
    NO NOTIFICATION IS A VALID DECISION.

Two claims are defended here.

The first is that ORA cannot say it did something it did not do. Every visible
ambient line has to trace back to a record written by work that ran, and the
tests that matter most are the ones asserting silence when nothing happened —
because a product that fills that gap with "sto monitorando" is lying quietly
and constantly, and nobody would ever file a bug about it.

The second is that a push is a decision nobody can reach by accident. There is
no path from `urgency == "high"`, from a front door, or from a card on Home to
a notification: each of those would be one plausible line in a diff, and each
would end the judgement this phase exists to make. Several tests here exist
only to fail the day somebody writes one.

The model is stubbed throughout. The two live QAs are run separately and
reported with an exact call count.
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
        "opportunities", "opportunity_decisions", "delivery_plans",
        "ambient_activity", "meaningful_changes", "opportunity_scan_state",
        "calendar_events", "life_places", "open_questions", "home_snapshots",
        "permission_grants", "users",
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
    # Each module binds the helper at import, so both homes are patched.
    import delivery.reasoning as delivery_reasoning
    import opportunities.reasoning as opportunity_reasoning

    monkeypatch.setattr(delivery_reasoning, "_ask_model", model)
    monkeypatch.setattr(opportunity_reasoning, "_ask_model", model)


class Provider:
    """A notification channel that records instead of sending."""

    name = "test"

    def __init__(self, ok=True):
        self.sent = []
        self.cancelled = []
        self.ok = ok

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        return {"ok": self.ok, "provider": self.name, "external_id": "test"}

    async def cancel(self, *, owner_id, plan_id):
        self.cancelled.append(plan_id)
        return {"ok": True}


def _provider(monkeypatch, ok=True) -> Provider:
    from delivery import provider as provider_module

    channel = Provider(ok=ok)
    monkeypatch.setattr(provider_module, "get_provider", lambda: channel)
    return channel


def _push(**over):
    answer = {
        "mode": "push",
        "timing": "now",
        "reason_to_interrupt": "L'ufficio chiude a mezzogiorno e il documento manca.",
        "reason_to_open": "Ti dico cosa serve portare e dove.",
        "copy_intent": "dire cosa manca e entro quando",
        "confidence": "strong",
        "sensitivity": "ordinary",
        "requires_recheck": True,
        "copy": {
            "title": "Manca un documento per domani",
            "body": "L'ufficio che lo rilascia è aperto solo stamattina.",
        },
    }
    answer.update(over)
    return answer


async def _allow_push(db, uid, allowed=True):
    """The permission the delivery layer reads, granted the way it is read."""
    import delivery.context as context_module

    async def _permission(_db, _uid, _now):
        return {"push": allowed}

    context_module._permission = _permission  # noqa: SLF001


async def _an_opportunity(db, uid, monkeypatch, **over):
    from opportunities.models import EvidenceRef, Opportunity
    from opportunities.repository import OpportunityRepository

    fields = {
        "owner_id": uid,
        "identity_key": f"cosa-{uuid.uuid4().hex[:6]}",
        "status": "active",
        "semantic_summary": "Manca il certificato per l'appuntamento di domani.",
        "why_it_matters": "Senza, l'appuntamento non si conclude.",
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


# ---------------------------------------------------------------------------
# Proof of work
# ---------------------------------------------------------------------------

def test_ora_cannot_say_it_did_something_it_did_not_do(monkeypatch):
    """
    §8/§46: the guard that keeps this whole layer honest.

    With nothing on file there is no line, and no amount of asking produces
    one. This is the branch a product under pressure to feel alive quietly
    removes, so it is asserted before anything else.
    """
    async def body():
        client, db = await _db()
        uid = f"d38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService

            model = FakeModel([{"worth_saying": True, "line": "Ho controllato tutto."}])
            _install(monkeypatch, model)
            service = DeliveryService(db)

            assert await service.ambient_line(uid) is None
            assert await service.summarise_recent(uid) is None
            assert model.seen == [], "ha chiesto una frase senza avere niente da dire"
            assert await service.ambient_line(uid) is None
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_visible_line_traces_back_to_work_that_ran(monkeypatch):
    """§6/§35: every visible sentence has provenance, even if nobody sees it."""
    async def body():
        client, db = await _db()
        uid = f"d38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService

            service = DeliveryService(db)
            await service.note_activity(
                uid,
                kind="review_completed",
                provenance={"changes_reviewed": 3, "raised": 0, "sources_unavailable": []},
            )
            _install(monkeypatch, FakeModel([{
                "worth_saying": True,
                "line": "Ho ricontrollato quello che stai seguendo: niente di nuovo.",
            }]))

            written = await service.summarise_recent(uid)
            assert written is not None
            assert written.visibility == "ambient"
            assert written.cognitive_provenance.get("written_from"), "nessuna provenienza"

            line = await service.ambient_line(uid)
            assert line["text"].startswith("Ho ricontrollato")
            # And the machine never reaches the screen.
            for leak in ("review_completed", "scan", "provenance", "visibility"):
                assert leak not in str(line)
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_review_that_could_not_see_everything_says_so(monkeypatch):
    """
    §34: "tutto tranquillo" is a claim, and a blind review cannot make it.

    The model is told which sources were unreachable, so the sentence it
    writes can be smaller than the one it would have written otherwise.
    """
    async def body():
        client, db = await _db()
        uid = f"d38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService

            service = DeliveryService(db)
            await service.note_activity(
                uid,
                kind="review_completed",
                provenance={"sources_unavailable": ["calendar", "places"]},
            )
            model = FakeModel([{
                "worth_saying": True,
                "line": "Ho ricontrollato quello che potevo verificare.",
            }])
            _install(monkeypatch, model)
            await service.summarise_recent(uid)

            asked = model.seen[0]["user"]
            assert "sources_it_could_not_check" in asked
            assert "calendar" in asked and "places" in asked

            # And the instructions say what that obliges it to do.
            told = model.seen[0]["system"]
            assert "tutto tranquillo" in told
            assert "sources could not be checked" in told
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_line_is_not_rewritten_every_few_minutes(monkeypatch):
    """A sentence that keeps changing reads as fidgeting, and costs a call each time."""
    async def body():
        client, db = await _db()
        uid = f"d38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService

            service = DeliveryService(db)
            await service.note_activity(uid, kind="review_completed", provenance={})
            model = FakeModel([
                {"worth_saying": True, "line": "Prima riga."},
                {"worth_saying": True, "line": "Seconda riga."},
            ])
            _install(monkeypatch, model)

            await service.summarise_recent(uid)
            await service.summarise_recent(uid)
            assert len(model.seen) == 1, "riscrive la riga a ogni passaggio"
            assert (await service.ambient_line(uid))["text"] == "Prima riga."
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_model_may_decide_a_line_is_not_worth_reading(monkeypatch):
    """A note that adds nothing is worse than no note."""
    async def body():
        client, db = await _db()
        uid = f"d38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService

            service = DeliveryService(db)
            await service.note_activity(uid, kind="review_completed", provenance={})
            _install(monkeypatch, FakeModel([{"worth_saying": False}]))

            assert await service.summarise_recent(uid) is None
            assert await service.ambient_line(uid) is None
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Four decisions, not four rungs
# ---------------------------------------------------------------------------

def test_the_model_can_choose_silence_and_nothing_happens(monkeypatch):
    """§40: real work, and still nothing said. The commonest correct outcome."""
    async def body():
        client, db = await _db()
        uid = f"d38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService

            opportunity = await _an_opportunity(db, uid, monkeypatch)
            channel = _provider(monkeypatch)
            _install(monkeypatch, FakeModel([{
                "mode": "silence",
                "reason_to_interrupt": "Non c'è niente da fare adesso.",
            }]))

            result = await DeliveryService(db).evaluate(uid, opportunity.id)
            assert result.mode == "silence"
            assert result.plan is None
            assert channel.sent == []
            assert await db.delivery_plans.count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_something_can_be_worth_a_screen_and_not_a_pocket(monkeypatch):
    """
    §5/§11: `push` is not the top of a ladder that starts at `in_app`.

    The same opportunity, judged twice, comes out differently — which is only
    possible because nothing derives one mode from another.
    """
    async def body():
        client, db = await _db()
        uid = f"d38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService

            opportunity = await _an_opportunity(db, uid, monkeypatch)
            channel = _provider(monkeypatch)
            await _allow_push(db, uid, True)
            service = DeliveryService(db)

            _install(monkeypatch, FakeModel([{
                "mode": "in_app",
                "reason_to_interrupt": "Vale la pena vederlo, non vale una notifica.",
            }]))
            first = await service.evaluate(uid, opportunity.id)
            assert first.mode == "in_app"
            assert channel.sent == []

            _install(monkeypatch, FakeModel([_push()]))
            second = await service.evaluate(uid, opportunity.id)
            assert second.mode == "push"
            assert len(channel.sent) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_push_carries_its_own_reason_and_lands_where_it_is_about(monkeypatch):
    """§13/§30: a notification that opens Home has thrown away what it knew."""
    async def body():
        client, db = await _db()
        uid = f"d38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService

            opportunity = await _an_opportunity(db, uid, monkeypatch)
            channel = _provider(monkeypatch)
            await _allow_push(db, uid, True)
            _install(monkeypatch, FakeModel([_push()]))

            result = await DeliveryService(db).evaluate(uid, opportunity.id)
            assert result.mode == "push"

            plan = result.plan
            assert plan.reason_to_open, "una push senza motivo per aprirla"
            assert plan.deep_link
            assert f"opportunityId={opportunity.id}" in plan.deep_link
            # The origin is preserved: a thread opened by an interruption is
            # not the same as one somebody chose to open.
            assert "entry=notification" in plan.deep_link

            sent = channel.sent[0]
            assert sent["title"] and sent["body"]
            assert sent["deep_link"] == plan.deep_link
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_judgement_to_wait_does_not_send_anything_yet(monkeypatch):
    """§16: `at` means at, and the moment has not arrived."""
    async def body():
        client, db = await _db()
        uid = f"d38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService

            opportunity = await _an_opportunity(db, uid, monkeypatch)
            channel = _provider(monkeypatch)
            await _allow_push(db, uid, True)
            later = (datetime.now(timezone.utc) + timedelta(hours=9)).isoformat()
            _install(monkeypatch, FakeModel([_push(timing="at", not_before=later)]))

            result = await DeliveryService(db).evaluate(uid, opportunity.id)
            assert result.mode == "push"
            assert result.plan.status == "pending"
            assert channel.sent == [], "ha inviato adesso qualcosa deciso per domani"

            # And nothing goes out when the due sweep runs before the moment.
            summary = await DeliveryService(db).deliver_due(uid)
            assert summary["sent"] == 0
            assert summary["held"] == 1
            assert channel.sent == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Recheck before delivery
# ---------------------------------------------------------------------------

def test_a_pending_push_is_re_examined_and_cancelled_if_the_reason_is_gone(monkeypatch):
    """
    §17/§44: the failure this whole design exists to prevent.

    The document arrives overnight. A notification decided yesterday and fired
    on a timer would ask about it at eight in the morning, and be wrong in the
    most memorable way a product can be wrong.
    """
    async def body():
        client, db = await _db()
        uid = f"d38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService
            from opportunities.repository import OpportunityRepository

            opportunity = await _an_opportunity(db, uid, monkeypatch)
            channel = _provider(monkeypatch)
            await _allow_push(db, uid, True)
            later = (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat()
            _install(monkeypatch, FakeModel([_push(timing="at", not_before=later)]))

            service = DeliveryService(db)
            result = await service.evaluate(uid, opportunity.id)
            plan_id = result.plan.id
            assert channel.sent == [], "ha inviato subito qualcosa deciso per dopo"

            # The fact changes overnight, and then the moment arrives.
            opportunity.status = "resolved"
            await OpportunityRepository(db).save(opportunity)
            await db.delivery_plans.update_one(
                {"id": plan_id},
                {"$set": {"not_before": (
                    datetime.now(timezone.utc) - timedelta(minutes=1)
                ).isoformat()}},
            )

            summary = await service.deliver_due(uid)
            assert summary["sent"] == 0
            assert summary["cancelled"] == 1
            assert channel.sent == [], "ha notificato una cosa già risolta"

            plan = await service.repo.get_plan(uid, plan_id)
            assert plan.status == "cancelled"
            assert plan.decision_provenance == "code_cancel"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_closing_an_opportunity_cancels_what_was_going_to_be_said(monkeypatch):
    """§31: a code guarantee, because there is nothing here to judge."""
    async def body():
        client, db = await _db()
        uid = f"d38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService
            from opportunities.service import OpportunityService

            opportunity = await _an_opportunity(db, uid, monkeypatch)
            channel = _provider(monkeypatch)
            await _allow_push(db, uid, True)
            later = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()
            _install(monkeypatch, FakeModel([_push(timing="at", not_before=later)]))

            service = DeliveryService(db)
            plan_id = (await service.evaluate(uid, opportunity.id)).plan.id

            # The person says no. The intention has to go with it.
            await OpportunityService(db).dismiss(uid, opportunity.id)

            plan = await service.repo.get_plan(uid, plan_id)
            assert plan.status == "cancelled"
            assert plan_id in channel.cancelled, "il canale non è stato avvisato"
            assert channel.sent == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_same_concern_re_evaluated_three_times_is_still_one_notification(monkeypatch):
    """§19/§45: three judgements about one thing, heard once."""
    async def body():
        client, db = await _db()
        uid = f"d38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService

            opportunity = await _an_opportunity(db, uid, monkeypatch)
            _provider(monkeypatch)
            await _allow_push(db, uid, True)
            later = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()

            service = DeliveryService(db)
            ids = set()
            for wording in ("primo", "secondo", "terzo"):
                _install(monkeypatch, FakeModel([
                    _push(timing="at", not_before=later, reason_to_open=wording)
                ]))
                result = await service.evaluate(uid, opportunity.id)
                ids.add(result.plan.id)

            assert len(ids) == 1, "tre valutazioni, tre notifiche"
            assert await db.delivery_plans.count_documents(
                {"owner_id": uid, "status": {"$in": ["pending", "held"]}}
            ) == 1
            # And it is the latest thinking, not the first.
            plan = await service.repo.open_plan_for(uid, opportunity.id)
            assert plan.reason_to_open == "terzo"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# What code holds
# ---------------------------------------------------------------------------

def test_without_permission_the_judgement_lands_on_the_screen(monkeypatch):
    """
    Permission is a fact about the channel, never a verdict on the content.

    Losing the substance because a phone setting is off would be worse than
    delivering it quietly, so the decision survives and changes address.
    """
    async def body():
        client, db = await _db()
        uid = f"d38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService

            opportunity = await _an_opportunity(db, uid, monkeypatch)
            channel = _provider(monkeypatch)
            await _allow_push(db, uid, False)
            _install(monkeypatch, FakeModel([_push()]))

            result = await DeliveryService(db).evaluate(uid, opportunity.id)
            assert result.mode == "in_app"
            assert result.blocked_by == "no_notification_permission"
            assert channel.sent == []
            assert result.plan.status == "held"
            assert result.plan.decision_provenance == "code_safety"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_burst_is_stopped_by_code_even_when_each_one_is_worth_it(monkeypatch):
    """
    §20/§21: a technical ceiling, not an opinion about relevance.

    The model sees the same history and usually stops long before here. This
    is what happens when it does not: three uninvited interruptions in an hour
    is a malfunction whatever each one was about.
    """
    async def body():
        client, db = await _db()
        uid = f"d38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService
            from delivery.service import MAX_PUSHES_PER_HOUR

            channel = _provider(monkeypatch)
            await _allow_push(db, uid, True)
            service = DeliveryService(db)

            now = datetime.now(timezone.utc)
            for minutes in (50, 40):
                await db.delivery_plans.insert_one({
                    "owner_id": uid, "id": f"dlv_old_{minutes}",
                    "opportunity_id": "other", "mode": "push", "status": "delivered",
                    "delivered_at": (now - timedelta(minutes=minutes)).isoformat(),
                    "created_at": now.isoformat(), "updated_at": now.isoformat(),
                })

            opportunity = await _an_opportunity(db, uid, monkeypatch)
            _install(monkeypatch, FakeModel([_push()]))
            result = await service.evaluate(uid, opportunity.id)

            assert MAX_PUSHES_PER_HOUR == 2
            assert result.blocked_by == "rate_limited"
            assert result.mode == "in_app"
            assert channel.sent == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_moment_that_has_passed_is_never_delivered_late(monkeypatch):
    """A notification that arrives too late to act on is worse than none."""
    async def body():
        client, db = await _db()
        uid = f"d38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService

            channel = _provider(monkeypatch)
            await _allow_push(db, uid, True)
            opportunity = await _an_opportunity(db, uid, monkeypatch)
            now = datetime.now(timezone.utc)
            await db.delivery_plans.insert_one({
                "owner_id": uid, "id": "dlv_stale", "opportunity_id": opportunity.id,
                "mode": "push", "status": "pending",
                "not_before": (now - timedelta(hours=3)).isoformat(),
                "not_after": (now - timedelta(hours=1)).isoformat(),
                "created_at": (now - timedelta(hours=4)).isoformat(),
                "updated_at": now.isoformat(),
            })

            summary = await DeliveryService(db).deliver_due(uid)
            assert summary["sent"] == 0
            assert channel.sent == []
            plan = await DeliveryService(db).repo.get_plan(uid, "dlv_stale")
            assert plan.status == "expired"
            assert plan.decision_provenance == "code_expiry"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Privacy
# ---------------------------------------------------------------------------

def test_a_lock_screen_gets_the_smaller_version(monkeypatch):
    """
    §36/§48: the phone shows this to whoever is holding it.

    Both versions are the same fact at two distances — never a decoy and never
    two different claims.
    """
    async def body():
        client, db = await _db()
        uid = f"d38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService

            opportunity = await _an_opportunity(db, uid, monkeypatch)
            channel = _provider(monkeypatch)
            await _allow_push(db, uid, True)
            _install(monkeypatch, FakeModel([_push(
                sensitivity="private",
                copy={
                    "title": "Risultati delle analisi di martedì",
                    "body": "Il referto di cardiologia è arrivato.",
                    "public_title": "C'è un aggiornamento per martedì",
                    "public_body": "Te lo mostro quando apri ORA.",
                },
            )]))

            result = await DeliveryService(db).evaluate(uid, opportunity.id)
            assert result.plan.sensitivity == "private"

            sent = channel.sent[0]
            assert sent["public_title"] == "C'è un aggiornamento per martedì"
            assert "cardiologia" not in sent["public_title"]
            assert "cardiologia" not in sent["public_body"]
            # The full version still exists, for once the phone is unlocked.
            assert "cardiologia" in sent["body"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_model_is_told_a_moment_and_never_a_life(monkeypatch):
    """No coordinates, no documents, no message bodies in the payload."""
    async def body():
        client, db = await _db()
        uid = f"d38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery import context as delivery_context

            await db.life_places.insert_one({
                "user_id": uid, "id": "plc_home", "label": "Casa", "role": "home",
                "role_confirmed_by_user": True, "status": "confirmed",
                "latitude": 45.4064, "longitude": 11.8768,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            moment = await delivery_context.build(db, uid)

            import json

            payload = json.dumps(moment, ensure_ascii=False, default=str)
            for leak in ("45.40", "11.87", "latitude", "longitude", "body", "content"):
                assert leak not in payload, f"il contesto porta {leak}"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# When the model is not there
# ---------------------------------------------------------------------------

def test_an_outage_invents_no_notification_and_no_silence(monkeypatch):
    """
    §47: an outage has no opinion.

    Nothing is sent, nothing is recorded as a decision to stay quiet, and no
    ambient line appears claiming a review happened.
    """
    async def body():
        client, db = await _db()
        uid = f"d38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService

            opportunity = await _an_opportunity(db, uid, monkeypatch)
            channel = _provider(monkeypatch)
            await _allow_push(db, uid, True)
            _install(monkeypatch, FakeModel([]))

            service = DeliveryService(db)
            result = await service.evaluate(uid, opportunity.id)

            assert result.unavailable is True
            assert result.mode == "silence"  # the default, not a conclusion
            assert result.plan is None
            assert channel.sent == []
            assert await db.delivery_plans.count_documents({"owner_id": uid}) == 0

            # And nothing claims work was described.
            await service.note_activity(uid, kind="review_completed", provenance={})
            assert await service.summarise_recent(uid) is None
            assert await service.ambient_line(uid) is None
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_channel_that_fails_holds_the_plan_rather_than_losing_it(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"d38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService

            opportunity = await _an_opportunity(db, uid, monkeypatch)
            _provider(monkeypatch, ok=False)
            await _allow_push(db, uid, True)
            _install(monkeypatch, FakeModel([_push()]))

            result = await DeliveryService(db).evaluate(uid, opportunity.id)
            plan = await DeliveryService(db).repo.get_plan(uid, result.plan.id)
            assert plan.status == "held"
            assert plan.delivered_at is None
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# What happened afterwards
# ---------------------------------------------------------------------------

def test_what_someone_did_with_a_notification_is_a_fact_and_not_a_score(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"d38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService

            opportunity = await _an_opportunity(db, uid, monkeypatch)
            _provider(monkeypatch)
            await _allow_push(db, uid, True)
            _install(monkeypatch, FakeModel([_push()]))

            service = DeliveryService(db)
            plan_id = (await service.evaluate(uid, opportunity.id)).plan.id

            outcome = await service.record_outcome(uid, plan_id, "opened")
            assert outcome["ok"] is True
            assert outcome["opportunity_id"] == opportunity.id

            plan = await service.repo.get_plan(uid, plan_id)
            assert plan.outcome == "opened"
            # A fact about what happened. Nothing was computed from it.
            for field in plan.model_dump():
                assert "score" not in field and "rate" not in field
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Structure — what a future diff must not be able to do quietly
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


def test_nothing_turns_a_word_or_a_place_into_a_notification():
    """
    §4/§52: the lines that must never exist.

    `if urgency == "high": push()` is one line, reads as sensible, and would
    end the judgement this phase is built on. So no branch anywhere in the
    delivery path may test a relevance word, an urgency word, or the name of
    a place — checked on the AST rather than by grepping prose.
    """
    forbidden = {
        "high", "urgent", "strong", "medium", "low", "soon",
        "casa", "home", "work", "ufficio",
    }
    for module in ("context.py", "service.py", "provider.py", "repository.py"):
        tree = ast.parse(_source("delivery", module))
        for node in ast.walk(tree):
            # Equality against one of these words is a rule. Membership
            # against the whole vocabulary — `x in ("weak", "reasonable",
            # "strong")` — is validating that the model answered in its own
            # contract, which is the opposite thing and has to stay allowed.
            if not isinstance(node, ast.Compare):
                continue
            if not any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
                continue
            for side in [node.left, *node.comparators]:
                if isinstance(side, ast.Constant) and isinstance(side.value, str):
                    assert side.value.strip().lower() not in forbidden, (
                        f"{module}:{node.lineno} decide in base a "
                        f"«{side.value}» — una regola, non un giudizio"
                    )


def test_a_push_can_only_exist_because_of_an_opportunity_the_model_judged():
    """§52: no push without an opportunity, and no push without a decision."""
    code = _code_only(_source("delivery", "service.py"))

    # Sending happens in exactly one place, and it is reached from a plan.
    assert code.count("get_provider().send") == 1
    body = code.split("async def _send")[1].split("async def")[0]
    assert "plan." in body

    # And a plan is only ever written after the model said `push`.
    evaluate = code.split("async def evaluate")[1].split("async def")[0]
    assert "decide_delivery" in evaluate
    # `ast.unparse` normalises quotes, so the comparison is matched by shape.
    assert re.search(r"decision\.mode\s*!=\s*['\"]push['\"]", evaluate), (
        "evaluate() non distingue push da tutto il resto"
    )


def test_delivery_creates_no_work_executes_nothing_and_writes_only_its_own():
    """§18/§19/§57."""
    for module in ("context.py", "service.py", "repository.py", "provider.py"):
        code = _code_only(_source("delivery", module))
        for banned in (
            "action_engine", "execute_action", "create_task", "attention_items",
            "work_items", "send_email", "calendar_events.insert",
        ):
            assert banned not in code, f"{module} fa {banned}"

        for write in ("insert_one", "update_one", "update_many", "delete_many"):
            for target in re.findall(rf"db\[?['\"]?(\w+)['\"]?\]?\.{write}", code):
                assert target in (
                    "delivery_plans", "ambient_activity", "PLANS", "ACTIVITY",
                ), f"{module} scrive su {target}"


def test_no_numeric_scoring_anywhere_in_the_judgement():
    """§3: words a person could argue with, never a number to tune."""
    from delivery.models import Confidence, DeliveryMode
    import typing

    assert set(typing.get_args(Confidence)) == {"weak", "reasonable", "strong"}
    assert set(typing.get_args(DeliveryMode)) == {
        "silence", "quiet_presence", "in_app", "push"
    }

    code = _code_only(_source("delivery", "service.py"))
    assert not re.search(r"\bscore\b|\bweight\b|interruption_cost|utility\s*=", code), (
        "è comparso un punteggio"
    )


def test_the_contract_forbids_dark_patterns():
    """
    §38/§39: no FOMO, no guilt, no streaks, no engagement for its own sake.

    Named in the prompt rather than filtered afterwards, because a system told
    only "be helpful" and rewarded for opens will find its way to «ti sei
    dimenticato di me» on its own.
    """
    prompt = _source("delivery", "reasoning.py")
    for required in (
        "You gain nothing from being opened",
        "no streak",
        "no retention",
        "fear of missing out",
        "misses them",
    ):
        assert required in prompt, f"il contratto non vieta: {required}"

    for banned in ("ti aspetta", "non perdere", "torna a trovarci", "streak bonus"):
        assert banned not in prompt.lower()


def test_the_reasoner_never_touches_a_notification_channel():
    """§24/§25: deciding and sending must not move together."""
    reasoning = _code_only(_source("delivery", "reasoning.py"))
    for channel in ("expo", "Notifications", "get_provider", "send("):
        assert channel not in reasoning, f"il ragionatore conosce {channel}"

    provider = _code_only(_source("delivery", "provider.py"))
    for judgement in ("decide", "_ask_model", "opportunity", "relevance"):
        assert judgement not in provider, f"il canale conosce {judgement}"


def test_a_deep_link_is_built_by_code_from_a_whitelist():
    """
    §39: a model may reason about where a tap should land, never write a URL.

    A URL from a model is a string that text from somebody else's document
    could have influenced, and it opens whatever it says. So the model picks
    a target by name and this builds the address — an unknown target and a
    malformed id both fall back to Home rather than to whatever was supplied.
    """
    from delivery.service import ALLOWED_TARGETS, _deep_link

    link = _deep_link("opp_abc123")
    assert "opp_abc123" in link
    assert "entry=notification" in link, "l'origine non è preservata"
    assert link.startswith("/ora")

    # A target nobody offered.
    assert _deep_link("opp_abc123", target="https://altrove.example") == "/"
    # An id that is not one of ours.
    assert _deep_link("../../admin") == "/"
    assert _deep_link("javascript:alert(1)") == "/"

    for template in ALLOWED_TARGETS.values():
        assert template.startswith("/"), "una destinazione esce dall'app"


def test_home_reads_the_line_and_never_writes_one():
    """§9: a screen that could create its own evidence would."""
    service = _code_only(_source("home", "service.py"))
    assert "ambient_line(" in service
    for forbidden in ("note_activity", "summarise_recent", "record_activity"):
        assert forbidden not in service, f"Home fabbrica presenza: {forbidden}"

    frontend = HERE.parent / "frontend"
    chrome = (frontend / "src" / "components" / "home" / "v3" / "HomeChrome.tsx").read_text(
        encoding="utf-8"
    )
    # The line exists only when the backend sent one.
    assert "ambient?.text ?" in chrome
    for invented in ("Sto lavorando", "Sto monitorando", "Ho controllato tutto"):
        assert invented not in chrome, f"copy inventata nel componente: {invented}"


def test_there_is_no_tab_and_no_activity_dashboard():
    """§57: ambient presence is a line, not a place to visit."""
    frontend = HERE.parent / "frontend"
    layout = (frontend / "app" / "(tabs)" / "_layout.tsx").read_text(encoding="utf-8")
    # The tab names, not every word in the file: `useAmbientInset` is the
    # shell's own spacing helper and has nothing to do with this.
    tabs = re.findall(r'name="([^"]+)"', layout)
    for tab in tabs:
        assert not any(
            word in tab.lower() for word in ("ambient", "notific", "delivery", "attivit\u00e0 di ora")
        ), f"è comparsa una tab: {tab}"

    routes = [
        p.name for p in (frontend / "app").rglob("*.tsx")
        if any(w in p.name.lower() for w in ("ambient", "delivery", "notification"))
    ]
    assert not routes, f"è comparsa una schermata dedicata: {routes}"
