"""
Di chi è il turno, e quando una frase è davvero finita.

    AL TELEFONO NON CI SI VEDE: IL TURNO È TUTTO QUELLO CHE C'È.

E la lezione che questo file esiste per non dimenticare, misurata su una
telefonata vera:

    `speech_final` NON È LA FINE DEL TURNO.

Su «Ciao ORA, dimmi che giorno è oggi» l'operatore ha alzato la mano dopo
2,4 secondi su 4 di parlato — cioè sulla pausa dopo «Ciao, ORA», mentre la
persona stava ancora parlando. Un runtime che risponde a `speech_final`
interrompe la gente a metà frase, e lo fa sembrando sordo.

Quindi il commit è una decisione che combina quello che si sa:

    ha cominciato a parlare        (VAD)
    quello che ha detto finora     (final transcript, accumulato)
    dove ha fatto pause            (speech_final, indizio)
    quanto silenzio è passato      (UtteranceEnd, e il nostro conto)
    quanto ha parlato in tutto
    se la frase sta in piedi da sola
    dove eravamo un attimo fa

    PRIMA DEL COMMIT È UN'IPOTESI. DOPO, È QUELLO CHE HA DETTO.

Niente entra nel Conversation Engine prima del commit: né un provvisorio, né
un pezzo definitivo, né una pausa. Un'ipotesi che diventa un messaggio è un
modo di mettere in bocca a qualcuno mezza frase.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

# Dove siamo adesso.
Where = Literal[
    "connecting",    # la linea si sta aprendo
    "listening",     # aperta, nessuno parla
    "user_speaking", # sta parlando la persona
    "turn_candidate",# sembra che abbia finito, ma non è ancora deciso
    "thinking",      # deciso: ORA sta capendo cosa rispondere
    "ora_speaking",  # ORA sta parlando
    "interrupting",  # la persona ha ripreso la parola mentre ORA parlava
    "ending",        # la telefonata sta finendo
]

# Sotto questo non c'è una frase: è un «mh», un colpo di tosse, una porta che
# sbatte. Si guarda quello che è stato trascritto, non quanto tempo è passato:
# la trascrizione di un turno può arrivare tutta in una volta.
MIN_SPOKEN_CHARS = 2

# La rete sotto: se il segnale di fine turno non arrivasse mai, dopo questo
# si guarda comunque se la frase sta in piedi. Lungo apposta — è un guasto,
# non un ritmo di conversazione.
SILENCE_NET_MS = 4000

# Oltre questo si chiude comunque, anche senza silenzio: qualcuno ha
# appoggiato il telefono, o la linea sta sibilando.
MAX_SPEECH_MS = 30000

# Parole con cui una frase italiana non finisce mai. Non è grammatica: è il
# modo più economico di riconoscere che manca ancora qualcosa.
_HANGING = re.compile(
    r"\b(e|o|ma|che|di|da|a|in|con|su|per|tra|fra|il|lo|la|i|gli|le|un|uno|"
    r"una|del|della|dei|delle|al|alla|ai|alle|dal|dalla|nel|nella|se|quando|"
    r"mentre|perché|però|anche|come|quanto|quale|cioè|ecco)\s*$",
    re.IGNORECASE,
)


@dataclass
class Timing:
    """
    I tempi di un turno, in millisecondi dall'inizio del turno stesso.

        SENZA NUMERI, «SEMBRA LENTO» È UN'OPINIONE.

    Nessuno di questi campi contiene una parola di quello che è stato detto.
    """

    user_speech_start_ms: Optional[int] = None
    user_last_voice_ms: Optional[int] = None
    turn_candidate_ms: Optional[int] = None
    turn_committed_ms: Optional[int] = None
    stt_final_ms: Optional[int] = None
    ora_request_start_ms: Optional[int] = None
    ora_first_token_ms: Optional[int] = None
    ora_complete_ms: Optional[int] = None
    tts_request_start_ms: Optional[int] = None
    tts_first_audio_ms: Optional[int] = None
    playback_first_chunk_ms: Optional[int] = None
    playback_complete_ms: Optional[int] = None
    # Quando qualcuno ha interrotto, e quanto ci è voluto a stare zitti.
    barge_in_detected_ms: Optional[int] = None
    tts_cancelled_ms: Optional[int] = None
    playback_cleared_ms: Optional[int] = None
    new_user_turn_started_ms: Optional[int] = None

    def _gap(self, a, b) -> Optional[int]:
        return None if a is None or b is None else b - a

    @property
    def silence_the_person_hears_ms(self) -> Optional[int]:
        """
        Da quando smette di parlare a quando sente ORA. Il numero vero.

        Si misura dall'ultima voce, non dal commit: la persona non sa che
        esiste un commit, sa solo che ha finito di parlare e aspetta.
        """
        return self._gap(self.user_last_voice_ms, self.playback_first_chunk_ms)

    @property
    def time_to_stop_talking_ms(self) -> Optional[int]:
        """Da quando interrompe a quando la coda è vuota."""
        return self._gap(self.barge_in_detected_ms, self.playback_cleared_ms)

    def derived(self) -> Dict[str, Optional[int]]:
        """I quattro salti che dicono dove si perde tempo."""
        return {
            "end_of_speech_to_commit_ms": self._gap(
                self.user_last_voice_ms, self.turn_committed_ms,
            ),
            "commit_to_ora_first_token_ms": self._gap(
                self.turn_committed_ms, self.ora_first_token_ms,
            ),
            "ora_first_token_to_tts_audio_ms": self._gap(
                self.ora_first_token_ms, self.tts_first_audio_ms,
            ),
            "end_of_speech_to_first_audio_ms": self.silence_the_person_hears_ms,
        }

    def as_dict(self) -> Dict[str, Optional[int]]:
        out = {
            k: v for k, v in self.__dict__.items() if v is not None
        }
        out.update({k: v for k, v in self.derived().items() if v is not None})
        return out


class TurnManager:
    """
    Chi ha la parola, e quando una frase è finita davvero.

    Non contiene audio, non chiama nessun fornitore e non decide cosa dire.
    Riceve fatti e produce una sola cosa che conta: il momento in cui
    un'ipotesi diventa un turno.
    """

    def __init__(self) -> None:
        self.where: Where = "connecting"
        self.timings: List[Timing] = []
        self.interruptions = 0
        self.first_audio_in_ms: Optional[int] = None
        self.connect_ms: Dict[str, Optional[int]] = {}

        self._opened = time.perf_counter()
        self._turn_began: Optional[float] = None
        self._now: Optional[Timing] = None
        # Quello che si è sentito finora in questo turno. Un'ipotesi.
        self._final_pieces: List[str] = []
        self._partial = ""
        self._saw_pause = False
        self._saw_utterance_end = False
        self._last_voice: Optional[float] = None

    # --- il tempo ---------------------------------------------------------

    def _ms(self) -> int:
        base = self._turn_began or self._opened
        return int((time.perf_counter() - base) * 1000)

    def line_is_open(self) -> None:
        self.where = "listening"

    def heard_the_first_audio(self) -> None:
        if self.first_audio_in_ms is None:
            self.first_audio_in_ms = int((time.perf_counter() - self._opened) * 1000)

    # --- quello che dice chi ascolta --------------------------------------

    def speech_started(self) -> bool:
        """
        Qualcuno ha cominciato. Torna `True` se è un barge-in.

        È l'unico segnale che conta mentre ORA parla, e arriva prima delle
        parole: aspettare la prima trascrizione per accorgersi che qualcuno ha
        interrotto vuol dire continuare a parlargli sopra per un secondo.
        """
        if self.where == "ora_speaking":
            self.interruptions += 1
            if self._now is not None:
                self._now.barge_in_detected_ms = self._ms()
            self.where = "interrupting"
            return True
        if self.where in ("listening", "turn_candidate"):
            if self.where == "listening":
                self._begin_turn()
            self.where = "user_speaking"
            self._saw_pause = False
            self._saw_utterance_end = False
        return False

    def began_speaking_after_interruption(self) -> None:
        """Dopo un'interruzione, il turno nuovo comincia qui."""
        was = self._now
        self._close_the_turn()
        self._begin_turn()
        if was is not None and self._now is not None:
            self._now.new_user_turn_started_ms = 0
        self.where = "user_speaking"

    def partial(self, text: str) -> None:
        """Un pezzo che può ancora cambiare. Non esce di qui."""
        self._partial = text
        self._last_voice = time.perf_counter()
        if self._now is not None:
            self._now.user_last_voice_ms = self._ms()

    def final_piece(self, text: str) -> None:
        """Un pezzo che non cambia più. Si accumula; da solo non è un turno."""
        if text:
            self._final_pieces.append(text)
        self._partial = ""
        self._last_voice = time.perf_counter()
        if self._now is not None:
            self._now.stt_final_ms = self._ms()
            self._now.user_last_voice_ms = self._ms()

    def pause(self) -> None:
        """
        C'era una pausa naturale. **Indizio, non fine.**

        Misurato: scatta anche dopo «Ciao, ORA» mentre la frase continua.
        """
        self._saw_pause = True
        if self.where == "user_speaking":
            self.where = "turn_candidate"
            if self._now is not None:
                self._now.turn_candidate_ms = self._ms()

    def utterance_end(self) -> None:
        """L'operatore dice che il silenzio è stato lungo. Peso maggiore."""
        self._saw_utterance_end = True
        if self.where == "user_speaking":
            self.where = "turn_candidate"
            if self._now is not None:
                self._now.turn_candidate_ms = self._ms()

    # --- la decisione -----------------------------------------------------

    def what_was_said(self) -> str:
        """L'ipotesi corrente, per intero."""
        return " ".join(p for p in self._final_pieces if p).strip()

    def should_commit(self) -> bool:
        """
        Se questa ipotesi è diventata un turno.

            UN COMMIT SBAGLIATO SI SENTE SUBITO.

        Troppo presto e ORA interrompe; troppo tardi e sembra che non ci sia.
        Si combina tutto quello che si sa invece di guardare un segnale solo,
        e ogni condizione qui è il motivo per cui un segnale da solo non
        bastava.
        """
        if self.where not in ("user_speaking", "turn_candidate"):
            return False

        said = self.what_was_said()
        if not said:
            return False

        #     QUANTO HA PARLATO SI LEGGE IN QUELLO CHE HA DETTO.
        #
        # Il primo tentativo misurava il tempo dall'inizio del turno, ed era
        # sbagliato: quando la trascrizione arriva tutta insieme quel numero
        # è zero, e nessun turno partiva più. Quanto sia lungo un parlato lo
        # dicono le parole, che è anche l'unica cosa che conta per decidere se
        # c'è qualcosa da rispondere.
        if len(said) < MIN_SPOKEN_CHARS:
            return False

        spoken_ms = self._now.user_last_voice_ms if self._now else None
        if spoken_ms is not None and spoken_ms > MAX_SPEECH_MS:
            # Troppo lungo: qualcuno ha appoggiato il telefono.
            return True

        quiet_ms = (
            int((time.perf_counter() - self._last_voice) * 1000)
            if self._last_voice else 0
        )

        #     UN TIMER CHE BATTE QUELLO DI CHI ASCOLTA È UN TIMER INUTILE.
        #
        # Qui c'era una seconda strada: «pausa dichiarata + 800 ms di silenzio
        # + frase che sta in piedi». Sembrava prudente e non lo era, per una
        # ragione che si vede solo misurando. Chi trascrive dichiara il
        # silenzio a mille millisecondi; aspettarne ottocento e decidere da
        # soli vuol dire arrivare sempre primi, e quindi non chiedergli mai
        # niente. Alla prova con voce vera ha chiuso il turno su «Ciao, ORA.»
        # — che *sembra* una frase finita, perché il trascrittore mette il
        # punto a ogni pezzo — mentre la persona stava dicendo «dimmi che
        # giorno è oggi».
        #
        # Quindi resta un segnale solo, ed è quello di chi guarda i tempi
        # delle parole invece dell'orologio. La pausa resta quello che è: un
        # indizio che mette il turno in dubbio e niente più.
        if self._saw_utterance_end:
            return True

        #     UN SILENZIO FRA GLI EVENTI NON È UN SILENZIO IN LINEA.
        #
        # Qui c'era una scorciatoia — «se sono passati 1,6 secondi senza
        # eventi, commetti» — e alla prima prova con voce vera ha fatto
        # esattamente il danno che tutto questo file esiste per evitare: ha
        # chiuso il turno su «Ciao, ora» mentre la persona stava dicendo
        # «dimmi che giorno è oggi». Il trascrittore consegna i pezzi
        # definitivi a gruppi, e fra un gruppo e l'altro passano secondi in
        # cui *noi* non sentiamo niente e la persona sta parlando benissimo.
        #
        # Chi sa davvero se è calato il silenzio è il trascrittore, che guarda
        # i tempi delle parole: è `UtteranceEnd`, ed è già gestito sopra.
        # Quello che resta qui è solo una rete per il caso in cui quel segnale
        # non arrivi mai — molto più lunga, e comunque non su una frase che
        # visibilmente continua.
        if quiet_ms >= SILENCE_NET_MS:
            return self._stands_on_its_own(said)

        return False

    @staticmethod
    def _stands_on_its_own(said: str) -> bool:
        """
        Se questa frase può reggere da sola.

        Non è analisi grammaticale: è riconoscere che «dimmi che giorno è» e
        «dimmi che giorno è oggi e» non sono la stessa cosa. Una frase che
        finisce con una congiunzione o un articolo continua, e rispondere lì
        significa interrompere.
        """
        text = said.strip()
        if not text:
            return False
        if text[-1] in ".?!":
            return True
        if _HANGING.search(text):
            return False
        # Tre parole sono il minimo perché una frase senza punteggiatura
        # possa dire qualcosa.
        return len(text.split()) >= 3

    def commit(self) -> str:
        """
        L'ipotesi diventa quello che ha detto. Da qui entra nel core.

        Torna il testo e svuota: quello che c'era prima non appartiene più al
        turno prossimo.
        """
        said = self.what_was_said()
        self.where = "thinking"
        if self._now is not None:
            self._now.turn_committed_ms = self._ms()
        self._final_pieces = []
        self._partial = ""
        self._saw_pause = False
        self._saw_utterance_end = False
        return said

    # --- il giro di ORA ---------------------------------------------------

    def ora_asked(self) -> None:
        if self._now is not None:
            self._now.ora_request_start_ms = self._ms()

    def ora_decided(self) -> None:
        """
        Il core ha finito di decidere.

        Il core non streamma — misurato, guadagnerebbe 150 ms su 3.000 — e
        quindi il primo token e la decisione completa coincidono. I due campi
        restano distinti perché il giorno che cambierà si vedrà la differenza
        senza toccare niente.
        """
        if self._now is not None:
            now = self._ms()
            self._now.ora_first_token_ms = now
            self._now.ora_complete_ms = now

    def tts_asked(self) -> None:
        if self._now is not None:
            self._now.tts_request_start_ms = self._ms()

    def tts_answered(self) -> None:
        if self._now is not None and self._now.tts_first_audio_ms is None:
            self._now.tts_first_audio_ms = self._ms()

    def ora_started_speaking(self) -> bool:
        if self.where not in ("thinking", "listening"):
            return False
        self.where = "ora_speaking"
        if self._now is not None and self._now.playback_first_chunk_ms is None:
            self._now.playback_first_chunk_ms = self._ms()
        return True

    def ora_finished_speaking(self) -> None:
        if self._now is not None:
            self._now.playback_complete_ms = self._ms()
        self._close_the_turn()
        self.where = "listening"

    # --- l'interruzione ---------------------------------------------------

    def tts_cancelled(self) -> None:
        if self._now is not None:
            self._now.tts_cancelled_ms = self._ms()

    def playback_cleared(self) -> None:
        if self._now is not None:
            self._now.playback_cleared_ms = self._ms()

    # --- le uscite --------------------------------------------------------

    def give_up_this_turn(self) -> None:
        """Qualcosa non ha funzionato. Si torna ad ascoltare, senza fingere."""
        self._close_the_turn()
        self.where = "listening"

    def hung_up(self) -> None:
        self._close_the_turn()
        self.where = "ending"

    # --- dentro -----------------------------------------------------------

    def _begin_turn(self) -> None:
        self._turn_began = time.perf_counter()
        self._now = Timing(user_speech_start_ms=0)
        self._last_voice = time.perf_counter()
        self._final_pieces = []
        self._partial = ""

    def _close_the_turn(self) -> None:
        if self._now is not None and self._now.as_dict():
            self.timings.append(self._now)
        self._now = None
        self._turn_began = None
        self._last_voice = None

    # --- quello che si racconta -------------------------------------------

    def how_it_went(self) -> Dict[str, object]:
        """I numeri della telefonata. Nessuna parola di quello che si è detto."""
        waits = [
            t.silence_the_person_hears_ms
            for t in self.timings
            if t.silence_the_person_hears_ms is not None
        ]
        stops = [
            t.time_to_stop_talking_ms
            for t in self.timings
            if t.time_to_stop_talking_ms is not None
        ]
        out: Dict[str, object] = {
            "first_audio_in_ms": self.first_audio_in_ms,
            "connect_ms": dict(self.connect_ms),
            "turns": len(self.timings),
            "interruptions": self.interruptions,
            "each_turn": [t.as_dict() for t in self.timings][:12],
        }
        if waits:
            ordered = sorted(waits)
            out["silence_median_ms"] = ordered[len(ordered) // 2]
            out["silence_worst_ms"] = ordered[-1]
        if stops:
            out["stop_talking_worst_ms"] = max(stops)
        return out
