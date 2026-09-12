"""
L'operatore: chi apre la linea, e come gli si parla.

    IL TRASPORTO TELEFONICO NON È UNA VOCE. È UN ATTUATORE.

Vonage non sta accanto a Gemini TTS e non implementa `SpeechOutputProvider`:
quella è la voce di ORA, e vive nell'app. Questo è il filo che porta il suono
fino al telefono di un'altra persona, ed è una cosa che tocca il mondo — allo
stesso livello del calendario o della posta, sotto la stessa autorità.

    QUALE OPERATORE SIA È UN DETTAGLIO, E DEVE RESTARE UN DETTAGLIO.

Il resto del telefono — l'autorità, il mandato, il fascicolo pre-chiamata, la
lettura dell'esito — non sa da chi passi il suono. Cambiare operatore costa
questo file.

Tre cose specifiche di Vonage, e nessuna cambia quello che ORA fa:

- **l'autenticazione è una firma, non una password.** Ogni richiesta porta un
  JWT firmato RS256 con la chiave privata dell'applicazione, che vive fuori
  dal repository e si legge da `VONAGE_PRIVATE_KEY_PATH`. La chiave non entra
  mai in un log, in un database o in una risposta;

- **la chiamata si guida con un NCCO**, un piccolo copione JSON che si
  restituisce quando qualcuno risponde: qui dice una cosa sola, «apri un
  websocket verso ORA e mandaci l'audio»;

- **l'audio è PCM lineare a 16 bit**, binario, non base64 dentro JSON. È il
  formato della rete telefonica letto senza involucro, e va tenuto presente
  quando lo si darà in pasto a un modello che ascolta: quello vuole 24 kHz, e
  qui arrivano 16.
"""

from __future__ import annotations

import logging
import os
import time
import uuid as _uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ora.telephone.carrier")

# L'API voce di Vonage. Il nome storico del dominio è quello che è.
API = "https://api.nexmo.com/v1/calls"

NAME = "Vonage"

# Quanti secondi far squillare prima di lasciar perdere. Non è una soglia di
# dominio: è quanto aspetta una persona normale.
RING_SECONDS = 30

# Come arriva l'audio dalla linea. Sedici kilohertz è quello che Vonage offre
# di meglio su un websocket, e il doppio di quanto la rete telefonica porti
# davvero: non aggiunge informazione, ma evita un ricampionamento in più
# quando questo suono andrà a un modello che ascolta.
AUDIO_RATE = 16000
AUDIO_CONTENT_TYPE = f"audio/l16;rate={AUDIO_RATE}"


def _application_id() -> str:
    return (os.environ.get("VONAGE_APPLICATION_ID") or "").strip()


def _from_number() -> str:
    return "".join(
        ch for ch in (os.environ.get("VONAGE_FROM_NUMBER") or "") if ch.isdigit()
    )


def public_base() -> str:
    """Da dove l'operatore ci raggiunge, senza barra finale."""
    return (os.environ.get("VONAGE_PUBLIC_BASE_URL") or "").strip().rstrip("/")


def _private_key() -> Optional[bytes]:
    """
    La chiave privata, letta dal disco al momento dell'uso.

        LA CHIAVE NON PASSA DA NESSUNA PARTE DOVE POSSA RESTARE.

    Non in una variabile globale, non in un database, non in un log, non in
    una risposta HTTP. Si legge, si firma, e quello che resta in giro è un
    JWT che scade in un minuto. Se il file non c'è, non si telefona: meglio
    una chiamata che non parte di una chiave cercata altrove.
    """
    path = (os.environ.get("VONAGE_PRIVATE_KEY_PATH") or "").strip()
    if not path:
        return None
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except Exception as e:
        # Il tipo di errore, mai il percorso e mai il contenuto.
        logger.info("chiave dell'applicazione non leggibile: %s", type(e).__name__)
        return None


def _token() -> Optional[str]:
    """Un lasciapassare firmato, valido un minuto."""
    key = _private_key()
    app_id = _application_id()
    if not key or not app_id:
        return None
    try:
        import jwt

        now = int(time.time())
        return jwt.encode(
            {
                "application_id": app_id,
                "iat": now,
                "nbf": now,
                "exp": now + 60,
                "jti": str(_uuid.uuid4()),
            },
            key,
            algorithm="RS256",
        )
    except Exception as e:
        logger.info("lasciapassare non firmato: %s", type(e).__name__)
        return None


