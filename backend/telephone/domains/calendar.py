"""
L'esito di una telefonata, scritto nel calendario.

    QUI FINISCE LA DIFFERENZA FRA «HANNO DETTO DI SÌ» E «È SPOSTATO».

Fino a questo file esiste solo un resoconto: la controparte ha confermato, il
backend l'ha validato, ed è scritto da qualche parte che la missione è
riuscita. Il calendario però è ancora alle sedici — ed è il calendario che
qualcuno guarda la mattina dopo. Questo è l'unico posto in cui la telefonata
diventa un fatto.

    E PROPRIO PER QUESTO NON SI FIDA DI NIENTE.

Tre controlli, e passano tutti prima di toccare qualsiasi cosa:

  - **l'autorità**: questa missione poteva spostare, e quello che è stato
    confermato è un orario e nient'altro;
  - **l'identità**: l'evento è ancora quello su cui la missione è stata
    scritta — stessa partenza di quando si è composto il numero, e stessa ora
    di quella che la controparte ha detto di aver spostato;
  - **la traduzione**: «alle 18:00» diventa una data e un'ora vere, con il
    fuso dell'evento e la durata che l'evento aveva già.

Se uno dei tre non passa non si scrive e non si insiste: si dice che cosa non
tornava. Un calendario sbagliato è peggio di un calendario vecchio, perché
quello vecchio almeno si nota.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ora.telephone.apply.calendar")

#     IL CALENDARIO E' UN ADATTATORE COME GLI ALTRI, E LO DICHIARA.
# Questi due nomi sono il contratto: chi applica legge il registro, chiede
# `(dominio, operazione)` e riceve un modulo che risponde. Nessun `if` con
# scritto «calendar» da nessuna parte fuori di qui.
DOMAIN = "calendar"
OPERATIONS = ("reschedule", "book", "cancel")

# Che cosa una telefonata di spostamento può aver confermato. Chiusa di
# proposito: una chiave che non è qui dentro è una cosa che non si è chiesto
# il permesso di cambiare, e non la si scrive «visto che c'era».
RESCHEDULE_KEYS = frozenset({"appointment_date", "old_time", "new_time"})

# Che cosa può aver confermato una disdetta: quale appuntamento, e nient'altro.
# Non c'è un valore nuovo da scrivere — c'è un evento da riconoscere.
CANCEL_KEYS = frozenset({"appointment_date", "appointment_time"})

# E una prenotazione: quando, e quanto dura se l'hanno detto.
BOOK_KEYS = frozenset({"appointment_date", "appointment_time", "duration_minutes"})

# Da dove viene un evento nato da una telefonata. Insieme al nome della
# missione è la coppia che rende impossibile crearne due per la stessa
# commissione.
PHONE_CALL_SOURCE = "ora_phone_call"

# Quanto lontano può finire un appuntamento spostato.
#
#     DUE SETTIMANE NON SONO UNA REGOLA DI BUON SENSO: SONO UN PARAFULMINE.
#
# Il mandato dice «fra giovedì e sabato» e nessun confronto di testo può
# decidere se le 18:00 del ventisette ci stiano dentro — provarci produce
# falsi allarmi, e un controllo di sicurezza che grida a vuoto insegna a
# ignorarlo. Questo limite non prova a interpretare il mandato: prende l'unico
# errore che si può riconoscere senza capire la frase, cioè un salto che con
# uno spostamento non c'entra niente — l'anno sbagliato, il mese sbagliato.
FAR_ENOUGH_DAYS = 14

# Quanto dura un appuntamento di cui non si sa la fine. La stessa ora che
# significa «un appuntamento» in tutto il resto del progetto.
DEFAULT_MINUTES = 60


class Verdict:
    """Che cosa è successo, e perché. Non un'eccezione: una risposta."""

    def __init__(
        self,
        status: str,
        *,
        writes: Optional[List[str]] = None,
        error: str = "",
        fields: Optional[Dict[str, str]] = None,
    ) -> None:
        self.status = status          # applied | skipped | conflict | failed
        self.writes = writes or []
        self.error = error
        self.fields = fields or {}


# ---------------------------------------------------------------------------
# La parte che non tocca niente
# ---------------------------------------------------------------------------


def translate(binding, outcome) -> Tuple[Dict[str, str], str]:
    """
    Da quello che la controparte ha confermato a campi veri, o al motivo
    per cui non si può.

        È PURA APPOSTA.

    Nessun database, nessuna rete: solo il legame e l'esito. È la parte in cui
    si può sbagliare di calcolo, ed è la parte che si può provare senza far
    finta di avere un calendario.

    Tre operazioni, tre traduzioni diverse: spostare ricalcola un orario
    conservando la durata, disdire non calcola niente e verifica soltanto che
    si stia parlando dello stesso appuntamento, prenotare costruisce da zero
    ciò che non c'era.
    """
    fare = binding.target.operation
    if fare == "reschedule":
        return _translate_reschedule(binding, outcome)
    if fare == "cancel":
        return _translate_cancel(binding, outcome)
    if fare == "book":
        return _translate_book(binding, outcome)
    return {}, f"operazione non applicabile: {fare}"


