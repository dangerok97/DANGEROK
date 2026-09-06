"""
The calendar, read as a change rather than as a list.

    WHAT MATTERS IS NOT WHAT IS THERE. IT IS WHAT MOVED.

The connector already syncs incrementally and the ingestion pipeline already
decides whether a record is new, changed or unchanged — that work is not
repeated here. What was missing is the sentence a person would say: not "this
event has a new hash" but "la visita è passata dalle 10 alle 15".

So this reads the ingestion rows the sync just wrote, walks back to the row
each one superseded, and compares them. Two properties fall out of doing it
that way rather than by asking the provider again: it is free, and it is
replay-safe — running it twice over the same rows produces the same
fingerprints and therefore no second signal.

Three things it is careful about.

**One change, one signal — carrying everything.** An appointment that moved
and changed room is one thing that happened to somebody, so it is one signal.
It is emphatically *not* one fact: both differences travel, because choosing
between them would mean ranking them, and "arriving late matters more than
being in the wrong room" is a judgement about a life rather than about a
record.

    CODE KNOWS WHAT CHANGED. THE MODEL DECIDES WHETHER IT MATTERS.

The only thing filtered here is what a provider rewrites on every save — an
etag, a sequence number, its own timestamp. That is not relevance; it is the
difference between a record changing and a life changing.

**Recurring events.** Google gives each occurrence its own id and points it at
its master. Occurrences are what move, so occurrences are what we watch — and
when the rule itself changes, the provider hands back the master *and* the
occurrences it regenerated. Reporting that as fifty appointments moving would
be describing the world wrongly: one thing changed. So an occurrence whose
differences are already accounted for by its master's is folded into it, and
the master says how many it covers. An occurrence that changed something its
master did not is a separate fact and survives — that is somebody moving one
appointment out of a series, which is a different event in their life.

**Whose appointment it is.** An event this person arranged is theirs to
rearrange; one they were invited to belongs to whoever called it. The
difference travels as a fact, and separately reaches the authority ceiling:
acting on somebody else's commitment reaches a third party whatever else it
looks like.

**ORA's own footprints.** ORA writes an event, the sync sees a new event. If
that becomes an ordinary observation the agent reads its own work as news and
does it again — so the write is recognised, from ORA's own record of having
made it, and the signal is marked as ours.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from ingestion.reading import plain

from connected.models import (
    OBSERVABLE_FIELDS,
    WITHHELD_CONTENT_FIELDS,
    ConnectedSignal,
    FieldChange,
    SignalType,
    now_iso,
)

logger = logging.getLogger("ora.connected.calendar")

# How many ingestion rows one pass will turn into signals. A person coming
# back from two weeks offline should produce a bounded amount of work.
MAX_ROWS = 60

# The record type the ingestion pipeline writes for a calendar event, from
# whichever calendar connector. The one field about a calendar row that means
# the same thing to every writer.
CALENDAR_RECORD_TYPE = "calendar_event"


async def read_changes(
    db, owner_id: str, *, source_id: str, since: Optional[str] = None,
    account: str = "",
) -> List[ConnectedSignal]:
    """
    Turn what the last sync wrote into what changed, in words.

    `since` is a watermark and nothing more: correctness comes from the
    fingerprint, which makes re-reading the same rows harmless. The watermark
    only stops us paying for it.
    """
    query: Dict[str, Any] = {
        "user_id": owner_id,
        "connector_instance_id": source_id,
        # What every real writer stamps on a calendar row. `source_type` is
        # NOT that: the ingestion pipeline puts the connector's own id there
        # ("calendar_google", the Apple connector's id), so a filter on
        # "calendar" matched nothing that was ever written by a sync — only
        # the rows this package's own tests wrote for themselves. That is the
        # shape of mistake that passes every test and reads an empty world in
        # production, and the instance id above already pins the connector.
        "source_record_type": CALENDAR_RECORD_TYPE,
    }
    if since:
        query["ingested_at"] = {"$gt": since}

    try:
        rows = await db.ingestion_events.find(query, {"_id": 0}).sort(
            "ingested_at", 1
        ).to_list(MAX_ROWS)
    except Exception as e:
        logger.info("ingestion read soft-fail: %s", type(e).__name__)
        return []

    ours = await _ora_handles(db, owner_id)
    signals: List[ConnectedSignal] = []
    for row in rows:
        signal = await _signal_for(db, owner_id, source_id, row, ours, account)
        if signal is not None:
            signals.append(signal)
    return _fold_series(signals, rows)


def _unwrap(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    The normalised event, with each field's envelope taken off.

    One line, because the unwrapping now lives with the code that puts the
    envelope on. It had been a private copy here, and a private copy is what
    let the same mistake sit unnoticed in the Home adapter and in the chat's
    calendar query at the same time — three readers, three assumptions, one
    of them right.
    """
    return plain(payload)


