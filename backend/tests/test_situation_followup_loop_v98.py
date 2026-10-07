"""Scripted model decisions, real cognitive loop and scheduling persistence.

These are integration tests of execution wiring, not live AI judgement tests.
No weather, notification, or other external provider is called.
"""
from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.models import ConversationSession
from conversation_engine.ai_core.loop import run_cognitive_loop
from situations.followup import read_followup, arrange_followup
from situations.models import SituationState
from situations.repository import SituationRepository


@pytest.mark.asyncio
async def test_saved_attention_is_reconsidered_and_real_tool_schedules_it(monkeypatch):
    monkeypatch.setenv('AMBIENT_RUNTIME', '1')
    db = AsyncMongoMockClient().test
    await db.agent_goals.create_index('id', unique=True)
    await db.agent_runs.create_index('goal_id', unique=True)
    await db.ambient_wakes.create_index('identity', unique=True)
    session = ConversationSession(user_id='followup-loop', meta={'ui_mode': 'ai_core', 'ai_core': {}})
    due = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
    calls = []

    async def decide(system, payload):
        calls.append(str(payload))
        if len(calls) == 1:
            return {'response_mode': 'answer', 'message_to_user': 'Ho registrato la situazione.',
                    'situation_update': {'operation': 'create',
                        'summary': 'Una situazione temporanea è ancora in corso.',
                        'attention_intent': 'Rivalutare le condizioni prima del prossimo passo.',
                        'source_refs': ['user_conversation']}}
        if len(calls) == 2:
            assert 'situation_followup_required' in str(payload)
            state = await db.situations.find_one({'user_id': session.user_id}, {'_id': 0})
            assert state['id'] in str(payload), 'cognition must receive the canonical identity'
            return {'response_mode': 'tool', 'tool_call': {
                'capability': 'schedule_situation_check', 'arguments': {
                    'situation_id': state['id'], 'expected_revision': state['revision'],
                    'check_at': due, 'purpose': 'Rivalutare il contesto al prossimo controllo.',
                    'completion_when': 'Quando le evidenze indicano che è arrivato il momento utile per agire.',
                    'notify_when': 'Se prima emerge un rischio che cambia il prossimo passo.'}}}
        assert len(calls) == 3, 'the repair must not loop indefinitely'
        return {'response_mode': 'answer', 'message_to_user': 'Il prossimo controllo risulta registrato.'}

    result = await run_cognitive_loop(sess=session, user_message='Una situazione temporanea è ancora in corso.',
                                     db=db, decision_fn=decide)
    assert result.ok
    assert result.tool_calls == 1
    assert len(calls) == 3
    state = await db.situations.find_one({'user_id': session.user_id}, {'_id': 0})
    followup = await read_followup(db, session.user_id, state['id'])
    assert followup['status'] == 'scheduled'
    assert followup['next_check_at'] == due
    assert followup['last_checked_at'] is None
    assert await db.agent_goals.count_documents({'owner_id': session.user_id}) == 1
    assert await db.ambient_wakes.count_documents({'owner_id': session.user_id}) == 1


@pytest.mark.asyncio
async def test_later_conversation_reads_existing_intention_without_rescheduling(monkeypatch):
    monkeypatch.setenv('AMBIENT_RUNTIME', '1')
    db = AsyncMongoMockClient().test
    session = ConversationSession(user_id='followup-later', meta={'ui_mode': 'ai_core', 'ai_core': {}})
    state = SituationState(id='sit_later', user_id=session.user_id, session_id=session.id,
                           summary='La situazione è ancora attiva.')
    await SituationRepository(db).insert(state)
    due = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
    before = await arrange_followup(db, session.user_id, situation_id=state.id,
        expected_revision=1, check_at=due, purpose='Rivedere le informazioni disponibili.',
        completion_when='Quando le evidenze indicano che è arrivato il momento utile per agire.',
        notify_when='Se prima il prossimo passo cambia per un rischio.')
    assert before['status'] == 'scheduled'

    async def decide(system, payload):
        assert due in str(payload), 'the ordinary conversation must receive the real recorded checkpoint'
        assert 'scheduled' in str(payload)
        return {'response_mode': 'answer', 'message_to_user': 'Il controllo già registrato non è stato spostato.'}

    result = await run_cognitive_loop(sess=session, user_message='Quando avevi intenzione di aggiornarmi?',
                                     db=db, decision_fn=decide)
    assert result.ok and result.tool_calls == 0
    assert (await read_followup(db, session.user_id, state.id))['next_check_at'] == due
    assert await db.ambient_wakes.count_documents({}) == 1
