"""
Il ponte fra la linea telefonica e la voce che risponde.

    UN TURNO DI TELEFONATA DURA UN SECONDO E MEZZO.

Questa è la ragione per cui qui non c'è il motore di ragionamento di ORA.
Misurato su questo prodotto: la sintesi vocale non in streaming impiega fra i
cinque e gli otto secondi e mezzo per una frase, e un turno di ragionamento
fra i tre e i trenta secondi. Sommati, ogni battuta di una telefonata
sarebbe fra i dieci e i quaranta secondi di silenzio in linea. Nessuno
aspetta. La persona dall'altra parte dice «pronto?», poi riaggancia.

Quindi in linea ci va un modello che ascolta e risponde nello stesso giro —
parlato a parlato, senza passare dal testo e senza aspettare la fine della
frase per cominciare a capire. Ma quel modello non sa niente della vita di
nessuno e non ha nessuna autorità: sa quello che gli è stato messo in mano
prima di comporre il numero, e può accettare soltanto quello che c'è scritto
nel mandato. Il Personal Life Model, l'autorità, l'Action Engine e la
governance restano dove stanno e decidono prima e dopo, non durante.

L'audio non si converte. La rete telefonica porta G.711 μ-law a 8 kHz e il
modello realtime lo accetta e lo restituisce nello stesso formato: in mezzo
non c'è nessun ricampionamento, che è la differenza fra una voce naturale e
una voce sott'acqua, e fra venti millisecondi di ritardo e duecento. Quale
operatore porti quei byte, qui, non si sa: sta in `carrier`.

**NON È COLLEGATO. Sprint 3.2.**

Questo file esiste e funziona, ma in questo momento non lo chiama nessuno, e
non sarebbe corretto che lo chiamasse: il trasporto di Vonage porta PCM
lineare binario a 16 kHz, mentre qui l'audio viaggia in base64 dentro JSON —
la forma di un altro operatore. Farli combaciare vuol dire due cose, ed è
esattamente il lavoro dello Sprint 3.2: leggere i frame binari, e ricampionare
fra i 16 kHz che arrivano dalla linea e i 24 kHz che il modello vuole.

Quello che resta valido qui dentro è tutto il resto — la disciplina sui turni,
l'interruzione, il fascicolo che diventa istruzione, il conto della latenza —
e per questo il file rimane invece di essere buttato.

E c'è una cosa che il ponte deve saper fare più di ogni altra: **stare zitto
quando l'altro parla**. Un assistente che continua la frase mentre una
persona lo interrompe non è naturale, è sgradevole — e al telefono, dove non
ci si vede, è il segnale più forte che dall'altra parte non c'è nessuno.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger("ora.telephone.bridge")

REALTIME_URL = "wss://api.openai.com/v1/realtime"
DEFAULT_MODEL = "gpt-realtime"
# La voce di ORA al telefono. `ORA_PHONE_VOICE` per cambiarla senza toccare
# il codice; il valore di partenza è quello che somiglia di più alla Kore
# scelta ascoltando, nello Sprint 1.
DEFAULT_VOICE = "sage"

# Ogni quanto il carrier manda un pacchetto: 20 ms di audio. Serve solo a
# leggere i numeri di latenza, non a decidere niente.
FRAME_MS = 20


def can_call() -> bool:
    """Se in questo momento esiste un operatore a cui chiedere una linea."""
    from telephone.carrier import can_call as carrier_can_call

    return carrier_can_call()


def can_speak_live() -> bool:
    """Se c'è qualcuno capace di ascoltare e rispondere in linea."""
    return bool((os.environ.get("OPENAI_API_KEY") or "").strip())


def why_not() -> str:
    """Cosa manca, per nome, in italiano. Detto a chi ragiona, non a un log."""
    from telephone.carrier import why_not as carrier_why_not

    return carrier_why_not()