def can_call() -> bool:
    """Se in questo momento esiste un operatore a cui chiedere una linea."""
    return bool(
        _application_id()
        and (os.environ.get("VONAGE_PRIVATE_KEY_PATH") or "").strip()
        and _from_number()
        and public_base().startswith("https://")
    )


def why_not() -> str:
    """Cosa manca, per nome e in italiano. Lo legge chi ragiona, non un log."""
    missing: List[str] = []
    if not _application_id():
        missing.append("nessuna applicazione voce configurata")
    if not (os.environ.get("VONAGE_PRIVATE_KEY_PATH") or "").strip():
        missing.append("nessuna chiave dell'applicazione")
    elif _private_key() is None:
        missing.append("la chiave dell'applicazione non si legge")
    if not _from_number():
        missing.append("nessun numero da cui chiamare")
    if not public_base().startswith("https://"):
        missing.append("nessun indirizzo pubblico dove ricevere l'audio")
    return "; ".join(missing)


# ---------------------------------------------------------------------------
# Il copione: cosa deve fare la chiamata quando qualcuno risponde
# ---------------------------------------------------------------------------

def ncco_for(call_id: str) -> List[Dict[str, Any]]:
    """
    Il copione che apre l'audio verso ORA.

        UN NCCO È UN'ISTRUZIONE, NON UNA CONVERSAZIONE.

    Dice una cosa sola: collega questa chiamata a un websocket. Non fa parlare
    nessuno, non registra niente, non suona musica d'attesa. Chi parlerà è
    ORA, dall'altro capo di quel filo, e quello che dirà lo decide il percorso
    cognitivo di sempre — non questo JSON.

    `call_id` è il nostro, non quello di Vonage: viaggia nell'indirizzo del
    websocket perché quando la connessione si apre si sappia subito di quale
    telefonata si tratta, senza doverla cercare.
    """
    base = public_base().replace("https://", "wss://").replace("http://", "ws://")
    return [
        {
            "action": "connect",
            "from": _from_number(),
            "endpoint": [
                {
                    "type": "websocket",
                    "uri": f"{base}/vonage/socket?call_id={call_id}",
                    "content-type": AUDIO_CONTENT_TYPE,
                    # Quello che ORA deve sapere appena la linea si apre. Solo
                    # riferimenti: niente nome, niente numero, niente motivo.
                    # Chi ascoltasse questo websocket non imparerebbe nulla
                    # sulla vita di nessuno.
                    "headers": {"call_id": call_id},
                }
            ],
        }
    ]


def ncco_when_something_broke() -> List[Dict[str, Any]]:
    """
    Il copione di riserva: dire che non si può, e chiudere.

        UN FALLBACK CHE TACE LASCIA UNA PERSONA CON UN TELEFONO MUTO.

    Vonage lo chiede quando l'indirizzo principale non risponde. Restituire un
    copione vuoto lascerebbe la linea aperta in silenzio, a pagamento, finché
    qualcuno non riaggancia. Una frase e una chiusura sono più oneste.
    """
    return [
        {
            "action": "talk",
            "language": "it-IT",
            "text": (
                "Mi dispiace, c'è un problema tecnico e non posso proseguire. "
                "Riproveremo più tardi. Buona giornata."
            ),
        }
    ]


# ---------------------------------------------------------------------------
# Aprire e chiudere la linea
# ---------------------------------------------------------------------------

