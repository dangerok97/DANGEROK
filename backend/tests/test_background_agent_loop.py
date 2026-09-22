"""Regression gates for work continuing without a Home request or device."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
AsyncMongoMockClient = pytest.importorskip("mongomock_motor").AsyncMongoMockClient
from agent.models import AutonomousGoal, AgentEvidence, ResultProvenance
from agent.service import AgentService
from agent.background import recover_due, advance_wake
from ambient.models import AmbientWake
from ambient.runtime import tick

@pytest.fixture
def db(monkeypatch):
    # mongomock 4.x re-finds updated documents by _id after applying projection;
    # excluding _id wrongly returns None. Keep it; production models ignore it.
    import mongomock.collection
    original = mongomock.collection.Collection.find_one_and_update
    def update(self, *args, **kwargs):
        kwargs.pop('projection', None)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(mongomock.collection.Collection, 'find_one_and_update', update)
    return AsyncMongoMockClient().test

async def goal(db, **kw):
    g = AutonomousGoal(owner_id='alice', objective='Verifica appuntamento',
        desired_outcome='Sapere cosa risulta nel calendario', status='active',
        next_run_at=datetime.now(timezone.utc).isoformat(), **kw)
    await db.agent_goals.insert_one(g.model_dump())
    return g

@pytest.mark.asyncio
async def test_due_goal_runs_without_request_and_stops_when_complete(db, monkeypatch):
    g = await goal(db)
    work = AsyncMock()
    async def finish(self, owner, current, run, budget, **kwargs):
        assert run.background
        current.status = 'completed'
        current.completed_at = datetime.now(timezone.utc).isoformat()
        await work(owner, current.id)
        return {'ok': True, 'state': 'completed'}
    monkeypatch.setattr(AgentService, '_work', finish)
    monkeypatch.setattr(AgentService, '_consider_visibility', AsyncMock())
    await db.agent_runs.create_index('goal_id', unique=True)
    assert await recover_due(db) == 1
    assert await recover_due(db) == 0
    out = await tick(db, now=datetime.now(timezone.utc) + timedelta(minutes=1))
    assert out['completed'] == 1
    row = await db.agent_goals.find_one({'id': g.id})
    assert row['status'] == 'completed' and row['next_run_at'] is None
    assert await recover_due(db) == 0
    work.assert_awaited_once_with('alice', g.id)

@pytest.mark.asyncio
async def test_recovery_excludes_legacy_other_users_and_human_waits(db, monkeypatch):
    g = await goal(db, requires_user_authority=True)
    legacy = await goal(db)
    await db.agent_goals.update_one({'id': legacy.id}, {'$unset': {'next_run_at': ''}})
    assert await recover_due(db) == 0
    advance = AsyncMock()
    monkeypatch.setattr(AgentService, 'advance', advance)
    wake = AmbientWake(owner_id='alice', reason='opportunity_revisit', source_ref=f'goal:{g.id}')
    assert (await advance_wake(db, wake)).result == 'waiting_for_person'
    wake.owner_id = 'bob'
    assert (await advance_wake(db, wake)).result == 'goal_closed'
    advance.assert_not_awaited()

@pytest.mark.asyncio
async def test_repeated_stall_has_persisted_limit_and_crash_can_resume(db, monkeypatch):
    g = await goal(db)
    async def broken(*a, **kw): raise RuntimeError('worker died')
    monkeypatch.setattr(AgentService, '_work', broken)
    monkeypatch.setattr(AgentService, '_consider_visibility', AsyncMock())
    await db.agent_runs.create_index('goal_id', unique=True)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            await AgentService(db).advance('alice', g.id, worker_id='ambient:test')
        row = await db.agent_goals.find_one({'id': g.id})
        assert row['next_run_at']  # the due time survived failure
    result = await AgentService(db).advance('alice', g.id, worker_id='ambient:test')
    assert result['state'] == 'background_paused'
    assert (await db.agent_goals.find_one({'id': g.id}))['next_run_at'] is None

@pytest.mark.asyncio
async def test_background_review_reaches_existing_goal_decision(db, monkeypatch):
    from ambient.service import AmbientService
    from opportunities.discovery import OpportunityDiscovery
    from opportunities.surfacing import SurfacingService
    from delivery.service import DeliveryService
    opp = SimpleNamespace(id='opp1', semantic_summary='Orario cambiato', why_it_matters='Verifica',
        why_now='', requires_clarification=False, clarifying_question='', initiative='prepare',
        what_ora_can_do='Controllare', evidence=[])
    scan = SimpleNamespace(created=[opp], updated=[])
    monkeypatch.setattr(OpportunityDiscovery, 'review', AsyncMock(return_value=SimpleNamespace(ran=True, unavailable=False, scan=scan)))
    monkeypatch.setattr(AmbientService, '_note', AsyncMock())
    monkeypatch.setattr(SurfacingService, 'decide', AsyncMock())
    monkeypatch.setattr(DeliveryService, 'evaluate', AsyncMock(return_value=SimpleNamespace(plan=None)))
    consider = AsyncMock(return_value={'outcome': 'create_goal'})
    monkeypatch.setattr(AgentService, 'consider', consider)
    await AmbientService(db).review_life(AmbientWake(owner_id='alice', reason='state_changed'))
    assert consider.await_args.kwargs['opportunity_id'] == 'opp1'
    assert consider.await_args.kwargs['origin'] == 'agent_initiated'

@pytest.mark.asyncio
async def test_calendar_reads_only_current_selected_events(db, monkeypatch):
    # Load the real adapter without home/__init__ importing HTTP/app bootstrap.
    import sys, types
    from pathlib import Path
    import agent
    package = types.ModuleType('home')
    package.__path__ = [str(Path(agent.__file__).resolve().parent.parent / 'home')]
    monkeypatch.setitem(sys.modules, 'home', package)
    from agent.providers import read_calendar
    now = datetime.now(timezone.utc)
    await db.connector_instances.insert_one({'user_id':'alice', 'connector_id':'calendar_google',
        'status':'connected', 'selected_resource_ids':['primary'], 'last_sync_at': now.isoformat()})
    for name, status, ingestion, calendar in [
        ('Current','confirmed','processed','primary'),
        ('Cancelled','cancelled','processed','primary'),
        ('Old','confirmed','superseded','primary'),
        ('Unchanged','confirmed','skipped','primary'),
        ('Not selected','confirmed','processed','other'),
    ]:
        await db.ingestion_events.insert_one({'user_id':'alice','connector_id':'calendar_google',
            'external_id':name,'source_record_type':'calendar_event','ingestion_status':ingestion,
            'ingested_at':now.isoformat(), 'normalized_payload':{k:{'value':v} for k,v in {
                'title':name,'starts_at':(now+timedelta(days=1)).isoformat(),
                'status':status,'calendar_id':calendar}.items()}})
    result = await read_calendar(db, 'alice', None)
    assert len(result.claims) == 1 and 'Current' in result.claims[0].text
    assert result.provenance.source_class == 'internal_observation'
    assert 'non conferma cancellazioni' in result.observation
    assert (await read_calendar(db,'bob',None)).status == 'unavailable'

@pytest.mark.asyncio
async def test_completed_work_stays_visible_only_with_real_evidence(db, monkeypatch):
    g = await goal(db)
    await db.agent_goals.update_one({'id':g.id}, {'$set':{'status':'completed',
        'completed_at':datetime.now(timezone.utc).isoformat(),'rationale':'Verificato sul calendario'}})
    svc = AgentService(db)
    monkeypatch.setattr(svc,'_where_it_really_came_from',AsyncMock(return_value='Calendario'))
    assert await svc.for_home('alice') == []
    evidence = AgentEvidence(owner_id='alice',goal_id=g.id, claim='Appuntamento presente',
        provenance=ResultProvenance(source_class='internal_observation',capability='calendar.read'))
    await svc.evidence.record(evidence)
    cards = await svc.for_home('alice')
    assert cards[0]['state'] == 'Verifica completata'
    assert cards[0]['outcome'] == 'Verificato sul calendario'

@pytest.mark.asyncio
async def test_background_prepares_effect_even_with_standing_authority(db, monkeypatch):
    from agent.models import ActionStep, ActionPlan, AgentRun, AgentBudget
    g = await goal(db)
    svc = AgentService(db)
    step = ActionStep(intent='Sposta appuntamento', step_type='execute', capability_needed='calendar.write')
    plan = ActionPlan(owner_id='alice', goal_id=g.id, steps=[step])
    assessment = SimpleNamespace(effective_outcome='proceed_autonomously', code_reason='', reasoning='', public=lambda: {})
    monkeypatch.setattr(svc, '_authority_for', AsyncMock(return_value=assessment))
    monkeypatch.setattr(svc.authority, 'effective_authority', AsyncMock(return_value=SimpleNamespace(may_execute=True, reason_code='', public=lambda: {})))
    execute = AsyncMock(return_value=SimpleNamespace(observation='Preparato'))
    monkeypatch.setattr(svc.executor, 'run', execute)
    monkeypatch.setattr(svc, '_note_ambient', AsyncMock())
    out = await svc._do_step('alice', g, plan, step, AgentRun(owner_id='alice', background=True), AgentBudget(), language='it')
    assert out['state'] == 'awaiting_authority'
    assert execute.await_args.kwargs['may_touch_the_world'] is False
    assert (await db.agent_goals.find_one({'id':g.id}))['requires_user_authority'] is True

@pytest.mark.asyncio
async def test_cooldown_keeps_a_wake_for_unreviewed_changes(db, monkeypatch):
    from ambient.service import AmbientService
    from opportunities.discovery import OpportunityDiscovery
    from opportunities.changes import ChangeLog
    monkeypatch.setattr(OpportunityDiscovery, 'review', AsyncMock(return_value=SimpleNamespace(ran=False)))
    monkeypatch.setattr(ChangeLog, 'pending', AsyncMock(return_value=[object()]))
    result = await AmbientService(db).review_life(AmbientWake(owner_id='alice', reason='state_changed'))
    assert result.retry_after_seconds == 120
