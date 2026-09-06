"""
V3.10 Sprint 3 — several sources, one life.

    MULTIPLE SOURCES CAN REFER TO THE SAME THING IN A PERSON'S LIFE.
    NO LINK IS EVER MADE BY A STRING MATCH.
    CODE DOES NOT CHOOSE THE TRUE SOURCE.

The core of the sprint, and the part with the most ways to be quietly wrong.
Three of them have their own tests here, because each passes casual review:

  - linking by resemblance, which works on the examples it was written for
    and is wrong about everybody else;
  - resolving a disagreement in code, which produces a confident answer that
    nobody can examine and that is permanent;
  - letting a link become an action, which is where "the email says it moved"
    turns into a calendar being rewritten by a stranger.

Every judgement here is recorded. No live model calls.
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
        "connected_situation_links", "meaningful_changes", "ambient_wakes",
        "documents", "memories", "life_objects", "agent_receipts",
        "calendar_event_drafts",
    ):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


def _when(days=2, hour=16):
    moment = datetime.now(timezone.utc) + timedelta(days=days)
    return moment.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


async def _instance(db, uid, connector="mail_gmail"):
    instance_id = f"inst_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    await db.connector_instances.insert_one({
        "id": instance_id, "user_id": uid, "connector_id": connector,
        "status": "connected", "secret_reference": "vault_ref",
        "metadata": {"account_email": ACCOUNT}, "cursor": {},
        "created_at": now, "updated_at": now, "last_sync_at": now,
    })
    return instance_id


async def _appointment(db, uid, *, ref="ev_dentista", what="Dentista",
                       when=None, source_id="inst_cal"):
    """
    An appointment in this person's calendar, written the way a sync writes it.

        UN APPUNTAMENTO E' UNA RIGA DI CALENDARIO, NON UN SEGNALE.

    Questo scriveva solo un segnale — il registro di cosa e' cambiato — e per
    un po' e' bastato, perche' i candidati venivano letti da li'. Adesso
    vengono letti dal calendario, che e' dove un appuntamento sta davvero, e
    la riga la costruiscono il normalizzatore e il repository veri: la forma
    e' quella che scrive la produzione, non quella che spera un lettore.

    Il segnale resta, perche' un appuntamento appena messo in calendario *ha*
    prodotto un segnale, e alcune prove qui sotto parlano proprio di quello.
    """
    from datetime import datetime as _dt

    from connected.models import ConnectedSignal
    from connected.signals import SignalService
    from ingestion.event_model import IngestionEventRepository
    from ingestion.normalizer import GoogleCalendarNormalizer

    starts = when or _when(2, 10)
    moment = _dt.fromisoformat(str(starts).replace("Z", "+00:00"))
    normalized = GoogleCalendarNormalizer(
        connector_id="calendar_google", connector_instance_id=source_id,
    ).normalize(
        raw={
            "id": ref, "status": "confirmed", "summary": what,
            "start": {"dateTime": moment.isoformat()},
            "end": {"dateTime": (moment + timedelta(minutes=60)).isoformat()},
            "organizer": {"email": ACCOUNT}, "attendees": [],
            "etag": uuid.uuid4().hex[:8], "updated": moment.isoformat(),
        },
        calendar_id=ACCOUNT, calendar_name=ACCOUNT,
    )
    await IngestionEventRepository(db).insert(
        user_id=uid, connector_id="calendar_google",
        connector_instance_id=source_id, external_id=ref,
        external_version=normalized.source_hash,
        source_type="calendar_google", source_record_type="calendar_event",
        raw_reference={"calendar_id": ACCOUNT},
        normalized_payload=normalized.to_dict(),
        payload_hash=normalized.source_hash,
        source_created_at=None, source_updated_at=moment.isoformat(),
        provenance={"connector_id": "calendar_google"},
        sensitivity="personal", status="processed",
    )

    signal = ConnectedSignal(
        owner_id=uid, source_type="calendar", source_id=source_id,
        signal_type="calendar.event.created", source_object_ref=ref,
        payload_summary=f"«{what}» è stato messo in calendario.",
        after=what, effective_at=starts, relationship="own",
    )
    service = SignalService(db)
    await service.record(signal)
    # Already judged, on some earlier pass. What makes it a *candidate* is
    # that it was observed, not that it is waiting — and leaving it pending
    # would make this fixture quietly test two interpretations at once.
    await service.settle(uid, signal.id, outcome="worth_knowing")
    return signal


async def _mail_signal(db, uid, instance_id, *, subject, message_id="m1",
                       thread_id="t1", received=None):
    from connected.models import ConnectedSignal, FieldChange
    from connected.signals import SignalService

    signal = ConnectedSignal(
        owner_id=uid, source_type="email", source_id=instance_id,
        signal_type="email.message.added", source_object_ref=message_id,
        payload_summary=f"È arrivato un messaggio: «{subject}».",
        after=subject, effective_at=received or datetime.now(timezone.utc).isoformat(),
        changed_fields=[
            FieldChange(field="subject", after=subject),
            FieldChange(field="body", content_withheld=True),
        ],
        relationship="invited",
        provenance={"thread_ref": thread_id, "instance_id": instance_id},
    )
    await SignalService(db).record(signal)
    return signal


async def _document(db, uid, doc_id="doc_tac", title="Referto TAC"):
    now = datetime.now(timezone.utc).isoformat()
    await db.documents.replace_one(
        {"id": doc_id, "user_id": uid},
        {"id": doc_id, "user_id": uid, "title": title, "tags": ["salute"],
         "document_type": "referto", "deleted": False,
         "created_at": now, "updated_at": now},
        upsert=True,
    )


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


def signal_arrival(link) -> str:
    """When the reading happened, which is never what the reading says."""
    return str(link["disagreements"][0]["this_source_observed_at"])


# ---------------------------------------------------------------------------
# What code hands over
# ---------------------------------------------------------------------------

def test_candidates_are_facts_with_no_score_and_no_ranking():
    """
    §12/§55: code retrieves, the model decides.

    A candidate carries what it is, when, where it came from and how directly
    it knows — and no number saying how likely it is. The moment a score
    appears here, the linking decision has quietly moved into code, and the
    model is only ratifying arithmetic somebody wrote once.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected import situations

            instance_id = await _instance(db, uid)
            await _appointment(db, uid)
            await _document(db, uid)
            signal = await _mail_signal(db, uid, instance_id,
                                        subject="Conferma appuntamento")

            candidates = await situations.candidates_for(db, uid, signal)

            kinds = {c["kind"] for c in candidates}
            assert "appointment" in kinds and "document" in kinds
            for candidate in candidates:
                assert {"kind", "ref", "what", "when", "from_source"} <= set(candidate)
                for scoring in ("score", "confidence", "similarity", "rank",
                                "weight", "match"):
                    assert scoring not in candidate, (
                        f"il codice ha già deciso: {scoring}"
                    )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_appointment_far_outside_the_window_is_not_offered():
    """
    §12: the only filters are time and count, and both are retrieval bounds.

    Bounding by *when* is not a claim about meaning — an appointment eight
    months away is not less important, it is simply not what an email that
    arrived this morning is plausibly about, and paying a judgement to
    consider it is paying for nothing.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected import situations

            instance_id = await _instance(db, uid)
            await _appointment(db, uid, ref="ev_vicino", what="Dentista",
                               when=_when(2, 10))
            await _appointment(db, uid, ref="ev_lontano", what="Dentista",
                               when=_when(240, 10))
            signal = await _mail_signal(db, uid, instance_id, subject="Il dentista")

            refs = {
                c["ref"] for c in await situations.candidates_for(db, uid, signal)
            }
            assert "ev_vicino" in refs
            assert "ev_lontano" not in refs
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_situation_the_life_model_already_holds_is_offered_as_one():
    """
    §12/§42: the Personal Life Model is the container, not a new graph.

    A Life Object already spans a document, an appointment and a goal. What
    this sprint adds is a way for a new reading to be *about* one — not a
    second place where things are said to go together.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected import situations

            now = datetime.now(timezone.utc).isoformat()
            await db.life_objects.insert_one({
                "id": "lo_salute", "user_id": uid, "type": "HEALTH",
                "title": "Controllo annuale", "status": "active",
                "documents": ["doc_tac"], "calendar_events": ["ev_dentista"],
                "created_at": now, "updated_at": now,
            })
            instance_id = await _instance(db, uid)
            signal = await _mail_signal(db, uid, instance_id, subject="La visita")

            candidates = await situations.candidates_for(db, uid, signal)
            situation = next(c for c in candidates if c["kind"] == "situation")

            assert situation["ref"] == "lo_salute"
            assert situation["already_holds"] == {"documents": 1, "appointments": 1}
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# E2E A — calendar and email, one afternoon
# ---------------------------------------------------------------------------

