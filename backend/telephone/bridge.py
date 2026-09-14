"""
Il giro completo di una telefonata: la voce entra, quella di ORA esce.

    VOICE IS NOT A SEPARATE ASSISTANT.
    IL TELEFONO È UN TRASPORTO, NON UN ALTRO ORA.

Questo file tiene insieme sei pezzi che sanno ognuno una cosa sola — ascoltare
(`deepgram.Listening`), decidere di chi è il turno (`turn.TurnManager`),
ragionare (`same_ora`, che è `AICoreOrchestrator` e nient'altro), tagliare la
risposta dove si respira (`chunker`), dirla (`deepgram.Speaking`) e versarla
sulla linea (`playback`) — e non ne aggiunge nessuno.

    NON C'È UN PROMPT DEL TELEFONO.

Non c'è una memoria del telefono, non c'è un modo telefonico di decidere cosa
si può fare, e non c'è un modello più veloce per le telefonate. La frase detta
a voce entra dalla stessa porta di una frase scritta nell'app. `origin="phone"`
viaggia come provenienza — serve a ORA per sapere che sta parlando e non
scrivendo — e non comanda niente.

    NESSUN AUDIO PRIMA CHE ORA ABBIA DECISO DI RISPONDERE.

È il cancello che tiene in piedi tutto il resto. Il core non produce testo:
produce una **decisione**, e `ora_text` è un campo dentro quella decisione.
Finché la decisione non è completa non si sa nemmeno se questo turno è una
risposta — potrebbe essere una chiamata a uno strumento, una richiesta di
autorità, un blocco. Quindi si aspetta la decisione intera, si guarda cosa
dice, e solo se c'è qualcosa da dire a una persona si apre la bocca.

    L'AUDIO È UN FIUME, NON UN ARCHIVIO.

Niente di quello che passa di qui resta di qui. Il PCM va a chi ascolta e
viene dimenticato nello stesso gesto: non c'è un buffer che cresce, non c'è un
file, non c'è un campo nel database. Restano il testo, i tempi e i conteggi.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import unicodedata
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional

from telephone.playback import PlaybackController
from telephone.providers import Heard, Spoke
from telephone.turn import TurnManager

logger = logging.getLogger("ora.telephone.bridge")

# Quanto si aspetta un giro di pensiero prima di lasciar perdere. Oltre, la
# persona ha già ripetuto la domanda o ha riagganciato.
THINKING_TIMEOUT_S = 45

# Ogni quanto si controlla se l'ipotesi è diventata un turno. Venti volte al
# secondo: abbastanza fitto da non aggiungere ritardo percepibile.
COMMIT_TICK_S = 0.05

# Sotto questo non c'è nessuno che interrompe: è un rumore, un soffio, una
# sillaba di ritorno dalla linea.
MIN_INTERRUPTING_CHARS = 3

#     L'ECO NON FINISCE QUANDO ORA SMETTE.
# La linea restituisce con ritardo: la coda dell'ultima frase rientra quando
# ORA ha già chiuso la bocca. Misurato a secco, con la voce rimandata dentro:
# senza questa finestra ORA si sentiva parlare e se lo annotava come una
# domanda — nel registro è comparso «them: Come posso aiutare?», che era una
# sua frase di un istante prima.
ECHO_TAIL_S = 3.0

#     L'ECO NON TORNA MAI UGUALE.
# «Oggi è domenica 13 settembre 2026» è rientrata trascritta «…settembre
# 2020», e un confronto letterale non l'ha riconosciuta: è finita nel registro
# come una domanda della persona. Quindi non si cerca la frase identica, si
# guarda quanta parte di quello che è arrivato era già nostra.
ENOUGH_TO_BE_OURS = 0.7

#     CHI INTERROMPE ASPETTA ALMENO DI SENTIRE CHE STAI PARLANDO.
# Sulla telefonata vera le interruzioni sono arrivate a 382, 330 e **27**
# millisecondi dall'inizio della voce di ORA. Ventisette millisecondi non è
# una persona che reagisce: è la linea. Sotto questa soglia non si interrompe
# nessuno, e chi voleva interrompere davvero lo rifà mezzo secondo dopo —
# costa una frase ripetuta, non una telefonata intera.
NOBODY_INTERRUPTS_THAT_FAST_MS = 1200

_NOT_A_LETTER = re.compile(r"[^\w\s]", re.UNICODE)


def _plain(text: str) -> str:
    """La stessa frase senza accenti, senza punteggiatura, senza maiuscole.

    Serve per confrontare quello che entra con quello che sta uscendo: l'eco
    torna quasi uguale, ma non identica — «oggi è domenica» può rientrare come
    «oggi e domenica», e un confronto letterale non la riconoscerebbe.
    """
    flat = unicodedata.normalize("NFKD", (text or "").lower())
    flat = "".join(c for c in flat if not unicodedata.combining(c))
    return " " + " ".join(_NOT_A_LETTER.sub(" ", flat).split()) + " "


class RealtimeVoiceSession:
    """
    Una telefonata, mentre succede.

    Riceve pacchetti audio e ne produce altri. Non sa di quale operatore
    siano, non apre linee telefoniche e non chiude chiamate: quello è il
    trasporto, e sta da un'altra parte.
    """

    def __init__(
        self,
        db,
        *,
        owner_id: str,
        session_ref: str,
        send: Callable[[bytes], Awaitable[None]],
        clear_transport: Optional[Callable[[], Awaitable[None]]] = None,
        on_said: Optional[Callable[[str, str], Awaitable[None]]] = None,
        listening=None,
        speaking=None,
        dossier=None,
    ) -> None:
        self.db = db
        self.owner_id = owner_id
        self.session_ref = session_ref
        self.on_said = on_said
        self.dossier = dossier

        self.turns = TurnManager()
        self.playback = PlaybackController(send=send, clear_transport=clear_transport)
        # Quante volte chi ascolta ha sospettato una fine che poi non era.
        # Serve a sapere quanto varrebbe speculare, che è lo sprint dopo.
        self._eager_guesses = 0
        self._turns_resumed = 0

        # I fornitori arrivano da fuori: il runtime non sa come si chiamano.
        # Qui si sceglie il valore di partenza, e un test può metterne altri.
        if listening is None or speaking is None:
            from telephone.deepgram import Speaking, the_ear

            listening = listening or the_ear()
            speaking = speaking or Speaking()
        self.ears = listening
        self.mouth = speaking

        #     SE C'È QUALCUNO CHE CAPISCE QUANDO HAI FINITO, SI DÀ RETTA A LUI.
        # Chi ascolta dichiara se sa decidere i turni. Il gestore dei turni lo
        # sa da subito: i suoi timer diventano una rete di sicurezza invece di
        # essere il metodo.
        self.turns.someone_else_decides_turns = bool(
            getattr(listening, "decides_turns", False)
        )

        self._pump: Optional[asyncio.Task] = None
        self._ticker: Optional[asyncio.Task] = None
        self._working: Optional[asyncio.Task] = None
        self._turn_id = 0
        self._closing = False
        # Quello che ORA sta dicendo in questo momento. Serve a una cosa sola:
        # riconoscere la propria voce quando torna indietro dalla linea.
        self._speaking_now = ""
        # E quello che ha appena finito di dire, finché la linea può ancora
        # riportarlo indietro.
        self._just_said = ""
        self._just_said_until = 0.0
        self._voice_came_back = 0
        self._talking_since = 0.0
        self._too_fast_to_be_a_person = 0
        self.failures: List[str] = []
        self.transcript: List[Dict[str, str]] = []

    # --- aprire -----------------------------------------------------------

    async def open(self) -> bool:
        """
        Apre l'orecchio e la bocca. `False` quando non si può parlare.

        Si aprono tutti e due adesso, non al primo turno: misurato, aprirli
        costa 560 e 787 millisecondi, e pagarli mentre una persona aspetta
        sarebbe metà del tempo di risposta buttato in una stretta di mano.
        """
        if not self.ears.is_available() or not self.mouth.is_available():
            self.failures.append("no_provider")
            return False
        ok_ears = await self.ears.open()
        ok_mouth = await self.mouth.open()
        if not ok_ears or not ok_mouth:
            self.failures.append("provider_not_open")
            await self.close()
            return False

        self.turns.connect_ms = {
            "listening": getattr(self.ears, "connect_ms", None),
            "speaking": getattr(self.mouth, "connect_ms", None),
        }
        self.turns.line_is_open()
        self._pump = asyncio.create_task(self._listen_to_the_ears())
        self._ticker = asyncio.create_task(self._watch_for_the_end_of_turns())
        return True

    # --- l'audio che arriva -----------------------------------------------

    async def hear(self, pcm: bytes) -> None:
        """
        Un pacchetto dalla linea. Passa e non resta.

        Nessuna conversione: la linea porta PCM lineare a 16 kHz e chi ascolta
        lo accetta così. Nessun accumulo: il pacchetto va e viene dimenticato.
        """
        if not pcm or self._closing:
            return
        self.turns.heard_the_first_audio()
        await self.ears.hear(pcm)

    # --- quello che dice chi ascolta --------------------------------------

    async def _listen_to_the_ears(self) -> None:
        try:
            async for heard in self.ears.events():
                if self._closing:
                    return
                await self._one_fact(heard)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.info("ascolto interrotto: %s", type(e).__name__)

    async def _one_fact(self, heard) -> None:
        kind = heard.kind

        #     MENTRE ORA PARLA, LA LINEA RIPORTA ANCHE ORA.
        # Tutto quello che arriva adesso va guardato due volte: potrebbe
        # essere una persona che riprende la parola, o la voce di ORA che
        # rientra dal telefono. Vedi `_is_it_really_a_person`.
        if self.turns.where == "ora_speaking":
            await self._while_ora_is_speaking(heard)
            return

        if kind == "speech_started":
            self.turns.speech_started()
            return

        #     IL TURNO È FINITO PERCHÉ LO DICE CHI ASCOLTA.
        # Arriva la frase intera, ed è autorevole: nessun timer nostro ha
        # voce in capitolo. Il gestore dei turni la prende e il ciclo che
        # guarda i commit se ne accorge al prossimo battito.
        if kind == "end_of_turn":
            self.turns.the_turn_is_over(
                heard.text,
                confidence=heard.confidence,
                trigger=heard.trigger,
                turn_index=heard.turn_index,
            )
            return

        if kind == "eager_end":
            #     SI REGISTRA, NON SI PENSA.
            # Far partire un ragionamento da un «forse ha finito» è lo Sprint
            # 3.3b. Qui si misura soltanto quanto varrebbe.
            self._eager_guesses += 1
            self.turns.maybe_the_turn_is_over(heard.confidence)
            return

        if kind == "turn_resumed":
            self._turns_resumed += 1
            self.turns.the_turn_resumed()
            return

        if kind in ("partial", "final"):
            # Anche adesso che ORA tace, quello che arriva può essere la coda
            # della sua ultima frase che rientra dalla linea.
            theirs = self._without_our_own_voice(heard.text)
            if len(_plain(theirs).strip()) < MIN_INTERRUPTING_CHARS:
                self._voice_came_back += 1
                return
            if theirs != heard.text:
                self._voice_came_back += 1
            if kind == "partial":
                # Un'ipotesi non esce mai di qui.
                self.turns.partial(theirs)
            else:
                self.turns.final_piece(theirs)
            return

        if kind == "pause":
            # Indizio, non fine. Misurato: scatta a metà frase.
            self.turns.pause()
            return

        if kind == "utterance_end":
            self.turns.utterance_end()
            return

    async def _while_ora_is_speaking(self, heard) -> None:
        """
        Qualcosa arriva mentre ORA sta parlando. Chi è?

            UNA VOCE CHE TORNA INDIETRO NON È QUALCUNO CHE PARLA.

        Misurato su una telefonata vera, ed è il motivo per cui quella
        telefonata non ha prodotto una sola risposta intera: cinque turni,
        cinque interruzioni, distanti dall'inizio della voce di ORA 382, 2186,
        1216, 330 e **27** millisecondi. Ventisette millisecondi non è una
        persona che reagisce: è la linea che riporta indietro quello che ORA
        ha appena detto, e chi ascolta che lo scambia per qualcuno.

        Quindi `SpeechStarted` da solo non interrompe più niente. Da solo dice
        «c'è del suono», e su un telefono del suono c'è sempre — anche il
        nostro. Si aspettano le **parole**, e si guarda se sono le nostre.

        Costa: una persona che interrompe davvero viene sentita quando arriva
        la prima trascrizione invece che al primo suono, qualche centinaio di
        millisecondi più tardi. È il prezzo di non interrompersi da sola, e su
        una linea telefonica non è un prezzo, è l'unica strada.
        """
        if heard.kind in (
            "speech_started", "pause", "utterance_end",
            # E la fine di un turno, mentre parliamo noi, è quasi sempre la
            # fine del **nostro**: la linea ci riporta indietro, chi ascolta
            # trascrive, e dichiara finito un turno che non è di nessuno. Le
            # parole che arrivano con quell'evento passano dal filtro sotto,
            # come tutte le altre.
            "eager_end", "turn_resumed",
        ):
            return

        if heard.kind == "end_of_turn":
            # Si guarda solo se erano parole di qualcun altro; se lo erano,
            # il turno nuovo comincia da capo dopo l'interruzione.
            heard = Heard("final", heard.text, heard.at_ms)

        if heard.kind not in ("partial", "final"):
            return

        theirs = self._without_our_own_voice(heard.text)
        if len(_plain(theirs).strip()) < MIN_INTERRUPTING_CHARS:
            # Era tutta roba nostra: nessuno ha ripreso la parola.
            self._voice_came_back += 1
            return

        speaking_for = int((time.perf_counter() - self._talking_since) * 1000)
        if self._talking_since and speaking_for < NOBODY_INTERRUPTS_THAT_FAST_MS:
            # Troppo presto perché sia una reazione: è la linea.
            self._too_fast_to_be_a_person += 1
            return

        # È una persona: adesso l'interruzione è vera.
        self.turns.speech_started()
        await self._barge_in()
        if heard.kind == "final":
            self.turns.final_piece(theirs)
        else:
            self.turns.partial(theirs)

    def _stopped_talking(self, words: str) -> None:
        """
        ORA ha chiuso la bocca; la linea non ancora.

        Quello che stava dicendo smette di essere «adesso» e diventa «poco
        fa»: per qualche secondo continua a essere riconoscibile, perché per
        qualche secondo continua a rientrare.
        """
        if words:
            self._just_said = words
            self._just_said_until = time.perf_counter() + ECHO_TAIL_S
        self._speaking_now = ""
        self._talking_since = 0.0

    def _what_ora_has_in_the_air(self) -> str:
        """Quello che ORA sta dicendo, più quello che la linea può ancora
        riportare indietro."""
        mine = _plain(self._speaking_now) if self._speaking_now else ""
        if self._just_said and time.perf_counter() < self._just_said_until:
            mine += _plain(self._just_said)
        return mine

    def _without_our_own_voice(self, words: str) -> str:
        """
        Quello che resta togliendo la nostra voce dal davanti.

            L'ECO STA IN TESTA, LE PAROLE DELLA PERSONA IN CODA.

        Quando ORA smette, la coda della sua frase rientra e chi trascrive la
        attacca a quello che la persona sta dicendo subito dopo: è arrivato
        «Oggi è domenica 13 settembre 2020 E che impegno domani?», dove la
        prima metà era nostra e la seconda no. Buttare tutto vuol dire perdere
        la domanda; tenere tutto vuol dire metterla in bocca alla persona.

        Quindi si taglia solo il pezzo davanti che era già nostro, e si
        sopporta che non torni identico: basta che lo sia abbastanza.
        """
        mine = self._what_ora_has_in_the_air()
        raw = (words or "").split()
        if not mine.strip() or not raw:
            return words

        flat = [_plain(t).strip() for t in raw]
        cut = 0
        for how_many in range(len(flat), 1, -1):
            head = flat[:how_many]
            ours = sum(1 for t in head if t and f" {t} " in mine)
            if ours / how_many >= ENOUGH_TO_BE_OURS:
                cut = how_many
                break
        return " ".join(raw[cut:])

    def _is_it_really_a_person(self, words: str) -> bool:
        """Se di quello che è arrivato resta qualcosa che non avevamo detto noi."""
        left = self._without_our_own_voice(words)
        return len(_plain(left).strip()) >= MIN_INTERRUPTING_CHARS

    async def _watch_for_the_end_of_turns(self) -> None:
        """
        Guarda se l'ipotesi è diventata un turno.

        Vive in un ciclo suo perché il commit dipende anche dal **tempo** —
        quanto silenzio è passato — e il tempo non arriva come evento.
        """
        try:
            while not self._closing:
                await asyncio.sleep(COMMIT_TICK_S)
                if self._working is not None and not self._working.done():
                    continue
                if not self.turns.should_commit():
                    continue
                said = self.turns.commit()
                if not said:
                    self.turns.give_up_this_turn()
                    continue
                self._turn_id += 1
                self._working = asyncio.create_task(self._answer(said, self._turn_id))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.info("guardia dei turni caduta: %s", type(e).__name__)

    # --- il giro ----------------------------------------------------------

    async def _answer(self, said: str, turn_id: int) -> None:
        """Un turno, dal commit alla voce. Nessun fallimento chiude la linea."""
        try:
            await asyncio.wait_for(
                self._think_and_speak(said, turn_id), THINKING_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            self.failures.append("ora_timeout")
            logger.info("giro troppo lento: si torna ad ascoltare")
            self.turns.give_up_this_turn()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.failures.append(type(e).__name__)
            logger.info("giro non riuscito: %s", type(e).__name__)
            self.turns.give_up_this_turn()
        finally:
            self._stopped_talking(self._speaking_now)

    async def _think_and_speak(self, said: str, turn_id: int) -> None:
        await self._remember("them", said)

        # 1. La stessa ORA. Si aspetta la decisione intera.
        self.turns.ora_asked()
        from telephone.same_ora import a_turn_of_conversation

        answer = await a_turn_of_conversation(
            self.db,
            owner_id=self.owner_id,
            session_id=self.session_ref,
            words=said,
            origin="phone",
        )
        self.turns.ora_decided()

        words, why_not = self._what_to_say(answer)
        if not words:
            #     NESSUN AUDIO PREMATURO.
            # La decisione non era una risposta: era uno strumento, una
            # richiesta di autorità, un blocco. Non si dice niente e non si
            # inventa un riempitivo — ORA non l'ha deciso.
            self.failures.append(why_not or "no_answer")
            logger.info("turno senza risposta parlabile: %s", why_not or "vuoto")
            self.turns.give_up_this_turn()
            return

        # 2. Tagliata dove si respira, e detta.
        await self._say_it(words, turn_id)

    def _what_to_say(self, answer) -> tuple:
        """
        Che cosa di questa decisione va detto a voce, se qualcosa.

            IL CANCELLO.

        `mode` è la decisione finale del core. Solo `answer` e `ask` producono
        qualcosa che una persona deve sentire: la prima è una risposta, la
        seconda è una domanda che ORA ha deciso di fare. Tutto il resto —
        `tool`, `act`, `context`, `research` — sono passi interni, e un passo
        interno detto ad alta voce è ORA che pensa nell'orecchio di qualcuno.
        """
        if not isinstance(answer, dict):
            return "", "no_result"

        if not self.session_ref:
            self.session_ref = str(answer.get("session_id") or "")

        mode = str(answer.get("mode") or "").strip().lower()
        text = str(answer.get("ora_text") or "").strip()
        question = str(answer.get("question") or "").strip()

        if mode in ("answer", "compare", "finish") and text:
            return text, ""
        if mode == "ask" and question:
            return question, ""
        # Alcuni percorsi rispondono senza dichiarare il modo: se c'è del testo
        # destinato a una persona, quello è una risposta.
        if not mode and (text or question):
            return (text or question), ""
        return "", f"mode={mode or 'assente'}"

    async def _say_it(self, words: str, turn_id: int) -> None:
        from telephone.chunker import speakable_pieces
        from telephone.spoken import for_the_ear

        #     STESSO SIGNIFICATO, ALTRA FORMA.
        # Quello che ORA ha deciso di dire resta intero: cambia solo la forma
        # dei pezzi che esistono perché una cosa va letta — gli orari scritti
        # in cifre, le virgolette dei titoli, il grassetto, gli indirizzi web.
        words = for_the_ear(words)
        pieces = speakable_pieces(words)
        if not pieces:
            self.turns.give_up_this_turn()
            return

        handle = self.playback.begin(
            generation_id=f"gen_{uuid.uuid4().hex[:8]}", turn_id=turn_id,
        )
        self.turns.tts_asked()
        self._speaking_now = words
        first = True

        async def on_audio(pcm: bytes) -> None:
            nonlocal first
            if handle.cancelled:
                return
            if first:
                first = False
                self.turns.tts_answered()
                self.turns.ora_started_speaking()
                self._talking_since = time.perf_counter()
            await self.playback.feed(pcm, handle)

        spoke: Spoke = await self.mouth.speak(
            _pieces_as_stream(pieces), on_audio=on_audio,
        )
        if spoke.failed:
            self.failures.append(f"tts_{spoke.failed}")
            logger.info("la voce non ha finito: %s", spoke.failed)

        #     GENERARE NON È PARLARE.
        # Il fornitore ha finito di produrre, ma la voce continua a uscire
        # dalla coda per altri secondi — e per tutti quei secondi la linea la
        # riporta indietro. Quindi quello che ORA sta dicendo si dimentica
        # quando ha finito di **dirlo**, non quando ha finito di generarlo.
        if handle.cancelled:
            return
        await self.playback.finish(handle)
        if handle.cancelled:
            return

        self._stopped_talking(words)
        if first:
            #     NEL REGISTRO SOLO QUELLO CHE QUALCUNO HA SENTITO.
            # `first` è ancora vero: non è uscito un byte. Scrivere lo stesso
            # «ORA ha detto» sarebbe un verbale di una frase che nessuno ha
            # sentito — e la telefonata in cui è successo lo ha dimostrato:
            # il registro conteneva una risposta, la persona al telefono
            # aveva sentito silenzio.
            self.failures.append("tts_silent")
            logger.info("nessun audio prodotto: il turno non si annota")
            self.turns.give_up_this_turn()
            return

        await self._remember("ora", words)
        self.turns.ora_finished_speaking()

    # --- l'interruzione ---------------------------------------------------

    async def _barge_in(self) -> None:
        """
        Qualcuno ha ripreso la parola. ORA tace, adesso.

            CHI RICOMINCIA A PARLARE NON CHIEDE IL PERMESSO.

        Tre gesti, in quest'ordine: si dice al fornitore di smettere di
        generare, si butta quello che era in coda da noi, e si dice al
        trasporto di buttare quello che aveva già preso in carico. Saltarne
        uno significa sentire ORA finire la frase da sola dopo il silenzio.
        """
        logger.info("interrotta: si torna ad ascoltare")
        # Da adesso non esce più niente dalla nostra parte — ma quello che era
        # già partito può ancora tornare indietro, e va riconosciuto.
        self._stopped_talking(self._speaking_now)
        try:
            await self.mouth.cancel()
            self.turns.tts_cancelled()
        except Exception as e:
            logger.info("la voce non si è fermata: %s", type(e).__name__)
        try:
            await self.playback.cancel()
            self.turns.playback_cleared()
        except Exception as e:
            logger.info("la coda non si è svuotata: %s", type(e).__name__)

        if self._working is not None and not self._working.done():
            self._working.cancel()
        self.turns.began_speaking_after_interruption()

    # --- il testo che resta ------------------------------------------------

    async def _remember(self, who: str, words: str) -> None:
        """Il testo si tiene; l'audio no. È tutta la regola."""
        self.transcript.append({"who": who, "said": words})
        self.transcript = self.transcript[-60:]
        if self.on_said is not None:
            try:
                await self.on_said(who, words)
            except Exception as e:
                logger.info("battuta non annotata: %s", type(e).__name__)

    # --- chiudere ---------------------------------------------------------

    async def close(self) -> None:
        """La linea si è chiusa: si lascia andare tutto, in ordine."""
        self._closing = True
        self.turns.hung_up()
        for task in (self._ticker, self._pump, self._working):
            if task is not None and not task.done():
                task.cancel()
        self._ticker = self._pump = self._working = None
        try:
            await self.playback.close()
        except Exception:
            pass
        for provider in (self.mouth, self.ears):
            try:
                await provider.close()
            except Exception:
                pass

    def how_it_went(self) -> Dict[str, Any]:
        """I numeri e il testo. Mai un campione di audio."""
        out: Dict[str, Any] = dict(self.turns.how_it_went())
        out["playback"] = self.playback.how_it_went()
        # Quante volte la linea ci ha riportato la nostra voce. Se questo
        # numero è alto e le interruzioni sono zero, il filtro sta lavorando.
        out["own_voice_ignored"] = self._voice_came_back
        out["too_fast_to_be_a_person"] = self._too_fast_to_be_a_person
        out["who_decides_turns"] = (
            "provider" if self.turns.someone_else_decides_turns else "timers"
        )
        out["eager_guesses"] = self._eager_guesses
        out["turns_resumed"] = self._turns_resumed
        if self.failures:
            out["failures"] = self.failures[:10]
        return out


async def _pieces_as_stream(pieces: List[str]):
    """
    I pezzi, uno dopo l'altro.

    Oggi arrivano tutti insieme perché il core risponde tutto insieme. Il
    giorno che arriveranno a goccia, questa funzione sparisce e il resto non
    se ne accorge.
    """
    for piece in pieces:
        yield piece
