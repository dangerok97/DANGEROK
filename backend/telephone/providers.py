"""
Chi ascolta e chi parla, come contratti.

    IL RUNTIME DEL TELEFONO NON DEVE SAPERE IL NOME DI NESSUN FORNITORE.

Si è già cambiato operatore telefonico due volte in due sprint — Twilio,
Telnyx, Vonage — e ogni volta è costato un file solo perché il trasporto stava
dietro un contratto. Qui si fa la stessa cosa per l'orecchio e per la bocca,
prima di averne bisogno: il giorno che un fornitore alza i prezzi, perde
l'italiano o smette di rispondere, quello che cambia è l'implementazione.

Due cose che questi contratti fanno apposta.

**Gli eventi dell'ascolto sono normalizzati.** Ogni fornitore ha nomi suoi —
`SpeechStarted`, `is_final`, `speech_final`, `UtteranceEnd` — e chi decide di
chi è il turno non deve impararli. Quello che esce di qui sono cinque fatti:
ha cominciato, ecco un pezzo provvisorio, ecco un pezzo definitivo, qui c'era
una pausa, qui il turno sembra finito.

**La bocca accetta testo a pezzi anche se oggi glielo diamo intero.** Il core
di ORA non streamma — misurato, guadagnerebbe centocinquanta millisecondi su
tremila — ma un giorno lo farà, o cambierà modello. `speak()` prende un
iterabile asincrono di pezzi di testo: oggi gliene passiamo uno solo, e il
giorno che diventano venti non si riscrive niente.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Protocol,
)

# Che cosa può dire chi ascolta. Cinque fatti, nessun nome di fornitore.
HeardKind = Literal[
    # Qualcuno ha cominciato a parlare. Serve al barge-in, e arriva prima
    # di qualunque parola.
    "speech_started",
    # Un pezzo che può ancora cambiare. Non entra mai nel Conversation Engine.
    "partial",
    # Un pezzo che non cambia più. Si accumula, ma da solo non è un turno.
    "final",
    # Qui c'era una pausa naturale. È un indizio di confine, non una fine:
    # misurato su una frase vera, è scattato dopo «Ciao, ORA» mentre la
    # persona stava ancora parlando.
    "pause",
    # Un silenzio abbastanza lungo da far pensare che abbia finito.
    "utterance_end",

    #     E TRE FATTI DA CHI IL TURNO LO DECIDE DAVVERO.
    #
    # I cinque qui sopra descrivono il **suono**: qualcuno parla, ecco delle
    # parole, c'è stato un silenzio. Chi li riceve deve poi indovinare se la
    # frase è finita, e misurato indovina male: su «Ciao ORA, dimmi che giorno
    # è oggi» un trascrittore a tempo ha chiuso il turno dopo il vocativo.
    #
    # Questi tre arrivano invece da un modello che guarda il **significato** e
    # dice lui quando un turno finisce. Chi ascolta smette di essere un
    # cronometro e diventa qualcuno che capisce quando hai finito di parlare.

    # Il turno è finito, e questo è tutto quello che è stato detto. Non è un
    # pezzo da accumulare: è la frase intera, ed è autorevole.
    "end_of_turn",
    # Sembra finito, con meno confidenza. Si registra e basta: far partire un
    # pensiero qui dentro è lo Sprint dopo, e per adesso non lo si fa.
    "eager_end",
    # Non era finito: la persona ha ripreso. Annulla l'indizio di prima.
    "turn_resumed",
]


@dataclass
class Heard:
    """Una cosa che chi ascolta ha da dire."""

    kind: HeardKind
    text: str = ""
    at_ms: int = 0
    # Quanto è sicuro chi ascolta che il turno sia finito, quando lo sa dire.
    # Un numero, non una parola di quello che è stato detto.
    confidence: Optional[float] = None
    # Che cosa ha chiuso il turno: il modello, il silenzio, o noi.
    trigger: str = ""
    # Quale turno della telefonata. Serve a legare i tempi al turno giusto.
    turn_index: Optional[int] = None
    # Quello che il fornitore ha detto, per poterlo leggere in un log tecnico
    # senza che il resto del codice lo interpreti.
    raw: str = ""


class StreamingSpeechInputProvider(Protocol):
    """
    Chi ascolta una telefonata mentre succede.

    Si apre una volta per chiamata e resta aperto: misurato, la stretta di
    mano verso l'Europa costa mezzo secondo, e pagarla a ogni turno sarebbe un
    terzo del tempo di risposta buttato.
    """

    name: str

    def is_available(self) -> bool:
        """Se adesso, con quello che c'è configurato, può ascoltare."""

    async def open(self) -> bool:
        """Apre la linea. `False` quando non ci riesce."""

    async def hear(self, pcm: bytes) -> None:
        """Un pacchetto di audio, così come arriva dalla linea."""

    def events(self) -> AsyncIterator[Heard]:
        """Quello che ha capito, mentre lo capisce."""

    async def close(self) -> None:
        """Chiude la linea e lascia andare tutto."""


class StreamingSpeechOutputProvider(Protocol):
    """
    Chi dice una frase, a pezzi, mentre la si genera.

    `speak` prende un flusso di testo perché un giorno il core lo produrrà a
    pezzi. Oggi gliene arriva uno solo e va bene così: l'interfaccia non
    cambierà.

    `cancel` è la metà che conta per il barge-in: deve poter fermare la
    generazione *e* dire al fornitore di buttare quello che aveva in coda.
    """

    name: str

    def is_available(self) -> bool: ...

    async def open(self) -> bool: ...

    async def speak(
        self, text_chunks: AsyncIterator[str], *, on_audio: Callable[[bytes], Awaitable[None]],
    ) -> "Spoke": ...

    async def cancel(self) -> None:
        """Smetti di generare e butta via quello che avevi in coda."""

    async def close(self) -> None: ...


@dataclass
class Spoke:
    """Com'è andata a dire una frase."""

    # Millisecondi dal primo pezzo di testo al primo byte di audio.
    first_audio_ms: Optional[int] = None
    # Quanto audio è stato generato, in millisecondi di parlato.
    generated_ms: int = 0
    bytes_out: int = 0
    cancelled: bool = False
    failed: str = ""


async def one_piece(text: str) -> AsyncIterator[str]:
    """
    Un testo intero, travestito da flusso.

    Serve finché il core risponde tutto insieme, e sparirà da sé il giorno che
    smetterà di farlo — senza che il runtime del telefono se ne accorga.
    """
    if text:
        yield text
