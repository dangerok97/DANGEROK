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


def test_no_session_ever_starts_without_saying_how_to_sound(monkeypatch):
    """
        NESSUNA SESSIONE PARTE MUTA SU QUESTO PUNTO.

    Prima, senza preferenza, non si mandava `speechConfig` e il modello usava
    la sua voce. Sembrava la cosa discreta da fare — finche' su una telefonata
    vera la voce e' cambiata a meta' e non c'era un solo campo capace di
    smentirlo. Adesso ORA chiede sempre la propria voce, anche quando nessuno
    l'ha configurata, e su qualunque filo: primo, secondo, o riaperto per
    riprendere una chiamata caduta.
    """
    from telephone.live import THE_VOICE, _how_she_sounds

    for valore in ("", "   ", None):
        if valore is None:
            monkeypatch.delenv("GEMINI_LIVE_VOICE", raising=False)
        else:
            monkeypatch.setenv("GEMINI_LIVE_VOICE", valore)
        suona = _how_she_sounds()
        assert "speechConfig" in suona, f"sessione muta con {valore!r}"
        assert suona["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"][
            "voiceName"] == THE_VOICE
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


# ---------------------------------------------------------------------------
# 3 · Riprendere una telefonata a cui è caduto il filo
# ---------------------------------------------------------------------------
#
#     UN FILO CHE CADE NON È UNA MISSIONE FINITA.
#
# Su una prenotazione vera il filo è caduto quattordici secondi dopo
# l'apertura, mentre lo studio stava fissando l'appuntamento. ORA non aveva
# riagganciato: le avevano tolto la sessione da sotto, e non sapeva
# riprenderla. Il server le porgeva un appiglio circa una volta al secondo —
# ventotto in trentotto secondi — e li stavamo contando e buttando.

class FiloFinto:
    """
    Un filo verso chi parla, che si può far cadere quando serve.

    Accetta il setup, risponde `setupComplete`, e poi dice quello che gli si
    mette in bocca. Cadere è un comportamento come un altro.
    """

    aperti = []

    def __init__(self, *, accetta=True, da_dire=None):
        self.accetta = accetta
        self.mandati = []
        self.chiuso = False
        self._coda = list(da_dire or [])
        FiloFinto.aperti.append(self)

    async def send(self, testo):
        import json as _json

        self.mandati.append(_json.loads(testo))

    async def recv(self):
        import json as _json

        if self._coda:
            prossimo = self._coda.pop(0)
            if isinstance(prossimo, Exception):
                raise prossimo
            return _json.dumps(prossimo)
        # Finita la coda, il filo cade: e' il caso che interessa.
        raise ConnectionError("il filo si è chiuso")

    async def close(self):
        self.chiuso = True

    @property
    def setup(self):
        for m in self.mandati:
            if "setup" in m:
                return m["setup"]
        return {}


def _setup_ok():
    return {"setupComplete": {}}


def _handle(nome, resumable=True):
    return {"sessionResumptionUpdate": {"newHandle": nome, "resumable": resumable}}


async def _una_sessione(monkeypatch, fili, *, tipo="reschedule"):
    """Una sessione a missione aperta su una sequenza di fili finti."""
    from telephone.introduction import introduction_for
    from telephone.live import MissionVoiceSession
    from telephone.mission import CallMissionPacket

    monkeypatch.setenv("GEMINI2_API_KEY", "non-una-chiave-vera")
    monkeypatch.setenv("GEMINI_LIVE_MODEL", "un-modello-di-prova")
    monkeypatch.delenv("GEMINI_LIVE_VOICE", raising=False)

    packet = CallMissionPacket(
        mission_id="mis_prova", mission_type=tipo,
        goal="Spostare l'appuntamento", counterparty="Studio Bianchi",
        on_behalf_of="Francesco", local_datetime="2026-09-15T10:00:00+02:00",
        timezone="Europe/Rome", subject="l'appuntamento",
    )
    packet.introduction = introduction_for(packet)
    packet.say_this_first = packet.introduction.opening_line()

    da_dare = list(fili)

    async def connect():
        if not da_dare:
            raise ConnectionError("non ci sono altri fili")
        return da_dare.pop(0)

    async def send(_pcm):
        return None

    return MissionVoiceSession(
        None, owner_id="u1", session_ref="s", send=send,
        packet=packet, connect=connect,
    )


