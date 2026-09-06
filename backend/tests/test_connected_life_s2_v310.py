"""
V3.10 Sprint 2 — from sensing to knowing.

    WITHHELD IS NOT UNREACHABLE. IT IS UNKEPT.
    A REPLACED DOCUMENT IS NOT A SECOND ARRIVAL.
    ONE CHANGE IS ONE SIGNAL, HOWEVER MANY ROWS THE PROVIDER SENT.
    AN APPOINTMENT SOMEBODY WAS INVITED TO IS SOMEBODY ELSE'S DECISION.

Sprint 1 built the senses and left four things it had honestly declared: the
withheld content was unreachable, the shelf could only see arrivals, a
recurring series looked like fifty appointments, and whose an event was got
recorded and never read. Each of those is a way the same system quietly
misdescribes a life, and each has its own test here.

The one that needed the most care is the first. Making private content
reachable is exactly the change that undoes a privacy boundary if it is done
casually, so the tests are about the boundary rather than about the feature:
it is fetched only when a judgement said it could not decide, it reaches one
prompt, and there is nowhere in the system it can come to rest.

No live model calls.
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
CALENDAR = "cal_s2@example.com"
ACCOUNT = "io@example.com"


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, uid):
    for coll in (
        "connected_signals", "connected_source_attempts", "connected_object_state",
        "connected_content_reads", "connector_instances", "ingestion_events",
        "documents", "memories", "ambient_wakes", "meaningful_changes",
        "calendar_event_drafts", "agent_receipts", "permission_consents",
        "permission_audit",
    ):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


def _when(days=1, hour=10):
    moment = datetime.now(timezone.utc) + timedelta(days=days)
    return moment.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


async def _instance(db, uid):
    instance_id = f"inst_{uuid.uuid4().hex[:8]}"
    await db.connector_instances.insert_one({
        "id": instance_id, "user_id": uid, "connector_id": "calendar_google",
        "status": "connected",
        "metadata": {"default_calendar_id": CALENDAR, "account_email": ACCOUNT},
        "cursor": {}, "last_sync_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return instance_id


async def _ingested(db, uid, instance_id, *, external_id, supersedes=None, **payload):
    row_id = f"ing_{uuid.uuid4().hex[:12]}"
    body = {
        "title": "Visita", "starts_at": _when(), "status": "confirmed",
        "location": "", "attendees": [], "description": "",
        "etag": uuid.uuid4().hex[:8],
    }
    body.update(payload)
    await db.ingestion_events.insert_one({
        "id": row_id, "user_id": uid, "connector_id": "calendar_google",
        "connector_instance_id": instance_id, "external_id": external_id,
        "source_type": "calendar_google", "source_record_type": "calendar_event",
        "ingestion_status": "processed", "normalized_payload": body,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "supersedes_event_id": supersedes,
    })
    return row_id


async def _watermark(db, uid) -> str:
    """Where a sync would leave the mark: the newest row it has already read."""
    rows = await db.ingestion_events.find(
        {"user_id": uid}, {"_id": 0, "ingested_at": 1}
    ).sort("ingested_at", -1).to_list(1)
    return str(rows[0]["ingested_at"]) if rows else ""


async def _document(db, uid, doc_id, **fields):
    now = datetime.now(timezone.utc).isoformat()
    base = {
        "id": doc_id, "user_id": uid, "title": "Referto", "tags": [],
        "notes": "", "hash": "h1", "archived": False, "deleted": False,
        "created_at": now, "updated_at": now,
    }
    base.update(fields)
    await db.documents.replace_one({"id": doc_id, "user_id": uid}, base, upsert=True)
    return base


def _fields(signal) -> dict:
    return {c.field: c for c in signal.changed_fields}


class Recorded:
    """Judgements replayed. A list, because a re-ask is a second call."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.seen_payloads = []

    async def __call__(self, system, user):
        self.seen_payloads.append(user)
        if not self.answers:
            return None
        answer = self.answers.pop(0)
        return dict(answer) if isinstance(answer, dict) else answer


def _install(monkeypatch, model):
    import connected.reasoning as reasoning

    monkeypatch.setattr(reasoning, "_ask_model", model)
    return model


