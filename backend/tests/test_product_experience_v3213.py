"""
V3.21.3 — quello che il prodotto deve dire, e come fa a saperlo.

    UNA DOMANDA RISPOSTA NON RESTA APERTA. UN AGGIORNAMENTO DICE DA DOVE VIENE.

Queste prove tengono ferme le decisioni del rebuild che vivono nel backend: le
domande della Home si chiudono quando si risponde nella conversazione; ogni
aggiornamento porta la sua provenienza e dice se serve qualcosa; «portami a
lavoro» confronta i modi invece di sputare link; tornare in un posto è un
evento diverso dall'arrivarci; e mentre ORA lavora si dice quello che sta
facendo davvero, mai un'attività inventata.
"""

from __future__ import annotations

import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from test_post_call_application_v315 import FintoDb  # noqa: E402


# ===========================================================================
# 3 · Le domande per te si chiudono da sole
# ===========================================================================

def _domanda(**cambia):
    from waiting.models import OpenQuestion, ResumePointer, WorkRefs

    campi = dict(
        user_id="u1",
        question="È questo il numero corretto?",
        refs=WorkRefs(session_id="ces_1"),
        resume=ResumePointer(kind="conversation"),
        created_at="2026-09-19T10:00:00+00:00",
    )
    campi.update(cambia)
    return OpenQuestion(**campi)


@pytest.mark.asyncio
async def test_answering_in_the_thread_closes_the_home_question():
    """Misurato in app: si rispondeva in chat e la domanda restava in Home."""
    from waiting.service import WaitingService

    db = FintoDb()
    db.open_questions.righe.append(_domanda().model_dump())
    service = WaitingService(db)

    chiuse = await service.answered_in_the_thread("u1", "ces_1", answer="sì")
    assert chiuse == 1
    riga = db.open_questions.righe[0]
    assert riga["status"] == "answered"
    assert riga["answer_source"] == "ora"
    assert riga["continuation"]["status"] == "done"
    assert await service.list_open("u1") == []


@pytest.mark.asyncio
async def test_a_question_from_another_thread_stays_open():
    from waiting.service import WaitingService

    db = FintoDb()
    db.open_questions.righe.append(_domanda(refs=__import__(
        "waiting.models", fromlist=["WorkRefs"]).WorkRefs(session_id="ces_altra")).model_dump())
    assert await WaitingService(db).answered_in_the_thread("u1", "ces_1", answer="sì") == 0
    assert db.open_questions.righe[0]["status"] == "open"


@pytest.mark.asyncio
async def test_questions_already_answered_in_the_past_are_reconciled():
    """Chi ha già risposto prima di questa regola non se la ritrova davanti."""
    from waiting.service import WaitingService

    db = FintoDb()
    db.open_questions.righe.append(_domanda().model_dump())
    db.conversation_sessions.righe.append({
        "id": "ces_1", "user_id": "u1",
        "history": [
            {"role": "ora", "text": "È questo il numero corretto?", "at": "2026-09-19T10:00:00+00:00"},
            {"role": "user", "text": "sì", "at": "2026-09-19T10:01:00+00:00"},
        ],
    })
    assert await WaitingService(db).reconcile_with_threads("u1") == 1
    assert db.open_questions.righe[0]["status"] == "answered"


@pytest.mark.asyncio
async def test_a_question_asked_after_the_last_message_stays_open():
    """La riconciliazione non chiude una domanda più recente della risposta."""
    from waiting.service import WaitingService

    db = FintoDb()
    db.open_questions.righe.append(_domanda(created_at="2026-09-19T12:00:00+00:00").model_dump())
    db.conversation_sessions.righe.append({
        "id": "ces_1", "user_id": "u1",
        "history": [{"role": "user", "text": "sì", "at": "2026-09-19T10:01:00+00:00"}],
    })
    assert await WaitingService(db).reconcile_with_threads("u1") == 0
    assert db.open_questions.righe[0]["status"] == "open"


