"""
V3.7 Sprint 2 — continuous discovery, and a quiet place to meet it.

    A CHANGE EARNS A REVIEW, NOT ATTENTION.
    SURFACE != NOTIFY.

Two things are being defended here, and they are different.

The first is that no domain can turn an event into a card. A calendar edit, a
front door, an uploaded file: each one buys a review, and the review is free to
say nothing, which is what it says most of the time. Several of these tests
exist to fail loudly the day somebody adds `if calendar_changed: create(...)`,
because that line would be invisible in a diff and fatal to the whole idea.

The second is that being true does not earn a place on somebody's screen. The
surfacing decision is a second judgement, made by the model, with its own
reasons — and code holds only what code can hold: how many fit, in what order,
and the timestamps that make "already shown" a fact.

The model is stubbed everywhere except the two live QAs, which are run
separately and reported. These tests never reach a provider.
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

import _loop_harness  # tests/_loop_harness.py: the one place a loop is chosen

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
        "opportunities", "opportunity_decisions", "meaningful_changes",
        "opportunity_scan_state", "calendar_events", "open_questions",
        "life_places", "presence_states", "presence_sessions", "home_snapshots",
        "comparison_runs", "observed_routines",
    ):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


class FakeModel:
    """The model, saying what a test needs it to say."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.seen = []

    async def __call__(self, system, user):
        self.seen.append({"system": system, "user": user})
        return self.answers.pop(0) if self.answers else None


def _install(monkeypatch, model):
    # Bound into the module at import: patching the shared helper's home would
    # leave this one pointing at the real provider.
    import opportunities.reasoning as reasoning

    monkeypatch.setattr(reasoning, "_ask_model", model)


def _silence(reason="niente di rilevante"):
    return {"opportunities": [], "reason_for_silence": reason}


def _raised(identity, refs, **over):
    out = {
        "identity_key": identity,
        "what": "Manca il documento per l'appuntamento.",
        "why_it_matters": "Senza quel documento l'appuntamento non si può fare.",
        "why_now": "È fra due giorni e l'ufficio apre solo la mattina.",
        "relevance": "high",
        "urgency": "soon",
        "time_sensitivity": "perishable",
        "confidence": "reasonable",
        "evidence_refs": list(refs),
    }
    out.update(over)
    return out


def _decisions(*pairs):
    return {
        "decisions": [
            {"id": oid, "decision": word, "rationale": "perché sì"}
            for oid, word in pairs
        ]
    }


async def _seed_event(db, uid, *, title="Appuntamento in comune", days=2):
    ref = f"evt_{uuid.uuid4().hex[:8]}"
    when = datetime.now(timezone.utc) + timedelta(days=days)
    await db.calendar_events.insert_one(
        {
            "user_id": uid, "id": ref, "title": title,
            "start_at": when.isoformat(),
            "end_at": (when + timedelta(hours=1)).isoformat(),
            "all_day": False,
        }
    )
    return ref


# ---------------------------------------------------------------------------
# What a domain is allowed to say
# ---------------------------------------------------------------------------

def test_a_change_carries_facts_and_has_no_way_to_say_it_matters():
    """
    §2: the envelope is anaemic on purpose.

    There is no field for urgency, no field for relevance, no boolean that
    means "this one is important" — so a domain that wanted to insist has
    nowhere to write it. That absence is the design, which is why it is
    asserted rather than assumed.
    """
    from opportunities.changes import MeaningfulChange

    fields = set(MeaningfulChange.model_fields)
    for forbidden in (
        "urgency", "relevance", "importance", "priority", "score",
        "opportunity", "notify", "action", "confidence",
    ):
        assert forbidden not in fields, f"un dominio potrebbe dichiarare {forbidden}"


def test_a_domain_cannot_invent_a_kind_that_means_something(monkeypatch):
    """A vocabulary fixed in one place is a vocabulary nobody can extend quietly."""
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.changes import ChangeLog

            log = ChangeLog(db)
            good = await log.record(uid, source="calendar", kind="event.updated")
            assert good.outcome == "accepted"

            invented = await log.record(uid, source="calendar", kind="event.is_urgent")
            assert invented.outcome == "rejected"

            unknown = await log.record(uid, source="marketing", kind="offer.available")
            assert unknown.outcome == "rejected"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Not asking the same question twice
# ---------------------------------------------------------------------------

