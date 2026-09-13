"""
Quello che ORA sta dicendo, mentre esce sulla linea.

    SI PARLA ALLA VELOCITÀ A CUI SI VIENE ASCOLTATI.

Rovesciare quattro secondi di voce dentro un websocket tutti insieme non li fa
arrivare prima: li fa arrivare a scatti, o li fa buttare via da una coda che
non li aspettava. Venti millisecondi alla volta, ogni venti millisecondi.

E l'altra metà, che è quella che rende sopportabile una telefonata:

    QUANDO QUALCUNO INTERROMPE, IL SILENZIO DEVE ESSERE IMMEDIATO.

Per questo ogni risposta parlata ha una maniglia. Non si «smette di mandare»:
si annulla una cosa che ha un nome, un numero e un turno, e da quel momento
tutto ciò che apparteneva a quella risposta viene buttato — anche i pacchetti
che arrivano dopo, anche quelli già in coda. Un pacchetto in ritardo che
scivola fuori dopo l'annullamento è ORA che dice mezza sillaba a vuoto, e si
sente.

Quello che non si può riprendere è ciò che ha già lasciato il server. Su
questo filo non esiste un richiamo: è un limite reale, misurato in un
pacchetto — venti millisecondi — e dichiarato invece che nascosto.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, List, Optional

logger = logging.getLogger("ora.telephone.playback")

FRAME_MS = 20
RATE = 16000
FRAME_BYTES = int(RATE * FRAME_MS / 1000) * 2

# Quanto audio si accetta di tenere in coda. Oltre, la voce è così indietro
# rispetto alla conversazione che è meglio perderne un pezzo che dirlo tardi.
MAX_QUEUED_MS = 4000


@dataclass
class SpeechGenerationHandle:
    """
    Una risposta parlata, con il filo per tirarla indietro.

    Esiste perché «annullare» dev'essere una cosa che si può fare a un
    oggetto preciso: senza, l'annullamento è una variabile globale che
    qualcuno dimentica di controllare.
    """

    generation_id: str
    turn_id: int
    cancelled: bool = False
    generated_audio_ms: int = 0
    queued_audio_ms: int = 0
    sent_audio_ms: int = 0
    started_at: float = field(default_factory=time.perf_counter)

    def cancel(self) -> None:
        self.cancelled = True

    def as_dict(self) -> dict:
        return {
            "generation_id": self.generation_id,
            "turn_id": self.turn_id,
            "cancelled": self.cancelled,
            "generated_audio_ms": self.generated_audio_ms,
            "queued_audio_ms": self.queued_audio_ms,
            "sent_audio_ms": self.sent_audio_ms,
        }


class PlaybackController:
    """
    La coda verso la linea, e chi decide quando smettere.

    Un pacchetto alla volta, al ritmo del parlato. Niente di quello che passa
    di qui viene conservato: si manda e si dimentica.
    """

    def __init__(
        self,
        *,
        send: Callable[[bytes], Awaitable[None]],
        clear_transport: Optional[Callable[[], Awaitable[None]]] = None,
        frame_bytes: int = FRAME_BYTES,
        frame_ms: int = FRAME_MS,
    ) -> None:
        self._send = send
        self._clear_transport = clear_transport
        self.frame_bytes = frame_bytes
        self.frame_ms = frame_ms

        self._queue: asyncio.Queue = asyncio.Queue()
        self._leftover = b""
        self._pump: Optional[asyncio.Task] = None
        self.current: Optional[SpeechGenerationHandle] = None
        self.bytes_sent = 0
        self.frames_sent = 0
        self.frames_dropped = 0

    # --- una risposta alla volta ------------------------------------------

    def begin(self, *, generation_id: str, turn_id: int) -> SpeechGenerationHandle:
        """Comincia una risposta parlata. Da qui in poi c'è qualcosa da fermare."""
        self.current = SpeechGenerationHandle(
            generation_id=generation_id, turn_id=turn_id,
        )
        self._leftover = b""
        if self._pump is None or self._pump.done():
            self._pump = asyncio.create_task(self._keep_pouring())
        return self.current

    async def feed(self, pcm: bytes, handle: SpeechGenerationHandle) -> None:
        """
        Audio appena generato. Si taglia a pacchetti e si mette in coda.

        Il pezzo che avanza resta qui: mandare mezzo pacchetto fa scattare la
        voce, e i fornitori non consegnano l'audio a multipli di venti
        millisecondi.
        """
        if handle.cancelled or self.current is not handle or not pcm:
            return
        handle.generated_audio_ms += int(len(pcm) / 2 / RATE * 1000)

        buf = self._leftover + pcm
        cut = len(buf) - (len(buf) % self.frame_bytes)
        self._leftover = buf[cut:]
        for i in range(0, cut, self.frame_bytes):
            if handle.cancelled:
                return
            if handle.queued_audio_ms - handle.sent_audio_ms > MAX_QUEUED_MS:
                # Siamo troppo indietro: meglio perdere un pacchetto che
                # parlare sopra una conversazione già andata avanti.
                self.frames_dropped += 1
                continue
            self._queue.put_nowait((handle, buf[i:i + self.frame_bytes]))
            handle.queued_audio_ms += self.frame_ms

    async def finish(self, handle: SpeechGenerationHandle) -> None:
        """Non c'è altro audio da generare: si aspetta che la coda si svuoti."""
        if handle.cancelled or self.current is not handle:
            return
        if self._leftover:
            # L'ultimo pezzo si completa con silenzio, o scatta.
            tail = self._leftover + b"\x00" * (self.frame_bytes - len(self._leftover))
            self._queue.put_nowait((handle, tail))
            handle.queued_audio_ms += self.frame_ms
            self._leftover = b""
        while not handle.cancelled and handle.sent_audio_ms < handle.queued_audio_ms:
            await asyncio.sleep(self.frame_ms / 1000.0)

    # --- fermarsi ---------------------------------------------------------

    async def cancel(self) -> int:
        """
        Smetti adesso. Torna quanti pacchetti sono stati buttati.

        Si annulla la maniglia *prima* di svuotare la coda: così un pacchetto
        che arriva nel frattempo trova già la porta chiusa e non scivola fuori
        dopo il silenzio.
        """
        handle = self.current
        if handle is None:
            return 0
        handle.cancel()

        thrown = 0
        while True:
            try:
                self._queue.get_nowait()
                thrown += 1
            except asyncio.QueueEmpty:
                break
        self._leftover = b""
        self.frames_dropped += thrown

        if self._clear_transport is not None:
            try:
                await self._clear_transport()
            except Exception as e:
                logger.info("coda del trasporto non svuotata: %s", type(e).__name__)
        return thrown

    # --- il rubinetto -----------------------------------------------------

    async def _keep_pouring(self) -> None:
        """Un pacchetto ogni venti millisecondi, finché c'è qualcosa da dire."""
        try:
            while True:
                handle, frame = await self._queue.get()
                if handle.cancelled or self.current is not handle:
                    # Arrivato dopo l'annullamento: si butta senza mandarlo.
                    self.frames_dropped += 1
                    continue
                try:
                    await self._send(frame)
                except Exception as e:
                    logger.info("pacchetto non consegnato: %s", type(e).__name__)
                    continue
                handle.sent_audio_ms += self.frame_ms
                self.bytes_sent += len(frame)
                self.frames_sent += 1
                await asyncio.sleep(self.frame_ms / 1000.0)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.info("rubinetto chiuso: %s", type(e).__name__)

    async def close(self) -> None:
        """La linea si chiude: si lascia andare tutto."""
        await self.cancel()
        if self._pump is not None:
            self._pump.cancel()
            self._pump = None
        self.current = None

    def how_it_went(self) -> dict:
        return {
            "frames_sent": self.frames_sent,
            "bytes_sent": self.bytes_sent,
            "frames_dropped": self.frames_dropped,
        }
