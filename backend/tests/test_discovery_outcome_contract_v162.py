"""Discovery's actual output examples, through the real SDK and fake HTTP.

The previous prompt mentioned assessment outside Return JSON while its two
output examples omitted it. Check those examples themselves, then keep model
silence and legacy responses nonbinding. No real model or network is used.
"""
import asyncio
from copy import deepcopy
import json
from unittest.mock import AsyncMock

import httpx
from mongomock_motor import AsyncMongoMockClient
import pytest

from llm import manager as llm_manager
from opportunities import reasoning
from opportunities.discovery import OpportunityDiscovery
from scripts import autonomy_completion_eval_v162 as gate
from test_pending_outcome_contract_v162 import (
    assessment,
    proposal,
    synthetic_transport_only,  # noqa: F401 - shared autouse safety fixture
)


ASSESSMENT_FIELDS = [
    "desired_outcome", "outcome_state", "remaining_internal_work",
    "supporting_refs", "completion_refs",
]


def output_examples(system):
    """Decode the real examples after Return JSON, excluding earlier prose."""
    contract = system.rsplit("Return JSON", 1)[1]
    decoder = json.JSONDecoder()
    examples = []
    offset = 0
    while (start := contract.find("{", offset)) >= 0:
        value, end = decoder.raw_decode(contract[start:])
        examples.append(value)
        offset = start + end
    return examples


def assert_complete_examples(system):
    silent, useful = output_examples(system)
    for example in (silent, useful):
        assert list(example)[:2] == ["outcome_assessment", "opportunities"]
        assert list(example["outcome_assessment"]) == ASSESSMENT_FIELDS
        assert example["outcome_assessment"]["outcome_state"] == "open|resolved|not_established"
    assert silent["opportunities"] == [] and silent["reason_for_silence"]
    assert len(useful["opportunities"]) == 1
    item = useful["opportunities"][0]
    assert list(item)[0] == "outcome_assessment"
    assert list(item["outcome_assessment"]) == ASSESSMENT_FIELDS
    assert "identity_key" in item and "evidence_refs" in item
    assert "all four come out negative" not in system
    assert "Most useful things are `inform` or `recommend`" not in system


@pytest.mark.asyncio
async def test_return_json_examples_include_assessment_before_both_decisions(monkeypatch):
    reply = {"opportunities": [], "reason_for_silence": "A valid legacy silence."}
    ask = AsyncMock(return_value=reply)
    monkeypatch.setattr(reasoning, "_ask_model", ask)

    assert await reasoning.scan({}, already_raised=[]) is reply

    assert ask.await_count == 1
    assert_complete_examples(ask.call_args.args[0])


@pytest.mark.asyncio
@pytest.mark.parametrize("response_kind", [
    "legacy_silence", "assessed_silence", "retained_proposal", "audit_silence",
])
async def test_real_sdk_receives_complete_discovery_contract_and_preserves_decision(
    monkeypatch, response_kind,
):
    forwarded, transported, replies = [], [], []
    original_chat = llm_manager.ProviderManager.chat

    async def observe_manager(self, **kwargs):
        forwarded.append({"system": kwargs["system"], "user": kwargs["user"]})
        return await original_chat(self, **kwargs)

    def respond(request):
        assert request.url.host == "generativelanguage.googleapis.com"
        body = json.loads(request.content)
        system = "".join(part.get("text", "") for part in body["systemInstruction"]["parts"])
        user = "".join(part.get("text", "") for content in body["contents"] for part in content["parts"])
        assert {"system": system, "user": user} == forwarded[-1]
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        payload = json.loads(user)
        transported.append(payload)

        if "life_right_now" in payload:
            assert_complete_examples(system)
            rows = payload["life_right_now"]["memories"]
            refs = [row["ref"] for row in rows]
            if response_kind == "legacy_silence":
                reply = {"opportunities": [], "reason_for_silence": "Synthetic legacy silence."}
            elif response_kind == "assessed_silence":
                # Even an open assessment cannot force a proposal or a retry.
                reply = {"outcome_assessment": assessment(refs), "opportunities": [],
                         "reason_for_silence": "Synthetic silence despite an open assessment."}
            else:
                reply = {"outcome_assessment": assessment(refs), "opportunities": [proposal(refs)]}
        else:
            assert "proposed" in payload
            rows = payload["snapshot"]["memories"]
            proposed = payload["proposed"]
            assert proposed == replies[0]
            if response_kind == "audit_silence":
                # The existing audit may reject a proposal without assessment.
                reply = {"verified": True, "opportunities": [], "reason_for_silence": "Synthetic audit silence."}
            else:
                reply = {"outcome_assessment": proposed["outcome_assessment"], "verified": True,
                         "opportunities": proposed["opportunities"], "reason_for_silence": ""}

        assert len(rows) == 1 and rows[0]["statement"] == gate.FIXTURE_NOTE
        assert rows[0]["authority"] == "user_stated" and not rows[0]["excerpt_truncated"]
        assert not payload.get("context_truncated")
        replies.append(deepcopy(reply))
        return httpx.Response(200, json={
            "candidates": [{"content": {"role": "model", "parts": [{"text": json.dumps(reply)}]},
                            "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 2, "totalTokenCount": 6},
        })

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda *args, **kwargs: httpx.MockTransport(respond))
    monkeypatch.setattr(llm_manager, "_runtime_preferred", "gemini2")
    monkeypatch.setattr(llm_manager, "_manager", llm_manager.ProviderManager())
    monkeypatch.setattr(llm_manager.ProviderManager, "chat", observe_manager)
    db = AsyncMongoMockClient()["v162_discovery_contract_" + response_kind]
    # 'live' selects production code; all SDK HTTP responses above are fake.
    with gate.isolated_engine(db, mode="live", scenario="source_change_crash") as probe:
        await gate.seed_case(db, "source_change_crash")
        discovery = OpportunityDiscovery(db)
        with pytest.raises(asyncio.CancelledError):
            await discovery.review(gate.OWNER)
        assert transported == []

        result = await discovery.review(gate.OWNER)

        assert result.ran and not result.unavailable
        assert len(result.scan.created) == int(response_kind == "retained_proposal")
        assert await db.agent_goals.count_documents({}) == 0
        assert await db.agent_evidence.count_documents({}) == 0
        assert await db.ambient_wakes.count_documents({}) == 0
        expected_calls = 2 if response_kind in ("retained_proposal", "audit_silence") else 1
        assert len(transported) == len(forwarded) == probe.model_attempts == expected_calls
        assert probe.model_http_requests == expected_calls
        assert probe.network.blocked == [] and probe.blocked_effects == 0


@pytest.mark.asyncio
async def test_assessment_does_not_replace_the_existing_audit_verdict(monkeypatch):
    pending = {"outcome_assessment": assessment(), "opportunities": [proposal([])]}
    unverified = {"outcome_assessment": assessment(), "opportunities": pending["opportunities"]}
    ask = AsyncMock(side_effect=[pending, unverified])
    monkeypatch.setattr(reasoning, "_ask_model", ask)

    assert await reasoning.scan({}, already_raised=[]) is None
    assert ask.await_count == 2
