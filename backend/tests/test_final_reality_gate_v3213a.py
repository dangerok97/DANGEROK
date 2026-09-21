"""
V3.21.3a — quello che la Home aspetta adesso, da dove viene, e quanto costa.

    «DOMANDE PER TE» NON E' UNO STORICO. UNA FONTE NON SI INVENTA.
    UNA FRASE GIA' SCRITTA NON SI RIGENERA.

Tre decisioni di questo sprint, tenute ferme qui:

1. Una preparazione di telefonata è **un lavoro solo**. Confermare il numero e
   chiedere il via libera sono due fasi della stessa cosa: in Home ne resta
   aperta una, la corrente, anche quando sono nate in due conversazioni
   diverse. Il legame è l'identificativo della preparazione — mai il testo.
2. Un aggiornamento dice da dove viene davvero. Quando la sorgente non si
   ricostruisce, lo dichiara invece di usare una perifrasi.
3. Quando uno strumento restituisce già la frase che la persona leggerà, il
   turno non paga una seconda generazione del modello per riscriverla.
"""

from __future__ import annotations

import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from test_post_call_application_v315 import FintoDb  # noqa: E402


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


# ===========================================================================
# 1 · Una preparazione, una domanda
# ===========================================================================

@pytest.mark.asyncio
async def test_a_new_phase_supersedes_the_previous_one_of_the_same_preparation():
    """
    Misurato in app: «qual è il numero?» restava aperta mentre ORA chiedeva
    già il via libera per la stessa telefonata, e la Home mostrava due domande
    per un lavoro solo.
    """
    from waiting.models import ResumePointer, WorkRefs
    from waiting.service import WaitingService

    db = FintoDb()
    service = WaitingService(db)
    prima = _domanda(refs=WorkRefs(session_id="ces_1", preparation_id="prep_1"))
    db.open_questions.righe.append(prima.model_dump())

    await service.record_blocking_question(
        "u1",
        question="Vuoi che chiami Giulia adesso?",
        refs=WorkRefs(session_id="ces_2", preparation_id="prep_1"),
        resume=ResumePointer(kind="conversation"),
    )

    aperte = await service.list_open("u1")
    assert len(aperte) == 1
    assert aperte[0]["question"].startswith("Vuoi che chiami")
    assert db.open_questions.righe[0]["status"] == "superseded"


@pytest.mark.asyncio
async def test_two_phases_of_one_preparation_leave_only_the_current_one():
    """
    La riconciliazione non si fida di come le domande sono nate: guarda il
    lavoro a cui appartengono e tiene la più recente.
    """
    from waiting.models import WorkRefs
    from waiting.service import WaitingService

    db = FintoDb()
    db.open_questions.righe.append(
        _domanda(
            refs=WorkRefs(session_id="ces_1", preparation_id="prep_1"),
            created_at="2026-09-19T10:00:00+00:00",
        ).model_dump()
    )
    db.open_questions.righe.append(
        _domanda(
            question="Vuoi che chiami adesso?",
            refs=WorkRefs(session_id="ces_2", preparation_id="prep_1"),
            created_at="2026-09-19T11:00:00+00:00",
        ).model_dump()
    )
    db.mission_preparations.righe.append(
        {"preparation_id": "prep_1", "owner_id": "u1", "call_id": ""}
    )

    service = WaitingService(db)
    assert await service.reconcile_with_threads("u1") >= 1

    aperte = await service.list_open("u1")
    assert len(aperte) == 1
    assert aperte[0]["question"] == "Vuoi che chiami adesso?"
    vecchia = [r for r in db.open_questions.righe if r["question"].startswith("È questo")][0]
    assert vecchia["status"] == "superseded"
    assert vecchia["resolved_reason"] == "replaced_by_newer_phase"