def _translate_reschedule(binding, outcome) -> Tuple[Dict[str, str], str]:
    cambiamenti = dict(outcome.confirmed_changes or {})
    fuori = set(cambiamenti) - RESCHEDULE_KEYS
    if fuori:
        #     QUELLO CHE NON È STATO CHIESTO NON SI SCRIVE.
        # Una telefonata per spostare che torna anche con un indirizzo nuovo
        # non ha l'autorità per cambiarlo: quel dato si racconta, non si applica.
        return {}, "confermate cose fuori dalla missione: " + ", ".join(sorted(fuori))

    ora_nuova = _hhmm(cambiamenti.get("new_time"))
    if not ora_nuova:
        return {}, "non c'è un orario nuovo utilizzabile"

    partenza = _read(binding.expected.get("start_datetime"))
    if partenza is None:
        return {}, "l'appuntamento di partenza non ha un orario leggibile"

    giorno = _day(cambiamenti.get("appointment_date")) or partenza.date()
    nuova = partenza.replace(
        year=giorno.year, month=giorno.month, day=giorno.day,
        hour=ora_nuova[0], minute=ora_nuova[1], second=0, microsecond=0,
    )
    nuova = _same_wall_clock_in(nuova, binding.expected.get("timezone", ""))

    if abs((nuova.date() - partenza.date()).days) > FAR_ENOUGH_DAYS:
        return {}, "la data confermata è troppo lontana per essere uno spostamento"
    if nuova == partenza:
        return {}, "l'orario confermato è quello che c'era già"

    # La durata è quella che l'appuntamento aveva: spostare non vuol dire
    # accorciare, e nessuno al telefono ha parlato di quanto dura.
    fine = _read(binding.expected.get("end_datetime"))
    quanto = (
        (fine - partenza) if fine and fine > partenza
        else timedelta(minutes=DEFAULT_MINUTES)
    )
    return {
        "start_datetime": nuova.isoformat(),
        "end_datetime": (nuova + quanto).isoformat(),
    }, ""


# ---------------------------------------------------------------------------
# La parte che tocca
# ---------------------------------------------------------------------------


async def apply(db, *, call, binding, outcome) -> Verdict:
    """
    Scrive nel calendario quello che la controparte ha confermato.

    Una porta sola per tre operazioni, e dentro tre percorsi che non si
    somigliano: il primo ricalcola, il secondo toglie, il terzo crea. Quello
    che hanno in comune sono i controlli — autorità, consenso, identità — e
    quelli non si saltano per nessuna delle tre.
    """
    fare = binding.target.operation
    if fare == "cancel":
        return await _apply_cancel(db, call=call, binding=binding, outcome=outcome)
    if fare == "book":
        return await _apply_book(db, call=call, binding=binding, outcome=outcome)
    if fare != "reschedule":
        return Verdict("skipped", error=f"operazione non applicabile: {fare}")
    return await _apply_reschedule(db, call=call, binding=binding, outcome=outcome)


