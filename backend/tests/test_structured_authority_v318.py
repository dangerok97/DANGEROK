"""
L'autorità in una forma che si può verificare, invece che leggere.

    «UN APPUNTAMENTO FRA GIOVEDÌ E SABATO, IN ORARIO DI STUDIO».

È il mandato come lo scrive una persona, ed è giusto che lo scriva così. Ma
nessun confronto di testo può decidere se «venerdì 18 alle 10» ci stia dentro,
e provarci produce falsi allarmi — il progetto l'ha già imparato una volta, e
da allora l'unico controllo sull'orario era un parafulmine da quattordici
giorni che non interpretava niente.

Queste prove tengono ferme le quattro cose che rendono un'autorità
un'autorità:

    a decidere è il backend, sempre, e sempre allo stesso modo;
    il testo che una persona legge e la policy su cui si decide sono due cose;
    una decisione aggiunge una possibilità, non ne riscrive l'elenco;
    e una missione senza policy non è una missione senza regole — è una
    missione più vecchia, e continua a funzionare come prima.
"""

from __future__ import annotations

import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from test_post_call_application_v315 import (  # noqa: E402
    APPUNTAMENTO, FintoDb, FintoGoogle,
)


# ---------------------------------------------------------------------------
# Il banco
# ---------------------------------------------------------------------------

def _autorita(**cambia):
    from telephone.authority import CallMissionAuthority, a_slot_from

    campi = dict(
        operation="reschedule",
        entity_id="cal_abc123",
        desired=a_slot_from("2026-10-07", "15:00", 45),
        alternatives=[a_slot_from("2026-10-08", "11:00")],
        human_summary="confermare le 15:00 del 7 ottobre",
    )
    campi.update(cambia)
    return CallMissionAuthority(**campi)


def _proposta(operazione="reschedule", data="", ora="", entity="cal_abc123"):
    from telephone.authority import Proposal, a_slot_from

    fessura = a_slot_from(data, ora) if data else None
    return Proposal(
        operation=operazione,
        slot=fessura if (fessura and fessura.is_real()) else None,
        entity_id=entity,
    )


def _giudica(proposta, autorita):
    from telephone.authority import evaluate_authority

    return evaluate_authority(proposta, autorita)


# ---------------------------------------------------------------------------
# 1 · Il giudice
# ---------------------------------------------------------------------------

def test_exactly_what_was_asked_is_allowed():
    """La cosa che si era chiesta si può fare. È il caso facile, e va provato."""
    v = _giudica(_proposta(data="2026-10-07", ora="15:00"), _autorita())
    assert v.verdict == "allowed"
    assert v.code == "exactly_what_was_asked"
    assert v.ok()


def test_an_explicitly_allowed_alternative_is_allowed():
    """
    Quello che qualcuno ha scritto fra le alternative si accetta in linea.

    È l'unica autorità che ORA ha per dire di sì da sola a qualcosa che non
    era l'obiettivo — e deve essere scritta come data, non come descrizione.
    """
    v = _giudica(_proposta(data="2026-10-08", ora="11:00"), _autorita())
    assert v.verdict == "allowed"
    assert v.code == "explicitly_allowed"
    assert "08/10 alle 11:00" in v.says


def test_a_time_outside_the_mandate_goes_back_to_a_person():
    """
        DENTRO I CONFINI MA NON SCRITTO: SI CHIEDE.

    È il caso più comune di tutti, ed è per questo che il mandato è un elenco
    chiuso: quello che non c'è non è permesso, è da chiedere.
    """
    v = _giudica(_proposta(data="2026-10-07", ora="16:30"), _autorita())
    assert v.verdict == "needs_user"
    assert v.code == "not_in_the_mandate"
    assert not v.ok()


def test_another_day_that_nobody_authorised_goes_back_to_a_person():
    """Un giorno diverso non è un'altra opzione: è un'altra decisione."""
    v = _giudica(_proposta(data="2026-10-09", ora="15:00"), _autorita())
    assert v.verdict == "needs_user"


