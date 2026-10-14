"""
L'agenda di una persona: oggi, e i giorni che vengono dopo.

    UN'AGENDA NON È UN RIASSUNTO DELLA SITUAZIONE.

«Vedi agenda» e «Vedi tutto» portavano alla stessa pagina, e una pagina sola
per due domande diverse non risponde bene a nessuna delle due: chi chiede
l'agenda vuole sapere *quando*, chi chiede la sintesi vuole sapere *come sta
andando*.

Gli eventi ORA arrivano dai nodi `event` del Life Graph; quelli Google usano
lo stesso lettore dell'archivio di sincronizzazione della Home. Il mese non
avvia una sincronizzazione e non crea copie per mostrare gli appuntamenti.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List
from zoneinfo import ZoneInfo
from timezone_service import resolve_user_timezone
from home.calendar_read import (
    calendar_source_key, calendar_times_in_window, connected_calendar_instances,
    selected_calendar_source,
)
from home.adapters.google_calendar import google_calendar_attributes, google_calendar_records

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
        zone = ZoneInfo((await resolve_user_timezone(self.db, user_id)).tz_name)
        oggi = datetime.now(zone).date()
        inizio = datetime(oggi.year, oggi.month, oggi.day, tzinfo=zone)
        fine = inizio + timedelta(days=quanti)

        instances = await connected_calendar_instances(self.db, user_id)
        eventi = await self._events_between(user_id, inizio, fine, instances=instances)
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
            "calendar_connected": bool(await self._connected_sources(user_id, instances)),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def month_view(self, user_id: str, *, month: str) -> Dict[str, Any]:
        """The ORA-owned calendar, with optional linked sources in the same month.

        There is no dependency on Google, Apple or any connector to see dates
        or create events. This is a read-only projection of existing nodes;
        connected sources never become the owner of local appointments.
        """
        if len(month) != 7:
            raise ValueError("invalid_month")
        try:
            parsed = datetime.strptime(month, "%Y-%m")
        except ValueError as exc:
            raise ValueError("invalid_month") from exc
        if parsed.strftime("%Y-%m") != month:
            raise ValueError("invalid_month")
        zone = ZoneInfo((await resolve_user_timezone(self.db, user_id)).tz_name)
        first = datetime(parsed.year, parsed.month, 1, tzinfo=zone)
        next_month = datetime(
            parsed.year + int(parsed.month == 12), parsed.month % 12 + 1, 1,
            tzinfo=zone,
        )
        today = datetime.now(zone).date()
        instances = await connected_calendar_instances(self.db, user_id)
        events = await self._events_between(
            user_id, first, next_month, with_notes=False, instances=instances,
        )
        # Old connector mirrors must not appear as an active subscription
        # after the person disconnects the provider. ORA entries are always
        # available, regardless of OAuth/device permissions.
        connected = await self._connected_sources(user_id, instances)
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        sources = {"ora": 0, "google": 0, "apple": 0, "other": 0}
        for item in events:
            key = str(item.get("starts_at") or "")[:10]
            if key:
                grouped.setdefault(key, []).append(item)
                source = item.get("source_type") or "other"
                sources[source] = sources.get(source, 0) + 1
        days = []
        cursor = first.date()
        while cursor < next_month.date():
            key = cursor.isoformat()
            days.append({
                "date": key,
                "label": _come_si_chiama_il_giorno(cursor, today),
                "is_today": cursor == today,
                "events": sorted(
                    grouped.get(key, []),
                    key=lambda item: str(item.get("starts_at") or ""),
                ),
            })
            cursor += timedelta(days=1)
        return {
            "month": month,
            "timezone": str(zone),
            "days": days,
            "total_events": len(events),
            "source_counts": sources,
            "calendar_connected": bool(connected),
            "connected_sources": sorted(connected),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _connected_sources(self, user_id: str, rows=None) -> set[str]:
        if rows is None:
            rows = await connected_calendar_instances(self.db, user_id)
        sources: set[str] = set()
        for row in rows:
            connector = str(row.get("connector_id") or "").lower()
            if "calendar" not in connector:
                continue
            if "google" in connector:
                sources.add("google")
            elif "apple" in connector:
                sources.add("apple")
            else:
                sources.add("other")
        return sources

    async def _events_between(
        self, user_id: str, inizio: datetime, fine: datetime, *,
        with_notes: bool = True,
        instances=None,
    ) -> List[Dict[str, Any]]:
        """
        Gli eventi ORA e le fonti collegate, letti per l'intero periodo.

        La cache Google usa il lettore della Home; i nodi proiettati restano
        un ripiego soltanto quando non esiste già la corrispondente evidenza.
        """
        query = {
            "user_id": user_id,
            "type": "event",
            "status": "active",
            "attributes.starts_at": {
                "$gte": (inizio - timedelta(days=1)).date().isoformat(),
                "$lt": (fine + timedelta(days=1)).date().isoformat(),
            },
        }
        docs = await self.db.life_nodes.find(
            query, {"_id": 0, "id": 1, "label": 1, "attributes": 1},
        ).sort("attributes.starts_at", 1).to_list(length=2000)
        if instances is None:
            instances = await connected_calendar_instances(self.db, user_id)
        records = await google_calendar_records(
            self.db, user_id, inizio, fine, instances=instances,
            external_ids=list({
                str((node.get("attributes") or {}).get("external_event_id"))
                for node in docs if (node.get("attributes") or {}).get("external_event_id")
                and (node.get("attributes") or {}).get("connector_id") == "calendar_google"
            }),
        )
        represented = [calendar_source_key(google_calendar_attributes(row)) for row in records]
        native_or_unmirrored = []
        for node in docs:
            attrs = node.get("attributes") or {}
            if not selected_calendar_source(attrs, instances):
                continue
            key = calendar_source_key(attrs)
            if key[0] == "calendar_google" and key[3] and any(
                candidate[0] == key[0] and candidate[3] == key[3]
                and (not key[1] or candidate[1] == key[1])
                and (not key[2] or candidate[2] == key[2])
                for candidate in represented
            ):
                # Provider evidence is newer than its graph projection. This
                # also hides a stale node when the event moved or was cancelled.
                continue
            native_or_unmirrored.append(node)
        docs = native_or_unmirrored + [{
            "id": row.get("id"),
            "label": plain_attrs.get("title") or plain_attrs.get("summary"),
            "attributes": plain_attrs,
        } for row in records if (plain_attrs := google_calendar_attributes(row))
           and str(plain_attrs.get("status") or "").lower() != "cancelled"
           and row.get("source_status") != "detached"]

        fuori: List[Dict[str, Any]] = []
        for d in docs:
            attrs = calendar_times_in_window(d.get("attributes") or {}, inizio, fine)
            if attrs is None:
                continue
            fuori.append({
                "id": d.get("id"),
                "title": d.get("label") or "Appuntamento",
                "starts_at": attrs.get("starts_at"),
                "ends_at": attrs.get("ends_at"),
                "end_time_known": attrs.get("end_time_known", True) is not False,
                "all_day": bool(attrs.get("all_day")),
                "location": attrs.get("location") or "",
                "time_label": _che_ora(attrs),
                #     DA DOVE ARRIVA QUESTO APPUNTAMENTO.
                # «L'ho aggiunto io da un documento» e «ce l'avevi già nel
                # calendario» sono due cose diverse, e chi legge ha diritto di
                # sapere quale sta guardando.
                "source_label": _da_dove(attrs),
                "source_type": _source_type(attrs),
                "ora_note": (
                    await self._what_ora_has_to_do_with_it(user_id, d.get("id"))
                    if with_notes else ""
                ),
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
        return bool(await self._connected_sources(user_id))


def _che_ora(attrs: Dict[str, Any]) -> str:
    """«09:30 — 10:15», «09:30», «Tutto il giorno». Niente ISO in faccia."""
    if attrs.get("all_day"):
        return "Tutto il giorno"
    inizio = _ora_di(attrs.get("starts_at"))
    # A technical fallback end exists so calendar geometry remains valid, but
    # it must never be rendered as if a source actually stated it.
    if attrs.get("end_time_known", True) is False:
        return inizio or ""
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


def _source_type(attrs: Dict[str, Any]) -> str:
    if attrs.get("kind") == "home_manual":
        return "ora"
    connector = str(attrs.get("connector_id") or "").lower()
    if "google" in connector:
        return "google"
    if "apple" in connector:
        return "apple"
    if connector:
        return "other"
    # No external connector: an event managed within ORA's own Life Graph.
    return "ora"


def _da_dove(attrs: Dict[str, Any]) -> str:
    source = _source_type(attrs)
    return {
        "ora": "Calendario ORA",
        "google": "Google Calendar",
        "apple": "Calendario Apple",
    }.get(source, str(attrs.get("connector_id") or "Altro calendario"))