@pytest.mark.asyncio
async def test_a_finished_call_leaves_no_question_of_its_preparation_open():
    """Dopo l'esito non resta niente da chiedere su quella telefonata."""
    from waiting.models import WorkRefs
    from waiting.service import WaitingService

    db = FintoDb()
    db.open_questions.righe.append(
        _domanda(refs=WorkRefs(session_id="ces_1", preparation_id="prep_1")).model_dump()
    )
    db.mission_preparations.righe.append(
        {"preparation_id": "prep_1", "owner_id": "u1", "call_id": "call_1"}
    )
    db.phone_calls.righe.append({"id": "call_1", "state": "ended"})

    service = WaitingService(db)
    await service.reconcile_with_threads("u1")

    assert await service.list_open("u1") == []


@pytest.mark.asyncio
async def test_a_question_of_a_preparation_that_no_longer_exists_is_let_go():
    from waiting.models import WorkRefs
    from waiting.service import WaitingService

    db = FintoDb()
    db.open_questions.righe.append(
        _domanda(refs=WorkRefs(session_id="ces_1", preparation_id="sparita")).model_dump()
    )

    service = WaitingService(db)
    await service.reconcile_with_threads("u1")

    assert await service.list_open("u1") == []
    assert db.open_questions.righe[0]["resolved_reason"] == "preparation_gone"


@pytest.mark.asyncio
async def test_a_thread_nobody_came_back_to_is_let_go_after_two_days():
    """
    Il difetto vero, misurato sui dati: si guardava `updated_at` della
    conversazione per capire se era andata avanti — ma quel campo si muove
    anche quando a parlare è ORA, che scrive la domanda un istante prima che
    la domanda venga registrata. Ogni riga sembrava viva, e non si chiudeva
    mai niente.
    """
    from waiting.models import WorkRefs
    from waiting.service import WaitingService

    db = FintoDb()
    db.open_questions.righe.append(
        _domanda(
            refs=WorkRefs(session_id="ces_vecchia"),
            created_at="2026-09-01T10:00:00+00:00",
        ).model_dump()
    )
    db.conversation_sessions.righe.append({
        "id": "ces_vecchia", "user_id": "u1",
        # ORA ha parlato dopo la domanda; la persona no.
        "updated_at": "2026-09-01T10:00:01+00:00",
        "history": [
            {"role": "user", "text": "chiama qualcuno", "at": "2026-09-01T09:59:00+00:00"},
            {"role": "ora", "text": "È questo il numero corretto?", "at": "2026-09-01T10:00:01+00:00"},
        ],
    })

    service = WaitingService(db)
    assert await service._let_go_of_abandoned_threads("u1") == 1
    assert db.open_questions.righe[0]["resolved_reason"] == "abandoned_thread"


@pytest.mark.asyncio
async def test_a_question_without_a_conversation_is_not_abandoned_by_time():
    """Si lascia andare un thread, non un lavoro: un piano non scade da solo."""
    from waiting.models import WorkRefs
    from waiting.service import WaitingService

    db = FintoDb()
    db.open_questions.righe.append(
        _domanda(
            question="Quale data preferisci per il rinnovo?",
            refs=WorkRefs(plan_id="pln_1"),
            created_at="2026-09-01T10:00:00+00:00",
        ).model_dump()
    )

    service = WaitingService(db)
    assert await service._let_go_of_abandoned_threads("u1") == 0
    assert len(await service.list_open("u1")) == 1


# ===========================================================================
# 2 · Da dove viene davvero
# ===========================================================================

def test_a_source_that_cannot_be_reconstructed_says_so():
    """
    «Nata dal lavoro di ORA» sembrava una provenienza e non lo era: non dice
    né che cosa ORA ha letto, né quando. Adesso la card lo ammette.
    """
    from agent.models import AutonomousGoal

    goal = AutonomousGoal(
        owner_id="u1",
        objective="Ritiro di un certificato",
        desired_outcome="Avere il certificato in mano",
        created_at="2026-09-18T09:00:00+00:00",
    )
    assert goal.where_it_came_from() == "originale non disponibile"


