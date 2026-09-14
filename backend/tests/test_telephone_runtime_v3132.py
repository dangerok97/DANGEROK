"""
V3.13 Sprint 3.2 — il runtime vocale: dal parlato alla voce di ORA.

    `speech_final` NON È LA FINE DEL TURNO.
    PRIMA DEL COMMIT È UN'IPOTESI.
    NESSUN AUDIO PRIMA CHE ORA ABBIA DECISO DI RISPONDERE.
    L'AUDIO È UN FIUME, NON UN ARCHIVIO.

Quattro frasi, e quasi tutto quello che c'è qui dentro difende una di esse.
La prima è la più costosa da imparare: su una telefonata vera l'operatore ha
alzato la mano dopo 2,4 secondi su 4 di parlato, cioè sulla pausa dopo «Ciao,
ORA», mentre la persona stava ancora parlando. Un runtime che risponde lì
interrompe la gente, e sembra sordo mentre lo fa.
"""

from __future__ import annotations

import ast
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import AsyncIterator, List

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import _loop_harness  # tests/_loop_harness.py: the one place a loop is chosen

HERE = Path(_BACKEND)


def _code_only(text: str) -> str:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if ast.get_docstring(node, clean=False):
                node.body = node.body[1:]
    stripped = ast.unparse(tree)
    return "\n".join(
        "" if line.strip().startswith("#") else line.split("#")[0]
        for line in stripped.splitlines()
    )


def _run(coro):
    return _loop_harness.run(coro)


# ---------------------------------------------------------------------------
# Il suono, quando serve cambiarlo di passo
# ---------------------------------------------------------------------------

