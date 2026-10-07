"""Reported mobile reply is raw Markdown, not plain clock text.

Unit tests reproduce the exact presentation regression. Integration decisions
are scripted; no real weather reading or notification receipt is claimed.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.loop import (
    _claims_wrong_situation_check_time,
    _latest_situation_schedule,
    run_cognitive_loop,
)
from conversation_engine.models import ConversationSession
from situations.clock import local_check_fields
from situations.followup import arrange_followup, read_followup
from situations.models import SituationState
from situations.repository import SituationRepository

MOBILE_REPLY = (
    "I panni sono stati stesi alle 14:02. ORA terrà questa situazione in vista e "
    "controllerà l'asciugatura. Il prossimo controllo è già programmato per le "
    "**15:00 di oggi**. Ti avviserò se le condizioni ambientali (vento, umidità, "
    "ecc.) potrebbero influenzare il processo o se i panni sembrano asciugarsi "
    "in modo irregolare. Se vuoi, posso anche verificare le condizioni "
    "meteorologiche attuali per aiutarti a capire meglio come procedere."
)


@pytest.mark.parametrize('text', [
    MOBILE_REPLY,
    'Il prossimo controllo è già\nprogrammato per le **15:00 di oggi**.',
    'Il prossimo controllo è programmato per le __15:00__.',
    'Il prossimo controllo è programmato per le `15:00`.',
    'Il prossimo controllo è programmato per le <strong>15:00</strong>.',
    'Il prossimo controllo è programmato per le&nbsp;**15:00**.',
    'Il prossimo controllo è programmato per le\u202f**15:00**.',
    'Il prossimo controllo è programmato per le ore 15.00.',
])
def test_formatted_wrong_clock_is_detected(text):
    assert _claims_wrong_situation_check_time(text, '17:00')


@pytest.mark.parametrize('text', [
    'Il prossimo controllo è programmato per le **17:00**.',
    'Ho steso i panni alle 15:00.',
    'Il controllo precedente è stato eseguito alle 15:00.',
    'Non farò un controllo alle 15:00.',
    'Ti avviso quando è il momento utile.',
])
def test_correct_unrelated_past_and_negative_clocks_are_preserved(text):
    assert not _claims_wrong_situation_check_time(text, '17:00')


@pytest.mark.parametrize('utc_value,tz_name,expected_time,expected_offset', [
    ('2026-10-07T15:00:00Z', 'Europe/Rome', '17:00', '+02:00'),
    ('2026-01-07T15:00:00Z', 'Europe/Rome', '16:00', '+01:00'),
    ('2026-10-25T00:30:00Z', 'Europe/Rome', '02:30', '+02:00'),
    ('2026-10-25T01:30:00Z', 'Europe/Rome', '02:30', '+01:00'),
    ('2026-10-07T15:00:00Z', 'Asia/Kolkata', '20:30', '+05:30'),
    ('2026-10-07T23:30:00Z', 'Europe/Rome', '01:30', '+02:00'),
])
def test_local_clock_preserves_the_original_instant(utc_value, tz_name, expected_time, expected_offset):
    result = local_check_fields(utc_value, tz_name)
    assert result['next_check_time_local'] == expected_time
    assert result['next_check_at_local'].endswith(expected_offset)
    assert datetime.fromisoformat(result['next_check_at_local']) == datetime.fromisoformat(utc_value.replace('Z', '+00:00'))
    assert expected_time in result['next_check_label']


def test_exact_screenshot_conversion():
    assert local_check_fields('2026-10-07T15:00:00Z', 'Europe/Rome')['next_check_label'] == '7 ott 2026, 17:00'
    assert local_check_fields('2026-10-07T15:00:00+02:00', 'Europe/Rome')['next_check_label'] == '7 ott 2026, 15:00'
    assert local_check_fields('2026-10-07T15:00:00', 'Europe/Rome') == {}
    assert local_check_fields('invalid', 'Europe/Rome') == {}
    assert local_check_fields('2026-10-07T15:00:00Z', 'invalid') == {}


def test_latest_read_can_confirm_or_revoke_a_schedule_but_never_mix_targets():
    payload = {'situation_id': 'sit_a', 'status': 'scheduled', 'next_check_at': '2026-10-07T15:00:00Z'}
    arrange = {'name': 'schedule_situation_check', 'status': 'ok', 'payload': payload}
    read = {'name': 'get_situation_followup', 'status': 'ok', 'payload': payload}
    assert _latest_situation_schedule([read]) == payload
    assert _latest_situation_schedule([arrange, read]) == payload
    stopped = {'name': 'get_situation_followup', 'status': 'ok', 'payload': {'situation_id': 'sit_a', 'status': 'stopped'}}
    assert _latest_situation_schedule([arrange, stopped]) is None
    failed = {'name': 'get_situation_followup', 'status': 'error', 'payload': {}}
    assert _latest_situation_schedule([arrange, failed]) is None
    other = {'name': 'get_situation_followup', 'status': 'ok', 'payload': {**payload, 'situation_id': 'sit_b'}}
    assert _latest_situation_schedule([arrange, other]) is None


async def prepare(monkeypatch):
    monkeypatch.setenv('AMBIENT_RUNTIME', '1')
    db = AsyncMongoMockClient().test
    await db.agent_goals.create_index('id', unique=True)
    await db.agent_runs.create_index('goal_id', unique=True)
    await db.ambient_wakes.create_index('identity', unique=True)
    session = ConversationSession(user_id='v107-local-clock', meta={'ui_mode': 'ai_core', 'ai_core': {}})
    await db.users.insert_one({'id': session.user_id, 'settings': {'timezone': 'Europe/Rome'}})
    state = SituationState(id='sit_v107', user_id=session.user_id, session_id=session.id,
                           summary='Una situazione temporanea da seguire.',
                           attention_intent='Rivalutare quando arriva il momento utile.')
    await SituationRepository(db).insert(state)
    due = (datetime.now(timezone.utc) + timedelta(hours=3)).replace(minute=0, second=0, microsecond=0)
    result = await arrange_followup(db, session.user_id, situation_id=state.id, expected_revision=1,
        check_at=due.isoformat(), purpose='Rivalutare le informazioni disponibili.',
        completion_when='Le evidenze indicano che è il momento utile per intervenire',
        notify_when='Un rischio richiede di intervenire prima')
    assert result['status'] == 'scheduled'
    return db, session, state, result


@pytest.mark.asyncio
async def test_readback_labels_do_not_change_time_or_create_work(monkeypatch):
    db, session, state, before = await prepare(monkeypatch)
    after = await read_followup(db, session.user_id, state.id)
    assert after['situation_id'] == state.id
    assert after['timezone'] == 'Europe/Rome'
    assert after['timezone_authority'] == 'user_confirmed'
    assert after['next_check_at'] == before['next_check_at']
    assert datetime.fromisoformat(after['next_check_at_local']) == datetime.fromisoformat(after['next_check_at'])
    assert await db.ambient_wakes.count_documents({}) == 1
    assert await db.agent_goals.count_documents({}) == 1
    assert (await read_followup(db, 'other-owner', state.id))['next_check_at_local'] is None


@pytest.mark.asyncio
@pytest.mark.parametrize('asks_when', [True, False])
async def test_actual_loop_repairs_formatted_clock_after_read_only_status(monkeypatch, asks_when):
    db, session, state, before = await prepare(monkeypatch)
    actual = before['next_check_time_local']
    wrong = f'{(int(actual[:2]) - 2) % 24:02d}:{actual[3:]}'
    calls = []
    async def decide(system, payload):
        calls.append(str(payload))
        if len(calls) == 1:
            return {'response_mode': 'tool', 'tool_call': {
                'capability': 'get_situation_followup', 'arguments': {'situation_id': state.id}}}
        return {'response_mode': 'answer', 'message_to_user': MOBILE_REPLY.replace('15:00', wrong),
                'situation_update': {'operation': 'none'}}

    result = await run_cognitive_loop(sess=session,
        user_message='A che ora controllerai?' if asks_when else 'Ho steso i panni.',
        db=db, decision_fn=decide)
    assert result.ok and result.tool_calls == 1
    assert '**' not in result.ora_text
    assert f'per le {wrong}' not in result.ora_text
    assert f'alle {wrong}' not in result.ora_text
    assert 'Se vuoi' not in result.ora_text
    assert 'irregolare' not in result.ora_text
    assert 'Ti avviso quando' in result.ora_text
    if asks_when:
        assert actual in result.ora_text
        assert before['next_check_label'] in result.ora_text
    else:
        assert 'prossimo controllo' not in result.ora_text.lower()
    assert any('situation_schedule_time_consistency' in p for p in calls)
    assert (await read_followup(db, session.user_id, state.id))['next_check_at'] == before['next_check_at']
    assert await db.ambient_wakes.count_documents({}) == 1
