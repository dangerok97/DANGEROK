import copy
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from pymongo.errors import DuplicateKeyError
from opportunities.work import update_work, evidence_labels

class Collection:
    def __init__(self): self.rows = {}
    async def find_one(self, query): return copy.deepcopy(self.rows.get(query.get('_id')))
    async def insert_one(self, row):
        if row['_id'] in self.rows: raise DuplicateKeyError('duplicate')
        self.rows[row['_id']] = copy.deepcopy(row)
    async def update_one(self, query, change):
        row = self.rows.get(query.get('_id'))
        allowed = query.get('status', {}).get('$in')
        if row is None or (allowed and row['status'] not in allowed): return SimpleNamespace(modified_count=0)
        row.update(change['$set']); return SimpleNamespace(modified_count=1)

@pytest.fixture
def setup(monkeypatch):
    orch = SimpleNamespace(get=AsyncMock(return_value={'ok': False}), start=AsyncMock(return_value={'ok': True, 'session_id': 'session', 'question': 'Quale data?', 'ora_text': 'Manca la data'}), message=AsyncMock(return_value={'ok': True, 'session_id': 'session', 'ora_text': 'Controllato'}))
    monkeypatch.setitem(sys.modules, 'conversation_engine.ai_core.orchestrator', SimpleNamespace(AICoreOrchestrator=lambda db: orch))
    db = SimpleNamespace(update_work=Collection(), opportunities=SimpleNamespace(update_one=AsyncMock()))
    opp = SimpleNamespace(id='opp_1234', semantic_summary='Da verificare', what_ora_can_do='Controlla', evidence=[])
    return db, opp, orch

@pytest.mark.asyncio
async def test_repeated_start_resumes_same_work(setup):
    db, opp, orch = setup
    first = await update_work(db, 'alice', opp, start=True)
    second = await update_work(db, 'alice', opp, start=True)
    assert first == second
    assert first['status'] == 'needs_user'
    assert orch.start.await_count == 1
    assert '_id' not in first and 'owner_id' not in first

@pytest.mark.asyncio
async def test_owner_isolation_and_reply_session(setup):
    db, opp, orch = setup
    await update_work(db, 'alice', opp, start=True)
    assert await update_work(db, 'bob', opp) == {'status': 'not_started'}
    result = await update_work(db, 'alice', opp, start=True, reply='Domani')
    assert result['status'] == 'ready'
    orch.message.assert_awaited_once_with('alice', 'session', text='Domani')

@pytest.mark.asyncio
async def test_failure_does_not_restart_work(setup):
    db, opp, orch = setup
    orch.start.side_effect = RuntimeError('provider down')
    with pytest.raises(Exception): await update_work(db, 'alice', opp, start=True)
    result = await update_work(db, 'alice', opp, start=True)
    assert result['status'] == 'failed'
    assert orch.start.await_count == 1

@pytest.mark.asyncio
async def test_running_claim_prevents_second_execution(setup):
    db, opp, orch = setup
    from datetime import datetime, timezone
    await db.update_work.insert_one({'_id': 'alice:opp_1234', 'owner_id': 'alice', 'status': 'running', 'started_at': datetime.now(timezone.utc).isoformat()})
    result = await update_work(db, 'alice', opp, start=True)
    assert result['status'] == 'running'
    orch.start.assert_not_awaited()

def test_same_evidence_not_counted_twice():
    e = SimpleNamespace(kind='calendar', ref='event1', summary='Appuntamento')
    assert evidence_labels([e, e]) == ['Appuntamento']

@pytest.mark.asyncio
async def test_external_session_continuation_is_visible(setup):
    db, opp, orch = setup
    await update_work(db, 'alice', opp, start=True)
    orch.get.return_value = {'ok': True, 'session_id': 'session', 'ora_text': 'Nuovo esito'}
    result = await update_work(db, 'alice', opp)
    assert result['result']['ora_text'] == 'Nuovo esito'
    assert result['status'] == 'ready'
