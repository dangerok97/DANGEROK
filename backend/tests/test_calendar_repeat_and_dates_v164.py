"""Independent mutation-count and calendar-copy checks; all accounts synthetic."""
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from home import manual_event
from conversation_engine.ai_core.tools import calendar_caps
from conversation_engine.ai_core.grounding.calendar_weekday import guard_calendar_weekdays

UID = 'cal164-owner'
OTHER = 'cal164-other-owner'
TITLE = 'Visita fittizia CAL164'
DAY = '2027-01-15'


@pytest_asyncio.fixture
async def world(monkeypatch):
    db = AsyncMongoMockClient().calendar_repeat_v164
    await db.users.insert_one({'id': UID, 'timezone': 'Europe/Rome'})
    wake = AsyncMock()
    monkeypatch.setattr(manual_event, '_wake', wake)
    original = await manual_event.create_manual_event(
        db, UID, title=TITLE, start=DAY+'T10:00:00+01:00',
        end=DAY+'T10:45:00+01:00', tz_name='Europe/Rome', request_id='cal164-own',
    )
    canary = await manual_event.create_manual_event(
        db, OTHER, title='Non toccare', start=DAY+'T10:00:00+01:00',
        end=DAY+'T10:45:00+01:00', tz_name='Europe/Rome', request_id='cal164-other',
    )
    wake.reset_mock()
    # The mock database creates a collection wrapper on each attribute lookup.
    # Bind the exact wrapper first, otherwise the spy watches a discarded one.
    collection = db.life_nodes
    monkeypatch.setattr(db, 'life_nodes', collection)
    writes = AsyncMock(wraps=collection.update_one)
    monkeypatch.setattr(collection, 'update_one', writes)
    return db, original, canary, writes, wake


def move_request(event_id, hour=11):
    spoken = f"Sposta la visita fittizia CAL164 alle {hour}:00 nel calendario ORA."
    args = {'calendar_ref': 'calendar:'+event_id,
            'start_datetime': f'{DAY}T{hour:02d}:00:00+01:00', 'timezone': 'Europe/Rome',
            'user_authority': {'requested_by_user': True, 'user_words': spoken, 'what_they_asked_for': spoken}}
    return args, {'user_id': UID, 'user_message': spoken, 'reasoning_epoch': 'cal164-test-turn'}


@pytest.mark.asyncio
async def test_raw_repeated_update_does_not_write_again(world):
    db, original, canary, writes, wake = world
    fields = {'start_datetime': DAY+'T11:00:00+01:00', 'timezone': 'Europe/Rome'}
    first = await manual_event.update_manual_event(db, UID, original['id'], fields)
    second = await manual_event.update_manual_event(db, UID, original['id'], fields)
    third = await manual_event.update_manual_event(db, UID, original['id'],
        {**fields, 'end_datetime': DAY+'T11:45:00+01:00'})
    fourth = await manual_event.update_manual_event(db, UID, original['id'],
        {**fields, 'end_datetime': DAY+'T11:45:00+01:00'})
    assert writes.await_count == 1, 'An unchanged appointment must not be written repeatedly'
    assert wake.await_count == 1, 'An unchanged appointment must not wake new work'
    assert first['changed_now'] is True
    assert all(row['changed_now'] is False for row in (second, third, fourth))
    assert first['updated_at'] == fourth['updated_at']
    seen = await manual_event.get_manual_event(db, OTHER, canary['id'])
    assert manual_event.manual_event_public(seen) == canary


@pytest.mark.asyncio
async def test_real_capability_reports_no_change_and_does_not_create_new_receipts(world):
    db, original, _, writes, wake = world
    args, runtime = move_request(original['id'])
    runtime['db'] = db
    first = await calendar_caps.update_calendar_event(args, runtime)
    assert first.status == 'ok', first.model_dump()
    assert first.payload['operation'] == 'updated'
    receipts = await db.agent_receipts.count_documents({'owner_id': UID})
    second = await calendar_caps.update_calendar_event(args, runtime)
    equivalent = await calendar_caps.update_calendar_event(
        {**args, 'end_datetime': DAY+'T11:45:00+01:00'}, runtime)
    assert second.status == equivalent.status == 'ok'
    assert second.payload['operation'] == equivalent.payload['operation'] == 'already_updated'
    assert second.payload['changed_now'] is False and second.payload['verified'] is True
    assert writes.await_count == wake.await_count == 1
    assert await db.agent_receipts.count_documents({'owner_id': UID}) == receipts
    assert await db.life_nodes.count_documents({'user_id': UID, 'status': 'active'}) == 1


