"""
V3.10 Sprint 3 — a mailbox as signals, and a thread as one conversation.

    A MESSAGE IS NOT NEWS BECAUSE IT IS UNREAD.
    A THREAD IS ONE CONVERSATION, HOWEVER MANY MESSAGES IT HAS.
    EMAIL IS NOT MEANING.

The sensor half. What a message becomes, what it deliberately does not carry,
and the two mistakes that would make ORA into a mail client: reporting every
message as its own event, and letting code decide what a message is.

No live model calls: every judgement here is recorded.
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
    ):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


async def _mail_row(db, uid, instance_id, *, message_id, thread_id, subject,
                    relationship="unknown", received=None, categories=(),
                    attachments=False, supersedes=None):
    """One ingestion row in exactly the shape the connector writes."""
    row_id = f"ing_{uuid.uuid4().hex[:12]}"
    await db.ingestion_events.insert_one({
        "id": row_id, "user_id": uid, "connector_id": "mail_gmail",
        "connector_instance_id": instance_id, "external_id": message_id,
        "source_type": "mail_gmail", "source_record_type": "email_message",
        "ingestion_status": "processed",
        "normalized_payload": {
            "message_ref": message_id,
            "thread_ref": thread_id,
            "subject": subject,
            "sender_relationship": relationship,
            "recipient_count": 1,
            "received_at": received or datetime.now(timezone.utc).isoformat(),
            "attachments_present": attachments,
            "attachment_count": 1 if attachments else 0,
            "provider_categories": list(categories),
            "in_inbox": True,
            "content_available": True,
        },
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "supersedes_event_id": supersedes,
    })
    return row_id


async def _instance(db, uid):
    instance_id = f"inst_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    await db.connector_instances.insert_one({
        "id": instance_id, "user_id": uid, "connector_id": "mail_gmail",
        "status": "connected", "secret_reference": "vault_ref",
        "metadata": {"account_email": ACCOUNT}, "cursor": {},
        "created_at": now, "updated_at": now, "last_sync_at": now,
    })
    return instance_id


def _fields(signal) -> dict:
    return {c.field: c for c in signal.changed_fields}


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


# ---------------------------------------------------------------------------
# What a message becomes
# ---------------------------------------------------------------------------

def test_a_message_becomes_a_fact_without_its_words():
    """
    §5/§31: the subject travels, the body does not, the sender is a relationship.

    The subject is the message's own statement of what it is about and the
    one field without which nothing could ever be linked to an appointment.
    The body is marked present and withheld — both halves matter, because
    "there is more to read" is what makes asking possible.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected import email_sensor

            instance_id = await _instance(db, uid)
            await _mail_row(db, uid, instance_id, message_id="m1", thread_id="t1",
                            subject="Conferma appuntamento",
                            relationship="automated", attachments=True)

            signals = await email_sensor.read_changes(
                db, uid, source_id=instance_id,
            )

            assert len(signals) == 1
            signal = signals[0]
            assert signal.signal_type == "email.message.added"
            assert signal.source_type == "email"
            fields = _fields(signal)
            assert fields["subject"].after == "Conferma appuntamento"
            assert fields["sender_relationship"].after == "automated"
            assert fields["attachments_present"].after == "1 allegati"
            assert fields["body"].content_withheld is True
            assert fields["body"].after == "", "il corpo è nel segnale"
            assert "mittente automatico" in signal.payload_summary
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_provider_category_is_a_fact_and_never_a_verdict():
    """
    §11: a promotions label is what Google thinks, and that is evidence at best.

    The forbidden version of this test is the one where a category makes the
    code drop the message. Marketing and a flight cancellation can carry the
    same label, and a filter here would silently lose the second.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected import email_sensor

            instance_id = await _instance(db, uid)
            await _mail_row(db, uid, instance_id, message_id="m1", thread_id="t1",
                            subject="Offerte del mese", relationship="automated",
                            categories=("CATEGORY_PROMOTIONS",))

            signals = await email_sensor.read_changes(db, uid, source_id=instance_id)

            assert len(signals) == 1, "il codice ha scartato una promozione"
            assert _fields(signals[0])["provider_category"].after == "CATEGORY_PROMOTIONS"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_three_replies_in_one_pass_are_one_conversation():
    """
    §9: the criterion. A thread is one thing, however many messages it has.

    Reporting three arrivals would describe the world wrongly and cost three
    judgements for one event in somebody's life. The conversation's words
    become the latest message's, because in a conversation the last thing
    said is the state of it.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected import email_sensor

            instance_id = await _instance(db, uid)
            for n, subject in enumerate([
                "Richiesta ricevuta", "Richiesta in valutazione", "Richiesta approvata",
            ]):
                await _mail_row(db, uid, instance_id, message_id=f"m{n}",
                                thread_id="t_pratica", subject=subject)

            signals = await email_sensor.read_changes(db, uid, source_id=instance_id)

            assert len(signals) == 1, f"{len(signals)} segnali per una conversazione"
            assert signals[0].covers == 3
            assert signals[0].signal_type == "email.thread.updated"
            assert "approvata" in signals[0].payload_summary, (
                "la conversazione non è ferma all'ultimo messaggio"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_reply_to_a_conversation_already_seen_is_that_conversation_moving(monkeypatch):
    """
    §27/§41: the thread evolves across passes, and the second pass says so.

    "Richiesta approvata" arriving a day after "richiesta ricevuta" is the
    same situation reaching a different state — not a new arrival, which is
    what a system with no memory of threads would call it.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected import email_sensor

            service = _service(db)
            instance_id = await _instance(db, uid)
            await _mail_row(db, uid, instance_id, message_id="m1",
                            thread_id="t_pratica", subject="Richiesta ricevuta")
            first = await email_sensor.read_changes(db, uid, source_id=instance_id)
            for signal in first:
                await service.signals.record(signal)
            assert first[0].signal_type == "email.message.added"

            watermark = first[0].observed_at
            await _mail_row(db, uid, instance_id, message_id="m2",
                            thread_id="t_pratica", subject="Richiesta approvata")

            second = await email_sensor.read_changes(
                db, uid, source_id=instance_id, since=watermark,
            )
            assert len(second) == 1
            assert second[0].signal_type == "email.thread.updated"
            assert second[0].covers == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_two_messages_in_different_conversations_stay_two_things():
    """§9: folding is per conversation, not a general urge to say less."""
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected import email_sensor

            instance_id = await _instance(db, uid)
            await _mail_row(db, uid, instance_id, message_id="m1", thread_id="t1",
                            subject="Il dentista")
            await _mail_row(db, uid, instance_id, message_id="m2", thread_id="t2",
                            subject="La banca")

            signals = await email_sensor.read_changes(db, uid, source_id=instance_id)
            assert {s.after for s in signals} == {"Il dentista", "La banca"}
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_same_message_seen_twice_is_recorded_once():
    """§10: dedupe at the signal layer, on top of dedupe at the ingestion layer."""
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected import email_sensor

            service = _service(db)
            instance_id = await _instance(db, uid)
            await _mail_row(db, uid, instance_id, message_id="m1", thread_id="t1",
                            subject="Ciao")

            for _ in range(2):
                for signal in await email_sensor.read_changes(
                    db, uid, source_id=instance_id,
                ):
                    await service.signals.record(signal)

            assert await db.connected_signals.count_documents({"owner_id": uid}) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Meaning stays with the model
# ---------------------------------------------------------------------------

def test_a_newsletter_can_end_in_nothing_at_all(monkeypatch):
    """
    §26/§39: the criterion. Noise costs nobody anything.

    No wake, no change log entry, no memory, nothing on the home screen. And
    the word `noise` is the model's — there is no rule anywhere that says a
    promotions label means unimportant.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected import email_sensor

            service = _service(db)
            instance_id = await _instance(db, uid)
            await _mail_row(db, uid, instance_id, message_id="m1", thread_id="t1",
                            subject="-40% questo weekend", relationship="automated",
                            categories=("CATEGORY_PROMOTIONS",))
            for signal in await email_sensor.read_changes(db, uid, source_id=instance_id):
                await service.signals.record(signal)

            _install(monkeypatch, Recorded([
                {"outcome": "noise", "what_it_means": "", "relates_to": "",
                 "reasoning": "pubblicità", "needs_content": False},
            ]))
            out = await service.interpret(uid)

            assert out["noise"] == 1 and out["passed_on"] == 0
            assert out["linked"] == 0, "ha pagato un collegamento per del rumore"
            assert await db.ambient_wakes.count_documents({"owner_id": uid}) == 0
            assert await db.meaningful_changes.count_documents({"owner_id": uid}) == 0
            assert await db.memories.count_documents({"user_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_message_that_matters_knocks_on_the_doors_that_already_exist(monkeypatch):
    """
    §16/§44/§45: no new agent, no new delivery, no goal created here.

    What a meaningful message produces is the same three things a moved
    appointment produces: a change in the log V3.7 built, a wake in the
    scheduler V3.8 built, and nothing else. The goal decision belongs to
    V3.9 and is not made in this package.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected import email_sensor

            service = _service(db)
            instance_id = await _instance(db, uid)
            await _mail_row(db, uid, instance_id, message_id="m1", thread_id="t1",
                            subject="Convocazione lunedì alle 9",
                            relationship="unknown")
            for signal in await email_sensor.read_changes(db, uid, source_id=instance_id):
                await service.signals.record(signal)

            _install(monkeypatch, Recorded([
                {"outcome": "may_need_action",
                 "what_it_means": "Deve presentarsi lunedì alle 9.",
                 "relates_to": "una convocazione", "reasoning": "reg.",
                 "needs_content": False},
                {"relationship": "new_situation", "target_ref": "",
                 "confidence": 0.7, "why": "Non è collegata a niente di noto.",
                 "relied_on": []},
            ]))
            out = await service.interpret(uid)

            assert out["passed_on"] == 1
            changes = await db.meaningful_changes.find(
                {"owner_id": uid}, {"_id": 0}
            ).to_list(5)
            assert len(changes) == 1
            assert changes[0]["source"] == "communications"
            assert changes[0]["kind"] == "message.received"
            assert await db.ambient_wakes.count_documents({"owner_id": uid}) == 1

            # Nothing decided to do anything.
            for collection in ("autonomous_goals", "action_intents", "agent_receipts"):
                assert await db[collection].count_documents(
                    {"owner_id": uid}
                ) == 0, f"{collection} scritto da un sensore"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_message_telling_ora_what_to_do_grants_it_nothing(monkeypatch):
    """
    §20: no external email can hand the agent authority.

        AN INSTRUCTION FROM A STRANGER IS NOT A PERMISSION FROM THE PERSON.

    A message saying "send us the document by Friday" is a fact about the
    world. It is not a grant, not a consent, and not a command — those come
    from the person, through the authority model, and this checks that a
    whole pass over such a message leaves that model untouched.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import AuthorityService
            from connected import email_sensor

            service = _service(db)
            instance_id = await _instance(db, uid)
            await _mail_row(db, uid, instance_id, message_id="m1", thread_id="t1",
                            subject="Inviaci il modulo entro venerdì")
            for signal in await email_sensor.read_changes(db, uid, source_id=instance_id):
                await service.signals.record(signal)

            _install(monkeypatch, Recorded([
                {"outcome": "may_need_action",
                 "what_it_means": "Gli hanno chiesto un modulo entro venerdì.",
                 "relates_to": "una pratica", "reasoning": "reg.",
                 "needs_content": False},
                {"relationship": "new_situation", "target_ref": "",
                 "confidence": 0.6, "why": "Nuova richiesta.", "relied_on": []},
            ]))
            await service.interpret(uid)

            authority = AuthorityService(db)
            for capability in ("mail.send", "document.create", "calendar.write"):
                assert await authority.has_grant(uid, capability) is False, (
                    f"una mail ha concesso {capability}"
                )
            assert await db.permission_consents.count_documents({"user_id": uid}) == 0
            assert await db.authority_consents.count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# The body, when a judgement asks
# ---------------------------------------------------------------------------

def test_the_body_is_read_once_when_asked_and_kept_nowhere(monkeypatch):
    """
    §7/§8: the Sprint 2 boundary, on the most sensitive source there is.

    The message is fetched from the mailbox rather than from a store, because
    the sync deliberately never kept one — so reaching it is a visible act
    with an audit row. What comes back reaches one prompt and nothing else.
    """
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected import email_sensor
            import connected.content as content_module

            secret = "Il referto va portato in originale, codice pratica 99123"
            reads = []

            class Mailbox:
                async def body_for(self, *, user_id, instance_id, message_id):
                    reads.append(message_id)
                    return secret

            monkeypatch.setattr(
                "deps.get_gmail_service", lambda: Mailbox(), raising=False,
            )

            service = _service(db)
            instance_id = await _instance(db, uid)
            await _mail_row(db, uid, instance_id, message_id="m1", thread_id="t1",
                            subject="Informazioni per la visita")
            for signal in await email_sensor.read_changes(db, uid, source_id=instance_id):
                await service.signals.record(signal)

            model = _install(monkeypatch, Recorded([
                {"outcome": "noise", "what_it_means": "", "relates_to": "",
                 "reasoning": "non posso decidere senza leggerlo",
                 "needs_content": True, "why_content": "cosa chiede il messaggio"},
                {"outcome": "worth_knowing",
                 "what_it_means": "Deve portare il referto in originale.",
                 "relates_to": "la visita", "reasoning": "reg.",
                 "needs_content": False},
                {"relationship": "new_situation", "target_ref": "",
                 "confidence": 0.5, "why": "Nuova.", "relied_on": []},
            ]))
            out = await service.interpret(uid)

            assert out["asked_for_content"] == 1
            assert reads == ["m1"], "il corpo non è stato letto dalla casella"
            assert secret not in model.seen_payloads[0]
            assert "99123" in model.seen_payloads[1]

            for collection in ("connected_signals", "connected_content_reads",
                               "ingestion_events", "meaningful_changes", "memories"):
                rows = await db[collection].find(
                    {"$or": [{"owner_id": uid}, {"user_id": uid}]}, {"_id": 0}
                ).to_list(20)
                assert "99123" not in str(rows), f"il messaggio è finito in {collection}"

            audit = await db.connected_content_reads.find(
                {"owner_id": uid}, {"_id": 0}
            ).to_list(5)
            assert len(audit) == 1 and audit[0]["fields"] == ["body"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_mailbox_that_will_not_answer_does_not_stop_the_judgement(monkeypatch):
    """§40: an unreadable body is decided without, not crashed on."""
    async def body():
        client, db = await _db()
        uid = f"s3_{uuid.uuid4().hex[:8]}"
        try:
            from connected import email_sensor

            class Broken:
                async def body_for(self, **kw):
                    raise RuntimeError("token revoked")

            monkeypatch.setattr(
                "deps.get_gmail_service", lambda: Broken(), raising=False,
            )
            service = _service(db)
            instance_id = await _instance(db, uid)
            await _mail_row(db, uid, instance_id, message_id="m1", thread_id="t1",
                            subject="Qualcosa")
            for signal in await email_sensor.read_changes(db, uid, source_id=instance_id):
                await service.signals.record(signal)

            _install(monkeypatch, Recorded([
                {"outcome": "noise", "what_it_means": "", "relates_to": "",
                 "reasoning": "servirebbe il testo", "needs_content": True,
                 "why_content": "capire cosa chiede"},
            ]))
            out = await service.interpret(uid)

            assert out["ok"] is True
            assert out["asked_for_content"] == 0, "una lettura fallita è stata contata"
            assert out["noise"] == 1
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


def test_no_code_path_decides_what_a_message_is():
    """
    §6/§11/§13: meaning is not derived from a subject, a sender or a label.

    The whole sprint fails quietly if somebody adds `if "conferma" in
    subject`. It would pass every behavioural test, work on the examples it
    was written for, and be wrong about everybody whose life does not use
    those words.
    """
    source = (HERE / "connected/email_sensor.py").read_text(encoding="utf-8")
    body = ast.dump(_code_only(ast.parse(source)))

    for word in ("conferma", "confirm", "cancell", "annull", "scadenz",
                 "urgent", "fattura", "invoice", "newsletter", "promo",
                 "spam", "unsubscribe"):
        assert word not in body.lower(), f"il sensore cerca la parola «{word}»"

    # And no comparison against the subject at all: the field is carried, not
    # inspected. `in` over a subject is exactly how the first version of this
    # mistake gets written.
    for node in ast.walk(_code_only(ast.parse(source))):
        if isinstance(node, ast.Compare) and any(
            isinstance(op, (ast.In, ast.NotIn)) for op in node.ops
        ):
            rendered = ast.dump(node)
            assert "subject" not in rendered, "il sensore ispeziona l'oggetto"


def test_nothing_ranks_the_sources_against_each_other():
    """
    §43: no static weights. Anywhere.

        CODE DOES NOT CHOOSE THE TRUE SOURCE.

    A table saying `calendar=0.9, email=0.8` would be a permanent, invisible
    answer to a question that depends entirely on the situation — and it is
    the single most likely thing for somebody to add the first time two
    sources disagree in production.
    """
    for name in ("connected/situations.py", "connected/email_sensor.py",
                 "connected/service.py"):
        tree = _code_only(_tree(name))
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys = {
                    k.value for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                }
                values_are_numbers = node.values and all(
                    isinstance(v, ast.Constant) and isinstance(v.value, (int, float))
                    for v in node.values
                )
                assert not (
                    values_are_numbers and {"email", "calendar"} & keys
                ), f"{name} pesa le sorgenti"
        source = ast.dump(tree).lower()
        for weighing in ("source_weight", "trust_score", "authority_score",
                         "priority_by_source"):
            assert weighing not in source, f"{name} contiene {weighing}"


def test_nothing_in_the_content_layer_can_log_what_it_read():
    """
    §32: no body in the logs. Checked at the only place a body exists.

    A log line is the easiest place in the world for private content to end
    up, and the most invisible: it is added while debugging, it is not in the
    database, no test looks at it, and it ships. So every logging call in the
    module that handles content is walked, and none of them may reference a
    name that holds any.
    """
    tree = _code_only(_tree("connected/content.py"))
    holds_content = {"text", "content", "body", "notes", "value", "out",
                     "payload", "row", "message", "secret"}

    for call in [n for n in ast.walk(tree) if isinstance(n, ast.Call)]:
        target = getattr(call.func, "value", None)
        if getattr(target, "id", "") != "logger":
            continue
        for argument in ast.walk(call):
            if isinstance(argument, ast.Name):
                assert argument.id not in holds_content, (
                    f"un log può stampare {argument.id}"
                )
            if isinstance(argument, ast.Attribute):
                assert argument.attr not in holds_content, (
                    f"un log può stampare .{argument.attr}"
                )


def test_the_sensor_never_talks_to_the_mailbox_itself():
    """
    §22: no attachment downloads, no body fetches, no second read of anybody's mail.

    The sensor works from ingestion rows. Reaching the provider from here
    would be a read of somebody's mailbox with no judgement having asked for
    it and no audit row recording it — which is exactly how "just fetch the
    attachment while we're here" gets written.
    """
    tree = _tree("connected/email_sensor.py")
    imported = {
        (n.module or "") for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
    }
    assert not any(
        m.startswith("connectors.gmail.service") or m == "deps" for m in imported
    ), "il sensore può parlare con la casella"

    source = ast.dump(_code_only(tree))
    # The fetch verbs, not the field names: `attachments_present` is a fact
    # the row already carries, and forbidding the word would forbid saying so.
    for reaching in ("get_gmail_service", "body_of", "body_for", "metadata_of",
                     "attachmentId", "get_attachment", "download"):
        assert reaching not in source, f"il sensore va a prendere: {reaching}"