def test_every_known_source_is_named_in_words_a_person_uses():
    from agent.models import AutonomousGoal

    for tipo, atteso in (
        ("email", "un'email che ho letto"),
        ("message", "un messaggio che ho letto"),
        ("document", "un documento che mi hai dato"),
        ("calendar_event", "appuntamento nel calendario"),
        ("conversation", "una cosa che mi hai detto in chat"),
        ("memory", "quello che avevo già capito di te"),
        ("inference", "una deduzione mia"),
    ):
        goal = AutonomousGoal(
            owner_id="u1",
            objective="Qualcosa",
            desired_outcome="Qualcosa di fatto",
            source_kind=tipo,
            created_at="2026-09-18T09:00:00+00:00",
        )
        detto = goal.where_it_came_from()
        assert detto.startswith(atteso), (tipo, detto)
        assert "18 settembre" in detto


def test_one_vocabulary_for_every_row_of_the_updates():
    """
    In «Aggiornamenti di ORA» finiscono quattro cose diverse. Se ognuna
    chiamasse la stessa sorgente con un nome suo, la provenienza sembrerebbe
    un'etichetta invece che un fatto.
    """
    from agent.models import AutonomousGoal, how_we_say_the_source

    quando = "2026-09-18T09:00:00+00:00"
    assert how_we_say_the_source("life_reasoning", quando).startswith(
        "una deduzione mia da quello che so della tua vita"
    )
    assert "18 settembre" in how_we_say_the_source("email", quando)
    # Una sorgente che non si sa tradurre non diventa una perifrasi.
    assert how_we_say_the_source("", quando) == "originale non disponibile"
    assert how_we_say_the_source("qualcosa_di_nuovo", quando) == "originale non disponibile"

    # E il goal dice la stessa cosa con le stesse parole.
    goal = AutonomousGoal(
        owner_id="u1", objective="x", desired_outcome="y",
        source_kind="email", created_at=quando,
    )
    assert goal.where_it_came_from() == how_we_say_the_source("email", quando)


def test_a_goal_without_any_reference_says_what_is_still_missing():
    """
    Non è un giudizio sul testo: è il fatto che non ci sia niente a cui
    agganciare la cosa di cui ORA sta parlando.
    """
    from agent.models import AutonomousGoal
    from agent.service import AgentService

    senza = AutonomousGoal(
        owner_id="u1", objective="Ritiro di un certificato", desired_outcome="x",
    )
    con = AutonomousGoal(
        owner_id="u1", objective="Ritiro del certificato", desired_outcome="x",
        source_refs=["ev_1"],
    )
    assert "se mi dici a che cosa si riferisce" in AgentService._what_is_still_vague(senza)
    assert AgentService._what_is_still_vague(con) == ""


def test_a_thing_ora_cannot_identify_loses_the_definite_article():
    """
    Misurato sui dati veri: «Ritiro del certificato — giovedì» con
    `source_kind` e `source_refs` vuoti. L'articolo prometteva un certificato
    preciso che ORA non sapeva indicare.
    """
    from agent.models import AutonomousGoal

    vago = AutonomousGoal(
        owner_id="u1",
        objective="Avere il ritiro del certificato in agenda per giovedì.",
        desired_outcome="Certificato ritirato",
    )
    scheda = vago.for_human()
    assert "il ritiro di un certificato" in scheda["what"]
    assert scheda["unclear"] == "Non riesco ancora a capire di quale certificato si tratti."

    preciso = AutonomousGoal(
        owner_id="u1",
        objective="Avere il ritiro del certificato in agenda per giovedì.",
        desired_outcome="Certificato ritirato",
        source_kind="calendar_event",
        source_refs=["ev_1"],
    )
    # Quando ORA sa di che cosa parla, la frase resta quella che ha scritto.
    assert "il ritiro del certificato" in preciso.for_human()["what"]
    assert preciso.for_human()["unclear"] == ""


