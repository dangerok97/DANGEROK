"""
Da «hanno confermato» a «è spostato», una volta sola e solo quando è vero.

    LA TELEFONATA È ANDATA BENE NON VUOL DIRE CHE IL CALENDARIO SIA CAMBIATO.

Fino a questo sprint esisteva un fatto solo. Lo studio confermava, il gate
validava, la scheda diceva «Appuntamento spostato alle 18:00» — e il
calendario restava alle 16:00. Queste prove tengono ferme le cinque cose che
rendono il secondo fatto un fatto:

    l'evento si decide **prima** della telefonata, e chi parla non lo sa mai;
    si applica solo un esito che il backend ha già dichiarato azionabile;
    si applica una volta sola, e a dirlo è la chiave, non un `if`;
    se l'appuntamento è cambiato nel frattempo non si scrive niente sopra;
    e se l'applicazione non riesce, la telefonata resta riuscita — cambia la
    frase che si legge, non l'esito di chi ha risposto al telefono.
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
# Un database finto, con l'unica cosa che qui conta davvero: `_id` è unico
# ---------------------------------------------------------------------------

class GiaPreso(Exception):
    """Quello che Mongo solleva quando una chiave c'è già."""


def _combacia(riga, query) -> bool:
    for chiave, atteso in (query or {}).items():
        if chiave == "$or":
            if not any(_combacia(riga, ramo) for ramo in atteso):
                return False
            continue
        vero = riga.get(chiave)
        if isinstance(atteso, dict):
            if "$in" in atteso and vero not in atteso["$in"]:
                return False
            if "$exists" in atteso and (chiave in riga) != atteso["$exists"]:
                return False
            if "$lt" in atteso and not (vero is not None and vero < atteso["$lt"]):
                return False
        elif vero != atteso:
            return False
    return True


def _senza_id(riga, proiezione):
    fuori = dict(riga)
    if proiezione and proiezione.get("_id") == 0:
        fuori.pop("_id", None)
    return fuori


class Righe:
    def __init__(self, righe):
        self._righe = righe

    def __aiter__(self):
        async def gen():
            for r in self._righe:
                yield r
        return gen()


class Tabella:
    def __init__(self):
        self.righe = []
        self.scritture = 0

    async def find_one(self, query, proiezione=None):
        for r in self.righe:
            if _combacia(r, query):
                return _senza_id(r, proiezione)
        return None

    def find(self, query, proiezione=None):
        return Righe([_senza_id(r, proiezione)
                      for r in self.righe if _combacia(r, query)])

    async def insert_one(self, documento):
        ident = documento.get("_id")
        if ident is not None and any(r.get("_id") == ident for r in self.righe):
            raise GiaPreso(ident)
        self.righe.append(dict(documento))
        self.scritture += 1

    async def find_one_and_update(self, query, cambio):
        """
        Trova e scrive nello stesso gesto, o non fa niente.

            È L'ATOMICITÀ, ED È TUTTO IL PUNTO DELLA RIVENDICAZIONE.

        Fra il trovare e lo scrivere non ci deve stare un secondo processo.
        Qui dentro non c'è un `await` in mezzo, che su un loop solo è
        esattamente la stessa garanzia.
        """
        for r in self.righe:
            if _combacia(r, query):
                r.update(cambio.get("$set") or {})
                self.scritture += 1
                return dict(r)
        return None

    async def update_one(self, query, cambio, upsert=False):
        for r in self.righe:
            if _combacia(r, query):
                r.update(cambio.get("$set") or {})
                for campo, quali in (cambio.get("$addToSet") or {}).items():
                    dentro = r.setdefault(campo, [])
                    for x in (quali or {}).get("$each", []):
                        if x not in dentro:
                            dentro.append(x)
                self.scritture += 1
                return
        if upsert:
            nuovo = dict(query)
            nuovo.update(cambio.get("$set") or {})
            self.righe.append(nuovo)
            self.scritture += 1


class FintoDb:
    def __init__(self):
        self._tabelle = {}

    def __getitem__(self, nome):
        return self._tabelle.setdefault(nome, Tabella())

    def __getattr__(self, nome):
        if nome.startswith("_"):
            raise AttributeError(nome)
        return self[nome]


# ---------------------------------------------------------------------------
# Le cose in gioco
# ---------------------------------------------------------------------------

APPUNTAMENTO = {
    "id": "cal_abc123",
    "user_id": "u1",
    "title": "Dentista",
    "start_datetime": "2026-09-14T16:00:00+02:00",
    "end_datetime": "2026-09-14T16:45:00+02:00",
    "timezone": "Europe/Rome",
    "status": "confirmed",
}


def _chiamata(**cambia):
    from telephone.models import Mandate, PhoneCall

    campi = dict(
        id="tel_uno",
        owner_id="u1",
        to_number="+393000000000",
        calling_whom="Studio Dentistico Bianchi",
        mandate=Mandate(
            why_calling="spostare il mio appuntamento dal dentista di oggi "
                        "dalle 16 alle 18",
            may_agree_to=["confermare le 18:00 di oggi"],
            must_bring_back=["lo studio conferma il nuovo orario"],
        ),
        state="ended",
        how_it_ended="they_hung_up",
        started_at="2026-09-14T14:00:10+00:00",
        ended_at="2026-09-14T14:01:02+00:00",
    )
    campi.update(cambia)
    return PhoneCall(**campi)


def _esito(status="success", **cambia):
    from telephone.mission import CallMissionOutcome

    campi = dict(
        mission_id="mis_tel_uno",
        status=status,
        confirmed_changes={
            "appointment_date": "2026-09-14",
            "old_time": "16:00",
            "new_time": "18:00",
        },
    )
    campi.update(cambia)
    return CallMissionOutcome(**campi)


def _legame(**cambia):
    from telephone.binding import CallMissionBinding, MissionTarget

    campi = dict(
        mission_id="mis_tel_uno",
        call_id="tel_uno",
        owner_id="u1",
        target=MissionTarget(
            domain="calendar", entity_id="cal_abc123", operation="reschedule",
        ),
        expected={
            "start_datetime": "2026-09-14T16:00:00+02:00",
            "end_datetime": "2026-09-14T16:45:00+02:00",
            "timezone": "Europe/Rome",
            "title": "Dentista",
        },
    )
    campi.update(cambia)
    return CallMissionBinding(**campi)


class FintoGoogle:
    """
    Il calendario, quel tanto che basta a vedere se è stato toccato.

    Tiene il conto delle scritture perché è l'unica domanda che le prove
    sull'idempotenza sanno fare: non «com'è finita», ma «quante volte».
    """

    scritture = []
    solleva = None

    def __init__(self, db):
        self.db = db

    async def reschedule_draft(self, *, user_id, draft_id, fields):
        FintoGoogle.scritture.append((user_id, draft_id, dict(fields)))
        if FintoGoogle.solleva is not None:
            raise FintoGoogle.solleva
        riga = await self.db.calendar_event_drafts.find_one(
            {"id": draft_id, "user_id": user_id},
        )
        if riga is None:
            raise LookupError("event_not_found")
        await self.db.calendar_event_drafts.update_one(
            {"id": draft_id}, {"$set": {**fields, "sync_status": "synced"}},
        )
        return {**riga, **fields, "sync_status": "synced"}


