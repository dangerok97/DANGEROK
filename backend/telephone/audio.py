"""
Il suono, mentre attraversa.

    L'AUDIO È UN FIUME, NON UN ARCHIVIO.

Qui dentro passano centinaia di pacchetti al minuto e non ne resta nessuno.
Non c'è una funzione che scriva un file, non c'è una che accumuli senza
limite, e non c'è una riga di log che porti con sé un campione.

Tre mestieri, tutti piccoli:

- **cambiare passo.** La linea telefonica porta sedici kilohertz; chi parla ne
  restituisce ventiquattro. Convertirli reinterpretando i byte è la cosa che
  fa sembrare una voce registrata sott'acqua o dentro un cartone animato:
  bisogna ricalcolare i campioni, e scendendo bisogna anche filtrare, o quello
  che sta sopra la nuova Nyquist torna dentro come fischio.

- **sentire se qualcuno sta parlando.** Non serve capire cosa: serve sapere
  quando comincia e quando ha finito, perché è quello che decide quando ORA
  può rispondere. Si misura l'energia, e la soglia si adatta al rumore di
  fondo di *questa* linea — una chiamata da un'auto e una da una stanza
  silenziosa non hanno lo stesso zero.

- **tagliare a pacchetti.** Venti millisecondi alla volta, perché è così che
  la rete telefonica vuole il suono, e mandarne di più tutto insieme significa
  che la voce arriva a scatti.
"""

from __future__ import annotations

import logging
import math
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger("ora.telephone.audio")

# Il passo della linea: quello che Vonage manda e quello che si aspetta.
LINE_RATE = 16000
# Quanto dura un pacchetto. Venti millisecondi è la misura della telefonia.
FRAME_MS = 20
BYTES_PER_SAMPLE = 2


def frame_bytes(rate: int = LINE_RATE, ms: int = FRAME_MS) -> int:
    """Quanti byte sono `ms` millisecondi a questo passo."""
    return int(rate * ms / 1000) * BYTES_PER_SAMPLE


def seconds_of(pcm: bytes, rate: int = LINE_RATE) -> float:
    """Quanto dura questo suono. Serve a dirlo, non a tenerlo."""
    return len(pcm) / BYTES_PER_SAMPLE / rate if rate else 0.0


def resample(pcm: bytes, *, src: int, dst: int) -> bytes:
    """
    Lo stesso suono, a un altro passo.

        RICAMPIONARE NON È REINTERPRETARE I BYTE.

    Scendendo si filtra prima di buttare via campioni: senza, tutto quello che
    sta sopra la metà del nuovo passo si ripiega dentro la banda e si sente
    come un fischio metallico che nessun trascrittore capisce. Salendo il
    filtro non serve, perché non si aggiunge energia in alto — si interpola, e
    basta.

    Il filtro è un seno cardinale finestrato: sessantaquattro coefficienti,
    che a questi passi costano niente e bastano.
    """
    if not pcm or src == dst:
        return pcm
    if src <= 0 or dst <= 0:
        return b""

    try:
        x = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
        if x.size == 0:
            return b""

        if dst < src:
            taps = 64
            cutoff = 0.45 * dst / src
            n = np.arange(taps) - (taps - 1) / 2.0
            window = np.hanning(taps)
            h = np.sinc(2 * cutoff * n) * window
            h = h / h.sum()
            x = np.convolve(x, h, mode="same")

        wanted = int(round(x.size * dst / src))
        if wanted <= 0:
            return b""
        at = np.linspace(0, x.size - 1, wanted)
        y = np.interp(at, np.arange(x.size), x)
        return np.clip(y, -32768, 32767).astype("<i2").tobytes()
    except Exception as e:
        # Un ricampionamento che fallisce non deve portarsi via la telefonata:
        # meglio un turno perso che una linea chiusa.
        logger.info("ricampionamento fallito: %s", type(e).__name__)
        return b""


