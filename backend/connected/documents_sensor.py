"""
The shelf, read as a change.

    A NEW DOCUMENT IS NOT A NEW PROJECT.
    A REPLACED DOCUMENT IS NOT A SECOND ARRIVAL.

Second sensor, and deliberately the dullest one available: ORA's own document
archive, which already exists, already belongs to the person, and needs no
new connection. The point of a second sensor is to prove the pipeline is not
calendar-shaped — that a different kind of world event enters the same door,
dedupes the same way and is judged by the same layer.

The archive rewrites in place, so unlike the calendar it has no past of its
own: the filename becomes the new filename and the old one is gone. That is
what `SeenState` is for, and it is why a document that is renamed produces
`document.updated` rather than a second `document.added` — the difference
matters because one of those is news and the other is a system that cannot
tell it has met this file before.

What this sensor still does not claim is what the extraction found. "The
facts in this document changed" is known to the documents pipeline and not to
this one; what is observable here is the record — its name, its labels,
whether the file itself is a different file, whether it was put away. Saying
more would be inventing a certainty, and the debt stays declared.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from connected.models import ConnectedSignal, SignalType, now_iso
from connected.seen import SeenState

logger = logging.getLogger("ora.connected.documents")

MAX_ROWS = 40

# What a person could notice about a document of theirs. `content` is the
# file's own hash: whether this is still the same file, which is observable
# without the file ever being read.
_OBSERVABLE = ("title", "tags", "notes", "content", "archived", "deleted")

# Their private annotation, and the file's identity. Compared by digest, so
# "it changed" is answerable and what it changed to is never written down.
_WITHHELD = ("notes", "content")


async def read_changes(
    db, owner_id: str, *, since: Optional[str] = None,
) -> List[ConnectedSignal]:
    """
    What has happened on the shelf since we last looked.

    Three things can happen to a document and all three are observable from
    the record: it arrives, it changes, it is put away. Which of them this is
    comes from whether we have seen the object before — not from a timestamp
    comparison, because a clock tells you when a row was written and not
    whether you already knew about it.
    """
    query: Dict[str, Any] = {"user_id": owner_id}
    if since:
        # Anything touched since the watermark, however it was touched.
        query["updated_at"] = {"$gt": since}

    try:
        rows = await db.documents.find(
            query,
            {"_id": 0, "id": 1, "title": 1, "filename": 1, "created_at": 1,
             "updated_at": 1, "document_type": 1, "tags": 1, "notes": 1,
             "hash": 1, "archived": 1, "deleted": 1},
        ).sort("updated_at", 1).to_list(MAX_ROWS)
    except Exception as e:
        logger.info("documents read soft-fail: %s", type(e).__name__)
        return []

    seen = SeenState(db)
    signals: List[ConnectedSignal] = []
    for row in rows:
        signal = await _signal_for(seen, owner_id, row)
        if signal is not None:
            signals.append(signal)
    return signals


async def _signal_for(seen: SeenState, owner_id: str, row: Dict[str, Any]):
    doc_id = str(row.get("id") or "")
    if not doc_id:
        return None

    name = str(row.get("title") or row.get("filename") or "un documento")[:80]
    readings = {
        "title": name,
        "tags": ", ".join(str(t) for t in (row.get("tags") or []))[:160],
        "notes": str(row.get("notes") or ""),
        "content": str(row.get("hash") or ""),
        "archived": "si" if row.get("archived") else "no",
        "deleted": "si" if row.get("deleted") else "no",
    }
    # Read through the declared list rather than beside it. Written this way
    # so that `_OBSERVABLE` is the thing that decides what is noticed: a
    # constant nothing consults is a comment that looks like code, and the
    # day somebody edits it expecting an effect is the day a whole kind of
    # change stops being seen.
    observable = {field: readings[field] for field in _OBSERVABLE}
    known, changes = await seen.compare(
        owner_id, "documents", doc_id,
        observable=observable, withheld=_WITHHELD,
    )
    await seen.remember(
        owner_id, "documents", doc_id,
        observable=observable, withheld=_WITHHELD,
    )

    gone = bool(row.get("deleted") or row.get("archived"))
    if not known:
        if gone:
            # Put away before we ever noticed it. Telling somebody about a
            # document that is already filed is noise by construction, and
            # the memory now knows about it either way.
            return None
        kind: SignalType = "document.added"
        summary = f"È arrivato un documento: «{name}»."
    elif gone and any(c.field in ("archived", "deleted") for c in changes):
        kind = "document.removed"
        summary = f"«{name}» è stato messo via."
    elif changes:
        kind = "document.updated"
        summary = _in_words(name, changes)
    else:
        return None

    return ConnectedSignal(
        owner_id=owner_id,
        source_id="documents",
        source_type="documents",
        signal_type=kind,
        observed_at=str(row.get("updated_at") or row.get("created_at") or now_iso()),
        effective_at=str(row.get("updated_at") or row.get("created_at") or "") or None,
        source_object_ref=doc_id,
        # The name and what moved. Never the contents: a document's text stays
        # in the archive that already governs who may read it.
        payload_summary=summary,
        after=name,
        changed_fields=changes,
        origin="external",
        provenance={
            "owner": "documents",
            "document_type": str(row.get("document_type") or "")[:60],
            # A document is the person's own by construction: it is on their
            # shelf because they put it there.
            "relationship": "own",
        },
        relationship="own",
        confidence="certain",
        raw_ref=doc_id[:120],
    )


def _in_words(name: str, changes) -> str:
    """One sentence naming what moved, without ranking it."""
    names = {
        "title": "il nome",
        "tags": "le etichette",
        "notes": "le note",
        "content": "il file",
        "archived": "dov'è",
        "deleted": "dov'è",
    }
    what = []
    for change in changes:
        label = names.get(change.field, change.field)
        if label not in what:
            what.append(label)
    if len(what) == 1:
        return f"Di «{name}» è cambiato {what[0]}."
    return f"Di «{name}» è cambiato: {', '.join(what[:4])}."