def test_resampling_keeps_the_duration_and_does_not_clip():
    """
    §2: ricampionare non è reinterpretare i byte.

    Sul percorso vero non serve — Vonage, Nova-3 e Aura-2 parlano tutti
    linear16 a 16 kHz — ma esiste come rete per il giorno che un fornitore
    non lo farà, e una rete non provata non è una rete.

    Tre cose devono reggere: la durata resta la stessa, il conteggio dei
    campioni torna, e scendendo non si introduce distorsione.
    """
    import math

    import numpy as np

    from telephone.audio import resample, seconds_of

    # Un secondo di la a 440 Hz, che è dentro la banda telefonica.
    rate = 16000
    samples = np.array(
        [int(12000 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(rate)],
        dtype="<i2",
    )
    original = samples.tobytes()
    assert abs(seconds_of(original, rate) - 1.0) < 0.001

    up = resample(original, src=16000, dst=24000)
    assert abs(seconds_of(up, 24000) - 1.0) < 0.01, "salendo la durata cambia"
    assert abs(len(up) / 2 - 24000) < 24, "il conteggio dei campioni non torna"

    down = resample(original, src=16000, dst=8000)
    assert abs(seconds_of(down, 8000) - 1.0) < 0.01, "scendendo la durata cambia"

    # Nessun campione sbatte contro il fondo scala: il segnale di partenza sta
    # ampiamente sotto, e un ricampionamento che satura sta sbagliando.
    for out in (up, down):
        peaks = np.frombuffer(out, dtype="<i2")
        assert int(np.max(np.abs(peaks))) < 32000, "il ricampionamento satura"

    # E non si inventa niente dal niente.
    assert resample(b"", src=16000, dst=24000) == b""
    assert resample(original, src=16000, dst=16000) is original


# ---------------------------------------------------------------------------
# Dove si taglia una frase
# ---------------------------------------------------------------------------

def test_the_chunker_never_breaks_a_number_or_a_date():
    """
    §8: una frase si taglia dove una persona respirerebbe.

    «4.000 €» spezzato dopo il punto diventa «quattro» e poi «zero zero zero
    euro». «gio. 17» diventa due frasi. Sono i due modi più rapidi di far
    sembrare rotta una risposta giusta.
    """
    from telephone.chunker import speakable_pieces

    pieces = speakable_pieces(
        "Il bonifico è di 4.000 euro. L'appuntamento è gio. 17 alle 11:00. "
        "Te lo confermo?"
    )
    joined = " ".join(pieces)
    assert "4.000" in joined, "il numero è stato spezzato"
    assert "gio. 17" in joined, "l'abbreviazione è stata spezzata"
    assert "11:00" in joined
    assert len(pieces) >= 2, "una risposta lunga non è stata tagliata"
    # Nessun pezzo comincia con un numero orfano.
    for piece in pieces:
        assert not piece.strip().startswith("000")

    # Una frase corta resta una frase sola: tagliarla non aiuta nessuno.
    assert speakable_pieces("Sì.") == ["Sì."]
    assert speakable_pieces("") == []
    assert speakable_pieces("   ") == []

    # E un monologo senza punteggiatura viene detto lo stesso.
    long_one = "va bene allora " * 40
    out = speakable_pieces(long_one)
    assert out, "una frase senza punti non viene detta"
    assert all(len(p) <= 260 for p in out)
    # Nessuna parola è stata tagliata a metà.
    assert "".join(out).replace(" ", "") == long_one.replace(" ", "")


# ---------------------------------------------------------------------------
# Di chi è il turno
# ---------------------------------------------------------------------------

def test_a_pause_alone_is_not_the_end_of_a_turn():
    """
    §4: la lezione più cara di questo sprint.

    Misurato su audio vero: `speech_final` scatta sulla pausa dopo «Ciao,
    ORA» mentre la frase continua. Se bastasse quello, ORA risponderebbe a
    metà della domanda — e lo farebbe ogni volta che qualcuno la chiama per
    nome prima di chiedere qualcosa, cioè quasi sempre.
    """
    from telephone.turn import TurnManager

    t = TurnManager()
    t.line_is_open()
    t.speech_started()
    t.final_piece("Ciao, ORA")
    t.pause()

    assert t.where == "turn_candidate", "una pausa non mette il turno in dubbio"
    assert not t.should_commit(), (
        "una pausa dopo due parole viene presa per la fine della frase"
    )

    # Anche con il punto, che il trascrittore mette a ogni pezzo: «Ciao, ORA.»
    # sembra una frase finita e non lo è.
    t2 = TurnManager()
    t2.line_is_open()
    t2.speech_started()
    t2.final_piece("Ciao, ORA.")
    t2.pause()
    t2._last_voice = time.perf_counter() - 1.2
    assert not t2.should_commit(), (
        "il punto messo dal trascrittore viene preso per la fine del turno"
    )

    # La frase continua, e si chiude quando lo dice chi ascolta.
    t.speech_started()
    t.final_piece("dimmi che giorno è oggi.")
    t.utterance_end()
    assert t.should_commit(), "il segnale di fine turno non chiude il turno"

    said = t.commit()
    assert said == "Ciao, ORA dimmi che giorno è oggi."
    assert t.where == "thinking"
    # E il turno prossimo comincia vuoto.
    assert t.what_was_said() == ""


def test_a_hanging_word_keeps_the_turn_open():
    """
    §4: «dimmi che giorno è oggi e» non è una frase finita.

    Una congiunzione o un articolo in fondo vuol dire che la persona sta
    ancora parlando, e rispondere lì è interromperla.
    """
    from telephone.turn import TurnManager

    # Sono i casi che il meccanismo riconosce davvero: una frase che finisce
    # con una congiunzione, un articolo o una preposizione continua sempre.
    # Non li riconosce tutti — «volevo sapere se per caso» finisce con un
    # sostantivo legittimo, e nessuna lista di parole può distinguerlo da «non
    # è il caso» — e allungare la lista per inseguirli sarebbe grammatica
    # scritta male. Dopo un secondo di silenzio, rispondere lì è difendibile.
    for unfinished in (
        "ricordami domani di chiamare il",
        "volevo sapere se per",
        "senti una cosa, quando",
    ):
        t = TurnManager()
        t.line_is_open()
        t.speech_started()
        t.final_piece(unfinished)
        t.pause()
        # La rete sotto, quella che scatta quando il segnale di fine turno non
        # arriva mai: nemmeno lì si chiude una frase che visibilmente continua.
        t._last_voice = time.perf_counter() - 5.0
        assert not t.should_commit(), f"«{unfinished}» è stata presa per finita"

    # Mentre una frase che sta in piedi, dopo lo stesso guasto, parte.
    t = TurnManager()
    t.line_is_open()
    t.speech_started()
    t.final_piece("ricordami di chiamare il notaio")
    t.pause()
    t._last_voice = time.perf_counter() - 5.0
    assert t.should_commit()


def test_utterance_end_is_enough_on_its_own():
    """
    §4: quando l'operatore dice che il silenzio è stato lungo, basta.

    È il segnale più solido che si ha — guarda i tempi delle parole, non
    l'energia — e aspettare oltre farebbe sembrare ORA assente.
    """
    from telephone.turn import TurnManager

    t = TurnManager()
    t.line_is_open()
    t.speech_started()
    t.final_piece("e allora")   # una frase che non starebbe in piedi da sola
    t.utterance_end()
    assert t.should_commit(), "un silenzio lungo non chiude il turno"


def test_a_cough_is_not_a_turn():
    """§4: un turno più corto di trecento millisecondi non è una frase."""
    from telephone.turn import TurnManager

    t = TurnManager()
    t.line_is_open()
    t.speech_started()
    t.final_piece("mh")
    t.pause()
    assert not t.should_commit()


def test_a_partial_never_becomes_a_turn():
    """
    §5: prima del commit è un'ipotesi.

    Un provvisorio che diventa un messaggio è un modo di mettere in bocca a
    qualcuno mezza frase. Qui si verifica che non ci sia nessuna strada.
    """
    from telephone.turn import TurnManager

    t = TurnManager()
    t.line_is_open()
    t.speech_started()
    t.partial("ricordami di chiamare")
    assert t.what_was_said() == "", "un provvisorio è finito nell'ipotesi"
    assert not t.should_commit()

    # E nel runtime, un provvisorio non raggiunge il core.
    bridge = _code_only((HERE / "telephone" / "bridge.py").read_text(encoding="utf-8"))
    partial_branch = bridge.split("if kind == 'partial'")[1][:260]
    assert "a_turn_of_conversation" not in partial_branch
    assert "turns.partial" in partial_branch


# ---------------------------------------------------------------------------
# Il cancello
# ---------------------------------------------------------------------------

def test_only_a_real_answer_becomes_audio():
    """
    §6: nessun audio prima che ORA abbia deciso di rispondere.

    Il core non produce testo: produce una decisione. Finché non è completa
    non si sa se questo turno è una risposta o un passo interno — e un passo
    interno detto ad alta voce è ORA che pensa nell'orecchio di qualcuno.
    """
    from telephone.bridge import RealtimeVoiceSession

    async def nowhere(pcm):
        return None

    session = RealtimeVoiceSession(
        None, owner_id="u", session_ref="s", send=nowhere,
        listening=_FakeEars(), speaking=_FakeMouth(),
    )

    # Quello che va detto.
    assert session._what_to_say({"mode": "answer", "ora_text": "Oggi è venerdì."})[0]
    assert session._what_to_say({"mode": "ask", "question": "A che ora?"})[0]

    # Quello che non va detto: sono passi interni del ragionamento.
    for silent in ("tool", "act", "context", "research", "finish"):
        words, why = session._what_to_say(
            {"mode": silent, "ora_text": "" if silent != "finish" else ""}
        )
        assert words == "", f"il modo «{silent}» produce audio"
        assert why, "non dice perché sta zitta"

    # E niente non è una risposta.
    assert session._what_to_say(None)[0] == ""
    assert session._what_to_say({})[0] == ""


# ---------------------------------------------------------------------------
# La coda verso la linea
# ---------------------------------------------------------------------------

def test_playback_pours_at_the_speed_of_listening_and_stops_when_told():
    """
    §10 + §11: si parla al ritmo in cui si viene ascoltati, e si smette subito.

    Due garanzie. La prima: i pacchetti escono della misura giusta — mezzo
    pacchetto fa scattare la voce. La seconda, quella che conta: dopo
    l'annullamento non esce più niente, **nemmeno quello che era già in coda
    o che arriva un istante dopo**. Un pacchetto in ritardo dopo il silenzio è
    ORA che dice mezza sillaba a vuoto.
    """
    async def body():
        from telephone.playback import FRAME_BYTES, PlaybackController

        sent: List[bytes] = []
        cleared = {"n": 0}

        async def send(frame):
            sent.append(frame)

        async def clear():
            cleared["n"] += 1

        p = PlaybackController(send=send, clear_transport=clear)
        handle = p.begin(generation_id="g1", turn_id=1)

        # Un secondo di audio: cinquanta pacchetti da venti millisecondi.
        await p.feed(b"\x01\x02" * (FRAME_BYTES // 2 * 50), handle)
        await asyncio.sleep(0.25)
        assert sent, "non è uscito niente"
        assert all(len(f) == FRAME_BYTES for f in sent), "pacchetti di misura sbagliata"
        partial = len(sent)
        assert partial < 50, "è uscito tutto insieme invece che al ritmo del parlato"

        # Interruzione.
        thrown = await p.cancel()
        assert handle.cancelled
        assert thrown > 0, "la coda era già vuota: non si è buttato niente"
        assert cleared["n"] == 1, "al trasporto non è stato detto di svuotare"

        # Quello che arriva dopo non esce.
        after = len(sent)
        await p.feed(b"\x03\x04" * (FRAME_BYTES // 2 * 10), handle)
        await asyncio.sleep(0.15)
        assert len(sent) == after, "un pacchetto è uscito dopo l'annullamento"

        await p.close()

    _run(body())


# ---------------------------------------------------------------------------
# Il giro intero, senza rete
# ---------------------------------------------------------------------------

class _FakeEars:
    """Un orecchio che dice quello che gli si mette in bocca."""

    name = "fake"
    connect_ms = 1

    def __init__(self, script=None):
        self.script = list(script or [])
        self.heard_bytes = 0
        self.opened = False
        self.closed = False

    def is_available(self):
        return True

    async def open(self):
        self.opened = True
        return True

    async def hear(self, pcm):
        self.heard_bytes += len(pcm)

    async def events(self):
        for item in self.script:
            await asyncio.sleep(0.01)
            yield item

    async def close(self):
        self.closed = True


class _FakeMouth:
    """Una bocca che produce silenzio misurabile, e sa smettere."""

    name = "fake"
    connect_ms = 1

    def __init__(self, fail=""):
        self.said: List[str] = []
        self.cancelled = 0
        self.closed = False
        self.fail = fail

    def is_available(self):
        return True

    async def open(self):
        return True

    async def speak(self, text_chunks, *, on_audio):
        from telephone.providers import Spoke

        out = Spoke()
        if self.fail:
            out.failed = self.fail
            return out
        async for piece in text_chunks:
            self.said.append(piece)
            await on_audio(b"\x00\x00" * 320)
            out.bytes_out += 640
            if out.first_audio_ms is None:
                out.first_audio_ms = 5
        return out

    async def cancel(self):
        self.cancelled += 1

    async def close(self):
        self.closed = True


def test_the_whole_loop_from_speech_to_voice():
    """
    §19: la pipeline intera, senza mockare il pezzo che conta.

    Gli unici finti qui sono i due fornitori — non c'è rete in un test — ma il
    gestore dei turni, il commit, il cancello, il chunker e la coda sono
    quelli veri. Si verifica che una frase detta diventi una risposta parlata
    e che il testo resti mentre l'audio no.
    """
    async def body():
        import telephone.same_ora as same_ora
        from telephone.bridge import RealtimeVoiceSession
        from telephone.providers import Heard

        asked: List[str] = []

        async def fake_core(db, *, owner_id, session_id, words, origin="phone"):
            asked.append(words)
            assert origin == "phone", "la provenienza non arriva al core"
            return {
                "mode": "answer",
                "ora_text": "Oggi è venerdì 12 settembre. Serve altro?",
                "session_id": "ces_finta",
            }

        real = same_ora.a_turn_of_conversation
        same_ora.a_turn_of_conversation = fake_core
        try:
            sent: List[bytes] = []

            async def send(frame):
                sent.append(frame)

            ears = _FakeEars([
                Heard("speech_started"),
                Heard("final", "Ciao ORA"),
                Heard("pause"),
                Heard("final", "dimmi che giorno è oggi."),
                Heard("utterance_end"),
            ])
            mouth = _FakeMouth()
            session = RealtimeVoiceSession(
                None, owner_id="u", session_ref="", send=send,
                listening=ears, speaking=mouth,
            )
            assert await session.open()
            await session.hear(b"\x00\x00" * 320)

            for _ in range(60):
                await asyncio.sleep(0.05)
                if mouth.said:
                    break

            assert asked == ["Ciao ORA dimmi che giorno è oggi."], (
                f"al core è arrivato: {asked}"
            )
            assert mouth.said, "ORA non ha detto niente"
            assert "venerdì" in " ".join(mouth.said)
            await asyncio.sleep(0.2)
            assert sent, "niente è uscito sulla linea"

            # Il testo resta; l'audio no.
            who = [t["who"] for t in session.transcript]
            assert who == ["them", "ora"]
            numbers = session.how_it_went()
            assert numbers["turns"] >= 1
            assert "each_turn" in numbers
            first = numbers["each_turn"][0]
            for needed in (
                "turn_committed_ms", "ora_request_start_ms",
                "tts_request_start_ms", "playback_first_chunk_ms",
            ):
                assert needed in first, f"manca la misura {needed}"

            await session.close()
            assert ears.closed and mouth.closed, "i fornitori non sono stati chiusi"
        finally:
            same_ora.a_turn_of_conversation = real

    _run(body())


def test_a_long_answer_comes_out_whole():
    """
    §10bis: una risposta lunga esce intera, non bucata.

        ESSERE AVANTI NON È ESSERE IN RITARDO.

    Il difetto che questa prova esiste per non far tornare, sentito da una
    persona al telefono: «oggi è lunedì 14 settembre duemilave», e poi
    «domani non hai impegn». Misurato sulla stessa telefonata: **128 frame
    buttati su 610 — il ventuno per cento della voce di ORA**, buchi dentro le
    frasi.

    La causa era un tetto sulla coda che confrontava quanto era stato generato
    con quanto era stato mandato. Chi genera la voce produce cinque secondi di
    audio in uno: stare avanti è lo stato normale, ed è quello che rende il
    parlato continuo invece che a scatti. Il tetto scattava sempre.

    Qui si versa dentro una risposta lunga tutta insieme — come fa il
    fornitore vero — e si pretende che esca tutta.
    """
    async def body():
        from telephone.playback import PlaybackController

        uscito = []

        async def send(frame):
            uscito.append(frame)

        playback = PlaybackController(send=send)
        handle = playback.begin(generation_id="g1", turn_id=1)

        # Dodici secondi di parlato, consegnati in un colpo solo: è
        # esattamente quello che fa Aura-2 su una risposta di due frasi.
        dodici_secondi = b"\x11\x11" * (16000 * 12)
        await playback.feed(dodici_secondi, handle)
        await playback.finish(handle)

        atteso = len(dodici_secondi) // playback.frame_bytes
        assert playback.frames_dropped == 0, (
            f"buttati {playback.frames_dropped} frame di una risposta normale"
        )
        assert playback.frames_sent == atteso, (
            f"usciti {playback.frames_sent} frame su {atteso}: la voce è bucata"
        )
        assert len(uscito) == atteso
        # E quello che è uscito è davvero la voce, non silenzio di riempimento.
        assert b"".join(uscito).count(b"\x11") == len(dodici_secondi)

        await playback.close()

    _run(body())


def test_an_interrupted_answer_is_stopped_not_perforated():
    """
    §10bis: e quando la conversazione va avanti, si smette — non si buca.

    Il caso che il vecchio tetto voleva coprire è questo, ed era già coperto
    meglio: `cancel()` svuota tutto in sedici millisecondi misurati. La
    differenza fra i due rimedi è quella fra «ORA ha smesso di parlare» e «ORA
    parla a singhiozzo», e al telefono si sente.
    """
    async def body():
        from telephone.playback import PlaybackController

        uscito = []

        async def send(frame):
            uscito.append(frame)
            await asyncio.sleep(0)

        playback = PlaybackController(send=send)
        handle = playback.begin(generation_id="g1", turn_id=1)
        await playback.feed(b"\x22\x22" * (16000 * 10), handle)

        await playback.cancel()

        assert handle.cancelled
        prima = len(uscito)
        await asyncio.sleep(0.1)
        assert len(uscito) == prima, "ha continuato a parlare dopo lo stop"
        await playback.close()

    _run(body())


def test_speaking_over_ora_stops_her():
    """
    §11: barge-in. Chi ricomincia a parlare non chiede il permesso.

        MA UNA VOCE CHE TORNA INDIETRO NON È QUALCUNO CHE PARLA.

    Questa prova affermava che bastasse un `SpeechStarted`, e una telefonata
    vera l'ha smentita: cinque turni, cinque interruzioni, una a **27
    millisecondi** dall'inizio della voce di ORA. Nessuna persona reagisce in
    27 millisecondi — era la linea che riportava indietro ORA, e chi ascolta
    che la scambiava per qualcuno. La telefonata non ha prodotto una sola
    risposta intera.

    Quindi adesso servono le parole, e devono essere parole di qualcun altro.
    """
    async def body():
        import telephone.same_ora as same_ora
        from telephone.bridge import RealtimeVoiceSession
        from telephone.providers import Heard

        detto = "Ecco, allora, domani hai una riunione. " * 8

        async def slow_core(db, *, owner_id, session_id, words, origin="phone"):
            return {"mode": "answer", "ora_text": detto}

        real = same_ora.a_turn_of_conversation
        same_ora.a_turn_of_conversation = slow_core
        try:
            async def send(frame):
                await asyncio.sleep(0)

            ears = _FakeEars([
                Heard("speech_started"),
                Heard("final", "dimmi che giorno è oggi."),
                Heard("utterance_end"),
            ])
            mouth = _FakeMouth()
            session = RealtimeVoiceSession(
                None, owner_id="u", session_ref="s", send=send,
                listening=ears, speaking=mouth,
            )
            await session.open()

            for _ in range(60):
                await asyncio.sleep(0.05)
                if session.turns.where == "ora_speaking":
                    break
            assert session.turns.where == "ora_speaking", "ORA non ha cominciato"

            # 1. Del suono, e basta. Non è nessuno.
            await session._one_fact(Heard("speech_started"))
            assert mouth.cancelled == 0, "un suono da solo ha interrotto ORA"
            assert session.turns.where == "ora_speaking"

            # 2. Parole che sono le nostre: è la linea che ce le riporta.
            await session._one_fact(Heard("partial", "ecco allora domani hai"))
            assert mouth.cancelled == 0, "ORA si è interrotta con la propria voce"
            assert session.turns.interruptions == 0
            assert session.how_it_went()["own_voice_ignored"] >= 1

            # 3. Parole d'altri, ma troppo presto perché sia una reazione.
            await session._one_fact(Heard("partial", "aspetta un momento"))
            assert mouth.cancelled == 0, (
                "interrotta prima che una persona potesse reagire"
            )
            assert session.how_it_went()["too_fast_to_be_a_person"] >= 1

            # 4. Le stesse parole, dopo che ORA ha parlato abbastanza da poter
            #    essere sentita. Adesso sì.
            session._talking_since -= 3
            await session._one_fact(Heard("partial", "aspetta un momento"))
            assert mouth.cancelled == 1, "alla voce non è stato detto di smettere"
            assert session.playback.current.cancelled, "la coda non è stata annullata"
            assert session.turns.interruptions == 1
            assert session.turns.where == "user_speaking", (
                "non si è tornati ad ascoltare"
            )
            # E quello che ha detto interrompendo non si perde.
            assert "aspetta" in session.turns._partial.lower()

            await session.close()
        finally:
            same_ora.a_turn_of_conversation = real

    _run(body())


def test_the_echo_is_cut_off_the_front_and_the_question_survives():
    """
    §11: togliere la nostra voce senza portarsi via la loro.

    Casi presi da una prova con la voce rimandata dentro alla linea. L'eco non
    torna mai identica — «settembre 2026» è rientrata «settembre 2020» — e non
    torna mai da sola: chi trascrive la attacca davanti a quello che la
    persona sta dicendo subito dopo.

        BUTTARE TUTTO PERDE LA DOMANDA.
        TENERE TUTTO LA METTE IN BOCCA A CHI NON L'HA FATTA.
    """
    async def body():
        from telephone.bridge import RealtimeVoiceSession

        async def send(frame):
            return None

        session = RealtimeVoiceSession(
            None, owner_id="u", session_ref="s", send=send,
            listening=_FakeEars(), speaking=_FakeMouth(),
        )
        session._speaking_now = "Oggi è domenica 13 settembre 2026."

        # 1. Tutta nostra, anche se trascritta male: non è nessuno.
        assert not session._is_it_really_a_person("oggi e domenica 13 settembre 2020")

        # 2. Metà nostra e metà loro: resta la domanda.
        left = session._without_our_own_voice(
            "Oggi è domenica 13 settembre 2020 E che impegno domani?"
        )
        assert "impegno domani" in left.lower(), left
        assert "settembre" not in left.lower(), f"l'eco è rimasta: {left}"
        assert session._is_it_really_a_person(
            "Oggi è domenica 13 settembre 2020 E che impegno domani?"
        )

        # 3. Niente di nostro: passa intera.
        assert session._without_our_own_voice("Aspetta un momento") == (
            "Aspetta un momento"
        )

        # 4. E quando ORA ha smesso da un pezzo, non si filtra più niente.
        session._speaking_now = ""
        session._just_said = "Oggi è domenica 13 settembre 2026."
        session._just_said_until = 0.0
        assert session._without_our_own_voice("oggi è domenica") == "oggi è domenica"

        await session.close()

    _run(body())


def test_a_syllable_coming_back_from_the_line_is_not_an_interruption():
    """
    §11: e nemmeno mezza parola.

    La trascrizione di un'eco arriva a pezzi piccolissimi. Sotto una certa
    lunghezza non c'è nessuno che parla: c'è del suono che somiglia a una
    sillaba, e interrompere lì significa non finire mai una frase.
    """
    from telephone.bridge import _plain, MIN_INTERRUPTING_CHARS

    assert len(_plain("o").strip()) < MIN_INTERRUPTING_CHARS
    assert len(_plain("mh").strip()) < MIN_INTERRUPTING_CHARS
    assert len(_plain("aspetta").strip()) >= MIN_INTERRUPTING_CHARS

    # E il confronto regge accenti e punteggiatura, perché l'eco non torna mai
    # trascritta identica: «oggi è domenica» può rientrare come «oggi e
    # domenica».
    assert _plain("oggi e domenica").strip() in _plain("Oggi è domenica 13.")


def test_nothing_breaks_when_a_provider_does():
    """
    §16: un fornitore che cade non chiude la telefonata.

    La persona sente al massimo un silenzio e ripete la domanda — come farebbe
    con chiunque. Quello che non deve succedere è una linea morta, un ciclo
    infinito o un turno che resta appeso.
    """
    async def body():
        import telephone.same_ora as same_ora
        from telephone.bridge import RealtimeVoiceSession
        from telephone.providers import Heard

        async def broken_core(db, **kw):
            raise RuntimeError("il core è caduto")

        real = same_ora.a_turn_of_conversation
        same_ora.a_turn_of_conversation = broken_core
        try:
            async def send(frame):
                return None

            session = RealtimeVoiceSession(
                None, owner_id="u", session_ref="s", send=send,
                listening=_FakeEars(), speaking=_FakeMouth(),
            )
            await session.open()
            await session._answer("dimmi che giorno è", 1)
            assert session.turns.where == "listening", (
                "dopo un fallimento non si torna ad ascoltare"
            )
            assert session.failures, "il fallimento non è stato registrato"
            await session.close()
        finally:
            same_ora.a_turn_of_conversation = real

        # E una voce che non parla non lascia la sessione appesa.
        async def send2(frame):
            return None

        import telephone.same_ora as same_ora2

        async def ok_core(db, **kw):
            return {"mode": "answer", "ora_text": "Va bene."}

        real2 = same_ora2.a_turn_of_conversation
        same_ora2.a_turn_of_conversation = ok_core
        try:
            from telephone.bridge import RealtimeVoiceSession as S

            s2 = S(
                None, owner_id="u", session_ref="s", send=send2,
                listening=_FakeEars(), speaking=_FakeMouth(fail="timeout"),
            )
            await s2.open()
            await s2._answer("qualcosa", 1)
            assert any("tts_" in f for f in s2.failures), (
                "il fallimento della voce non è stato registrato"
            )
            await s2.close()
        finally:
            same_ora2.a_turn_of_conversation = real2

    _run(body())


def test_hanging_up_lets_everything_go():
    """
    §15 + §16: a fine chiamata non resta un byte, e nessun compito appeso.

    Un task asyncio che sopravvive alla telefonata è una perdita lenta: dieci
    telefonate e il server ha dieci cicli che girano su una linea chiusa.
    """
    async def body():
        from telephone.bridge import RealtimeVoiceSession

        async def send(frame):
            return None

        ears, mouth = _FakeEars(), _FakeMouth()
        session = RealtimeVoiceSession(
            None, owner_id="u", session_ref="s", send=send,
            listening=ears, speaking=mouth,
        )
        await session.open()
        await session.hear(b"\x00\x00" * 320)
        await session.close()

        assert session._pump is None and session._ticker is None
        assert ears.closed and mouth.closed
        assert session.turns.where == "ending"
        # Quello che resta è testo e numeri.
        numbers = session.how_it_went()
        blob = repr(numbers)
        assert "\\x00" not in blob, "nei numeri è finito dell'audio"

    _run(body())


def test_the_last_turn_still_counts_when_the_line_drops():
    """
    §14: chi riattacca mentre ORA risponde resta nei numeri.

    Alla prova a secco il conteggio diceva «un turno» quando i turni erano
    due: il trasporto leggeva i tempi *prima* di chiudere, e il turno ancora
    in corso non era ancora stato archiviato. Un difetto di misura è peggio
    di un difetto visibile, perché fa sembrare sano quello che non lo è.
    """
    async def body():
        from telephone.bridge import RealtimeVoiceSession

        async def send(frame):
            return None

        session = RealtimeVoiceSession(
            None, owner_id="u", session_ref="s", send=send,
            listening=_FakeEars(), speaking=_FakeMouth(),
        )
        await session.open()

        # Un turno che arriva fino a «ORA sta pensando» e non oltre.
        session.turns.speech_started()
        session.turns.final_piece("Mi puoi richiamare domani mattina?")
        session.turns.utterance_end()
        assert session.turns.should_commit()
        session.turns.commit()
        session.turns.ora_asked()

        # La linea cade adesso.
        await session.close()
        numbers = session.how_it_went()
        assert numbers["turns"] == 1, "il turno in corso è sparito dai numeri"

    _run(body())


def test_the_transport_reads_the_numbers_after_closing():
    """
    §14: e il trasporto li legge nell'ordine giusto.

    La proprietà sopra vale solo se chi la usa chiude prima di contare.
    """
    code = _code_only(
        (HERE / "telephone" / "vonage_router.py").read_text(encoding="utf-8")
    )
    chiude = code.index("await session.close()")
    conta = code.index("session.how_it_went()")
    assert chiude < conta, "si contano i turni prima di averli chiusi"


class _FakeVoiceSocket:
    """
    Il filo verso chi fa la voce, con la sua memoria.

    Serve una cosa sola che le bocche finte non sanno fare: ricordarsi che a
    un `Clear` corrisponde un `Cleared`, e che quel messaggio resta sul filo
    finché qualcuno non lo legge.
    """

    def __init__(self):
        self.waiting = []
        self.sent = []

    async def send(self, raw):
        self.sent.append(raw)
        kind = json.loads(raw).get("type")
        if kind == "Flush":
            self.waiting.append(b"\x11\x11" * 320)
            self.waiting.append(json.dumps({"type": "Flushed"}))
        elif kind == "Clear":
            # Quello che aveva in canna, e poi la conferma.
            self.waiting.append(b"\x99\x99" * 320)
            self.waiting.append(json.dumps({"type": "Cleared"}))

    async def recv(self):
        if not self.waiting:
            await asyncio.sleep(3)
        return self.waiting.pop(0)

    async def close(self):
        return None


def test_the_voice_speaks_again_after_being_interrupted():
    """
    §13: il difetto peggiore dello sprint, e non somigliava a un guasto.

    Su una telefonata vera, dopo la prima interruzione ORA non ha parlato mai
    più. Chi interrompe fa annullare il giro che stava parlando; quel giro
    muore dentro `recv()` e la conferma dell'interruzione resta sul filo. Il
    turno seguente manda `Speak`, legge il primo messaggio che trova — quella
    conferma — e se ne va convinto di aver finito.

        QUATTRO MILLISECONDI, ZERO BYTE, NESSUN ERRORE.

    Per questo nessuna prova se n'era accorta: non c'era niente da vedere.
    """
    async def body():
        from telephone.deepgram import Speaking

        voice = Speaking()
        voice.ws = _FakeVoiceSocket()

        async def pieces(*words):
            for w in words:
                yield w

        heard = []

        async def on_audio(pcm):
            heard.append(pcm)

        # Primo turno: parla.
        first = await voice.speak(pieces("Buongiorno."), on_audio=on_audio)
        assert first.bytes_out > 0
        heard.clear()

        # Qualcuno interrompe, e il giro che ascoltava muore lì: nessuno
        # legge la conferma. È esattamente quello che fa `_barge_in`.
        await voice.cancel()
        assert voice._awaiting_cleared, "non ci si ricorda di aspettare la conferma"

        # Secondo turno: DEVE parlare.
        second = await voice.speak(pieces("Domani alle dieci."), on_audio=on_audio)
        assert second.failed == "", f"la voce ha fallito: {second.failed}"
        assert second.bytes_out > 0, "dopo un'interruzione la voce resta muta"
        assert heard, "nessun audio è arrivato a chi lo versa sulla linea"
        # E quello che il fornitore aveva in canna prima dell'interruzione non
        # finisce nell'orecchio di nessuno.
        assert b"\x99\x99" not in b"".join(heard), "audio di prima dell'interruzione"

        #     IL CASO ESATTO DELLA TELEFONATA.
        # Là il giro annullato aveva già letto l'audio vecchio, e sul filo era
        # rimasta soltanto la conferma. Senza la correzione è quella a
        # diventare la risposta del turno dopo: il ciclo la legge, la scambia
        # per «ho finito», ed esce senza aver detto niente.
        voice.ws.waiting = [json.dumps({"type": "Cleared"})]
        voice._awaiting_cleared = True
        heard.clear()

        third = await voice.speak(pieces("Ci vediamo giovedì."), on_audio=on_audio)
        assert third.failed == "", f"la voce ha fallito: {third.failed}"
        assert third.bytes_out > 0, (
            "una conferma non letta è diventata la risposta del turno dopo"
        )
        assert heard, "dopo un'interruzione ORA è rimasta muta"

    _run(body())


def test_a_turn_with_no_audio_is_not_written_down_as_spoken():
    """
    §15: nel registro solo quello che qualcuno ha sentito.

    Nella stessa telefonata il documento conteneva «ORA ha detto: oggi è…» e
    la persona al telefono aveva sentito silenzio. Un verbale che attribuisce
    a ORA una frase mai uscita è peggio di un turno perso, perché è l'unica
    cosa che resta quando la telefonata è finita.
    """
    async def body():
        from telephone.bridge import RealtimeVoiceSession

        class _Mute(_FakeMouth):
            async def speak(self, text_chunks, *, on_audio):
                from telephone.providers import Spoke

                async for _ in text_chunks:
                    pass
                return Spoke()      # nessun `on_audio`, nessun errore

        async def send(frame):
            return None

        session = RealtimeVoiceSession(
            None, owner_id="u", session_ref="s", send=send,
            listening=_FakeEars(), speaking=_Mute(),
        )
        await session.open()
        await session._say_it("Oggi è domenica 13 settembre 2026.", 1)

        detto = [t for t in session.transcript if t["who"] == "ora"]
        assert not detto, f"annotata una frase mai uscita: {detto}"
        assert "tts_silent" in session.failures
        assert session.turns.where == "listening", "il turno non si è chiuso"
        await session.close()

    _run(body())


def test_what_is_written_for_a_screen_is_said_for_an_ear():
    """
    §18: stesso significato, altra forma.

    Al telefono la risposta di ORA viene letta ad alta voce, e allora si sente
    tutto quello che sullo schermo non si vedeva: «dalle 16:00 alle 17:00»
    detto com'è scritto suona come un annuncio di stazione, e le virgolette
    di un titolo non si pronunciano.
    """
    from telephone.spoken import for_the_ear

    said = for_the_ear(
        'Domani hai in programma l\'evento "QA ORA — latenza" '
        "dalle 16:00 alle 17:00."
    )
    assert "16:00" not in said and "17:00" not in said
    assert "dalle quattro alle cinque del pomeriggio" in said
    assert '"' not in said and "—" not in said
    # E quello che ORA ha detto c'è ancora: non si è tolto niente.
    assert "QA ORA" in said and "Domani" in said

    # Gli articoli delle ore: si sentono subito se sono sbagliati.
    assert "A mezzogiorno" in for_the_ear("Alle 12:00 ci vediamo.")
    assert "a mezzanotte" in for_the_ear("Chiude alle 00:00.")
    assert "all'una" in for_the_ear("Ci vediamo alle 13:00.")
    assert "alle le" not in for_the_ear("Ci vediamo dalle 16:00 alle 17:00.")

    # Due momenti diversi restano due momenti diversi.
    lunga = for_the_ear("La riunione è dalle 09:00 alle 18:30.")
    assert "di mattina" in lunga and "di sera" in lunga

    # Gli indirizzi web non si dettano, e la frase non resta monca.
    senza = for_the_ear("Puoi vederlo su https://esempio.it/x (è il tuo).")
    assert "http" not in senza
    assert not senza.rstrip(".").endswith("su")

    # Quello che esiste solo per essere letto se ne va.
    pulito = for_the_ear("**Ecco**:\n- primo\n- secondo")
    assert "*" not in pulito and "- " not in pulito
    assert "primo" in pulito and "secondo" in pulito

    # E una frase già parlabile non viene toccata.
    semplice = "Certo, ci penso io."
    assert for_the_ear(semplice) == semplice


def test_the_runtime_says_the_spoken_form_and_not_the_written_one():
    """
    §18: e la dice davvero, non la calcola e basta.

    La trasformazione sta fra la decisione e la voce: se il runtime mandasse
    al fornitore la frase scritta, tutto il resto non servirebbe a niente.
    """
    async def body():
        from telephone.bridge import RealtimeVoiceSession

        async def send(frame):
            return None

        mouth = _FakeMouth()
        session = RealtimeVoiceSession(
            None, owner_id="u", session_ref="s", send=send,
            listening=_FakeEars(), speaking=mouth,
        )
        await session.open()
        await session._say_it("Ci vediamo dalle 16:00 alle 17:00.", 1)

        detto = " ".join(mouth.said)
        assert "16:00" not in detto, f"al telefono è andata la frase scritta: {detto}"
        assert "quattro" in detto and "cinque" in detto
        await session.close()

    _run(body())


def test_the_core_is_told_it_will_be_heard_only_on_the_phone():
    """
    §18: e il core lo sa, ma solo quando è vero.

        CAMBIA LA FORMA, NON QUELLO CHE HA DECISO.

    La chiave sta in alto e da sola, come quella sui collegamenti: una regola
    in mezzo a trenta non è una regola. E non compare nell'app, dove una
    risposta si legge e un elenco puntato è la forma giusta.
    """
    import json

    from conversation_engine.ai_core.prompt import build_user_payload

    comune = dict(
        user_message="che giorno è oggi?",
        recent_turns=[], active_goal=None, context_facts=[],
        tools=[], observations=[],
    )

    scritto = json.loads(build_user_payload(**comune))
    assert "you_are_being_heard_not_read" not in scritto

    parlato = json.loads(build_user_payload(**comune, spoken_out_loud=True))
    regola = parlato.get("you_are_being_heard_not_read") or ""
    assert regola, "al telefono il core non sa di essere ascoltato"

    #     IN ALTO SI MISURA IN CARATTERI, NON IN POSIZIONI.
    #
    # Qui c'era un indice, e il giorno che il payload ha guadagnato un campo
    # — `today_weekday`, otto caratteri — la prova è caduta senza che niente
    # fosse peggiorato. Quello che conta è quanto testo il modello deve
    # attraversare prima di incontrare la regola: se è un pugno di caratteri
    # è in cima, se sono mille è sepolta.
    chiavi = list(parlato)
    dove = chiavi.index("you_are_being_heard_not_read")
    prima = sum(
        len(json.dumps(parlato[k], ensure_ascii=False)) for k in chiavi[:dove]
    )
    assert prima < 1200, f"la regola arriva dopo {prima} caratteri: è sepolta"

    # E dice che non cambia quello che ORA decide.
    for parola in ("mode", "tools", "authority"):
        assert parola in regola, f"non è detto che {parola} non cambia"


# ---------------------------------------------------------------------------
# Le regole che non si vedono
# ---------------------------------------------------------------------------

def test_the_runtime_does_not_know_any_provider_by_name():
    """
    §17: la logica del telefono non dipende da nessun fornitore.

    Si è già cambiato operatore telefonico due volte in due sprint, e ogni
    volta è costato un file solo. Qui si tiene la stessa proprietà per
    l'orecchio e per la bocca, prima di averne bisogno.
    """
    for name in ("bridge.py", "turn.py", "playback.py", "chunker.py"):
        code = _code_only((HERE / "telephone" / name).read_text(encoding="utf-8"))
        for provider in (
            "deepgram", "api.deepgram", "nova-3", "aura-2",
            "openai", "gemini", "elevenlabs", "whisper",
        ):
            if name == "bridge.py" and provider == "deepgram":
                # Il runtime sceglie un valore di partenza in un punto solo,
                # e lo fa dentro una `import` locale: è l'unica riga in cui
                # un nome di fornitore compare, ed è sostituibile da fuori.
                continue
            assert provider not in code.lower(), (
                f"telephone/{name} conosce un fornitore: {provider}"
            )

    # E i contratti esistono davvero.
    from telephone.providers import (
        StreamingSpeechInputProvider,
        StreamingSpeechOutputProvider,
    )

    assert hasattr(StreamingSpeechInputProvider, "hear")
    assert hasattr(StreamingSpeechOutputProvider, "cancel")


def test_the_output_provider_already_accepts_text_in_pieces():
    """
    §17: le interfacce reggono lo streaming del core prima che esista.

    Il core oggi risponde tutto insieme — misurato, fra la prima parola e
    l'ultima passano cinquanta millisecondi, e streammarlo guadagnerebbe un
    decimo di secondo su otto. Ma il giorno che cambierà modello, `speak`
    prende già un flusso: non si riscrive il runtime.
    """
    import inspect

    from telephone.deepgram import Speaking

    sig = inspect.signature(Speaking.speak)
    assert "text_chunks" in sig.parameters, (
        "la bocca prende una stringa: il giorno dello streaming si riscrive"
    )
    body = _code_only((HERE / "telephone" / "deepgram.py").read_text(encoding="utf-8"))
    assert "async for piece in text_chunks" in body


def test_the_warm_up_is_infrastructure_and_not_a_question():
    """
    §7: il risveglio durante lo squillo non entra nella conversazione.

    Misurato: il primo turno costa 5.479 ms e i successivi 1.510, perché il
    primo paga il tentativo su un account esaurito. Pagarlo mentre il telefono
    squilla vuol dire non pagarlo mai — ma non deve diventare una finta
    domanda dell'utente.
    """
    code = _code_only((HERE / "telephone" / "dossier.py").read_text(encoding="utf-8"))

    # Non passa dall'orchestratore e non scrive niente.
    for forbidden in (
        "AICoreOrchestrator", "a_turn_of_conversation", "insert_one",
        "update_one", "memories", "life_objects", "authority.grant",
    ):
        assert forbidden not in code, f"il preflight fa cognizione: {forbidden}"

    # Parla direttamente al gestore dei modelli, che è infrastruttura.
    assert "from llm.manager import get_manager" in code
    assert "wake_the_providers" in code


def test_no_cognitive_branch_for_the_phone():
    """
    §6: VOICE IS NOT A SEPARATE ASSISTANT.

    `origin="phone"` può influire su provenienza e forma. Non deve poter
    scegliere un altro cervello. Questa prova fallisce se qualcuno lo prova.
    """
    for name in ("bridge.py", "same_ora.py", "turn.py", "dossier.py"):
        code = _code_only((HERE / "telephone" / name).read_text(encoding="utf-8"))
        for branching in (
            "if origin ==", "if origin in", "PhoneAssistant", "TelephoneBrain",
            "PhoneLLM", "PhonePrompt", "PhoneMemory", "phone_prompt",
            "PHONE_SYSTEM", "fast_model",
        ):
            assert branching not in code, (
                f"telephone/{name} biforca la cognizione: {branching}"
            )

    same = _code_only((HERE / "telephone" / "same_ora.py").read_text(encoding="utf-8"))
    assert "AICoreOrchestrator" in same
    assert "orchestrator.message(" in same and "orchestrator.start(" in same


def test_a_gap_between_events_is_not_a_gap_in_speech():
    """
    §4: il difetto che la prima prova con voce vera ha trovato.

    C'era una scorciatoia — «1,6 secondi senza eventi, chiudi il turno» — e
    alla prima frase detta davvero ha chiuso su «Ciao, ora» mentre la persona
    stava dicendo «dimmi che giorno è oggi». Il trascrittore consegna i pezzi
    definitivi a gruppi: fra un gruppo e l'altro passano secondi in cui noi
    non sentiamo niente e la persona sta parlando benissimo.

    Chi sa se è calato il silenzio è chi guarda i tempi delle parole, non il
    nostro orologio.
    """
    from telephone.turn import TurnManager

    t = TurnManager()
    t.line_is_open()
    t.speech_started()
    t.final_piece("Ciao, ora")
    t.pause()
    # Tre secondi senza eventi: nella prova vera erano 3,2.
    t._last_voice = time.perf_counter() - 3.0
    assert not t.should_commit(), (
        "un buco fra gli eventi viene ancora preso per la fine della frase"
    )

    # E la rete sotto scatta solo su una frase che sta in piedi.
    t._last_voice = time.perf_counter() - 5.0
    assert not t.should_commit(), (
        "anche dopo cinque secondi si chiude una frase che continua"
    )

    t.final_piece("dimmi che giorno è oggi.")
    t._last_voice = time.perf_counter() - 5.0
    assert t.should_commit(), "la rete sotto non scatta mai"
