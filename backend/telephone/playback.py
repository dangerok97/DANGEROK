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

#     ESSERE AVANTI NON È ESSERE IN RITARDO.
#
# Qui c'era un tetto di quattro secondi sulla coda, con questa motivazione:
# «se siamo così indietro rispetto alla conversazione, meglio perdere un
# pacchetto che dirlo tardi». La motivazione era giusta e la misura sbagliata.
#
# Confrontava **quanto è stato generato** con **quanto è stato mandato** — e
# chi genera la voce produce cinque secondi di audio in uno. Stare avanti è lo
# stato normale: è quello che rende il parlato continuo invece che a scatti.
# Quindi la coda superava sempre il tetto, si buttavano pacchetti, il
# contatore dei mandati avanzava, si riapriva, si buttava ancora.
#
# Misurato su una telefonata vera: **128 frame buttati su 610, il ventuno per
# cento della voce di ORA**, distribuiti dentro le frasi. Chi ascoltava ha
# sentito «oggi è lunedì 14 settembre duemilave» e «domani non hai impegn», e
# poi qualcosa che sembrava ORA che parlava sopra sé stessa. Non era un
# problema di modello né di linea: era questa riga.
#
# Il caso che quella regola voleva davvero coprire — la conversazione è andata
# avanti e questa risposta non serve più — è già coperto da `cancel()`, che
# svuota tutto in sedici millisecondi misurati. Quello è il rimedio giusto:
# smettere di dire una cosa intera, non dirla bucata.
#
# Quello che resta qui è solo una difesa contro l'assurdo: una coda che cresce
# senza fine perché qualcosa si è rotto. Due minuti di parlato sono più lunghi
# di qualunque risposta che ORA abbia mai prodotto, e se si arrivasse lì
# sarebbe un guasto da vedere nei numeri, non un ritmo da assecondare.
MAX_QUEUED_MS = 120_000

#     QUANTO SI ASPETTA UN BATTITO PRIMA DI CONTARE DA SOLI.
# La linea ne manda uno ogni venti millisecondi — misurato su tre telefonate
# vere: 49,1 · 49,4 · 49,1 al secondo, silenzi compresi. Sessanta millisecondi
# sono tre battiti mancati di fila: abbastanza per dire che il trasporto si e'
# fermato, poco abbastanza da non lasciare un buco udibile.
NO_BEAT_AFTER_S = 0.060

#     IL CREDITO DICE SE. LA SCADENZA DICE QUANDO.
# Mai due pacchetti piu vicini di cosi. Serve solo quando il rubinetto si e
# svegliato tardi e ha piu crediti in mano: recupera, ma a una velocita che
# resta telefonicamente sensata. In condizioni normali i crediti arrivano ogni
# venti millisecondi e questa soglia non tocca niente.
MIN_GAP_S = 0.008

#     SOTTO QUESTA SOGLIA NON SI CHIEDE PIU' AL TIMER.
# Misurato su questa macchina: `sleep(20 ms)` ne dorme 31, `sleep(8 ms)` ne
# dorme 0,3. Gli ultimi millisecondi prima di una scadenza si passano cedendo
# il controllo e richiedendo che ora e', non affidandosi a un'attesa.
TOO_SHORT_TO_SLEEP_S = 0.003

#     CEDERE IL CONTROLLO NON E' ASPETTARE.
#
# `sleep(0)` promette di lasciar lavorare gli altri, e mantiene: torna appena
# non c'e' nessun altro pronto. Quando non c'e' nessun altro pronto torna
# **subito**, e un ciclo che lo richiama fino alla scadenza diventa un giro a
# vuoto travestito da buona educazione.
#
# Misurato su una telefonata vera: 459 attese su 513 sono tornate presto, e
# ognuna ha prodotto migliaia di cessioni — 1.549.103 in settantanove secondi,
# quasi ventimila al secondo. Il costo non e' il processore: e' che fra una
# cessione e l'altra il loop deve passare da chi legge il filo audio, e con
# ventimila passaggi al secondo quella lettura arriva tardi. Il buco peggiore
# fra due pacchetti e' stato di quindici secondi.
#
# Quindi si cede un paio di volte — che e' il caso in cui davvero c'e'
# qualcun altro pronto e basta lasciarlo passare — e poi si dorme per davvero.
# Un pisolino breve puo' tornare presto, e va benissimo: la scadenza e' un
# orario e si riguarda comunque. Quello che cambia e' il prezzo di riguardare,
# che da un giro a vuoto diventa un risveglio.
YIELDS_BEFORE_A_REAL_NAP = 2
SHORT_NAP_S = 0.002

