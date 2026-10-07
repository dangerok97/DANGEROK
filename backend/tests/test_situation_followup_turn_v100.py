"""Replay the reported passive reply for an EXISTING Situation, with no mutation.

Model decisions and weather are scripted. The cognitive loop, capability dispatch,
Situation ownership, checkpoint persistence and later readback are exercised.
These tests do not claim live AI, weather accuracy or notification delivery.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.ai_core.models import CognitiveDecision, ContextFact, Observation
from conversation_engine.ai_core.tools import weather_caps
from conversation_engine.models import ConversationSession
from situations.followup import arrange_followup, read_followup
from situations.models import SituationState
from situations.repository import SituationRepository
from situations.turn_followup import FollowupTurnGate

QUESTION = 'Quando avevi intenzione di avvisarmi di raccogliere i panni?'
BAD = ('Non avevo impostato un orario o un promemoria automatico per i panni stesi: '
       'la situazione risulta aperta ma senza controlli programmati. Vuoi che verifichi '
       'le condizioni meteo attuali o che imposti un controllo per un orario specifico?')


async def setup(monkeypatch, *, attention=True):
    monkeypatch.setenv('AMBIENT_RUNTIME', '1')
    db = AsyncMongoMockClient().test
    await db.agent_goals.create_index('id', unique=True)
    await db.agent_runs.create_index('goal_id', unique=True)
    await db.ambient_wakes.create_index('identity', unique=True)
    session = ConversationSession(user_id='v100-owner', meta={'ui_mode': 'ai_core', 'ai_core': {}})
    state = SituationState(id='sit_v100_existing', user_id=session.user_id,
        session_id='ces_previous_session', summary='Panni stesi all’aperto.',
        attention_intent='Rivalutare le condizioni e segnalare un momento utile.' if attention else None,
        next_check_summary='Controllare le condizioni al prossimo momento utile.')
    await SituationRepository(db).insert(state)
    return db, session, state


@pytest.mark.asyncio
@pytest.mark.parametrize('initial_mode,attention', [('answer', True), ('ask', True), ('answer', False)])
async def test_old_situation_no_mutation_rejects_menu_and_executes_read_then_schedule(monkeypatch, initial_mode, attention):
    db, session, state = await setup(monkeypatch, attention=attention)
    weather = AsyncMock(return_value=Observation(kind='tool', name='get_weather_forecast', status='ok',
        payload={'fixture': True, 'available': True, 'condition_label': 'Dati meteo simulati per il test.'}))
    monkeypatch.setattr(weather_caps, 'get_weather_forecast', weather)
    due = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
    calls = []

    async def decide(system, payload):
        calls.append(payload)
        if len(calls) == 1:
            assert 'Current-turn follow-up responsibility' in system
            assert state.id in payload
            return {'response_mode': initial_mode, 'message_to_user': BAD,
                    'question': BAD if initial_mode == 'ask' else None,
                    'situation_update': {'operation': 'none'}}
        if len(calls) == 2:
            assert 'situation_followup_required' in payload
            return {'response_mode': 'tool', 'tool_call': {'capability': 'get_weather_forecast', 'arguments': {}}}
        if len(calls) == 3:
            assert 'Dati meteo simulati per il test.' in payload
            return {'response_mode': 'tool', 'tool_call': {'capability': 'schedule_situation_check',
                'arguments': {'situation_id': state.id, 'expected_revision': 1, 'check_at': due,
                              'purpose': 'Rivalutare i dati reali al prossimo controllo.',
                              'completion_when': 'Quando le evidenze indicano che è arrivato il momento utile per concludere.',
                              'notify_when': 'Se prima emerge un rischio o cambia il prossimo passo utile.'}}}
        assert len(calls) == 4
        return {'response_mode': 'answer', 'message_to_user': 'Prima mancava il controllo; ora risulta registrato nella scheda.'}

    result = await run_cognitive_loop(sess=session, user_message=QUESTION, db=db, decision_fn=decide)
    assert result.ok and result.tool_calls == 2
    assert BAD not in result.ora_text and 'Vuoi che' not in result.ora_text
    weather.assert_awaited_once()
    followup = await read_followup(db, session.user_id, state.id)
    assert followup['status'] == 'scheduled' and followup['next_check_at'] == due
    assert await db.situations.count_documents({}) == 1
    assert (await SituationRepository(db).get(session.user_id, state.id)).revision == 1
    assert await db.agent_goals.count_documents({}) == 1
    assert await db.ambient_wakes.count_documents({}) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['unrelated', 'declined'])
async def test_relevance_and_explicit_restriction_do_not_start_work(monkeypatch, kind):
    db, session, state = await setup(monkeypatch)
    message = 'Parliamo invece del progetto musicale.' if kind == 'unrelated' else 'Non avviare controlli: voglio solo sapere cosa avevi fatto.'
    calls = 0

    async def decide(system, payload):
        nonlocal calls
        calls += 1
        return {'response_mode': 'answer', 'message_to_user': 'Va bene, non avvio un controllo.',
                'situation_followup': {'disposition': kind, 'reason': 'Il messaggio non delega questo lavoro.',
                    'situation_id': state.id if kind == 'declined' else None,
                    'user_words': 'Non avviare controlli' if kind == 'declined' else None}}

    result = await run_cognitive_loop(sess=session, user_message=message, db=db, decision_fn=decide)
    assert result.ok and result.tool_calls == 0 and calls == 1
    assert await db.agent_goals.count_documents({}) == 0


@pytest.mark.asyncio
async def test_ignored_recovery_cannot_repeat_menu_or_claim_a_job(monkeypatch):
    db, session, state = await setup(monkeypatch)
    decide = AsyncMock(return_value={'response_mode': 'answer', 'message_to_user': BAD})
    result = await run_cognitive_loop(sess=session, user_message=QUESTION, db=db, decision_fn=decide)
    assert decide.await_count == 2
    assert BAD not in result.ora_text and 'Vuoi che' not in result.ora_text
    assert 'Non risulta confermato' in result.ora_text
    assert (await read_followup(db, session.user_id, state.id))['status'] == 'not_scheduled'
    assert await db.ambient_wakes.count_documents({}) == 0


@pytest.mark.asyncio
async def test_already_scheduled_status_read_preserves_deadline(monkeypatch):
    db, session, state = await setup(monkeypatch)
    due = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
    await arrange_followup(db, session.user_id, situation_id=state.id, expected_revision=1,
        check_at=due, purpose='Verificare le condizioni.',
        completion_when='Quando le evidenze indicano che è arrivato il momento utile per concludere.',
        notify_when='Se prima cambia il prossimo passo per un rischio.')
    decide = AsyncMock(return_value={'response_mode': 'answer', 'message_to_user': 'Il controllo già registrato resta invariato.'})
    result = await run_cognitive_loop(sess=session, user_message=QUESTION, db=db, decision_fn=decide)
    assert decide.await_count == 1 and result.tool_calls == 0
    assert (await read_followup(db, session.user_id, state.id))['next_check_at'] == due
    assert await db.ambient_wakes.count_documents({}) == 1


@pytest.mark.asyncio
async def test_gate_rechecks_owner_and_closed_lifecycle(monkeypatch):
    db, session, state = await setup(monkeypatch)
    facts = [ContextFact(source='situation', ref=f'situation:{state.id}')]
    gate = FollowupTurnGate(db, 'another-owner')
    await gate.refresh(facts)
    assert not gate.pending
    await db.situations.update_one({'id': state.id}, {'$set': {'status': 'resolved'}})
    gate = FollowupTurnGate(db, session.user_id)
    await gate.refresh(facts)
    assert not gate.pending


@pytest.mark.asyncio
async def test_genuine_blocker_requires_structured_need_or_actual_tool_failure(monkeypatch):
    db, session, state = await setup(monkeypatch)
    gate = FollowupTurnGate(db, session.user_id)
    await gate.refresh([ContextFact(source='situation', ref=f'situation:{state.id}')])
    decision = CognitiveDecision(response_mode='ask', question='In quale luogo si trova?',
        situation_followup={'disposition': 'blocked', 'situation_id': state.id, 'reason': 'Manca il luogo.'})
    assert not gate.accepts_final(decision, QUESTION, [])
    decision = CognitiveDecision.model_validate({**decision.model_dump(), 'uncertainty': {
        'blocking': True, 'missing_information': [{'ref': 'place', 'description': 'Il luogo della situazione.',
              'necessity': 'required', 'blocking': True, 'strategy': 'ask'}]}})
    assert gate.accepts_final(decision, QUESTION, [])
    decision.uncertainty = None
    assert gate.accepts_final(decision, QUESTION, [{'kind': 'tool', 'status': 'denied'}])
    assert not gate.accepts_final(decision, QUESTION, [{'kind': 'context', 'status': 'error'}])
    decision.situation_followup.disposition = 'declined'
    decision.situation_followup.user_words = 'Non fare niente'
    assert not gate.accepts_final(decision, QUESTION, [])
