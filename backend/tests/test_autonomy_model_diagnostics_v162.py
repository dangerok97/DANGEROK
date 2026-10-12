"""Observe current manager outcomes without exporting provider payloads.

The real manager's failover runs over synthetic providers and fake HTTP only.
These diagnostics do not alter decisions, retry policy, counters or budgets.
"""
import asyncio
from copy import deepcopy
import json

import httpx
from mongomock_motor import AsyncMongoMockClient
import pytest

from llm.base import LLMResult
from llm.errors import LLMProviderUnavailable, LLMQuotaError, LLMRateLimitError
from llm.manager import ProviderManager
from scripts import autonomy_completion_eval_v162 as gate
from test_pending_outcome_contract_v162 import synthetic_transport_only  # noqa: F401


SECRET = "synthetic-private-prompt-source-url-and-credential"


class FakeProvider:
    def __init__(self, name, *, failure=None):
        self.name, self.failure = name, failure
        self.calls = 0

    def is_configured(self):
        return True

    async def chat(self, **kwargs):
        self.calls += 1
        url = ("https://generativelanguage.googleapis.com/v1beta/models/synthetic:generateContent"
               if self.name == "gemini2" else "https://api.mistral.ai/v1/chat/completions")
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"private": SECRET}),
        )) as client:
            await client.post(url, headers={"authorization": SECRET}, json=kwargs)
        if self.failure:
            raise self.failure
        return LLMResult(text=SECRET, provider=self.name, model="synthetic-model",
            usage={"total_tokens": 3, "private": SECRET})


def manager_for(*providers):
    manager = ProviderManager()
    manager._providers = {provider.name: provider for provider in providers}
    manager.ordered_names = lambda preference=None: list(manager._providers)
    return manager


@pytest.mark.asyncio
async def test_successful_fallback_uses_only_current_response_and_not_last_failed_chain():
    first = FakeProvider("gemini2", failure=LLMRateLimitError(SECRET))
    second = FakeProvider("mistral")
    manager = manager_for(first, second)
    stale = [{"provider": "openai", "failure_kind": "authentication", "private": SECRET}]
    manager._last_attempts = stale
    db = AsyncMongoMockClient().model_diagnostics_v162
    with gate.isolated_engine(db, mode="live") as probe:
        result = await manager.chat(system=SECRET, user=SECRET)
        assert result.text == SECRET
        # Gemini is now cooling down. The successful manager response does
        # not report that skip; this probe must not invent a complete chain.
        await manager.chat(system=SECRET, user=SECRET)
        report = gate.model_observations(probe)
        observations = report["model_call_outcomes"]
        assert len(observations) == 2
        assert observations[0]["fallbacks"] == [{"provider": "gemini2", "failure_kind": "rate_limit"}]
        assert observations[1]["fallbacks"] == []
        assert all(row["provider"] == "mistral" and row["outcome"] == "succeeded"
                   and row["failure_kind"] is None and row["elapsed_ms"] >= 0 for row in observations)
        assert [row["sequence"] for row in observations] == [1, 2]
        assert report["model_call_outcomes_scope"] == "manager_reported_final_chain"
        assert report["model_call_elapsed_scope"] == "logical_call_including_fallbacks_and_pacing"
        assert probe.model_attempts == len(probe.model_calls) == 2 and probe.model_http_requests == 3
        assert manager._last_attempts is stale
        assert SECRET not in json.dumps(report)
        assert probe.network.scope.get() == "blocked"


@pytest.mark.asyncio
async def test_exhausted_real_manager_reports_current_failed_chain_without_claiming_a_response():
    manager = manager_for(FakeProvider("gemini2", failure=LLMQuotaError(SECRET)),
                          FakeProvider("mistral", failure=LLMQuotaError(SECRET)))
    manager._last_attempts = [{"provider": "openai", "failure_kind": "network"}]
    db = AsyncMongoMockClient().model_failed_chain_v162
    with gate.isolated_engine(db, mode="live") as probe:
        with pytest.raises(LLMProviderUnavailable) as caught:
            await manager.chat(system=SECRET, user=SECRET)
        row, = probe.model_call_outcomes
        assert row["outcome"] == "failed" and row["failure_kind"] == "provider_unavailable"
        assert row["provider"] == "unknown"
        assert row["fallbacks"] == [{"provider": "gemini2", "failure_kind": "quota"},
                                    {"provider": "mistral", "failure_kind": "quota"}]
        assert len(caught.value.attempts) == 2
        assert probe.model_attempts == 1 and probe.model_http_requests == 2
        assert probe.model_calls == [] and not gate.model_observations(probe)["real_model_executed"]
        assert SECRET not in json.dumps(gate.model_observations(probe))
        assert probe.network.scope.get() == "blocked"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["unavailable", "unexpected", "cancelled"])