#     E UN'ULTIMA USCITA, PER UN OROLOGIO CHE NON SI MUOVE AFFATTO.
#
# Il pisolino fisso termina con qualunque timer che avanzi un po'. Con uno che
# non avanza per niente — non esiste su una macchina vera, esiste in una prova
# che lo riproduce apposta — dormire all'infinito sarebbe restare appesi, e
# restare appesi e' peggio di qualunque imprecisione. Oltre questo numero di
# giri si torna a cedere il controllo, che e' l'unica cosa che fa progredire
# un loop comunque sia fatto l'orologio.
#
# Duecento e' irraggiungibile in esercizio: con la barriera a otto
# millisecondi i giri misurati sono fra quattro e quaranta.
TOO_MANY_TURNS = 200


class BeatCredits:
    """
    I battiti della linea, contati invece che segnalati.

        UN TICK, UN CREDITO. UN CREDITO, UN PACCHETTO.

    Se il rubinetto resta indietro e nel frattempo la linea batte tre volte,
    deve trovare tre crediti — non uno. E' l'unica differenza col vecchio
    Event, ed e' la differenza fra duecentosette battiti persi e nessuno.
    """

    def __init__(self) -> None:
        self._n = 0
        self._wake = asyncio.Event()
        #     QUANDO SI E' PAGATO SENZA CREDITO, SI DEVE UN CREDITO.
        # Un frame mandato dal ripiego ha gia consumato il suo tempo: quando i
        # battiti tornano, il primo che arriva pareggia quel debito invece di
        # autorizzare un pacchetto in piu. Senza questo, ogni buco di linea
        # lascerebbe dietro una raffica.
        self._owed = 0

        self.produced = 0
        self.consumed = 0
        self.peak = 0
        self.reconciled = 0

    # --- chi li produce ----------------------------------------------------

    def release(self) -> None:
        """La linea ha battuto."""
        #     UN BATTITO ARRIVATO E' UN BATTITO PRODOTTO, SEMPRE.
        # Anche quando serve a pagare un debito invece che ad autorizzare un
        # pacchetto. Contandolo solo fra i riconciliati l'invariante non
        # tornava per esattamente il numero dei ripieghi — ventidue sulla
        # quinta telefonata — e un conto che non torna e un conto che non si
        # puo usare per dire «nessun credito e sparito».
        self.produced += 1
        if self._owed:
            # Prima si pareggiano i conti, poi si autorizza.
            self._owed -= 1
            self.reconciled += 1
            return
        self._n += 1
        self.peak = max(self.peak, self._n)
        self._wake.set()

    # --- chi li consuma ----------------------------------------------------

    async def acquire(self, timeout: float) -> bool:
        """Un credito, o `False` se la linea ha smesso di battere."""
        if self._n <= 0:
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout)
            except asyncio.TimeoutError:
                self._owed += 1
                return False
        if self._n <= 0:
            self._owed += 1
            return False
        self._n -= 1
        self.consumed += 1
        if self._n <= 0:
            self._wake.clear()
        return True

    # --- e chi butta quelli scaduti ----------------------------------------

    def forget_the_old_ones(self) -> int:
        """
        I crediti maturati mentre non c'era niente da dire.

        Rappresentano tempo passato in silenzio: tenerli vorrebbe dire aprire
        la frase successiva con una raffica di pacchetti tutti insieme.
        """
        quanti = self._n
        self._n = 0
        self._owed = 0
        self.reconciled += quanti
        self._wake.clear()
        return quanti

    @property
    def pending(self) -> int:
        return self._n

    @property
    def owed(self) -> int:
        return self._owed

    def how_it_went(self) -> dict:
        return {
            "beat_credits_produced": self.produced,
            "beat_credits_consumed": self.consumed,
            "beat_credits_pending": self._n,
            "beat_credits_peak": self.peak,
            "stale_credits_dropped_or_reconciled": self.reconciled,
            "beat_credits_owed": self._owed,
        }


