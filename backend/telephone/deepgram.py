"""
Deepgram: l'orecchio e la bocca, dietro i contratti.

    LINEAR16 A 16 KHZ DA UNA PARTE E DALL'ALTRA.

È la ragione per cui è stato scelto, e vale la pena dirla: Vonage manda PCM
lineare mono a 16 kHz, Nova-3 lo accetta così com'è, e Aura-2 lo restituisce
così com'è. Fra il telefono e chi ascolta non c'è **nessuna conversione**, e
nemmeno fra chi parla e il telefono. Ogni ricampionamento evitato è qualità
che non si perde e millisecondi che non si pagano.

Due cose misurate su questo account, che spiegano com'è fatto questo file.

**I socket restano aperti.** Aprire la linea verso l'Europa costa 787 ms per
il TTS e 560 ms per lo STT. Su una frase, il primo audio arriva a **154-278
ms** se il socket è già caldo e a **3.054 ms** se lo si apre adesso. Quindi si
aprono una volta per telefonata.

**`speech_final` non è la fine del turno.** Su «Ciao ORA, dimmi che giorno è
oggi» è scattato a 2,4 secondi su 4 di parlato — cioè sulla pausa dopo «Ciao,
ORA», mentre la persona stava ancora parlando. Qui esce come `pause`, che è
quello che è: un indizio. Chi decide di chi è il turno sta da un'altra parte.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import AsyncIterator, Awaitable, Callable, List, Optional

from telephone.providers import Heard, Spoke

logger = logging.getLogger("ora.telephone.deepgram")

RATE = 16000
NAME = "deepgram"

# Quanto silenzio prima che l'operatore dica «mi sa che ha finito». Un secondo
# è la sua misura minima; sotto, si affida solo all'endpointing, che abbiamo
# visto scattare a meta' frase.
UTTERANCE_END_MS = 1500

# Quante parole proprie si possono suggerire. «ORA» è anche l'avverbio
# italiano più comune che esista, e senza aiuto esce minuscolo.
KEYTERMS = ("ORA",)


def _key() -> str:
    return (os.environ.get("DEEPGRAM_API_KEY") or "").strip()


def _host() -> str:
    return (os.environ.get("DEEPGRAM_HOST") or "api.deepgram.com").strip()


def is_configured() -> bool:
    return bool(_key())


def _auth() -> dict:
    return {"Authorization": f"Token {_key()}"}


# ---------------------------------------------------------------------------
# L'orecchio
# ---------------------------------------------------------------------------

class Listening:
    """Nova-3 in italiano, su un socket che resta aperto per tutta la chiamata."""

    name = NAME

    def __init__(self, *, rate: int = RATE, language: str = "it") -> None:
        self.rate = rate
        self.language = language
        self.ws = None
        self.connect_ms: Optional[int] = None
        self._out: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._reader: Optional[asyncio.Task] = None
        self._opened_at = 0.0
        self._closed = False

    def is_available(self) -> bool:
        return is_configured()

    def _url(self) -> str:
        bits = [
            "model=nova-3",
            f"language={self.language}",
            "encoding=linear16",
            f"sample_rate={self.rate}",
            "channels=1",
            # Provvisori accesi: servono a `utterance_end_ms`, e danno al
            # gestore dei turni un segnale di «sta ancora parlando».
            "interim_results=true",
            # Il segnale che serve al barge-in, e arriva prima delle parole.
            "vad_events=true",
            f"utterance_end_ms={UTTERANCE_END_MS}",
            "punctuate=true",
            "smart_format=true",
        ]
        bits += [f"keyterm={k}" for k in KEYTERMS]
        return f"wss://{_host()}/v1/listen?" + "&".join(bits)

    async def open(self) -> bool:
        if not self.is_available():
            return False
        try:
            import websockets
        except ImportError:
            logger.info("websockets non disponibile: nessun ascolto")
            return False
        began = time.perf_counter()
        try:
            self.ws = await websockets.connect(
                self._url(), additional_headers=_auth(), max_size=None, open_timeout=15,
            )
        except Exception as e:
            logger.info("ascolto non aperto: %s", type(e).__name__)
            return False
        self.connect_ms = int((time.perf_counter() - began) * 1000)
        self._opened_at = time.perf_counter()
        self._reader = asyncio.create_task(self._read())
        return True

    def _ms(self) -> int:
        return int((time.perf_counter() - self._opened_at) * 1000)

    async def _read(self) -> None:
        """Traduce quello che dice l'operatore nei cinque fatti del contratto."""
        try:
            async for raw in self.ws:  # type: ignore[union-attr]
                if not isinstance(raw, str):
                    continue
                try:
                    e = json.loads(raw)
                except Exception:
                    continue
                kind = e.get("type", "")

                if kind == "SpeechStarted":
                    await self._say(Heard("speech_started", at_ms=self._ms(), raw=kind))

                elif kind == "Results":
                    alt = (e.get("channel") or {}).get("alternatives") or [{}]
                    text = (alt[0].get("transcript") or "").strip()
                    if not text:
                        # Un `speech_final` senza parole è comunque una pausa,
                        # e il gestore dei turni la vuole sapere.
                        if e.get("speech_final"):
                            await self._say(Heard("pause", at_ms=self._ms(), raw=kind))
                        continue
                    if e.get("is_final"):
                        await self._say(Heard("final", text, self._ms(), kind))
                        if e.get("speech_final"):
                            await self._say(Heard("pause", text, self._ms(), kind))
                    else:
                        await self._say(Heard("partial", text, self._ms(), kind))

                elif kind == "UtteranceEnd":
                    await self._say(Heard("utterance_end", at_ms=self._ms(), raw=kind))

                elif kind in ("Error", "Warning"):
                    # Il tipo di errore, mai una parola di quello che è stato
                    # detto e mai un campione di audio.
                    logger.info(
                        "ascolto: %s", str((e.get("description") or kind))[:80],
                    )
        except Exception as e:
            if not self._closed:
                logger.info("ascolto interrotto: %s", type(e).__name__)

    async def _say(self, heard: Heard) -> None:
        try:
            self._out.put_nowait(heard)
        except asyncio.QueueFull:
            # Una coda piena vuol dire che nessuno sta leggendo: si butta il
            # più vecchio, che è anche il meno utile.
            try:
                self._out.get_nowait()
                self._out.put_nowait(heard)
            except Exception:
                pass

    async def hear(self, pcm: bytes) -> None:
        """Un pacchetto dalla linea, così com'è. Nessuna conversione."""
        if self.ws is None or not pcm:
            return
        try:
            await self.ws.send(pcm)
        except Exception as e:
            if not self._closed:
                logger.info("audio non consegnato all'ascolto: %s", type(e).__name__)

    async def events(self) -> AsyncIterator[Heard]:
        while True:
            heard = await self._out.get()
            if heard is None:  # type: ignore[comparison-overlap]
                return
            yield heard

    async def close(self) -> None:
        self._closed = True
        if self.ws is not None:
            try:
                await self.ws.send(json.dumps({"type": "CloseStream"}))
            except Exception:
                pass
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None
        if self._reader is not None:
            self._reader.cancel()
            self._reader = None
        try:
            self._out.put_nowait(None)  # type: ignore[arg-type]
        except Exception:
            pass