async def _apply_reschedule(db, *, call, binding, outcome) -> Verdict:
    """Sposta l'appuntamento, se è ancora quello di cui si stava parlando."""
    ref = binding.target.entity_id
    draft = await db.calendar_event_drafts.find_one(
        {"id": ref, "user_id": binding.owner_id},
        {"_id": 0, "id": 1, "status": 1, "start_datetime": 1,
         "end_datetime": 1, "timezone": 1},
    )
    if not draft:
        return Verdict("failed", error="l'appuntamento non è più nel calendario")
    if draft.get("status") == "cancelled":
        return Verdict("skipped", error="l'appuntamento è stato disdetto nel frattempo")

    #     L'EVENTO È ANCORA QUELLO DI ALLORA?
    #
    # Due domande diverse con la stessa risposta se va bene. La prima la fa il
    # legame: l'appuntamento parte ancora dove partiva quando abbiamo composto
    # il numero. La seconda la fa la controparte: ha detto di aver spostato
    # quello delle sedici, e se in calendario ci sono le nove non stavano
    # parlando di questo. Se una delle due non torna, la telefonata riguarda un
    # evento che non esiste più — e sopra a un evento del genere non si scrive.
    atteso = (binding.expected.get("start_datetime") or "").strip()
    adesso = str(draft.get("start_datetime") or "").strip()
    if atteso and adesso and not _same_moment(atteso, adesso):
        return Verdict(
            "conflict",
            error="l'appuntamento è cambiato dopo la telefonata",
        )

    detta = _hhmm((outcome.confirmed_changes or {}).get("old_time"))
    if detta is not None:
        vero = _read(adesso or atteso)
        if vero is not None and (vero.hour, vero.minute) != detta:
            return Verdict(
                "conflict",
                error=(
                    "la controparte ha spostato le "
                    f"{detta[0]:02d}:{detta[1]:02d}, in calendario c'erano le "
                    f"{vero.hour:02d}:{vero.minute:02d}"
                ),
            )

    campi, perche = translate(binding, outcome)
    if perche:
        return Verdict("skipped", error=perche)

    negato = _what_the_authority_says(binding, outcome)
    if negato is not None:
        return negato

    calendario = _the_calendar(db)

    #     IL SÌ ALLA TELEFONATA NON È IL SÌ AL CALENDARIO.
    #
    # Sono due autorità diverse e vengono da due momenti diversi: una la dà la
    # persona quando autorizza la chiamata, l'altra è il permesso col quale il
    # calendario è stato collegato — e può essere stato revocato nel frattempo,
    # anche stamattina. Ogni altra scrittura in calendario passa da qui; questa
    # è arrivata per una strada nuova, e la strada nuova non è un motivo per
    # saltare il cancello.
    negato = await _consent_missing(db, calendario, binding.owner_id)
    if negato:
        return Verdict("failed", error=negato, fields=campi)

    try:
        aggiornato = await calendario.reschedule_draft(
            user_id=binding.owner_id, draft_id=ref, fields=campi,
        )
    except LookupError:
        return Verdict("failed", error="l'appuntamento non è più nel calendario")
    except Exception as e:
        #     IL LOCALE PUÒ ESSERE GIÀ CAMBIATO ANCHE SE GOOGLE NO.
        # `reschedule_draft` scrive i campi prima di provare a spingerli, e lo
        # fa apposta: l'intenzione non si perde. Qui però non si può dire
        # «spostato», perché il calendario che la persona apre è quello di
        # Google. Si dice che non è confermato, che è la verità.
        logger.info("spostamento non riuscito: %s", type(e).__name__)
        return Verdict(
            "failed",
            error=f"il calendario non ha accettato lo spostamento ({type(e).__name__})",
            fields=campi,
        )

    stato = str((aggiornato or {}).get("sync_status") or "")
    if stato not in ("synced", "local_only", ""):
        return Verdict(
            "failed",
            error="lo spostamento non risulta confermato su Google Calendar",
            fields=campi,
        )
    return Verdict("applied", writes=[f"calendar:{ref}"], fields=campi)


async def _consent_missing(db, calendario, owner_id: str) -> str:
    """
    Il permesso di scrivere in calendario, o perché non c'è.

    Torna una stringa vuota quando si può — e una frase da dire a una persona
    quando no. Il consenso si dà per singolo account collegato, quindi si
    chiede per quello attivo: chiederlo in generale vorrebbe dire accettare un
    sì dato per un altro calendario.
    """
    from permissions.errors import (
        CapabilityDisabled, CapabilityUnknown, ConsentDenied,
    )
    from permissions.models import INSTANCE_WILDCARD

    try:
        inst = await calendario._instance_for_user(owner_id)
    except Exception:
        inst = None
    quale = str(inst["id"]) if inst else INSTANCE_WILDCARD

    from connectors.google_calendar.consent import require_calendar_consent

    try:
        await require_calendar_consent(
            db, user_id=owner_id, write=True, connector_instance_id=quale,
        )
    except ConsentDenied:
        return "il permesso di scrivere nel calendario non è attivo"
    except (CapabilityDisabled, CapabilityUnknown):
        return "il calendario non è collegato"
    return ""


