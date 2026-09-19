"""
Le porte verso l'operatore telefonico: pubbliche, e inerti.

    UN ENDPOINT CHE GOVERNA TELEFONATE STA SU INTERNET.

Queste quattro porte devono essere pubbliche — l'operatore deve poter chiedere
il copione, raccontare cosa succede e consegnare l'audio — e stanno **fuori da
`/api`**, perché è così che sono già scritte nel pannello di Vonage e perché
non hanno niente a che vedere con la sessione di nessuno: non c'è un browser,
non c'è un JWT di ORA, non c'è una persona davanti.

La protezione non è una password, che qui non ci sarebbe dove mettere. È che
**queste porte non sanno fare niente da sole**: agiscono soltanto su una
telefonata che ORA ha davvero composto e sta aspettando. Un `call_id`
sconosciuto, o una chiamata che non è in attesa, non produce nulla — non un
errore, non un log rumoroso, non un effetto. Chi bussasse a caso otterrebbe
un copione che saluta e chiude.

E c'è una cosa che qui dentro non succede mai: **l'audio non viene salvato.**
Non su disco, non in memoria oltre il frame che sta passando, non in Mongo.
Si contano i byte per poter dire che è arrivato, e si lasciano andare.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request, WebSocket
from fastapi.responses import JSONResponse

from deps import db
from telephone import carrier
from telephone.models import PhoneCall
from telephone.service import TelephoneService

logger = logging.getLogger("ora.telephone.vonage")

# Fuori da `/api`: gli indirizzi nel pannello sono già questi, e cambiarli
# significherebbe rompere una configurazione che funziona.
router = APIRouter(prefix="/vonage", tags=["vonage"])

# Gli stati in cui una telefonata sta legittimamente aspettando l'operatore.
# Fuori da questi, un evento che la riguarda è rumore.
EXPECTING = ("dialling", "talking")

# Quello che si è preparato mentre il telefono squillava, in attesa che
# qualcuno risponda. Vive quanto la telefonata e sparisce con lei: non è un
# archivio, è un tavolo apparecchiato.
_DOSSIERS: Dict[str, Any] = {}
_READY: Dict[str, Any] = {}


async def _the_call_we_are_waiting_for(
    call_id: str, call_ref: str = "",
) -> Optional[PhoneCall]:
    """
    La telefonata che ORA ha composto e sta aspettando, o niente.

        UNA PORTA PUBBLICA CHE AGISCE SU QUALUNQUE COSA È UNA PORTA APERTA.

    È tutta la protezione di queste rotte, e basta perché è strutturale: non
    esiste un modo di far succedere qualcosa senza il riferimento di una
    chiamata che ORA ha già deciso, autorizzato e composto.
    """
    row = None
    if call_id:
        row = await db["phone_calls"].find_one({"id": call_id}, {"_id": 0})
    if row is None and call_ref:
        row = await db["phone_calls"].find_one({"provider_ref": call_ref}, {"_id": 0})
    if row is None:
        return None
    call = PhoneCall.model_validate(row)
    return call if call.state in EXPECTING else None


@router.get("/answer")
async def answer(call_id: str = "", uuid: str = "") -> JSONResponse:
    """
    Il copione, chiesto quando qualcuno solleva la cornetta.

    Se la telefonata è una che ORA sta aspettando, il copione apre l'audio
    verso di noi. Altrimenti dice una frase e chiude — che è la risposta
    giusta sia a un errore sia a qualcuno che ha trovato l'indirizzo.
    """
    call = await _the_call_we_are_waiting_for(call_id, uuid)
    if call is None:
        logger.info("copione chiesto per una chiamata che non aspettavamo")
        return JSONResponse(carrier.ncco_when_something_broke())
    return JSONResponse(carrier.ncco_for(call.id))


@router.get("/fallback")
async def fallback(call_id: str = "", uuid: str = "") -> JSONResponse:
    """
    Il copione di riserva, quando il principale non ha risposto.

    Non prova a recuperare la telefonata: se il percorso normale è rotto,
    insistere significa far ascoltare a una persona un silenzio che costa. Una
    frase, e si chiude.
    """
    logger.info("copione di riserva richiesto")
    return JSONResponse(carrier.ncco_when_something_broke())


@router.post("/event")
async def event(request: Request, call_id: str = "") -> Dict[str, Any]:
    """
    Che cosa sta succedendo alla chiamata, secondo la rete.

    Squilla, hanno risposto, è finita. Si annota lo stato e nient'altro: da
    qui non parte nessuna decisione, nessuna scrittura nella vita di nessuno,
    nessuna azione verso il mondo.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    said = carrier.read_event(body if isinstance(body, dict) else {})
    #     UNO STATO CHE NON SI VEDE È UNO STATO CHE NON SI PUÒ SISTEMARE.
    #
    # La parola dell'operatore e il riferimento della chiamata, e nient'altro:
    # nessun numero, nessun nome, niente della vita di nessuno. Senza questa
    # riga, una telefonata che finisce in tre secondi è un mistero — e la
    # prima volta lo è stata davvero.
    logger.info(
        "evento: stato=%s motivo=%s chiamata=%s",
        said["raw"] or "(vuoto)",
        (body or {}).get("reason") or (body or {}).get("detail") or "-",
        said["call_ref"][:12] or "-",
    )
    call = await _the_call_we_are_waiting_for(call_id, said["call_ref"])
    if call is None:
        # Inerte di proposito: né errore né effetto.
        return {"ok": True}

    service = TelephoneService(db)

    # Il riferimento dell'operatore arriva con il primo evento utile.
    if said["call_ref"] and call.provider_ref != said["call_ref"]:
        call.provider_ref = said["call_ref"]
        await service.mark(call, call.state)

    if said["what"] == "ringing":
        #     FRA «SQUILLA» E «PRONTO» NON STA ASPETTANDO NESSUNO.
        # Sono gli unici secondi gratis della telefonata: si prepara il
        # fascicolo e si sveglia la catena dei modelli, così il primo turno
        # non paga quello che ha pagato ogni primo turno finora. Non entra
        # nella conversazione, non scrive niente, non è una domanda.
        if call.id not in _READY:
            _READY[call.id] = asyncio.create_task(_get_ready(call))

    elif said["what"] == "answered":
        await service.mark(call, "talking", started_at=_now())
    elif said["what"] == "ended":
        went_well = said["ended_how"] in ("they_hung_up", "we_hung_up")
        # Il motivo si registra solo quando c'è stato un rifiuto. Su una
        # telefonata riuscita l'operatore manda `reason: "ok"`, e scriverlo
        # sotto «perché la rete ha rifiutato» è una riga che racconta una
        # cosa che non è successa.
        await service.mark(
            call,
            "ended" if went_well else "failed",
            ended_at=_now(),
            how_it_ended=said["ended_how"],
            why_the_network_refused="" if went_well else said.get("why", "")[:120],
        )
        if not went_well:
            #     NESSUNO HA RISPOSTO: NON C'E' UNA CONVERSAZIONE CHE LO DICA.
            # Quando si è parlato, l'esito lo scrive chi chiude il filo audio.
            from telephone.chat_report import tell_the_chat

            await tell_the_chat(db, call)

    return {"ok": True}


