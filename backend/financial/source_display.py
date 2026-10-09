"""Show the exact owner-owned email subject behind a financial fact.

Only normalized ingestion metadata is read. No message body, token, recipient,
or source-email address is retrieved or exposed.
"""
from __future__ import annotations

from typing import Dict, Iterable

from ingestion.reading import plain


def _mail_ref(fact) -> str:
    # Financial observations retain the provider message handle in provenance;
    # governed Life Model facts may retain it only in evidence_refs/source_refs.
    for source in getattr(fact, "provenance", []) or []:
        if getattr(source, "source", "") == "email":
            ref = str(getattr(source, "source_ref", "") or "").strip()
            if ref:
                return ref.removeprefix("mail:")
    for ref in getattr(fact, "source_refs", []) or []:
        if str(ref).startswith("mail:"):
            return str(ref).removeprefix("mail:")
    return ""


async def email_labels_for_facts(db, owner_id: str, facts: Iterable) -> Dict[str, str]:
    refs = {
        str(fact.id): _mail_ref(fact)
        for fact in facts
        if getattr(fact, "id", "") and _mail_ref(fact)
    }
    if not refs:
        return {}
    # All source lookups require owner identity, never just a Gmail message id.
    messages = await db.ingestion_events.find(
        {
            "user_id": owner_id, "source_record_type": "email_message",
            "external_id": {"$in": list(dict.fromkeys(refs.values()))[:80]},
            "ingestion_status": {"$ne": "superseded"},
        },
        {"_id": 0, "external_id": 1, "normalized_payload": 1, "ingested_at": 1},
    ).sort("ingested_at", -1).to_list(100)
    by_ref: Dict[str, str] = {}
    for row in messages:
        ref = str(row.get("external_id") or "")
        if ref in by_ref:
            continue
        data = plain(row.get("normalized_payload"))
        subject = " ".join(str(data.get("subject") or "").split())[:160]
        if subject:
            by_ref[ref] = f"Email «{subject}»"
    return {fid: by_ref[ref] for fid, ref in refs.items() if ref in by_ref}
