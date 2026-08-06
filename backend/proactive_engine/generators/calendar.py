"""Calendar generator — overlapping events → suggest modify."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from proactive_engine.dedupe import make_dedupe_key, window_label
from proactive_engine.models import SuggestionAction, SuggestionCandidate


def _parse(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _overlap(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> bool:
    return a0 < b1 and b0 < a1


async def _load_events(db, user_id: str, now: datetime) -> List[Dict[str, Any]]:
    end = now + timedelta(days=7)
    events: List[Dict[str, Any]] = []

    # Life graph internal events
    cur = db.life_nodes.find(
        {
            "user_id": user_id,
            "type": "event",
            "status": "active",
            "attributes.starts_at": {
                "$gte": (now - timedelta(hours=1)).isoformat(),
                "$lte": end.isoformat(),
            },
        },
        {"_id": 0},
    ).limit(100)
    for d in await cur.to_list(100):
        attrs = d.get("attributes") or {}
        start = attrs.get("starts_at")
        end_at = attrs.get("ends_at")
        if not start:
            continue
        events.append({
            "id": d.get("id"),
            "title": d.get("label") or "Impegno",
            "starts_at": start,
            "ends_at": end_at,
            "source": "life_node",
        })

    # Google-ingested mirrors (if present as ingestion / calendar events collection)
    try:
        gcur = db.calendar_events.find(
            {
                "user_id": user_id,
                "starts_at": {
                    "$gte": (now - timedelta(hours=1)).isoformat(),
                    "$lte": end.isoformat(),
                },
            },
            {"_id": 0},
        ).limit(100)
        for d in await gcur.to_list(100):
            events.append({
                "id": d.get("id") or d.get("external_id"),
                "title": d.get("title") or d.get("summary") or "Evento",
                "starts_at": d.get("starts_at") or d.get("start"),
                "ends_at": d.get("ends_at") or d.get("end"),
                "source": "calendar_events",
            })
    except Exception:
        pass

    return events


async def generate_calendar_candidates(
    db, user_id: str, *, now: Optional[datetime] = None,
) -> List[SuggestionCandidate]:
    now = now or datetime.now(timezone.utc)
    events = await _load_events(db, user_id, now)
    parsed: List[Tuple[Dict[str, Any], datetime, datetime]] = []
    for ev in events:
        s = _parse(ev.get("starts_at"))
        if not s:
            continue
        e = _parse(ev.get("ends_at")) or (s + timedelta(hours=1))
        if e <= s:
            e = s + timedelta(minutes=30)
        parsed.append((ev, s, e))

    parsed.sort(key=lambda x: x[1])
    out: List[SuggestionCandidate] = []
    win = window_label(now, 12)
    seen_pairs = set()

    for i in range(len(parsed)):
        for j in range(i + 1, len(parsed)):
            a, a0, a1 = parsed[i]
            b, b0, b1 = parsed[j]
            if b0 >= a1:
                break
            if not _overlap(a0, a1, b0, b1):
                continue
            pair_key = tuple(sorted([str(a.get("id")), str(b.get("id"))]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            title = "Due impegni si sovrappongono — modifica uno"
            desc = (
                f"«{a.get('title')}» e «{b.get('title')}» si sovrappongono. "
                "Sposta o accorcia uno dei due per evitare conflitti."
            )
            entity = f"{a.get('id')}|{b.get('id')}"
            out.append(SuggestionCandidate(
                title=title,
                description=desc,
                reason="Sovrapposizione calendario rilevata",
                type="calendar",
                source="calendar",
                calendar_event=str(a.get("id")),
                action=SuggestionAction(
                    kind="modify_event",
                    label="Rivedi impegni",
                    route="/situazione",
                    params={
                        "event_ids": [a.get("id"), b.get("id")],
                        "titles": [a.get("title"), b.get("title")],
                    },
                ),
                dedupe_key=make_dedupe_key(
                    suggestion_type="calendar",
                    source="calendar",
                    action_kind="modify_event",
                    entity_id=entity,
                    window=win,
                ),
                expires_at=min(a1, b1).isoformat(),
                importance_hint=0.8,
                urgency_hint=0.85 if a0 <= now + timedelta(hours=24) else 0.65,
                confidence=0.9,
                evidence={
                    "event_a": a,
                    "event_b": b,
                    "deadline": a0.isoformat(),
                },
            ))
            if len(out) >= 3:
                return out
    return out
