"""
Disdire e prenotare, con la stessa disciplina dello spostamento.

    SPOSTARE SBAGLIATO SI VEDE. DISDIRE SBAGLIATO NO.

Un appuntamento spostato nel giorno sbagliato lo si nota; uno disdetto per
errore semplicemente non c'è più, e ci si accorge il giorno in cui non ci si
presenta a quello giusto. Per questo qui l'identità si controlla due volte e
non c'è nessuna aritmetica da verificare.

    E PRENOTARE È L'UNICA DELLE TRE CHE PUÒ CREARE UN DOPPIONE.

Spostare e disdire agiscono su una cosa che esiste: al massimo la toccano due
volte, e la seconda non cambia niente. Creare invece, ripetuto, produce due
appuntamenti — e due appuntamenti dallo stesso dentista sono una telefonata in
più che qualcuno dovrà fare per disdirne uno.
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from test_post_call_application_v315 import (  # noqa: E402
    APPUNTAMENTO, FintoDb, FintoGoogle, _vecchia,
)


# ---------------------------------------------------------------------------
# Il banco
# ---------------------------------------------------------------------------

DOMANI = "2099-09-20T10:00:00+02:00"


def _chiamata(perche: str, **cambia):
    from telephone.models import Mandate, PhoneCall

    campi = dict(
        id="tel_uno",
        owner_id="u1",
        to_number="+393000000000",
        calling_whom="Studio Dentistico Bianchi",
        mandate=Mandate(
            why_calling=perche,
            may_agree_to=["quello che mi propongono fra lunedì e mercoledì"],
            must_bring_back=["lo studio conferma"],
        ),
        state="ended",
        how_it_ended="they_hung_up",
        started_at="2026-09-14T14:00:10+00:00",
        ended_at="2026-09-14T14:01:02+00:00",
    )
    campi.update(cambia)
    return PhoneCall(**campi)


def _disdetta(**cambia):
    return _chiamata("disdire il mio appuntamento dal dentista", **cambia)


def _prenotazione(**cambia):
    return _chiamata("prenotare una visita dal dentista", **cambia)


def _esito(confirmed, status="success"):
    from telephone.mission import CallMissionOutcome

    return CallMissionOutcome(
        mission_id="mis_tel_uno", status=status, confirmed_changes=confirmed,
    )


class _FintoGateway:
    """
    Il livello che crea eventi, con la sua deduplica — che è il punto.

    `create_from_candidate` non fa un secondo evento per la stessa coppia
    documento-candidato: restituisce quello che c'era. Qui il candidato è la
    missione, e questo banco riproduce esattamente quel comportamento perché è
    su quello che poggia tutta l'idempotenza della prenotazione.
    """

    creati = []

    def __init__(self, db):
        self.db = db

    def get(self, _nome):
        return self

    async def create_from_candidate(self, *, user_id, candidate):
        gia = await self.db.calendar_event_drafts.find_one({
            "user_id": user_id,
            "source_document_id": candidate["source_document_id"],
            "source_event_candidate_id": candidate["id"],
        })
        if gia:
            return dict(gia)
        nuovo = {
            "id": f"ced_{len(_FintoGateway.creati) + 1}",
            "user_id": user_id,
            "title": candidate["title"],
            "start_datetime": candidate["start_datetime"],
            "end_datetime": candidate["end_datetime"],
            "timezone": candidate["timezone"],
            "status": "confirmed",
            "source_document_id": candidate["source_document_id"],
            "source_event_candidate_id": candidate["id"],
            "google_event_id": None,
            "sync_status": "local_only",
        }
        _FintoGateway.creati.append(nuovo["id"])
        self.db.calendar_event_drafts.righe.append(dict(nuovo))
        return dict(nuovo)


class _FintoCalendario(FintoGoogle):
    """Aggiunge a FintoGoogle quello che disdetta e prenotazione chiedono."""

    tolti = []

    class _Provider:
        @staticmethod
        async def delete_event(*, access_token, calendar_id, event_id):
            _FintoCalendario.tolti.append(event_id)
            return True

    class _Gcal:
        provider = None

        @staticmethod
        async def _get_access_token(*, user_id, instance):
            return "un-token"

    def __init__(self, db):
        super().__init__(db)
        self.gcal = _FintoCalendario._Gcal()
        self.gcal.provider = _FintoCalendario._Provider()

    async def _instance_for_user(self, user_id):
        return {"id": "ci_1", "metadata": {"default_calendar_id": "cal@ora"}}

    async def sync_draft(self, *, user_id, draft_id):
        FintoGoogle.scritture.append((user_id, draft_id, {"create": True}))
        await self.db.calendar_event_drafts.update_one(
            {"id": draft_id},
            {"$set": {"google_event_id": f"g_{draft_id}", "sync_status": "synced"}},
        )
        return await self.db.calendar_event_drafts.find_one({"id": draft_id})


@pytest.fixture
def mondo(monkeypatch):
    import telephone.domains.calendar as adattatore

    FintoGoogle.scritture = []
    FintoGoogle.solleva = None
    _FintoCalendario.tolti = []
    _FintoGateway.creati = []

    monkeypatch.setattr(adattatore, "_the_calendar", _FintoCalendario)
    monkeypatch.setattr(
        "documents.intelligence.calendar_adapter.CalendarGateway",
        _FintoGateway, raising=True,
    )

    async def concesso(*_a, **_k):
        return ""

    monkeypatch.setattr(adattatore, "_consent_missing", concesso)

    db = FintoDb()
    db.calendar_event_drafts.righe.append({
        **APPUNTAMENTO, "google_event_id": "g_abc", "google_calendar_id": "cal@ora",
    })
    return db


async def _lega(db, call, **kw):
    from telephone.binding import bind_a_calendar_event

    return await bind_a_calendar_event(
        db, call=call, even_if_it_is_past=True, **kw,
    )


def _stato(db, ident="cal_abc123"):
    for r in db.calendar_event_drafts.righe:
        if r["id"] == ident:
            return r
    return None


async def _appesa(db, legame):
    from telephone.application import APPLICATIONS, CallMissionApplication, key_for

    chiave = key_for(legame.mission_id, legame.target.operation,
                     legame.target.entity_id)
    record = CallMissionApplication(
        mission_id=legame.mission_id, call_id="tel_uno", owner_id="u1",
        target_domain="calendar", target_entity_id=legame.target.entity_id,
        operation=legame.target.operation, outcome_status="success",
        application_status="pending", created_at=_vecchia(),
        idempotency_key=chiave,
    )
    await db[APPLICATIONS].insert_one({**record.model_dump(), "_id": chiave})
    return record


def _mettici_la_chiamata(db, call, esito):
    call.metrics = {"outcome": esito.model_dump()}
    db["phone_calls"].righe.append(call.model_dump())


# ===========================================================================
# CANCEL
# ===========================================================================

CONFERMA_DISDETTA = {"appointment_date": "2026-09-14", "appointment_time": "16:00"}


@pytest.mark.asyncio
async def test_cancel_success(mondo):
    """Confermata la disdetta → l'appuntamento sparisce da qui e da Google."""
    from telephone.application import apply_the_outcome

    legame, perche, _ = await _lega(mondo, _disdetta(), calendar_ref="cal_abc123")
    assert perche == "" and legame.target.operation == "cancel"

    record = await apply_the_outcome(
        mondo, _disdetta(), _esito(CONFERMA_DISDETTA))

    assert record.application_status == "applied"
    assert record.writes == ["calendar:cal_abc123"]
    assert _stato(mondo)["status"] == "cancelled"
    assert _FintoCalendario.tolti == ["g_abc"]


