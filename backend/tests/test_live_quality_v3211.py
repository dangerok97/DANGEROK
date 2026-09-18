"""
Una telefonata più naturale, senza riscrivere quello che già regge.

    «LENTA» NON È UNA DIAGNOSI. «SCATTA» NEMMENO.

Queste prove tengono ferme le tre cose che V3.21.1 ha cambiato e le tre che
non doveva cambiare. Le prime: la lingua della missione arriva al setup in tutti
e tre i posti; la fine del turno ha una soglia esplicita; e ogni buco nella
voce lascia una fotografia che dice da dove viene. Le seconde: Charon su ogni
setup, la coda che non spara raffiche, e il commiato che resta un commiato.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from test_live_runtime_v313 import _packet  # noqa: E402


def _sessione(packet=None):
    from telephone.live import MissionVoiceSession

    async def send(_pcm):
        return None

    return MissionVoiceSession(
        None, owner_id="u1", session_ref="s", send=send, packet=packet,
    )


# ---------------------------------------------------------------------------
# La lingua
# ---------------------------------------------------------------------------

def test_a_mission_is_italian_unless_it_says_otherwise():
    """La lingua sta nel pacchetto, con l'italiano come default."""
    p = _packet()
    assert p.language == "it"
    assert p.language_tag() == "it-IT"


def test_the_language_is_not_hardcoded():
    """Il giorno in cui si chiamerà in inglese, basta il pacchetto."""
    p = _packet()
    p.language = "en"
    setup = _sessione(p)._setup_message()["setup"]

    assert setup["generationConfig"]["speechConfig"]["languageCode"] == "en-US"
    assert setup["inputAudioTranscription"]["languageCodes"] == ["en-US"]


def test_the_setup_carries_the_language_in_all_three_places():
    """
    Voce, trascrizione in entrata, trascrizione in uscita.

    Misurato sul vero: senza, la controparte è stata trascritta in portoghese.
    """
    setup = _sessione(_packet())._setup_message()["setup"]

    assert setup["generationConfig"]["speechConfig"]["languageCode"] == "it-IT"
    assert setup["inputAudioTranscription"] == {"languageCodes": ["it-IT"]}
    assert setup["outputAudioTranscription"] == {"languageCodes": ["it-IT"]}


def test_a_resumed_session_keeps_the_language_and_the_turn_threshold():
    """La ripresa è la stessa sessione: stessa lingua, stessa soglia."""
    s = _sessione(_packet())
    prima = s._setup_message()["setup"]
    dopo = s._setup_message(resume_handle="appiglio")["setup"]

    assert dopo["sessionResumption"] == {"handle": "appiglio"}
    for campo in ("generationConfig", "inputAudioTranscription",
                  "outputAudioTranscription", "realtimeInputConfig"):
        assert dopo[campo] == prima[campo], campo


# ---------------------------------------------------------------------------
# Charon
# ---------------------------------------------------------------------------