def test_a_different_operation_is_forbidden():
    """
        `needs_user` E `forbidden` NON SI SOMIGLIANO.

    Un orario fuori dal mandato lo può autorizzare una persona; un'operazione
    che nessuno ha chiesto no — non al telefono, non dopo.
    """
    v = _giudica(_proposta(operazione="cancel"), _autorita())
    assert v.verdict == "forbidden"
    assert v.code == "operation_not_allowed"
    assert "spostare" in v.says and "disdire" in v.says


def test_cancelling_when_only_a_move_was_authorised_is_forbidden():
    """Lo stesso caso detto con le parole di chi lo teme: disdire per errore."""
    v = _giudica(
        _proposta(operazione="cancel", data="2026-10-07", ora="15:00"),
        _autorita(),
    )
    assert v.verdict == "forbidden"


def test_another_appointment_is_forbidden():
    """Un altro oggetto non è un'altra opzione: è un altro impegno."""
    v = _giudica(
        _proposta(data="2026-10-08", ora="11:00", entity="cal_di_qualcun_altro"),
        _autorita(),
    )
    assert v.verdict == "forbidden"
    assert v.code == "wrong_target"


def test_temporal_bounds_are_checked():
    """I confini si verificano, e dicono quale dei due è stato superato."""
    regole = _autorita(earliest="2026-10-05", latest="2026-10-10",
                       alternatives=[])

    prima = _giudica(_proposta(data="2026-10-01", ora="11:00"), regole)
    assert prima.verdict == "needs_user" and prima.code == "before_earliest"

    dopo = _giudica(_proposta(data="2026-10-12", ora="11:00"), regole)
    assert dopo.verdict == "needs_user" and dopo.code == "after_latest"


def test_same_day_only_is_a_constraint_of_its_own():
    """
    «Spostalo più tardi, ma oggi» è comunissimo e due date lo esprimono male.
    """
    regole = _autorita(same_day_only=True, alternatives=[])

    stesso = _giudica(_proposta(data="2026-10-07", ora="17:00"), regole)
    assert stesso.verdict == "needs_user"
    assert stesso.code == "not_in_the_mandate"      # dentro il giorno, non scritto

    altro = _giudica(_proposta(data="2026-10-08", ora="15:00"), regole)
    assert altro.verdict == "needs_user"
    assert altro.code == "different_day"


def test_a_forbidden_change_is_named_and_refused():
    """
    Confronto esatto, non somiglianza.

    Il progetto ha già visto un controllo per somiglianza segnalare come
    violazione un appuntamento perfettamente dentro il mandato, e un allarme
    che grida a vuoto insegna a ignorarlo.
    """
    regole = _autorita(forbidden_changes=["date"], alternatives=[])
    v = _giudica(_proposta(data="2026-10-08", ora="11:00"), regole)
    assert v.verdict == "forbidden"
    assert v.code == "forbidden_change"


def test_a_proposal_without_a_time_cannot_be_judged():
    """
        `invalid` NON È UN NO.

    Vuol dire che non si è capito abbastanza per giudicare, ed è diverso da un
    rifiuto: chi lo riceve deve poter distinguere le due cose.
    """
    v = _giudica(_proposta(), _autorita())
    assert v.verdict == "invalid"
    assert v.code == "no_time_in_proposal"


def test_cancelling_needs_no_time_at_all():
    """Disdire non ha un quando da verificare: è lo stesso appuntamento."""
    regole = _autorita(operation="cancel", desired=None, alternatives=[],
                       latest="2026-12-31")
    v = _giudica(_proposta(operazione="cancel"), regole)
    assert v.verdict == "allowed"
    assert v.code == "no_time_to_check"


def test_the_judge_is_deterministic():
    """
    Gli stessi due oggetti danno sempre la stessa risposta.

    È la proprietà per cui esiste: una decisione che si può rileggere fra sei
    mesi e capire perché.
    """
    regole = _autorita()
    proposta = _proposta(data="2026-10-07", ora="16:30")
    risposte = {(_giudica(proposta, regole).verdict,
                 _giudica(proposta, regole).code) for _ in range(20)}
    assert len(risposte) == 1


