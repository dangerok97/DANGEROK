"""
Fra «ha finito» e «ORA parla» c'è un attimo in cui la parola non è di nessuno.

    L'ASSESTAMENTO COMINCIA DALL'EAGER, NON DALLA FINE.

«Ciao ORA» è un turno completo — è un saluto, e Flux ha ragione a chiuderlo.
Ma la persona quasi sempre continua, e al telefono si è sentito così: ORA
saluta con sei secondi di ritardo mentre chi ha chiamato sta già facendo la
domanda, e poi risponde anche a quella. Due risposte sopra una voce sola.

La cura non è aspettare di più dopo `EndOfTurn`: sarebbe pagare due volte lo
stesso silenzio. Fra `EagerEndOfTurn` e `EndOfTurn` Flux ha **già** aspettato,
e misurato su quattro turni veri ha aspettato 564, 7, 715 e 652 millisecondi.
Quel tempo si sconta; si aspetta solo quello che manca, e mai oltre un tetto —
se no il turno detto senza esitazioni pagherebbe per quello esitante.

    NIENTE PARTE DURANTE L'ASSESTAMENTO.

Nessun pensiero, nessuno strumento, nessuna scrittura, nessun audio. Per
questo non serve annullare niente quando la persona riprende: non c'era
niente da annullare. È la ragione per cui questa versione non tocca il core.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from tests._loop_harness import run as _run  # noqa: E402

HERE = Path(_BACKEND)


def _turni():
    from telephone.turn import TurnManager

    t = TurnManager(someone_else_decides_turns=True)
    t.line_is_open()
    return t


def _parla(t, testo="una frase"):
    t.speech_started()
    t.partial(testo)


def _chiude(t, testo, *, eager_prima_ms=None, confidence=0.95):
    """Chiude un turno, eventualmente con un eager arrivato prima."""
    if eager_prima_ms is not None:
        t.maybe_the_turn_is_over(confidence)
        if t._now is not None:
            # L'eager è arrivato tot millisecondi fa.
            t._now.provider_eager_eot_ms = t._ms() - eager_prima_ms
    t.the_turn_is_over(testo, confidence=confidence, trigger="model")


def _passa_il_residuo(t):
    if t._settled_at is not None:
        t._settled_at = time.perf_counter() - (t._residual_s + 0.05)


# ---------------------------------------------------------------------------
# A-C: la continuazione
# ---------------------------------------------------------------------------

def test_a_a_resume_inside_the_window_becomes_one_single_turn():
    """
    §27.A: «Ciao ORA» + ripresa dentro la finestra = un turno solo.

        NON STAVA COMINCIANDO UN'ALTRA FRASE: STAVA FINENDO QUESTA.
    """
    t = _turni()
    _parla(t, "Ciao ORA")
    _chiude(t, "Ciao ORA.", eager_prima_ms=600)
    assert t.floor == "SETTLING"
    assert not t.should_commit(), "è partito qualcosa durante l'assestamento"

    # La persona riprende: quello che aveva detto diventa l'inizio.
    t.speech_started()
    assert t.floor == "USER_HAS_FLOOR"
    assert not t.should_commit()
    assert t.resumed_before_anything_started == 1

    t.partial("che giorno è oggi")
    _chiude(t, "Che giorno è oggi?", eager_prima_ms=600)
    _passa_il_residuo(t)

    assert t.should_commit()
    detto = t.commit()
    assert detto == "Ciao ORA. Che giorno è oggi?", detto
    assert t.coalesced_turns == 1


def test_b_a_resume_after_the_window_is_a_turn_of_its_own():
    """
    §27.C: passata la finestra, una frase nuova è una frase nuova.

    Non si fondono due domande separate solo perché ORA era lenta: la finestra
    ha una fine, e dopo quella il turno è partito.
    """
    t = _turni()
    _parla(t, "Che giorno è oggi")
    _chiude(t, "Che giorno è oggi?", eager_prima_ms=600)
    _passa_il_residuo(t)
    assert t.should_commit()
    assert t.commit() == "Che giorno è oggi?"

    # Adesso ORA sta pensando: quello che arriva è un'altra battuta.
    assert t.floor == "ORA_PENDING"
    t.speech_started()
    assert t.coalesced_turns == 0, "fuso qualcosa dopo che il turno era partito"


def test_c_a_complete_question_pays_almost_nothing():
    """
    §27.D: una domanda netta non paga per un'esitazione altrui.

        IL TETTO ESISTE PER QUESTO.

    Misurato: il turno 2 del gate è andato da eager a finale in **sette**
    millisecondi. Con la sola formula avrebbe aspettato 893 ms — quasi un
    secondo aggiunto proprio dove non serviva.
    """
    from telephone.turn import (
        MAX_RESIDUAL_AFTER_END_MS, SETTLE_TARGET_FROM_EAGER_MS,
    )

    t = _turni()
    _parla(t, "Che giorno è oggi")
    _chiude(t, "Che giorno è oggi?", eager_prima_ms=7)
    aggiunto = t._now.settling_residual_ms

    senza_tetto = SETTLE_TARGET_FROM_EAGER_MS - 7
    assert senza_tetto > 800, "la premessa della prova non vale più"
    assert aggiunto == MAX_RESIDUAL_AFTER_END_MS
    assert aggiunto <= 300, f"aggiunti {aggiunto} ms a un turno netto"


def test_the_silence_flux_already_waited_is_discounted():
    """
    §27.2: il silenzio già passato non si paga due volte.

    Sono i quattro turni veri del reality gate, con i loro delta.
    """
    from telephone.turn import (
        MAX_RESIDUAL_AFTER_END_MS, SETTLE_TARGET_FROM_EAGER_MS,
    )

    residui = []
    for delta in (564, 7, 715, 652):
        t = _turni()
        _parla(t)
        _chiude(t, "una frase intera", eager_prima_ms=delta)
        residui.append(t._now.settling_residual_ms)
        assert t._now.settling_already_elapsed_ms == delta
        assert t._now.settling_target_ms == SETTLE_TARGET_FROM_EAGER_MS

    atteso = [
        min(max(0, SETTLE_TARGET_FROM_EAGER_MS - d), MAX_RESIDUAL_AFTER_END_MS)
        for d in (564, 7, 715, 652)
    ]
    assert residui == atteso, residui
    mediana = sorted(residui)[len(residui) // 2]
    assert mediana <= 300, f"mediana aggiunta {mediana} ms"


def test_g_without_an_eager_there_is_a_prudent_fallback():
    """
    §27.G: se l'eager non arriva, non c'è niente da scontare.

    Succede su un turno chiuso a scadenza, o con Nova-3 che l'eager non ce
    l'ha proprio. Si aspetta il tetto e basta.
    """
    from telephone.turn import SETTLE_WITHOUT_EAGER_MS

    t = _turni()
    _parla(t)
    t.the_turn_is_over("una frase", confidence=0.9, trigger="timeout")
    assert t._now.settling_residual_ms == SETTLE_WITHOUT_EAGER_MS
    assert t._now.settling_already_elapsed_ms == 0
    assert not t.should_commit()
    _passa_il_residuo(t)
    assert t.should_commit()


# ---------------------------------------------------------------------------
# E-F: quello che Flux ci dice da solo
# ---------------------------------------------------------------------------

def test_e_a_resumed_turn_never_starts_anything():
    """
    §27.E: `TurnResumed` è Flux che dice «non aveva finito».

    È il caso migliore: non serve nessuna finestra, perché il turno non è mai
    stato chiuso.
    """
    t = _turni()
    _parla(t, "Domani devo andare")
    t.maybe_the_turn_is_over(0.7)
    assert not t.should_commit()

    t.the_turn_resumed()
    assert t.floor == "USER_HAS_FLOOR"
    assert not t.should_commit()

    t.partial("Domani devo andare dal dentista")
    _chiude(t, "Domani devo andare dal dentista.", eager_prima_ms=650)
    _passa_il_residuo(t)
    assert t.commit() == "Domani devo andare dal dentista."
    assert t.coalesced_turns == 0, "una ripresa di Flux non è una fusione nostra"


# ---------------------------------------------------------------------------
# H: dopo il primo audio non si fonde più niente
# ---------------------------------------------------------------------------

def test_h_the_floor_is_ora_only_when_a_frame_has_really_left():
    """
    §27.6: ORA ha la parola quando un frame è uscito sul filo.

        NON QUANDO LA DECISIONE È PRONTA, NON QUANDO L'AUDIO È IN CODA.

    Prima di quello nessuno ha sentito niente, e un nuovo intervento non sta
    interrompendo: sta parlando in un silenzio.
    """
    t = _turni()
    _parla(t)
    _chiude(t, "una domanda", eager_prima_ms=600)
    _passa_il_residuo(t)
    t.commit()
    assert t.floor == "ORA_PENDING"

    t.ora_asked()
    t.ora_decided()
    t.tts_asked()
    assert t.floor == "ORA_PENDING", "il floor preso senza aver detto niente"

    t.tts_answered()
    t.ora_started_speaking()
    assert t.floor == "ORA_PENDING", "il floor preso con l'audio ancora in coda"

    t.ora_took_the_floor()
    assert t.floor == "ORA_HAS_FLOOR"


def test_h_speaking_over_ora_after_first_audio_is_an_interruption():
    """§27.H: dopo il primo audio è barge-in, non continuazione."""
    t = _turni()
    _parla(t)
    _chiude(t, "una domanda", eager_prima_ms=600)
    _passa_il_residuo(t)
    t.commit()
    t.ora_started_speaking()
    t.ora_took_the_floor()

    assert t.speech_started() is True, "non riconosciuta come interruzione"
    assert t.floor == "INTERRUPTING"
    assert t.coalesced_turns == 0


# ---------------------------------------------------------------------------
# I-J: quello che non deve cambiare
# ---------------------------------------------------------------------------

def test_j_nova3_is_untouched():
    """
    §27.J: senza chi decide i turni, non c'è nessun assestamento.

    Nova-3 non manda eager e non manda `EndOfTurn`: il suo giro è quello di
    prima, e questa finestra non lo sfiora.
    """
    from telephone.turn import TurnManager

    t = TurnManager(someone_else_decides_turns=False)
    t.line_is_open()
    t.speech_started()
    t.final_piece("che giorno è oggi")
    t.utterance_end()
    # Nessuna attesa: commit immediato, come è sempre stato.
    assert t.should_commit()
    assert t.commit() == "che giorno è oggi"


def test_i_twenty_turns_leave_nothing_behind():
    """§27.I: venti turni, nessun compito e nessuna frase appesa."""
    async def body():
        t = _turni()
        prima = len(asyncio.all_tasks())
        for i in range(20):
            _parla(t, f"domanda {i}")
            _chiude(t, f"Domanda numero {i}?", eager_prima_ms=600)
            _passa_il_residuo(t)
            assert t.should_commit()
            assert t.commit() == f"Domanda numero {i}?"
            t.ora_started_speaking()
            t.ora_took_the_floor()
            t.ora_finished_speaking()
            await asyncio.sleep(0)

        assert len(asyncio.all_tasks()) <= prima + 1
        assert t._unfinished_after_all == ""
        assert t._settled is None
        assert len(t.timings) == 20

    _run(body())


def test_the_numbers_separate_our_waiting_from_flux_waiting():
    """
    §27.7: si deve poter distinguere la nostra attesa da quella di Flux.

        SE NO, «I TURNI SONO PIÙ BELLI» E «LE RISPOSTE SONO PIÙ LENTE»
        SAREBBERO LA STESSA RIGA DI LOG.
    """
    t = _turni()
    _parla(t)
    _chiude(t, "una frase", eager_prima_ms=600)
    _passa_il_residuo(t)
    t.commit()
    t.ora_finished_speaking()

    numeri = t.how_it_went()
    for chiave in (
        "floor", "settle_target_from_eager_ms", "max_residual_after_end_ms",
        "pre_response_resume_count", "coalesced_turn_count",
        "duplicate_response_prevented_count",
    ):
        assert chiave in numeri, f"manca {chiave}"

    tempi = numeri["each_turn"][0]
    for chiave in (
        "settling_target_ms", "settling_already_elapsed_ms",
        "settling_residual_ms", "extra_latency_added_by_floor_ms",
    ):
        assert chiave in tempi, f"manca {chiave}"
    assert tempi["extra_latency_added_by_floor_ms"] == tempi["settling_residual_ms"]

    # E nessuno di questi numeri porta una parola di quello che si è detto.
    assert "frase" not in json.dumps(numeri, ensure_ascii=False)


def test_nothing_is_started_during_settling():
    """
    §27: l'invariante che rende superfluo il fence.

        NIENTE PARTE DURANTE L'ASSESTAMENTO, QUINDI NIENTE VA ANNULLATO.

    `should_commit` è l'unica porta verso il core: finché risponde di no, non
    esiste nessun percorso che chiami `a_turn_of_conversation`, esegua uno
    strumento o scriva qualcosa.
    """
    import ast as _ast

    bridge = (HERE / "telephone" / "bridge.py").read_text(encoding="utf-8")
    albero = _ast.parse(bridge)

    # Chi chiama il core lo fa da un solo posto, e solo dopo un commit.
    guardia = [
        n for n in _ast.walk(albero)
        if isinstance(n, _ast.Call)
        and getattr(n.func, "attr", "") == "should_commit"
    ]
    assert len(guardia) == 1, "il commit si decide in più di un posto"

    sorgente = _ast.unparse(albero)
    dove = sorgente.index("should_commit")
    dopo = sorgente[dove:dove + 400]
    assert "commit()" in dopo, "si commette senza aver chiesto se si può"
