"""
Il runtime a missione, guidato a mano, senza chiamare nessuno.

    UNA PROVA CHE HA BISOGNO DI GOOGLE NON È UNA PROVA: È UN AUGURIO.

Il filo verso chi parla è iniettabile, quindi qui dentro c'è un filo finto che
dice esattamente quello che vogliamo che dica — compreso quello che nessun
modello ben educato direbbe mai, che è precisamente ciò che va provato.

Si verifica quello che il runtime deve garantire **da solo**, senza contare
sulla buona volontà di chi parla:

    l'elenco degli strumenti è chiuso;
    un dato non previsto non esce;
    la disponibilità non chiude la missione;
    l'audio passa e non resta;
    e quando si chiude, non resta niente aperto.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# --- un filo che facciamo parlare noi --------------------------------------

class FakeWire:
    """Il socket verso chi parla, senza chi parla."""

    def __init__(self) -> None:
        self.sent = []
        self.closed = False
        self._in: asyncio.Queue = asyncio.Queue()

    async def send(self, text: str) -> None:
        self.sent.append(json.loads(text))

    async def recv(self):
        return await self._in.get()

    async def close(self) -> None:
        self.closed = True

    # --- quello che diciamo noi che il modello abbia detto -----------------

    async def says(self, message: dict) -> None:
        await self._in.put(json.dumps(message))
        for _ in range(4):
            await asyncio.sleep(0)
        await asyncio.sleep(0.03)

    def what_it_sent(self, key: str):
        return [m for m in self.sent if key in m]


class FakeUsers:
    def __init__(self, profilo=None):
        self._profilo = profilo or {}

    async def find_one(self, _query):
        return dict(self._profilo)


class FakeDb:
    def __init__(self, profilo=None):
        self.users = FakeUsers(profilo)


def _packet():
    from telephone.introduction import introduction_for
    from telephone.mission import CallMissionPacket, MissionFact

    p = CallMissionPacket(
        mission_id="mis_prova",
        mission_type="reschedule",
        goal="Spostare l'appuntamento di oggi dalle 16:00 alle 18:00",
        counterparty="Studio Dentistico Bianchi",
        on_behalf_of="Francesco Cefalà",
        local_datetime="2026-09-14T09:00:00+02:00",
        timezone="Europe/Rome",
        subject="appuntamento dal dentista di oggi",
        current_state={"when": "2026-09-14T16:00:00+02:00"},
        desired_state={"when": "2026-09-14T18:00:00+02:00"},
        allowed_negotiation=["confermare le 18:00 di oggi"],
        known_facts=[MissionFact(
            field="nome_paziente", value="Francesco Cefalà",
            sensitivity="identity", why_it_is_here="serve per trovarla",
        )],
        allowed_on_demand_fields=["data_di_nascita"],
    )
    p.introduction = introduction_for(p)
    p.say_this_first = p.introduction.opening_line()
    return p


async def _aperta(monkeypatch, profilo=None):
    """Una sessione aperta su un filo finto, con l'audio raccolto in una lista."""
    from telephone.live import MissionVoiceSession

    monkeypatch.setenv("GEMINI2_API_KEY", "non-una-chiave-vera")
    monkeypatch.setenv("GEMINI_LIVE_MODEL", "un-modello-di-prova")

    wire = FakeWire()
    alla_linea = []

    async def send(pcm: bytes) -> None:
        alla_linea.append(pcm)

    detto = []

    async def on_said(chi, parole):
        detto.append((chi, parole))

    sess = MissionVoiceSession(
        FakeDb(profilo), owner_id="u1", session_ref="s1",
        send=send, on_said=on_said, packet=_packet(),
        connect=lambda: _subito(wire),
    )
    aperta = asyncio.create_task(sess.open())
    await asyncio.sleep(0)
    await wire._in.put(json.dumps({"setupComplete": {}}))
    assert await aperta is True
    return sess, wire, alla_linea, detto


async def _subito(wire):
    return wire


def _tool(nome, argomenti, id_="t1"):
    return {"toolCall": {"functionCalls": [
        {"id": id_, "name": nome, "args": argomenti},
    ]}}


def _risposta(wire):
    """L'ultima risposta a uno strumento mandata sul filo."""
    return wire.what_it_sent("toolResponse")[-1]["toolResponse"]["functionResponses"][0]["response"]


# ---------------------------------------------------------------------------
# Come si apre
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_session_opens_with_the_mission_and_six_tools(monkeypatch):
    """
    §7 / §10: una chiamata, una sessione, sei strumenti.

        ORA NE HA TRENTANOVE. QUI NE PASSANO SEI.
    """
    sess, wire, _, _ = await _aperta(monkeypatch)
    try:
        setup = wire.what_it_sent("setup")[0]["setup"]
        nomi = {
            f["name"] for f in setup["tools"][0]["function_declarations"]
        }
        assert nomi == {
            "get_call_context", "get_allowed_alternatives",
            "request_user_confirmation", "record_call_fact",
            "complete_mission", "fail_mission",
        }
        istruzioni = setup["systemInstruction"]["parts"][0]["text"]
        assert "say_this_first" in istruzioni
        assert "non sei quella persona" in istruzioni
        # §17: il prompt intero di ORA qui non entra. Diciottomila token
        # contro poco piu' di mille: la differenza si vede a occhio.
        assert len(istruzioni) < 6000, f"il contesto pesa {len(istruzioni)} caratteri"
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_the_key_never_travels_inside_the_session(monkeypatch):
    """
    §17: la chiave sta nell'indirizzo, non nei messaggi, e in nessun registro.
    """
    sess, wire, _, _ = await _aperta(monkeypatch)
    try:
        tutto = json.dumps(wire.sent, ensure_ascii=False)
        assert "non-una-chiave-vera" not in tutto
        assert "non-una-chiave-vera" not in json.dumps(sess.how_it_went(), default=str)
    finally:
        await sess.close()


# ---------------------------------------------------------------------------
# L'elenco chiuso
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_tool_outside_the_list_is_refused(monkeypatch):
    """
    §10: chi non è nell'elenco non entra, e non importa come si chiama.

    Il nome scelto qui è quello di uno strumento vero di ORA: se l'allowlist
    fosse aperta «per comodità», questo passerebbe e toccherebbe un calendario.
    """
    sess, wire, _, _ = await _aperta(monkeypatch)
    try:
        await wire.says(_tool("create_calendar_event", {"title": "x"}))
        assert _risposta(wire) == {"error": "strumento sconosciuto"}
        assert sess.how_it_went()["tool_refused"] == 1
    finally:
        await sess.close()


# ---------------------------------------------------------------------------
# Quello che non è previsto non esce
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_field_nobody_authorised_does_not_come_out(monkeypatch):
    """
    §17: il codice fiscale c'è nel profilo, e resta nel profilo.

        IL PACCHETTO PORTA IL NOME DEL CAMPO, MAI IL VALORE.
    """
    profilo = {"codice_fiscale": "CFLFNC90C12H501X", "birth_date": "1990-03-12"}
    sess, wire, _, _ = await _aperta(monkeypatch, profilo)
    try:
        await wire.says(_tool("get_call_context", {"field": "codice_fiscale"}))
        risposta = _risposta(wire)
        assert risposta["refused"] is True
        assert "CFLFNC90C12H501X" not in json.dumps(wire.sent, ensure_ascii=False)
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_a_field_the_mission_allowed_is_fetched_when_asked(monkeypatch):
    """§6 del PoC: la data di nascita era prevista, e si va a prenderla."""
    sess, wire, _, _ = await _aperta(monkeypatch, {"birth_date": "1990-03-12"})
    try:
        await wire.says(_tool("get_call_context", {"field": "data_di_nascita"}))
        assert _risposta(wire) == {"value": "1990-03-12"}
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_what_the_packet_already_knows_is_not_fetched_again(monkeypatch):
    """Il nome sta già nel pacchetto: non si va a cercarlo altrove."""
    sess, wire, _, _ = await _aperta(monkeypatch)
    try:
        await wire.says(_tool("get_call_context", {"field": "nome_paziente"}))
        assert _risposta(wire) == {"value": "Francesco Cefalà"}
    finally:
        await sess.close()


# ---------------------------------------------------------------------------
# Il gate di conferma, dentro il runtime vero
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_availability_does_not_close_the_mission_here_either(monkeypatch):
    """
    §9: il registro validato nel PoC è lo stesso che gira qui.

        «ALLE 18 ABBIAMO POSTO» NON È «L'HO SPOSTATO ALLE 18».
    """
    sess, wire, _, _ = await _aperta(monkeypatch)
    try:
        await wire.says(_tool("record_call_fact", {
            "kind": "availability", "value": "alle 18 c'è posto",
        }))
        await wire.says(_tool("complete_mission", {
            "confirmed_changes": {"appointment_date": "2026-09-14",
                                  "new_time": "18:00"},
            "confirmation": "alle 18 c'è posto",
        }))
        risposta = _risposta(wire)
        assert risposta["accepted"] is False
        # Nessuno ha ancora chiesto di *fare* lo spostamento: la domanda
        # giusta non è «me lo conferma?» ma «può procedere?».
        assert risposta["reason"] == "change_not_requested_yet"
        assert sess.outcome is None
        # E quello che la bocca dirà non nomina nessun sistema.
        assert "strumento" not in risposta["say"].lower()
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_a_confirmation_in_the_next_turn_closes_it(monkeypatch):
    """§9: e quando la conferma arriva davvero, si chiude al primo colpo."""
    sess, wire, _, _ = await _aperta(monkeypatch)
    try:
        await wire.says(_tool("record_call_fact", {
            "kind": "availability", "value": "alle 18 c'è posto",
        }))
        await wire.says({"serverContent": {"turnComplete": True}})   # tocca a loro
        await wire.says(_tool("complete_mission", {
            "confirmed_changes": {"appointment_date": "2026-09-14",
                                  "old_time": "16:00", "new_time": "18:00"},
            "confirmation": "fatto, l'ho spostato alle 18",
        }))
        assert _risposta(wire)["accepted"] is True
        assert sess.outcome is not None
        assert sess.outcome.status == "success"
        assert sess.outcome.is_actionable()
        assert sess.outcome.confirmed_changes["new_time"] == "18:00"
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_something_outside_the_mission_comes_back_to_a_person(monkeypatch):
    """
    §11: fuori dall'autorità non si decide, si chiede.

    E l'esito non è un successo più piccolo: `is_actionable()` è falso, quindi
    da qui non si muove niente nel mondo.
    """
    sess, wire, _, _ = await _aperta(monkeypatch)
    try:
        await wire.says(_tool("request_user_confirmation", {
            "reason": "propongono domani alle 11",
        }))
        assert _risposta(wire)["answer"] == "pending"
        assert sess.outcome.status == "needs_user"
        assert not sess.outcome.is_actionable()
        assert "domani alle 11" in sess.outcome.user_confirmation_needed
    finally:
        await sess.close()


# ---------------------------------------------------------------------------
# L'audio: passa e non resta
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_model_audio_reaches_the_line_at_the_line_rate(monkeypatch):
    """
    §6: ventiquattromila entrano, sedicimila escono, e in mezzo non si sente
    la giunta.
    """
    import base64

    import numpy as np

    sess, wire, alla_linea, _ = await _aperta(monkeypatch)
    try:
        t = np.arange(2400) / 24000
        onda = (np.sin(2 * np.pi * 440 * t) * 9000).astype("<i2").tobytes()
        for i in range(0, len(onda), 960):
            await wire.says({"serverContent": {"modelTurn": {"parts": [
                {"inlineData": {"data": base64.b64encode(onda[i:i + 960]).decode()}},
            ]}}})
        await wire.says({"serverContent": {"turnComplete": True}})
        await asyncio.sleep(0.25)

        uscito = b"".join(alla_linea)
        assert uscito, "niente è arrivato sulla linea"
        y = np.frombuffer(uscito, dtype="<i2").astype(float)
        # Nessun salto oltre la pendenza del seno stesso: se il filtro si
        # riazzerasse a ogni pacchetto, qui ci sarebbe una scalinata.
        assert np.abs(np.diff(y)).max() < 9000 * 2 * np.pi * 440 / 16000 * 1.6
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_nothing_that_passes_through_is_kept(monkeypatch):
    """
    §17: l'audio è un fiume, non un archivio.

    Quello che si racconta dopo sono testi, tempi e conteggi. Se un giorno
    qualcuno aggiungesse «il PCM, giusto per il debug», questa prova cade.
    """
    import base64

    sess, wire, _, detto = await _aperta(monkeypatch)
    try:
        finto = bytes(960)
        await wire.says({"serverContent": {"modelTurn": {"parts": [
            {"inlineData": {"data": base64.b64encode(finto).decode()}},
        ]}}})
        await wire.says({"serverContent": {
            "outputTranscription": {"text": "Buongiorno, sono l'assistente di Francesco."},
            "turnComplete": True,
        }})
        numeri = sess.how_it_went()
        for valore in numeri.values():
            assert not isinstance(valore, (bytes, bytearray)), numeri
        assert all(isinstance(p, str) for _, p in detto)
        assert "inlineData" not in json.dumps(numeri, default=str)
    finally:
        await sess.close()


