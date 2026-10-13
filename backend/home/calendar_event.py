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
from dataclasses import dataclass
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


def _provider_identity(row: Dict[str, Any]) -> tuple[str, str, str]:
    payload = plain(row.get("normalized_payload"))
    return (
        str(row.get("connector_id") or "calendar_google"),
        str(row.get("connector_instance_id") or ""),
        str(payload.get("calendar_id") or (row.get("raw_reference") or {}).get("calendar_id") or ""),
    )


async def _row(db, user_id: str, item_id: str) -> Optional[Dict[str, Any]]:
    """
    La riga di questo appuntamento, comunque la si chiami.

    Il pulsante in Home porta con se' l'id della riga di ingestion; una
    conversazione o un link possono portare l'id che ha su Google. Sono due
    nomi della stessa cosa e vengono accettati entrambi, perche' chiedere alla
    persona di sapere quale sia sarebbe assurdo.
    """
    from home.manual_event import get_manual_event
    local = await get_manual_event(db, user_id, item_id)
    if local:
        attrs = local.get("attributes") or {}
        return {
            "id": local["id"], "external_id": "", "ora_manual": True,
            "updated_at": local.get("updated_at"),
            "normalized_payload": {
                "title": local["label"], "starts_at": attrs.get("starts_at"),
                "ends_at": attrs.get("ends_at"), "timezone": attrs.get("timezone"),
                "location": attrs.get("location"), "description": local.get("description"),
                "calendar_name": "Calendario ORA", "all_day": bool(attrs.get("all_day")),
                "status": "confirmed" if local.get("status") == "active" else "cancelled",
            },
        }
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
            if field == "external_id":
                # Google event ids are scoped to a calendar, not to a user.
                # A bare provider id must never silently choose an account.
                candidates = await db.ingestion_events.find(
                    {"user_id": user_id, "external_id": item_id,
                     "source_record_type": {"$in": ["event", "calendar_event", "google_event"]}},
                    {"_id": 0, "connector_id": 1, "connector_instance_id": 1,
                     "normalized_payload.calendar_id": 1, "raw_reference.calendar_id": 1},
                ).limit(201).to_list(length=201)
                if len(candidates) > 200 or len({_provider_identity(candidate) for candidate in candidates}) != 1:
                    return None
            return found

    # Ingestion can create Life Graph nodes whose id differs from the provider
    # event id. The agenda links to that canonical node. Show it read-only
    # unless a provider-specific write handle has actually been resolved.
    node = await db.life_nodes.find_one(
        {"id": item_id, "user_id": user_id, "type": "event",
         "status": "active"},
        {"_id": 0},
    )
    if node:
        attrs = node.get("attributes") or {}
        connector = str(attrs.get("connector_id") or "")
        return {
            "id": node.get("id"),
            "external_id": "",
            "source_connector_id": connector,
            "read_only": True,
            "normalized_payload": {
                "title": node.get("label") or "Evento",
                "starts_at": attrs.get("starts_at"),
                "ends_at": attrs.get("ends_at"),
                "all_day": bool(attrs.get("all_day")),
                "location": attrs.get("location"),
                "description": node.get("description"),
                "timezone": attrs.get("timezone"),
                "calendar_name": (
                    "Calendario Apple" if "apple" in connector else
                    "Google Calendar" if "google" in connector else
                    "Calendario ORA" if not connector else connector
                ),
                "status": "confirmed",
            },
        }
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
        {"user_id": user_id, "id": item_id}, {"_id": 0},
    )
    if not draft:
        candidates = await db.calendar_event_drafts.find(
            {"user_id": user_id, "google_event_id": item_id}, {"_id": 0},
        ).limit(2).to_list(length=2)
        if len(candidates) != 1:
            return None
        draft = candidates[0]
    if not draft:
        return None
    return {
        "id": str(draft.get("id") or ""),
        "ora_draft": True,
        "connector_id": "calendar_google",
        "connector_instance_id": draft.get("connector_instance_id"),
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


def _event_provider(row: Dict[str, Any], payload: Dict[str, Any]) -> str:
    if row.get("ora_manual"):
        return "ORA"
    connector = str(
        row.get("source_connector_id")
        or row.get("connector_id")
        or payload.get("connector_id")
        or ""
    ).lower()
    if "apple" in connector:
        return "Calendario Apple"
    if "google" in connector:
        return "Google Calendar"
    if row.get("read_only"):
        return "Calendario ORA" if not connector else "Altro calendario"
    # Legacy Google ingestion rows may not have a connector_id.
    return "Google Calendar"


@dataclass
class _GoogleTarget:
    instance: Dict[str, Any]
    calendar_id: str
    calendar_ids: list[str]
    single_account: bool


async def _google_target(db, user_id: str, row: Dict[str, Any]) -> tuple[Optional[_GoogleTarget], str]:
    """Resolve the event's own account and calendar without a provider call."""
    from home.calendar_read import selected_calendar_source

    connector, instance_id, calendar_id = _provider_identity(row)
    if connector != "calendar_google" or not calendar_id or row.get("source_status") == "detached":
        return None, "invalid_calendar_target"
    # Include disconnected accounts: the sole connected account is not proof
    # that a historical, unbound event belongs to that account.
    accounts = await db.connector_instances.find(
        {"user_id": user_id, "connector_id": "calendar_google"}, {"_id": 0, "id": 1},
    ).limit(2).to_list(length=2)
    single_account = len(accounts) == 1
    if not instance_id:
        if not single_account:
            return None, "ambiguous_calendar_target"
        instance_id = str(accounts[0].get("id") or "")
    if not instance_id:
        return None, "invalid_calendar_target"
    instance = await db.connector_instances.find_one(
        {"user_id": user_id, "connector_id": "calendar_google", "id": instance_id,
         "status": {"$in": ["connected", "syncing"]}}, {"_id": 0},
    )
    if not instance:
        return None, "calendar_not_connected"
    account = str((instance.get("metadata") or {}).get("account_email") or "")
    aliases = [calendar_id]
    if account and calendar_id in {"primary", account}:
        aliases = ["primary", account]
        calendar_id = account
    if not any(selected_calendar_source({
        "connector_id": "calendar_google", "connector_instance_id": instance_id,
        "calendar_id": alias,
    }, [instance]) for alias in aliases):
        return None, "calendar_not_selected"
    return _GoogleTarget(instance, calendar_id, aliases, single_account), ""


async def event_detail(db, user_id: str, item_id: str) -> Optional[Dict[str, Any]]:
    """Cosa c'e' da sapere di questo appuntamento, in parole."""
    row = await _row(db, user_id, item_id)
    if row is None:
        return None
    payload = plain(row.get("normalized_payload"))
    cancelled = str(payload.get("status") or "").lower() == "cancelled"
    provider = _event_provider(row, payload)
    can_change = not cancelled and not row.get("read_only") and provider in ("ORA", "Google Calendar")
    if can_change and row.get("external_id"):
        target, _ = await _google_target(db, user_id, row)
        can_change = target is not None
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
            payload.get("calendar_name") or payload.get("calendar_id") or provider
        ),
        "provider": provider,
        "is_local": bool(row.get("ora_manual")),
        "timezone": payload.get("timezone"),
        "updated_at": row.get("updated_at"),
        "state": "annullato" if cancelled else "in calendario",
        "cancelled": cancelled,
        # ORA puo' spostarlo e toglierlo solo se e' un calendario su cui puo'
        # scrivere. Non e' un dettaglio tecnico: e' la differenza fra un
        # pulsante che funziona e uno che mente.
        "can_be_changed": can_change,
    }