def test_an_email_about_an_appointment_is_the_same_situation(monkeypatch):
    """
    §24/§35: the sprint's headline. Two sources, one afternoon.

    The link is recorded with what it relied on, so "why does ORA think these
    are the same thing" has an answer that names the evidence rather than
    gesturing at a model.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected import situations

            service = _service(db)
            instance_id = await _instance(db, uid)
            await _appointment(db, uid, ref="ev_dentista", what="Dentista",
                               when=_when(2, 10))
            await _mail_signal(db, uid, instance_id,
                               subject="Il tuo appuntamento è stato spostato alle 16")

            _install(monkeypatch, Recorded([
                {"outcome": "changes_something_known",
                 "what_it_means": "La visita dal dentista è passata alle 16.",
                 "relates_to": "il dentista", "reasoning": "reg.",
                 "needs_content": False},
                {"relationship": "same_situation", "target_ref": "ev_dentista",
                 "confidence": 0.9,
                 "why": "Il messaggio parla dell'appuntamento di giovedì.",
                 "relied_on": ["ev_dentista"]},
            ]))

            out = await service.interpret(uid)

            assert out["passed_on"] == 1
            assert out["linked"] == 1

            links = await situations.links_for(db, uid)
            assert len(links) == 1
            link = links[0]
            assert link["relationship"] == "same_situation"
            assert link["target_kind"] == "appointment"
            assert link["target_ref"] == "ev_dentista"
            assert link["relied_on"] == ["ev_dentista"]
            assert link["reason_summary"], "un collegamento senza una ragione"

            # And the observation proposed to the Life Model carries the link,
            # so the provenance of a belief includes why two readings were
            # treated as one thing.
            memories = await db.memories.find({"user_id": uid}, {"_id": 0}).to_list(5)
            provenance = str([m.get("provenance") for m in memories])
            assert "situation_link:" in provenance or not memories
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_two_readings_are_not_merged_into_one_and_neither_is_overwritten(monkeypatch):
    """
    §17: same situation is not the same as same record.

    Both observations survive with their own provenance. A link that quietly
    rewrote the calendar observation with the email's time would be a system
    that believes the last thing it read, and it would be unfixable later
    because the original reading would be gone.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            service = _service(db)
            instance_id = await _instance(db, uid)
            await _appointment(db, uid, ref="ev_dentista", when=_when(2, 10))
            await _mail_signal(db, uid, instance_id, subject="Spostato alle 16")

            _install(monkeypatch, Recorded([
                {"outcome": "worth_knowing", "what_it_means": "Spostato.",
                 "relates_to": "il dentista", "reasoning": "reg.",
                 "needs_content": False},
                {"relationship": "same_situation", "target_ref": "ev_dentista",
                 "confidence": 0.8, "why": "Stessa visita.",
                 "relied_on": ["ev_dentista"]},
            ]))
            await service.interpret(uid)

            appointment = await db.connected_signals.find_one(
                {"owner_id": uid, "source_object_ref": "ev_dentista"}, {"_id": 0}
            )
            assert appointment["effective_at"] == _when(2, 10), (
                "l'osservazione del calendario è stata riscritta"
            )
            assert appointment["source_type"] == "calendar"
            assert await db.connected_signals.count_documents(
                {"owner_id": uid}
            ) == 2, "due letture sono diventate una"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# E2E B — email and document