# ---------------------------------------------------------------------------
# Interruzioni
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_being_interrupted_stops_the_mouth(monkeypatch):
    """
    §14.G: qualcuno parla sopra, e la frase non si finisce.

        CHI VIENE INTERROTTO TACE.
    """
    import base64

    sess, wire, alla_linea, _ = await _aperta(monkeypatch)
    try:
        lungo = bytes(24000 * 2)   # un secondo di voce da versare
        await wire.says({"serverContent": {"modelTurn": {"parts": [
            {"inlineData": {"data": base64.b64encode(lungo).decode()}},
        ]}}})
        await wire.says({"serverContent": {"interrupted": True}})
        quanto_era_uscito = len(b"".join(alla_linea))
        await asyncio.sleep(0.2)
        assert len(b"".join(alla_linea)) - quanto_era_uscito < 3200, (
            "ha continuato a parlare dopo essere stato interrotto"
        )
        assert sess.how_it_went()["barge_in_ms"], "l'interruzione non è stata misurata"
    finally:
        await sess.close()


# ---------------------------------------------------------------------------
# Quando si chiude
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_closing_leaves_nothing_open(monkeypatch):
    """
    §17: niente task appesi, niente socket aperti.

        UN SOCKET LASCIATO APERTO È UNA PORTA CHE QUALCUNO PUÒ TENERE.
    """
    prima = len(asyncio.all_tasks())
    sess, wire, _, _ = await _aperta(monkeypatch)
    await wire.says({"serverContent": {"turnComplete": True}})

    await sess.close()
    await asyncio.sleep(0.05)

    assert wire.closed, "il filo è rimasto aperto"
    assert sess.ws is None
    assert sess._pump is None
    assert len(asyncio.all_tasks()) <= prima + 1
    # E chiudere due volte non è un errore: succede quando la linea cade.
    await sess.close()


@pytest.mark.asyncio
async def test_a_call_that_drops_does_not_look_like_a_success(monkeypatch):
    """
    §12: se la linea cade prima di un esito, l'esito è «parziale».

    Non «riuscita», e nemmeno niente: niente vorrebbe dire che qualcuno più
    tardi debba indovinare com'è andata.
    """
    sess, wire, _, _ = await _aperta(monkeypatch)
    await sess.close()
    assert sess.outcome is not None
    assert sess.outcome.status == "partial"
    assert not sess.outcome.is_actionable()


# ---------------------------------------------------------------------------
# Il flag
# ---------------------------------------------------------------------------

def test_the_default_is_still_the_classic_runtime(monkeypatch):
    """§5: il valore di partenza non cambia, e non cambia per sbaglio."""
    from telephone.runtime import CLASSIC, which_runtime

    monkeypatch.delenv("ORA_VOICE_RUNTIME", raising=False)
    assert which_runtime() == CLASSIC
    monkeypatch.setenv("ORA_VOICE_RUNTIME", "qualcosa-di-strano")
    assert which_runtime() == CLASSIC
    monkeypatch.setenv("ORA_VOICE_RUNTIME", "gemini_live")
    assert which_runtime() == "gemini_live"


def test_a_flag_is_not_a_reason_to_drop_a_call(monkeypatch):
    """
    §5: se il runtime a missione non può aprirsi, risponde il classico.

    Manca la chiave, manca il modello, manca il mandato: la persona dall'altra
    parte non deve accorgersi di niente.
    """
    from telephone.bridge import RealtimeVoiceSession
    from telephone.runtime import the_voice_for

    monkeypatch.setenv("ORA_VOICE_RUNTIME", "gemini_live")
    monkeypatch.delenv("GEMINI2_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_LIVE_MODEL", raising=False)

    async def send(_pcm):
        return None

    voce = the_voice_for(
        FakeDb(), owner_id="u1", session_ref="s1", send=send,
        call=object(), dossier=object(),
    )
    assert isinstance(voce, RealtimeVoiceSession)


def test_the_classic_runtime_still_knows_nothing_about_missions():
    """
    §18: il classico non importa niente di tutto questo.

    `runtime.py` importa entrambi — è il suo mestiere — e `live.py` è il
    runtime nuovo. Nessun altro file di `telephone/` deve conoscerli.
    """
    import ast
    from pathlib import Path

    qui = Path(_BACKEND) / "telephone"
    #     IL LIVELLO CHE VIENE DOPO NON È UN TERZO RUNTIME.
    # `binding.py` lega la missione all'oggetto che dovrà cambiare e
    # `application.py` ne applica l'esito: leggere una missione è tutto
    # quello che fanno.
    suoi = {"mission.py", "live.py", "runtime.py", "introduction.py",
            "history.py", "binding.py", "application.py"}
    for path in sorted(qui.glob("*.py")):
        if path.name in suoi:
            continue
        albero = ast.parse(path.read_text(encoding="utf-8"))
        for nodo in ast.walk(albero):
            modulo = (
                nodo.module if isinstance(nodo, ast.ImportFrom) else None
            ) or ""
            if modulo.endswith(("mission", "live")):
                raise AssertionError(f"{path.name} importa {modulo}")


