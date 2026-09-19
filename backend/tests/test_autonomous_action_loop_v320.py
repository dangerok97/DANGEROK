"""
Il primo giro completo, dal proposito al mondo cambiato.

    C'ERANO TUTTI I MOTORI, E NON C'ERA IL GIRO.

Ognuno provato, ognuno verde, e nessuno che li attraversasse in fila. Queste
prove tengono ferme le cose che rendono un giro un giro invece di sette cose
che capitano nello stesso pomeriggio:

    lo stesso innesco non produce due propositi;
    senza un sì non succede niente fuori, e non perché ci sia una guardia —
      perché non c'è una strada;
    una telefonata riuscita non è un appuntamento spostato;
    un record `applied` non è un calendario alle diciotto;
    una commissione che si ferma e riprende resta **un** proposito;
    e quello che una persona legge è italiano, mai uno stato interno.

    LA PAROLA CHE COSTA DI PIÙ È «FATTO».

Metà di questo file esiste per i casi in cui non si può dire.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from test_post_call_application_v315 import (  # noqa: E402
    APPUNTAMENTO, FintoDb, FintoGoogle,
)


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


def _chiamata(call_id="tel_uno", stato="authorised", finita="unknown"):
    from telephone.models import Mandate, PhoneCall

    return PhoneCall(
        id=call_id,
        owner_id="u1",
        to_number="+393000000000",
        calling_whom="Studio Dentistico Bianchi",
        mandate=Mandate(
            why_calling="spostare il mio appuntamento dal dentista di oggi "
                        "dalle 16 alle 18",
            may_agree_to=["confermare le 18:00 di oggi"],
            must_bring_back=["lo studio conferma il nuovo orario"],
        ),
        state=stato,
        how_it_ended=finita,
        started_at="2026-09-14T14:00:10+00:00",
        ended_at="2026-09-14T14:01:02+00:00" if stato == "ended" else None,
    )


def _esito(status="success", mission_id="mis_tel_uno", **cambia):
    from telephone.mission import CallMissionOutcome

    campi = dict(
        mission_id=mission_id,
        status=status,
        confirmed_changes={
            "appointment_date": "2026-09-14",
            "old_time": "16:00",
            "new_time": "18:00",
        },
    )
    campi.update(cambia)
    return CallMissionOutcome(**campi)


def _legame(call_id="tel_uno", mission_id="mis_tel_uno", **cambia):
    from telephone.authority import CallMissionAuthority, a_slot_from
    from telephone.binding import CallMissionBinding, MissionTarget

    campi = dict(
        mission_id=mission_id,
        call_id=call_id,
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
        authority=CallMissionAuthority(
            operation="reschedule",
            entity_id="cal_abc123",
            desired=a_slot_from("2026-09-14", "18:00"),
            human_summary="confermare le 18:00 di oggi",
        ),
    )
    campi.update(cambia)
    return CallMissionBinding(**campi)


def _legame_impegno(call_id="tel_due", mission_id="mis_tel_due"):
    from telephone.binding import CallMissionBinding, MissionTarget

    return CallMissionBinding(
        mission_id=mission_id, call_id=call_id, owner_id="u1",
        target=MissionTarget(
            domain="commitments", entity_id="dec_abc123", operation="complete",
        ),
        expected={"status": "pending", "title": "Richiamare il commercialista"},
    )


async def _lega(db, legame):
    from telephone.binding import BINDINGS

    await db[BINDINGS].insert_one(legame.model_dump())
    return legame


def _proposta_di(frase: str):
    """Una frase della controparte classificata come proposta precisa."""
    from telephone.mission import CounterpartyStatement

    return CounterpartyStatement(kind="proposal", fact=frase, turn=3)


def _in_linea(db, call, esito=None):
    """Mette la telefonata nel database, con il suo esito se ne ha uno."""
    riga = call.model_dump()
    if esito is not None:
        riga["metrics"] = {"outcome": esito.model_dump()}
    esistente = [r for r in db["phone_calls"].righe if r.get("id") == call.id]
    if esistente:
        esistente[0].update(riga)
    else:
        db["phone_calls"].righe.append(riga)
    return call


@pytest.fixture
def mondo(monkeypatch):
    """Un calendario che si lascia guardare, e un impegno aperto."""
    import telephone.domains.calendar as adattatore

    FintoGoogle.scritture = []
    FintoGoogle.solleva = None
    monkeypatch.setattr(adattatore, "_the_calendar", FintoGoogle)

    async def concesso(*_a, **_k):
        return ""

    monkeypatch.setattr(adattatore, "_consent_missing", concesso)

    db = FintoDb()
    db.calendar_event_drafts.righe.append(dict(APPUNTAMENTO))
    db.decisions.righe.append(dict(IMPEGNO))
    return db


def _quando(db):
    return db.calendar_event_drafts.righe[0]["start_datetime"]


async def _un_piano_autorizzato(db, call=None, legame=None):
    """Il caso normale: preparato, legato, e con il sì già dato."""
    from autonomy.orchestrator import grant, plan_a_user_request

    call = call or _chiamata()
    legame = legame or _legame(call_id=call.id)
    _in_linea(db, call)
    await _lega(db, legame)
    plan, perche = await plan_a_user_request(db, call=call, binding=legame)
    assert plan is not None, perche
    return await grant(db, plan, authority_ref="explicit_yes")


# ===========================================================================
# 1 · Una richiesta che arriva in fondo
# ===========================================================================

@pytest.mark.asyncio
async def test_a_user_request_goes_all_the_way_to_a_changed_calendar(mondo):
    """
    Richiesta → piano → autorità → telefonata → esito → applicazione →
    stato canonico → resoconto.

        È IL GIRO, ED È LA PRIMA VOLTA CHE ESISTE.

    Nessun pezzo di questa catena è nuovo. Nuovo è che ci sia un oggetto che
    sappia di essere tutti e sette insieme, e che alla fine possa dire «fatto»
    per un motivo verificato invece che per un record che si autocertifica.
    """
    from autonomy.orchestrator import on_call_finished
    from telephone.application import apply_the_outcome

    plan = await _un_piano_autorizzato(mondo)
    assert plan.state == "authorised"

    call = _in_linea(mondo, _chiamata(stato="ended", finita="they_hung_up"), _esito())
    await apply_the_outcome(mondo, call, _esito())
    plan = await on_call_finished(mondo, call)

    assert plan.state == "completed"
    assert plan.verified is True
    assert _quando(mondo).startswith("2026-09-14T18:00")
    assert plan.application_id == "mis_tel_uno|reschedule|cal_abc123"


@pytest.mark.asyncio
async def test_the_plan_tells_it_in_italian(mondo):
    """
    §8: quello che una persona legge non è mai uno stato interno.

        «FATTO.» — NON «state=completed».

    Ed è un controllo, non una convenzione: qui si legge la scheda e si
    verifica che nessuna delle nove parole del backend ci sia finita dentro.
    """
    from autonomy.orchestrator import on_call_finished
    from autonomy.presentation import as_a_card, in_full
    from telephone.application import apply_the_outcome

    await _un_piano_autorizzato(mondo)
    call = _in_linea(mondo, _chiamata(stato="ended", finita="they_hung_up"), _esito())
    await apply_the_outcome(mondo, call, _esito())
    plan = await on_call_finished(mondo, call)

    scheda = as_a_card(plan)
    assert scheda["status_label"] == "Fatto"
    assert "18:00" in scheda["summary"]
    assert scheda["done"] is True and scheda["verified"] is True
    assert scheda["what_it_touches"] == "spostare — il calendario"

    testo = str(in_full(plan))
    for parola in ("completed", "waiting_authority", "applying", "authorised",
                   "idempotency", "mis_tel_uno", "cal_abc123"):
        assert parola not in testo, parola


# ===========================================================================
# 2 · Si ferma, si decide, riprende — e resta un piano solo
# ===========================================================================

@pytest.mark.asyncio
async def test_needs_user_pauses_the_same_plan_and_the_decision_resumes_it(mondo):
    """
    §5: qualunque livello produca `needs_user`, il piano aspetta.

        NESSUN PIANO NUOVO. MAI.

    La ripresa fa una seconda telefonata e il piano la segue, ma resta quello
    di prima — stessa chiave, stessa storia, stesso nome di missione. È così
    che «fatto» si può dire una volta sola.
    """
    from autonomy.orchestrator import on_call_finished, on_user_decision
    from autonomy.plan import PLANS
    from telephone.application import apply_the_outcome
    from telephone.continuation import continuation_for, decide

    plan = await _un_piano_autorizzato(mondo)
    primo_id = plan.plan_id

    #     LO STUDIO PROPONE ALTRO.
    fermato = _esito(
        "needs_user", confirmed_changes={},
        user_confirmation_needed="Lo studio non può alle 18:00.",
        counterparty_statements=[_proposta_di("giovedì 8 alle 11:00")],
        #     LA STESSA COSA IN DATE, CHE È L'UNICA CONFRONTABILE.
        proposed_slot={"date": "2026-09-18", "time": "11:00"},
    )
    call = _in_linea(mondo, _chiamata(stato="ended", finita="they_hung_up"), fermato)
    await apply_the_outcome(mondo, call, fermato)
    plan = await on_call_finished(mondo, call)

    assert plan.state == "waiting_user"
    assert plan.needs_user_decision is True
    assert _quando(mondo).startswith("2026-09-14T16:00")

    #     LA PERSONA ACCETTA.
    continuazione = await continuation_for(mondo, "tel_uno")
    esito = await decide(mondo, continuation=continuazione, decision="accept")
    assert esito.ok and esito.call is not None
    plan = await on_user_decision(mondo, esito.continuation)

    assert plan.plan_id == primo_id
    assert plan.state == "authorised"
    assert plan.call_id == esito.call.id
    assert plan.needs_user_decision is False
    #     UN PIANO SOLO, NON DUE.
    assert len(mondo[PLANS].righe) == 1


@pytest.mark.asyncio
async def test_cancelling_the_decision_closes_the_same_plan(mondo):
    """§5 · §9: se la persona lascia perdere, il piano si chiude. Non fallisce."""
    from autonomy.orchestrator import on_call_finished, on_user_decision
    from telephone.application import apply_the_outcome
    from telephone.continuation import continuation_for, decide

    await _un_piano_autorizzato(mondo)
    fermato = _esito("needs_user", confirmed_changes={}, proposal="giovedì alle 11")
    call = _in_linea(mondo, _chiamata(stato="ended", finita="they_hung_up"), fermato)
    await apply_the_outcome(mondo, call, fermato)
    await on_call_finished(mondo, call)

    continuazione = await continuation_for(mondo, "tel_uno")
    esito = await decide(mondo, continuation=continuazione, decision="cancel")
    plan = await on_user_decision(mondo, esito.continuation)

    assert plan.state == "cancelled"
    assert plan.needs_user_decision is False
    assert _quando(mondo).startswith("2026-09-14T16:00")


# ===========================================================================
# 3 · Un pensiero di ORA arriva fino alla proposta
# ===========================================================================

@pytest.mark.asyncio
async def test_a_signal_produces_a_proposal_and_nothing_else(mondo):
    """
    §3B: in V1 ORA può proporre. Non può fare.

        UN SISTEMA CHE AGISCE PER UN PENSIERO PROPRIO DEVE PRIMA ESSERE
        CREDUTO SUI PENSIERI.

    Il piano nasce senza autorità e resta fermo: non c'è nessuna telefonata,
    nessun legame, nessuna applicazione — e soprattutto non c'è una strada che
    ce lo porti, perché `advance` da lì non si muove.
    """
    from autonomy.orchestrator import advance, plan_from_a_signal
    from autonomy.presentation import as_a_card, what_you_can_answer

    plan, perche = await plan_from_a_signal(
        mondo, owner_id="u1",
        dedupe_key="cal:cal_abc123:rev3",
        goal="spostare la visita, che si sovrappone al volo",
        reason="il volo di giovedì parte un'ora prima di quell'appuntamento",
    )
    assert plan is not None, perche
    assert plan.state == "proposed"
    assert plan.authority_state == "absent"

    #     E NON SI MUOVE.
    plan = await advance(mondo, plan)
    assert plan.state == "proposed"
    assert mondo["phone_calls"].righe == []
    assert FintoGoogle.scritture == []

    scheda = as_a_card(plan)
    assert scheda["needs_you"] is True
    assert scheda["summary"].startswith("Ti propongo")
    assert what_you_can_answer(plan) == ["yes", "no"]


@pytest.mark.asyncio
async def test_a_signal_without_a_stable_identity_produces_nothing(mondo):
    """
    §7: una chiave che non è una chiave spegne l'idempotenza in silenzio.

    Meglio non aprire il piano che aprirne uno che si duplicherà al primo
    replay del segnale.
    """
    from autonomy.orchestrator import plan_from_a_signal

    plan, perche = await plan_from_a_signal(
        mondo, owner_id="u1", dedupe_key="", goal="qualcosa", reason="perché",
    )
    assert plan is None
    assert "identità stabile" in perche


# ===========================================================================
# 4 · Senza un sì non succede niente fuori
# ===========================================================================

@pytest.mark.asyncio
async def test_without_authority_the_plan_never_reaches_the_world(mondo):
    """
    §3 · §9: nessuna azione esterna senza autorità esplicita.

        E NON PERCHÉ CI SIA UNA GUARDIA: PERCHÉ NON C'È UNA STRADA.

    Il piano è preparato e legato, l'esito è lì e sarebbe applicabile. Manca
    solo il sì, e senza quello `advance` non lo porta da nessuna parte —
    nemmeno a guardare.
    """
    from autonomy.orchestrator import advance, plan_a_user_request

    call = _in_linea(mondo, _chiamata(stato="ended", finita="they_hung_up"), _esito())
    legame = await _lega(mondo, _legame())
    plan, _ = await plan_a_user_request(mondo, call=call, binding=legame)

    assert plan.state == "waiting_authority"
    assert plan.authority_state == "proposed"

    for _ in range(3):
        plan = await advance(mondo, plan)

    assert plan.state == "waiting_authority"
    assert plan.verified is False
    assert _quando(mondo).startswith("2026-09-14T16:00")
    assert FintoGoogle.scritture == []


@pytest.mark.asyncio
async def test_a_refusal_closes_the_plan_without_touching_anything(mondo):
    """§9: detto di no non è un fallimento. È una risposta."""
    from autonomy.orchestrator import advance, plan_a_user_request, refuse

    call = _in_linea(mondo, _chiamata())
    legame = await _lega(mondo, _legame())
    plan, _ = await plan_a_user_request(mondo, call=call, binding=legame)
    plan = await refuse(mondo, plan)

    assert plan.state == "cancelled"
    assert plan.authority_state == "refused"
    assert (await advance(mondo, plan)).state == "cancelled"
    assert FintoGoogle.scritture == []


# ===========================================================================
# 5 · Quando non si può dire «fatto»
# ===========================================================================

@pytest.mark.asyncio
async def test_a_failed_application_never_becomes_completed(mondo):
    """
    §4: una telefonata riuscita non basta.

        «HANNO CONFERMATO» NON È «È SPOSTATO».

    Lo studio ha detto di sì, il gate ha validato, la missione è riuscita — e
    Google non ha voluto saperne. La telefonata resta andata bene; il piano
    no, e lo dice.
    """
    from autonomy.orchestrator import on_call_finished
    from telephone.application import apply_the_outcome

    await _un_piano_autorizzato(mondo)
    FintoGoogle.solleva = RuntimeError("Google non risponde")

    call = _in_linea(mondo, _chiamata(stato="ended", finita="they_hung_up"), _esito())
    await apply_the_outcome(mondo, call, _esito())
    plan = await on_call_finished(mondo, call)

    assert plan.state == "failed"
    assert plan.verified is False
    assert _quando(mondo).startswith("2026-09-14T16:00")


@pytest.mark.asyncio
async def test_an_applied_record_over_an_unchanged_world_is_not_done(mondo):
    """
    §4: nemmeno un record `applied` basta.

        «APPLICATO» È UN RECORD. «FATTO» È IL MONDO.

    Qui il record dice di sì e il calendario è rimasto alle sedici. È il caso
    che nessun controllo interno può vedere, perché ogni controllo interno
    guarda lo stesso record. Il piano guarda il calendario, e dice quello che
    vede — compreso che è meglio controllare.
    """
    from autonomy.orchestrator import on_call_finished
    from telephone.application import apply_the_outcome

    await _un_piano_autorizzato(mondo)
    call = _in_linea(mondo, _chiamata(stato="ended", finita="they_hung_up"), _esito())
    await apply_the_outcome(mondo, call, _esito())

    #     QUALCUNO HA RIMESSO L'APPUNTAMENTO DOV'ERA.
    mondo.calendar_event_drafts.righe[0]["start_datetime"] = (
        "2026-09-14T16:00:00+02:00")

    plan = await on_call_finished(mondo, call)

    assert plan.state == "failed"
    assert plan.verified is False
    assert "controlli" in plan.error


@pytest.mark.asyncio
async def test_nobody_answered_is_said_as_nobody_answered(mondo):
    """§8: il motivo si dice in italiano, non in un codice."""
    from autonomy.orchestrator import on_call_finished
    from autonomy.presentation import as_a_card

    await _un_piano_autorizzato(mondo)
    call = _in_linea(mondo, _chiamata(stato="ended", finita="no_answer"))
    plan = await on_call_finished(mondo, call)

    assert plan.state == "failed"
    assert as_a_card(plan)["summary"] == "Non ha risposto."
    assert as_a_card(plan)["status_label"] == "Non sono riuscita a completarlo"


# ===========================================================================
# 6 · Idempotenza
# ===========================================================================

@pytest.mark.asyncio
async def test_the_same_trigger_opens_one_plan(mondo):
    """
    §7: lo stesso innesco non produce due propositi.

        A DIRLO È IL DATABASE, NON UN `if`.

    La chiave è l'`_id`: un secondo tentativo non arriva nemmeno a guardare se
    esiste. Cercare-poi-scrivere avrebbe lasciato aperta la finestra fra le
    due cose, che è quella in cui due richieste ravvicinate fanno due piani.
    """
    from autonomy.orchestrator import plan_a_user_request
    from autonomy.plan import PLANS

    call = _in_linea(mondo, _chiamata())
    legame = await _lega(mondo, _legame())

    primo, _ = await plan_a_user_request(mondo, call=call, binding=legame)
    secondo, _ = await plan_a_user_request(mondo, call=call, binding=legame)

    assert primo.plan_id == secondo.plan_id
    assert len(mondo[PLANS].righe) == 1


@pytest.mark.asyncio
async def test_the_same_signal_replayed_opens_one_plan(mondo):
    """§7: e vale anche per un segnale ripetuto, che è il caso più comune."""
    from autonomy.orchestrator import plan_from_a_signal
    from autonomy.plan import PLANS

    for _ in range(3):
        plan, _ = await plan_from_a_signal(
            mondo, owner_id="u1", dedupe_key="cal:cal_abc123:rev3",
            goal="spostare la visita", reason="si sovrappone al volo",
        )
    assert plan is not None
    assert len(mondo[PLANS].righe) == 1


@pytest.mark.asyncio
async def test_advancing_twice_writes_once(mondo):
    """
    §7: due esecuzioni, una scrittura.

        `advance` RILEGGE, NON RIFÀ.

    Chiamata due volte di fila dà due volte la stessa risposta, e nessuna
    delle due tocca il mondo: le scritture le fa l'application layer, quando è
    il suo momento, e la sua chiave le conta.
    """
    from autonomy.orchestrator import advance, on_call_finished
    from telephone.application import APPLICATIONS, apply_the_outcome

    await _un_piano_autorizzato(mondo)
    call = _in_linea(mondo, _chiamata(stato="ended", finita="they_hung_up"), _esito())
    await apply_the_outcome(mondo, call, _esito())
    await apply_the_outcome(mondo, call, _esito())

    plan = await on_call_finished(mondo, call)
    plan = await advance(mondo, plan)
    plan = await advance(mondo, plan)

    assert plan.state == "completed"
    assert len(FintoGoogle.scritture) == 1
    assert len(mondo[APPLICATIONS].righe) == 1
    assert _quando(mondo).startswith("2026-09-14T18:00")


# ===========================================================================
# 7 · Un secondo dominio, lo stesso giro
# ===========================================================================

@pytest.mark.asyncio
async def test_the_same_loop_closes_a_commitment(mondo):
    """
    §6: il giro non è del calendario. È del ciclo.

    Stesso piano, stessa autorità, stessa applicazione, stessa verifica — e
    dall'altra parte una macchina a stati che non somiglia a un calendario.
    L'orchestratore non se ne accorge, ed è esattamente il punto.
    """
    from autonomy.orchestrator import on_call_finished
    from autonomy.presentation import as_a_card
    from telephone.application import apply_the_outcome

    call = _chiamata(call_id="tel_due")
    legame = _legame_impegno(call_id="tel_due")
    plan = await _un_piano_autorizzato(mondo, call=call, legame=legame)
    assert plan.domain == "commitments"

    esito = _esito(
        mission_id="mis_tel_due",
        confirmed_changes={"appointment_date": "2026-09-14"},
    )
    finita = _in_linea(
        mondo, _chiamata(call_id="tel_due", stato="ended", finita="they_hung_up"),
        esito,
    )
    await apply_the_outcome(mondo, finita, esito)
    plan = await on_call_finished(mondo, finita)

    assert plan.state == "completed"
    assert plan.verified is True
    assert mondo.decisions.righe[0]["action_state"]["status"] == "completed"
    assert as_a_card(plan)["summary"] == "Impegno chiuso."
    assert as_a_card(plan)["what_it_touches"] == "chiudere — i tuoi impegni"


# ===========================================================================
# 8 · Recupero da uno stato intermedio
# ===========================================================================

@pytest.mark.asyncio
async def test_a_plan_left_hanging_is_picked_up_again(mondo):
    """
    §9: il processo è morto fra la telefonata e il resoconto.

        UN PIANO IN `applying` CHE NON SI MUOVE È UNA DOMANDA APERTA.

    Il mondo è già cambiato — l'applicazione era passata — e il piano è
    rimasto indietro. Nessuno indovina: si torna a guardare, e il calendario
    risponde.
    """
    from autonomy.orchestrator import recover_plans
    from autonomy.plan import by_key, save
    from telephone.application import apply_the_outcome

    plan = await _un_piano_autorizzato(mondo)
    call = _in_linea(mondo, _chiamata(stato="ended", finita="they_hung_up"), _esito())
    await apply_the_outcome(mondo, call, _esito())

    #     IL PROCESSO MUORE QUI: IL MONDO È CAMBIATO, IL PIANO NO.
    plan.state = "applying"
    await save(mondo, plan)
    assert _quando(mondo).startswith("2026-09-14T18:00")

    ripresi = await recover_plans(mondo)

    assert len(ripresi) == 1
    assert ripresi[0].state == "completed"
    assert (await by_key(mondo, plan.idempotency_key)).verified is True
    # Nessuna seconda scrittura: si è guardato, non rifatto.
    assert len(FintoGoogle.scritture) == 1


@pytest.mark.asyncio
async def test_recovery_leaves_alone_what_is_waiting_for_a_person(mondo):
    """
    §9: chi aspetta una persona non è rimasto a metà.

    `proposed`, `waiting_authority` e `waiting_user` non sono stati appesi:
    sono stati in cui il giro sta facendo la cosa giusta, cioè niente.
    """
    from autonomy.orchestrator import plan_from_a_signal, recover_plans

    await plan_from_a_signal(
        mondo, owner_id="u1", dedupe_key="cal:cal_abc123:rev3",
        goal="spostare la visita", reason="si sovrappone al volo",
    )
    call = _in_linea(mondo, _chiamata())
    legame = await _lega(mondo, _legame())
    from autonomy.orchestrator import plan_a_user_request

    await plan_a_user_request(mondo, call=call, binding=legame)

    assert await recover_plans(mondo) == []


# ===========================================================================
# 9 · La storia
# ===========================================================================

@pytest.mark.asyncio
async def test_the_history_reads_like_a_report(mondo):
    """
    §8 · §11: quello che è successo, in fila e in italiano.

        NON UN LOG: UN RESOCONTO.

    Chi legge non ha seguito niente: deve poter ricostruire il giro dalla
    prima riga all'ultima senza incontrare una parola che non userebbe.
    """
    from autonomy.orchestrator import on_call_finished
    from autonomy.presentation import in_full
    from telephone.application import apply_the_outcome

    await _un_piano_autorizzato(mondo)
    call = _in_linea(mondo, _chiamata(stato="ended", finita="they_hung_up"), _esito())
    await apply_the_outcome(mondo, call, _esito())
    plan = await on_call_finished(mondo, call)

    righe = [r["says"] for r in in_full(plan)["history"]]
    assert righe[0].startswith("Ti propongo di chiamare Studio Dentistico")
    assert "Hai detto di sì" in righe[1]
    assert "18:00" in righe[-1]
    assert all(r and r[0].isupper() for r in righe)


@pytest.mark.asyncio
async def test_a_long_history_keeps_its_first_line(mondo):
    """
    La prima riga dice perché questo piano esiste.

    Una storia lunga che la perdesse diventerebbe una storia senza inizio, e
    chi la legge dopo un mese non saprebbe più di che cosa si sta parlando.
    """
    from autonomy.plan import AutonomousActionPlan

    plan = AutonomousActionPlan(owner_id="u1", goal="spostare la visita")
    plan.note("proposed", "opened", "Ti propongo di spostare la visita.")
    for i in range(80):
        plan.note("executing", "tick", f"Riga numero {i}.")

    assert len(plan.history) == 40
    assert plan.history[0].says == "Ti propongo di spostare la visita."
    assert plan.history[-1].says == "Riga numero 79."


# ===========================================================================
# 10 · Il ciclo non è un secondo motore
# ===========================================================================

def test_the_orchestrator_does_not_decide_anything_itself():
    """
    §1: non duplica la logica interna di nessun motore.

        QUESTO FILE NON SA NIENTE.

    Nessuna regola su quando spostare un appuntamento, nessun giudizio
    sull'autorità, nessuna scrittura in un dominio. Il giorno in cui una di
    queste cose comparisse qui, sarebbe il giorno in cui ORA ha due teste — e
    questa prova è quello che lo rende rumoroso invece che silenzioso.
    """
    import inspect

    from autonomy import orchestrator, plan, presentation

    for modulo in (orchestrator, plan, presentation):
        sorgente = inspect.getsource(modulo)
        for roba in (
            "calendar_event_drafts", "db.decisions", "study_sessions",
            "insert_one({\"id\"", "GoogleCalendar", "ActionCenterService",
            "def evaluate_authority", "def key_for(mission",
        ):
            assert roba not in sorgente, f"{modulo.__name__}: {roba}"


def test_the_orchestrator_names_no_domain():
    """
    §1 · §6: e non conosce nessun dominio per nome.

    Il registro risponde per coppia; l'orchestratore passa quello che ha nel
    piano e riceve chi sa fare quella cosa. Un `if` con scritto «calendar»
    qui dentro sarebbe il primo passo verso un terzo posto in cui decidere.
    """
    import inspect

    from autonomy import orchestrator

    sorgente = inspect.getsource(orchestrator)
    for dominio in ("\"calendar\"", "'calendar'", "\"commitments\"", "\"study\""):
        assert dominio not in sorgente, dominio


def test_the_human_words_cover_every_state():
    """
    §8: nove stati, nove frasi.

    Uno stato senza frase vorrebbe dire che, prima o poi, a una persona
    finisce davanti la parola con cui il backend ci ragiona.
    """
    from typing import get_args

    from autonomy.plan import PlanState
    from autonomy.presentation import COME_SI_LEGGE

    assert set(get_args(PlanState)) == set(COME_SI_LEGGE)