@router.websocket("/socket")
async def socket(websocket: WebSocket) -> None:
    """
    La telefonata, mentre succede: la voce entra e quella di ORA esce.

        NIENTE DI QUELLO CHE PASSA DI QUI RESTA DI QUI.

    Vonage apre questa connessione quando il copione glielo chiede, manda un
    primo messaggio di testo con i suoi riferimenti, e poi soltanto frame
    binari: PCM lineare a 16 bit, venti millisecondi alla volta. Si risponde
    con la stessa forma, ed è così che ORA parla.

    Qui dentro non si decide niente. I pacchetti vanno a chi ascolta e vengono
    dimenticati nello stesso gesto; quello che torna indietro lo decide il
    runtime, che di Vonage non sa niente.
    """
    call_id = websocket.query_params.get("call_id") or ""
    call = await _the_call_we_are_waiting_for(call_id)
    if call is None:
        # Non si accetta nemmeno la connessione: un websocket aperto verso una
        # telefonata che non esiste è una porta che qualcuno può tenere aperta.
        await websocket.close(code=4404)
        logger.info("audio offerto per una chiamata che non aspettavamo")
        return

    await websocket.accept()
    service = TelephoneService(db)
    #     QUI NON SI SCEGLIE: SI CHIEDE CHI RISPONDE.
    # Il trasporto non sa e non deve sapere quale runtime condurra' la
    # telefonata. Chiede una voce e ne riceve una, con lo stesso contratto di
    # sempre — `open`, `hear`, `close`, `how_it_went`.
    from telephone.binding import binding_for
    from telephone.runtime import the_voice_for

    #     A CHE COSA E' ATTACCATA QUESTA TELEFONATA, SE A QUALCOSA.
    # Deciso prima, quando c'era ancora una persona a cui chiedere «quale
    # appuntamento?». Qui si legge e basta: e' un dato del server, non entra
    # nel packet e non lo sente nessuno.
    legame = await binding_for(db, call.id)

    frames_in = 0
    bytes_in = 0

    async def to_the_line(pcm: bytes) -> None:
        await websocket.send_bytes(pcm)

    async def clear_the_line() -> None:
        """
        Quello che il trasporto aveva già preso in carico.

            QUI C'È UN LIMITE VERO, E VA DETTO.

        Su questo filo non esiste un comando per richiamare indietro l'audio
        già consegnato: si può smettere di mandarne, e lo si fa altrove. Quello
        che ha già lasciato il server — al massimo un pacchetto, venti
        millisecondi — la persona lo sente comunque.
        """
        return None

    async def note(who: str, words: str) -> None:
        fresh = await service.get(call.owner_id, call.id)
        if fresh is not None:
            await service.heard(fresh, who, words)

    session = the_voice_for(
        db,
        owner_id=call.owner_id,
        session_ref=call.session_ref,
        send=to_the_line,
        clear_transport=clear_the_line,
        on_said=note,
        dossier=await _the_dossier_for(call),
        call=call,
        binding=legame,
    )

    opened = await session.open()
    if not opened:
        logger.info("runtime non aperto: si chiude la linea")
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
        await session.close()
        return

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            chunk = message.get("bytes")
            if chunk:
                frames_in += 1
                bytes_in += len(chunk)
                # Passa e non resta: nessuna coda, nessun file, nessun campo.
                await session.hear(chunk)
                continue

            if message.get("text"):
                # Il primo messaggio porta i riferimenti dell'operatore. Non
                # contiene audio e non contiene niente della vita di nessuno.
                logger.info("audio aperto per la chiamata (metadati ricevuti)")

    except Exception as e:
        logger.info("filo audio chiuso: %s", type(e).__name__)
    finally:
        #     PRIMA SI CHIUDE, POI SI CONTA.
        # Al contrario si perdeva l'ultimo turno: quello ancora in corso
        # quando la linea cade non e' ancora nei tempi, e il conteggio diceva
        # uno quando i turni erano due. Chiudere lo mette a posto per primo.
        await session.close()
        numbers = session.how_it_went()
        logger.info(
            "audio: %d frame in, %d byte in — niente salvato", frames_in, bytes_in,
        )
        fresh = await service.get(call.owner_id, call.id)
        if fresh is not None:
            fresh.audio_frames = frames_in
            fresh.audio_bytes = bytes_in
            fresh.first_audio_ms = numbers.get("first_audio_in_ms")
            fresh.metrics = numbers
            await service.mark(fresh, fresh.state)
            await _apply_what_was_agreed(fresh, session)
        _DOSSIERS.pop(call.id, None)
        _READY.pop(call.id, None)
        try:
            await websocket.close()
        except Exception:
            pass


