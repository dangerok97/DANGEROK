"""
V3.10 — una sorgente sana non aspetta dietro a cinquecento rotte.

    UNA CODA CHE SERVE PRIMA CHI NON SI PUO' SERVIRE NON E' UNA CODA.

Il gate reale aveva mostrato una casella e un calendario veri che arrivavano
in fondo a una coda condivisa con settanta righe permanentemente scadute. La
traccia ha poi assolto la coda in quel caso particolare — era vuota — ma la
proprieta' resta quella che serve garantire, e va garantita dove si puo'
misurare senza dipendere da com'e' il database quel giorno: qui.

La prova costruisce il caso peggiore realistico — piu' di cinquecento
sorgenti esigibili, un centinaio scollegate o degradate, e le due sane in
fondo — e chiede una cosa sola: che le sane vengano lette comunque, entro il
tempo promesso.
"""
from __future__ import annotations

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

HEALTHY_CALENDAR = "sano_calendario"
HEALTHY_MAIL = "sano_posta"


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


class _Crowd:
    """
    Una folla di sorgenti, con dentro le due che contano.

    Sostituisce l'elenco delle sorgenti di una persona. Le rotte sono rotte
    davvero: `is_readable` falso, come una connessione revocata.
    """

    def __init__(self, *, broken: int, degraded: int):
        from connected.models import ConnectedSource

        self.made = []
        for n in range(broken):
            self.made.append(ConnectedSource(
                id=f"rotta_{n}", owner_id="", source_type="calendar",
                connector_id="calendar_google", status="disconnected",
            ))
        for n in range(degraded):
            self.made.append(ConnectedSource(
                id=f"degradata_{n}", owner_id="", source_type="calendar",
                connector_id="calendar_google", status="degraded",
            ))
        # Le due sane, in fondo a tutto.
        self.made.append(ConnectedSource(
            id=HEALTHY_CALENDAR, owner_id="", source_type="calendar",
            connector_id="calendar_google", status="connected",
        ))
        self.made.append(ConnectedSource(
            id=HEALTHY_MAIL, owner_id="", source_type="email",
            connector_id="mail_gmail", status="connected",
        ))


async def _fill_queue(db, owners, *, overdue_minutes: int):
    """La coda com'e' dopo giorni di righe mai servite."""
    from connected.sources import ATTEMPTS

    long_ago = (
        datetime.now(timezone.utc) - timedelta(minutes=overdue_minutes)
    ).isoformat()
    rows = []
    for owner_id, sources in owners.items():
        for source in sources:
            rows.append({
                "owner_id": owner_id, "source_id": source.id,
                "next_attempt_at": long_ago, "failures": 0,
            })
    await db[ATTEMPTS].insert_many(rows)
    return len(rows)


def _install(monkeypatch, owners):
    """Ogni persona vede le proprie sorgenti; nessuna rete, nessun provider."""
    from connected.service import ConnectedLifeService
    from connected.sources import SourceRegistry

    async def list_for(self, owner_id):
        return owners.get(owner_id, [])

    monkeypatch.setattr(SourceRegistry, "list", list_for)

    read = []

    async def sync(self, owner_id, source_id):
        read.append((owner_id, source_id))
        if source_id.startswith("degradata_"):
            # Un 401: il provider risponde male, e la sorgente lo dice.
            return {"ok": False, "reason": "sync_failed", "state": "degraded"}
        return {"ok": True, "seen": 0, "recorded": 0, "deduped": 0}

    monkeypatch.setattr(ConnectedLifeService, "sync", sync)
    return read


def _crowd(*, people: int, broken_each: int, degraded_each: int):
    """Tante persone, ciascuna con le sue sorgenti. Le sane stanno da una sola."""
    owners = {}
    for n in range(people):
        crowd = _Crowd(broken=broken_each, degraded=degraded_each)
        owners[f"folla_{n:03d}"] = crowd.made[:-2]
    ours = _Crowd(broken=broken_each, degraded=degraded_each)
    owners["chi_conta"] = ours.made
    return owners


# ---------------------------------------------------------------------------