def test_the_human_text_and_the_policy_are_two_things():
    """
        IL TESTO E LA POLICY STANNO IN DUE POSTI.

    Tenerli nello stesso campo significherebbe, prima o poi, decidere leggendo
    una frase.
    """
    regole = _autorita()
    assert regole.human_summary == "confermare le 15:00 del 7 ottobre"
    # E la frase non entra in nessuna decisione: cambiarla non cambia niente.
    muto = _autorita(human_summary="qualunque cosa, davvero qualunque")
    assert _giudica(_proposta(data="2026-10-07", ora="16:30"), muto).verdict == (
        _giudica(_proposta(data="2026-10-07", ora="16:30"), regole).verdict)


# ---------------------------------------------------------------------------
# 2 · Le missioni più vecchie
# ---------------------------------------------------------------------------

def test_no_policy_is_not_permission():
    """
        NESSUNA REGOLA NON VUOL DIRE «TUTTO PERMESSO».

    Vuol dire che non c'è abbastanza per giudicare, e chi ha chiamato il
    giudice deve saperlo — non ricevere un sì.
    """
    assert _giudica(_proposta(data="2026-10-07", ora="15:00"), None).verdict == (
        "invalid")

    from telephone.authority import CallMissionAuthority

    vuota = CallMissionAuthority(operation="reschedule")
    assert vuota.has_any_rule() is False
    v = _giudica(_proposta(data="2026-10-07", ora="15:00"), vuota)
    assert v.verdict == "invalid"
    assert v.code == "no_structured_authority"


@pytest.fixture
def mondo(monkeypatch):
    import telephone.domains.calendar as adattatore

    FintoGoogle.scritture = []
    FintoGoogle.solleva = None
    monkeypatch.setattr(adattatore, "_the_calendar", FintoGoogle)

    async def concesso(*_a, **_k):
        return ""

    monkeypatch.setattr(adattatore, "_consent_missing", concesso)

    db = FintoDb()
    db.calendar_event_drafts.righe.append(dict(APPUNTAMENTO))
    db["phone_calls"].righe.append(_chiamata().model_dump())
    return db


def _chiamata(**cambia):
    from telephone.models import Mandate, PhoneCall

    campi = dict(
        id="tel_uno", owner_id="u1", to_number="+393000000000",
        calling_whom="Studio Dentistico Bianchi",
        mandate=Mandate(
            why_calling="spostare il mio appuntamento dal dentista "
                        "dalle 16:00 alle 18:00",
            may_agree_to=["confermare le 18:00 di oggi"],
            must_bring_back=["lo studio conferma"],
        ),
        state="ended", how_it_ended="they_hung_up",
        started_at="2026-09-15T14:00:10+00:00",
        ended_at="2026-09-15T14:01:02+00:00",
    )
    campi.update(cambia)
    return PhoneCall(**campi)


def _esito(confirmed, status="success"):
    from telephone.mission import CallMissionOutcome

    return CallMissionOutcome(
        mission_id="mis_tel_uno", status=status, confirmed_changes=confirmed)


async def _lega(db, *, authority=None, call_id="tel_uno"):
    from telephone.binding import BINDINGS, CallMissionBinding, MissionTarget

    legame = CallMissionBinding(
        mission_id="mis_tel_uno", call_id=call_id, owner_id="u1",
        target=MissionTarget(
            domain="calendar", entity_id="cal_abc123", operation="reschedule"),
        expected={
            "start_datetime": "2026-09-14T16:00:00+02:00",
            "end_datetime": "2026-09-14T16:45:00+02:00",
            "timezone": "Europe/Rome", "title": "Dentista",
        },
        authority=authority,
    )
    await db[BINDINGS].insert_one(legame.model_dump())
    return legame


