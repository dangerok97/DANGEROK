"""Coverage metadata tests. No model/network or user calendar is accessed."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from conversation_engine.ai_core.calendar_ahead import the_next_two_days
from conversation_engine.ai_core.models import Observation
from conversation_engine.ai_core.tools import calendar_caps


@pytest.mark.asyncio
async def test_successful_empty_window_preserves_scope_and_requires_fresh_named_event_read(monkeypatch):
    db = object()
    reader = AsyncMock(return_value=Observation(kind='tool', name='get_calendar_events', status='ok',
        payload={'status': 'ok', 'events': []}))
    monkeypatch.setattr(calendar_caps, 'get_calendar_events', reader)
    result = await the_next_two_days(db, 'calendar-synthetic-owner')
    assert result['status'] == 'observed_empty_window'
    assert result['events'] == [] and result['observed_at']
    assert result['historical_conversation_is_current_evidence'] is False
    assert result['may_be_truncated'] is False
    assert 'call get_calendar_events' in result['this_is_only_the_next_48_hours']
    assert 'HISTORICAL' in result['this_is_only_the_next_48_hours']
    assert datetime.fromisoformat(result['window']['to']) - datetime.fromisoformat(result['window']['from']) == timedelta(hours=48)
    reader.assert_awaited_once()
    assert reader.await_args.args[1] == {'db': db, 'user_id': 'calendar-synthetic-owner'}


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['error', 'failed', 'partial', 'needs_client', 'unavailable'])
async def test_unconfirmed_read_cannot_become_an_empty_calendar(monkeypatch, status):
    monkeypatch.setattr(calendar_caps, 'get_calendar_events', AsyncMock(return_value=Observation(
        kind='tool', name='get_calendar_events', status=status, payload={'status': status, 'events': []})))
    result = await the_next_two_days(object(), 'calendar-synthetic-owner')
    assert result['status'] == 'unavailable'
    assert result['observed_at'] is None
    assert result['historical_conversation_is_current_evidence'] is False
    assert result['events'] == []


@pytest.mark.asyncio
async def test_timeout_retains_unknown_scope_without_disclosing_exception_text(monkeypatch):
    monkeypatch.setattr(calendar_caps, 'get_calendar_events', AsyncMock(side_effect=TimeoutError('private-data-sentinel')))
    result = await the_next_two_days(object(), 'calendar-synthetic-owner')
    assert result['status'] == 'unavailable' and result['observed_at'] is None
    assert 'private-data-sentinel' not in str(result)
    assert result['window']['from'] and result['window']['to']


@pytest.mark.asyncio
@pytest.mark.parametrize('events', [None, {'unexpected': 'shape'}, 'not a list'])
async def test_malformed_event_list_is_unknown_not_empty(monkeypatch, events):
    monkeypatch.setattr(calendar_caps, 'get_calendar_events', AsyncMock(return_value=Observation(
        kind='tool', name='get_calendar_events', status='ok', payload={'status': 'ok', 'events': events})))
    result = await the_next_two_days(object(), 'calendar-synthetic-owner')
    assert result['status'] == 'unavailable' and result['observed_at'] is None


@pytest.mark.asyncio
async def test_recorded_events_keep_exact_refs_and_truncation_boundary(monkeypatch):
    events = [{'calendar_ref': f'calendar:test-{i}', 'title': f'Synthetic {i}',
        'start_datetime': f'2030-01-03T{i % 24:02d}:00:00+01:00', 'timezone': 'Europe/Rome'} for i in range(25)]
    monkeypatch.setattr(calendar_caps, 'get_calendar_events', AsyncMock(return_value=Observation(
        kind='tool', name='get_calendar_events', status='ok', payload={'status': 'ok', 'events': events})))
    result = await the_next_two_days(object(), 'calendar-synthetic-owner')
    assert result['status'] == 'observed_events'
    assert result['events'] == events[:20]
    assert result['may_be_truncated'] is True and result['observed_at']
    assert result['historical_conversation_is_current_evidence'] is False


@pytest.mark.asyncio
async def test_missing_scope_never_calls_reader(monkeypatch):
    reader = AsyncMock()
    monkeypatch.setattr(calendar_caps, 'get_calendar_events', reader)
    assert await the_next_two_days(None, 'calendar-synthetic-owner') is None
    assert await the_next_two_days(object(), '') is None
    reader.assert_not_awaited()
