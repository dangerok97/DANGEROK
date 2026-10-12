"""Pending-outcome decision contract and its production transport boundary.

The real provider manager, Gemini adapter and installed SDK serialize these
requests into a fake HTTP transport. Replies are fixtures, not model-quality
evidence: even a no_goal response describing an open need must pass through.
No live model, network, account, notification or external effect is exercised.
"""
import asyncio
from copy import deepcopy
import json
from unittest.mock import AsyncMock

import aiohttp
import httpx
from mongomock_motor import AsyncMongoMockClient
import pytest

from agent import reasoning as agent_reasoning
from agent.admission import drain
from llm import manager as llm_manager
from opportunities import reasoning as opportunity_reasoning
from opportunities.discovery import OpportunityDiscovery
from scripts import autonomy_completion_eval_v162 as gate


@pytest.fixture(autouse=True)
def synthetic_transport_only(monkeypatch):
    # A configured developer environment must not choose any real credential.
    for name in (
        "GEMINI_API_KEY", "GEMINI_API_KEY_2", "GOOGLE_API_KEY", "OPENAI_API_KEY",
        "GROQ_API_KEY", "MISTRAL_API_KEY", "EMERGENT_LLM_KEY",
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy",
        "GOOGLE_GEMINI_BASE_URL", "GOOGLE_VERTEX_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GEMINI2_API_KEY", "synthetic-pending-outcome-unused-key")
    monkeypatch.setenv("GEMINI2_MODEL", "gemini-synthetic-pending-outcome")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "false")
    monkeypatch.setenv("DOCUMENT_AI_TIMEOUT_S", "8")
    monkeypatch.setenv("LLM_PROVIDER", "gemini2")

    def reject_transport(*args, **kwargs):
        pytest.fail("Uncontrolled transport attempted; no network request was sent")

    monkeypatch.setattr(aiohttp.ClientSession, "request", reject_transport)
    monkeypatch.setattr(httpx.Client, "send", reject_transport)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", reject_transport)


def assessment(refs=(), *, state="open"):
    return {
        "desired_outcome": None if state == "not_established" else "Un confronto scritto dei costi e dei vincoli.",
        "outcome_state": state,
        "remaining_internal_work": "Preparare il confronto sulla base dei dati riferiti." if state == "open" else None,
        "supporting_refs": list(refs),
        "completion_refs": list(refs) if state == "resolved" else [],
    }


def proposal(refs, *, with_assessment=True):
    item = {
        "identity_key": "synthetic:missing-internal-result",
        "what": "Il confronto scritto non è ancora disponibile.",
        "why_it_matters": "Rendere disponibili costi e vincoli per la scelta aperta.",
        "why_now": "Il risultato resta utile; non è documentata una scadenza.",
        "initiative": "prepare", "what_i_can_do": "Preparare il confronto dai dati attribuiti alla nota.",
        "relevance": "medium", "urgency": "none", "time_sensitivity": "stable",
        "confidence": "reasonable", "evidence_refs": list(refs),
        "requires_clarification": False, "needs_research": False,
    }
    if with_assessment:
        item["outcome_assessment"] = assessment(refs)
    return item