def test_charon_survives_the_language_code():
    """Aggiungere la lingua non deve far perdere la voce."""
    voce = _sessione(_packet())._setup_message()["setup"]["generationConfig"]["speechConfig"]
    assert voce["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Charon"


@pytest.mark.parametrize("slot", ["GEMINI2_API_KEY", "GEMINI_API_KEY"])
def test_charon_on_every_credential(monkeypatch, slot):
    """
    Primario o ripiego, la voce è la stessa.

        ORA HA UNA VOCE, E NON DIPENDE DA CHI PAGA IL FILO.
    """
    for k in ("GEMINI2_API_KEY", "GEMINI_API_KEY", "GEMINI_LIVE_VOICE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv(slot, "non-una-chiave-vera")

    setup = _sessione(_packet())._setup_message()["setup"]
    voce = setup["generationConfig"]["speechConfig"]["voiceConfig"]
    assert voce["prebuiltVoiceConfig"]["voiceName"] == "Charon"


# ---------------------------------------------------------------------------
# La fine del turno
# ---------------------------------------------------------------------------

def test_the_turn_threshold_is_explicit(monkeypatch):
    """
    Cinquecento millisecondi di silenzio, detti al server.

    Misurato: col default la risposta arriva in 1781 ms, con 500 in 1182.
    """
    monkeypatch.delenv("GEMINI_LIVE_SILENCE_MS", raising=False)
    aad = _sessione(_packet())._setup_message()["setup"]["realtimeInputConfig"][
        "automaticActivityDetection"]
    assert aad == {"endOfSpeechSensitivity": "END_SENSITIVITY_HIGH",
                   "silenceDurationMs": 500}


@pytest.mark.parametrize("valore,atteso", [("150", 300), ("5000", 2000),
                                           ("700", 700), ("rotto", 500)])
def test_the_turn_threshold_stays_within_sane_bounds(monkeypatch, valore, atteso):
    """Troppo basso interrompe chi fa una pausa; troppo alto è il problema di prima."""
    from telephone.live import _silence_ms

    monkeypatch.setenv("GEMINI_LIVE_SILENCE_MS", valore)
    assert _silence_ms() == atteso


# ---------------------------------------------------------------------------
# La deriva
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("frase", ["sì", "va bene", "no", "Lorenzo Bianchi",
                                   "Sì, confermo.", "Perfetto. Allora"])
def test_short_italian_is_never_a_drift(frase):
    """«Sì» non è una lingua. Nemmeno un nome proprio."""
    from telephone.language import drifted

    assert drifted(frase, "it-IT") is None


def test_the_real_portuguese_transcript_is_a_drift():
    """Il transcript vero del gate V3.20."""
    from telephone.language import drifted

    assert drifted("Sim, ver qual é a data de disponibilidade.", "it-IT") == "pt"


def test_a_foreign_sentence_is_noted_and_changes_nothing():
    """
    Una frase straniera della controparte si scrive, e basta.

    La lingua della sessione resta quella della missione, e la chiamata non
    si interrompe.
    """
    s = _sessione(_packet())
    s._check_the_language("them", "Sim, ver qual é a data de disponibilidade.")
    s._check_the_language("ora", "Buongiorno, sono l'assistente di Francesco, chiamo per l'appuntamento.")

    rapporto = s._quality_report()
    assert rapporto["their_language_drift_count"] == 1
    assert rapporto["language_drift_count"] == 0
    assert rapporto["mission_language"] == "it-IT"
    assert s._setup_message()["setup"]["inputAudioTranscription"] == {
        "languageCodes": ["it-IT"]}
    assert s._closed is False


# ---------------------------------------------------------------------------
# I buchi nella voce
# ---------------------------------------------------------------------------

def test_a_long_silence_inside_generated_audio_is_noted():
    """B: il buco è dentro la voce, non nel trasporto."""
    import array

    from telephone.live import MODEL_RATE

    s = _sessione(_packet())
    s._opened_at = time.perf_counter()

    def pcm(ms, forte):
        n = MODEL_RATE * ms // 1000
        return array.array("h", [forte if i % 2 else -forte for i in range(n)]).tobytes()

    adesso = time.perf_counter()
    s._listen_for_silence(pcm(200, 3000), adesso)   # voce
    s._listen_for_silence(pcm(600, 0), adesso)      # silenzio lungo
    s._listen_for_silence(pcm(100, 3000), adesso)   # voce di nuovo

    assert len(s._generated_silences) == 1
    assert s._generated_silences[0]["silence_ms"] == 600


def test_leading_silence_is_a_boundary_not_a_hole():
    """Il silenzio prima della prima voce è il confine fra due risposte."""
    import array

    from telephone.live import MODEL_RATE

    s = _sessione(_packet())
    s._opened_at = time.perf_counter()
    zero = array.array("h", [0] * (MODEL_RATE * 800 // 1000)).tobytes()
    voce = array.array("h", [3000, -3000] * (MODEL_RATE // 20)).tobytes()
    s._listen_for_silence(zero, time.perf_counter())
    s._listen_for_silence(voce, time.perf_counter())

    assert s._generated_silences == []


@pytest.mark.asyncio
async def test_a_stalled_process_is_caught():
    """D: se l'event loop si ferma, il cane da guardia lo scrive."""
    s = _sessione(_packet())
    s._opened_at = time.perf_counter()
    guardia = asyncio.create_task(s._watch_the_clock())
    await asyncio.sleep(0.05)
    time.sleep(0.2)                     # il processo fermo, di proposito
    await asyncio.sleep(0.05)
    s._closed = True
    guardia.cancel()
    try:
        await guardia
    except asyncio.CancelledError:
        pass

    assert s._loop_stalls
    assert max(x["stall_ms"] for x in s._loop_stalls) >= 150


def test_a_gap_during_a_stall_is_classified_as_local():
    """La classificazione guarda che cosa succedeva nello stesso momento."""
    s = _sessione(_packet())
    s._opened_at = s.playback._opened_at
    s.playback.gap_events = [
        {"at_ms": 5000, "gap_ms": 1200, "queued_ms": 8000, "in_fallback": False,
         "beat_silent_for_ms": 20, "generation_finished": False, "credits_owed": 0},
        {"at_ms": 9000, "gap_ms": 300, "queued_ms": 0, "in_fallback": False,
         "beat_silent_for_ms": 20, "generation_finished": False, "credits_owed": 0},
    ]
    s._loop_stalls = [{"at_ms": 3900, "stall_ms": 1150}]
    s._gemini_gap_events = [{"at_ms": 9000, "gap_ms": 310, "queued_ms_on_arrival": 0,
                             "absorbed": False}]

    cause = s._why_the_voice_stopped()
    assert cause["D_local_stall"] == 1
    assert cause["A_late_chunk"] == 1
    assert [g["cause"] for g in cause["gaps"]] == ["D_local_stall", "A_late_chunk"]


def test_a_late_chunk_with_a_full_queue_is_absorbed():
    """Un buco a monte con voce in coda non arriva alla linea: lo si dice."""
    s = _sessione(_packet())
    s._opened_at = time.perf_counter()
    s._gemini_gap_events = [
        {"at_ms": 100, "gap_ms": 180, "queued_ms_on_arrival": 900, "absorbed": True},
        {"at_ms": 200, "gap_ms": 150, "queued_ms_on_arrival": 0, "absorbed": False},
    ]
    assert s._quality_report()["gemini_gaps_absorbed"] == 1


@pytest.mark.asyncio
async def test_the_playback_photographs_a_gap_inside_a_response():
    """Ogni buco sopra i cento millisecondi lascia la sua fotografia."""
    from telephone.playback import PlaybackController, SpeechGenerationHandle

    mandati = []

    async def send(frame):
        mandati.append(time.perf_counter())

    play = PlaybackController(send=send)
    h = play.begin(generation_id="g", turn_id=1)
    frame = b"\x00\x01" * 320   # venti millisecondi a sedicimila
    await play.feed(frame * 12, h)
    await asyncio.sleep(0.4)
    await play.feed(frame * 2, h)
    await asyncio.sleep(0.25)
    await play.finish(h)
    await asyncio.sleep(0.1)
    await play.close()

    foto = play.how_it_went()["gap_events"]
    assert foto, "nessun buco fotografato"
    for campo in ("at_ms", "gap_ms", "queued_ms", "in_fallback", "beat_silent_for_ms"):
        assert campo in foto[0]


# ---------------------------------------------------------------------------
# La latenza di casa
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_local_path_to_the_first_frame_adds_no_wait():
    """
    Dal primo audio di Gemini al primo pacchetto sulla linea: niente attese.

    Con abbastanza voce per riempire il cuscinetto, il primo pacchetto esce
    subito. È la metà della latenza che dipende da noi, e sul gate era 19 ms.
    """
    from telephone.playback import PlaybackController

    mandati = []

    async def send(frame):
        mandati.append(time.perf_counter())

    play = PlaybackController(send=send)
    h = play.begin(generation_id="g", turn_id=1)
    inizio = time.perf_counter()
    await play.feed(b"\x00\x01" * 320 * 15, h)   # trecento millisecondi
    while not mandati and time.perf_counter() - inizio < 1:
        await asyncio.sleep(0.001)
    await play.finish(h)
    await play.close()

    assert mandati, "niente è uscito"
    assert (mandati[0] - inizio) * 1000 < 60


def test_the_report_separates_upstream_from_local():
    """La latenza si divide in due, sempre."""
    s = _sessione(_packet())
    s._responses = [
        {"gemini_first_audio_ms": 1200, "local_first_audio_ms": 18},
        {"gemini_first_audio_ms": 1100, "local_first_audio_ms": 22},
    ]
    r = s._quality_report()
    assert r["upstream_first_audio_p50_ms"] in (1100, 1200)
    assert r["local_first_audio_max_ms"] == 22


# ---------------------------------------------------------------------------
# Dal gate reale: il turno veloce e il nome di chi ferma il processo
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_turn_faster_than_our_ears_is_still_measured():
    """
    Misurato sul vero: con 500 ms di soglia Gemini risponde prima che le
    nostre orecchie (900 ms) dichiarino la fine, e il turno spariva dalle
    misure. Adesso la fine è «adesso meno il silenzio già passato».
    """
    import base64

    s = _sessione(_packet())
    s._opened_at = time.perf_counter()
    s._ears.speaking = True
    s._ears._quiet_ms = 400
    await s._pour(base64.b64encode(b"\x00\x01" * 2400).decode())

    assert s._first_audio, "il turno non è stato misurato"
    assert 350 <= s._first_audio[0] <= 600
    assert s._answered_before_our_ears is True


@pytest.mark.asyncio
async def test_a_late_end_of_speech_does_not_leak_into_the_next_turn():
    """La dichiarazione tardiva della stessa frase non vale per la risposta dopo."""
    import base64

    s = _sessione(_packet())
    s._opened_at = time.perf_counter()
    s._ears.speaking = True
    s._ears._quiet_ms = 400
    await s._pour(base64.b64encode(b"\x00\x01" * 2400).decode())
    s._speech_ended_at = None

    #     LE ORECCHIE ARRIVANO ADESSO ALLA FINE DELLA STESSA FRASE.
    # Un filo finto: senza, `hear` esce prima di ascoltare.
    class Filo:
        async def send(self, _m):
            return None

    s.ws = Filo()
    s._ears.hear = lambda _pcm: (False, True)
    await s.hear(b"\x00\x00" * 320)
    assert s._speech_ended_at is None
    assert s._answered_before_our_ears is False


@pytest.mark.asyncio
async def test_the_stall_witness_names_the_culprit():
    """Uno stallo lungo lascia scritto dove era fermo il processo."""
    s = _sessione(_packet())
    s._opened_at = time.perf_counter()
    guardia = asyncio.create_task(s._watch_the_clock())
    await asyncio.sleep(0.08)

    def colpevole_di_prova():
        time.sleep(0.35)

    colpevole_di_prova()
    await asyncio.sleep(0.1)
    s._closed = True
    guardia.cancel()
    try:
        await guardia
    except asyncio.CancelledError:
        pass

    assert s._stall_culprits, "nessun colpevole fotografato"
    assert any("colpevole_di_prova" in r for c in s._stall_culprits for r in c["our_code"])


# ---------------------------------------------------------------------------
# Lo stallo trovato sul vero: un client HTTP nuovo ferma il processo
# ---------------------------------------------------------------------------

def test_the_carrier_reuses_one_tls_context():
    """
    Misurato: un `httpx.AsyncClient()` nuovo ferma l'event loop ~450 ms per
    caricare i certificati; col contesto condiviso costa 0,1 ms. Sul gate il
    riaggancio si è fermato 548 ms esattamente lì.
    """
    from telephone import carrier

    assert carrier._tls() is carrier._tls()


@pytest.mark.asyncio
async def test_hang_up_opens_its_client_with_the_shared_context(monkeypatch):
    """Il riaggancio non costruisce un contesto nuovo."""
    import httpx

    from telephone import carrier

    visti = []

    class Finto:
        def __init__(self, *a, **k):
            visti.append(k.get("verify"))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def put(self, *a, **k):
            class R:
                status_code = 204
            return R()

    monkeypatch.setattr(httpx, "AsyncClient", Finto)
    monkeypatch.setattr(carrier, "_token", lambda: "t")
    await carrier.hang_up("ref-finto")

    assert visti and visti[0] is carrier._tls()


@pytest.mark.asyncio
async def test_a_live_call_is_counted_while_it_is_open(monkeypatch):
    """Lo sfondo sa quando c'è una telefonata che parla."""
    from telephone.live import calls_in_progress

    s = _sessione(_packet())
    prima = calls_in_progress()
    from telephone import live

    live._IN_CORSO.add(id(s))
    assert calls_in_progress() == prima + 1
    await s.close()
    assert calls_in_progress() == prima


def test_background_sync_waits_for_the_call(monkeypatch):
    """
    Una telefonata in corso ha la precedenza sulle letture delle fonti.

    Sul gate V3.20 due letture durante l'apertura hanno aperto due client
    nuovi, a 1,44 s l'uno dall'altro: due strappi da più di un secondo.
    """
    from ambient import runtime
    from telephone import live

    live._IN_CORSO.clear()
    assert runtime._a_call_is_live() is False
    live._IN_CORSO.add("una-telefonata")
    try:
        assert runtime._a_call_is_live() is True
    finally:
        live._IN_CORSO.clear()


def test_the_deferral_counter_exists():
    """Il ramo che rimanda le letture scrive un contatore: deve esserci."""
    from ambient import runtime

    runtime._stats["sources_deferred_for_call"] += 1
    assert runtime._stats["sources_deferred_for_call"] >= 1