async def _signal_for(
    db, owner_id: str, source_id: str, row: Dict[str, Any], ours: set,
    account: str = "",
) -> Optional[ConnectedSignal]:
    payload = _unwrap(row.get("normalized_payload"))
    external_id = str(row.get("external_id") or "")
    if not external_id:
        return None

    # A row that superseded nothing and is not new to us is a re-read of a
    # world that did not move. The pipeline already said so by skipping it.
    previous: Dict[str, Any] = {}
    prior_id = row.get("supersedes_event_id")
    if prior_id:
        try:
            found = await db.ingestion_events.find_one(
                {"id": prior_id, "user_id": owner_id},
                {"_id": 0, "normalized_payload": 1},
            )
            previous = _unwrap((found or {}).get("normalized_payload"))
        except Exception as e:
            logger.info("previous row soft-fail: %s", type(e).__name__)

    kind, changed = _what_changed(previous, payload)
    if kind is None:
        return None
    before, after = _headline(kind, previous, payload, changed)

    signal = ConnectedSignal(
        owner_id=owner_id,
        source_id=source_id,
        source_type="calendar",
        signal_type=kind,
        observed_at=str(row.get("ingested_at") or now_iso()),
        effective_at=_effective(payload),
        source_object_ref=external_id,
        payload_summary=_in_words(kind, payload, changed),
        before=before,
        after=after,
        changed_fields=changed,
        origin="self_originated" if external_id in ours else "external",
        relationship=_relationship(payload, account),
        provenance={
            "connector_id": row.get("connector_id"),
            "instance_id": source_id,
            "ingestion_event_id": row.get("id"),
            "series_master": str(payload.get("recurrence_instance_id") or ""),
            "is_series_master": bool(
                payload.get("recurrence_rule")
                and not payload.get("recurrence_instance_id")
            ),
        },
        confidence="certain",
        raw_ref=str(row.get("id") or "")[:120],
    )
    return signal


def _what_changed(
    previous: Dict[str, Any], current: Dict[str, Any],
) -> Tuple[Optional[SignalType], List[FieldChange]]:
    """
    Everything about this record that is now different. All of it.

        NOTHING IS DROPPED BECAUSE IT SEEMED UNIMPORTANT.

    This used to return one name and one pair of values, chosen by a
    hard-coded order: cancellation beat a time change, a time change beat a
    room change, and an attendee or a description beat nothing at all — they
    were discarded, on the grounds that "nobody would notice". That is a
    judgement about somebody's life, and it was being made here, where no
    context about the life exists.

    So now: `created` and `cancelled` when the record structurally appears or
    goes away, and otherwise `changed` with every observable difference
    attached. The result is sorted by field name, which is a serialisation
    order and not a ranking — there is no first, and nothing downstream reads
    position for meaning.
    """
    status = str(current.get("status") or "confirmed")
    if status == "cancelled":
        if str(previous.get("status") or "") == "cancelled":
            return None, []
        return "calendar.event.cancelled", [
            FieldChange(field="status", before="confermato", after="annullato")
        ]

    if not previous:
        return "calendar.event.created", [
            FieldChange(field="starts_at", after=_when(current)),
        ]

    changed = _observable_differences(previous, current)
    if not changed:
        # Nothing a person could observe differs. The provider rewrote its
        # own bookkeeping — an etag, a sequence — and that is a fact about a
        # record rather than about a life. Filtering it is arithmetic: the
        # comparison never looked at anything but the fields a human can see.
        return None, []
    return "calendar.event.changed", changed


