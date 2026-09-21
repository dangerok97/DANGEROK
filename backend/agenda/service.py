"""
L'agenda di una persona: oggi, e i giorni che vengono dopo.

    UN'AGENDA NON È UN RIASSUNTO DELLA SITUAZIONE.

«Vedi agenda» e «Vedi tutto» portavano alla stessa pagina, e una pagina sola
per due domande diverse non risponde bene a nessuna delle due: chi chiede
l'agenda vuole sapere *quando*, chi chiede la sintesi vuole sapere *come sta
andando*.

Gli eventi arrivano da dove arrivano già per il riepilogo della giornata — i
nodi `event` del Life Graph — quindi non c'è una seconda verità sul calendario
e non c'è niente di finto: se un giorno è vuoto, è vuoto.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

logger = logging.getLogger("ora.agenda")

MAX_DAYS = 14
DEFAULT_DAYS = 7

_GIORNI = (
    "lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica",
)
_MESI = (
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
)


def _come_si_chiama_il_giorno(quando: date, oggi: date) -> str:
    """«Oggi», «Domani», o «giovedì 24 settembre». Mai una data nuda."""
    if quando == oggi:
        return "Oggi"
    if quando == oggi + timedelta(days=1):
        return "Domani"
    return f"{_GIORNI[quando.weekday()]} {quando.day} {_MESI[quando.month - 1]}"


class AgendaService:
    def __init__(self, db):
        self.db = db

    async def days_ahead(self, user_id: str, *, days: int = DEFAULT_DAYS) -> Dict[str, Any]:
        """
        I prossimi giorni, ognuno con i suoi impegni.

        Torna anche i giorni vuoti: un'agenda che salta i giorni senza niente
        fa sembrare pieno un calendario che è libero, ed è proprio
        l'informazione che serve a chi la guarda.
        """
        quanti = max(1, min(int(days or DEFAULT_DAYS), MAX_DAYS))
        oggi = datetime.now(timezone.utc).date()
        inizio = datetime(oggi.year, oggi.month, oggi.day, tzinfo=timezone.utc)
        fine = inizio + timedelta(days=quanti)

        eventi = await self._events_between(user_id, inizio, fine)
        per_giorno: Dict[str, List[Dict[str, Any]]] = {}
        for e in eventi:
            chiave = str(e.get("starts_at") or "")[:10]
            if chiave:
                per_giorno.setdefault(chiave, []).append(e)

        giorni: List[Dict[str, Any]] = []
        for i in range(quanti):
            quando = oggi + timedelta(days=i)
            chiave = quando.isoformat()
            giorni.append({
                "date": chiave,
                "label": _come_si_chiama_il_giorno(quando, oggi),
                "is_today": quando == oggi,
                "events": sorted(
                    per_giorno.get(chiave, []),
                    key=lambda x: str(x.get("starts_at") or ""),
                ),
            })

        return {
            "days": giorni,
            "total_events": len(eventi),
            "calendar_connected": await self._a_calendar_is_connected(user_id),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _events_between(
        self, user_id: str, inizio: datetime, fine: datetime,
    ) -> List[Dict[str, Any]]:
        """
        Gli eventi del periodo, dagli stessi nodi che legge il riepilogo.

        Una sola interrogazione per tutto l'arco invece di una al giorno: sono
        gli stessi dati, e chiederli sette volte non li rende più veri.
        """
        query = {
            "user_id": user_id,
            "type": "event",
            "status": "active",
            "attributes.starts_at": {
                "$gte": inizio.isoformat(),
                "$lt": fine.isoformat(),
            },
        }
        try:
            docs = await self.db.life_nodes.find(
                query, {"_id": 0, "id": 1, "label": 1, "attributes": 1},
            ).sort("attributes.starts_at", 1).to_list(length=500)
        except Exception as e:  # pragma: no cover
            logger.info("agenda senza eventi: %s", type(e).__name__)
            return []

        fuori: List[Dict[str, Any]] = []
        for d in docs:
            attrs = d.get("attributes") or {}
            fuori.append({
                "id": d.get("id"),
                "title": d.get("label") or "Appuntamento",
                "starts_at": attrs.get("starts_at"),
                "ends_at": attrs.get("ends_at"),
                "all_day": bool(attrs.get("all_day")),
                "location": attrs.get("location") or "",
                "time_label": _che_ora(attrs),
                #     DA DOVE ARRIVA QUESTO APPUNTAMENTO.
                # «L'ho aggiunto io da un documento» e «ce l'avevi già nel
                # calendario» sono due cose diverse, e chi legge ha diritto di
                # sapere quale sta guardando.
                "source_label": _da_dove(attrs),
                "ora_note": await self._what_ora_has_to_do_with_it(user_id, d.get("id")),
            })
        return fuori

    async def _what_ora_has_to_do_with_it(self, user_id: str, event_id: str) -> str:
        """
        Che cosa c'entra ORA con questo appuntamento. Vuoto quando non c'entra.

        Non è una supposizione: si guarda se esiste una bozza di evento che ORA
        ha creato, o una telefonata legata a questo appuntamento.
        """
        if not event_id:
            return ""
        try:
            bozza = await self.db.calendar_event_drafts.find_one(
                {"id": event_id, "user_id": user_id}, {"_id": 0, "source_document_id": 1},
            )
            if bozza:
                return (
                    "L'ho aggiunto io da un documento che mi hai dato."
                    if bozza.get("source_document_id")
                    else "L'ho aggiunto io per te."
                )
            chiamata = await self.db.phone_calls.find_one(
                {"owner_id": user_id, "calendar_event_id": event_id},
                {"_id": 0, "state": 1},
            )
            if chiamata:
                return (
                    "C'è una telefonata legata a questo appuntamento."
                    if str(chiamata.get("state")) not in ("ended", "failed", "expired")
                    else "Ho già telefonato per questo appuntamento."
                )
        except Exception as e:  # pragma: no cover
            logger.info("agenda senza nota ORA: %s", type(e).__name__)
        return ""

    async def _a_calendar_is_connected(self, user_id: str) -> bool:
        try:
            n = await self.db.connector_instances.count_documents({
                "user_id": user_id,
                "connector_id": {"$in": ["calendar_google", "calendar_apple"]},
                "status": {"$in": ["connected", "syncing"]},
            })
            return n > 0
        except Exception:  # pragma: no cover
            return False


def _che_ora(attrs: Dict[str, Any]) -> str:
    """«09:30 — 10:15», «09:30», «Tutto il giorno». Niente ISO in faccia."""
    if attrs.get("all_day"):
        return "Tutto il giorno"
    inizio = _ora_di(attrs.get("starts_at"))
    fine = _ora_di(attrs.get("ends_at"))
    if inizio and fine and fine != inizio:
        return f"{inizio} — {fine}"
    return inizio or ""


def _ora_di(quando: Any) -> str:
    try:
        t = datetime.fromisoformat(str(quando).replace("Z", "+00:00"))
        return t.strftime("%H:%M")
    except Exception:
        return ""


def _da_dove(attrs: Dict[str, Any]) -> str:
    connettore = str(attrs.get("connector_id") or "")
    if "google" in connettore:
        return "Google Calendar"
    if "apple" in connettore:
        return "Calendario di Apple"
    if connettore:
        return connettore
    return "Aggiunto qui"