async def reconcile(db, *, call, binding, outcome) -> Verdict:
    """
    Che cosa è successo davvero, per un'applicazione rimasta a metà.

        UN RECORD `pending` NON DICE SE LA SCRITTURA È ANDATA.

    Dice solo che qualcuno l'aveva presa in carico e non è tornato. Fra il
    momento in cui il record nasce e quello in cui si chiude ci sono due
    scritture — la bozza locale e Google — e un processo che muore in mezzo
    lascia esattamente questa domanda aperta.

    A rispondere non è una supposizione: è il calendario. Si guarda dov'è
    l'appuntamento adesso e si confronta con le due sole posizioni che hanno
    un significato.

      - **è già dove doveva arrivare** → la scrittura era andata, e il record
        era solo rimasto indietro. Si chiude, e non si tocca niente;
      - **è ancora dove stava** → la scrittura non è mai partita. Si riprova,
        **una volta**, passando dalla stessa porta di sempre;
      - **è altrove** → qualcuno l'ha spostato nel frattempo. Conflitto, e
        sopra non si scrive.

    Non esiste un quarto caso, e non esiste un ramo che indovina.
    """
    fare = binding.target.operation
    if fare == "cancel":
        return await _reconcile_cancel(db, call=call, binding=binding, outcome=outcome)
    if fare == "book":
        return await _reconcile_book(db, call=call, binding=binding, outcome=outcome)
    if fare != "reschedule":
        return Verdict("skipped", error=f"operazione non applicabile: {fare}")

    campi, perche = translate(binding, outcome)
    if perche:
        return Verdict("skipped", error=perche)

    negato = _what_the_authority_says(binding, outcome)
    if negato is not None:
        return negato

    draft = await db.calendar_event_drafts.find_one(
        {"id": binding.target.entity_id, "user_id": binding.owner_id},
        {"_id": 0, "id": 1, "status": 1, "start_datetime": 1},
    )
    if not draft:
        return Verdict("failed", error="l'appuntamento non è più nel calendario")
    if draft.get("status") == "cancelled":
        return Verdict("skipped", error="l'appuntamento è stato disdetto nel frattempo")

    adesso = str(draft.get("start_datetime") or "").strip()

    #     GIÀ ARRIVATO: SI CHIUDE IL RECORD, NON SI RISCRIVE L'EVENTO.
    # È il caso del processo morto **dopo** la scrittura, ed è quello in cui
    # riprovare farebbe il danno: una seconda scrittura identica è inutile, e
    # una seconda scrittura su un calendario che nel frattempo è cambiato di
    # nuovo sarebbe un sopruso.
    if _same_moment(adesso, campi["start_datetime"]):
        return Verdict(
            "applied",
            writes=[f"calendar:{binding.target.entity_id}"],
            fields=campi,
        )

    #     ANCORA FERMO: LA SCRITTURA NON È MAI PARTITA.
    # Un tentativo solo, e dalla porta normale — con dentro i suoi controlli
    # di autorità, consenso e identità, che non si saltano perché è un
    # secondo giro.
    if _same_moment(adesso, binding.expected.get("start_datetime", "")):
        return await apply(db, call=call, binding=binding, outcome=outcome)

    return Verdict(
        "conflict",
        error="l'appuntamento è cambiato dopo la telefonata",
    )


def _what_the_authority_says(binding, outcome) -> Optional[Verdict]:
    """
    Il giudice, chiamato prima di toccare qualsiasi cosa.

        CHI HA PARLATO RIPORTA. CHI STA QUI GIUDICA.

    Quello che la controparte ha confermato viene tradotto in una data e
    un'ora vere e confrontato con l'autorita' strutturata. Non si legge una
    frase e non si interpreta niente: due oggetti, una risposta, sempre la
    stessa.

    Torna `None` quando si puo' procedere — compreso il caso in cui non c'e'
    un'autorita' strutturata da consultare. Quello non e' un permesso: e' una
    missione piu' vecchia, dove a decidere restano i controlli che c'erano
    prima. Trattarlo come un no vorrebbe dire rompere tutto quello che
    funziona.
    """
    from telephone.authority import Proposal, a_slot_from, evaluate_authority

    regole = getattr(binding, "authority", None)
    if regole is None:
        return None

    cambiamenti = dict(getattr(outcome, "confirmed_changes", None) or {})
    quando = a_slot_from(
        cambiamenti.get("appointment_date", ""),
        cambiamenti.get("new_time") or cambiamenti.get("appointment_time", ""),
        cambiamenti.get("duration_minutes", 0) or 0,
    )
    responso = evaluate_authority(
        Proposal(
            operation=binding.target.operation,
            slot=quando if quando.is_real() else None,
            entity_id=binding.target.entity_id,
        ),
        regole,
    )
    if responso.verdict in ("allowed", "invalid"):
        #     `invalid` NON E' UN NO.
        # Vuol dire che il giudice non aveva abbastanza per pronunciarsi: i
        # controlli di sempre — identita', concorrenza, traduzione — sono gia'
        # passati, e sono loro a rispondere.
        return None

    logger.info("l'autorita' non consente questa scrittura: %s", responso.code)
    return Verdict("skipped", error=responso.says or responso.code)


async def look(db, *, binding) -> Optional[Dict[str, Any]]:
    """
    Dov'e' l'appuntamento adesso, secondo lo stato canonico.

        CHI DECIDE GUARDA. NON SUPPONE.

    E' il terzo dovere del contratto, e finora viveva dentro `apply` e
    `reconcile` come due letture separate. Qui e' una sola, e un dominio nuovo
    la trova gia' scritta.
    """
    ref = binding.target.entity_id or binding.created_entity_id
    if not ref:
        return None
    return await db.calendar_event_drafts.find_one(
        {"id": ref, "user_id": binding.owner_id}, {"_id": 0},
    )


def remembers(row: Dict[str, Any]) -> Dict[str, str]:
    """
    Com'era l'appuntamento quando si è deciso di telefonare.

        `expected` NON È UN DOPPIONE: È LA DATA DI SCADENZA DELLA MISSIONE.

    Sono i campi che `bind_a_calendar_event` fotografava a mano da sempre.
    Averli qui vuol dire che chi lega non deve sapere che cosa sia un
    appuntamento — glielo dice il dominio, come lo dirà ogni altro.
    """
    return {
        "start_datetime": str((row or {}).get("start_datetime") or ""),
        "end_datetime": str((row or {}).get("end_datetime") or ""),
        "timezone": str((row or {}).get("timezone") or "Europe/Rome"),
        "title": str((row or {}).get("title") or "")[:120],
    }


