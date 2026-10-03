"""Life-assistant continuity: app closed, interrupted work, replies and revocation.

Synthetic owners only. Real persistence/services on in-memory Mongo; model and
external boundaries are controlled. CI also runs the existing real-Mongo gates.
"""
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from agent import reasoning
from agent.admission import drain
from agent.background import recover_due, advance_wake
from agent.clarifications import answer_question, work_view
from agent.models import AutonomousGoal, ActionPlan, ActionStep, AgentEvidence, ResultProvenance
from agent.service import AgentService
from ambient.models import AmbientWake
from opportunities.models import Opportunity
from opportunities.repository import OpportunityRepository
from opportunities.work import update_work


@pytest_asyncio.fixture
async def db(monkeypatch):
    import mongomock.collection
    original = mongomock.collection.Collection.find_one_and_update
    def update(self, *args, **kwargs):
        kwargs.pop('projection', None)  # mongomock loses re-finds without _id
        return original(self, *args, **kwargs)
    if os.environ.get('CONTINUITY_REAL_MONGO') == '1':
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(os.environ['MONGO_URL'], serverSelectionTimeoutMS=3000)
        database = client[f'ora_continuity_{uuid.uuid4().hex}']
    else:
        monkeypatch.setattr(mongomock.collection.Collection, 'find_one_and_update', update)
        client = AsyncMongoMockClient()
        database = client.test
    await database.agent_goals.create_index('id', unique=True)
    await database.agent_runs.create_index('goal_id', unique=True)
    await database.agent_goals.create_index([('owner_id', 1), ('opportunity_id', 1)], unique=True,
        partialFilterExpression={'opportunity_id': {'$gt': ''}, 'status': {'$in': ['proposed', 'active', 'waiting']}})
    monkeypatch.setattr(AgentService, '_note_ambient', AsyncMock())
    monkeypatch.setattr(AgentService, '_consider_visibility', AsyncMock())
    monkeypatch.setattr(AgentService, '_observe_life_change', AsyncMock())
    try:
        yield database
    finally:
        await client.drop_database(database.name)
        client.close()


async def concern(db, owner='alice'):
    return await OpportunityRepository(db).save(Opportunity(owner_id=owner,
        identity_key='contract:one', status='active', semantic_summary='Rinnovo da verificare',
        why_it_matters='Le condizioni cambiano', what_ora_can_do='Confrontare le condizioni'))


@pytest.mark.asyncio
async def test_opening_pending_automatic_work_cannot_start_a_parallel_session(db):
    opp = await concern(db)
    for start in (False, True):
        result = await update_work(db, 'alice', opp, start=start)
        assert result['status'] == 'running' and not result.get('session_id')
    assert await db.update_work.count_documents({}) == 0