def test_the_chat_closes_its_questions_when_the_call_is_over():
    import inspect

    import telephone.chat_report as report

    testo = inspect.getsource(report.tell_the_chat)
    assert "close_for_work" in testo and "call_finished" in testo


# ===========================================================================
# 4 · Gli aggiornamenti dicono da dove vengono
# ===========================================================================

def _obiettivo(**cambia):
    from agent.models import AutonomousGoal

    campi = dict(
        owner_id="u1",
        objective="Avere il ritiro del certificato in agenda per giovedì",
        desired_outcome="Il ritiro è segnato in calendario giovedì mattina",
        why_now="L'ufficio anagrafe apre solo la mattina",
        source_kind="calendar_event",
        created_at="2026-09-18T09:00:00+00:00",
    )
    campi.update(cambia)
    return AutonomousGoal(**campi)


def test_an_update_says_what_where_from_and_what_it_needs():
    scheda = _obiettivo().for_human()
    assert scheda["what"].startswith("Avere il ritiro")
    # V3.21.3a: la fonte si legge dentro «Fonte: …», quindi minuscola, e
    # dice *nel* calendario *del* giorno — non un titolo staccato.
    assert scheda["source"] == "appuntamento nel calendario del 18 settembre"
    assert scheda["why_now"]
    #     NIENTE DA FARE E' UNA RISPOSTA, E SI DICE.
    assert scheda["needs_you"] == ""


def test_an_update_that_needs_the_person_says_so():
    manca = _obiettivo(requires_user_input=True).for_human()
    assert "sai solo tu" in manca["needs_you"]
    autorita = _obiettivo(requires_user_authority=True).for_human()
    assert "via libera" in autorita["needs_you"]


def test_a_goal_the_person_asked_for_says_so():
    mia = _obiettivo(origin="user_requested").for_human()
    assert mia["source"] == "me l'hai chiesto tu il 18 settembre"


def test_an_unknown_origin_is_not_invented():
    ignota = _obiettivo(source_kind="", origin="agent_initiated").for_human()
    # V3.21.3a: «Nata dal lavoro di ORA» era una perifrasi per «non lo so».
    # Una fonte che non si ricostruisce si dichiara.
    assert ignota["source"] == "originale non disponibile"


# ===========================================================================
# 7 · «Portami a lavoro» — prima il consiglio, poi i link
# ===========================================================================

@pytest.mark.asyncio
async def test_the_journey_compares_the_ways_of_getting_there(monkeypatch):
    import places.caps as caps

    tempi = {"drive": 1320, "transit": 1680, "bicycle": 2100}

    async def finto(*, origin, destination, travel_mode="drive"):
        return {
            "available": True,
            "duration_seconds": tempi[travel_mode],
            "distance_meters": 8200,
            "reflects_current_traffic": travel_mode == "drive",
        }

    monkeypatch.setattr("places.routing.get_route", finto)
    scelte = await caps._how_to_get_there({"latitude": 45.0, "longitude": 9.0},
                                          {"latitude": 45.1, "longitude": 9.1})
    assert [s["mode"] for s in scelte] == ["drive", "transit", "bicycle"]
    assert scelte[0]["duration_label"] == "22 min"
    assert scelte[0]["recommended"] is True
    assert scelte[1]["recommended"] is False
    #     IL TRAFFICO SI DICE SOLO DOVE E' STATO CONSIDERATO.
    assert scelte[0]["reflects_current_traffic"] is True
    assert scelte[2]["reflects_current_traffic"] is False


@pytest.mark.asyncio
async def test_without_a_routing_provider_nothing_is_invented(monkeypatch):
    import places.caps as caps

    async def niente(*, origin, destination, travel_mode="drive"):
        return {"available": False, "why_unavailable": "nessun provider configurato"}

    monkeypatch.setattr("places.routing.get_route", niente)
    assert await caps._how_to_get_there({"latitude": 1.0, "longitude": 1.0},
                                        {"latitude": 2.0, "longitude": 2.0}) == []
    nota = caps._routing_note()
    assert nota["available"] in (True, False)
    assert isinstance(nota["why_unavailable"], str)