class LiveVoice:
    """
    La voce in linea: apre la sessione col modello realtime e la governa.

    Non decide niente. Riceve l'audio della telefonata e restituisce l'audio
    della risposta; per strada raccoglie quello che è stato detto da una parte
    e dall'altra, perché dopo serve a capire com'è andata.
    """

    def __init__(
        self,
        *,
        brought: Dict[str, Any],
        privacy: List[str],
        on_said: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self.brought = brought
        self.privacy = privacy
        self.on_said = on_said or (lambda who, text: None)
        self.ws = None
        self.said: List[Dict[str, str]] = []
        # Quanto ci ha messo la voce a cominciare a rispondere, turno per
        # turno. È il numero che dice se questa telefonata era sostenibile.
        self.first_audio_ms: List[int] = []
        self._turn_started: Optional[float] = None
        self._greeted = False

    async def open(self) -> bool:
        """Apre la linea col modello. `False` quando non si può."""
        key = (os.environ.get("OPENAI_API_KEY") or "").strip()
        if not key:
            return False
        try:
            import websockets
        except ImportError:
            logger.info("websockets non disponibile: nessuna voce in linea")
            return False

        model = (os.environ.get("ORA_REALTIME_MODEL") or DEFAULT_MODEL).strip()
        try:
            self.ws = await websockets.connect(
                f"{REALTIME_URL}?model={model}",
                additional_headers={"Authorization": f"Bearer {key}"},
                max_size=None,
            )
        except Exception as e:
            logger.info("linea col modello non aperta: %s", type(e).__name__)
            return False

        await self._configure()
        return True

    async def _configure(self) -> None:
        """
        Dice al modello chi è, cosa sa, e cosa può accettare.

        Il rilevamento del parlato lo fa il server: è lui che sente quando la
        persona comincia e quando smette, e lo sente prima di noi perché ha
        l'audio in mano. `interrupt_response` è la riga che rende la telefonata
        sopportabile — quando la persona ricomincia a parlare, quello che ORA
        stava dicendo si interrompe a metà parola, come fra due persone.
        """
        instructions = (
            self.brought["how_to_behave"]
            + "\n\n--- IL TUO MANDATO ---\n"
            + json.dumps(
                {
                    k: self.brought.get(k)
                    for k in (
                        "who_you_are",
                        "who_you_are_calling",
                        "say_this_first",
                        "why_you_are_calling",
                        "may_agree_to",
                        "must_bring_back",
                        "what_this_is_about",
                        "already_busy",
                    )
                },
                ensure_ascii=False,
            )
            + "\n\n--- RISERVATEZZA ---\n"
            + "\n".join(f"- {line}" for line in self.privacy)
        )
        await self._send({
            "type": "session.update",
            "session": {
                "type": "realtime",
                "output_modalities": ["audio"],
                "audio": {
                    "input": {
                        # Lo stesso formato che arriva dalla linea: niente
                        # conversione, niente ritardo, niente qualità persa.
                        "format": {"type": "audio/pcmu"},
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.5,
                            "prefix_padding_ms": 300,
                            # Mezzo secondo di silenzio prima di considerare
                            # finito il turno: al telefono la gente si ferma a
                            # pensare, e tagliarla dopo due decimi la fa
                            # sentire interrotta.
                            "silence_duration_ms": 500,
                            "interrupt_response": True,
                        },
                        "transcription": {"model": "whisper-1", "language": "it"},
                    },
                    "output": {
                        "format": {"type": "audio/pcmu"},
                        "voice": (os.environ.get("ORA_PHONE_VOICE") or DEFAULT_VOICE).strip(),
                        "speed": 1.0,
                    },
                },
                "instructions": instructions,
            },
        })

    async def greet(self) -> None:
        """
        La presentazione, e parte per prima.

        Non è una risposta a niente: è la prima cosa che si sente quando la
        linea si apre, e il testo è già deciso. Si chiede al modello di dirla
        e basta — così la dichiarazione di essere una macchina non dipende da
        come è andata la generazione.
        """
        if self._greeted:
            return
        self._greeted = True
        self._turn_started = asyncio.get_event_loop().time()
        await self._send({
            "type": "response.create",
            "response": {
                "instructions": (
                    "Di' esattamente questa frase, e poi continua spiegando "
                    "brevemente il motivo della chiamata: "
                    f"«{self.brought['say_this_first']}»"
                ),
            },
        })

    async def hear(self, mulaw_b64: str) -> None:
        """Venti millisecondi di telefonata, così come arrivano."""
        await self._send({"type": "input_audio_buffer.append", "audio": mulaw_b64})

    async def _send(self, payload: Dict[str, Any]) -> None:
        if self.ws is None:
            return
        try:
            await self.ws.send(json.dumps(payload))
        except Exception as e:
            logger.info("invio al modello fallito: %s", type(e).__name__)

    async def listen(
        self,
        *,
        speak: Callable[[str], Awaitable[None]],
        stop_speaking: Callable[[], Awaitable[None]],
    ) -> None:
        """
        Ascolta il modello e passa alla linea quello che dice.

        `stop_speaking` è l'altra metà dell'interruzione: il modello smette di
        generare, ma quello che è già partito sta in una coda dentro il
        carrier e continuerebbe a sentirsi per un paio di secondi. Va svuotata,
        o la persona interrompe e sente ORA che finisce la frase lo stesso.
        """
        if self.ws is None:
            return
        try:
            async for raw in self.ws:
                try:
                    event = json.loads(raw)
                except Exception:
                    continue
                kind = event.get("type") or ""

                if kind == "response.output_audio.delta":
                    if self._turn_started is not None:
                        began = int(
                            (asyncio.get_event_loop().time() - self._turn_started) * 1000
                        )
                        self.first_audio_ms.append(began)
                        self._turn_started = None
                    await speak(event.get("delta") or "")

                elif kind == "input_audio_buffer.speech_started":
                    # Ha ricominciato a parlare: ORA tace, subito.
                    await stop_speaking()

                elif kind == "input_audio_buffer.speech_stopped":
                    self._turn_started = asyncio.get_event_loop().time()

                elif kind == "conversation.item.input_audio_transcription.completed":
                    text = (event.get("transcript") or "").strip()
                    if text:
                        self.said.append({"who": "them", "said": text})
                        self.on_said("them", text)

                elif kind == "response.output_audio_transcript.done":
                    text = (event.get("transcript") or "").strip()
                    if text:
                        self.said.append({"who": "ora", "said": text})
                        self.on_said("ora", text)

                elif kind == "error":
                    logger.info(
                        "modello in linea: %s",
                        str((event.get("error") or {}).get("type") or "errore")[:60],
                    )
        except Exception as e:
            logger.info("linea col modello chiusa: %s", type(e).__name__)

    async def close(self) -> None:
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None

    def how_fast(self) -> Dict[str, Any]:
        """Quanto ci ha messo a rispondere, turno per turno."""
        if not self.first_audio_ms:
            return {"turns": 0}
        ordered = sorted(self.first_audio_ms)
        return {
            "turns": len(ordered),
            "median_ms": ordered[len(ordered) // 2],
            "worst_ms": ordered[-1],
            "frame_ms": FRAME_MS,
        }
