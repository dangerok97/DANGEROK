"""Bounded, explicitly requested correction of old email-derived finance facts.

No email body is persisted. A source-read audit contains only owner, message
handle, fields and reason. Every read resolves the user's own Gmail instance.
"""
from __future__ import annotations

from types import SimpleNamespace
from financial.bridge import read_money_in
from financial.models import Provenance


async def review_email_financial_sources(db, owner_id: str, *, limit: int = 5) -> dict:
    inspected = read_ok = updated = unchanged = unconfirmed = unavailable = already_reviewed = 0
    seen: set[str] = set()
    max_count = max(1, min(int(limit), 5))
    candidates = await db.financial_facts.find(
        {"owner_id": owner_id, "status": {"$in": ["known", "disputed"]},
         "provenance.source": "email"},
        {"_id": 0, "provenance": 1, "created_at": 1},
    ).sort("created_at", -1).limit(30).to_list(30)

    for row in candidates:
        source = next((
            p for p in row.get("provenance") or []
            if isinstance(p, dict) and p.get("source") == "email"
            and p.get("source_ref")
        ), None)
        if not source:
            continue
        message_ref = str(source["source_ref"]).strip().removeprefix("mail:")
        if not message_ref or message_ref in seen:
            continue
        seen.add(message_ref)
        if inspected >= max_count:
            break
        # A previous successful source read is not re-triggered by repeated
        # taps. A failed one is retriable after reconnection.
        already = await db.financial_source_reviews.find_one(
            {"owner_id": owner_id, "message_ref": message_ref,
             "status": "completed"}, {"_id": 0, "message_ref": 1}
        )
        if already:
            already_reviewed += 1
            continue
        inspected += 1
        email = await db.ingestion_events.find_one(
            {"user_id": owner_id, "external_id": message_ref,
             "source_record_type": "email_message",
             "ingestion_status": {"$ne": "superseded"}},
            {"_id": 0, "connector_instance_id": 1, "normalized_payload": 1},
            sort=[("ingested_at", -1)],
        )
        if not email or not email.get("connector_instance_id"):
            unavailable += 1
            continue
        signal = SimpleNamespace(
            id=f"financial_source_review:{message_ref}",
            source_type="email",
            source_id=str(email["connector_instance_id"]),
            source_object_ref=message_ref,
        )
        from connected.content import _from_email, _note_the_read
        exact = await _from_email(db, owner_id, signal, ["body"])
        body = str(exact.get("body") or "").strip()
        if not body:
            unavailable += 1
            continue
        read_ok += 1
        await _note_the_read(
            db, owner_id, signal, fields=["body"],
            why="Rilettura richiesta per verificare servizio, importo e data.",
        )
        from ingestion.reading import plain
        payload = plain(email.get("normalized_payload")) or {}
        subject = str(payload.get("subject") or "").strip()[:200]
        outcome = await read_money_in(
            db, owner_id,
            observation={
                "source_type": "email", "source_ref": f"mail:{message_ref}",
                "in_words": subject, "private_source_excerpt": body[:400],
                "read_reason": "explicit_financial_source_review",
            },
            provenance=Provenance(
                source="email", source_ref=message_ref,
                how_directly=f"Email originale: {subject}"[:200],
            ),
            source_refs=[f"mail:{message_ref}"],
        )
        result = str(outcome.get("outcome") or "")
        if result in ("kept", "superseded", "already_known", "disputed"):
            # Read succeeded, but the financial model may have learned
            # nothing new. Distinguish that from an actual correction.
            if result == "already_known":
                unchanged += 1
            else:
                updated += 1
            await db.financial_source_reviews.update_one(
                {"owner_id": owner_id, "message_ref": message_ref},
                {"$set": {
                    "owner_id": owner_id, "message_ref": message_ref,
                    "status": "completed",
                }},
                upsert=True,
            )
        elif result == "nothing":
            # The source was read, but the previous economic classification
            # was not confirmed. Preserve the original record; do not claim
            # the information was updated or quietly delete financial data.
            unconfirmed += 1
        else:
            unavailable += 1

    if updated:
        message = (
            f"Ho verificato {read_ok} email e aggiornato {updated} informazioni "
            "economiche. Gli importi non presenti nelle fonti restano sconosciuti."
        )
        if unchanged:
            message += f" {unchanged} erano già corrette."
        if unconfirmed:
            message += f" Per {unconfirmed} non è stato confermato un fatto economico."
    elif read_ok:
        message = (
            f"Ho riletto {read_ok} email, ma non ho nuovi importi o scadenze "
            "confermati da aggiungere."
        )
        if unconfirmed:
            message += (
                f" In {unconfirmed} casi la fonte non ha confermato "
                "il precedente significato economico."
            )
    elif already_reviewed and not inspected:
        message = (
            f"Le {already_reviewed} email economiche disponibili erano già "
            "state verificate. Non è necessario ripetere la lettura."
        )
    elif not inspected:
        message = (
            "Non risultano email economiche precedentemente riconosciute da "
            "rileggere. Questo non dimostra che la casella sia vuota."
        )
    else:
        message = (
            "Non ho potuto rileggere le email selezionate. "
            "Controlla il collegamento Gmail o riprova."
        )
    if unavailable and read_ok:
        message += f" {unavailable} verifiche non sono riuscite."

    return {
        "checked": inspected, "read_successfully": read_ok,
        "updated": updated, "unchanged": unchanged,
        "unconfirmed": unconfirmed, "already_reviewed": already_reviewed,
        "not_available": unavailable, "message": message,
    }