async def place(
    *, to_number: str, call_id: str, minutes: int,
) -> Optional[Dict[str, str]]:
    """
    Compone il numero. Torna il riferimento della chiamata, o `None`.

    Gli indirizzi che si passano qui sono quelli che l'operatore userà per
    raccontare cosa succede e per chiedere il copione. Portano il nostro
    `call_id`, così ogni evento sa già a quale telefonata appartiene.

    Nessun parametro chiede una registrazione, e non deve comparirne uno.
    """
    token = _token()
    if not token or not can_call():
        return None

    base = public_base()
    try:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            answer = await client.post(
                API,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "to": [{"type": "phone", "number": to_number.lstrip("+")}],
                    "from": {"type": "phone", "number": _from_number()},
                    "answer_url": [f"{base}/vonage/answer?call_id={call_id}"],
                    "answer_method": "GET",
                    "event_url": [f"{base}/vonage/event?call_id={call_id}"],
                    "event_method": "POST",
                    "ringing_timer": RING_SECONDS,
                    # Il limite lo mette il mandato, e vale anche se qualcosa
                    # va storto: una chiamata che non finisce è una chiamata
                    # che costa e che nessuno sta guardando.
                    "length_timer": max(60, minutes * 60),
                },
            )
        if answer.status_code not in (200, 201):
            #     UN CODICE DI ERRORE NON DICE COSA FARE. IL TESTO SÌ.
            #
            # «422» non aiuta nessuno; «il numero from non appartiene a questo
            # account» si risolve in un minuto. Il corpo dell'errore non
            # contiene segreti — è la spiegazione dell'operatore — e senza di
            # esso ogni telefonata fallita diventa un'indagine.
            detail = ""
            try:
                detail = answer.text[:400]
            except Exception:
                detail = ""
            logger.info(
                "%s non ha aperto la linea: http %s — %s",
                NAME, answer.status_code, detail,
            )
            return {"call_ref": "", "error": f"http {answer.status_code}: {detail}"}
        data = answer.json() or {}
        return {
            "call_ref": str(data.get("uuid") or ""),
            "session_ref": str(data.get("conversation_uuid") or ""),
        }
    except Exception as e:
        logger.info("%s non raggiungibile: %s", NAME, type(e).__name__)
        return None


async def hang_up(call_ref: str) -> bool:
    """
    Chiude la linea.

    Serve quando è ORA a dover chiudere — il mandato è esaurito, o qualcosa è
    andato storto e restare in linea non aiuterebbe nessuno. Chiudere non è
    un'azione di cui chiedere il permesso: è la fine di una cosa che il
    permesso ce l'aveva già.
    """
    token = _token()
    if not call_ref or not token:
        return False
    try:
        import httpx

        async with httpx.AsyncClient(timeout=20) as client:
            answer = await client.put(
                f"{API}/{call_ref}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"action": "hangup"},
            )
        return answer.status_code in (200, 202, 204)
    except Exception as e:
        logger.info("chiusura fallita: %s", type(e).__name__)
        return False


# ---------------------------------------------------------------------------
# Ascoltare l'operatore
# ---------------------------------------------------------------------------

def read_event(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Che cosa dice l'operatore, tradotto in parole nostre.

    Il resto del telefono non conosce i nomi degli stati di nessun fornitore:
    riceve «squilla», «ha risposto», «è finita». Se un giorno l'operatore
    cambia di nuovo, cambia questa funzione e basta.
    """
    said = str((body or {}).get("status") or "").lower()

    what = {
        "started": "ringing",
        "ringing": "ringing",
        "answered": "answered",
        "completed": "ended",
        "busy": "ended",
        "cancelled": "ended",
        "failed": "ended",
        "rejected": "ended",
        "timeout": "ended",
        "unanswered": "ended",
        "machine": "machine",
    }.get(said, "something_else")

    #     «RIFIUTATA DALLA RETE» NON È «NON HA RISPOSTO NESSUNO».
    #
    # Il primo tentativo vero è tornato `rejected/restricted` — l'operatore non
    # ha lasciato passare la chiamata — e finiva tradotto in «no_answer», cioè
    # in una frase che dà la colpa alla persona chiamata per qualcosa che è
    # successo prima che il suo telefono squillasse. Una traduzione comoda che
    # accusa qualcuno è peggio di una traduzione mancante.
    ended_how = {
        "completed": "they_hung_up",
        "cancelled": "we_hung_up",
        "busy": "busy",
        "timeout": "no_answer",
        "unanswered": "no_answer",
        "rejected": "failed",
        "failed": "failed",
    }.get(said, "unknown")

    return {
        "what": what,
        "raw": said,
        "call_ref": str((body or {}).get("uuid") or ""),
        "conversation_ref": str((body or {}).get("conversation_uuid") or ""),
        "ended_how": ended_how,
        # Perché, quando l'operatore lo dice. «restricted» vuol dire che la
        # rete non ha lasciato passare la chiamata, ed è una cosa che si
        # sistema nel pannello e non nel codice: senza questa parola, un
        # rifiuto e un telefono spento sono indistinguibili.
        "why": str((body or {}).get("reason") or (body or {}).get("detail") or ""),
        "direction": str((body or {}).get("direction") or ""),
    }
