from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from opportunities.snapshot import _calendar_overlaps
from opportunities import reasoning

NOW=datetime(2026,9,28,tzinfo=timezone.utc)

def test_overlap_uses_intersection_not_start_difference():
    rows=[{'ref':'a','starts_at':'2026-09-29T10:00:00+02:00','ends_at':'2026-09-29T11:00:00+02:00'},
          {'ref':'b','starts_at':'2026-09-29T08:15:00+00:00','ends_at':'2026-09-29T09:15:00+00:00'}]
    facts=_calendar_overlaps(rows,NOW)
    assert len(facts)==1 and facts[0]['overlap_minutes']==45
    rows[1]['starts_at']='2026-09-29T09:00:00+00:00'
    assert _calendar_overlaps(rows,NOW)==[]
    rows[0]['all_day']=True
    rows[1]['starts_at']='2026-09-29T08:15:00+00:00'
    assert _calendar_overlaps(rows,NOW)==[]

@pytest.mark.asyncio
async def test_only_verified_corrected_proposals_leave_scan(monkeypatch):
    draft={'opportunities':[{'identity_key':'overlap','why_it_matters':'15 minuti'}]}
    corrected={'verified':True,'opportunities':[{'identity_key':'overlap','why_it_matters':'45 minuti'}]}
    ask=AsyncMock(side_effect=[draft,corrected]);monkeypatch.setattr(reasoning,'_ask_model',ask)
    result=await reasoning.scan({'temporal':{'calendar_overlaps':[{'overlap_minutes':45}]}},already_raised=[])
    assert result==corrected and ask.await_count==2

@pytest.mark.asyncio
async def test_audit_failure_is_unavailable_not_unchecked_advice(monkeypatch):
    monkeypatch.setattr(reasoning,'_ask_model',AsyncMock(side_effect=[{'opportunities':[{'identity_key':'x'}]},None]))
    assert await reasoning.scan({},already_raised=[]) is None

@pytest.mark.asyncio
async def test_audit_cannot_invent_new_concern(monkeypatch):
    monkeypatch.setattr(reasoning,'_ask_model',AsyncMock(return_value={'verified':True,'opportunities':[{'identity_key':'new'}]}))
    assert await reasoning.audit_proposals({}, {'opportunities':[{'identity_key':'old'}]}) is None

@pytest.mark.asyncio
async def test_silence_does_not_trigger_extra_model_call(monkeypatch):
    ask=AsyncMock(return_value={'opportunities':[]});monkeypatch.setattr(reasoning,'_ask_model',ask)
    assert (await reasoning.scan({},already_raised=[]))['opportunities']==[]
    ask.assert_awaited_once()

@pytest.mark.asyncio
async def test_goal_admission_reads_cited_home_details_with_owner_scope(monkeypatch):
    from home.manual_event import create_manual_event
    from agent.service import AgentService
    from agent import reasoning as agent_reasoning
    from datetime import timedelta
    db=AsyncMongoMockClient().test
    at=datetime.now(timezone.utc)+timedelta(days=1)
    event=await create_manual_event(db,'alice',title='Prova',start=at.isoformat(),end=(at+timedelta(hours=1)).isoformat(),
        tz_name='Europe/Rome',description='Sportello aperto solo 10-11')
    decide=AsyncMock(return_value={'outcome':'no_goal'})
    monkeypatch.setattr(agent_reasoning,'decide_goal',decide)
    await AgentService(db).consider('alice',situation={},source_refs=['calendar:'+event['id']])
    payload=decide.call_args.args[0]
    assert payload['source_context'][0]['preparation_notes']=='Sportello aperto solo 10-11'
    await AgentService(db).consider('bob',situation={},source_refs=['calendar:'+event['id']])
    assert decide.call_args.args[0]['source_context']==[]
    assert decide.call_args.args[0]['source_context_unavailable']


def test_change_notice_does_not_erase_source_provenance():
    from opportunities.snapshot import evidence_refs
    assert evidence_refs({"calendar":[{"ref":"calendar:event"}],
        "what_changed":[{"ref":"calendar:event","what_moved":"calendar:event.updated"}]})["calendar:event"]=="calendar_event"
