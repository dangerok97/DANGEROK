"""
V3.10 Sprint 3 — the mailbox as an instrument.

    A MAILBOX IS NOT A THING TO COPY. IT IS A THING TO NOTICE CHANGES IN.
    A FAILED READING IS NOT AN EMPTY INBOX.

The connector half: cursors, expiry, duplicates, minimisation, and the fact
that nothing here can write. Everything runs against the fake provider, which
shares no parsing with the real one on purpose.

It opens with a test about the calendar, which belongs here because it is
the same mistake in the same place: a sensor that reads ingestion rows must
read the rows ingestion actually writes, and the only way to be sure of that
is to let the real pipeline write one.

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
from ingestion.reading import plain

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")
HERE = Path(_BACKEND)
ACCOUNT = "io@example.com"


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, uid):
    for coll in (
        "ingestion_events", "connector_instances", "connected_signals",
        "connected_source_attempts", "connected_content_reads",
        "connected_situation_links", "permission_consents", "permission_audit",
        "documents", "memories", "life_objects", "agent_receipts",
    ):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


class AlwaysConsents:
    """Permissions, reduced to what this layer actually asks of them."""

    class _Audit:
        def __init__(self):
            self.rows = []

        async def log(self, **kw):
            self.rows.append(kw)

    def __init__(self, allow=True):
        self.allow = allow
        self.audit = self._Audit()

    async def check_access(self, **kw):
        return self.allow


class OpenVault:
    async def get(self, ref, *, user_id):
        return {"access_token": "t", "refresh_token": "r",
                "expires_at": "2999-01-01T00:00:00+00:00"}

    async def rotate(self, ref, *, payload):
        return ref


async def _instance(db, uid, *, cursor=None):
    instance_id = f"inst_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    await db.connector_instances.insert_one({
        "id": instance_id, "user_id": uid, "connector_id": "mail_gmail",
        "status": "connected", "secret_reference": "vault_ref",
        "metadata": {"account_email": ACCOUNT},
        "cursor": dict(cursor or {}),
        "created_at": now, "updated_at": now, "last_sync_at": now,
    })
    return instance_id


def _service(db, provider, *, allow=True):
    from connectors.gmail.service import GmailReadService

    return GmailReadService(
        db=db, permissions=AlwaysConsents(allow), vault=OpenVault(),
        provider=provider,
    )


def _mailbox(**kw):
    from connectors.gmail.provider import FakeGmailProvider

    return FakeGmailProvider(**kw)


# ---------------------------------------------------------------------------
# The sensor reads what the pipeline writes
# ---------------------------------------------------------------------------

def test_the_calendar_sensor_reads_rows_the_real_pipeline_wrote():
    """
    The row is built by ingestion, not by this test.

    Sprint 1 filtered calendar rows on `source_type == "calendar"` and read
    each field as a plain string. Real rows carry the connector's own id
    there — "calendar_google" — and each field wrapped with its own
    provenance. So the sensor matched nothing that a sync had ever written,
    and would have read every real mailbox and calendar as an empty world.

    Every test in Sprint 1 and 2 passed, because every one of them wrote its
    own fixture in the shape its own sensor expected. This one cannot: the
    normalizer and the repository build the row, exactly as a sync does.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected import calendar_sensor
            from ingestion.event_model import IngestionEventRepository
            from ingestion.normalizer import GoogleCalendarNormalizer

            instance_id = f"inst_{uuid.uuid4().hex[:8]}"
            when = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
                microsecond=0
            )
            raw = {
                "id": "ev_real", "status": "confirmed", "summary": "Visita",
                "location": "Studio Centro",
                "start": {"dateTime": when.isoformat()},
                "end": {"dateTime": (when + timedelta(hours=1)).isoformat()},
                "organizer": {"email": ACCOUNT},
                "attendees": [], "etag": "e1", "updated": when.isoformat(),
            }
            normalized = GoogleCalendarNormalizer(
                connector_id="calendar_google", connector_instance_id=instance_id,
            ).normalize(raw=raw, calendar_id="primary", calendar_name="Primary")

            await IngestionEventRepository(db).insert(
                user_id=uid, connector_id="calendar_google",
                connector_instance_id=instance_id, external_id="ev_real",
                external_version=normalized.source_hash,
                source_type="calendar_google", source_record_type="calendar_event",
                raw_reference={"calendar_id": "primary"},
                normalized_payload=normalized.to_dict(),
                payload_hash=normalized.source_hash,
                source_created_at=None, source_updated_at=None,
                provenance={"connector_id": "calendar_google"},
                sensitivity="personal", status="processed",
            )

            signals = await calendar_sensor.read_changes(
                db, uid, source_id=instance_id, account=ACCOUNT,
            )

            assert len(signals) == 1, "il sensore non vede le righe vere"
            assert signals[0].source_object_ref == "ev_real"
            # And the envelope came off: a title is a title, not a dict.
            assert "Visita" in signals[0].payload_summary
            assert signals[0].relationship == "own"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Reading a mailbox