def detect_conflict(binding, row: Dict[str, Any]) -> Optional[Verdict]:
    """
    L'appuntamento è ancora quello su cui la missione era stata scritta?

    Il settimo dovere, col nome che ha nel contratto. La domanda che dipende
    anche da quello che la controparte ha detto resta dov'era — la fa
    `_still_the_same_appointment`, che ha in mano pure l'esito.
    """
    atteso = (binding.expected.get("start_datetime") or "").strip()
    adesso = str((row or {}).get("start_datetime") or "").strip()
    if atteso and adesso and not _same_moment(atteso, adesso):
        return Verdict("conflict", error="l'appuntamento è cambiato dopo la telefonata")
    return None


def says(operation: str, fields: Dict[str, str]) -> str:
    """Come si racconta a chi non c'era. Il calendario parla di orari."""
    quando = _read(fields.get("start_datetime", ""))
    ora = quando.strftime("%H:%M") if quando else ""
    return {
        "reschedule": f"Appuntamento spostato{' alle ' + ora if ora else ''}.",
        "book": f"Prenotazione effettuata{' alle ' + ora if ora else ''}.",
        "cancel": "Appuntamento disdetto.",
    }.get(operation, "Fatto.")


def _the_calendar(db):
    """
    Il servizio che sa scrivere in calendario.

        SI PASSA DALLA STESSA PORTA DI SEMPRE.

    `reschedule_draft` è già il punto unico da cui passa ogni spostamento —
    tiene il lucchetto per evento, aggiorna la bozza di ORA e spinge su Google
    senza mai creare un secondo evento per la stessa intenzione. Scrivere in
    Mongo da qui sarebbe stato più corto e avrebbe saltato tutto questo.
    """
    from deps import get_google_calendar_service
    from documents.intelligence.google_sync import GoogleCalendarSyncService

    return GoogleCalendarSyncService(
        db=db, google_calendar_service=get_google_calendar_service(),
    )


# ---------------------------------------------------------------------------
# Orologi
# ---------------------------------------------------------------------------


def _read(iso: Optional[str]) -> Optional[datetime]:
    testo = (iso or "").strip()
    if not testo:
        return None
    try:
        return datetime.fromisoformat(testo.replace("Z", "+00:00"))
    except Exception:
        return None


def _same_moment(a: str, b: str) -> bool:
    """
    Se due scritture indicano lo stesso istante.

    Non un confronto di stringhe: `+02:00` e `Z` scrivono lo stesso momento in
    due modi, e una sincronizzazione che riscrive il fuso non è qualcuno che
    ha spostato l'appuntamento.
    """
    x, y = _read(a), _read(b)
    if x is None or y is None:
        return a.strip() == b.strip()
    if (x.tzinfo is None) != (y.tzinfo is None):
        return x.replace(tzinfo=None) == y.replace(tzinfo=None)
    return x == y


def _hhmm(valore: Any) -> Optional[Tuple[int, int]]:
    """«18:00» → (18, 0). Qualunque altra cosa → niente."""
    testo = str(valore or "").strip()
    if ":" not in testo:
        return None
    ore, _, minuti = testo.partition(":")
    try:
        h, m = int(ore), int(minuti[:2])
    except ValueError:
        return None
    return (h, m) if 0 <= h <= 23 and 0 <= m <= 59 else None


def _day(valore: Any):
    testo = str(valore or "").strip()[:10]
    try:
        return datetime.strptime(testo, "%Y-%m-%d").date()
    except ValueError:
        return None


def _same_wall_clock_in(quando: datetime, fuso: str):
    """
    Le 18:00 di quel giorno, in quel fuso.

        UNO SPOSTAMENTO PUÒ ATTRAVERSARE UN CAMBIO D'ORA.

    Riusare l'offset di partenza — `+02:00` — funziona finché l'appuntamento
    resta nella stessa stagione, e a fine ottobre sposta l'appuntamento di
    un'ora senza che nessuno l'abbia chiesto. Ricostruire l'orario dentro la
    zona lo evita; se la zona non si sa, si tiene quello che c'era, che è
    comunque meglio che indovinare.
    """
    nome = (fuso or "").strip()
    if not nome or quando.tzinfo is None:
        return quando
    try:
        from zoneinfo import ZoneInfo

        return quando.replace(tzinfo=ZoneInfo(nome))
    except Exception:
        return quando


# ===========================================================================
# DISDIRE
# ===========================================================================
#
#     DISDIRE NON CALCOLA NIENTE. DEVE SOLO ESSERE SICURO DI CHI.
#
# Uno spostamento sbagliato si vede: l'appuntamento è nel giorno sbagliato e
# qualcuno se ne accorge. Una disdetta sbagliata non si vede — l'appuntamento
# semplicemente non c'è più, e ci si accorge il giorno in cui non ci si
# presenta a quello giusto. Quindi qui non c'è nessuna aritmetica da
# verificare: c'è solo l'identità, e si controlla due volte.


