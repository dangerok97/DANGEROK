"""
Un appuntamento, guardato da vicino — e tolto di mezzo, se la persona lo chiede.

    UN EVENTO DEL CALENDARIO NON E' UNA COSA DA ORGANIZZARE. E' UNA COSA CHE
    HAI.

Toccare una visita dal dentista apriva un flusso generico dell'action engine
che chiedeva «vuoi preparare un esame oppure creare un evento?». La risposta
giusta a quel tocco non e' una domanda: e' l'appuntamento stesso, con quello
che una persona vuole sapere e le due cose che puo' farci — spostarlo o
toglierlo.

Due funzioni, e la differenza fra loro e' tutto quello che conta qui.

**Leggere** e' una domanda al proprio archivio: cosa dice la riga che il sync
ha scritto. Nessun id tecnico esce da qui, nessuna capability, nessun JSON di
servizio: quello che torna e' fatto di frasi.

**Cancellare** e' un effetto sul mondo di qualcun altro, e quindi passa dove
passano gli effetti: un'autorita' legata a *quell'* evento, la cancellazione
sul provider, e una rilettura che verifica. Solo dopo la rilettura si puo'
dire «eliminato» — e se la rilettura non conferma, non lo si dice.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ingestion.reading import plain, where

logger = logging.getLogger("ora.home.calendar_event")

# Quello che si dice a una persona di un appuntamento. Non e' la riga del
# database: e' cosa e', quando, dove, e da dove lo sappiamo.
HUMAN_FIELDS = (
    "title", "starts_at", "ends_at", "all_day", "location", "description",
    "calendar_name", "status", "timezone",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _moment(value: Any) -> Optional[datetime]:
    try:
        found = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return found if found.tzinfo else found.replace(tzinfo=timezone.utc)


async def _row(db, user_id: str, item_id: str) -> Optional[Dict[str, Any]]:
    """
    La riga di questo appuntamento, comunque la si chiami.

    Il pulsante in Home porta con se' l'id della riga di ingestion; una
    conversazione o un link possono portare l'id che ha su Google. Sono due
    nomi della stessa cosa e vengono accettati entrambi, perche' chiedere alla
    persona di sapere quale sia sarebbe assurdo.
    """
    for field in ("id", "external_id"):
        found = await db.ingestion_events.find_one(
            {
                "user_id": user_id,
                field: item_id,
                "source_record_type": {
                    "$in": ["event", "calendar_event", "google_event"],
                },
            },
            {"_id": 0},
            sort=[("ingested_at", -1)],
        )
        if found:
            return found
    return await _from_our_own_record(db, user_id, item_id)


async def _from_our_own_record(
    db, user_id: str, item_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Lo stesso appuntamento, letto dalla bozza che ORA tiene di quello che ha scritto.

        UN IMPEGNO APPENA CREATO ESISTE PRIMA DI ESSERE STATO RILETTO.

    L'archivio si riempie quando il sync passa — o subito dopo una scrittura,
    quando l'archiviazione immediata riesce. Fra i due momenti c'e' una
    finestra, stretta ma vera, in cui l'evento e' su Google e in Home ma
    l'archivio non ne sa ancora niente. Chiedere di toglierlo proprio li'
    rispondeva «non esiste», di una cosa che la persona aveva davanti.

    Quindi c'e' un secondo posto dove guardare, ed e' il nostro stesso
    registro di aver scritto. Non e' un secondo motore: quello che torna ha
    la stessa forma di una riga di ingestion, e tutto il resto — autorita',
    cancellazione, rilettura — continua a essere uno solo.
    """
    draft = await db.calendar_event_drafts.find_one(
        {
            "user_id": user_id,
            "$or": [{"id": item_id}, {"google_event_id": item_id}],
        },
        {"_id": 0},
    )
    if not draft:
        return None
    return {
        "id": str(draft.get("id") or ""),
        "external_id": str(draft.get("google_event_id") or ""),
        "normalized_payload": {
            "title": draft.get("title") or "Evento",
            "starts_at": draft.get("start_datetime"),
            "ends_at": draft.get("end_datetime"),
            "all_day": bool(draft.get("all_day")),
            "location": draft.get("venue_name") or draft.get("location"),
            "description": draft.get("description"),
            "calendar_id": draft.get("google_calendar_id") or "primary",
            "calendar_name": draft.get("google_calendar_id") or "Google Calendar",
            "status": (
                "cancelled" if draft.get("status") == "cancelled" else "confirmed"
            ),
            "timezone": draft.get("timezone"),
        },
    }


