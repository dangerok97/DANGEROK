"""Regression: saved intent is not scheduled work; use real persistence/dispatch.

External providers and model judgement are not exercised by these tests. The
checks prove ownership, actual Mongo writes, dedupe, read-back and runtime wiring.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.repository import AgentRepository
from ambient.repository import AmbientRepository
from ambient.service import AmbientService
from situations.models import SituationState, SituationUpdate
from situations.repository import SituationRepository
from situations.service import SituationService
from situations.followup import arrange_followup, read_followup, goal_id_for, get_situation_followup

OWNER = 'followup-owner'
SID = 'sit_followup_v98'


async def setup(monkeypatch):
    monkeypatch.setenv('AMBIENT_RUNTIME', '1')
    db = AsyncMongoMockClient().test
    # Use exactly the production identities, including the concurrent-run lock.
    await db.agent_goals.create_index('id', unique=True)
    await db.agent_runs.create_index('goal_id', unique=True)
    await db.ambient_wakes.create_index('identity', unique=True)
    state = SituationState(id=SID, user_id=OWNER, summary='Ho steso i panni all’aperto.',
        attention_intent='Rivalutare le condizioni e segnalare il momento utile.',
        next_check_summary='Ricontrollerò in seguito.')
    await SituationRepository(db).insert(state)
    return db


def args(**extra):
    return dict(situation_id=SID, expected_revision=1,
        check_at=(datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat(),
        purpose='Rileggere le condizioni rilevanti al prossimo checkpoint.',
        completion_when='Quando le evidenze indicano che è arrivato il momento utile per concludere.',
        notify_when='Segnalare prima un rischio che cambia cosa conviene fare.', **extra)


@pytest.mark.asyncio
async def test_saved_intention_and_prose_are_not_a_schedule(monkeypatch):
    db = await setup(monkeypatch)
    out = await read_followup(db, OWNER, SID)
    assert out['status'] == 'not_scheduled'
    assert out['next_check_at'] is None
    assert out['last_checked_at'] is None


@pytest.mark.asyncio
async def test_creates_real_goal_and_wake_and_survives_new_reader(monkeypatch):
    db = await setup(monkeypatch)
    out = await arrange_followup(db, OWNER, **args())
    assert out['ok'] and out['status'] == 'scheduled'
    goal = await db.agent_goals.find_one({'owner_id': OWNER, 'id': out['goal_id']})
    wake = await db.ambient_wakes.find_one({'owner_id': OWNER, 'source_ref': f"goal:{out['goal_id']}"})
    assert goal is not None and wake is not None
    assert goal['next_run_at'] == wake['scheduled_for'] == out['next_check_at']
    assert goal['source_refs'] == [f'situation:{SID}']
    again = await get_situation_followup({'situation_id': SID}, {'db': db, 'user_id': OWNER})
    assert again.payload['next_check_at'] == out['next_check_at']
    assert again.payload['last_checked_at'] is None, 'scheduling is not execution'
    assert again.payload['delivery_channel'] == 'in_app'


@pytest.mark.asyncio
async def test_status_query_and_duplicate_schedule_do_not_postpone(monkeypatch):
    db = await setup(monkeypatch)
    first = await arrange_followup(db, OWNER, **args())
    changed = args()
    changed['check_at'] = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    second = await arrange_followup(db, OWNER, **changed)
    assert second['reused'] is True
    assert second['next_check_at'] == first['next_check_at']
    assert await db.agent_goals.count_documents({}) == 1
    assert await db.ambient_wakes.count_documents({}) == 1


@pytest.mark.asyncio
async def test_owner_isolation_and_stale_revision(monkeypatch):
    db = await setup(monkeypatch)
    assert (await read_followup(db, 'someone-else', SID))['status'] == 'unavailable'
    wrong = await arrange_followup(db, 'someone-else', **args())
    assert wrong['ok'] is False
    stale = args(); stale['expected_revision'] = 2
    assert (await arrange_followup(db, OWNER, **stale))['error'] == 'revision_conflict'
    assert await db.agent_goals.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('value', ['tomorrow', '2026-10-01T10:00:00', '2000-01-01T00:00:00Z'])
async def test_invalid_or_ambiguous_checkpoint_never_saves(monkeypatch, value):
    db = await setup(monkeypatch)
    invalid = args(); invalid['check_at'] = value
    assert (await arrange_followup(db, OWNER, **invalid))['ok'] is False
    assert await db.agent_goals.count_documents({}) == 0


@pytest.mark.asyncio
async def test_disabled_runtime_is_not_sold_as_monitoring(monkeypatch):
    db = await setup(monkeypatch)
    monkeypatch.setenv('AMBIENT_RUNTIME', '0')
    assert (await arrange_followup(db, OWNER, **args()))['error'] == 'runtime_disabled'
    assert await db.ambient_wakes.count_documents({}) == 0


@pytest.mark.asyncio
async def test_failed_wake_write_is_not_success_and_retry_repairs_same_goal(monkeypatch):
    db = await setup(monkeypatch)
    original = AmbientService.schedule
    monkeypatch.setattr(AmbientService, 'schedule', AsyncMock(return_value=None))
    failed = await arrange_followup(db, OWNER, **args())
    assert failed['ok'] is False and failed['status'] == 'recovery_pending'
    assert failed['next_check_at'] is None
    monkeypatch.setattr(AmbientService, 'schedule', original)
    repaired = await arrange_followup(db, OWNER, **args())
    assert repaired['status'] == 'scheduled'
    assert repaired['goal_id'] == failed['goal_id']
    assert await db.agent_goals.count_documents({}) == 1


@pytest.mark.asyncio
async def test_only_executed_evidence_updates_last_checked(monkeypatch):
    db = await setup(monkeypatch)
    out = await arrange_followup(db, OWNER, **args())
    repo = AgentRepository(db)
    await repo.journal(OWNER, out['goal_id'], kind='waiting', note='Aspetto.')
    assert (await read_followup(db, OWNER, SID))['last_checked_at'] is None
    await repo.journal(OWNER, out['goal_id'], kind='step_done', note='Fonte riletta.',
                       detail={'really_happened': True, 'status': 'succeeded'})
    assert (await read_followup(db, OWNER, SID))['last_checked_at'] is not None


@pytest.mark.asyncio
async def test_due_wake_reaches_existing_agent_without_new_user_message(monkeypatch):
    from agent.background import advance_wake
    from agent.service import AgentService
    from ambient.models import AmbientWake
    db = await setup(monkeypatch)
    out = await arrange_followup(db, OWNER, **args())
    due = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    await db.agent_goals.update_one({'id': out['goal_id']}, {'$set': {'next_run_at': due}})
    doc = await db.ambient_wakes.find_one({'source_ref': f"goal:{out['goal_id']}"}, {'_id': 0})
    advance = AsyncMock(return_value={'state': 'waiting'})
    monkeypatch.setattr(AgentService, 'advance', advance)
    await advance_wake(db, AmbientWake.model_validate(doc))
    advance.assert_awaited_once()
    assert advance.await_args.args == (OWNER, out['goal_id'])
    assert advance.await_args.kwargs['worker_id'].startswith('ambient:')


@pytest.mark.asyncio
async def test_resolve_cancels_dedicated_work_but_preserves_unrelated_goal(monkeypatch):
    db = await setup(monkeypatch)
    out = await arrange_followup(db, OWNER, **args())
    await db.agent_goals.insert_one({'id': 'other-goal', 'owner_id': OWNER, 'status': 'active'})
    await SituationService(db).apply(user_id=OWNER, session_id='test', reasoning_epoch='resolve',
        update=SituationUpdate(operation='resolve', situation_id=SID, expected_revision=1))
    assert (await read_followup(db, OWNER, SID))['status'] == 'stopped'
    assert (await db.agent_goals.find_one({'id': out['goal_id']}))['status'] == 'cancelled'
    assert (await db.agent_goals.find_one({'id': 'other-goal'}))['status'] == 'active'
    assert await db.ambient_wakes.count_documents({'source_ref': f"goal:{out['goal_id']}", 'status': 'pending'}) == 0


@pytest.mark.asyncio
async def test_conversation_context_contains_real_checkpoint(monkeypatch):
    from conversation_engine.ai_core.context_broker import ContextBroker
    db = await setup(monkeypatch)
    out = await arrange_followup(db, OWNER, **args())
    facts = await ContextBroker(db)._situation_facts(OWNER, session_id=None, detailed=False)
    assert out['next_check_at'] in facts[0].statement
    assert 'follow_up=' in facts[0].statement
    assert 'scheduled' in facts[0].statement


def test_tools_are_generic_and_external_authority_is_not_granted():
    from conversation_engine.ai_core.tools.registry import ToolRegistry
    registry = ToolRegistry(None)
    assert registry.get('get_situation_followup').side_effect == 'READ_ONLY'
    assert registry.get('schedule_situation_check').side_effect == 'REVERSIBLE_WRITE'
    required = registry.get('schedule_situation_check').input_schema['required']
    assert 'situation_id' in required
    assert 'completion_when' in required