# ---------------------------------------------------------------------------

def test_a_document_the_message_asks_for_can_be_linked_to_it(monkeypatch):
    """
    §23/§36: "portare il referto" and a referto on the shelf.

    The useful outcome is that the thing being asked for is already there.
    What this test checks is the part that makes such an outcome possible and
    honest: the document reached the judgement as a candidate, and the link
    that came back names it as the evidence.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected import situations

            service = _service(db)
            instance_id = await _instance(db, uid)
            await _document(db, uid, "doc_tac", "Referto TAC")
            await _mail_signal(db, uid, instance_id,
                               subject="Per la visita: portare il referto TAC")

            model = _install(monkeypatch, Recorded([
                {"outcome": "worth_knowing",
                 "what_it_means": "Le hanno chiesto di portare il referto.",
                 "relates_to": "la visita", "reasoning": "reg.",
                 "needs_content": False},
                {"relationship": "related", "target_ref": "doc_tac",
                 "confidence": 0.75,
                 "why": "Il referto richiesto è già tra i suoi documenti.",
                 "relied_on": ["doc_tac"]},
            ]))
            out = await service.interpret(uid)

            assert out["linked"] == 1
            link = (await situations.links_for(db, uid))[0]
            assert link["target_kind"] == "document"
            assert link["target_ref"] == "doc_tac"

            # The document was offered by title, never by content.
            assert "Referto TAC" in model.seen_payloads[1]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# E2E C — the sources disagree
# ---------------------------------------------------------------------------

def test_when_two_sources_disagree_both_statements_are_kept(monkeypatch):
    """
    §18/§37: the criterion. Code presents the disagreement; it never settles it.

    The calendar says 10:00 and the email says 16:00. What travels is both
    statements, when each was observed, and how directly each knows — and
    what is recorded afterwards is that they disagree. There is no branch
    anywhere that picks the fresher one, the more direct one, or the one from
    the source somebody once decided to trust.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected import situations

            service = _service(db)
            instance_id = await _instance(db, uid)
            await _appointment(db, uid, ref="ev_dentista", when=_when(2, 10))
            await _mail_signal(db, uid, instance_id, subject="Spostato alle 16",
                               received=_when(2, 16))

            model = _install(monkeypatch, Recorded([
                {"outcome": "worth_knowing",
                 "what_it_means": "Il messaggio dice un orario diverso.",
                 "relates_to": "il dentista", "reasoning": "reg.",
                 "needs_content": False},
                {"relationship": "same_situation", "target_ref": "ev_dentista",
                 "confidence": 0.6,
                 "why": "Stessa visita, con due orari diversi.",
                 "relied_on": ["ev_dentista"]},
            ]))
            await service.interpret(uid)

            # The disagreement reached the judgement with both sides.
            shown = model.seen_payloads[1]
            assert "disagreements" in shown
            assert "how_directly_it_knows" in shown

            link = (await situations.links_for(db, uid))[0]
            disagreement = link["disagreements"][0]
            assert disagreement["what_this_source_says"] != disagreement["what_the_other_says"]
            assert disagreement["this_source_observed_at"]
            assert disagreement["the_other_observed_at"]

            # What the message says is its own words — not the moment it
            # arrived. Presenting an arrival timestamp as a claim about an
            # appointment would be code inventing a contradiction out of two
            # unrelated times, and the model would be weighing a fiction.
            assert disagreement["what_this_source_says"] == "Spostato alle 16"
            assert disagreement["what_this_source_says"] != signal_arrival(link)
            assert "message" in disagreement["how_this_source_knows"]
            # No winner anywhere in the record.
            for deciding in ("winner", "resolved_to", "truth", "correct_value"):
                assert deciding not in str(link), f"il codice ha scelto: {deciding}"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_older_message_does_not_quietly_win_over_a_newer_calendar(monkeypatch):
    """
    §37: the ordering is a fact, and it is the model's to weigh.

    The message is a week old and the calendar was read this morning. A
    system that overwrote on arrival order would move the appointment to a
    time that was already superseded — and would do it silently, because
    nothing would have recorded that a decision was made at all.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected import situations

            service = _service(db)
            instance_id = await _instance(db, uid)
            await _appointment(db, uid, ref="ev_dentista", when=_when(2, 10))
            await _mail_signal(db, uid, instance_id, subject="Alle 16",
                               received=_when(-7, 16))

            _install(monkeypatch, Recorded([
                {"outcome": "worth_knowing", "what_it_means": "Un messaggio vecchio.",
                 "relates_to": "il dentista", "reasoning": "reg.",
                 "needs_content": False},
                {"relationship": "uncertain", "target_ref": "",
                 "confidence": 0.3,
                 "why": "Il messaggio è più vecchio dell'ultima lettura del calendario.",
                 "relied_on": []},
            ]))
            await service.interpret(uid)

            appointment = await db.connected_signals.find_one(
                {"owner_id": uid, "source_object_ref": "ev_dentista"}, {"_id": 0}
            )
            assert appointment["effective_at"] == _when(2, 10)

            link = (await situations.links_for(db, uid))[0]
            assert link["relationship"] == "uncertain"
            assert link["target_ref"] == ""
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_model_that_will_not_decide_produces_no_link(monkeypatch):
    """
    §14: `uncertain` is a real answer and nothing rescues it.

    There is deliberately no code path that picks the closest candidate when
    the model declines. A link nobody was sure of is worse than none: from
    then on everything downstream reasons about a situation that was never
    established, and the uncertainty is invisible.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected import situations

            service = _service(db)
            instance_id = await _instance(db, uid)
            await _appointment(db, uid, ref="ev_dentista")
            await _mail_signal(db, uid, instance_id, subject="Dentista")

            _install(monkeypatch, Recorded([
                {"outcome": "worth_knowing", "what_it_means": "Un messaggio.",
                 "relates_to": "", "reasoning": "reg.", "needs_content": False},
                # Says same_situation but names nothing. Half an answer.
                {"relationship": "same_situation", "target_ref": "",
                 "confidence": 0.9, "why": "Sembra la stessa cosa.",
                 "relied_on": []},
            ]))
            await service.interpret(uid)

            link = (await situations.links_for(db, uid))[0]
            assert link["relationship"] == "uncertain", (
                "un collegamento senza bersaglio è stato accettato"
            )
            assert link["target_ref"] == ""
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_target_that_was_never_offered_is_refused(monkeypatch):
    """
    §14: a link to something nobody put on the table is a link to nothing.

    And a link to nothing reads downstream exactly like a link to something,
    which is why this is checked in code rather than trusted.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected import situations

            service = _service(db)
            instance_id = await _instance(db, uid)
            await _appointment(db, uid, ref="ev_dentista")
            await _mail_signal(db, uid, instance_id, subject="Qualcosa")

            _install(monkeypatch, Recorded([
                {"outcome": "worth_knowing", "what_it_means": "Un messaggio.",
                 "relates_to": "", "reasoning": "reg.", "needs_content": False},
                {"relationship": "same_situation", "target_ref": "ev_inventato",
                 "confidence": 0.95, "why": "…", "relied_on": ["ev_inventato"]},
            ]))
            await service.interpret(uid)

            link = (await situations.links_for(db, uid))[0]
            assert link["target_ref"] == ""
            assert link["relationship"] == "uncertain"
            assert link["relied_on"] == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_noise_is_never_linked_to_anything(monkeypatch):
    """§26: nothing that meant nothing gets a second judgement paid for it."""
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected import situations

            service = _service(db)
            instance_id = await _instance(db, uid)
            await _appointment(db, uid, ref="ev_dentista")
            await _mail_signal(db, uid, instance_id, subject="-40% questo weekend")

            model = _install(monkeypatch, Recorded([
                {"outcome": "noise", "what_it_means": "", "relates_to": "",
                 "reasoning": "pubblicità", "needs_content": False},
            ]))
            out = await service.interpret(uid)

            assert out["linked"] == 0
            assert len(model.seen_payloads) == 1
            assert await situations.links_for(db, uid) == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_link_never_becomes_an_action(monkeypatch):
    """
    §19/§46: information authority is not action authority.

        A MESSAGE SAYING IT MOVED DOES NOT MOVE ANYTHING.

    The whole pass runs: a message says the appointment is at 16, the model
    says same situation, the observation is proposed. What must not exist
    anywhere in that chain is a write — to the calendar, to a goal, to an
    intent. If ORA is to change the appointment it goes through V3.9's
    authority model like everything else, starting with a person.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            service = _service(db)
            instance_id = await _instance(db, uid)
            await _appointment(db, uid, ref="ev_dentista", when=_when(2, 10))
            await _mail_signal(db, uid, instance_id,
                               subject="L'appuntamento è stato spostato alle 16")

            _install(monkeypatch, Recorded([
                {"outcome": "changes_something_known",
                 "what_it_means": "La visita risulta spostata alle 16.",
                 "relates_to": "il dentista", "reasoning": "reg.",
                 "needs_content": False},
                {"relationship": "same_situation", "target_ref": "ev_dentista",
                 "confidence": 0.9, "why": "Stessa visita.",
                 "relied_on": ["ev_dentista"]},
            ]))
            await service.interpret(uid)

            for collection in ("calendar_event_drafts", "action_intents",
                               "agent_receipts", "autonomous_goals",
                               "execution_claims"):
                assert await db[collection].count_documents(
                    {"$or": [{"owner_id": uid}, {"user_id": uid}]}
                ) == 0, f"una mail ha prodotto una scrittura in {collection}"
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