# ---------------------------------------------------------------------------
# La bocca
# ---------------------------------------------------------------------------

#     MILLE MILLISECONDI SONO POCHI PER UN VOCATIVO.
# Tre telefonate su tre hanno chiuso il turno su «Ciao ORA» mentre la persona
# stava dicendo «che giorno è oggi»: dopo un nome, la pausa di chi parla è più
# lunga di un secondo. ORA rispondeva al saluto e si faceva interrompere dal
# resto della domanda. Millecinquecento costano mezzo secondo su un'attesa che
# ne dura otto, e comprano di non tagliare la gente a metà frase.


class Speaking:
    """Aura-2 in italiano, su un socket che resta aperto per tutta la chiamata."""

    name = NAME

    def __init__(self, *, rate: int = RATE, voice: str = "") -> None:
        self.rate = rate
        self.voice = (voice or os.environ.get("ORA_PHONE_VOICE") or "aura-2-cesare-it").strip()
        self.ws = None
        self.connect_ms: Optional[int] = None
        self._closed = False
        self._cancelled = False
        # Gli abbiamo detto di smettere e non abbiamo ancora letto la sua
        # conferma. Finché è vero, sul filo c'è roba del turno precedente.
        self._awaiting_cleared = False

    def is_available(self) -> bool:
        return is_configured()

    def _url(self) -> str:
        return (
            f"wss://{_host()}/v1/speak"
            f"?model={self.voice}&encoding=linear16&sample_rate={self.rate}"
        )

    async def open(self) -> bool:
        if not self.is_available():
            return False
        try:
            import websockets
        except ImportError:
            return False
        began = time.perf_counter()
        try:
            self.ws = await websockets.connect(
                self._url(), additional_headers=_auth(), max_size=None, open_timeout=15,
            )
        except Exception as e:
            logger.info("voce non aperta: %s", type(e).__name__)
            return False
        self.connect_ms = int((time.perf_counter() - began) * 1000)
        return True

    async def speak(
        self,
        text_chunks: AsyncIterator[str],
        *,
        on_audio: Callable[[bytes], Awaitable[None]],
    ) -> Spoke:
        """
        Dice quello che arriva, e consegna l'audio man mano che esce.

        Oggi `text_chunks` porta un pezzo solo, perché il core risponde tutto
        insieme. Il giorno che ne porterà venti, qui non cambia niente.
        """
        out = Spoke()
        if self.ws is None:
            out.failed = "not_open"
            return out
        await self._swallow_what_was_left()
        self._cancelled = False
        began = time.perf_counter()

        try:
            sent_any = False
            async for piece in text_chunks:
                words = (piece or "").strip()
                if not words:
                    continue
                await self.ws.send(json.dumps({"type": "Speak", "text": words}))
                sent_any = True
            if not sent_any:
                out.failed = "nothing_to_say"
                return out
            # `Flush` chiede quello che è rimasto in canna: senza, l'ultima
            # frase resta dentro il fornitore.
            await self.ws.send(json.dumps({"type": "Flush"}))
        except Exception as e:
            out.failed = type(e).__name__
            return out

        try:
            while True:
                if self._cancelled:
                    out.cancelled = True
                    break
                msg = await asyncio.wait_for(self.ws.recv(), timeout=20)
                if isinstance(msg, (bytes, bytearray)):
                    if out.first_audio_ms is None:
                        out.first_audio_ms = int((time.perf_counter() - began) * 1000)
                    out.bytes_out += len(msg)
                    out.generated_ms = int(out.bytes_out / 2 / self.rate * 1000)
                    await on_audio(bytes(msg))
                else:
                    kind = json.loads(msg).get("type", "")
                    if kind == "Cleared":
                        # La conferma dell'interruzione: l'abbiamo letta noi,
                        # quindi il turno prossimo non la troverà in faccia.
                        self._awaiting_cleared = False
                        break
                    if kind == "Flushed":
                        break
                    if kind in ("Error", "Warning"):
                        out.failed = kind
                        break
        except asyncio.TimeoutError:
            out.failed = "timeout"
        except Exception as e:
            out.failed = type(e).__name__
        return out

    async def cancel(self) -> None:
        """
        Smetti di parlare, adesso.

            `CLEAR` SVUOTA ANCHE QUELLO CHE IL FORNITORE AVEVA IN CANNA.

        Senza, il fornitore continuerebbe a generare la frase intera e a
        mandarla: la persona che ha interrotto sentirebbe ORA finire il
        discorso da sola, che è la cosa più fastidiosa che un assistente possa
        fare al telefono.
        """
        self._cancelled = True
        if self.ws is None:
            return
        try:
            await self.ws.send(json.dumps({"type": "Clear"}))
            self._awaiting_cleared = True
        except Exception as e:
            logger.info("interruzione non consegnata: %s", type(e).__name__)

    async def _swallow_what_was_left(self) -> None:
        """
        Quello che era rimasto sul filo dopo un'interruzione.

            UN «CLEARED» NON LETTO DIVENTA LA RISPOSTA DEL TURNO DOPO.

        Misurato su una telefonata vera, ed è il difetto peggiore di tutto lo
        sprint perché non somigliava a un guasto. Chi interrompe fa annullare
        il giro che stava parlando: quel giro muore dentro `recv()`, e la
        conferma dell'interruzione resta lì. Il turno seguente manda `Speak` e
        `Flush`, legge il primo messaggio che trova — quello — e se ne va
        convinto di aver finito. Quattro millisecondi, zero byte, **nessun
        errore**. Da lì in poi ORA non parla mai più, e chi sta al telefono
        sente soltanto silenzio.

        Qui si butta tutto quello che appartiene a prima: l'audio già generato
        e la conferma. Se nessuno ha interrotto, non si aspetta niente.
        """
        if not self._awaiting_cleared or self.ws is None:
            return
        self._awaiting_cleared = False
        deadline = time.perf_counter() + 2.0
        while time.perf_counter() < deadline:
            try:
                msg = await asyncio.wait_for(self.ws.recv(), timeout=0.4)
            except asyncio.TimeoutError:
                return
            except Exception as e:
                logger.info("filo della voce interrotto: %s", type(e).__name__)
                return
            if isinstance(msg, (bytes, bytearray)):
                continue        # audio di prima: non lo sentirà nessuno
            try:
                if json.loads(msg).get("type") == "Cleared":
                    return
            except Exception:
                return

    async def close(self) -> None:
        self._closed = True
        if self.ws is not None:
            try:
                await self.ws.send(json.dumps({"type": "Close"}))
            except Exception:
                pass
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None