@pytest.fixture
def mondo(monkeypatch):
    """Un database, un appuntamento, e un calendario che si lascia guardare."""
    import telephone.domains.calendar as adattatore

    FintoGoogle.scritture = []
    FintoGoogle.solleva = None
    monkeypatch.setattr(adattatore, "_the_calendar", FintoGoogle)

    #     IL CONSENSO È UN CANCELLO VERO, E QUI È APERTO.
    # Queste prove guardano l'applicazione, non il sistema dei permessi, che
    # ha le sue. Aperto di default e chiuso in una prova sola, che è quella
    # che serve: che il cancello ci sia.
    async def concesso(*_a, **_k):
        return ""

    monkeypatch.setattr(adattatore, "_consent_missing", concesso)

    db = FintoDb()
    db.calendar_event_drafts.righe.append(dict(APPUNTAMENTO))
    chiamata = _chiamata()
    chiamata.metrics = {"outcome": _esito().model_dump()}
    db["phone_calls"].righe.append(chiamata.model_dump())
    return db


async def _lega(db, legame=None):
    from telephone.binding import BINDINGS

    legame = legame or _legame()
    await db[BINDINGS].insert_one(legame.model_dump())
    return legame


def _quando(db):
    return db.calendar_event_drafts.righe[0]["start_datetime"]


# ---------------------------------------------------------------------------
# §4 — il legame non viaggia con la voce
# ---------------------------------------------------------------------------

def test_the_model_never_learns_which_event_it_is():
    """
    §4: l'identificativo dell'evento non entra nel packet.

        IL PACCHETTO PORTA IL NOME DEL CAMPO, MAI IL VALORE.

    La stessa regola del numero di telefono, applicata a un dato che sarebbe
    ancora più inutile pronunciare: chi telefona non deve scegliere l'evento,
    quindi non deve nemmeno sapere che gli eventi hanno un nome.
    """
    from telephone.dossier import TelephoneCallDossier
    from telephone.mission import packet_for

    fascicolo = TelephoneCallDossier(
        owner_id="u1", call_id="tel_uno", on_behalf_of="Francesco Cefalà",
    )
    packet = packet_for(_chiamata(), fascicolo, binding=_legame())
    testo = packet.for_the_model()

    assert "cal_abc123" not in testo
    assert "cal_abc123" not in packet.model_dump_json()
    # E nemmeno il numero, che è la regola da cui questa discende.
    assert "393000000000" not in testo


def test_but_the_model_does_learn_when_the_appointment_is():
    """
    §19: il legame porta l'orario di partenza, che serve a parlare.

    Senza, la missione diceva «sposta la visita» senza sapere da quando, e chi
    telefonava doveva farselo dire dallo studio — cioè chiedere una cosa che
    ORA sapeva già.
    """
    from telephone.dossier import TelephoneCallDossier
    from telephone.mission import packet_for

    fascicolo = TelephoneCallDossier(
        owner_id="u1", call_id="tel_uno", on_behalf_of="Francesco Cefalà",
    )
    packet = packet_for(_chiamata(), fascicolo, binding=_legame())

    assert packet.current_state.get("when") == "2026-09-14T16:00:00+02:00"
    assert "16:00" in packet.for_the_model()


# ---------------------------------------------------------------------------
# A — l'esito confermato diventa un calendario diverso
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_confirmed_reschedule_actually_moves_the_appointment(mondo):
    """
    A: successo azionabile → il calendario cambia davvero.

    È la prova che questo sprint esiste per far passare: prima di oggi qui
    finiva tutto, e l'appuntamento restava alle sedici.
    """
    from telephone.application import apply_the_outcome

    await _lega(mondo)
    record = await apply_the_outcome(mondo, _chiamata(), _esito())

    assert record.application_status == "applied"
    assert record.writes == ["calendar:cal_abc123"]
    assert record.outcome_status == "success"
    assert _quando(mondo).startswith("2026-09-14T18:00")
    # E la durata è quella che l'appuntamento aveva: spostare non è accorciare.
    assert mondo.calendar_event_drafts.righe[0]["end_datetime"].startswith(
        "2026-09-14T18:45")


@pytest.mark.asyncio
async def test_the_call_remembers_what_it_changed(mondo):
    """
    §14: `PhoneCall.wrote` finalmente si riempie — ma non è il meccanismo.

    Il campo c'era dal primo giorno ed è rimasto vuoto per tutti gli sprint in
    cui una telefonata non poteva cambiare niente. Adesso può.
    """
    from telephone.application import apply_the_outcome

    await _lega(mondo)
    await apply_the_outcome(mondo, _chiamata(), _esito())

    riga = await mondo["phone_calls"].find_one({"id": "tel_uno"})
    assert riga["wrote"] == ["calendar:cal_abc123"]


# ---------------------------------------------------------------------------
# B, C, D, E — quello che non si applica
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_b_availability_alone_writes_nothing(mondo):
    """
    B: «alle 18 abbiamo posto» non è «l'ho spostato alle 18».

    Il gate lo ferma già in linea, e questo è il secondo cancello: un successo
    senza niente di confermato dentro non è azionabile, e qui non si inventa
    quello che manca.
    """
    from telephone.application import apply_the_outcome

    await _lega(mondo)
    record = await apply_the_outcome(
        mondo, _chiamata(), _esito(confirmed_changes={}),
    )

    assert record.application_status == "skipped"
    assert _quando(mondo).startswith("2026-09-14T16:00")
    assert FintoGoogle.scritture == []


@pytest.mark.asyncio
@pytest.mark.parametrize("stato", ["needs_user", "failed", "partial"])
async def test_cde_every_other_outcome_goes_back_to_a_person(mondo, stato):
    """
    C, D, E: `needs_user`, `failed` e `partial` sono esiti, non permessi.

    Nessuno dei tre è «quasi un successo». Una versione uno che ne applicasse
    qualcuno in qualche caso sarebbe una versione uno di cui non ci si fida.
    """
    from telephone.application import apply_the_outcome

    await _lega(mondo)
    record = await apply_the_outcome(mondo, _chiamata(), _esito(status=stato))

    assert record.application_status == "skipped"
    assert record.outcome_status == stato
    assert _quando(mondo).startswith("2026-09-14T16:00")
    assert FintoGoogle.scritture == []


