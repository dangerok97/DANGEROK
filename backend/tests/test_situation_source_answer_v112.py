"""Replay the reported source-read/scheduling contradiction.

Model decisions and Gmail responses are scripted. The real cognitive loop,
capability dispatch, owner-scoped Situation gate and final response are tested.
These tests do not prove autonomous notification delivery or a real shipment.
"""
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.ai_core.models import CognitiveDecision
from conversation_engine.models import ConversationSession
from shipping import caps
from situations.models import SituationState
from situations.repository import SituationRepository
from situations.turn_followup import FollowupTurnGate, verified_readbacks

REF = 'mail:v112-message'
BODY = 'Il tuo pacco è stato spedito ed è in arrivo il giorno 09/10/2026.'
QUESTION = 'Devono arrivarmi pacchi?'


async def setup_case(monkeypatch):
    monkeypatch.setenv('AMBIENT_RUNTIME', '1')
    db = AsyncMongoMockClient().test
    session = ConversationSession(user_id='v112-owner', meta={'ui_mode': 'ai_core', 'ai_core': {}})
    situation = SituationState(
        id='sit_v112_package', user_id=session.user_id,
        summary='Pacco segnalato in una email personale.',
        attention_intent='Seguire eventuali aggiornamenti sulla consegna.',
    )
    await SituationRepository(db).insert(situation)
    exact = AsyncMock(return_value={
        'status': 'ok', 'message_ref': 'v112-message', 'subject': 'CONSEGNA AMAZON',
        'sender_relationship': 'self', 'body_excerpt': BODY,
        'source': 'gmail',
    })
    monkeypatch.setattr(caps, '_read_exact_message', exact)
    return db, session, situation, exact


@pytest.mark.asyncio
async def test_status_question_returns_sourced_date_without_creating_a_monitor(monkeypatch):
    db, session, situation, read = await setup_case(monkeypatch)
    calls = 0

    async def decide(system, payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {'response_mode': 'tool', 'tool_call': {
                'capability': 'get_shipment_status',
                'arguments': {'message_ref': 'v112-message'},
            }}
        return {
            'response_mode': 'answer',
            'message_to_user': 'Nella tua email è indicato un pacco spedito con arrivo previsto il 09/10/2026. Non è una conferma del corriere.',
            'situation_update': {'operation': 'none'},
            'situation_followup': {
                'disposition': 'status_only', 'situation_id': situation.id,
                'reason': 'La domanda chiede cosa riporta la fonte, non di riparare un promemoria.',
                'evidence_refs': [REF],
            },
        }

    result = await run_cognitive_loop(sess=session, user_message=QUESTION, db=db, decision_fn=decide)
    assert result.ok
    assert '09/10/2026' in result.ora_text
    assert 'Non risulta confermato' not in result.ora_text
    assert 'Non è una conferma del corriere' in result.ora_text
    assert read.await_count == 1
    assert await db.situations.count_documents({}) == 1
    assert await db.agent_goals.count_documents({}) == 0
    assert await db.ambient_wakes.count_documents({}) == 0
    kept = await SituationRepository(db).get(session.user_id, situation.id)
    assert kept.attention_intent == situation.attention_intent
    assert kept.revision == situation.revision


@pytest.mark.asyncio
async def test_failed_followup_keeps_exact_source_instead_of_erasing_the_answer(monkeypatch):
    db, session, situation, read = await setup_case(monkeypatch)
    calls = 0

    async def decide(system, payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {'response_mode': 'tool', 'tool_call': {
                'capability': 'get_shipment_status',
                'arguments': {'message_ref': 'v112-message'},
            }}
        return {'response_mode': 'answer', 'message_to_user': 'Ti avviso: è tutto sotto controllo.'}

    result = await run_cognitive_loop(sess=session, user_message=QUESTION, db=db, decision_fn=decide)
    assert result.ok
    assert BODY in result.ora_text
    assert 'La tua email' in result.ora_text
    assert 'Non risulta ancora attivo un controllo automatico' in result.ora_text
    assert 'è tutto sotto controllo' not in result.ora_text
    assert await db.agent_goals.count_documents({}) == 0
    assert await db.ambient_wakes.count_documents({}) == 0


def test_status_only_requires_current_successful_adapter_evidence():
    gate = FollowupTurnGate(None, 'owner')
    gate.pending = [{'situation_id': 's1', 'follow_up': {'status': 'not_scheduled'}}]
    decision = CognitiveDecision.model_validate({
        'response_mode': 'answer', 'message_to_user': 'La fonte riporta una data.',
        'situation_followup': {'disposition': 'status_only', 'reason': 'Solo stato',
                               'evidence_refs': [REF]},
    })
    read = {'kind': 'tool', 'name': 'registered_reader', 'status': 'ok',
            'payload': {'factual_readback': {'ref': REF, 'label': 'Fonte', 'text': BODY}},
            'provenance': [REF]}
    assert gate.accepts_final(decision, QUESTION, [read])
    assert not gate.accepts_final(decision, QUESTION, [])
    assert not gate.accepts_final(decision, QUESTION, [{**read, 'status': 'error'}])
    assert not gate.accepts_final(decision, QUESTION, [{**read, 'kind': 'system'}])
    assert not gate.accepts_final(decision, QUESTION, [{**read, 'provenance': ['mail:other']}])
    # The previous successful source must not leak into a later failed turn.
    assert BODY not in gate.failure_text()
    # Candidate headlines are not an inspected body or a verified date.
    candidates = {'kind': 'tool', 'status': 'ok', 'provenance': [REF],
                  'payload': {'recent_message_candidates': [{'subject': 'Consegna'}]}}
    assert not gate.accepts_final(decision, QUESTION, [candidates])


def test_readback_is_bounded_and_extracts_no_fictitious_tracking_status():
    exact = {'status': 'ok', 'message_ref': 'v112-message', 'subject': 'CONSEGNA AMAZON',
             'sender_relationship': 'self', 'body_excerpt': BODY}
    readback = caps._factual_readback(exact)
    assert readback['text'] == BODY
    assert readback['ref'] == REF
    assert 'La tua email' in readback['label']
    assert 'Amazon ha confermato' not in readback['label']
    assert caps._factual_readback({'status': 'unavailable'}) is None
    assert caps._factual_readback({**exact, 'body_excerpt': ''}) is None
    obs = {'kind': 'tool', 'status': 'ok', 'provenance': [REF],
           'payload': {'factual_readback': readback}}
    assert len(verified_readbacks([obs, obs])) == 1


@pytest.mark.asyncio
async def test_failed_mail_refresh_is_not_claimed_to_be_fresh(monkeypatch):
    monkeypatch.setattr(caps, '_refresh_mail', AsyncMock(return_value={
        'connected': True, 'refresh': [{'ok': False, 'reason': 'sync_failed'}],
    }))
    monkeypatch.setattr(caps, '_recent_mail_evidence', AsyncMock(return_value=[]))
    monkeypatch.setattr(caps, '_active_situations', AsyncMock(return_value=[]))
    result = await caps.get_shipment_status({}, {'db': AsyncMongoMockClient().test, 'user_id': 'owner'})
    assert result.status == 'partial'
    assert result.payload['status'] == 'refresh_failed'
    assert result.payload['refresh_complete'] is False
    assert result.payload['live_carrier_tracking'] is False
