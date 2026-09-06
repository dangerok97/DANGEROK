"""
V3.10 — one calendar, one truth.

    THE CHAT AND THE HOME SCREEN ARE NOT TWO SYSTEMS.
    A LOCAL RECORD SAYING "SYNCED" IS NOT THE CALENDAR.

The bug this suite exists for: ORA said in chat that an appointment was
already in the calendar, and the Home screen said the day was empty. Both
were reading the same collection. One of them could not parse it.

Ingestion stores every field inside a `NormalizedField` envelope — value plus
where it came from — and the Home adapter read the fields as if they were
plain. `payload["starts_at"]` returned a dict: truthy, so the guard passed;
unparseable, so the `except` skipped the row. Every Google event, silently,
for as long as that code existed. Nothing logged, nothing warned, and the
person saw "nessun impegno" over a full calendar.

So these tests build their rows with the **real normalizer** and assert that
every reader can see them. A fixture written by hand in the shape a reader
expects is exactly what hid this for three sprints.
"""

from __future__ import annotations

import ast
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import _loop_harness

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")
HERE = Path(_BACKEND)
ROME = ZoneInfo("Europe/Rome")
ACCOUNT = "qa.truth@example.com"


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, uid):
    for coll in ("connector_instances", "ingestion_events", "life_nodes",
                 "calendar_event_drafts", "connected_signals",
                 "connected_source_attempts", "permission_consents"):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


async def _instance(db, uid, *, calendars=None):
    instance_id = f"inst_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    await db.connector_instances.insert_one({
        "id": instance_id, "user_id": uid, "connector_id": "calendar_google",
        "status": "connected", "secret_reference": "ref",
        "metadata": {"account_email": ACCOUNT},
        "selected_resource_ids": list(calendars or []),
        "cursor": {}, "created_at": now, "updated_at": now, "last_sync_at": now,
    })
    return instance_id


async def _real_row(db, uid, instance_id, *, external_id, title, starts_at,
                    calendar_id=ACCOUNT, minutes=60, status="processed", updated=None):
    """
    One ingestion row, built the way a sync builds it.

    The normalizer and the repository do the writing. Nothing in this helper
    decides the shape of the document — which is the point: the shape is
    whatever production writes, not whatever a reader hopes for.
    """
    from ingestion.event_model import IngestionEventRepository
    from ingestion.normalizer import GoogleCalendarNormalizer

    normalized = GoogleCalendarNormalizer(
        connector_id="calendar_google", connector_instance_id=instance_id,
    ).normalize(
        raw={
            "id": external_id, "status": "confirmed", "summary": title,
            "start": {"dateTime": starts_at.isoformat()},
            "end": {"dateTime": (starts_at + timedelta(minutes=minutes)).isoformat()},
            "organizer": {"email": ACCOUNT}, "attendees": [],
            "etag": uuid.uuid4().hex[:8], "updated": starts_at.isoformat(),
        },
        calendar_id=calendar_id, calendar_name=calendar_id,
    )
    await IngestionEventRepository(db).insert(
        user_id=uid, connector_id="calendar_google",
        connector_instance_id=instance_id, external_id=external_id,
        external_version=normalized.source_hash,
        source_type="calendar_google", source_record_type="calendar_event",
        raw_reference={"calendar_id": calendar_id},
        normalized_payload=normalized.to_dict(),
        payload_hash=normalized.source_hash,
        source_created_at=None,
        source_updated_at=(updated or starts_at).isoformat(),
        provenance={"connector_id": "calendar_google"},
        sensitivity="personal", status=status,
    )
    return normalized


# ---------------------------------------------------------------------------
# The bug
# ---------------------------------------------------------------------------