def _quando(db, ident="cal_abc123"):
    for r in db.calendar_event_drafts.righe:
        if r["id"] == ident:
            return r["start_datetime"]
    return None


@pytest.mark.asyncio
async def test_a_legacy_mission_without_a_policy_still_works(mondo):
    """
        UNA MISSIONE SENZA POLICY È UNA MISSIONE PIÙ VECCHIA, NON UNA VIETATA.

    A decidere restano i controlli che c'erano prima — identità, concorrenza,
    traduzione — ed è quello che tiene in piedi tutto ciò che funzionava già.
    """
    from telephone.application import apply_the_outcome

    await _lega(mondo, authority=None)
    record = await apply_the_outcome(mondo, _chiamata(), _esito({
        "appointment_date": "2026-09-14", "old_time": "16:00",
        "new_time": "18:00",
    }))

    assert record.application_status == "applied"
    assert _quando(mondo).startswith("2026-09-14T18:00")


# ---------------------------------------------------------------------------
# 3 · Il giudice davanti alla scrittura
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_an_authorised_change_is_written(mondo):
    """Quello che la policy consente si scrive, come sempre."""
    from telephone.application import apply_the_outcome
    from telephone.authority import CallMissionAuthority, a_slot_from

    await _lega(mondo, authority=CallMissionAuthority(
        operation="reschedule", entity_id="cal_abc123",
        desired=a_slot_from("2026-09-14", "18:00"),
    ))
    record = await apply_the_outcome(mondo, _chiamata(), _esito({
        "appointment_date": "2026-09-14", "old_time": "16:00",
        "new_time": "18:00",
    }))

    assert record.application_status == "applied"
    assert _quando(mondo).startswith("2026-09-14T18:00")


@pytest.mark.asyncio
async def test_nothing_is_written_when_the_authority_says_no(mondo):
    """
        §: NESSUNA MUTATION SE L'AUTORITÀ NON CONSENTE.

    È il punto per cui questo sprint esiste. Prima l'unico controllo
    sull'orario era un limite di quattordici giorni che non interpretava
    niente: un appuntamento spostato a un'ora che nessuno aveva autorizzato,
    ma nello stesso mese, passava.
    """
    from telephone.application import apply_the_outcome
    from telephone.authority import CallMissionAuthority, a_slot_from

    await _lega(mondo, authority=CallMissionAuthority(
        operation="reschedule", entity_id="cal_abc123",
        desired=a_slot_from("2026-09-14", "18:00"),
    ))
    record = await apply_the_outcome(mondo, _chiamata(), _esito({
        "appointment_date": "2026-09-14", "old_time": "16:00",
        "new_time": "19:30",          # nessuno l'ha autorizzata
    }))

    assert record.application_status == "skipped"
    assert "non era fra le cose che potevo accettare" in record.error
    assert _quando(mondo).startswith("2026-09-14T16:00")
    assert FintoGoogle.scritture == []


@pytest.mark.asyncio
async def test_an_authorised_alternative_is_written(mondo):
    """E un'alternativa scritta nella policy passa senza chiedere niente."""
    from telephone.application import apply_the_outcome
    from telephone.authority import CallMissionAuthority, a_slot_from

    await _lega(mondo, authority=CallMissionAuthority(
        operation="reschedule", entity_id="cal_abc123",
        desired=a_slot_from("2026-09-14", "18:00"),
        alternatives=[a_slot_from("2026-09-14", "19:30")],
    ))
    record = await apply_the_outcome(mondo, _chiamata(), _esito({
        "appointment_date": "2026-09-14", "old_time": "16:00",
        "new_time": "19:30",
    }))

    assert record.application_status == "applied"
    assert _quando(mondo).startswith("2026-09-14T19:30")


# ---------------------------------------------------------------------------
# 4 · La decisione entra nella policy
# ---------------------------------------------------------------------------

