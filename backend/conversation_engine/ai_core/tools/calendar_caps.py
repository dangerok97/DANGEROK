"""AI Core capabilities wrapping Calendar (V2.8.6b).

Calendar is a capability, not a second brain: this module wraps the
V2.8.6a-hardened services (`CalendarGateway`/`InternalCalendarProvider`,
`GoogleCalendarSyncService`, `timezone_service`, `connectors.google_calendar
.consent`) — nothing here talks to Google directly, and nothing here decides
whether a user statement "means" a calendar event. That decision stays with
the AI; this module only guarantees ownership, consent, idempotency, bounded
output and failure honesty once the AI has decided to read or write.

Canonical ref: an AI-managed calendar item is always `calendar:{draft_id}`
(draft_id prefixed `ced_`) — the same ref shape already emitted by the
Context Broker's `_calendar` source and already a recognized Context Graph
prefix. Read-only ingested Google events (`ingestion_events`, items the user
already had in Google before ORA touched anything) are surfaced for
conflict-awareness only, with no canonical ref — they are not directly
actionable via these capabilities (V2.8.6b canonical-ref policy, see
docs/ARCHITECTURE.md).
"""
from __future__ import annotations

from ingestion.reading import plain, where

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agent import commanded
from agent.authority import UserCommand
from conversation_engine.ai_core.models import Observation
from connectors.google_calendar.consent import (
    CapabilityDisabled,
    CapabilityUnknown,
    ConsentDenied,
    calendar_consent_granted,
    require_calendar_consent,
)
from documents.intelligence.calendar_adapter import CalendarGateway
from documents.intelligence.google_sync import (
    GoogleCalendarAPIError,
    GoogleCalendarSyncService,
)
from timezone_service import is_valid_iana_timezone, resolve_user_timezone

logger = logging.getLogger("ora.ai_core.calendar_caps")

_MAX_TITLE = 200
_MAX_LOCATION = 300
_MAX_DESCRIPTION = 800
# The project's one answer to "how long is an appointment nobody measured".
# Imported rather than re-declared: the shared builder is where every calendar
# write ends up, and two constants that agree today are two constants that
# disagree later.
from documents.intelligence.google_sync import DEFAULT_EVENT_MINUTES as _DEFAULT_MINUTES
_MAX_WINDOW_DAYS = 60
_DEFAULT_WINDOW_DAYS = 7
_MAX_EVENTS_RETURNED = 20


def _fail(name: str, code: str, detail: str = "") -> Observation:
    return Observation(
        kind="tool",
        name=name,
        status="error",
        payload={"status": "error", "failure_kind": code, "detail": detail[:200]},
    )


def _ref(draft_id: str) -> str:
    return f"calendar:{draft_id}"


def _strip_ref(value: Optional[str]) -> str:
    v = str(value or "").strip()
    return v[len("calendar:") :] if v.startswith("calendar:") else v


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Authority, in front of the write.
#
#     DO NOT ASK FOR CONFIRMATION OF A DECISION THE USER HAS JUST MADE.
#     A COMMAND IS AN AUTHORITY FACT, NOT A REASON TO SKIP A SAFEGUARD.
#
# What used to be here was a sentence in a docstring: "the AI is expected to
# have already proposed this and received explicit user confirmation — the
# runtime does not re-litigate that". Which is to say the authority for every
# external write ORA made lived in a prompt instruction, and whether it had
# been honoured was not a thing anybody could check afterwards.
#
# Now two facts reach this gate, and code owns both of them: what the person
# wrote this turn, and whether ORA had asked them something before they wrote
# it. Either can carry the authority, each produces an ordinary consent row
# bound to the act's hash, and neither is the model's word for itself.
#
# The consequence people will actually notice is the one this micro-fix is
# named for: somebody who writes «segnami un evento domani alle 10» is not
# asked whether they want an event tomorrow at ten.
# ---------------------------------------------------------------------------


