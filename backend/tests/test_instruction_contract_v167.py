"""Contract tests, not rules that choose an action from a life-case label."""
import json
from copy import deepcopy
from unittest.mock import AsyncMock
import pytest
import jsonschema
from conversation_engine.ai_core import instruction_contract as contract
from conversation_engine.ai_core.models import CognitiveDecision
from conversation_engine.ai_core.prompt import COGNITIVE_SYSTEM_PROMPT
from conversation_engine.ai_core.source_activation import SOURCE_INSTRUCTION, run_source_turn
from agent.authority import AuthorityService
from test_general_source_core_v166 import world, OWNER, BODY, action


def compact(monkeypatch):
    monkeypatch.setenv('ORA_CORE_COMPACT_CONTRACT', '1')
    return contract.instruction_surface(legacy=COGNITIVE_SYSTEM_PROMPT,
        source_turn=True, source_instruction=SOURCE_INSTRUCTION)


def test_source_surface_is_off_by_default_and_preserves_legacy_bytes(monkeypatch):
    monkeypatch.delenv('ORA_CORE_COMPACT_CONTRACT', raising=False)
    old = COGNITIVE_SYSTEM_PROMPT + 'FOLLOWUP' + SOURCE_INSTRUCTION
    assert contract.instruction_surface(legacy=COGNITIVE_SYSTEM_PROMPT,
        source_turn=True, source_instruction=SOURCE_INSTRUCTION, followup_instruction='FOLLOWUP') == old


def test_pilot_flag_cannot_change_chat_or_whatsapp_system(monkeypatch):
    compact(monkeypatch)
    assert contract.instruction_surface(legacy=COGNITIVE_SYSTEM_PROMPT,
        source_turn=False, followup_instruction='FOLLOWUP') == COGNITIVE_SYSTEM_PROMPT + 'FOLLOWUP'
    raw = '{ "observations": [], "epistemic_reminder": "legacy" }'
    assert contract.input_surface(raw, source_turn=False) == raw


def test_compact_contract_has_materially_less_text_and_uses_canonical_schema(monkeypatch):
    system = compact(monkeypatch)
    assert len(system) < len(COGNITIVE_SYSTEM_PROMPT + SOURCE_INSTRUCTION) * .35
    assert system.startswith(contract.CORE_PRINCIPLES)
    schema = contract.decision_schema(True)
    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema['properties']['response_mode']['enum'] == list(contract.SOURCE_MODES)
    canonical = CognitiveDecision.model_json_schema()
    for field in contract.SOURCE_FIELDS - {'response_mode'}:
        assert schema['properties'][field] == canonical['properties'][field]
    for name, value in schema.get('$defs', {}).items():
        assert value == canonical['$defs'][name]
    assert 'MemoryCandidate' not in schema.get('$defs', {})
    assert 'SituationUpdate' not in schema.get('$defs', {})


@pytest.mark.parametrize('decision', [
    {'response_mode': 'answer', 'message_to_user': 'Nessun intervento necessario.'},
    {'response_mode': 'ask', 'question': 'Quale sede è corretta?'},
    {'response_mode': 'tool', 'tool_call': {'capability': 'read_connected_source', 'arguments': {'source_ref': 'signal:known'}}},
    {'response_mode': 'context', 'context_need': {'query': 'Impegni collegati già registrati'}},
    {'response_mode': 'finish', 'message_to_user': 'Operazione completata.'},
])
def test_supported_decisions_validate_against_both_contracts(decision):
    jsonschema.validate(decision, contract.decision_schema(True))
    assert CognitiveDecision.model_validate(decision).response_mode == decision['response_mode']


@pytest.mark.parametrize('decision', [
    {'response_mode': 'act'},
    {'response_mode': 'research'},
    {'response_mode': 'answer', 'memory_candidates': [{'summary': 'invented'}]},
    {'response_mode': 'answer', 'situation_update': {'operation': 'create'}},
    {'response_mode': 'answer', 'context_graph_updates': [{}]},
])
def test_unsupported_source_protocol_not_advertised_as_executable(decision):
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(decision, contract.decision_schema(True))


