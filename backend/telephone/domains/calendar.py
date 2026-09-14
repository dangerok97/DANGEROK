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

DOMAIN = "calendar"

# Che cosa una telefonata di spostamento può aver confermato. Chiusa di
# proposito: una chiave che non è qui dentro è una cosa che non si è chiesto
# il permesso di cambiare, e non la si scrive «visto che c'era».
RESCHEDULE_KEYS = frozenset({"appointment_date", "old_time", "new_time"})

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
    Da «alle 18:00» a due campi veri, o al motivo per cui non si può.

        È PURA APPOSTA.

    Nessun database, nessuna rete: solo il legame e l'esito. È la parte in cui
    si può sbagliare di calcolo, ed è la parte che si può provare senza far
    finta di avere un calendario.
    """
    if binding.target.operation != "reschedule":
        return {}, f"operazione non applicabile: {binding.target.operation}"

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
    Sposta l'appuntamento, se è ancora quello di cui si stava parlando.
    """
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