async def _apply_what_was_agreed(call, session) -> None:
    """
    L'esito confermato diventa un cambiamento vero, adesso.

        NON QUANDO L'OPERATORE DICE «COMPLETED».

    Il momento giusto non e' quello in cui la rete dichiara chiusa la
    telefonata: e' quello in cui l'esito esiste, e' stato validato dal gate ed
    e' definitivo — cioe' qui, appena la sessione si e' chiusa. Legarlo
    all'evento del carrier avrebbe voluto dire dipendere da un messaggio che
    puo' arrivare due volte, arrivare tardi, o non arrivare affatto: ne
    abbiamo visti di tutti e tre i tipi.

        E SE L'APPLICAZIONE FALLISCE, LA TELEFONATA RESTA ANDATA BENE.

    Nessuno riscrive `metrics.outcome` da qui. La controparte ha confermato:
    e' un fatto, ed e' vero anche se il calendario non ha voluto saperne.
    Quello che cambia e' la frase che si legge sulla scheda.
    """
    try:
        from telephone.application import apply_the_outcome

        #     IL TRASPORTO NON SA CHE FORMA ABBIA UN ESITO.
        # Passa quello che la sessione ha in mano e non lo guarda: se non e'
        # un esito di missione — il runtime classico non ne ha — a dirlo e'
        # chi lo applica. Un `isinstance` qui avrebbe voluto dire un filo
        # audio che conosce la missione, ed e' la cosa che questo file non fa.
        fatto = await apply_the_outcome(db, call, getattr(session, "outcome", None))
        if fatto is not None:
            logger.info(
                "esito applicato: %s (%s)",
                fatto.application_status, fatto.error or "-",
            )
        #     E SE QUESTA TELEFONATA ERA UN PEZZO DI UN PROPOSITO, IL PROPOSITO
        #     ADESSO PUO' SAPERE COM'E' FINITA.
        # Il gancio e' sottile apposta: chi chiude il filo audio non deve
        # sapere che esiste un ciclo. Se il piano non c'e' — la maggior parte
        # delle telefonate — non succede niente, e non e' un caso da gestire.
        from autonomy.orchestrator import on_call_finished

        await on_call_finished(db, call)
    except Exception as e:  # pragma: no cover
        logger.info("applicazione non tentata: %s", type(e).__name__)
    #     E LA CHAT DA CUI E' PARTITA VIENE A SAPERE COM'E' ANDATA.
    from telephone.chat_report import tell_the_chat

    await tell_the_chat(db, call)


