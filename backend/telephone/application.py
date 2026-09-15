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

# Dopo quanto un `pending` smette di essere «sta succedendo» e diventa
# «è rimasto lì».
#
#     DUE MINUTI SONO SESSANTA VOLTE L'APPLICAZIONE PIÙ LENTA MISURATA.
#
# Sul vero l'applicazione completa ha impiegato 2,1 secondi, di cui 1,6 di
# andata e ritorno con Google. Due minuti non toccano niente che stia ancora
# lavorando — nemmeno con un fornitore in grave ritardo — e non lasciano un
# record appeso per un pomeriggio.
STALE_AFTER_S = 120

# Per quanto vale la presa in carico di chi sta recuperando.
#
#     UN LOCK CHE NON SCADE È UN RECORD PERSO PER SEMPRE.
#
# Chi rivendica un record appeso ci mette sopra il proprio nome. Se muore
# mentre lo tiene, quel nome resta — e senza una scadenza nessuno potrebbe mai
# più toccarlo. Cinque minuti sono molto più di un recupero (2,1 secondi sul
# vero) e molto meno di un pomeriggio.
LEASE_S = 300


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

    #     QUANDO QUALCUNO L'HA PRESA IN CARICO.
    # Senza questa data un record `pending` è indistinguibile fra «è partita
    # trenta millisecondi fa» e «è morta un'ora fa»: la prima non si tocca,
    # la seconda va recuperata, e a dirlo è solo il tempo.
    created_at: str = Field(default_factory=now_iso, max_length=40)
    # Quando qualcuno ha detto «di questo me ne occupo io». Vuoto vuol dire
    # che è libero. Non è uno stato: è un nome sopra una cosa da fare.
    claimed_at: str = Field(default="", max_length=40)
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
    """
    L'applicazione di questa telefonata, se qualcuno ci ha provato.

    Per telefonata, non per nome della missione: una commissione ripresa ha due
    telefonate e una missione sola, e l'applicazione appartiene a quella che
    l'ha davvero scritta.
    """
    row = await db[APPLICATIONS].find_one({"call_id": call_id}, {"_id": 0})
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
    fuori: Dict[str, CallMissionApplication] = {}
    righe = db[APPLICATIONS].find({"call_id": {"$in": list(call_ids)}}, {"_id": 0})
    async for row in righe:
        try:
            record = CallMissionApplication.model_validate(row)
        except Exception:  # pragma: no cover
            continue
        fuori[record.call_id] = record
    return fuori


def is_stale(record: CallMissionApplication, *, now: Optional[str] = None) -> bool:
    """Se questa presa in carico è rimasta lì invece di star succedendo."""
    from datetime import datetime, timezone

    if record.application_status != "pending":
        return False
    try:
        nato = datetime.fromisoformat(
            (record.created_at or "").replace("Z", "+00:00"))
        adesso = (
            datetime.fromisoformat(now.replace("Z", "+00:00")) if now
            else datetime.now(timezone.utc)
        )
        if nato.tzinfo is None:
            nato = nato.replace(tzinfo=timezone.utc)
        if adesso.tzinfo is None:
            adesso = adesso.replace(tzinfo=timezone.utc)
        return (adesso - nato).total_seconds() >= STALE_AFTER_S
    except Exception:
        #     UNA DATA ILLEGGIBILE NON AUTORIZZA A RISCRIVERE UN CALENDARIO.
        return False


async def recover_stale(db, *, now: Optional[str] = None) -> List[CallMissionApplication]:
    """
    Le applicazioni rimaste a metà, riportate a una conclusione.

        CHI MUORE IN MEZZO A DUE SCRITTURE NON LASCIA UN ERRORE. LASCIA UN
        FORSE.

    Un processo che si spegne fra la presa in carico e la chiusura del record
    lascia un `pending` che non dice se il calendario è stato toccato. Questa
    funzione non lo indovina e non riprova alla cieca: chiede al dominio di
    guardare lo stato canonico e di dire dove sta l'appuntamento adesso.

    Torna i record che ha chiuso — vuoto è il caso normale, ed è quello che si
    spera di leggere.
    """
    chiusi: List[CallMissionApplication] = []
    righe = db[APPLICATIONS].find({"application_status": "pending"}, {"_id": 0})
    async for row in righe:
        try:
            record = CallMissionApplication.model_validate(row)
        except Exception:  # pragma: no cover
            continue
        if not is_stale(record, now=now):
            #     UN'APPLICAZIONE CHE STA ANCORA LAVORANDO NON SI TOCCA.
            continue
        if not await _claim(db, record):
            #     SE NON È MIA, NON LA TOCCO.
            # Due processi che recuperano insieme lo stesso record appeso
            # farebbero esattamente la doppia scrittura contro cui esiste
            # tutto il resto di questo file.
            continue
        chiuso = await recover_one(db, record)
        if chiuso is not None and chiuso.application_status != "pending":
            chiusi.append(chiuso)
    return chiusi