# Righe che ORA scrive nella descrizione per se' stessa: il riferimento al
# documento da cui e' nato l'evento, la firma, e il luogo che compare gia' nel
# suo campo. Sono la nostra contabilita', non le note della persona, e in una
# schermata che dice «Note» non hanno niente da fare.
_OUR_OWN_BOOKKEEPING = (
    "creato da ora", "rif. documento ora", "luogo:", "ora — life os",
)


def _human_notes(text: Any) -> Optional[str]:
    """Le note come le ha scritte una persona, senza la nostra contabilita'."""
    kept = [
        line for line in str(text or "").splitlines()
        if line.strip() and not any(
            line.strip().lower().startswith(mark) for mark in _OUR_OWN_BOOKKEEPING
        )
    ]
    return chr(10).join(kept).strip() or None


async def event_detail(db, user_id: str, item_id: str) -> Optional[Dict[str, Any]]:
    """Cosa c'e' da sapere di questo appuntamento, in parole."""
    row = await _row(db, user_id, item_id)
    if row is None:
        return None
    payload = plain(row.get("normalized_payload"))
    cancelled = str(payload.get("status") or "").lower() == "cancelled"
    return {
        "id": row.get("id"),
        "title": payload.get("title") or "Evento",
        "starts_at": payload.get("starts_at"),
        "ends_at": payload.get("ends_at"),
        "all_day": bool(payload.get("all_day")),
        "location": payload.get("location") or None,
        "description": _human_notes(payload.get("description")),
        # Da dove arriva, detto come lo direbbe una persona: «il tuo Google
        # Calendar», non «connector_id=calendar_google».
        "where_it_comes_from": (
            payload.get("calendar_name") or payload.get("calendar_id") or "Google Calendar"
        ),
        "provider": "Google Calendar",
        "state": "annullato" if cancelled else "in calendario",
        "cancelled": cancelled,
        # ORA puo' spostarlo e toglierlo solo se e' un calendario su cui puo'
        # scrivere. Non e' un dettaglio tecnico: e' la differenza fra un
        # pulsante che funziona e uno che mente.
        "can_be_changed": not cancelled,
    }