class Resampler:
    """
    Lo stesso suono a un altro passo, ma senza mai fermare il suono.

        UN FIUME NON SI RICAMPIONA UN SECCHIO ALLA VOLTA.

    `resample()` qui sopra prende un suono intero e lo riscrive: va benissimo
    per una frase gia pronta. Ma un fiume arriva venti millisecondi per volta,
    e filtrare ogni pacchetto come se fosse solo al mondo lascia una
    discontinuita a ogni giunta — cinquanta volte al secondo. Non e un
    dettaglio teorico: si sente come un ronzio sotto la voce.

    La differenza sta tutta in due cose che qui si portano avanti fra una
    chiamata e l'altra: la coda del filtro, e il punto frazionario in cui si
    era arrivati a leggere. Con quelle due, l'uscita e identica byte per byte
    a quella che darebbe un ricampionamento dell'intero flusso.

        CIO' CHE NON HA ANCORA CONTESTO A DESTRA, ASPETTA.

    Un filtro centrato ha bisogno di sapere anche cosa viene dopo. Quello che
    non si puo ancora filtrare resta nel buffer fino al pacchetto successivo:
    sono meta dei coefficienti, trentadue campioni, un millisecondo e mezzo a
    ventiquattromila. E' il prezzo minimo, ed e deterministico.

    Non tiene niente: quello che esce viene dimenticato, e quello che resta e
    solo il minimo per non tagliare male la giunta successiva.
    """

    def __init__(self, *, src: int, dst: int, taps: int = 64) -> None:
        self.src = int(src)
        self.dst = int(dst)
        self._step = (self.src / self.dst) if self.dst else 1.0
        self._taps = int(taps) if self.dst < self.src else 0
        self._h: Optional[np.ndarray] = None
        if self._taps:
            cutoff = 0.45 * self.dst / self.src
            n = np.arange(self._taps) - (self._taps - 1) / 2.0
            h = np.sinc(2 * cutoff * n) * np.hanning(self._taps)
            self._h = (h / h.sum()).astype(np.float32)
        # Cio' che e entrato e non e ancora uscito: coda del filtro piu' i
        # campioni che non hanno ancora contesto a destra.
        self._buf = np.zeros(0, dtype=np.float32)
        # Dove leggere il prossimo campione d'uscita, in indici di `_buf`.
        self._at = 0.0

    @property
    def passthrough(self) -> bool:
        """Se non c'e niente da fare, non si fa niente."""
        return self.src == self.dst

    def feed(self, pcm: bytes) -> bytes:
        """Il pezzo di fiume che e arrivato, al passo nuovo."""
        if self.passthrough or not pcm:
            return pcm if self.passthrough else b""
        try:
            arrivati = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
            if arrivati.size:
                self._buf = np.concatenate([self._buf, arrivati])
            return self._take(hold_back=self._taps // 2)
        except Exception as e:
            logger.info("ricampionamento in corsa fallito: %s", type(e).__name__)
            return b""

    def drain(self) -> bytes:
        """
        La coda, quando il fiume finisce.

        Si completa con silenzio quel tanto che serve a dare contesto a destra
        all'ultimo pezzo di voce, e si svuota.
        """
        if self.passthrough or self._buf.size == 0:
            return b""
        coda = np.zeros(self._taps or 2, dtype=np.float32)
        self._buf = np.concatenate([self._buf, coda])
        out = self._take(hold_back=0)
        self._buf = np.zeros(0, dtype=np.float32)
        self._at = 0.0
        return out

    def _take(self, *, hold_back: int) -> bytes:
        """Quanto si puo' leggere adesso senza inventare il futuro."""
        if self._buf.size == 0:
            return b""

        filtrato = (
            np.convolve(self._buf, self._h, mode="same")
            if self._h is not None else self._buf
        )
        # Oltre questo indice non c'e abbastanza contesto: si aspetta. Il due
        # non e un margine di sicurezza: l'interpolazione legge anche il
        # campione dopo quello su cui cade.
        limite = filtrato.size - hold_back - 2
        if limite < 1:
            return b""

        quanti = int(np.floor((limite - self._at) / self._step)) + 1
        if quanti <= 0:
            return b""
        dove = self._at + self._step * np.arange(quanti)
        dove = dove[dove <= limite]
        if dove.size == 0:
            return b""

        giu = np.floor(dove).astype(np.int64)
        frazione = (dove - giu).astype(np.float32)
        y = filtrato[giu] * (1.0 - frazione) + filtrato[giu + 1] * frazione

        # Si butta via solo cio' che non serve piu' ne al filtro ne alla
        # prossima lettura, e si sposta il punto di lettura di conseguenza.
        prossimo = self._at + self._step * dove.size
        tenere = max(self._taps, 2)
        butta = int(min(np.floor(prossimo), max(0, self._buf.size - tenere)))
        if butta > 0:
            self._buf = self._buf[butta:]
            prossimo -= butta
        self._at = float(prossimo)
        return np.clip(y, -32768, 32767).astype("<i2").tobytes()


def in_frames(pcm: bytes, size: int) -> List[bytes]:
    """
    Il suono tagliato a pacchetti della misura giusta.

    L'ultimo si completa con silenzio invece di essere mandato corto: un
    pacchetto di misura sbagliata fa scattare la voce.
    """
    if size <= 0 or not pcm:
        return []
    out = [pcm[i:i + size] for i in range(0, len(pcm), size)]
    if out and len(out[-1]) < size:
        out[-1] = out[-1] + b"\x00" * (size - len(out[-1]))
    return out


def loudness(pcm: bytes) -> float:
    """
    Quanto è forte questo pezzo di suono, da zero a uno.

    Non è un volume in decibel e non deve esserlo: serve solo a confrontare
    questo istante con il silenzio di questa stessa linea.
    """
    if not pcm:
        return 0.0
    try:
        x = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        if x.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(x))))
    except Exception:
        return 0.0


