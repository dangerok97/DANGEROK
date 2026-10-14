"""Actual Mongo + exited Python workers, but synthetic notification provider.

A provider-call row is a test boundary observation, NOT a real device receipt.
No real user, mail service, Expo, Meta or model is accessed. Only explicitly
opted-in localhost CI databases with a new per-test name may be used/cleaned.
"""
from __future__ import annotations

from datetime import timedelta
import asyncio
import json
import os
from pathlib import Path
import sys
import uuid

import pytest
import pytest_asyncio

from delivery import source_results as sources
from test_source_result_delivery_v170 import completed, OWNER
from test_general_source_core_v166 import world

URI = 'mongodb://127.0.0.1:27017'
PREFIX = 'ora_result_v170_process_'


@pytest_asyncio.fixture
async def real_completed(completed):
    if os.environ.get('ORA_SOURCE_REAL_DB_TEST') != '1':
        pytest.skip('requires explicit isolated-CI database opt-in')
    assert os.environ.get('CI') == 'true'
    assert os.environ.get('MONGO_URL') == URI
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=5000)
    name = PREFIX + uuid.uuid4().hex
    source_db, signal, activity, *_ = completed
    try:
        await client.admin.command('ping')
        db = client[name]
        # The fixture was produced by the actual source/Core/event/Home code.
        # All of its documents belong to synthetic owners; no personal DB copy.
        for collection in await source_db._db.list_collection_names():
            rows = await source_db[collection].find({}).to_list(200)
            if rows:
                await db[collection].insert_many(rows)
        from delivery.repository import DeliveryRepository
        from ambient.repository import AmbientRepository
        await DeliveryRepository(db).ensure_indexes()
        await AmbientRepository(db).ensure_indexes()
        yield db, name, signal.id, activity
    finally:
        assert name.startswith(PREFIX) and name != os.environ.get('DB_NAME')
        await client.drop_database(name)
        client.close()


CHILD = r'''
import asyncio, json, os, sys
from unittest.mock import AsyncMock, patch
from motor.motor_asyncio import AsyncIOMotorClient
from delivery import source_results, source_result_review, reasoning, context, provider
from delivery.repository import DeliveryRepository
from test_source_result_delivery_v170 import answer, OWNER

async def run():
    mode, name = sys.argv[1:]
    assert os.environ.get('CI') == 'true'
    assert os.environ['MONGO_URL'] == 'mongodb://127.0.0.1:27017'
    assert name.startswith('ora_result_v170_process_')
    assert os.environ['ORA_SOURCE_CORE_PILOT_OWNERS'] == OWNER
    assert os.environ['ORA_SOURCE_RESULT_DELIVERY_OWNERS'] == OWNER
    client = AsyncIOMotorClient(os.environ['MONGO_URL'], serverSelectionTimeoutMS=5000)
    db = client[name]
    async def choose(*args, **kwargs):
        if mode == 'recover_no_model':
            raise AssertionError('Completed/in-flight notification must not rerun judgement')
        await db.synthetic_model_calls.insert_one({'owner_id': OWNER, 'mode': mode})
        return answer()
    class Channel:
        name = 'synthetic-durable-provider'
        async def send(self, **kwargs):
            assert kwargs['owner_id'] == OWNER
            await db.synthetic_provider_calls.insert_one({'owner_id': OWNER,
                'plan_id': kwargs['plan_id'], 'device_delivery_verified': False})
            if mode == 'after_provider':
                os._exit(42)
            return {'ok': True, 'provider': self.name}
        async def cancel(self, **kwargs):
            return {'ok': True}
    original_decision = source_results.save_decision
    async def save_decision(*args, **kwargs):
        plan = await original_decision(*args, **kwargs)
        if mode == 'after_plan':
            os._exit(41)
        return plan
    original_save = DeliveryRepository.save_plan
    async def save_status(repository, plan):
        await original_save(repository, plan)
        if mode == 'after_delivery_status' and plan.status == 'delivered':
            os._exit(43)
    try:
        with patch.object(reasoning, 'decide_delivery', choose), \
             patch.object(context, '_permission', AsyncMock(return_value={'push': True})), \
             patch.object(provider, 'get_provider', lambda: Channel()), \
             patch.object(source_results, 'save_decision', save_decision), \
             patch.object(DeliveryRepository, 'save_plan', save_status):
            handled = await source_result_review.drain(db)
        print(json.dumps({'handled': handled}), flush=True)
    finally:
        client.close()
asyncio.run(run())
'''


async def child(mode, name):
    root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ)
    environment['PYTHONPATH'] = str(root) + os.pathsep + str(root/'tests')
    process = await asyncio.create_subprocess_exec(sys.executable, '-c', CHILD, mode, name,
        cwd=root, env=environment, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), 25)
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        raise
    return process.returncode, stdout.decode(), stderr.decode()


@pytest.mark.asyncio
@pytest.mark.parametrize('stage,exit_code,model_calls', [
    ('after_plan', 41, 2), ('after_provider', 42, 1), ('after_delivery_status', 43, 1),
])
async def test_another_process_recovers_without_repeating_uncertain_send(real_completed, stage, exit_code, model_calls):
    db, name, signal_id, activity = real_completed
    code, _, error = await child(stage, name)
    assert code == exit_code, error
    plan = await sources.existing_plan(db, OWNER, activity)
    assert plan is not None
    before = await db.synthetic_provider_calls.count_documents({})
    assert before == (0 if stage == 'after_plan' else 1)
    if stage == 'after_provider':
        assert plan['status'] == 'pending' and plan['_source_dispatch']['state'] == 'started'
    # Only this dead test worker's lease is expired, in this new test database.
    await db.connected_signals.update_one({'id': signal_id, 'owner_id': OWNER},
        {'$set': {'_core_work.delivery_review.lease_until': (sources.now()-timedelta(seconds=1)).isoformat()}})
    recovery = 'recover' if stage == 'after_plan' else 'recover_no_model'
    code, output, error = await child(recovery, name)
    assert code == 0, error
    assert json.loads(output) == {'handled': 1}
    assert await db.synthetic_provider_calls.count_documents({}) == 1
    assert await db.synthetic_model_calls.count_documents({}) == model_calls
    assert await db.delivery_plans.count_documents({'owner_id': OWNER}) == 1
    assert await db.life_nodes.count_documents({'user_id': OWNER, 'type': 'event'}) == 1
    assert await db.ambient_activity.count_documents({'owner_id': OWNER}) == 1
    saved = await sources.existing_plan(db, OWNER, activity)
    if stage == 'after_provider':
        assert saved['status'] != 'delivered'
        assert saved['_source_dispatch']['state'] == 'started'
        assert not saved.get('delivered_at')
    else:
        assert saved['status'] == 'delivered'
    code, output, error = await child('recover_no_model', name)
    assert code == 0 and json.loads(output) == {'handled': 0}, error
    assert await db.synthetic_provider_calls.count_documents({}) == 1
