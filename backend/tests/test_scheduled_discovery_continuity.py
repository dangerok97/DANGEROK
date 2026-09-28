from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from opportunities.discovery import OpportunityDiscovery
from opportunities.models import ScanResult
from opportunities.service import OpportunityService
from opportunities import snapshot
from ambient.models import AmbientWake
from ambient.service import AmbientService

@pytest.mark.asyncio
async def test_due_review_without_new_changes_reaches_scan_once_per_temporal_state(monkeypatch):
    db=AsyncMongoMockClient().test
    state={'calendar':[{'ref':'calendar:event','starts_at':'2026-09-29T09:00:00+02:00'}],
           'temporal':{'hour_bucket':'2026-09-28T17'}}
    monkeypatch.setattr(snapshot,'build',AsyncMock(side_effect=lambda *a,**kw:state.copy()))
    scan=AsyncMock(return_value=ScanResult(silence=True))
    monkeypatch.setattr(OpportunityService,'scan',scan)
    discovery=OpportunityDiscovery(db)
    assert not (await discovery.review('alice')).ran
    assert (await discovery.review('alice',scheduled=True)).ran
    await db.opportunity_scan_state.update_one({'owner_id':'alice'},{'$set':{'last_scan_at':'2020-01-01T00:00:00+00:00'}})
    assert not (await discovery.review('alice',scheduled=True)).ran
    assert scan.await_count==1
    state['temporal']={'hour_bucket':'2026-09-28T18'}
    await db.opportunity_scan_state.update_one({'owner_id':'alice'},{'$set':{'last_scan_at':'2020-01-01T00:00:00+00:00'}})
    assert (await discovery.review('alice',scheduled=True)).ran
    assert scan.await_count==2

@pytest.mark.asyncio
async def test_cooldown_retains_due_wake_instead_of_losing_it(monkeypatch):
    db=AsyncMongoMockClient().test
    await db.opportunity_scan_state.insert_one({'owner_id':'alice','last_scan_at':datetime.now(timezone.utc).isoformat()})
    scan=AsyncMock()
    monkeypatch.setattr(OpportunityService,'scan',scan)
    wake=AmbientWake(owner_id='alice',reason='opportunity_revisit',opportunity_id='opp')
    outcome=await AmbientService(db).review_life(wake)
    assert outcome.retry_after_seconds==120 and outcome.error=='review_deferred'
    scan.assert_not_awaited()

@pytest.mark.asyncio
async def test_provider_unavailable_keeps_due_review_retryable(monkeypatch):
    db=AsyncMongoMockClient().test
    monkeypatch.setattr(OpportunityService,'scan',AsyncMock(return_value=ScanResult(unavailable=True)))
    wake=AmbientWake(owner_id='alice',reason='ambient_review')
    result=await AmbientService(db).review_life(wake)
    assert result.retry_after_seconds and result.error=='model_unavailable'
    assert await db.opportunity_scan_state.count_documents({'owner_id':'alice'})==0

@pytest.mark.asyncio
async def test_runtime_completes_due_review_with_no_home_or_chat(monkeypatch):
    from ambient.runtime import tick
    from ambient.repository import AmbientRepository
    # mongomock looks up projected _id after find_one_and_update; production does not.
    import mongomock.collection
    original = mongomock.collection.Collection.find_one_and_update
    def update(self, *args, **kwargs):
        kwargs.pop("projection", None)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(mongomock.collection.Collection, "find_one_and_update", update)
    db=AsyncMongoMockClient().test
    scan=AsyncMock(return_value=ScanResult(silence=True))
    monkeypatch.setattr(OpportunityService,'scan',scan)
    wake=AmbientWake(owner_id='alice',reason='ambient_review',scheduled_for=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat())
    monkeypatch.setattr(AmbientService, "_note", AsyncMock())
    await AmbientRepository(db).schedule(wake)
    result=await tick(db,limit=1)
    assert result['completed']==1
    scan.assert_awaited_once()
    assert (await db.ambient_wakes.find_one({'id':wake.id}))['last_error']=='reviewed'