# ---------------------------------------------------------------------------
# F, G, H — una volta sola, e quando serve
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_f_applying_twice_moves_the_appointment_once(mondo):
    """
    F: due applicazioni, una scrittura.

        UN ESITO SI APPLICA UNA VOLTA SOLA, E SI PUÒ DIMOSTRARE.

    A deciderlo non è un `if` ma la chiave del record: il secondo tentativo
    non arriva nemmeno all'adattatore.
    """
    from telephone.application import apply_the_outcome

    await _lega(mondo)
    primo = await apply_the_outcome(mondo, _chiamata(), _esito())
    secondo = await apply_the_outcome(mondo, _chiamata(), _esito())

    assert primo.idempotency_key == secondo.idempotency_key
    assert secondo.application_status == "applied"
    assert len(FintoGoogle.scritture) == 1
    assert _quando(mondo).startswith("2026-09-14T18:00")


def test_the_key_is_made_of_things_that_do_not_change():
    """
    §7: missione, operazione, oggetto. Non l'ora, non il tentativo.

    Tre cose che restano identiche fra un tentativo e l'altro — è proprio
    questo che le rende capaci di riconoscere il secondo.
    """
    from telephone.application import key_for

    assert key_for("mis_x", "reschedule", "cal_1") == "mis_x|reschedule|cal_1"
    assert key_for("mis_x", "reschedule", "cal_1") == key_for(
        "mis_x", "reschedule", "cal_1")
    assert key_for("mis_x", "reschedule", "cal_1") != key_for(
        "mis_x", "reschedule", "cal_2")


@pytest.mark.asyncio
async def test_g_a_repeated_carrier_event_changes_nothing(mondo):
    """
    G: l'operatore dice due volte che è finita.

    Succede, e l'abbiamo visto. Il trigger non è quel messaggio — è l'esito
    definitivo — ma anche se qualcuno ripassasse di qui due volte, la chiave
    regge lo stesso.
    """
    from telephone.application import APPLICATIONS, apply_the_outcome

    await _lega(mondo)
    for _ in range(3):
        await apply_the_outcome(mondo, _chiamata(), _esito())

    assert len(FintoGoogle.scritture) == 1
    assert len(mondo[APPLICATIONS].righe) == 1


@pytest.mark.asyncio
async def test_h_the_calendar_moves_even_if_the_carrier_never_says_so(mondo):
    """
    H: l'evento dell'operatore non arriva mai.

        IL MOMENTO GIUSTO NON È QUELLO IN CUI LA RETE DICE «COMPLETED».

    È quello in cui l'esito esiste, è validato ed è definitivo: la chiusura
    della sessione. Legarlo al messaggio del carrier voleva dire dipendere da
    una cosa che può arrivare due volte, tardi, o mai.
    """
    from telephone.application import application_for
    from telephone.vonage_router import _apply_what_was_agreed

    await _lega(mondo)

    class Sessione:
        outcome = _esito()

    import telephone.vonage_router as vr
    vecchio, vr.db = vr.db, mondo
    try:
        #     LA CHIAMATA È ANCORA `talking`: NESSUNO HA DETTO CHE È FINITA.
        await _apply_what_was_agreed(_chiamata(state="talking"), Sessione())
    finally:
        vr.db = vecchio

    record = await application_for(mondo, "tel_uno")
    assert record.application_status == "applied"
    assert _quando(mondo).startswith("2026-09-14T18:00")


# ---------------------------------------------------------------------------
# I, J, K — quando non si scrive
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_i_an_appointment_that_moved_meanwhile_is_not_overwritten(mondo):
    """
    I: qualcuno ha spostato l'appuntamento mentre eravamo al telefono.

        UN CALENDARIO SBAGLIATO È PEGGIO DI UN CALENDARIO VECCHIO.

    L'accordo preso riguardava un evento che non esiste più. Non è un errore
    di nessuno, ed è per questo che non è `failed`: è `conflict`, e si dice.
    """
    from telephone.application import apply_the_outcome

    await _lega(mondo)
    await mondo.calendar_event_drafts.update_one(
        {"id": "cal_abc123"},
        {"$set": {"start_datetime": "2026-09-15T09:00:00+02:00"}},
    )
    record = await apply_the_outcome(mondo, _chiamata(), _esito())

    assert record.application_status == "conflict"
    assert FintoGoogle.scritture == []
    assert _quando(mondo).startswith("2026-09-15T09:00")


@pytest.mark.asyncio
async def test_i_bis_they_confirmed_moving_a_different_hour(mondo):
    """
    I: la controparte ha spostato le 16, in calendario ci sono le 9.

    Due controlli diversi con la stessa conclusione. Questo guarda quello che
    ha detto la controparte invece di quello che sapeva il legame — e se le
    due ore non combaciano, non stavano parlando di questo appuntamento.
    """
    from telephone.application import apply_the_outcome

    fuori_orario = _legame()
    fuori_orario.expected["start_datetime"] = "2026-09-14T09:00:00+02:00"
    await mondo.calendar_event_drafts.update_one(
        {"id": "cal_abc123"},
        {"$set": {"start_datetime": "2026-09-14T09:00:00+02:00"}},
    )
    await _lega(mondo, fuori_orario)
    record = await apply_the_outcome(mondo, _chiamata(), _esito())

    assert record.application_status == "conflict"
    assert "16:00" in record.error and "09:00" in record.error
    assert FintoGoogle.scritture == []


@pytest.mark.asyncio
async def test_j_an_event_that_is_not_theirs_is_not_touched(mondo):
    """
    J: il legame punta a un evento che non è di questa persona.

    Non si cerca un ripiego. Un evento che non c'è, o che è di qualcun altro,
    non si sostituisce con quello che gli somiglia di più.
    """
    from telephone.application import apply_the_outcome

    altrui = _legame()
    altrui.target.entity_id = "cal_di_qualcun_altro"
    await _lega(mondo, altrui)
    record = await apply_the_outcome(mondo, _chiamata(), _esito())

    assert record.application_status == "failed"
    assert FintoGoogle.scritture == []
    assert _quando(mondo).startswith("2026-09-14T16:00")


@pytest.mark.asyncio
async def test_j_bis_a_call_with_no_binding_only_reports(mondo):
    """
    §3: nessun legame, nessuna ricerca per somiglianza.

    È il caso in cui la telefonata è stata preparata senza dire quale
    appuntamento. Resta una telefonata valida: riporta una risposta invece di
    cambiare un calendario. Quello che non fa è indovinare.
    """
    from telephone.application import apply_the_outcome

    record = await apply_the_outcome(mondo, _chiamata(), _esito())

    assert record.application_status == "skipped"
    assert record.target_entity_id == ""
    assert FintoGoogle.scritture == []


