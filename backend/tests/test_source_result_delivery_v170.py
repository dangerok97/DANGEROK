"""Actual Core/calendar/Home/Delivery code, synthetic sources and model responses.

The provider records messages in memory and NEVER contacts a device or Meta.
A recorded provider acceptance is explicitly not evidence of phone delivery.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
import json
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from pymongo.errors import AutoReconnect

from connected.core_work import SourceCoreWorker
from delivery.models import DeliverySubject
from delivery.service import DeliveryService
from delivery import source_results as sources, source_result_review as review
from test_general_source_core_v166 import world, OWNER, OTHER, BODY
from test_durable_source_work_v169 import grant, decisions
from test_source_integrity_v168 import StableMockDatabase

CONTRACT = '{"synthetic":"scripted-model"}'


def answer(**overrides):
    response = {'mode': 'push', 'timing': 'now',
        'reason_to_interrupt': 'La persona ha chiesto di conoscere il completamento del lavoro.',
        'reason_to_open': 'Il calendario contiene il risultato verificato.',
        'what_decided_the_mode': 'Conferma del risultato richiesta, con canale autorizzato.',
        'sensitivity': 'ordinary', 'copy': {
            'title': 'UNSUPPORTED_MODEL_TITLE', 'body': 'UNSUPPORTED_MODEL_SUCCESS',
            'public_title': 'PRIVATE_LABEL_FROM_UNTRUSTED_COPY', 'public_body': 'PRIVATE_LABEL'},
    }
    response.update(overrides)
    return response


class RecordingProvider:
    name = 'scripted-no-device'
    def __init__(self):
        self.calls, self.cancelled = [], []
        self.response = {'ok': True, 'provider': self.name}
        self.error = None
    async def send(self, **kwargs):
        self.calls.append(kwargs)
        await asyncio.sleep(0)
        if self.error:
            raise self.error
        return dict(self.response)
    async def cancel(self, *, owner_id, plan_id):
        self.cancelled.append((owner_id, plan_id))
        return {'ok': True}


@pytest_asyncio.fixture
async def completed(world, monkeypatch):
    from delivery import provider, reasoning, context
    raw, signal, body = world
    db = StableMockDatabase(raw)
    monkeypatch.setenv('ORA_SOURCE_CORE_PILOT_OWNERS', OWNER)
    monkeypatch.setenv('ORA_SOURCE_RESULT_DELIVERY_OWNERS', OWNER)
    monkeypatch.setenv('ORA_SOURCE_MODEL_CONTRACT', CONTRACT)
    await grant(db)
    choose, seen = decisions(signal)
    out = await SourceCoreWorker(db).process_one(OWNER, signal.id, decision_fn=choose)
    assert out['state'] == 'completed' and not out['notifications_sent']
    channel = RecordingProvider()
    monkeypatch.setattr(provider, 'get_provider', lambda: channel)
    permission = AsyncMock(return_value={'push': True})
    monkeypatch.setattr(context, '_permission', permission)
    decision = AsyncMock(return_value=answer())
    monkeypatch.setattr(reasoning, 'decide_delivery', decision)
    service = DeliveryService(db)
    await service.repo.ensure_indexes()
    return db, signal, out['activity_id'], service, channel, decision, seen, permission


async def subject(fixture):
    return await sources.current_subject(fixture[0], OWNER, fixture[2])


@pytest.mark.asyncio
async def test_source_to_original_delivery_uses_verified_copy_and_one_durable_plan(completed):
    db, signal, activity, service, channel, decision, seen, permission = completed
    row = await db.connected_signals.find_one({'id': signal.id})
    assert row['_core_work']['delivery_review']['phase'] == 'pending'
    assert not channel.calls
    assert await review.drain(db) == 1
    assert len(channel.calls) == 1 and len(seen) == 3
    sent = channel.calls[0]
    assert 'Colloquio confermato' in sent['body'] and '16/05/2031 alle 14:00' in sent['body']
    assert sent['deep_link'] == '/' and sent['owner_id'] == OWNER
    assert 'UNSUPPORTED_MODEL' not in json.dumps(sent) and 'PRIVATE_LABEL' not in json.dumps(sent)
    assert 'Colloquio' not in sent['public_body']
    plan = await db.delivery_plans.find_one({'owner_id': OWNER})
    assert plan['source_type'] == 'source_result' and plan['opportunity_id'] == ''
    assert plan['status'] == 'delivered' and plan['_source_dispatch']['state'] == 'accepted'
    assert plan['_source_dispatch']['device_delivery_verified'] is False
    assert plan['_source_dispatch']['provider'] == channel.name
    assert await db.opportunities.count_documents({}) == 0
    assert await db.agent_goals.count_documents({}) == 0
    assert await db.whatsapp_alert_outbox.count_documents({}) == 0
    assert await db.autonomy_consents.count_documents({'source': 'explicit_user_command'}) == 0
    assert BODY not in json.dumps(plan, default=str)
    assert await review.drain(db) == 0
    await service.evaluate_subject(OWNER, await subject(completed))
    assert len(channel.calls) == 1 and decision.await_count == 1
    assert await db.life_nodes.count_documents({'user_id': OWNER}) == 1
    assert await db.ambient_activity.count_documents({'owner_id': OWNER}) == 1


@pytest.mark.asyncio
async def test_delivery_reasoning_retains_request_local_model_contract(completed, monkeypatch):
    from llm.model_contract import active_contract
    from delivery import reasoning
    async def choose(*args, **kwargs):
        assert active_contract() == {'synthetic': 'scripted-model'}
        return answer()
    monkeypatch.setattr(reasoning, 'decide_delivery', choose)
    assert active_contract() is None
    await review.drain(completed[0])
    assert active_contract() is None
    assert len(completed[4].calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('flag', ['ORA_SOURCE_CORE_PILOT_OWNERS', 'ORA_SOURCE_RESULT_DELIVERY_OWNERS'])
@pytest.mark.parametrize('value', ['', '*', OTHER])
async def test_notification_pilot_off_or_foreign_never_sends(completed, monkeypatch, flag, value):
    db, _, _, _, channel, decision, _, _ = completed
    monkeypatch.setenv(flag, value)
    assert await review.drain(db) == 0
    assert not channel.calls
    decision.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_model_contract_keeps_review_pending_without_using_fallback(completed, monkeypatch):
    db, signal, _, _, channel, decision, _, _ = completed
    monkeypatch.delenv('ORA_SOURCE_MODEL_CONTRACT', raising=False)
    assert await review.drain(db) == 1
    row = await db.connected_signals.find_one({'id': signal.id})
    assert row['_core_work']['delivery_review']['phase'] == 'retry'
    assert row['_core_work']['phase'] == 'completed'
    assert not channel.calls
    decision.assert_not_awaited()


@pytest.mark.asyncio
async def test_forged_result_or_another_account_cannot_be_a_delivery_subject(completed):
    db, signal, activity, service, channel, decision, _, _ = completed
    fake = DeliverySubject(source_type='source_result', id='ambsrc_fake', owner_id=OWNER,
                           semantic_summary='Invented completed work')
    assert (await service.evaluate_subject(OWNER, fake)).blocked_by == 'source_result_changed'
    assert await sources.current_subject(db, OTHER, activity) is None
    assert await sources.current_subject(db, OWNER, 'https://untrusted.invalid') is None
    assert not channel.calls
    decision.assert_not_awaited()


@pytest.mark.asyncio
async def test_caller_summary_does_not_override_verified_database_result(completed):
    current = await subject(completed)
    current.semantic_summary = 'Invented a payment of 500 euros'
    await completed[3].evaluate_subject(OWNER, current)
    assert '500' not in completed[4].calls[0]['body']
    seen = completed[5].call_args.args[0]
    assert '500' not in seen['about']['what']


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['connector', 'event', 'visibility', 'fingerprint', 'later_revision'])
async def test_source_or_result_changes_before_review_prevent_send(completed, mutation):
    db, signal, activity, service, channel, decision, _, _ = completed
    if mutation == 'connector':
        await db.connector_instances.update_one({'id': signal.source_id}, {'$set': {'status': 'revoked'}})
    elif mutation == 'event':
        await db.life_nodes.update_one({'user_id': OWNER}, {'$set': {'status': 'archived'}})
    elif mutation == 'visibility':
        await db.ambient_activity.update_one({'id': activity}, {'$set': {'visibility': 'internal'}})
    elif mutation == 'fingerprint':
        await db.connected_signals.update_one({'id': signal.id}, {'$set': {'fingerprint': 'changed'}})
    else:
        row = await db.connected_signals.find_one({'id': signal.id}, {'_id': 0})
        row.update(id='sig_newer', observed_at=(sources.now()+timedelta(minutes=1)).isoformat(), fingerprint='new')
        await db.connected_signals.insert_one(row)
    assert await review.drain(db) >= 1
    assert not channel.calls
    decision.assert_not_awaited()


@pytest.mark.asyncio
async def test_revocation_during_model_decision_is_rechecked(completed, monkeypatch):
    from delivery import reasoning
    db, signal, _, service, channel, _, _, _ = completed
    async def choose(*args, **kwargs):
        await db.connector_instances.update_one({'id': signal.source_id}, {'$set': {'status': 'revoked'}})
        return answer()
    monkeypatch.setattr(reasoning, 'decide_delivery', choose)
    await service.evaluate_subject(OWNER, await subject(completed))
    assert not channel.calls
    assert await db.delivery_plans.count_documents({}) == 0


@pytest.mark.asyncio
async def test_database_outage_is_not_silence_or_a_deleted_source(completed, monkeypatch):
    db, _, _, service, channel, decision, _, _ = completed
    current = await subject(completed)
    injected = AsyncMock(side_effect=AutoReconnect('synthetic read outage'))
    monkeypatch.setattr(db.connected_signals, 'find_one', injected)
    result = await service.evaluate_subject(OWNER, current)
    assert result.unavailable and result.blocked_by == 'source_check_unavailable'
    assert injected.await_count == 1
    decision.assert_not_awaited()
    assert not channel.calls


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['silence', 'quiet_presence', 'in_app'])
async def test_no_notification_is_a_real_delivery_choice_not_an_error(completed, mode):
    db, signal, _, _, channel, decision, seen, _ = completed
    decision.return_value = answer(mode=mode)
    assert await review.drain(db) == 1
    row = await db.connected_signals.find_one({'id': signal.id})
    assert row['_core_work']['delivery_review']['outcome'] == mode
    assert row['_core_work']['delivery_review']['phase'] == 'settled'
    assert not channel.calls and len(seen) == 3
    assert await review.drain(db) == 0


@pytest.mark.asyncio
async def test_unavailable_judgement_retries_with_bound_instead_of_claiming_silence(completed, monkeypatch):
    db, signal, _, _, channel, decision, seen, _ = completed
    decision.return_value = None
    fixed = sources.now()
    for number in range(review.ATTEMPTS):
        monkeypatch.setattr(review, 'now', lambda number=number: fixed+timedelta(minutes=3*number))
        assert await review.drain(db) == 1
    row = await db.connected_signals.find_one({'id': signal.id})
    assert row['_core_work']['delivery_review']['phase'] == 'paused'
    assert row['_core_work']['delivery_review']['outcome'] == 'unavailable'
    assert await review.drain(db) == 0
    assert len(seen) == 3 and not channel.calls


@pytest.mark.asyncio
async def test_pending_plan_waits_and_rechecks_before_the_original_sender(completed, monkeypatch):
    import delivery.service as module
    db, _, activity, service, channel, decision, _, _ = completed
    fixed = module._now()
    decision.return_value = answer(timing='at', not_before=(fixed+timedelta(minutes=5)).isoformat())
    await service.evaluate_subject(OWNER, await subject(completed))
    assert not channel.calls
    stored = await sources.existing_plan(db, OWNER, activity)
    assert stored['status'] == 'pending'
    monkeypatch.setattr(module, '_now', lambda: fixed+timedelta(minutes=6))
    decision.return_value = answer()
    await service.deliver_due(OWNER)
    assert len(channel.calls) == 1
    assert decision.await_count == 2


@pytest.mark.asyncio
async def test_concurrent_decisions_cannot_mint_multiple_plans_or_sends(completed):
    db, _, _, service, channel, _, _, _ = completed
    current = await subject(completed)
    results = await asyncio.gather(*(service.evaluate_subject(OWNER, current) for _ in range(8)))
    assert len(results) == 8 and len(channel.calls) == 1
    assert await db.delivery_plans.count_documents({}) == 1


@pytest.mark.asyncio
async def test_revoked_notification_permission_is_checked_immediately_before_send(completed):
    db, _, activity, service, channel, decision, _, permission = completed
    permission.side_effect = [{'push': True}, {'push': False}]
    await service.evaluate_subject(OWNER, await subject(completed))
    saved = await sources.existing_plan(db, OWNER, activity)
    assert saved['status'] == 'held' and saved['rationale'] == 'no_notification_permission'
    assert saved['_source_dispatch']['state'] == 'not_sent'
    assert not channel.calls


@pytest.mark.asyncio
async def test_unknown_acceptance_is_never_resent_after_worker_retries(completed):
    db, signal, activity, service, channel, decision, _, _ = completed
    channel.error = TimeoutError('synthetic lost provider acknowledgement')
    await review.drain(db)
    stored = await sources.existing_plan(db, OWNER, activity)
    assert stored['_source_dispatch']['state'] == 'unknown' and stored['status'] == 'held'
    assert len(channel.calls) == 1
    await service.evaluate_subject(OWNER, await subject(completed))
    await service.deliver_due(OWNER)
    assert len(channel.calls) == 1
    assert decision.await_count == 1


@pytest.mark.asyncio
async def test_notification_tap_uses_owned_persisted_plan_not_arbitrary_link(completed):
    db, _, activity, service, channel, _, _, _ = completed
    await review.drain(db)
    pid = sources.plan_id(OWNER, activity)
    assert (await service.record_outcome(OTHER, pid, 'opened'))['ok'] is False
    assert (await service.record_outcome(OWNER, pid, 'opened'))['route'] == '/'
    await db.delivery_plans.update_one({'id': pid}, {'$set': {'deep_link': 'https://untrusted.invalid'}})
    assert (await service.record_outcome(OWNER, pid, 'opened'))['ok'] is False