@pytest.mark.asyncio
async def test_cancel_needs_user_changes_nothing(mondo):
    """`needs_user` non toglie niente: è un esito, non un permesso a metà."""
    from telephone.application import apply_the_outcome

    await _lega(mondo, _disdetta(), calendar_ref="cal_abc123")
    record = await apply_the_outcome(
        mondo, _disdetta(), _esito({}, status="needs_user"))

    assert record.application_status == "skipped"
    assert _stato(mondo)["status"] == "confirmed"
    assert _FintoCalendario.tolti == []


@pytest.mark.asyncio
async def test_cancel_on_something_already_cancelled(mondo):
    """
    Era già via, e non l'abbiamo tolto noi.

    Non è un fallimento e non è un successo da rivendicare: è una cosa che non
    c'era più da fare.
    """
    from telephone.application import apply_the_outcome

    legame, _, _ = await _lega(mondo, _disdetta(), calendar_ref="cal_abc123")
    await mondo.calendar_event_drafts.update_one(
        {"id": "cal_abc123"}, {"$set": {"status": "cancelled"}})

    record = await apply_the_outcome(
        mondo, _disdetta(), _esito(CONFERMA_DISDETTA))

    assert record.application_status == "skipped"
    assert "era già disdetto" in record.error
    assert _FintoCalendario.tolti == []