# ===========================================================================
# 3 · Una frase già scritta non si rigenera
# ===========================================================================

def test_the_sentence_a_tool_already_wrote_is_the_one_the_person_reads():
    """
    Se la frase dello strumento vince comunque sul testo del modello, la
    generazione che l'ha prodotta era tempo pagato e buttato.
    """
    from conversation_engine.ai_core.loop import _the_tool_s_own_sentence

    osservazioni = [
        {
            "name": "prepare_a_phone_call",
            "payload": {
                "say_this": "Ho trovato Giulia, +39 000, dalla rubrica. È questo il numero?",
                "preparation_id": "prep_1",
            },
        }
    ]
    assert _the_tool_s_own_sentence(osservazioni).startswith("Ho trovato Giulia")
    # Uno strumento che restituisce dati, non frasi, non parla al posto di ORA.
    assert _the_tool_s_own_sentence([{"name": "get_calendar", "payload": {"say_this": "x"}}]) == ""


def test_the_decision_built_from_the_tool_sentence_is_a_valid_one():
    """
    Misurato in app: la scorciatoia costruiva una decisione con uno stato di
    ragionamento che non esiste, e il turno moriva con un 500 — «Non riesco a
    raggiungere ORA in questo momento». Una decisione scritta dal codice deve
    passare le stesse regole di una scritta dal modello.
    """
    from conversation_engine.ai_core.models import CognitiveDecision

    frase = "Ho trovato Giulia, +39 000. È questo il numero corretto?"
    d = CognitiveDecision(
        response_mode="ask",
        user_intent_summary="conferma chiesta dallo strumento",
        reasoning_status="needs_user_input",
        message_to_user=frase,
        question=frase,
        confidence=0.9,
    )
    assert d.response_mode == "ask" and d.question == frase


def test_the_shortcut_is_only_taken_after_a_tool_has_spoken():
    """Al primo passo del turno non c'è nessuna osservazione: si ragiona."""
    from conversation_engine.ai_core.loop import _the_tool_s_own_sentence

    assert _the_tool_s_own_sentence([]) == ""
    assert _the_tool_s_own_sentence(None) == ""


# ===========================================================================
# 4 · Chi ho trovato non è sempre chi mi hai chiesto
# ===========================================================================

def test_a_similar_surname_is_not_the_person_you_asked_for():
    """
    Misurato in app (V3.21.3a): «Chiama Giulia Test», nessuna Giulia da nessuna
    parte, e ORA ha proposto «Francesco Test» come se l'avesse trovata. La
    conferma veniva chiesta su una premessa falsa.
    """
    from telephone.caps import _a_different_person_with_a_similar_name as diversa

    assert diversa("Giulia Test", "Francesco Test") is True
    # Il nome chiesto tutto dentro quello trovato è la stessa persona.
    assert diversa("Francesco", "Francesco Test") is False
    # Nessuna parola in comune: il numero è arrivato da un'altra strada — la
    # relazione in rubrica, un appuntamento — e non c'è niente da correggere.
    assert diversa("la mia ragazza", "Giulia Test") is False
    assert diversa("", "Giulia Test") is False


def test_when_the_name_does_not_match_ora_says_so_before_asking():
    from telephone.caps import _the_sentence

    carta = {
        "ready": False,
        "counterparty": "Giulia Test",
        "number_confirmed": False,
        "candidates": [],
        "contact": {
            "name": "Francesco Test",
            "number": "+39 000 000 0000",
            "source_label": "Una telefonata precedente",
            "source_detail": "l'avevi già chiamato con ORA",
        },
        "question": None,
        "says": "",
        "summary": "",
    }
    detto = _the_sentence(carta, False, False)
    assert detto.startswith("Non ho un numero per Giulia Test.")
    assert "Francesco Test" in detto