@pytest.mark.asyncio
async def test_a_dropped_wire_is_resumed_with_the_last_handle(monkeypatch):
    """
    Il filo cade con un appiglio buono in mano → si riprende.

    E la ripresa porta l'appiglio dentro il setup: e' cosi' che il server
    capisce che non e' una telefonata nuova.
    """
    primo = FiloFinto(da_dire=[
        _setup_ok(), _handle("abc"), _handle("def"),
        ConnectionError("caduto"),
    ])
    secondo = FiloFinto(da_dire=[_setup_ok()])
    sess = await _una_sessione(monkeypatch, [primo, secondo])

    assert await sess.open()
    await asyncio.sleep(0.2)

    assert sess._resumes_done == 1, "non ha ripreso"
    assert secondo.setup["sessionResumption"] == {"handle": "def"}, (
        "ha ripreso senza l'ultimo appiglio valido"
    )
    assert primo.chiuso, "il filo vecchio è rimasto aperto"
    await sess.close()


@pytest.mark.asyncio
async def test_the_latest_valid_handle_wins(monkeypatch):
    """Più appigli: vale l'ultimo, non il primo."""
    primo = FiloFinto(da_dire=[
        _setup_ok(), _handle("uno"), _handle("due"), _handle("tre"),
        ConnectionError("caduto"),
    ])
    secondo = FiloFinto(da_dire=[_setup_ok()])
    sess = await _una_sessione(monkeypatch, [primo, secondo])

    assert await sess.open()
    await asyncio.sleep(0.2)

    assert secondo.setup["sessionResumption"]["handle"] == "tre"
    assert sess.how_it_went()["session_resumption_updates"] == 3
    await sess.close()


@pytest.mark.asyncio
async def test_a_handle_that_is_not_resumable_does_not_overwrite(monkeypatch):
    """
        UN APPIGLIO NON RIPRENDIBILE NON SOSTITUISCE QUELLO BUONO.

    Sovrascriverlo vorrebbe dire perdere l'unica cosa che serve proprio quando
    il filo cade — e il server ne manda di entrambi i tipi.
    """
    primo = FiloFinto(da_dire=[
        _setup_ok(), _handle("buono"),
        _handle("inutile", resumable=False),
        {"sessionResumptionUpdate": {"newHandle": "", "resumable": True}},
        ConnectionError("caduto"),
    ])
    secondo = FiloFinto(da_dire=[_setup_ok()])
    sess = await _una_sessione(monkeypatch, [primo, secondo])

    assert await sess.open()
    await asyncio.sleep(0.2)

    assert secondo.setup["sessionResumption"]["handle"] == "buono"
    await sess.close()


@pytest.mark.asyncio
async def test_go_away_reconnects_before_the_wire_falls(monkeypatch):
    """
    §4: `goAway` è un preavviso, non un errore della missione.

    Dice quanto tempo resta: si riapre prima che cada, così chi sta parlando
    non sente niente.
    """
    primo = FiloFinto(da_dire=[
        _setup_ok(), _handle("h1"),
        {"goAway": {"timeLeft": "5s"}},
        {"serverContent": {}},
    ])
    secondo = FiloFinto(da_dire=[_setup_ok()])
    sess = await _una_sessione(monkeypatch, [primo, secondo])

    assert await sess.open()
    await asyncio.sleep(0.2)

    numeri = sess.how_it_went()
    assert numeri["go_away_count"] == 1
    assert numeri["go_away_time_left"] == "5s"
    assert numeri["resumes_succeeded"] >= 1, "non ha riaperto dopo il preavviso"
    assert "goAway" in numeri["reconnect_reasons"]
    assert secondo.setup["sessionResumption"]["handle"] == "h1"
    await sess.close()


@pytest.mark.asyncio
async def test_a_drop_without_a_handle_fails_safely(monkeypatch):
    """
        SE NON C'È UN APPIGLIO, NON SI FINGE.

    Aprire una sessione vuota e proseguire vorrebbe dire una ORA nuova che non
    sa niente di quello che si è detto, con la stessa voce. Meglio dichiarare
    che il trasporto è caduto.
    """
    solo = FiloFinto(da_dire=[_setup_ok(), ConnectionError("caduto subito")])
    sess = await _una_sessione(monkeypatch, [solo])

    assert await sess.open()
    await asyncio.sleep(0.2)
    await sess.close()

    numeri = sess.how_it_went()
    assert numeri["transport_failure"], "non ha dichiarato il guasto"
    assert "nessun appiglio" in numeri["transport_failure"]
    assert numeri["resumes_succeeded"] == 0
    #     E UNA TELEFONATA COSÌ NON SCRIVE NIENTE NEL MONDO.
    assert sess.outcome is not None
    assert sess.outcome.status == "partial"
    assert not sess.outcome.is_actionable()