@pytest.mark.asyncio
async def test_cancel_conflict_when_the_hour_does_not_match(mondo):
    """
        UNA DISDETTA SBAGLIATA NON SI VEDE FINCHÉ NON TE NE ACCORGI.

    La controparte dice di aver tolto le 16; in calendario ci sono le 9. Non
    stavano parlando di questo appuntamento, e su questo non si tocca niente.
    """
    from telephone.application import apply_the_outcome

    await mondo.calendar_event_drafts.update_one(
        {"id": "cal_abc123"},
        {"$set": {"start_datetime": "2026-09-14T09:00:00+02:00"}})
    await _lega(mondo, _disdetta(), calendar_ref="cal_abc123")

    record = await apply_the_outcome(
        mondo, _disdetta(), _esito(CONFERMA_DISDETTA))

    assert record.application_status == "conflict"
    assert "16:00" in record.error and "09:00" in record.error
    assert _stato(mondo)["status"] == "confirmed"
    assert _FintoCalendario.tolti == []


@pytest.mark.asyncio
async def test_cancel_applied_twice_removes_once(mondo):
    """Due applicazioni, una disdetta."""
    from telephone.application import APPLICATIONS, apply_the_outcome

    await _lega(mondo, _disdetta(), calendar_ref="cal_abc123")
    await apply_the_outcome(mondo, _disdetta(), _esito(CONFERMA_DISDETTA))
    secondo = await apply_the_outcome(mondo, _disdetta(), _esito(CONFERMA_DISDETTA))

    assert secondo.application_status == "applied"
    assert _FintoCalendario.tolti == ["g_abc"]
    assert len(mondo[APPLICATIONS].righe) == 1


@pytest.mark.asyncio
async def test_cancel_recovery_after_a_crash(mondo):
    """
    Il recupero della V3.15.2 vale anche qui, e legge il mondo al contrario.

    Per uno spostamento «è già dove doveva arrivare» vuol dire riuscito; per
    una disdetta lo vuol dire «non c'è più». Sono due funzioni invece di una
    con un flag dentro, ed è per questo che la differenza si vede.
    """
    from telephone.application import recover_stale

    call = _disdetta()
    esito = _esito(CONFERMA_DISDETTA)
    legame, _, _ = await _lega(mondo, call, calendar_ref="cal_abc123")
    _mettici_la_chiamata(mondo, call, esito)
    await _appesa(mondo, legame)

    # Morto prima della scrittura: l'appuntamento è ancora lì.
    chiusi = await recover_stale(mondo)

    assert chiusi[0].application_status == "applied"
    assert _stato(mondo)["status"] == "cancelled"
    assert _FintoCalendario.tolti == ["g_abc"]


@pytest.mark.asyncio
async def test_cancel_recovery_after_the_write_does_not_remove_twice(mondo):
    """Morto dopo: si chiude il record e non si tocca niente."""
    from telephone.application import recover_stale

    call = _disdetta()
    esito = _esito(CONFERMA_DISDETTA)
    legame, _, _ = await _lega(mondo, call, calendar_ref="cal_abc123")
    _mettici_la_chiamata(mondo, call, esito)
    await mondo.calendar_event_drafts.update_one(
        {"id": "cal_abc123"}, {"$set": {"status": "cancelled"}})
    await _appesa(mondo, legame)

    chiusi = await recover_stale(mondo)

    assert chiusi[0].application_status == "applied"
    assert _FintoCalendario.tolti == []


