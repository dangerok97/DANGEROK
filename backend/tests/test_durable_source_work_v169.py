"""Synthetic input and model decisions; actual Core, calendar and Home repositories.

Assertions inspect persisted effects and receipts. No provider/model call and no
push, WhatsApp, personal account or production owner is involved.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import json
from unittest.mock import AsyncMock

import pytest
from connected import core_work
from connected.core_work import SourceCoreWorker, SourceWork, LeaseLost
from connected.signals import SignalService
from agent.authority import AuthorityService
from delivery.service import DeliveryService
from test_general_source_core_v166 import world, OWNER, OTHER, BODY, action
from test_source_integrity_v168 import StableMockDatabase


async def grant(db):
    service = AuthorityService(db)
    await service.set_mode(OWNER, 'act_within_grants')
    await service.grant(OWNER, 'calendar.local.write', effect_scope=['create'], by='user')


@pytest.mark.asyncio
async def test_source_pilot_readiness_requires_enrollment_mode_and_create_grant(world, monkeypatch):
    raw, signal, _ = world
    db = StableMockDatabase(raw)
    monkeypatch.setenv('ORA_SOURCE_CORE_PILOT_OWNERS', OWNER)

    # Railway enrollment alone is never consent.
    assert await core_work.ready_for_owner(db, OWNER) is False

    authority = AuthorityService(db)
    await authority.set_mode(OWNER, 'act_within_grants')
    # The mode is a ceiling choice, not a capability grant.
    assert await core_work.ready_for_owner(db, OWNER) is False

    granted = await authority.grant(
        OWNER,
        'calendar.local.write',
        effect_scope=['create'],
        scope_note='Aggiungere nuovi impegni personali al calendario ORA.',
        by='user',
    )
    assert await core_work.ready_for_owner(db, OWNER) is True

    await authority.revoke(
        OWNER,
        'calendar.local.write',
        grant_id=granted['grant']['id'],
    )
    assert await core_work.ready_for_owner(db, OWNER) is False


@pytest.mark.asyncio
async def test_source_pilot_expired_grant_keeps_legacy_lane(world, monkeypatch):
    raw, signal, _ = world
    db = StableMockDatabase(raw)
    monkeypatch.setenv('ORA_SOURCE_CORE_PILOT_OWNERS', OWNER)
    authority = AuthorityService(db)
    await authority.set_mode(OWNER, 'act_within_grants')
    given = await authority.grant(
        OWNER, 'calendar.local.write', effect_scope=['create'], by='user'
    )
    assert await core_work.ready_for_owner(db, OWNER) is True
    await db.autonomy_grants.update_one(
        {'owner_id': OWNER, 'id': given['grant']['id']},
        {'$set': {'expires_at': datetime.now(timezone.utc) - timedelta(seconds=1)}},
    )
    # The UI-safe public grant summary still reports active; readiness must
    # check the real expiry independently before switching source interpreters.
    assert (await authority.grants(OWNER))[0]['active'] is True
    assert await core_work.ready_for_owner(db, OWNER) is False


@pytest.mark.asyncio
async def test_source_pilot_requires_user_grant_not_code_grant(world, monkeypatch):
    raw, signal, _ = world
    db = StableMockDatabase(raw)
    monkeypatch.setenv('ORA_SOURCE_CORE_PILOT_OWNERS', OWNER)
    authority = AuthorityService(db)
    await authority.set_mode(OWNER, 'act_within_grants')
    await authority.grant(
        OWNER, 'calendar.local.write', effect_scope=['create'], by='code'
    )
    assert await core_work.ready_for_owner(db, OWNER) is False
    await authority.grant(
        OWNER, 'calendar.local.write', effect_scope=['create'], by='user'
    )
    assert await core_work.ready_for_owner(db, OWNER) is True


@pytest.mark.asyncio
async def test_source_pilot_readiness_respects_explicit_observe_even_with_grant(world, monkeypatch):
    raw, signal, _ = world
    db = StableMockDatabase(raw)
    monkeypatch.setenv('ORA_SOURCE_CORE_PILOT_OWNERS', OWNER)

    authority = AuthorityService(db)
    await authority.grant(
        OWNER,
        'calendar.local.write',
        effect_scope=['create'],
        scope_note='Aggiungere nuovi impegni personali al calendario ORA.',
        by='user',
    )
    await authority.set_mode(OWNER, 'observe')

    assert await core_work.ready_for_owner(db, OWNER) is False


@pytest.mark.asyncio
async def test_source_pilot_readiness_rejects_modify_only_grant(world, monkeypatch):
    raw, signal, _ = world
    db = StableMockDatabase(raw)
    monkeypatch.setenv('ORA_SOURCE_CORE_PILOT_OWNERS', OWNER)

    authority = AuthorityService(db)
    await authority.set_mode(OWNER, 'act_within_grants')
    await authority.grant(
        OWNER,
        'calendar.local.write',
        effect_scope=['modify'],
        scope_note='Modificare impegni personali nel calendario ORA.',
        by='user',
    )

    assert await core_work.ready_for_owner(db, OWNER) is False


def decisions(signal, *, before_answer=None):
    seen = []
    async def decide(system, payload):
        data = json.loads(payload)
        seen.append(data)
        assert data['user_message'] == ''
        assert data['source_activation']['human_message_present'] is False
        if len(seen) == 1:
            return {'response_mode': 'tool', 'reasoning_status': 'needs_tool',
                    'tool_call': {'name': 'read_connected_source',
                                  'arguments': {'source_ref': 'signal:' + signal.id}}}
        if len(seen) == 2:
            assert BODY in payload
            return {'response_mode': 'tool', 'reasoning_status': 'needs_tool',
                    'tool_call': {'name': 'create_calendar_event', 'arguments': action()}}
        if before_answer:
            await before_answer()
        return {'response_mode': 'answer', 'message_to_user': 'Appuntamento registrato.'}
    return decide, seen


@pytest.mark.asyncio
async def test_same_core_reads_writes_verifies_and_hands_off_one_home_result(world):
    raw, signal, body = world
    db = StableMockDatabase(raw)
    await grant(db)
    decide, seen = decisions(signal)
    out = await SourceCoreWorker(db).process_one(OWNER, signal.id, decision_fn=decide)
    assert out['state'] == 'completed' and out['home_visible']
    assert not out['notifications_sent']
    assert len(seen) == 3
    assert await db.life_nodes.count_documents({'user_id': OWNER, 'type': 'event'}) == 1
    home = await db.ambient_activity.find_one({'owner_id': OWNER})
    assert home['visibility'] == 'ambient' and '16/05/2031 alle 14:00' in home['summary']
    assert 'Colloquio confermato' in home['summary']
    assert len(home['source_refs']) == 2
    source = await db.connected_signals.find_one({'owner_id': OWNER, 'id': signal.id})
    assert source['status'] == 'interpreted' and source['_core_work']['phase'] == 'completed'
    assert source['_core_work']['effect']['state'] == 'verified'
    assert BODY not in json.dumps(source, default=str)
    assert 'arguments' not in source['_core_work']['effect']
    assert await db.autonomy_consents.count_documents({'source': 'explicit_user_command'}) == 0
    again = await SourceCoreWorker(db).process_one(OWNER, signal.id, decision_fn=decide)
    assert again['state'] == 'not_claimed' and len(seen) == 3
    assert await db.ambient_activity.count_documents({'owner_id': OWNER}) == 1


@pytest.mark.asyncio
async def test_simultaneous_workers_have_exactly_one_claim(world):
    raw, signal, body = world
    db = StableMockDatabase(raw)
    claims = await asyncio.gather(*(SourceCoreWorker(db).claim(OWNER, signal.id) for _ in range(8)))
    assert sum(x is not None for x in claims) == 1
    assert await SourceCoreWorker(db).claim(OTHER, signal.id) is None
    body.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_worker_cannot_start_or_finish_effect_after_reclaim(world, monkeypatch):
    raw, signal, _ = world
    db = StableMockDatabase(raw)
    worker = SourceCoreWorker(db)
    old = await worker.claim(OWNER, signal.id)
    now = core_work._now() + timedelta(seconds=core_work.LEASE_SECONDS + 1)
    monkeypatch.setattr(core_work, '_now', lambda: now)
    new = await worker.claim(OWNER, signal.id)
    assert new and old.token != new.token
    with pytest.raises(LeaseLost):
        await old.before_effect('create_calendar_event', action())
    with pytest.raises(LeaseLost):
        await old.change({'_core_work.phase': 'completed'})
    await new.current()


@pytest.mark.asyncio
async def test_interruption_after_verified_effect_recovers_without_model_or_duplicate(world, monkeypatch):
    raw, signal, _ = world
    db = StableMockDatabase(raw)
    await grant(db)
    async def interrupted():
        raise asyncio.CancelledError()
    decide, seen = decisions(signal, before_answer=interrupted)
    with pytest.raises(asyncio.CancelledError):
        await SourceCoreWorker(db).process_one(OWNER, signal.id, decision_fn=decide)
    assert await db.life_nodes.count_documents({'user_id': OWNER}) == 1
    assert await db.ambient_activity.count_documents({}) == 0
    row = await db.connected_signals.find_one({'id': signal.id})
    assert row['_core_work']['effect']['state'] == 'verified'
    now = core_work._now() + timedelta(seconds=core_work.LEASE_SECONDS + 1)
    monkeypatch.setattr(core_work, '_now', lambda: now)
    no_model = AsyncMock(side_effect=AssertionError('A recorded effect must not be repeated'))
    recovered = await SourceCoreWorker(db).process_one(OWNER, signal.id, decision_fn=no_model)
    assert recovered['state'] == 'completed' and recovered['home_visible']
    no_model.assert_not_awaited()
    assert await db.life_nodes.count_documents({'user_id': OWNER}) == 1
    assert await db.ambient_activity.count_documents({'owner_id': OWNER}) == 1


@pytest.mark.asyncio
async def test_uncertain_effect_is_not_blindly_repeated(world, monkeypatch):
    raw, signal, _ = world
    db = StableMockDatabase(raw)
    work = await SourceCoreWorker(db).claim(OWNER, signal.id)
    await work.before_effect('create_calendar_event', action())
    now = core_work._now() + timedelta(seconds=core_work.LEASE_SECONDS + 1)
    monkeypatch.setattr(core_work, '_now', lambda: now)
    decide = AsyncMock(side_effect=AssertionError('Unknown write cannot be retried'))
    result = await SourceCoreWorker(db).process_one(OWNER, signal.id, decision_fn=decide)
    assert result['state'] == 'reconciliation_required'
    decide.assert_not_awaited()
    assert await db.life_nodes.count_documents({'user_id': OWNER}) == 0
    assert await db.ambient_activity.count_documents({}) == 0
    assert (await SourceCoreWorker(db).process_one(OWNER, signal.id, decision_fn=decide))['state'] == 'not_claimed'


@pytest.mark.asyncio
@pytest.mark.parametrize('ack_lost', [False, True])
async def test_home_outage_recovers_without_replanning_or_duplicate(world, monkeypatch, ack_lost):
    raw, signal, _ = world
    db = StableMockDatabase(raw)
    await grant(db)
    original = DeliveryService.note_activity
    attempts = []
    async def fail_once(self, *args, **kwargs):
        attempts.append(kwargs['activity_id'])
        if len(attempts) == 1:
            if ack_lost:
                await original(self, *args, **kwargs)
            raise ConnectionError('synthetic Home storage error')
        return await original(self, *args, **kwargs)
    monkeypatch.setattr(DeliveryService, 'note_activity', fail_once)
    decide, seen = decisions(signal)
    result = await SourceCoreWorker(db).process_one(OWNER, signal.id, decision_fn=decide)
    assert result['state'] == 'result_ready' and not result['home_visible']
    now = core_work._now() + timedelta(minutes=1)
    monkeypatch.setattr(core_work, '_now', lambda: now)
    result = await SourceCoreWorker(db).process_one(OWNER, signal.id, decision_fn=decide)
    assert result['state'] == 'completed' and len(seen) == 3
    assert len(set(attempts)) == 1
    assert await db.ambient_activity.count_documents({'owner_id': OWNER}) == 1
    assert await db.life_nodes.count_documents({'user_id': OWNER}) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['cancel_event', 'revoke_source', 'supersede_signal'])
async def test_changed_source_or_effect_is_not_announced_as_current(world, monkeypatch, change):
    raw, signal, _ = world
    db = StableMockDatabase(raw)
    await grant(db)
    async def interrupt():
        raise asyncio.CancelledError()
    decide, _ = decisions(signal, before_answer=interrupt)
    with pytest.raises(asyncio.CancelledError):
        await SourceCoreWorker(db).process_one(OWNER, signal.id, decision_fn=decide)
    if change == 'cancel_event':
        await db.life_nodes.update_one({'user_id': OWNER}, {'$set': {'status': 'archived'}})
    elif change == 'revoke_source':
        await db.connector_instances.update_one({'id': 'mail_test'}, {'$set': {'status': 'revoked'}})
    else:
        await db.connected_signals.update_one({'id': signal.id}, {'$set': {'status': 'superseded'}})
    now = core_work._now() + timedelta(seconds=core_work.LEASE_SECONDS + 1)
    monkeypatch.setattr(core_work, '_now', lambda: now)
    result = await SourceCoreWorker(db).process_one(OWNER, signal.id, decision_fn=AsyncMock())
    assert result['state'] in {'stale_result', 'not_claimed'}
    assert not result['home_visible']
    assert await db.ambient_activity.count_documents({'visibility': 'ambient'}) == 0


@pytest.mark.asyncio
async def test_grant_missing_prevents_event_and_false_home_success(world):
    raw, signal, _ = world
    db = StableMockDatabase(raw)
    decide, _ = decisions(signal)
    result = await SourceCoreWorker(db).process_one(OWNER, signal.id, decision_fn=decide)
    assert result['state'] != 'completed'
    assert await db.life_nodes.count_documents({'user_id': OWNER}) == 0
    assert await db.ambient_activity.count_documents({}) == 0
    assert await db.autonomy_consents.count_documents({}) == 0


@pytest.mark.asyncio
async def test_source_no_effect_creates_no_home_noise(world):
    raw, signal, _ = world
    db = StableMockDatabase(raw)
    calls = []
    async def decide(system, payload):
        calls.append(1)
        if len(calls) == 1:
            return {'response_mode': 'tool', 'reasoning_status': 'needs_tool',
                'tool_call': {'name': 'read_connected_source', 'arguments': {'source_ref': 'signal:'+signal.id}}}
        return {'response_mode': 'answer', 'message_to_user': 'Nessuna operazione eseguita.'}
    result = await SourceCoreWorker(db).process_one(OWNER, signal.id, decision_fn=decide)
    assert result['state'] == 'reviewed_no_effect'
    assert await db.ambient_activity.count_documents({}) == 0
    assert await db.life_nodes.count_documents({}) == 0


@pytest.mark.asyncio
async def test_outage_before_any_effect_is_bounded_and_does_not_ask_another_engine(world, monkeypatch):
    from conversation_engine.ai_core import loop
    raw, signal, _ = world
    db = StableMockDatabase(raw)
    clock = [core_work._now()]
    monkeypatch.setattr(core_work, '_now', lambda: clock[0])
    broken = AsyncMock(side_effect=ConnectionError('synthetic model unavailable'))
    monkeypatch.setattr(loop, 'run_cognitive_loop', broken)
    for index in range(core_work.MAX_ATTEMPTS):
        result = await SourceCoreWorker(db).process_one(OWNER, signal.id, decision_fn=AsyncMock())
        assert result['state'] == ('failed' if index == core_work.MAX_ATTEMPTS-1 else 'retry')
        # Retries back off (30 s, 2, 8, 32 min, capped): step past the longest.
        clock[0] += timedelta(seconds=core_work.RETRY_MAX_SECONDS + 60)
    assert (await SourceCoreWorker(db).process_one(OWNER, signal.id, decision_fn=AsyncMock()))['state'] == 'not_claimed'
    assert broken.await_count == core_work.MAX_ATTEMPTS
    assert await db.ambient_activity.count_documents({}) == 0


@pytest.mark.parametrize('setting,expected', [('', False), ('*', False), (OTHER, False), (OWNER, True), (OWNER+','+OTHER, True)])
def test_pilot_is_explicit_owner_configuration_not_implicit_permission(monkeypatch, setting, expected):
    monkeypatch.setenv('ORA_SOURCE_CORE_PILOT_OWNERS', setting)
    assert core_work.enabled_for(OWNER) is expected


@pytest.mark.asyncio
async def test_existing_connected_entry_uses_one_lane_only_when_enrolled_and_opted_in(world, monkeypatch):
    from connected.service import ConnectedLifeService
    from connected import reasoning
    raw, signal, _ = world
    db = StableMockDatabase(raw)
    monkeypatch.setenv('ORA_SOURCE_CORE_PILOT_OWNERS', OWNER)
    await grant(db)
    processor = AsyncMock(return_value={'ok': True, 'passed_on': 1})
    monkeypatch.setattr(SourceCoreWorker, 'process_pending', processor)
    legacy = AsyncMock(side_effect=AssertionError('Do not run two interpreters'))
    monkeypatch.setattr(reasoning, 'interpret_signal', legacy)
    result = await ConnectedLifeService(db).interpret(OWNER)
    assert result['passed_on'] == 1
    processor.assert_awaited_once()
    legacy.assert_not_awaited()


@pytest.mark.asyncio
async def test_old_lane_does_not_take_claimed_pilot_work_when_flag_is_disabled(world, monkeypatch):
    raw, signal, _ = world
    db = StableMockDatabase(raw)
    monkeypatch.delenv('ORA_SOURCE_CORE_PILOT_OWNERS', raising=False)
    assert len(await SignalService(db).pending(OWNER)) == 1
    assert await SourceCoreWorker(db).claim(OWNER, signal.id)
    assert await SignalService(db).pending(OWNER) == []