def _service(db):
    from connected.service import ConnectedLifeService

    return ConnectedLifeService(db)


# ---------------------------------------------------------------------------
# The withheld content
# ---------------------------------------------------------------------------

def test_content_is_fetched_only_when_the_judgement_says_it_must(monkeypatch):
    """
    A judgement that can decide without the note never causes it to be read.

    This is the half that keeps the feature from undoing the boundary. A
    layer that fetched content "in case it helps" would be a layer that reads
    everybody's private notes on every sync, and it would pass any test that
    only checked the happy path.
    """
    async def body():
        client, db = await _db()
        uid = f"s2_{uuid.uuid4().hex[:8]}"
        try:
            from connected.models import ConnectedSignal, FieldChange

            # There is a real note behind this signal, and it is reachable.
            # The point of the test is that nothing reaches for it.
            secret = "Il codice del portone è 4471"
            instance_id = await _instance(db, uid)
            await _ingested(db, uid, instance_id, external_id="ev_1",
                            description=secret)

            service = _service(db)
            await service.signals.record(ConnectedSignal(
                owner_id=uid, source_type="calendar", source_id=instance_id,
                signal_type="calendar.event.changed", source_object_ref="ev_1",
                changed_fields=[FieldChange(field="description", content_withheld=True)],
            ))
            model = _install(monkeypatch, Recorded([
                {"outcome": "noise", "what_it_means": "", "relates_to": "",
                 "reasoning": "reg.", "needs_content": False},
            ]))

            out = await service.interpret(uid)

            assert out["looked_at"] == 1, "ha chiesto due volte senza motivo"
            assert out["asked_for_content"] == 0
            assert len(model.seen_payloads) == 1
            assert secret not in model.seen_payloads[0]
            assert "what_you_asked_to_see" not in model.seen_payloads[0], (
                "il prompt contiene una sezione che nessuno ha chiesto"
            )
            assert await db.connected_content_reads.count_documents(
                {"owner_id": uid}
            ) == 0, "ha letto una nota privata che nessuno aveva chiesto"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_content_reaches_one_prompt_and_is_kept_nowhere(monkeypatch):
    """
    §1: asked for, seen once, and gone.

    The note travels into the second call and into nothing else — not the
    signal, not the seen-state, not the audit row, not the change log. The
    audit says a read happened and which fields; anybody with that collection
    learns nothing they did not already have.
    """
    async def body():
        client, db = await _db()
        uid = f"s2_{uuid.uuid4().hex[:8]}"
        try:
            from connected.models import ConnectedSignal, FieldChange

            secret = "Portare gli esami del sangue, dott. Rossi, 333 1234567"
            instance_id = await _instance(db, uid)
            await _ingested(db, uid, instance_id, external_id="ev_note",
                            description=secret)

            service = _service(db)
            await service.signals.record(ConnectedSignal(
                owner_id=uid, source_type="calendar", source_id=instance_id,
                signal_type="calendar.event.changed", source_object_ref="ev_note",
                payload_summary="Di «Visita» è cambiato: le note.",
                changed_fields=[FieldChange(field="description", content_withheld=True)],
            ))
            model = _install(monkeypatch, Recorded([
                {"outcome": "noise", "what_it_means": "", "relates_to": "",
                 "reasoning": "non posso decidere senza la nota",
                 "needs_content": True,
                 "why_content": "la nota potrebbe dire cosa portare"},
                {"outcome": "may_need_action",
                 "what_it_means": "Deve ricordarsi di portare gli esami.",
                 "relates_to": "la visita", "reasoning": "reg.",
                 "needs_content": False},
            ]))

            out = await service.interpret(uid)

            assert out["asked_for_content"] == 1
            assert out["passed_on"] == 1
            assert len(model.seen_payloads) == 2

            # It reached the second prompt, and only the second.
            assert secret not in model.seen_payloads[0]
            assert "esami del sangue" in model.seen_payloads[1]

            # And nowhere else at all.
            for collection in (
                "connected_signals", "connected_object_state",
                "connected_content_reads", "meaningful_changes",
            ):
                rows = await db[collection].find(
                    {"$or": [{"owner_id": uid}, {"user_id": uid}]}, {"_id": 0}
                ).to_list(20)
                blob = str(rows)
                assert secret not in blob, f"la nota è finita in {collection}"
                assert "333 1234567" not in blob, f"un numero è finito in {collection}"

            # The read is on the record, without what was read.
            reads = await db.connected_content_reads.find(
                {"owner_id": uid}, {"_id": 0}
            ).to_list(5)
            assert len(reads) == 1
            assert reads[0]["fields"] == ["description"]
            assert reads[0]["why"], "una lettura senza una ragione"
            assert "content" not in reads[0] and "value" not in reads[0]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_judgement_is_asked_at_most_once_more(monkeypatch):
    """
    A model that keeps asking gets one answer and then decides.

    Without this, a judgement that returns `needs_content` every time would
    loop — and each turn of that loop is a real read of somebody's private
    record.
    """
    async def body():
        client, db = await _db()
        uid = f"s2_{uuid.uuid4().hex[:8]}"
        try:
            from connected.models import ConnectedSignal, FieldChange

            instance_id = await _instance(db, uid)
            await _ingested(db, uid, instance_id, external_id="ev_loop",
                            description="qualcosa")
            service = _service(db)
            await service.signals.record(ConnectedSignal(
                owner_id=uid, source_type="calendar", source_id=instance_id,
                signal_type="calendar.event.changed", source_object_ref="ev_loop",
                changed_fields=[FieldChange(field="description", content_withheld=True)],
            ))
            asking = {"outcome": "noise", "what_it_means": "", "relates_to": "",
                      "reasoning": "ancora", "needs_content": True,
                      "why_content": "ancora"}
            model = _install(monkeypatch, Recorded([asking, asking, asking]))

            out = await service.interpret(uid)

            assert len(model.seen_payloads) == 2, "ha continuato a chiedere"
            assert out["asked_for_content"] == 1
            assert await db.connected_content_reads.count_documents(
                {"owner_id": uid}
            ) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_answer_given_after_seeing_the_content_does_not_ask_again(monkeypatch):
    """
    §1: the second answer is the last one, whatever it says.

    The service asks once and then decides, so a model stuck on
    `needs_content` cannot loop it. This is the same rule stated one layer
    down, where the answer itself is assembled: once the content has been
    shown, the answer that comes back is not allowed to be a request for it.
    Belt and braces, and cheap — the thing on the other side of the loop is a
    repeated read of somebody's private record.
    """
    async def body():
        client, db = await _db()
        uid = f"s2_{uuid.uuid4().hex[:8]}"
        try:
            from connected import reasoning

            asking = {"outcome": "noise", "what_it_means": "", "relates_to": "",
                      "reasoning": "ancora", "needs_content": True,
                      "why_content": "ancora"}
            _install(monkeypatch, Recorded([asking, asking]))

            first = await reasoning.interpret_signal(
                {"in_words": "qualcosa è cambiato"},
                life={}, source={}, recent=[],
            )
            assert first["needs_content"] is True

            after = await reasoning.interpret_signal(
                {"in_words": "qualcosa è cambiato"},
                life={}, source={}, recent=[],
                content={"description": "la nota"},
            )
            assert after["needs_content"] is False, "chiede di nuovo ciò che ha visto"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_other_peoples_addresses_are_never_the_content(monkeypatch):
    """
    §1: an attendee list is not a thing to hand a model, even on request.

    "Two people are on it" is what a judgement about somebody's afternoon
    needs. Their addresses are third-party personal data and there is no
    question about this person's day that requires them.
    """
    async def body():
        client, db = await _db()
        uid = f"s2_{uuid.uuid4().hex[:8]}"
        try:
            from connected import content as private
            from connected.models import ConnectedSignal, FieldChange

            instance_id = await _instance(db, uid)
            await _ingested(
                db, uid, instance_id, external_id="ev_people",
                attendees=["capo@azienda.it", "collega@azienda.it"],
                organizer="capo@azienda.it",
            )
            signal = ConnectedSignal(
                owner_id=uid, source_type="calendar", source_id=instance_id,
                signal_type="calendar.event.changed", source_object_ref="ev_people",
                changed_fields=[
                    FieldChange(field="attendees", content_withheld=True),
                    FieldChange(field="organizer", content_withheld=True),
                ],
            )
            seen = await private.read_transiently(db, uid, signal, why="test")

            assert seen == {"attendees": "2 persone", "organizer": "qualcun altro"}
            assert "azienda.it" not in str(seen)
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# The shelf
# ---------------------------------------------------------------------------