@pytest.mark.asyncio
async def test_a_resume_that_keeps_failing_gives_up_honestly(monkeypatch):
    """
    §8: niente cicli infiniti, niente tempesta di riconnessioni.

    Un filo che cade tre volte di fila non è un inciampo, e continuare a
    riaprirlo mentre una persona aspetta al telefono vuol dire farle ascoltare
    il silenzio più a lungo invece di chiudere con onestà.
    """
    from telephone.live import MAX_RESUME_ATTEMPTS

    primo = FiloFinto(da_dire=[_setup_ok(), _handle("h"), ConnectionError("giù")])
    # Tutti i successivi rifiutano il setup.
    rotti = [FiloFinto(da_dire=[{"niente": {}}]) for _ in range(MAX_RESUME_ATTEMPTS)]
    sess = await _una_sessione(monkeypatch, [primo] + rotti)

    assert await sess.open()
    await asyncio.sleep(1.5)
    await sess.close()

    numeri = sess.how_it_went()
    assert numeri["resume_attempts"] == MAX_RESUME_ATTEMPTS
    assert numeri["resumes_succeeded"] == 0
    assert "non riuscita" in numeri["transport_failure"]
    assert not sess.outcome.is_actionable()


@pytest.mark.asyncio
async def test_resuming_does_not_start_the_call_over(monkeypatch):
    """
    §5: chi ascolta non deve accorgersi di niente.

        LA CONTINUITÀ LA PORTA L'APPIGLIO, NON NOI.

    Niente seconda presentazione, niente saluto ripetuto, niente conversazione
    che ricomincia. E la missione resta la stessa: stesso ledger, stessa
    autorità, stessa identità.
    """
    primo = FiloFinto(da_dire=[_setup_ok(), _handle("h"), ConnectionError("giù")])
    secondo = FiloFinto(da_dire=[_setup_ok()])
    sess = await _una_sessione(monkeypatch, [primo, secondo])

    assert await sess.open()
    sess.mission.heard("availability", "alle 18 ci sarebbe posto")
    ledger_prima = list(sess.mission.statements)
    missione_prima = sess.packet.mission_id
    await asyncio.sleep(0.2)

    # Sul filo nuovo c'è il setup, e nient'altro che somigli a un'apertura.
    dopo_il_setup = [m for m in secondo.mandati if "setup" not in m]
    assert dopo_il_setup == [], f"ha rimandato qualcosa: {dopo_il_setup}"

    assert sess.packet.mission_id == missione_prima
    assert list(sess.mission.statements) == ledger_prima
    assert sess._opening in ("completed", "speaking", "deferred", "pending")
    await sess.close()


@pytest.mark.asyncio
async def test_every_connection_asks_for_charon(monkeypatch):
    """
    §6: anche i fili aperti per riprendere chiedono la voce di ORA.

    È il punto in cui si perdeva: una sessione ripresa senza `speechConfig`
    prende la voce predefinita del modello — e chi ascolta sente cambiare
    interlocutore a metà telefonata.
    """
    from telephone.live import THE_VOICE

    primo = FiloFinto(da_dire=[_setup_ok(), _handle("h"), ConnectionError("giù")])
    secondo = FiloFinto(da_dire=[_setup_ok(), _handle("h2"), ConnectionError("giù")])
    terzo = FiloFinto(da_dire=[_setup_ok()])
    sess = await _una_sessione(monkeypatch, [primo, secondo, terzo])

    assert await sess.open()
    await asyncio.sleep(0.4)

    for filo in (primo, secondo, terzo):
        voce = filo.setup["generationConfig"]["speechConfig"]["voiceConfig"][
            "prebuiltVoiceConfig"]["voiceName"]
        assert voce == THE_VOICE, f"un filo ha chiesto {voce}"

    numeri = sess.how_it_went()
    #     OGNI FILO, ANCHE QUELLO CHE NON SI È APERTO.
    # La voce si chiede al momento di comporre il setup, non dopo che ha
    # funzionato: un tentativo fallito che avesse chiesto la voce sbagliata
    # sarebbe comunque il sintomo del difetto.
    assert numeri["live_connections"], "nessuna connessione registrata"
    assert all(c["live_voice_in_setup"] == THE_VOICE
               for c in numeri["live_connections"])
    assert all(c["speech_config_sent"] for c in numeri["live_connections"])

    riusciti = [c for c in numeri["live_connections"] if not c["failed_because"]]
    assert len(riusciti) == 3
    # Il primo apre, gli altri riprendono.
    assert [c["resumed_from_handle"] for c in riusciti] == [False, True, True]
    assert [c["connection_index"] for c in riusciti] == [1, 2, 3]
    await sess.close()


