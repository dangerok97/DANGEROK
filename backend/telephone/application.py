"""
Dall'esito di una telefonata a un cambiamento vero, una volta sola.

    LA TELEFONATA È ANDATA BENE NON VUOL DIRE CHE IL CALENDARIO SIA CAMBIATO.

Sono due fatti, e fino a questo sprint ne esisteva uno solo. Lo studio
confermava, il backend validava, la scheda della chiamata diceva «Appuntamento
spostato alle 18:00» — e il calendario restava alle 16:00. Due verità, e quella
che una persona apre la mattina era quella vecchia.

Questo file tiene il secondo fatto, separato dal primo e con un nome suo.

    UN ESITO SI APPLICA UNA VOLTA SOLA, E SI PUÒ DIMOSTRARE.

L'applicazione non è un effetto collaterale della chiamata: è un record, con
la sua chiave. La chiave è `missione + operazione + oggetto`, ed è l'`_id` del
documento — così a decidere se questa cosa è già stata fatta non è un `if`, è
il database. Due tentativi producono un documento e una scrittura; il secondo
si accorge del primo prima di toccare qualsiasi cosa.

    E SE L'APPLICAZIONE FALLISCE, LA TELEFONATA RESTA RIUSCITA.

Non si torna indietro a riscrivere l'esito. La controparte *ha* confermato: è
successo, ed è vero anche se poi Google non ha risposto. Cambiare l'esito
significherebbe raccontare che la telefonata è andata male, cioè dare la colpa
alla persona che ha risposto al telefono per un problema che è nostro. Quello
che cambia è la frase che si legge sulla scheda, e la cambia chi la scrive.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from telephone.binding import binding_for, mission_id_for
from telephone.domains import adapter_for
from telephone.models import now_iso

logger = logging.getLogger("ora.telephone.apply")

APPLICATIONS = "call_mission_applications"

# Dove sta l'applicazione di un esito.
#
#     `conflict` NON È `failed`, ED È PER QUESTO CHE ESISTE.
#
# Fallito vuol dire che qualcosa si è rotto e si può riprovare. In conflitto
# vuol dire che nessuno ha sbagliato: l'appuntamento è cambiato mentre eravamo
# al telefono, e riprovare scriverebbe sopra la decisione più recente di
# qualcuno. Sono due frasi diverse da dire a una persona, quindi sono due
# stati.
ApplicationStatus = Literal["pending", "applied", "skipped", "conflict", "failed"]


class CallMissionApplication(BaseModel):
    """Che cosa è stato fatto nel mondo per via di questa telefonata."""

    mission_id: str = Field(min_length=1, max_length=64)
    call_id: str = Field(min_length=1, max_length=64)
    owner_id: str = Field(min_length=1, max_length=64)

    # --- l'oggetto -------------------------------------------------------
    target_domain: str = Field(default="", max_length=32)
    target_entity_id: str = Field(default="", max_length=64)
    operation: str = Field(default="", max_length=32)

    # --- com'è andata la telefonata, e com'è andata l'applicazione --------
    #
    # Due campi, mai uno. Il primo è quello che la controparte ha confermato;
    # il secondo è quello che ORA è riuscita a scrivere. Tenerli insieme in un
    # campo solo è esattamente l'errore che questo sprint chiude.
    outcome_status: str = Field(default="", max_length=16)
    application_status: ApplicationStatus = "pending"

    applied_at: str = Field(default="", max_length=40)
    # I riferimenti canonici di quello che è stato toccato. Vuoto è il caso
    # normale: quasi nessuna telefonata scrive qualcosa.
    writes: List[str] = Field(default_factory=list, max_length=4)
    # Perché non si è potuto, in italiano, come lo direbbe una persona.
    error: str = Field(default="", max_length=300)

    idempotency_key: str = Field(min_length=1, max_length=200)

    def went_through(self) -> bool:
        return self.application_status == "applied"


def key_for(mission_id: str, operation: str, entity_id: str) -> str:
    """
    La chiave che rende questa applicazione irripetibile.

    Missione, operazione, oggetto. Non l'ora, non il tentativo, non un numero
    progressivo: tre cose che non cambiano fra un tentativo e l'altro, perché
    è proprio questo che le rende utili a riconoscere il secondo.
    """
    return f"{mission_id}|{operation or '-'}|{entity_id or '-'}"[:200]


async def application_for(db, call_id: str) -> Optional[CallMissionApplication]:
    """L'applicazione di questa telefonata, se qualcuno ci ha provato."""
    row = await db[APPLICATIONS].find_one(
        {"mission_id": mission_id_for(call_id)}, {"_id": 0},
    )
    if not row:
        return None
    try:
        return CallMissionApplication.model_validate(row)
    except Exception as e:  # pragma: no cover
        logger.info("applicazione illeggibile: %s", type(e).__name__)
        return None