def _translate_cancel(binding, outcome) -> Tuple[Dict[str, str], str]:
    """Non ci sono campi nuovi da scrivere: c'è un evento da riconoscere."""
    cambiamenti = dict(outcome.confirmed_changes or {})
    fuori = set(cambiamenti) - CANCEL_KEYS
    if fuori:
        return {}, "confermate cose fuori dalla missione: " + ", ".join(sorted(fuori))
    if not binding.target.entity_id:
        return {}, "non c'è un appuntamento da disdire"
    return {"status": "cancelled"}, ""


async def _apply_cancel(db, *, call, binding, outcome) -> Verdict:
    """Toglie l'appuntamento, se è ancora quello di cui si stava parlando."""
    ref = binding.target.entity_id
    draft = await db.calendar_event_drafts.find_one(
        {"id": ref, "user_id": binding.owner_id},
        {"_id": 0, "id": 1, "status": 1, "start_datetime": 1, "title": 1,
         "google_event_id": 1, "google_calendar_id": 1},
    )
    if not draft:
        return Verdict("failed", error="l'appuntamento non è più nel calendario")
    if draft.get("status") == "cancelled":
        #     ERA GIÀ VIA, E NON L'ABBIAMO TOLTO NOI.
        # Non è un fallimento e non è un successo da rivendicare: è una cosa
        # che non c'era più da fare. Dirlo è più onesto che segnarsi il merito.
        return Verdict("skipped", error="l'appuntamento era già disdetto")

    campi, perche = translate(binding, outcome)
    if perche:
        return Verdict("skipped", error=perche)

    negato = _what_the_authority_says(binding, outcome)
    if negato is not None:
        return negato

    verdetto = _still_the_same_appointment(binding, outcome, draft)
    if verdetto is not None:
        return verdetto

    calendario = _the_calendar(db)
    negato = await _consent_missing(db, calendario, binding.owner_id)
    if negato:
        return Verdict("failed", error=negato, fields=campi)

    try:
        await _remove_it(db, calendario, binding.owner_id, draft)
    except Exception as e:
        logger.info("disdetta non riuscita: %s", type(e).__name__)
        return Verdict(
            "failed",
            error=f"il calendario non ha accettato la disdetta ({type(e).__name__})",
            fields=campi,
        )
    return Verdict("applied", writes=[f"calendar:{ref}"], fields=campi)


async def _remove_it(db, calendario, owner_id: str, draft: Dict[str, Any]) -> None:
    """
    Via da Google, e poi via da qui.

        PRIMA FUORI, POI DENTRO.

    L'ordine non è indifferente. Segnare prima la bozza come disdetta e poi
    fallire su Google lascerebbe ORA convinta che sia sparito mentre alla
    persona squilla ancora il promemoria. Al contrario, se Google accetta e la
    bozza non si aggiorna, il prossimo recupero se ne accorge e chiude — che è
    esattamente il caso per cui il recupero esiste.
    """
    handle = str(draft.get("google_event_id") or "")
    if handle:
        inst = await calendario._instance_for_user(owner_id)
        if not inst:
            raise RuntimeError("Google Calendar non collegato")
        access = await calendario.gcal._get_access_token(user_id=owner_id, instance=inst)
        cal_id = str(
            draft.get("google_calendar_id")
            or (inst.get("metadata") or {}).get("default_calendar_id") or ""
        )
        if not cal_id:
            raise RuntimeError("Nessun calendario Google disponibile")
        await calendario.gcal.provider.delete_event(
            access_token=access, calendar_id=cal_id, event_id=handle,
        )

    from datetime import timezone as _tz

    await db.calendar_event_drafts.update_one(
        {"id": draft["id"], "user_id": owner_id},
        {"$set": {
            "status": "cancelled",
            "sync_status": "synced" if handle else "local_only",
            "updated_at": datetime.now(_tz.utc).isoformat(),
        }},
    )


async def _reconcile_cancel(db, *, call, binding, outcome) -> Verdict:
    """
    Una disdetta rimasta a metà: dov'è finito l'appuntamento?

    Due sole posizioni che contano, come per lo spostamento. Non c'è più — o
    risulta disdetto — e allora la scrittura era andata. È ancora lì dov'era,
    e allora non è mai partita: si riprova una volta.
    """
    draft = await db.calendar_event_drafts.find_one(
        {"id": binding.target.entity_id, "user_id": binding.owner_id},
        {"_id": 0, "id": 1, "status": 1, "start_datetime": 1},
    )
    if not draft or draft.get("status") == "cancelled":
        #     QUI «NON C'È PIÙ» VUOL DIRE RIUSCITA, NON GUASTO.
        # È l'opposto dello spostamento, e si vede bene perché le due
        # riconciliazioni sono due funzioni invece di una con un flag dentro.
        return Verdict(
            "applied",
            writes=[f"calendar:{binding.target.entity_id}"],
            fields={"status": "cancelled"},
        )

    atteso = (binding.expected.get("start_datetime") or "").strip()
    adesso = str(draft.get("start_datetime") or "").strip()
    if atteso and adesso and not _same_moment(atteso, adesso):
        return Verdict("conflict", error="l'appuntamento è cambiato dopo la telefonata")

    return await _apply_cancel(db, call=call, binding=binding, outcome=outcome)