@pytest.mark.asyncio
async def test_k_a_date_that_is_not_a_reschedule_is_refused(mondo):
    """
    K: l'anno sbagliato non è uno spostamento.

    Nessun confronto di testo può dire se «fra giovedì e sabato» contenga le
    18:00 del ventisette — provarci produce falsi allarmi, e un allarme che
    grida a vuoto insegna a ignorarlo. Questo limite prende solo l'errore che
    si riconosce senza capire la frase.
    """
    from telephone.application import apply_the_outcome

    await _lega(mondo)
    record = await apply_the_outcome(mondo, _chiamata(), _esito(
        confirmed_changes={
            "appointment_date": "2027-03-02", "old_time": "16:00",
            "new_time": "18:00",
        },
    ))

    assert record.application_status == "skipped"
    assert "lontana" in record.error
    assert FintoGoogle.scritture == []


@pytest.mark.asyncio
async def test_k_bis_things_outside_the_mission_are_not_written(mondo):
    """
    §9: una telefonata per spostare non ha l'autorità di cambiare l'indirizzo.

    Un dato che emerge si racconta; non si applica «visto che c'era».
    """
    from telephone.application import apply_the_outcome

    await _lega(mondo)
    record = await apply_the_outcome(mondo, _chiamata(), _esito(
        confirmed_changes={
            "appointment_date": "2026-09-14", "new_time": "18:00",
            "location": "via Roma 4",
        },
    ))

    assert record.application_status == "skipped"
    assert "location" in record.error
    assert FintoGoogle.scritture == []


@pytest.mark.asyncio
async def test_a_calendar_that_refuses_does_not_make_the_call_a_failure(mondo):
    """
    §16: l'applicazione fallisce, la telefonata resta riuscita.

    La controparte *ha* confermato: è successo, ed è vero anche se poi Google
    non ha risposto. Riscrivere l'esito vorrebbe dire dare la colpa alla
    persona che ha risposto al telefono per un problema che è nostro.
    """
    from telephone.application import apply_the_outcome

    FintoGoogle.solleva = RuntimeError("Google Calendar non collegato")
    await _lega(mondo)
    esito = _esito()
    record = await apply_the_outcome(mondo, _chiamata(), esito)

    assert record.application_status == "failed"
    assert record.outcome_status == "success"
    # E l'esito in mano è ancora quello di prima: nessuno l'ha toccato.
    assert esito.status == "success"
    assert esito.is_actionable()


# ---------------------------------------------------------------------------
# La traduzione, che è pura e si può provare senza un calendario
# ---------------------------------------------------------------------------

def test_the_new_time_keeps_the_length_it_had():
    from telephone.domains.calendar import translate

    campi, perche = translate(_legame(), _esito())
    assert perche == ""
    assert campi["start_datetime"].startswith("2026-09-14T18:00")
    assert campi["end_datetime"].startswith("2026-09-14T18:45")


def test_moving_across_the_clock_change_does_not_move_the_hour():
    """
        UNO SPOSTAMENTO PUÒ ATTRAVERSARE UN CAMBIO D'ORA.

    Riusare l'offset di partenza — `+02:00` — funziona finché l'appuntamento
    resta nella stessa stagione, e a fine ottobre sposterebbe l'appuntamento
    di un'ora senza che nessuno l'abbia chiesto.
    """
    from telephone.domains.calendar import translate

    #     L'ORA LEGALE FINISCE FRA L'APPUNTAMENTO E IL SUO SPOSTAMENTO.
    # Il 25 ottobre 2026 l'Europa torna a +01:00. Un appuntamento del 20 che
    # si sposta al 26 attraversa quella notte.
    di_ottobre = _legame()
    di_ottobre.expected["start_datetime"] = "2026-10-20T16:00:00+02:00"
    di_ottobre.expected["end_datetime"] = "2026-10-20T16:45:00+02:00"

    campi, perche = translate(di_ottobre, _esito(confirmed_changes={
        "appointment_date": "2026-10-26", "old_time": "16:00",
        "new_time": "18:00",
    }))
    assert perche == ""
    # L'ora scritta è le 18:00, e l'offset è quello di dopo il cambio.
    assert campi["start_datetime"].startswith("2026-10-26T18:00")
    assert campi["start_datetime"].endswith("+01:00")


def test_confirming_the_time_it_already_had_writes_nothing():
    from telephone.domains.calendar import translate

    campi, perche = translate(_legame(), _esito(confirmed_changes={
        "appointment_date": "2026-09-14", "old_time": "16:00",
        "new_time": "16:00",
    }))
    assert campi == {}
    assert "che c'era già" in perche


# ---------------------------------------------------------------------------
# L — come si legge, quando le due cose non coincidono
# ---------------------------------------------------------------------------

def _riuscita(call):
    call.metrics = {
        "runtime": "gemini_live",
        "outcome": {
            "mission_id": "mis_tel_uno",
            "status": "success",
            "confirmed_changes": {
                "appointment_date": "2026-09-14",
                "old_time": "16:00",
                "new_time": "18:00",
            },
        },
    }
    return call


def _applicazione(stato, errore=""):
    from telephone.application import CallMissionApplication

    return CallMissionApplication(
        mission_id="mis_tel_uno", call_id="tel_uno", owner_id="u1",
        target_domain="calendar", target_entity_id="cal_abc123",
        operation="reschedule", outcome_status="success",
        application_status=stato, error=errore,
        idempotency_key="mis_tel_uno|reschedule|cal_abc123",
    )


def test_l_when_it_worked_the_line_says_what_it_always_said():
    from telephone.history import as_a_card

    scheda = as_a_card(_riuscita(_chiamata()), _applicazione("applied"))
    assert scheda["presentation_status"] == "completata"
    assert scheda["outcome_summary"] == "Appuntamento spostato alle 18:00."
    assert scheda["changed_something"] is True


def test_l_a_failed_application_is_said_out_loud():
    """
    §13: «Lo studio ha confermato, ma ORA non è riuscita ad aggiornare».

    Senza questa riga la frase sarebbe la stessa sia quando il calendario è
    cambiato sia quando non lo è — e una persona si fiderebbe di un calendario
    rimasto alle sedici.
    """
    from telephone.history import as_a_card

    scheda = as_a_card(_riuscita(_chiamata()), _applicazione("failed"))

    assert scheda["presentation_status"] == "completata"
    assert scheda["changed_something"] is False
    riga = scheda["outcome_summary"]
    # Prima quello che ha fatto la controparte — è successo, ed è merito suo.
    assert riga.startswith("Hanno confermato lo spostamento alle 18:00,")
    assert "non sono riuscita ad aggiornare il calendario" in riga
    # E non dice «Appuntamento spostato», che sarebbe la frase rassicurante.
    assert "Appuntamento spostato" not in riga