@pytest.mark.asyncio
async def test_the_advice_says_when_to_leave(monkeypatch):
    import places.caps as caps

    class Giornata:
        @staticmethod
        def to_dict():
            return {"events": [{"title": "riunione Team Prodotto",
                                "start": "2026-09-20T11:00:00+02:00"}]}

    class Servizio:
        async def today(self, uid, tz_name=""):
            return Giornata()

    monkeypatch.setattr("deps.get_daily_summary_service", lambda: Servizio())
    scelte = [{"mode": "drive", "duration_seconds": 1320, "recommended": True}]
    frase, quando = await caps._when_to_leave(None, "u1", scelte)
    assert "partire entro le 10:28" in frase
    assert "riunione Team Prodotto delle 11:00" in frase
    assert quando == "10:28"


@pytest.mark.asyncio
async def test_no_calendar_no_advice(monkeypatch):
    import places.caps as caps

    class Vuota:
        @staticmethod
        def to_dict():
            return {"events": []}

    class Servizio:
        async def today(self, uid, tz_name=""):
            return Vuota()

    monkeypatch.setattr("deps.get_daily_summary_service", lambda: Servizio())
    frase, quando = await caps._when_to_leave(
        None, "u1", [{"mode": "drive", "duration_seconds": 600, "recommended": True}])
    assert frase == "" and quando == ""


def test_the_chat_carries_the_journey_not_only_the_links():
    from conversation_engine.ai_core.loop import _journey_from

    oss = [{
        "name": "open_navigation",
        "payload": {
            "capability": "open_navigation",
            "ready": True,
            "place": {"label": "Ufficio"},
            "journey_options": [
                {"mode": "drive", "label": "In auto", "duration_label": "22 min",
                 "duration_seconds": 1320, "recommended": True},
            ],
            "advice": "Ti consiglio di partire entro le 10:20.",
        },
    }]
    fuori = _journey_from(oss)
    assert fuori["destination"] == "Ufficio"
    assert fuori["options"][0]["label"] == "In auto"
    assert "10:20" in fuori["advice"]
    assert _journey_from([{"name": "altro", "payload": {}}]) == {}


# ===========================================================================
# 6 · Mentre ORA lavora, si dice che cosa sta facendo
# ===========================================================================

def test_the_waiting_state_is_a_real_activity():
    from conversation_engine.ai_core.loop import what_is_happening

    assert what_is_happening("get_calendar") == "Controllo il tuo calendario…"
    assert what_is_happening("prepare_a_phone_call") == "Cerco il contatto…"
    assert what_is_happening("open_navigation").startswith("Verifico il percorso")
    #     UNA CAPACITA' SCONOSCIUTA NON SI RACCONTA: SI DICE IL VERO GENERICO.
    generico = what_is_happening("capacita_che_non_esiste")
    assert generico == "Sto cercando quello che serve…"


def test_the_turn_phases_are_measured():
    """«La chat è lenta» non è una diagnosi: queste sono le fasi, in millisecondi."""
    import inspect

    import conversation_engine.ai_core.loop as loop

    testo = inspect.getsource(loop)
    assert '_fase("context", _t)' in testo
    assert '_fase("model", _t)' in testo
    assert '_fase("tools", _t)' in testo


# ===========================================================================
# 8 · Entrato, uscito, tornato
# ===========================================================================

def _osservazione(quando: str):
    from places.models import Coordinates, PresenceObservation

    return PresenceObservation(
        user_id="u1",
        coordinates=Coordinates(latitude=45.0, longitude=9.0),
        accuracy_meters=20.0,
        observed_at=quando,
        source="device",
    )


def _zona():
    from places.models import Coordinates, PresenceZone

    return PresenceZone(
        center=Coordinates(latitude=45.0, longitude=9.0),
        entry_radius_m=100, exit_radius_m=160,
    )


def _dentro(quando: str = ""):
    from places.models import ZoneHit

    return ZoneHit(place_id="pl_1", distance_m=10.0, inside_entry=True,
                   inside_exit=True, zone=_zona())


