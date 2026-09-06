"""
The mailbox, read as something happening rather than as an inbox.

    A MESSAGE IS NOT NEWS BECAUSE IT IS UNREAD.
    A THREAD IS ONE CONVERSATION, HOWEVER MANY MESSAGES IT HAS.

Third sensor, and the one that most needed to not become a feature. Every
instinct here pulls toward building a mail client: unread counts, a list, a
"you have 12 new emails" card. None of that is knowledge about a life. What
this produces is the same thing the other two sensors produce — a fact that
something changed, in words, with no opinion attached.

Three things it is careful about.

**A thread is one thing.** Three replies in one pass is one conversation
moving, not three arrivals. They fold into a single signal about the thread,
which says how many messages it covers — for exactly the reason a recurring
series folds: reporting it three times would describe the world wrongly and
cost three judgements for one event in somebody's life.

**Nothing here decides what a message is.** There is no rule that says a
newsletter is noise, that a no-reply address is unimportant, or that a
subject containing "conferma" is a confirmation. The provider's own category
travels as a fact and so does the sender relationship, and both are evidence
for a judgement made elsewhere. `automated` is the sharpest case: a flight
change, a hospital reminder and a marketing blast are all automated, and code
that treated the word as a verdict would silently drop two of the three.

**The words stay in the mailbox.** A signal carries the subject — the
message's own statement of what it is about, and the one field without which
nothing could ever be connected to an appointment — and the fact that a body
exists. The body itself is never in a signal, and is read only when a
judgement says it cannot decide without it.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from connected.models import ConnectedSignal, FieldChange, SignalType, now_iso
from connectors.gmail.scopes import EMAIL_RECORD_TYPE

logger = logging.getLogger("ora.connected.email")

MAX_ROWS = 40

# What a person could notice about a message that arrived. Everything here is
# a fact about the message; none of it is a claim about what the message is.
OBSERVABLE_EMAIL_FIELDS = (
    "subject",
    "sender_relationship",
    "received_at",
    "attachments_present",
    "recipient_count",
    "provider_categories",
)

# Present, deliberately not carried. The judgement is told it exists so that
# "I cannot decide without reading it" is a thing it can say, rather than a
# gap it has to guess across.
WITHHELD_EMAIL_FIELDS = ("body",)


async def read_changes(
    db, owner_id: str, *, source_id: str, since: Optional[str] = None,
) -> List[ConnectedSignal]:
    """
    What has arrived in this mailbox since we last looked.

    Reads the ingestion rows the sync wrote — never the provider. The rows
    are already deduped, already minimised and already ours, and going back
    to Gmail here would be a second read of somebody's mail to learn
    something we had already been told.
    """
    query: Dict[str, Any] = {
        "user_id": owner_id,
        "connector_instance_id": source_id,
        "source_record_type": EMAIL_RECORD_TYPE,
    }
    if since:
        query["ingested_at"] = {"$gt": since}

    try:
        rows = await db.ingestion_events.find(query, {"_id": 0}).sort(
            "ingested_at", 1
        ).to_list(MAX_ROWS)
    except Exception as e:
        logger.info("email read soft-fail: %s", type(e).__name__)
        return []

    ours = await _ora_sent(db, owner_id)
    seen_before = await _threads_already_seen(db, owner_id, source_id)

    signals: List[ConnectedSignal] = []
    for row in rows:
        signal = _signal_for(owner_id, source_id, row, ours, seen_before)
        if signal is not None:
            signals.append(signal)
            thread = str(signal.provenance.get("thread_ref") or "")
            if thread:
                seen_before.setdefault(thread, set()).add(signal.source_object_ref)
    return _fold_threads(signals)


def _signal_for(
    owner_id: str, source_id: str, row: Dict[str, Any], ours: set,
    seen_before: Dict[str, set],
) -> Optional[ConnectedSignal]:
    payload = row.get("normalized_payload") or {}
    message_ref = str(payload.get("message_ref") or row.get("external_id") or "")
    if not message_ref:
        return None

    thread_ref = str(payload.get("thread_ref") or "")
    subject = str(payload.get("subject") or "").strip()

    # A conversation we have observed *through a different message* is a
    # conversation moving on. Reading the same message again is not: a replay
    # after a resync would otherwise turn one arrival into an update and
    # produce a second signal about an event that happened once. The
    # distinction is structural and carries no claim about whether the move
    # matters.
    continues = bool(thread_ref) and bool(
        seen_before.get(thread_ref, set()) - {message_ref}
    )
    kind: SignalType = (
        "email.thread.updated" if continues else "email.message.added"
    )

    changed = [
        FieldChange(field="subject", after=subject[:160]),
        FieldChange(
            field="sender_relationship",
            after=str(payload.get("sender_relationship") or "unknown"),
        ),
        FieldChange(field="received_at", after=str(payload.get("received_at") or "")),
    ]
    if payload.get("attachments_present"):
        changed.append(FieldChange(
            field="attachments_present",
            after=f"{int(payload.get('attachment_count') or 1)} allegati",
        ))
    for category in payload.get("provider_categories") or []:
        changed.append(FieldChange(field="provider_category", after=str(category)[:40]))
    if payload.get("content_available"):
        # The body exists and is not here. Both halves are the point.
        changed.append(FieldChange(field="body", content_withheld=True))

    return ConnectedSignal(
        owner_id=owner_id,
        source_id=source_id,
        source_type="email",
        signal_type=kind,
        observed_at=str(row.get("ingested_at") or now_iso()),
        effective_at=str(payload.get("received_at") or "") or None,
        source_object_ref=message_ref,
        payload_summary=_in_words(kind, payload),
        after=subject[:160],
        changed_fields=changed,
        origin="self_originated" if message_ref in ours else "external",
        # Whose the message is, in the same vocabulary the calendar uses:
        # something that arrived from outside is not this person's own
        # arrangement, and `invited` is the closest true word for it.
        relationship="own" if payload.get("sender_relationship") == "self" else "invited",
        provenance={
            "connector_id": row.get("connector_id"),
            "instance_id": source_id,
            "ingestion_event_id": row.get("id"),
            "thread_ref": thread_ref,
            "sender_relationship": str(payload.get("sender_relationship") or "unknown"),
        },
        confidence="certain",
        raw_ref=str(row.get("id") or "")[:120],
    )


def _in_words(kind: str, payload: Dict[str, Any]) -> str:
    """One sentence a person would recognise. Never a verdict on the message."""
    subject = str(payload.get("subject") or "").strip()[:80] or "senza oggetto"
    who = {
        "self": "da te stesso",
        "known_person": "da qualcuno che conosci",
        "automated": "da un mittente automatico",
        "unknown": "da un mittente che ORA non conosce",
    }.get(str(payload.get("sender_relationship") or "unknown"), "")
    if kind == "email.thread.updated":
        return f"È arrivato un altro messaggio su «{subject}», {who}."
    return f"È arrivato un messaggio {who}: «{subject}»."


def _fold_threads(signals: List[ConnectedSignal]) -> List[ConnectedSignal]:
    """
    Messages of one conversation, in one pass, as one signal.

        A THREAD IS ONE CONVERSATION, HOWEVER MANY MESSAGES IT HAS.

    Arithmetic, not judgement: the first signal of a thread stands, later
    ones in the same pass increment what it covers, and its own words become
    the words of the last message — because in a conversation the latest
    thing said is the state of it. Nothing is discarded on grounds of
    importance, and a message belonging to no thread folds into nothing.
    """
    kept: List[ConnectedSignal] = []
    first_of: Dict[str, ConnectedSignal] = {}
    for signal in signals:
        thread = str(signal.provenance.get("thread_ref") or "")
        anchor = first_of.get(thread) if thread else None
        if anchor is None:
            if thread:
                first_of[thread] = signal
            kept.append(signal)
            continue

        anchor.covers += 1
        # The conversation is now at the later message, and says so.
        anchor.signal_type = "email.thread.updated"
        anchor.payload_summary = signal.payload_summary
        anchor.after = signal.after
        anchor.effective_at = signal.effective_at or anchor.effective_at
        anchor.fingerprint = anchor.compute_fingerprint()
    return kept


async def _threads_already_seen(db, owner_id: str, source_id: str) -> Dict[str, set]:
    """
    Conversations ORA has observed, and through which messages.

    Read from the signals already recorded rather than from the mailbox: the
    question is what *we* have seen, and a mailbox cannot answer that. The
    message refs are kept, not just the thread, because "have we seen this
    conversation" and "have we seen this message" are different questions and
    only the first makes something an update.
    """
    out: Dict[str, set] = {}
    try:
        rows = await db.connected_signals.find(
            {"owner_id": owner_id, "source_id": source_id, "source_type": "email"},
            {"_id": 0, "provenance": 1, "source_object_ref": 1},
        ).sort("observed_at", -1).to_list(200)
    except Exception as e:
        logger.info("thread history soft-fail: %s", type(e).__name__)
        return out
    for row in rows:
        thread = str((row.get("provenance") or {}).get("thread_ref") or "")
        if thread:
            out.setdefault(thread, set()).add(str(row.get("source_object_ref") or ""))
    return out


async def _ora_sent(db, owner_id: str) -> set:
    """
    Messages ORA itself is responsible for, by its own record of doing it.

        ORA MUST RECOGNISE ITS OWN FOOTPRINTS.

    Nothing writes mail today — there is no send capability wired anywhere in
    this system — so this set is empty in practice. It exists because the day
    a draft is sent is the day a mailbox starts handing ORA its own work
    back, and a loop that begins then would be very hard to see. The receipt
    is the evidence, exactly as it is for calendar writes.
    """
    handles: set = set()
    try:
        rows = await db.agent_receipts.find(
            {"owner_id": owner_id, "capability": {"$in": ["mail.send", "mail.draft"]}},
            {"_id": 0, "external_ref": 1},
        ).sort("requested_at", -1).to_list(50)
    except Exception as e:
        logger.info("own mail soft-fail: %s", type(e).__name__)
        return handles
    for row in rows:
        ref = str(row.get("external_ref") or "")
        if ref:
            handles.add(ref)
    return handles