# ---------------------------------------------------------------------------

def test_a_first_reading_writes_one_row_per_message_and_no_body():
    """
    §31: what is stored is what a life can be sensed through, and no more.

    The row holds who it is from as a relationship, what it is about, when it
    arrived and whether anything was attached. What it does not hold is the
    message: nobody with this collection gets to read somebody's mail.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            secret = "Il codice IBAN è IT60X0542811101000000123456"
            mailbox = _mailbox()
            mailbox.add("m1", thread_id="t1", headers={
                "From": "Studio Dentistico <info@studio.it>",
                "To": ACCOUNT, "Subject": "Conferma appuntamento",
            }, body=secret)
            instance_id = await _instance(db, uid)

            out = await _service(db, mailbox).sync(user_id=uid, instance_id=instance_id)

            assert out["written"] == 1
            rows = await db.ingestion_events.find(
                {"user_id": uid}, {"_id": 0}
            ).to_list(5)
            assert len(rows) == 1
            payload = rows[0]["normalized_payload"]
            assert payload["subject"] == "Conferma appuntamento"
            assert payload["thread_ref"] == "t1"
            assert payload["content_available"] is True
            assert rows[0]["source_record_type"] == "email_message"

            blob = str(rows)
            assert "IT60" not in blob, "il corpo del messaggio è stato salvato"
            assert "info@studio.it" not in blob, "l'indirizzo del mittente è salvato"
            assert mailbox.body_reads == [], "il sync ha letto un corpo"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_same_message_twice_is_one_row():
    """§10: a history replay, a retry and an overlapping pass are one arrival."""
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            mailbox = _mailbox()
            mailbox.add("m1", thread_id="t1", headers={"Subject": "Ciao"})
            instance_id = await _instance(db, uid)
            service = _service(db, mailbox)

            first = await service.sync(user_id=uid, instance_id=instance_id)
            second = await service.sync(user_id=uid, instance_id=instance_id)

            assert first["written"] == 1
            assert second["written"] == 0 and second["skipped"] == 1
            assert await db.ingestion_events.count_documents({"user_id": uid}) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_expired_cursor_resyncs_instead_of_reporting_an_empty_mailbox():
    """
    §30/§40: Gmail forgets positions after about a week. That is not a failure.

    The wrong answers are both available and both bad: treat the 404 as an
    error and the mailbox goes dark, or treat it as "nothing new" and a week
    of somebody's life silently disappears. The right answer is a bounded
    resync, and the dedupe makes the overlap free.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            mailbox = _mailbox()
            mailbox.add("m1", thread_id="t1", headers={"Subject": "Vecchio"})
            mailbox.expired_history.add("999")
            instance_id = await _instance(db, uid, cursor={"history_id": "999"})

            out = await _service(db, mailbox).sync(user_id=uid, instance_id=instance_id)

            assert out["resynced"] is True
            assert out["written"] == 1, "una casella viva è stata letta come vuota"

            # And the recovered messages are not duplicated on the next pass.
            again = await _service(db, mailbox).sync(user_id=uid, instance_id=instance_id)
            assert again["written"] == 0
            assert await db.ingestion_events.count_documents({"user_id": uid}) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_message_that_was_deleted_does_not_stop_the_whole_reading():
    """
    Un messaggio cancellato fra due letture non e' una casella rotta.

    La history nomina cosa e' cambiato, e una mail arrivata e poi buttata via
    resta nominata li'. Chiederla risponde 404. Quel 404 usciva dall'intera
    lettura: bastava un messaggio cancellato perche' la casella non venisse
    piu' letta — mai piu', in silenzio, con il cursore fermo e la schermata
    che continuava a dire «connesso». E' successo davvero, sull'account su
    cui questa cosa veniva dimostrata: tre email nuove non arrivavano, e la
    ragione era una quarta che non c'era piu'.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            mailbox = _mailbox()
            mailbox.add("m1", thread_id="t1", headers={"Subject": "Prima"})
            mailbox.add("gone", thread_id="t2", headers={"Subject": "Sparita"})
            mailbox.add("m2", thread_id="t3", headers={"Subject": "Dopo"})
            mailbox.vanished.add("gone")
            instance_id = await _instance(db, uid)

            out = await _service(db, mailbox).sync(user_id=uid, instance_id=instance_id)

            assert out["ok"] is True, "un messaggio sparito ha fermato la lettura"
            assert out["written"] == 2, "gli altri messaggi non sono stati letti"
            subjects = {
                plain(r["normalized_payload"])["subject"]
                for r in await db.ingestion_events.find(
                    {"user_id": uid}, {"_id": 0, "normalized_payload": 1},
                ).to_list(10)
            }
            assert subjects == {"Prima", "Dopo"}

            # E il cursore si e' mosso: la lettura e' finita davvero.
            instance = await db.connector_instances.find_one(
                {"id": instance_id}, {"_id": 0, "cursor": 1, "last_sync_at": 1},
            )
            assert instance["cursor"].get("history_id")
            assert instance.get("last_sync_at")
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_cursor_only_moves_after_a_reading_that_finished():
    """
    §30: a position that ran ahead of what was read is a silent hole.

    A sync that failed halfway and still advanced the cursor loses everything
    in the gap, forever and without a trace — so a failed reading leaves the
    position exactly where it was.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connectors.gmail.provider import GmailAPIError

            class Breaks:
                async def profile(self, **kw):
                    return {"historyId": "500"}

                async def list_messages(self, **kw):
                    raise GmailAPIError(500)

                async def history(self, **kw):
                    raise GmailAPIError(500)

                async def metadata_of(self, **kw):
                    return {}

                async def body_of(self, **kw):
                    return ""

            instance_id = await _instance(db, uid, cursor={"history_id": "100"})
            with pytest.raises(GmailAPIError):
                await _service(db, Breaks()).sync(user_id=uid, instance_id=instance_id)

            found = await db.connector_instances.find_one(
                {"id": instance_id}, {"_id": 0, "cursor": 1}
            )
            assert found["cursor"]["history_id"] == "100", "il cursore è avanzato"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_mailbox_nobody_consented_to_is_not_read():
    """§32: consent is checked here, not assumed by whoever calls."""
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from permissions.errors import ConsentDenied

            mailbox = _mailbox()
            mailbox.add("m1", thread_id="t1", headers={"Subject": "Ciao"})
            instance_id = await _instance(db, uid)

            with pytest.raises(ConsentDenied):
                await _service(db, mailbox, allow=False).sync(
                    user_id=uid, instance_id=instance_id,
                )
            assert await db.ingestion_events.count_documents({"user_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_one_mailbox_never_answers_for_another_person():
    """§32: owner isolation, on the read that would leak it."""
    async def body():
        client, db = await _db()
        mine = f"s3_{uuid.uuid4().hex[:8]}"
        theirs = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected import email_sensor

            mailbox = _mailbox()
            mailbox.add("m1", thread_id="t1", headers={"Subject": "Privato"})
            instance_id = await _instance(db, mine)
            await _service(db, mailbox).sync(user_id=mine, instance_id=instance_id)

            seen = await email_sensor.read_changes(
                db, theirs, source_id=instance_id,
            )
            assert seen == [], "la posta di una persona è arrivata a un'altra"
        finally:
            await _clean(db, mine)
            await _clean(db, theirs)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Who sent it
# ---------------------------------------------------------------------------

def test_sender_relationship_is_evidence_and_never_a_guess():
    """
    §21: three answers derivable from facts, and `unknown` for everything else.

    The tempting fourth — guessing "organization" from a domain — is absent,
    because a hospital, a bank and an airline are strangers from here and
    sorting them by string would be deciding what matters in a life from a
    hostname.
    """
    from connectors.gmail.service import sender_relationship

    def message(headers):
        return {"payload": {"headers": [
            {"name": k, "value": v} for k, v in headers.items()
        ]}}

    known = {"amico@example.com"}
    assert sender_relationship(
        message({"From": ACCOUNT}), account=ACCOUNT, known=known,
    ) == "self"
    assert sender_relationship(
        message({"From": "news@shop.it", "List-Unsubscribe": "<https://x>"}),
        account=ACCOUNT, known=known,
    ) == "automated"
    assert sender_relationship(
        message({"From": "noreply@banca.it"}), account=ACCOUNT, known=known,
    ) == "automated"
    assert sender_relationship(
        message({"From": "Amico <amico@example.com>"}), account=ACCOUNT, known=known,
    ) == "known_person"
    # An airline confirming a flight is a stranger, and saying so is honest.
    assert sender_relationship(
        message({"From": "conferme@compagnia.it"}), account=ACCOUNT, known=known,
    ) == "unknown"


def test_somebody_from_their_calendar_is_a_known_person():
    """§21: `known_person` is evidence — this address has been in a room with them."""
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            await db.ingestion_events.insert_one({
                "id": "ing_x", "user_id": uid, "connector_id": "calendar_google",
                "connector_instance_id": "inst_cal", "external_id": "ev1",
                "source_type": "calendar_google",
                "source_record_type": "calendar_event",
                "normalized_payload": {
                    "organizer": {"value": "capo@azienda.it"},
                    "attendees": [{"value": "collega@azienda.it"}],
                },
                "ingested_at": datetime.now(timezone.utc).isoformat(),
            })
            mailbox = _mailbox()
            mailbox.add("m1", thread_id="t1", headers={
                "From": "collega@azienda.it", "Subject": "Domani",
            })
            instance_id = await _instance(db, uid)
            await _service(db, mailbox).sync(user_id=uid, instance_id=instance_id)

            row = await db.ingestion_events.find_one(
                {"user_id": uid, "source_record_type": "email_message"}, {"_id": 0}
            )
            assert row["normalized_payload"]["sender_relationship"] == "known_person"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Nothing here can act
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


def test_the_mail_connector_has_no_way_to_send_anything():
    """
    §3/§47: read verbs only, checked in the code rather than promised in a doc.

    A connector that could send would only need one caller to become a system
    that sends mail on somebody's behalf. There is no such method, and the
    absence is asserted where a refactor would notice.
    """
    for name in ("connectors/gmail/provider.py", "connectors/gmail/service.py"):
        tree = _code_only(_tree(name))
        # Every literal string in the module: an endpoint that could write is
        # a path before it is anything else, and a path is a constant here.
        literals = [
            n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        ]
        # As paths, which is the only form an endpoint takes. Matching the
        # bare word would trip over `sender_relationship` and teach the next
        # person to loosen the guard, which is worse than not having one.
        for verb in ("/send", "/trash", "/untrash", "/modify", "/drafts",
                     "/batchDelete", "/batchModify"):
            assert not any(verb in text for text in literals), (
                f"{name} nomina un endpoint di scrittura: {verb}"
            )

    # And the HTTP client itself has only one method.
    provider = _code_only(_tree("connectors/gmail/provider.py"))
    calls = {
        getattr(n.func, "attr", "")
        for n in ast.walk(provider) if isinstance(n, ast.Call)
    }
    assert not ({"post", "put", "patch", "delete"} & calls), (
        f"il provider scrive: {calls & {'post', 'put', 'patch', 'delete'}}"
    )


def test_the_email_sensor_cannot_reach_anything_that_acts():
    """
    §46: signal → reasoning → goal → authority → action, with no shortcut.

    The dangerous version of this sprint writes itself: an email says
    cancelled, so remove the event. This walks the sensor for any route to
    the machinery that could, including the import that would be step one.
    """
    for name in ("connected/email_sensor.py", "connected/situations.py"):
        tree = _tree(name)
        imported = {
            (n.module or "") for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
        } | {
            a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
            for a in n.names
        }
        for forbidden in ("agent.effects", "agent.execution", "goal_engine",
                          "agent.service", "delivery"):
            assert not any(forbidden in m for m in imported), (
                f"{name} importa {forbidden}"
            )
        source = ast.dump(_code_only(tree))
        for acting in ("create_goal", "create_event", "update_event",
                       "delete_event", "run_effect", "schedule"):
            assert acting not in source, f"{name} agisce: {acting}"


def test_the_mailbox_source_advertises_no_way_to_write():
    """§4: a source that claimed a write capability is the first step to having one."""
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected.service import ConnectedLifeService

            instance_id = await _instance(db, uid)
            found = await ConnectedLifeService(db).sources.list(uid)
            mailbox = next(s for s in found if s.source_type == "email")

            assert mailbox.write_capabilities == []
            assert mailbox.provider == "Gmail"
            assert mailbox.account_ref == ACCOUNT
            # And it is described to a person the way a calendar is: what it
            # is, whether it works, when it was read. Nothing about cursors.
            assert set(mailbox.for_human()) == {"what", "state", "last_read_at"}
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_mailbox_that_cannot_be_read_says_so_rather_than_looking_empty():
    """§29/§40: failure and emptiness are different words, and always were."""
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected.service import ConnectedLifeService

            instance_id = await _instance(db, uid)
            service = ConnectedLifeService(db)
            await service.sources.note_failure(uid, instance_id, error="GmailAPIError")

            mailbox = next(
                s for s in await service.sources.list(uid) if s.source_type == "email"
            )
            assert mailbox.status == "degraded"
            # Still worth trying again — that is what degraded means — but
            # emphatically not something to state as how the world is.
            assert mailbox.is_readable is True
            assert mailbox.can_be_leaned_on is False
            assert mailbox.for_human()["state"] != "Connesso"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())
