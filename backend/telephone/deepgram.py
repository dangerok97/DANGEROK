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
from typing import Any, AsyncIterator, Awaitable, Callable, List, Optional

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


#     FLUX DECIDE IL TURNO, NON LO CRONOMETRA.
#
# Nova-3 dice quando c'è del suono e quando c'è del silenzio; chi lo ascolta
# deve indovinare se la frase è finita, e misurato indovina male. Flux ha un
# modello che guarda il significato e manda `EndOfTurn` quando una persona ha
# davvero finito di parlare.
#
# Quanta confidenza serve perché un turno sia chiuso. **Misurato**, su «Ciao
# ORA. Dimmi che giorno è oggi.» detta da una voce vera:
#
#     «Ciao ORA, che giorno è oggi?»        «Che giorno è oggi?»
#     0,80 → DUE turni                       un turno
#     0,90 → DUE turni                       un turno
#     0,95 → un turno, 614 ms                un turno, 175 ms
#     1,00 → nessun turno: si chiude solo a scadenza
#
#     «CIAO ORA» È DAVVERO UN TURNO COMPLETO, E FLUX HA RAGIONE.
#
# È un saluto: chi lo sente potrebbe benissimo rispondere «ciao». Il modello
# non sbaglia — sta descrivendo la lingua. Siamo noi a volere che un vocativo
# resti attaccato a quello che segue, e il modo di dirglielo è chiedere più
# confidenza prima di chiudere.
#
# Zero-virgola-novantacinque è il primo valore che tiene insieme il vocativo,
# e non costa niente dove conta: una domanda diretta viene chiusa in 175-519
# millisecondi. Le affermazioni sono più lente — «Domani devo andare dal
# dentista» impiega 1.836 ms — ma restano intere, che è la cosa per cui una
# persona vera ha dovuto ripetere una domanda al telefono.
FLUX_EOT_THRESHOLD = 0.95

# Sotto quanta confidenza si dice soltanto «forse ha finito». Serve alle
# misure e a niente altro: in questo sprint nessun pensiero parte da qui.
FLUX_EAGER_THRESHOLD = 0.8

# Quanto silenzio prima che Flux chiuda comunque un turno, quando il suo
# modello non si decide. È la sua rete di sicurezza, non la nostra.
FLUX_EOT_TIMEOUT_MS = 5000

#     VENTI MILLISECONDI ALLA VOLTA SONO TROPPO POCHI PER LUI.
#
# Vonage consegna pacchetti da venti millisecondi; Deepgram consiglia ottanta
# per Flux. Non è una preferenza estetica: **misurato**, sulla stessa frase,
# `EndOfTurn` è arrivato a 1.252 ms dalla fine del parlato mandando venti
# millisecondi alla volta, e a **786 ms** mandandone ottanta. Quattrocentosessanta
# millisecondi di differenza, a favore dei pacchetti più grandi.
#
# Aggregare costa: i primi tre pacchetti di ogni gruppo aspettano, fino a
# sessanta millisecondi. Si pagano volentieri per riaverne quattrocento.
FLUX_CHUNK_MS = 80


def _flux_setting(name: str, fallback: float) -> float:
    try:
        return float(os.environ.get(name) or fallback)
    except ValueError:
        return fallback


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


