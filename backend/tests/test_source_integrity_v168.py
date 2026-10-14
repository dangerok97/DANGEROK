"""Source storage invariants, not rules for deciding what a message means.

All accounts and observations are synthetic; no LLM, mailbox or delivery call.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient
from pymongo.errors import AutoReconnect, DuplicateKeyError, OperationFailure

from connected.models import ConnectedSignal, ConnectedSource, FieldChange
from connected.signals import SignalService

OWNER = 'source-integrity-synthetic-owner'
OTHER = 'source-integrity-synthetic-other'
PRIVATE = 'PRIVATE_DO_NOT_PERSIST_OR_LOG'


def observation(*, source='source-A', owner=OWNER, value='first', kind='email', ref='shared-provider-id'):
    return ConnectedSignal(owner_id=owner, source_id=source, source_type=kind,
        signal_type='email.thread.updated' if kind == 'email' else 'calendar.event.changed',
        source_object_ref=ref, after=value,
        changed_fields=[FieldChange(field='subject' if kind == 'email' else 'title', after=value)])


async def database():
    db = AsyncMongoMockClient().source_integrity_v168
    service = SignalService(db)
    await service.ensure_indexes()
    return db, service


@pytest.mark.asyncio
async def test_equal_external_ids_from_distinct_connections_are_not_duplicates():
    db, service = await database()
    a, b = observation(), observation(source='source-B')
    kept_a, _ = await service.record(a)
    kept_b, outcome = await service.record(b)
    assert kept_a and kept_b and outcome == 'recorded'
    assert kept_a.fingerprint != kept_b.fingerprint
    assert len(await service.pending(OWNER)) == 2
    for item in (a, b):
        replay = item.model_copy(update={'id': item.id + '_replay'})
        assert await service.record(replay) == (None, 'duplicate')
    assert await db.connected_signals.count_documents({}) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('other_source,other_type', [('source-B', 'email'), ('source-A', 'calendar')])
async def test_supersession_cannot_cross_a_connection_or_source_type(other_source, other_type):
    db, service = await database()
    a = observation(value='before')
    b = observation(source=other_source, kind=other_type, value='after')
    await service.record(a)
    await service.record(b)
    assert (await service.get(OWNER, a.id)).status == 'pending'
    assert len(await service.pending(OWNER)) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [AutoReconnect(PRIVATE), OperationFailure(PRIVATE)])
async def test_failed_insert_is_not_a_duplicate_and_does_not_remove_previous_work(monkeypatch, error):
    db, service = await database()
    a, b = observation(value='before'), observation(value='after')
    await service.record(a)
    monkeypatch.setattr(db.connected_signals, 'insert_one', AsyncMock(side_effect=error))
    with pytest.raises(type(error)):
        await service.record(b)
    assert (await service.get(OWNER, a.id)).status == 'pending'
    assert await db.connected_signals.count_documents({'id': b.id}) == 0


@pytest.mark.asyncio
async def test_nonmatching_unique_key_failure_is_not_reported_as_a_known_duplicate(monkeypatch):
    db, service = await database()
    monkeypatch.setattr(db.connected_signals, 'insert_one', AsyncMock(side_effect=DuplicateKeyError(PRIVATE)))
    with pytest.raises(DuplicateKeyError):
        await service.record(observation())
    assert await db.connected_signals.count_documents({}) == 0


@pytest.mark.asyncio
async def test_uncertain_insert_ack_can_be_retried_without_duplicate_or_lost_predecessor(monkeypatch):
    db, service = await database()
    a, b = observation(value='before'), observation(value='after')
    await service.record(a)
    original = db.connected_signals.insert_one
    async def persisted_but_ack_lost(doc, **kwargs):
        await original(doc, **kwargs)
        raise AutoReconnect('synthetic acknowledgement lost')
    monkeypatch.setattr(db.connected_signals, 'insert_one', persisted_but_ack_lost)
    with pytest.raises(AutoReconnect):
        await service.record(b)
    assert (await service.get(OWNER, a.id)).status == 'pending'
    assert await db.connected_signals.count_documents({}) == 2
    assert [x.id for x in await service.pending(OWNER)] == [a.id]
    assert await service.get(OWNER, b.id) is None
    monkeypatch.setattr(db.connected_signals, 'insert_one', original)
    assert await service.record(b) == (None, 'duplicate')
    assert [x.id for x in await service.pending(OWNER)] == [b.id]
    assert (await service.get(OWNER, a.id)).status == 'superseded'
    assert await db.connected_signals.count_documents({}) == 2


@pytest.mark.asyncio
async def test_cleanup_failure_is_repairable_on_duplicate_without_reinserting(monkeypatch):
    db, service = await database()
    a, b = observation(value='before'), observation(value='after')
    await service.record(a)
    original = db.connected_signals.update_one
    monkeypatch.setattr(db.connected_signals, 'update_one', AsyncMock(side_effect=AutoReconnect('synthetic cleanup outage')))
    with pytest.raises(AutoReconnect):
        await service.record(b)
    assert await db.connected_signals.count_documents({}) == 2
    assert (await service.get(OWNER, a.id)).status == 'pending'
    assert [x.id for x in await service.pending(OWNER)] == [a.id]
    monkeypatch.setattr(db.connected_signals, 'update_one', original)
    assert await service.record(b) == (None, 'duplicate')
    ready = await service.pending(OWNER)
    assert len(ready) == 1 and ready[0].id == b.id and ready[0].supersedes == a.id


@pytest.mark.asyncio
async def test_predecessor_settled_during_insert_is_not_overwritten(monkeypatch):
    db, service = await database()
    a, b = observation(value='before'), observation(value='after')
    await service.record(a)
    original = db.connected_signals.insert_one
    async def finish_previous_then_insert(doc, **kwargs):
        await service.settle(OWNER, a.id, outcome='already_reviewed')
        return await original(doc, **kwargs)
    monkeypatch.setattr(db.connected_signals, 'insert_one', finish_previous_then_insert)
    await service.record(b)
    previous = await service.get(OWNER, a.id)
    assert previous.status == 'interpreted' and previous.outcome == 'already_reviewed'


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['superseded', 'skipped', 'interpreted'])
@pytest.mark.parametrize('operation', ['settle', 'skip'])
async def test_late_workers_cannot_rewrite_terminal_source_state(status, operation):
    db, service = await database()
    a = observation()
    await service.record(a)
    await db.connected_signals.update_one({'id': a.id}, {'$set': {'status': status, 'outcome': 'original'}})
    if operation == 'settle':
        await service.settle(OWNER, a.id, outcome='late_completion')
    else:
        await service.skip(OWNER, a.id, why='late_noise')
    seen = await service.get(OWNER, a.id)
    assert seen.status == status and seen.outcome == 'original'


@pytest.mark.asyncio
@pytest.mark.parametrize('operation,status', [('settle', 'interpreted'), ('skip', 'skipped')])
async def test_pending_work_can_still_finish_and_other_owner_cannot_finish_it(operation, status):
    db, service = await database()
    a = observation()
    await service.record(a)
    if operation == 'settle':
        await service.settle(OTHER, a.id, outcome='foreign')
        assert (await service.get(OWNER, a.id)).status == 'pending'
        await service.settle(OWNER, a.id, outcome='completed')
    else:
        await service.skip(OTHER, a.id, why='foreign')
        assert (await service.get(OWNER, a.id)).status == 'pending'
        await service.skip(OWNER, a.id, why='completed')
    assert (await service.get(OWNER, a.id)).status == status


@pytest.mark.asyncio
async def test_old_fingerprint_replay_keeps_old_id_and_does_not_reopen_work():
    db, service = await database()
    legacy = observation()
    doc = legacy.model_dump()
    doc.update(fingerprint=legacy.compute_fingerprint(), status='interpreted', outcome='already_seen')
    await db.connected_signals.insert_one(doc)
    replay = observation()
    assert await service.record(replay) == (None, 'duplicate')
    assert await db.connected_signals.count_documents({}) == 1
    assert (await service.get(OWNER, legacy.id)).status == 'interpreted'
    assert not await service.pending(OWNER)


@pytest.mark.asyncio
async def test_old_fingerprint_on_other_connection_does_not_hide_a_new_source():
    db, service = await database()
    legacy = observation()
    doc = legacy.model_dump(); doc['fingerprint'] = legacy.compute_fingerprint()
    await db.connected_signals.insert_one(doc)
    assert (await service.record(observation(source='source-B')))[0] is not None
    assert len(await service.pending(OWNER)) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('indexes', [True, False])
async def test_parallel_identical_observations_are_kept_once_even_without_optional_index(indexes):
    db = AsyncMongoMockClient().source_integrity_concurrency
    service = SignalService(db)
    if indexes:
        await service.ensure_indexes()
    results = await asyncio.gather(*(service.record(observation()) for _ in range(8)))
    assert sum(kept is not None for kept, _ in results) == 1
    assert await db.connected_signals.count_documents({}) == 1
    assert len(await service.pending(OWNER)) == 1


@pytest.mark.asyncio
async def test_sync_failure_cannot_advance_watermark_and_retry_keeps_all_observations(monkeypatch):
    from connected.service import ConnectedLifeService
    from connected import email_sensor
    db, signals = await database()
    service = ConnectedLifeService(db)
    source = ConnectedSource(id='source-A', owner_id=OWNER, source_type='email',
        status='connected', read_capabilities=['mail.read'])
    monkeypatch.setattr(service.sources, 'get', AsyncMock(return_value=source))
    monkeypatch.setattr(service.sources, 'note_attempt', AsyncMock())
    success = AsyncMock(); monkeypatch.setattr(service.sources, 'note_success', success)
    monkeypatch.setattr(service, '_sync_mail', AsyncMock())
    earlier = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    await db.connected_source_attempts.insert_one({'owner_id': OWNER, 'source_id': source.id, 'watermark': earlier})
    a, b = observation(ref='id-a'), observation(ref='id-b')
    monkeypatch.setattr(email_sensor, 'read_changes', AsyncMock(return_value=[a, b]))
    original = db.connected_signals.insert_one
    count = 0
    async def fail_second(doc, **kwargs):
        nonlocal count
        count += 1
        if count == 2: raise AutoReconnect('synthetic second insert failure')
        return await original(doc, **kwargs)
    monkeypatch.setattr(db.connected_signals, 'insert_one', fail_second)
    with pytest.raises(AutoReconnect):
        await service.sync(OWNER, source.id)
    success.assert_not_awaited()
    assert await service._watermark(OWNER, source.id) == earlier
    monkeypatch.setattr(db.connected_signals, 'insert_one', original)
    recovered = await service.sync(OWNER, source.id)
    assert recovered['ok'] and recovered['recorded'] == 1 and recovered['deduped'] == 1
    assert len(await signals.pending(OWNER)) == 2
    assert await service._watermark(OWNER, source.id) == max(a.observed_at, b.observed_at)