# ---------------------------------------------------------------------------
# Le tre cose che si sono viste solo telefonando davvero
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_line_does_not_run_dry_between_words():
    """
    La voce andava a tratti, «come se non ci fosse linea».

        UN RUBINETTO SENZA VASCA GOCCIOLA.

    Il rubinetto versava il primo pacchetto appena arrivava. Con Deepgram la
    frase arriva tutta insieme e la coda è piena dal primo istante; con Gemini
    Live l'audio nasce mentre lo si versa, e all'inizio di ogni risposta la
    coda resta a secco — sulla linea cade il silenzio in mezzo alle parole.

    Qui si simula proprio quello: pacchetti che arrivano a singhiozzo. Col
    cuscinetto la voce esce di fila; senza, esce a pezzi.
    """
    from telephone.playback import PlaybackController

    uscita = []

    async def send(frame):
        uscita.append(time.perf_counter())

    play = PlaybackController(send=send, jitter_ms=200)
    handle = play.begin(generation_id="g1", turn_id=1)

    async def a_singhiozzo():
        for _ in range(10):
            await play.feed(bytes(320 * 2), handle)   # 20 ms per volta
            await asyncio.sleep(0.045)                # più lento del parlato
        await play.finish(handle)

    await asyncio.wait_for(a_singhiozzo(), timeout=5)
    await asyncio.sleep(0.1)
    await play.close()

    assert play.cushions >= 1, "il cuscinetto non è mai entrato in funzione"
    assert len(uscita) >= 8, f"sono usciti solo {len(uscita)} pacchetti"
    # Senza cuscinetto la voce seguirebbe il ritmo di chi genera — quarantacinque
    # millisecondi — invece di quello del parlato. Si guarda la mediana e non il
    # buco peggiore: un singolo intervallo su una macchina carica dice quanto è
    # occupato il sistema operativo, la mediana dice se il cuscinetto ha retto.
    buchi = sorted((b - a) * 1000 for a, b in zip(uscita, uscita[1:]))
    mediana = buchi[len(buchi) // 2]
    assert mediana < 35, f"mediana {mediana:.0f} ms: segue chi genera, non il parlato"
    assert sum(1 for b in buchi if b > 44) <= 2, buchi


def test_the_classic_runtime_gets_no_cushion_and_pays_nothing():
    """
    §5: e il classico non paga per un problema che non ha.

    Duecento millisecondi di margine sono un'assicurazione per chi riceve la
    voce mentre nasce. A chi la riceve già fatta sarebbero ritardo regalato,
    e il classico è ancora la risposta giusta per la maggior parte delle
    telefonate.
    """
    from telephone.playback import PlaybackController

    async def send(_f):
        return None

    assert PlaybackController(send=send).jitter_ms == 0


@pytest.mark.asyncio
async def test_the_transcript_puts_the_question_before_the_answer(monkeypatch):
    """
    Nel registro la risposta stava sopra la frase a cui rispondeva.

    Rileggendo la prima telefonata vera sembrava che ORA avesse ringraziato
    *prima* che lo studio confermasse. Non era andata così — ma un registro
    che si legge al contrario è un registro che racconta una cosa diversa da
    quella successa, e qualcuno prima o poi ci crede.
    """
    sess, wire, _, detto = await _aperta(monkeypatch)
    try:
        await wire.says({"serverContent": {
            "inputTranscription": {"text": "Sì, alle 18 abbiamo posto."},
            "outputTranscription": {"text": "Mi conferma che è spostato?"},
            "turnComplete": True,
        }})
        assert [chi for chi, _ in detto] == ["them", "ora"]
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_a_failure_with_something_on_the_table_is_a_question(monkeypatch):
    """
    «Non si può fare» e «qualcuno deve decidere» non sono lo stesso esito.

        CHI HA LASCIATO UNA PORTA APERTA NON HA FALLITO: HA CHIESTO.

    Alla seconda telefonata vera lo studio ha proposto domani alle undici.
    La voce ha detto la cosa giusta — «devo sentire Francesco» — e poi ha
    chiuso dichiarando un fallimento. Ma un fallimento è una porta chiusa, e
    quella porta era aperta: chi rilegge l'esito domani deve trovarci
    l'alternativa da valutare, non un vicolo cieco.
    """
    sess, wire, _, _ = await _aperta(monkeypatch)
    try:
        await wire.says(_tool("record_call_fact", {
            "kind": "availability", "value": "domani alle 11:00",
        }))
        await wire.says(_tool("fail_mission", {
            "reason": "oggi dopo le 18 sono pieni, non posso accettare domani",
        }))
        assert sess.outcome.status == "needs_user"
        assert not sess.outcome.is_actionable()
        assert "domani" in sess.outcome.user_confirmation_needed
        assert sess.outcome.followup_required
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_a_failure_with_nothing_on_the_table_stays_a_failure(monkeypatch):
    """
    E quando non c'era niente da decidere, è un fallimento e basta.

    La prenotazione non si trova: non c'è nessuna alternativa in sospeso, e
    mandare la persona a scegliere fra il nulla sarebbe solo rumore.
    """
    sess, wire, _, _ = await _aperta(monkeypatch)
    try:
        await wire.says(_tool("record_call_fact", {
            "kind": "refusal", "value": "a quel nome non risulta nulla",
        }))
        await wire.says(_tool("fail_mission", {
            "reason": "lo studio non trova la prenotazione",
        }))
        assert sess.outcome.status == "failed"
        assert not sess.outcome.is_actionable()
    finally:
        await sess.close()


# ---------------------------------------------------------------------------
# §10 · Riagganciare senza tagliare la parola in bocca a nessuno
# ---------------------------------------------------------------------------

def _quiet(monkeypatch, *, grace=0.01, window=0.08, cap=1.0):
    """La stessa macchina a stati, con le lancette accelerate."""
    monkeypatch.setattr("telephone.live.GOODBYE_GRACE_S", grace)
    monkeypatch.setattr("telephone.live.QUIET_LINE_BEFORE_CLOSING_S", window)
    monkeypatch.setattr("telephone.live.DONT_WAIT_FOREVER_S", cap)


def _they_hang_up_here(monkeypatch):
    from telephone import carrier

    riagganciate = []

    async def finta(ref):
        riagganciate.append(ref)
        return True

    monkeypatch.setattr(carrier, "hang_up", finta)
    return riagganciate


async def _mission_done(sess, wire, saluta=True):
    """
    Porta la missione a un esito terminale valido, per la strada lunga.

    Che adesso è l'unica: disponibilità, poi un turno nuovo della controparte,
    poi la conferma. Al primo colpo il registro non chiude più.
    """
    await wire.says(_tool("record_call_fact", {
        "kind": "availability", "value": "alle 18 c'è posto",
    }))
    await wire.says({"serverContent": {"turnComplete": True}})
    await wire.says(_tool("complete_mission", {
        "confirmed_changes": {"appointment_date": "2026-09-14",
                              "new_time": "18:00"},
        "confirmation": "fatto, l'ho spostato alle 18",
    }))
    assert sess.outcome is not None and sess.outcome.status == "success"
    if saluta:
        # E adesso non si chiude senza salutare: glielo si fa dire.
        await wire.says({"serverContent": {"outputTranscription": {
            "text": "La ringrazio, buona giornata.",
        }}})


@pytest.mark.asyncio
async def test_a_quiet_line_after_the_last_word_is_closed(monkeypatch):
    """
    §10.A: missione compiuta, ORA ha finito, nessuno parla → si chiude.

    È il caso normale, ed è l'unico in cui riagganciare è la cosa gentile.
    """
    _quiet(monkeypatch)
    riagganciate = _they_hang_up_here(monkeypatch)
    sess, wire, _, _ = await _aperta(monkeypatch)
    sess.call = type("C", (), {"provider_ref": "uuid"})()
    try:
        await _mission_done(sess, wire)
        await wire.says({"serverContent": {"turnComplete": True}})
        await asyncio.sleep(0.3)

        assert riagganciate == ["uuid"]
        n = sess.how_it_went()
        assert n["call_closing"] == "closed"
        assert n["hangup_while_human_speaking"] == 0
        assert n["final_quiet_window_ms"] >= 75
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_someone_speaking_after_the_goodbye_stops_the_hangup(monkeypatch):
    """
    §10.B/E: «aspetti un secondo» dopo il saluto.

        CHI PARLA HA SEMPRE RAGIONE SULLA CHIUSURA.

    È esattamente quello che è successo alla terza telefonata vera: ORA aveva
    salutato, la persona ha provato a riprenderla, e si è ritrovata il
    telefono muto in mano. Qui la chiusura torna indietro.
    """
    import numpy as np

    _quiet(monkeypatch, window=0.6, cap=3.0)
    riagganciate = _they_hang_up_here(monkeypatch)
    sess, wire, _, _ = await _aperta(monkeypatch)
    sess.call = type("C", (), {"provider_ref": "uuid"})()
    try:
        await _mission_done(sess, wire)
        await wire.says({"serverContent": {"turnComplete": True}})
        await asyncio.sleep(0.05)

        # Qualcuno apre bocca mentre la finestra sta ancora scorrendo. Prima
        # il fondo della linea, perché le orecchie imparano quanto è alto il
        # silenzio *qui* prima di sapere che cos'è una voce.
        for _ in range(30):
            await sess.hear(bytes(320 * 2))
        forte = (np.sin(np.arange(320) / 3.0) * 12000).astype("<i2").tobytes()
        for _ in range(8):
            await sess.hear(forte)
        await asyncio.sleep(0.15)

        assert riagganciate == [], "ha riagganciato su qualcuno che parlava"
        n = sess.how_it_went()
        assert n["call_closing"] == "open", "la chiusura non è stata revocata"
        assert n["human_speech_after_terminal_count"] >= 1
        assert n["close_window_resets"] >= 1
        assert n["hangup_while_human_speaking"] == 0
        # §10.F: l'esito non si tocca. Un fatto non si revoca.
        assert sess.outcome.status == "success"
        assert sess.outcome.is_actionable()
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_a_new_answer_from_ora_also_revokes_the_closing(monkeypatch):
    """
    §10.D: la conversazione riparte, e la chiusura si annulla da sola.

    Se Gemini risponde a chi ha ripreso la parola, la telefonata è viva: non
    serve che qualcuno se ne accorga a mano.
    """
    import base64

    _quiet(monkeypatch, window=1.0, cap=3.0)
    riagganciate = _they_hang_up_here(monkeypatch)
    sess, wire, _, _ = await _aperta(monkeypatch)
    sess.call = type("C", (), {"provider_ref": "uuid"})()
    try:
        await _mission_done(sess, wire)
        await wire.says({"serverContent": {"turnComplete": True}})
        await asyncio.sleep(0.05)
        assert sess.how_it_went()["call_closing"] == "pending"

        await wire.says({"serverContent": {"modelTurn": {"parts": [
            {"inlineData": {"data": base64.b64encode(bytes(960)).decode()}},
        ]}}})
        await asyncio.sleep(0.05)

        assert riagganciate == []
        assert sess.how_it_went()["call_closing"] == "open"
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_after_the_interruption_the_line_closes_when_it_goes_quiet(
    monkeypatch,
):
    """
    §10.C: hanno parlato, hanno finito, e adesso si può chiudere.

    La finestra non è un divieto: è un'attesa. Quando il silenzio dura
    davvero, la telefonata finisce.
    """
    _quiet(monkeypatch, window=0.08, cap=1.0)
    riagganciate = _they_hang_up_here(monkeypatch)
    sess, wire, _, _ = await _aperta(monkeypatch)
    sess.call = type("C", (), {"provider_ref": "uuid"})()
    try:
        await _mission_done(sess, wire)
        await wire.says({"serverContent": {"turnComplete": True}})
        await asyncio.sleep(0.03)
        sess._somebody_is_talking_again()          # qualcuno ha ripreso
        assert riagganciate == []

        # Ha finito. Ma dopo un'interruzione non si chiude in silenzio: ORA
        # risaluta, e solo allora la finestra torna a scorrere.
        await wire.says({"serverContent": {"outputTranscription": {
            "text": "Grazie a lei, buona giornata.",
        }}})
        await wire.says({"serverContent": {"turnComplete": True}})
        await asyncio.sleep(0.35)
        assert riagganciate == ["uuid"]
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_the_same_care_applies_when_the_mission_failed(monkeypatch):
    """
    §10.G: un esito che non è un successo si chiude con la stessa cura.

    Chi si è sentito dire «non sono riuscito» ha più motivi, non meno, di
    voler aggiungere una parola.
    """
    _quiet(monkeypatch)
    riagganciate = _they_hang_up_here(monkeypatch)
    sess, wire, _, _ = await _aperta(monkeypatch)
    sess.call = type("C", (), {"provider_ref": "uuid"})()
    try:
        await wire.says(_tool("fail_mission", {"reason": "non trovano nulla"}))
        assert sess.outcome.status == "failed"
        assert sess.how_it_went()["call_closing"] == "open", (
            "ha aperto la chiusura prima ancora di finire di parlare"
        )
        await wire.says({"serverContent": {"outputTranscription": {
            "text": "La ringrazio comunque, arrivederci.",
        }}})
        await wire.says({"serverContent": {"turnComplete": True}})
        await asyncio.sleep(0.3)
        assert riagganciate == ["uuid"]
        assert sess.how_it_went()["hangup_while_human_speaking"] == 0
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_a_terminal_outcome_never_hangs_up_mid_sentence(monkeypatch):
    """
    §1.B/C/D: l'esito arriva mentre ORA sta ancora parlando.

    `complete_mission` viene chiamato in mezzo a un turno: la bocca è ancora
    aperta, e non si riaggancia su una frase a metà.
    """
    _quiet(monkeypatch)
    riagganciate = _they_hang_up_here(monkeypatch)
    sess, wire, _, _ = await _aperta(monkeypatch)
    sess.call = type("C", (), {"provider_ref": "uuid"})()
    try:
        await _mission_done(sess, wire, saluta=False)
        await asyncio.sleep(0.2)
        assert riagganciate == [], "ha chiuso senza aspettare la fine del turno"
        assert sess.how_it_went()["call_closing"] == "open"
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_a_line_already_busy_never_finishes_the_quiet_window(monkeypatch):
    """
    §1.E: la linea è occupata da prima che la finestra cominci.

        NON SI RIAGGANCIA SU UNA LINEA CHE PARLA — MAI, NON «QUASI MAI».

    Le protezioni sono due, e servono a cose diverse. Una scatta quando
    qualcuno **comincia** a parlare, ed è quella che copre «aspetti un
    secondo». Questa copre il caso in cui stava già parlando: nessun inizio
    da intercettare, solo una linea occupata che va guardata a ogni giro.

    Provando a togliere il controllo dentro la finestra, la prova sopra
    restava verde — la coprivano le orecchie in `hear`. Questa no.
    """
    _quiet(monkeypatch, window=0.08, cap=0.4)
    riagganciate = _they_hang_up_here(monkeypatch)
    sess, wire, _, _ = await _aperta(monkeypatch)
    sess.call = type("C", (), {"provider_ref": "uuid"})()
    try:
        await _mission_done(sess, wire)
        # Qualcuno sta già parlando: nessun inizio, solo una linea occupata.
        sess._ears.speaking = True
        await wire.says({"serverContent": {"turnComplete": True}})
        await asyncio.sleep(0.3)

        assert riagganciate == [], "ha riagganciato su una linea occupata"
        n = sess.how_it_went()
        assert n["call_closing"] == "open"
        assert n["hangup_while_human_speaking"] == 0
        assert n["human_speech_after_terminal_count"] >= 1
    finally:
        sess._ears.speaking = False
        await sess.close()


@pytest.mark.asyncio
async def test_the_last_check_before_hanging_up_is_the_line_itself(monkeypatch):
    """
    §1.E, l'ultimo gradino: si guarda la linea un istante prima di chiudere.

    Fra la fine della finestra e la chiamata al carrier passa pochissimo, ma
    in quel pochissimo qualcuno può aver ripreso a parlare. Chi riaggancia
    guarda un'ultima volta, e se sente una voce non chiude — e lo scrive.
    """
    riagganciate = _they_hang_up_here(monkeypatch)
    sess, wire, _, _ = await _aperta(monkeypatch)
    sess.call = type("C", (), {"provider_ref": "uuid"})()
    try:
        sess._call_closing = "pending"
        sess._goodbye = "completed"        # il congedo c'è già stato
        sess._ears.speaking = True
        await sess._hang_up_now()

        assert riagganciate == []
        assert sess._hung_up is False
        n = sess.how_it_went()
        # Il contatore esiste per farsi vedere quando qualcosa sfugge.
        assert n["hangup_while_human_speaking"] == 1
        assert n["call_closing"] == "open"
    finally:
        sess._ears.speaking = False
        await sess.close()


# ---------------------------------------------------------------------------
# §11 · Il passo lo batte la linea
# ---------------------------------------------------------------------------

def _play(**kw):
    from telephone.playback import PlaybackController

    uscite = []

    async def send(_f):
        uscite.append(time.perf_counter())

    return PlaybackController(send=send, **kw), uscite


@pytest.mark.asyncio
async def test_the_voice_follows_the_beat_it_is_given():
    """
    §11.A/C: un pacchetto per battito, e nessun jitter aggiunto sopra.

        IL METRONOMO NON È NOSTRO. È DELLA LINEA.

    Qui non si può verificare che l'uscita stia a venti millisecondi, e il
    motivo è esattamente quello che ha causato il problema: su questo host
    `asyncio.sleep(20 ms)` ne dorme trentuno, quindi nemmeno il generatore di
    battiti di questa prova riesce a battere a venti. Una prova che asserisse
    «uscita a 20 ms» misurerebbe la fortuna.

    Quello che si può verificare — ed è la proprietà che conta — è che la voce
    **segua** il battito che riceve: un pacchetto per battito, e una cadenza
    in uscita che non è più irregolare di quella in entrata. Se la linea batte
    a venti, ORA esce a venti; se batte storto, ORA esce storto uguale, non
    peggio.
    """
    play, uscite = _play(jitter_ms=0, external_clock=True)
    handle = play.begin(generation_id="g", turn_id=1)
    await play.feed(bytes(320 * 2 * 100), handle)

    battiti = []

    async def la_linea_batte():
        for _ in range(100):
            battiti.append(time.perf_counter())
            play.tick()
            await asyncio.sleep(0.02)

    await asyncio.wait_for(la_linea_batte(), timeout=8)
    await asyncio.sleep(0.1)
    n = play.how_it_went()
    await play.close()

    assert n["clock_source"] == "vonage"
    assert n["beat_credits_consumed"] >= 90, n
    # Qualche scadenza c'è sempre — dopo l'ultimo pacchetto la linea smette di
    # servire battiti, e sotto carico il generatore di questa prova può
    # fermarsi oltre i sessanta millisecondi, perché batte con lo stesso
    # `sleep` difettoso. Quello che conta è che il ripiego resti l'eccezione.
    assert n["fallback_clock_count"] <= 0.15 * len(uscite), n
    assert len(uscite) >= 90, f"solo {len(uscite)} pacchetti su 100 battiti"

    # La verifica sta su quanto dura tutto, non su quanto dura un pacchetto:
    # un singolo intervallo dipende da come il sistema operativo ha
    # organizzato la giornata, la somma no. Se la voce seguisse un orologio
    # suo invece del battito, qui i due archi si separerebbero.
    arco_battiti = (battiti[-1] - battiti[0]) * 1000
    arco_uscita = (uscite[-1] - uscite[0]) * 1000
    assert abs(arco_uscita - arco_battiti) < 0.10 * arco_battiti, (
        f"la voce ha impiegato {arco_uscita:.0f} ms per seguire "
        f"{arco_battiti:.0f} ms di battiti"
    )
    #     QUI NON SI MISURA IL RITARDO ASSOLUTO, E C'È UN MOTIVO.
    # `frame_schedule_lateness` conta la distanza da una cadenza ideale di
    # venti millisecondi. Su questa macchina il battito arriva a trentuno —
    # è lo stesso `sleep` difettoso che ha causato il problema — quindi quel
    # numero qui dentro misurerebbe il difetto del banco, non quello del
    # codice. Lo si legge sulla telefonata vera, dove i venti millisecondi li
    # batte la rete telefonica.
    #
    # Quello che si può affermare qui, e che è la proprietà che conta: la
    # voce non aggiunge un ritardo suo sopra quello che riceve.


@pytest.mark.asyncio
async def test_without_a_beat_the_voice_keeps_its_own_time():
    """
    §11.D / §6: se la linea smette di battere, ORA non ammutolisce.

        UN OROLOGIO CHE PUÒ FERMARSI VA SORVEGLIATO.

    Ed è la ragione per cui il ripiego non può essere `sleep(20 ms)` ripetuto:
    su questo host accumulerebbe undici millisecondi di ritardo a ogni giro.
    Qui la scadenza è assoluta e avanza da sola.
    """
    play, uscite = _play(jitter_ms=0, external_clock=True)
    handle = play.begin(generation_id="g", turn_id=1)
    await play.feed(bytes(320 * 2 * 20), handle)

    await asyncio.sleep(0.6)          # nessun battito: la linea tace
    n = play.how_it_went()
    await play.close()

    assert n["clock_source"] == "monotonic_fallback"
    assert n["fallback_clock_count"] >= 1
    assert len(uscite) >= 5, "si è fermata con la linea"


@pytest.mark.asyncio
async def test_the_clock_can_change_hands_without_losing_a_frame():
    """
    §11.F/G: si passa dal battito al ripiego e ritorno.

    Un cambio d'orologio non deve né saltare né ripetere un pacchetto: quello
    che esce è esattamente quello che è entrato, nell'ordine in cui è entrato.
    """
    from telephone.playback import PlaybackController

    uscite = []

    async def send(f):
        uscite.append(f)

    play = PlaybackController(send=send, jitter_ms=0, external_clock=True)
    handle = play.begin(generation_id="g", turn_id=1)
    # Trenta pacchetti riconoscibili uno per uno.
    for i in range(30):
        await play.feed(bytes([i, 0]) * 320, handle)

    async def la_linea_va_e_viene():
        for giro in range(34):
            if giro != 10:                 # al decimo, la linea salta un colpo
                play.tick()
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.3)

    await asyncio.wait_for(la_linea_va_e_viene(), timeout=8)
    n = play.how_it_went()
    await play.close()

    assert len(uscite) == 30, f"{len(uscite)} pacchetti invece di 30"
    for i, frame in enumerate(uscite):
        assert frame[0] == i, f"pacchetto {i} fuori posto o duplicato"
    assert n["frames_dropped"] == 0


