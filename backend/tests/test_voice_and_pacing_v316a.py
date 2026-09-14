"""
Quale voce ha parlato, e perché il filo andava a scatti.

    `opening_voice=Kore` REGISTRAVA UN DESIDERIO, NON UN FATTO.

Su una telefonata vera la voce è cambiata a metà, da femminile a maschile, e
l'unico campo che parlava di voce diceva «Kore» — perché registrava la
configurazione richiesta, non quella accettata. Qui si tiene fermo che la
traccia dica invece che cosa è uscito davvero: quale credenziale, quale
modello, e se la voce è stata messa nel messaggio di apertura.

    E CEDERE IL CONTROLLO NON È ASPETTARE.

Sulla stessa telefonata: 1.549.103 cessioni cooperative in settantanove
secondi, 459 attese su 513 tornate presto, e un buco di quindici secondi fra
due pacchetti. `sleep(0)` torna subito quando non c'è nessun altro pronto, e
chiamarlo fino alla scadenza è un giro a vuoto travestito da buona educazione
— che affama proprio chi deve leggere il filo audio.

Queste prove tengono ferme le due proprietà che contano insieme: nessuno passa
prima della scadenza, e nessuno gira a vuoto per arrivarci.
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ---------------------------------------------------------------------------
# 1 · Chi ha aperto la sessione, e con quale voce dentro
# ---------------------------------------------------------------------------

def test_the_credential_slot_is_named_never_shown(monkeypatch):
    """
    Si registra quale chiave, mai la chiave.

    Un rapporto che porta una credenziale è un rapporto che non si può
    incollare da nessuna parte, e questi numeri servono proprio per essere
    incollati in una discussione.
    """
    from telephone.live import _key, _key_slot

    monkeypatch.setenv("GEMINI2_API_KEY", "chiave-due")
    monkeypatch.setenv("GEMINI_API_KEY", "chiave-uno")
    assert _key_slot() == "gemini2"
    assert _key() == "chiave-due"
    assert "chiave" not in _key_slot()

    monkeypatch.delenv("GEMINI2_API_KEY")
    assert _key_slot() == "gemini"
    assert _key() == "chiave-uno"

    monkeypatch.delenv("GEMINI_API_KEY")
    assert _key_slot() == ""
    assert _key() == ""


def test_the_slot_does_not_follow_the_llm_manager(monkeypatch):
    """
        DUE SOTTOSISTEMI CHE CONDIVIDONO UN PREFISSO NON SONO LO STESSO.

    Subito prima della telefonata in cui la voce è cambiata, il manager LLM
    aveva messo `gemini` in castigo per quota ed era passato a `gemini2`. È
    stata la prima cosa sospettata — e non c'entra: questa scelta preferisce
    `gemini2` **sempre**, non guarda lo stato di nessun fornitore, e faceva
    così anche nella telefonata riuscita di prima.

    Se un giorno qualcuno la legasse davvero allo stato del manager, questa
    prova diventerebbe rossa — ed è esattamente quello che deve fare.
    """
    import inspect

    from telephone import live

    sorgente = inspect.getsource(live._key) + inspect.getsource(live._key_slot)
    for indizio in ("manager", "cooldown", "quota", "failure", "provider"):
        assert indizio not in sorgente.lower(), (
            f"la scelta della credenziale guarda «{indizio}»"
        )


def test_both_slots_open_exactly_the_same_live_session(monkeypatch):
    """
    §1: `gemini` e `gemini2` hanno la stessa configurazione Live?

    Sì, e non per disciplina: per costruzione. Modello, voce e modalità
    vengono da variabili d'ambiente che non sanno quale chiave aprirà il filo,
    quindi l'unica differenza fra i due slot è quale progetto Google paga.
    """
    from telephone.live import _how_she_sounds, _model

    monkeypatch.setenv("GEMINI_LIVE_MODEL", "un-modello")
    monkeypatch.setenv("GEMINI_LIVE_VOICE", "Kore")

    monkeypatch.setenv("GEMINI2_API_KEY", "due")
    monkeypatch.setenv("GEMINI_API_KEY", "uno")
    con_due = (_model(), _how_she_sounds())

    monkeypatch.delenv("GEMINI2_API_KEY")
    con_uno = (_model(), _how_she_sounds())

    assert con_due == con_uno, "i due slot aprirebbero sessioni diverse"
    assert con_due[1]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"][
        "voiceName"] == "Kore"


def test_no_voice_asked_means_no_voice_sent(monkeypatch):
    """Senza preferenza non si manda `speechConfig`, e il modello usa la sua."""
    from telephone.live import _how_she_sounds

    monkeypatch.setenv("GEMINI_LIVE_VOICE", "")
    suona = _how_she_sounds()
    assert "speechConfig" not in suona
    assert suona["responseModalities"] == ["AUDIO"]


def test_what_the_server_says_is_written_down_by_shape_only():
    """
        LA FORMA SÌ, IL CONTENUTO MAI.

    `goAway` e `sessionResumptionUpdate` sono i due messaggi che spiegherebbero
    una voce cambiata a metà, e li stavamo lasciando cadere senza contarli. Si
    annotano — ma di un messaggio del server si registrano le chiavi e i tipi,
    non quello che c'è dentro, perché lì possono esserci parole di una
    telefonata.
    """
    from telephone.live import _WHAT_WE_KNOW, _just_the_shape

    assert "goAway" in _WHAT_WE_KNOW
    assert "sessionResumptionUpdate" in _WHAT_WE_KNOW

    forma = _just_the_shape({"newHandle": "abc-segreto", "resumable": True})
    assert forma == {"newHandle": "str", "resumable": "bool"}
    assert "abc-segreto" not in str(forma)


def test_the_trace_survives_a_session_that_never_opened():
    """
    Una sessione che non si apre deve comunque poter raccontare perché.

    È il caso in cui la traccia serve di più, ed è quello in cui è più facile
    che non ci sia.
    """
    from telephone.live import MissionVoiceSession

    async def send(_f):
        return None

    sess = MissionVoiceSession(None, owner_id="u1", session_ref="s", send=send)
    numeri = sess.how_it_went()
    # Nessuna eccezione, e i campi della traccia semplicemente non ci sono
    # ancora: il resoconto resta leggibile.
    assert numeri["runtime"] == "gemini_live"
    assert numeri["server_announcements"] == []
    assert numeri["server_messages_not_understood"] == []


# ---------------------------------------------------------------------------
# 2 · Il passo: nessuno prima della scadenza, nessuno a vuoto
# ---------------------------------------------------------------------------

class OrologioDiWindows:
    """
    Un timer che torna presto, come quello vero.

        `SLEEP(8 MS)` SU QUELLA MACCHINA NE DORME 0,3.

    Riprodotto in forma pura: si onora un decimo di quello che si chiede. È la
    condizione che faceva degenerare la barriera in un giro a vuoto, quindi è
    la condizione in cui va misurata.
    """

    def __init__(self, onora=0.1):
        self.t = 1000.0
        self.onora = onora
        self.dormite = 0
        self.cessioni = 0
        self.chieste = []

    def now(self):
        return self.t

    async def sleep(self, quanto):
        #     UN'ATTESA FINTA CHE NON CEDE NON È UN'ATTESA.
        # `asyncio.sleep` passa sempre dal loop, anche con zero. Un banco che
        # non lo fa misura un mondo in cui nessun altro esiste — e la cosa in
        # esame qui è proprio se gli altri riescono a lavorare.
        await asyncio.sleep(0)
        if quanto <= 0:
            self.cessioni += 1
            #     UN GIRO A VUOTO COSTA CINQUE MICROSECONDI, NON CINQUANTA.
            # E' il numero che rende la misura onesta: con cinque microsecondi
            # per cessione, coprire otto millisecondi cedendo vuol dire
            # milleseicento giri — che e' l'ordine di grandezza misurato sulla
            # telefonata vera, 1.549.103 in settantanove secondi. Con un costo
            # dieci volte piu' generoso il difetto sembrerebbe dieci volte piu'
            # piccolo di com'e'.
            self.t += 0.000005
            return
        self.dormite += 1
        self.chieste.append(round(quanto, 6))
        self.t += quanto * self.onora


def _un_controllore(orologio):
    from telephone.playback import PlaybackController

    async def send(_f):
        return None

    return PlaybackController(
        send=send, external_clock=True,
        now=orologio.now, sleep=orologio.sleep,
    )


@pytest.mark.asyncio
async def test_ninety_seconds_of_pacing_do_not_spin():
    """
    Novanta secondi di telefonata, contati barriera per barriera.

        IL COSTO NON È IL PROCESSORE: È CHI NON RIESCE A LEGGERE IL FILO.

    Fra una cessione e l'altra il loop deve passare da chi legge l'audio in
    arrivo. Con ventimila passaggi al secondo quella lettura arriva tardi, e
    sulla telefonata vera il buco peggiore fra due pacchetti è stato di
    quindici secondi.

    Qui si simula il numero di barriere di una chiamata di novanta secondi —
    una ogni venti millisecondi — e si guarda quanto costa arrivarci.
    """
    from telephone.playback import MIN_GAP_S

    orologio = OrologioDiWindows()
    play = _un_controllore(orologio)

    quante = 90 * 50          # novanta secondi a cinquanta frame al secondo
    for _ in range(quante):
        await play._hold_until(orologio.now() + MIN_GAP_S)
    await play.close()

    per_barriera = orologio.cessioni / quante
    assert per_barriera <= 3, (
        f"{orologio.cessioni} cessioni in {quante} barriere "
        f"({per_barriera:.1f} per barriera): è tornato il giro a vuoto"
    )
    #     E IL NUMERO DELLA TELEFONATA VERA NON DEVE PIÙ SUCCEDERE.
    # Là erano 1.549.103 in settantanove secondi. Qui, per una chiamata più
    # lunga, il tetto è tre ordini di grandezza sotto.
    assert orologio.cessioni < 20_000, orologio.cessioni


@pytest.mark.asyncio
async def test_nobody_ever_passes_before_the_deadline():
    """
        LA BARRIERA PROMETTE «NON PRIMA», E QUESTA È LA PROMESSA.

    Il passo si può alleggerire quanto si vuole, ma non a costo di lasciar
    passare un pacchetto in anticipo: è così che nasce la raffica, ed è il
    difetto che si sente dall'altra parte.
    """
    from telephone.playback import MIN_GAP_S

    for onora in (0.001, 0.1, 0.5, 1.0, 2.0):
        orologio = OrologioDiWindows(onora)
        play = _un_controllore(orologio)
        for _ in range(50):
            scadenza = orologio.now() + MIN_GAP_S
            await asyncio.wait_for(play._hold_until(scadenza), timeout=5)
            assert orologio.now() >= scadenza, (
                f"passata in anticipo con un timer che onora {onora}"
            )
        await play.close()


@pytest.mark.asyncio
async def test_a_dead_timer_does_not_hang_the_barrier():
    """
    Un orologio che non si muove per niente.

    Non esiste su una macchina vera, ma se esistesse restare appesi sarebbe
    peggio di qualunque imprecisione. Oltre un tetto di giri si torna a cedere
    il controllo, che è l'unica cosa che fa progredire un loop comunque sia
    fatto l'orologio.
    """
    from telephone.playback import MIN_GAP_S

    orologio = OrologioDiWindows(onora=0.0)
    play = _un_controllore(orologio)
    partenza = orologio.now()
    await asyncio.wait_for(
        play._hold_until(partenza + MIN_GAP_S), timeout=5)
    assert orologio.now() >= partenza + MIN_GAP_S
    await play.close()


@pytest.mark.asyncio
async def test_the_event_loop_still_gets_a_turn():
    """
    Chi legge il filo audio deve poter lavorare mentre la barriera trattiene.

        È LA REGRESSIONE, DETTA AL CONTRARIO.

    Il giro a vuoto non era lento: era avaro. Teneva il loop occupato a
    richiedere l'ora invece di lasciare che qualcun altro leggesse un
    pacchetto. Qui c'è un compito che conta i propri turni mentre la barriera
    aspetta: se non ne ottiene, la barriera sta di nuovo affamando la linea.
    """
    from telephone.playback import MIN_GAP_S

    orologio = OrologioDiWindows()
    play = _un_controllore(orologio)
    turni = 0
    fermati = False

    async def chi_legge_il_filo():
        nonlocal turni
        while not fermati:
            turni += 1
            await asyncio.sleep(0)

    altro = asyncio.create_task(chi_legge_il_filo())
    for _ in range(200):
        await play._hold_until(orologio.now() + MIN_GAP_S)
    fermati = True
    await altro
    await play.close()

    assert turni >= 200, (
        f"chi legge il filo ha avuto solo {turni} turni in 200 barriere"
    )
    #     E IL PREZZO DI UN TURNO È QUELLO CHE CONTA.
    # Cedere il controllo dà un turno anche a chi gira a vuoto: la differenza
    # è quanti giri della barriera ci stanno in mezzo. Con mille giri per
    # barriera chi legge il filo viene servito mille volte più tardi, ed è
    # esattamente il ritardo che si è sentito.
    #     E IL CONTO SI FA, NON SI SPERA.
    # Con un timer che onora un decimo, un pisolino fisso da due millisecondi
    # avanza di 0,2 ms per volta: per coprirne otto ne servono una quarantina.
    # Cedendo il controllo, a cinque microsecondi per giro, ne servirebbero
    # milleseicento. Il tetto sta in mezzo, vicino al conto giusto.
    giri_barriera = orologio.cessioni + orologio.dormite
    per_barriera = giri_barriera / 200
    assert per_barriera <= 60, (
        f"{per_barriera:.0f} giri per barriera: chi legge il filo aspetta"
    )
    # E il confronto con quello che sarebbe stato cedendo fino in fondo.
    cedendo = MIN_GAP_S / 0.000005
    assert per_barriera < cedendo / 20, (
        f"{per_barriera:.0f} giri contro i {cedendo:.0f} del giro a vuoto: "
        "il guadagno non c'e'"
    )


@pytest.mark.asyncio
async def test_holding_can_be_cancelled_cleanly():
    """
    Chiudere la telefonata mentre la barriera trattiene non lascia niente.

    È il percorso dello spegnimento, e un'attesa che non si lascia cancellare
    è un processo che non si lascia fermare.
    """
    from telephone.playback import PlaybackController

    async def send(_f):
        return None

    dorme = asyncio.Event()

    async def sleep_lungo(_quanto):
        dorme.set()
        await asyncio.sleep(3600)

    play = PlaybackController(
        send=send, external_clock=True,
        now=lambda: 1000.0, sleep=sleep_lungo,
    )
    attesa = asyncio.create_task(play._hold_until(1000.0 + 5.0))
    await asyncio.wait_for(dorme.wait(), timeout=2)

    attesa.cancel()
    with pytest.raises(asyncio.CancelledError):
        await attesa
    assert attesa.cancelled()
    await play.close()


def test_the_counters_say_which_strategy_was_used():
    """
    I numeri del resoconto devono distinguere un'attesa da un giro a vuoto.

    Senza un contatore separato per i pisolini, la correzione sarebbe
    invisibile nel rapporto della prossima telefonata vera — e allora non
    sarebbe verificabile.
    """
    from telephone.playback import PlaybackController

    async def send(_f):
        return None

    play = PlaybackController(send=send, external_clock=True)
    numeri = play.how_it_went()
    for campo in ("cooperative_yield_count", "coarse_sleep_count",
                  "timer_lie_detected_count", "short_nap_count",
                  "longest_burst_run"):
        assert campo in numeri, campo


def test_the_short_nap_is_a_fixed_measure():
    """
        UNA MISURA FISSA NON PUÒ CONVERGERE.

    Scritta come «quello che resta», questa attesa ha ricreato in due minuti
    il difetto del V3.13: sotto la soglia chiedeva una frazione di ciò che
    mancava, il timer ne onorava un decimo, e il ciclo non tornava più. La
    costante esiste perché quella forma non si possa riscrivere per sbaglio.
    """
    import inspect

    from telephone import playback

    assert isinstance(playback.SHORT_NAP_S, float)
    assert 0 < playback.SHORT_NAP_S <= playback.MIN_GAP_S
    #     UNA GUARDIA CHE LEGGE I COMMENTI MISURA LA PROSA, NON IL CODICE.
    # Qui sopra, nel file vero, quella forma è citata apposta per spiegare
    # perché non si usa: senza questa riga la guardia si accenderebbe sulla
    # spiegazione del difetto invece che sul difetto.
    codice = " ".join(
        riga.split("#")[0]
        for riga in inspect.getsource(
            playback.PlaybackController._hold_until).splitlines()
    )
    assert "min(resta" not in codice, (
        "l'attesa è tornata a dipendere da quanto manca"
    )
