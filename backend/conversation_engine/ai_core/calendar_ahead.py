"""
Le prossime quarantotto ore, già in mano prima che qualcuno le chieda.

    LA DOMANDA PIÙ FREQUENTE NON DOVREBBE COSTARE UN GIRO IN PIÙ.

Misurato su una telefonata vera: «e che impegni ho domani?» costava **due**
passi di ragionamento invece di uno. Il primo passo non rispondeva niente —
diceva soltanto «chiamate `get_calendar_events`» — e il secondo, con gli
eventi finalmente sotto gli occhi, rispondeva. Duemilacinquecento
millisecondi per andare a prendere una cosa che si sapeva già di dover
prendere.

Qui quelle stesse quarantotto ore arrivano insieme al resto del contesto, e
il primo passo può rispondere subito.

    NESSUN SECONDO CALENDARIO.

Non si rilegge Mongo per conto proprio e non si reimplementa niente: si chiama
lo stesso identico handler dello strumento `get_calendar_events` — stessa
finestra, stesso filtro di consenso su Google, stessa forma degli eventi. Se
un giorno quel controllo cambiasse, cambierebbe anche qui, perché è lo stesso
codice.

    E NON È UN SECONDO PERCORSO COGNITIVO.

Non decide niente, non parla con nessun modello, non scrive da nessuna parte.
Mette dei fatti sul tavolo. Fuori da questa finestra ORA deve ancora chiedere,
e il blocco lo dice di sé stesso — se no la prima settimana in cui qualcuno
chiede «e la settimana prossima?» si sente rispondere di no.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("ora.ai_core.calendar_ahead")

# Quanto avanti si guarda. Due giorni coprono «oggi», «stasera», «domani» e
# «domattina», che sono quasi tutte le domande che si fanno a voce. Più avanti
# si va, più il payload pesa per informazioni che quasi nessuno chiederà.
HOURS_AHEAD = 48

# Oltre questo non ci stanno in un contesto: chi ha ottanta impegni in due
# giorni ha bisogno dello strumento, non di un riassunto.
MAX_EVENTS = 20


def _one_each(events: Any) -> list:
    """
    Lo stesso impegno elencato cinque volte resta un impegno.

        UN DUPLICATO NEL CALENDARIO NON È UN SECONDO APPUNTAMENTO.

    Misurato sul calendario vero di una persona: nove eventi nelle prossime
    quarantotto ore, **due** distinti — il resto erano copie lasciate da
    sincronizzazioni diverse. Passarle tutte al modello vuol dire sentirsi
    dire che domani si hanno cinque impegni, e sarebbe vero solo del
    database.

    Due eventi sono lo stesso quando hanno lo stesso titolo e cominciano
    nello stesso momento. Si tiene il primo, con il suo riferimento.
    """
    visti = set()
    uno_per_uno = []
    for e in events:
        if not isinstance(e, dict):
            continue
        chi = (
            str(e.get("title") or "").strip().lower(),
            str(e.get("start_datetime") or ""),
        )
        if chi in visti:
            continue
        visti.add(chi)
        uno_per_uno.append({
            k: e.get(k)
            for k in (
                "calendar_ref", "title", "start_datetime", "end_datetime",
                "all_day", "location", "source", "description", "timezone", "day_label",
            )
            if e.get(k) not in (None, "")
        })
        if len(uno_per_uno) >= MAX_EVENTS:
            break
    return uno_per_uno


def _coverage(now: datetime, until: datetime) -> Dict[str, Any]:
    """Bounded CURRENT observation, never a claim about the whole calendar.

    A failed read and a successfully observed empty 48-hour window have
    different meanings. Neither turns chat history into current evidence.
    """
    return {
        "window": {"from": now.isoformat(), "to": until.isoformat()},
        "events": [],
        "status": "unavailable",
        "observed_at": None,
        "source_capability": "get_calendar_events",
        "historical_conversation_is_current_evidence": False,
        "this_is_only_the_next_48_hours": (
            "Only events actually listed here were observed in this turn. "
            "This 48-hour window is NOT the whole calendar. For a named "
            "appointment not listed or a date outside it, call "
            "get_calendar_events for the appropriate interval. "
            "An earlier chat message or previously successful mutation "
            "is HISTORICAL, not proof of the current event time or absence. "
            "Never change an event merely to make a calendar read succeed."
        ),
    }


async def the_next_two_days(db, user_id: str) -> Optional[Dict[str, Any]]:
    """Use the existing governed reader and preserve observation coverage.

    None means missing user/database. With an authenticated owner, an
    unavailable reader must not masquerade as an observed empty calendar.
    This is read-only and adds no scheduling or model decision.
    """
    if db is None or not user_id:
        return None

    now = datetime.now(timezone.utc)
    until = now + timedelta(hours=HOURS_AHEAD)
    snapshot = _coverage(now, until)
    try:
        from conversation_engine.ai_core.tools.calendar_caps import (
            get_calendar_events,
        )
        seen = await get_calendar_events(
            {"time_min": now.isoformat(), "time_max": until.isoformat()},
            {"db": db, "user_id": user_id},
        )
    except Exception as exc:
        logger.info("agenda non precaricata: %s", type(exc).__name__)
        snapshot["reason"] = (
            "Calendar read unavailable; do not answer from an earlier "
            "conversation as though it were verified now."
        )
        return snapshot

    payload = getattr(seen, "payload", None)
    if (
        getattr(seen, "status", None) != "ok"
        or not isinstance(payload, dict)
        or payload.get("status") not in (None, "ok", "success")
    ):
        snapshot["reason"] = (
            "The calendar reader did not confirm a successful current observation."
        )
        return snapshot

    events = (
        payload.get("items")
        if isinstance(payload.get("items"), list)
        else payload.get("events")
    )
    if not isinstance(events, list):
        snapshot["reason"] = "The calendar response has no valid event list."
        return snapshot

    projected = _one_each(events)
    snapshot.update(
        events=projected,
        status="observed_events" if projected else "observed_empty_window",
        observed_at=datetime.now(timezone.utc).isoformat(),
        may_be_truncated=bool(payload.get("truncated")) or len(events) >= MAX_EVENTS,
    )
    return snapshot