@pytest.mark.asyncio
async def test_a_late_wakeup_does_not_become_a_permanent_delay():
    """
    §11.B / §7: il ripiego lavora a scadenze assolute.

    Si sveglia tardi; i pacchetti dopo devono tornare sulle loro scadenze
    invece di portarsi dietro il ritardo per sempre.
    """
    play, uscite = _play(jitter_ms=0, external_clock=False)
    handle = play.begin(generation_id="g", turn_id=1)
    await play.feed(bytes(320 * 2 * 25), handle)
    await asyncio.sleep(0.012)             # il risveglio in ritardo
    await asyncio.sleep(0.6)
    n = play.how_it_went()
    await play.close()

    assert len(uscite) >= 15
    # Il ritardo dell'ultimo pacchetto non è la somma di tutti i risvegli.
    assert n["frame_schedule_lateness_max_ms"] < 100, n


@pytest.mark.asyncio
async def test_the_beat_never_turns_into_a_busy_loop():
    """
    §11.E: aspettare un battito non vuol dire girare a vuoto.

    Se la linea non batte, il rubinetto deve dormire — non consumare il
    processore fino al prossimo pacchetto.
    """
    play, uscite = _play(jitter_ms=0, external_clock=True)
    handle = play.begin(generation_id="g", turn_id=1)
    await play.feed(bytes(320 * 2 * 4), handle)

    prima = time.process_time()
    await asyncio.sleep(0.4)
    speso = time.process_time() - prima
    await play.close()

    assert speso < 0.15, f"ha consumato {speso*1000:.0f} ms di processore in 400"


# ---------------------------------------------------------------------------
# §10 · Un battito e un credito, e i crediti non si perdono
# ---------------------------------------------------------------------------

def _credits():
    from telephone.playback import BeatCredits

    return BeatCredits()


@pytest.mark.asyncio
async def test_three_beats_before_anyone_listens_are_all_still_there():
    """
    §10.A/C: tre battiti prima che il consumatore si svegli.

        UN SEGNALE SI PERDE. UN CREDITO SI ACCUMULA.

    È il difetto che ha rovinato la quarta telefonata, ridotto alla sua forma
    più piccola. Con un `asyncio.Event` qui ne sopravviveva uno: l'Event è
    binario, e i due battiti arrivati dopo non erano mai esistiti. Sulla linea
    vera i battiti persi sono stati duecentosette, e ognuno è costato un
    timeout da sessanta millisecondi.
    """
    crediti = _credits()
    for _ in range(3):
        crediti.release()

    assert crediti.pending == 3
    for _ in range(3):
        assert await crediti.acquire(0.05) is True
    assert crediti.pending == 0
    assert await crediti.acquire(0.02) is False, "ha inventato un quarto credito"


@pytest.mark.asyncio
async def test_ten_produced_seven_consumed_leaves_three():
    """§10.B: la contabilità torna, ed è il punto di tutto."""
    crediti = _credits()
    for _ in range(10):
        crediti.release()
    for _ in range(7):
        assert await crediti.acquire(0.05) is True

    n = crediti.how_it_went()
    assert n["beat_credits_produced"] == 10
    assert n["beat_credits_consumed"] == 7
    assert n["beat_credits_pending"] == 3
    assert n["beat_credits_peak"] == 10


@pytest.mark.asyncio
async def test_no_credit_ever_vanishes():
    """
    §3: l'invariante. Prodotti = consumati + in attesa + riconciliati.

        NESSUN CREDITO DEVE SPARIRE.

    Se questo conto non torna, da qualche parte un battito è stato buttato
    senza che nessuno se ne accorgesse — che è esattamente quello che faceva
    l'Event, in silenzio.
    """
    crediti = _credits()
    for giro in range(20):
        crediti.release()
        if giro % 3 == 0:
            await crediti.acquire(0.05)
    buttati = crediti.forget_the_old_ones()
    for _ in range(5):
        crediti.release()
    await crediti.acquire(0.05)

    n = crediti.how_it_went()
    assert buttati > 0
    assert n["beat_credits_produced"] == (
        n["beat_credits_consumed"]
        + n["beat_credits_pending"]
        + n["stale_credits_dropped_or_reconciled"]
    ), n


@pytest.mark.asyncio
async def test_a_frame_sent_without_a_credit_is_a_debt():
    """
    §10.D/E: il ripiego non regala un pacchetto in più dopo.

        QUANDO SI E' PAGATO SENZA CREDITO, SI DEVE UN CREDITO.

    Un frame mandato mentre la linea taceva ha già consumato il suo tempo.
    Quando i battiti tornano, il primo pareggia quel debito invece di
    autorizzarne un altro — altrimenti ogni buco di linea lascerebbe dietro
    una raffica.
    """
    crediti = _credits()
    assert await crediti.acquire(0.02) is False    # ripiego: si manda comunque
    assert crediti.owed == 1

    crediti.release()                              # la linea torna
    assert crediti.pending == 0, "il debito non è stato pareggiato"
    assert crediti.how_it_went()["stale_credits_dropped_or_reconciled"] == 1

    crediti.release()
    assert crediti.pending == 1, "adesso sì che autorizza"


@pytest.mark.asyncio
async def test_a_slow_consumer_loses_nothing():
    """
    §10.F: il consumatore va lento, la linea no.

    Venticinque battiti mentre il rubinetto è fermo. Al risveglio devono
    esserci tutti: il tempo logico non si perde, si accumula.
    """
    crediti = _credits()

    async def la_linea_batte():
        for _ in range(25):
            crediti.release()
            await asyncio.sleep(0.001)

    await la_linea_batte()
    presi = 0
    while await crediti.acquire(0.01):
        presi += 1
    assert presi == 25, f"ne ha trovati {presi} invece di 25"


@pytest.mark.asyncio
async def test_credits_from_the_silence_do_not_open_the_next_sentence():
    """
    §2/§4: i crediti maturati mentre ORA taceva si buttano.

        UN CREDITO VECCHIO NON E' UN CREDITO.

    Fra una risposta e l'altra la linea batte lo stesso — sono venti, trenta
    secondi di battiti che rappresentano tempo passato in silenzio. Tenerli
    vorrebbe dire aprire la frase dopo con mille pacchetti tutti insieme.
    """
    from telephone.playback import PlaybackController

    uscite = []

    async def send(_f):
        uscite.append(time.perf_counter())

    play = PlaybackController(send=send, jitter_ms=0, external_clock=True)
    # Trenta secondi di silenzio sulla linea, mentre non c'è niente da dire.
    for _ in range(1500):
        play.tick()
    assert play.credits.pending == 1500

    handle = play.begin(generation_id="g", turn_id=1)
    assert play.credits.pending == 0, "la frase comincerebbe con una raffica"
    assert play.credits.how_it_went()[
        "stale_credits_dropped_or_reconciled"] == 1500

    await play.feed(bytes(320 * 2 * 5), handle)
    await asyncio.sleep(0.1)
    await play.close()
    # Senza battiti freschi, il ripiego fa uscire qualche pacchetto — non 1500.
    assert len(uscite) <= 8, f"{len(uscite)} pacchetti in cento millisecondi"