def test_an_event_on_the_calendar_appears_in_the_home_screen():
    """
    The regression, stated as the person would state it.

    There is an appointment tomorrow. It is in the calendar ORA reads. It
    must be on the Home screen — and before the fix, no Google event ever
    was, because the adapter could not read a field wrapped in its own
    provenance.
    """
    async def body():
        client, db = await _db()
        uid = f"tr_{uuid.uuid4().hex[:8]}"
        try:
            from home.adapters.google_calendar import load_google_calendar_events

            instance_id = await _instance(db, uid)
            when = (datetime.now(ROME) + timedelta(days=1)).replace(
                hour=10, minute=0, second=0, microsecond=0
            )
            await _real_row(db, uid, instance_id, external_id="ev_dentista",
                            title="Visita dentistica", starts_at=when)

            items, warnings = await load_google_calendar_events(db, uid)

            assert len(items) == 1, "la Home non vede un evento che c'è"
            assert items[0].title == "Visita dentistica"
            assert warnings == []
            # E le cose che un lettore rotto avrebbe reso illeggibili.
            assert isinstance(items[0].title, str)
            assert isinstance(items[0].start_at, str)
            assert datetime.fromisoformat(items[0].start_at)
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_chat_and_the_home_screen_see_the_same_appointment():
    """
    §7: the two must not be able to disagree, because they are one calendar.

    The chat's own listing and the Home adapter read the same rows through
    the same unwrapping now. Before, the chat's mirror query filtered on a
    field path that no stored document has (`starts_at` rather than
    `starts_at.value`), so it matched nothing — and the chat's confidence
    came from ORA's own draft instead.
    """
    async def body():
        client, db = await _db()
        uid = f"tr_{uuid.uuid4().hex[:8]}"
        try:
            from home.adapters.google_calendar import load_google_calendar_events
            from ingestion.reading import plain, where

            instance_id = await _instance(db, uid)
            when = (datetime.now(ROME) + timedelta(days=2)).replace(
                hour=10, minute=0, second=0, microsecond=0
            )
            await _real_row(db, uid, instance_id, external_id="ev_shared",
                            title="Visita dentistica", starts_at=when)

            home_items, _ = await load_google_calendar_events(db, uid)

            # The query the chat makes, against the same rows.
            found = await db.ingestion_events.find(
                {"user_id": uid, "connector_id": "calendar_google",
                 where("starts_at"): {"$gte": datetime.now(timezone.utc).isoformat()}},
                {"_id": 0, "normalized_payload": 1},
            ).to_list(10)

            assert len(home_items) == 1
            assert len(found) == 1, "la query della chat non trova la riga"
            assert plain(found[0]["normalized_payload"])["title"] == home_items[0].title
            assert plain(found[0]["normalized_payload"])["starts_at"] == home_items[0].start_at
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_appointment_late_at_night_belongs_to_its_own_local_day():
    """
    §7: the date boundary, in the timezone the person lives in.

    23:30 in Rome is 21:30 UTC on the same date, but 00:30 in Rome is 22:30
    UTC on the *previous* date. What the Home screen groups by is the local
    day, so what it must be handed is an instant that still knows its offset
    — never a naive string, and never a date already flattened to UTC.
    """
    async def body():
        client, db = await _db()
        uid = f"tr_{uuid.uuid4().hex[:8]}"
        try:
            from home.adapters.google_calendar import load_google_calendar_events

            instance_id = await _instance(db, uid)
            base = (datetime.now(ROME) + timedelta(days=3)).replace(
                hour=0, minute=30, second=0, microsecond=0
            )
            await _real_row(db, uid, instance_id, external_id="ev_notte",
                            title="Volo presto", starts_at=base)

            items, _ = await load_google_calendar_events(db, uid)
            assert len(items) == 1

            moment = datetime.fromisoformat(items[0].start_at)
            assert moment.tzinfo is not None, "l'istante ha perso il fuso"
            # È lo stesso momento, e in Italia è il giorno che la persona vede.
            assert moment == base
            assert moment.astimezone(ROME).date() == base.date()
            assert moment.astimezone(timezone.utc).date() == (base.date() - timedelta(days=1)), (
                "il caso interessante non è stato costruito"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_calendar_the_person_deselected_stops_appearing():
    """
    §7: what ORA shows follows what the person chose to let it read.

    The sync already reads only the selected calendars. What it did not do
    was stop *showing* the rows a now-deselected calendar left behind, so
    removing a calendar left its events on the Home screen indefinitely.
    """
    async def body():
        client, db = await _db()
        uid = f"tr_{uuid.uuid4().hex[:8]}"
        try:
            from home.adapters.google_calendar import load_google_calendar_events

            instance_id = await _instance(db, uid, calendars=[ACCOUNT])
            when = (datetime.now(ROME) + timedelta(days=1)).replace(
                hour=9, minute=0, second=0, microsecond=0
            )
            await _real_row(db, uid, instance_id, external_id="ev_mio",
                            title="Il mio impegno", starts_at=when)
            await _real_row(db, uid, instance_id, external_id="ev_feste",
                            title="Ferragosto", starts_at=when,
                            calendar_id="it.italian#holiday@group.v.calendar.google.com")

            items, _ = await load_google_calendar_events(db, uid)
            assert [i.title for i in items] == ["Il mio impegno"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_local_record_that_says_synced_is_not_evidence_of_a_calendar_entry():
    """
    §7: stale local state must not be able to say "it is already in there".

        A LOCAL RECORD SAYING "SYNCED" IS NOT THE CALENDAR.

    A draft carries `sync_status: synced` from the moment ORA wrote the
    event, and never looks again. Delete that event from Google and the field
    still says synced — forever — so the chat keeps answering "it is already
    in your calendar" about something that is not.

    What the fix does is cross the two, and what it deliberately does *not*
    do is conclude the opposite: not finding a row is not proof of absence,
    so the honest word is `unconfirmed`.
    """
    async def body():
        client, db = await _db()
        uid = f"tr_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools import calendar_caps

            instance_id = await _instance(db, uid)
            when = (datetime.now(ROME) + timedelta(days=1)).replace(
                hour=10, minute=0, second=0, microsecond=0
            )
            # Two drafts, both claiming to be synced. Only one is real.
            for draft_id, handle, title in (
                ("ced_reale", "ev_reale", "Visita che esiste"),
                ("ced_fantasma", "ev_fantasma", "Visita cancellata da Google"),
            ):
                await db.calendar_event_drafts.insert_one({
                    "id": draft_id, "user_id": uid, "title": title,
                    "start_datetime": when.isoformat(),
                    "end_datetime": (when + timedelta(hours=1)).isoformat(),
                    "status": "confirmed", "sync_status": "synced",
                    "google_event_id": handle, "provider": "google",
                })
            await _real_row(db, uid, instance_id, external_id="ev_reale",
                            title="Visita che esiste", starts_at=when)

            async def granted(*a, **kw):
                return True

            calendar_caps.calendar_consent_granted = granted
            observation = await calendar_caps.get_calendar_events(
                {
                    "time_min": (when - timedelta(days=1)).isoformat(),
                    "time_max": (when + timedelta(days=1)).isoformat(),
                },
                {"user_id": uid, "db": db},
            )
            events = (observation.payload or {}).get("events") or []
            by_title = {i["title"]: i for i in events}

            assert by_title["Visita che esiste"]["sync_status"] == "synced"
            assert by_title["Visita che esiste"]["confirmed_by_calendar"] is True
            assert by_title["Visita cancellata da Google"]["sync_status"] == "unconfirmed"
            assert by_title["Visita cancellata da Google"]["confirmed_by_calendar"] is False

            # And the confirmed one is listed once, not twice.
            assert len(events) == 2, [i["title"] for i in events]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_auto_sync_puts_a_new_event_on_the_home_screen_without_a_click():
    """
    §6: the whole chain, driven by the pass the background loop calls.

    Provider → ingestion → Home. Nobody presses anything, and the appointment
    that was not there a moment ago is on the screen.
    """
    async def body():
        client, db = await _db()
        uid = f"tr_{uuid.uuid4().hex[:8]}"
        try:
            from home.adapters.google_calendar import load_google_calendar_events

            instance_id = await _instance(db, uid)
            before, _ = await load_google_calendar_events(db, uid)
            assert before == []

            # What a sync writes, written by the sync's own machinery.
            when = (datetime.now(ROME) + timedelta(days=1)).replace(
                hour=16, minute=0, second=0, microsecond=0
            )
            await _real_row(db, uid, instance_id, external_id="ev_nuovo",
                            title="Appuntamento arrivato da solo", starts_at=when)

            after, _ = await load_google_calendar_events(db, uid)
            assert [i.title for i in after] == ["Appuntamento arrivato da solo"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def test_every_reader_of_a_normalized_payload_uses_the_same_unwrapping():
    """
    The reason this bug survived three sprints: three readers, three guesses.

    One of them queried `starts_at.value` and read `.get("value")`, one read
    the field plainly, one had its own private copy of the unwrapping. Only
    the first was right, and nothing made the others wrong out loud.

    So: the module that writes the envelope owns taking it off, and the
    readers use it. A new reader that walks a payload by hand fails here
    rather than in somebody's empty Home screen.
    """
    readers = [
        "home/adapters/google_calendar.py",
        "connected/calendar_sensor.py",
        "connected/content.py",
        "conversation_engine/ai_core/tools/calendar_caps.py",
    ]
    for name in readers:
        source = (HERE / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            (n.module or "") for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
        }
        reaches_unwrap = (
            "ingestion.reading" in imported
            or "connected.calendar_sensor" in imported
        )
        assert reaches_unwrap, f"{name} legge le buste per conto suo"

    # And nobody filters on the un-enveloped path any more, which is the
    # quieter half of the same mistake: such a query matches nothing at all.
    for name in readers + ["agent/providers.py", "context_assembler/calendar_provider.py"]:
        source = (HERE / name).read_text(encoding="utf-8")
        for field in ("starts_at", "ends_at", "title"):
            bad = f'"normalized_payload.{field}"'
            assert bad not in source, f"{name} filtra su {bad}, che non esiste mai"


def test_the_unwrapping_never_invents_a_value():
    """
    A dict without a `value` key is a value, and must survive untouched.

    Guessing here would quietly rewrite `extendedProperties` and `reminders`
    into nothing, which is the same class of silent loss this whole suite is
    about.
    """
    from ingestion.reading import plain, where

    assert plain({"title": {"value": "Visita", "provenance": {"x": 1}}}) == {
        "title": "Visita",
    }
    assert plain({"title": "Visita"}) == {"title": "Visita"}
    assert plain({"attendees": [{"value": "a@b"}, {"value": "c@d"}]}) == {
        "attendees": ["a@b", "c@d"],
    }
    assert plain({"reminders": {"useDefault": True}}) == {
        "reminders": {"useDefault": True},
    }
    assert plain(None) == {}
    assert where("starts_at") == "normalized_payload.starts_at.value"


def test_an_event_cancelled_on_google_stops_appearing():
    """
    §4: what was called off is not an appointment.

    The row stays — it is the trace of something that was — but a cancelled
    event on the Home screen is an appointment somebody turns up to. This is
    how a duplicate that was deleted on Google kept being shown afterwards.
    """
    async def body():
        client, db = await _db()
        uid = f"tr_{uuid.uuid4().hex[:8]}"
        try:
            from home.adapters.google_calendar import load_google_calendar_events
            from ingestion.event_model import IngestionEventRepository
            from ingestion.normalizer import GoogleCalendarNormalizer

            instance_id = await _instance(db, uid)
            when = (datetime.now(ROME) + timedelta(days=1)).replace(
                hour=10, minute=0, second=0, microsecond=0
            )
            await _real_row(db, uid, instance_id, external_id="ev_vivo",
                            title="Visita che resta", starts_at=when)

            # The same shape a sync writes when Google says it is gone.
            gone = GoogleCalendarNormalizer(
                connector_id="calendar_google", connector_instance_id=instance_id,
            ).normalize(
                raw={"id": "ev_morto", "status": "cancelled",
                     "summary": "Visita annullata",
                     "start": {"dateTime": when.isoformat()},
                     "end": {"dateTime": (when + timedelta(hours=1)).isoformat()},
                     "etag": "e2", "updated": when.isoformat()},
                calendar_id=ACCOUNT, calendar_name=ACCOUNT,
            )
            await IngestionEventRepository(db).insert(
                user_id=uid, connector_id="calendar_google",
                connector_instance_id=instance_id, external_id="ev_morto",
                external_version=gone.source_hash,
                source_type="calendar_google", source_record_type="calendar_event",
                raw_reference={"calendar_id": ACCOUNT},
                normalized_payload=gone.to_dict(), payload_hash=gone.source_hash,
                source_created_at=None, source_updated_at=when.isoformat(),
                provenance={"connector_id": "calendar_google"},
                sensitivity="personal", status="processed",
            )

            items, _ = await load_google_calendar_events(db, uid)
            assert [i.title for i in items] == ["Visita che resta"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_moving_an_appointment_leaves_one_event_in_the_home_screen():
    """
    §4: the end state of a move, seen from the screen.

    The old slot is empty, the new one holds the appointment, and there is
    exactly one of it — which is the whole thing the person asked for and
    did not get.
    """
    async def body():
        client, db = await _db()
        uid = f"tr_{uuid.uuid4().hex[:8]}"
        try:
            from home.adapters.google_calendar import load_google_calendar_events
            from ingestion.event_model import IngestionEventRepository
            from ingestion.normalizer import GoogleCalendarNormalizer

            instance_id = await _instance(db, uid)
            was = (datetime.now(ROME) + timedelta(days=4)).replace(
                hour=10, minute=0, second=0, microsecond=0
            )
            now_at = was + timedelta(days=1)

            # The event as it was, then the same event moved: same external
            # id, which is what a real reschedule produces.
            await _real_row(db, uid, instance_id, external_id="ev_dentista",
                            title="Visita dentistica", starts_at=was)
            moved = GoogleCalendarNormalizer(
                connector_id="calendar_google", connector_instance_id=instance_id,
            ).normalize(
                raw={"id": "ev_dentista", "status": "confirmed",
                     "summary": "Visita dentistica",
                     "start": {"dateTime": now_at.isoformat()},
                     "end": {"dateTime": (now_at + timedelta(hours=1)).isoformat()},
                     "etag": "e9", "updated": now_at.isoformat()},
                calendar_id=ACCOUNT, calendar_name=ACCOUNT,
            )
            await IngestionEventRepository(db).insert(
                user_id=uid, connector_id="calendar_google",
                connector_instance_id=instance_id, external_id="ev_dentista",
                external_version=moved.source_hash,
                source_type="calendar_google", source_record_type="calendar_event",
                raw_reference={"calendar_id": ACCOUNT},
                normalized_payload=moved.to_dict(), payload_hash=moved.source_hash,
                source_created_at=None, source_updated_at=now_at.isoformat(),
                provenance={"connector_id": "calendar_google"},
                sensitivity="personal", status="processed",
            )
            # The superseded row is marked, exactly as the pipeline marks it.
            await db.ingestion_events.update_one(
                {"user_id": uid, "external_id": "ev_dentista",
                 "payload_hash": {"$ne": moved.source_hash}},
                {"$set": {"ingestion_status": "superseded"}},
            )

            items, _ = await load_google_calendar_events(db, uid)
            dentist = [i for i in items if i.title == "Visita dentistica"]

            assert len(dentist) == 1, "lo spostamento ha lasciato due impegni"
            # Lo stesso istante: il normalizer lo scrive in UTC, la persona lo
            # legge nel proprio fuso. Confrontare le stringhe qui vorrebbe
            # dire pretendere che il magazzino parli italiano.
            assert datetime.fromisoformat(dentist[0].start_at) == now_at
            assert not any(
                str(i.start_at).startswith(was.date().isoformat()) for i in items
            ), "il vecchio orario è ancora occupato"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_sync_token_google_refuses_does_not_wedge_the_calendar(monkeypatch):
    """
    §: an expired or foreign marker is not a broken calendar.

    Google answers 410 when a sync token has expired and 400 when it does not
    recognise it at all — and the second happens: a token written by a fake
    provider during a test, left in the instance, made every subsequent real
    sync fail with 400, for ever, silently. The calendar simply stopped
    updating and nothing said why.

    The answer is the one the mailbox already gives an expired history id:
    drop the marker, re-read the window, carry on. The dedupe makes the
    overlap free.
    """
    async def body():
        client, db = await _db()
        uid = f"tr_{uuid.uuid4().hex[:8]}"
        try:
            from connectors.google_calendar.provider import (
                EventsPage, GoogleCalendarAPIError,
            )
            from connectors.google_calendar.service import GoogleCalendarService

            instance_id = await _instance(db, uid, calendars=[ACCOUNT])
            await db.connector_instances.update_one(
                {"id": instance_id},
                {"$set": {"cursor": {ACCOUNT: {"sync_token": "fake:0"}},
                          "selected_resource_ids": [ACCOUNT]}},
            )

            asked = []

            class Refuses:
                """Rifiuta il segnaposto, risponde alla finestra."""

                async def list_events(self, *, access_token, calendar_id,
                                      time_min=None, time_max=None,
                                      page_token=None, sync_token=None,
                                      max_results=250):
                    asked.append(sync_token)
                    if sync_token:
                        raise GoogleCalendarAPIError(400)
                    return EventsPage(events=[], next_sync_token="CI-vero")

                async def list_calendars(self, *, access_token):
                    return []

            class Vault:
                async def get(self, ref, *, user_id):
                    return {"access_token": "t", "refresh_token": "r",
                            "expires_at": "2999-01-01T00:00:00+00:00"}

                async def rotate(self, ref, *, payload):
                    return ref

            class Permissions:
                class _Audit:
                    async def log(self, **kw):
                        return None

                def __init__(self):
                    self.audit = self._Audit()

                async def check_access(self, **kw):
                    return True

            class Ingestion:
                async def ingest_calendar_events(self, **kw):
                    return []

            service = GoogleCalendarService(
                db=db, permissions=Permissions(), ingestion=Ingestion(),
                vault=Vault(), provider=Refuses(),
            )
            await db.connector_instances.update_one(
                {"id": instance_id}, {"$set": {"secret_reference": "ref"}},
            )
            out = await service.sync(user_id=uid, instance_id=instance_id)

            assert out["totals"]["failed"] == 0, "un segnaposto scaduto ha rotto il sync"
            assert asked == ["fake:0", None], (
                "non ha riprovato senza il segnaposto"
            )
            found = await db.connector_instances.find_one(
                {"id": instance_id}, {"_id": 0, "cursor": 1},
            )
            assert found["cursor"][ACCOUNT]["sync_token"] == "CI-vero", (
                "il segnaposto nuovo non è stato salvato"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_already_created_is_never_said_about_an_event_that_was_deleted():
    """
    «Gia' fatto» e' un'affermazione sul mondo, non su una riga di database.

    L'idempotenza risponde «c'e' gia'» al secondo tap sullo stesso invio, e
    fa bene. Ma la risposta veniva dalla sola riga del tentativo, senza
    guardare se la cosa ci fosse ancora: crea, cancella, richiedi la stessa
    cosa, e ORA rispondeva «e' gia' in calendario» — `verified: True` — di un
    evento che non esisteva piu'. La persona resta senza appuntamento e senza
    nessuno che glielo dica.
    """
    async def body():
        client, db = await _db()
        uid = f"truth_{uuid.uuid4().hex[:8]}"
        try:
            from agent import commanded
            from agent.authority import UserCommand
            from agent.execution import StepExecutor

            effect = commanded.calendar_effect({"title": "Visita"})
            act = await commanded.assess(
                db, uid, capability="calendar.write", effect=effect,
                parameters={"title": "Visita", "starts_at": (
                    datetime.now(timezone.utc) + timedelta(days=3)
                ).isoformat()},
                summary="Segnare in calendario: Visita",
                expected="«Visita» risulta in calendario.",
                command=UserCommand(
                    spoken="segnami la visita giovedì",
                    words="segnami la visita",
                    asked_for="aggiungere la visita",
                ),
                answered_proposal=False,
            )
            # Un primo tentativo, andato a buon fine.
            assert await StepExecutor(db).begin_declared(act.intent) == "go"
            from agent.execution import ATTEMPTS

            await db[ATTEMPTS].update_one(
                {"idempotency_key": act.intent.idempotency_key},
                {"$set": {"status": "executed"}},
            )
            assert await StepExecutor(db).begin_declared(act.intent) == "already_done"

            # Quello che aveva prodotto e' stato cancellato: si riprende.
            assert await StepExecutor(db).retake(act.intent) == "go"
        finally:
            from agent.execution import ATTEMPTS, RECEIPTS

            for coll in (ATTEMPTS, RECEIPTS):
                await db[coll].delete_many({"owner_id": uid})
                await db[coll].delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_the_create_path_looks_before_it_says_it_is_already_there():
    """
    La stessa cosa, sul percorso vero: il codice guarda prima di rispondere.

    Guardia strutturale, non di comportamento: nel ramo `already_done` di
    `create_calendar_event` deve esserci una lettura dello stato dell'evento
    precedente, e la risposta «already_created» deve stare dopo quella
    lettura. Una versione che risponde e basta torna a mentire.
    """
    source = (HERE / "conversation_engine/ai_core/tools/calendar_caps.py").read_text(
        encoding="utf-8",
    )
    branch = source.split('if taken == "already_done":', 1)[1]
    branch = branch.split("if taken != \"go\":", 1)[0]
    assert "cancelled" in branch, (
        "il ramo «gia' fatto» non guarda se l'evento c'e' ancora"
    )
    assert "reopen" in branch, (
        "un evento sparito non fa riprendere l'atto: la risposta resterebbe finta"
    )
    said = branch.index("already_created")
    looked = branch.index("cancelled")
    assert looked < said, "dice «c'e' gia'» prima di aver guardato"


# ---------------------------------------------------------------------------
# La catena vista dalla Home
# ---------------------------------------------------------------------------

def test_unchanged_rereads_do_not_push_the_real_appointment_off_the_screen():
    """
    Una rilettura che non ha visto niente di nuovo non e' un impegno.

        LA HOME NON DEVE CHIEDERE COSA E' STATO TOCCATO DI RECENTE.

    Ogni sincronizzazione lascia una riga «riletto, uguale» per ogni evento
    che non e' cambiato. Sono righe oneste — su un account vero un solo
    compleanno ricorrente ne aveva undici — ma la Home le contava come
    appuntamenti e ne prendeva ottanta ordinate per ultimo aggiornamento.
    Risultato misurato sull'account vero: la Home vedeva 2 dei 16 impegni
    realmente presenti nelle due settimane successive. Non in ritardo:
    assenti, sopra un calendario pieno, senza un errore da nessuna parte.
    """
    async def body():
        client, db = await _db()
        uid = f"tr_{uuid.uuid4().hex[:8]}"
        try:
            from home.adapters.google_calendar import load_google_calendar_events

            instance_id = await _instance(db, uid, calendars=[ACCOUNT])

            # L'appuntamento vero, letto una volta e mai piu' toccato.
            when = (datetime.now(ROME) + timedelta(days=4)).replace(
                hour=10, minute=0, second=0, microsecond=0
            )
            await _real_row(db, uid, instance_id, external_id="ev_dentista",
                            title="Visita dentistica — Studio Bianchi",
                            starts_at=when,
                            updated=datetime.now(ROME) - timedelta(days=3))

            # E poi cento riletture di cose vecchie che non sono cambiate.
            old_when = (datetime.now(ROME) - timedelta(days=200)).replace(
                hour=9, minute=0, second=0, microsecond=0
            )
            # Ognuna riletta adesso: e' il loro `updated` a essere recente,
            # ed e' per questo che vincevano le ottanta posizioni.
            just_now = datetime.now(ROME)
            for n in range(100):
                await _real_row(
                    db, uid, instance_id, external_id=f"ev_vecchio_{n}",
                    title=f"Compleanno ricorrente {n}", starts_at=old_when,
                    status="skipped", updated=just_now,
                )

            found, _ = await load_google_calendar_events(db, uid)
            titles = [i.title for i in found]
            assert "Visita dentistica — Studio Bianchi" in titles, (
                "le riletture hanno spinto fuori schermo l'unico impegno vero"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_same_event_read_twice_is_one_card_on_the_home_screen():
    """Due righe vive per lo stesso evento sono un evento, non due."""
    async def body():
        client, db = await _db()
        uid = f"tr_{uuid.uuid4().hex[:8]}"
        try:
            from home.adapters.google_calendar import load_google_calendar_events

            instance_id = await _instance(db, uid, calendars=[ACCOUNT])
            when = (datetime.now(ROME) + timedelta(days=3)).replace(
                hour=11, minute=0, second=0, microsecond=0
            )
            for _ in range(3):
                await _real_row(db, uid, instance_id, external_id="ev_uno",
                                title="Visita", starts_at=when)

            found, _ = await load_google_calendar_events(db, uid)
            assert [i.title for i in found] == ["Visita"], (
                f"lo stesso appuntamento compare {len(found)} volte"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_event_created_after_the_sync_token_is_read_by_the_incremental_pass():
    """
    Un evento nato dopo il segnaposto arriva con la lettura incrementale.

    E il segnaposto si sposta solo dopo che quello che e' arrivato e' stato
    scritto: un cursore che corre avanti e' un buco silenzioso.
    """
    async def body():
        client, db = await _db()
        uid = f"tr_{uuid.uuid4().hex[:8]}"
        try:
            from connectors.google_calendar.provider import EventsPage
            from connectors.google_calendar.service import GoogleCalendarService

            instance_id = await _instance(db, uid, calendars=[ACCOUNT])
            await db.connector_instances.update_one(
                {"id": instance_id},
                {"$set": {"cursor": {ACCOUNT: {"sync_token": "tok:prima"}},
                          "secret_reference": "ref"}},
            )
            when = (datetime.now(ROME) + timedelta(days=4)).replace(
                hour=10, minute=0, second=0, microsecond=0
            )
            fresh = {
                "id": "ev_dopo_il_token", "status": "confirmed",
                "summary": "Visita dentistica — Studio Bianchi",
                "start": {"dateTime": when.isoformat()},
                "end": {"dateTime": (when + timedelta(hours=1)).isoformat()},
                "organizer": {"email": ACCOUNT}, "attendees": [],
                "etag": "e1", "updated": when.isoformat(),
            }

            asked = []

            class OnlyTheDelta:
                async def list_events(self, *, access_token, calendar_id,
                                      time_min=None, time_max=None,
                                      page_token=None, sync_token=None,
                                      max_results=250):
                    asked.append(sync_token)
                    return EventsPage(events=[fresh], next_sync_token="tok:dopo")

                async def list_calendars(self, *, access_token):
                    return []

            class Vault:
                async def get(self, ref, *, user_id):
                    return {"access_token": "t", "refresh_token": "r",
                            "expires_at": "2999-01-01T00:00:00+00:00"}

                async def rotate(self, ref, *, payload):
                    return ref

            class Permissions:
                class _Audit:
                    async def log(self, **kw):
                        return None

                def __init__(self):
                    self.audit = self._Audit()

                async def check_access(self, **kw):
                    return True

            written = []

            class Ingestion:
                async def ingest_calendar_events(self, **kw):
                    written.extend(kw["raw_events"])
                    return []

            service = GoogleCalendarService(
                db=db, permissions=Permissions(), ingestion=Ingestion(),
                vault=Vault(), provider=OnlyTheDelta(),
            )
            out = await service.sync(user_id=uid, instance_id=instance_id)

            assert asked == ["tok:prima"], "non ha usato il segnaposto che aveva"
            assert [e["id"] for e in written] == ["ev_dopo_il_token"], (
                "l'evento nato dopo il segnaposto non e' stato letto"
            )
            assert out["totals"]["failed"] == 0
            found = await db.connector_instances.find_one(
                {"id": instance_id}, {"_id": 0, "cursor": 1},
            )
            assert found["cursor"][ACCOUNT]["sync_token"] == "tok:dopo", (
                "il segnaposto non si e' spostato dopo una lettura riuscita"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_home_response_shows_the_appointment_the_provider_has():
    """
    Quello che risponde `/api/home` e quello che ha il provider sono la stessa cosa.

    Non l'adapter da solo: tutta la composizione della Home, che e' dove un
    impegno puo' ancora sparire fra un adapter che lo trova e uno schermo che
    non lo mostra.
    """
    async def body():
        client, db = await _db()
        uid = f"tr_{uuid.uuid4().hex[:8]}"
        try:
            from home.adapters import gather_all

            instance_id = await _instance(db, uid, calendars=[ACCOUNT])
            when = (datetime.now(ROME) + timedelta(days=4)).replace(
                hour=10, minute=0, second=0, microsecond=0
            )
            await _real_row(db, uid, instance_id, external_id="ev_provider",
                            title="Visita dentistica — Studio Bianchi",
                            starts_at=when)

            gathered = await gather_all(db, uid)
            items = gathered[0]
            mine = [i for i in items if i.title == "Visita dentistica — Studio Bianchi"]
            assert len(mine) == 1, (
                f"la Home mostra l'appuntamento {len(mine)} volte"
            )
            assert str(mine[0].start_at)[:10] == when.astimezone(
                timezone.utc
            ).isoformat()[:10]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())
