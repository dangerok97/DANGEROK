from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from home.manual_event import create_manual_event, archive_manual_event
from opportunities import snapshot
from opportunities.changes import fingerprint
from agent.capabilities import CapabilityResolver
from agent.providers import read_local_calendar

NOW = datetime(2026, 9, 28, 14, 0, tzinfo=timezone.utc)

async def event(db, owner='alice', key='one', start='2026-09-29T09:00:00+02:00'):
    return await create_manual_event(db, owner, title='Appuntamento di prova', start=start,
        end='2026-09-29T11:00:00+02:00', tz_name='Europe/Rome', request_id=key,
        location='Studio sintetico', description='Portare il modulo di prova')

@pytest.mark.asyncio
async def test_home_event_reaches_background_evidence_with_preparation_and_duration():
    db = AsyncMongoMockClient().test
    e = await event(db)
    rows = await snapshot._calendar(db, 'alice', NOW)
    assert len(rows) == 1
    assert rows[0]['ref'] == 'calendar:' + e['id']
    assert rows[0]['ends_at'] == e['ends_at']
    assert rows[0]['location'] == 'Studio sintetico'
    assert rows[0]['preparation_notes'] == 'Portare il modulo di prova'
    assert snapshot.evidence_refs({'calendar': rows})[rows[0]['ref']] == 'calendar_event'
    assert await db.ambient_wakes.count_documents({'owner_id': 'alice', 'status': 'pending'}) == 1
    assert await snapshot._calendar(db, 'bob', NOW) == []
    before = fingerprint({'calendar': rows})
    await archive_manual_event(db, 'alice', e['id'])
    after = await snapshot._calendar(db, 'alice', NOW)
    assert after == [] and fingerprint({'calendar': after}) != before

@pytest.mark.asyncio
async def test_instants_sort_correctly_across_offsets():
    db = AsyncMongoMockClient().test
    await event(db, key='early', start='2026-09-29T09:00:00+02:00')
    await event(db, key='late', start='2026-09-29T08:30:00+00:00')
    rows = await snapshot._calendar(db, 'alice', NOW)
    assert rows[0]['starts_at'].endswith('+02:00')

@pytest.mark.asyncio
async def test_latest_provider_cancellation_and_moved_revision_hide_old_event():
    db = AsyncMongoMockClient().test
    for ref,latest in [('cancelled', {'status': 'cancelled'}), ('moved', {'starts_at':'2026-12-01T09:00:00+02:00'})]:
        payload={'title':'Provider event','starts_at':'2026-09-29T09:00:00+02:00'}
        for stamp,data in [('2026-09-27',payload),('2026-09-28',{**payload,**latest})]:
            await db.ingestion_events.insert_one({'user_id':'alice','source_record_type':'calendar_event',
                'external_id':ref,'ingested_at':stamp,'normalized_payload':data})
    assert await snapshot._calendar(db, 'alice', NOW) == []

@pytest.mark.asyncio
async def test_local_read_is_real_and_does_not_grant_google_access(monkeypatch):
    db = AsyncMongoMockClient().test
    await event(db)
    monkeypatch.setattr('agent.providers._now', lambda: NOW)
    allowed = await CapabilityResolver(db).resolve('alice','calendar.local.read')
    assert allowed.permitted and allowed.is_real
    from permissions.service import PermissionService
    monkeypatch.setattr(PermissionService,'check_access',AsyncMock(return_value=False))
    assert not (await CapabilityResolver(db).resolve('alice','calendar.read')).permitted
    result = await read_local_calendar(db,'alice',None)
    assert result.status == 'succeeded' and len(result.claims)==1
    assert 'Portare il modulo' in result.claims[0].text and '11:00' in result.claims[0].text
    assert (await read_local_calendar(db,'bob',None)).claims == []

@pytest.mark.asyncio
async def test_snapshot_uses_local_day_at_midnight(monkeypatch):
    db = AsyncMongoMockClient().test
    monkeypatch.setattr(snapshot,'_now',lambda:datetime(2026,9,28,22,30,tzinfo=timezone.utc))
    state=await snapshot.build(db,'alice')
    assert state['now']=='2026-09-29T00:30:00+02:00'
    assert state['local_weekday']=='tuesday'
    assert snapshot._days_from_now('2026-09-28T23:00:00+00:00',datetime.fromisoformat(state['now']))==0
