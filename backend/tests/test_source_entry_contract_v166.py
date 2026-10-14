"""The entry exposes resource access, not a decision about its contents."""
import json
import pytest
from test_general_source_core_v166 import world, OWNER, BODY
from conversation_engine.ai_core.source_activation import (
    SourceActivation, content_access_for, run_source_turn,
)
from conversation_engine.ai_core.loop import _has_positive_calendar_mutation_claim
from conversation_engine.ai_core.tools.registry import ToolRegistry


@pytest.mark.parametrize('source_type', ['email', 'calendar', 'documents'])
def test_source_families_offer_the_same_read_contract_without_action_routing(source_type):
    access = content_access_for('signal:observed', source_type)
    assert access['reader'] == {
        'capability': 'read_connected_source',
        'arguments': {'source_ref': 'signal:observed'},
    }
    assert access['state'] == 'not_read' and access['reader_supported']
    assert access['metadata_is_content'] is False
    assert 'create_calendar_event' not in json.dumps(access)


def test_unimplemented_source_is_not_advertised_as_readable():
    assert content_access_for('signal:observed', 'health')['reader_supported'] is False


@pytest.mark.asyncio
async def test_loading_an_activation_does_not_read_or_choose_an_effect(world):
    db, signal, body = world
    activation = await SourceActivation.load(db, OWNER, signal.id)
    assert activation.context['content_access']['state'] == 'not_read'
    assert activation.context['content_access']['reader']['arguments']['source_ref'] == 'signal:'+signal.id
    assert activation.context['human_message_present'] is False
    assert activation.context['authority']['chosen_by_user'] is False
    assert activation.tool_outcomes == []
    body.assert_not_awaited()
    assert await db.life_nodes.count_documents({}) == 0


@pytest.mark.asyncio
async def test_content_state_changes_only_after_real_source_read(world):
    db, signal, body = world
    activation = await SourceActivation.load(db, OWNER, signal.id)
    registry = activation.restrict_registry(ToolRegistry(db))
    names = {item['capability'] for item in registry.list_public()}
    assert activation.context['content_access']['reader']['capability'] in names
    result = await registry.execute('read_connected_source',
        {'source_ref': 'signal:'+signal.id}, runtime={'db': db, 'user_id': OWNER, 'user_message': ''})
    assert result.status == 'ok'
    assert activation.context['content_access']['state'] == 'read'
    assert activation.context['content_access']['read_at'] == result.payload['read_at']
    assert BODY not in json.dumps(activation.context)
    assert await db.life_nodes.count_documents({}) == 0


@pytest.mark.asyncio
async def test_actual_payload_contains_exact_resource_access_and_allows_no_action(world):
    db, signal, body = world
    seen = []
    async def decide(system, payload):
        data = json.loads(payload)
        access = data['source_activation']['content_access']
        assert data['user_message'] == ''
        assert not any(t['role'] == 'user' for t in data.get('recent_turns', []))
        assert any('read_connected_source(' in tool for tool in data['available_tools'])
        if not seen:
            assert access['state'] == 'not_read'
            seen.append('read')
            return {'response_mode': 'tool', 'tool_call': access['reader']}
        assert access['state'] == 'read' and BODY in payload
        return {'response_mode': 'answer', 'message_to_user': 'Non ho modificato nulla.'}
    output = await run_source_turn(db, OWNER, signal.id, decision_fn=decide)
    assert output['result'].ok
    assert [row['capability'] for row in output['effects']] == ['read_connected_source']
    assert await db.life_nodes.count_documents({}) == 0
    assert not output['notifications_sent'] and not output['source_settled']


@pytest.mark.parametrize('text', [
    "Non è stato aggiunto al calendario.",
    "Non ho aggiunto nulla al calendario.",
    "L'evento non è stato aggiunto al tuo calendario.",
    "I did not add the event to the calendar.",
])
def test_calendar_truth_guard_does_not_treat_explicit_denial_as_a_write(text):
    assert not _has_positive_calendar_mutation_claim(text)


@pytest.mark.parametrize('text', [
    "Ho aggiunto l'evento al calendario.",
    "L'ho spostato: l'evento è ora alle 18.",
    "Non era nel calendario, quindi l'ho aggiunto al calendario.",
    "I've added the appointment to the calendar.",
])
def test_calendar_truth_guard_still_requires_evidence_for_real_write_claims(text):
    assert _has_positive_calendar_mutation_claim(text)


@pytest.mark.asyncio
async def test_source_no_action_calendar_wording_finishes_without_persist_nudge(world):
    db, signal, body = world
    calls = 0

    async def decide(system, payload):
        nonlocal calls
        calls += 1
        data = json.loads(payload)
        if calls == 1:
            return {
                'response_mode': 'tool',
                'tool_call': data['source_activation']['content_access']['reader'],
            }
        return {
            'response_mode': 'finish',
            'message_to_user': (
                "Non è stato aggiunto nulla al calendario perché la fonte "
                "non conferma alcun impegno."
            ),
        }

    output = await run_source_turn(db, OWNER, signal.id, decision_fn=decide)
    assert output['result'].ok
    assert calls == 2
    assert [row['capability'] for row in output['effects']] == ['read_connected_source']
    events = [str(step.get('event')) for step in (output['result'].trace or {}).get('steps', [])]
    assert 'CALENDAR_PERSIST_NUDGE' not in events
    assert 'CALENDAR_CLAIM_BLOCKED_TERMINAL' not in events
    assert await db.life_nodes.count_documents({}) == 0