def _longest_run(valori, sotto: float) -> int:
    """La sequenza piu lunga di pacchetti troppo ravvicinati di fila."""
    peggio = corrente = 0
    for v in valori:
        corrente = corrente + 1 if v < sotto else 0
        peggio = max(peggio, corrente)
    return peggio


def _quantile(valori, quanto: int):
    """Il valore sotto cui sta il `quanto` per cento delle misure."""
    if not valori:
        return None
    ordinati = sorted(valori)
    dove = min(len(ordinati) - 1, int(quanto / 100 * len(ordinati)))
    return round(ordinati[dove], 1)


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
    # Se chi genera ha finito di generare. Serve al cuscinetto: non ha senso
    # aspettare margine da qualcuno che non mandera' piu' niente.
    finished: bool = False
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
        jitter_ms: int = 0,
        external_clock: bool = False,
        now=None,
        sleep=None,
    ) -> None:
        self._send = send
        self._clear_transport = clear_transport
        #     DUE FUNZIONI, NON UN FRAMEWORK.
        # Servono solo a poter provare la barriera con un orologio che sta
        # fermo quando vogliamo noi: la proprieta «non passa nessuno prima
        # della scadenza» si dimostra cosi, senza dipendere da come si
        # comporta il sistema operativo oggi.
        self._now = now or time.perf_counter
        self._sleep = sleep or asyncio.sleep
        self.frame_bytes = frame_bytes
        self.frame_ms = frame_ms
        #     UN RUBINETTO SENZA VASCA GOCCIOLA.
        # Quanto margine mettere da parte prima di cominciare a parlare. Zero
        # per chi riceve la voce gia fatta: la coda e' piena dal primo istante
        # e aspettare sarebbe solo ritardo regalato. Diverso da zero per chi
        # la riceve mentre nasce — li' la coda resta a secco all'inizio di
        # ogni risposta, e sulla linea cade il silenzio in mezzo alle parole.
        self.jitter_ms = max(0, int(jitter_ms))
        self._flowing = False
        #     CHI BATTE IL TEMPO.
        # `vonage` quando il battito arriva dal trasporto, `monotonic_fallback`
        # quando il trasporto tace e tocca a noi contare. Non e una scelta: e
        # una constatazione, e cambia da sola.
        self.external_clock = bool(external_clock)
        self.credits = BeatCredits()
        self.fallback_clock_count = 0
        self.missed_deadlines = 0
        self.consecutive_missed_max = 0
        self._missed_run = 0
        self._lateness_ms: List[float] = []
        self._anchor = None
        self._beats_expected = 0

        self._queue: asyncio.Queue = asyncio.Queue()
        self._leftover = b""
        self._pump: Optional[asyncio.Task] = None
        self.current: Optional[SpeechGenerationHandle] = None
        self.bytes_sent = 0
        self.frames_sent = 0
        self.frames_dropped = 0
        self.cushions = 0
        self.cushions_timed_out = 0
        #     UN BUCO NELLA VOCE HA CINQUE PADRI POSSIBILI.
        # Qui si tiene il conto di quelli che dipendono da questa classe: la
        # coda rimasta a secco e il passo che non ha tenuto il ritmo. Sono
        # numeri, non audio: niente di quello che passa resta.
        self.underruns = 0
        self.queue_empty_events = 0
        self._underrun_depth_ms = []      # quanto c'era in coda quando si e svuotata
        self._underrun_at_ms = []         # e quando, dall'inizio della linea
        self._waits_ms = []               # quanto si e aspettato ogni pacchetto
        self._intervals_ms = []           # quanto e passato fra un invio e l'altro
        #     I SILENZI FRA I TURNI NON SONO BUCHI NELLA VOCE.
        # Si tengono separati: solo questi si sentono come uno scatto.
        self._within_ms = []
        self._last_handle = None
        self._depth_ms = []               # quanta voce c'era in coda, pacchetto per pacchetto
        self._last_send = 0.0
        self._last_brake_ms = None    # quanto ha deciso di aspettare il freno
        self._just_filled = False     # se il pacchetto veniva da un cuscinetto
        self._why_tight = []          # e perche, quando esce troppo vicino
        #     QUANTO SPESSO LA BARRIERA E' DAVVERO ENTRATA IN GIOCO.
        # Con i battiti regolari a venti millisecondi la scadenza degli
        # otto e gia passata: la barriera guarda e lascia passare. Questi
        # numeri dicono quante volte invece ha dovuto trattenere qualcuno.
        self.barrier_waits = 0        # quante volte ha trattenuto
        self.coarse_sleeps = 0        # quante attese a tempo
        self.cooperative_yields = 0   # quante cessioni di controllo
        self.timer_lies = 0           # quante volte il timer non ha aspettato
        self.short_naps = 0           # quante attese brevi invece di girare a vuoto
        self._barrier_asked_ms = []   # quanto ha chiesto di aspettare
        self._last_send_took = None   # quanto e durata la send precedente
        self._in_fallback = False     # se il passo lo sta dando il ripiego
        self._response_started = 0.0  # quando e cominciata questa risposta
        self.turn_of_response = 0     # e a quale turno appartiene
        self._opened_at = time.perf_counter()
        self.first_send_at = None         # quando il primo pacchetto e uscito davvero

    def tick(self) -> None:
        """
        Un battito del trasporto: e' arrivato un pacchetto dalla linea.

            SI USA LA CADENZA, NON IL CONTENUTO.

        Che cosa ci sia dentro quel pacchetto non interessa a nessuno qui: si
        guarda solo che sia arrivato. Legare la voce di ORA a **quello che
        dice** l'altro sarebbe un accoppiamento sbagliato; legarla a **quando
        parla la rete** e' solo usare l'orologio giusto.
        """
        self.credits.release()

    # --- una risposta alla volta ------------------------------------------

    def begin(self, *, generation_id: str, turn_id: int) -> SpeechGenerationHandle:
        """Comincia una risposta parlata. Da qui in poi c'è qualcosa da fermare."""
        self.current = SpeechGenerationHandle(
            generation_id=generation_id, turn_id=turn_id,
        )
        self._leftover = b""
        # Ogni risposta si riempie la sua vasca: il margine di quella prima
        # se n'e' andato con lei.
        self._flowing = False
        self.first_send_at = None
        # Il ritardo si misura dentro una risposta, non dall'inizio della
        # telefonata: fra un turno e l'altro c'e' silenzio, e non e ritardo.
        self._anchor = None
        self._beats_expected = 0
        self._missed_run = 0
        self._response_started = time.perf_counter()
        self.turn_of_response = turn_id
        # I battiti maturati mentre non c'era niente da dire rappresentano
        # tempo passato in silenzio: aprirebbero la frase con una raffica.
        self.credits.forget_the_old_ones()
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
                #     SE SI ARRIVA QUI, È UN GUASTO.
                # Due minuti di parlato in coda non sono una risposta lunga:
                # sono qualcosa che non si è fermato. Si butta per non far
                # crescere la memoria all'infinito, e si lascia detto nei
                # numeri che è successo.
                self.frames_dropped += 1
                logger.info("coda della voce oltre ogni misura: pacchetto perso")
                continue
            self._queue.put_nowait((handle, buf[i:i + self.frame_bytes]))
            handle.queued_audio_ms += self.frame_ms

    async def finish(self, handle: SpeechGenerationHandle) -> None:
        """Non c'è altro audio da generare: si aspetta che la coda si svuoti."""
        if handle.cancelled or self.current is not handle:
            return
        handle.finished = True
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
        """
        Un pacchetto ogni venti millisecondi, finché c'è qualcosa da dire.

            VENTI MILLISECONDI DOPO L'ULTIMO, NON VENTI DOPO AVER FINITO.

        Prima si dormiva venti millisecondi *dopo* aver speso tempo a
        mandare: ogni pacchetto costava venti più il suo invio, e su una
        telefonata lunga la voce scivolava indietro di secondi. Adesso il
        passo è un orario, non una pausa: si dorme fino al momento giusto, e
        se si è rimasti indietro non si recupera correndo — si riparte da
        adesso, perché parlare in fretta è peggio che parlare tardi.
        """
        quando = 0.0       # quando e uscito davvero l'ultimo pacchetto
        scadenza = 0.0     # quando doveva uscire, secondo l'orologio
        try:
            while True:
                fermo_da = time.perf_counter()
                vuota = self._queue.empty()
                handle, frame = await self._queue.get()
                atteso = time.perf_counter() - fermo_da

                if handle.cancelled or self.current is not handle:
                    # Arrivato dopo l'annullamento: si butta senza mandarlo.
                    self.frames_dropped += 1
                    continue

                #     LA CODA A SECCO MENTRE SI PARLA E' UN BUCO NELLA VOCE.
                # Non quando si sta ancora riempiendo la vasca, e non quando
                # chi genera ha gia finito: li' e normale. In mezzo a una
                # frase, invece, e' esattamente lo scatto che si sente.
                if self._flowing and not handle.finished:
                    if vuota:
                        self.queue_empty_events += 1
                    if atteso > self.frame_ms / 1000.0:
                        self.underruns += 1
                        self._waits_ms.append(round(atteso * 1000, 1))
                        self._underrun_depth_ms.append(
                            handle.queued_audio_ms - handle.sent_audio_ms
                        )
                        self._underrun_at_ms.append(
                            int((time.perf_counter() - self._opened_at) * 1000)
                        )

                if not self._flowing:
                    await self._let_the_cushion_fill(handle)
                    self._flowing = True
                    self._just_filled = True
                    quando = time.perf_counter()

                partito = time.perf_counter()
                try:
                    await self._send(frame)
                except Exception as e:
                    logger.info("pacchetto non consegnato: %s", type(e).__name__)
                    continue
                adesso = time.perf_counter()
                durata = round((adesso - partito) * 1000, 2)
                if self.first_send_at is None:
                    self.first_send_at = adesso
                if self._anchor is None:
                    self._anchor = adesso
                atteso_per = self._anchor + self._beats_expected * self.frame_ms / 1000.0
                ritardo = (adesso - atteso_per) * 1000.0
                self._lateness_ms.append(round(ritardo, 1))
                self._beats_expected += 1
                if ritardo > self.frame_ms:
                    self.missed_deadlines += 1
                    self._missed_run += 1
                    self.consecutive_missed_max = max(
                        self.consecutive_missed_max, self._missed_run,
                    )
                else:
                    self._missed_run = 0
                if self._last_send:
                    quanto = round((adesso - self._last_send) * 1000, 1)
                    self._intervals_ms.append(quanto)
                    # Dentro la stessa risposta, e senza un cuscinetto in
                    # mezzo: e' li' che un buco si sente come uno scatto.
                    if self._last_handle is handle:
                        self._within_ms.append(quanto)
                        #     PERCHE' IL FRENO NON HA FRENATO.
                        # Sulla linea vera restano intervalli sotto il minimo
                        # che a banco non si riescono a riprodurre. Invece di
                        # correggere alla cieca si annota lo stato nel momento
                        # esatto: quanto aveva deciso di aspettare il freno,
                        # quanti crediti aveva in mano, se veniva da un
                        # cuscinetto. La prossima telefonata dira da che parte
                        # guardare.
                        if quanto < MIN_GAP_S * 1000 and len(self._why_tight) < 30:
                            self._why_tight.append({
                                "gap_ms": quanto,
                                "brake_ms": self._last_brake_ms,
                                "credits_pending": self.credits.pending,
                                "credits_consumed": self.credits.consumed,
                                "after_cushion": self._just_filled,
                                "fallback_active": self._in_fallback,
                                "prev_send_ms": self._last_send_took,
                                "send_ms": durata,
                                "queue_depth_ms": (
                                    handle.queued_audio_ms - handle.sent_audio_ms
                                ),
                                "turn": self.turn_of_response,
                                "ms_into_response": int(
                                    (adesso - self._response_started) * 1000
                                ) if self._response_started else None,
                                "at_ms": int((adesso - self._opened_at) * 1000),
                            })
                self._just_filled = False
                self._last_send_took = durata
                self._last_send = adesso
                self._last_handle = handle
                self._depth_ms.append(handle.queued_audio_ms - handle.sent_audio_ms)

                handle.sent_audio_ms += self.frame_ms
                self.bytes_sent += len(frame)
                self.frames_sent += 1

                quando, scadenza = await self._wait_for_the_beat(
                    quando, scadenza,
                )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.info("rubinetto chiuso: %s", type(e).__name__)

    async def _wait_for_the_beat(
        self, quando: float, scadenza: float,
    ) -> "tuple":
        """
        Aspetta il momento giusto per il prossimo pacchetto.

        Se il trasporto batte il tempo, si aspetta il suo battito e basta: e'
        la cadenza della rete telefonica, che non dipende dalla risoluzione
        dei timer di questa macchina.

            E SE IL BATTITO NON ARRIVA, SI CONTA — MA A SCADENZE.

        Il ripiego non e' «dormi venti millisecondi»: quello accumulerebbe il
        ritardo di ogni giro. E' una scadenza assoluta che avanza da sola, e
        quando si e' rimasti indietro non si recupera correndo — si riparte da
        adesso, perche parlare in fretta e' peggio che parlare tardi.
        """
        adesso = time.perf_counter()
        scadenza = (scadenza or adesso) + self.frame_ms / 1000.0

        if self.external_clock:
            if await self.credits.acquire(NO_BEAT_AFTER_S):
                #     IL CREDITO AUTORIZZA. IL MINIMO FRENA.
                # Se il rubinetto si sveglia in ritardo con tre crediti in
                # mano, li ha tutti e tre — nessun battito e andato perso — ma
                # non li spara nello stesso istante: fra due pacchetti resta un
                # minimo, perche una voce che recupera correndo e peggio di una
                # voce in ritardo.
                #     SI MISURA DALL'ULTIMO PACCHETTO USCITO, NON DA PRIMA.
                # Qui il freno guardava `quando`, cioe il momento in cui
                # era finita l'attesa precedente — un istante *prima*
                # dell'invio. Quando quell'invio era lento il margine se lo
                # mangiava lui, e il pacchetto dopo partiva subito: sulla
                # quinta telefonata settantasei intervalli sotto gli otto
                # millisecondi, ventisette di fila. Non si sentiva, ma un
                # freno che non frena e' un freno che un giorno serve e non
                # c'e'.
                self._in_fallback = False
                #     L'ANCORA E' L'ULTIMO INVIO VERO.
                # Non il risveglio, non il calcolo, non il credito: il momento
                # in cui un pacchetto e' davvero uscito sulla linea.
                non_prima_di = self._last_send + MIN_GAP_S
                self._last_brake_ms = round(
                    (non_prima_di - self._now()) * 1000, 2,
                )
                await self._hold_until(non_prima_di)
                uscito = self._now()
                # Il passo lo detta la linea: le scadenze si riancorano a lei.
                return uscito, uscito

            #     LA LINEA HA SMESSO DI BATTERE.
            # Un buco di rete, un trasporto fermo. La voce di ORA non deve
            # fermarsi con lui: si manda lo stesso, e resta segnato il debito —
            # il primo battito che torna lo pareggia invece di autorizzare un
            # pacchetto in piu.
            self.fallback_clock_count += 1
            self._in_fallback = True

        #     SENZA BATTITO, LE SCADENZE. MAI «VENTI DOPO L'ULTIMO».
        # Misurare il passo dal pacchetto precedente vuol dire aggiungere a
        # ogni giro il ritardo del giro prima. Le scadenze avanzano da sole; se
        # si e rimasti indietro non si rincorre — si riparte da adesso.
        resta = scadenza - time.perf_counter()
        if resta > 0:
            await asyncio.sleep(resta)
        else:
            scadenza = time.perf_counter()
        return time.perf_counter(), scadenza

    async def _hold_until(self, non_prima_di: float) -> None:
        """
        Non lascia passare niente prima di un istante preciso.

            LA SCADENZA E' UN ORARIO, NON UNA DURATA.

        Non si ricalcola mai da quando ci si sveglia: e' sempre la stessa, e
        ogni giro si chiede soltanto se e' ora. Cosi un timer che torna presto
        non fa danni — si richiede — e un timer che torna tardi nemmeno: si e'
        gia oltre, e si passa.

        La parte lontana si dorme, perche' li' sbagliare di qualche
        millisecondo non cambia niente. Gli ultimi si cedono: `sleep(0)` non
        promette un'attesa, promette solo di lasciar lavorare gli altri — ed e'
        l'unica promessa che questa macchina mantiene.
        """
        fidarsi = True
        trattenuto = False
        ceduti = 0
        giri = 0
        while True:
            giri += 1
            adesso = self._now()
            resta = non_prima_di - adesso
            if resta <= 0:
                if trattenuto:
                    self.barrier_waits += 1
                return
            if not trattenuto:
                trattenuto = True
                self._barrier_asked_ms.append(round(resta * 1000, 2))
            if fidarsi and resta > TOO_SHORT_TO_SLEEP_S:
                chiesto = resta - TOO_SHORT_TO_SLEEP_S
                self.coarse_sleeps += 1
                await self._sleep(chiesto)
                #     SE IL TIMER MENTE, SI SMETTE DI CHIEDERGLI.
                # Un'attesa che torna con meno di un decimo di quello che le
                # era stato chiesto non e' un'attesa breve: e' un timer che non
                # aspetta. Insistere vorrebbe dire avvicinarsi alla scadenza
                # senza raggiungerla mai — e' successo, e questo ciclo non
                # tornava piu'. Da li' in poi si cede soltanto.
                if (self._now() - adesso) < chiesto * 0.1:
                    self.timer_lies += 1
                    fidarsi = False
            elif ceduti < YIELDS_BEFORE_A_REAL_NAP or giri > TOO_MANY_TURNS:
                #     PRIMA SI LASCIA PASSARE CHI C'E'.
                # Due volte: se c'era qualcuno pronto e' gia' passato, e la
                # scadenza nel frattempo si e' avvicinata da sola.
                ceduti += 1
                self.cooperative_yields += 1
                await self._sleep(0)
            else:
                #     POI SI DORME PER DAVVERO, E SEMPRE DELLA STESSA MISURA.
                #
                # Non si cede piu': cedere quando non c'e' nessun altro pronto
                # torna subito, e ricominciare da capo e' il giro a vuoto che
                # ha affamato il filo audio.
                #
                #     E NON SI CHIEDE MAI «QUELLO CHE RESTA».
                #
                # Scritta la prima volta come `min(resta, SHORT_NAP_S)`, questa
                # riga ha ricreato in due minuti il difetto del V3.13: sotto i
                # due millisecondi chiedeva `resta`, il timer ne onorava un
                # decimo, e l'attesa si restringeva del novanta per cento a
                # ogni giro senza mai raggiungere lo zero. Un punto fisso, e
                # un ciclo che non torna.
                #
                # Una misura fissa non puo' convergere: o la scadenza arriva,
                # o si passa oltre di due millisecondi — e passare oltre non e'
                # un difetto. La barriera promette «non prima», non «non
                # dopo», e due millisecondi su un frame da venti non li sente
                # nessuno.
                self.short_naps += 1
                await self._sleep(SHORT_NAP_S)

    async def _let_the_cushion_fill(self, handle) -> None:
        """
        Aspetta di avere un po' di voce da parte, prima di cominciare.

        Non all'infinito: se chi genera ha finito, o se il margine non arriva,
        si parla lo stesso. Un cuscinetto è un'assicurazione, non un pedaggio.
        """
        if not self.jitter_ms:
            return
        self.cushions += 1
        basta = self.jitter_ms / self.frame_ms
        scade = time.perf_counter() + (self.jitter_ms / 1000.0) * 3
        while time.perf_counter() < scade:
            if handle.cancelled or handle.finished:
                return
            if self._queue.qsize() >= basta:
                return
            await asyncio.sleep(0.005)
        self.cushions_timed_out += 1

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
            # Quante volte si e aspettato di avere voce da parte, e quante
            # volte quel margine non e arrivato in tempo. La seconda e la
            # misura di quanto chi genera sia rimasto indietro.
            "cushions": self.cushions,
            "cushions_timed_out": self.cushions_timed_out,
            "underruns": self.underruns,
            "queue_empty_events": self.queue_empty_events,
            "underrun_waits_ms": self._waits_ms[:40],
            "underrun_depth_ms": self._underrun_depth_ms[:40],
            "underrun_at_ms": self._underrun_at_ms[:40],
            "queue_depth_min_ms": min(self._depth_ms) if self._depth_ms else None,
            "queue_depth_max_ms": max(self._depth_ms) if self._depth_ms else None,
            "send_interval_avg_ms": (
                round(sum(self._intervals_ms) / len(self._intervals_ms), 1)
                if self._intervals_ms else None
            ),
            "send_interval_p95_ms": (
                sorted(self._intervals_ms)[
                    min(len(self._intervals_ms) - 1,
                        int(0.95 * len(self._intervals_ms)))
                ] if self._intervals_ms else None
            ),
            "send_gaps_over_30ms": sum(1 for i in self._intervals_ms if i > 30),
            "send_gaps_over_50ms": sum(1 for i in self._intervals_ms if i > 50),
            "send_gaps_over_100ms": sum(1 for i in self._intervals_ms if i > 100),
            "worst_send_gaps_ms": sorted(self._intervals_ms, reverse=True)[:10],
            # --- dentro il turno: quello che si sente ------------------------
            "intra_turn_frames": len(self._within_ms),
            "intra_p50_ms": _quantile(self._within_ms, 50),
            "intra_p90_ms": _quantile(self._within_ms, 90),
            "intra_p95_ms": _quantile(self._within_ms, 95),
            "intra_max_ms": max(self._within_ms) if self._within_ms else None,
            "intra_gaps_over_30ms": sum(1 for i in self._within_ms if i > 30),
            "intra_gaps_over_50ms": sum(1 for i in self._within_ms if i > 50),
            "intra_gaps_over_100ms": sum(1 for i in self._within_ms if i > 100),
            "intra_worst_ms": sorted(self._within_ms, reverse=True)[:10],
            # --- e le raffiche: due pacchetti troppo vicini ------------------
            "intra_min_ms": min(self._within_ms) if self._within_ms else None,
            "intra_gaps_under_8ms": sum(1 for i in self._within_ms if i < 8),
            "intra_gaps_under_15ms": sum(1 for i in self._within_ms if i < 15),
            "longest_burst_run": _longest_run(self._within_ms, 8),
            "why_tight": self._why_tight,
            # --- la barriera ------------------------------------------------
            "barrier_wait_count": self.barrier_waits,
            "coarse_sleep_count": self.coarse_sleeps,
            "cooperative_yield_count": self.cooperative_yields,
            "timer_lie_detected_count": self.timer_lies,
            "short_nap_count": self.short_naps,
            "min_requested_barrier_ms": (
                min(self._barrier_asked_ms) if self._barrier_asked_ms else None
            ),
            "barrier_wait_p50_ms": _quantile(self._barrier_asked_ms, 50),
            "barrier_wait_p95_ms": _quantile(self._barrier_asked_ms, 95),
            "actual_min_gap_ms": min(self._within_ms) if self._within_ms else None,
            "intra_gaps_under_5ms": sum(1 for i in self._within_ms if i < 5),
            # --- l'orologio -------------------------------------------------
            #     CHI HA BATTUTO IL TEMPO, NON CHI LO BATTEVA ALLA FINE.
            # Prima qui si scriveva l'ultimo stato, e l'ultimo stato e sempre
            # il ripiego: dopo l'ultimo pacchetto di una risposta la linea
            # smette di servire battiti e il rubinetto scade. Una telefonata
            # con cento battiti e due scadenze non e stata «a orologio
            # interno»: e stata a orologio della linea.
            "clock_source": (
                "vonage" if self.credits.consumed > self.fallback_clock_count
                else "monotonic_fallback"
            ),
            "clock_source_counts": {
                "vonage": self.credits.consumed,
                "monotonic_fallback": self.fallback_clock_count,
            },
            "fallback_frames": self.fallback_clock_count,
            **self.credits.how_it_went(),
            "fallback_clock_count": self.fallback_clock_count,
            "missed_deadlines": self.missed_deadlines,
            "consecutive_missed_deadlines_max": self.consecutive_missed_max,
            "frame_schedule_lateness_p50_ms": _quantile(self._lateness_ms, 50),
            "frame_schedule_lateness_p90_ms": _quantile(self._lateness_ms, 90),
            "frame_schedule_lateness_p95_ms": _quantile(self._lateness_ms, 95),
            "frame_schedule_lateness_max_ms": (
                max(self._lateness_ms) if self._lateness_ms else None
            ),
            "outbound_inter_frame_p50_ms": _quantile(self._intervals_ms, 50),
            "outbound_inter_frame_p90_ms": _quantile(self._intervals_ms, 90),
            "outbound_inter_frame_p95_ms": _quantile(self._intervals_ms, 95),
            "outbound_inter_frame_max_ms": (
                max(self._intervals_ms) if self._intervals_ms else None
            ),
        }
