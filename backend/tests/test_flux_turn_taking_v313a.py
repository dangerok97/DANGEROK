"""
Quando i turni li decide chi ascolta, e non un cronometro.

    UNA RETE CHE SI TENDE PRIMA DEL TRAPEZISTA NON È UNA RETE.

Nova-3 dice quando c'è suono e quando c'è silenzio; chi lo riceve deve
indovinare se la frase è finita. Misurato su voce vera, indovina male: su
«Ciao ORA, dimmi che giorno è oggi» il turno si chiudeva dopo il vocativo, e
una persona al telefono ha dovuto ripetere la domanda.

Flux manda `EndOfTurn` quando un modello ha deciso che qualcuno ha finito di
parlare, e porta la frase intera. Questo file verifica che gli si dia retta —
e che i nostri timer restino dietro di lui invece di rubargli il lavoro.

Misurato durante questo sprint, sulla stessa frase italiana detta da una voce
vera, con pacchetti da ottanta millisecondi:

    «Ciao ORA, che giorno è oggi?»   0,80 e 0,90 → DUE turni
                                    0,95 → un turno, 614 ms
    «Che giorno è oggi?»            0,95 → un turno, 175 ms
    qualunque frase                 1,00 → nessun turno: solo a scadenza
"""

from __future__ import annotations

import ast
import asyncio
import json
import os
import sys
from pathlib import Path

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from tests._loop_harness import run as _run  # noqa: E402

HERE = Path(_BACKEND)


def _il_tempo_passa(t):
    """La finestra di assestamento si chiude: si sposta indietro l'orologio."""
    import time

    if t._settled_at is not None:
        t._settled_at = time.perf_counter() - (t._residual_s + 0.05)


def _turni(*, decide_qualcun_altro=True):
    from telephone.turn import TurnManager

    t = TurnManager(someone_else_decides_turns=decide_qualcun_altro)
    t.line_is_open()
    return t


# ---------------------------------------------------------------------------
# 1-5: il turno lo decide Flux
# ---------------------------------------------------------------------------

def test_1_a_short_question_is_one_turn_committed_by_end_of_turn():
    """§26.1: «Che giorno è oggi?» — un turno solo, chiuso da `EndOfTurn`."""
    t = _turni()
    t.speech_started()
    t.partial("Che giorno")
    t.partial("Che giorno è oggi")
    assert not t.should_commit(), "committato prima che il turno fosse finito"

    t.the_turn_is_over(
        "Che giorno è oggi?", confidence=0.86, trigger="model", turn_index=0,
    )
    #     PRIMA C'È UN ATTIMO IN CUI LA PAROLA NON È DI NESSUNO.
    # Da §3.3b1: il turno è chiuso ma si lascia alla persona il tempo di
    # riprendere. Finché quella finestra è aperta non parte niente.
    assert t.floor == "SETTLING"
    assert not t.should_commit()

    _il_tempo_passa(t)
    assert t.should_commit()
    assert t.commit() == "Che giorno è oggi?"
    assert t.where == "thinking"


def test_2_a_pause_after_the_vocative_does_not_close_the_turn():
    """
    §26.2: «Ciao ORA… dimmi che giorno è oggi» resta un turno solo.

        È IL DIFETTO CHE HA FATTO RIPETERE LA DOMANDA A UNA PERSONA VERA.

    Finché non arriva `EndOfTurn`, una pausa è una pausa — per lunga che sia.
    """
    t = _turni()
    t.speech_started()
    t.partial("Ciao ORA")
    t.pause()               # se mai arrivasse: è un indizio, non una fine
    assert not t.should_commit(), "chiuso il turno sul vocativo"

    t.partial("Ciao ORA dimmi che giorno è oggi")
    assert not t.should_commit()

    t.the_turn_is_over("Ciao ORA. Dimmi che giorno è oggi.", confidence=0.85)
    _il_tempo_passa(t)
    assert t.should_commit()
    assert "giorno" in t.commit()