class FluxListening:
    """
    Flux multilingue, e i turni li decide lui.

    Stessa forma di `Listening`: si apre, si nutre di PCM, produce `Heard`.
    Quello che cambia è cosa sa dire — non «c'è del silenzio» ma «ha finito
    di parlare, ed ecco tutto quello che ha detto».

        IL TRANSCRIPT DEFINITIVO ARRIVA INTERO, UNA VOLTA SOLA.

    Non ci sono pezzi da accumulare: `EndOfTurn` porta la frase completa. Gli
    aggiornamenti intermedi servono solo a sapere che qualcuno sta parlando —
    e a riconoscere la propria voce quando la linea la riporta indietro.
    """

    name = NAME
    # Chi usa questo oggetto sa che non deve indovinare la fine del turno.
    decides_turns = True

    def __init__(self, *, rate: int = RATE, language: str = "it") -> None:
        self.rate = rate
        self.language = language
        self.ws = None
        self.connect_ms: Optional[int] = None
        self._out: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._reader: Optional[asyncio.Task] = None
        self._opened_at = 0.0
        self._closed = False
        # Il pezzo di audio che si sta mettendo insieme per arrivare a ottanta
        # millisecondi. Passa e non resta: appena è pieno viene mandato e
        # svuotato, e non ne esiste mai più di uno.
        self._holding = bytearray()
        self._chunk_bytes = int(self.rate * FLUX_CHUNK_MS / 1000) * 2

    def is_available(self) -> bool:
        return is_configured()

    def _url(self) -> str:
        eot = _flux_setting("ORA_FLUX_EOT_THRESHOLD", FLUX_EOT_THRESHOLD)
        eager = _flux_setting("ORA_FLUX_EAGER_THRESHOLD", FLUX_EAGER_THRESHOLD)
        bits = [
            "model=flux-general-multi",
            f"language_hint={self.language}",
            "encoding=linear16",
            f"sample_rate={self.rate}",
            f"eot_threshold={eot}",
            f"eot_timeout_ms={int(FLUX_EOT_TIMEOUT_MS)}",
        ]
        # L'eager si accende solo per essere misurato. Deepgram pretende che
        # non superi la soglia vera, e ha ragione: un «forse» più sicuro di un
        # «sì» non vorrebbe dire niente.
        if 0 < eager <= eot:
            bits.append(f"eager_eot_threshold={eager}")
        return f"wss://{_host()}/v2/listen?" + "&".join(bits)

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
                self._url(), additional_headers=_auth(), max_size=None,
                open_timeout=15,
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
        """
        Traduce gli eventi di Flux nel contratto.

            IL TIPO DEL TURNO STA IN `event`, NON IN `type`.

        Scoperto sul socket e non sui documenti: ogni messaggio è un
        `TurnInfo`, e dentro c'è `event` che dice quale dei cinque è.
        """
        try:
            async for raw in self.ws:  # type: ignore[union-attr]
                if not isinstance(raw, str):
                    continue
                try:
                    e = json.loads(raw)
                except Exception:
                    continue

                tipo = e.get("type") or ""
                if tipo in ("Error", "FatalError"):
                    # Il tipo di errore, mai una parola di quello che è stato
                    # detto e mai un campione di audio.
                    logger.info(
                        "ascolto: %s",
                        str(e.get("description") or e.get("code") or tipo)[:80],
                    )
                    continue
                if tipo != "TurnInfo":
                    continue

                evento = e.get("event") or ""
                testo = (e.get("transcript") or "").strip()
                quando = self._ms()
                indice = e.get("turn_index")
                sicurezza = e.get("end_of_turn_confidence")

                if evento == "StartOfTurn":
                    await self._say(Heard(
                        "speech_started", at_ms=quando, raw=evento,
                        turn_index=indice,
                    ))
                    if testo:
                        await self._say(Heard(
                            "partial", testo, quando, raw=evento,
                            turn_index=indice,
                        ))

                elif evento == "Update":
                    # Un'ipotesi: non esce mai di qui, e serve a sapere che
                    # qualcuno sta parlando.
                    if testo:
                        await self._say(Heard(
                            "partial", testo, quando, raw=evento,
                            turn_index=indice,
                        ))

                elif evento == "EagerEndOfTurn":
                    await self._say(Heard(
                        "eager_end", testo, quando, confidence=sicurezza,
                        raw=evento, turn_index=indice,
                    ))

                elif evento == "TurnResumed":
                    await self._say(Heard(
                        "turn_resumed", testo, quando, confidence=sicurezza,
                        raw=evento, turn_index=indice,
                    ))

                elif evento == "EndOfTurn":
                    await self._say(Heard(
                        "end_of_turn", testo, quando, confidence=sicurezza,
                        trigger=str(e.get("trigger") or ""), raw=evento,
                        turn_index=indice,
                    ))
        except Exception as e:
            if not self._closed:
                logger.info("ascolto interrotto: %s", type(e).__name__)

    async def _say(self, heard: Heard) -> None:
        try:
            self._out.put_nowait(heard)
        except asyncio.QueueFull:
            try:
                self._out.get_nowait()
                self._out.put_nowait(heard)
            except Exception:
                pass

    async def hear(self, pcm: bytes) -> None:
        """
        Quattro pacchetti del telefono diventano uno per chi ascolta.

            PASSA E NON RESTA, COME PRIMA.

        L'unico accumulo è il gruppo che si sta componendo: al massimo sessanta
        millisecondi, e appena è pieno se ne va. Nessuna coda che cresce,
        nessun file, nessun campo.
        """
        if self.ws is None or not pcm:
            return
        self._holding.extend(pcm)
        while len(self._holding) >= self._chunk_bytes:
            pezzo = bytes(self._holding[: self._chunk_bytes])
            del self._holding[: self._chunk_bytes]
            try:
                await self.ws.send(pezzo)
            except Exception as e:
                if not self._closed:
                    logger.info(
                        "audio non consegnato all'ascolto: %s", type(e).__name__,
                    )
                return

    async def events(self) -> AsyncIterator[Heard]:
        while True:
            heard = await self._out.get()
            if heard is None:  # type: ignore[comparison-overlap]
                return
            yield heard

    async def close(self) -> None:
        self._closed = True
        self._holding.clear()
        if self._reader is not None and not self._reader.done():
            self._reader.cancel()
        if self.ws is not None:
            try:
                await self.ws.send(json.dumps({"type": "CloseStream"}))
            except Exception:
                pass
            try:
                await self.ws.close()
            except Exception:
                pass


def the_ear() -> Any:
    """
    Chi ascolta questa telefonata.

        SI CAMBIA ORECCHIO DA UNA RIGA DI CONFIGURAZIONE.

    `ORA_VOICE_STT=flux` passa al modello che decide i turni; qualunque altro
    valore — compreso nessun valore — lascia Nova-3 dov'era. Il valore di
    riposo è prudente apposta: il modello nuovo si accende quando qualcuno
    decide di accenderlo.
    """
    scelto = (os.environ.get("ORA_VOICE_STT") or "nova3").strip().lower()
    if scelto == "flux":
        return FluxListening()
    return Listening()


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