async def test_error_identity_and_cancellation_survive_and_sensitive_fields_are_not_exported(monkeypatch, kind):
    if kind == "unavailable":
        error = LLMProviderUnavailable([])
        # Deliberately include fields no reporting layer may stringify. The
        # current exception, not a manager-wide old record, supplies attempts.
        error.attempts = [{"provider": "gemini2", "failure_kind": "timeout",
                           "message": SECRET, "url": SECRET, "timestamp": SECRET}] * 20
        error.attempts[1] = {"provider": SECRET, "failure_kind": {"private": SECRET}}
    elif kind == "cancelled":
        error = asyncio.CancelledError(SECRET)
    else:
        error = RuntimeError(SECRET)
        error.kind = SECRET

    async def failed(self, *args, **kwargs):
        raise error

    monkeypatch.setattr(ProviderManager, "chat", failed)
    db = AsyncMongoMockClient().model_exception_v162
    with gate.isolated_engine(db, mode="live") as probe:
        with pytest.raises(type(error)) as caught:
            await ProviderManager.chat(object(), system=SECRET, user=SECRET)
        assert caught.value is error
        row, = probe.model_call_outcomes
        assert row["outcome"] == ("cancelled" if kind == "cancelled" else "failed")
        assert row["failure_kind"] == ("provider_unavailable" if kind == "unavailable" else "unknown")
        assert row["provider"] == "unknown" and row["elapsed_ms"] >= 0
        assert set(row) == {"sequence", "outcome", "provider", "failure_kind", "elapsed_ms", "fallbacks"}
        assert len(row["fallbacks"]) == (gate.MAX_MODEL_FAILURES_REPORTED if kind == "unavailable" else 0)
        if kind == "unavailable":
            assert row["fallbacks"][1] == {"provider": "unknown", "failure_kind": "unknown"}
        assert probe.model_attempts == 1 and probe.model_http_requests == 0 and probe.model_calls == []
        assert SECRET not in json.dumps(gate.model_observations(probe))
        assert probe.network.scope.get() == "blocked"


def test_success_metadata_is_allowlisted_bounded_and_does_not_modify_the_response():
    result = LLMResult(text=SECRET, provider="gemini2", model="synthetic-model", usage={
        "failover_errors": ["mistral:network", f"openai:{SECRET}", {"private": SECRET},
                            f"https://{SECRET}/private", f"{SECRET}:timeout", "gemini:quota"] * 5,
        "latency_ms": SECRET, "raw_error": SECRET,
    })
    before = deepcopy(result)
    row = gate._model_call_outcome(1, result, None, 12.345)
    assert result == before
    assert row["outcome"] == "succeeded" and row["provider"] == "gemini2"
    assert row["elapsed_ms"] == 12.3 and row["failure_kind"] is None
    assert len(row["fallbacks"]) <= gate.MAX_MODEL_FAILURES_REPORTED
    assert row["fallbacks"][0] == {"provider": "mistral", "failure_kind": "network"}
    assert SECRET not in json.dumps(row)


@pytest.mark.asyncio
async def test_diagnostic_bound_does_not_reset_or_weaken_the_existing_model_call_bound(monkeypatch):
    monkeypatch.setattr(gate, "MAX_MODEL_CALLS", 2)
    manager = manager_for(FakeProvider("mistral"))
    db = AsyncMongoMockClient().model_observation_bound_v162
    with gate.isolated_engine(db, mode="live") as probe:
        await manager.chat(system=SECRET, user=SECRET)
        await manager.chat(system=SECRET, user=SECRET)
        with pytest.raises(gate.EvaluationFailure, match="^MODEL_CALL_BOUND_EXCEEDED$"):
            await manager.chat(system=SECRET, user=SECRET)
        assert probe.model_attempts == 3
        assert len(probe.model_calls) == probe.model_http_requests == len(probe.model_call_outcomes) == 2
        assert probe.network.blocked == ["MODEL_CALL_BOUND_EXCEEDED"]
        assert probe.network.scope.get() == "blocked"