def test_3_a_resumed_turn_becomes_one_whole_sentence():
    """
    §26.3: «Domani devo andare…» + pausa + «…dal dentista» = un turno.

    Il sospetto di fine viene registrato, la ripresa lo cancella, e quello che
    si commette alla fine è la frase intera.
    """
    t = _turni()
    t.speech_started()
    t.partial("Domani devo andare")
    t.maybe_the_turn_is_over(0.62)
    assert not t.should_commit(), "un «forse» ha chiuso un turno"

    t.the_turn_resumed()
    assert not t.should_commit()
    assert t.where == "user_speaking"

    t.partial("Domani devo andare dal dentista")
    t.the_turn_is_over("Domani devo andare dal dentista.", confidence=0.88)
    _il_tempo_passa(t)
    assert t.should_commit()
    assert t.commit() == "Domani devo andare dal dentista."


def test_4_our_timers_never_get_there_first():
    """
    §26.4: durante una chiamata sana nessun timer nostro anticipa Flux.

    La rete sta a nove secondi perché Flux chiude comunque a cinque: se la
    nostra scattasse prima, non lo coprirebbe — gli ruberebbe il lavoro.
    """
    import time

    from telephone.turn import (
        SILENCE_NET_MS, SILENCE_NET_WHEN_SOMEONE_ELSE_DECIDES_MS,
    )
    from telephone.deepgram import FLUX_EOT_TIMEOUT_MS

    assert SILENCE_NET_WHEN_SOMEONE_ELSE_DECIDES_MS > FLUX_EOT_TIMEOUT_MS, (
        "la nostra rete scatta prima di quella del fornitore"
    )
    assert SILENCE_NET_WHEN_SOMEONE_ELSE_DECIDES_MS > SILENCE_NET_MS

    t = _turni()
    t.speech_started()
    t.partial("una frase che sta benissimo in piedi da sola")
    # Sei secondi di silenzio: oltre la vecchia rete, dentro quella nuova.
    t._last_voice = time.perf_counter() - 6.0
    assert not t.should_commit(), "la rete ha anticipato chi decide i turni"

    # E `UtteranceEnd`, che è un segnale di un altro fornitore, non conta.
    t.utterance_end()
    assert not t.should_commit(), "si è dato retta a un segnale di Nova-3"


def test_5_if_the_provider_says_nothing_the_safety_net_catches_the_turn():
    """
    §26.5: se `EndOfTurn` non arriva mai, la rete recupera il turno.

    È un guasto, non un ritmo: per questo la soglia è lunga e la frase deve
    comunque stare in piedi da sola.
    """
    import time

    from telephone.turn import SILENCE_NET_WHEN_SOMEONE_ELSE_DECIDES_MS

    t = _turni()
    t.speech_started()
    t.final_piece("che impegni ho domani")
    t._last_voice = time.perf_counter() - (
        SILENCE_NET_WHEN_SOMEONE_ELSE_DECIDES_MS / 1000 + 0.5
    )
    assert t.should_commit(), "nessuno ha raccolto il turno"
    assert t.commit() == "che impegni ho domani"


# ---------------------------------------------------------------------------
# 6-9: il giro intero
# ---------------------------------------------------------------------------

class _OrecchioFinto:
    """Chi ascolta, con una scaletta di eventi e la stessa forma di Flux."""

    name = "finto"
    connect_ms = 1
    decides_turns = True

    def __init__(self, scaletta=None):
        self.scaletta = list(scaletta or [])
        self.udito = []
        self.closed = False
        self._coda = asyncio.Queue()

    def is_available(self):
        return True

    async def open(self):
        for e in self.scaletta:
            await self._coda.put(e)
        return True

    async def hear(self, pcm):
        self.udito.append(len(pcm))

    async def events(self):
        while True:
            yield await self._coda.get()

    async def di(self, heard):
        await self._coda.put(heard)

    async def close(self):
        self.closed = True


class _BoccaFinta:
    name = "finta"
    connect_ms = 1

    def __init__(self):
        self.said = []
        self.cancelled = 0
        self.closed = False

    def is_available(self):
        return True

    async def open(self):
        return True

    async def speak(self, text_chunks, *, on_audio):
        from telephone.providers import Spoke

        out = Spoke()
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