def _still_the_same_appointment(binding, outcome, draft) -> Optional[Verdict]:
    """
    Due domande sull'identità, e bastano tutte e due.

        UNA DISDETTA SBAGLIATA NON SI VEDE FINCHÉ NON TE NE ACCORGI.

    La prima la fa il legame: l'appuntamento parte ancora da dove partiva
    quando abbiamo composto il numero. La seconda la fa la controparte: ha
    detto di aver disdetto quello delle sedici, e se in calendario ci sono le
    nove non stavano parlando di questo.
    """
    atteso = (binding.expected.get("start_datetime") or "").strip()
    adesso = str(draft.get("start_datetime") or "").strip()
    if atteso and adesso and not _same_moment(atteso, adesso):
        return Verdict("conflict", error="l'appuntamento è cambiato dopo la telefonata")

    detta = _hhmm((outcome.confirmed_changes or {}).get("appointment_time"))
    if detta is not None:
        vero = _read(adesso or atteso)
        if vero is not None and (vero.hour, vero.minute) != detta:
            return Verdict(
                "conflict",
                error=(
                    f"la controparte ha disdetto le {detta[0]:02d}:{detta[1]:02d}, "
                    f"in calendario c'erano le {vero.hour:02d}:{vero.minute:02d}"
                ),
            )
    return None


# ===========================================================================
# PRENOTARE
# ===========================================================================
#
#     PRENOTARE È L'UNICA DELLE TRE CHE PUÒ CREARE UN DOPPIONE.
#
# Spostare e disdire agiscono su una cosa che esiste: al massimo la toccano
# due volte, e la seconda non cambia niente. Creare invece, ripetuto, produce
# due appuntamenti — e due appuntamenti dallo stesso dentista alle 18:00 sono
# una telefonata in più che qualcuno dovrà fare per disdirne uno.
#
# La difesa non è un controllo nostro: è il nome. L'evento nasce portando
# addosso il nome della missione che lo ha creato, e il livello che crea
# eventi riconosce quel nome e restituisce quello di prima invece di farne un
# secondo. Un controllo si può dimenticare di chiamarlo; un nome no.


def _translate_book(binding, outcome) -> Tuple[Dict[str, str], str]:
    """Da «venerdì alle 10» a un appuntamento intero, pronto da creare."""
    cambiamenti = dict(outcome.confirmed_changes or {})
    fuori = set(cambiamenti) - BOOK_KEYS
    if fuori:
        return {}, "confermate cose fuori dalla missione: " + ", ".join(sorted(fuori))

    voluto = binding.desired or {}
    fuso = str(voluto.get("timezone") or "Europe/Rome")

    giorno = _day(cambiamenti.get("appointment_date"))
    ora = _hhmm(cambiamenti.get("appointment_time"))
    if giorno is None or ora is None:
        #     UNA PRENOTAZIONE SENZA UN QUANDO NON È UNA PRENOTAZIONE.
        # Qui non si ripiega su quello che si era chiesto: se la controparte
        # non ha detto data e ora, quello che ha confermato non si sa.
        return {}, "non c'è una data e un'ora confermate"

    inizio = datetime(
        giorno.year, giorno.month, giorno.day, ora[0], ora[1],
    )
    inizio = _same_wall_clock_in(_with_zone(inizio, fuso), fuso)

    quanto = _minutes(cambiamenti.get("duration_minutes")) or _minutes(
        voluto.get("duration_minutes")) or DEFAULT_MINUTES
    return {
        "start_datetime": inizio.isoformat(),
        "end_datetime": (inizio + timedelta(minutes=quanto)).isoformat(),
        "timezone": fuso,
        "title": str(voluto.get("title") or "Appuntamento")[:120],
    }, ""


async def _apply_book(db, *, call, binding, outcome) -> Verdict:
    """Crea l'appuntamento, una volta sola per missione."""
    campi, perche = translate(binding, outcome)
    if perche:
        return Verdict("skipped", error=perche)

    negato = _what_the_authority_says(binding, outcome)
    if negato is not None:
        return negato

    calendario = _the_calendar(db)
    negato = await _consent_missing(db, calendario, binding.owner_id)
    if negato:
        return Verdict("failed", error=negato, fields=campi)

    gia = await _the_one_this_mission_made(db, binding)
    if gia is not None:
        #     SE QUESTA MISSIONE NE HA GIÀ FATTO UNO, NON NE FA UN SECONDO.
        return Verdict(
            "applied", writes=[f"calendar:{gia['id']}"], fields=campi,
        )

    try:
        bozza = await _create_it(db, binding, campi)
    except Exception as e:
        logger.info("prenotazione non riuscita: %s", type(e).__name__)
        return Verdict(
            "failed",
            error=f"il calendario non ha accettato la prenotazione ({type(e).__name__})",
            fields=campi,
        )

    await _remember_which_one(db, binding, bozza["id"])
    return Verdict("applied", writes=[f"calendar:{bozza['id']}"], fields=campi)