def _observable_differences(
    previous: Dict[str, Any], current: Dict[str, Any],
) -> List[FieldChange]:
    """
    Compare the fields a person could observe, and report every difference.

    There is deliberately no branch below keyed on *which* field changed:
    every observable field is compared the same way, and the only per-field
    distinction is whether its content may be carried — which is a privacy
    rule, not a relevance one, and applies regardless of what the value is.
    """
    out: List[FieldChange] = []
    for field in OBSERVABLE_FIELDS:
        before = _readable(previous.get(field))
        after = _readable(current.get(field))
        if before == after:
            continue
        if field in WITHHELD_CONTENT_FIELDS:
            # It moved, and what it moved to is not ours to keep. The fact
            # travels; the content stays in the record it belongs to.
            out.append(FieldChange(field=field, content_withheld=True))
            continue
        out.append(FieldChange(field=field, before=before[:160], after=after[:160]))
    return sorted(out, key=lambda c: c.field)


def _readable(value: Any) -> str:
    """
    One comparable string for a field, whatever the provider put in it.

    Lists become a count rather than their contents: an attendee list is
    other people's addresses, and "two people instead of one" is the whole of
    what this layer needs to notice that it moved.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "si" if value else "no"
    if isinstance(value, (list, tuple)):
        return f"{len(value)}"
    if isinstance(value, dict):
        return "presente" if value else ""
    return str(value).strip()


def _headline(
    kind: str, previous: Dict[str, Any], current: Dict[str, Any],
    changed: List[FieldChange],
) -> Tuple[str, str]:
    """
    Two strings for surfaces that want one line, derived not chosen.

    `before`/`after` predate this file and other layers read them, so they
    stay — filled from the moment the thing is about, which is the one field
    every calendar change has. They are a convenience, and the composite
    delta is what anything deciding anything is given.
    """
    if kind == "calendar.event.cancelled":
        return _when(previous or current), ""
    if kind == "calendar.event.created":
        return "", _when(current)
    return _when(previous), _when(current)


def _when(payload: Dict[str, Any]) -> str:
    """The moment, in the words somebody would use for it."""
    raw = str(payload.get("starts_at") or "")
    if not raw:
        return ""
    from datetime import datetime

    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return raw[:160]
    return moment.strftime("%d/%m alle %H:%M")


def _effective(payload: Dict[str, Any]) -> Optional[str]:
    """When the thing itself is about, which is rarely when we saw it."""
    return str(payload.get("starts_at") or "") or None


def _relationship(payload: Dict[str, Any], account: str = "") -> str:
    """
    Whose commitment this is, from what the record says.

        AN APPOINTMENT SOMEBODY WAS INVITED TO IS SOMEBODY ELSE'S DECISION.

    Three answers and a fourth for not knowing, which is kept because it is
    sometimes the true one and because the convenient guess — "own" — is the
    one that would let ORA act on other people's arrangements.

    The organiser is what decides it. Attendees alone only say the event is
    shared; who called the meeting says whose it is, and those lead to
    different conclusions about what may be done without asking.
    """
    organiser = str(payload.get("organizer") or "").strip().lower()
    mine = str(account or "").strip().lower()
    attendees = payload.get("attendees") or []

    if organiser and mine:
        if organiser != mine:
            return "invited"
        return "shared" if attendees else "own"
    if attendees:
        # Somebody else is on it and we cannot tell who called it. Shared is
        # the honest reading and the cautious one.
        return "shared"
    if organiser and not mine:
        return "unknown"
    return "own"


def _fold_series(
    signals: List[ConnectedSignal], rows: List[Dict[str, Any]],
) -> List[ConnectedSignal]:
    """
    A recurring series changing is one thing, not one thing per occurrence.

        ONE CHANGE IS ONE SIGNAL, HOWEVER MANY ROWS THE PROVIDER SENT.

    When a rule changes, the provider hands back the master and every
    occurrence it regenerated. Folding is arithmetic on sets rather than a
    judgement: an occurrence survives on its own if it differs in a way its
    master does not, because that is somebody moving one appointment out of a
    series — a different event in their life, and one this must not swallow.
    """
    masters = {
        s.source_object_ref: s for s in signals
        if s.provenance.get("is_series_master")
    }
    if not masters:
        return signals

    parent_of = {
        str(r.get("external_id") or ""): str(
            (r.get("normalized_payload") or {}).get("recurrence_instance_id") or ""
        )
        for r in rows
    }

    kept: List[ConnectedSignal] = []
    for signal in signals:
        parent = parent_of.get(signal.source_object_ref, "")
        master = masters.get(parent) if parent else None
        if master is None or signal is master:
            kept.append(signal)
            continue

        if signal.signal_type != master.signal_type:
            # A new occurrence appearing inside a series whose rule also
            # changed is two pieces of news, not one. Folding across kinds
            # would swallow the arrival because the series happened to move
            # in the same pass.
            kept.append(signal)
            continue

        own_fields = {c.field for c in signal.changed_fields}
        master_fields = {c.field for c in master.changed_fields}
        if own_fields and not own_fields.issubset(master_fields):
            # It moved in a way the series did not. Its own news.
            kept.append(signal)
            continue

        master.covers += 1
        master.fingerprint = master.compute_fingerprint()

    for master in masters.values():
        if master.covers > 1:
            master.payload_summary = _series_words(master)
    return kept


def _series_words(master: ConnectedSignal) -> str:
    """The same sentence, said about a series rather than about a morning."""
    base = master.payload_summary.rstrip(".")
    return f"{base} — e vale per tutte le volte che si ripete."


def _in_words(kind: str, payload: Dict[str, Any], changed: List[FieldChange]) -> str:
    """
    One sentence, the way a person would say it. Never a record.

    Lists what differs without ranking it: "l'ora, il posto" is two facts in
    the order they serialise, and a reader supplies their own importance —
    which is the correct place for it to come from.
    """
    title = str(payload.get("title") or "un impegno").strip()[:80]
    if kind == "calendar.event.cancelled":
        return f"«{title}» è stato annullato."
    if kind == "calendar.event.created":
        when = _when(payload)
        return f"«{title}» è stato messo in calendario{_tail(when)}."

    names = {
        "title": "il nome",
        "starts_at": "l'ora",
        "ends_at": "la fine",
        "all_day": "la durata",
        "timezone": "il fuso",
        "location": "il posto",
        "status": "lo stato",
        "description": "le note",
        "attendees": "chi c'è",
        "recurrence_rule": "la ricorrenza",
        "recurrence_instance_id": "la serie",
        "organizer": "chi l'ha organizzato",
    }
    what = [names.get(c.field, c.field) for c in changed][:4]
    # Same shape for one field as for four. The alternative — agreeing the
    # participle with whatever happens to be first — reads worse in most
    # cases ("è cambiata le note") and would make the sentence depend on the
    # serialisation order, which is exactly the thing that carries no meaning.
    return f"Di «{title}» è cambiato: {', '.join(what)}."


def _tail(when: str) -> str:
    return f" per il {when}" if when else ""


async def _ora_handles(db, owner_id: str) -> set:
    """
    Everything ORA has itself put in this person's calendar.

        ORA MUST RECOGNISE ITS OWN FOOTPRINTS.

    Read from ORA's own records of having written — the execution receipts the
    agent keeps and the drafts the conversation keeps — rather than from a
    marker on the provider's copy. Our records cannot be copied by somebody
    duplicating an event, and they are the same records an audit would use to
    answer "did we do this?".

    Recognising is not ignoring. A signal about our own write is exactly what
    a verification wants to see; what it must never become is a reason to do
    the work again.
    """
    handles: set = set()
    try:
        receipts = await db.agent_receipts.find(
            {"owner_id": owner_id, "provider": "calendar"},
            {"_id": 0, "external_ref": 1},
        ).to_list(200)
        handles.update(
            str(r.get("external_ref")) for r in receipts if r.get("external_ref")
        )
    except Exception as e:
        logger.info("receipts read soft-fail: %s", type(e).__name__)

    try:
        drafts = await db.calendar_event_drafts.find(
            {"user_id": owner_id, "google_event_id": {"$ne": None}},
            {"_id": 0, "google_event_id": 1},
        ).to_list(200)
        handles.update(
            str(d.get("google_event_id")) for d in drafts if d.get("google_event_id")
        )
    except Exception as e:
        logger.info("drafts read soft-fail: %s", type(e).__name__)

    return handles