def test_a_replaced_document_is_not_a_second_arrival(monkeypatch):
    """
    §2: the criterion, exactly as written.

    A document whose file is replaced must produce one `updated`, not a
    second `added`. The difference is whether ORA can tell it has met this
    file before — and a system that cannot will greet the same document every
    time somebody edits it.
    """
    async def body():
        client, db = await _db()
        uid = f"s2_{uuid.uuid4().hex[:8]}"
        try:
            from connected import documents_sensor

            await _document(db, uid, "doc_1", title="Contratto", hash="h1")
            first = await documents_sensor.read_changes(db, uid)
            assert [s.signal_type for s in first] == ["document.added"]

            # Same document, different file behind it.
            await _document(db, uid, "doc_1", title="Contratto", hash="h2")
            second = await documents_sensor.read_changes(db, uid)

            assert len(second) == 1
            assert second[0].signal_type == "document.updated"
            assert "content" in _fields(second[0])
            assert _fields(second[0])["content"].content_withheld is True

            # And a third reading with nothing new says nothing.
            assert await documents_sensor.read_changes(db, uid) == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_document_put_away_says_so(monkeypatch):
    """§2: `document.removed`, from the record rather than from a guess."""
    async def body():
        client, db = await _db()
        uid = f"s2_{uuid.uuid4().hex[:8]}"
        try:
            from connected import documents_sensor

            await _document(db, uid, "doc_2", title="Vecchia bolletta")
            await documents_sensor.read_changes(db, uid)

            await _document(db, uid, "doc_2", title="Vecchia bolletta", deleted=True)
            signals = await documents_sensor.read_changes(db, uid)

            assert len(signals) == 1
            assert signals[0].signal_type == "document.removed"
            assert "messo via" in signals[0].payload_summary
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_private_annotation_on_a_document_is_a_fact_without_its_words(monkeypatch):
    """§1/§2: the same minimisation rule, on the second sensor."""
    async def body():
        client, db = await _db()
        uid = f"s2_{uuid.uuid4().hex[:8]}"
        try:
            from connected import documents_sensor

            await _document(db, uid, "doc_3", notes="")
            await documents_sensor.read_changes(db, uid)
            await _document(db, uid, "doc_3", notes="IBAN IT60X0542811101000000123456")
            signals = await documents_sensor.read_changes(db, uid)

            assert len(signals) == 1
            note = _fields(signals[0])["notes"]
            assert note.content_withheld is True
            assert "IT60" not in signals[0].model_dump_json()

            # Nor in the memory that makes the comparison possible.
            rows = await db.connected_object_state.find(
                {"owner_id": uid}, {"_id": 0}
            ).to_list(5)
            assert "IT60" not in str(rows), "il ricordo si è tenuto la nota"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Recurring series
