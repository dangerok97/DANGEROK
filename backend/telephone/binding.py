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

# Le operazioni che una telefonata può applicare. Anche questa lista è corta
# di proposito: `cancel` e `book` cambiano il mondo quanto `reschedule` e
# meritano ciascuna il proprio giro di prove, non un ramo aggiunto di fretta.
Operation = Literal["reschedule"]


class MissionTarget(BaseModel):
    """
    L'oggetto preciso che questa missione sta muovendo.

    Tre campi e nessuna descrizione: un dominio, un identificativo canonico,
    e che cosa gli si farà. Niente titolo, niente orario, niente nome —
    quelli servono a parlare, e di parlare si occupa il packet.
    """

    domain: Domain
    entity_id: str = Field(min_length=1, max_length=64)
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
    created_at: str = Field(default_factory=now_iso)


async def bind_a_calendar_event(
    db, *, call, calendar_ref: str, even_if_it_is_past: bool = False,
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
    #     SOLO UNO SPOSTAMENTO SPOSTA QUALCOSA.
    # Le altre missioni non sanno ancora applicare niente, e chiedere «quale
    # appuntamento?» a chi sta solo telefonando per informarsi sarebbe una
    # domanda senza risposta possibile. Si tace, e non si lega niente.
    if _what_kind_of_mission(call.mandate.why_calling or "") != "reschedule":
        return None, "", False

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
            domain="calendar", entity_id=ref, operation="reschedule",
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
    """Il legame di questa telefonata, se ne ha uno."""
    row = await db[BINDINGS].find_one(
        {"mission_id": mission_id_for(call_id)}, {"_id": 0},
    )
    if not row:
        return None
    try:
        return CallMissionBinding.model_validate(row)
    except Exception as e:  # pragma: no cover
        logger.info("legame illeggibile: %s", type(e).__name__)
        return None


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
