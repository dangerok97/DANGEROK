"""Atomic source work and actual interpreter exits, on isolated synthetic data.

The model decisions are scripted. Core, tools, grants, native calendar, Mongo
and Home are the application's real implementations. No real mailbox or push.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import uuid
from unittest.mock import AsyncMock

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


def require_real_ci():
    if os.environ.get('ORA_SOURCE_REAL_DB_TEST') != '1':
        pytest.skip('Real database execution requires isolated CI opt-in')
    assert os.environ.get('CI') == 'true'
    assert os.environ['MONGO_URL'] == 'mongodb://127.0.0.1:27017'


@pytest.mark.asyncio
async def test_real_mongo_concurrent_source_claims_return_one_owner():
    require_real_ci()
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


CHILD = r'''
import asyncio, json, logging, os, sys
from types import SimpleNamespace
from unittest.mock import AsyncMock
from motor.motor_asyncio import AsyncIOMotorClient
import deps
from connected.core_work import SourceCoreWorker
from conversation_engine.ai_core import loop
from home import manual_event
from delivery.service import DeliveryService
from llm.manager import ProviderManager

async def run():
    mode, name, owner, signal_id = sys.argv[1:]
    assert os.environ['CI'] == 'true'
    assert os.environ['MONGO_URL'] == 'mongodb://127.0.0.1:27017'
    assert name.startswith('ora_source_v169_process_')
    client = AsyncIOMotorClient(os.environ['MONGO_URL'], serverSelectionTimeoutMS=5000)
    db = client[name]
    deps.get_gmail_service = lambda: SimpleNamespace(body_for=AsyncMock(return_value=
        'PRIVATE_SOURCE169. Colloquio confermato il 16 maggio 2031 dalle 14:00 alle 14:30, Europe/Rome.'))
    loop.report_activity = AsyncMock()
    manual_event._wake = AsyncMock()
    ProviderManager.chat = AsyncMock(side_effect=AssertionError('No real LLM in this storage test'))
    if mode == 'after_event':
        original = manual_event.create_manual_event
        async def saved_then_exit(*args, **kwargs):
            await original(*args, **kwargs)
            os._exit(42)
        manual_event.create_manual_event = saved_then_exit
    if mode == 'after_home':
        original_home = DeliveryService.note_activity
        async def home_then_exit(self, *args, **kwargs):
            await original_home(self, *args, **kwargs)
            os._exit(44)
        DeliveryService.note_activity = home_then_exit
    calls = 0
    async def decide(system, payload):
        nonlocal calls
        calls += 1
        assert mode != 'recover', 'Recovery must not rerun the AI'
        data = json.loads(payload)
        assert data['user_message'] == ''
        if calls == 1:
            return {'response_mode': 'tool', 'reasoning_status': 'needs_tool',
                'tool_call': {'name': 'read_connected_source', 'arguments': {'source_ref': 'signal:'+signal_id}}}
        if calls == 2:
            return {'response_mode': 'tool', 'reasoning_status': 'needs_tool',
                'tool_call': {'name': 'create_calendar_event', 'arguments': {
                    'calendar_target': 'ora', 'operation_intent': 'new',
                    'title': 'Colloquio di collaudo', 'start_datetime': '2031-05-16T14:00:00+02:00',
                    'end_datetime': '2031-05-16T14:30:00+02:00', 'timezone': 'Europe/Rome'}}}
        if mode == 'after_receipt':
            os._exit(43)
        return {'response_mode': 'answer', 'message_to_user': 'Appuntamento registrato.'}
    try:
        result = await SourceCoreWorker(db).process_one(owner, signal_id, decision_fn=decide)
        print('ORA_SOURCE169_CHILD '+json.dumps({'result': result, 'model_decisions': calls}), flush=True)
    finally:
        client.close()
logging.basicConfig(level=logging.ERROR)
asyncio.run(run())
'''


async def child(mode, name, signal_id):
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env['PYTHONPATH'] = str(root)
    process = await asyncio.create_subprocess_exec(
        sys.executable, '-c', CHILD, mode, name, OWNER, signal_id,
        cwd=root, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), 35)
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        raise
    return process.returncode, stdout.decode(), stderr.decode()


@pytest.mark.asyncio
@pytest.mark.parametrize('checkpoint,exit_code', [('after_event', 42), ('after_receipt', 43), ('after_home', 44)])
async def test_separate_interpreter_recovers_without_repeating_real_calendar_effect(checkpoint, exit_code):
    require_real_ci()
    from agent.authority import AuthorityService
    from connectors.gmail.scopes import CONNECTOR_ID
    from delivery.repository import DeliveryRepository
    name = 'ora_source_v169_process_' + uuid.uuid4().hex
    client = AsyncIOMotorClient(os.environ['MONGO_URL'], serverSelectionTimeoutMS=5000)
    db = client[name]
    try:
        await DeliveryRepository(db).ensure_indexes()
        await db.users.insert_one({'id': OWNER, 'user_id': OWNER, 'settings': {'timezone': 'Europe/Rome'}})
        await db.connector_instances.insert_one({'id': 'source-A', 'user_id': OWNER,
            'connector_id': CONNECTOR_ID, 'status': 'connected', 'metadata': {},
            'last_sync_at': datetime.now(timezone.utc).isoformat()})
        signal, _ = await SignalService(db).record(observation())
        authority = AuthorityService(db)
        await authority.set_mode(OWNER, 'act_within_grants')
        await authority.grant(OWNER, 'calendar.local.write', by='user', effect_scope=['create'])
        code, stdout, stderr = await child(checkpoint, name, signal.id)
        assert code == exit_code, (code, stdout[-1600:], stderr[-1600:])
        assert await db.life_nodes.count_documents({'user_id': OWNER, 'type': 'event'}) == 1
        source = await db.connected_signals.find_one({'id': signal.id}, {'_id': 0})
        expected_effect = 'started' if checkpoint == 'after_event' else 'verified'
        assert source['_core_work']['effect']['state'] == expected_effect
        assert source['status'] == 'pending'
        # Expire only this killed process's lease; no wait or clock is forged
        # into the application, and this is an isolated database.
        await db.connected_signals.update_one({'id': signal.id}, {'$set': {
            '_core_work.lease_until': (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()}})
        code, stdout, stderr = await child('recover', name, signal.id)
        assert code == 0, (stdout[-1600:], stderr[-1600:])
        marker = [line for line in stdout.splitlines() if line.startswith('ORA_SOURCE169_CHILD ')][-1]
        report = json.loads(marker.removeprefix('ORA_SOURCE169_CHILD '))
        assert report['model_decisions'] == 0
        assert not report['result']['notifications_sent']
        expected_state = 'reconciliation_required' if checkpoint == 'after_event' else 'completed'
        assert report['result']['state'] == expected_state
        assert await db.life_nodes.count_documents({'user_id': OWNER, 'type': 'event'}) == 1
        assert await db.ambient_activity.count_documents({'owner_id': OWNER}) == (0 if checkpoint == 'after_event' else 1)
        source = await db.connected_signals.find_one({'id': signal.id}, {'_id': 0})
        assert 'PRIVATE_SOURCE169' not in json.dumps(source, default=str)
        if checkpoint != 'after_event':
            home = await db.ambient_activity.find_one({'owner_id': OWNER})
            assert home['visibility'] == 'ambient' and '16/05/2031 alle 14:00' in home['summary']
    finally:
        assert name.startswith('ora_source_v169_process_')
        await client.drop_database(name)
        client.close()


@pytest.mark.asyncio
async def test_due_work_is_not_starved_by_an_older_active_lease(monkeypatch):
    from connected import core_work
    db = StableMockDatabase(AsyncMongoMockClient().source_work_fairness_synthetic)
    old, _ = await SignalService(db).record(observation(ref='old'))
    due, _ = await SignalService(db).record(observation(ref='due'))
    assert await SourceCoreWorker(db).claim(OWNER, old.id)
    process = AsyncMock(return_value={'state': 'reviewed_no_effect'})
    monkeypatch.setattr(SourceCoreWorker, 'process_one', process)
    await SourceCoreWorker(db).process_pending(OWNER, limit=1)
    process.assert_awaited_once_with(OWNER, due.id)
