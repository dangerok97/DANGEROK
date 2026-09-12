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
    call = await _the_call_we_are_waiting_for(call_id, said["call_ref"])
    if call is None:
        # Inerte di proposito: né errore né effetto.
        return {"ok": True}

    service = TelephoneService(db)

    # Il riferimento dell'operatore arriva con il primo evento utile.
    if said["call_ref"] and call.provider_ref != said["call_ref"]:
        call.provider_ref = said["call_ref"]
        await service.mark(call, call.state)

    if said["what"] == "answered":
        await service.mark(call, "talking", started_at=_now())
    elif said["what"] == "ended":
        await service.mark(
            call,
            "ended" if said["ended_how"] in ("they_hung_up", "we_hung_up") else "failed",
            ended_at=_now(),
            how_it_ended=said["ended_how"],
        )

    return {"ok": True}


@router.websocket("/socket")
async def socket(websocket: WebSocket) -> None:
    """
    L'audio della telefonata, mentre passa.

        NIENTE DI QUELLO CHE PASSA DI QUI RESTA DI QUI.

    Vonage apre questa connessione quando il copione glielo chiede, manda un
    primo messaggio di testo con i suoi riferimenti, e poi soltanto frame
    binari: PCM lineare a 16 bit, venti millisecondi alla volta. Si può
    rispondere con la stessa forma, ed è così che ORA parlerà.

    In questo sprint qui non c'è ancora nessuno che ascolti o che risponda:
    si verifica che il filo esista, che l'audio arrivi davvero, e che non ne
    resti niente. Il punto in cui il parlato diventerà parole, e le parole
    diventeranno il solito percorso cognitivo di ORA, è `same_ora.py`, che
    esiste già e aspetta lo Sprint 3.2.
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

    # Quanto audio è passato. Solo conteggi: non i byte, non un campione, non
    # un secondo di conversazione.
    frames = 0
    audio_bytes = 0
    first_frame_ms: Optional[int] = None

    import time as _time

    opened_at = _time.perf_counter()
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            chunk = message.get("bytes")
            if chunk:
                frames += 1
                audio_bytes += len(chunk)
                if first_frame_ms is None:
                    first_frame_ms = int((_time.perf_counter() - opened_at) * 1000)
                # Qui, nello Sprint 3.2, il suono andrà a chi ascolta. Adesso
                # si lascia andare: nessuna coda, nessun buffer che cresce,
                # nessun file.
                continue

            text = message.get("text")
            if text:
                # Il primo messaggio porta i riferimenti dell'operatore. Non
                # contiene audio e non contiene niente della vita di nessuno.
                logger.info("audio aperto per la chiamata (metadati ricevuti)")

    except Exception as e:
        logger.info("filo audio chiuso: %s", type(e).__name__)
    finally:
        logger.info(
            "audio: %d frame, %d byte, primo frame a %s ms — niente salvato",
            frames, audio_bytes, first_frame_ms,
        )
        fresh = await service.get(call.owner_id, call.id)
        if fresh is not None:
            #     QUANTO AUDIO È PASSATO È UN FATTO; L'AUDIO NON LO È.
            # Si tiene il conteggio perché è l'unico modo di dire «il filo ha
            # funzionato» dopo che la telefonata è finita.
            fresh.audio_frames = frames
            fresh.audio_bytes = audio_bytes
            fresh.first_audio_ms = first_frame_ms
            await service.mark(fresh, fresh.state)
        try:
            await websocket.close()
        except Exception:
            pass


def _now() -> str:
    from telephone.models import now_iso

    return now_iso()
