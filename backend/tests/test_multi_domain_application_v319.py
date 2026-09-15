"""
Lo stesso motore, su tre domini che non si somigliano.

    UN CONTRATTO CHE UN DOMINIO SOLO RISPETTA NON È UN CONTRATTO.

Fino a ieri l'applicazione post-chiamata sapeva fare una cosa: spostare,
disdire e prenotare in calendario. Funzionava, ed era anche il problema —
niente dimostrava che quello che teneva in piedi il calendario fosse il
contratto e non il calendario stesso. Il secondo dominio è l'unico modo di
scoprirlo, e il terzo è l'unico modo di crederci.

Quindi queste prove chiedono a ciascuno le stesse nove domande, e le chiedono
nello stesso ordine:

    riesce quando deve;
    torna a una persona quando la controparte propone altro;
    non scrive quando l'autorità dice di no;
    applicato due volte scrive una volta sola;
    morto prima della scrittura, riprova una volta;
    morto dopo la scrittura, chiude il record e non riscrive;
    se l'oggetto è cambiato nel frattempo, non ci scrive sopra;
    un'applicazione appesa viene ripresa dal recupero;
    e senza mandato non si muove niente.

    E POI IL CALENDARIO, CHE DEVE ESSERE ANCORA VERDE.

Le sue prove stanno dove stavano — 371 fra V3.15 e V3.18 — e non sono state
toccate. Questo file aggiunge le altre due colonne della stessa tabella.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from test_post_call_application_v315 import FintoDb  # noqa: E402


# ===========================================================================
# Il banco
# ===========================================================================

IMPEGNO = {
    "id": "dec_abc123",
    "user_id": "u1",
    "title": "Richiamare il commercialista per la pratica",
    "status": "open",
    "action_state": {"status": "pending"},
}

SESSIONE = {
    "id": "ssn_abc123",
    "user_id": "u1",
    "plan_id": "spl_uno",
    "title": "Analisi II — capitolo 4",
    "status": "planned",
    # Le sessioni di studio sono scritte in UTC. Le 16:00 di Roma.
    "starts_at": "2026-09-14T14:00:00+00:00",
    "ends_at": "2026-09-14T15:00:00+00:00",
    "duration_minutes": 60,
    "session_type": "study",
}

PIANO = {"id": "spl_uno", "user_id": "u1", "sessions": [], "status": "active"}


def _chiamata(call_id="tel_uno", perche="", accetto=()):
    from telephone.models import Mandate, PhoneCall

    return PhoneCall(
        id=call_id,
        owner_id="u1",
        to_number="+393000000000",
        calling_whom="Studio Rossi",
        mandate=Mandate(
            why_calling=perche or "sapere se la pratica è chiusa",
            may_agree_to=list(accetto),
            must_bring_back=["una risposta"],
        ),
        state="ended",
        how_it_ended="they_hung_up",
        started_at="2026-09-14T14:00:10+00:00",
        ended_at="2026-09-14T14:01:02+00:00",
    )


def _esito(status="success", mission_id="mis_tel_uno", **cambia):
    from telephone.mission import CallMissionOutcome

    campi = dict(mission_id=mission_id, status=status, confirmed_changes={})
    campi.update(cambia)
    return CallMissionOutcome(**campi)


def _legame(dominio, operazione, entity, atteso, autorita=None, call_id="tel_uno"):
    from telephone.binding import CallMissionBinding, MissionTarget

    return CallMissionBinding(
        mission_id="mis_tel_uno",
        call_id=call_id,
        owner_id="u1",
        target=MissionTarget(
            domain=dominio, entity_id=entity, operation=operazione,
        ),
        expected=dict(atteso),
        authority=autorita,
    )


def _autorita(operazione, entity, *, data="", ora="", alternative=()):
    from telephone.authority import CallMissionAuthority, a_slot_from

    return CallMissionAuthority(
        operation=operazione,
        entity_id=entity,
        desired=a_slot_from(data, ora) if data else None,
        alternatives=[a_slot_from(d, o) for d, o in alternative],
        human_summary="quello che avevo concordato",
    )


async def _lega(db, legame):
    from telephone.binding import BINDINGS

    await db[BINDINGS].insert_one(legame.model_dump())
    return legame


def _mettici_una_chiamata(db, call):
    db["phone_calls"].righe.append(call.model_dump())
    return call


def _vecchia(minuti=10):
    return (datetime.now(timezone.utc) - timedelta(minutes=minuti)).isoformat()


async def _appesa(db, legame, operazione):
    """Un record `pending` nato abbastanza tempo fa da essere rimasto lì."""
    from telephone.application import APPLICATIONS, CallMissionApplication, key_for

    chiave = key_for(legame.mission_id, operazione, legame.target.entity_id)
    record = CallMissionApplication(
        mission_id=legame.mission_id, call_id=legame.call_id, owner_id="u1",
        target_domain=legame.target.domain,
        target_entity_id=legame.target.entity_id,
        operation=operazione, outcome_status="success",
        application_status="pending", created_at=_vecchia(),
        idempotency_key=chiave,
    )
    await db[APPLICATIONS].insert_one({**record.model_dump(), "_id": chiave})
    return record


# ===========================================================================
# IL CONTRATTO, PRIMA DEI DOMINI
# ===========================================================================

def test_every_declared_domain_actually_has_an_adapter():
    """
    Un dominio nel registro il cui modulo non esiste è una promessa.

        E UNA PROMESSA SI SCOPRE DURANTE UNA TELEFONATA.

    `_module_for` solleverebbe `ImportError` al primo esito da applicare, cioè
    dopo che una persona ha già parlato con qualcuno.
    """
    from telephone.domains import every_adapter, known_domains

    assert len(every_adapter()) == len(known_domains())


def test_all_three_adapters_answer_to_the_same_contract():
    """
    §7: nessun adattatore salta un dovere.

        UN CONTRATTO CHE NESSUNO VERIFICA È UNA CONVENZIONE.

    Otto doveri, tre moduli, una lista vuota. È la prova più corta del file ed
    è quella che tiene fermo tutto il resto.
    """
    from telephone.domains import every_adapter, follows_the_contract

    manca = {a.DOMAIN: follows_the_contract(a) for a in every_adapter()}
    assert manca == {"calendar": [], "commitments": [], "study": []}


def test_the_registry_answers_by_pair_not_by_domain():
    """
    §2: `domain + operation`, non `domain`.

    «Calendario» non basta: sapere spostare non vuol dire sapere prenotare, e
    un dominio che dichiarasse un'operazione che non sa fare la sbaglierebbe
    in silenzio.
    """
    from telephone.domains import adapter_for

    assert adapter_for("study", "reschedule") is not None
    assert adapter_for("commitments", "postpone") is not None
    #     E «NIENTE» È UNA RISPOSTA, NON UN GUASTO.
    assert adapter_for("study", "book") is None
    assert adapter_for("commitments", "reschedule") is None
    assert adapter_for("magazzino", "spedire") is None


def test_no_adapter_writes_its_own_judge():
    """
    §5: l'autorità è una sola, e sta in `telephone.authority`.

    Un secondo giudice vorrebbe dire due modi di dire di no, e prima o poi uno
    dei due direbbe di sì. Qui si verifica che nessun adattatore ne abbia uno
    suo: tutti chiamano la stessa funzione.
    """
    import inspect

    from telephone.domains import every_adapter

    for adattatore in every_adapter():
        sorgente = inspect.getsource(adattatore)
        assert "evaluate_authority" in sorgente, adattatore.DOMAIN
        # E nessuno si scrive un proprio verdetto di autorità.
        assert "def evaluate_authority" not in sorgente, adattatore.DOMAIN


def test_no_adapter_rebuilds_the_application_engine():
    """
    §7: nessuna duplicazione del motore.

    Prenotare la chiave, rivendicare il lease, chiudere il record: sono cose
    di `application.py`. Un adattatore che se le rifacesse in casa sarebbe un
    secondo motore, e due motori si scoprono quando divergono.
    """
    import inspect

    from telephone.domains import every_adapter

    for adattatore in every_adapter():
        sorgente = inspect.getsource(adattatore)
        for roba in ("key_for", "call_mission_applications", "_claim",
                     "recover_stale", "idempotency_key"):
            assert roba not in sorgente, f"{adattatore.DOMAIN}: {roba}"


# ===========================================================================
# IMPEGNI — quello che una telefonata chiude o rimanda
# ===========================================================================

@pytest.fixture
def impegni():
    """Un database con un impegno aperto, e il servizio vero che lo scrive."""
    db = FintoDb()
    db.decisions.righe.append(dict(IMPEGNO))
    return db


def _esito_impegno(**cambia):
    return _esito(confirmed_changes=cambia or {"new_date": "2026-09-20"})


def _stato(db):
    return db.decisions.righe[0]["action_state"]["status"]


@pytest.mark.asyncio
async def test_commitments_a_confirmed_close_really_closes_it(impegni):
    """
    1 · Successo: l'impegno cambia stato davvero, dalla porta di sempre.

    E non a mano: la riga di audit c'è, il campo legacy è allineato. Sono le
    tre cose che `ActionCenterService` fa e che un `update_one` da qui non
    avrebbe fatto.
    """
    from telephone.application import apply_the_outcome

    call = _mettici_una_chiamata(impegni, _chiamata())
    await _lega(impegni, _legame(
        "commitments", "complete", "dec_abc123", {"status": "pending"},
    ))

    record = await apply_the_outcome(
        impegni, call, _esito(confirmed_changes={"appointment_date": "2026-09-14"}),
    )

    assert record.application_status == "applied"
    assert record.writes == ["commitments:dec_abc123"]
    assert _stato(impegni) == "completed"
    # Il campo legacy che i client vecchi leggono.
    assert impegni.decisions.righe[0]["status"] == "completed"
    # E la riga di audit, scritta prima della mutazione.
    assert len(impegni.decision_action_history.righe) == 1
    assert impegni.decision_action_history.righe[0]["new_status"] == "completed"


@pytest.mark.asyncio
async def test_commitments_a_postpone_carries_a_real_date(impegni):
    """
    1 · Successo, seconda operazione: rimandare scrive un quando.

        UN RINVIO SENZA UNA DATA NON È UN RINVIO.
    """
    from telephone.application import apply_the_outcome

    call = _mettici_una_chiamata(impegni, _chiamata())
    await _lega(impegni, _legame(
        "commitments", "postpone", "dec_abc123", {"status": "pending"},
        autorita=_autorita("postpone", "dec_abc123", data="2026-09-20", ora="09:00"),
    ))

    record = await apply_the_outcome(
        impegni, call,
        _esito(confirmed_changes={"new_date": "2026-09-20"}),
    )

    assert record.application_status == "applied"
    assert _stato(impegni) == "postponed"
    fino = impegni.decisions.righe[0]["action_state"]["postponed_until"]
    assert fino.startswith("2026-09-20T09:00")


@pytest.mark.asyncio
async def test_commitments_a_postpone_without_a_date_writes_nothing(impegni):
    """
    1 · «Slitta» non è un esito: è un'intenzione.
    """
    from telephone.application import apply_the_outcome

    call = _mettici_una_chiamata(impegni, _chiamata())
    await _lega(impegni, _legame(
        "commitments", "postpone", "dec_abc123", {"status": "pending"},
    ))

    record = await apply_the_outcome(
        impegni, call, _esito(confirmed_changes={"appointment_time": "09:00"}),
    )

    assert record.application_status == "skipped"
    assert _stato(impegni) == "pending"
    assert impegni.decision_action_history.righe == []


@pytest.mark.asyncio
async def test_commitments_needs_user_touches_nothing(impegni):
    """
    2 · La controparte ha proposto altro → torna a una persona, e basta.

        CEDERE IL CONTROLLO NON È ASPETTARE.

    Nel mondo non si muove niente: è esattamente il punto di `needs_user`, e
    vale per un impegno come vale per un appuntamento.
    """
    from telephone.application import apply_the_outcome
    from telephone.continuation import continuation_for

    call = _mettici_una_chiamata(impegni, _chiamata())
    await _lega(impegni, _legame(
        "commitments", "postpone", "dec_abc123", {"status": "pending"},
    ))

    record = await apply_the_outcome(
        impegni, call,
        _esito("needs_user", confirmed_changes={}, proposal="richiami lunedì"),
    )

    assert record.application_status == "skipped"
    assert _stato(impegni) == "pending"
    assert impegni.decision_action_history.righe == []
    # Ma la commissione non è morta: aspetta.
    assert await continuation_for(impegni, "tel_uno") is not None


@pytest.mark.asyncio
async def test_commitments_the_authority_can_forbid_the_write(impegni):
    """
    3 · Fuori dal mandato → zero mutazione.

        A DECIDERE È IL BACKEND. SEMPRE.

    Il mandato diceva «rimanda»; l'esito dice «chiudi». Non è un'alternativa,
    è un'altra cosa — e a fermarla è lo stesso giudice del calendario.
    """
    from telephone.application import apply_the_outcome

    call = _mettici_una_chiamata(impegni, _chiamata())
    await _lega(impegni, _legame(
        "commitments", "complete", "dec_abc123", {"status": "pending"},
        autorita=_autorita("postpone", "dec_abc123", data="2026-09-20", ora="09:00"),
    ))

    record = await apply_the_outcome(
        impegni, call,
        _esito(confirmed_changes={"appointment_date": "2026-09-14"}),
    )

    assert record.application_status == "skipped"
    assert "rimandare" in record.error
    assert _stato(impegni) == "pending"
    assert impegni.decision_action_history.righe == []


@pytest.mark.asyncio
async def test_commitments_applied_twice_writes_once(impegni):
    """
    4 · Due applicazioni, una scrittura. E a dirlo è la chiave, non un `if`.
    """
    from telephone.application import APPLICATIONS, apply_the_outcome

    call = _mettici_una_chiamata(impegni, _chiamata())
    await _lega(impegni, _legame(
        "commitments", "complete", "dec_abc123", {"status": "pending"},
    ))
    esito = _esito(confirmed_changes={"appointment_date": "2026-09-14"})

    primo = await apply_the_outcome(impegni, call, esito)
    secondo = await apply_the_outcome(impegni, call, esito)

    assert primo.application_status == "applied"
    assert secondo.idempotency_key == primo.idempotency_key
    assert len(impegni[APPLICATIONS].righe) == 1
    # Una riga di audit sola: il secondo giro non è nemmeno arrivato al
    # servizio, perché il database gli ha detto che era già preso.
    assert len(impegni.decision_action_history.righe) == 1


@pytest.mark.asyncio
async def test_commitments_a_crash_before_the_write_is_retried_once(impegni):
    """
    5 · Morto prima della scrittura → si riprova, dalla porta normale.
    """
    from telephone.application import APPLICATIONS, recover_stale

    _mettici_una_chiamata(impegni, _chiamata())
    legame = await _lega(impegni, _legame(
        "commitments", "complete", "dec_abc123", {"status": "pending"},
    ))
    impegni["phone_calls"].righe[0]["metrics"] = {
        "outcome": _esito(confirmed_changes={"appointment_date": "2026-09-14"}
                          ).model_dump(),
    }
    await _appesa(impegni, legame, "complete")
    assert _stato(impegni) == "pending"

    chiusi = await recover_stale(impegni)

    assert len(chiusi) == 1
    assert chiusi[0].application_status == "applied"
    assert _stato(impegni) == "completed"
    assert len(impegni.decision_action_history.righe) == 1
    assert len(impegni[APPLICATIONS].righe) == 1


@pytest.mark.asyncio
async def test_commitments_a_crash_after_the_write_only_closes_the_record(impegni):
    """
    6 · Morto dopo la scrittura → si chiude il record, non si riscrive.

        UN RECORD `pending` NON DICE SE LA SCRITTURA È ANDATA.

    L'impegno è già chiuso. Rifare la transizione solleverebbe — la macchina a
    stati non esce dai terminali — e sarebbe la risposta giusta per il motivo
    sbagliato. Qui si guarda il mondo, si vede che ci siamo arrivati, e si
    chiude il record senza toccare niente.
    """
    from telephone.application import recover_stale

    _mettici_una_chiamata(impegni, _chiamata())
    legame = await _lega(impegni, _legame(
        "commitments", "complete", "dec_abc123", {"status": "pending"},
    ))
    impegni["phone_calls"].righe[0]["metrics"] = {
        "outcome": _esito(confirmed_changes={"appointment_date": "2026-09-14"}
                          ).model_dump(),
    }
    await _appesa(impegni, legame, "complete")
    #     LA SCRITTURA ERA PASSATA. IL PROCESSO È MORTO SUBITO DOPO.
    impegni.decisions.righe[0]["action_state"] = {"status": "completed"}
    impegni.decisions.righe[0]["status"] = "completed"

    chiusi = await recover_stale(impegni)

    assert len(chiusi) == 1
    assert chiusi[0].application_status == "applied"
    assert chiusi[0].writes == ["commitments:dec_abc123"]
    # Nessuna seconda riga di audit: non abbiamo riscritto niente.
    assert impegni.decision_action_history.righe == []


@pytest.mark.asyncio
async def test_commitments_a_changed_commitment_is_a_conflict(impegni):
    """
    7 · Qualcun altro l'ha mosso → la premessa è scaduta, e non si scrive.
    """
    from telephone.application import apply_the_outcome

    call = _mettici_una_chiamata(impegni, _chiamata())
    await _lega(impegni, _legame(
        "commitments", "complete", "dec_abc123", {"status": "pending"},
    ))
    #     DOPO LA TELEFONATA, DALL'APPLICAZIONE, QUALCUNO L'HA RIMANDATO.
    impegni.decisions.righe[0]["action_state"] = {
        "status": "postponed", "postponed_until": "2026-10-01T09:00:00",
    }

    record = await apply_the_outcome(
        impegni, call, _esito(confirmed_changes={"appointment_date": "2026-09-14"}),
    )

    assert record.application_status == "conflict"
    assert "cambiato dopo la telefonata" in record.error
    assert _stato(impegni) == "postponed"
    assert impegni.decision_action_history.righe == []


@pytest.mark.asyncio
async def test_commitments_a_fresh_pending_is_left_alone(impegni):
    """
    8 · Il recupero riprende quello che è rimasto lì, non quello in corso.

        UN `pending` FRESCO STA SUCCEDENDO.
    """
    from telephone.application import APPLICATIONS, CallMissionApplication, key_for
    from telephone.application import recover_stale
    from telephone.models import now_iso

    _mettici_una_chiamata(impegni, _chiamata())
    legame = await _lega(impegni, _legame(
        "commitments", "complete", "dec_abc123", {"status": "pending"},
    ))
    chiave = key_for(legame.mission_id, "complete", "dec_abc123")
    record = CallMissionApplication(
        mission_id=legame.mission_id, call_id="tel_uno", owner_id="u1",
        target_domain="commitments", target_entity_id="dec_abc123",
        operation="complete", outcome_status="success",
        application_status="pending", created_at=now_iso(),
        idempotency_key=chiave,
    )
    await impegni[APPLICATIONS].insert_one({**record.model_dump(), "_id": chiave})

    chiusi = await recover_stale(impegni)

    assert chiusi == []
    assert impegni[APPLICATIONS].righe[0]["application_status"] == "pending"
    assert _stato(impegni) == "pending"


@pytest.mark.asyncio
async def test_commitments_without_a_binding_nothing_is_touched(impegni):
    """
    9 · Nessun mandato, nessun legame, nessuna scrittura.

        CHI HA PARLATO NON SCRIVE NIENTE NEL MONDO.

    Senza legame non si cerca l'impegno che somiglia di più al discorso: è
    esattamente la cosa che questo arco di lavoro vieta, in ogni dominio.
    """
    from telephone.application import apply_the_outcome

    call = _mettici_una_chiamata(impegni, _chiamata())

    record = await apply_the_outcome(
        impegni, call, _esito(confirmed_changes={"appointment_date": "2026-09-14"}),
    )

    assert record.application_status == "skipped"
    assert _stato(impegni) == "pending"
    assert impegni.decision_action_history.righe == []


# ===========================================================================
# STUDIO — le sessioni che una telefonata sposta
# ===========================================================================

@pytest.fixture
def studio(monkeypatch):
    """Un database con una sessione pianificata, e il piano vero che la scrive."""
    monkeypatch.setenv("ORA_TIMEZONE", "Europe/Rome")
    db = FintoDb()
    db.study_sessions.righe.append(dict(SESSIONE))
    db.study_plans.righe.append(dict(PIANO))
    return db


def _sessione(db):
    return db.study_sessions.righe[0]


@pytest.mark.asyncio
async def test_study_a_confirmed_move_really_moves_the_session(studio):
    """
    1 · Successo: la sessione slitta, e il piano si ricalcola da solo.

        «LE 18» SONO LE 18 DI CHI HA TELEFONATO.

    La sessione è scritta in UTC e comincia alle 14:00 — cioè le 16:00 di
    Roma. Concordate le 18:00, deve finire alle 16:00 UTC: due ore, non
    quattro. Fondere i due orologi senza convertire era il modo silenzioso di
    sbagliarla.
    """
    from telephone.application import apply_the_outcome

    call = _mettici_una_chiamata(studio, _chiamata())
    await _lega(studio, _legame(
        "study", "reschedule", "ssn_abc123",
        {"starts_at": SESSIONE["starts_at"], "status": "planned"},
    ))

    record = await apply_the_outcome(studio, call, _esito(confirmed_changes={
        "appointment_date": "2026-09-14", "appointment_time": "18:00",
    }))

    assert record.application_status == "applied"
    assert record.writes == ["study:ssn_abc123"]
    riga = _sessione(studio)
    assert riga["status"] == "snoozed"
    assert datetime.fromisoformat(riga["starts_at"]) == datetime(
        2026, 9, 14, 16, 0, tzinfo=timezone.utc)
    # E la fine si sposta con l'inizio: spostare non è accorciare.
    assert datetime.fromisoformat(riga["ends_at"]) == datetime(
        2026, 9, 14, 17, 0, tzinfo=timezone.utc)
    # Il piano ha riletto il proprio avanzamento.
    assert studio.study_plans.righe[0]["progress"]["total_sessions"] == 1


@pytest.mark.asyncio
async def test_study_a_session_cannot_be_pulled_earlier(studio):
    """
    1 · E quello che il piano non sa fare, qui non si inventa.

        UNA SESSIONE DI STUDIO VA AVANTI.

    `session_action` sposta per differenza, e non c'è una seconda porta che
    accetti un istante. Anticipare passerebbe di qui con un numero negativo e
    lascerebbe la sessione segnata «rimandata» a un'ora precedente. Si ferma,
    e lo dice — invece di aprire un secondo scrittore per quello stato.
    """
    from telephone.application import apply_the_outcome

    call = _mettici_una_chiamata(studio, _chiamata())
    await _lega(studio, _legame(
        "study", "reschedule", "ssn_abc123",
        {"starts_at": SESSIONE["starts_at"], "status": "planned"},
    ))

    record = await apply_the_outcome(studio, call, _esito(confirmed_changes={
        "appointment_date": "2026-09-14", "appointment_time": "09:00",
    }))

    assert record.application_status == "skipped"
    assert "non anticipare" in record.error
    assert _sessione(studio)["status"] == "planned"
    assert _sessione(studio)["starts_at"] == SESSIONE["starts_at"]


@pytest.mark.asyncio
async def test_study_needs_user_touches_nothing(studio):
    """2 · La controparte propone altro → nel mondo non si muove niente."""
    from telephone.application import apply_the_outcome

    call = _mettici_una_chiamata(studio, _chiamata())
    await _lega(studio, _legame(
        "study", "reschedule", "ssn_abc123",
        {"starts_at": SESSIONE["starts_at"], "status": "planned"},
    ))

    record = await apply_the_outcome(
        studio, call, _esito("needs_user", proposal="giovedì alle 11"),
    )

    assert record.application_status == "skipped"
    assert _sessione(studio)["starts_at"] == SESSIONE["starts_at"]
    assert _sessione(studio)["status"] == "planned"


@pytest.mark.asyncio
async def test_study_the_authority_can_forbid_the_write(studio):
    """
    3 · Un orario fuori dal mandato → si chiede, non si scrive.

    Il mandato consentiva le 18:00; la controparte ha detto le 20:00. Non è un
    rifiuto — una persona può ancora autorizzarlo — ma da soli non si fa.
    """
    from telephone.application import apply_the_outcome

    call = _mettici_una_chiamata(studio, _chiamata())
    await _lega(studio, _legame(
        "study", "reschedule", "ssn_abc123",
        {"starts_at": SESSIONE["starts_at"], "status": "planned"},
        autorita=_autorita("reschedule", "ssn_abc123",
                           data="2026-09-14", ora="18:00"),
    ))

    record = await apply_the_outcome(studio, call, _esito(confirmed_changes={
        "appointment_date": "2026-09-14", "appointment_time": "20:00",
    }))

    assert record.application_status == "skipped"
    assert _sessione(studio)["starts_at"] == SESSIONE["starts_at"]
    assert _sessione(studio)["status"] == "planned"


@pytest.mark.asyncio
async def test_study_applied_twice_moves_it_once(studio):
    """
    4 · Due applicazioni, uno spostamento.

        E QUI IL DOPPIONE SI VEDREBBE SUBITO.

    Lo spostamento è per differenza: applicato due volte porterebbe la
    sessione a quattro ore invece che a due. È il dominio in cui la chiave
    conta di più, ed è per questo che la si prova qui.
    """
    from telephone.application import APPLICATIONS, apply_the_outcome

    call = _mettici_una_chiamata(studio, _chiamata())
    await _lega(studio, _legame(
        "study", "reschedule", "ssn_abc123",
        {"starts_at": SESSIONE["starts_at"], "status": "planned"},
    ))
    esito = _esito(confirmed_changes={
        "appointment_date": "2026-09-14", "appointment_time": "18:00",
    })

    await apply_the_outcome(studio, call, esito)
    await apply_the_outcome(studio, call, esito)

    assert len(studio[APPLICATIONS].righe) == 1
    assert datetime.fromisoformat(_sessione(studio)["starts_at"]) == datetime(
        2026, 9, 14, 16, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_study_a_crash_before_the_write_is_retried_once(studio):
    """5 · Morto prima della scrittura → la sessione è ferma, si riprova."""
    from telephone.application import recover_stale

    _mettici_una_chiamata(studio, _chiamata())
    legame = await _lega(studio, _legame(
        "study", "reschedule", "ssn_abc123",
        {"starts_at": SESSIONE["starts_at"], "status": "planned"},
    ))
    studio["phone_calls"].righe[0]["metrics"] = {"outcome": _esito(
        confirmed_changes={
            "appointment_date": "2026-09-14", "appointment_time": "18:00",
        }).model_dump()}
    await _appesa(studio, legame, "reschedule")

    chiusi = await recover_stale(studio)

    assert len(chiusi) == 1
    assert chiusi[0].application_status == "applied"
    assert datetime.fromisoformat(_sessione(studio)["starts_at"]) == datetime(
        2026, 9, 14, 16, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_study_a_crash_after_the_write_does_not_move_it_again(studio):
    """
    6 · Morto dopo la scrittura → si chiude il record, non si risposta.

    È il caso peggiore di questo dominio: riapplicare uno spostamento per
    differenza non fa una scrittura innocua, fa un'altra sessione ancora. Qui
    si guarda dove la sessione è arrivata, si vede che è già quella
    concordata, e ci si ferma.
    """
    from telephone.application import recover_stale

    _mettici_una_chiamata(studio, _chiamata())
    legame = await _lega(studio, _legame(
        "study", "reschedule", "ssn_abc123",
        {"starts_at": SESSIONE["starts_at"], "status": "planned"},
    ))
    studio["phone_calls"].righe[0]["metrics"] = {"outcome": _esito(
        confirmed_changes={
            "appointment_date": "2026-09-14", "appointment_time": "18:00",
        }).model_dump()}
    await _appesa(studio, legame, "reschedule")
    #     LA SCRITTURA ERA PASSATA.
    _sessione(studio).update({
        "status": "snoozed",
        "starts_at": "2026-09-14T16:00:00+00:00",
        "ends_at": "2026-09-14T17:00:00+00:00",
    })

    chiusi = await recover_stale(studio)

    assert len(chiusi) == 1
    assert chiusi[0].application_status == "applied"
    assert datetime.fromisoformat(_sessione(studio)["starts_at"]) == datetime(
        2026, 9, 14, 16, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_study_a_session_moved_by_someone_else_is_a_conflict(studio):
    """
    7 · Spostata da qualcun altro → il delta porterebbe dove nessuno ha detto.

    È il motivo per cui il controllo di conflitto, in questo dominio, non è
    una cortesia: calcolare la differenza su un inizio diverso produce una
    destinazione diversa, e nessuno se ne accorgerebbe.
    """
    from telephone.application import apply_the_outcome

    call = _mettici_una_chiamata(studio, _chiamata())
    await _lega(studio, _legame(
        "study", "reschedule", "ssn_abc123",
        {"starts_at": SESSIONE["starts_at"], "status": "planned"},
    ))
    _sessione(studio)["starts_at"] = "2026-09-14T09:00:00+00:00"

    record = await apply_the_outcome(studio, call, _esito(confirmed_changes={
        "appointment_date": "2026-09-14", "appointment_time": "18:00",
    }))

    assert record.application_status == "conflict"
    assert _sessione(studio)["starts_at"] == "2026-09-14T09:00:00+00:00"
    assert _sessione(studio)["status"] == "planned"


@pytest.mark.asyncio
async def test_study_recovery_closes_what_was_left_hanging(studio):
    """8 · Il recupero chiude, e chiude una volta sola."""
    from telephone.application import APPLICATIONS, recover_stale

    _mettici_una_chiamata(studio, _chiamata())
    legame = await _lega(studio, _legame(
        "study", "complete", "ssn_abc123",
        {"starts_at": SESSIONE["starts_at"], "status": "planned"},
    ))
    studio["phone_calls"].righe[0]["metrics"] = {"outcome": _esito(
        confirmed_changes={"appointment_date": "2026-09-14"}).model_dump()}
    await _appesa(studio, legame, "complete")

    primo = await recover_stale(studio)
    secondo = await recover_stale(studio)

    assert len(primo) == 1 and secondo == []
    assert _sessione(studio)["status"] == "completed"
    assert len(studio[APPLICATIONS].righe) == 1


@pytest.mark.asyncio
async def test_study_without_a_binding_nothing_is_touched(studio):
    """9 · Nessun legame, nessuna scrittura. In ogni dominio."""
    from telephone.application import apply_the_outcome

    call = _mettici_una_chiamata(studio, _chiamata())

    record = await apply_the_outcome(studio, call, _esito(confirmed_changes={
        "appointment_date": "2026-09-14", "appointment_time": "18:00",
    }))

    assert record.application_status == "skipped"
    assert _sessione(studio)["starts_at"] == SESSIONE["starts_at"]


# ===========================================================================
# IL LEGAME GENERICO
# ===========================================================================

@pytest.mark.asyncio
async def test_binding_asks_the_domain_what_to_remember(impegni):
    """
    §1: `expected` non lo decide chi lega — lo decide il dominio.

        UN APPUNTAMENTO È IL SUO ORARIO. UN IMPEGNO È IL SUO STATO.

    Chi lega non sa che cosa sia un impegno, e non deve saperlo: lo chiede a
    `remembers`. È il motivo per cui aggiungere un dominio non tocca
    `binding.py`.
    """
    from telephone.binding import bind_a_domain_target

    legame, perche, domanda = await bind_a_domain_target(
        impegni, call=_chiamata(), domain="commitments",
        operation="complete", entity_id="dec_abc123",
    )

    assert perche == "" and domanda is False
    assert legame.expected["status"] == "pending"
    assert legame.expected["title"].startswith("Richiamare")
    assert legame.target.domain == "commitments"


@pytest.mark.asyncio
async def test_binding_refuses_a_pair_nobody_can_apply(impegni):
    """
    §1: prima di comporre il numero, non dopo.

    Scoprire che nessuno sa applicare questa cosa mentre si applica vuol dire
    averla già chiesta a una persona al telefono.
    """
    from telephone.binding import bind_a_domain_target

    legame, perche, domanda = await bind_a_domain_target(
        impegni, call=_chiamata(), domain="commitments",
        operation="book", entity_id="dec_abc123",
    )

    assert legame is None
    assert "non so ancora" in perche
    assert domanda is False


@pytest.mark.asyncio
async def test_binding_refuses_something_that_is_not_yours(studio):
    """§1: non si cerca un ripiego, in nessun dominio."""
    from telephone.binding import bind_a_domain_target

    legame, perche, _ = await bind_a_domain_target(
        studio, call=_chiamata(), domain="study",
        operation="reschedule", entity_id="ssn_di_qualcun_altro",
    )

    assert legame is None
    assert perche == "questa cosa non è più fra le tue"


@pytest.mark.asyncio
async def test_the_model_never_learns_the_internal_id_of_any_domain(impegni):
    """
    §4: l'identificativo interno non entra nel pacchetto. In nessun dominio.

        IL PACCHETTO PORTA IL NOME DEL CAMPO, MAI IL VALORE.

    Era vero per gli eventi in calendario dal V3.15. Un dominio nuovo che se
    lo dimenticasse rimetterebbe in circolo esattamente il dato che chi
    telefona non deve avere.
    """
    from telephone.binding import bind_a_domain_target
    from telephone.dossier import TelephoneCallDossier
    from telephone.mission import packet_for

    call = _chiamata()
    legame, _, _ = await bind_a_domain_target(
        impegni, call=call, domain="commitments",
        operation="complete", entity_id="dec_abc123",
    )
    fascicolo = TelephoneCallDossier(
        owner_id="u1", call_id="tel_uno", on_behalf_of="Francesco Cefalà",
    )
    packet = packet_for(call, fascicolo, binding=legame)

    assert "dec_abc123" not in packet.for_the_model()
    assert "dec_abc123" not in packet.model_dump_json()


# ===========================================================================
# COME SI RACCONTA
# ===========================================================================

def test_each_domain_speaks_its_own_language():
    """
    §1 · 8: la presentazione è del dominio, e i domini non parlano uguale.

    Un calendario parla di orari, un impegno di stati, un piano di sessioni.
    Una frase sola per tutti e tre sarebbe stata più corta e avrebbe detto
    «Fatto.» a una persona che voleva sapere che cosa è successo.
    """
    from telephone.domains import calendar, commitments, study

    assert "spostato" in calendar.says(
        "reschedule", {"start_datetime": "2026-09-14T18:00:00+02:00"})
    assert commitments.says("complete", {}) == "Impegno chiuso."
    assert "20/09" in commitments.says(
        "postpone", {"until": "2026-09-20T09:00:00"})
    assert "Sessione di studio" in study.says(
        "reschedule", {"starts_at": "2026-09-14T16:00:00+00:00"})