@pytest.mark.asyncio
async def test_a_late_consumer_catches_up_without_a_machine_gun():
    """
    §4/§10.G/H: recupera il ritardo, ma non sparando.

        IL CREDITO AUTORIZZA. LA SCADENZA FRENA.

    Il rubinetto si sveglia con dieci crediti in mano: ce li ha tutti — nessun
    battito è andato perso — ma fra due pacchetti resta un minimo. Una voce che
    recupera correndo è peggio di una voce in ritardo.
    """
    from telephone.playback import PlaybackController

    uscite = []

    async def send(_f):
        uscite.append(time.perf_counter())

    play = PlaybackController(send=send, jitter_ms=0, external_clock=True)
    handle = play.begin(generation_id="g", turn_id=1)
    await play.feed(bytes(320 * 2 * 12), handle)
    for _ in range(10):
        play.tick()

    await asyncio.sleep(0.6)
    await play.close()

    # Sei su dieci bastano a dimostrare che i crediti sono stati usati: il
    # numero esatto dipende da quanto è occupata la macchina, la proprietà no.
    assert len(uscite) >= 6, f"solo {len(uscite)}: i crediti non sono serviti"
    # Una raffica non è un pacchetto un po' vicino: è una sequenza di pacchetti
    # attaccati. Si conta quella, non il minimo singolo — che su una macchina
    # carica misura lo scheduler del sistema operativo.
    n = play.how_it_went()
    #     LA RAFFICA E' UNA SEQUENZA, NON UN INTERVALLO.
    # Il freno mira esattamente al minimo, e le due misure stanno ai lati di un
    # `await`: un singolo intervallo puo cadere a 7,9 invece che a 8,0 senza
    # che nessun pacchetto sia partito troppo presto davvero. Quello che si
    # garantisce e che non ci sia un *seguito* — e che nessuno stia
    # sensibilmente sotto il minimo.
    assert n["longest_burst_run"] == 0, (
        f"{n['longest_burst_run']} pacchetti di fila troppo vicini"
    )
    assert n["intra_min_ms"] >= 7.0, n["intra_worst_ms"]
    # E restano in ordine, uno dopo l'altro.
    assert uscite == sorted(uscite)


@pytest.mark.asyncio
async def test_an_interruption_leaves_no_credit_behind_to_speak_with():
    """
    §10.I: l'interruzione svuota la coda, e i crediti non la riempiono.

    Dopo un barge-in i crediti accumulati non devono far uscire l'audio
    vecchio: quello che è stato annullato resta annullato.
    """
    from telephone.playback import PlaybackController

    uscite = []

    async def send(f):
        uscite.append(f)

    play = PlaybackController(send=send, jitter_ms=0, external_clock=True)
    handle = play.begin(generation_id="g", turn_id=1)
    await play.feed(bytes(320 * 2 * 30), handle)
    for _ in range(3):
        play.tick()
    await asyncio.sleep(0.08)
    quanti_prima = len(uscite)

    buttati = await play.cancel()
    for _ in range(40):
        play.tick()
    await asyncio.sleep(0.15)
    await play.close()

    assert buttati > 0
    assert len(uscite) == quanti_prima, (
        f"{len(uscite) - quanti_prima} pacchetti usciti dopo l'annullamento"
    )


@pytest.mark.asyncio
async def test_closing_the_session_leaves_no_credit_machinery_running(
    monkeypatch,
):
    """§10.J: niente task appesi, niente contatori che continuano a girare."""
    prima = len(asyncio.all_tasks())
    sess, wire, _, _ = await _aperta(monkeypatch)
    for _ in range(20):
        await sess.hear(bytes(640))
    assert sess.playback.credits.produced >= 20

    await sess.close()
    await asyncio.sleep(0.05)
    assert len(asyncio.all_tasks()) <= prima + 1
    assert sess.playback._pump is None


@pytest.mark.asyncio
async def test_the_transport_feeds_one_credit_per_inbound_frame(monkeypatch):
    """
    §1: un pacchetto dalla linea, un credito. Nient'altro.

    Si usa la cadenza, mai il contenuto: cinquanta pacchetti di silenzio puro
    valgono cinquanta crediti come cinquanta pacchetti di voce.
    """
    sess, wire, _, _ = await _aperta(monkeypatch)
    try:
        for _ in range(50):
            await sess.hear(bytes(640))
        assert sess.playback.credits.produced == 50

        n = sess.how_it_went()
        assert n["beat_credits_produced"] == 50
        assert n["clock_source_counts"]["vonage"] == 0, (
            "nessuno ha ancora parlato: nessun credito va consumato"
        )
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_the_books_balance_even_when_the_line_stops_beating():
    """
    §6: l'invariante tiene anche attraverso un ripiego.

        UN BATTITO ARRIVATO È UN BATTITO PRODOTTO, SEMPRE.

    Sulla quinta telefonata vera il conto non tornava per ventidue — esatta-
    mente il numero dei ripieghi. Non era un credito sparito: era che un
    battito arrivato a pagare un debito veniva contato fra i riconciliati e
    non fra i prodotti. Un conto che non torna non serve a dire «nessun
    credito è sparito», che è l'unica cosa per cui esiste.
    """
    crediti = _credits()
    for _ in range(4):
        crediti.release()
    for _ in range(4):
        await crediti.acquire(0.05)

    # Due ripieghi: la linea ha smesso di battere.
    assert await crediti.acquire(0.01) is False
    assert await crediti.acquire(0.01) is False
    assert crediti.owed == 2

    # E poi torna: i primi due battiti pagano, il terzo autorizza.
    for _ in range(3):
        crediti.release()

    n = crediti.how_it_went()
    assert n["beat_credits_produced"] == 7
    assert n["beat_credits_produced"] == (
        n["beat_credits_consumed"]
        + n["beat_credits_pending"]
        + n["stale_credits_dropped_or_reconciled"]
    ), n
    assert n["beat_credits_owed"] == 0


# ---------------------------------------------------------------------------
# §14 · Chi chiama parla per primo, ma non parla sopra
# ---------------------------------------------------------------------------

def _subito_apertura(monkeypatch, grazia=0.02):
    monkeypatch.setattr("telephone.live.LISTEN_BEFORE_OPENING_S", grazia)


def _cosa_ha_chiesto(wire):
    """L'ultima cosa mandata a chi parla come turno dell'utente."""
    fette = wire.what_it_sent("clientContent")
    if not fette:
        return ""
    return fette[-1]["clientContent"]["turns"][0]["parts"][0]["text"]


async def _scalda_le_orecchie(sess, quanti=30):
    """
    Il silenzio della linea, che è quello che Vonage manda davvero.

    Le orecchie hanno bisogno di sentirlo prima di saper riconoscere una voce,
    e sulla linea vera arriva da solo: mentre la sessione si apriva i pacchetti
    si accumulavano nel buffer del socket. Qui bisogna darglielo a mano.
    """
    for _ in range(quanti):
        await sess.hear(bytes(320 * 2))


def _una_voce(n=8):
    """Rumore abbastanza forte da essere una voce per le orecchie."""
    import numpy as np

    return (np.sin(np.arange(320) / 3.0) * 12000).astype("<i2").tobytes()


@pytest.mark.asyncio
async def test_she_opens_the_call_without_waiting_to_be_spoken_to(monkeypatch):
    """
    §14.A / §1: la linea si apre e ORA parla, senza che nessuno la interroghi.

        CHI COMPONE UN NUMERO NON ASPETTA DI ESSERE INTERROGATO.

    Prima aspettava. Una telefonata è arrivata muta proprio per questo:
    lei aspettava lui, lui aspettava lei, e dopo ventisei secondi la persona
    ha riagganciato.
    """
    _subito_apertura(monkeypatch)
    sess, wire, _, _ = await _aperta(monkeypatch)
    try:
        await _scalda_le_orecchie(sess)
        await asyncio.sleep(0.25)
        chiesto = _cosa_ha_chiesto(wire)
        assert chiesto, "non ha aperto bocca"
        assert "Buongiorno, sono l'assistente di Francesco Cefalà" in chiesto
        assert wire.what_it_sent("clientContent")[-1]["clientContent"][
            "turnComplete"] is True, "ha parlato senza chiudere il turno"
        assert sess.how_it_went()["opening_state"] == "starting"
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_the_first_line_is_the_one_the_backend_wrote(monkeypatch):
    """
    §14.E/F/G / §2: dice di chi è l'assistente e perché chiama. Nient'altro.

    La frase non se la inventa: è `say_this_first`, che nasce dalla missione e
    che il controllo di privacy ha già guardato.
    """
    _subito_apertura(monkeypatch)
    sess, wire, _, _ = await _aperta(monkeypatch)
    try:
        await _scalda_le_orecchie(sess)
        await asyncio.sleep(0.25)
        chiesto = _cosa_ha_chiesto(wire)
        assert sess.packet.say_this_first in chiesto
        assert "assistente di" in chiesto
        assert "appuntamento" in chiesto
        for mai in ("1990", "codice fiscale", "CFLFNC", "+39", "3774714389"):
            assert mai not in chiesto, mai
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_if_they_speak_first_she_does_not_talk_over_them(monkeypatch):
    """
    §14.B / §4: rispondono dicendo «pronto?» nello stesso istante.

        CHI PARLA PER PRIMO NON PARLA SOPRA.

    Le orecchie sentono una voce prima che se ne accorga Gemini — misurato
    sulla linea vera: da 217 a 663 millisecondi prima. Quel margine serve
    esattamente a questo: rimandare invece di sovrapporsi.
    """
    _subito_apertura(monkeypatch, grazia=0.25)
    sess, wire, _, _ = await _aperta(monkeypatch)
    try:
        for _ in range(30):
            await sess.hear(bytes(320 * 2))      # il fondo della linea
        for _ in range(8):
            await sess.hear(_una_voce())         # «pronto?»
        await asyncio.sleep(0.35)

        assert _cosa_ha_chiesto(wire) == "", "ha parlato sopra la persona"
        n = sess.how_it_went()
        assert n["opening_state"] == "pending"
        assert n["opening_deferred_for_human"] == 1
        assert n["speech_onsets_heard"] >= 1
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_an_interrupted_opening_is_completed_not_restarted(monkeypatch):
    """
    §14.C / §5: la interrompono mentre si presenta.

    Non si inventa una logica nuova: è il barge-in che già funziona, e poi il
    registro dell'apertura chiede soltanto il pezzo che manca.
    """
    import base64

    _subito_apertura(monkeypatch)
    sess, wire, _, _ = await _aperta(monkeypatch)
    try:
        await _scalda_le_orecchie(sess)
        await asyncio.sleep(0.25)
        assert sess.how_it_went()["opening_state"] == "starting"

        await wire.says({"serverContent": {
            # Tagliata dopo il nome ma prima del motivo: è il pezzo che
            # manca, non la presentazione intera.
            "outputTranscription": {
                "text": "Buongiorno, sono l'assistente di Francesco Cefa",
            },
        }})
        await wire.says({"serverContent": {"modelTurn": {"parts": [
            {"inlineData": {"data": base64.b64encode(bytes(960)).decode()}},
        ]}}})
        await wire.says({"serverContent": {"interrupted": True}})

        n = sess.how_it_went()
        assert n["opening_state"] == "interrupted"
        assert n["introduction_state"] == "partial"

        # E quello che manca lo chiede, senza rifare la presentazione.
        await wire.says({"serverContent": {"turnComplete": True}})
        await asyncio.sleep(0.05)
        nota = _cosa_ha_chiesto(wire)
        assert "Non ricominciare la presentazione da capo" in nota
        assert "chiami per" in nota
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_a_completed_opening_is_never_asked_for_again(monkeypatch):
    """§14.D: detta per intera, non si ripete."""
    _subito_apertura(monkeypatch)
    sess, wire, _, _ = await _aperta(monkeypatch)
    try:
        await _scalda_le_orecchie(sess)
        await asyncio.sleep(0.25)
        quante_prima = len(wire.what_it_sent("clientContent"))

        await wire.says({"serverContent": {"outputTranscription": {
            "text": "Buongiorno, sono l'assistente di Francesco. Chiamo per "
                    "spostare il suo appuntamento dal dentista di oggi, "
                    "dalle 16 alle 18.",
        }}})
        await wire.says({"serverContent": {"turnComplete": True}})
        await wire.says({"serverContent": {"turnComplete": True}})
        await asyncio.sleep(0.05)

        n = sess.how_it_went()
        assert n["opening_state"] == "completed"
        assert n["introduction_state"] == "completed"
        assert n["introduction_nudges"] == 0
        assert len(wire.what_it_sent("clientContent")) == quante_prima, (
            "ha rifatto la presentazione"
        )
        assert n["opening_completed_at_ms"] is not None
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_the_opening_leaves_no_task_behind(monkeypatch):
    """La chiusura non deve lasciare appeso il compito dell'apertura."""
    _subito_apertura(monkeypatch, grazia=5.0)     # non farà in tempo
    prima = len(asyncio.all_tasks())
    sess, wire, _, _ = await _aperta(monkeypatch)
    await sess.close()
    await asyncio.sleep(0.05)
    assert sess._opening_task is None
    assert len(asyncio.all_tasks()) <= prima + 1