async def applications_for(db, call_ids: List[str]) -> Dict[str, CallMissionApplication]:
    """
    Le applicazioni di un elenco di telefonate, in una domanda sola.

    L'elenco delle chiamate ne mostra venti per volta, e venti domande al
    database per scrivere venti righe sarebbero venti domande di troppo.
    """
    if not call_ids:
        return {}
    nomi = [mission_id_for(x) for x in call_ids]
    fuori: Dict[str, CallMissionApplication] = {}
    righe = db[APPLICATIONS].find({"mission_id": {"$in": nomi}}, {"_id": 0})
    async for row in righe:
        try:
            record = CallMissionApplication.model_validate(row)
        except Exception:  # pragma: no cover
            continue
        fuori[record.call_id] = record
    return fuori


async def apply_the_outcome(db, call, outcome) -> Optional[CallMissionApplication]:
    """
    Prende l'esito già validato e prova a farlo diventare vero.

        NON SI APPLICA UN ESITO CHE NON È UN ESITO.

    Il cancello è `is_actionable()`, e non ne esistono altri: successo
    confermato con dentro dei cambiamenti. `needs_user`, `failed` e `partial`
    sono esiti legittimi che tornano a una persona, non permessi a metà — e
    una versione uno che provasse ad applicarli in qualche caso sarebbe una
    versione uno di cui non ci si fida.

    Torna il record di quello che è successo, o `None` se non c'era nemmeno un
    esito da guardare. Non solleva mai: l'applicazione è un secondo fatto, e
    un secondo fatto andato male non deve far cadere il primo.
    """
    #     QUELLO CHE ARRIVA QUI PUO' NON ESSERE UN ESITO DI MISSIONE.
    # Il runtime classico ne ha uno di forma diversa, e il trasporto passa
    # quello che ha senza guardarlo — apposta. Il riconoscimento sta qui, dove
    # la missione si conosce, e chiede l'unica cosa che serve davvero: saper
    # dire da solo se e' azionabile.
    if outcome is None or not hasattr(outcome, "is_actionable"):
        return None

    mission_id = getattr(outcome, "mission_id", "") or mission_id_for(call.id)
    stato_esito = str(getattr(outcome, "status", "") or "")

    try:
        if not outcome.is_actionable():
            return await _write_down(
                db, call, mission_id, stato_esito, None,
                status="skipped",
                error=_why_not_actionable(outcome),
            )

        legame = await binding_for(db, call.id)
        if legame is None:
            #     L'ESITO C'È, L'INDIRIZZO NO.
            # È il caso in cui la telefonata è stata preparata senza dire
            # quale appuntamento si stava spostando. Si racconta e basta:
            # cercare adesso l'evento che somiglia di più a «le 18:00» è
            # esattamente la cosa che questo sprint vieta.
            return await _write_down(
                db, call, mission_id, stato_esito, None,
                status="skipped",
                error="la telefonata non era legata a un appuntamento del calendario",
            )

        adattatore = adapter_for(legame.target.domain)
        if adattatore is None:
            return await _write_down(
                db, call, mission_id, stato_esito, legame,
                status="skipped",
                error=f"non so ancora applicare esiti su «{legame.target.domain}»",
            )

        #     LA PRENOTAZIONE VIENE PRIMA DELLA SCRITTURA.
        # Il record nasce `pending` e nasce con la sua chiave come `_id`: da
        # quel momento un secondo tentativo non arriva nemmeno all'adattatore,
        # perché il database gli dice che questa cosa è già stata presa in
        # carico. Prenotare dopo aver scritto avrebbe lasciato aperta proprio
        # la finestra che serve chiudere.
        record, gia_fatto = await _reserve(db, call, mission_id, stato_esito, legame)
        if gia_fatto:
            logger.info("esito già applicato: non si tocca niente")
            return record

        verdetto = await adattatore.apply(
            db, call=call, binding=legame, outcome=outcome,
        )
        record = await _settle(db, record, verdetto)
        if record.went_through():
            await _note_on_the_call(db, call, record.writes)
        return record

    except Exception as e:
        #     UN ERRORE QUI NON RISCRIVE LA TELEFONATA.
        logger.info("applicazione non riuscita: %s", type(e).__name__)
        try:
            return await _write_down(
                db, call, mission_id, stato_esito, None,
                status="failed",
                error=f"l'applicazione si è interrotta ({type(e).__name__})",
            )
        except Exception:  # pragma: no cover
            return None


# ---------------------------------------------------------------------------
# Il record
# ---------------------------------------------------------------------------


