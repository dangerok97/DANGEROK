"""A source-backed preparation for two overlapping ORA commitments.

An LLM review cannot certify its own speculative rescheduling options. This
small case can be prepared from the current calendar rows and exact interval
arithmetic, with every proposed new appointment explicitly unconfirmed.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from home.manual_event import get_manual_event, manual_event_public


def is_home_calendar_pair(goal):
    refs = list(dict.fromkeys(goal.source_refs))
    return (goal.source_kind == "opportunity" and bool(goal.opportunity_id)
            and len(refs) == 2 and all(r.startswith("calendar:node_home_") for r in refs))


async def active_home_pair(db, owner_id, refs):
    refs = list(dict.fromkeys(refs))
    if len(refs) != 2 or not all(r.startswith("calendar:node_home_") for r in refs):
        return None
    events = []
    for ref in refs:
        node = await get_manual_event(db, owner_id, ref.removeprefix("calendar:"))
        if not node or node.get("status") != "active":
            return None
        row = manual_event_public(node)
        try:
            start = datetime.fromisoformat(row["starts_at"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(row["ends_at"].replace("Z", "+00:00"))
            zone = ZoneInfo(row["timezone"])
        except (KeyError, TypeError, ValueError):
            return None
        if start.tzinfo is None or end.tzinfo is None or end <= start or end <= datetime.now(timezone.utc):
            return None
        events.append((start, end, zone, row, ref))
    events.sort(key=lambda item: item[0])
    first, second = events
    overlap_start = max(first[0], second[0])
    overlap_end = min(first[1], second[1])
    if overlap_end <= overlap_start:
        return None
    minutes = round((overlap_end - overlap_start).total_seconds() / 60)
    if not minutes:
        return None
    return events, overlap_start, overlap_end, minutes


async def overlap_draft(db, owner_id, goal, evidence):
    refs = list(dict.fromkeys(goal.source_refs))
    if not is_home_calendar_pair(goal):
        return None
    pair = await active_home_pair(db, owner_id, refs)
    if pair is None:
        return None
    events, overlap_start, overlap_end, minutes = pair
    first, second = events
    # The goal must actually have read these sources. A goal merely citing two
    # event IDs is insufficient to mark a prepared deliverable as supported.
    ids = []
    for ref in refs:
        found = next((e.id for e in evidence if e.supports == ref or ref in e.provenance.source_refs), None)
        if not found:
            return None
        ids.append(found)
    date = first[0].astimezone(first[2]).strftime("%d/%m/%Y")
    def period(item):
        start, end, zone, *_ = item
        return f"{start.astimezone(zone):%H:%M}–{end.astimezone(zone):%H:%M}"
    content = (
        f"Il {date} risultano due impegni ORA sovrapposti per {minutes} minuti "
        f"({overlap_start.astimezone(first[2]):%H:%M}–{overlap_end.astimezone(first[2]):%H:%M}):\n"
        f"• {first[3]['title']}: {period(first)}.\n"
        f"• {second[3]['title']}: {period(second)}.\n\n"
        "Prima scelta da verificare: chiedere di spostare il secondo impegno. "
        "Non risulta confermata alcuna disponibilità alternativa; vanno considerati "
        "anche i tempi di spostamento e i requisiti annotati nei due eventi.\n\n"
        "Bozza da inviare al referente del secondo impegno, dopo aver scelto il destinatario:\n"
        f"Oggetto: Richiesta di spostamento dell'appuntamento del {date}\n\n"
        f"Buongiorno, ho un appuntamento fissato per il {date} alle {second[0].astimezone(second[2]):%H:%M}. "
        "Ho un altro impegno sovrapposto e vorrei sapere se possiamo concordare un orario diverso. "
        "Mi può indicare le disponibilità? Le confermerò dopo aver verificato i tempi "
        "necessari e quanto devo portare. Grazie.\n\n"
        "Nessun impegno è stato modificato e nessun messaggio è stato inviato."
    )
    return content, list(dict.fromkeys(ids))