#     FRA «SQUILLA» E «PRONTO» NON CI SONO SEMPRE DEI SECONDI.
#
# Il fascicolo si prepara quando arriva `ringing`, e di solito ci sono cinque
# o sei secondi di squilli per farlo. Su una telefonata vera l'operatore ha
# mandato `ringing` e `answered` nello stesso millisecondo — e `started`
# addirittura prima: il filo audio si e' aperto con il fascicolo ancora a
# meta', `the_voice_for` ha trovato `dossier=None` ed e' caduto sul runtime
# classico senza che nessuno lo avesse chiesto.
#
# Dall'altra parte si e' sentito silenzio, e nel rapporto non c'era traccia
# di una missione perche' missione non ce n'era stata.
QUANTO_ASPETTARE_IL_FASCICOLO_S = 3.0


async def _the_dossier_for(call):
    """
    Il fascicolo di questa telefonata, aspettandolo se sta ancora arrivando.

        UN PREPARATIVO IN RITARDO NON E' UN PREPARATIVO ASSENTE.

    Tre casi, e nessuno dei tre e' «arrenditi». Se e' pronto si prende; se e'
    in corso lo si aspetta un momento — qualche centinaio di millisecondi
    costa molto meno di una telefonata condotta dal runtime sbagliato; se non
    e' mai partito, perche' `ringing` non e' arrivato affatto, lo si fa
    partire adesso.

    Dopo l'attesa si torna quello che c'e', anche niente: a quel punto il
    ripiego sul classico e' una scelta, non un incidente di tempistica.
    """
    pronto = _DOSSIERS.get(call.id)
    if pronto is not None:
        return pronto

    preparativi = _READY.get(call.id)
    if preparativi is None:
        logger.info("il fascicolo non era partito: si prepara adesso")
        preparativi = asyncio.create_task(_get_ready(call))
        _READY[call.id] = preparativi

    try:
        await asyncio.wait_for(
            asyncio.shield(preparativi), timeout=QUANTO_ASPETTARE_IL_FASCICOLO_S,
        )
    except asyncio.TimeoutError:
        logger.info("il fascicolo non e' arrivato in tempo: si va con quello che c'e'")
    except Exception as e:
        logger.info("preparativi non riusciti: %s", type(e).__name__)
    return _DOSSIERS.get(call.id)


async def _get_ready(call) -> None:
    """
    Il fascicolo e il risveglio dei modelli, mentre squilla.

        È INFRASTRUTTURA, NON COGNIZIONE.

    Non passa dal Conversation Engine, non crea una sessione, non scrive un
    messaggio, non tocca memoria o autorità, non attiva strumenti e non
    produce niente che qualcuno leggerà.
    """
    try:
        from telephone.dossier import prepare_while_it_rings, wake_the_providers

        dossier, woken = await asyncio.gather(
            prepare_while_it_rings(db, call),
            wake_the_providers(),
            return_exceptions=True,
        )
        if not isinstance(dossier, Exception):
            _DOSSIERS[call.id] = dossier
            logger.info(
                "fascicolo pronto in %s ms",
                (dossier.prepared_ms or {}).get("total"),
            )
        if not isinstance(woken, Exception):
            logger.info(
                "catena dei modelli: svegliata=%s in %s ms",
                woken.get("woken"), woken.get("took_ms"),
            )
    except Exception as e:
        # Prepararsi male non deve impedire di telefonare: vuol dire che il
        # primo turno costerà quello che sarebbe costato comunque.
        logger.info("preparativi non riusciti: %s", type(e).__name__)


def _now() -> str:
    from telephone.models import now_iso

    return now_iso()
