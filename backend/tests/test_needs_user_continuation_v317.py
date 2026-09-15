"""
Una commissione che si ferma, e riprende da dove si era fermata.

    «ALLE 18 NO, POSSO DOMANI ALLE 11» NON È UN FALLIMENTO.

È il caso più comune di tutti, ed era l'unico che ORA non sapeva gestire. Il
mandato diceva «sposta alle 18»; lo studio propone un'altra cosa. Accettarla
sarebbe prendere un impegno che nessuno ha autorizzato — il mandato è un
elenco chiuso, e lo è per questo. Dichiarare fallita la missione sarebbe
buttare via una proposta buona e il lavoro di una telefonata.

Queste prove tengono ferme le quattro cose che rendono una pausa una pausa:

    finché nessuno decide, nel mondo non si tocca niente;
    quando si riprende, si riprende — non si ricomincia;
    la stessa decisione presa due volte resta una decisione;
    e due telefonate restano una missione sola.
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

def _chiamata(**cambia):
    from telephone.models import Mandate, PhoneCall

    campi = dict(
        id="tel_uno",
        owner_id="u1",
        to_number="+393000000000",
        calling_whom="Studio Dentistico Bianchi",
        mandate=Mandate(
            why_calling="spostare il mio appuntamento dal dentista "
                        "dalle 16:00 alle 18:00",
            may_agree_to=["confermare le 18:00 di oggi"],
            must_bring_back=["lo studio conferma il nuovo orario"],
            minutes=5,
        ),
        state="ended",
        how_it_ended="they_hung_up",
        started_at="2026-09-15T14:00:10+00:00",
        ended_at="2026-09-15T14:01:02+00:00",
    )
    campi.update(cambia)
    return PhoneCall(**campi)


def _serve_una_decisione(**cambia):
    """L'esito vero: hanno proposto un'altra cosa, e ORA non poteva dire sì."""
    from telephone.mission import CallMissionOutcome, CounterpartyStatement, MissionFact

    campi = dict(
        mission_id="mis_tel_uno",
        status="needs_user",
        confirmed_changes={},
        user_confirmation_needed="Lo studio non può alle 18:00.",
        counterparty_statements=[
            CounterpartyStatement(
                kind="refusal", fact="alle 18 non c'è posto", turn=2),
            CounterpartyStatement(
                kind="proposal", fact="Propone domani alle 11:00.", turn=3),
        ],
        new_facts=[MissionFact(field="prossimo_slot", value="domani alle 11:00")],
        followup_required=True,
    )
    campi.update(cambia)
    return CallMissionOutcome(**campi)


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


async def _lega(db, call_id="tel_uno"):
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
    )
    await db[BINDINGS].insert_one(legame.model_dump())
    return legame


def _quando(db, ident="cal_abc123"):
    for r in db.calendar_event_drafts.righe:
        if r["id"] == ident:
            return r["start_datetime"]
    return None


# ---------------------------------------------------------------------------
# 1 · Fermarsi invece di morire
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_an_alternative_outside_the_mandate_pauses_the_mission(mondo):
    """
    §: l'alternativa fuori mandato mette la missione in pausa.

        IL MANDATO È UN ELENCO CHIUSO, ED È PER QUESTO CHE SI DEVE CHIEDERE.

    Non è una mancanza da correggere: è il motivo per cui ORA non ha accettato
    da sola, e va raccontato a chi legge perché non sembri un capriccio.
    """
    from telephone.application import apply_the_outcome
    from telephone.continuation import continuation_for

    await _lega(mondo)
    record = await apply_the_outcome(mondo, _chiamata(), _serve_una_decisione())

    assert record.application_status == "skipped"
    ferma = await continuation_for(mondo, "tel_uno")
    assert ferma is not None
    assert ferma.state == "paused_for_user"
    assert ferma.mission_id == "mis_tel_uno"
    assert ferma.proposal == "Propone domani alle 11:00."
    assert ferma.reason == "Lo studio non può alle 18:00."
    assert ferma.facts == {"prossimo_slot": "domani alle 11:00"}
    assert "confermare le 18:00 di oggi" in ferma.authority_missing
    assert set(ferma.allowed_decisions) == {"accept", "alternative", "cancel"}


@pytest.mark.asyncio
async def test_nothing_is_written_while_nobody_has_decided(mondo):
    """
        FINCHÉ NESSUNO DECIDE, NEL MONDO NON SI TOCCA NIENTE.

    Una proposta in attesa di risposta è esattamente questo: in attesa.
    """
    from telephone.application import APPLICATIONS, apply_the_outcome

    await _lega(mondo)
    await apply_the_outcome(mondo, _chiamata(), _serve_una_decisione())

    assert _quando(mondo).startswith("2026-09-14T16:00")
    assert FintoGoogle.scritture == []
    applicate = [r for r in mondo[APPLICATIONS].righe
                 if r["application_status"] == "applied"]
    assert applicate == []


@pytest.mark.asyncio
async def test_the_same_call_read_twice_asks_only_once(mondo):
    """
    Una sola pausa per missione.

    Il recupero delle applicazioni rilegge gli esiti: due domande identiche
    davanti alla stessa persona sarebbero un difetto, non una precauzione.
    """
    from telephone.application import apply_the_outcome
    from telephone.continuation import CONTINUATIONS

    await _lega(mondo)
    await apply_the_outcome(mondo, _chiamata(), _serve_una_decisione())
    await apply_the_outcome(mondo, _chiamata(), _serve_una_decisione())

    assert len(mondo[CONTINUATIONS].righe) == 1


@pytest.mark.asyncio
async def test_an_ordinary_failure_does_not_ask_anything(mondo):
    """Una missione fallita non è una missione in pausa: non c'è da decidere."""
    from telephone.application import apply_the_outcome
    from telephone.continuation import CONTINUATIONS

    await _lega(mondo)
    await apply_the_outcome(
        mondo, _chiamata(), _serve_una_decisione(status="failed"))

    assert mondo[CONTINUATIONS].righe == []