@pytest.mark.asyncio
async def test_the_trace_says_what_happened_to_the_wire(monkeypatch):
    """§10: ogni connessione lascia detto chi era, e nessun segreto."""
    primo = FiloFinto(da_dire=[_setup_ok(), _handle("h-segreto"),
                               ConnectionError("giù")])
    secondo = FiloFinto(da_dire=[_setup_ok()])
    sess = await _una_sessione(monkeypatch, [primo, secondo])

    assert await sess.open()
    await asyncio.sleep(0.2)
    numeri = sess.how_it_went()

    for campo in ("live_connection_count", "session_resumption_updates",
                  "has_valid_resume_handle", "go_away_count",
                  "resume_attempts", "resumes_succeeded", "reconnect_ms",
                  "reconnect_reasons", "connection_closed_reasons",
                  "transport_failure"):
        assert campo in numeri, campo

    assert numeri["has_valid_resume_handle"] is True
    assert numeri["reconnect_ms"] and numeri["reconnect_ms"][0] >= 0
    #     L'APPIGLIO NON SI SCRIVE: SI DICE CHE C'È.
    # È un manico di sessione, e un rapporto che si incolla in una
    # conversazione non deve portarselo dietro.
    assert "h-segreto" not in str(numeri)
    assert "non-una-chiave-vera" not in str(numeri)
    await sess.close()


@pytest.mark.asyncio
async def test_closing_after_a_resume_leaves_nothing_running(monkeypatch):
    """Nessun task orfano, nessun filo aperto: si chiude tutto."""
    primo = FiloFinto(da_dire=[_setup_ok(), _handle("h"), ConnectionError("giù")])
    secondo = FiloFinto(da_dire=[_setup_ok()])
    sess = await _una_sessione(monkeypatch, [primo, secondo])

    assert await sess.open()
    await asyncio.sleep(0.2)
    await sess.close()

    assert primo.chiuso and secondo.chiuso
    assert sess._pump is None or sess._pump.done()
    rimasti = [t for t in asyncio.all_tasks()
               if t is not asyncio.current_task() and not t.done()]
    assert not rimasti, f"task orfani: {rimasti}"


@pytest.mark.asyncio
async def test_no_two_wires_are_ever_live_together(monkeypatch):
    """
    §4: mai due sessioni vive insieme, e mai un istante senza nessuna.

    È la differenza fra una ripresa che non si sente e un buco nella
    telefonata.
    """
    primo = FiloFinto(da_dire=[_setup_ok(), _handle("h"), ConnectionError("giù")])
    secondo = FiloFinto(da_dire=[_setup_ok()])
    sess = await _una_sessione(monkeypatch, [primo, secondo])

    assert await sess.open()
    await asyncio.sleep(0.2)

    # Il vecchio è chiuso, il nuovo no, e quello in uso è il nuovo.
    assert primo.chiuso is True
    assert secondo.chiuso is False
    assert sess.ws is secondo
    await sess.close()


@pytest.mark.asyncio
async def test_a_refused_resume_does_not_strand_the_old_wire(monkeypatch):
    """
    Se il setup di ripresa viene rifiutato, il filo appena aperto si chiude.

    Altrimenti resterebbe lì, mezzo aperto, a tenere una connessione che
    nessuno legge.
    """
    primo = FiloFinto(da_dire=[_setup_ok(), _handle("h"), ConnectionError("giù")])
    rifiuta = FiloFinto(da_dire=[{"qualcosaltro": {}}])
    buono = FiloFinto(da_dire=[_setup_ok()])
    sess = await _una_sessione(monkeypatch, [primo, rifiuta, buono])

    assert await sess.open()
    await asyncio.sleep(1.0)

    assert rifiuta.chiuso, "il filo rifiutato è rimasto aperto"
    assert sess._resumes_done == 1
    assert sess.ws is buono
    await sess.close()