# ---------------------------------------------------------------------------
# §14.H/I · La voce
# ---------------------------------------------------------------------------

def test_a_chosen_voice_reaches_the_session(monkeypatch):
    """§14.H: se qualcuno ha scelto una voce, viene chiesta."""
    from telephone.live import _how_she_sounds

    monkeypatch.setenv("GEMINI_LIVE_VOICE", "Aoede")
    config = _how_she_sounds()
    assert config["responseModalities"] == ["AUDIO"]
    assert config["speechConfig"]["voiceConfig"][
        "prebuiltVoiceConfig"]["voiceName"] == "Aoede"


def test_without_a_choice_ora_still_has_her_own(monkeypatch):
    """
    §14.I diceva: senza scelta, nessuna preferenza. Adesso dice il contrario.

        UNA VOCE NON SI SCEGLIE DA SOLI — MA UNA VOLTA SCELTA, SI TIENE.

    La regola nacque giusta: non imporre una voce che nessuno aveva chiesto.
    Poi qualcuno l'ha chiesta. Francesco ha ascoltato e ha scelto Charon, e da
    quel momento «nessuna preferenza» ha smesso di voler dire «lascia decidere
    al modello»: vuol dire «usa la voce di ORA».

    La differenza si e' sentita al telefono. Una sessione aperta senza
    `speechConfig` prende la voce predefinita del modello — un'altra — e su una
    telefonata vera la voce e' cambiata a meta' senza che nessun campo potesse
    smentirlo. Adesso nessuna sessione parte muta su questo punto.
    """
    from telephone.live import THE_VOICE, _how_she_sounds

    def quale(config):
        return config["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"][
            "voiceName"]

    monkeypatch.delenv("GEMINI_LIVE_VOICE", raising=False)
    assert quale(_how_she_sounds()) == THE_VOICE

    monkeypatch.setenv("GEMINI_LIVE_VOICE", "   ")
    assert quale(_how_she_sounds()) == THE_VOICE

    # E quando qualcuno ne chiede un'altra, resta l'ultima parola sua.
    monkeypatch.setenv("GEMINI_LIVE_VOICE", "Aoede")
    assert quale(_how_she_sounds()) == "Aoede"


@pytest.mark.asyncio
async def test_the_voice_travels_in_the_setup(monkeypatch):
    """E arriva davvero dentro il setup della sessione, non solo nel dizionario."""
    monkeypatch.setenv("GEMINI_LIVE_VOICE", "Leda")
    sess, wire, _, _ = await _aperta(monkeypatch)
    try:
        setup = wire.what_it_sent("setup")[0]["setup"]
        assert setup["generationConfig"]["speechConfig"]["voiceConfig"][
            "prebuiltVoiceConfig"]["voiceName"] == "Leda"
        assert sess.how_it_went()["opening_voice"] == "Leda"
    finally:
        await sess.close()


# ---------------------------------------------------------------------------
# §14.J · L'arretrato non diventa una raffica
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_backlog_of_twenty_credits_never_becomes_a_burst():
    """
    §14.J / §10: venti crediti arretrati, e una `send` che ogni tanto è lenta.

        SI MISURA DALL'ULTIMO PACCHETTO USCITO, NON DA PRIMA.

    Il freno guardava il momento in cui finiva l'attesa — un istante *prima*
    dell'invio. Quando quell'invio era lento, il margine se lo mangiava lui e
    il pacchetto dopo partiva subito: sulla quinta telefonata vera settantasei
    intervalli sotto gli otto millisecondi, e ventisette di fila. Non si
    sentiva, ma un freno che non frena è un freno che un giorno serve e non c'è.
    """
    from telephone.playback import MIN_GAP_S, PlaybackController

    uscite = []

    async def send(_f):
        uscite.append(time.perf_counter())
        # Una send ogni cinque è lenta: è la condizione che rompeva il freno.
        await asyncio.sleep(0.03 if len(uscite) % 5 == 0 else 0)

    play = PlaybackController(send=send, jitter_ms=0, external_clock=True)
    handle = play.begin(generation_id="g", turn_id=1)
    await play.feed(bytes(320 * 2 * 20), handle)
    for _ in range(20):
        play.tick()

    await asyncio.sleep(1.2)
    n = play.how_it_went()
    await play.close()

    assert len(uscite) == 20, f"{len(uscite)} pacchetti su 20 crediti"
    assert n["frames_dropped"] == 0
    # Nessun seguito, e nessuno sensibilmente sotto il minimo: l'intervallo
    # singolo a 7,9 e la risoluzione della misura, non un pacchetto partito
    # troppo presto.
    assert n["longest_burst_run"] == 0, n["intra_worst_ms"]
    assert n["intra_min_ms"] >= MIN_GAP_S * 1000 - 1.0, n["intra_min_ms"]
    # E non si è perso nessun credito per strada.
    assert n["beat_credits_produced"] == (
        n["beat_credits_consumed"]
        + n["beat_credits_pending"]
        + n["stale_credits_dropped_or_reconciled"]
    ), n


# ---------------------------------------------------------------------------
# §8 · Non si riaggancia senza salutare
# ---------------------------------------------------------------------------

async def _dice(wire, parole, chiudi=True):
    """Fa dire una frase a ORA, e chiude il turno."""
    await wire.says({"serverContent": {"outputTranscription": {"text": parole}}})
    if chiudi:
        await wire.says({"serverContent": {"turnComplete": True}})


@pytest.mark.asyncio
async def test_she_never_hangs_up_after_asking_a_question(monkeypatch):
    """
    §8.E: l'ultima cosa detta era una domanda. Non si chiude. Mai.

        CHI FA UNA DOMANDA ASPETTA LA RISPOSTA.

    È letteralmente quello che è successo alla sesta telefonata vera: ORA ha
    chiesto «ci sono problemi?», la persona ha risposto «no, tutto ok», e si è
    ritrovata il telefono muto in mano. La regola non ha bisogno di capire
    cosa sia una domanda — guarda come finisce la frase. È punteggiatura, non
    semantica.
    """
    _quiet(monkeypatch)
    riagganciate = _they_hang_up_here(monkeypatch)
    sess, wire, _, _ = await _aperta(monkeypatch)
    sess.call = type("C", (), {"provider_ref": "uuid"})()
    try:
        await _mission_done(sess, wire, saluta=False)
        await _dice(wire, "Perfetto. Ci sono altri problemi?")
        await asyncio.sleep(0.3)

        assert riagganciate == [], "ha riagganciato dopo aver fatto una domanda"
        n = sess.how_it_went()
        assert n["last_words_were_a_question"] is True
        assert n["goodbye_state"] == "pending"
        assert n["hangup_while_human_speaking"] == 0
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_after_no_tutto_ok_she_says_goodbye_before_closing(monkeypatch):
    """
    §8.B: «no tutto ok» → ORA saluta, e solo dopo chiude.

        UNA MISSIONE COMPIUTA NON È UNA CONVERSAZIONE FINITA.

    Non basta che l'esito sia terminale e che la linea taccia: serve un ultimo
    atto conversazionale. Se non c'è, si chiede — non si riaggancia.
    """
    _quiet(monkeypatch)
    riagganciate = _they_hang_up_here(monkeypatch)
    sess, wire, _, _ = await _aperta(monkeypatch)
    sess.call = type("C", (), {"provider_ref": "uuid"})()
    try:
        await _mission_done(sess, wire, saluta=False)
        # ORA dice qualcosa che non è né una domanda né un congedo.
        await _dice(wire, "Perfetto, grazie mille.")
        await asyncio.sleep(0.15)

        assert riagganciate == [], "ha chiuso senza congedarsi"
        n = sess.how_it_went()
        assert n["goodbye_state"] == "speaking"
        assert n["goodbye_nudges"] == 1
        # E la spinta le chiede un saluto, senza altre domande.
        nota = _cosa_ha_chiesto(wire)
        assert "saluto" in nota and "senza fare altre domande" in nota

        # Adesso saluta davvero, e la linea si chiude.
        await _dice(wire, "Va bene, allora la saluto. Buona giornata.")
        await asyncio.sleep(0.3)
        assert riagganciate == ["uuid"]
        assert sess.how_it_went()["goodbye_state"] == "completed"
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_a_goodbye_cut_in_half_does_not_close_the_line(monkeypatch):
    """
    §8.C: la interrompono mentre saluta.

    Il saluto non è avvenuto, quindi la telefonata non è finita. E chi ha
    interrotto ha qualcosa da dire: si ascolta.
    """
    import base64

    _quiet(monkeypatch, window=0.5, cap=2.0)
    riagganciate = _they_hang_up_here(monkeypatch)
    sess, wire, _, _ = await _aperta(monkeypatch)
    sess.call = type("C", (), {"provider_ref": "uuid"})()
    try:
        await _mission_done(sess, wire, saluta=False)
        await _dice(wire, "Perfetto, grazie mille.")
        await asyncio.sleep(0.1)
        assert sess.how_it_went()["goodbye_state"] == "speaking"

        await wire.says({"serverContent": {"modelTurn": {"parts": [
            {"inlineData": {"data": base64.b64encode(bytes(960)).decode()}},
        ]}}})
        await wire.says({"serverContent": {"interrupted": True}})
        await asyncio.sleep(0.15)

        assert riagganciate == []
        assert sess.how_it_went()["goodbye_state"] == "interrupted"
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_a_new_question_after_the_mission_gets_an_answer_then_a_goodbye(
    monkeypatch,
):
    """
    §8.D: chiedono altro dopo che la missione è chiusa.

    Si risponde, poi ci si congeda, poi si chiude. In quest'ordine — e l'esito
    della missione non si tocca: resta quello che era.
    """
    _quiet(monkeypatch)
    riagganciate = _they_hang_up_here(monkeypatch)
    sess, wire, _, _ = await _aperta(monkeypatch)
    sess.call = type("C", (), {"provider_ref": "uuid"})()
    try:
        await _mission_done(sess, wire, saluta=False)
        await _dice(wire, "Le serve altro?")            # una domanda: si aspetta
        await asyncio.sleep(0.12)
        assert riagganciate == []

        await _dice(wire, "Certo, glielo confermo per iscritto.")
        await asyncio.sleep(0.12)
        assert riagganciate == []                       # niente congedo: si chiede

        await _dice(wire, "Grazie a lei, arrivederci.")
        await asyncio.sleep(0.3)
        assert riagganciate == ["uuid"]
        assert sess.outcome.status == "success"
        assert sess.outcome.is_actionable()
    finally:
        await sess.close()