# ---------------------------------------------------------------------------

def test_a_series_changing_is_one_signal_not_one_per_occurrence(monkeypatch):
    """
    §3: the criterion, exactly as written.

    A rule change makes the provider hand back the master and every
    occurrence it regenerated. Reporting fifty appointments moving would
    describe the world wrongly and cost fifty judgements — one thing changed.
    """
    async def body():
        client, db = await _db()
        uid = f"s2_{uuid.uuid4().hex[:8]}"
        try:
            from connected import calendar_sensor

            instance_id = await _instance(db, uid)
            master = await _ingested(
                db, uid, instance_id, external_id="ev_master",
                title="Corso", starts_at=_when(1, 18),
                recurrence_rule="FREQ=WEEKLY;BYDAY=MO",
            )
            occurrences = []
            for n in range(3):
                occurrences.append(await _ingested(
                    db, uid, instance_id, external_id=f"ev_occ_{n}",
                    title="Corso", starts_at=_when(1 + n * 7, 18),
                    recurrence_instance_id="ev_master",
                ))
            await calendar_sensor.read_changes(db, uid, source_id=instance_id)
            watermark = await _watermark(db, uid)

            # The rule moves the whole thing to Tuesdays at 19.
            await _ingested(
                db, uid, instance_id, external_id="ev_master", title="Corso",
                starts_at=_when(2, 19), recurrence_rule="FREQ=WEEKLY;BYDAY=TU",
                supersedes=master,
            )
            for n in range(3):
                await _ingested(
                    db, uid, instance_id, external_id=f"ev_occ_{n}", title="Corso",
                    starts_at=_when(2 + n * 7, 19),
                    recurrence_instance_id="ev_master", supersedes=occurrences[n],
                )

            # And in the same pass, a lesson is added to the series.
            await _ingested(
                db, uid, instance_id, external_id="ev_occ_extra", title="Corso",
                starts_at=_when(30, 19), recurrence_instance_id="ev_master",
            )

            signals = await calendar_sensor.read_changes(
                db, uid, source_id=instance_id, since=watermark,
            )
            changed = [s for s in signals if s.signal_type == "calendar.event.changed"]
            assert len(changed) == 1, f"{len(changed)} segnali per un cambio di regola"
            assert changed[0].source_object_ref == "ev_master"
            assert changed[0].covers == 4, changed[0].covers
            assert "si ripete" in changed[0].payload_summary
            assert changed[0].for_ai()["how_many_occurrences_this_covers"] == 4

            # The new lesson is a second piece of news and was not swallowed.
            created = [s for s in signals if s.signal_type == "calendar.event.created"]
            assert [s.source_object_ref for s in created] == ["ev_occ_extra"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_one_occurrence_moved_on_its_own_is_its_own_news(monkeypatch):
    """
    §3: folding is arithmetic on sets, not a decision that instances matter less.

    Somebody moving next Monday's lesson without touching the series is a
    different event in their life, and a fold that swallowed it would be the
    old mistake wearing a new name.
    """
    async def body():
        client, db = await _db()
        uid = f"s2_{uuid.uuid4().hex[:8]}"
        try:
            from connected import calendar_sensor

            instance_id = await _instance(db, uid)
            master = await _ingested(
                db, uid, instance_id, external_id="ev_m2", title="Corso",
                starts_at=_when(1, 18), recurrence_rule="FREQ=WEEKLY",
            )
            occurrence = await _ingested(
                db, uid, instance_id, external_id="ev_o2", title="Corso",
                starts_at=_when(1, 18), recurrence_instance_id="ev_m2",
            )
            await calendar_sensor.read_changes(db, uid, source_id=instance_id)
            watermark = await _watermark(db, uid)

            # The series is renamed; one occurrence also moves room.
            await _ingested(
                db, uid, instance_id, external_id="ev_m2", title="Corso avanzato",
                starts_at=_when(1, 18), recurrence_rule="FREQ=WEEKLY",
                supersedes=master,
            )
            await _ingested(
                db, uid, instance_id, external_id="ev_o2", title="Corso avanzato",
                starts_at=_when(1, 18), location="Aula 3",
                recurrence_instance_id="ev_m2", supersedes=occurrence,
            )

            signals = await calendar_sensor.read_changes(
                db, uid, source_id=instance_id, since=watermark,
            )
            refs = {s.source_object_ref for s in signals}
            assert refs == {"ev_m2", "ev_o2"}, (
                "l'occorrenza che si è mossa da sola è stata inghiottita"
            )
            alone = next(s for s in signals if s.source_object_ref == "ev_o2")
            assert "location" in _fields(alone)
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Whose it is
# ---------------------------------------------------------------------------

def test_whose_appointment_it_is_reaches_the_judgement(monkeypatch):
    """
    §4: recorded in Sprint 1, read from Sprint 2.

    The same appointment moving means one thing when the person arranged it
    and another when their manager did. Sprint 1 wrote the fact into the
    signal and nothing looked at it; now it travels to the judgement.
    """
    async def body():
        client, db = await _db()
        uid = f"s2_{uuid.uuid4().hex[:8]}"
        try:
            from connected import calendar_sensor

            instance_id = await _instance(db, uid)
            mine = await _ingested(db, uid, instance_id, external_id="ev_mine",
                                   organizer=ACCOUNT)
            theirs = await _ingested(db, uid, instance_id, external_id="ev_theirs",
                                     organizer="capo@azienda.it",
                                     attendees=[ACCOUNT])
            await _ingested(db, uid, instance_id, external_id="ev_mine",
                            organizer=ACCOUNT, starts_at=_when(1, 15),
                            supersedes=mine)
            await _ingested(db, uid, instance_id, external_id="ev_theirs",
                            organizer="capo@azienda.it", attendees=[ACCOUNT],
                            starts_at=_when(1, 15), supersedes=theirs)

            signals = await calendar_sensor.read_changes(
                db, uid, source_id=instance_id, account=ACCOUNT,
            )
            by_ref = {s.source_object_ref: s for s in signals}
            assert by_ref["ev_mine"].relationship == "own"
            assert by_ref["ev_theirs"].relationship == "invited"

            shown = by_ref["ev_theirs"].for_ai()["whose_it_is"]
            assert "invited" in shown or "somebody else" in shown
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_ora_may_not_rearrange_somebody_elses_commitment(monkeypatch):
    """
    §4: the criterion with teeth — the authority ceiling reads it.

        ORA DOES NOT REARRANGE OTHER PEOPLE'S DAYS.

    An instruction to move an appointment somebody was invited to is an
    instruction to reach into another person's day. It stops being a low-risk
    personal act and goes back to asking, exactly as adding a guest does —
    and the standing-permission offer disappears with it.
    """
    async def body():
        client, db = await _db()
        uid = f"s2_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import effect_is_commandable
            from agent.commanded import calendar_effect
            from connected.models import ConnectedSignal
            from connected.ownership import reaches_other_people

            service = _service(db)
            await db.calendar_event_drafts.insert_one({
                "id": "ced_shared", "user_id": uid,
                "google_event_id": "ev_boss", "title": "Riunione",
            })
            await db.calendar_event_drafts.insert_one({
                "id": "ced_mine", "user_id": uid,
                "google_event_id": "ev_solo", "title": "Dentista",
            })
            for ref, relationship in (("ev_boss", "invited"), ("ev_solo", "own")):
                await service.signals.record(ConnectedSignal(
                    owner_id=uid, source_type="calendar", source_id="s1",
                    signal_type="calendar.event.changed",
                    source_object_ref=ref, relationship=relationship,
                    after=ref,
                ))

            assert await reaches_other_people(db, uid, "ced_shared") is True
            assert await reaches_other_people(db, uid, "ced_mine") is False

            theirs = calendar_effect(
                {"calendar_ref": "ced_shared", "title": "Riunione"},
                reaches_others=True,
            )
            assert theirs.external_party is True
            allowed, why = effect_is_commandable(theirs)
            assert allowed is False and why == "reaches_somebody_else"

            # And the person's own appointment is untouched by this.
            ours = calendar_effect(
                {"calendar_ref": "ced_mine", "title": "Dentista"},
                reaches_others=False,
            )
            assert effect_is_commandable(ours) == (True, "")
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_event_never_observed_is_not_assumed_to_be_theirs(monkeypatch):
    """
    §4: the convenient guess is the dangerous one.

    An event ORA has never seen answers `unknown`, never `own`. Assuming
    ownership is precisely the assumption that would let it move a meeting it
    was merely invited to.
    """
    async def body():
        client, db = await _db()
        uid = f"s2_{uuid.uuid4().hex[:8]}"
        try:
            from connected.ownership import relationship_for_event

            assert await relationship_for_event(db, uid, "ev_never_seen") == "unknown"
            assert await relationship_for_event(db, uid, "") == "unknown"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def _tree(relative: str) -> ast.AST:
    return ast.parse((HERE / relative).read_text(encoding="utf-8"))


def _code_only(node):
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


def test_nothing_can_write_withheld_content_anywhere():
    """
    §1: the boundary, checked where a refactor would break it.

    The module that reads private content must have exactly one way to record
    that it did, and that record must have nowhere to put what was read. A
    behavioural test passes the day somebody adds a `"content": text` to the
    audit row for debugging; this one fails.
    """
    tree = _tree("connected/content.py")
    body = _code_only(tree)

    writes = [
        n for n in ast.walk(body)
        if isinstance(n, ast.Call)
        and getattr(n.func, "attr", "") in ("insert_one", "update_one", "replace_one")
    ]
    assert len(writes) == 1, f"{len(writes)} scritture in un modulo che legge"

    stored = ast.dump(writes[0])
    for leaking in ("'content'", "'value'", "'text'", "'notes'", "'description'"):
        assert leaking not in stored, f"la riga di audit può contenere {leaking}"
    for required in ("'fields'", "'why'", "'read_at'", "'owner_id'"):
        assert required in stored, f"la riga di audit non dice {required}"


def test_content_reaches_the_prompt_and_no_other_caller():
    """
    §1: one entry point, and it is the reasoning boundary.

    Walks the service for what it does with the fetched content: it may pass
    it to the judgement and nothing else. A refactor that also handed it to
    the change log or the seen-state would be a leak that every behavioural
    test still passes.
    """
    node = _code_only(_tree("connected/service.py"))
    interpret = next(
        n for n in ast.walk(node)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "interpret"
    )

    users = []
    for call in [n for n in ast.walk(interpret) if isinstance(n, ast.Call)]:
        for kw in call.keywords:
            if isinstance(kw.value, ast.Name) and kw.value.id == "seen_content":
                users.append(getattr(call.func, "attr", getattr(call.func, "id", "")))
        for arg in call.args:
            if isinstance(arg, ast.Name) and arg.id == "seen_content":
                users.append(getattr(call.func, "attr", getattr(call.func, "id", "")))

    assert users, "il contenuto non arriva da nessuna parte"
    assert set(users) == {"interpret_signal"}, (
        f"il contenuto raggiunge anche: {set(users) - {'interpret_signal'}}"
    )


def test_the_fold_never_drops_an_occurrence_that_differs():
    """
    §3: the fold is a subset test, not a preference for masters.

    Structural because the tempting simplification — "an occurrence of a
    changed series is always redundant" — passes every happy-path test and
    silently loses the one appointment somebody actually moved.
    """
    node = _code_only(_tree("connected/calendar_sensor.py"))
    fold = next(
        n for n in ast.walk(node)
        if isinstance(n, ast.FunctionDef) and n.name == "_fold_series"
    )
    body = ast.dump(fold)
    assert "issubset" in body, "il ripiegamento non confronta gli insiemi"
    assert "changed_fields" in body

    source = (HERE / "connected/calendar_sensor.py").read_text(encoding="utf-8")
    for ranking in ("PRIORITY", "importance"):
        assert ranking not in ast.dump(_code_only(_tree("connected/calendar_sensor.py"))), (
            f"c'è una gerarchia: {ranking}"
        )


def test_sprint_2_added_no_actuators():
    """
    §5: the decision, written down as a test rather than as a promise.

    Connected Life senses. The only real write in the system remains
    `calendar.write` from V3.9, behind the authority ceiling that phase
    built — and this sprint deliberately did not add a second one. A guard
    rather than a note, because "we decided not to" is exactly the kind of
    decision that erodes without anybody choosing to erode it.
    """
    from agent.effects import wired_capabilities

    assert wired_capabilities() == ["calendar.write"]

    for name in (
        "models.py", "sources.py", "signals.py", "service.py", "seen.py",
        "content.py", "ownership.py", "calendar_sensor.py",
        "documents_sensor.py", "reasoning.py", "router.py",
    ):
        source = ast.dump(_code_only(_tree(f"connected/{name}")))
        for acting in ("create_event", "send", "run_effect", "execute", "delete_event"):
            assert acting not in source, f"connected/{name} agisce sul mondo: {acting}"
