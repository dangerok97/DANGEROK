"""Explicitly opt-in real Mongo/process checks, using only ephemeral CI data.

The child is terminated after Mongo acknowledged an insert and before the
replacement transition. Recovery runs in a DIFFERENT interpreter. This proves
source storage recovery only, not LLM decisions, calendar effects or push delivery.
"""
from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
import sys
import uuid

import pytest
import pytest_asyncio

from connected.signals import SignalService
from test_source_integrity_v168 import StableMockDatabase, observation, OWNER

URI = 'mongodb://127.0.0.1:27017'
PREFIX = 'ora_source_v168_process_'


@pytest_asyncio.fixture
async def mongo():
    if os.environ.get('ORA_SOURCE_REAL_DB_TEST') != '1':
        pytest.skip('Real database test requires explicit isolated-CI opt-in')
    assert os.environ.get('MONGO_URL') == URI
    assert os.environ.get('CI') == 'true'
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=5000)
    name = PREFIX + uuid.uuid4().hex
    try:
        await client.admin.command('ping')
        yield client, name, StableMockDatabase(client[name])
    finally:
        assert name.startswith(PREFIX) and name != os.environ.get('DB_NAME')
        await client.drop_database(name)
        client.close()


@pytest.mark.asyncio
async def test_real_mongo_eight_clients_insert_one_observation_without_secondary_index(mongo, monkeypatch):
    from motor.motor_asyncio import AsyncIOMotorClient
    client, name, db = mongo
    clients, arrivals, gate = [], 0, asyncio.Event()
    async def writer():
        nonlocal arrivals
        connection = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=5000)
        clients.append(connection)
        view = StableMockDatabase(connection[name])
        original = view.connected_signals.find_one
        first = True
        async def synchronize_initial_absence(query, *args, **kwargs):
            nonlocal first, arrivals
            row = await original(query, *args, **kwargs)
            if first and 'fingerprint' in query:
                first = False
                arrivals += 1
                if arrivals == 8:
                    gate.set()
                await gate.wait()
            return row
        monkeypatch.setattr(view.connected_signals, 'find_one', synchronize_initial_absence)
        return await SignalService(view).record(observation())
    try:
        rows = await asyncio.wait_for(asyncio.gather(*(writer() for _ in range(8))), 20)
        assert arrivals == 8 and sum(row is not None for row, _ in rows) == 1
        assert await db.connected_signals.count_documents({}) == 1
        indexes = await db.connected_signals.index_information()
        assert set(indexes) == {'_id_'}
        assert len(await SignalService(db).pending(OWNER)) == 1
    finally:
        for connection in clients:
            connection.close()


CHILD = r'''
import asyncio, json, os, sys
from motor.motor_asyncio import AsyncIOMotorClient
from connected.models import ConnectedSignal
from connected.signals import SignalService
from test_source_integrity_v168 import StableMockDatabase

async def run():
    mode, name, encoded = sys.argv[1:]
    assert os.environ.get('CI') == 'true'
    assert os.environ['MONGO_URL'] == 'mongodb://127.0.0.1:27017'
    assert name.startswith('ora_source_v168_process_')
    client = AsyncIOMotorClient(os.environ['MONGO_URL'], serverSelectionTimeoutMS=5000)
    db = StableMockDatabase(client[name])
    if mode == 'crash_after_insert':
        original = db.connected_signals.insert_one
        async def persist_then_exit(document, **kwargs):
            await original(document, **kwargs)
            os._exit(42)
        db.connected_signals.insert_one = persist_then_exit
    try:
        saved, result = await SignalService(db).record(ConnectedSignal.model_validate_json(encoded))
        print(json.dumps({'recorded': saved is not None, 'outcome': result}), flush=True)
    finally:
        client.close()
asyncio.run(run())
'''


async def child(mode, dbname, signal):
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env['PYTHONPATH'] = str(root) + os.pathsep + str(root / 'tests')
    process = await asyncio.create_subprocess_exec(
        sys.executable, '-c', CHILD, mode, dbname, signal.model_dump_json(),
        cwd=root, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), 20)
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        raise
    return process.returncode, stdout.decode(), stderr.decode()


@pytest.mark.asyncio
async def test_new_process_recovers_replacement_after_actual_interpreter_exit(mongo):
    _, name, db = mongo
    service = SignalService(db)
    await service.ensure_indexes()
    old, new = observation(value='old'), observation(value='new')
    await service.record(old)
    code, _, error = await child('crash_after_insert', name, new)
    assert code == 42, error
    assert await db.connected_signals.count_documents({}) == 2
    assert (await service.get(OWNER, old.id)).status == 'pending'
    assert await service.get(OWNER, new.id) is None
    assert [row.id for row in await service.pending(OWNER)] == [old.id]
    replay = new.model_copy(update={'id': 'synthetic-restarted-caller'})
    code, output, error = await child('recover', name, replay)
    assert code == 0, error
    assert json.loads(output) == {'recorded': False, 'outcome': 'duplicate'}
    assert await db.connected_signals.count_documents({}) == 2
    assert (await service.get(OWNER, old.id)).status == 'superseded'
    assert [row.id for row in await service.pending(OWNER)] == [new.id]
    assert (await service.get(OWNER, new.id)).supersedes == old.id


@pytest.mark.asyncio
async def test_real_store_keeps_connections_separate_and_fences_late_completion(mongo):
    _, _, db = mongo
    service = SignalService(db)
    await service.ensure_indexes()
    first = observation(source='A', value='old')
    other_connection = observation(source='B', value='old')
    await service.record(first)
    await service.record(other_connection)
    replacement = observation(source='A', value='new')
    await service.record(replacement)
    await service.settle(OWNER, first.id, outcome='late worker completion')
    assert (await service.get(OWNER, first.id)).status == 'superseded'
    assert (await service.get(OWNER, other_connection.id)).status == 'pending'
    assert set(row.id for row in await service.pending(OWNER)) == {other_connection.id, replacement.id}