# ---------------------------------------------------------------------------
# 2 · Chiedere, e sapere di aver chiesto
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reading_it_marks_the_question_as_asked(mondo):
    """
        UNA DOMANDA CHE NESSUNO VEDE NON È UNA DOMANDA.

    Serve a distinguere «non ha risposto» da «non gliel'abbiamo mai chiesto»,
    che sono due difetti diversi e si correggono in due posti diversi.
    """
    from telephone.application import apply_the_outcome
    from telephone.continuation import mark_shown, waiting_for

    await _lega(mondo)
    await apply_the_outcome(mondo, _chiamata(), _serve_una_decisione())

    ferme = await waiting_for(mondo, "u1")
    assert len(ferme) == 1 and ferme[0].state == "paused_for_user"

    vista = await mark_shown(mondo, ferme[0])
    assert vista.state == "pending_user_decision"
    assert vista.shown_at

    # E resta aperta: mostrarla non è deciderla.
    assert vista.still_open()
    assert len(await waiting_for(mondo, "u1")) == 1


@pytest.mark.asyncio
async def test_the_question_reads_like_somebody_wrote_it(mondo):
    """
    §5: «Lo studio non può alle 18:00. Propone domani alle 11:00.»

    Chi legge questa frase non ha seguito la telefonata: è la prima e spesso
    l'unica cosa che saprà, e deve bastargli per rispondere.
    """
    from telephone.application import apply_the_outcome
    from telephone.continuation import as_a_question, continuation_for

    await _lega(mondo)
    await apply_the_outcome(mondo, _chiamata(), _serve_una_decisione())
    domanda = as_a_question(await continuation_for(mondo, "tel_uno"))

    assert domanda["says"] == (
        "Lo studio non può alle 18:00. Propone domani alle 11:00.")
    assert domanda["open"] is True
    assert domanda["can"] == ["accept", "alternative", "cancel"]
    # Nessuno stato interno in faccia a nessuno.
    assert "needs_user" not in str(domanda)


# ---------------------------------------------------------------------------
# 3 · Decidere
# ---------------------------------------------------------------------------

