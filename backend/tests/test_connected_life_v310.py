"""
V3.10 Sprint 1 — the outside world as a sensor, and what must not follow.

    INTEGRATIONS ARE NOT FEATURES.
    THEY ARE SENSORS AND ACTUATORS OF THE PERSONAL LIFE MODEL.

    CONNECTED DOES NOT MEAN INTERRUPTING.
    A FAILED READING IS NOT AN EMPTY WORLD.
    ORA MUST RECOGNISE ITS OWN FOOTPRINTS.

Connecting a life to real sources is where a careful system turns into a noisy
one. Every test here is one of the ways that happens.

**The same news twice.** A sync that re-reads an unchanged world must cost one
lookup. Everything expensive downstream — a judgement, a wake, a goal, a
sentence in somebody's pocket — begins with a signal, so a duplicate signal is
a duplicate of all of it.

**Its own footprints.** ORA writes an event; the next sync sees a new event.
Without recognition the agent reads its own work as news and does it again.

**An empty world.** A sync that fails must never look like a calendar with
nothing in it. That mistake does not produce an error anybody sees — it
produces a confident system that has stopped knowing anything.

**Meaning invented by code.** There is no `if` anywhere that creates a goal,
and a guard walks the module to keep it that way. Code produces the
observation; whether it means anything is somebody else's judgement, and
`noise` is the ordinary answer.

No live model calls. The provider is the connector's own fake and the
judgement is replayed from ones that were really made.
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
CALENDAR = "cal_connected@example.com"


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, uid):
    for coll in (
        "connected_signals", "connected_source_attempts", "connector_instances",
        "ingestion_events", "documents", "memories", "ambient_wakes",
        "ambient_activity", "meaningful_changes", "opportunities",
        "agent_receipts", "calendar_event_drafts", "permission_consents",
        "permission_audit", "memory_governance_decisions", "life_memories",
    ):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


def _when(days=1, hour=10):
    moment = datetime.now(timezone.utc) + timedelta(days=days)
    return moment.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


async def _instance(db, uid, *, status="connected"):
    """A calendar this person connected, as the connector layer records one."""
    instance_id = f"inst_{uuid.uuid4().hex[:8]}"
    await db.connector_instances.insert_one({
        "id": instance_id, "user_id": uid, "connector_id": "calendar_google",
        "status": status, "metadata": {"default_calendar_id": CALENDAR,
                                       "account_email": "qa@example.com"},
        "cursor": {CALENDAR: {"sync_token": "tok_1"}},
        "last_sync_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return instance_id


async def _ingested(
    db, uid, instance_id, *, external_id, title="Visita", starts_at=None,
    status="confirmed", location="", supersedes=None, at=None,
    attendees=None, description="", etag=None,
):
    """One row exactly as the ingestion pipeline writes it."""
    row_id = f"ing_{uuid.uuid4().hex[:12]}"
    await db.ingestion_events.insert_one({
        "id": row_id, "user_id": uid, "connector_id": "calendar_google",
        "connector_instance_id": instance_id, "external_id": external_id,
        "source_type": "calendar_google", "source_record_type": "calendar_event",
        "ingestion_status": "processed",
        "normalized_payload": {
            "title": title, "starts_at": starts_at or _when(),
            "status": status, "location": location,
            "attendees": list(attendees or []), "description": description,
            # What a provider rewrites on every save, whether or not anything
            # happened to the person.
            "etag": etag or uuid.uuid4().hex[:8],
            "source_updated_at": datetime.now(timezone.utc).isoformat(),
        },
        "ingested_at": at or datetime.now(timezone.utc).isoformat(),
        "supersedes_event_id": supersedes,
    })
    return row_id


def _fields(signal) -> dict:
    """The delta as a lookup, so a test can ask about one field by name."""
    return {c.field: c for c in signal.changed_fields}


class Recorded:
    """Judgements that were really made, replayed by what they answered."""

    def __init__(self, answer=None):
        self.answer = answer
        self.asked = 0

    async def __call__(self, system, user):
        self.asked += 1
        return dict(self.answer) if isinstance(self.answer, dict) else self.answer


def _install(monkeypatch, model):
    import connected.reasoning as reasoning

    monkeypatch.setattr(reasoning, "_ask_model", model)
    return model


def _service(db):
    from connected.service import ConnectedLifeService

    return ConnectedLifeService(db)


# ---------------------------------------------------------------------------
# The instruments
# ---------------------------------------------------------------------------

def test_a_source_says_how_old_what_it_knows_is():
    """
    §21/§22: connected and current are two different claims.

    A calendar can be perfectly connected and hold a picture from two days
    ago. A system that reports only "connected" lets a reasoning step state a
    stale day as the current one — which is not a visible bug, just a
    confident answer that happens to be wrong.
    """
    from connected.models import ConnectedSource, freshness_of

    now = datetime.now(timezone.utc)
    assert freshness_of("calendar", None) == "unknown"
    assert freshness_of("calendar", (now - timedelta(minutes=30)).isoformat()) == "fresh"
    assert freshness_of("calendar", (now - timedelta(hours=6)).isoformat()) == "aging"
    assert freshness_of("calendar", (now - timedelta(hours=48)).isoformat()) == "stale"

    # And not one threshold for everything: documents do not move on their own.
    assert freshness_of("documents", (now - timedelta(hours=6)).isoformat()) == "fresh"

    working = ConnectedSource(
        owner_id="u", source_type="calendar", status="connected",
        freshness_state="fresh",
    )
    old = ConnectedSource(
        owner_id="u", source_type="calendar", status="connected",
        freshness_state="stale",
    )
    assert working.can_be_leaned_on is True
    assert old.can_be_leaned_on is False, "una foto vecchia trattata come adesso"


def test_what_a_person_sees_about_a_connection_is_three_things(monkeypatch):
    """
    §25: no cursor, no scopes, no codes.

    Everything else in the model is our plumbing wearing the costume of a
    fact about their life. What survives is the connection, whether it works,
    and when it was last read.
    """
    async def body():
        client, db = await _db()
        uid = f"cx_{uuid.uuid4().hex[:8]}"
        try:
            await _instance(db, uid)
            sources = await _service(db).sources.list(uid)
            assert len(sources) == 2, "calendario e documenti"

            for source in sources:
                shown = source.for_human()
                assert set(shown) == {"what", "state", "last_read_at"}
                # The values, not the shape of the dict: what a person reads
                # is the three sentences, and none of them may carry our
                # plumbing.
                blob = " ".join(str(v) for v in shown.values()).lower()
                for forbidden in (
                    "cursor", "sync_token", "scope", "inst_", "connector",
                    "calendar_google", "error", "token", "degraded", "stale",
                ):
                    assert forbidden not in blob, f"mostra «{forbidden}»"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_failed_reading_is_not_an_empty_world(monkeypatch):
    """
    §23: the most dangerous mistake available to a connected system.

    The sync throws. Nothing is deleted, no signal is invented, the source
    says plainly that it could not be read — and what we already knew is
    still what we know. A system that treated this as "no events" would
    conclude somebody's day is free.
    """
    async def body():
        client, db = await _db()
        uid = f"cx_{uuid.uuid4().hex[:8]}"
        try:
            instance_id = await _instance(db, uid)
            await _ingested(db, uid, instance_id, external_id="ev_known")
            service = _service(db)

            async def explode(*a, **k):
                raise RuntimeError("provider down")

            monkeypatch.setattr(service, "_sync_calendar", explode)
            out = await service.sync(uid, instance_id)

            assert out["ok"] is False and out["reason"] == "sync_failed"
            source = await service.sources.get(uid, instance_id)
            assert source.status == "degraded", source.status
            assert source.error_state, "nessuna traccia di cosa è andato storto"
            # Nothing invented, nothing removed.
            assert await db.connected_signals.count_documents({"owner_id": uid}) == 0
            assert await db.ingestion_events.count_documents({"user_id": uid}) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_source_that_recovers_says_so(monkeypatch):
    """
    §24: a failure that outlives itself is a failure nobody believes.

    A source still reporting last week's error after four good readings is one
    people learn to ignore — and then they ignore the real ones too.
    """
    async def body():
        client, db = await _db()
        uid = f"cx_{uuid.uuid4().hex[:8]}"
        try:
            instance_id = await _instance(db, uid)
            service = _service(db)
            await service.sources.note_failure(uid, instance_id, error="Timeout")
            assert (await service.sources.get(uid, instance_id)).status == "degraded"

            async def fine(*a, **k):
                return None

            monkeypatch.setattr(service, "_sync_calendar", fine)
            out = await service.sync(uid, instance_id)
            assert out["ok"] is True

            source = await service.sources.get(uid, instance_id)
            assert source.status == "connected"
            assert source.error_state == "", "l'errore vecchio è rimasto attaccato"
            assert source.freshness_state == "fresh"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# The observations
# ---------------------------------------------------------------------------

def test_the_calendar_is_read_as_what_moved(monkeypatch):
    """
    §9/§14/§15: not what is there — what changed, in facts.

    An appointment that moved produces one signal that says so, carrying
    either side of the move. A hash that differs is not a fact, and facts are
    what every layer above this needs.
    """
    async def body():
        client, db = await _db()
        uid = f"cx_{uuid.uuid4().hex[:8]}"
        try:
            from connected import calendar_sensor

            instance_id = await _instance(db, uid)
            first = await _ingested(
                db, uid, instance_id, external_id="ev_1",
                title="Visita", starts_at=_when(1, 10),
            )
            await _ingested(
                db, uid, instance_id, external_id="ev_1",
                title="Visita", starts_at=_when(1, 15), supersedes=first,
            )

            signals = await calendar_sensor.read_changes(
                db, uid, source_id=instance_id
            )
            kinds = [s.signal_type for s in signals]
            assert "calendar.event.created" in kinds
            assert "calendar.event.changed" in kinds

            moved = next(s for s in signals if s.signal_type == "calendar.event.changed")
            assert "starts_at" in _fields(moved)
            when = _fields(moved)["starts_at"]
            assert when.before and when.after and when.before != when.after
            assert "Visita" in moved.payload_summary
            assert moved.origin == "external"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_two_things_changing_are_two_facts_in_one_signal(monkeypatch):
    """
    §2/§5/§8A: one signal, and nothing chosen inside it.

        CODE KNOWS WHAT CHANGED. THE MODEL DECIDES WHETHER IT MATTERS.

    An appointment that moved *and* changed room is one thing that happened
    to somebody, so it is one signal — and both differences survive. The
    version this replaces returned only the time, because a hard-coded order
    said arriving late beats being in the wrong room. That is a judgement
    about a life, and it was being made in a comparison function that has
    never seen one.
    """
    async def body():
        client, db = await _db()
        uid = f"cx_{uuid.uuid4().hex[:8]}"
        try:
            from connected import calendar_sensor

            instance_id = await _instance(db, uid)
            first = await _ingested(
                db, uid, instance_id, external_id="ev_2",
                starts_at=_when(1, 10), location="Studio A",
            )
            await _ingested(
                db, uid, instance_id, external_id="ev_2",
                starts_at=_when(1, 16), location="Studio B", supersedes=first,
            )

            signals = await calendar_sensor.read_changes(
                db, uid, source_id=instance_id
            )
            about = [s for s in signals if s.source_object_ref == "ev_2"]
            moves = [s for s in about if s.signal_type != "calendar.event.created"]
            assert len(moves) == 1, f"{len(moves)} segnali per un cambiamento"

            fields = _fields(moves[0])
            assert "starts_at" in fields, "l'ora è sparita"
            assert "location" in fields, "il posto è sparito"
            assert fields["location"].before == "Studio A"
            assert fields["location"].after == "Studio B"

            # And what the judgement is shown carries both.
            shown = moves[0].for_ai()["what_is_different"]
            assert {f["field"] for f in shown} >= {"starts_at", "location"}
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_attendee_is_not_discarded_by_code(monkeypatch):
    """
    §3/§8B: code does not get to decide that nobody would notice.

    Somebody being added to an appointment used to produce nothing at all,
    on the grounds that it was not worth mentioning. Whether it is worth
    mentioning depends on who they are and what else is true about the
    person's day — neither of which this layer can see.
    """
    async def body():
        client, db = await _db()
        uid = f"cx_{uuid.uuid4().hex[:8]}"
        try:
            from connected import calendar_sensor

            instance_id = await _instance(db, uid)
            when = _when(2, 9)
            first = await _ingested(
                db, uid, instance_id, external_id="ev_guest", starts_at=when,
            )
            await _ingested(
                db, uid, instance_id, external_id="ev_guest", starts_at=when,
                attendees=["capo@example.com"], supersedes=first,
            )

            signals = await calendar_sensor.read_changes(
                db, uid, source_id=instance_id
            )
            changed = [
                s for s in signals
                if s.source_object_ref == "ev_guest"
                and s.signal_type == "calendar.event.changed"
            ]
            assert changed, "un invitato in più è stato buttato via dal codice"
            assert "attendees" in _fields(changed[0])
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_private_note_changing_is_a_fact_without_its_content(monkeypatch):
    """
    §4/§8C/§30: minimisation is not the same as discarding the fact.

    A description is somebody's private note. It has no business in a stored
    signal — and "the note changed" is a fact the judgement is entitled to.
    Protecting the content by pretending nothing happened would be protecting
    it by lying.
    """
    async def body():
        client, db = await _db()
        uid = f"cx_{uuid.uuid4().hex[:8]}"
        try:
            from connected import calendar_sensor

            instance_id = await _instance(db, uid)
            when = _when(2, 11)
            secret = "Portare gli esami del sangue, dott. Rossi, 333 1234567"
            first = await _ingested(
                db, uid, instance_id, external_id="ev_note", starts_at=when,
                description="",
            )
            await _ingested(
                db, uid, instance_id, external_id="ev_note", starts_at=when,
                description=secret, supersedes=first,
            )

            signals = await calendar_sensor.read_changes(
                db, uid, source_id=instance_id
            )
            changed = next(
                s for s in signals if s.signal_type == "calendar.event.changed"
            )
            note = _fields(changed)["description"]
            assert note.content_withheld is True
            assert note.before == "" and note.after == ""

            # Nowhere in what is stored, nor in what a judgement is shown.
            stored = changed.model_dump_json()
            assert "esami del sangue" not in stored
            assert "333" not in stored
            assert secret not in str(changed.for_ai())
            # But the fact travels.
            shown = {f["field"]: f for f in changed.for_ai()["what_is_different"]}
            assert shown["description"]["changed"] is True
            assert shown["description"]["content_not_carried"] is True
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_change_only_the_provider_can_see_is_not_a_change(monkeypatch):
    """
    §8D: provider noise and a human-observable change are different things.

    An etag, a sequence number, a provider's own idea of when it last saved:
    these move on every write and mean nothing to anybody. Filtering them is
    arithmetic — the comparison never looks at anything but the fields a
    person could observe — and is the one filter this layer is allowed.
    """
    async def body():
        client, db = await _db()
        uid = f"cx_{uuid.uuid4().hex[:8]}"
        try:
            from connected import calendar_sensor

            instance_id = await _instance(db, uid)
            when = _when(2, 9)
            first = await _ingested(
                db, uid, instance_id, external_id="ev_3", starts_at=when,
                etag="aaa",
            )
            await _ingested(
                db, uid, instance_id, external_id="ev_3", starts_at=when,
                etag="bbb", supersedes=first,
            )

            signals = await calendar_sensor.read_changes(
                db, uid, source_id=instance_id
            )
            moves = [
                s for s in signals
                if s.source_object_ref == "ev_3"
                and s.signal_type != "calendar.event.created"
            ]
            assert moves == [], "ha segnalato la contabilità del provider"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_cancellation_is_read_as_one(monkeypatch):
    """§14: the only change that empties a slot in somebody's day."""
    async def body():
        client, db = await _db()
        uid = f"cx_{uuid.uuid4().hex[:8]}"
        try:
            from connected import calendar_sensor

            instance_id = await _instance(db, uid)
            first = await _ingested(db, uid, instance_id, external_id="ev_4")
            await _ingested(
                db, uid, instance_id, external_id="ev_4", status="cancelled",
                supersedes=first,
            )
            signals = await calendar_sensor.read_changes(
                db, uid, source_id=instance_id
            )
            kinds = [s.signal_type for s in signals]
            assert "calendar.event.cancelled" in kinds
            gone = next(s for s in signals if s.signal_type == "calendar.event.cancelled")
            assert "annullato" in gone.payload_summary
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_same_reading_twice_is_one_observation(monkeypatch):
    """
    §11: the guard everything expensive sits behind.

    A re-sync of an unchanged world must cost one indexed lookup. Without
    this, every judgement, wake, goal and notification downstream happens
    twice for one thing that happened once.
    """
    async def body():
        client, db = await _db()
        uid = f"cx_{uuid.uuid4().hex[:8]}"
        try:
            from connected import calendar_sensor

            instance_id = await _instance(db, uid)
            first = await _ingested(
                db, uid, instance_id, external_id="ev_5", starts_at=_when(1, 10)
            )
            await _ingested(
                db, uid, instance_id, external_id="ev_5", starts_at=_when(1, 15),
                supersedes=first,
            )
            service = _service(db)
            signals = await calendar_sensor.read_changes(
                db, uid, source_id=instance_id
            )
            for signal in signals:
                await service.signals.record(signal)
            once = await db.connected_signals.count_documents({"owner_id": uid})

            pending_before = {s.id for s in await service.signals.pending(uid)}

            # The provider hands us the same rows again.
            for signal in await calendar_sensor.read_changes(
                db, uid, source_id=instance_id
            ):
                kept, why = await service.signals.record(signal)
                assert kept is None and why == "duplicate"

            assert await db.connected_signals.count_documents({"owner_id": uid}) == once

            # And it changed nothing that was already there. This is the half
            # a unique index cannot cover: without the lookup that stops a
            # duplicate early, the second pass walks on and supersedes the
            # observation it is a duplicate *of* — leaving nothing pending and
            # an agent with nothing to reason about, while every count still
            # looks right.
            assert {s.id for s in await service.signals.pending(uid)} == pending_before, (
                "un duplicato ha spostato quello che c'era già"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_second_pass_over_an_unchanged_world_reads_nothing(monkeypatch):
    """
    §10: delta first, and the difference between correct and affordable.

    The fingerprint is what makes a re-read *harmless*; the watermark is what
    makes it *free*. Both matter, and only the first is a correctness
    property — which is exactly why this test exists: a mutation that ignores
    the cursor keeps every other test green while quietly turning each pass
    into a full re-derivation of a fortnight of somebody's calendar.

    Measured as rows turned into signals rather than as a timing, because a
    test that asserts speed asserts the machine it ran on.
    """
    async def body():
        client, db = await _db()
        uid = f"cx_{uuid.uuid4().hex[:8]}"
        try:
            from connected import calendar_sensor

            instance_id = await _instance(db, uid)
            first = await _ingested(
                db, uid, instance_id, external_id="ev_10", starts_at=_when(1, 10)
            )
            await _ingested(
                db, uid, instance_id, external_id="ev_10", starts_at=_when(1, 15),
                supersedes=first,
            )
            service = _service(db)

            async def already_read(*a, **k):
                return None

            monkeypatch.setattr(service, "_sync_calendar", already_read)
            first_pass = await service.sync(uid, instance_id)
            assert first_pass["seen"] > 0

            # Nothing new arrived. The second pass must not walk the same rows
            # again and lean on dedupe to undo the work.
            second_pass = await service.sync(uid, instance_id)
            assert second_pass["seen"] == 0, (
                f"ha riletto {second_pass['seen']} righe già lette"
            )
            assert second_pass["deduped"] == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_same_thing_moving_again_supersedes_the_first_move(monkeypatch):
    """
    §29: 10 → 15 → 16 is one appointment changing twice.

    The pending observation about the first move is not wrong, it is simply no
    longer the news — and leaving it pending would have the agent reason
    about an appointment that has since moved on.
    """
    async def body():
        client, db = await _db()
        uid = f"cx_{uuid.uuid4().hex[:8]}"
        try:
            from connected.models import ConnectedSignal

            service = _service(db)
            from connected.models import FieldChange

            first = ConnectedSignal(
                owner_id=uid, source_type="calendar", source_id="s1",
                signal_type="calendar.event.changed",
                source_object_ref="ev_6", before="10:00", after="15:00",
                changed_fields=[
                    FieldChange(field="starts_at", before="10:00", after="15:00")
                ],
            )
            second = ConnectedSignal(
                owner_id=uid, source_type="calendar", source_id="s1",
                signal_type="calendar.event.changed",
                source_object_ref="ev_6", before="15:00", after="16:00",
                changed_fields=[
                    FieldChange(field="starts_at", before="15:00", after="16:00")
                ],
            )
            kept, why = await service.signals.record(first)
            assert why == "recorded"
            kept2, why2 = await service.signals.record(second)
            assert why2 == "superseded_previous"

            pending = await service.signals.pending(uid)
            assert len(pending) == 1
            assert pending[0].after == "16:00"
            assert pending[0].supersedes == first.id

            # And the history still knows where it came from.
            history = await service.signals.history(uid, "ev_6")
            assert len(history) == 2
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_composite_delta_dedupes_on_everything_it_carries(monkeypatch):
    """
    §10: the fingerprint has to know about the whole delta.

    "Moved to 15:00" and "moved to 15:00 and to Studio B" are two different
    observations. A fingerprint built only from the headline would call them
    the same, and the second — the one with more in it — would be silently
    swallowed by the first.
    """
    async def body():
        client, db = await _db()
        uid = f"cx_{uuid.uuid4().hex[:8]}"
        try:
            from connected.models import ConnectedSignal, FieldChange

            service = _service(db)

            # The same object, the same headline, one extra fact. Everything
            # outside `changed_fields` is identical on purpose: if the
            # fingerprint ignored the delta these two would collide, and the
            # richer observation would be swallowed by the poorer one.
            only_time = ConnectedSignal(
                owner_id=uid, source_type="calendar", source_id="s1",
                signal_type="calendar.event.changed",
                source_object_ref="ev_c1", before="10:00", after="15:00",
                changed_fields=[
                    FieldChange(field="starts_at", before="10:00", after="15:00")
                ],
            )
            time_and_place = ConnectedSignal(
                owner_id=uid, source_type="calendar", source_id="s1",
                signal_type="calendar.event.changed",
                source_object_ref="ev_c1", before="10:00", after="15:00",
                changed_fields=[
                    FieldChange(field="starts_at", before="10:00", after="15:00"),
                    FieldChange(field="location", before="Studio A", after="Studio B"),
                ],
            )
            assert only_time.compute_fingerprint() != time_and_place.compute_fingerprint(), (
                "due osservazioni diverse hanno la stessa impronta"
            )

            # And the identical delta, seen twice, is one observation.
            again = ConnectedSignal(
                owner_id=uid, source_type="calendar", source_id="s1",
                signal_type="calendar.event.changed",
                source_object_ref="ev_c1", before="10:00", after="15:00",
                changed_fields=[
                    FieldChange(field="starts_at", before="10:00", after="15:00")
                ],
            )
            kept, why = await service.signals.record(only_time)
            assert why == "recorded"
            kept2, why2 = await service.signals.record(again)
            assert kept2 is None and why2 == "duplicate"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_second_composite_update_supersedes_the_first(monkeypatch):
    """
    §10: the same appointment changing twice, with different fields each time.

    The pending observation about the first change is not wrong, it is no
    longer the news — and an agent reasoning about a room that has since
    changed again is reasoning about a world that has moved on.
    """
    async def body():
        client, db = await _db()
        uid = f"cx_{uuid.uuid4().hex[:8]}"
        try:
            from connected.models import ConnectedSignal, FieldChange

            service = _service(db)
            first = ConnectedSignal(
                owner_id=uid, source_type="calendar", source_id="s1",
                signal_type="calendar.event.changed",
                source_object_ref="ev_c3", before="10:00", after="15:00",
                changed_fields=[
                    FieldChange(field="starts_at", before="10:00", after="15:00")
                ],
            )
            second = ConnectedSignal(
                owner_id=uid, source_type="calendar", source_id="s1",
                signal_type="calendar.event.changed",
                source_object_ref="ev_c3", before="15:00", after="16:00",
                changed_fields=[
                    FieldChange(field="starts_at", before="15:00", after="16:00"),
                    FieldChange(field="location", before="Studio A", after="Studio B"),
                ],
            )
            await service.signals.record(first)
            kept, why = await service.signals.record(second)
            assert why == "superseded_previous"

            pending = await service.signals.pending(uid)
            assert len(pending) == 1
            fields = {c.field for c in pending[0].changed_fields}
            assert fields == {"starts_at", "location"}
            assert pending[0].supersedes == first.id
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_one_persons_calendar_is_not_anothers(monkeypatch):
    """Owner isolation, checked where a mistake would be silent."""
    async def body():
        client, db = await _db()
        mine = f"cx_{uuid.uuid4().hex[:8]}"
        yours = f"cx_{uuid.uuid4().hex[:8]}"
        try:
            from connected import calendar_sensor

            my_instance = await _instance(db, mine)
            await _instance(db, yours)
            await _ingested(db, mine, my_instance, external_id="ev_mine")

            seen = await calendar_sensor.read_changes(
                db, yours, source_id=my_instance
            )
            assert seen == [], "ha letto il calendario di un'altra persona"

            sources = await _service(db).sources.list(yours)
            assert my_instance not in [s.id for s in sources]
        finally:
            await _clean(db, mine)
            await _clean(db, yours)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Its own footprints
# ---------------------------------------------------------------------------

def test_ora_recognises_the_events_it_wrote_itself(monkeypatch):
    """
    §18: the loop that would otherwise be infinite.

    ORA writes an event, the sync sees a new event, the agent reads it as news
    and writes it again. Recognition comes from ORA's own record of having
    written — a receipt, a draft — and not from a marker on the provider's
    copy, which anybody could duplicate.
    """
    async def body():
        client, db = await _db()
        uid = f"cx_{uuid.uuid4().hex[:8]}"
        try:
            from connected import calendar_sensor

            instance_id = await _instance(db, uid)
            await db.agent_receipts.insert_one({
                "id": "rcp_1", "owner_id": uid, "provider": "calendar",
                "external_ref": "ev_ours", "provider_status": "succeeded",
            })
            await _ingested(db, uid, instance_id, external_id="ev_ours")
            await _ingested(db, uid, instance_id, external_id="ev_theirs")

            signals = await calendar_sensor.read_changes(
                db, uid, source_id=instance_id
            )
            by_ref = {s.source_object_ref: s for s in signals}
            assert by_ref["ev_ours"].origin == "self_originated"
            assert by_ref["ev_theirs"].origin == "external"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_its_own_work_never_becomes_new_work(monkeypatch):
    """
    §18/§36: recognised is not ignored, and never a reason to act.

    The observation is real and is exactly what a verification wants. What it
    must never do is reach the change log, propose a memory, or wake anybody
    up — and it must never cost a judgement either, because asking a model
    about our own writes is paying to be told we did them.
    """
    async def body():
        client, db = await _db()
        uid = f"cx_{uuid.uuid4().hex[:8]}"
        try:
            from connected.models import ConnectedSignal

            service = _service(db)
            model = _install(monkeypatch, Recorded({
                "outcome": "may_need_action", "what_it_means": "reg.",
                "relates_to": "reg.", "reasoning": "reg.",
            }))
            await service.signals.record(ConnectedSignal(
                owner_id=uid, source_type="calendar", source_id="s1",
                signal_type="calendar.event.created",
                source_object_ref="ev_ours", after="domani alle 10",
                origin="self_originated",
            ))

            out = await service.interpret(uid)

            assert out["own_work"] == 1
            assert out["looked_at"] == 0, "ha pagato un giudizio per il proprio lavoro"
            assert model.asked == 0
            assert await db.ambient_wakes.count_documents({"owner_id": uid}) == 0
            assert await db.meaningful_changes.count_documents({"owner_id": uid}) == 0

            settled = await service.signals.get(uid, (await service.signals.history(uid, "ev_ours"))[0].id)
            assert settled.status == "interpreted"
            assert settled.outcome == "own_work_confirmed"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Meaning, and the absence of it
# ---------------------------------------------------------------------------

def test_noise_ends_in_nothing(monkeypatch):
    """
    §8/§39: the ordinary answer, and what must follow from it.

    No change recorded, no memory proposed, nobody woken, nothing on a
    screen. A connected system whose noise still costs a wake is a connected
    system that drains a battery to conclude nothing.
    """
    async def body():
        client, db = await _db()
        uid = f"cx_{uuid.uuid4().hex[:8]}"
        try:
            from connected.models import ConnectedSignal

            service = _service(db)
            _install(monkeypatch, Recorded({
                "outcome": "noise", "what_it_means": "",
                "relates_to": "", "reasoning": "reg.",
            }))
            from connected.models import FieldChange

            await service.signals.record(ConnectedSignal(
                owner_id=uid, source_type="calendar", source_id="s1",
                signal_type="calendar.event.changed",
                source_object_ref="ev_noise", after="stand-up",
                changed_fields=[
                    FieldChange(field="title", before="Stand-up", after="Daily")
                ],
            ))

            out = await service.interpret(uid)

            assert out["noise"] == 1 and out["passed_on"] == 0
            assert await db.ambient_wakes.count_documents({"owner_id": uid}) == 0
            assert await db.meaningful_changes.count_documents({"owner_id": uid}) == 0
            assert await db.connected_signals.count_documents(
                {"owner_id": uid, "status": "skipped"}
            ) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_something_that_matters_reaches_the_machinery_that_already_exists(monkeypatch):
    """
    §12/§13: a signal knocks on a door. It does not open one.

    What a meaningful change produces is a `MeaningfulChange` in the change
    log V3.7 already built and an `AmbientWake` V3.8 already runs — and then
    nothing, because what comes of it is decided by the loop that wakes up.
    No goal is created here, and none could be.
    """
    async def body():
        client, db = await _db()
        uid = f"cx_{uuid.uuid4().hex[:8]}"
        try:
            from connected.models import ConnectedSignal

            service = _service(db)
            _install(monkeypatch, Recorded({
                "outcome": "may_need_action",
                "what_it_means": "La visita di domani si è spostata al pomeriggio.",
                "relates_to": "la visita", "reasoning": "reg.",
            }))
            from connected.models import FieldChange

            await service.signals.record(ConnectedSignal(
                owner_id=uid, source_type="calendar", source_id="s1",
                signal_type="calendar.event.changed",
                source_object_ref="ev_7", before="10:00", after="15:00",
                payload_summary="Di «Visita» è cambiata l'ora.",
                changed_fields=[
                    FieldChange(field="starts_at", before="10:00", after="15:00")
                ],
            ))

            out = await service.interpret(uid)
            assert out["passed_on"] == 1

            changes = await db.meaningful_changes.find(
                {"owner_id": uid}, {"_id": 0}
            ).to_list(5)
            assert len(changes) == 1
            assert changes[0]["source"] == "calendar"
            assert changes[0]["kind"] == "event.updated"
            assert changes[0]["entity_ref"] == "ev_7"

            wakes = await db.ambient_wakes.find({"owner_id": uid}, {"_id": 0}).to_list(5)
            assert len(wakes) == 1
            assert wakes[0]["reason"] == "state_changed"

            # And no goal anywhere. The wake decides that, later, elsewhere.
            assert await db.agent_goals.count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_what_the_world_says_is_proposed_never_written(monkeypatch):
    """
    §26/§27: observed is not true.

    A change that makes something ORA believes out of date is offered to the
    governance that owns durable learning, with the provenance to trace it
    back. Governance may refuse. Nothing here writes a memory.
    """
    async def body():
        client, db = await _db()
        uid = f"cx_{uuid.uuid4().hex[:8]}"
        try:
            from connected.models import ConnectedSignal

            service = _service(db)
            _install(monkeypatch, Recorded({
                "outcome": "changes_something_known",
                "what_it_means": "Adesso il corso è di martedì, non di lunedì.",
                "relates_to": "il corso", "reasoning": "reg.",
            }))

            seen = {}

            class FakeGovernance:
                def __init__(self, _db):
                    pass

                async def apply(self, **kwargs):
                    seen.update(kwargs)

                    class Outcome:
                        decision = "accepted"
                        persisted = True

                    return Outcome()

            import life_memory.governance as governance

            monkeypatch.setattr(governance, "MemoryGovernanceService", FakeGovernance)

            from connected.models import FieldChange

            await service.signals.record(ConnectedSignal(
                owner_id=uid, source_type="calendar", source_id="s1",
                signal_type="calendar.event.changed",
                source_object_ref="ev_8", before="lunedì", after="martedì",
                changed_fields=[
                    FieldChange(field="starts_at", before="lunedì", after="martedì")
                ],
            ))
            await service.interpret(uid)

            assert seen, "non è passato dalla governance"
            candidate = seen["candidate"]
            assert candidate.operation == "propose", "ha scritto invece di proporre"
            assert "martedì" in candidate.summary
            trail = " ".join(candidate.provenance)
            assert "connected_signal:" in trail
            assert "interpretation:" in trail, "impossibile risalire a come l'ha capito"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# The second sensor
# ---------------------------------------------------------------------------

def test_a_document_arriving_is_an_observation_not_a_project(monkeypatch):
    """
    §19/§20/§38: the pipeline is not calendar-shaped.

    A different kind of world event enters the same door and is judged by the
    same layer — and «contratto affitto.pdf» does not become "gestisci
    l'affitto" because a filename says so.
    """
    async def body():
        client, db = await _db()
        uid = f"cx_{uuid.uuid4().hex[:8]}"
        try:
            from connected import documents_sensor

            await db.documents.insert_one({
                "id": "doc_1", "user_id": uid, "title": "Contratto affitto",
                "document_type": "contract",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

            signals = await documents_sensor.read_changes(db, uid)
            assert len(signals) == 1
            assert signals[0].signal_type == "document.added"
            assert signals[0].source_object_ref == "doc_1"
            assert "Contratto affitto" in signals[0].payload_summary
            # The shelf's contents stay on the shelf.
            assert "text" not in signals[0].payload_summary.lower()

            service = _service(db)
            _install(monkeypatch, Recorded({
                "outcome": "noise", "what_it_means": "",
                "relates_to": "", "reasoning": "reg.",
            }))
            for signal in signals:
                await service.signals.record(signal)
            out = await service.interpret(uid)

            assert out["noise"] == 1
            assert await db.agent_goals.count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_disconnecting_stops_the_looking_and_keeps_the_learning(monkeypatch):
    """
    §32: two different questions, answered differently.

    Future readings stop and pending observations are dropped, because they
    describe a world we no longer have permission to watch. What already
    reached the Life Model stays: deleting somebody's memories because they
    unplugged a calendar is a decision governance owns, not this layer.
    """
    async def body():
        client, db = await _db()
        uid = f"cx_{uuid.uuid4().hex[:8]}"
        try:
            from connected.models import ConnectedSignal

            service = _service(db)
            instance_id = await _instance(db, uid)
            await service.signals.record(ConnectedSignal(
                owner_id=uid, source_type="calendar", source_id=instance_id,
                signal_type="calendar.event.created", source_object_ref="ev_9",
                after="domani",
            ))
            await db.memories.insert_one({
                "user_id": uid, "id": "mem_1", "status": "known",
                "summary": "Ha una visita giovedì.",
            })

            out = await service.disconnect(uid, instance_id)
            assert out["dropped_pending"] == 1
            assert await service.signals.pending(uid) == []
            assert await db.memories.count_documents({"user_id": uid}) == 1

            # And a disconnected instance is no longer readable.
            await db.connector_instances.update_one(
                {"id": instance_id}, {"$set": {"status": "revoked"}}
            )
            source = await service.sources.get(uid, instance_id)
            assert source.status == "disconnected"
            assert source.is_readable is False
            blocked = await service.sync(uid, instance_id)
            assert blocked["ok"] is False and blocked["reason"] == "not_connected"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Structure, checked by walking the code
# ---------------------------------------------------------------------------

def _tree(relative: str) -> ast.AST:
    return ast.parse((HERE / relative).read_text(encoding="utf-8"))


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


def test_no_goal_is_ever_created_by_connected_code():
    """
    §13: the line that separates a sensor from an opinion.

        THE CODE PRODUCES THE SIGNAL. THE AI DECIDES WHETHER IT MEANS ANYTHING.

    Walks every module in `connected/` for any way to create a goal, a plan
    or an opportunity. A behavioural test passes the day somebody adds the
    line; this one fails.
    """
    import copy

    forbidden = (
        "create_goal", "consider", "AutonomousGoal", "save_plan",
        "OpportunityService", "Opportunity(", "advance",
    )
    for name in (
        "models.py", "sources.py", "signals.py", "service.py",
        "calendar_sensor.py", "documents_sensor.py", "reasoning.py",
        "router.py",
    ):
        source = ast.dump(_code_only(_tree(f"connected/{name}")))
        for word in forbidden:
            assert word.rstrip("(") not in source, (
                f"connected/{name} può creare lavoro da sé: {word}"
            )


def test_no_field_name_decides_whether_a_change_is_worth_reporting():
    """
    §12: the guard against the mistake this gate was called to fix.

        CODE KNOWS WHAT CHANGED. THE MODEL DECIDES WHETHER IT MATTERS.

    Walks the comparison for any branch keyed on *which* field changed —
    `if field == "attendees": ignore`, a priority table, an early return that
    drops the rest once something more important was found. A technical
    ordering is allowed and is used: the result is sorted by field name so
    two readings serialise identically. What is not allowed is that ordering
    deciding what survives.

    Structural because the behavioural version passes the day somebody adds
    one field to a skip list: every existing test still goes green, and one
    kind of change quietly stops existing.
    """
    import copy

    tree = _tree("connected/calendar_sensor.py")
    compare = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_observable_differences"
    )
    body = _code_only(compare)

    # The only per-field distinction allowed is the privacy one, and it must
    # not remove the field from the result.
    for node in ast.walk(body):
        if not isinstance(node, ast.Compare):
            continue
        text = ast.dump(node)
        if "WITHHELD_CONTENT_FIELDS" in text:
            continue
        for banned in ("attendees", "description", "location", "starts_at", "title"):
            assert f"'{banned}'" not in text, (
                f"il confronto decide qualcosa in base al campo «{banned}»"
            )

    # Every observable field goes through the same loop, and the loop's only
    # exits are "identical" and "content withheld".
    loops = [n for n in ast.walk(body) if isinstance(n, ast.For)]
    assert len(loops) == 1, "più di un percorso per confrontare i campi"
    assert "OBSERVABLE_FIELDS" in ast.dump(loops[0].iter)

    # And no ranking anywhere in the module that could drop information.
    # Read from the code with its prose stripped: a paragraph explaining that
    # importance is the reader's to supply must not fail the check that
    # importance is never computed.
    code = ast.dump(_code_only(tree))
    for ranking in ("PRIORITY", "RANK", "importance", "matters_more"):
        assert ranking not in code, f"c'è una gerarchia: {ranking}"


def test_every_observable_difference_reaches_the_judgement():
    """
    §7/§11: what the model is given is the whole delta, not a headline.

    `for_ai()` must carry `changed_fields`. A judgement shown one of three
    differences is judging a different event from the one that happened, and
    would be right about the wrong thing.
    """
    from connected.models import ConnectedSignal, FieldChange

    signal = ConnectedSignal(
        owner_id="u", source_type="calendar",
        signal_type="calendar.event.changed", source_object_ref="ev",
        changed_fields=[
            FieldChange(field="starts_at", before="10:00", after="16:00"),
            FieldChange(field="location", before="A", after="B"),
            FieldChange(field="attendees", content_withheld=True),
        ],
    )
    shown = signal.for_ai()
    assert "what_is_different" in shown
    assert {f["field"] for f in shown["what_is_different"]} == {
        "starts_at", "location", "attendees"
    }
    withheld = next(
        f for f in shown["what_is_different"] if f["field"] == "attendees"
    )
    assert withheld["changed"] is True and withheld["content_not_carried"] is True

    # And the prompt says so, because a payload the model is not told is
    # complete is a payload it may assume was filtered.
    import inspect

    from connected.reasoning import interpret_signal

    prompt = inspect.getsource(interpret_signal)
    assert "every difference that was observed" in prompt
    assert "not carried" in prompt


def test_connected_life_builds_no_second_engine():
    """
    §12/§N: no ConnectedLifeAgent, no SyncAgent, no second delivery.

    Every meaningful change ends in something that already existed. The one
    place this module touches the rest of ORA is `_pass_on`, and each of its
    three doors is a system with its own tests behind it.
    """
    node = _code_only(_tree("connected/service.py"))
    calls = [
        getattr(n.func, "attr", getattr(n.func, "id", ""))
        for n in ast.walk(node) if isinstance(n, ast.Call)
    ]
    assert "ChangeLog" in calls, "non parla al registro dei cambiamenti"
    assert "schedule" in calls, "non sveglia nessuno"
    assert "apply" in calls, "non passa dalla governance"

    source = (HERE / "connected/service.py").read_text(encoding="utf-8")
    for invented in ("DeliveryService", "NotificationProvider", "push"):
        assert invented not in source, f"si è costruito un {invented} suo"


def test_a_self_originated_signal_can_never_be_passed_on():
    """
    §18: structural, because the behavioural version passes on the happy path.

    The check that keeps ORA from acting on its own writes sits before
    anything expensive, and a refactor that moved it below the judgement
    would restore the loop while every other test stayed green.
    """
    node = _code_only(_tree("connected/service.py"))
    interpret = next(
        n for n in ast.walk(node)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "interpret"
    )
    body = ast.dump(interpret)
    assert "self_originated" in body, "non riconosce più il proprio lavoro"

    # The recognition must sit above the judgement in the statement list, not
    # merely appear somewhere in the function. Measured on the loop's own
    # body so an import at the top cannot satisfy it.
    loop = next(n for n in ast.walk(interpret) if isinstance(n, ast.For))
    statements = [ast.dump(stmt) for stmt in loop.body]
    recognised = next(
        i for i, stmt in enumerate(statements) if "self_originated" in stmt
    )
    judged = next(
        i for i, stmt in enumerate(statements) if "interpret_signal" in stmt
    )
    assert recognised < judged, (
        "chiede un giudizio sul proprio lavoro prima di riconoscerlo"
    )


def test_a_failed_sync_never_reports_success():
    """
    §23: structural, because the honest path and the lying path look alike.

    Every exit from `sync` must leave the source saying something true about
    itself. The dangerous refactor is one that returns early on failure
    without recording it — and then a degraded calendar reports as connected.
    """
    node = _code_only(_tree("connected/service.py"))
    sync = next(
        n for n in ast.walk(node)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "sync"
    )
    handlers = [n for n in ast.walk(sync) if isinstance(n, ast.ExceptHandler)]
    assert handlers, "un sync senza rete di sicurezza"
    for handler in handlers:
        calls = [
            getattr(n.func, "attr", getattr(n.func, "id", ""))
            for n in ast.walk(handler) if isinstance(n, ast.Call)
        ]
        assert "note_failure" in calls, "un fallimento che non lascia traccia"


def test_no_provider_token_can_reach_a_persisted_model():
    """
    §30/§31: the boundary that matters most now that the data is real.

    Nothing in the connected model has a field a credential could live in,
    and nothing in the module reads one. The audit is structural because a
    token that leaks into a stored document is a token that leaks into a
    backup, a log and a support ticket.
    """
    from connected.models import ConnectedSignal, ConnectedSource

    for model in (ConnectedSource, ConnectedSignal):
        for name in model.model_fields:
            assert not any(
                bad in name.lower()
                for bad in ("token", "secret", "password", "credential", "bearer")
            ), f"{model.__name__}.{name}"

    for name in ("sources.py", "signals.py", "service.py", "calendar_sensor.py"):
        source = (HERE / f"connected/{name}").read_text(encoding="utf-8")
        for bad in ("access_token", "refresh_token", "secret_reference"):
            assert bad not in source, f"connected/{name} tocca {bad}"
