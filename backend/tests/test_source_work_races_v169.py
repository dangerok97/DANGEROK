"""Race-boundary checks around the shared Core, not source-specific rules."""
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from connected import core_work
from connected.core_work import SourceCoreWorker, _LeasedActivation
from conversation_engine.ai_core.tools.registry import ToolRegistry
from delivery.service import DeliveryService
from test_general_source_core_v166 import world, OWNER, action
from test_source_integrity_v168 import StableMockDatabase
from test_durable_source_work_v169 import grant, decisions


@pytest.mark.asyncio
async def test_old_worker_losing_lease_does_not_hide_new_workers_valid_home(world, monkeypatch):
    raw, signal, _ = world
    db = StableMockDatabase(raw)
    await grant(db)
    original = DeliveryService.note_activity
    reports, calls = [], []
    async def takeover(self, *args, **kwargs):
        calls.append(kwargs['activity_id'])
        result = await original(self, *args, **kwargs)
        if len(calls) == 1:
            now = core_work._now() + timedelta(seconds=core_work.LEASE_SECONDS + 1)
            monkeypatch.setattr(core_work, '_now', lambda: now)
            no_model = AsyncMock(side_effect=AssertionError('Receipt handoff needs no new AI'))
            reports.append(await SourceCoreWorker(db).process_one(OWNER, signal.id, decision_fn=no_model))
            no_model.assert_not_awaited()
        return result
    monkeypatch.setattr(DeliveryService, 'note_activity', takeover)
    decide, _ = decisions(signal)
    old_result = await SourceCoreWorker(db).process_one(OWNER, signal.id, decision_fn=decide)
    assert old_result['state'] == 'lease_lost'
    assert reports[0]['state'] == 'completed'
    assert len(set(calls)) == 1
    assert await db.ambient_activity.count_documents({'owner_id': OWNER, 'visibility': 'ambient'}) == 1
    row = await db.connected_signals.find_one({'id': signal.id})
    assert row['_core_work']['phase'] == 'completed' and row['status'] == 'interpreted'


@pytest.mark.asyncio
async def test_event_cancelled_during_handoff_is_not_left_visible(world, monkeypatch):
    raw, signal, _ = world
    db = StableMockDatabase(raw)
    await grant(db)
    original = DeliveryService.note_activity
    async def changed(self, *args, **kwargs):
        result = await original(self, *args, **kwargs)
        await db.life_nodes.update_one({'user_id': OWNER, 'type': 'event'}, {'$set': {'status': 'archived'}})
        return result
    monkeypatch.setattr(DeliveryService, 'note_activity', changed)
    decide, _ = decisions(signal)
    out = await SourceCoreWorker(db).process_one(OWNER, signal.id, decision_fn=decide)
    assert out['state'] == 'stale_result' and not out['home_visible']
    assert await db.ambient_activity.count_documents({'visibility': 'ambient'}) == 0


@pytest.mark.asyncio
async def test_one_effect_budget_reuses_receipt_and_never_grants_a_second_effect(world):
    raw, signal, _ = world
    db = StableMockDatabase(raw)
    await grant(db)
    work = await SourceCoreWorker(db).claim(OWNER, signal.id)
    activation = await _LeasedActivation.load(db, OWNER, signal.id)
    activation.work = work
    tools = activation.restrict_registry(ToolRegistry(db))
    runtime = {'db': db, 'user_id': OWNER, 'user_message': ''}
    unread = await tools.execute('create_calendar_event', action(), runtime=runtime)
    assert unread.status != 'ok'
    assert '_core_work' in await db.connected_signals.find_one({'id': signal.id})
    assert 'effect' not in (await work.current())['_core_work']
    await tools.execute('read_connected_source', {'source_ref': 'signal:'+signal.id}, runtime=runtime)
    created = await tools.execute('create_calendar_event', action(), runtime=runtime)
    repeated = await tools.execute('create_calendar_event', action(), runtime=runtime)
    assert created.status == repeated.status == 'ok'
    assert created.provenance == repeated.provenance
    denied = await tools.execute('create_calendar_event', action(title='Different unbudgeted event'), runtime=runtime)
    assert denied.status != 'ok'
    assert await db.life_nodes.count_documents({'user_id': OWNER, 'type': 'event'}) == 1
    assert await db.autonomy_consents.count_documents({'source': 'explicit_user_command'}) == 0