def test_no_candidate_is_chosen_by_comparing_two_pieces_of_text():
    """
    §13: the forbidden implementation, checked where it would be written.

        if "dentista" in email.subject: attach_to_dentist_event

    That line passes review, works on the demo, and is wrong about every
    person whose life does not use the word it was written for. This walks
    the retrieval module for any comparison between two strings that could
    stand in for identity.
    """
    tree = _code_only(_tree("connected/situations.py"))

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and any(
            isinstance(op, (ast.In, ast.NotIn)) for op in node.ops
        ):
            rendered = ast.dump(node)
            for texty in ("subject", "title", "what", "payload_summary", "label"):
                assert texty not in rendered, (
                    f"un candidato viene scelto confrontando testo: {texty}"
                )
        # Nor by any of the usual similarity helpers.
        if isinstance(node, ast.Call):
            called = getattr(node.func, "attr", getattr(node.func, "id", ""))
            assert called not in (
                "SequenceMatcher", "ratio", "get_close_matches", "fuzz",
                "levenshtein", "startswith", "endswith",
            ), f"il codice misura somiglianza: {called}"


def test_the_linking_decision_has_no_fallback_that_picks_a_candidate():
    """
    §14: when the model does not decide, nothing decides.

    Checked structurally because the fallback is such a natural thing to add
    — "if the model is unsure, take the closest in time" — and it would turn
    every uncertain case into a confident wrong one.
    """
    node = _code_only(_tree("connected/service.py"))
    linker = next(
        n for n in ast.walk(node)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_link_to_what_is_known"
    )
    body = ast.dump(linker)

    assert "decide_link" in body, "il collegamento non passa dal giudizio"
    # The only way a candidate is chosen is by matching the ref the model
    # named. No indexing into the list, no min/max over it, no sort.
    for picking in ("sorted(", "min(", "max("):
        assert picking not in ast.unparse(linker), f"il codice sceglie: {picking}"
    for node_ in ast.walk(linker):
        if isinstance(node_, ast.Subscript) and isinstance(node_.slice, ast.Constant):
            assert not isinstance(node_.slice.value, int), (
                "il codice prende un candidato per posizione"
            )