def _sessione(orecchio, bocca, risposte=None):
    """Una sessione vera, con un core finto che risponde quello che gli si dice."""
    import telephone.same_ora as same_ora
    from telephone.bridge import RealtimeVoiceSession

    detto = list(risposte or ["Va bene."])

    async def core(db, *, owner_id, session_id, words, origin="phone"):
        return {
            "mode": "answer",
            "ora_text": detto.pop(0) if detto else "Va bene.",
            "session_id": "s",
        }

    vero = same_ora.a_turn_of_conversation
    same_ora.a_turn_of_conversation = core

    async def send(frame):
        await asyncio.sleep(0)

    sess = RealtimeVoiceSession(
        None, owner_id="u", session_ref="s", send=send,
        listening=orecchio, speaking=bocca,
    )
    return sess, (lambda: setattr(same_ora, "a_turn_of_conversation", vero))


async def _aspetta(condizione, limite=6.0):
    import time

    t = time.perf_counter()
    while time.perf_counter() - t < limite:
        if condizione():
            return True
        await asyncio.sleep(0.02)
    return False


def test_6_and_7_consecutive_turns_all_go_through():
    """§26.6-7: due turni, e poi cinque, tutti risposti."""
    async def body():
        from telephone.providers import Heard

        orecchio, bocca = _OrecchioFinto(), _BoccaFinta()
        sess, ripristina = _sessione(
            orecchio, bocca, [f"Risposta {i}" for i in range(1, 6)],
        )
        try:
            assert await sess.open()
            for i in range(5):
                await orecchio.di(Heard("speech_started", turn_index=i))
                await orecchio.di(Heard("partial", f"domanda {i}", turn_index=i))
                await orecchio.di(Heard(
                    "end_of_turn", f"Domanda numero {i}?", confidence=0.85,
                    trigger="model", turn_index=i,
                ))
                assert await _aspetta(
                    lambda n=i: len([t for t in sess.transcript
                                     if t["who"] == "ora"]) > n
                ), f"il turno {i} non ha prodotto risposta"

            detti = [t["said"] for t in sess.transcript if t["who"] == "them"]
            assert detti == [f"Domanda numero {i}?" for i in range(5)]
            numeri = sess.how_it_went()
            assert numeri["turns"] >= 5
            assert numeri["who_decides_turns"] == "provider"
        finally:
            ripristina()
            await sess.close()

    _run(body())


def test_8_barge_in_still_works_with_flux():
    """
    §26.8: l'interruzione non regredisce.

    Con Flux non arriva più un segnale di solo suono, e va benissimo: il
    barge-in chiedeva già delle **parole**, e parole non nostre.
    """
    async def body():
        from telephone.providers import Heard

        orecchio, bocca = _OrecchioFinto(), _BoccaFinta()
        sess, ripristina = _sessione(orecchio, bocca, ["Ecco, allora, " * 40])
        try:
            assert await sess.open()
            await orecchio.di(Heard("speech_started"))
            await orecchio.di(Heard(
                "end_of_turn", "Raccontami la settimana.", confidence=0.9,
            ))
            assert await _aspetta(lambda: sess.turns.where == "ora_speaking")

            sess._talking_since -= 3     # ORA parla da abbastanza
            await sess._one_fact(Heard("partial", "aspetta un momento"))

            assert bocca.cancelled == 1, "alla voce non è stato detto di smettere"
            assert sess.playback.current.cancelled
            assert sess.turns.interruptions == 1
        finally:
            ripristina()
            await sess.close()

    _run(body())


def test_9_closing_the_line_leaves_nothing_behind():
    """§26.9: chiusa la linea, nessun compito e nessun socket sopravvive."""
    async def body():
        from telephone.providers import Heard

        orecchio, bocca = _OrecchioFinto(), _BoccaFinta()
        sess, ripristina = _sessione(orecchio, bocca)
        try:
            prima = len(asyncio.all_tasks())
            assert await sess.open()
            await orecchio.di(Heard("speech_started"))
            await orecchio.di(Heard("partial", "a metà di una frase"))
            await asyncio.sleep(0.1)
            await sess.close()
            await asyncio.sleep(0)

            assert sess._pump is None and sess._ticker is None
            assert orecchio.closed and bocca.closed
            assert len(asyncio.all_tasks()) <= prima + 1
        finally:
            ripristina()

    _run(body())


# ---------------------------------------------------------------------------
# 10-14: la configurazione, l'audio, e quello che non cambia
# ---------------------------------------------------------------------------

