"""Real presentation/persistence wiring, offline database fixtures, no live AI/weather."""
from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import AgentEvidence, ResultProvenance
from agent.service import AgentService
from situations.followup import arrange_followup
from situations.models import SituationState
from situations.repository import SituationRepository

OWNER = 'home-v108-owner'
SID = 'sit_home_v108'
HEADLINE = 'Esito simulato: è il momento di verificare i capi e raccoglierli.'


async def setup(monkeypatch):
    monkeypatch.setenv('AMBIENT_RUNTIME', '1')
    db = AsyncMongoMockClient().test
    await db.agent_goals.create_index('id', unique=True)
    await db.agent_runs.create_index('goal_id', unique=True)
    await db.ambient_wakes.create_index('identity', unique=True)
    state = SituationState(id=SID, user_id=OWNER, summary='Panni stesi ad asciugare',
        semantic_kind='Panni stesi', icon_key='shirt', source_refs=['user_conversation'],
        attention_intent='Valutare il momento utile per raccoglierli.')
    await SituationRepository(db).insert(state)
    due = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    arranged = await arrange_followup(db, OWNER, situation_id=SID, expected_revision=1,
        check_at=due, purpose='Verificare le condizioni e il risultato.',
        completion_when='Le evidenze indicano che è il momento di raccoglierli.',
        notify_when='Un rischio richiede di intervenire prima.')
    assert arranged['ok']
    return db, AgentService(db), arranged['goal_id'], due


async def publish(db, gid, *, owner=OWNER, real=True, source='connected_provider', status='succeeded'):
    stamp = datetime.now(timezone.utc).isoformat()
    await db.agent_journal.insert_one({'owner_id': owner, 'goal_id': gid, 'at': stamp,
        'kind': 'step_done', 'note': 'Esito simulato per collaudo.',
        'detail': {'status': status, 'really_happened': real, 'came_from': source}})
    await db.agent_updates.insert_one({'owner_id': OWNER, 'goal_id': gid, 'at': stamp,
        'outcome': 'inform_user', 'headline': HEADLINE, 'refs': [f'journal:{stamp}']})


@pytest.mark.asyncio
async def test_pending_watch_is_not_an_update_but_detail_preserves_schedule(monkeypatch):
    db, service, gid, due = await setup(monkeypatch)
    before = await db.situations.find_one({'user_id': OWNER, 'id': SID})
    assert await service.for_home(OWNER) == []
    detail = await service.for_detail(OWNER, gid)
    assert detail['what'] == 'Panni stesi'
    assert detail['icon_key'] == 'shirt'
    assert detail['source'] == 'Una tua conversazione'
    assert detail['progress_kind'] == 'scheduled'
    assert detail['show_in_updates'] is False
    assert detail['detected'] == ''
    assert detail['already_done'] == ''
    assert detail['state'] == 'Controllo programmato.'
    assert 'Prossimo controllo:' in detail['next_step']
    assert (await db.agent_goals.find_one({'id': gid}))['next_run_at'] == due
    assert await db.situations.find_one({'user_id': OWNER, 'id': SID}) == before
    assert await db.ambient_wakes.count_documents({}) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('proof', ['missing', 'foreign_owner', 'simulated', 'failed', 'only_user_statement'])
async def test_unproven_headline_never_becomes_update(monkeypatch, proof):
    db, service, gid, _ = await setup(monkeypatch)
    if proof == 'missing':
        await db.agent_updates.insert_one({'owner_id': OWNER, 'goal_id': gid,
            'at': datetime.now(timezone.utc).isoformat(), 'outcome': 'inform_user',
            'headline': HEADLINE, 'refs': ['journal:missing']})
    else:
        await publish(db, gid, owner='other-owner' if proof == 'foreign_owner' else OWNER,
            real=proof != 'simulated', source='user_statement' if proof == 'only_user_statement' else 'connected_provider',
            status='failed' if proof == 'failed' else 'succeeded')
    assert await service.for_home(OWNER) == []


@pytest.mark.asyncio
async def test_executed_work_alone_is_not_automatically_a_useful_update(monkeypatch):
    db, service, gid, _ = await setup(monkeypatch)
    await publish(db, gid)
    await db.agent_updates.delete_many({})
    assert await service.for_home(OWNER) == []


@pytest.mark.asyncio
async def test_proven_visibility_decision_reaches_home_and_detail_as_same_result(monkeypatch):
    db, service, gid, due = await setup(monkeypatch)
    await publish(db, gid)
    cards = await service.for_home(OWNER)
    assert len(cards) == 1
    assert cards[0]['state'] == HEADLINE
    assert cards[0]['what'] == 'Panni stesi'
    assert cards[0]['progress_kind'] == 'update'
    assert cards[0]['show_in_updates'] is True
    assert cards[0]['detected'] == ''
    assert cards[0]['already_done'] == ''
    assert (await service.for_detail(OWNER, gid))['state'] == HEADLINE
    assert (await db.agent_goals.find_one({'id': gid}))['next_run_at'] == due


@pytest.mark.asyncio
async def test_broken_schedule_remains_visible_instead_of_silently_disappearing(monkeypatch):
    db, service, gid, _ = await setup(monkeypatch)
    await db.ambient_wakes.delete_many({})
    cards = await service.for_home(OWNER)
    assert len(cards) == 1 and cards[0]['progress_kind'] == 'problem'
    assert 'recuperato' in cards[0]['state']
    assert cards[0]['next_step'] == ''


@pytest.mark.asyncio
async def test_disabled_runtime_remains_visible(monkeypatch):
    db, service, gid, _ = await setup(monkeypatch)
    monkeypatch.setenv('AMBIENT_RUNTIME', '0')
    cards = await service.for_home(OWNER)
    assert len(cards) == 1 and cards[0]['progress_kind'] == 'problem'
    assert 'disattivati' in cards[0]['state']


@pytest.mark.asyncio
async def test_removed_situation_does_not_reappear_as_an_update(monkeypatch):
    db, service, gid, _ = await setup(monkeypatch)
    await publish(db, gid)
    await db.situations.update_one({'user_id': OWNER, 'id': SID}, {'$set': {'status': 'cancelled'}})
    assert await service.for_home(OWNER) == []
    assert await service.for_home('another-owner') == []


@pytest.mark.asyncio
async def test_overdue_watch_is_not_hidden_as_future_work(monkeypatch):
    db, service, gid, _ = await setup(monkeypatch)
    due = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    await db.agent_goals.update_one({'id': gid}, {'$set': {'next_run_at': due}})
    await db.ambient_wakes.update_many({'owner_id': OWNER}, {'$set': {'scheduled_for': due}})
    cards = await service.for_home(OWNER)
    assert len(cards) == 1 and cards[0]['progress_kind'] == 'problem'
    assert 'in ritardo' in cards[0]['state']


@pytest.mark.asyncio
async def test_user_need_remains_actionable(monkeypatch):
    db, service, gid, _ = await setup(monkeypatch)
    await db.agent_goals.update_one({'id': gid}, {'$set': {'requires_user_input': True, 'status': 'waiting'}})
    cards = await service.for_home(OWNER)
    assert len(cards) == 1 and cards[0]['progress_kind'] == 'needs_input'
    assert cards[0]['needs_you']
