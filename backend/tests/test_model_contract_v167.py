"""Failover may change provider, not silently leave an explicit model contract."""
import asyncio
import json
import pytest
from llm.model_contract import scoped_model_contract, active_contract, parse_contract
from test_provider_failover_v34 import _manager, _Stub
from test_general_source_core_v166 import world, OWNER


def test_absent_contract_preserves_default_order(monkeypatch):
    monkeypatch.delenv('LLM_PROVIDER', raising=False)
    manager = _manager(gemini=_Stub('gemini'), mistral=_Stub('mistral'))
    before = manager.ordered_names()
    with scoped_model_contract(None):
        assert manager.ordered_names() == before
        assert active_contract() is None


@pytest.mark.parametrize('raw', ['{}', '[]', 'null', '{broken', '{"gemini":null}', '{"gemini":true}', '{"gemini":""}'])
def test_invalid_contract_never_means_unrestricted(raw):
    with pytest.raises(ValueError):
        with scoped_model_contract(raw):
            pytest.fail('invalid configuration reached invocation')
    assert active_contract() is None


@pytest.mark.asyncio
async def test_preference_cannot_escape_explicit_provider_and_model():
    a, b = _Stub('gemini'), _Stub('mistral')
    manager = _manager(gemini=a, mistral=b)
    with scoped_model_contract('{"gemini":"gemini-stub"}'):
        result = await manager.chat(system='s', user='u', user_preference='mistral')
    assert result.provider == 'gemini' and a.calls == 1 and b.calls == 0
    assert active_contract() is None


@pytest.mark.asyncio
async def test_model_configuration_drift_does_not_fall_back_outside_contract():
    from llm.errors import LLMNotConfigured
    a, b = _Stub('gemini'), _Stub('mistral')
    manager = _manager(gemini=a, mistral=b)
    with scoped_model_contract('{"gemini":"different-model"}'):
        with pytest.raises(LLMNotConfigured):
            await manager.chat(system='s', user='u')
    assert a.calls == b.calls == 0


@pytest.mark.asyncio
async def test_quota_on_only_allowed_model_fails_without_silent_downgrade():
    from llm.errors import LLMQuotaError, LLMProviderUnavailable
    a, b = _Stub('gemini', error=LLMQuotaError('quota')), _Stub('mistral')
    manager = _manager(gemini=a, mistral=b)
    with scoped_model_contract('{"gemini":"gemini-stub"}'):
        with pytest.raises(LLMProviderUnavailable):
            await manager.chat(system='s', user='u')
    assert a.calls == 1 and b.calls == 0
    # A subsequent normal conversation is NOT globally denied its fallback.
    result = await manager.chat(system='s', user='u')
    assert result.provider == 'mistral' and b.calls == 1


@pytest.mark.asyncio
async def test_failover_still_operates_between_allowed_candidates():
    from llm.errors import LLMQuotaError
    a, b, c = _Stub('gemini', error=LLMQuotaError('quota')), _Stub('gemini2'), _Stub('mistral')
    manager = _manager(gemini=a, gemini2=b, mistral=c)
    with scoped_model_contract('{"gemini":"gemini-stub","gemini2":"gemini2-stub"}'):
        result = await manager.chat(system='s', user='u')
    assert result.provider == 'gemini2'
    assert (a.calls, b.calls, c.calls) == (1,1,0)


def test_nested_scope_cannot_widen_and_exceptions_restore_context():
    with scoped_model_contract('{"gemini":"gemini-stub"}'):
        with scoped_model_contract(None):
            assert active_contract() == {'gemini':'gemini-stub'}
        with scoped_model_contract('{"mistral":"mistral-stub"}'):
            assert active_contract() == {}
        assert active_contract() == {'gemini':'gemini-stub'}
        with pytest.raises(RuntimeError):
            with scoped_model_contract('{"gemini":"gemini-stub"}'):
                raise RuntimeError('synthetic interruption')
        assert active_contract() == {'gemini':'gemini-stub'}
    assert active_contract() is None


@pytest.mark.asyncio
async def test_concurrent_calls_do_not_share_model_contract():
    ready, release = asyncio.Event(), asyncio.Event()
    async def scoped():
        with scoped_model_contract('{"gemini":"gemini-stub"}'):
            ready.set(); await release.wait()
            assert active_contract() == {'gemini':'gemini-stub'}
    async def normal():
        await ready.wait()
        assert active_contract() is None
        release.set()
    await asyncio.gather(scoped(), normal())
    assert active_contract() is None


@pytest.mark.asyncio
async def test_source_turn_takes_operator_contract_not_email_or_model_fields(world, monkeypatch):
    from conversation_engine.ai_core.source_activation import run_source_turn
    db, signal, body = world
    monkeypatch.setenv('ORA_SOURCE_MODEL_CONTRACT', '{"operator_provider":"operator_model"}')
    seen = []
    async def decide(system, payload):
        seen.append(active_contract())
        assert json.loads(payload)['user_message'] == ''
        return {'response_mode':'answer', 'message_to_user':'Nessuna operazione eseguita.'}
    await run_source_turn(db, OWNER, signal.id, decision_fn=decide)
    assert seen and all(c == {'operator_provider':'operator_model'} for c in seen)
    assert active_contract() is None
    assert await db.life_nodes.count_documents({}) == 0
