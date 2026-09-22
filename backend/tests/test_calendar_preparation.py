"""Calendar preparation runs from sync, respects current data and never edits it."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo
import sys
import pytest
# Import domain modules without booting HTTP deps in the isolated regression run.
import importlib.util
from pathlib import Path
from types import ModuleType
if 'proactive_engine' not in sys.modules:
    package = ModuleType('proactive_engine')
    package.__path__ = [str(Path(importlib.util.find_spec('proactive_engine').origin).parent)]
    sys.modules['proactive_engine'] = package
from proactive_engine.generators import calendar
from proactive_engine.service import ProactiveEngineService
AsyncMongoMockClient = pytest.importorskip('mongomock_motor').AsyncMongoMockClient

NOW = datetime(2026, 9, 23, 8, tzinfo=timezone.utc)
def event(id, hour, minute=0, duration=60):
    start = NOW.replace(day=24, hour=hour, minute=minute)
    return {'id': id, 'title': id, 'source': 'life_node', 'starts_at': start.isoformat(), 'ends_at': (start+timedelta(minutes=duration)).isoformat()}

@pytest.fixture
def world(monkeypatch):
    db = AsyncMongoMockClient().test
    events = [event('dentist', 8), event('meeting', 8, 30), event('busy', 9, 30, 90)]
    monkeypatch.setattr(calendar, '_load_events', AsyncMock(side_effect=lambda *a: events))
    return db, events

@pytest.mark.asyncio
async def test_alternatives_preserve_duration_and_avoid_all_other_events(world):
    db, events = world
    candidates = await calendar.generate_calendar_candidates(db, 'alice', now=NOW)
    prep = candidates[0].meta['preparation']
    assert len(prep['options']) == 2
    for option in prep['options']:
        start, end = map(datetime.fromisoformat, (option['starts_at'], option['ends_at']))
        assert end-start == timedelta(hours=1)
        for ev in events:
            if ev['id'] != option['event_id']:
                assert not calendar._overlap(start, end, calendar._parse(ev['starts_at']), calendar._parse(ev['ends_at']))
    assert candidates[0].action.kind == 'prepare_change'
    assert await db.calendar_events.count_documents({}) == 0

@pytest.mark.asyncio
async def test_stale_calendar_has_no_alternatives(world):
    db, events = world
    events[0].update(source='google_calendar', synced_at=(NOW-timedelta(hours=1)).isoformat())
    c = (await calendar.generate_calendar_candidates(db, 'alice', now=NOW))[0]
    assert c.meta['preparation']['options'] == []
    assert 'recent' in c.meta['preparation']['summary']

@pytest.mark.asyncio
async def test_background_refresh_updates_same_card_and_retires_resolved(world, monkeypatch):
    db, events = world
    # Freeze generation time while exercising real persistence, scoring and gate.
    generate = calendar.generate_calendar_candidates
    monkeypatch.setattr(calendar, 'generate_calendar_candidates', lambda db, user, **kw: generate(db, user, now=NOW))
    from proactive_engine.decision_engine import GateResult
    monkeypatch.setattr('proactive_engine.service.would_assistant_speak', lambda *a, **kw: GateResult(True))
    service = ProactiveEngineService(db)
    await service.refresh_calendar('alice')
    first = await db.proactive_suggestions.find_one({'user_id': 'alice'})
    assert first and first['meta']['preparation']['options']
    await service.refresh_calendar('alice')
    assert await db.proactive_suggestions.count_documents({'user_id': 'alice'}) == 1
    events[1].update(event('meeting', 13))
    await service.refresh_calendar('alice')
    assert (await db.proactive_suggestions.find_one({'id': first['id']}))['status'] == 'expired'
    assert await db.proactive_suggestions.count_documents({'user_id': 'bob'}) == 0

@pytest.mark.asyncio
async def test_successful_background_poll_prepares_calendar_without_home(world, monkeypatch):
    from connected import polling
    db, events = world
    source = SimpleNamespace(id='calendar-source', source_type='calendar')
    monkeypatch.setattr(polling, 'due', AsyncMock(return_value=[source]))
    monkeypatch.setattr(polling, 'schedule_next', AsyncMock())
    monkeypatch.setattr(polling, '_owners_with_something_to_understand', AsyncMock(return_value=[]))
    sync = AsyncMock(return_value={'ok': True, 'recorded': 0})
    monkeypatch.setitem(sys.modules, 'connected.service', SimpleNamespace(ConnectedLifeService=lambda db: SimpleNamespace(sync=sync)))
    prepare = AsyncMock()
    monkeypatch.setattr(ProactiveEngineService, 'refresh_calendar', prepare)
    result = await polling.poll_once(db, now=NOW, owners=['alice'])
    assert result['read'] == 1
    prepare.assert_awaited_once_with('alice')


def test_alternatives_never_extend_past_observed_horizon():
    start = NOW + timedelta(days=7)
    event = {'id': 'late', 'title': 'Late'}
    triple = (event, start, start + timedelta(hours=1))
    assert calendar.alternative_slots([triple], triple, triple, now=NOW, tz=ZoneInfo('Europe/Rome')) == []
