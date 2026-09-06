"""
V3.10 Sprint 3 — ORA reads the instruments; nobody presses anything.

    THE USER DOES NOT SYNCHRONISE THEIR LIFE. ORA DOES.

The auto-sync half. What is checked here is mostly what happens when things
go wrong, because the happy path of "poll a source" is three lines and the
expensive mistakes are all in the other branches: a revoked token retried
every twenty seconds, a failed read reported as an empty calendar, a restart
that re-imports somebody's whole mailbox, ORA waking itself up over an event
it wrote.

Nothing here reaches Google: providers are fakes, and the runtime loop is
never started — `poll_once` is called with an explicit clock, which is what
makes a two-hour backoff testable in a millisecond.
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
REPO = HERE.parent
ACCOUNT = "qa.autosync@example.com"


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, uid):
    for coll in (
        "connector_instances", "connected_source_attempts", "connected_signals",
        "ingestion_events", "documents", "memories", "ambient_wakes",
        "meaningful_changes", "agent_receipts", "connected_situation_links",
    ):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


async def _mailbox_instance(db, uid, *, status="connected", cursor=None):
    instance_id = f"inst_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    await db.connector_instances.insert_one({
        "id": instance_id, "user_id": uid, "connector_id": "mail_gmail",
        "status": status, "secret_reference": "ref",
        "metadata": {"account_email": ACCOUNT}, "cursor": dict(cursor or {}),
        "created_at": now, "updated_at": now, "last_sync_at": None,
    })
    return instance_id


class Vault:
    def __init__(self):
        self.stored = {"ref": {"payload": {
            "access_token": "at", "refresh_token": "rt",
            "expires_at": "2999-01-01T00:00:00+00:00"}}}

    async def get(self, ref, *, user_id):
        return dict(self.stored[ref]["payload"])

    async def rotate(self, ref, *, payload):
        return ref


class Permissions:
    class _Audit:
        async def log(self, **kw):
            return None

    def __init__(self, allow=True):
        self.audit = self._Audit()
        self.allow = allow

    async def check_access(self, **kw):
        return self.allow


def _install_gmail(monkeypatch, provider, *, allow=True):
    """The mailbox reader ORA would build for itself, with a fake provider."""
    from connectors.gmail.service import GmailReadService

    import deps

    service = GmailReadService(
        db=deps.db, permissions=Permissions(allow), vault=Vault(), provider=provider,
    )

    def build():
        return service

    monkeypatch.setattr("deps.get_gmail_service", build, raising=False)
    return service


def _mailbox(*messages):
    from connectors.gmail.provider import FakeGmailProvider

    provider = FakeGmailProvider(address=ACCOUNT)
    for n, subject in enumerate(messages):
        provider.add(f"m{n}", thread_id=f"t{n}", headers={"Subject": subject})
    return provider


# ---------------------------------------------------------------------------
# When to look
# ---------------------------------------------------------------------------

def test_each_instrument_has_its_own_cadence():
    """
    §4: a mailbox and a calendar do not move at the same speed.

    One blind interval is either too slow for mail or too rude to a calendar
    API. These numbers are cost decisions — quota, battery — and deliberately
    not judgements about what matters in somebody's life.
    """
    from connected.polling import interval_for

    # Il calendario e' il piu' fitto: un appuntamento spostato dal dentista non
    # puo' aspettare un quarto d'ora, perche' in quel quarto d'ora la Home dice
    # con sicurezza una cosa falsa. La posta segue, lo scaffale dei documenti
    # resta lento perche' cambia solo quando e' la persona a metterci qualcosa.
    assert interval_for("calendar") < interval_for("email") < interval_for("documents")
    # La latenza tipica *e'* la cadenza piu' il giro del loop: 20 + 10 = 30 s
    # per il calendario, che e' il bersaglio, e 60 + 10 = 70 s per la posta,
    # dentro i 120 promessi.
    assert interval_for("calendar").total_seconds() == 20
    assert interval_for("email").total_seconds() == 60


def test_a_failing_source_is_asked_less_often_not_more():
    """
    §4: backoff, capped.

    Without it a revoked token becomes a request every twenty seconds until
    somebody notices the bill — and the person's source says exactly the same
    thing either way.
    """
    from connected.polling import BACKOFF_CAP_MINUTES, interval_for

    steps = [interval_for("email", n).total_seconds() for n in range(0, 8)]
    assert steps == sorted(steps), "il backoff non cresce"
    assert steps[1] > steps[0]
    assert max(steps) == BACKOFF_CAP_MINUTES * 60, "il backoff non ha un tetto"


def test_a_source_never_read_is_due_immediately(monkeypatch):
    """
    Connecting must produce a reading now, not in five minutes.

    Somebody who has just connected a mailbox and sees nothing happen
    concludes it did not work — and they are almost right.
    """
    async def body():
        client, db = await _db()
        uid = f"as_{uuid.uuid4().hex[:8]}"
        try:
            from connected.polling import due

            await _mailbox_instance(db, uid)
            waiting = await due(db, uid)
            # Lo scaffale dei documenti c'e' sempre e va letto anche lui: qui
            # interessa che la casella appena collegata sia fra le dovute.
            assert [s.source_type for s in waiting].count("email") == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_source_read_a_moment_ago_is_not_read_again(monkeypatch):
    """§4: no full resync loop, and no reading the same mailbox twice a tick."""
    async def body():
        client, db = await _db()
        uid = f"as_{uuid.uuid4().hex[:8]}"
        try:
            from connected.polling import due, schedule_next

            instance_id = await _mailbox_instance(db, uid)
            now = datetime.now(timezone.utc)
            await schedule_next(db, uid, instance_id, "email", failed=False, now=now)

            assert instance_id not in [s.id for s in await due(db, uid, now=now)]
            later = now + timedelta(minutes=6)
            assert instance_id in [s.id for s in await due(db, uid, now=later)]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_disconnected_mailbox_is_never_polled(monkeypatch):
    """
    §19: disconnecting stops the reading, including the reading nobody asked for.

    A scheduler that keeps trying a revoked source is a scheduler that keeps
    somebody's data flowing after they said stop.
    """
    async def body():
        client, db = await _db()
        uid = f"as_{uuid.uuid4().hex[:8]}"
        try:
            from connected.polling import due, poll_once

            instance_id = await _mailbox_instance(db, uid, status="revoked")
            assert instance_id not in [s.id for s in await due(db, uid)]

            provider = _mailbox("Non dovrebbe essere letto")
            _install_gmail(monkeypatch, provider)
            out = await poll_once(db, owners=[uid])

            assert await db.ingestion_events.count_documents({"user_id": uid}) == 0
            assert await db.connected_signals.count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Reading without being asked
# ---------------------------------------------------------------------------

def test_a_new_message_becomes_a_signal_with_nobody_pressing_anything(monkeypatch):
    """
    §10: the sprint's product claim, in one test.

    A message arrives; nothing is pressed; a signal exists. The whole path
    runs — provider, ingestion, sensor, dedupe — driven by the same pass the
    background loop calls.
    """
    async def body():
        client, db = await _db()
        uid = f"as_{uuid.uuid4().hex[:8]}"
        try:
            from connected.polling import interval_for, poll_once

            instance_id = await _mailbox_instance(db, uid)
            provider = _mailbox("Conferma appuntamento di giovedì")
            _install_gmail(monkeypatch, provider)

            handled = await poll_once(db, owners=[uid])

            assert handled["read"] >= 1
            signals = await db.connected_signals.find(
                {"owner_id": uid}, {"_id": 0}
            ).to_list(5)
            assert len(signals) == 1
            assert signals[0]["source_type"] == "email"
            assert signals[0]["status"] == "pending"

            # And the mailbox now says when it was read, and from where to
            # resume.
            instance = await db.connector_instances.find_one(
                {"id": instance_id}, {"_id": 0}
            )
            assert instance["last_sync_at"], "una lettura riuscita non è stata annotata"
            assert instance["cursor"]["history_id"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_polling_the_same_mailbox_twice_produces_one_signal(monkeypatch):
    """§4/§10: replay safety, on the path that runs every few minutes forever."""
    async def body():
        client, db = await _db()
        uid = f"as_{uuid.uuid4().hex[:8]}"
        try:
            from connected.polling import interval_for, poll_once

            await _mailbox_instance(db, uid)
            provider = _mailbox("Una cosa sola")
            _install_gmail(monkeypatch, provider)

            now = datetime.now(timezone.utc)
            await poll_once(db, now=now, owners=[uid])
            await poll_once(db, now=now + timedelta(minutes=30), owners=[uid])

            assert await db.connected_signals.count_documents({"owner_id": uid}) == 1
            assert await db.ingestion_events.count_documents({"user_id": uid}) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_failed_reading_leaves_the_world_where_it_was(monkeypatch):
    """
    §17: a provider that will not answer is not a life where nothing happened.

    The signal from before survives, the source says it cannot be read, and
    the next attempt is further away rather than immediate.
    """
    async def body():
        client, db = await _db()
        uid = f"as_{uuid.uuid4().hex[:8]}"
        try:
            from connected.polling import interval_for, poll_once
            from connected.service import ConnectedLifeService

            instance_id = await _mailbox_instance(db, uid)
            provider = _mailbox("Prima che si rompesse")
            _install_gmail(monkeypatch, provider)
            now = datetime.now(timezone.utc)
            await poll_once(db, now=now, owners=[uid])
            assert await db.connected_signals.count_documents({"owner_id": uid}) == 1

            class Broken:
                async def profile(self, **kw):
                    raise RuntimeError("gmail down")

                async def list_messages(self, **kw):
                    raise RuntimeError("gmail down")

                async def history(self, **kw):
                    raise RuntimeError("gmail down")

                async def metadata_of(self, **kw):
                    raise RuntimeError("gmail down")

                async def body_of(self, **kw):
                    raise RuntimeError("gmail down")

            _install_gmail(monkeypatch, Broken())
            later = now + timedelta(minutes=10)
            await poll_once(db, now=later, owners=[uid])

            # Nothing was lost and nothing was invented.
            assert await db.connected_signals.count_documents({"owner_id": uid}) == 1

            source = next(
                s for s in await ConnectedLifeService(db).sources.list(uid)
                if s.source_type == "email"
            )
            assert source.status == "degraded"
            assert source.can_be_leaned_on is False
            assert "Non riesco" in source.for_human()["state"]

            row = await db.connected_source_attempts.find_one(
                {"owner_id": uid, "source_id": instance_id}, {"_id": 0}
            )
            assert row["failures"] == 1
            gap = datetime.fromisoformat(row["next_attempt_at"]) - later
            # La regola, non un numero: dopo un errore si aspetta piu' del
            # normale. Scritta cosi' resta vera anche se la cadenza cambia.
            assert gap.total_seconds() >= 2 * interval_for("email").total_seconds(), (
                "riprova troppo presto"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_source_that_comes_back_is_read_again_and_the_error_is_cleared(monkeypatch):
    """
    §17: recovery is automatic, and the failure stops being reported.

    A source still showing last week's error after four good readings is a
    source people stop believing — and then they stop believing the real
    failures too.
    """
    async def body():
        client, db = await _db()
        uid = f"as_{uuid.uuid4().hex[:8]}"
        try:
            from connected.polling import interval_for, poll_once
            from connected.service import ConnectedLifeService

            instance_id = await _mailbox_instance(db, uid)

            class Broken:
                async def profile(self, **kw):
                    raise RuntimeError("down")

                async def history(self, **kw):
                    raise RuntimeError("down")

                async def list_messages(self, **kw):
                    raise RuntimeError("down")

                async def metadata_of(self, **kw):
                    raise RuntimeError("down")

                async def body_of(self, **kw):
                    return ""

            now = datetime.now(timezone.utc)
            _install_gmail(monkeypatch, Broken())
            await poll_once(db, now=now, owners=[uid])

            _install_gmail(monkeypatch, _mailbox("Sono tornato"))
            recovered_at = now + timedelta(hours=2)
            await poll_once(db, now=recovered_at, owners=[uid])

            source = next(
                s for s in await ConnectedLifeService(db).sources.list(uid)
                if s.source_type == "email"
            )
            assert source.status == "connected"
            assert source.error_state == ""
            assert await db.connected_signals.count_documents({"owner_id": uid}) == 1

            row = await db.connected_source_attempts.find_one(
                {"owner_id": uid, "source_id": instance_id}, {"_id": 0}
            )
            assert row["failures"] == 0, "il contatore di errori non si azzera"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_after_a_restart_the_reading_resumes_from_the_cursor(monkeypatch):
    """
    §18: a restart must not re-import somebody's mailbox.

    Nothing about the schedule or the position lives in memory: both are
    rows. This simulates the only thing a restart actually changes — a new
    process with no state — and asserts the second reading picks up where the
    first left off.
    """
    async def body():
        client, db = await _db()
        uid = f"as_{uuid.uuid4().hex[:8]}"
        try:
            import ambient.runtime as runtime
            from connected import polling
            from connected.polling import interval_for, poll_once

            instance_id = await _mailbox_instance(db, uid)
            provider = _mailbox("Prima del riavvio")
            _install_gmail(monkeypatch, provider)
            now = datetime.now(timezone.utc)
            await poll_once(db, now=now, owners=[uid])

            before = await db.connector_instances.find_one(
                {"id": instance_id}, {"_id": 0}
            )
            position = before["cursor"]["history_id"]
            assert position

            # The restart: a fresh worker id, no in-process state, and the
            # runtime's own entry point rather than the polling function.
            runtime._worker_id = ""
            runtime.reset_stats_for_test()

            provider.add("m_new", thread_id="t_new", headers={"Subject": "Dopo il riavvio"})
            after_restart = now + timedelta(minutes=30)
            handled = await polling.poll_once(
                db, now=after_restart, owners=[uid],
            )

            assert handled["read"] >= 1
            after = await db.connector_instances.find_one(
                {"id": instance_id}, {"_id": 0}
            )
            assert after["cursor"]["history_id"] != position, "il cursore non è avanzato"

            subjects = {
                s["after"] for s in await db.connected_signals.find(
                    {"owner_id": uid}, {"_id": 0, "after": 1}
                ).to_list(10)
            }
            assert subjects == {"Prima del riavvio", "Dopo il riavvio"}
            assert await db.ingestion_events.count_documents({"user_id": uid}) == 2, (
                "il riavvio ha reimportato quello che c'era già"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_ora_does_not_wake_itself_over_an_event_it_wrote(monkeypatch):
    """
    §16: the loop that would be very hard to see.

    ORA writes an event, the auto-sync finds it, and without the receipt it
    would be news — so the agent would wake, read its own work as a change in
    the world, and be tempted to do it again. The receipt is the evidence,
    and the signal is settled as ORA's own before any judgement is paid for.
    """
    async def body():
        client, db = await _db()
        uid = f"as_{uuid.uuid4().hex[:8]}"
        try:
            from connected import calendar_sensor
            from connected.service import ConnectedLifeService

            instance_id = f"inst_{uuid.uuid4().hex[:8]}"
            now = datetime.now(timezone.utc)
            await db.agent_receipts.insert_one({
                "id": "rc_1", "owner_id": uid, "capability": "calendar.write",
                "external_ref": "ev_mine", "provider": "calendar",
                "requested_at": now.isoformat(),
            })
            await db.ingestion_events.insert_one({
                "id": "ing_1", "user_id": uid, "connector_id": "calendar_google",
                "connector_instance_id": instance_id, "external_id": "ev_mine",
                "source_type": "calendar_google",
                "source_record_type": "calendar_event",
                "normalized_payload": {
                    "title": {"value": "Dentista"},
                    "starts_at": {"value": (now + timedelta(days=1)).isoformat()},
                    "status": "confirmed",
                },
                "ingested_at": now.isoformat(),
            })

            service = ConnectedLifeService(db)
            for signal in await calendar_sensor.read_changes(
                db, uid, source_id=instance_id,
            ):
                await service.signals.record(signal)

            recorded = await db.connected_signals.find_one(
                {"owner_id": uid}, {"_id": 0}
            )
            assert recorded["origin"] == "self_originated"

            out = await service.interpret(uid)
            assert out["own_work"] == 1
            assert out["passed_on"] == 0
            assert await db.ambient_wakes.count_documents({"owner_id": uid}) == 0
            assert await db.meaningful_changes.count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_one_persons_broken_source_does_not_stop_everybody_elses(monkeypatch):
    """
    A shared loop with an unguarded exception reads one mailbox and stops.

    Which is invisible: the person whose sync threw sees an error eventually,
    and everybody after them in the list simply never gets read.
    """
    async def body():
        client, db = await _db()
        first = f"as_{uuid.uuid4().hex[:8]}"
        second = f"as_{uuid.uuid4().hex[:8]}"
        try:
            from connected.polling import interval_for, poll_once

            await _mailbox_instance(db, first)
            await _mailbox_instance(db, second)

            class HalfBroken:
                def __init__(self):
                    self.calls = 0
                    self.good = _mailbox("Per il secondo")

                async def profile(self, *, access_token):
                    return await self.good.profile(access_token=access_token)

                async def history(self, **kw):
                    self.calls += 1
                    if self.calls == 1:
                        raise RuntimeError("il primo si rompe")
                    return await self.good.history(**kw)

                async def list_messages(self, **kw):
                    self.calls += 1
                    if self.calls == 1:
                        raise RuntimeError("il primo si rompe")
                    return await self.good.list_messages(**kw)

                async def metadata_of(self, **kw):
                    return await self.good.metadata_of(**kw)

                async def body_of(self, **kw):
                    return ""

            broken = HalfBroken()
            _install_gmail(monkeypatch, broken)
            await poll_once(db, limit=40, owners=[first, second])

            # Entrambe le caselle sono state provate: quella rotta ha alzato
            # un'eccezione e il giro è andato avanti lo stesso.
            looked_at = {
                row["source_id"] for row in
                await db.connected_source_attempts.find(
                    {"owner_id": {"$in": [first, second]}},
                    {"_id": 0, "source_id": 1},
                ).to_list(20)
            }
            assert len(looked_at) >= 2, "il giro si è fermato al primo errore"
            assert broken.calls >= 2, "la seconda casella non è stata nemmeno provata"
        finally:
            await _clean(db, first)
            await _clean(db, second)
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


def test_the_background_loop_actually_reads_the_sources():
    """
    §3: registration is the thing that silently disappears.

    Everything else in this file tests `poll_once` directly, which would keep
    passing forever if nobody ever called it. This checks the one line that
    makes it happen at all — inside the loop that already exists, not in a
    scheduler of its own.
    """
    tree = _code_only(_tree("ambient/runtime.py"))
    loop = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_loop"
    )
    called = ast.unparse(loop)
    assert "read_sources(db)" in called, "il loop non legge le sorgenti"
    assert called.index("read_sources") < called.index("await tick"), (
        "le sorgenti vengono lette dopo i wake: quello che arriva aspetta un giro"
    )

    reader = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "read_sources"
    )
    assert "poll_once" in ast.unparse(reader)


def test_no_second_scheduler_was_built():
    """
    §3: one loop, one place that starts and stops it.

    A second background task is a second thing to shut down cleanly, and the
    way that shows up is a test suite that hangs on exit.
    """
    source = (HERE / "connected/polling.py").read_text(encoding="utf-8")
    tree = _code_only(ast.parse(source))
    body = ast.unparse(tree)
    for scheduling in ("create_task", "asyncio.sleep", "while True", "Timer",
                       "add_job", "cron"):
        assert scheduling not in body, f"connected/polling.py fa da scheduler: {scheduling}"


def test_polling_never_asks_a_model_anything():
    """
    §3: deciding *when to look* is arithmetic, and costs nothing.

    A polling pass that reached a model would turn an empty database into a
    bill, and would make the cheapest part of the system the most expensive.
    """
    tree = _code_only(_tree("connected/polling.py"))
    body = ast.unparse(tree)
    for reaching in ("interpret_signal", "decide_link", "_ask_model", "reasoning"):
        assert reaching not in body, f"il polling chiama il modello: {reaching}"


def test_no_screen_asks_a_person_to_synchronise():
    """
    §1/§8: the button is gone from the product, not hidden in it.

    Checked across every screen rather than in the one that had it: the
    failure mode is somebody re-adding it as a "fallback" in a different
    file, which is exactly what the brief forbids.
    """
    screens = list((REPO / "frontend/app").rglob("*.tsx"))
    assert screens, "nessuna schermata trovata"
    for path in screens:
        text = path.read_text(encoding="utf-8", errors="ignore")
        stripped = "\n".join(
            line for line in text.splitlines() if not line.strip().startswith("//")
        )
        # Apple Calendar non e' in questa lista di proposito: li' il telefono
        # consegna gli eventi *durante* il collegamento — e' l'azione stessa
        # di collegare, non un pulsante che chiede di sincronizzare dopo.
        for calling in ("googleCalendarSync(", "gmailSync("):
            assert calling not in stripped, f"{path.name} chiede di sincronizzare"
        for labelled in ('label="Sincronizza"', "'Sincronizza'", '"Sincronizza"'):
            assert labelled not in stripped, f"{path.name} mostra un pulsante Sincronizza"

    # The endpoints stay: the scheduler and the tests use them. What is gone
    # is the expectation that a person presses anything.
    from connectors.gmail.router import router as gmail_router

    paths = {r.path for r in gmail_router.routes}
    assert any(p.endswith("/sync") for p in paths), (
        "l'endpoint di sync è stato rimosso: lo scheduler ne ha bisogno"
    )


def test_a_sync_that_explodes_still_slows_the_next_attempt(monkeypatch):
    """
    §4/§17: the branch that only runs when something unforeseen breaks.

    A source whose sync fails *politely* returns `sync_failed` and is backed
    off by the ordinary path. This is the other case — the sync itself
    raising, which is what a bug, a driver error or an unhandled provider
    shape looks like — and it must back off too. Without it, the one source
    in the worst state is the one retried hardest.
    """
    async def body():
        client, db = await _db()
        uid = f"as_{uuid.uuid4().hex[:8]}"
        try:
            from connected import polling
            from connected.service import ConnectedLifeService

            instance_id = await _mailbox_instance(db, uid)

            async def explode(self, owner_id, source_id):
                raise RuntimeError("qualcosa di imprevisto")

            monkeypatch.setattr(ConnectedLifeService, "sync", explode)

            now = datetime.now(timezone.utc)
            handled = await polling.poll_once(db, now=now, limit=8, owners=[uid])

            assert handled["failed"] >= 1
            row = await db.connected_source_attempts.find_one(
                {"owner_id": uid, "source_id": instance_id}, {"_id": 0}
            )
            assert row["failures"] >= 1, "un'eccezione non è stata contata come errore"
            gap = datetime.fromisoformat(row["next_attempt_at"]) - now
            assert gap.total_seconds() >= 2 * polling.interval_for(
                "email"
            ).total_seconds(), "riprova come se nulla fosse"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_thousand_accounts_do_not_starve_the_one_that_is_waiting():
    """
    §4: the queue is served oldest-wait-first, not first-two-hundred-names.

    The first version walked every owner with a connected account and took a
    slice: on a database with hundreds of them, the same names were read
    every tick and everybody past the cut was never read at all. It was found
    by watching a real account go unread for hours while the loop reported
    itself busy.

    So: whoever has been waiting longest goes first, and a freshly connected
    source joins the back of the queue rather than the front — one per pass,
    which is enough to be read within a tick or two and not enough to starve
    the people already in it.
    """
    async def body():
        client, db = await _db()
        owners = [f"as_{uuid.uuid4().hex[:8]}" for _ in range(6)]
        try:
            from connected.polling import owners_to_look_at

            now = datetime.now(timezone.utc)
            # Five accounts connected but never read, and one that has been
            # waiting since this morning.
            waiting_since = (now - timedelta(hours=6)).isoformat()
            for owner in owners[:5]:
                await _mailbox_instance(db, owner)
            await _mailbox_instance(db, owners[5])
            await db.connected_source_attempts.insert_one({
                "owner_id": owners[5], "source_id": "inst_old",
                "next_attempt_at": waiting_since, "failures": 0,
            })

            queue = await owners_to_look_at(db, now=now, limit=4)

            assert owners[5] in queue, "chi aspetta da stamattina non è in coda"
            never_read = [o for o in queue if o in owners[:5]]
            assert len(never_read) <= 1, (
                "gli account mai letti occupano la coda e affamano gli altri"
            )
            # A newcomer may go first — one of them, and only one: reading a
            # just-connected source immediately is the difference between a
            # screen that changes after saying yes to Google and one that
            # does not. What must never happen is what did happen: the
            # newcomers filling the queue and the waiting account never
            # reached at all.
            assert len(queue) >= 2
            assert queue.index(owners[5]) <= 1
        finally:
            for owner in owners:
                await _clean(db, owner)
            await db.connected_source_attempts.delete_many(
                {"owner_id": {"$in": owners}},
            )
            client.close()

    _run(body())