def test_the_same_news_twice_is_one_piece_of_news(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.changes import ChangeLog

            log = ChangeLog(db)
            first = await log.record(
                uid, source="documents", kind="document.added", entity_ref="doc_1"
            )
            second = await log.record(
                uid, source="documents", kind="document.added", entity_ref="doc_1"
            )
            assert first.outcome == "accepted"
            assert second.outcome == "duplicate"
            assert len(await log.pending(uid)) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_one_thing_edited_eight_times_is_one_review(monkeypatch):
    """
    §4: coalescing.

    Somebody dragging an event around their calendar produces a burst. Each
    edit is genuinely different — so none of them is a duplicate — and asking
    the model eight times about eight versions of the same afternoon would be
    both expensive and worse than asking once about the last one.
    """
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.changes import ChangeLog

            log = ChangeLog(db)
            outcomes = []
            for hour in range(8):
                r = await log.record(
                    uid, source="calendar", kind="event.updated",
                    entity_ref="evt_same", after=f"spostato alle {9 + hour}",
                )
                outcomes.append(r.outcome)

            assert outcomes[0] == "accepted"
            assert set(outcomes[1:]) == {"coalesced"}

            batch = await log.claim(uid, "scn_test")
            # One claim takes the lot: one question, eight facts.
            assert len(batch) == 8
            assert not await log.pending(uid)
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_news_about_a_world_already_reviewed_is_not_news(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.changes import ChangeLog

            old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
            result = await ChangeLog(db).record(
                uid, source="calendar", kind="event.updated", occurred_at=old
            )
            assert result.outcome == "stale"
            assert not await ChangeLog(db).pending(uid)
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_nothing_pending_costs_nothing(monkeypatch):
    """The commonest case of all: a life where nothing moved."""
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.discovery import OpportunityDiscovery

            model = FakeModel([_silence()])
            _install(monkeypatch, model)

            outcome = await OpportunityDiscovery(db).review(uid)
            assert outcome.ran is False
            assert outcome.skipped
            assert model.seen == [], "ha chiesto al modello per niente"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_same_facts_are_not_put_to_the_model_twice(monkeypatch):
    """
    §30: a fingerprint is a way of saving money, never a judgement.

    Something moved, so there is a change to review — but the facts a scan
    would be shown are the ones it read last time, so the answer is already
    known. The change is consumed and no call is made.
    """
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.discovery import OpportunityDiscovery
            import opportunities.discovery as disc

            monkeypatch.setattr(disc, "COOLDOWN_SECONDS", 0)
            await _seed_event(db, uid)
            model = FakeModel([_silence(), _silence()])
            _install(monkeypatch, model)

            d = OpportunityDiscovery(db)
            await d.changes.record(uid, source="calendar", kind="event.updated")
            first = await d.review(uid)
            assert first.ran is True
            assert len(model.seen) == 1

            # Something moves again, but nothing a scan would see is different.
            await d.changes.record(
                uid, source="documents", kind="document.added", entity_ref="doc_x"
            )
            second = await d.review(uid)
            assert second.ran is False
            assert "stessi" in second.skipped
            assert len(model.seen) == 1, "ha ripetuto la stessa domanda"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_burst_does_not_become_a_burst_of_questions(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.discovery import OpportunityDiscovery

            await _seed_event(db, uid)
            model = FakeModel([_silence(), _silence()])
            _install(monkeypatch, model)

            d = OpportunityDiscovery(db)
            await d.changes.record(uid, source="calendar", kind="event.updated")
            assert (await d.review(uid)).ran is True

            await d.changes.record(
                uid, source="conversation", kind="intent.changed", entity_ref="i_1"
            )
            held = await d.review(uid)
            assert held.ran is False
            assert "appena" in held.skipped
            # And it is held, not lost: the next review still finds it.
            assert len(await d.changes.pending(uid)) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# QA B — three changes, one review
# ---------------------------------------------------------------------------

def test_three_things_moving_together_are_one_question(monkeypatch):
    """§36: calendar, document and conversation → one call, three facts."""
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.discovery import OpportunityDiscovery

            await _seed_event(db, uid)
            model = FakeModel([_silence("niente di concreto")])
            _install(monkeypatch, model)

            d = OpportunityDiscovery(db)
            await d.changes.record(uid, source="calendar", kind="event.updated", entity_ref="e1")
            await d.changes.record(uid, source="documents", kind="document.added", entity_ref="d1")
            await d.changes.record(
                uid, source="conversation", kind="open_question.settled", entity_ref="q1"
            )

            outcome = await d.review(uid)
            assert outcome.ran is True
            assert outcome.changes_reviewed == 3
            assert len(model.seen) == 1, "una revisione, non tre"

            # All three reached the model, as facts and nothing more.
            asked = model.seen[0]["user"]
            assert "calendar:event.updated" in asked
            assert "documents:document.added" in asked
            assert "conversation:open_question.settled" in asked
            assert outcome.scan.silence is True
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# QA A, C — a change is not a card
# ---------------------------------------------------------------------------

def test_a_calendar_change_with_no_consequence_says_nothing(monkeypatch):
    """§25/§35: calendar change → review → silence. No record, no card."""
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.discovery import OpportunityDiscovery
            from opportunities.surfacing import SurfacingService

            await _seed_event(db, uid, title="Cena con Marco", days=3)
            _install(monkeypatch, FakeModel([_silence("nessuna conseguenza")]))

            d = OpportunityDiscovery(db)
            await d.changes.record(uid, source="calendar", kind="event.updated")
            outcome = await d.review(uid)

            assert outcome.ran is True
            assert outcome.scan.silence is True
            assert await db.opportunities.count_documents({"owner_id": uid}) == 0
            assert await SurfacingService(db).for_home(uid) == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_walking_through_your_own_front_door_produces_nothing(monkeypatch):
    """
    §26/§37: presence is context, and context is not a reason.

    Arriving home is the single most tempting trigger in the product and the
    one that would make ORA feel like it is watching. It earns a review like
    anything else, and on its own the review has nothing to say.
    """
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.discovery import OpportunityDiscovery
            from opportunities.surfacing import SurfacingService

            await db.life_places.insert_one({
                "user_id": uid, "id": "plc_home", "label": "Casa", "role": "home",
                "role_confirmed_by_user": True, "status": "confirmed",
                "latitude": 45.4, "longitude": 11.8,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            _install(monkeypatch, FakeModel([_silence("essere a casa non è un motivo")]))

            d = OpportunityDiscovery(db)
            noted = await d.changes.record(
                uid, source="places", kind="presence.changed",
                entity_ref="plc_home", after="arrivato",
            )
            assert noted.outcome == "accepted"

            outcome = await d.review(uid)
            assert outcome.scan.silence is True
            assert await db.opportunities.count_documents({"owner_id": uid}) == 0
            assert await SurfacingService(db).for_home(uid) == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# QA D — raised, then shown
# ---------------------------------------------------------------------------

def test_something_real_is_raised_and_then_separately_decided_to_be_shown(monkeypatch):
    """§38: two judgements, in order, neither one implying the other."""
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.discovery import OpportunityDiscovery
            from opportunities.surfacing import SurfacingService

            ref = await _seed_event(db, uid)
            model = FakeModel([{"opportunities": [_raised("documento-appuntamento", [ref])]}])
            _install(monkeypatch, model)

            d = OpportunityDiscovery(db)
            await d.changes.record(uid, source="calendar", kind="event.added", entity_ref=ref)
            outcome = await d.review(uid)
            assert len(outcome.scan.created) == 1
            raised_id = outcome.scan.created[0].id

            # Raised is not shown. Nothing is on Home yet.
            surfacing = SurfacingService(db)
            assert await surfacing.for_home(uid) == []

            _install(monkeypatch, FakeModel([_decisions((raised_id, "surface"))]))
            result = await surfacing.decide(uid)
            assert result["decided"] == 1

            cards = await surfacing.for_home(uid)
            assert len(cards) == 1
            assert cards[0]["title"] == "Manca il documento per l'appuntamento."
            assert cards[0]["why_now"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_card_shows_a_sentence_and_never_the_words_the_system_thinks_in(monkeypatch):
    """
    §10: NEVER EXPOSE IMPLEMENTATION STATE WHEN A HUMAN STATE EXISTS.

    Checked on the payload rather than in the component, because a screen can
    only render what it was given: if `urgency` never leaves the backend, no
    future card can accidentally show it.
    """
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.service import OpportunityService
            from opportunities.surfacing import SurfacingService

            ref = await _seed_event(db, uid)
            _install(monkeypatch, FakeModel([{"opportunities": [_raised("doc-app", [ref])]}]))
            created = (await OpportunityService(db).scan(uid)).created
            _install(monkeypatch, FakeModel([_decisions((created[0].id, "surface"))]))
            await SurfacingService(db).decide(uid)

            import json

            payload = json.dumps(await SurfacingService(db).for_home(uid), ensure_ascii=False)
            for leak in (
                "relevance", "urgency", "confidence", "identity_key",
                "candidate", "time_sensitivity", "surface_state", "high",
                "strong", "perishable",
            ):
                assert leak not in payload, f"la card mostrerebbe {leak}"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_home_stays_quiet_when_more_things_deserve_space(monkeypatch):
    """
    §44/§22: the model chooses which, code decides how many.

    Four surface-worthy things is the case that turns a home into a dashboard.
    The model is allowed to want all four; the limit is not its decision.
    """
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.service import OpportunityService
            from opportunities.surfacing import MAX_VISIBLE, SurfacingService

            refs = [await _seed_event(db, uid, title=f"Cosa {i}", days=2 + i) for i in range(4)]
            _install(
                monkeypatch,
                FakeModel([{
                    "opportunities": [
                        _raised(f"cosa-{i}", [refs[i]], what=f"Cosa numero {i}.")
                        for i in range(4)
                    ]
                }]),
            )
            # The scan itself is bounded too, so raise them in two passes.
            svc = OpportunityService(db)
            created = list((await svc.scan(uid)).created)
            _install(
                monkeypatch,
                FakeModel([{
                    "opportunities": [
                        _raised(f"cosa-{i}", [refs[i]], what=f"Cosa numero {i}.")
                        for i in range(3, 4)
                    ]
                }]),
            )
            created += list((await svc.scan(uid)).created)
            assert len(created) == 4

            surfacing = SurfacingService(db)
            _install(
                monkeypatch,
                FakeModel([_decisions(*[(o.id, "surface") for o in created])]),
            )
            result = await surfacing.decide(uid)
            assert result["decided"] == 4, "il modello le ha volute tutte e quattro"

            cards = await surfacing.for_home(uid)
            assert len(cards) == MAX_VISIBLE <= 2, "Home è diventata una lista"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_model_may_hold_something_it_believes(monkeypatch):
    """§15/§16: a valid opportunity that is the wrong thing to say right now."""
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.service import OpportunityService
            from opportunities.surfacing import SurfacingService

            ref = await _seed_event(db, uid)
            _install(monkeypatch, FakeModel([{"opportunities": [_raised("doc-app", [ref])]}]))
            created = (await OpportunityService(db).scan(uid)).created
            assert created[0].relevance == "high"

            _install(monkeypatch, FakeModel([{
                "decisions": [{
                    "id": created[0].id, "decision": "hold",
                    "rationale": "sta già gestendo altro",
                }]
            }]))
            surfacing = SurfacingService(db)
            await surfacing.decide(uid)

            assert await surfacing.for_home(uid) == [], "high è diventato una regola"
            stored = await surfacing.repo.get(uid, created[0].id)
            # Held, not closed: still true, still active, simply not now.
            assert stored.status == "active"
            assert stored.surface_state == "held"
            assert stored.surface_rationale
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# QA E, F — what a person does about it
# ---------------------------------------------------------------------------

def test_not_interested_takes_it_off_the_screen_and_out_of_the_scan(monkeypatch):
    """§39: the card goes, and the concern does not come back."""
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.service import OpportunityService
            from opportunities.surfacing import SurfacingService

            ref = await _seed_event(db, uid)
            _install(monkeypatch, FakeModel([{"opportunities": [_raised("doc-app", [ref])]}]))
            svc = OpportunityService(db)
            created = (await svc.scan(uid)).created
            _install(monkeypatch, FakeModel([_decisions((created[0].id, "surface"))]))
            surfacing = SurfacingService(db)
            await surfacing.decide(uid)
            assert len(await surfacing.for_home(uid)) == 1

            await svc.dismiss(uid, created[0].id)
            assert await surfacing.for_home(uid) == [], "la card è rimasta"

            # And a scan on the same facts does not raise it again.
            _install(monkeypatch, FakeModel([{"opportunities": [_raised("doc-app", [ref])]}]))
            again = await svc.scan(uid)
            assert not again.created
            assert await db.opportunities.count_documents({"owner_id": uid}) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_later_hides_the_card_and_settles_nothing(monkeypatch):
    """
    §14/§40: "Più tardi" is not a reminder.

    Nothing is scheduled, nobody will be told anything at a chosen hour, and
    the concern is exactly as true afterwards as before. All that changed is
    that it stopped taking up room.
    """
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.service import OpportunityService
            from opportunities.surfacing import SurfacingService

            ref = await _seed_event(db, uid)
            _install(monkeypatch, FakeModel([{"opportunities": [_raised("doc-app", [ref])]}]))
            created = (await OpportunityService(db).scan(uid)).created
            _install(monkeypatch, FakeModel([_decisions((created[0].id, "surface"))]))
            surfacing = SurfacingService(db)
            await surfacing.decide(uid)

            _install(monkeypatch, FakeModel([{
                "revisit_in_hours": 18, "rationale": "l'ufficio riapre domani",
                "confidence": "reasonable",
            }]))
            result = await surfacing.defer(uid, created[0].id)
            assert result["ok"] is True
            assert await surfacing.for_home(uid) == []

            stored = await surfacing.repo.get(uid, created[0].id)
            assert stored.status == "active", "rimandare l'ha chiusa"
            assert stored.deferred_until

            # No decision was recorded either: nobody decided anything.
            assert await surfacing.repo.decisions_for(uid, created[0].id) == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_same_card_does_not_look_new_every_morning(monkeypatch):
    """§23/§24: shown once is a fact, and the model is told it."""
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.service import OpportunityService
            from opportunities.surfacing import SurfacingService

            ref = await _seed_event(db, uid)
            _install(monkeypatch, FakeModel([{"opportunities": [_raised("doc-app", [ref])]}]))
            created = (await OpportunityService(db).scan(uid)).created
            oid = created[0].id

            surfacing = SurfacingService(db)
            _install(monkeypatch, FakeModel([_decisions((oid, "surface"))]))
            await surfacing.decide(uid)
            await surfacing.mark_seen(uid, oid)

            model = FakeModel([_decisions((oid, "hold"))])
            _install(monkeypatch, model)
            await surfacing.decide(uid)

            asked = model.seen[0]["user"]
            assert '"times_shown": 1' in asked or '"times_shown":1' in asked
            assert "already_seen" in asked

            stored = await surfacing.repo.get(uid, oid)
            assert stored.seen_at
            assert stored.surfaced_count == 1, "restare visibile conta come nuova apparizione"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# QA H — the fact changes
# ---------------------------------------------------------------------------

def test_when_the_reason_is_gone_the_card_goes_with_it(monkeypatch):
    """§42: resolved by a review, removed from Home, not duplicated."""
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.service import OpportunityService
            from opportunities.surfacing import SurfacingService

            ref = await _seed_event(db, uid)
            _install(monkeypatch, FakeModel([{"opportunities": [_raised("doc-app", [ref])]}]))
            svc = OpportunityService(db)
            created = (await svc.scan(uid)).created
            _install(monkeypatch, FakeModel([_decisions((created[0].id, "surface"))]))
            surfacing = SurfacingService(db)
            await surfacing.decide(uid)
            assert len(await surfacing.for_home(uid)) == 1

            _install(monkeypatch, FakeModel([{
                "outcome": "resolve", "rationale": "il documento è stato trovato",
            }]))
            await svc.review(uid, created[0].id)

            assert await surfacing.for_home(uid) == []
            assert await db.opportunities.count_documents({"owner_id": uid}) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# QA I — the model is not there
# ---------------------------------------------------------------------------

def test_an_outage_invents_nothing_and_loses_nothing(monkeypatch):
    """
    §43/§31: a network error is not a judgement in either direction.

    Nothing is raised, no card appears, and — the part that is easy to get
    wrong — the change is still pending afterwards. Marking it consumed would
    turn "we never looked" into "we looked and there was nothing", which is a
    lie the next review would inherit.
    """
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.discovery import OpportunityDiscovery
            from opportunities.surfacing import SurfacingService

            await _seed_event(db, uid)
            _install(monkeypatch, FakeModel([]))  # every call returns None

            d = OpportunityDiscovery(db)
            await d.changes.record(uid, source="calendar", kind="event.added")
            outcome = await d.review(uid)

            assert outcome.ran is True
            assert outcome.unavailable is True
            assert outcome.scan.silence is True and outcome.scan.unavailable is True
            assert await db.opportunities.count_documents({"owner_id": uid}) == 0
            assert await SurfacingService(db).for_home(uid) == []
            assert len(await d.changes.pending(uid)) == 1, "il cambiamento è andato perso"

            # And the fingerprint was not stored, so the retry really retries.
            state = await db.opportunity_scan_state.find_one({"owner_id": uid}) or {}
            assert not state.get("fingerprint")
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_outage_in_surfacing_leaves_the_screen_exactly_as_it_was(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.service import OpportunityService
            from opportunities.surfacing import SurfacingService

            ref = await _seed_event(db, uid)
            _install(monkeypatch, FakeModel([{"opportunities": [_raised("doc-app", [ref])]}]))
            created = (await OpportunityService(db).scan(uid)).created
            surfacing = SurfacingService(db)
            _install(monkeypatch, FakeModel([_decisions((created[0].id, "surface"))]))
            await surfacing.decide(uid)
            before = await surfacing.for_home(uid)

            _install(monkeypatch, FakeModel([]))
            result = await surfacing.decide(uid)
            assert result["unavailable"] is True
            assert result["decided"] == 0
            assert await surfacing.for_home(uid) == before
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Structure — the things a future diff must not be able to do quietly
# ---------------------------------------------------------------------------

def _source(*parts) -> str:
    return (HERE.joinpath(*parts)).read_text(encoding="utf-8")


def _code_only(text: str) -> str:
    """Strip docstrings and comments: a guard must read code, not prose."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                node.body = node.body[1:]
    stripped = ast.unparse(tree)
    return "\n".join(
        line.split("#")[0] if not line.strip().startswith("#") else ""
        for line in stripped.splitlines()
    )


def test_no_domain_can_turn_an_event_into_an_opportunity():
    """
    §1/§47: the line that must never exist.

    `if calendar_changed: create_opportunity()` is one line, reads as helpful,
    and would quietly end AI-first proactivity. Nothing in the discovery path
    may name a domain and act on it, and nothing outside `opportunities/` may
    reach the writing side at all.
    """
    domains = {
        "calendar", "places", "presence", "documents", "document",
        "conversation", "comparison", "research", "work",
    }

    for module in ("changes.py", "discovery.py", "surfacing.py"):
        tree = ast.parse(_source("opportunities", module))
        for node in ast.walk(tree):
            # Every branch in the discovery path, including the one-line kind.
            test = getattr(node, "test", None) if isinstance(node, (ast.If, ast.IfExp)) else None
            if test is None:
                continue
            for inner in ast.walk(test):
                if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                    assert inner.value.split(".")[0].split(":")[0] not in domains, (
                        f"{module}:{node.lineno} decide in base al dominio "
                        f"«{inner.value}» — un trigger, non un giudizio"
                    )

    # The vocabulary itself is data, not a branch: the names may be listed
    # (a domain has to be able to say which words it owns) but never tested.
    from opportunities.changes import KNOWN_SOURCES

    assert domains.issuperset(KNOWN_SOURCES), "un dominio non dichiarato"

    # Only the opportunities package writes opportunities. Elsewhere the
    # repository may be reached for exactly one thing — creating its indexes at
    # boot — and any other call is a domain deciding what somebody should hear.
    for path in HERE.rglob("*.py"):
        if "opportunities" in path.parts or "tests" in path.parts or "scripts" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for call in re.findall(r"OpportunityRepository\([^)]*\)\.(\w+)", text):
            # Reading is fine and necessary — the delivery layer has to know
            # whether a concern is still open before saying anything about it.
            # Writing is what belongs to the package that owns the judgement.
            assert call in (
                "ensure_indexes", "get", "list", "by_identity", "decisions_for",
            ), f"{path.name} scrive opportunity: repo.{call}"
        for call in re.findall(r"OpportunityService\([^)]*\)\.(\w+)", text):
            # `resolve` is the one sanctioned write from outside: a goal that
            # reaches its outcome settles the concern it grew out of (V3.9
            # §32). Everything else — raising, dismissing, reviewing — stays
            # inside the package that owns the judgement.
            assert call in ("list_active", "resolve"), (
                f"{path.name} chiama service.{call}"
            )


def test_a_change_can_never_reach_a_screen_without_a_judgement():
    """
    Every path from a change to a card goes through the model, twice.

    Structural because it is invisible at runtime: a `note()` that surfaced
    something directly would pass every behavioural test in this file by
    producing the right card for the wrong reason.
    """
    changes = _code_only(_source("opportunities", "changes.py"))
    for forbidden in ("SurfacingService", "surface", "for_home", "notify"):
        assert forbidden not in changes, f"changes.py conosce {forbidden}"

    discovery = _code_only(_source("opportunities", "discovery.py"))
    # Discovery may start a scan and may ask the existing scheduler to wake up.
    # What it may not do is talk to the model itself or decide what a scan
    # concluded — those belong to the service and to the model respectively.
    assert "opportunities.reasoning" not in discovery, "discovery parla al modello"
    assert "_ask_model" not in discovery
    assert "silence=True" not in discovery, "discovery decide il silenzio"


def test_nothing_here_notifies_creates_work_or_acts():
    """§17/§18/§19: three things V3.7 does not do."""
    for module in ("changes.py", "discovery.py", "surfacing.py", "service.py"):
        code = _code_only(_source("opportunities", module))
        for forbidden in (
            "push_notification", "send_notification", "expo.dev",
            "action_engine", "execute_action", "create_task",
            "attention_items", "work_items",
        ):
            assert forbidden not in code, f"{module} fa {forbidden}"

        for write in ("insert_one", "update_one", "update_many", "delete_many"):
            for owned in re.findall(rf"db\[?['\"]?(\w+)['\"]?\]?\.{write}", code):
                assert owned in (
                    "opportunities", "opportunity_decisions", "meaningful_changes",
                    "opportunity_scan_state", "col", "COLLECTION", "STATE",
                    "OPPORTUNITIES", "DECISIONS",
                ), f"{module} scrive su {owned}"


def test_surfacing_is_not_a_threshold_in_disguise():
    """
    §15: no `if relevance == "high": show`.

    The judgement is the model's, and the moment code maps a word to a
    decision it has taken it back — quietly, and in a way no behavioural test
    would notice until somebody's home filled up.
    """
    code = _code_only(_source("opportunities", "surfacing.py"))
    for banned in ('"high"', "'high'", '"urgent"', "'urgent'", '"strong"', "'strong'"):
        assert banned not in code, f"surfacing.py decide in base a {banned}"
    assert not re.search(r"score|weight|points|rank\s*=", code), "è comparso un punteggio"


def test_the_wake_up_is_the_existing_one():
    """§5: no second orchestrator."""
    discovery = _source("opportunities", "discovery.py")
    assert "schedule_user_reasoning" in discovery
    for own in ("asyncio.Queue", "while True", "create_task", "_worker_loop"):
        assert own not in discovery, f"discovery.py ha un suo loop: {own}"

    scheduler = _source("life_orchestration", "scheduler.py")
    assert "_review_opportunities" in scheduler, "il gancio non è dove gira già il lavoro"


def test_the_change_log_keeps_a_working_note_and_not_a_diary():
    """§32/§33: retention, and refs instead of contents."""
    from opportunities.changes import MeaningfulChange, RETENTION_DAYS

    assert 0 < RETENTION_DAYS <= 30
    code = _source("opportunities", "changes.py")
    assert 'create_index("expires_at", expireAfterSeconds=0)' in code

    fields = MeaningfulChange.model_fields
    for forbidden in ("body", "text", "content", "payload", "latitude", "longitude", "coordinates"):
        assert forbidden not in fields, f"il cambiamento porta {forbidden}"
    # Human words are allowed, but only a phrase of them.
    assert fields["before"].metadata[0].max_length <= 200
    assert fields["after"].metadata[0].max_length <= 200


def test_home_reads_a_decision_it_never_makes():
    """
    §21: Home renders, it does not reason.

    A page that asked a model on every render would be slow, expensive and
    non-deterministic — the same morning would look different twice.
    """
    service = _code_only(_source("home", "service.py"))
    assert "for_home(" in service, "Home non legge le opportunity"
    for forbidden in ("decide(", "OpportunityDiscovery", "scan("):
        assert forbidden not in service.split("SurfacingService")[-1][:400], (
            f"Home decide: {forbidden}"
        )


def test_the_conversation_reaches_an_opportunity_the_way_it_reaches_anything_else():
    """
    §20: a context source, ranked like the others, not a special case.

    "Cosa devo preparare per domani?" should reach it and "quanto costa
    Netflix?" should not — and that is retrieval's job, which is why this is
    a source rather than something spliced into the prompt.
    """
    sources = _source("conversation_engine", "ai_core", "context_sources.py")
    assert '"opportunities",' in sources
    assert "list_active" in sources
    code = _code_only(sources)
    # Only what is live: a refused concern is not context.
    assert "dismissed" not in code.split("_opportunities")[-1][:1200]


def test_vediamo_opens_a_conversation_and_creates_nothing():
    """§12/§41: the handoff carries a handle, never an instruction."""
    frontend = HERE.parent / "frontend"
    home = (frontend / "app" / "(tabs)" / "index.tsx").read_text(encoding="utf-8")
    assert "buildOraConversationHref" in home
    assert "opportunityId: o.id" in home
    for forbidden in ("createTask", "runAction", "executeAction", "homeAction(o.id"):
        assert forbidden not in home, f"«Vediamo» fa {forbidden}"

    orchestrator = _code_only(_source("conversation_engine", "ai_core", "orchestrator.py"))
    assert "active_opportunity_id" in orchestrator
    # Bound to the session, never acted on.
    assert "resolve(" not in orchestrator.split("active_opportunity_id")[1][:300]


def test_the_card_offers_three_answers_and_none_of_them_executes():
    frontend = HERE.parent / "frontend"
    feed = (frontend / "src" / "components" / "home" / "v3" / "HomeSections.tsx").read_text(
        encoding="utf-8"
    )
    for label in ("Vediamo", "Più tardi", "Non mi interessa"):
        assert f">{label}<" in feed.replace("\n", "").replace("  ", "") or label in feed, (
            f"manca «{label}»"
        )
    for forbidden in ("Esegui", "Converti in attività", "Ricordamelo", "Notificami"):
        assert forbidden not in feed, f"la card offre «{forbidden}»"

    # Whatever arrives, the section stays a section.
    assert "slice(0, 2)" in feed


# ---------------------------------------------------------------------------
# How long "later" lasts
# ---------------------------------------------------------------------------

async def _one_raised(db, uid, monkeypatch, **over):
    """One raised, surfaced opportunity, ready to be deferred."""
    from opportunities.service import OpportunityService
    from opportunities.surfacing import SurfacingService

    ref = await _seed_event(db, uid)
    _install(monkeypatch, FakeModel([{"opportunities": [_raised("doc-app", [ref], **over)]}]))
    created = (await OpportunityService(db).scan(uid)).created
    surfacing = SurfacingService(db)
    _install(monkeypatch, FakeModel([_decisions((created[0].id, "surface"))]))
    await surfacing.decide(uid)
    return surfacing, created[0]


def _hours_between(deferred_until: str) -> float:
    when = datetime.fromisoformat(deferred_until)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (when - datetime.now(timezone.utc)).total_seconds() / 3600


def test_how_long_later_lasts_is_decided_and_not_assumed(monkeypatch):
    """
    §1/§2: six hours was code answering a question it could not answer.

    "Più tardi" about an appointment tomorrow morning means this evening. The
    model says so, and the hold is exactly what it said — recorded with its
    reason, so a person could be told why it came back when it did.
    """
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            surfacing, raised = await _one_raised(db, uid, monkeypatch)

            _install(monkeypatch, FakeModel([{
                "revisit_in_hours": 5,
                "rationale": "L'ufficio è aperto solo domani mattina.",
                "confidence": "strong",
            }]))
            result = await surfacing.defer(uid, raised.id)

            assert result["decided_by"] == "model"
            assert 4.5 < _hours_between(result["deferred_until"]) < 5.5

            stored = await surfacing.repo.get(uid, raised.id)
            assert stored.revisit_source == "model"
            assert stored.revisit_rationale == "L'ufficio è aperto solo domani mattina."
            assert await surfacing.for_home(uid) == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_two_different_things_get_two_different_laters(monkeypatch):
    """
    §6B: the same two words, two answers.

    If every deferral came back after the same interval the judgement would be
    decorative — so this asserts that what the model says is what happens,
    across a case with a clock on it and one without.
    """
    async def body():
        client, db = await _db()
        held = {}
        for label, hours in (("urgente", 4), ("senza fretta", 96)):
            uid = f"d37_{uuid.uuid4().hex[:8]}"
            try:
                surfacing, raised = await _one_raised(db, uid, monkeypatch)
                _install(monkeypatch, FakeModel([{
                    "revisit_in_hours": hours, "rationale": label,
                    "confidence": "reasonable",
                }]))
                result = await surfacing.defer(uid, raised.id)
                held[label] = _hours_between(result["deferred_until"])
            finally:
                await _clean(db, uid)
        client.close()

        assert 3.5 < held["urgente"] < 4.5
        assert 95 < held["senza fretta"] < 97
        assert held["senza fretta"] > held["urgente"] * 5, (
            "«più tardi» dura sempre uguale: il giudizio non arriva fino in fondo"
        )

    _run(body())


def test_the_model_is_told_what_the_thing_is_waiting_on(monkeypatch):
    """Deciding how long later lasts without this would be deciding blind."""
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            surfacing, raised = await _one_raised(db, uid, monkeypatch)
            model = FakeModel([{"revisit_in_hours": 8, "rationale": "x"}])
            _install(monkeypatch, model)
            await surfacing.defer(uid, raised.id)

            asked = model.seen[0]["user"]
            assert "valid_until" in asked
            assert "waiting_on_an_answer" in asked
            assert "how_time_sensitive" in asked
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_hold_nobody_decided_says_so(monkeypatch):
    """
    §3: with no model there is no judgement, and none is invented.

    The card is kept off the screen just long enough not to reappear in the
    same breath — and the record calls that what it is, so a later pass can
    tell an unanswered tap from a considered one.
    """
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.surfacing import RETRY_HOLD_MINUTES

            surfacing, raised = await _one_raised(db, uid, monkeypatch)
            _install(monkeypatch, FakeModel([]))  # unreachable
            result = await surfacing.defer(uid, raised.id)

            assert result["ok"] is True
            assert result["decided_by"] == "technical_retry_hold"
            held = _hours_between(result["deferred_until"])
            assert 0 < held <= (RETRY_HOLD_MINUTES / 60) + 0.05

            stored = await surfacing.repo.get(uid, raised.id)
            assert stored.revisit_source == "technical_retry_hold"
            # No reason, because nobody had one.
            assert stored.revisit_rationale == ""
            # And still true, still active, nothing decided about it.
            assert stored.status == "active"
            assert await surfacing.repo.decisions_for(uid, raised.id) == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_judgement_outside_any_sane_range_is_pulled_back_into_it(monkeypatch):
    """
    Bounds are code's half of the split, and only that.

    Ten minutes would make the tap pointless and a year would bring it back
    into a different life. Clamping is arithmetic; it never overrules a
    judgement that lands inside the range.
    """
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.surfacing import MAX_REVISIT_HOURS, MIN_REVISIT_HOURS

            surfacing, raised = await _one_raised(db, uid, monkeypatch)
            _install(monkeypatch, FakeModel([{"revisit_in_hours": 99999, "rationale": "y"}]))
            result = await surfacing.defer(uid, raised.id)
            assert _hours_between(result["deferred_until"]) <= MAX_REVISIT_HOURS + 0.1
            assert MIN_REVISIT_HOURS == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_later_still_creates_no_work_no_notification_and_no_reminder(monkeypatch):
    """§4/§6E: a revisit time is not a schedule and nobody will be told anything."""
    async def body():
        client, db = await _db()
        uid = f"d37_{uuid.uuid4().hex[:8]}"
        try:
            surfacing, raised = await _one_raised(db, uid, monkeypatch)
            _install(monkeypatch, FakeModel([{"revisit_in_hours": 12, "rationale": "z"}]))
            await surfacing.defer(uid, raised.id)

            for coll in ("attention_items", "work_items", "notifications", "reminders"):
                if coll in await db.list_collection_names():
                    assert await db[coll].count_documents({"user_id": uid}) == 0

            stored = await surfacing.repo.get(uid, raised.id)
            assert stored.status == "active", "rimandare l'ha chiusa"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_no_fixed_duration_stands_in_for_a_judgement():
    """
    §6 guard: a constant may hold a card, it may not decide when to speak.

    The only durations allowed in this file are the technical retry hold and
    the two bounds — each named for what it is. Anything else would be six
    hours coming back under a different name.
    """
    import opportunities.surfacing as surfacing_module

    code = _code_only(_source("opportunities", "surfacing.py"))

    # Every duration reachable from the defer path, by name.
    allowed = {"RETRY_HOLD_MINUTES", "MIN_REVISIT_HOURS", "MAX_REVISIT_HOURS"}
    for name, value in vars(surfacing_module).items():
        if name.isupper() and isinstance(value, int) and name not in allowed:
            assert "REVISIT" not in name and "DEFER" not in name, (
                f"{name} decide di nuovo quanto dura «più tardi»"
            )
    assert not hasattr(surfacing_module, "DEFER_HOURS"), "DEFER_HOURS è tornata"

    # And no literal timedelta in the deciding half of defer().
    defer_body = code.split("async def defer")[1].split("async def")[0]
    for arg in re.findall(r"timedelta\(([^)]*)\)", defer_body):
        number = re.search(r"=\s*(\d+)", arg)
        assert number is None or any(word in arg for word in allowed), (
            f"defer() usa una durata scritta a mano: timedelta({arg})"
        )

    # The judgement must actually be asked for.
    assert "decide_revisit" in code, "nessuno chiede quando riproporla"


def test_a_technical_hold_is_never_read_as_a_decision():
    """The two are different words in the contract, not one word with a flag."""
    from opportunities.models import RevisitSource
    import typing

    assert set(typing.get_args(RevisitSource)) == {"model", "technical_retry_hold"}