def test_coming_back_is_not_the_same_as_arriving():
    from places import presence
    from places.models import PresenceState

    stato = PresenceState(user_id="u1", place_id="pl_1", status="outside",
                          left_at="2026-09-20T09:00:00+00:00")
    dentro = _dentro("")
    quando = ["2026-09-20T12:00:00+00:00", "2026-09-20T12:03:00+00:00",
              "2026-09-20T12:06:00+00:00", "2026-09-20T12:09:00+00:00"]
    cambio = ""
    for t in quando:
        stato, cambio = presence.advance(stato, _osservazione(t), dentro)
        if cambio:
            break
    assert cambio == "returned"
    assert stato.status == "present"
    assert stato.left_at is None


def test_arriving_after_a_long_time_is_arriving():
    from places import presence
    from places.models import PresenceState

    stato = PresenceState(user_id="u1", place_id="pl_1", status="outside",
                          left_at="2026-09-17T09:00:00+00:00")
    dentro = _dentro("")
    cambio = ""
    for t in ("2026-09-20T12:00:00+00:00", "2026-09-20T12:03:00+00:00",
              "2026-09-20T12:06:00+00:00", "2026-09-20T12:09:00+00:00"):
        stato, cambio = presence.advance(stato, _osservazione(t), dentro)
        if cambio:
            break
    assert cambio == "entered"


def test_leaving_remembers_when():
    from places import presence
    from places.models import PresenceState

    stato = PresenceState(user_id="u1", place_id="pl_1", status="present",
                          since="2026-09-20T08:00:00+00:00")
    cambio = ""
    for t in ("2026-09-20T09:00:00+00:00", "2026-09-20T09:05:00+00:00",
              "2026-09-20T09:10:00+00:00", "2026-09-20T09:15:00+00:00"):
        stato, cambio = presence.advance(stato, _osservazione(t), None)
        if cambio:
            break
    assert cambio == "exited"
    assert stato.left_at is not None


def test_the_service_reports_the_three_events():
    import inspect

    import places.service as service

    testo = inspect.getsource(service)
    assert 'out["returned"] = returned' in testo
    assert 'if change in ("entered", "returned"):' in testo


# ===========================================================================
# 9 · La preparazione della telefonata mostra il messaggio
# ===========================================================================

def test_the_preparation_card_carries_the_message():
    import inspect

    import preparation.service as service

    assert '"message_to_deliver": prep.message_to_deliver or ""' in inspect.getsource(service.as_a_card)


@pytest.mark.asyncio
async def test_a_question_about_a_finished_call_is_closed():
    """«Vuoi che la chiami?» su una telefonata già fatta non è più una domanda."""
    from waiting.service import WaitingService

    db = FintoDb()
    db.open_questions.righe.append(
        _domanda(question="Vuoi che la chiami?").model_dump())
    db.conversation_sessions.righe.append({"id": "ces_1", "user_id": "u1", "history": []})
    db.phone_calls.righe.append({
        "id": "tel_1", "owner_id": "u1", "chat_session_id": "ces_1", "state": "ended",
    })
    assert await WaitingService(db).reconcile_with_threads("u1") == 1
    assert db.open_questions.righe[0]["status"] == "cancelled"
    assert db.open_questions.righe[0]["resolved_reason"] == "call_finished"


# ===========================================================================
# 9 · Chi chiamare, letto nella frase
# ===========================================================================

def test_who_to_call_is_read_from_the_sentence():
    """
    Nella schermata della preparazione non c'è un modello che estragga il nome:
    prima restava senza contatto e diceva «così non posso telefonare».
    """
    from telephone.requests import who_in

    assert who_in("Chiama Asia e dille che arrivo tardi") == "Asia"
    assert who_in("Chiama la mia ragazza e dille che la amo") == "la mia ragazza"
    assert who_in("chiama il ristorante Da Mario per prenotare") == "il ristorante Da Mario"
    assert who_in("Chiama Lorenzo") == "Lorenzo"
    #     SE NON LO DICE, NON SI INDOVINA.
    assert who_in("vorrei parlare con il dentista") == ""
    assert who_in("") == ""