def test_l_a_conflict_reads_differently_from_a_failure():
    """
    §12: «è cambiato mentre eravamo al telefono» chiede una cosa diversa.

    Il fallimento vuole che si riprovi; il conflitto vuole che si vada a
    guardare. Due frasi, perché sono due richieste.
    """
    from telephone.history import as_a_card

    scheda = as_a_card(_riuscita(_chiamata()), _applicazione("conflict"))
    riga = scheda["outcome_summary"]

    assert "era già cambiato" in riga
    assert "non l'ho toccato" in riga
    assert scheda["changed_something"] is False


def test_l_a_call_that_never_promised_a_calendar_reads_as_before():
    """
        UN'APPLICAZIONE CHE NON C'È NON È UN'APPLICAZIONE FALLITA.

    Nessun legame vuol dire che a nessuno era stato promesso un calendario
    aggiornato: raccontare un fallimento che non è successo è sbagliato quanto
    tacerne uno che è successo.
    """
    from telephone.history import as_a_card

    senza = _applicazione("skipped")
    senza.target_entity_id = ""
    for applicazione in (None, senza):
        scheda = as_a_card(_riuscita(_chiamata()), applicazione)
        assert scheda["outcome_summary"] == "Appuntamento spostato alle 18:00."
        assert scheda["changed_something"] is None


def test_l_the_detail_says_what_was_tried():
    from telephone.history import in_full

    scheda = in_full(
        _riuscita(_chiamata()),
        application=_applicazione("failed", "il calendario non ha accettato"),
    )
    assert scheda["application_status"] == "failed"
    assert scheda["application_target"] == "calendar"
    assert "non ha accettato" in scheda["application_error"]
    # E i due esiti restano due campi distinti.
    assert scheda["mission_status"] == "success"


def test_l_a_call_nobody_answered_says_nothing_about_calendars():
    """
        PRIMA COM'È ANDATA LA LINEA, POI COM'È ANDATA LA MISSIONE.

    L'ordine non cambia perché è arrivato un terzo fatto. Se non ha risposto
    nessuno non c'è niente da applicare, e parlare di calendari sposterebbe la
    colpa sul posto sbagliato.
    """
    from telephone.history import as_a_card

    muta = _chiamata(state="failed", how_it_ended="no_answer",
                     started_at=None, ended_at=None)
    scheda = as_a_card(muta, _applicazione("skipped"))
    assert scheda["presentation_status"] == "nessuna_risposta"
    assert scheda["outcome_summary"] == "Nessuna risposta."


# ---------------------------------------------------------------------------
# §19 — l'ambiguità si scioglie prima di comporre il numero
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_binding_is_made_before_anybody_dials(mondo):
    """
    §19: si lega l'evento quando c'è ancora qualcuno a cui chiedere.

    Dopo la telefonata resterebbe solo un orario, e un orario da solo non dice
    quale evento.
    """
    from telephone.binding import bind_a_calendar_event, binding_for

    legame, perche, _ = await bind_a_calendar_event(
        mondo, call=_chiamata(), calendar_ref="calendar:cal_abc123",
        # L'appuntamento del banco e' nel passato, e dal V3.15.2 la guardia lo
        # ferma: qui si sta provando il legame, non la guardia, e il permesso
        # esplicito e' il modo di dirlo.
        even_if_it_is_past=True,
    )
    assert perche == ""
    assert legame.target.entity_id == "cal_abc123"
    # E porta con sé com'era l'appuntamento: è la data di scadenza della missione.
    assert legame.expected["start_datetime"] == "2026-09-14T16:00:00+02:00"
    assert (await binding_for(mondo, "tel_uno")).mission_id == "mis_tel_uno"


@pytest.mark.asyncio
@pytest.mark.parametrize("ref,pezzo", [
    ("", "quale appuntamento"),
    ("calendar:non_esiste", "non è nel tuo calendario"),
])
async def test_an_event_that_cannot_be_named_is_not_guessed(mondo, ref, pezzo):
    """
    §3: non si cerca un ripiego.

    Un evento che non c'è non si sostituisce con quello che gli somiglia di
    più. La telefonata si può fare lo stesso — riporterà una risposta — ma
    nessuno deve credere che il calendario cambierà.
    """
    from telephone.binding import bind_a_calendar_event

    legame, perche, _ = await bind_a_calendar_event(
        mondo, call=_chiamata(), calendar_ref=ref,
    )
    assert legame is None
    assert pezzo in perche


@pytest.mark.asyncio
async def test_a_call_that_only_asks_is_not_tied_to_anything(mondo):
    """
    Una telefonata che chiede e basta non lega niente, e non lo lamenta.

    Chiedere «quale appuntamento?» a chi sta solo telefonando per informarsi
    sarebbe una domanda senza risposta possibile.
    """
    from telephone.binding import bind_a_calendar_event
    from telephone.models import Mandate

    solo_chiedere = _chiamata(mandate=Mandate(
        why_calling="chiedere se lo studio è aperto sabato mattina",
    ))
    legame, perche, _ = await bind_a_calendar_event(
        mondo, call=solo_chiedere, calendar_ref="",
    )
    assert legame is None
    assert perche == ""


def test_the_answer_says_whether_the_calendar_will_change():
    """
    §19: «ti chiamo e poi te lo dico» e «ti chiamo e lo sposto» sono due cose.

        È ESATTAMENTE QUELLO SU CUI LA PERSONA STA DICENDO DI SÌ.

    Quindi va detto prima del sì, non scoperto dopo guardando il calendario.
    """
    from telephone.caps import _what_it_will_change

    legato = _what_it_will_change(_legame(), "")
    assert legato["will_update_calendar"] is True

    sciolto = _what_it_will_change(None, "non mi hai detto quale appuntamento")
    assert sciolto["will_update_calendar"] is False
    assert "quale appuntamento" in sciolto["why_nothing_will_change"]
    assert "il calendario resterà com'è" in sciolto["how_to_say_that_too"]

    # E su una telefonata che non doveva cambiare niente non si lamenta niente.
    muta = _what_it_will_change(None, "")
    assert muta == {"will_update_calendar": False}


@pytest.mark.asyncio
async def test_a_revoked_calendar_permission_stops_the_write(mondo, monkeypatch):
    """
    Il sì alla telefonata non è il sì al calendario.

        SONO DUE AUTORITÀ, E VENGONO DA DUE MOMENTI DIVERSI.

    Una la dà la persona quando autorizza la chiamata; l'altra è il permesso
    con cui il calendario è stato collegato, e può essere stato revocato nel
    frattempo. Questa applicazione è arrivata per una strada nuova, e una
    strada nuova non è un motivo per saltare un cancello che tutte le altre
    scritture in calendario attraversano.
    """
    import telephone.domains.calendar as adattatore
    from telephone.application import apply_the_outcome

    async def revocato(*_a, **_k):
        return "il permesso di scrivere nel calendario non è attivo"

    monkeypatch.setattr(adattatore, "_consent_missing", revocato)

    await _lega(mondo)
    record = await apply_the_outcome(mondo, _chiamata(), _esito())

    assert record.application_status == "failed"
    assert "permesso" in record.error
    assert FintoGoogle.scritture == []
    assert _quando(mondo).startswith("2026-09-14T16:00")