def _serve_una_decisione(slot=("2026-09-15", "11:00")):
    from telephone.mission import CallMissionOutcome, CounterpartyStatement

    return CallMissionOutcome(
        mission_id="mis_tel_uno", status="needs_user",
        user_confirmation_needed="Lo studio non può alle 18:00.",
        counterparty_statements=[CounterpartyStatement(
            kind="proposal", fact="Propone domani alle 11:00.", turn=2)],
        proposed_slot={"date": slot[0], "time": slot[1]} if slot else {},
        followup_required=True,
    )


@pytest.mark.asyncio
async def test_a_decision_updates_the_policy_not_a_list_of_words(mondo):
    """
        LA DECISIONE ENTRA NELLA POLICY, NON IN UN ELENCO DI FRASI.

    Concatenare il testo a `may_agree_to` diceva a chi telefona che cosa può
    accettare, in una forma che nessuno può verificare. Aggiungere l'orario
    alle alternative lo dice anche al giudice — che è l'unico che deciderà
    davvero se quella scrittura si può fare.
    """
    from telephone.application import apply_the_outcome
    from telephone.authority import CallMissionAuthority, a_slot_from
    from telephone.binding import binding_for
    from telephone.continuation import continuation_for, decide

    await _lega(mondo, authority=CallMissionAuthority(
        operation="reschedule", entity_id="cal_abc123",
        desired=a_slot_from("2026-09-14", "18:00"),
    ))
    await apply_the_outcome(mondo, _chiamata(), _serve_una_decisione())
    ferma = await continuation_for(mondo, "tel_uno")
    assert ferma.proposed_slot is not None
    assert ferma.proposed_slot.date == "2026-09-15"

    esito = await decide(mondo, continuation=ferma, decision="accept")
    assert esito.ok

    nuova = await binding_for(mondo, esito.call.id)
    assert nuova.authority is not None
    assert nuova.authority.already_allows(a_slot_from("2026-09-15", "11:00"))
    #     E QUELLO CHE C'ERA PRIMA RESTA.
    assert nuova.authority.desired.same_moment_as(a_slot_from("2026-09-14", "18:00"))

    # E adesso il giudice la lascia passare.
    from telephone.authority import Proposal, evaluate_authority

    v = evaluate_authority(
        Proposal(operation="reschedule", entity_id="cal_abc123",
                 slot=a_slot_from("2026-09-15", "11:00")),
        nuova.authority,
    )
    assert v.verdict == "allowed" and v.code == "explicitly_allowed"


@pytest.mark.asyncio
async def test_deciding_twice_adds_the_slot_once(mondo):
    """
        UNA DECISIONE AGGIUNGE, NON RISCRIVE — E NON AGGIUNGE DUE VOLTE.
    """
    from telephone.application import apply_the_outcome
    from telephone.authority import CallMissionAuthority, a_slot_from
    from telephone.binding import binding_for
    from telephone.continuation import by_id, continuation_for, decide

    await _lega(mondo, authority=CallMissionAuthority(
        operation="reschedule", entity_id="cal_abc123",
        desired=a_slot_from("2026-09-14", "18:00"),
    ))
    await apply_the_outcome(mondo, _chiamata(), _serve_una_decisione())
    ferma = await continuation_for(mondo, "tel_uno")

    primo = await decide(mondo, continuation=ferma, decision="accept")
    secondo = await decide(
        mondo, continuation=await by_id(mondo, ferma.id, "u1"), decision="accept")

    assert secondo.call is None, "ha fatto partire una seconda telefonata"
    nuova = await binding_for(mondo, primo.call.id)
    assert len(nuova.authority.alternatives) == 1

    # E la funzione che aggiunge è idempotente anche da sola.
    fessura = a_slot_from("2026-09-15", "11:00")
    due_volte = nuova.authority.now_also_allows(fessura).now_also_allows(fessura)
    assert len(due_volte.alternatives) == 1