def test_input_projection_preserves_every_evidence_and_tool_contract(monkeypatch):
    compact(monkeypatch)
    data = {'observations': [{'private_content': BODY, 'provenance': ['signal:known']}],
        'current_facts': {'observed_at': '2031-05-01'}, 'recent_turns': [{'text': 'old'}],
        'source_activation': {'content_access': {'state': 'not_read'}},
        'context_facts': [{'ref': 'mem_known', 'statement': 'known'}],
        'available_tools': [{'name': 'new_tool', 'input_schema': {'type': 'object'}}],
        'epistemic_reminder': 'old domain instructions', 'what_ora_can_do': 'old reminder',
        'you_are_being_heard_not_read': 'voice instructions', 'life_os': {'known': True}}
    before = deepcopy(data)
    projected = json.loads(contract.input_surface(json.dumps(data), source_turn=True))
    for key, value in before.items():
        if key not in {'epistemic_reminder', 'what_ora_can_do'}:
            assert projected[key] == value
    assert data == before
    assert not projected['decision_contract']['delivery_available']


@pytest.mark.asyncio
async def test_actual_core_uses_small_contract_and_original_granted_tool(world, monkeypatch):
    db, signal, reader = world
    system = compact(monkeypatch)
    authority = AuthorityService(db)
    await authority.set_mode(OWNER, 'act_within_grants')
    await authority.grant(OWNER, 'calendar.local.write', by='user', effect_scope=['create'])
    calls = []
    async def decide(system, payload):
        parsed = json.loads(payload); calls.append(parsed)
        assert system.startswith(contract.CORE_PRINCIPLES)
        assert len(system) < len(COGNITIVE_SYSTEM_PROMPT) * .35
        assert parsed['user_message'] == ''
        assert 'read_connected_source' in json.dumps(parsed['available_tools'])
        if len(calls) == 1:
            return {'response_mode': 'tool', 'tool_call': {'capability': 'read_connected_source', 'arguments': {'source_ref': 'signal:'+signal.id}}}
        if len(calls) == 2:
            assert BODY in payload
            return {'response_mode': 'tool', 'tool_call': {'capability': 'create_calendar_event', 'arguments': action()}}
        return {'response_mode': 'answer', 'message_to_user': 'Ho registrato il colloquio.'}
    run = await run_source_turn(db, OWNER, signal.id, decision_fn=decide)
    assert run['result'].ok and len(calls) == 3
    assert await db.life_nodes.count_documents({'user_id': OWNER, 'type': 'event'}) == 1
    assert any(e['operation'] == 'created' and e['verified'] for e in run['effects'])
    assert BODY not in json.dumps(run['session'].meta, default=str)
    assert not run['notifications_sent']


@pytest.mark.asyncio
async def test_smaller_instructions_never_expand_existing_authority(world, monkeypatch):
    db, signal, reader = world
    compact(monkeypatch)
    count = 0
    async def decide(system, payload):
        nonlocal count
        count += 1
        if count == 1:
            return {'response_mode': 'tool', 'tool_call': {'capability': 'read_connected_source', 'arguments': {'source_ref': 'signal:'+signal.id}}}
        if count == 2:
            return {'response_mode': 'tool', 'tool_call': {'capability': 'create_calendar_event', 'arguments': action()}}
        return {'response_mode': 'answer', 'message_to_user': 'Non ho l’autorizzazione per effettuare la modifica.'}
    run = await run_source_turn(db, OWNER, signal.id, decision_fn=decide)
    assert await db.life_nodes.count_documents({'user_id': OWNER, 'type': 'event'}) == 0
    assert await db.autonomy_consents.count_documents({}) == 0
    assert not any(e['verified'] for e in run['effects'])


@pytest.mark.asyncio
async def test_unavailable_mutation_is_still_blocked_by_runtime(world, monkeypatch):
    db, signal, reader = world
    compact(monkeypatch)
    async def decide(system, payload):
        return {'response_mode': 'act', 'message_to_user': 'Proposta non eseguibile.'}
    run = await run_source_turn(db, OWNER, signal.id, decision_fn=decide, max_steps=2)
    assert await db.life_nodes.count_documents({}) == 0
    assert await db.agent_action_attempts.count_documents({}) == 0
    assert not run['notifications_sent']