def _user_command(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> UserCommand:
    """
    What the person said, and what the model claims to have read in it.

    The message comes from the runtime; only the quote comes from the model,
    and the quote is checked against the message rather than believed. A model
    that cannot point at the words gets no authority from them — and the
    failure is the ordinary propose-then-confirm flow, which is the thing that
    was already working.
    """
    declared = arguments.get("user_authority")
    declared = declared if isinstance(declared, dict) else {}
    if not declared.get("requested_by_user"):
        return UserCommand(spoken=str(runtime.get("user_message") or ""))
    return UserCommand(
        spoken=str(runtime.get("user_message") or ""),
        words=str(declared.get("user_words") or "")[:200],
        asked_for=str(declared.get("what_they_asked_for") or "")[:300],
    )


def _answered_a_proposal(runtime: Dict[str, Any]) -> bool:
    """Whether ORA had proposed something and this message is the reply."""
    return bool(runtime.get("pending_act"))


def _needs(name: str, missing: str, ask: str) -> Observation:
    """
    Something needed is not there. Ask for that, and only that.

        ASK FOR WHAT IS MISSING, NOT FOR PERMISSION TO DO WHAT WAS ASKED.

    «Segnami il dentista» with no time is a request with a hole in it, not a
    request in doubt. The hole is one question long; the doubt would be a
    second one nobody needs.
    """
    return Observation(
        kind="tool", name=name, status="partial",
        payload={
            "status": "needs_information",
            "missing": missing,
            "reason": (
                "Manca un dato necessario per creare l'evento. Chiedi soltanto "
                f"quello — {ask} — e non chiedere conferma di un'azione che la "
                "persona ha già chiesto."
            ),
        },
    )


def _authority_required(name: str, act) -> Observation:
    """Nothing checkable authorises this. Propose it, the way it always was."""
    return Observation(
        kind="tool", name=name, status="partial",
        payload={
            "status": "authority_required",
            "basis": act.basis,
            "reason": (
                "Questa azione tocca il mondo e non c'è un'autorizzazione "
                "verificabile per farla adesso. Proponila con response_mode=act, "
                "in una frase, e aspetta la risposta della persona. Non dire che "
                "è stata fatta."
            ),
        },
    )


def _is_at(seen: Dict[str, Any], wanted: Any) -> bool:
    """
    Whether the event the calendar just handed back starts when we asked.

    Compared as instants, never as strings: Google answers in whatever
    offset it likes, and «2026-09-11T10:00:00+02:00» and
    «2026-09-11T08:00:00Z» are the same moment. A string comparison here
    would report a successful move as a failed one, which is the kind of
    false alarm that teaches people to ignore alarms.
    """
    if not wanted:
        return False
    said = (seen.get("start") or {}) if isinstance(seen.get("start"), dict) else {}
    when = said.get("dateTime") or said.get("date")
    left, right = _parse_dt(str(when or "")), _parse_dt(str(wanted))
    if not left or not right:
        return False
    return left == right


async def _read_back(sync: GoogleCalendarSyncService, user_id: str, synced: dict):
    """
    Go and look at what was just written.

        READ AFTER WRITE.
        PROVIDER ACCEPTED IS NOT OUTCOME ACHIEVED.

    The whole difference between «l'ho segnato» and «l'ho chiesto». Without
    this the only evidence the event exists is that we asked for it, which is
    evidence of having asked.
    """
    event_id = str(synced.get("google_event_id") or "")
    calendar_id = str(synced.get("google_calendar_id") or "")
    if not event_id or not calendar_id:
        return {}, False
    try:
        inst = await sync._instance_for_user(user_id)
        if not inst:
            return {}, False
        access = await sync.gcal._get_access_token(user_id=user_id, instance=inst)
        found = await sync.gcal.provider.get_event(
            access_token=access, calendar_id=calendar_id, event_id=event_id,
        )
        return (found or {}), bool(found)
    except Exception as e:
        logger.info("calendar read-back soft-fail: %s", type(e).__name__)
        return {}, False


async def _file_it_now(
    db, sync: GoogleCalendarSyncService, user_id: str, calendar_id: str,
    raw: Dict[str, Any],
) -> bool:
    """
    Metti subito in archivio quello che si e' appena riletto da Google.

        QUELLO CHE ORA HA APPENA SCRITTO NON DEVE ASPETTARE IL PROSSIMO GIRO.

    Il polling passa ogni minuto, ed e' la cadenza giusta per il mondo: le
    cose che cambiano da sole si possono aspettare. Ma un appuntamento che la
    persona ha appena chiesto non e' il mondo che cambia — e' lei che ha
    appena fatto una cosa, e la schermata subito dopo deve mostrarla. Un
    minuto di «non c'e' niente» dopo aver detto «segnamelo» e' la schermata
    che dice che non l'hai fatto.

    Quello che si archivia e' la copia riletta dal provider, non quello che si
    era chiesto: e' la stessa riga che scriverebbe il sync fra un minuto, e
    infatti fra un minuto il dedupe la riconoscera' e non ne fara' una
    seconda.
    """
    if not raw or not raw.get("id"):
        return False
    try:
        instance = await sync._instance_for_user(user_id)
        if not instance:
            return False
        await sync.gcal.ingestion.ingest_calendar_events(
            user_id=user_id,
            connector_id="calendar_google",
            connector_instance_id=instance.get("id"),
            calendar_id=calendar_id,
            calendar_name=calendar_id,
            raw_events=[raw],
        )
        return True
    except Exception as e:
        # Non e' un fallimento della scrittura: l'evento e' su Google e la
        # rilettura lo ha visto. Al massimo la Home lo mostra fra un minuto.
        logger.info("archiviazione immediata soft-fail: %s", type(e).__name__)
        return False


async def _sync_service(db) -> GoogleCalendarSyncService:
    # `deps` pulls in full app wiring — imported lazily here, same pattern
    # already used at the other GoogleCalendarSyncService call site
    # (documents/intelligence/service.py).
    from deps import get_google_calendar_service

    return GoogleCalendarSyncService(db=db, google_calendar_service=get_google_calendar_service())


async def _active_instance_id(sync: GoogleCalendarSyncService, uid: str) -> str:
    """Consent is granted per connector-instance (multi-account support),
    not just a wildcard — resolve the user's active instance so the consent
    check matches what OAuth actually granted, falling back to the wildcard
    default when no instance is connected yet (is_granted() still checks the
    wildcard tier too, so a generic grant is not lost by passing this)."""
    from permissions.models import INSTANCE_WILDCARD

    try:
        inst = await sync._instance_for_user(uid)
    except Exception:
        inst = None
    return str(inst["id"]) if inst else INSTANCE_WILDCARD


async def get_calendar_events(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    """READ_ONLY. Local storage only — never a live Google call per turn."""
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    if not uid or db is None:
        return _fail("get_calendar_events", "NOT_CONFIGURED")

    time_min = _parse_dt(arguments.get("time_min"))
    time_max = _parse_dt(arguments.get("time_max"))
    if not time_min:
        # Default to a UTC-aware "now" — a naive local "now" would silently
        # break the lexicographic string-range comparison below against
        # stored ISO strings that (like every event this module writes)
        # carry an explicit UTC offset, hiding real events whenever the
        # server's local timezone offset isn't exactly zero.
        time_min = datetime.now(time_max.tzinfo if time_max and time_max.tzinfo else timezone.utc)
    if not time_max:
        from datetime import timedelta

        time_max = time_min + timedelta(days=_DEFAULT_WINDOW_DAYS)
    if (time_max - time_min).days > _MAX_WINDOW_DAYS:
        from datetime import timedelta

        time_max = time_min + timedelta(days=_MAX_WINDOW_DAYS)
    if time_max <= time_min:
        return _fail("get_calendar_events", "INVALID_WINDOW", "time_max must be after time_min")

    tmin_iso, tmax_iso = time_min.isoformat(), time_max.isoformat()

    drafts_cur = db.calendar_event_drafts.find(
        {
            "user_id": uid,
            "status": {"$ne": "cancelled"},
            "start_datetime": {"$gte": tmin_iso, "$lt": tmax_iso},
        },
        {
            "_id": 0, "id": 1, "title": 1, "start_datetime": 1, "end_datetime": 1,
            "timezone": 1, "all_day": 1, "location": 1, "status": 1,
            "sync_status": 1, "provider": 1,
            # Il manico del provider: serve per chiedere al calendario se
            # l'evento c'e' davvero. Non esce mai da questa funzione.
            "google_event_id": 1,
        },
    ).sort("start_datetime", 1).limit(_MAX_EVENTS_RETURNED)
    drafts = await drafts_cur.to_list(_MAX_EVENTS_RETURNED)

    items = [
        {
            "calendar_ref": _ref(d["id"]),
            "source": "ora_managed",
            "title": d.get("title"),
            "start_datetime": d.get("start_datetime"),
            "end_datetime": d.get("end_datetime"),
            "timezone": d.get("timezone"),
            "all_day": bool(d.get("all_day")),
            "location": d.get("location"),
            "status": d.get("status"),
            "sync_status": d.get("sync_status"),
        }
        for d in drafts
    ]

    # Google-imported events are gated on calendar.read consent — a local
    # cache/mirror must never become a bypass of a revoked connector. This
    # never blocks the read as a whole: ORA-managed events above are the
    # user's own local record and stay visible regardless of Google
    # connection state (their provenance is already explicit as
    # "ora_managed", never presented as current Google state).
    sync = await _sync_service(db)
    instance_id = await _active_instance_id(sync, uid)
    google_read_granted = await calendar_consent_granted(
        db, user_id=uid, write=False, connector_instance_id=instance_id,
    )

    remaining = max(0, _MAX_EVENTS_RETURNED - len(items))
    if remaining and google_read_granted:
        ingested_cur = db.ingestion_events.find(
            {
                "user_id": uid,
                "connector_id": "calendar_google",
                "source_status": {"$ne": "detached"},
                # Il campo vero e' `starts_at.value`: ogni campo viaggia
                # dentro la sua busta, e un filtro sulla busta non trova
                # niente — silenziosamente, come se il calendario fosse
                # vuoto. E' lo stesso errore che teneva la Home a zero.
                where("starts_at"): {"$gte": tmin_iso, "$lt": tmax_iso},
            },
            {"_id": 0, "normalized_payload": 1, "external_id": 1},
        ).sort(where("starts_at"), 1).limit(remaining)
        mirrored = await ingested_cur.to_list(remaining)

        # Quello che il calendario conferma davvero.
        #
        #     UN RECORD LOCALE CHE DICE «SINCRONIZZATO» NON E' IL CALENDARIO.
        #
        # Un draft porta `sync_status: synced` da quando ORA lo ha scritto, e
        # da allora non ha piu' guardato: se qualcuno cancella l'evento da
        # Google, quel campo continua a dire «synced» per sempre e la chat
        # continua a rispondere «e' gia' in calendario». Qui si incrociano le
        # due liste sul manico del provider, e il draft che il mirror
        # conferma viene marcato come confermato.
        #
        # Quello che NON si fa e' concludere il contrario: non trovare una
        # riga non prova che l'evento non ci sia — la finestra e' limitata, la
        # lettura puo' essere in ritardo — quindi il caso non confermato si
        # chiama `unconfirmed`, che e' quello che sappiamo davvero.
        confirmed = {str(e.get("external_id") or "") for e in mirrored} - {""}
        already_ours = {
            str(d.get("google_event_id") or "") for d in drafts
        } - {""}
        for item, draft in zip(items, drafts):
            handle = str(draft.get("google_event_id") or "")
            if not handle:
                continue
            if handle in confirmed:
                item["sync_status"] = "synced"
                item["confirmed_by_calendar"] = True
            elif item.get("sync_status") == "synced":
                item["sync_status"] = "unconfirmed"
                item["confirmed_by_calendar"] = False

        for e in mirrored:
            p = plain(e.get("normalized_payload"))
            if str(e.get("external_id") or "") in already_ours:
                # Lo stesso appuntamento, gia' in lista come cosa di ORA e
                # adesso confermato dal calendario. Elencarlo due volte
                # farebbe dire al modello che sono due impegni.
                continue
            items.append({
                "calendar_ref": None,  # read-only external mirror, not actionable
                "source": "google_external",
                "title": p.get("title"),
                "start_datetime": p.get("starts_at"),
                "end_datetime": p.get("ends_at"),
                "timezone": p.get("timezone"),
                "all_day": bool(p.get("all_day")),
                "location": p.get("location"),
                "status": "confirmed",
                "sync_status": "synced",
            })

    items.sort(key=lambda x: x.get("start_datetime") or "")

    # Bounded, deterministic overlap detection — evidence only; the AI
    # decides whether a conflict matters, this never blocks/asks by itself.
    conflicts: List[List[int]] = []
    for i in range(len(items)):
        a_start, a_end = _parse_dt(items[i]["start_datetime"]), _parse_dt(items[i]["end_datetime"])
        if not a_start or not a_end:
            continue
        for j in range(i + 1, len(items)):
            b_start, b_end = _parse_dt(items[j]["start_datetime"]), _parse_dt(items[j]["end_datetime"])
            if not b_start or not b_end:
                continue
            if a_start < b_end and b_start < a_end:
                conflicts.append([i, j])

    return Observation(
        kind="tool",
        name="get_calendar_events",
        status="ok",
        payload={
            "status": "ok",
            "window": {"time_min": tmin_iso, "time_max": tmax_iso},
            "events": items,
            "conflict_index_pairs": conflicts[:10],
            "truncated": len(items) >= _MAX_EVENTS_RETURNED,
            "google_events_included": google_read_granted,
            "google_events_note": (
                None if google_read_granted else
                "Google Calendar read access is not authorized, so previously "
                "imported Google events are not included here — only ORA's own "
                "locally-managed events. Do not claim the calendar is empty of "
                "Google commitments; explain honestly that Google read access "
                "would need to be reauthorized to see them again."
            ),
        },
        provenance=[it["calendar_ref"] for it in items if it.get("calendar_ref")],
    )


def _same_thing(title: str) -> str:
    """
    Il titolo ridotto a cio' che si puo' confrontare senza interpretare.

    Minuscole, accenti via, punteggiatura via, spazi collassati. Non e' una
    somiglianza: due titoli che finiscono uguali qui sono la stessa stringa
    scritta in modo diverso, e questo e' un fatto. Tutto il resto — «visita
    dentistica» contro «dentista» — e' un giudizio su cosa intendeva la
    persona, e non si fa qui.
    """
    import re
    import unicodedata

    flat = unicodedata.normalize("NFKD", str(title or ""))
    flat = "".join(c for c in flat if not unicodedata.combining(c))
    flat = re.sub(r"[^a-z0-9 ]+", " ", flat.lower())
    return " ".join(flat.split())


async def _already_have_one(db, uid: str, *, title: str, start: str) -> Optional[Dict[str, Any]]:
    """
    Un impegno che ORA gia' gestisce e che porta esattamente questo nome.

        SPOSTARE NON E' CREARE.

    Cercato in una finestra di due settimane intorno alla data nuova, perche'
    una persona che dice «spostala all'11» sta parlando di qualcosa che ha
    gia', non di una seconda visita. Se c'e', questa funzione lo restituisce
    e chi ha chiamato si ferma: un secondo evento con lo stesso nome e un
    orario diverso e' quasi sempre lo stesso impegno scritto due volte, e la
    persona se lo ritrova in calendario per sempre.

    Il confronto e' sul titolo esatto, normalizzato. Non e' una rete a maglie
    fini: «Visita dentistica QA» e «Visita dentista» sono due stringhe
    diverse e passerebbero. Quello che questa funzione prende e' il caso
    frequente e verificabile; il caso generale non e' un problema di
    stringhe, ed e' affrontato dove va affrontato — nel dire la verita' su
    cosa e' stato fatto.
    """
    from datetime import timedelta

    when = _parse_dt(start)
    if not when:
        return None
    wanted = _same_thing(title)
    if not wanted:
        return None
    lo = (when - timedelta(days=14)).isoformat()
    hi = (when + timedelta(days=14)).isoformat()
    try:
        rows = await db.calendar_event_drafts.find(
            {"user_id": uid, "status": {"$ne": "cancelled"},
             "start_datetime": {"$gte": lo, "$lte": hi}},
            {"_id": 0, "id": 1, "title": 1, "start_datetime": 1,
             "google_event_id": 1},
        ).to_list(40)
    except Exception:
        return None
    for row in rows:
        if _same_thing(row.get("title")) != wanted:
            continue
        if str(row.get("start_datetime") or "")[:16] == str(start)[:16]:
            # Stesso nome e stessa ora: e' lo stesso evento, non uno spostato.
            # Se ne occupa l'idempotenza piu' avanti.
            continue
        return row
    return None


async def create_calendar_event(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    """
    REVERSIBLE_WRITE, behind a real authority gate.

    What used to be written here was that the runtime does not re-litigate
    whether the user agreed. It does now, and it does it without adding a
    question: either the person asked for this in words code can find in
    their message, or ORA proposed it and they answered. Either way a consent
    row exists afterwards, bound to the act by hash, and the write is claimed
    atomically, receipted, and read back before anybody says it happened.
    """
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    epoch = runtime.get("reasoning_epoch") or ""
    if not uid or db is None:
        return _fail("create_calendar_event", "NOT_CONFIGURED")

    title = str(arguments.get("title") or "").strip()[:_MAX_TITLE]
    start = arguments.get("start_datetime")
    if not title:
        return _needs("create_calendar_event", "title", "che cos'è")
    if not start or not _parse_dt(start):
        return _needs("create_calendar_event", "start_datetime", "quando")
    end = arguments.get("end_datetime")
    duration_minutes = arguments.get("duration_minutes")
    if not end:
        # An event with no end is an event of no length. Google accepts one
        # and shows a sliver nobody can read — which is what «segnami un
        # evento domani alle 10» produced before this line existed: the write
        # succeeded, the read-back confirmed it, and the outcome was still
        # wrong. Nobody asking for an appointment means a zero-minute one.
        from datetime import timedelta

        start_dt = _parse_dt(start)
        try:
            minutes = float(duration_minutes) if duration_minutes else _DEFAULT_MINUTES
        except (TypeError, ValueError):
            minutes = _DEFAULT_MINUTES
        end = (start_dt + timedelta(minutes=minutes)).isoformat() if start_dt else None
    if end and _parse_dt(end) and _parse_dt(start) and _parse_dt(end) <= _parse_dt(start):
        return _fail("create_calendar_event", "INVALID_INPUT", "end_datetime must be after start")

    tz = arguments.get("timezone")
    if tz and not is_valid_iana_timezone(str(tz)):
        tz = None
    tz_authority = "user_stated"
    if not tz:
        resolved = await resolve_user_timezone(db, uid)
        tz = resolved.tz_name
        tz_authority = resolved.authority

    # Spostare non si fa creando. Due modi di saperlo, e nessuno dei due si
    # fida del fatto che il modello scelga lo strumento giusto.
    #
    #     UN INTENTO DI SPOSTARE NON PUO' ESSERE SODDISFATTO CREANDO.
    #
    # Il primo e' la dichiarazione del modello: `operation_intent` e' un
    # campo che deve compilare, e se dice «modify» questa e' la chiamata
    # sbagliata — detto da lui, quindi non discutibile.
    #
    # Il secondo e' la frase della persona, presa da dove e' arrivata e non
    # dal riassunto che ne fa il modello. Serve perche' il primo copre solo
    # il caso in cui il modello sa cosa sta facendo, e il bug vero e' stato
    # esattamente il contrario: ha chiamato create senza dichiarare niente,
    # con un titolo diverso, e la persona si e' ritrovata due visite.
    #
    # `create_anyway` non apre nessuna di queste due porte. Apre solo quella
    # dei titoli uguali piu' sotto, che riguarda i doppioni per distrazione:
    # qui ci vuole una volonta' nuova della persona, cioe' un messaggio suo
    # che non chieda piu' di spostare.
    declared = str(arguments.get("operation_intent") or "").strip().lower()
    spoken = str(runtime.get("user_message") or "")
    asked_to_move = commanded.reads_as_a_move(spoken)
    if declared in ("modify", "reschedule", "update") or asked_to_move:
        target = _strip_ref(arguments.get("calendar_ref"))
        return Observation(
            kind="tool", name="create_calendar_event", status="rejected",
            payload={
                "status": "rejected",
                "failure_kind": "modify_requires_update",
                "operation_intent": declared or "modify",
                "why_we_think_so": (
                    "il modello lo ha dichiarato" if declared
                    else "la persona ha chiesto di spostare qualcosa"
                ),
                "calendar_ref": _ref(target) if target else None,
                "reason": (
                    "Spostare un impegno non si fa creandone un altro: quello "
                    "di prima resterebbe dov'è. Trova l'evento con "
                    "get_calendar_events e chiama update_calendar_event con "
                    "il suo calendar_ref. Se davvero serve un secondo "
                    "appuntamento distinto, deve dirlo la persona."
                ),
            },
        )

    # Un impegno con questo nome esiste gia', a un'altra ora.
    #
    #     UN SECONDO EVENTO NON E' UNO SPOSTAMENTO.
    #
    # Rifiutare invece di segnalare: una segnalazione dentro una risposta
    # riuscita e' una nota che il modello puo' non leggere, e il costo di non
    # leggerla e' un doppione nel calendario di una persona, per sempre.
    # Qui non si sceglie al posto del modello — gli si dice quale evento c'e'
    # gia' e con quale riferimento aggiornarlo, e se davvero ne servono due
    # basta ripetere la chiamata con `create_anyway`.
    if not arguments.get("create_anyway"):
        twin = await _already_have_one(db, uid, title=title, start=str(start))
        if twin:
            return Observation(
                kind="tool", name="create_calendar_event", status="rejected",
                payload={
                    "status": "rejected",
                    "failure_kind": "looks_like_a_move",
                    "existing": {
                        "calendar_ref": _ref(twin["id"]),
                        "title": twin.get("title"),
                        "start_datetime": twin.get("start_datetime"),
                    },
                    "reason": (
                        "C'è già un impegno con questo nome, a un altro orario. "
                        "Se la persona lo sta spostando, chiama "
                        "update_calendar_event con quel calendar_ref: creare un "
                        "secondo evento lascerebbe entrambi in calendario. Se "
                        "invece ne servono davvero due, richiama create con "
                        "create_anyway: true."
                    ),
                },
                provenance=[_ref(twin["id"])],
            )

    sync = await _sync_service(db)
    instance_id = await _active_instance_id(sync, uid)
    try:
        await require_calendar_consent(db, user_id=uid, write=True, connector_instance_id=instance_id)
    except ConsentDenied:
        return Observation(
            kind="tool", name="create_calendar_event", status="consent_required",
            payload={
                "status": "consent_required",
                "reason": (
                    "Calendar write consent is not granted. Explain honestly that "
                    "the user needs to connect/authorize Calendar before ORA can "
                    "create this on Google — never claim it was created."
                ),
            },
        )
    except (CapabilityDisabled, CapabilityUnknown):
        return _fail("create_calendar_event", "CAPABILITY_UNAVAILABLE")

    # --- is anybody allowed to do this, and on what basis -----------------
    effect = commanded.calendar_effect(arguments)
    act = await commanded.assess(
        db, uid,
        capability="calendar.write",
        effect=effect,
        parameters={
            "title": title,
            "starts_at": str(start),
            "ends_at": str(end or ""),
            "timezone": str(tz or ""),
        },
        summary=f"Segnare in calendario: {title}",
        expected=f"«{title}» risulta in calendario.",
        command=_user_command(arguments, runtime),
        answered_proposal=_answered_a_proposal(runtime),
    )
    if not act.may_execute:
        return _authority_required("create_calendar_event", act)

    taken = await commanded.begin(db, act)
    if taken == "already_done":
        # The same act, asked for twice: a re-sent message, a double tap, a
        # client retry. One event, and the honest answer is that it is
        # already there — not a second one, and not a failure either.
        ref = await commanded.already_done_ref(db, uid, act.intent) or ""
        prior = await db.calendar_event_drafts.find_one(
            {"user_id": uid, "google_event_id": ref},
            {"_id": 0, "id": 1, "status": 1},
        ) if ref else None
        still_there = bool(prior) and str(prior.get("status") or "") != "cancelled"
        if not still_there:
            # L'atto era stato eseguito, ma quello che aveva prodotto non c'e'
            # piu': l'evento e' stato cancellato dopo.
            #
            #     «GIA' FATTO» E' UN'AFFERMAZIONE SUL MONDO, NON SU UNA RIGA.
            #
            # Rispondere «c'e' gia'» qui e' un successo finto della specie
            # peggiore: la persona chiede di rimettere una cosa che aveva
            # cancellato, ORA dice che c'e', il calendario e' vuoto, e nessuno
            # dei due se ne accorge finche' non e' il giorno. Succedeva:
            # bastava creare, cancellare e ricreare lo stesso impegno.
            #
            # Quindi si riprende l'atto e lo si fa davvero. L'idempotenza
            # resta intatta per quello che serve — due tap ravvicinati sullo
            # stesso invio trovano ancora l'evento al suo posto.
            taken = await commanded.reopen(db, act)
        else:
            return Observation(
                kind="tool", name="create_calendar_event", status="ok",
                payload={
                    "status": "ok",
                    "operation": "already_created",
                    "calendar_ref": _ref(prior["id"]),
                    "google_event_id": ref or None,
                    "verified": True,
                    "reason": (
                        "Questo stesso evento era già stato creato. Dillo "
                        "così, senza crearne un altro e senza scusarti."
                    ),
                },
                provenance=[_ref(prior["id"])],
            )
    if taken != "go":
        return Observation(
            kind="tool", name="create_calendar_event", status="partial",
            payload={
                "status": "already_running",
                "reason": "Questa stessa cosa la sta già facendo un'altra richiesta.",
            },
        )

    candidate = {
        "id": f"epoch:{epoch}" if epoch else f"noepoch:{title[:40]}:{start}",
        "source_document_id": "ai_core_conversation",
        "title": title,
        "description": str(arguments.get("description") or "")[:_MAX_DESCRIPTION],
        "start_datetime": start,
        "end_datetime": end,
        "timezone": tz,
        "all_day": bool(arguments.get("all_day", False)),
    }
    location = arguments.get("location")
    if location:
        candidate["venue_name"] = str(location)[:_MAX_LOCATION]

    gateway = CalendarGateway(db)
    draft = await gateway.get("internal").create_from_candidate(
        user_id=uid, candidate=candidate,
    )
    draft_id = draft["id"]

    try:
        synced = await sync.sync_draft(user_id=uid, draft_id=draft_id)
    except GoogleCalendarAPIError as e:
        await commanded.settle(
            db, act, provider="calendar", external_ref="", accepted=False,
            observed=False, error_type=f"google_http_{e.status_code}",
        )
        return Observation(
            kind="tool", name="create_calendar_event", status="partial",
            payload={
                "status": "partial",
                "calendar_ref": _ref(draft_id),
                "reason": (
                    "Saved locally as ORA's own record of the commitment, but Google "
                    "Calendar sync failed. Do not claim it is on the user's Google "
                    "Calendar — only that it is recorded and can be retried."
                ),
                "failure_kind": f"google_http_{e.status_code}",
                "timezone": {"tz_name": tz, "authority": tz_authority},
            },
            provenance=[_ref(draft_id)],
        )
    except RuntimeError as e:
        await commanded.settle(
            db, act, provider="calendar", external_ref="", accepted=False,
            observed=False, error_type=type(e).__name__,
        )
        return Observation(
            kind="tool", name="create_calendar_event", status="partial",
            payload={
                "status": "partial",
                "calendar_ref": _ref(draft_id),
                "reason": (
                    "Saved locally; Google Calendar is not connected, so it is not "
                    "yet on the user's Google Calendar. Never claim otherwise."
                ),
                "failure_kind": type(e).__name__,
                "timezone": {"tz_name": tz, "authority": tz_authority},
            },
            provenance=[_ref(draft_id)],
        )

    # Accepted. Now go and look, because those are two different facts and
    # the whole point of this sprint is not to confuse them.
    seen, observed = await _read_back(sync, uid, synced)
    if observed:
        await _file_it_now(
            db, sync, uid, str(synced.get("google_calendar_id") or "primary"), seen,
        )
    await commanded.settle(
        db, act, provider="calendar",
        external_ref=str(synced.get("google_event_id") or ""),
        accepted=True, observed=observed,
    )
    return Observation(
        kind="tool", name="create_calendar_event",
        status="ok" if observed else "partial",
        payload={
            "status": "ok" if observed else "partial",
            "operation": "created",
            # Detto qui perche' e' qui che si e' deciso. Un turno che ha
            # aggiunto un impegno non puo' essere raccontato come uno
            # spostamento: l'evento di prima e' ancora dov'era, e la persona
            # che legge «ho aggiornato» non andra' a controllare.
            "moved_anything": False,
            "say_it_as": "aggiunto",
            "calendar_ref": _ref(draft_id),
            "google_event_id": synced.get("google_event_id"),
            "sync_status": synced.get("sync_status"),
            "verified": observed,
            "what_the_calendar_says": (
                {"title": seen.get("summary"), "start": (seen.get("start") or {})}
                if observed else None
            ),
            "reason": None if observed else (
                "Google ha preso la richiesta ma l'evento non risulta ancora "
                "quando lo si rilegge. Dillo così: è stato chiesto, non è "
                "confermato."
            ),
            "authority": act.basis,
            "timezone": {"tz_name": tz, "authority": tz_authority},
        },
        provenance=[_ref(draft_id)],
    )


async def update_calendar_event(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    """REVERSIBLE_WRITE. Requires an explicit canonical ref — never fuzzy
    title-based selection. If the AI is unsure which event, it must ask
    rather than guess (governed at the prompt/reasoning level, not here)."""
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    if not uid or db is None:
        return _fail("update_calendar_event", "NOT_CONFIGURED")

    draft_id = _strip_ref(arguments.get("calendar_ref"))
    if not draft_id:
        return _fail("update_calendar_event", "INVALID_INPUT", "calendar_ref required")

    existing = await db.calendar_event_drafts.find_one(
        {"id": draft_id, "user_id": uid}, {"_id": 0, "id": 1, "status": 1},
    )
    if not existing:
        return Observation(
            kind="tool", name="update_calendar_event", status="not_found",
            payload={
                "status": "not_found",
                "reason": "No owned calendar event matches this ref. Ask, do not guess.",
            },
        )
    if existing.get("status") == "cancelled":
        # reschedule_draft() itself refuses a cancelled draft (raises before
        # any DB write), but that refusal isn't a type the AI can act on
        # honestly — reject explicitly here, before touching consent or
        # Google, so the AI gets a clear reason instead of a generic
        # failure. Never reactivate, never recreate, never pick another
        # event — the AI must ask the user what they actually want.
        return Observation(
            kind="tool", name="update_calendar_event", status="rejected",
            payload={
                "status": "rejected",
                "calendar_ref": _ref(draft_id),
                "failure_kind": "event_cancelled",
                "reason": (
                    "This calendar event is cancelled and cannot be rescheduled. "
                    "Do not claim it was moved. Do not silently reactivate or "
                    "recreate it — if the user wants this commitment back, ask "
                    "them or propose creating a new event instead."
                ),
            },
        )

    sync = await _sync_service(db)
    instance_id = await _active_instance_id(sync, uid)
    try:
        await require_calendar_consent(db, user_id=uid, write=True, connector_instance_id=instance_id)
    except ConsentDenied:
        return Observation(
            kind="tool", name="update_calendar_event", status="consent_required",
            payload={"status": "consent_required", "calendar_ref": _ref(draft_id)},
        )
    except (CapabilityDisabled, CapabilityUnknown):
        return _fail("update_calendar_event", "CAPABILITY_UNAVAILABLE")

    # Il manico dell'evento com'e' adesso, per poter dire dopo se e' lo
    # stesso evento o un altro.
    before = await db.calendar_event_drafts.find_one(
        {"id": draft_id, "user_id": uid}, {"_id": 0, "google_event_id": 1},
    )
    before_handle = str((before or {}).get("google_event_id") or "")

    fields: Dict[str, Any] = {}
    for key in ("title", "start_datetime", "end_datetime", "location", "description"):
        if arguments.get(key) is not None:
            fields[key] = arguments[key]
    tz = arguments.get("timezone")
    if tz and is_valid_iana_timezone(str(tz)):
        fields["timezone"] = tz
    if not fields:
        return _needs("update_calendar_event", "fields", "che cosa cambia")

    # Same gate as create, for the same reason. «Sposta la visita alle 11» is
    # a decision the person has already made; the only thing worth checking is
    # that it is still their own event and still nothing that reaches anybody.
    #
    # "Their own" is a real question here in a way it is not for a new event.
    # An appointment somebody was invited to belongs to whoever called it, and
    # an instruction to move it is an instruction to reach into another
    # person's day — so it stops being a low-risk personal act and goes back
    # to asking, exactly as adding a guest does.
    from connected.ownership import reaches_other_people

    effect = commanded.calendar_effect(
        arguments,
        reaches_others=await reaches_other_people(db, uid, draft_id),
    )
    act = await commanded.assess(
        db, uid,
        capability="calendar.write",
        effect=effect,
        parameters={
            "calendar_ref": draft_id,
            **{k: str(v)[:200] for k, v in fields.items()},
        },
        summary="Cambiare un evento già in calendario",
        expected="L'evento risulta cambiato in calendario.",
        command=_user_command(arguments, runtime),
        answered_proposal=_answered_a_proposal(runtime),
    )
    if not act.may_execute:
        return _authority_required("update_calendar_event", act)

    taken = await commanded.begin(db, act)
    if taken == "already_done":
        return Observation(
            kind="tool", name="update_calendar_event", status="ok",
            payload={
                "status": "ok", "operation": "already_updated",
                "calendar_ref": _ref(draft_id), "verified": True,
                "reason": "Questo stesso cambio era già stato fatto.",
            },
            provenance=[_ref(draft_id)],
        )
    if taken != "go":
        return Observation(
            kind="tool", name="update_calendar_event", status="partial",
            payload={
                "status": "already_running",
                "reason": "Questa stessa cosa la sta già facendo un'altra richiesta.",
            },
        )

    try:
        updated = await sync.reschedule_draft(
            user_id=uid, draft_id=draft_id, fields=fields,
        )
    except (GoogleCalendarAPIError, RuntimeError) as e:
        # reschedule_draft() commits the local field patch unconditionally
        # before any Google-side step can raise — the new details are
        # already saved locally even though the Google push failed. Report
        # that honestly (partial, like create_calendar_event) rather than
        # implying nothing happened, which would be just as false a claim
        # in the other direction.
        await commanded.settle(
            db, act, provider="calendar", external_ref="", accepted=False,
            observed=False, error_type=type(e).__name__,
        )
        return Observation(
            kind="tool", name="update_calendar_event", status="partial",
            payload={
                "status": "partial",
                "calendar_ref": _ref(draft_id),
                "reason": (
                    "The new details were saved locally, but the change was not "
                    "confirmed on Google Calendar. Only claim the local update — "
                    "never that Google Calendar itself was updated."
                ),
                "failure_kind": type(e).__name__,
            },
        )

    if updated.get("sync_status") not in ("synced", None):
        await commanded.settle(
            db, act, provider="calendar",
            external_ref=str(updated.get("google_event_id") or ""),
            accepted=True, observed=False, error_type="sync_unconfirmed",
        )
        return Observation(
            kind="tool", name="update_calendar_event", status="partial",
            payload={
                "status": "partial",
                "calendar_ref": _ref(draft_id),
                "reason": (
                    "The new details were saved locally, but sync with Google "
                    "Calendar is not confirmed. Only claim the local update — "
                    "never that Google Calendar itself was updated."
                ),
            },
        )

    seen, observed = await _read_back(sync, uid, updated)
    if observed:
        await _file_it_now(
            db, sync, uid, str(updated.get("google_calendar_id") or "primary"), seen,
        )
    moved_as_asked = observed and _is_at(
        seen, fields.get("start_datetime"),
    ) and bool(before_handle and updated.get("google_event_id") == before_handle)
    await commanded.settle(
        db, act, provider="calendar",
        external_ref=str(updated.get("google_event_id") or ""),
        accepted=True, observed=observed,
    )
    return Observation(
        kind="tool", name="update_calendar_event",
        status="ok" if observed else "partial",
        payload={
            "status": "ok" if observed else "partial",
            "operation": "updated",
            "moved_anything": True,
            "say_it_as": "spostato",
            # Lo slot vecchio e' libero e quello nuovo e' pieno — che e'
            # l'unica cosa che la persona puo' controllare. Si legge da un
            # solo colpo d'occhio: e' lo *stesso* evento del provider, e
            # adesso e' all'ora richiesta; quindi dov'era prima non c'e'
            # piu'. Se l'identita' non fosse conservata questa deduzione
            # non varrebbe, ed e' per questo che sta qui accanto.
            "old_slot_empty": bool(moved_as_asked),
            "new_slot_has_it": bool(moved_as_asked),
            # L'identita' del provider e' la prova che si e' spostato un
            # evento invece di crearne un altro. Se il manico e' cambiato,
            # qualunque cosa sia successa non e' uno spostamento, e non va
            # raccontata come tale.
            "provider_identity_preserved": bool(
                before_handle and updated.get("google_event_id") == before_handle
            ),
            "calendar_ref": _ref(draft_id),
            "google_event_id": updated.get("google_event_id"),
            "sync_status": updated.get("sync_status"),
            "verified": observed,
            "what_the_calendar_says": (
                {"title": seen.get("summary"), "start": (seen.get("start") or {})}
                if observed else None
            ),
            "authority": act.basis,
        },
        provenance=[_ref(draft_id)],
    )


async def cancel_calendar_event(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    """
    Togli un impegno dal calendario, dalla conversazione.

        UN SOLO MODO DI TOGLIERE UN IMPEGNO.

    Questa funzione aveva un percorso suo: cancellava sul provider e si
    fidava della risposta, senza rileggere. Due percorsi di cancellazione
    vuol dire due idee di cosa significhi «eliminato», e quella con la
    verifica piu' debole vince sempre — perche' e' quella che risponde di
    si' anche quando non e' vero.

    Quindi qui non c'e' piu' niente che cancelli: si trova di quale evento si
    sta parlando e si chiede a chi lo sa fare. Autorita' legata a quel manico,
    cancellazione sul provider, rilettura, e «eliminato» solo dopo.

    Funziona anche sugli eventi che ORA non ha creato: prima serviva per forza
    una bozza nostra, e un appuntamento messo dalla persona su Google non si
    poteva togliere parlando.
    """
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    if not uid or db is None:
        return _fail("cancel_calendar_event", "NOT_CONFIGURED")

    from home.calendar_event import delete_event, event_detail

    # Di cosa si sta parlando: la bozza nostra, oppure direttamente il manico
    # che l'evento ha su Google. Entrambi sono nomi della stessa cosa.
    ref = _strip_ref(arguments.get("calendar_ref")) or str(
        arguments.get("google_event_id") or ""
    ).strip()
    if not ref:
        return _fail(
            "cancel_calendar_event", "INVALID_INPUT", "calendar_ref required",
        )

    handle = ref
    draft = await db.calendar_event_drafts.find_one(
        {"id": ref, "user_id": uid},
        {"_id": 0, "id": 1, "status": 1, "google_event_id": 1, "title": 1},
    )
    if draft:
        if draft.get("status") == "cancelled":
            return Observation(
                kind="tool", name="cancel_calendar_event", status="ok",
                payload={
                    "status": "ok", "operation": "already_cancelled",
                    "calendar_ref": _ref(ref), "verified": True,
                    "say_it_as": "eliminato",
                },
                provenance=[_ref(ref)],
            )
        handle = str(draft.get("google_event_id") or "") or ref

    detail = await event_detail(db, uid, handle)
    if detail is None:
        return Observation(
            kind="tool", name="cancel_calendar_event", status="not_found",
            payload={
                "status": "not_found",
                "reason": "Non c'è nessun impegno che corrisponda a questo.",
            },
        )

    out = await delete_event(db, uid, handle, confirmed_title=detail["title"])

    if not out.get("ok"):
        why = str(out.get("reason") or "delete_failed")
        return Observation(
            kind="tool", name="cancel_calendar_event", status="failed",
            payload={
                "status": "failed",
                "failure_kind": why,
                "calendar_ref": _ref(ref),
                # La frase che segue e' l'unica difesa contro il fallimento
                # peggiore di tutti: dire che e' stato tolto quando c'e'
                # ancora, e lasciare che la persona non si presenti.
                "reason": (
                    "La cancellazione non è stata confermata. Non dire che è "
                    "stato eliminato: è ancora in calendario."
                ),
                "say_it_as": "",
            },
            provenance=[_ref(ref)],
        )

    return Observation(
        kind="tool", name="cancel_calendar_event", status="ok",
        payload={
            "status": "ok",
            # La parola resta quella del tool: chi legge questa osservazione
            # e' addestrato su «cancelled», e cambiargliela sotto per un
            # dettaglio di implementazione sarebbe un cambio di contratto
            # travestito da rinomina.
            "operation": (
                "already_cancelled"
                if out.get("operation") == "already_gone" else "cancelled"
            ),
            "calendar_ref": _ref(ref),
            "google_event_id": out.get("google_event_id"),
            "deleted_on_google": bool(out.get("deleted_on_google")),
            "verified": bool(out.get("verified")),
            "say_it_as": out.get("say_it_as") or "eliminato",
            "what_was_removed": detail["title"],
        },
        provenance=[_ref(ref)],
    )