def test_a_healthy_calendar_is_read_within_a_minute_behind_five_hundred_stale(
    monkeypatch,
):
    """
    §2/4: cinquecento righe scadute davanti, e le sane vengono servite lo stesso.

    Il tempo qui e' quello del runtime: si contano i giri, e ogni giro vale
    `TICK_SECONDS`. La domanda e' quanti giri servono perche' il calendario
    sano venga letto, e la risposta deve stare dentro il cancello duro.
    """
    async def body():
        client, db = await _db()
        owners = _crowd(people=100, broken_each=4, degraded_each=1)
        try:
            from ambient.runtime import TICK_SECONDS
            from connected.polling import poll_once
            from connected.sources import ATTEMPTS

            read = _install(monkeypatch, owners)
            total = await _fill_queue(db, owners, overdue_minutes=90)
            assert total > 500, f"la folla e' solo {total}"

            # I giri, uno dopo l'altro, come li farebbe il loop.
            now = datetime.now(timezone.utc)
            ticks = 0
            while ticks < 60:
                ticks += 1
                await poll_once(db, now=now + timedelta(seconds=TICK_SECONDS * ticks))
                if any(s == HEALTHY_CALENDAR for _, s in read):
                    break

            waited = ticks * TICK_SECONDS
            assert any(s == HEALTHY_CALENDAR for _, s in read), (
                f"il calendario sano non e' stato letto in {waited:.0f}s"
            )
            print(
                f"  calendario sano letto dopo {ticks} giri = {waited:.0f}s "
                f"dietro {total} righe scadute"
            )
            assert waited <= 60, (
                f"il calendario sano ha aspettato {waited:.0f}s dietro {total} righe"
            )
        finally:
            for owner_id in owners:
                await db[ATTEMPTS].delete_many({"owner_id": owner_id})
            client.close()

    _run(body())


def test_a_healthy_mailbox_is_read_within_two_minutes_behind_the_same_crowd(
    monkeypatch,
):
    """§3/4: e la posta entro i suoi due minuti."""
    async def body():
        client, db = await _db()
        owners = _crowd(people=100, broken_each=4, degraded_each=1)
        try:
            from ambient.runtime import TICK_SECONDS
            from connected.polling import poll_once
            from connected.sources import ATTEMPTS

            read = _install(monkeypatch, owners)
            await _fill_queue(db, owners, overdue_minutes=90)

            now = datetime.now(timezone.utc)
            ticks = 0
            while ticks < 60:
                ticks += 1
                await poll_once(db, now=now + timedelta(seconds=TICK_SECONDS * ticks))
                if any(s == HEALTHY_MAIL for _, s in read):
                    break

            waited = ticks * TICK_SECONDS
            assert any(s == HEALTHY_MAIL for _, s in read), (
                f"la casella sana non e' stata letta in {waited:.0f}s"
            )
            assert waited <= 120, f"la casella sana ha aspettato {waited:.0f}s"
        finally:
            for owner_id in owners:
                await db[ATTEMPTS].delete_many({"owner_id": owner_id})
            client.close()

    _run(body())


def test_unreadable_sources_leave_the_head_of_the_queue(monkeypatch):
    """
    §2: le righe che non puntano a niente vengono spostate avanti, non servite.

    E lo spostamento non consuma il tempo del giro: se lo consumasse, con
    qualche centinaio di righe morte in testa il budget finirebbe prima di
    arrivare a chi si poteva leggere davvero — che e' la fame da evitare.
    """
    async def body():
        client, db = await _db()
        owners = _crowd(people=40, broken_each=6, degraded_each=0)
        try:
            from connected.polling import poll_once
            from connected.sources import ATTEMPTS

            _install(monkeypatch, owners)
            await _fill_queue(db, owners, overdue_minutes=120)

            now = datetime.now(timezone.utc)
            out = await poll_once(db, now=now)
            assert out["parked"] > 0, "nessuna riga morta e' stata spostata"

            still = await db[ATTEMPTS].count_documents({
                "owner_id": {"$in": list(owners)},
                "source_id": {"$regex": "^rotta_"},
                "next_attempt_at": {"$lte": now.isoformat()},
            })
            moved = await db[ATTEMPTS].count_documents({
                "owner_id": {"$in": list(owners)},
                "source_id": {"$regex": "^rotta_"},
                "next_attempt_at": {"$gt": now.isoformat()},
            })
            assert moved > 0
            assert moved >= still, (
                "piu' righe morte sono rimaste in testa di quante ne siano uscite"
            )
        finally:
            for owner_id in owners:
                await db[ATTEMPTS].delete_many({"owner_id": owner_id})
            client.close()

    _run(body())


