"""
V3.21.2 — quando la telefonata non va come doveva.

    UNA TELEFONATA DEVE FINIRE IN UNO STATO VERO, ANCHE QUANDO VA STORTA.

Nessuno risponde, è occupato, risponde una segreteria, cade la linea, cade la
voce, la sessione va ripresa, l'apertura viene interrotta, arriva un «no» a due
domande insieme. In nessuno di questi casi ORA può fingere un successo,
perdere il piano, rifare la telefonata o dire una cosa nel momento sbagliato.

Queste prove tengono fermo il comportamento. Le prove dal vivo stanno nella
roadmap, con quello che non si è potuto provare dal vivo dichiarato tale.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from test_autonomous_action_loop_v320 import (  # noqa: E402,F401
    _chiamata as _chiamata_piano,
    _in_linea,
    _un_piano_autorizzato,
    mondo,
)
from test_live_runtime_v313 import (  # noqa: E402
    FakeDb,
    FakeWire,
    _cosa_ha_chiesto,
    _scalda_le_orecchie,
    _subito,
    _subito_apertura,
    _tool,
    _risposta,
)
from test_post_call_application_v315 import FintoDb  # noqa: E402
from test_voice_and_pacing_v316a import (  # noqa: E402
    FiloFinto,
    _handle,
    _setup_ok,
    _una_sessione,
)


class FiloChiudibile(FiloFinto):
    """Un filo che resta aperto finché qualcuno non lo chiude."""

    async def recv(self):
        while not self._coda and not self.chiuso:
            await asyncio.sleep(0.01)
        if self.chiuso and not self._coda:
            raise ConnectionError("chiuso di proposito")
        return await super().recv()


# ---------------------------------------------------------------------------
# Una consegna aperta su un filo finto
# ---------------------------------------------------------------------------

def _consegna(message="la amo", recipient="Asia"):
    from telephone.models import Mandate, PhoneCall

    return PhoneCall(
        id="tel_asia", owner_id="u1", to_number="+393330000042",
        calling_whom=recipient,
        mandate=Mandate(why_calling=f"consegnare un messaggio ad {recipient}",
                        message=message, recipient=recipient),
        provider_ref="",
    )


async def _consegna_aperta(monkeypatch):
    """Una sessione di consegna, aperta su un filo finto."""
    from telephone.dossier import TelephoneCallDossier
    from telephone.live import MissionVoiceSession
    from telephone.mission import packet_for

    monkeypatch.setenv("GEMINI2_API_KEY", "non-una-chiave-vera")
    monkeypatch.setenv("GEMINI_LIVE_MODEL", "un-modello-di-prova")
    call = _consegna()
    packet = packet_for(call, TelephoneCallDossier(
        owner_id="u1", call_id=call.id, on_behalf_of="Francesco"))
    wire = FakeWire()

    async def send(_pcm):
        return None

    sess = MissionVoiceSession(FakeDb(), owner_id="u1", session_ref="s", send=send,
                               call=call, packet=packet, connect=lambda: _subito(wire))
    aperta = asyncio.create_task(sess.open())
    await asyncio.sleep(0)
    await wire._in.put(json.dumps({"setupComplete": {}}))
    assert await aperta is True
    return sess, wire


# ===========================================================================
# 1 · L'apertura interrotta
# ===========================================================================

@pytest.mark.asyncio
async def test_an_interrupted_opening_does_not_repeat_who_we_are(monkeypatch):
    """
    «Ciao, sono l'assistente di Francesco—» / «Pronto?» / «Ciao. Parlo con Asia?»

    La nota arriva con l'interruzione, e dice di non ripetere chi siamo.
    """
    _subito_apertura(monkeypatch)
    sess, wire = await _consegna_aperta(monkeypatch)
    try:
        await _scalda_le_orecchie(sess)
        await asyncio.sleep(0.25)
        assert sess.how_it_went()["opening_state"] == "speaking"
        assert "Ciao, sono l'assistente di Francesco. Parlo con Asia?" in _cosa_ha_chiesto(wire)

        await wire.says({"serverContent": {"outputTranscription": {
            "text": "Ciao, sono l'assistente di Francesco"}}})
        await wire.says({"serverContent": {"interrupted": True}})

        assert sess.how_it_went()["opening_state"] == "interrupted"
        nota = _cosa_ha_chiesto(wire)
        assert "non ripeterlo" in nota
        assert "«Parlo con Asia?»" in nota
        assert "Ciao, sono l'assistente" not in nota
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_the_identity_question_is_not_asked_again(monkeypatch):
    """
    Misurato sul vero: con una sola parola chiave il registro non considerava
    mai detto «Parlo con Asia?», e la nota lo faceva ripetere.
    """
    _subito_apertura(monkeypatch)
    sess, wire = await _consegna_aperta(monkeypatch)
    try:
        await _scalda_le_orecchie(sess)
        await asyncio.sleep(0.25)
        quante_prima = len(wire.what_it_sent("clientContent"))

        await wire.says({"serverContent": {"outputTranscription": {
            "text": "Ciao, sono l'assistente di Francesco. Parlo con Asia?"}}})
        await wire.says({"serverContent": {"turnComplete": True}})

        n = sess.how_it_went()
        assert n["introduction_state"] == "completed"
        assert n["introduction_nudges"] == 0
        assert n["opening_state"] == "identity_pending"
        assert len(wire.what_it_sent("clientContent")) == quante_prima, "ha rifatto la domanda"

        #     «SÌ» E L'APERTURA E' FINITA. NON SI RICHIEDE PIU'.
        await wire.says(_tool("recipient_confirmed", {"how_they_confirmed": "sì"}))
        assert sess.how_it_went()["opening_state"] == "completed"
        assert sess.how_it_went()["identity_settled"] is True
    finally:
        await sess.close()


def test_one_keyword_is_enough_to_settle_a_delivery_opening():
    from telephone.introduction import Introduction, IntroductionLedger

    registro = IntroductionLedger(Introduction(
        assistant_for="Francesco", reason_summary="parlare con Asia",
        reason_keywords=["asia"], asks_for="Asia"))
    registro.we_said("Ciao, sono l'assistente di Francesco. Parlo con Asia?")
    assert registro.is_settled()
    assert registro.what_still_has_to_be_said() == ""


# ===========================================================================
# 2 · 3 · Nessuna risposta, occupato
# ===========================================================================

def _finita(**cambia):
    from telephone.models import Mandate, PhoneCall

    campi = dict(
        id="tel_f", owner_id="u1", to_number="+393000000000", calling_whom="Studio",
        mandate=Mandate(why_calling="spostare il mio appuntamento dal dentista"),
        state="ended", how_it_ended="they_hung_up",
        started_at="2026-09-19T10:00:10+00:00", ended_at="2026-09-19T10:01:00+00:00",
    )
    campi.update(cambia)
    return PhoneCall(**campi)


def test_no_answer_reads_as_no_answer_and_never_as_a_technical_failure():
    from telephone.history import as_a_card, result_of

    call = _finita(state="failed", how_it_ended="no_answer", started_at=None)
    assert result_of(call) == "no_answer"
    scheda = as_a_card(call)
    assert scheda["outcome_summary"] == "Non ha risposto."
    assert scheda["status_label"] == "Nessuna risposta"
    for tecnico in ("failed", "ring_timeout", "carrier", "timeout"):
        assert tecnico not in json.dumps(scheda["outcome_summary"])


def test_busy_is_busy_not_no_answer():
    from telephone.history import as_a_card, result_of

    call = _finita(state="failed", how_it_ended="busy", started_at=None)
    assert result_of(call) == "busy"
    assert as_a_card(call)["outcome_summary"] == "Il numero era occupato."


def test_the_carrier_refusing_the_call_is_not_no_answer():
    from telephone.history import in_one_line, result_of

    call = _finita(state="failed", how_it_ended="failed", started_at=None)
    assert result_of(call) == "not_connected"
    assert in_one_line(call) == "La telefonata non è partita."


def test_the_carrier_names_are_translated_once():
    from telephone.carrier import read_event

    assert read_event({"status": "timeout"})["ended_how"] == "no_answer"
    assert read_event({"status": "unanswered"})["ended_how"] == "no_answer"
    assert read_event({"status": "busy"})["ended_how"] == "busy"
    assert read_event({"status": "rejected"})["ended_how"] == "failed"
    assert read_event({"status": "machine"})["what"] == "machine"
    assert read_event({"status": "human"})["what"] == "human"


@pytest.mark.asyncio
async def test_a_call_nobody_answered_closes_its_plan(mondo):
    """
    Sul vero Vonage manda `timeout` e la telefonata finisce `failed`: il piano
    leggeva solo `ended` e restava «authorised» per sempre.
    """
    from autonomy.orchestrator import on_call_finished

    await _un_piano_autorizzato(mondo)
    call = _in_linea(mondo, _chiamata_piano(stato="failed", finita="no_answer"))
    plan = await on_call_finished(mondo, call)

    assert plan.state == "failed"
    assert plan.state not in ("executing", "authorised")
    assert plan.error == "Non ha risposto."
    assert mondo["call_mission_applications"].righe == []


@pytest.mark.asyncio
async def test_a_busy_call_closes_its_plan_too(mondo):
    from autonomy.orchestrator import on_call_finished

    await _un_piano_autorizzato(mondo)
    call = _in_linea(mondo, _chiamata_piano(stato="failed", finita="busy"))
    plan = await on_call_finished(mondo, call)
    assert plan.state == "failed"
    assert plan.error == "Il numero era occupato."


# ===========================================================================
# 4 · La segreteria
# ===========================================================================

def test_voicemail_needs_two_signals():
    from telephone.voicemail import VoicemailWatch

    w = VoicemailWatch()
    w.carrier_says("machine")
    assert w.verdict == "suspected"
    w.heard("Il numero da lei chiamato... lasci un messaggio dopo il segnale acustico")
    assert w.verdict == "voicemail"

    due = VoicemailWatch()
    due.heard("Risponde la segreteria telefonica di Asia. Lasci un messaggio.")
    assert due.verdict == "voicemail"


def test_a_person_saying_segreteria_once_is_not_a_voicemail():
    from telephone.voicemail import VoicemailWatch

    w = VoicemailWatch()
    w.carrier_says("human")
    w.heard("Pronto? Ah no, pensavo fosse la segreteria telefonica dello studio.")
    assert w.verdict == "suspected"
    persona = VoicemailWatch()
    persona.heard("Pronto, chi parla?")
    assert persona.verdict == ""


@pytest.mark.asyncio
async def test_a_voicemail_never_hears_the_message(monkeypatch):
    """
    Carrier «machine» + frase da messaggio registrato: si chiude senza dire
    niente, e il messaggio non esce nemmeno se la segreteria dice «sono Asia».
    """
    sess, wire = await _consegna_aperta(monkeypatch)
    try:
        await sess.the_carrier_says("machine")
        assert sess.outcome is None, "un segnale solo non basta"

        r = await sess._answer_one("recipient_confirmed", {"how_they_confirmed": "sono Asia"})
        assert r["accepted"] is False
        assert "message_to_deliver" not in r

        await wire.says({"serverContent": {"inputTranscription": {
            "text": "Ciao sono Asia, lasciate un messaggio dopo il segnale."}}})
        await wire.says({"serverContent": {"turnComplete": True}})

        assert sess.outcome is not None
        assert sess.outcome.ended_because == "voicemail"
        assert sess.outcome.delivery == "voicemail"
        assert sess.outcome.status == "failed"
        assert "la amo" not in json.dumps([m for m in wire.sent])
        assert sess.how_it_went()["goodbye_story"][-1] == "skipped_voicemail"
    finally:
        await sess.close()


@pytest.mark.asyncio
async def test_the_models_word_alone_does_not_make_a_voicemail(monkeypatch):
    """Il modello dice «segreteria», nessun altro segnale: «non raggiunta»."""
    from telephone.history import result_of

    sess, _ = await _consegna_aperta(monkeypatch)
    try:
        await sess._answer_one("recipient_not_available", {"who_answered": "voicemail"})
        assert sess.outcome.delivery == "not_reached"
        assert sess.outcome.ended_because == ""
        call = _consegna().model_copy(update={
            "state": "ended", "how_it_ended": "we_hung_up",
            "started_at": "2026-09-19T10:00:00+00:00",
            "metrics": {"outcome": sess.outcome.model_dump()}})
        assert result_of(call) != "voicemail"
    finally:
        await sess.close()


def test_a_voicemail_reads_as_a_voicemail():
    from telephone.history import as_a_card

    call = _finita(metrics={"outcome": {"mission_id": "m", "status": "failed",
                                        "ended_because": "voicemail"}})
    scheda = as_a_card(call)
    assert scheda["presentation_status"] == "segreteria"
    assert scheda["outcome_summary"] == "Ha risposto la segreteria."


def test_machine_detection_is_asked_to_the_carrier(monkeypatch):
    from telephone.carrier import _machine_detection

    monkeypatch.delenv("ORA_MACHINE_DETECTION", raising=False)
    assert _machine_detection() == {}
    monkeypatch.setenv("ORA_MACHINE_DETECTION", "continue")
    assert _machine_detection() == {"machine_detection": "continue"}
    monkeypatch.setenv("ORA_MACHINE_DETECTION", "off")
    assert _machine_detection() == {}


# ===========================================================================
# 5 · La linea che cade
# ===========================================================================

@pytest.mark.asyncio
async def test_a_line_drop_mid_conversation_is_not_a_success(monkeypatch):
    from telephone.history import in_one_line, result_of

    sess, wire = await _consegna_aperta(monkeypatch)
    await wire.says({"serverContent": {"inputTranscription": {"text": "Pronto?"}}})
    await wire.says({"serverContent": {"turnComplete": True}})
    await sess.close()

    assert sess.outcome.status == "partial"
    assert sess.outcome.ended_because == "line_dropped"
    assert not sess.outcome.is_actionable()
    call = _consegna().model_copy(update={
        "state": "ended", "how_it_ended": "they_hung_up",
        "started_at": "2026-09-19T10:00:00+00:00",
        "metrics": {"outcome": sess.outcome.model_dump()}})
    assert result_of(call) == "transport_failure"
    assert in_one_line(call) == "La chiamata si è interrotta prima che riuscissi a concludere."


@pytest.mark.asyncio
async def test_a_line_drop_after_a_validated_outcome_keeps_the_outcome(monkeypatch):
    sess, _ = await _consegna_aperta(monkeypatch)
    await sess._answer_one("recipient_confirmed", {"how_they_confirmed": "sì"})
    reply = await sess._answer_one("message_delivered", {"recipient_reply": "anch'io"})
    assert reply["say"] == "Grazie, buona giornata!"
    assert "riferisco" not in reply["say"]
    await sess.close()
    assert sess.outcome.status == "success"
    assert sess.outcome.delivery == "delivered"
    assert sess.outcome.ended_because == ""


@pytest.mark.asyncio
async def test_a_drop_with_a_proposal_on_the_table_goes_to_a_person(monkeypatch):
    sess, wire, _, _ = await __import__("test_live_runtime_v313")._aperta(monkeypatch)
    await wire.says({"serverContent": {"inputTranscription": {"text": "alle 18 no"}}})
    await wire.says({"serverContent": {"turnComplete": True}})
    sess.mission.heard("proposal", "domani alle 11")
    await sess.close()
    assert sess.outcome.status == "needs_user"
    assert sess.outcome.ended_because == "line_dropped"


# ===========================================================================
# 6 · La ripresa della sessione Live
# ===========================================================================

@pytest.mark.asyncio
async def test_a_live_drop_with_a_handle_resumes_the_same_mission(monkeypatch):
    primo = FiloFinto(da_dire=[_setup_ok(), _handle("h1"), ConnectionError("giù")])
    secondo = FiloChiudibile(da_dire=[_setup_ok()])
    sess = await _una_sessione(monkeypatch, [primo, secondo])
    assert await sess.open()
    await asyncio.sleep(0.3)

    n = sess.how_it_went()
    assert n["live_connection_count"] == 2
    assert n["resumes_succeeded"] == 1
    uno, due = n["live_connections"]
    assert uno["reason"] == "first" and uno["closed_because"] == "ConnectionError"
    assert due["resume_handle_present"] is True
    assert due["reason"] == "ConnectionError"
    assert uno["mission_id"] == due["mission_id"] == "mis_prova"
    assert secondo.setup["sessionResumption"] == {"handle": "h1"}
    #     NIENTE SECONDA APERTURA SUL FILO NUOVO.
    assert [m for m in secondo.mandati if "setup" not in m] == []
    assert n["transport_failure"] == ""
    await sess.close()


@pytest.mark.asyncio
async def test_a_resume_that_fails_is_a_live_runtime_failure(monkeypatch):
    primo = FiloFinto(da_dire=[_setup_ok(), _handle("h1"), ConnectionError("giù")])
    rifiuti = [FiloFinto(da_dire=[{"altro": 1}]) for _ in range(3)]
    sess = await _una_sessione(monkeypatch, [primo, *rifiuti])
    assert await sess.open()
    await asyncio.sleep(2.2)
    await sess.close()

    n = sess.how_it_went()
    assert n["resumes_succeeded"] == 0
    assert n["resume_attempts"] == 3
    assert "ripresa non riuscita" in n["transport_failure"]
    assert sess.outcome.ended_because == "live_runtime_failure"
    assert not sess.outcome.is_actionable()


@pytest.mark.asyncio
async def test_go_away_is_honoured_before_the_drop(monkeypatch):
    primo = FiloFinto(da_dire=[_setup_ok(), _handle("h1"), {"goAway": {"timeLeft": "5s"}}])
    secondo = FiloChiudibile(da_dire=[_setup_ok()])
    sess = await _una_sessione(monkeypatch, [primo, secondo])
    assert await sess.open()
    await asyncio.sleep(0.3)
    n = sess.how_it_went()
    assert n["go_away_count"] == 1
    assert n["live_connections"][0].get("go_away") is True
    assert n["live_connections"][1]["reason"] == "goAway"
    assert n["resumes_succeeded"] == 1
    await sess.close()


def test_the_dev_fault_injection_is_off_by_default_and_never_in_production(monkeypatch):
    from telephone.live import _dev_drop_after_turns

    monkeypatch.delenv("ORA_DEV_DROP_LIVE_AFTER_TURNS", raising=False)
    assert _dev_drop_after_turns() == 0
    monkeypatch.setenv("ORA_DEV_DROP_LIVE_AFTER_TURNS", "2")
    monkeypatch.setenv("ENVIRONMENT", "development")
    assert _dev_drop_after_turns() == 2
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert _dev_drop_after_turns() == 0


@pytest.mark.asyncio
async def test_the_dev_fault_injection_drops_only_the_live_wire(monkeypatch):
    """Dopo N turni si chiude il filo Gemini, e la ripresa lo riapre."""
    monkeypatch.setenv("ORA_DEV_DROP_LIVE_AFTER_TURNS", "1")
    monkeypatch.setenv("ENVIRONMENT", "development")

    primo = FiloChiudibile(da_dire=[_setup_ok(), _handle("h1"),
                                    {"serverContent": {"turnComplete": True}}])
    secondo = FiloChiudibile(da_dire=[_setup_ok()])
    sess = await _una_sessione(monkeypatch, [primo, secondo])
    assert await sess.open()
    await asyncio.sleep(0.5)
    n = sess.how_it_went()
    assert n["dev_fault_injected"] is True
    assert n["live_connections"][0]["closed_because"] == "dev_fault_injection"
    assert n["resumes_succeeded"] == 1
    assert n["hung_up_by_ora"] is False
    await sess.close()


def test_the_live_wire_reuses_the_shared_tls_context():
    import inspect

    import telephone.live as live

    assert "ssl=_tls()" in inspect.getsource(live._dial)


# ===========================================================================
# 8 · Le risposte parziali
# ===========================================================================

def test_a_short_no_to_two_questions_is_ambiguous():
    from telephone.mission import an_ambiguous_reply

    assert an_ambiguous_reply("Non potete alle 18? Avete posto alle 19?", "No.")
    assert an_ambiguous_reply("Alle 18? O alle 19?", "Sì")
    assert not an_ambiguous_reply("Avete posto alle 19?", "No.")
    assert not an_ambiguous_reply("Alle 18? O alle 19?", "Alle 19 sì, alle 18 no.")


@pytest.mark.asyncio
async def test_an_ambiguous_no_does_not_close_the_mission(monkeypatch):
    sess, wire, _, _ = await __import__("test_live_runtime_v313")._aperta(monkeypatch)
    try:
        await wire.says({"serverContent": {"outputTranscription": {
            "text": "Non potete alle 18? Avete disponibilità alle 19?"}}})
        await wire.says({"serverContent": {"turnComplete": True}})
        await wire.says({"serverContent": {"inputTranscription": {"text": "No."}}})
        await wire.says(_tool("fail_mission", {"reason": "hanno detto no"}))

        r = _risposta(wire)
        assert r["accepted"] is False
        assert "una cosa alla volta" in r["do_this"]
        assert sess.outcome is None

        #     E UNA RISPOSTA PIENA CHIUDE, COME SEMPRE.
        await wire.says({"serverContent": {"outputTranscription": {
            "text": "Quindi nemmeno alle 19?"}}})
        await wire.says({"serverContent": {"turnComplete": True}})
        await wire.says({"serverContent": {"inputTranscription": {
            "text": "No, nemmeno alle 19, siamo pieni tutto il giorno."}}})
        await wire.says(_tool("fail_mission", {"reason": "pieni"}, id_="t2"))
        assert sess.outcome is not None
        assert sess.outcome.status == "failed"
    finally:
        await sess.close()


def test_one_question_at_a_time_is_in_the_rules():
    from telephone.live import SESSION_PROMPT

    assert "Fai una domanda alla volta" in SESSION_PROMPT
    assert "segreteria" in SESSION_PROMPT


# ===========================================================================
# 10 · Il piano non resta mai a metà
# ===========================================================================

@pytest.mark.asyncio
async def test_a_call_with_no_news_is_closed_and_so_is_its_plan(mondo):
    from autonomy.orchestrator import recover_plans
    from telephone.service import settle_the_forgotten

    await _un_piano_autorizzato(mondo)
    vecchia = _chiamata_piano(stato="talking")
    vecchia = vecchia.model_copy(update={"started_at": "2026-09-14T14:00:10+00:00"})
    _in_linea(mondo, vecchia)

    assert await settle_the_forgotten(mondo) == 1
    riga = mondo["phone_calls"].righe[0]
    assert riga["state"] == "failed" and riga["how_it_ended"] == "unknown"

    await recover_plans(mondo)
    piano = mondo["autonomous_action_plans"].righe[0]
    assert piano["state"] == "failed"


# ===========================================================================
# 12 · Lo storico, a pagine vere
# ===========================================================================

async def _storico(db, quante=25, stesso_istante=False):
    from telephone.models import Mandate, PhoneCall
    from telephone.service import TelephoneService

    s = TelephoneService(db)
    for i in range(quante):
        call = PhoneCall(
            id=f"tel_{i:03d}", owner_id="u1", to_number="+393000000000",
            calling_whom=f"Studio {i}", mandate=Mandate(why_calling="chiedere"),
            authorised_at=("2026-09-19T10:00:00+00:00" if stesso_istante
                           else f"2026-09-{1 + i // 24:02d}T{i % 24:02d}:00:00+00:00"),
            state="failed" if i % 5 == 0 else "ended",
            how_it_ended="no_answer" if i % 5 == 0 else "they_hung_up",
        )
        await s._save(call)
    return s


@pytest.mark.asyncio
async def test_the_history_is_paginated_by_the_database():
    db = FintoDb()
    s = await _storico(db)

    visti, prima = [], ""
    for _ in range(4):
        pagina, in_tutto, prima = await s.recent("u1", limit=10, before=prima)
        visti += [c.id for c in pagina]
        assert in_tutto == 25
        if not prima:
            break
    assert len(visti) == 25 and len(set(visti)) == 25
    assert visti == sorted(visti, reverse=True)


@pytest.mark.asyncio
async def test_the_order_is_stable_even_at_the_same_instant():
    db = FintoDb()
    s = await _storico(db, quante=7, stesso_istante=True)
    a, _, dopo = await s.recent("u1", limit=4)
    b, _, fine = await s.recent("u1", limit=4, before=dopo)
    assert [c.id for c in a + b] == [f"tel_{i:03d}" for i in range(6, -1, -1)]
    assert fine == ""


@pytest.mark.asyncio
async def test_the_status_filter_is_a_query_not_a_scan():
    db = FintoDb()
    s = await _storico(db)
    pagina, in_tutto, _ = await s.recent("u1", limit=50, status="nessuna_risposta")
    assert in_tutto == 5
    assert all(c.how_it_ended == "no_answer" for c in pagina)
    assert all(r.get("status_reads") for r in db["phone_calls"].righe)


def test_the_route_returns_the_cursor_the_app_asks_for():
    import inspect

    import telephone.router as router

    testo = inspect.getsource(router.call_history)
    assert "before=before" in testo and '"next_before"' in testo
    import telephone.service as service

    assert ".limit(300)" not in inspect.getsource(service.TelephoneService.recent)


# ===========================================================================
# 13 · Le telefonate fantasma
# ===========================================================================

@pytest.mark.asyncio
async def test_a_call_prepared_days_ago_reads_as_not_started():
    from telephone.history import as_a_card
    from telephone.models import Mandate, PhoneCall
    from telephone.placing import dial
    from telephone.service import settle_the_forgotten

    fantasma = PhoneCall(id="tel_ghost", owner_id="u1", to_number="+393000000000",
                         calling_whom="Asia", mandate=Mandate(why_calling="salutarla"),
                         authorised_at="2026-09-18T18:39:58+00:00")
    assert as_a_card(fantasma)["status_label"] == "Non avviata"

    db = FintoDb()
    db.phone_calls.righe.append(fantasma.model_dump())
    assert await settle_the_forgotten(db) == 1
    assert db.phone_calls.righe[0]["state"] == "expired"

    #     E UN SI' DI IERI NON LA FA PARTIRE OGGI.
    vecchia = PhoneCall(**{**fantasma.model_dump(), "id": "tel_ghost2"})
    fatta, perche = await dial(db, "u1", vecchia)
    assert fatta is None and "troppo tempo fa" in perche


# ===========================================================================
# 14 · Il tunnel caduto
# ===========================================================================

@pytest.mark.asyncio
async def test_a_dead_tunnel_is_named_and_nothing_is_dialled(monkeypatch):
    import telephone.carrier as carrier

    chiamate = []

    async def spento():
        return False

    monkeypatch.setattr(carrier, "_token", lambda: "t")
    monkeypatch.setattr(carrier, "can_call", lambda: True)
    monkeypatch.setattr(carrier, "public_base_answers", spento)

    class Mai:
        def __init__(self, *a, **k):
            chiamate.append(1)

    monkeypatch.setattr("httpx.AsyncClient", Mai)
    fuori = await carrier.place(to_number="+39", call_id="tel_x", minutes=2)
    assert fuori == {"call_ref": "", "error": carrier.TUNNEL_DOWN}
    assert chiamate == []
    assert "tunnel" in carrier.TUNNEL_DOWN and "gemini" not in carrier.TUNNEL_DOWN.lower()


def test_the_guidance_cannot_shorten_the_phone_tool_sentence():
    """
    Misurato in app: in un turno «ask» la guida ha riscritto la domanda in
    «È questo il numero corretto?», senza nome, numero né provenienza.
    """
    import inspect

    import conversation_engine.ai_core.loop as loop

    testo = inspect.getsource(loop)
    guida = testo.index('if guidance_ask and mode == "ask":')
    dopo = testo.index("state_mod.append_turn(st, role=\"ora\", text=ora, kind=mode)", guida)
    assert "_the_tool_s_own_sentence(observations[turn_start:])" in testo[guida:dopo]


@pytest.mark.asyncio
async def test_a_message_to_deliver_is_ready_without_asking_the_model(monkeypatch):
    """
    Misurato in app: il valutatore ha inventato «ricordi perché ti ho chiamato
    l'ultima volta?» su un messaggio già completo. Per una consegna non si chiede.
    """
    import preparation.readiness as valutatore
    from preparation.preparation import ContactCandidate, MissionPreparation

    async def non_chiamarmi(_prep):
        raise AssertionError("il modello non va interpellato per una consegna")

    monkeypatch.setattr(valutatore, "_what_the_model_sees", non_chiamarmi)
    prep = MissionPreparation(
        owner_id="u1", user_request="Chiama Francesco Test e digli che è un test",
        counterparty="Francesco Test", operation="deliver_message",
        message_to_deliver="questo è un test di ripresa",
        selected_contact=ContactCandidate(
            name="Francesco Test", number="+393000000000", kind="person",
            source="address_book", contact_identity="francesco test"),
        contact_identity="francesco test",
        number_confirmed=True, number_trust="confirmed_now",
    )
    fatta = await valutatore.evaluate(None, prep, operation="deliver_message")
    assert fatta.readiness == "READY"
    assert fatta.conversation_ready is True


@pytest.mark.asyncio
async def test_a_resume_after_a_finished_turn_lets_the_sentence_finish(monkeypatch):
    """
    Gate A dal vivo: il filo è caduto subito dopo la fine di un turno e la
    ripresa ha buttato l'audio completo in coda, tagliando il messaggio.
    """
    primo = FiloFinto(da_dire=[_setup_ok(), _handle("h1"), ConnectionError("giù")])
    secondo = FiloChiudibile(da_dire=[_setup_ok()])
    sess = await _una_sessione(monkeypatch, [primo, secondo])
    annullate = []

    async def annulla():
        annullate.append(1)
        return 0

    monkeypatch.setattr(sess.playback, "cancel", annulla)
    sess._speaking = None          # il turno era già finito di generare
    assert await sess.open()
    await asyncio.sleep(0.3)
    assert sess.how_it_went()["resumes_succeeded"] == 1
    assert annullate == [], "ha buttato una frase già completa"
    await sess.close()


def test_the_delivery_rules_fill_the_silence_while_the_message_is_released():
    s = __import__("test_message_delivery_v3211a")._sessione()
    assert "non restare in silenzio" in s._rules_for_this_kind_of_call()


def test_completed_with_ring_timeout_is_no_answer():
    """Gate B dal vivo: `completed` e `timeout` arrivano insieme, in ordine qualunque."""
    from telephone.carrier import read_event

    detto = read_event({"status": "completed", "reason": "ring_timeout"})
    assert detto["what"] == "ended" and detto["ended_how"] == "no_answer"
    assert read_event({"status": "completed", "reason": "ok"})["ended_how"] == "they_hung_up"


def test_a_second_end_event_does_not_rewrite_the_end():
    import inspect

    import telephone.vonage_router as vr

    testo = inspect.getsource(vr.event)
    assert 'if call.state in ("ended", "failed", "expired"):' in testo


def test_the_ring_timeout_is_read_from_detail_too():
    """Gate B dal vivo (terzo giro): il motivo stava in `detail`."""
    from telephone.carrier import read_event

    assert read_event({"status": "completed", "detail": "ring_timeout"})["ended_how"] == "no_answer"


def test_a_call_never_answered_cannot_end_with_a_hang_up():
    import inspect

    import telephone.vonage_router as vr

    testo = inspect.getsource(vr.event)
    assert 'and not call.started_at:' in testo
    assert 'said["ended_how"] = "no_answer"' in testo


@pytest.mark.asyncio
async def test_old_calls_told_wrong_by_the_network_are_corrected():
    """Mai risposte, nessun esito, «hanno riagganciato»: diventano «nessuna risposta»."""
    from telephone.service import settle_the_forgotten

    db = FintoDb()
    storta = _finita(id="tel_storta", started_at=None, ended_at="2026-09-19T16:15:09+00:00")
    buona = _finita(id="tel_buona")
    db.phone_calls.righe += [storta.model_dump(), buona.model_dump()]
    db.phone_calls.righe[1]["metrics"] = {"outcome": {"status": "success"}}
    await settle_the_forgotten(db)
    per_id = {r["id"]: r for r in db.phone_calls.righe}
    assert per_id["tel_storta"]["how_it_ended"] == "no_answer"
    assert per_id["tel_storta"]["status_reads"] == "nessuna_risposta"
    assert per_id["tel_buona"]["how_it_ended"] == "they_hung_up"