@pytest.mark.asyncio
async def test_new_move_and_return_to_old_time_are_real_changes(world):
    db, original, _, writes, wake = world
    for hour in (11, 12, 11):
        args, runtime = move_request(original['id'], hour)
        runtime.update(db=db, reasoning_epoch=f'cal164-hour-{hour}')
        result = await calendar_caps.update_calendar_event(args, runtime)
        assert result.status == 'ok', result.model_dump()
        assert result.payload['operation'] == 'updated'
        assert result.payload['changed_now'] is True
    assert writes.await_count == wake.await_count == 3
    row = await manual_event.get_manual_event(db, UID, original['id'])
    assert row['attributes']['starts_at'] == DAY+'T11:00:00+01:00'


@pytest.mark.asyncio
async def test_retry_after_lost_success_is_noop_but_stale_different_change_is_rejected(world):
    db, original, _, writes, wake = world
    fields = {'start_datetime': DAY+'T11:00:00+01:00'}
    await manual_event.update_manual_event(db, UID, original['id'], fields)
    replay = await manual_event.update_manual_event(
        db, UID, original['id'], fields, expected_updated_at=original['updated_at'])
    assert replay['changed_now'] is False
    with pytest.raises(ValueError, match='event_changed'):
        await manual_event.update_manual_event(db, UID, original['id'],
            {'start_datetime': DAY+'T12:00:00+01:00'}, expected_updated_at=original['updated_at'])
    assert writes.await_count == wake.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [('title', 'Titolo corretto'), ('description', 'Nota nuova'), ('location', 'Sala B')])
async def test_material_change_is_not_hidden_by_noop_guard(world, field, value):
    db, original, _, writes, wake = world
    result = await manual_event.update_manual_event(db, UID, original['id'], {field: value})
    again = await manual_event.update_manual_event(db, UID, original['id'], {field: value})
    assert result['changed_now'] is True and again['changed_now'] is False
    assert writes.await_count == wake.await_count == 1


@pytest.mark.asyncio
async def test_real_failed_write_can_be_retried(world):
    db, original, _, writes, wake = world
    writes.side_effect = TimeoutError('synthetic database outage')
    with pytest.raises(TimeoutError):
        await manual_event.update_manual_event(db, UID, original['id'], {'start_datetime': DAY+'T11:00:00+01:00'})
    wake.assert_not_awaited()
    writes.side_effect = None
    result = await manual_event.update_manual_event(db, UID, original['id'], {'start_datetime': DAY+'T11:00:00+01:00'})
    assert result['changed_now'] is True
    assert writes.await_count == 2 and wake.await_count == 1


@pytest.mark.asyncio
async def test_other_owner_and_cancelled_event_cannot_be_updated(world):
    db, original, canary, writes, wake = world
    with pytest.raises(ValueError, match='event_not_found'):
        await manual_event.update_manual_event(db, UID, canary['id'], {'title': 'No'})
    await db.life_nodes.update_one({'id': original['id']}, {'$set': {'status': 'archived'}})
    writes.reset_mock()
    with pytest.raises(ValueError, match='event_cancelled'):
        await manual_event.update_manual_event(db, UID, original['id'], {'start_datetime': DAY+'T10:00:00+01:00'})
    writes.assert_not_awaited()
    wake.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('start,end', [
    ('2027-03-28T02:30:00+01:00', '2027-03-28T04:00:00+02:00'),
    ('2027-01-15T11:00:00+02:00', '2027-01-15T11:45:00+02:00'),
    ('2027-01-15T11:00:00+01:00', '2027-01-15T10:45:00+01:00'),
])
async def test_invalid_time_never_produces_a_write(world, start, end):
    db, original, _, writes, wake = world
    with pytest.raises(ValueError):
        await manual_event.update_manual_event(db, UID, original['id'],
            {'start_datetime': start, 'end_datetime': end, 'timezone': 'Europe/Rome'})
    writes.assert_not_awaited()
    wake.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('start,end', [
    ('2027-03-28T01:30:00+01:00', '2027-03-28T03:15:00+02:00'),
    ('2027-10-31T02:30:00+02:00', '2027-10-31T02:15:00+01:00'),
    ('2027-10-31T02:30:00+01:00', '2027-10-31T03:15:00+01:00'),
])
async def test_explicit_dst_instants_preserve_elapsed_duration(world, start, end):
    db, original, _, writes, wake = world
    result = await manual_event.update_manual_event(db, UID, original['id'],
        {'start_datetime': start, 'timezone': 'Europe/Rome'})
    assert result['starts_at'] == start and result['ends_at'] == end
    assert writes.await_count == wake.await_count == 1


