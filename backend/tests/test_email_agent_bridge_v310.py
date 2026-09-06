"""
V3.10 Sprint 3 — the mailbox knocks on doors that already exist.

    NO NEW AGENT. NO NEW DELIVERY ENGINE. NO GOAL CREATED BY AN `IF`.

Everything a meaningful message produces was built in an earlier phase: the
change log is V3.7's, the wake is V3.8's, the goal decision and the authority
ceiling are V3.9's. This suite is about the joins — that they are used, that
they are used once, and that nothing new was quietly built beside them.

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
REPO = HERE.parent


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, uid):
    for coll in (
        "ingestion_events", "connector_instances", "connected_signals",
        "connected_source_attempts", "connected_situation_links",
        "meaningful_changes", "ambient_wakes", "documents", "memories",
        "life_objects", "agent_receipts",
    ):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


async def _mail_signal(db, uid, *, subject, message_id, thread_id="t1"):
    from connected.models import ConnectedSignal, FieldChange
    from connected.signals import SignalService

    signal = ConnectedSignal(
        owner_id=uid, source_type="email", source_id="inst_mail",
        signal_type="email.message.added", source_object_ref=message_id,
        payload_summary=f"È arrivato un messaggio: «{subject}».",
        after=subject, effective_at=datetime.now(timezone.utc).isoformat(),
        changed_fields=[FieldChange(field="subject", after=subject)],
        provenance={"thread_ref": thread_id},
    )
    await SignalService(db).record(signal)
    return signal


class Recorded:
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


def _meaning(text="Qualcosa è cambiato."):
    return {"outcome": "worth_knowing", "what_it_means": text,
            "relates_to": "una pratica", "reasoning": "reg.",
            "needs_content": False}


def _no_link():
    return {"relationship": "new_situation", "target_ref": "",
            "confidence": 0.5, "why": "Nuova.", "relied_on": []}


# ---------------------------------------------------------------------------
# One knock, not several
# ---------------------------------------------------------------------------

def test_two_meaningful_messages_in_one_pass_do_not_book_two_thinks(monkeypatch):
    """
    §45: the wake layer coalesces, and this is what depends on it.

    A person who gets three real messages in ten minutes should be thought
    about once. Booking one think per message is how a sensor turns into a
    notification stream wearing an agent's clothes.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            service = _service(db)
            await _mail_signal(db, uid, subject="Prima cosa", message_id="m1",
                               thread_id="t1")
            await _mail_signal(db, uid, subject="Seconda cosa", message_id="m2",
                               thread_id="t2")

            # Two judgements and no link judgements: this life holds nothing
            # for these messages to be about, so nothing is asked about
            # linking — which is itself the correct behaviour and is why the
            # answers below are only two.
            _install(monkeypatch, Recorded([
                _meaning("La prima."), _meaning("La seconda."),
            ]))
            out = await service.interpret(uid)

            assert out["passed_on"] == 2
            assert out["linked"] == 0
            assert await db.ambient_wakes.count_documents({"owner_id": uid}) == 1, (
                "due messaggi hanno prenotato due risvegli"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_same_message_replayed_makes_no_second_observation(monkeypatch):
    """
    §10/§40: recovery must not double what a life is told.

    After an expired cursor the connector resyncs, and the same message comes
    round again. The signal layer deduplicates it before any of this — so the
    replay produces no second change, no second wake and no second belief.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected import email_sensor

            service = _service(db)
            instance_id = "inst_mail"
            now = datetime.now(timezone.utc).isoformat()
            for _ in range(2):
                await db.ingestion_events.insert_one({
                    "id": f"ing_{uuid.uuid4().hex[:10]}", "user_id": uid,
                    "connector_id": "mail_gmail",
                    "connector_instance_id": instance_id, "external_id": "m1",
                    "source_type": "mail_gmail",
                    "source_record_type": "email_message",
                    "normalized_payload": {
                        "message_ref": "m1", "thread_ref": "t1",
                        "subject": "Convocazione", "sender_relationship": "unknown",
                        "recipient_count": 1, "received_at": now,
                        "attachments_present": False, "attachment_count": 0,
                        "provider_categories": [], "in_inbox": True,
                        "content_available": True,
                    },
                    "ingested_at": now,
                })

            kept = 0
            for signal in await email_sensor.read_changes(
                db, uid, source_id=instance_id,
            ):
                stored, _why = await service.signals.record(signal)
                kept += 1 if stored is not None else 0

            assert kept == 1, "una risincronizzazione ha duplicato un messaggio"

            _install(monkeypatch, Recorded([_meaning(), _no_link()]))
            out = await service.interpret(uid)

            assert out["passed_on"] == 1
            assert await db.meaningful_changes.count_documents({"owner_id": uid}) == 1
            assert await db.ambient_wakes.count_documents({"owner_id": uid}) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_belief_from_a_message_is_proposed_and_never_written(monkeypatch):
    """
    §16: Life Observation → governance. No direct memory write, from any source.

    The provenance is the part worth checking: a belief learned this way
    carries the signal it came from, so a wrong one is correctable rather
    than mysterious.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            service = _service(db)
            signal = await _mail_signal(db, uid, subject="Nuovo indirizzo dello studio",
                                        message_id="m1")

            _install(monkeypatch, Recorded([
                {"outcome": "changes_something_known",
                 "what_it_means": "Lo studio ha cambiato indirizzo.",
                 "relates_to": "il dentista", "reasoning": "reg.",
                 "needs_content": False},
                _no_link(),
            ]))
            await service.interpret(uid)

            memories = await db.memories.find({"user_id": uid}, {"_id": 0}).to_list(5)
            for memory in memories:
                provenance = str(memory.get("provenance") or "")
                assert f"connected_signal:{signal.id}" in provenance, (
                    "una convinzione senza traccia di dove viene"
                )
                assert memory.get("status") != "known" or memory.get("governance_key"), (
                    "scritta senza passare dalla governance"
                )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_judgement_that_never_arrives_leaves_the_world_untouched(monkeypatch):
    """
    §40: silence is a missing answer, not an answer of "nothing".

    Every provider is down. The pass must end quietly with the signals still
    pending — not crash, and not settle them as noise, which would silently
    discard whatever they were about.

    This is here because it did crash: the re-ask added in Sprint 2 read the
    answer before anything had checked that there was one.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            service = _service(db)
            await _mail_signal(db, uid, subject="Qualcosa", message_id="m1")
            _install(monkeypatch, Recorded([]))

            out = await service.interpret(uid)

            assert out["ok"] is True
            assert out["passed_on"] == 0 and out["noise"] == 0
            pending = await service.signals.pending(uid)
            assert len(pending) == 1, "un segnale è stato archiviato senza giudizio"
            assert await db.ambient_wakes.count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Nothing new was built
# ---------------------------------------------------------------------------

def test_there_is_no_mail_agent_anywhere():
    """
    §44: the thing this sprint most easily becomes.

    An InboxAgent would be reasonable-looking, self-contained, and the end of
    one ORA: a second loop with its own idea of what matters, its own way of
    reaching somebody, and no share in what the rest of the system knows.
    """
    offenders = []
    for path in HERE.rglob("*.py"):
        if any(part in ("__pycache__", ".venv", "tests") for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name in ("class MailAgent", "class InboxAgent",
                     "class CommunicationAgent", "class EmailAgent"):
            if name in text:
                offenders.append(f"{path.name}: {name}")
    assert offenders == [], offenders


def test_the_only_delivery_engine_is_still_v38():
    """§45: email relevance never becomes a push by itself."""
    for name in ("connected/email_sensor.py", "connected/situations.py",
                 "connected/service.py"):
        tree = ast.parse((HERE / name).read_text(encoding="utf-8"))
        imported = {
            (n.module or "") for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
        }
        for forbidden in ("delivery.service", "delivery.push", "push"):
            assert not any(m == forbidden for m in imported), (
                f"{name} parla direttamente con la consegna"
            )


def test_the_mailbox_uses_the_same_source_machinery_as_everything_else():
    """
    §4: one source-of-truth about connections, not a second one for mail.

    Checked by shape: the registry builds a mailbox through the same
    `ConnectedSource` every other instrument uses, so a mailbox cannot grow
    its own idea of what "connected" means.
    """
    tree = ast.parse((HERE / "connected/sources.py").read_text(encoding="utf-8"))
    mailboxes = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_mailboxes"
    )
    built = [
        getattr(n.func, "id", "") for n in ast.walk(mailboxes)
        if isinstance(n, ast.Call)
    ]
    assert "ConnectedSource" in built
    # And it never invents a status word of its own.
    assert "_INSTANCE_STATUS" in ast.unparse(mailboxes)


def test_the_email_capability_catalogue_offers_no_way_to_send():
    """
    §3/§47: mail.send exists in the catalogue, wired to nothing, and stays so.

    V3.9 declared it and made it permanently non-autonomous. Sprint 3 does
    not wire it, and this asserts both halves: the only wired write in the
    system is still the calendar's, and mail.send is still refused autonomy
    by name.
    """
    from agent.authority import _NEVER_AUTONOMOUS
    from agent.effects import wired_capabilities
    from agent.capabilities import capability_status

    assert wired_capabilities() == ["calendar.write"]
    assert "mail.send" in _NEVER_AUTONOMOUS
    assert capability_status("mail.send") == "unavailable"
