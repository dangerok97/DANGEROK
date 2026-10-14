"""Atomic source-work records; all data is fabricated and isolated."""
import asyncio
from datetime import timedelta
import os
import uuid

import pytest
from mongomock_motor import AsyncMongoMockClient
from motor.motor_asyncio import AsyncIOMotorClient
from connected.core_work import SourceCoreWorker
from connected.signals import SignalService
from test_source_integrity_v168 import StableMockDatabase, observation, OWNER


@pytest.mark.asyncio
async def test_mock_atomic_claim_returns_the_row_it_actually_claimed():
    db = StableMockDatabase(AsyncMongoMockClient().claim_snapshot_synthetic)
    signal, _ = await SignalService(db).record(observation())
    before = await db.connected_signals.find_one({'id': signal.id}, {'_id': 0})
    claim = await SourceCoreWorker(db).claim(OWNER, signal.id)
    after = await db.connected_signals.find_one({'id': signal.id}, {'_id': 0})
    assert claim is not None, {'before': before, 'after': after}
    assert after['_core_work']['token'] == claim.token
    assert after['_core_work']['attempts'] == 1
    assert await SourceCoreWorker(db).claim(OWNER, signal.id) is None


@pytest.mark.asyncio
async def test_real_mongo_concurrent_source_claims_return_one_owner():
    if os.environ.get('ORA_SOURCE_REAL_DB_TEST') != '1':
        pytest.skip('Real database execution requires isolated CI opt-in')
    assert os.environ.get('CI') == 'true'
    assert os.environ['MONGO_URL'] == 'mongodb://127.0.0.1:27017'
    name = 'ora_source_v169_claim_' + uuid.uuid4().hex
    clients = [AsyncIOMotorClient(os.environ['MONGO_URL'], serverSelectionTimeoutMS=5000) for _ in range(8)]
    try:
        db = clients[0][name]
        signal, _ = await SignalService(db).record(observation())
        results = await asyncio.gather(*(SourceCoreWorker(c[name]).claim(OWNER, signal.id) for c in clients))
        assert sum(r is not None for r in results) == 1
        claim = next(r for r in results if r is not None)
        actual = await db.connected_signals.find_one({'id': signal.id}, {'_id': 0})
        assert actual['_core_work']['attempts'] == 1
        assert actual['_core_work']['token'] == claim.token
        await claim.current()
    finally:
        assert name.startswith('ora_source_v169_claim_')
        await clients[0].drop_database(name)
        for client in clients:
            client.close()