@pytest.mark.asyncio
async def test_document_only_upload_enters_existing_source_queue_without_home(db, monkeypatch):
    from documents.service import DocumentService
    from documents.storage import StoredObject
    from documents.intelligence import worker
    from connected.polling import _what_to_read
    from connected.documents_sensor import read_changes
    monkeypatch.setenv('DOCUMENT_EXTRACTION_ENABLED', 'true')
    monkeypatch.setattr(worker, 'enqueue_document_job', AsyncMock())
    content = b'Condizioni sintetiche: costo annuo 120 euro.'
    storage = SimpleNamespace(put=AsyncMock(return_value=StoredObject(
        provider='test', key='test:contract', size=len(content), hash='fixture-hash')))
    service = DocumentService(db=db, storage=storage)
    result = await service.upload(user_id='alice', content=content,
        original_filename='condizioni.txt', mime_type='text/plain')
    doc_id = result['document']['id']
    assert await db.connector_instances.count_documents({}) == 0
    # This read is the same one reached from the background loop. No owner hint,
    # Home route, chat, connected-provider registration or explicit sync.
    queue, _ = await _what_to_read(db, now=datetime.now(timezone.utc), limit=10)
    assert [(owner, source.id) for owner, source in queue] == [('alice', 'documents')]
    assert (await read_changes(db, 'alice'))[0].signal_type == 'document.added'
    assert await read_changes(db, 'alice') == []
    assert not (await db.documents.find_one({'id': doc_id})).get('connected_read_pending')
    # A delayed extraction wakes the shelf again, even after normal scheduling.
    await db.connected_source_attempts.update_one({'owner_id': 'alice'},
        {'$set': {'next_attempt_at': (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()}})
    await service._extract_and_persist(user_id='alice', doc_id=doc_id,
        blob=b'Costo corretto: 100 euro.', mime_type='text/plain', life_node_id=None)
    queue, _ = await _what_to_read(db, now=datetime.now(timezone.utc), limit=10)
    assert [(owner, source.id) for owner, source in queue] == [('alice', 'documents')]
    assert (await read_changes(db, 'alice'))[0].signal_type == 'document.updated'
    assert await read_changes(db, 'bob') == []


@pytest.mark.asyncio
async def test_new_document_handoff_does_not_backfill_untouched_history(db):
    from connected.polling import _what_to_read
    await db.documents.insert_one({'id': 'historical', 'user_id': 'bob', 'filename': 'old.txt'})
    queue, _ = await _what_to_read(db, now=datetime.now(timezone.utc), limit=10)
    assert queue == []


@pytest.mark.asyncio
async def test_admission_question_reply_drives_same_durable_work_without_chat(db, monkeypatch):
    opp = await concern(db)
    decide = AsyncMock(side_effect=[{'outcome': 'clarify', 'question': 'Quale piano è attivo?'},
        {'outcome': 'create_goal', 'objective': 'Confronta il piano attivo', 'desired_outcome': 'Confronto utilizzabile'}])
    monkeypatch.setattr(reasoning, 'decide_goal', decide)
    await drain(db)
    view = await update_work(db, 'alice', opp)
    assert view['status'] == 'needs_user' and not view.get('session_id')
    assert (await OpportunityRepository(db).get('alice', opp.id)).for_home()['question'] == 'Quale piano è attivo?'
    reply = 'È attivo il piano mensile.'
    await update_work(db, 'alice', opp, start=True, reply=reply, question_revision=view['question_revision'])
    await answer_question(db, 'alice', opp.id, reply, view['question_revision'])  # request retry
    await recover_due(db)
    await recover_due(db)
    assert decide.await_count == 2
    assert decide.await_args.args[0]['user_clarifications'][0]['answer'] == reply
    goal = await db.agent_goals.find_one({'opportunity_id': opp.id})
    assert goal['clarifications'][0]['answer'] == reply
    assert goal['requires_user_authority'] is False
    assert await db.agent_goals.count_documents({'owner_id': 'alice'}) == 1
    assert await db.ambient_wakes.count_documents({'source_ref': f"goal:{goal['id']}"}) == 1
    assert await db.update_work.count_documents({}) == 0, 'no parallel conversation/job'


@pytest.mark.asyncio
async def test_question_revision_and_owner_are_enforced(db, monkeypatch):
    opp = await concern(db)
    monkeypatch.setattr(reasoning, 'decide_goal', AsyncMock(return_value={'outcome': 'clarify', 'question': 'Quale piano?'}))
    await drain(db)
    revision = (await work_view(db, 'alice', opp.id))['question_revision']
    assert await work_view(db, 'bob', opp.id) is None
    with pytest.raises(HTTPException) as err:
        await answer_question(db, 'bob', opp.id, 'Risposta', revision)
    assert err.value.status_code == 404
    opp.semantic_summary = 'La fonte è cambiata'
    await OpportunityRepository(db).save(opp)
    with pytest.raises(HTTPException) as err:
        await answer_question(db, 'alice', opp.id, 'Risposta vecchia', revision)
    assert err.value.status_code == 409
    assert 'agent_review_answers' not in await db.opportunities.find_one({'id': opp.id})


@pytest.mark.asyncio
async def test_two_answers_to_one_question_do_not_duplicate_admission(db, monkeypatch):
    opp = await concern(db)
    monkeypatch.setattr(reasoning, 'decide_goal', AsyncMock(return_value={'outcome': 'clarify', 'question': 'Quale piano?'}))
    await drain(db)
    revision = (await work_view(db, 'alice', opp.id))['question_revision']
    await asyncio.gather(*(answer_question(db, 'alice', opp.id, 'Mensile', revision) for _ in range(2)))
    row = await db.opportunities.find_one({'id': opp.id})
    assert len(row['agent_review_answers']) == 1 and row['agent_review_attempts'] == 0


async def running_goal(db, opp):
    row = await db.opportunities.find_one({'id': opp.id})
    goal = AutonomousGoal(owner_id=opp.owner_id, opportunity_id=opp.id,
        opportunity_revision=row['agent_review_revision'], objective='Verifica condizioni',
        desired_outcome='Confronto documentato', status='waiting', requires_user_authority=True,
        prepared_text='Vecchio risultato', background_runs=3)
    service = AgentService(db)
    await service.repo.create_goal(goal)
    plan = ActionPlan(owner_id=goal.owner_id, goal_id=goal.id, status='waiting', steps=[
        ActionStep(intent='Vecchia proposta', step_type='execute', status='blocked', capability_needed='calendar.write')])
    await service.repo.save_plan(plan)
    await service.evidence.record(AgentEvidence(owner_id=goal.owner_id, goal_id=goal.id,
        claim='Vecchie condizioni', provenance=ResultProvenance(source_class='internal_observation')))
    return goal, plan


@pytest.mark.asyncio
async def test_changed_source_replans_same_goal_and_retires_old_result(db, monkeypatch):
    opp = await concern(db)
    goal, old_plan = await running_goal(db, opp)
    opp.semantic_summary = 'La data del rinnovo è cambiata'
    await OpportunityRepository(db).save(opp)
    await recover_due(db)
    assert await db.agent_goals.count_documents({}) == 1
    assert (await db.agent_goals.find_one({'id': goal.id}))['source_review_pending']
    async def work(self, owner, current, run, budget, **kwargs):
        assert current.id == goal.id and current.background_runs == 1
        assert not current.requires_user_authority and not current.prepared_text
        assert current.source_situation['semantic_summary'] == opp.semantic_summary
        assert await self.repo.plan_for(owner, current.id) is None
        assert await self.evidence.for_goal(owner, current.id) == []
        current.status = 'completed'
        return {'ok': True, 'state': 'completed'}
    monkeypatch.setattr(AgentService, '_work', work)
    wake = AmbientWake(owner_id='alice', reason='opportunity_revisit', source_ref=f'goal:{goal.id}')
    assert (await advance_wake(db, wake)).result == 'completed'
    assert (await db.agent_plans.find_one({'id': old_plan.id}))['status'] == 'cancelled'
    assert await db.agent_evidence.count_documents({'superseded': True}) == 1, 'history preserved'


@pytest.mark.asyncio
async def test_closing_source_stops_its_automatic_work(db, monkeypatch):
    opp = await concern(db)
    goal, _ = await running_goal(db, opp)
    opp.status = 'dismissed'
    await OpportunityRepository(db).save(opp)
    await recover_due(db)
    work = AsyncMock()
    monkeypatch.setattr(AgentService, '_work', work)
    await advance_wake(db, AmbientWake(owner_id='alice', reason='opportunity_revisit', source_ref=f'goal:{goal.id}'))
    current = await db.agent_goals.find_one({'id': goal.id})
    assert current['status'] == 'abandoned' and current['next_run_at'] is None
    work.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_one_goal_preserves_other_alarms_and_cannot_be_undone(db):
    service = AgentService(db)
    goal = AutonomousGoal(owner_id='alice', objective='Controlla', desired_outcome='Esito', status='active')
    await service.repo.create_goal(goal)
    for ref in [f'goal:{goal.id}', 'goal:other', 'delivery:one']:
        await db.ambient_wakes.insert_one({'owner_id': 'alice', 'source_ref': ref, 'status': 'pending'})
    await service.cancel('alice', goal.id)
    assert await db.ambient_wakes.count_documents({'status': 'pending'}) == 2
    goal.prepared_text = 'Risposta tardiva'
    await service.repo.save_goal(goal)
    row = await db.agent_goals.find_one({'id': goal.id})
    assert row['status'] == 'cancelled' and row['prepared_text'] == ''
    assert (await service.answer('alice', goal.id, reply='Continua'))['ok'] is False


@pytest.mark.asyncio
async def test_old_worker_cannot_release_new_workers_lease(db):
    repo = AgentService(db).repo
    assert await repo.claim('alice', 'goal', worker_id='first')
    later = datetime.now(timezone.utc) + timedelta(minutes=6)
    assert await repo.claim('alice', 'goal', worker_id='second', now=later)
    await repo.release('goal', worker_id='first')
    assert (await repo.run_row('goal'))['lease_until'] > later.isoformat()


@pytest.mark.asyncio
@pytest.mark.parametrize('slow_lane', ['market', 'delivery-admission'])
async def test_slow_lane_does_not_block_due_work_and_shutdown_cancels(monkeypatch, slow_lane):
    from ambient import runtime
    from agent import background
    from delivery import admission
    from energy_offers.service import EnergyOfferService
    slow, reached, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async def slow_operation(*args, **kwargs):
        slow.set()
        try: await asyncio.Event().wait()
        finally: cancelled.set()
    async def tick(*args, **kwargs): reached.set()
    monkeypatch.setattr(EnergyOfferService, 'run_due',
                        slow_operation if slow_lane == 'market' else AsyncMock())
    monkeypatch.setattr(admission, 'drain',
                        slow_operation if slow_lane == 'delivery-admission' else AsyncMock())
    monkeypatch.setattr(runtime, 'tick', tick)
    monkeypatch.setattr(runtime, 'read_sources', AsyncMock())
    monkeypatch.setattr(runtime, 'keep_relations_current', AsyncMock())
    monkeypatch.setattr(runtime, 'sweep', AsyncMock())
    monkeypatch.setattr(background, 'recover_due', AsyncMock())
    try:
        await runtime._cycle(object(), 0)
        await asyncio.wait_for(slow.wait(), .5)
        await asyncio.wait_for(reached.wait(), .5)
        task = runtime._jobs[slow_lane]
        await runtime._cycle(object(), 0)
        assert runtime._jobs[slow_lane] is task, 'never overlap a pending lane'
        # Six service lanes (including durable delivery recovery) and two
        # due-work slots. P0 added recovery without an unbounded task per user.
        assert len(runtime._jobs) <= 8
    finally:
        await runtime._stop_jobs()
    assert cancelled.is_set() and not runtime._jobs


@pytest.mark.asyncio
async def test_phone_priority_defers_all_new_background_jobs(monkeypatch):
    from ambient import runtime
    monkeypatch.setattr(runtime, '_a_call_is_live', lambda: True)
    launch = AsyncMock()
    monkeypatch.setattr(runtime, '_launch', launch)
    await runtime._cycle(object(), 0)
    launch.assert_not_called()


@pytest.mark.asyncio
async def test_long_deferral_rearms_without_restart_or_early_reasoning(monkeypatch):
    from life_orchestration import scheduler
    from life_orchestration.service import OrchestrationService
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    service = SimpleNamespace(next_deferral_due_at=AsyncMock(return_value=future))
    calls = []
    async def timer(owner, delay): calls.append(delay)
    monkeypatch.setattr(scheduler, '_stopping', False)
    monkeypatch.setattr(scheduler, '_deferred_tasks', {})
    monkeypatch.setattr(scheduler, '_deferred_due', {})
    original = scheduler._deferred_wake
    monkeypatch.setattr(scheduler, '_deferred_wake', timer)
    assert await scheduler.arm_deferred_timer('alice', service)
    await scheduler._deferred_tasks['alice']
    assert calls == [scheduler.MAX_DEFER_TIMER_SECONDS]
    monkeypatch.setattr(OrchestrationService, 'has_due_deferral', AsyncMock(return_value=False))
    rearm = AsyncMock()
    reason = AsyncMock()
    monkeypatch.setattr(scheduler, 'arm_deferred_timer', rearm)
    monkeypatch.setattr(scheduler, 'schedule_user_reasoning', reason)
    await original('alice', 0)
    rearm.assert_awaited_once_with('alice')
    reason.assert_not_awaited()


@pytest.mark.asyncio
async def test_earlier_deferral_replaces_the_old_timer(monkeypatch):
    from life_orchestration import scheduler
    monkeypatch.setattr(scheduler, '_stopping', False)
    monkeypatch.setattr(scheduler, '_deferred_tasks', {})
    monkeypatch.setattr(scheduler, '_deferred_due', {})
    service = SimpleNamespace(next_deferral_due_at=AsyncMock(return_value=(datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()))
    await scheduler.arm_deferred_timer('alice', service)
    old = scheduler._deferred_tasks['alice']
    assert not await scheduler.arm_deferred_timer('alice', service)
    service.next_deferral_due_at.return_value = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()
    assert await scheduler.arm_deferred_timer('alice', service)
    new = scheduler._deferred_tasks['alice']
    assert old is not new
    new.cancel()
    await asyncio.gather(old, new, return_exceptions=True)


@pytest.mark.asyncio
async def test_expiry_wakes_waiting_goal_without_new_source_or_model_call(db, monkeypatch):
    opp = await concern(db)
    goal, _ = await running_goal(db, opp)
    expiry = datetime.now(timezone.utc) + timedelta(hours=2)
    # Same revision: the passing of time itself must invalidate the work.
    await db.opportunities.update_one({'id': opp.id}, {'$set': {'valid_until': expiry.isoformat()}})
    decide = AsyncMock()
    monkeypatch.setattr(reasoning, 'decide_goal', decide)
    await drain(db)
    assert (await db.opportunities.find_one({'id': opp.id}))['agent_review_due'] == expiry.isoformat()
    assert (await db.agent_goals.find_one({'id': goal.id})).get('source_review_pending') is None
    await drain(db, now=expiry + timedelta(seconds=1))
    current = await db.agent_goals.find_one({'id': goal.id})
    assert current['source_review_pending'] == goal.opportunity_revision
    decide.assert_not_awaited()


@pytest.mark.asyncio
async def test_source_change_during_verification_cannot_publish_old_result(db):
    from agent.models import AgentRun
    opp = await concern(db)
    goal, plan = await running_goal(db, opp)
    opp.semantic_summary = 'Nuove condizioni mentre ORA verifica'
    await OpportunityRepository(db).save(opp)
    result = await AgentService(db)._close('alice', goal, plan,
        AgentRun(owner_id='alice', goal_id=goal.id), 'completed', 'Vecchio confronto')
    assert result['state'] == 'source_changed'
    current = await db.agent_goals.find_one({'id': goal.id})
    assert current['status'] == 'active' and not current['prepared_text']
    assert (await db.opportunities.find_one({'id': opp.id}))['status'] == 'active'


@pytest.mark.asyncio
async def test_ordinary_answer_cannot_satisfy_an_authority_request(db):
    opp = await concern(db)
    goal, plan = await running_goal(db, opp)
    plan.steps = [ActionStep(intent='Autorizza la modifica', step_type='ask_user',
        ask_kind='authority', status='blocked')]
    service = AgentService(db)
    await service.repo.save_plan(plan)
    assert (await service.answer('alice', goal.id, reply='La data è lunedì'))['reason'] == 'question_not_open'
    assert (await service.repo.get_goal('alice', goal.id)).requires_user_authority


@pytest.mark.asyncio
async def test_exhausted_wake_is_terminal_and_cancelled_wake_cannot_revive(db, monkeypatch):
    from ambient import runtime
    from ambient.models import WakeOutcome
    from ambient.repository import AmbientRepository, MAX_ATTEMPTS
    repo = AmbientRepository(db)
    wake = AmbientWake(owner_id='alice', reason='ambient_review', attempts=MAX_ATTEMPTS - 1,
        scheduled_for=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat())
    await repo.schedule(wake)
    monkeypatch.setattr(runtime, '_handle', AsyncMock(return_value=WakeOutcome(
        wake_id=wake.id, reason=wake.reason, retry_after_seconds=60)))
    assert (await runtime.tick(db))['failed'] == 1
    assert (await repo.get_wake(wake.id)).status == 'failed'
    other = AmbientWake(owner_id='alice', reason='ambient_review', source_ref='another',
        scheduled_for=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat())
    await repo.schedule(other)
    claimed = await repo.claim_due(worker_id='old')
    await repo.cancel_for('alice', source_ref='another')
    await repo.release(claimed.id, when=datetime.now(timezone.utc).isoformat(), worker_id='old')
    await repo.complete(claimed.id, worker_id='old')
    assert (await repo.get_wake(other.id)).status == 'cancelled'


@pytest.mark.asyncio
async def test_last_crashed_wake_releases_identity_after_lease_expiry(db):
    from ambient.repository import AmbientRepository, MAX_ATTEMPTS
    repo = AmbientRepository(db)
    wake = AmbientWake(owner_id='alice', reason='ambient_review', status='claimed', attempts=MAX_ATTEMPTS,
        lease_until=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat())
    await repo.schedule(wake)
    assert await repo.claim_due(worker_id='new') is None
    assert (await repo.get_wake(wake.id)).status == 'failed'


@pytest.mark.asyncio
async def test_far_future_wake_survives_until_due_even_after_rescheduling(db):
    from ambient.repository import AmbientRepository, WAKE_RETENTION_DAYS
    repo = AmbientRepository(db)
    due = datetime.now(timezone.utc) + timedelta(days=30)
    wake = AmbientWake(owner_id='alice', reason='ambient_review', scheduled_for=due.isoformat())
    await repo.schedule(wake)
    row = await db.ambient_wakes.find_one({'id': wake.id})
    assert row['expires_at'].replace(tzinfo=timezone.utc) >= due + timedelta(days=WAKE_RETENTION_DAYS, milliseconds=-1)
    later = due + timedelta(days=30)
    await repo.reschedule(wake.id, when=later.isoformat())
    row = await db.ambient_wakes.find_one({'id': wake.id})
    assert row['expires_at'].replace(tzinfo=timezone.utc) >= later + timedelta(days=WAKE_RETENTION_DAYS, milliseconds=-1)
