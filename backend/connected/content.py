"""
Reading what was deliberately not kept, for exactly as long as a judgement needs it.

    WITHHELD IS NOT UNREACHABLE. IT IS UNKEPT.

Sprint 1 stopped carrying the content of private notes, attendee lists and
organisers: a stored signal is a thing that ends up in backups, logs and
support tickets, and somebody's medical note has no business in any of them.
What it kept was the fact — "the note changed" — because dropping that too
would have been protecting the content by lying about the world.

That leaves a real gap. Sometimes "the note changed" is genuinely
undecidable: it might say «portare gli esami» or it might say «ricordati il
parcheggio», and one of those matters. So the judgement is allowed to ask,
once, and this is what answers.

Three rules make it safe, and each is enforced somewhere a test can see it.

**It is never written down.** What comes back is a value in a local variable
that reaches one prompt and is then gone. Nothing here inserts, updates or
caches, and a guard walks the module for anything that could.

**It is never logged.** The audit row records that a read happened, whose it
was, which fields, and why — and has nowhere to put what was read.

**It is asked for, not taken.** Content is fetched only when the judgement
said it could not decide without it, and only for fields that actually
changed. A layer that pre-fetched everything "in case" would be the layer
that quietly undid the minimisation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from connected.calendar_sensor import CALENDAR_RECORD_TYPE, _unwrap
from connected.models import now_iso

logger = logging.getLogger("ora.connected.content")

READS = "connected_content_reads"

# How long the record that a read happened is kept. Long enough to answer
# "why did ORA see my note last Tuesday", short enough not to become a second
# diary.
RETENTION_DAYS = 90

# The most that ever reaches a prompt from a withheld field. A judgement that
# cannot be made from this much is a judgement that should not be made by
# reading more.
MAX_CHARS = 400


async def ensure_indexes(db) -> None:
    try:
        await db[READS].create_index([("owner_id", 1), ("read_at", -1)])
        await db[READS].create_index("expires_at", expireAfterSeconds=0)
    except Exception:
        logger.exception("indici content reads non creati (non fatale)")


async def read_transiently(
    db, owner_id: str, signal, *, why: str,
) -> Optional[Dict[str, str]]:
    """
    Fetch the withheld content behind one signal, for one judgement.

    Returns a small mapping of field name to bounded text, or `None` when
    there is nothing withheld to fetch — which is the common case and costs a
    dictionary comprehension.

    The return value is deliberately not stored by this function and must not
    be stored by its caller. It exists to be put in front of a model and then
    forgotten.
    """
    withheld = [c.field for c in signal.changed_fields if c.content_withheld]
    if not withheld:
        return None

    if signal.source_type == "calendar":
        content = await _from_calendar(db, owner_id, signal, withheld)
    elif signal.source_type == "documents":
        content = await _from_documents(db, owner_id, signal, withheld)
    elif signal.source_type == "email":
        content = await _from_email(db, owner_id, signal, withheld)
    else:
        content = None

    if not content:
        return None

    await _note_the_read(db, owner_id, signal, fields=list(content), why=why)
    return content


async def _from_calendar(db, owner_id: str, signal, withheld) -> Dict[str, str]:
    """
    The event as ingestion last normalised it, minus everything not asked for.

    Read from ORA's own ingestion row rather than from the provider: it is
    already there, it is already governed, and going back to Google would be
    a second network call to fetch something we deliberately declined to keep
    a copy of.
    """
    try:
        row = await db.ingestion_events.find_one(
            {"user_id": owner_id, "external_id": signal.source_object_ref,
             "source_record_type": CALENDAR_RECORD_TYPE},
            {"_id": 0, "normalized_payload": 1},
            sort=[("ingested_at", -1)],
        )
    except Exception as e:
        logger.info("calendar content soft-fail: %s", type(e).__name__)
        return {}

    payload = _unwrap((row or {}).get("normalized_payload"))
    out: Dict[str, str] = {}
    for field in withheld:
        value = payload.get(field)
        if field == "attendees":
            # How many, never who. An attendee list is other people's
            # addresses, and a judgement about somebody's afternoon does not
            # need them — it needs to know that the meeting has people on it.
            people = value if isinstance(value, list) else []
            if people:
                out[field] = f"{len(people)} persone"
            continue
        if field == "organizer":
            out[field] = "qualcun altro" if value else ""
            continue
        text = str(value or "").strip()
        if text:
            out[field] = text[:MAX_CHARS]
    return {k: v for k, v in out.items() if v}


async def _from_documents(db, owner_id: str, signal, withheld) -> Dict[str, str]:
    """The document's own annotation, bounded. Never the file's text."""
    try:
        row = await db.documents.find_one(
            {"id": signal.source_object_ref, "user_id": owner_id},
            {"_id": 0, "notes": 1},
        )
    except Exception as e:
        logger.info("document content soft-fail: %s", type(e).__name__)
        return {}
    notes = str((row or {}).get("notes") or "").strip()
    if "notes" in withheld and notes:
        return {"notes": notes[:MAX_CHARS]}
    return {}


async def _from_email(db, owner_id: str, signal, withheld) -> Dict[str, str]:
    """
    The text of one message, fetched from the mailbox for one judgement.

    Unlike the other two sensors this cannot read from an ingestion row,
    because the sync deliberately never stored a body — so this is a real
    call to the provider, for one message, by id. That is the honest cost of
    not keeping people's mail: reaching it again is a visible act with an
    audit row rather than a lookup in a store we should not have.

    A body that cannot be fetched — no connection, a revoked token, a message
    that is gone — returns nothing at all. The judgement then decides without
    it, which is what it was doing a moment ago anyway.
    """
    if "body" not in withheld:
        return {}
    try:
        from deps import get_gmail_service

        text = await get_gmail_service().body_for(
            user_id=owner_id,
            instance_id=signal.source_id,
            message_id=signal.source_object_ref,
        )
    except Exception as e:
        logger.info("mail content soft-fail: %s", type(e).__name__)
        return {}
    text = str(text or "").strip()
    return {"body": text[:MAX_CHARS]} if text else {}


async def _note_the_read(db, owner_id: str, signal, *, fields, why: str) -> None:
    """
    Write down that this happened. There is nowhere here to put what was read.

    The shape is the safeguard: whose, which signal, which fields, when, and
    the reason the judgement gave. Somebody asking "why did ORA look at my
    note" gets an answer, and somebody with access to this collection learns
    nothing they did not already have.
    """
    try:
        await db[READS].insert_one({
            "owner_id": owner_id,
            "signal_id": signal.id,
            "source_type": signal.source_type,
            "source_object_ref": signal.source_object_ref,
            "fields": [str(f)[:40] for f in fields][:8],
            "why": str(why)[:200],
            "read_at": now_iso(),
            "expires_at": datetime.now(timezone.utc) + timedelta(days=RETENTION_DAYS),
        })
    except Exception as e:
        logger.info("content read note soft-fail: %s", type(e).__name__)


async def reads_for(db, owner_id: str, *, limit: int = 20):
    """When ORA has looked at withheld content, and why. Never at what."""
    try:
        return await db[READS].find(
            {"owner_id": owner_id}, {"_id": 0}
        ).sort("read_at", -1).to_list(limit)
    except Exception as e:
        logger.info("content reads soft-fail: %s", type(e).__name__)
        return []


async def forget_all(db, owner_id: str) -> int:
    result = await db[READS].delete_many({"owner_id": owner_id})
    return result.deleted_count