def test_cancel_reads_like_a_person_wrote_it():
    """
    «Hanno confermato la disdetta alle 18:00» si legge come se avessero
    disdetto alle diciotto. Per una disdetta l'ora non è un risultato: è il
    nome dell'appuntamento tolto.
    """
    from telephone.history import as_a_card
    from telephone.application import CallMissionApplication

    call = _disdetta()
    call.metrics = {"outcome": {
        "mission_id": "mis_tel_uno", "status": "success",
        "confirmed_changes": CONFERMA_DISDETTA,
    }}

    fatta = as_a_card(call, None)
    assert fatta["outcome_summary"] == "Appuntamento disdetto alle 16:00."

    rotta = CallMissionApplication(
        mission_id="mis_tel_uno", call_id="tel_uno", owner_id="u1",
        target_domain="calendar", target_entity_id="cal_abc123",
        operation="cancel", outcome_status="success",
        application_status="failed", idempotency_key="k",
    )
    riga = as_a_card(call, rotta)["outcome_summary"]
    assert riga.startswith("Hanno confermato la disdetta dell'appuntamento alle 16:00,")
    assert "non sono riuscita ad aggiornare il calendario" in riga
    assert "Appuntamento disdetto" not in riga


# ===========================================================================
# BOOK
# ===========================================================================

CONFERMA_PRENOTAZIONE = {
    "appointment_date": "2099-09-20",
    "appointment_time": "10:00",
    "duration_minutes": "30",
}


@pytest.mark.asyncio
async def test_book_success(mondo):
    """Confermata la prenotazione → nasce un evento, uno solo."""
    from telephone.application import apply_the_outcome

    legame, perche, _ = await _lega(
        mondo, _prenotazione(), desired_datetime=DOMANI, desired_minutes=30)
    assert perche == ""
    assert legame.target.operation == "book"
    # Prima della telefonata non esiste ancora niente da modificare.
    assert legame.target.entity_id == ""
    assert legame.desired["start_datetime"] == DOMANI

    record = await apply_the_outcome(
        mondo, _prenotazione(), _esito(CONFERMA_PRENOTAZIONE))

    assert record.application_status == "applied"
    assert _FintoGateway.creati == ["ced_1"]
    nato = _stato(mondo, "ced_1")
    assert nato["start_datetime"].startswith("2099-09-20T10:00")
    assert nato["end_datetime"].startswith("2099-09-20T10:30")
    assert nato["title"] == "Studio Dentistico Bianchi"
    assert nato["google_event_id"] == "g_ced_1"


@pytest.mark.asyncio
async def test_book_needs_user_creates_nothing(mondo):
    """`needs_user` non crea niente. Un evento inventato è peggio di nessuno."""
    from telephone.application import apply_the_outcome

    await _lega(mondo, _prenotazione(), desired_datetime=DOMANI)
    record = await apply_the_outcome(
        mondo, _prenotazione(), _esito({}, status="needs_user"))

    assert record.application_status == "skipped"
    assert _FintoGateway.creati == []


@pytest.mark.asyncio
async def test_book_without_a_confirmed_time_creates_nothing(mondo):
    """
    Una prenotazione senza un quando non è una prenotazione.

    Qui non si ripiega su quello che si era chiesto: se la controparte non ha
    detto data e ora, quello che ha confermato non si sa.
    """
    from telephone.application import apply_the_outcome

    await _lega(mondo, _prenotazione(), desired_datetime=DOMANI)
    record = await apply_the_outcome(
        mondo, _prenotazione(), _esito({"appointment_date": "2099-09-20"}))

    assert record.application_status == "skipped"
    assert "data e un'ora confermate" in record.error
    assert _FintoGateway.creati == []