async def _in_pausa(db):
    from telephone.application import apply_the_outcome
    from telephone.continuation import continuation_for

    await _lega(db)
    await apply_the_outcome(db, _chiamata(), _serve_una_decisione())
    return await continuation_for(db, "tel_uno")


@pytest.mark.asyncio
async def test_accepting_the_proposal_resumes_the_same_mission(mondo):
    """
        STESSO NOME, SECONDA TELEFONATA.

    Nasce una chiamata nuova — serve: una proposta non è una conferma, e il
    gate non ha mai accettato il contrario — ma porta il nome della missione
    originale. È così che l'applicazione resta una sola anche se le telefonate
    sono due.
    """
    from telephone.binding import binding_for
    from telephone.continuation import decide
    from telephone.service import TelephoneService

    ferma = await _in_pausa(mondo)
    esito = await decide(mondo, continuation=ferma, decision="accept")

    assert esito.ok and esito.call is not None
    assert esito.continuation.state == "resumed"
    assert esito.continuation.resumed_call_id == esito.call.id
    assert esito.call.id != "tel_uno"

    #     LA TELEFONATA NON PARTE DA SOLA. NEMMENO ADESSO.
    # Questa porta allarga il mandato; perché squilli serve ancora il sì
    # esplicito su quella chiamata, come per ogni altra.
    assert esito.call.state == "authorised"

    seconda = await TelephoneService(mondo).get("u1", esito.call.id)
    assert seconda.calling_whom == "Studio Dentistico Bianchi"
    assert seconda.to_number == "+393000000000"

    #     L'AUTORITÀ NUOVA SI AGGIUNGE, NON SOSTITUISCE.
    assert "confermare le 18:00 di oggi" in seconda.mandate.may_agree_to
    assert "Propone domani alle 11:00." in seconda.mandate.may_agree_to
    assert seconda.mandate.why_calling == _chiamata().mandate.why_calling

    #     E IL LEGAME SI EREDITA, CON IL NOME DI PRIMA.
    # L'oggetto da cambiare è lo stesso: ritrovarlo adesso vorrebbe dire
    # cercarlo, e cercarlo è la cosa che questo progetto non fa.
    ereditato = await binding_for(mondo, esito.call.id)
    assert ereditato is not None
    assert ereditato.mission_id == "mis_tel_uno"
    assert ereditato.target.entity_id == "cal_abc123"
    assert ereditato.expected["start_datetime"] == "2026-09-14T16:00:00+02:00"


@pytest.mark.asyncio
async def test_offering_another_alternative_resumes_too(mondo):
    """Chi non vuole domani alle 11 può proporre altro, e la missione riparte."""
    from telephone.continuation import decide
    from telephone.service import TelephoneService

    ferma = await _in_pausa(mondo)
    esito = await decide(
        mondo, continuation=ferma, decision="alternative",
        alternative="giovedì pomeriggio, dopo le 15",
    )

    assert esito.ok and esito.call is not None
    assert esito.continuation.state == "resumed"
    assert esito.continuation.decided_text == "giovedì pomeriggio, dopo le 15"

    seconda = await TelephoneService(mondo).get("u1", esito.call.id)
    assert "giovedì pomeriggio, dopo le 15" in seconda.mandate.may_agree_to
    # E la proposta che non ha accettato non entra nel mandato.
    assert "Propone domani alle 11:00." not in seconda.mandate.may_agree_to


@pytest.mark.asyncio
async def test_an_alternative_without_words_is_refused(mondo):
    """«Un'altra cosa» senza dire quale non è una decisione."""
    from telephone.continuation import decide

    ferma = await _in_pausa(mondo)
    esito = await decide(mondo, continuation=ferma, decision="alternative")

    assert esito.ok is False
    assert "quale alternativa" in esito.why
    assert esito.continuation.still_open()


@pytest.mark.asyncio
async def test_cancelling_closes_it_without_calling_anybody(mondo):
    """
        LASCIAR PERDERE È UNA CONCLUSIONE, NON UN FALLIMENTO.
    """
    from telephone.continuation import decide

    ferma = await _in_pausa(mondo)
    esito = await decide(mondo, continuation=ferma, decision="cancel")

    assert esito.ok
    assert esito.continuation.state == "cancelled"
    assert esito.call is None
    assert esito.continuation.still_open() is False
    assert mondo["phone_calls"].righe and len(mondo["phone_calls"].righe) == 1
    assert _quando(mondo).startswith("2026-09-14T16:00")