# ---------------------------------------------------------------------------
# §18 · La sesta telefonata, per intero
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_sixth_call_replayed_from_end_to_end(monkeypatch):
    """
    §18: esattamente quello che è successo, e che adesso non deve più.

    Tre difetti in una telefonata sola: ha chiuso la missione su una
    disponibilità, e ha riagganciato dopo aver fatto una domanda. Qui la
    sequenza è la stessa, battuta per battuta, e ogni passaggio è quello che
    allora è andato storto.
    """
    _quiet(monkeypatch, window=0.2, cap=2.0)
    riagganciate = _they_hang_up_here(monkeypatch)
    sess, wire, _, _ = await _aperta(monkeypatch)
    sess.call = type("C", (), {"provider_ref": "uuid"})()
    try:
        # «Pronto?» — e ORA si presenta.
        await _scalda_le_orecchie(sess)
        await _dice(wire, "Buongiorno, sono l'assistente di Francesco Cefalà. "
                          "Chiamo per spostare il suo appuntamento dal "
                          "dentista di oggi, dalle 16 alle 18.")
        assert sess.how_it_went()["introduction_state"] == "completed"

        # «Sì, alle 18 abbiamo disponibilità» → prova a chiudere. RESPINTA.
        await wire.says(_tool("complete_mission", {
            "confirmed_changes": {"appointment_date": "2026-09-14",
                                  "new_time": "18:00"},
            "confirmation": "alle 18 abbiamo disponibilità",
        }))
        risposta = _risposta(wire)
        assert risposta["accepted"] is False, "ha chiuso su una disponibilità"
        assert risposta["reason"] == "change_not_requested_yet"
        assert sess.outcome is None
        assert riagganciate == []

        # ORA chiede di procedere; loro prendono tempo.
        await _dice(wire, "Perfetto. Può quindi effettuare lo spostamento?")
        await wire.says({"serverContent": {"turnComplete": True}})
        assert riagganciate == [], "ha chiuso mentre la trattativa era aperta"

        # E adesso confermano davvero: turno nuovo, conferma vera.
        await wire.says(_tool("complete_mission", {
            "confirmed_changes": {"appointment_date": "2026-09-14",
                                  "old_time": "16:00", "new_time": "18:00"},
            "confirmation": "sì, fatto, l'ho spostato alle 18",
        }))
        assert _risposta(wire)["accepted"] is True
        assert sess.outcome.status == "success"
        assert sess.outcome.is_actionable()

        # «Ci sono problemi?» → non si chiude dopo una domanda.
        await _dice(wire, "Perfetto. Ci sono problemi?")
        await asyncio.sleep(0.2)
        assert riagganciate == [], "ha riagganciato dopo una domanda"

        # «No tutto ok» → ORA si congeda, e solo allora chiude.
        await _dice(wire, "Bene, allora la ringrazio. Buona giornata.")
        await asyncio.sleep(0.35)
        assert riagganciate == ["uuid"]

        n = sess.how_it_went()
        assert n["hangup_while_human_speaking"] == 0
        assert n["goodbye_state"] == "completed"
        assert n["mission_progress"] == "completed"
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_the_last_gate_before_the_carrier_is_the_goodbye(monkeypatch):
    """
    §7: e l'ultimo gradino guarda anche il congedo.

    La regola vera sta più a monte — la finestra di chiusura non si apre
    nemmeno finché ORA non si è congedata. Questa è la rete sotto: se un
    giorno qualcuno chiamasse `_hang_up_now` per un'altra strada, la linea non
    si chiude lo stesso.

    Togliendo il controllo a monte le altre prove restavano verdi; questa no.
    """
    riagganciate = _they_hang_up_here(monkeypatch)
    sess, wire, _, _ = await _aperta(monkeypatch)
    sess.call = type("C", (), {"provider_ref": "uuid"})()
    try:
        sess._call_closing = "pending"
        sess._goodbye = "speaking"          # stava ancora salutando
        await sess._hang_up_now()

        assert riagganciate == []
        assert sess._hung_up is False
        assert sess.how_it_went()["call_closing"] == "open"
        # E non è il caso della persona che parla: quella spia resta a zero.
        assert sess.how_it_went()["hangup_while_human_speaking"] == 0
    finally:
        await sess.close()


# ---------------------------------------------------------------------------
# §8/§9 · La barriera, con un orologio che diciamo noi
# ---------------------------------------------------------------------------

class OrologioBugiardo:
    """
    Un timer che promette un'attesa e non la mantiene.

        `SLEEP(8 MS)` SU QUESTA MACCHINA NE DORME 0,3.

    Non è un'invenzione per far passare una prova: è la misura della settima
    telefonata vera, dove il freno decideva 7,97 ms e otteneva 0,30. Qui quel
    comportamento è riprodotto in forma pura e deterministica — il tempo
    avanza di un decimo di quello che si chiede — così la proprietà della
    barriera si dimostra senza dipendere da come è fatto il sistema operativo
    di chi esegue le prove.
    """

    def __init__(self, bugia=0.1):
        self.t = 1000.0
        self.bugia = bugia
        self.dormite = 0
        self.cessioni = 0
        # Quanto e' stato chiesto, ogni volta. Serve a dimostrare che le
        # attese non si restringono verso lo zero — la forma che nel V3.13
        # produsse un ciclo che non tornava.
        self.chieste = []

    def now(self):
        return self.t

    async def sleep(self, quanto):
        if quanto <= 0:
            # Un giro del loop costa comunque qualcosa.
            self.cessioni += 1
            self.t += 0.0002
            return
        self.dormite += 1
        self.chieste.append(round(quanto, 6))
        self.t += quanto * self.bugia


@pytest.mark.asyncio
async def test_the_barrier_holds_even_when_the_timer_lies():
    """
    §2/§4: nessuno passa prima della scadenza, chiunque menta sul tempo.

        LA SCADENZA È UN ORARIO, NON UNA DURATA.

    Il freno di prima chiedeva a `sleep` di aspettare otto millisecondi e si
    fidava. La barriera non si fida di niente: conosce un istante assoluto, e
    a ogni risveglio chiede soltanto se è ora.
    """
    from telephone.playback import (
        MIN_GAP_S, SHORT_NAP_S, YIELDS_BEFORE_A_REAL_NAP, PlaybackController,
    )

    orologio = OrologioBugiardo()

    async def send(_f):
        return None

    play = PlaybackController(
        send=send, external_clock=True,
        now=orologio.now, sleep=orologio.sleep,
    )

    partenza = orologio.now()
    scadenza = partenza + MIN_GAP_S
    await asyncio.wait_for(play._hold_until(scadenza), timeout=5)

    assert orologio.now() >= scadenza, (
        f"passata a {orologio.now() - partenza:.6f} s invece di {MIN_GAP_S}"
    )
    # E non è passata per un pelo dopo mille giri a vuoto.
    assert orologio.dormite + orologio.cessioni < 200, (
        orologio.dormite, orologio.cessioni
    )
    await play.close()


@pytest.mark.asyncio
async def test_a_deadline_already_passed_costs_nothing():
    """
    §7: quando i battiti arrivano regolari, la barriera non aspetta.

    Con la linea che batte ogni venti millisecondi la scadenza degli otto è
    passata da un pezzo: non si dorme, non si cede, non si aggiunge latenza.
    Se questa prova fallisse, il minimo anti-raffica sarebbe diventato il
    metronomo — che è esattamente quello che il §7 vieta.
    """
    from telephone.playback import PlaybackController

    orologio = OrologioBugiardo()

    async def send(_f):
        return None

    play = PlaybackController(
        send=send, external_clock=True,
        now=orologio.now, sleep=orologio.sleep,
    )
    prima = orologio.now()
    await play._hold_until(prima - 0.05)      # scaduta cinquanta ms fa

    assert orologio.now() == prima, "ha aspettato per niente"
    assert orologio.dormite == 0 and orologio.cessioni == 0
    await play.close()


@pytest.mark.asyncio
async def test_the_far_part_is_slept_and_the_last_part_is_yielded():
    """
    §3: si dorme la parte lontana, si cedono gli ultimi millisecondi.

    Dormire fino in fondo vorrebbe dire fidarsi del timer proprio dove non è
    affidabile; cedere fin dall'inizio vorrebbe dire mille giri per
    un'attesa lunga. La divisione è lì per questo.
    """
    from telephone.playback import PlaybackController, TOO_SHORT_TO_SLEEP_S

    orologio = OrologioBugiardo(bugia=1.0)     # un timer onesto, per una volta

    async def send(_f):
        return None

    play = PlaybackController(
        send=send, external_clock=True,
        now=orologio.now, sleep=orologio.sleep,
    )
    await play._hold_until(orologio.now() + 0.100)
    assert orologio.dormite >= 1, "non ha dormito la parte lontana"

    #     SOTTO LA SOGLIA NON SI CHIEDE PIU' «QUELLO CHE RESTA».
    #
    # La prova diceva «non si dorme affatto», e per un po' e' stata la cosa
    # giusta: cedere il controllo sembrava gratis. Al telefono non lo era —
    # un milione e mezzo di cessioni in settantanove secondi, e il filo audio
    # che arrivava tardi. Adesso sotto la soglia si dorme, ma di una misura
    # **fissa**: quello che non si fa piu' e' chiedere al timer una frazione
    # di cio' che manca, che e' la forma che non converge.
    from telephone.playback import SHORT_NAP_S

    prima = len(orologio.chieste)
    await play._hold_until(orologio.now() + TOO_SHORT_TO_SLEEP_S / 2)
    sotto_soglia = orologio.chieste[prima:]
    assert orologio.cessioni >= 1, "non ha ceduto il controllo"
    assert set(sotto_soglia) <= {SHORT_NAP_S}, (
        f"ha chiesto un'attesa calcolata sotto la soglia: {sotto_soglia}"
    )
    await play.close()


@pytest.mark.asyncio
async def test_a_backlog_is_drained_one_frame_at_a_time():
    """
    §6: venti crediti insieme non diventano venti pacchetti insieme.

        IL CREDITO DICE QUANTI. LA SCADENZA DICE QUANDO.

    Nessun credito si perde — il tempo logico è tutto lì — ma ogni pacchetto
    attraversa la barriera, quindi l'arretrato si smaltisce in fila invece che
    in una raffica.
    """
    from telephone.playback import MIN_GAP_S, PlaybackController

    uscite = []

    async def send(_f):
        uscite.append(time.perf_counter())
        await asyncio.sleep(0)

    play = PlaybackController(send=send, jitter_ms=0, external_clock=True)
    handle = play.begin(generation_id="g", turn_id=1)
    await play.feed(bytes(320 * 2 * 20), handle)
    for _ in range(20):
        play.tick()

    await asyncio.sleep(1.0)
    n = play.how_it_went()
    await play.close()

    assert len(uscite) == 20, f"{len(uscite)} pacchetti su 20 crediti"
    assert n["frames_dropped"] == 0
    assert n["intra_gaps_under_8ms"] == 0, n["intra_worst_ms"]
    assert n["longest_burst_run"] == 0
    assert n["intra_min_ms"] >= MIN_GAP_S * 1000 - 0.5, n["intra_min_ms"]
    assert n["beat_credits_produced"] == (
        n["beat_credits_consumed"]
        + n["beat_credits_pending"]
        + n["stale_credits_dropped_or_reconciled"]
    ), n


@pytest.mark.asyncio
async def test_waiting_is_not_spinning():
    """
    §3/§5: aspettare non vuol dire girare a vuoto sul processore.

    La barriera cede il controllo invece di occuparlo. Sul banco consuma meno
    del freno che sostituisce — 234 ms di processore contro 266 su cinque
    secondi — perché smette di chiedere attese che il sistema non onora.
    """
    from telephone.playback import PlaybackController

    async def send(_f):
        return None

    play = PlaybackController(send=send, external_clock=True)
    speso_prima = time.process_time()
    await play._hold_until(time.perf_counter() + 0.25)
    speso = time.process_time() - speso_prima
    await play.close()

    assert speso < 0.10, f"ha bruciato {speso*1000:.0f} ms per aspettarne 250"


# ---------------------------------------------------------------------------
# §11 · Il primo non è l'ultimo
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_first_onset_is_written_once_and_never_again(monkeypatch):
    """
    §11: due numeri, due significati.

        UNA METRICA CHE DICE UNA COSA DIVERSA DA COME SI CHIAMA È PEGGIO DI UNA
        METRICA ASSENTE.

    `first_human_onset_at_ms` riportava l'ultimo inizio di parlato. Sulla
    settima telefonata diceva 41 secondi — che come «primo» non ha senso, e
    infatti non lo era.
    """
    import numpy as np

    sess, wire, _, _ = await _aperta(monkeypatch)
    try:
        await _scalda_le_orecchie(sess)
        forte = (np.sin(np.arange(320) / 3.0) * 12000).astype("<i2").tobytes()

        for _ in range(8):
            await sess.hear(forte)
        primo = sess.how_it_went()["first_human_onset_at_ms"]
        assert primo is not None

        # Silenzio, e poi parlano di nuovo.
        for _ in range(60):
            await sess.hear(bytes(320 * 2))
        for _ in range(8):
            await sess.hear(forte)

        n = sess.how_it_went()
        assert n["first_human_onset_at_ms"] == primo, "il primo si è mosso"
        assert n["last_human_onset_at_ms"] >= primo
        assert n["speech_onsets_heard"] >= 2
    finally:
        await sess.close()


# ---------------------------------------------------------------------------
# §8/§9 · La barriera, con un orologio che diciamo noi
# ---------------------------------------------------------------------------