# ===========================================================================
# V3.15.2 — POST-CALL HARDENING
# ===========================================================================
#
#     LA V3.15 SAPEVA SCRIVERE. QUESTA SA COSA FARE QUANDO NON RIESCE.
#
# Due difetti diversi, tutti e due invisibili finché non capitano davvero: una
# telefonata partita per spostare un appuntamento di ieri, e un'applicazione
# rimasta a metà perché il processo è morto fra due scritture.

FUTURO = {
    **APPUNTAMENTO,
    "id": "cal_futuro",
    "title": "Dentista, la settimana prossima",
    "start_datetime": "2099-09-14T16:00:00+02:00",
    "end_datetime": "2099-09-14T16:45:00+02:00",
}


# ---------------------------------------------------------------------------
# 1 · La guardia sull'appuntamento già passato
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_future_appointment_binds_without_a_question(mondo):
    """
    Futuro → si lega e basta.

    La guardia non deve farsi notare nel caso normale: se l'appuntamento deve
    ancora succedere non c'è niente da chiedere, e una domanda in più prima di
    ogni telefonata sarebbe un attrito senza motivo.
    """
    from telephone.binding import bind_a_calendar_event

    mondo.calendar_event_drafts.righe.append(dict(FUTURO))
    legame, perche, chiarimento = await bind_a_calendar_event(
        mondo, call=_chiamata(), calendar_ref="cal_futuro",
    )

    assert legame is not None
    assert legame.target.entity_id == "cal_futuro"
    assert perche == ""
    assert chiarimento is False


@pytest.mark.asyncio
async def test_a_past_appointment_asks_instead_of_dialling(mondo):
    """
    Passato senza permesso → si domanda, e non si lega niente.

        TELEFONARE PER SPOSTARE LA VISITA DI IERI È UNA FIGURA CHE PAGA LA
        PERSONA, NON ORA.

    E nasce quasi sempre da un malinteso: l'evento sbagliato, o una data letta
    storta. L'unico momento in cui si può chiedere è adesso — dopo lo squillo
    non c'è più nessuno a cui chiedere.
    """
    from telephone.binding import bind_a_calendar_event, binding_for

    legame, domanda, chiarimento = await bind_a_calendar_event(
        mondo, call=_chiamata(), calendar_ref="cal_abc123",
    )

    assert legame is None
    assert chiarimento is True
    assert "già" in domanda and "passato" in domanda
    # È una domanda, non un referto: finisce col punto interrogativo.
    assert domanda.rstrip().endswith("?")
    # E porta il titolo, perché «quale?» deve avere una risposta leggibile.
    assert "Dentista" in domanda
    # Niente è stato scritto: non esiste un legame a metà.
    assert await binding_for(mondo, "tel_uno") is None


@pytest.mark.asyncio
async def test_a_past_appointment_binds_when_somebody_said_so(mondo):
    """
    Passato con permesso esplicito → si procede.

    Capita di richiamare per rimettere in piedi un appuntamento saltato. La
    guardia non vieta: chiede. E una risposta è una risposta.
    """
    from telephone.binding import bind_a_calendar_event

    legame, perche, chiarimento = await bind_a_calendar_event(
        mondo, call=_chiamata(), calendar_ref="cal_abc123",
        even_if_it_is_past=True,
    )

    assert legame is not None
    assert perche == "" and chiarimento is False
    assert legame.expected["start_datetime"] == "2026-09-14T16:00:00+02:00"


def test_the_question_is_not_told_as_a_refusal():
    """
    §1: chi riceve l'esito deve distinguere una domanda da un rifiuto.

    «Non è nel tuo calendario» chiude il discorso; «è di ieri, telefono lo
    stesso?» lo apre. Raccontarle uguale vorrebbe dire non chiedere mai.
    """
    from telephone.caps import _what_it_will_change

    domanda = _what_it_will_change(
        None, "«Dentista» è già passato: vuoi che telefoni lo stesso?", True,
    )
    assert domanda["needs_clarification"] is True
    assert domanda["will_update_calendar"] is False
    assert "telefoni lo stesso" in domanda["ask_this_first"]
    assert "proceed_even_if_past" in domanda["how_to_say_that_too"]

    rifiuto = _what_it_will_change(
        None, "questo appuntamento non è nel tuo calendario", False,
    )
    assert "needs_clarification" not in rifiuto
    assert "ask_this_first" not in rifiuto


def test_an_hour_ago_counts_as_past_just_like_yesterday():
    """
        NON È LA DATA, È L'ISTANTE.

    Un appuntamento delle 16:00 alle 16:54 è passato quanto quello di ieri.
    Confrontare solo i giorni lo lascerebbe scivolare — ed è proprio il caso
    che ha fatto nascere questa guardia.
    """
    from datetime import datetime, timedelta, timezone

    from telephone.binding import _already_gone

    adesso = datetime.now(timezone.utc)
    assert _already_gone((adesso - timedelta(hours=1)).isoformat(), "Europe/Rome") is True
    assert _already_gone((adesso + timedelta(hours=1)).isoformat(), "Europe/Rome") is False

    # Una data illeggibile non ferma una telefonata: una guardia che non sa
    # dire non deve decidere.
    assert _already_gone("", "Europe/Rome") is False
    assert _already_gone("non è una data", "Europe/Rome") is False


# ---------------------------------------------------------------------------
# 2 · Il recupero di un'applicazione rimasta a metà
# ---------------------------------------------------------------------------

async def _appesa(db, *, quando: str, legame=None):
    """Un record `pending` nato a un'ora che decidiamo noi."""
    from telephone.application import APPLICATIONS, CallMissionApplication, key_for

    legame = await _lega(db, legame)
    chiave = key_for(legame.mission_id, "reschedule", legame.target.entity_id)
    record = CallMissionApplication(
        mission_id=legame.mission_id, call_id="tel_uno", owner_id="u1",
        target_domain="calendar", target_entity_id=legame.target.entity_id,
        operation="reschedule", outcome_status="success",
        application_status="pending", created_at=quando,
        idempotency_key=chiave,
    )
    await db[APPLICATIONS].insert_one({**record.model_dump(), "_id": chiave})
    return record


def _vecchia(minuti=10):
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) - timedelta(minutes=minuti)).isoformat()