async def delete_event(
    db, user_id: str, item_id: str, *, confirmed_title: str = "",
) -> Dict[str, Any]:
    """
    Toglilo dal calendario vero, e dillo solo dopo averlo verificato.

        UNA CONFERMA GENERICA NON VALE PER UN ALTRO EVENTO.

    La conferma che arriva da chi chiama porta il titolo dell'appuntamento che
    la persona ha visto quando ha detto di si'. Se non corrisponde a quello
    che sta per essere cancellato, non si cancella niente: e' l'unico modo per
    cui un «sì» dato a una visita non possa valere per la cena di sabato.
    """
    from agent import commanded
    from connectors.google_calendar.provider import GoogleCalendarAPIError

    row = await _row(db, user_id, item_id)
    if row is None:
        return {"ok": False, "reason": "not_found"}

    payload = plain(row.get("normalized_payload"))
    title = str(payload.get("title") or "Evento")
    external_id = str(row.get("external_id") or "")
    calendar_id = str(payload.get("calendar_id") or "primary")
    # Un impegno che non e' mai arrivato su Google — la sincronizzazione non
    # era collegata, o e' fallita — esiste solo nel nostro registro. Toglierlo
    # e' un cambio di stato locale, e non c'e' nessun provider a cui chiederlo
    # ne' niente da rileggere: la verita' e' tutta qui. Resta lo stesso
    # percorso, con il passaggio sul provider che non ha niente da fare.
    only_ours = not external_id

    if str(payload.get("status") or "").lower() == "cancelled":
        # Gia' tolto. Ripeterlo non e' un errore e non e' un secondo effetto:
        # un pulsante toccato due volte deve rispondere la stessa cosa.
        return {
            "ok": True, "operation": "already_gone", "verified": True,
            "title": title, "say_it_as": "eliminato",
        }

    if confirmed_title and confirmed_title.strip() != title.strip():
        return {
            "ok": False, "reason": "confirmation_does_not_match",
            "title": title,
        }

    # --- chi lo ha chiesto, e per cosa esattamente -----------------------
    effect = commanded.calendar_effect({"title": title, "delete": True})
    act = await commanded.assess(
        db, user_id,
        capability="calendar.write",
        effect=effect,
        parameters={
            "title": title,
            # L'autorita' e' legata a *questo* manico. Due eventi con lo
            # stesso nome sono due atti diversi, e il si' dato a uno non
            # arriva all'altro.
            "google_event_id": external_id,
            "starts_at": str(payload.get("starts_at") or ""),
            "operation": "delete",
        },
        summary=f"Togliere dal calendario: {title}",
        expected=f"«{title}» non risulta più in calendario.",
        command=commanded.UserCommand(
            spoken=f"elimina {title}",
            words=f"elimina {title}",
            asked_for=f"eliminare «{title}»",
        ),
        answered_proposal=True,
    )
    if not act.may_execute:
        return {"ok": False, "reason": "authority_required", "title": title}

    taken = await commanded.begin(db, act)
    if taken == "already_done":
        return {
            "ok": True, "operation": "already_gone", "verified": True,
            "title": title, "say_it_as": "eliminato",
        }
    if taken != "go":
        return {"ok": False, "reason": "already_running", "title": title}

    if only_ours:
        await db.calendar_event_drafts.update_many(
            {"user_id": user_id, "id": str(row.get("id") or "")},
            {"$set": {"status": "cancelled", "updated_at": _now().isoformat()}},
        )
        await commanded.settle(
            db, act, provider="calendar", external_ref="",
            accepted=True, observed=True,
        )
        return {
            "ok": True, "operation": "deleted", "verified": True,
            "deleted_on_google": False, "title": title,
            "say_it_as": "eliminato",
        }

    # --- l'effetto, sul calendario di Google -----------------------------
    import deps

    gcal = deps.get_google_calendar_service()
    instance = await db.connector_instances.find_one(
        {"user_id": user_id, "connector_id": "calendar_google",
         "status": {"$in": ["connected", "syncing", "active"]}},
        {"_id": 0},
    )
    if not instance:
        await commanded.settle(
            db, act, provider="calendar", external_ref=external_id,
            accepted=False, observed=False, error_type="not_connected",
        )
        return {"ok": False, "reason": "calendar_not_connected", "title": title}

    accepted = False
    try:
        access = await gcal._get_access_token(user_id=user_id, instance=instance)
        await gcal.provider.delete_event(
            access_token=access, calendar_id=calendar_id, event_id=external_id,
        )
        accepted = True
    except GoogleCalendarAPIError as e:
        if e.status_code == 404:
            # Google non ce l'ha piu'. Non e' un errore: e' il risultato.
            accepted = True
        else:
            logger.info("delete rifiutato da google: %s", e.status_code)
    except Exception as e:
        logger.info("delete soft-fail: %s", type(e).__name__)

    # --- e adesso si guarda ----------------------------------------------
    #
    #     ACCETTATO DAL PROVIDER NON E' SPARITO.
    #
    # Si rilegge l'evento da Google. Sparito o annullato: e' andato. Ancora
    # confermato: non lo e', e non lo si dice.
    gone = False
    seen: Optional[Dict[str, Any]] = None
    if accepted:
        try:
            access = await gcal._get_access_token(user_id=user_id, instance=instance)
            seen = await gcal.provider.get_event(
                access_token=access, calendar_id=calendar_id, event_id=external_id,
            )
            gone = not seen or str((seen or {}).get("status") or "") == "cancelled"
        except GoogleCalendarAPIError as e:
            gone = e.status_code == 404
        except Exception as e:
            logger.info("read-after-delete soft-fail: %s", type(e).__name__)

    await commanded.settle(
        db, act, provider="calendar", external_ref=external_id,
        accepted=accepted, observed=gone,
        error_type="" if gone else "not_observed_gone",
    )

    if not gone:
        return {
            "ok": False, "reason": "not_confirmed_gone", "title": title,
            "say_it_as": "",
        }

    # --- il proprio archivio, allineato a quello che si e' visto ---------
    await db.ingestion_events.update_many(
        {"user_id": user_id, "external_id": external_id},
        {"$set": {
            "normalized_payload.status": "cancelled",
            # Il lavoro e' nostro. Il sync che ripassa fra un minuto deve
            # riconoscerlo come tale e non trattarlo come una novita' del
            # mondo su cui svegliare qualcuno.
            "ora_originated": True,
            "ora_originated_at": _now().isoformat(),
        }},
    )
    await db.calendar_event_drafts.update_many(
        {"user_id": user_id, "google_event_id": external_id},
        {"$set": {"status": "cancelled", "updated_at": _now().isoformat()}},
    )
    await db.life_nodes.update_many(
        {"user_id": user_id, "attributes.external_event_id": external_id},
        {"$set": {"status": "archived"}},
    )

    return {
        "ok": True, "operation": "deleted", "verified": True,
        "deleted_on_google": True, "title": title,
        "google_event_id": external_id,
        "say_it_as": "eliminato",
    }