@pytest.mark.asyncio
async def test_overlapping_events_are_read_without_changing_either_or_leaking_other_owner(world):
    db, original, canary, writes, wake = world
    overlap = await manual_event.create_manual_event(db, UID, title='Secondo impegno fittizio',
        start=DAY+'T10:15:00+01:00', end=DAY+'T11:15:00+01:00',
        tz_name='Europe/Rome', request_id='cal164-overlap')
    writes.reset_mock()
    wake.reset_mock()
    result = await calendar_caps.get_calendar_events(
        {'time_min': DAY+'T00:00:00+01:00', 'time_max': DAY+'T23:59:59+01:00'},
        {'db': db, 'user_id': UID})
    assert result.status == 'ok'
    items = result.payload.get('items') or result.payload.get('events') or []
    assert {item['calendar_ref'] for item in items} == {'calendar:'+original['id'], 'calendar:'+overlap['id']}
    assert 'calendar:'+canary['id'] not in {item['calendar_ref'] for item in items}
    writes.assert_not_awaited()
    wake.assert_not_awaited()


EVIDENCE = [{'name': 'get_calendar_events', 'status': 'ok', 'payload': {'status': 'ok', 'events': [
    {'start_datetime': '2026-10-15T10:30:00+02:00', 'timezone': 'Europe/Rome'}]}}]


@pytest.mark.parametrize('text,expected,count', [
    ('mercoledì 15 ottobre 2026 alle 10:30', 'giovedì 15 ottobre 2026 alle 10:30', 1),
    ('Mercoledi 15 ottobre 2026', 'Giovedì 15 ottobre 2026', 1),
    ('**mercoledì 15 ottobre 2026**', '**giovedì 15 ottobre 2026**', 1),
    ('mercoledì **15 ottobre 2026**', 'giovedì **15 ottobre 2026**', 1),
    ('giovedì 15 ottobre 2026', 'giovedì 15 ottobre 2026', 0),
    ('mercoledì 15 ottobre', 'mercoledì 15 ottobre', 0),
    ('mercoledì 16 ottobre 2026', 'mercoledì 16 ottobre 2026', 0),
    ('mercoledì 31 febbraio 2026', 'mercoledì 31 febbraio 2026', 0),
    ('«mercoledì 15 ottobre 2026»', '«mercoledì 15 ottobre 2026»', 0),
    ('`mercoledì 15 ottobre 2026`', '`mercoledì 15 ottobre 2026`', 0),
])
def test_only_supported_explicit_weekday_is_corrected(text, expected, count):
    assert guard_calendar_weekdays(text, EVIDENCE) == (expected, count)


@pytest.mark.parametrize('status', ['failed', 'partial', 'error', 'needs_client'])
def test_failed_calendar_read_cannot_support_a_text_correction(status):
    obs = deepcopy(EVIDENCE)
    obs[0]['status'] = status
    text = 'mercoledì 15 ottobre 2026'
    assert guard_calendar_weekdays(text, obs) == (text, 0)


def test_fresh_prefetch_and_timezone_date_are_supported_but_unrelated_tool_is_not():
    text = 'giovedì 16 ottobre 2026'
    ahead = {'events': [{'start_datetime': '2026-10-15T22:30:00Z', 'timezone': 'Europe/Rome'}]}
    assert guard_calendar_weekdays(text, [], ahead) == ('venerdì 16 ottobre 2026', 1)
    obs = deepcopy(EVIDENCE)
    obs[0]['name'] = 'web_search'
    assert guard_calendar_weekdays('mercoledì 15 ottobre 2026', obs)[1] == 0


@pytest.mark.asyncio
async def test_core_final_answer_and_saved_history_use_the_same_correct_weekday(monkeypatch):
    from conversation_engine.ai_core import loop, calendar_ahead, state
    from conversation_engine.models import ConversationSession
    db = AsyncMongoMockClient().cal164_copy_core
    await db.users.insert_one({'id': UID, 'timezone': 'Europe/Rome'})
    monkeypatch.setattr(calendar_ahead, 'the_next_two_days', AsyncMock(return_value={
        'events': EVIDENCE[0]['payload']['events']}))
    async def choose(*args, **kwargs):
        return {'response_mode': 'answer', 'reasoning_status': 'enough_information',
                'message_to_user': 'La visita è mercoledì 15 ottobre 2026 alle 10:30.'}
    session = ConversationSession(user_id=UID)
    result = await loop.run_cognitive_loop(sess=session, db=db,
        user_message='Qual è la data della visita?', decision_fn=choose)
    assert result.ora_text == 'La visita è giovedì 15 ottobre 2026 alle 10:30.'
    assert state.get_ai_state(session)['recent_turns'][-1]['text'] == result.ora_text
    assert result.tool_calls == 0