class OrologioBugiardo:
    """
    Un timer che promette un'attesa e non la mantiene.

        `SLEEP(8 MS)` SU QUESTA MACCHINA NE DORME 0,3.

    Non è un'invenzione per far passare una prova: è la misura della settima
    telefonata vera, dove il freno decideva 7,97 ms e otteneva 0,30. Qui quel
    comportamento è riprodotto in forma pura e deterministica — il tempo
    avanza di un decimo di quello che si chiede — così la proprietà della
    barriera si dimostra senza dipendere da come è fatto il sistema operativo
    di chi esegue le prove.
    """

    def __init__(self, bugia=0.1):
        self.t = 1000.0
        self.bugia = bugia
        self.dormite = 0
        self.cessioni = 0
        # Quanto e' stato chiesto, ogni volta. Serve a dimostrare che le
        # attese non si restringono verso lo zero — la forma che nel V3.13
        # produsse un ciclo che non tornava.
        self.chieste = []

    def now(self):
        return self.t

    async def sleep(self, quanto):
        if quanto <= 0:
            # Un giro del loop costa comunque qualcosa.
            self.cessioni += 1
            self.t += 0.0002
            return
        self.dormite += 1
        self.chieste.append(round(quanto, 6))
        self.t += quanto * self.bugia


@pytest.mark.asyncio
async def test_the_barrier_holds_even_when_the_timer_lies():
    """
    §2/§4: nessuno passa prima della scadenza, chiunque menta sul tempo.

        LA SCADENZA È UN ORARIO, NON UNA DURATA.

    Il freno di prima chiedeva a `sleep` di aspettare otto millisecondi e si
    fidava. La barriera non si fida di niente: conosce un istante assoluto, e
    a ogni risveglio chiede soltanto se è ora.
    """
    from telephone.playback import (
        MIN_GAP_S, SHORT_NAP_S, YIELDS_BEFORE_A_REAL_NAP, PlaybackController,
    )

    orologio = OrologioBugiardo()

    async def send(_f):
        return None

    play = PlaybackController(
        send=send, external_clock=True,
        now=orologio.now, sleep=orologio.sleep,
    )

    partenza = orologio.now()
    scadenza = partenza + MIN_GAP_S
    await asyncio.wait_for(play._hold_until(scadenza), timeout=5)

    assert orologio.now() >= scadenza, (
        f"passata a {orologio.now() - partenza:.6f} s invece di {MIN_GAP_S}"
    )
    # E non è passata per un pelo dopo mille giri a vuoto.
    assert orologio.dormite + orologio.cessioni < 200, (
        orologio.dormite, orologio.cessioni
    )
    #     E SMETTE DI CHIEDERE *QUELLO CHE RESTA* A CHI NON RISPONDE.
    #
    # Questa prova, la prima volta, non finiva: chiedendo sempre «resta meno
    # la soglia» a un timer che ne onora un decimo, l'attesa si avvicinava
    # alla soglia senza mai attraversarla. Un punto fisso, e un ciclo che non
    # torna. La correzione di allora fu passare a cedere il controllo.
    #
    #     CEDERE PERO' NON E' ASPETTARE, E SI E' SENTITO AL TELEFONO.
    #
    # `sleep(0)` torna subito quando non c'e' nessun altro pronto, e cederlo
    # fino alla scadenza e' un giro a vuoto travestito da buona educazione:
    # 1.549.103 cessioni in settantanove secondi di telefonata vera, con il
    # filo audio che arrivava tardi e il buco peggiore di quindici secondi.
    #
    # Adesso si cede un paio di volte — il caso in cui davvero c'e' qualcun
    # altro pronto — e poi si dorme di una quantita' **fissa**. Fissa e' la
    # parola: un pisolino che non si accorcia insieme a quello che resta non
    # puo' ricreare il punto fisso di allora, e costa un risveglio invece di
    # mille giri.
    assert orologio.cessioni <= YIELDS_BEFORE_A_REAL_NAP, (
        f"ha ceduto {orologio.cessioni} volte: e' tornato il giro a vuoto"
    )
    assert orologio.dormite >= 1, "non ha mai dormito davvero"
    #     E DOPO LA PRIMA BUGIA SI CHIEDE SEMPRE LA STESSA MISURA.
    #
    # E' la proprieta' che rende impossibile il ciclo che non torna, e vale la
    # pena guardarla direttamente invece di dedurla dal fatto che la prova
    # finisce. Scritta come `min(resta, SHORT_NAP_S)`, questa riga chiedeva
    # `resta` sotto i due millisecondi e lo vedeva restringersi del novanta
    # per cento a ogni giro — la prova non tornava piu', in due minuti.
    assert set(orologio.chieste[1:]) == {SHORT_NAP_S}, (
        f"le attese non sono fisse: {sorted(set(orologio.chieste))}"
    )
    await play.close()


@pytest.mark.asyncio
async def test_a_deadline_already_passed_costs_nothing():
    """
    §7: quando i battiti arrivano regolari, la barriera non aspetta.

    Con la linea che batte ogni venti millisecondi la scadenza degli otto è
    passata da un pezzo: non si dorme, non si cede, non si aggiunge latenza.
    Se questa prova fallisse, il minimo anti-raffica sarebbe diventato il
    metronomo — che è esattamente quello che il §7 vieta.
    """
    from telephone.playback import PlaybackController

    orologio = OrologioBugiardo()

    async def send(_f):
        return None

    play = PlaybackController(
        send=send, external_clock=True,
        now=orologio.now, sleep=orologio.sleep,
    )
    prima = orologio.now()
    await play._hold_until(prima - 0.05)      # scaduta cinquanta ms fa

    assert orologio.now() == prima, "ha aspettato per niente"
    assert orologio.dormite == 0 and orologio.cessioni == 0
    await play.close()


@pytest.mark.asyncio
async def test_the_far_part_is_slept_and_the_last_part_is_yielded():
    """
    §3: si dorme la parte lontana, si cedono gli ultimi millisecondi.

    Dormire fino in fondo vorrebbe dire fidarsi del timer proprio dove non è
    affidabile; cedere fin dall'inizio vorrebbe dire mille giri per
    un'attesa lunga. La divisione è lì per questo.
    """
    from telephone.playback import PlaybackController, TOO_SHORT_TO_SLEEP_S

    orologio = OrologioBugiardo(bugia=1.0)     # un timer onesto, per una volta

    async def send(_f):
        return None

    play = PlaybackController(
        send=send, external_clock=True,
        now=orologio.now, sleep=orologio.sleep,
    )
    await play._hold_until(orologio.now() + 0.100)
    assert orologio.dormite >= 1, "non ha dormito la parte lontana"

    #     SOTTO LA SOGLIA NON SI CHIEDE PIU' «QUELLO CHE RESTA».
    #
    # La prova diceva «non si dorme affatto», e per un po' e' stata la cosa
    # giusta: cedere il controllo sembrava gratis. Al telefono non lo era —
    # un milione e mezzo di cessioni in settantanove secondi, e il filo audio
    # che arrivava tardi. Adesso sotto la soglia si dorme, ma di una misura
    # **fissa**: quello che non si fa piu' e' chiedere al timer una frazione
    # di cio' che manca, che e' la forma che non converge.
    from telephone.playback import SHORT_NAP_S

    prima = len(orologio.chieste)
    await play._hold_until(orologio.now() + TOO_SHORT_TO_SLEEP_S / 2)
    sotto_soglia = orologio.chieste[prima:]
    assert orologio.cessioni >= 1, "non ha ceduto il controllo"
    assert set(sotto_soglia) <= {SHORT_NAP_S}, (
        f"ha chiesto un'attesa calcolata sotto la soglia: {sotto_soglia}"
    )
    await play.close()


@pytest.mark.asyncio
async def test_a_backlog_is_drained_one_frame_at_a_time():
    """
    §6: venti crediti insieme non diventano venti pacchetti insieme.

        IL CREDITO DICE QUANTI. LA SCADENZA DICE QUANDO.

    Nessun credito si perde — il tempo logico è tutto lì — ma ogni pacchetto
    attraversa la barriera, quindi l'arretrato si smaltisce in fila invece che
    in una raffica.
    """
    from telephone.playback import MIN_GAP_S, PlaybackController

    uscite = []

    async def send(_f):
        uscite.append(time.perf_counter())
        await asyncio.sleep(0)

    play = PlaybackController(send=send, jitter_ms=0, external_clock=True)
    handle = play.begin(generation_id="g", turn_id=1)
    await play.feed(bytes(320 * 2 * 20), handle)
    for _ in range(20):
        play.tick()

    await asyncio.sleep(1.0)
    n = play.how_it_went()
    await play.close()

    assert len(uscite) == 20, f"{len(uscite)} pacchetti su 20 crediti"
    assert n["frames_dropped"] == 0
    assert n["intra_gaps_under_8ms"] == 0, n["intra_worst_ms"]
    assert n["longest_burst_run"] == 0
    assert n["intra_min_ms"] >= MIN_GAP_S * 1000 - 0.5, n["intra_min_ms"]
    assert n["beat_credits_produced"] == (
        n["beat_credits_consumed"]
        + n["beat_credits_pending"]
        + n["stale_credits_dropped_or_reconciled"]
    ), n


@pytest.mark.asyncio
async def test_waiting_is_not_spinning():
    """
    §3/§5: aspettare non vuol dire girare a vuoto sul processore.

    La barriera cede il controllo invece di occuparlo. Sul banco consuma meno
    del freno che sostituisce — 234 ms di processore contro 266 su cinque
    secondi — perché smette di chiedere attese che il sistema non onora.
    """
    from telephone.playback import PlaybackController

    async def send(_f):
        return None

    play = PlaybackController(send=send, external_clock=True)
    speso_prima = time.process_time()
    await play._hold_until(time.perf_counter() + 0.25)
    speso = time.process_time() - speso_prima
    await play.close()

    assert speso < 0.10, f"ha bruciato {speso*1000:.0f} ms per aspettarne 250"


# ---------------------------------------------------------------------------
# §11 · Il primo non è l'ultimo
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_first_onset_is_written_once_and_never_again(monkeypatch):
    """
    §11: due numeri, due significati.

        UNA METRICA CHE DICE UNA COSA DIVERSA DA COME SI CHIAMA È PEGGIO DI UNA
        METRICA ASSENTE.

    `first_human_onset_at_ms` riportava l'ultimo inizio di parlato. Sulla
    settima telefonata diceva 41 secondi — che come «primo» non ha senso, e
    infatti non lo era.
    """
    import numpy as np

    sess, wire, _, _ = await _aperta(monkeypatch)
    try:
        await _scalda_le_orecchie(sess)
        forte = (np.sin(np.arange(320) / 3.0) * 12000).astype("<i2").tobytes()

        for _ in range(8):
            await sess.hear(forte)
        primo = sess.how_it_went()["first_human_onset_at_ms"]
        assert primo is not None

        # Silenzio, e poi parlano di nuovo.
        for _ in range(60):
            await sess.hear(bytes(320 * 2))
        for _ in range(8):
            await sess.hear(forte)

        n = sess.how_it_went()
        assert n["first_human_onset_at_ms"] == primo, "il primo si è mosso"
        assert n["last_human_onset_at_ms"] >= primo
        assert n["speech_onsets_heard"] >= 2
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_the_barrier_survives_a_timer_that_does_not_sleep_at_all():
    """
    §2: il caso estremo, che è anche il più istruttivo.

    Un timer che torna sempre subito è la forma pura del difetto misurato. La
    barriera non ci deve cascare né restarci appesa: cede il controllo finché
    l'orario non arriva, e arriva.
    """
    from telephone.playback import MIN_GAP_S, PlaybackController

    orologio = OrologioBugiardo(bugia=0.0)      # non dorme mai, per niente

    async def send(_f):
        return None

    play = PlaybackController(
        send=send, external_clock=True,
        now=orologio.now, sleep=orologio.sleep,
    )
    partenza = orologio.now()
    await asyncio.wait_for(
        play._hold_until(partenza + MIN_GAP_S), timeout=5,
    )
    assert orologio.now() >= partenza + MIN_GAP_S
    assert orologio.cessioni > 0, "non ha mai ceduto il controllo"
    await play.close()