@pytest.mark.asyncio
async def test_a_decision_taken_twice_stays_one_decision(mondo):
    """
        CHI PREME DUE VOLTE LO STESSO PULSANTE NON FA PARTIRE DUE TELEFONATE.

    La prima risposta vince e le successive tornano lo stesso risultato: è il
    modo in cui si dice «sì, l'ho già fatto» senza rifarlo.
    """
    from telephone.continuation import CONTINUATIONS, decide

    ferma = await _in_pausa(mondo)
    primo = await decide(mondo, continuation=ferma, decision="accept")
    quante_prima = len(mondo["phone_calls"].righe)

    secondo = await decide(mondo, continuation=ferma, decision="accept")

    assert secondo.ok
    assert secondo.call is None, "ha fatto partire una seconda telefonata"
    assert "già stata presa" in secondo.why
    assert secondo.continuation.resumed_call_id == primo.call.id
    assert len(mondo["phone_calls"].righe) == quante_prima
    assert len(mondo[CONTINUATIONS].righe) == 1


@pytest.mark.asyncio
async def test_changing_your_mind_after_cancelling_does_not_reopen(mondo):
    """Una commissione lasciata cadere resta caduta: si riparte da capo, non da qui."""
    from telephone.continuation import decide

    ferma = await _in_pausa(mondo)
    await decide(mondo, continuation=ferma, decision="cancel")
    dopo = await decide(mondo, continuation=ferma, decision="accept")

    assert dopo.call is None
    assert dopo.continuation.state == "cancelled"


@pytest.mark.asyncio
async def test_accepting_nothing_is_not_a_decision(mondo):
    """Senza una proposta non c'è niente da accettare."""
    from telephone.application import apply_the_outcome
    from telephone.continuation import continuation_for, decide

    await _lega(mondo)
    await apply_the_outcome(mondo, _chiamata(), _serve_una_decisione(
        counterparty_statements=[]))
    ferma = await continuation_for(mondo, "tel_uno")
    assert ferma.proposal == ""

    esito = await decide(mondo, continuation=ferma, decision="accept")
    assert esito.ok is False
    assert "non c'è una proposta" in esito.why


@pytest.mark.asyncio
async def test_a_decision_nobody_understands_is_refused(mondo):
    """Tre risposte possibili, e nessuna quarta."""
    from telephone.continuation import decide

    ferma = await _in_pausa(mondo)
    esito = await decide(mondo, continuation=ferma, decision="forse")

    assert esito.ok is False
    assert ferma.still_open()


# ---------------------------------------------------------------------------
# 4 · Due telefonate, una missione
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_resumed_call_applies_once_for_the_whole_mission(mondo):
    """
        DUE TELEFONATE RESTANO UNA MISSIONE SOLA.

    La chiave di idempotenza porta il nome della missione, non quello della
    telefonata: la ripresa che applica e la prima che ci riprovasse userebbero
    la stessa chiave, e la seconda non scriverebbe niente.
    """
    from telephone.application import APPLICATIONS, apply_the_outcome
    from telephone.continuation import decide
    from telephone.mission import CallMissionOutcome
    from telephone.service import TelephoneService

    ferma = await _in_pausa(mondo)
    esito = await decide(mondo, continuation=ferma, decision="accept")
    seconda = await TelephoneService(mondo).get("u1", esito.call.id)

    #     E L'ESITO DELLA RIPRESA PORTA IL NOME DI PRIMA.
    confermato = CallMissionOutcome(
        mission_id="mis_tel_uno", status="success",
        confirmed_changes={
            "appointment_date": "2026-09-14", "old_time": "16:00",
            "new_time": "18:00",
        },
    )
    record = await apply_the_outcome(mondo, seconda, confermato)

    assert record.application_status == "applied"
    assert record.mission_id == "mis_tel_uno"
    assert record.call_id == seconda.id
    assert record.idempotency_key == "mis_tel_uno|reschedule|cal_abc123"
    assert _quando(mondo).startswith("2026-09-14T18:00")
    assert len(FintoGoogle.scritture) == 1

    # La prima telefonata che riprovasse: stessa chiave, nessuna scrittura.
    di_nuovo = await apply_the_outcome(mondo, _chiamata(), confermato)
    assert di_nuovo.idempotency_key == record.idempotency_key
    assert len(FintoGoogle.scritture) == 1
    applicati = [r for r in mondo[APPLICATIONS].righe
                 if r["application_status"] == "applied"]
    assert len(applicati) == 1