@pytest.mark.asyncio
async def test_book_applied_twice_creates_one_event(mondo):
    """
        PRENOTARE È L'UNICA DELLE TRE CHE PUÒ CREARE UN DOPPIONE.

    E la difesa non è un controllo nostro: è il nome della missione, che
    l'evento porta addosso. Un controllo si può dimenticare di chiamarlo; un
    nome no.
    """
    from telephone.application import APPLICATIONS, apply_the_outcome

    await _lega(mondo, _prenotazione(), desired_datetime=DOMANI)
    await apply_the_outcome(mondo, _prenotazione(), _esito(CONFERMA_PRENOTAZIONE))
    secondo = await apply_the_outcome(
        mondo, _prenotazione(), _esito(CONFERMA_PRENOTAZIONE))

    assert secondo.application_status == "applied"
    assert _FintoGateway.creati == ["ced_1"]
    assert len(mondo[APPLICATIONS].righe) == 1


@pytest.mark.asyncio
async def test_book_crash_before_the_write_creates_it_once(mondo):
    """Morto prima: l'evento non c'è, si crea. Una volta."""
    from telephone.application import recover_stale

    call = _prenotazione()
    esito = _esito(CONFERMA_PRENOTAZIONE)
    legame, _, _ = await _lega(mondo, call, desired_datetime=DOMANI)
    _mettici_la_chiamata(mondo, call, esito)
    await _appesa(mondo, legame)

    chiusi = await recover_stale(mondo)

    assert chiusi[0].application_status == "applied"
    assert _FintoGateway.creati == ["ced_1"]


@pytest.mark.asyncio
async def test_book_crash_after_the_write_does_not_create_a_second(mondo):
    """
    Morto dopo: l'evento c'è già, e lo si riconosce dal nome della missione.

    Non per somiglianza di titolo e orario — che è esattamente la ricerca che
    questo progetto ha vietato a sé stesso.
    """
    from telephone.application import recover_stale

    call = _prenotazione()
    esito = _esito(CONFERMA_PRENOTAZIONE)
    legame, _, _ = await _lega(mondo, call, desired_datetime=DOMANI)
    _mettici_la_chiamata(mondo, call, esito)
    # La scrittura era andata: l'evento porta il nome di questa missione.
    mondo.calendar_event_drafts.righe.append({
        "id": "ced_esistente", "user_id": "u1", "title": "Studio Dentistico Bianchi",
        "start_datetime": "2099-09-20T10:00:00+02:00",
        "end_datetime": "2099-09-20T10:30:00+02:00",
        "timezone": "Europe/Rome", "status": "confirmed",
        "source_document_id": "ora_phone_call",
        "source_event_candidate_id": legame.mission_id,
    })
    await _appesa(mondo, legame)

    chiusi = await recover_stale(mondo)

    assert chiusi[0].application_status == "applied"
    assert chiusi[0].writes == ["calendar:ced_esistente"]
    # Nessuna seconda creazione, nessuna seconda scrittura su Google.
    assert _FintoGateway.creati == []
    assert FintoGoogle.scritture == []


@pytest.mark.asyncio
async def test_book_recovery_remembers_which_event_was_born(mondo):
    """
    Dopo il recupero il legame sa che cosa ha creato.

    Non serve all'idempotenza — quella la garantisce il nome sull'evento — ma
    serve a chi legge: «che cosa ha creato questa telefonata?» deve avere una
    risposta diretta.
    """
    from telephone.binding import binding_for
    from telephone.application import recover_stale

    call = _prenotazione()
    esito = _esito(CONFERMA_PRENOTAZIONE)
    legame, _, _ = await _lega(mondo, call, desired_datetime=DOMANI)
    _mettici_la_chiamata(mondo, call, esito)
    await _appesa(mondo, legame)

    await recover_stale(mondo)

    fresco = await binding_for(mondo, "tel_uno")
    assert fresco.created_entity_id == "ced_1"
    #     E L'IDENTITÀ DELLA MISSIONE NON È CAMBIATA.
    # Se `target.entity_id` si riempisse a cose fatte, la chiave di idempotenza
    # cambierebbe con lui e la prossima applicazione ne scriverebbe una
    # seconda. È successo, e questa riga tiene ferma la correzione.
    assert fresco.target.entity_id == ""