def test_10_the_flag_defaults_to_the_old_ear():
    """§26.10: senza dire niente, resta Nova-3. Il default è prudente."""
    from telephone.deepgram import Listening, the_ear

    prima = os.environ.pop("ORA_VOICE_STT", None)
    try:
        assert isinstance(the_ear(), Listening)
        for altro in ("nova3", "NOVA3", "", "qualsiasi cosa"):
            os.environ["ORA_VOICE_STT"] = altro
            assert isinstance(the_ear(), Listening), altro
    finally:
        os.environ.pop("ORA_VOICE_STT", None)
        if prima is not None:
            os.environ["ORA_VOICE_STT"] = prima


def test_11_the_flag_switches_to_flux_and_the_address_is_right():
    """
    §26.11: con `flux` si va su `/v2/listen` e sul modello multilingue.

    E la soglia è 0,8, non il default di Deepgram: a 0,7, misurato, una frase
    italiana che comincia con un vocativo viene tagliata in due.
    """
    from telephone.deepgram import FLUX_EOT_THRESHOLD, FluxListening, the_ear

    prima = os.environ.get("ORA_VOICE_STT")
    try:
        os.environ["ORA_VOICE_STT"] = "flux"
        orecchio = the_ear()
        assert isinstance(orecchio, FluxListening)
        assert orecchio.decides_turns is True

        url = orecchio._url()
        assert "/v2/listen?" in url
        assert "model=flux-general-multi" in url
        assert "language_hint=it" in url
        assert "encoding=linear16" in url
        assert "sample_rate=16000" in url
        assert f"eot_threshold={FLUX_EOT_THRESHOLD}" in url
        # Misurato: 0,8 e 0,9 spezzano «Ciao ORA, che giorno è oggi?»;
        # 0,95 la tiene intera e chiude una domanda diretta in 175 ms.
        assert FLUX_EOT_THRESHOLD == 0.95
        # L'eager si accende per essere misurato, e non può superare la
        # soglia vera.
        assert "eager_eot_threshold=" in url
    finally:
        os.environ.pop("ORA_VOICE_STT", None)
        if prima is not None:
            os.environ["ORA_VOICE_STT"] = prima


def test_12_audio_is_grouped_not_kept():
    """
    §26.12: i pacchetti si raggruppano a ottanta millisecondi e non restano.

        MISURATO: 1.252 ms CONTRO 786 ms.

    Stessa frase, `EndOfTurn` a 1.252 millisecondi dalla fine del parlato
    mandando venti millisecondi alla volta, e a 786 mandandone ottanta. Il
    gruppo in composizione è l'unico audio che esiste, e dura al massimo
    sessanta millisecondi.
    """
    async def body():
        from telephone.deepgram import FLUX_CHUNK_MS, FluxListening

        orecchio = FluxListening()
        mandati = []

        class _Filo:
            async def send(self, dati):
                mandati.append(dati)

        orecchio.ws = _Filo()
        venti = b"\x01\x02" * 320      # 20 ms a 16 kHz

        for _ in range(3):
            await orecchio.hear(venti)
        assert mandati == [], "mandato un gruppo incompleto"
        assert len(orecchio._holding) == 3 * len(venti)

        await orecchio.hear(venti)
        assert len(mandati) == 1, "il quarto pacchetto non ha chiuso il gruppo"
        assert len(mandati[0]) == int(16000 * FLUX_CHUNK_MS / 1000) * 2
        assert orecchio._holding == b"", "l'audio è rimasto in mano"

        await orecchio.close()
        assert orecchio._holding == b""

    _run(body())


