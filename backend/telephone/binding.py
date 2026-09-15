"""
A che cosa, nel mondo di ORA, è attaccata questa telefonata.

    «ALLE 18:00» NON DICE QUALE APPUNTAMENTO.

L'esito di una missione riuscita contiene un orario, e un orario non è un
indirizzo. Chi ha parlato al telefono sa una cosa sola — che lo studio ha
registrato lo spostamento — e non ha, né deve avere, l'identificativo
dell'evento in calendario. Quindi l'evento va deciso **prima**: quando ORA
prepara la telefonata, davanti alla persona, mentre si può ancora chiedere
«quale dei due?».

    NON SI CERCA L'EVENTO DOPO, PER SOMIGLIANZA.

Cercarlo dopo vorrebbe dire abbinare «dentista» a un titolo, o «le 16» a un
orario, su un calendario che nel frattempo può essere cambiato. Un abbinamento
sbagliato qui non è un errore di visualizzazione: è l'appuntamento di qualcun
altro spostato. Se al momento di preparare la chiamata non si sa quale evento
è, la risposta giusta è chiedere — e questo file non ha un ramo che indovina.

    E IL LEGAME NON VIAGGIA CON LA VOCE.

Sta qui, in un record del server, insieme a com'era l'evento nel momento in cui
la missione è stata scritta. Quel «com'era» serve dopo: se quando si applica
l'esito l'evento non è più com'era, la premessa della telefonata è scaduta e
non si sovrascrive niente.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from telephone.mission import _what_kind_of_mission, mission_id_for
from telephone.models import now_iso

logger = logging.getLogger("ora.telephone.binding")

BINDINGS = "call_mission_bindings"

# I domini che sanno ricevere l'esito di una telefonata. Uno, per ora, e
# dichiararlo qui è il modo di tenere onesto il resto: un dominio non elencato
# non ha un adattatore, e senza adattatore non si scrive niente.
Domain = Literal["calendar"]

# Le operazioni che una telefonata può applicare. Ognuna ha avuto il proprio
# giro di prove, e nessuna è arrivata per somiglianza con le altre: spostare,
# disdire e prenotare cambiano il mondo in tre modi diversi, e sbagliano in
# tre modi diversi.
Operation = Literal["reschedule", "cancel", "book"]

# Le operazioni che agiscono su un evento che esiste già. `book` no: il suo
# oggetto non c'è ancora, ed è proprio quello che la telefonata va a creare.
ON_SOMETHING_THAT_EXISTS = ("reschedule", "cancel")


class MissionTarget(BaseModel):
    """
    L'oggetto preciso che questa missione sta muovendo.

    Tre campi e nessuna descrizione: un dominio, un identificativo canonico,
    e che cosa gli si farà. Niente titolo, niente orario, niente nome —
    quelli servono a parlare, e di parlare si occupa il packet.
    """

    domain: Domain
    #     VUOTO È LEGITTIMO, ED È IL CASO DI `book`.
    # Un appuntamento da prenotare non ha ancora un identificativo: nasce
    # dall'applicazione, dopo che la controparte ha confermato. Prima di
    # allora l'unico nome che ha è quello della missione.
    entity_id: str = Field(default="", max_length=64)
    operation: Operation


class CallMissionBinding(BaseModel):
    """
    La missione, l'oggetto, e com'era l'oggetto quando si è deciso di chiamare.

        `expected` NON È UN DOPPIONE: È LA DATA DI SCADENZA DELLA MISSIONE.

    Serve a rispondere, dopo, a una domanda sola: stiamo ancora parlando della
    stessa cosa? Se l'appuntamento delle 16 nel frattempo è diventato delle 9,
    l'accordo preso al telefono riguardava un evento che non esiste più — e
    applicarlo comunque sarebbe scrivere in calendario una cosa che nessuno ha
    confermato.
    """

    mission_id: str = Field(min_length=1, max_length=64)
    call_id: str = Field(min_length=1, max_length=64)
    owner_id: str = Field(min_length=1, max_length=64)
    target: MissionTarget
    # Com'era l'oggetto quando la missione è stata scritta. Solo i campi che
    # servono a riconoscerlo e a ricostruire il nuovo valore.
    expected: Dict[str, str] = Field(default_factory=dict)
    #     E DOVE SI VUOLE ARRIVARE, QUANDO NON C'È UN PUNTO DI PARTENZA.
    # Per una prenotazione è l'unico stato che esiste: data, ora, quanto dura
    # se si sa, con chi. Serve a chi parla per chiedere la cosa giusta, e a
    # chi applica per creare esattamente quella e non un'altra.
    desired: Dict[str, str] = Field(default_factory=dict)
    #     QUELLO CHE LA TELEFONATA HA CREATO, SE HA CREATO QUALCOSA.
    #
    # Sta qui e **non** dentro `target`, e la distinzione non è estetica.
    # `target` è l'identità della missione, ed entra nella chiave di
    # idempotenza: se cambiasse a cose fatte, la seconda applicazione della
    # stessa prenotazione userebbe una chiave diversa e si scriverebbe un
    # secondo record. Misurato — succedeva.
    #
    # Quindi l'identità resta quella di quando la missione è nata, e il
    # risultato si annota accanto.
    created_entity_id: str = Field(default="", max_length=64)
    created_at: str = Field(default_factory=now_iso)


async def bind_a_calendar_event(
    db, *, call, calendar_ref: str = "", even_if_it_is_past: bool = False,
    desired_datetime: str = "", desired_minutes: int = 0,
) -> Tuple[Optional[CallMissionBinding], str, bool]:
    """
    Lega questa telefonata all'evento che dovrà spostare.

    Torna tre cose: il legame, il motivo in italiano per cui non si può fare —
    che è una frase da dire a una persona, non un codice da registrare — e se
    quel motivo è una **domanda** invece che un rifiuto.

    La differenza fra le due conta. «Questo appuntamento non è nel tuo
    calendario» chiude il discorso; «quell'appuntamento è di ieri, telefono lo
    stesso?» lo apre, e chi riceve la risposta deve poterle distinguere.

    Non solleva: una telefonata che non si può legare resta una telefonata
    valida, e verrà soltanto raccontata invece che applicata.
    """
    #     TRE MISSIONI CAMBIANO IL CALENDARIO. LE ALTRE NO.
    # Chiedere «quale appuntamento?» a chi sta solo telefonando per informarsi
    # sarebbe una domanda senza risposta possibile. Si tace, e non si lega
    # niente: quella telefonata riporterà una risposta, ed è quello che deve
    # fare.
    tipo = _what_kind_of_mission(call.mandate.why_calling or "")
    if tipo not in ("reschedule", "cancel", "book"):
        return None, "", False

    if tipo == "book":
        return await _bind_a_new_appointment(
            db, call=call, quando=desired_datetime, minuti=desired_minutes,
            anche_se_passato=even_if_it_is_past,
        )

    ref = _just_the_id(calendar_ref)
    if not ref:
        return None, "non mi hai detto quale appuntamento", False

    draft = await db.calendar_event_drafts.find_one(
        {"id": ref, "user_id": call.owner_id},
        {"_id": 0, "id": 1, "title": 1, "start_datetime": 1,
         "end_datetime": 1, "timezone": 1, "status": 1},
    )
    if not draft:
        #     NON SI CERCA UN RIPIEGO.
        # Un evento che non c'è, o che è di qualcun altro, non si sostituisce
        # con quello che gli somiglia di più. Si dice che non c'è.
        return None, "questo appuntamento non è nel tuo calendario", False
    if draft.get("status") == "cancelled":
        return None, "questo appuntamento risulta disdetto", False
    if not draft.get("start_datetime"):
        return None, "questo appuntamento non ha un orario da spostare", False

    #     UN APPUNTAMENTO GIÀ PASSATO NON SI SPOSTA: SI CHIEDE.
    #
    # Telefonare a uno studio per spostare la visita di ieri è una figura che
    # fa ORA e che paga la persona, e nasce quasi sempre da un malinteso —
    # l'evento sbagliato, o una data letta storta. Non è però impossibile che
    # sia voluto: capita di richiamare per rimettere in piedi un appuntamento
    # saltato. Quindi non si rifiuta e non si procede: si domanda, finché c'è
    # qualcuno a cui domandare. Dopo lo squillo non c'è più.
    if not even_if_it_is_past and _already_gone(
        str(draft.get("start_datetime") or ""),
        str(draft.get("timezone") or "Europe/Rome"),
    ):
        return (
            None,
            f"«{str(draft.get('title') or 'quell appuntamento')[:60]}» è già "
            "passato: vuoi che telefoni lo stesso?",
            True,
        )

    binding = CallMissionBinding(
        mission_id=mission_id_for(call.id),
        call_id=call.id,
        owner_id=call.owner_id,
        target=MissionTarget(
            domain="calendar", entity_id=ref, operation=tipo,
        ),
        expected={
            "start_datetime": str(draft.get("start_datetime") or ""),
            "end_datetime": str(draft.get("end_datetime") or ""),
            "timezone": str(draft.get("timezone") or "Europe/Rome"),
            "title": str(draft.get("title") or "")[:120],
        },
    )
    await db[BINDINGS].update_one(
        {"mission_id": binding.mission_id},
        {"$set": binding.model_dump()},
        upsert=True,
    )
    return binding, "", False


async def binding_for(db, call_id: str) -> Optional[CallMissionBinding]:
    """
    Il legame di questa telefonata, se ne ha uno.

        SI CERCA PER TELEFONATA, NON PER NOME DELLA MISSIONE.

    Di solito sono la stessa cosa. Non lo sono quando una commissione si e'
    fermata e ha ripreso: la seconda telefonata porta il nome della missione
    originale — e' cosi' che l'applicazione resta una sola — ma ha un `call_id`
    tutto suo, ed e' da li' che la si ritrova.
    """
    row = await db[BINDINGS].find_one({"call_id": call_id}, {"_id": 0})
    if not row:
        return None
    try:
        return CallMissionBinding.model_validate(row)
    except Exception as e:  # pragma: no cover
        logger.info("legame illeggibile: %s", type(e).__name__)
        return None


async def _bind_a_new_appointment(
    db, *, call, quando: str, minuti: int, anche_se_passato: bool,
) -> Tuple[Optional[CallMissionBinding], str, bool]:
    """
    Lega una prenotazione a quello che si vuole ottenere, non a un oggetto.

        UNA PRENOTAZIONE NON HA UN PRIMA.

    Le altre due missioni partono da un evento che esiste e lo spostano o lo
    tolgono; questa parte dal niente. Quindi il legame non porta un
    `entity_id` — quello nascerà dopo, se la controparte conferma — ma porta
    **che cosa si è chiesto**: data, ora, quanto dura, con chi.

    Serve a due lettori diversi. A chi parla, per chiedere quella cosa lì e
    non una che le somiglia. E a chi applica, per creare esattamente ciò che è
    stato confermato invece di fidarsi di un orario che torna da solo.

        E SENZA UN QUANDO NON SI PRENOTA NIENTE.

    «Prenotami dal dentista» senza una data non è una missione: è una cosa da
    concordare prima, e finché non c'è la telefonata riporta e basta.
    """
    if not (quando or "").strip():
        return None, "non mi hai detto per quando prenotare", False

    fuso = _where_the_person_is()
    if not anche_se_passato and _already_gone(quando, fuso):
        return (
            None,
            "quella data è già passata: vuoi che chiami lo stesso?",
            True,
        )

    binding = CallMissionBinding(
        mission_id=mission_id_for(call.id),
        call_id=call.id,
        owner_id=call.owner_id,
        target=MissionTarget(domain="calendar", entity_id="", operation="book"),
        expected={},
        desired={
            "start_datetime": quando.strip()[:40],
            "timezone": fuso,
            "duration_minutes": str(int(minuti)) if minuti else "",
            "counterparty": (call.calling_whom or "")[:120],
            "title": _what_to_call_it(call),
        },
    )
    await db[BINDINGS].update_one(
        {"mission_id": binding.mission_id},
        {"$set": binding.model_dump()},
        upsert=True,
    )
    return binding, "", False


def _what_to_call_it(call) -> str:
    """
    Come si chiamerà in calendario l'appuntamento che ancora non esiste.

    Il nome di chi si chiama, che è l'unica cosa che una persona riconosce
    guardando l'agenda la settimana dopo. Non la ragione della telefonata:
    «spostare la visita» è un compito, non un appuntamento.
    """
    return (call.calling_whom or "Appuntamento").strip()[:120]


def _where_the_person_is() -> str:
    from telephone.mission import _where_they_are

    return _where_they_are()


def _already_gone(inizio: str, fuso: str) -> bool:
    """
    Se quell'appuntamento è già cominciato.

        NON È LA DATA, È L'ISTANTE.

    Un evento delle 16:00 di oggi alle 16:54 è passato quanto quello di ieri,
    e confrontare solo i giorni lo lascerebbe scivolare. Se l'orario non si
    riesce a leggere si risponde **no**: una guardia che non sa dire non deve
    fermare una telefonata.
    """
    from datetime import datetime, timezone as _tz

    testo = (inizio or "").strip()
    if not testo:
        return False
    try:
        quando = datetime.fromisoformat(testo.replace("Z", "+00:00"))
    except Exception:
        return False
    if quando.tzinfo is None:
        try:
            from zoneinfo import ZoneInfo

            quando = quando.replace(tzinfo=ZoneInfo((fuso or "Europe/Rome").strip()))
        except Exception:
            quando = quando.replace(tzinfo=_tz.utc)
    return quando < datetime.now(_tz.utc)


def _just_the_id(ref: str) -> str:
    """
    L'identificativo, comunque sia stato scritto.

    Il resto del progetto scrive i riferimenti al calendario come
    `calendar:<id>`, e chi prepara la telefonata li ripete come li ha letti.
    Accettare tutte e due le forme costa una riga e toglie un modo di
    sbagliare.
    """
    testo = (ref or "").strip()
    if ":" in testo:
        testo = testo.rsplit(":", 1)[-1].strip()
    return testo[:64]
