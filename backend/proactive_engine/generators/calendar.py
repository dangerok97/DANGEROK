"""Calendar generator — overlapping events → suggest modify."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from proactive_engine.dedupe import make_dedupe_key
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
            "attributes.connector_id": {"$ne": "calendar_google"},
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

    # Use the same current, selected-calendar view as Home. Life graph Google
    # mirrors can lag ingestion (and still contain cancelled appointments).
    from home.adapters.google_calendar import load_google_calendar_events, google_connection_state
    state = await google_connection_state(db, user_id)
    items, _ = await load_google_calendar_events(db, user_id)
    for item in items:
        events.append({
            # This is the same opaque owner-scoped ref emitted by the
            # conversational calendar reader. A prepared suggestion can now
            # continue into the canonical update tool instead of dead-ending
            # with a provider id it is not allowed to use.
            "id": "calendar:google:" + str(
                item.meta.get("ingestion_event_id") or item.source_id
            ),
            "title": item.title, "starts_at": item.start_at, "ends_at": item.end_at,
            "source": "google_calendar", "synced_at": state.get("last_sync_at"),
            "calendar_id": item.meta.get("calendar_id"),
        })

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
        e = _parse(ev.get("ends_at"))
        if not e or e <= s:
            continue
        if e > now:
            parsed.append((ev, s, e))

    parsed.sort(key=lambda x: x[1])
    out: List[SuggestionCandidate] = []
    win = "conflict-v2"
    from timezone_service import resolve_user_timezone
    from zoneinfo import ZoneInfo
    tz = ZoneInfo((await resolve_user_timezone(db, user_id)).tz_name)
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

            options = alternative_slots(parsed, (a, a0, a1), (b, b0, b1), now=now, tz=tz)
            fresh = all(_parse(ev.get("ends_at")) for ev in events) and all(ev.get("source") != "google_calendar" or (
                _parse(ev.get("synced_at")) and now - _parse(ev["synced_at"]) < timedelta(minutes=5)
            ) for ev, _, _ in parsed)
            if not fresh:
                options = []
            preparation = {
                "checked_at": now.isoformat(),
                "summary": "Ho confrontato gli orari degli impegni e cercato alternative della stessa durata.",
                "question": "Quale impegno puoi spostare? Le disponibilità degli altri partecipanti vanno confermate.",
                "options": options,
                "limits": f"Orari indicativi tra le 08 e le 20 ({tz.key}), entro tre giorni, sui calendari letti. Non includono tempi di viaggio o impegni non collegati.",
            }
            if not options:
                preparation["summary"] = ("I dati non sono abbastanza recenti o completi per proporre orari." if not fresh
                    else "Non ho trovato un’alternativa della stessa durata nella finestra esaminata.")
            title = "Due impegni si sovrappongono"
            desc = (
                f"«{a.get('title')}» e «{b.get('title')}» si sovrappongono. "
                f"{len(options)} alternative da valutare pronte." if options else
                f"«{a.get('title')}» e «{b.get('title')}» si sovrappongono. Serve scegliere quale riprogrammare."
            )
            entity = "|".join(pair_key)
            out.append(SuggestionCandidate(
                title=title,
                description=desc,
                reason="Sovrapposizione calendario rilevata",
                type="calendar",
                source="calendar",
                calendar_event=str(a.get("id")),
                action=SuggestionAction(
                    kind="prepare_change",
                    label="Prepara lo spostamento",
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
                meta={"preparation": preparation},
                evidence={
                    "event_a": a,
                    "event_b": b,
                    "deadline": a0.isoformat(),
                },
            ))
            if len(out) >= 3:
                return out
    return out


def alternative_slots(parsed, a, b, *, now, tz):
    """Bounded deterministic preparation; never changes events or claims availability."""
    options = []
    for event, start, end in (a, b):
        duration = end - start
        if duration <= timedelta(0) or duration > timedelta(hours=12):
            continue
        cursor = max(start, now).astimezone(tz).replace(second=0, microsecond=0)
        cursor += timedelta(minutes=15 - cursor.minute % 15)
        stop = min(start.astimezone(tz) + timedelta(days=3), (now + timedelta(days=7)).astimezone(tz))
        while cursor + duration <= stop:
            finish = cursor + duration
            if (cursor.hour >= 8 and finish.date() == cursor.date() and
                (finish.hour < 20 or (finish.hour == 20 and finish.minute == 0)) and
                not any(other["id"] != event["id"] and _overlap(cursor, finish, s, e)
                        for other, s, e in parsed)):
                options.append({"event_id": event["id"], "title": event["title"],
                                "starts_at": cursor.isoformat(), "ends_at": finish.isoformat()})
                break
            cursor += timedelta(minutes=15)
    return options