def test_13_no_raw_audio_is_ever_kept():
    """
    §26.13: dell'audio non resta niente, nemmeno adesso che si raggruppa.

    Il gruppo in composizione è l'unica eccezione, ed è dichiarata: si svuota
    a ogni invio e alla chiusura.
    """
    codice = (HERE / "telephone" / "deepgram.py").read_text(encoding="utf-8")
    albero = ast.parse(codice)

    #     SI CERCANO LE CHIAMATE, NON LE PAROLE.
    # Una guardia che cerca «open(» dentro il testo trova anche
    # `async def open(self)`, che è il nome di un metodo nostro: fallirebbe
    # per una ragione che non c'entra niente con l'audio.
    aperture = [
        n.func.id for n in ast.walk(albero)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id in ("open", "bytearray_to_file")
    ]
    assert not aperture, f"si aprono file: {aperture}"

    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Expr) and isinstance(nodo.value, ast.Constant):
            nodo.value.value = ""
    solo_codice = ast.unparse(albero)

    for conservare in ("wave", "BytesIO", "base64", "aiofiles"):
        assert conservare not in solo_codice, f"l'audio viene conservato: {conservare}"

    # E l'unico accumulo dichiarato si svuota in due punti.
    assert solo_codice.count("_holding.clear()") >= 1
    # Il gruppo si consuma man mano che se ne va: `del` sulla fetta mandata.
    assert "delself._holding[" in solo_codice.replace(" ", "")


def test_14_same_ora_gets_the_same_words_whoever_listens():
    """
    §26.14: SAME ORA — dopo il commit, il core riceve la stessa cosa.

        CAMBIA CHI ASCOLTA, NON CHI PENSA.

    Nova-3 consegna pezzi che si accumulano, Flux consegna la frase intera.
    Quello che entra nel Conversation Engine è la stessa identica stringa, con
    la stessa provenienza.
    """
    async def body():
        import telephone.same_ora as same_ora
        from telephone.bridge import RealtimeVoiceSession
        from telephone.providers import Heard

        arrivato = []

        async def core(db, *, owner_id, session_id, words, origin="phone"):
            arrivato.append({"words": words, "origin": origin})
            return {"mode": "answer", "ora_text": "ok", "session_id": "s"}

        vero = same_ora.a_turn_of_conversation
        same_ora.a_turn_of_conversation = core

        async def send(frame):
            await asyncio.sleep(0)

        try:
            # Con chi decide i turni: la frase arriva intera.
            flux = _OrecchioFinto()
            s1 = RealtimeVoiceSession(
                None, owner_id="u", session_ref="s", send=send,
                listening=flux, speaking=_BoccaFinta(),
            )
            await s1.open()
            await flux.di(Heard("speech_started"))
            await flux.di(Heard("end_of_turn", "Che giorno è oggi?", confidence=0.9))
            assert await _aspetta(lambda: len(arrivato) == 1)
            await s1.close()

            # Con chi non li decide: gli stessi pezzi si accumulano.
            nova = _OrecchioFinto()
            nova.decides_turns = False
            s2 = RealtimeVoiceSession(
                None, owner_id="u", session_ref="s", send=send,
                listening=nova, speaking=_BoccaFinta(),
            )
            await s2.open()
            await nova.di(Heard("speech_started"))
            await nova.di(Heard("final", "Che giorno è oggi?"))
            await nova.di(Heard("utterance_end"))
            assert await _aspetta(lambda: len(arrivato) == 2)
            await s2.close()

            assert arrivato[0]["words"] == arrivato[1]["words"] == "Che giorno è oggi?"
            assert arrivato[0]["origin"] == arrivato[1]["origin"] == "phone"
        finally:
            same_ora.a_turn_of_conversation = vero

    _run(body())


def test_the_metrics_can_prove_the_gain():
    """
    §26.15: i numeri che servono a dimostrare il guadagno esistono.

    «Sembra più veloce» non è una misura. Questi campi lo sono.
    """
    from telephone.turn import Timing

    t = Timing(
        user_speech_start_ms=0, user_last_voice_ms=1000,
        provider_eager_eot_ms=1500, provider_end_of_turn_ms=1800,
        turn_committed_ms=1830, ora_first_token_ms=4200,
        tts_first_audio_ms=4400, playback_first_chunk_ms=4400,
        eot_confidence=0.85, eot_trigger="model", provider_turn_index=0,
    )
    d = t.as_dict()
    assert d["end_of_speech_to_provider_eot_ms"] == 800
    assert d["provider_eot_to_commit_ms"] == 30
    assert d["eager_to_final_eot_ms"] == 300
    assert d["end_of_speech_to_commit_ms"] == 830
    assert d["end_of_speech_to_first_audio_ms"] == 3400
    assert d["eot_confidence"] == 0.85 and d["eot_trigger"] == "model"

    # E nessuno di questi campi contiene una parola di quello che si è detto.
    assert "text" not in json.dumps(d).lower()