@pytest.mark.asyncio
async def test_a_crash_before_the_write_is_retried_exactly_once(mondo):
    """
    Morto **prima** della scrittura → si riprova, una volta.

    L'appuntamento è ancora dove stava: la scrittura non è mai partita. Si
    riprova dalla porta normale, con dentro i suoi controlli — non si scrive a
    mano perché è un secondo giro.
    """
    from telephone.application import APPLICATIONS, recover_stale

    await _appesa(mondo, quando=_vecchia())
    assert _quando(mondo).startswith("2026-09-14T16:00")

    chiusi = await recover_stale(mondo)

    assert len(chiusi) == 1
    assert chiusi[0].application_status == "applied"
    assert chiusi[0].writes == ["calendar:cal_abc123"]
    assert _quando(mondo).startswith("2026-09-14T18:00")
    # Una scrittura sola, e un record solo.
    assert len(FintoGoogle.scritture) == 1
    assert len(mondo[APPLICATIONS].righe) == 1


@pytest.mark.asyncio
async def test_a_crash_after_the_write_only_closes_the_record(mondo):
    """
    Morto **dopo** la scrittura → si chiude il record, non si riscrive.

        UN RECORD `pending` NON DICE SE LA SCRITTURA È ANDATA.

    È il caso in cui riprovare farebbe il danno: una seconda scrittura identica
    è inutile, e su un calendario cambiato di nuovo sarebbe un sopruso. Il
    calendario è già alle 18: il record era solo rimasto indietro.
    """
    from telephone.application import recover_stale

    await mondo.calendar_event_drafts.update_one(
        {"id": "cal_abc123"},
        {"$set": {"start_datetime": "2026-09-14T18:00:00+02:00",
                  "end_datetime": "2026-09-14T18:45:00+02:00"}},
    )
    await _appesa(mondo, quando=_vecchia())

    chiusi = await recover_stale(mondo)

    assert chiusi[0].application_status == "applied"
    assert chiusi[0].writes == ["calendar:cal_abc123"]
    # E nessuno ha toccato il calendario una seconda volta.
    assert FintoGoogle.scritture == []
    assert _quando(mondo).startswith("2026-09-14T18:00")


@pytest.mark.asyncio
async def test_an_appointment_moved_elsewhere_meanwhile_is_a_conflict(mondo):
    """
    Né dov'era né dove doveva arrivare → qualcuno l'ha spostato. Conflitto.

    Non è un fallimento e non si riprova: riprovare scriverebbe sopra la
    decisione più recente di una persona.
    """
    from telephone.application import recover_stale

    await mondo.calendar_event_drafts.update_one(
        {"id": "cal_abc123"},
        {"$set": {"start_datetime": "2026-09-16T09:00:00+02:00"}},
    )
    await _appesa(mondo, quando=_vecchia())

    chiusi = await recover_stale(mondo)

    assert chiusi[0].application_status == "conflict"
    assert FintoGoogle.scritture == []
    assert _quando(mondo).startswith("2026-09-16T09:00")


@pytest.mark.asyncio
async def test_an_application_still_working_is_not_touched(mondo):
    """
    Un `pending` fresco sta succedendo, non è rimasto lì.

    Sul vero l'applicazione completa ha impiegato 2,1 secondi. Recuperare a
    quaranta millisecondi vorrebbe dire correre contro chi sta ancora
    scrivendo — cioè costruire la doppia scrittura che tutto il resto evita.
    """
    from datetime import datetime, timezone

    from telephone.application import APPLICATIONS, recover_stale

    await _appesa(mondo, quando=datetime.now(timezone.utc).isoformat())

    chiusi = await recover_stale(mondo)

    assert chiusi == []
    assert FintoGoogle.scritture == []
    assert mondo[APPLICATIONS].righe[0]["application_status"] == "pending"
    assert _quando(mondo).startswith("2026-09-14T16:00")


@pytest.mark.asyncio
async def test_recovering_twice_changes_nothing_the_second_time(mondo):
    """
    Due recuperi, una scrittura.

        STESSA CHIAVE, NESSUN RECORD NUOVO.

    Il recupero non è un secondo tentativo che si annota a parte: è lo stesso
    fatto che arriva finalmente a una conclusione.
    """
    from telephone.application import APPLICATIONS, recover_stale

    record = await _appesa(mondo, quando=_vecchia())
    primo = await recover_stale(mondo)
    secondo = await recover_stale(mondo)

    assert primo[0].application_status == "applied"
    # Il secondo giro non trova più niente di appeso: non c'è nulla da chiudere.
    assert secondo == []
    assert len(FintoGoogle.scritture) == 1
    assert len(mondo[APPLICATIONS].righe) == 1
    assert mondo[APPLICATIONS].righe[0]["idempotency_key"] == record.idempotency_key
    assert _quando(mondo).startswith("2026-09-14T18:00")


@pytest.mark.asyncio
async def test_the_recovered_record_keeps_its_own_key(mondo):
    """§2: nessun record nuovo, e la chiave è quella di sempre."""
    from telephone.application import APPLICATIONS, application_for, recover_stale

    prima = await _appesa(mondo, quando=_vecchia())
    await recover_stale(mondo)
    dopo = await application_for(mondo, "tel_uno")

    assert dopo.idempotency_key == prima.idempotency_key
    assert dopo.mission_id == prima.mission_id
    assert dopo.created_at == prima.created_at
    assert dopo.applied_at != ""
    assert len(mondo[APPLICATIONS].righe) == 1


# ---------------------------------------------------------------------------
# 3 · Come si legge, mentre si sta ancora verificando
# ---------------------------------------------------------------------------

def test_a_pending_application_does_not_read_as_all_done():
    """
    §3: «sto verificando» non è «tutto fatto».

    Finché non si sa se il calendario è stato toccato, la riga non può dire che
    lo è: manderebbe qualcuno a fidarsi di un aggiornamento che potrebbe non
    esserci.
    """
    from telephone.history import as_a_card

    scheda = as_a_card(_riuscita(_chiamata()), _applicazione("pending"))
    riga = scheda["outcome_summary"]

    assert "Appuntamento spostato" not in riga
    assert riga.startswith("Hanno confermato lo spostamento alle 18:00,")
    assert "sto verificando l'aggiornamento del calendario" in riga
    assert scheda["changed_something"] is False


# ---------------------------------------------------------------------------
# 4 · Chi chiama il recupero, e chi impedisce che lo chiamino in due
# ---------------------------------------------------------------------------
#
#     UN RECUPERO CHE NESSUNO CHIAMA NON RECUPERA NIENTE.

@pytest.mark.asyncio
async def test_two_workers_recovering_together_write_once(mondo):
    """
    Due recuperi in parallelo sullo stesso record appeso → una scrittura sola.

        LA RIVENDICAZIONE LA FA IL DATABASE, NON UN `if`.

    Un `find_one` seguito da un `update_one` ha in mezzo una finestra, e in
    quella finestra ci stanno due processi. Chi arriva secondo deve trovare il
    filtro che non combacia più e tornare a mani vuote.
    """
    from telephone.application import APPLICATIONS, recover_stale

    await _appesa(mondo, quando=_vecchia())

    primo, secondo = await asyncio.gather(
        recover_stale(mondo), recover_stale(mondo),
    )

    # Uno solo dei due ha chiuso qualcosa, e non importa quale.
    assert sorted([len(primo), len(secondo)]) == [0, 1]
    assert len(FintoGoogle.scritture) == 1
    assert len(mondo[APPLICATIONS].righe) == 1
    assert _quando(mondo).startswith("2026-09-14T18:00")