async def _claim(db, record: CallMissionApplication) -> bool:
    """
    Mette il proprio nome sopra un record appeso, o dice che ce n'è già uno.

        LA RIVENDICAZIONE LA FA IL DATABASE, NON UN `if`.

    Un `find_one` seguito da un `update_one` ha in mezzo una finestra, e in
    quella finestra ci stanno due processi. Qui la condizione viaggia dentro
    la stessa operazione che scrive: chi arriva secondo trova il filtro che
    non combacia più e torna a mani vuote, senza aver toccato niente.

        E LA RIVENDICAZIONE SCADE.

    Chi muore mentre la tiene lascia il proprio nome sopra il record. Senza
    scadenza quel record non sarebbe più recuperabile da nessuno — il guasto
    che stiamo sistemando, ricreato un piano più sotto.
    """
    from datetime import datetime, timedelta, timezone

    adesso = datetime.now(timezone.utc)
    scaduta = (adesso - timedelta(seconds=LEASE_S)).isoformat()
    try:
        preso = await db[APPLICATIONS].find_one_and_update(
            {
                "_id": record.idempotency_key,
                "application_status": "pending",
                "$or": [
                    {"claimed_at": {"$exists": False}},
                    {"claimed_at": ""},
                    {"claimed_at": {"$lt": scaduta}},
                ],
            },
            {"$set": {"claimed_at": adesso.isoformat()}},
        )
    except Exception as e:  # pragma: no cover
        logger.info("rivendicazione non riuscita: %s", type(e).__name__)
        return False
    return preso is not None


async def recover_one(
    db, record: CallMissionApplication,
) -> Optional[CallMissionApplication]:
    """
    Una sola applicazione appesa, riconciliata con il mondo.

        STESSA CHIAVE, NESSUN RECORD NUOVO.

    Il recupero non è un secondo tentativo che si annota a parte: è lo stesso
    fatto che arriva finalmente a una conclusione. Scrivere un secondo record
    vorrebbe dire che la stessa cosa risulta fatta due volte — che è
    esattamente ciò contro cui la chiave esiste.
    """
    try:
        call = await _the_call(db, record.call_id)
        if call is None:
            return await _settle(db, record, _nothing(
                "failed", "la telefonata di questa applicazione non esiste più"))

        outcome = _the_outcome_of(call)
        if outcome is None:
            return await _settle(db, record, _nothing(
                "skipped", "questa telefonata non ha un esito da applicare"))

        legame = await binding_for(db, record.call_id)
        if legame is None:
            return await _settle(db, record, _nothing(
                "skipped", "il legame con l'appuntamento non c'è più"))

        adattatore = adapter_for(legame.target.domain, legame.target.operation)
        if adattatore is None or not hasattr(adattatore, "reconcile"):
            return await _settle(db, record, _nothing(
                "skipped",
                f"non so riconciliare {legame.target.operation} su «{legame.target.domain}»"))

        verdetto = await adattatore.reconcile(
            db, call=call, binding=legame, outcome=outcome,
        )
        chiuso = await _settle(db, record, verdetto)
        if chiuso.went_through():
            await _note_on_the_call(db, call, chiuso.writes)
        return chiuso

    except Exception as e:
        logger.info("recupero non riuscito: %s", type(e).__name__)
        try:
            return await _settle(db, record, _nothing(
                "failed", f"il recupero si è interrotto ({type(e).__name__})"))
        except Exception:  # pragma: no cover
            return None


class _nothing:
    """Un verdetto senza adattatore, per i casi che si chiudono prima."""

    def __init__(self, status: str, error: str) -> None:
        self.status = status
        self.writes: List[str] = []
        self.error = error
        self.fields: Dict[str, str] = {}


async def _the_call(db, call_id: str):
    """La telefonata di questo record, come oggetto."""
    from telephone.models import PhoneCall

    row = await db["phone_calls"].find_one({"id": call_id}, {"_id": 0})
    return PhoneCall.model_validate(row) if row else None


def _the_outcome_of(call):
    """
    L'esito validato di questa telefonata, riletto da dov'è rimasto.

    Non si ricostruisce e non si reinventa: o è quello che il gate aveva
    validato allora, o non c'è.
    """
    from telephone.mission import CallMissionOutcome

    grezzo = (call.metrics or {}).get("outcome")
    if not isinstance(grezzo, dict):
        return None
    try:
        return CallMissionOutcome.model_validate(grezzo)
    except Exception:
        return None


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
            if stato_esito == "needs_user":
                #     UN ESITO CHE ASPETTA UNA PERSONA NON E' UN ESITO MORTO.
                # Qui la commissione si ferma invece di finire: quello che ha
                # imparato resta scritto, e aspetta una risposta. Nel mondo
                # non si tocca niente — e' esattamente il punto.
                from telephone.continuation import pause_for_user

                try:
                    await pause_for_user(db, call=call, outcome=outcome)
                except Exception as e:  # pragma: no cover
                    logger.info("pausa non registrata: %s", type(e).__name__)
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

        adattatore = adapter_for(legame.target.domain, legame.target.operation)
        if adattatore is None:
            return await _write_down(
                db, call, mission_id, stato_esito, legame,
                status="skipped",
                error=f"non so ancora {legame.target.operation} su «{legame.target.domain}»",
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
            #     SE QUESTA ERA UNA RIPRESA, ADESSO E' CHIUSA.
            # Non tocca niente quando non lo era: si scrive soltanto su una
            # commissione che risultava ripresa e aspettava di sapere com'e'
            # finita.
            try:
                from telephone.continuation import settle as chiudi

                await chiudi(db, mission_id=mission_id, succeeded=True)
            except Exception as e:  # pragma: no cover
                logger.info("continuazione non chiusa: %s", type(e).__name__)
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
            # Chiuso: la presa in carico non serve più a nessuno.
            "claimed_at": "",
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
