"""Verified-result boundaries: no extra permission, fabricated fact or blind resend."""
from datetime import timedelta
import asyncio
from unittest.mock import AsyncMock

import pytest
from delivery import source_results as sources, source_result_review as review
from delivery.service import DeliveryService
from test_source_result_delivery_v170 import completed, subject, answer, OWNER, OTHER
from test_general_source_core_v166 import world


@pytest.mark.asyncio
async def test_modified_home_summary_cannot_be_sent_with_old_provenance(completed):
    db, _, activity, service, channel, decision, _, _ = completed
    before = await subject(completed)
    await db.ambient_activity.update_one({'id': activity}, {'$set': {'summary': 'Ho pagato 500 euro.'}})
    out = await service.evaluate_subject(OWNER, before)
    assert out.blocked_by == 'source_result_changed'
    assert not channel.calls
    decision.assert_not_awaited()


@pytest.mark.asyncio
async def test_unreadable_receipt_does_not_invent_an_event(completed):
    db, signal, _, service, channel, decision, _, _ = completed
    before = await subject(completed)
    await db.connected_signals.update_one({'id': signal.id},
        {'$set': {'_core_work.effect.observation.payload.verified': False}})
    assert (await service.evaluate_subject(OWNER, before)).blocked_by == 'source_result_changed'
    decision.assert_not_awaited()
    assert not channel.calls


@pytest.mark.asyncio
async def test_actual_review_pass_discovers_pending_result_without_replaying_core(completed):
    from delivery.admission import drain_with_receipts
    db, signal, _, _, channel, decision, source_calls, _ = completed
    assert await drain_with_receipts(db) == 1
    assert len(source_calls) == 3 and decision.await_count == 1
    assert len(channel.calls) == 1
    assert await drain_with_receipts(db) == 0
    assert len(channel.calls) == 1


@pytest.mark.asyncio
async def test_explicit_zero_acceptance_throttle_obeys_backoff_before_single_retry(completed, monkeypatch):
    import delivery.service as module
    db, _, activity, service, channel, decision, _, _ = completed
    channel.response = {'ok': False, 'provider': channel.name, 'safe_to_retry': True, 'reason': 'expo_http_429'}
    await service.evaluate_subject(OWNER, await subject(completed))
    saved = await sources.existing_plan(db, OWNER, activity)
    assert saved['status'] == 'held' and saved['_source_dispatch']['state'] == 'rejected'
    assert saved['transport_retry_due'] and len(channel.calls) == 1
    await service.evaluate_subject(OWNER, await subject(completed))
    assert len(channel.calls) == 1  # A fresh model answer must not erase backoff.
    later = sources.moment(saved['transport_retry_due']) + timedelta(seconds=1)
    monkeypatch.setattr(sources, 'now', lambda: later)
    monkeypatch.setattr(module, '_now', lambda: later)
    channel.response = {'ok': True, 'provider': channel.name}
    await service.deliver_due(OWNER)
    assert len(channel.calls) == 2
    assert (await sources.existing_plan(db, OWNER, activity))['status'] == 'delivered'
    await service.deliver_due(OWNER)
    assert len(channel.calls) == 2


@pytest.mark.asyncio
async def test_scheduled_result_is_cancelled_when_calendar_entry_changes(completed, monkeypatch):
    import delivery.service as module
    db, _, activity, service, channel, decision, _, _ = completed
    first = module._now()
    decision.return_value = answer(timing='at', not_before=(first+timedelta(minutes=3)).isoformat())
    await service.evaluate_subject(OWNER, await subject(completed))
    assert not channel.calls
    await db.life_nodes.update_one({'user_id': OWNER}, {'$set': {'label': 'Nuova scelta della persona'}})
    monkeypatch.setattr(module, '_now', lambda: first+timedelta(minutes=4))
    await service.deliver_due(OWNER)
    assert not channel.calls and decision.await_count == 1
    assert (await sources.existing_plan(db, OWNER, activity))['status'] == 'cancelled'


@pytest.mark.asyncio
async def test_eight_review_workers_do_not_create_eight_model_decisions(completed):
    db, _, _, _, channel, decision, _, _ = completed
    results = await asyncio.gather(*(review.drain(db) for _ in range(8)))
    assert sum(results) == 1
    assert len(channel.calls) == 1 and decision.await_count == 1


@pytest.mark.asyncio
async def test_existing_sender_rechecks_source_after_send_claim(completed, monkeypatch):
    db, signal, _, service, channel, _, _, _ = completed
    original = service._send_current
    async def revoke_first(owner, plan):
        await db.connector_instances.update_one({'id': signal.source_id}, {'$set': {'status': 'revoked'}})
        return await original(owner, plan)
    monkeypatch.setattr(service, '_send_current', revoke_first)
    await service.evaluate_subject(OWNER, await subject(completed))
    assert not channel.calls


@pytest.mark.asyncio
async def test_shared_delivery_other_account_permissions_are_not_inherited(completed):
    db, _, _, _, channel, decision, _, _ = completed
    current = await subject(completed)
    result = await DeliveryService(db).evaluate_subject(OTHER, current)
    assert result.blocked_by == 'source_result_changed'
    assert not channel.calls
    decision.assert_not_awaited()