@pytest.mark.asyncio
async def test_a_successful_resume_closes_the_continuation(mondo):
    """La commissione sa com'è finita, non resta «ripresa» per sempre."""
    from telephone.continuation import continuation_for, decide
    from telephone.mission import CallMissionOutcome
    from telephone.application import apply_the_outcome
    from telephone.service import TelephoneService

    ferma = await _in_pausa(mondo)
    esito = await decide(mondo, continuation=ferma, decision="accept")
    seconda = await TelephoneService(mondo).get("u1", esito.call.id)

    await apply_the_outcome(mondo, seconda, CallMissionOutcome(
        mission_id="mis_tel_uno", status="success",
        confirmed_changes={"appointment_date": "2026-09-14",
                           "old_time": "16:00", "new_time": "18:00"},
    ))

    chiusa = await continuation_for(mondo, "tel_uno")
    assert chiusa.state == "succeeded"
    assert chiusa.still_open() is False
    assert len(await __import__(
        "telephone.continuation", fromlist=["waiting_for"]
    ).waiting_for(mondo, "u1")) == 0


@pytest.mark.asyncio
async def test_the_resumed_call_can_be_found_from_either_side(mondo):
    """
    La stessa commissione si ritrova da tutte e due le telefonate.

    Chi apre la prima vuole sapere com'è andata a finire; chi apre la seconda
    vuole sapere da dove veniva.
    """
    from telephone.continuation import continuation_for, decide

    ferma = await _in_pausa(mondo)
    esito = await decide(mondo, continuation=ferma, decision="accept")

    da_prima = await continuation_for(mondo, "tel_uno")
    da_dopo = await continuation_for(mondo, esito.call.id)
    assert da_prima is not None and da_dopo is not None
    assert da_prima.id == da_dopo.id == ferma.id


@pytest.mark.asyncio
async def test_a_continuation_whose_call_vanished_fails_honestly(mondo):
    """
    Una pausa che non ha più la sua telefonata non riprende niente.

    Non si ricostruisce un mandato a memoria: senza la telefonata di prima non
    si sa più che cosa si poteva accettare.
    """
    from telephone.continuation import decide

    ferma = await _in_pausa(mondo)
    mondo["phone_calls"].righe.clear()

    esito = await decide(mondo, continuation=ferma, decision="accept")
    assert esito.ok is False
    assert "non c'è più" in esito.why
    assert esito.call is None


# ---------------------------------------------------------------------------
# 5 · Come si legge
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_card_still_asks_for_a_decision(mondo):
    """
    §5: la scheda deve portare una CTA vera, non uno stato.

    «Serve una tua decisione» era già lì; adesso dietro c'è qualcosa da
    premere, e la frase dice che cosa è successo.
    """
    from telephone.application import application_for, apply_the_outcome
    from telephone.continuation import as_a_question, continuation_for
    from telephone.history import as_a_card

    await _lega(mondo)
    call = _chiamata()
    call.metrics = {"outcome": _serve_una_decisione().model_dump()}
    await apply_the_outcome(mondo, call, _serve_una_decisione())

    scheda = as_a_card(call, await application_for(mondo, "tel_uno"))
    assert scheda["presentation_status"] == "serve_una_decisione"
    assert scheda["needs_decision"] is True
    assert scheda["outcome_summary"] == "Lo studio non può alle 18:00."

    domanda = as_a_question(await continuation_for(mondo, "tel_uno"))
    assert domanda["proposal"] == "Propone domani alle 11:00."
    assert domanda["why_i_could_not_decide"]