class Ears:
    """
    Sentire quando qualcuno comincia a parlare, e quando ha finito.

        IL SILENZIO DI UNA LINEA NON È MAI ZERO.

    Una soglia fissa funziona in laboratorio e fallisce al telefono: una
    chiamata da un'auto in tangenziale ha un fondo dieci volte più alto di una
    da una stanza chiusa, e con una soglia fissa o si perde la voce o si prende
    il rumore per voce. Quindi il fondo si impara ascoltandolo: nei primi
    istanti di ogni chiamata si guarda quanto è alto il silenzio *qui*, e la
    soglia gli sta sopra di un margine.

    Il resto è conteggio. Qualche pacchetto sopra la soglia e qualcuno sta
    parlando; abbastanza pacchetti sotto e ha finito. Non c'è niente di
    intelligente, e non deve esserci: quello che è stato detto lo capisce
    chi trascrive.
    """

    # Quanto silenzio prima di considerare finito un turno. Mezzo secondo
    # taglia le pause di chi pensa; un secondo e mezzo fa sembrare ORA lenta.
    SILENCE_MS = 900
    # Quanto parlato prima di dire che è parlato. Due pacchetti bastano a
    # scartare un colpo di tosse della linea.
    SPEECH_FRAMES = 3
    # Quanto sta sopra il fondo una voce. Tre volte è prudente e funziona.
    OVER_FLOOR = 3.0
    # Sotto questo non c'è voce nemmeno in una stanza insonorizzata.
    ABSOLUTE_FLOOR = 0.004
    # Quanti pacchetti servono per farsi un'idea del silenzio di questa linea.
    LEARNING_FRAMES = 25

    def __init__(self, *, frame_ms: int = FRAME_MS) -> None:
        self.frame_ms = frame_ms
        self._floor_samples: List[float] = []
        self._floor: Optional[float] = None
        self._loud_run = 0
        self._quiet_ms = 0
        self.speaking = False

    @property
    def ready(self) -> bool:
        """
        Se hanno gia imparato quanto e alto il silenzio di questa linea.

            PRIMA DI AVER IMPARATO IL SILENZIO NON SANNO RICONOSCERE UNA VOCE.

        Serve a chi deve decidere se fidarsi di `speaking`: nei primi
        venticinque pacchetti la risposta e sempre «nessuno parla», e non
        perche non parli nessuno.
        """
        return self._floor is not None

    @property
    def floor(self) -> float:
        """Quanto è alto il silenzio su questa linea."""
        return self._floor if self._floor is not None else self.ABSOLUTE_FLOOR

    def _threshold(self) -> float:
        return max(self.ABSOLUTE_FLOOR, self.floor * self.OVER_FLOOR)

    def hear(self, pcm: bytes) -> Tuple[bool, bool]:
        """
        Un pacchetto. Torna (ha_cominciato, ha_finito).

        Le due cose non sono mai vere insieme, e quasi sempre sono false
        entrambe: la maggior parte dei pacchetti non cambia niente.
        """
        level = loudness(pcm)

        # I primi pacchetti servono a imparare quanto è alto il silenzio.
        if self._floor is None:
            self._floor_samples.append(level)
            if len(self._floor_samples) >= self.LEARNING_FRAMES:
                quiet = sorted(self._floor_samples)[: max(1, len(self._floor_samples) // 2)]
                self._floor = sum(quiet) / len(quiet)
            return False, False

        loud = level > self._threshold()

        if not self.speaking:
            self._loud_run = self._loud_run + 1 if loud else 0
            if self._loud_run >= self.SPEECH_FRAMES:
                self.speaking = True
                self._quiet_ms = 0
                return True, False
            # Nel silenzio il fondo continua a essere imparato, piano: una
            # linea cambia durante una telefonata.
            if not loud:
                self._floor = self._floor * 0.98 + level * 0.02
            return False, False

        if loud:
            self._quiet_ms = 0
            return False, False

        self._quiet_ms += self.frame_ms
        if self._quiet_ms >= self.SILENCE_MS:
            self.speaking = False
            self._loud_run = 0
            self._quiet_ms = 0
            return False, True
        return False, False

    def forget_the_turn(self) -> None:
        """Ricomincia ad ascoltare da capo, tenendo quello che sa della linea."""
        self.speaking = False
        self._loud_run = 0
        self._quiet_ms = 0