def test_a_source_that_keeps_failing_is_asked_less_and_less(monkeypatch):
    """§2: 401 e degradate escono in fretta dal percorso veloce."""
    async def body():
        client, db = await _db()
        owners = _crowd(people=5, broken_each=0, degraded_each=2)
        try:
            from connected.polling import interval_for, poll_once
            from connected.sources import ATTEMPTS

            _install(monkeypatch, owners)
            await _fill_queue(db, owners, overdue_minutes=30)

            now = datetime.now(timezone.utc)
            for n in range(4):
                await poll_once(db, now=now + timedelta(seconds=30 * n))

            row = await db[ATTEMPTS].find_one(
                {"owner_id": "chi_conta", "source_id": "degradata_0"}, {"_id": 0})
            assert row["failures"] >= 1, "un 401 non e' stato contato come errore"
            gap = (
                datetime.fromisoformat(row["next_attempt_at"]) - now
            ).total_seconds()
            assert gap > interval_for("calendar").total_seconds(), (
                "una sorgente che fallisce viene richiesta come se niente fosse"
            )
        finally:
            for owner_id in owners:
                await db[ATTEMPTS].delete_many({"owner_id": owner_id})
            client.close()

    _run(body())


def test_a_restart_keeps_the_schedule_and_claims_nothing_twice(monkeypatch):
    """
    §4: il riavvio non riparte da capo, e nessuna sorgente viene presa due volte.

    La programmazione vive nel database e non nella memoria di un processo:
    e' quello che rende sicuro avere piu' di un worker, ed e' anche la
    ragione per cui questa prova ricostruisce tutto da zero fra un giro e
    l'altro.
    """
    async def body():
        client, db = await _db()
        owners = _crowd(people=20, broken_each=2, degraded_each=0)
        try:
            from connected.polling import poll_once
            from connected.sources import ATTEMPTS

            read = _install(monkeypatch, owners)
            await _fill_queue(db, owners, overdue_minutes=60)

            now = datetime.now(timezone.utc)
            await poll_once(db, now=now)
            after_first = list(read)
            schedule = {
                (r["owner_id"], r["source_id"]): r["next_attempt_at"]
                for r in await db[ATTEMPTS].find(
                    {"owner_id": {"$in": list(owners)}}, {"_id": 0},
                ).to_list(2000)
            }

            # «Riavvio»: stesso database, niente in memoria.
            await poll_once(db, now=now)
            twice = [x for x in read[len(after_first):] if x in after_first]
            assert not twice, f"prese due volte nello stesso istante: {twice[:3]}"

            kept = {
                (r["owner_id"], r["source_id"]): r["next_attempt_at"]
                for r in await db[ATTEMPTS].find(
                    {"owner_id": {"$in": list(owners)}}, {"_id": 0},
                ).to_list(2000)
            }
            for key, when in schedule.items():
                assert key in kept, "il riavvio ha perso una riga di coda"
        finally:
            for owner_id in owners:
                await db[ATTEMPTS].delete_many({"owner_id": owner_id})
            client.close()

    _run(body())


def test_a_hiccup_reading_the_sources_does_not_park_a_healthy_one(monkeypatch):
    """
    §2: NON SO NON E' NIENTE DA LEGGERE.

    Se chiedere quali sorgenti ha una persona fallisce — un singhiozzo del
    database, una connessione caduta — non si sa niente di lei. Trattarlo
    come «qui non c'e' niente» spostava avanti di mezz'ora un calendario
    perfettamente sano: successo sull'account vero, che per mezz'ora non e'
    piu' stato letto.
    """
    async def body():
        client, db = await _db()
        owners = _crowd(people=2, broken_each=1, degraded_each=0)
        try:
            from connected import polling
            from connected.polling import poll_once
            from connected.sources import ATTEMPTS

            _install(monkeypatch, owners)
            await _fill_queue(db, owners, overdue_minutes=10)

            async def hiccup(db_, owner_id, *, now=None):
                raise RuntimeError("il database ha singhiozzato")

            monkeypatch.setattr(polling, "due", hiccup)

            now = datetime.now(timezone.utc)
            await poll_once(db, now=now)
            # Si guardano le nostre righe, non il contatore globale: sullo
            # stesso database ci sono le righe lasciate da altre prove, e un
            # contatore che le somma non direbbe niente di questa.
            parked_ours = await db[ATTEMPTS].count_documents({
                "owner_id": {"$in": list(owners)},
                "health": {"$nin": ["", None]},
            })
            assert parked_ours == 0, (
                "un errore nel leggere le sorgenti e' stato scambiato "
                "per «non c'e' niente da leggere»"
            )
            row = await db[ATTEMPTS].find_one(
                {"owner_id": "chi_conta", "source_id": HEALTHY_CALENDAR},
                {"_id": 0},
            )
            assert str(row["next_attempt_at"]) <= now.isoformat(), (
                "il calendario sano e' stato spostato avanti per un singhiozzo"
            )
            assert not row.get("health")
        finally:
            for owner_id in owners:
                await db[ATTEMPTS].delete_many({"owner_id": owner_id})
            client.close()

    _run(body())