@pytest.mark.asyncio
async def test_a_proposal_nobody_translated_leaves_the_policy_alone(mondo):
    """
    Se chi ha telefonato non ha tradotto la proposta in una data, non si
    inventa.

    Resta il comportamento di prima — il testo — e il giudice fermerà quella
    scrittura come fermerebbe qualunque altra cosa non scritta.
    """
    from telephone.application import apply_the_outcome
    from telephone.authority import CallMissionAuthority, a_slot_from
    from telephone.binding import binding_for
    from telephone.continuation import continuation_for, decide

    await _lega(mondo, authority=CallMissionAuthority(
        operation="reschedule", entity_id="cal_abc123",
        desired=a_slot_from("2026-09-14", "18:00"),
    ))
    await apply_the_outcome(mondo, _chiamata(), _serve_una_decisione(slot=None))
    ferma = await continuation_for(mondo, "tel_uno")
    assert ferma.proposed_slot is None

    esito = await decide(mondo, continuation=ferma, decision="accept")
    nuova = await binding_for(mondo, esito.call.id)
    assert nuova.authority.alternatives == []
    # Il testo però c'è, come prima.
    assert "Propone domani alle 11:00." in (
        await __import__("telephone.service", fromlist=["TelephoneService"])
        .TelephoneService(mondo).get("u1", esito.call.id)
    ).mandate.may_agree_to


@pytest.mark.asyncio
async def test_proposing_something_else_does_not_authorise_a_slot(mondo):
    """
        UN'ALTRA DATA NON È QUELLA CHE HANNO PROPOSTO.

    Chi propone un'alternativa sua sta chiedendo di trattare ancora, non
    autorizzando un orario preciso: quello resta da concordare in linea.
    """
    from telephone.application import apply_the_outcome
    from telephone.authority import CallMissionAuthority, a_slot_from
    from telephone.binding import binding_for
    from telephone.continuation import continuation_for, decide

    await _lega(mondo, authority=CallMissionAuthority(
        operation="reschedule", entity_id="cal_abc123",
        desired=a_slot_from("2026-09-14", "18:00"),
    ))
    await apply_the_outcome(mondo, _chiamata(), _serve_una_decisione())
    ferma = await continuation_for(mondo, "tel_uno")

    esito = await decide(
        mondo, continuation=ferma, decision="alternative",
        alternative="giovedì pomeriggio",
    )
    nuova = await binding_for(mondo, esito.call.id)
    assert nuova.authority.alternatives == []


# ---------------------------------------------------------------------------
# 5 · Il pacchetto
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_policy_never_travels_with_the_voice(mondo):
    """
    §5: a chi parla si dà la versione minima e comprensibile del mandato.

        LA POLICY SERVE A GIUDICARE, NON A PARLARE.

    Chi telefona non deve decidere se una proposta è dentro il mandato — non
    è il suo mestiere e non ne ha l'autorità — quindi i vincoli non gli
    servono, e gli identificativi interni men che meno.
    """
    from telephone.authority import CallMissionAuthority, a_slot_from
    from telephone.dossier import TelephoneCallDossier
    from telephone.mission import packet_for

    legame = await _lega(mondo, authority=CallMissionAuthority(
        operation="reschedule", entity_id="cal_abc123",
        desired=a_slot_from("2026-09-14", "18:00"),
        alternatives=[a_slot_from("2026-09-15", "11:00")],
        earliest="2026-09-14", latest="2026-09-20",
    ))
    fascicolo = TelephoneCallDossier(
        owner_id="u1", call_id="tel_uno", on_behalf_of="Francesco")
    testo = packet_for(_chiamata(), fascicolo, binding=legame).for_the_model()

    # Niente identificativi interni, come sempre.
    assert "cal_abc123" not in testo
    assert "mis_tel_uno" in testo      # il nome della missione sì: è suo
    # E nessun campo della policy: chi parla riporta, non giudica.
    for dentro in ("earliest", "latest", "same_day_only", "alternatives",
                   "forbidden_changes", "requires_user_confirmation"):
        assert dentro not in testo, f"la policy è finita nel pacchetto: {dentro}"

    # Quello che gli serve per parlare invece c'è: che cosa può accettare, in
    # parole.
    assert "allowed_negotiation" in testo
