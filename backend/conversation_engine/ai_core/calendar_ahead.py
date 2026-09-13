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
                "all_day", "location", "source",
            )
            if e.get(k) not in (None, "")
        })
        if len(uno_per_uno) >= MAX_EVENTS:
            break
    return uno_per_uno


async def the_next_two_days(db, user_id: str) -> Optional[Dict[str, Any]]:
    """
    Gli impegni delle prossime quarantotto ore, o `None`.

    `None` quando non c'è niente da dire — nessun evento, o la lettura non è
    riuscita. Un blocco vuoto nel payload sarebbe peggio che assente: somiglia
    a «non hai impegni», che è una cosa che qui nessuno sa.
    """
    if db is None or not user_id:
        return None

    now = datetime.now(timezone.utc)
    until = now + timedelta(hours=HOURS_AHEAD)

    try:
        from conversation_engine.ai_core.tools.calendar_caps import (
            get_calendar_events,
        )

        seen = await get_calendar_events(
            {"time_min": now.isoformat(), "time_max": until.isoformat()},
            {"db": db, "user_id": user_id},
        )
    except Exception as e:
        # Guardare avanti è un vantaggio, non un requisito: se non riesce, la
        # domanda costerà il giro in più che costava prima.
        logger.info("agenda non precaricata: %s", type(e).__name__)
        return None

    if getattr(seen, "kind", "") == "error":
        return None

    payload = getattr(seen, "payload", None) or {}
    events = payload.get("items") or payload.get("events") or []
    if not isinstance(events, list) or not events:
        return None

    return {
        "window": {"from": now.isoformat(), "to": until.isoformat()},
        "events": _one_each(events),
        # Il blocco dice di sé stesso dove finisce. Senza questa riga, la
        # prima domanda su un periodo diverso riceverebbe un «no» ricavato
        # dall'assenza — che è esattamente l'errore che questo prodotto
        # passa il tempo a non fare.
        "this_is_only_the_next_48_hours": (
            "Already retrieved, no tool call needed for this window. "
            "For any other period — later this week, next week, a specific "
            "date outside it — call get_calendar_events. An event missing "
            "from here means only that it is not in the next 48 hours."
        ),
    }