async def _reserve(db, call, mission_id: str, stato_esito: str, legame):
    """
    Mette il cartello «me ne occupo io», e dice se c'era già.

    Torna `(record, era_già_lì)`. Quando era già lì non si guarda nemmeno se
    fosse riuscito: che sia `applied`, `conflict` o `failed`, qualcuno ha già
    deciso per questa chiave e un secondo giro non è una correzione, è una
    seconda scrittura.
    """
    chiave = key_for(mission_id, legame.target.operation, legame.target.entity_id)
    record = CallMissionApplication(
        mission_id=mission_id,
        call_id=call.id,
        owner_id=call.owner_id,
        target_domain=legame.target.domain,
        target_entity_id=legame.target.entity_id,
        operation=legame.target.operation,
        outcome_status=stato_esito,
        application_status="pending",
        idempotency_key=chiave,
    )
    try:
        await db[APPLICATIONS].insert_one({**record.model_dump(), "_id": chiave})
        return record, False
    except Exception:
        #     SE NON SI È POTUTO INSERIRE, O C'ERA GIÀ O È ROTTO.
        # Distinguere le due cose vuol dire guardare: se il documento c'è,
        # questa chiave era già stata presa e va bene così. Se non c'è,
        # l'inserimento è fallito per un motivo suo e non lo si nasconde.
        esistente = await db[APPLICATIONS].find_one({"_id": chiave}, {"_id": 0})
        if esistente:
            return CallMissionApplication.model_validate(esistente), True
        raise


async def _settle(db, record: CallMissionApplication, verdetto):
    """Chiude il record con quello che l'adattatore ha davvero fatto."""
    record.application_status = verdetto.status
    record.writes = list(verdetto.writes)[:4]
    record.error = (verdetto.error or "")[:300]
    record.applied_at = now_iso()
    await db[APPLICATIONS].update_one(
        {"_id": record.idempotency_key},
        {"$set": {
            "application_status": record.application_status,
            "writes": record.writes,
            "error": record.error,
            "applied_at": record.applied_at,
        }},
    )
    return record


async def _write_down(
    db, call, mission_id: str, stato_esito: str, legame,
    *, status: str, error: str,
) -> CallMissionApplication:
    """
    Un record per una cosa che non si è fatta.

        NON AVER APPLICATO È UNA DECISIONE, E LE DECISIONI SI SCRIVONO.

    Senza questa riga, «l'abbiamo guardato e non si poteva» e «nessuno ci ha
    mai messo mano» sarebbero indistinguibili — e la seconda è un guasto,
    mentre la prima è il funzionamento normale.
    """
    dominio = legame.target.domain if legame is not None else ""
    oggetto = legame.target.entity_id if legame is not None else ""
    operazione = legame.target.operation if legame is not None else ""
    chiave = key_for(mission_id, operazione, oggetto)
    record = CallMissionApplication(
        mission_id=mission_id,
        call_id=call.id,
        owner_id=call.owner_id,
        target_domain=dominio,
        target_entity_id=oggetto,
        operation=operazione,
        outcome_status=stato_esito,
        application_status=status,  # type: ignore[arg-type]
        applied_at=now_iso(),
        error=error[:300],
        idempotency_key=chiave,
    )
    try:
        await db[APPLICATIONS].insert_one({**record.model_dump(), "_id": chiave})
    except Exception:
        esistente = await db[APPLICATIONS].find_one({"_id": chiave}, {"_id": 0})
        if esistente:
            return CallMissionApplication.model_validate(esistente)
        raise
    return record


async def _note_on_the_call(db, call, writes: List[str]) -> None:
    """
    Segna sulla telefonata che cosa ha scritto nel mondo.

        IL CAMPO C'ERA DA SEMPRE, E NON L'AVEVA MAI SCRITTO NESSUNO.

    `PhoneCall.wrote` esisteva dal primo giorno, ed è rimasto vuoto per tutti
    gli sprint in cui una telefonata non poteva cambiare niente. Adesso può, e
    questo è il posto giusto per riempirlo — ma resta un'annotazione, non il
    meccanismo: chi decide se una cosa è già stata fatta è la chiave del
    record, non questo elenco.
    """
    if not writes:
        return
    try:
        await db["phone_calls"].update_one(
            {"id": call.id},
            {"$addToSet": {"wrote": {"$each": list(writes)[:4]}}},
        )
    except Exception as e:  # pragma: no cover
        logger.info("annotazione sulla chiamata non riuscita: %s", type(e).__name__)


def _why_not_actionable(outcome) -> str:
    """Perché da questo esito non si muove niente, detto a una persona."""
    stato = str(getattr(outcome, "status", "") or "")
    if stato == "needs_user":
        return "l'esito aspetta una tua decisione"
    if stato == "partial":
        return "la telefonata non ha chiuso la questione"
    if stato == "failed":
        return "la missione non è riuscita"
    if stato == "success":
        return "la controparte non ha confermato niente di concreto"
    return "non c'è un esito su cui agire"