async def delete_event(
    db, user_id: str, item_id: str, *, confirmed_title: str = "",
    command=None, answered_proposal: bool = True, confirmation=None,
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

    if row.get("read_only") or _event_provider(row, payload) not in ("ORA", "Google Calendar"):
        return {"ok": False, "reason": "read_only_calendar", "title": title}
    if only_ours and not (row.get("ora_manual") or row.get("ora_draft")):
        return {"ok": False, "reason": "invalid_calendar_target", "title": title}

    if (row.get("ora_manual") and not confirmed_title) or (confirmed_title and confirmed_title.strip() != title.strip()):
        return {
            "ok": False, "reason": "confirmation_does_not_match",
            "title": title,
        }

    target = None
    if not only_ours:
        from connectors.google_calendar.consent import calendar_consent_granted

        target, reason = await _google_target(db, user_id, row)
        if not target:
            return {"ok": False, "reason": reason, "title": title}
        if not await calendar_consent_granted(
            db, user_id=user_id, write=True, connector_instance_id=target.instance["id"],
        ):
            return {"ok": False, "reason": "authority_required", "title": title}

    if confirmation is not None:
        from agent.calendar_assent import CalendarCancellationConfirmation
        latest = await event_detail(db, user_id, item_id)
        if (type(confirmation) is not CalendarCancellationConfirmation or not latest
                or not row.get("ora_manual")
                or not confirmation.matches_readback(user_id, "calendar:" + str(row["id"]), latest)):
            return {"ok": False, "reason": "event_changed", "title": title}

    # --- chi lo ha chiesto, e per cosa esattamente -----------------------
    effect = commanded.calendar_effect({"title": title, "delete": True})
    act = await commanded.assess(
        db, user_id,
        capability="calendar.local.write" if row.get("ora_manual") else "calendar.write",
        effect=effect,
        parameters={
            "title": title,
            # L'autorita' e' legata a *questo* manico. Due eventi con lo
            # stesso nome sono due atti diversi, e il si' dato a uno non
            # arriva all'altro.
            "google_event_id": external_id,
            "connector_instance_id": target.instance["id"] if target else "",
            "calendar_id": target.calendar_id if target else "",
            "calendar_ref": str(row.get("id") or "") if only_ours else external_id,
            "starts_at": str(payload.get("starts_at") or ""),
            "operation": "delete",
        },
        summary=f"Togliere dal calendario: {title}",
        expected=f"«{title}» non risulta più in calendario.",
        command=command or commanded.UserCommand(
            spoken="sì",
            words=f"elimina {title}",
            asked_for=f"eliminare «{title}»",
        ),
        answered_proposal=answered_proposal, confirmation=confirmation,
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
        observed = True
        if row.get("ora_manual"):
            from home.manual_event import archive_manual_event
            observed = await archive_manual_event(db, user_id, str(row["id"]))
        else:
            await db.calendar_event_drafts.update_many(
                {"user_id": user_id, "id": str(row.get("id") or "")},
                {"$set": {"status": "cancelled", "updated_at": _now().isoformat()}},
            )
        await commanded.settle(
            db, act, provider="calendar", external_ref="",
            accepted=True, observed=observed,
        )
        if not observed:
            return {"ok": False, "reason": "not_confirmed_gone", "title": title}
        return {
            "ok": True, "operation": "deleted", "verified": True,
            "deleted_on_google": False, "title": title,
            "say_it_as": "eliminato",
        }

    # --- l'effetto, sul calendario di Google -----------------------------
    import deps

    current, reason = await _google_target(db, user_id, row)
    if (not current or current.instance["id"] != target.instance["id"]
            or current.calendar_id != target.calendar_id):
        await commanded.settle(
            db, act, provider="calendar", external_ref=external_id,
            accepted=False, observed=False, error_type=reason or "calendar_target_changed",
        )
        return {"ok": False, "reason": reason or "calendar_target_changed", "title": title}
    if not await calendar_consent_granted(
        db, user_id=user_id, write=True, connector_instance_id=current.instance["id"],
    ):
        await commanded.settle(
            db, act, provider="calendar", external_ref=external_id,
            accepted=False, observed=False, error_type="authority_required",
        )
        return {"ok": False, "reason": "authority_required", "title": title}
    target = current
    instance, calendar_id = target.instance, target.calendar_id
    gcal = deps.get_google_calendar_service()

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
    ingestion_scopes = [{
        "connector_id": "calendar_google", "connector_instance_id": instance["id"],
        "$or": [{"normalized_payload.calendar_id": {"$in": target.calendar_ids}},
                {where("calendar_id"): {"$in": target.calendar_ids}}],
    }]
    if not row.get("ora_draft"):
        # The exact row also covers an unambiguously resolved legacy record.
        ingestion_scopes.append({"id": row["id"]})
    await db.ingestion_events.update_many(
        {"user_id": user_id, "external_id": external_id, "$or": ingestion_scopes},
        {"$set": {
            "normalized_payload.status": "cancelled",
            # Il lavoro e' nostro. Il sync che ripassa fra un minuto deve
            # riconoscerlo come tale e non trattarlo come una novita' del
            # mondo su cui svegliare qualcuno.
            "ora_originated": True,
            "ora_originated_at": _now().isoformat(),
        }},
    )
    draft_scopes = [{"connector_instance_id": instance["id"]}]
    if row.get("ora_draft"):
        draft_scopes.append({"id": row["id"]})
    else:
        draft_scopes.append({"source_document_id": row["id"],
                             "connector_instance_id": {"$in": [None, ""]}})
    if target.single_account:
        draft_scopes.append({"connector_instance_id": {"$in": [None, ""]}})
    await db.calendar_event_drafts.update_many(
        {"user_id": user_id, "google_event_id": external_id,
         "google_calendar_id": {"$in": target.calendar_ids}, "$or": draft_scopes},
        {"$set": {"status": "cancelled", "updated_at": _now().isoformat()}},
    )
    await db.life_nodes.update_many(
        {"user_id": user_id, "attributes.external_event_id": external_id,
         "attributes.connector_id": "calendar_google",
         "attributes.connector_instance_id": instance["id"],
         "attributes.calendar_id": {"$in": target.calendar_ids}},
        {"$set": {"status": "archived"}},
    )

    return {
        "ok": True, "operation": "deleted", "verified": True,
        "deleted_on_google": True, "title": title,
        "google_event_id": external_id,
        "say_it_as": "eliminato",
    }