@pytest.mark.asyncio
async def test_book_needs_a_when_before_anybody_dials(mondo):
    """
    «Prenotami dal dentista» senza una data non è una missione.

    È una cosa da concordare prima, e finché non c'è la telefonata riporta e
    basta invece di prenotare a caso.
    """
    from telephone.binding import bind_a_calendar_event

    legame, perche, chiarimento = await bind_a_calendar_event(
        mondo, call=_prenotazione(),
    )
    assert legame is None
    assert "per quando" in perche
    assert chiarimento is False


@pytest.mark.asyncio
async def test_booking_in_the_past_asks_first(mondo):
    """La stessa guardia della V3.15.2, dall'altro lato del tempo."""
    from telephone.binding import bind_a_calendar_event

    legame, domanda, chiarimento = await bind_a_calendar_event(
        mondo, call=_prenotazione(), desired_datetime="2020-01-01T10:00:00+01:00",
    )
    assert legame is None
    assert chiarimento is True
    assert domanda.rstrip().endswith("?")


def test_book_reads_like_a_person_wrote_it():
    from telephone.history import as_a_card

    call = _prenotazione()
    call.metrics = {"outcome": {
        "mission_id": "mis_tel_uno", "status": "success",
        "confirmed_changes": CONFERMA_PRENOTAZIONE,
    }}
    assert as_a_card(call, None)["outcome_summary"] == (
        "Prenotazione effettuata alle 10:00.")


# ===========================================================================
# L'autorità, che non cambia con l'operazione
# ===========================================================================

@pytest.mark.asyncio
async def test_nothing_outside_the_mission_is_written(mondo):
    """
    §3: una disdetta non cambia l'indirizzo, una prenotazione non cambia il
    titolo. Quello che non è stato chiesto si racconta, non si applica.
    """
    from telephone.application import apply_the_outcome

    await _lega(mondo, _disdetta(), calendar_ref="cal_abc123")
    record = await apply_the_outcome(mondo, _disdetta(), _esito(
        {**CONFERMA_DISDETTA, "location": "via Roma 4"}))

    assert record.application_status == "skipped"
    assert "location" in record.error
    assert _stato(mondo)["status"] == "confirmed"


def test_the_model_is_asked_the_right_question_for_each_mission():
    """
        CHE COSA SIA UNA CONFERMA CAMBIA CON LA MISSIONE.

    Chiedere un `new_time` a chi ha appena disdetto è chiedere un campo
    obbligatorio che non ha senso — e un campo così si riempie comunque, con
    qualcosa.
    """
    from telephone.live import ALLOWED_TOOLS, tools_for

    def conferma(tipo):
        d = {f["name"]: f for f in tools_for(tipo)[0]["function_declarations"]}
        assert set(d) == set(ALLOWED_TOOLS), f"{tipo}: gli strumenti sono cambiati"
        return d["complete_mission"]["parameters"]["properties"]["confirmed_changes"]

    assert "new_time" in conferma("reschedule")["properties"]
    assert "new_time" not in conferma("cancel")["properties"]
    assert conferma("cancel")["required"] == ["appointment_date", "appointment_time"]
    assert "duration_minutes" in conferma("book")["properties"]


@pytest.mark.asyncio
async def test_the_internal_id_never_reaches_whoever_is_talking(mondo):
    """§1: nemmeno adesso. La regola vale per tutte e tre le missioni."""
    from telephone.dossier import TelephoneCallDossier
    from telephone.mission import packet_for

    fascicolo = TelephoneCallDossier(
        owner_id="u1", call_id="tel_uno", on_behalf_of="Francesco")

    legame, _, _ = await _lega(mondo, _disdetta(), calendar_ref="cal_abc123")
    assert "cal_abc123" not in packet_for(
        _disdetta(), fascicolo, binding=legame).for_the_model()

    prenota, _, _ = await _lega(
        mondo, _prenotazione(), desired_datetime=DOMANI)
    packet = packet_for(_prenotazione(), fascicolo, binding=prenota)
    # Ma il quando sì: è l'unica cosa che chi parla deve chiedere.
    assert packet.desired_state.get("when") == DOMANI
    assert "ced_" not in packet.for_the_model()
