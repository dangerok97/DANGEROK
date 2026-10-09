"""Human source descriptions for existing monetary facts.

Only owner-scoped ingestion metadata: never persist, return or log email bodies.
The source label is provenance, not a claim that the model identified a charge.
"""
from __future__ import annotations

from typing import Dict, Iterable

from financial.models import FinancialFact
from ingestion.reading import plain


def _subject(raw: object) -> str:
    return " ".join(str(raw or "").split())[:140]


async def email_source_labels(db, owner_id: str, facts: Iterable[FinancialFact]) -> Dict[str, str]:
    rows = list(facts)
    refs: Dict[str, str] = {}
    for fact in rows:
        if not fact.provenance or fact.provenance[0].source != "email":
            continue
        ref = str(fact.provenance[0].source_ref or "").strip()
        if ref.startswith("mail:"):
            ref = ref.split(":", 1)[1]
        if ref:
            refs[fact.id] = ref
    if not refs:
        return {}
    sources = await db.ingestion_events.find(
        {"user_id": owner_id, "source_record_type": "email_message",
         "external_id": {"$in": list(set(refs.values()))[:80]},
         "ingestion_status": {"$ne": "superseded"}},
        {"_id": 0, "external_id": 1, "normalized_payload": 1, "ingested_at": 1},
    ).sort("ingested_at", -1).to_list(100)
    by_ref: Dict[str, str] = {}
    for row in sources:
        ref = str(row.get("external_id") or "")
        if ref in by_ref:
            continue  # newest non-superseded reading wins
        payload = plain(row.get("normalized_payload"))
        subject = _subject(payload.get("subject"))
        if subject:
            by_ref[ref] = f"Email «{subject}»"
    return {fact_id: by_ref[ref] for fact_id, ref in refs.items() if ref in by_ref}


def exact_named_zone_timestamp(source_content: dict | None) -> str | None:
    """Resolve one explicit provider timestamp with an IANA timezone.

    This handles source text such as '2026-10-11 03:25:28 America/Los_Angeles'
    without treating 'in two days' as more authoritative than the written
    calendar date. If more than one timestamp is present, no choice is made.
    It does not decide whether a timestamp denotes a bill, receipt or renewal:
    that remains the financial judgement's responsibility.
    """
    import re
    from datetime import datetime
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    text = str((source_content or {}).get("body") or "")
    matches = re.findall(
        r"(?<!\\d)(\\d{4}-\\d{2}-\\d{2})[ T]"
        r"(\\d{2}:\\d{2}:\\d{2})\\s+"
        r"([A-Za-z][A-Za-z_]+/[A-Za-z_]+(?:/[A-Za-z_]+)?)",
        text,
    )
    if len(set(matches)) != 1:
        return None
    day, clock, zone = matches[0]
    try:
        at = datetime.fromisoformat(f"{day}T{clock}").replace(tzinfo=ZoneInfo(zone))
        if at.astimezone(ZoneInfo("UTC")).astimezone(ZoneInfo(zone)).replace(
            tzinfo=None
        ) != at.replace(tzinfo=None):
            return None
        return at.isoformat()
    except (ValueError, ZoneInfoNotFoundError):
        return None