def test_recording_a_link_writes_a_link_and_nothing_else():
    """
    §16/§17: a link is a row, never a merge.

    The tempting version writes the email's time onto the Life Object, and it
    is wrong twice: it makes a durable claim without governance, and it
    destroys the reading it overwrote. This checks the module can only write
    to its own collection.
    """
    tree = _code_only(_tree("connected/situations.py"))
    written = set()
    for call in [n for n in ast.walk(tree) if isinstance(n, ast.Call)]:
        if getattr(call.func, "attr", "") in (
            "insert_one", "update_one", "replace_one", "delete_many", "update_many",
        ):
            target = call.func.value
            written.add(ast.unparse(target))

    assert written, "il modulo non scrive niente — il test è vuoto"
    for target in written:
        assert "LINKS" in target, f"scrive fuori dalla sua collezione: {target}"



def test_the_appointment_a_message_is_about_reaches_the_judgement():
    """
    Un limite troppo stretto esclude la risposta giusta, e in silenzio.

    Un messaggio su un appuntamento arriva giorni prima di quello di cui
    parla, e nel frattempo in agenda ci sono le cose di dopodomani. Con
    quattro posti presi dai candidati piu' vicini, la visita della settimana
    prossima — la sola cosa che l'email potesse riguardare — non veniva
    nemmeno mostrata, e il modello rispondeva «situazione nuova»: sulle carte
    che aveva, correttamente.
    """
    async def body():
        client, db = await _db()
        uid = f"link_{uuid.uuid4().hex[:8]}"
        try:
            instance_id = await _instance(db, uid)
            for n in range(6):
                await _appointment(
                    db, uid, ref=f"vicino_{n}", what=f"Cosa di domani {n}",
                    when=_when(1, 9 + n),
                )
            await _appointment(
                db, uid, ref="dentista", what="Visita dentistica",
                when=_when(7, 10),
            )
            signal = await _mail_signal(
                db, uid, instance_id,
                subject="Studio dentistico: cambio appuntamento",
            )

            from connected import situations

            found = await situations.candidates_for(db, uid, signal)
            refs = [c["ref"] for c in found if c["kind"] == "appointment"]
            assert "dentista" in refs, (
                "l'unico appuntamento di cui il messaggio poteva parlare "
                "non e' arrivato al giudizio"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_appointment_that_was_cancelled_is_not_offered_as_a_candidate():
    """
    Un impegno annullato non e' qualcosa di cui un messaggio possa parlare.

    Escluderlo e' un fatto sulla riga — c'e' scritto `cancelled` — e non
    un'opinione sul significato. Offrirlo invece riempiva i posti buoni con
    cose che non esistono piu'.
    """
    async def body():
        client, db = await _db()
        uid = f"link_{uuid.uuid4().hex[:8]}"
        try:
            instance_id = await _instance(db, uid)
            await _appointment(db, uid, ref="andato", what="Disdetto",
                               when=_when(2, 9))
            await db.ingestion_events.update_many(
                {"user_id": uid, "external_id": "andato"},
                {"$set": {"normalized_payload.status": "cancelled"}},
            )
            signal = await _mail_signal(
                db, uid, instance_id, subject="Qualcosa",
            )

            from connected import situations

            found = await situations.candidates_for(db, uid, signal)
            refs = [c["ref"] for c in found if c["kind"] == "appointment"]
            assert "andato" not in refs
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())