async def _create_it(db, binding, campi: Dict[str, str]) -> Dict[str, Any]:
    """
    L'appuntamento nuovo, dalla porta da cui passano tutti gli altri.

    `create_from_candidate` non crea un secondo evento per la stessa
    intenzione: riconosce la coppia documento-candidato e restituisce quello
    che c'era. Qui il candidato è la missione — un nome che non cambia fra un
    tentativo e l'altro — ed è così che il doppione diventa impossibile invece
    che improbabile.
    """
    from documents.intelligence.calendar_adapter import CalendarGateway

    candidato = {
        "id": binding.mission_id,
        "source_document_id": PHONE_CALL_SOURCE,
        "title": campi["title"],
        "description": "",
        "start_datetime": campi["start_datetime"],
        "end_datetime": campi["end_datetime"],
        "timezone": campi["timezone"],
        "all_day": False,
    }
    bozza = await CalendarGateway(db).get("internal").create_from_candidate(
        user_id=binding.owner_id, candidate=candidato,
    )
    await _the_calendar(db).sync_draft(
        user_id=binding.owner_id, draft_id=bozza["id"],
    )
    return bozza


async def _the_one_this_mission_made(db, binding) -> Optional[Dict[str, Any]]:
    """
    L'appuntamento che questa missione ha già creato, se esiste.

        IL NOME DELLA MISSIONE È SULL'EVENTO.

    È così che un recupero dopo un processo morto sa distinguere «non l'ho
    mai creato» da «l'ho creato e non me ne sono accorto» senza cercare per
    somiglianza di titolo e orario — che è esattamente la ricerca che questo
    progetto ha vietato a sé stesso.
    """
    return await db.calendar_event_drafts.find_one(
        {
            "user_id": binding.owner_id,
            "source_document_id": PHONE_CALL_SOURCE,
            "source_event_candidate_id": binding.mission_id,
            "status": {"$ne": "cancelled"},
        },
        {"_id": 0, "id": 1, "start_datetime": 1, "status": 1},
    )


async def _remember_which_one(db, binding, entity_id: str) -> None:
    """
    Scrive sul legame quale evento è nato.

    Non serve all'idempotenza — quella la garantisce il nome sull'evento — ma
    serve a chi legge dopo: senza, il legame di una prenotazione riuscita
    resterebbe senza oggetto, e «che cosa ha creato questa telefonata?» non
    avrebbe una risposta diretta.

        E NON SI SCRIVE DENTRO `target`.

    Quello è l'identità della missione ed entra nella chiave di idempotenza.
    Cambiarlo a cose fatte significava che la seconda applicazione della stessa
    prenotazione usava una chiave diversa e scriveva un secondo record. È
    successo, e questa riga è il motivo per cui non succede più.
    """
    from telephone.binding import BINDINGS

    try:
        await db[BINDINGS].update_one(
            {"mission_id": binding.mission_id},
            {"$set": {"created_entity_id": entity_id}},
        )
        binding.created_entity_id = entity_id
    except Exception as e:  # pragma: no cover
        logger.info("legame non aggiornato: %s", type(e).__name__)


async def _reconcile_book(db, *, call, binding, outcome) -> Verdict:
    """
    Una prenotazione rimasta a metà: l'appuntamento è nato o no?

    A dirlo è il nome sull'evento, non una supposizione. Se c'è, la scrittura
    era andata e il record era rimasto indietro. Se non c'è, non è mai partita
    e si riprova — una volta, dalla porta normale.
    """
    gia = await _the_one_this_mission_made(db, binding)
    if gia is not None:
        await _remember_which_one(db, binding, gia["id"])
        return Verdict(
            "applied",
            writes=[f"calendar:{gia['id']}"],
            fields={"start_datetime": str(gia.get("start_datetime") or "")},
        )
    return await _apply_book(db, call=call, binding=binding, outcome=outcome)


def _minutes(valore: Any) -> int:
    """Quanto dura, in minuti, o zero se non lo si sa."""
    try:
        quanti = int(str(valore or "").strip() or 0)
    except ValueError:
        return 0
    return quanti if 0 < quanti <= 8 * 60 else 0


def _with_zone(quando: datetime, fuso: str) -> datetime:
    """Un orario senza fuso diventa un orario in quel fuso."""
    try:
        from zoneinfo import ZoneInfo

        return quando.replace(tzinfo=ZoneInfo((fuso or "Europe/Rome").strip()))
    except Exception:
        return quando