def assert_assessment_observed(observed, expected):
    # The bounded observer adds shape/omission metadata and omits null text.
    # The actual decision facts and references must still be unchanged.
    assert {field: observed.get(field) for field in expected} == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario,propose", [
    ("completed_result", False),
    ("already_resolved", False),
    ("irrelevant", False),
    ("source_change_crash", False),
    ("source_change_crash", True),
])
async def test_complete_canonical_context_and_contract_reach_real_sdk_http_unchanged(
    monkeypatch, scenario, propose,
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
        assert body["generationConfig"]["temperature"] == pytest.approx(0.2)
        payload = json.loads(user)
        transported.append(payload)

        if "proposed" in payload:
            # Exercise the existing audit too; it must receive the assessment
            # unchanged, and need no extra inference to enforce the new field.
            item = payload["proposed"]["opportunities"][0]
            assert item["outcome_assessment"]["outcome_state"] == "open"
            assert "useful internal preparation" in system
            rows = payload["snapshot"]["memories"]
            response = {"verified": True, "opportunities": [item], "reason_for_silence": ""}
        else:
            for field in ("outcome_assessment", "desired_outcome", "outcome_state",
                          "remaining_internal_work", "supporting_refs", "completion_refs"):
                assert field in system
            assert "user_stated" in system and "external effect" in system
            assert "not_established" in system
            rows = (payload["life_right_now"]["memories"] if "life_right_now" in payload
                    else payload.get("source_context", []))
            refs = [row["ref"] for row in rows]
            state = "resolved" if scenario == "already_resolved" else "not_established" if scenario == "irrelevant" else "open"
            if "life_right_now" in payload:
                response = ({"opportunities": [proposal(refs)]} if propose else {
                    "opportunities": [], "reason_for_silence": "Synthetic silence; no semantic assertion.",
                    "outcome_assessment": assessment(refs, state=state),
                })
            else:
                response = {
                    "outcome": "no_goal", "reasoning": "Synthetic no_goal; no semantic assertion.",
                    "outcome_assessment": assessment(refs, state=state),
                }

        if scenario == "irrelevant":
            assert rows == []  # The unrelated Memory must not leak into admission.
            assert gate.FIXTURE_CONTEXT not in user
        else:
            assert len(rows) == 1
            expected = gate.RESOLVED_FIXTURE_NOTE if scenario == "already_resolved" else gate.FIXTURE_NOTE
            assert rows[0]["statement"] == expected
            assert rows[0]["authority"] == "user_stated"
            assert not rows[0]["excerpt_truncated"]
            assert gate.baseline.FACT in user
            assert not payload.get("context_truncated")
        replies.append(deepcopy(response))
        return httpx.Response(200, json={
            "candidates": [{"content": {"role": "model", "parts": [{"text": json.dumps(response)}]},
                            "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 2, "totalTokenCount": 6},
        })

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda *args, **kwargs: httpx.MockTransport(respond))
    monkeypatch.setattr(llm_manager, "_runtime_preferred", "gemini2")
    monkeypatch.setattr(llm_manager, "_manager", llm_manager.ProviderManager())
    monkeypatch.setattr(llm_manager.ProviderManager, "chat", observe_manager)
    db = AsyncMongoMockClient()["v162_pending_contract_" + scenario]
    # 'live' selects the unchanged production reasoning/SDK path; the only
    # enabled HTTP transport above supplies synthetic replies in this test.
    with gate.isolated_engine(db, mode="live", scenario=scenario) as probe:
        await gate.seed_case(db, scenario)
        if scenario == "source_change_crash":
            discovery = OpportunityDiscovery(db)
            with pytest.raises(asyncio.CancelledError):
                await discovery.review(gate.OWNER)
            assert not transported
            result = await discovery.review(gate.OWNER)
            assert result.ran and not result.unavailable
            assert len(result.scan.created) == int(propose)
            observed = probe.structured_decisions[-1]
            if propose:
                assert_assessment_observed(
                    observed["opportunities"][0]["outcome_assessment"],
                    replies[0]["opportunities"][0]["outcome_assessment"],
                )
            else:
                assert_assessment_observed(observed["outcome_assessment"], replies[0]["outcome_assessment"])
        else:
            assert await drain(db, owner_id=gate.OWNER, limit=1) == 1
            source = await db.opportunities.find_one({"owner_id": gate.OWNER})
            assert source["agent_review_outcome"] == "no_goal"
            assert source["agent_review_state"] == "settled"
            assert source["agent_review_due"] is None
            assert_assessment_observed(
                probe.structured_decisions[-1]["outcome_assessment"], replies[0]["outcome_assessment"],
            )
        assert await db.agent_goals.count_documents({}) == 0
        assert await db.agent_evidence.count_documents({}) == 0
        assert await db.ambient_wakes.count_documents({}) == 0
        expected_calls = 2 if propose else 1  # Existing proposal audit only.
        assert len(forwarded) == len(transported) == probe.model_attempts == expected_calls
        assert probe.model_http_requests == expected_calls
        assert probe.network.blocked == [] and probe.blocked_effects == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["no_goal", "create_goal", "clarify", "wait"])
@pytest.mark.parametrize("metadata", ["absent", "valid", "unknown"])
async def test_admission_preserves_each_decision_without_requiring_assessment(monkeypatch, outcome, metadata):
    response = {"outcome": outcome, "reasoning": "Synthetic decision remains authoritative."}
    if metadata == "valid":
        # Deliberately open even for no_goal: diagnostics must not force work.
        response["outcome_assessment"] = assessment(["memory:synthetic"])
    elif metadata == "unknown":
        response["outcome_assessment"] = {"future_metadata": "not used by runtime"}
    ask = AsyncMock(return_value=response)
    monkeypatch.setattr(agent_reasoning, "_ask_model", ask)
    result = await agent_reasoning.decide_goal({"source_context": []})
    assert result is response
    assert result["outcome"] == outcome
    assert ask.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [None, {"outcome": "invalid", "outcome_assessment": assessment()}])
async def test_assessment_does_not_repair_an_unavailable_or_invalid_decision(monkeypatch, response):
    ask = AsyncMock(return_value=response)
    monkeypatch.setattr(agent_reasoning, "_ask_model", ask)
    assert await agent_reasoning.decide_goal({}) is None
    assert ask.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("metadata", ["absent", "valid", "unknown"])
async def test_discovery_silence_remains_one_decision_with_optional_assessment(monkeypatch, metadata):
    response = {"opportunities": [], "reason_for_silence": "Synthetic decision remains authoritative."}
    if metadata == "valid":
        response["outcome_assessment"] = assessment(["memory:synthetic"])
    elif metadata == "unknown":
        response["outcome_assessment"] = "unsupported metadata remains nonbinding"
    ask = AsyncMock(return_value=response)
    monkeypatch.setattr(opportunity_reasoning, "_ask_model", ask)
    assert await opportunity_reasoning.scan({}, already_raised=[]) is response
    assert ask.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("with_assessment", [False, True])
@pytest.mark.parametrize("retained", [False, True])
async def test_existing_proposal_audit_can_retain_or_reject_without_new_gate(
    monkeypatch, with_assessment, retained,
):
    item = proposal(["memory:synthetic"], with_assessment=with_assessment)
    proposed = {"opportunities": [item]}
    reviewed = {"verified": True, "opportunities": [deepcopy(item)] if retained else [],
                "reason_for_silence": "" if retained else "No supported useful work remains."}
    ask = AsyncMock(side_effect=[proposed, reviewed])
    monkeypatch.setattr(opportunity_reasoning, "_ask_model", ask)
    result = await opportunity_reasoning.scan({"memories": [{"ref": "memory:synthetic"}]}, already_raised=[])
    assert result is reviewed
    assert ask.await_count == 2
    audit_payload = json.loads(ask.call_args_list[1].args[1])
    assert audit_payload["proposed"] == proposed
    assert result["opportunities"] == ([item] if retained else [])