@pytest.mark.asyncio
async def test_a_claim_is_released_when_the_record_closes(mondo):
    """La presa in carico serve finché è aperta. Chiusa, si libera."""
    from telephone.application import APPLICATIONS, recover_stale

    await _appesa(mondo, quando=_vecchia())
    await recover_stale(mondo)

    assert mondo[APPLICATIONS].righe[0]["claimed_at"] == ""
    assert mondo[APPLICATIONS].righe[0]["application_status"] == "applied"


@pytest.mark.asyncio
async def test_a_claim_left_by_a_dead_worker_expires(mondo):
    """
        UN LOCK CHE NON SCADE È UN RECORD PERSO PER SEMPRE.

    Chi muore mentre tiene la rivendicazione lascia il proprio nome sopra il
    record. Senza scadenza nessuno potrebbe più toccarlo: sarebbe il guasto
    che stiamo sistemando, ricreato un piano più sotto.
    """
    from telephone.application import APPLICATIONS, LEASE_S, recover_stale

    await _appesa(mondo, quando=_vecchia(minuti=30))
    # Un nome lasciato lì da un processo morto mezz'ora fa.
    mondo[APPLICATIONS].righe[0]["claimed_at"] = _vecchia(
        minuti=int(LEASE_S / 60) + 10)

    chiusi = await recover_stale(mondo)

    assert len(chiusi) == 1
    assert chiusi[0].application_status == "applied"


@pytest.mark.asyncio
async def test_a_fresh_claim_is_respected(mondo):
    """E una presa in carico viva non si scavalca."""
    from telephone.application import APPLICATIONS, recover_stale
    from datetime import datetime, timezone

    await _appesa(mondo, quando=_vecchia())
    mondo[APPLICATIONS].righe[0]["claimed_at"] = datetime.now(
        timezone.utc).isoformat()

    assert await recover_stale(mondo) == []
    assert FintoGoogle.scritture == []
    assert mondo[APPLICATIONS].righe[0]["application_status"] == "pending"


@pytest.mark.asyncio
async def test_the_loop_scans_at_startup_and_then_keeps_going(mondo, monkeypatch):
    """
    Una passata all'avvio, e poi una ogni intervallo.

    All'avvio perché è il momento in cui è **certo** che ci sia qualcosa da
    recuperare: se il processo precedente è morto in mezzo a due scritture, il
    suo `pending` è lì che aspetta proprio adesso.
    """
    import telephone.recovery as giro

    passate = []

    async def conta(db, quale):
        passate.append(quale)
        return 0

    monkeypatch.setattr(giro, "_one_pass", conta)
    monkeypatch.setattr(giro, "EVERY_S", 0.01)

    giro.start_recovery(mondo)
    await asyncio.sleep(0.05)
    await giro.stop_recovery()

    assert passate[0] == "avvio"
    assert "periodica" in passate[1:], "il giro non ha continuato"


@pytest.mark.asyncio
async def test_starting_it_twice_does_not_make_two_loops(mondo, monkeypatch):
    """Due cicli sullo stesso database sarebbero lavoro doppio per niente."""
    import telephone.recovery as giro

    async def niente(db, quale):
        return 0

    monkeypatch.setattr(giro, "_one_pass", niente)
    giro.start_recovery(mondo)
    primo = giro._task
    giro.start_recovery(mondo)
    try:
        assert giro._task is primo
    finally:
        await giro.stop_recovery()


@pytest.mark.asyncio
async def test_one_broken_pass_does_not_kill_the_loop(mondo, monkeypatch):
    """
        UN CICLO CHE MUORE AL PRIMO INTOPPO È PEGGIO DI NESSUN CICLO.

    Perché sembra che ci sia. Qualunque cosa succeda dentro una passata si
    annota e si aspetta il giro dopo.
    """
    import telephone.recovery as giro

    tentativi = []

    async def a_volte_esplode(db):
        tentativi.append(1)
        if len(tentativi) == 1:
            raise RuntimeError("il database non risponde")
        return []

    monkeypatch.setattr(
        "telephone.application.recover_stale", a_volte_esplode, raising=True)
    monkeypatch.setattr(giro, "EVERY_S", 0.01)

    giro.start_recovery(mondo)
    await asyncio.sleep(0.06)
    task = giro._task
    vivo = task is not None and not task.done()
    await giro.stop_recovery()

    assert len(tentativi) >= 2, "il giro si è fermato al primo errore"
    assert vivo, "il giro è morto invece di aspettare il minuto dopo"


@pytest.mark.asyncio
async def test_a_single_broken_pass_returns_zero_instead_of_raising(mondo, monkeypatch):
    """La passata non solleva mai verso chi la chiama."""
    import telephone.recovery as giro

    async def esplode(db):
        raise RuntimeError("niente rete")

    monkeypatch.setattr(
        "telephone.application.recover_stale", esplode, raising=True)
    assert await giro._one_pass(mondo, "prova") == 0


@pytest.mark.asyncio
async def test_shutdown_cancels_the_loop_cleanly(mondo, monkeypatch):
    """
    Spegnere non aspetta e non lascia niente acceso.

        CANCELLARE NON PERDE NIENTE.

    Ogni cosa da fare è durevole in Mongo, e una rivendicazione presa quando
    il processo muore torna libera appena scade.
    """
    import telephone.recovery as giro

    async def lenta(db, quale):
        await asyncio.sleep(3600)
        return 0

    monkeypatch.setattr(giro, "_one_pass", lenta)

    giro.start_recovery(mondo)
    task = giro._task
    await asyncio.sleep(0)
    assert task is not None and not task.done()

    await giro.stop_recovery()

    assert task.cancelled() or task.done()
    assert giro._task is None
    # E spegnere due volte non è un errore.
    await giro.stop_recovery()


def test_the_server_turns_it_on_and_off():
    """
    §: il giro è agganciato al runtime, non a un cron esterno.

    Una prova strutturale, perché è esattamente la riga che qualcuno toglie
    per sbaglio durante un refactor dell'avvio — e senza quella riga tutto il
    resto di questo file continua a passare mentre nessuno recupera niente.
    """
    from pathlib import Path

    server = Path(__file__).resolve().parents[1] / "server.py"
    codice = server.read_text(encoding="utf-8")

    assert "from telephone.recovery import start_recovery" in codice
    assert "start_recovery(db)" in codice
    assert "from telephone.recovery import stop_recovery" in codice
    assert "await stop_recovery()" in codice
