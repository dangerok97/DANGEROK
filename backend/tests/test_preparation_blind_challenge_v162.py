"""Opt-in blind critic: a second source-grounded judgement, not semantic proof.

No real model, HTTP, account, notification, or physical state is used. Tests
show the distinct negative path even when the preceding model audit says YES.
"""
from copy import deepcopy
import json

import pytest

from agent import preparation, reasoning
from agent.preparation_challenge import input_payload, schema, verdict
from test_preparation_source_quotes_v162 import OWNER, TEXT, audit, seed


UNSUPPORTED = "B può essere interrotto senza vincoli."


def response(accepted, issues=None):
    return {"accepted": accepted, "issues": list(issues or []),
            "reason": "Ogni clausola è condizionata dalla fonte." if accepted
                      else "È stata attribuita una condizione non documentata."}


@pytest.mark.parametrize("answer,result", [
    (response(True), "accepted"),
    (response(False), "rejected"),
    (response(True, [{"claim": UNSUPPORTED, "missing_premise": "Condizioni di recesso non date.",
                     "evidence_ids": ["ev_one"]}]), "rejected"),
    ({"accepted": "true", "issues": [], "reason": "Mancanza."}, "invalid"),
    ({"accepted": True, "issues": [{"claim": UNSUPPORTED,
                                  "missing_premise": "Non provata.",
                                  "evidence_ids": ["foreign"]}], "reason": "Problema."}, "invalid"),
    ({"accepted": True, "issues": [], "reason": ""}, "invalid"),
    (None, "invalid"),
])
def test_challenge_verdict_is_typed_and_owner_source_bounded(answer, result):
    assert verdict(answer, ["ev_one"]) == result


def test_challenge_input_omits_earlier_audit_verdict():
    request = {"objective": "Comparare due opzioni"}
    sources = [{"id": "ev_one", "claim_passages": [{"id": "p_one", "text": "A costa 5."}]}]
    original = deepcopy(sources)
    encoded = input_payload(request, "Da fonte A costa 5.", sources)
    payload = json.loads(encoded)
    assert payload["stage"] == "blind_source_challenge"
    assert payload["request"] == request and payload["evidence"] == original
    assert payload["evidence_truncated"] is False
    second = input_payload(request, "Da fonte A costa 5.", sources, evidence_truncated=True)
    assert json.loads(second)["evidence_truncated"] is True
    assert "verified" not in encoded and "previous_audit" not in encoded
    assert sources == original
    assert schema(["ev_one"])["properties"]["issues"]["items"]["properties"]["evidence_ids"]["items"]["enum"] == ["ev_one"]
    assert input_payload(request, "x" * 9001, sources) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("challenge,expected_error", [
    (response(False, [{"claim": UNSUPPORTED,
                       "missing_premise": "B's exit terms are absent.",
                       "evidence_ids": []}]), "preparation_challenge_rejected"),
    (response(True, [{"claim": UNSUPPORTED,
                      "missing_premise": "Source does not specify B cancellation.",
                      "evidence_ids": []}]), "preparation_challenge_rejected"),
    (None, "preparation_challenge_unavailable"),
    ({"accepted": True, "issues": "not-a-list", "reason": "Unclear."},
     "preparation_challenge_unavailable"),
])
async def test_blind_critic_can_block_a_falsely_positive_first_audit_without_data_loss(
    monkeypatch, challenge, expected_error
):
    monkeypatch.setenv("ORA_PREPARATION_BLIND_CHALLENGE", "1")
    h = await seed()
    original = audit(h)
    # Intentionally inaccurate: authentic price quotes do not establish
    # cancellation without restrictions. The first auditor wrongly approves.
    original["content"] = UNSUPPORTED
    original["claim_review"][0]["claim"] = UNSUPPORTED
    original["claim_review"][0]["support"] = "derived"
    original["claim_review"][0]["compatible_counterexample"] = ""
    previous = "Bozza precedente valida."
    h.goal.prepared_text, h.goal.prepared_sources = previous, [h.sources[0].id]
    await h.db.agent_goals.update_one({"id": h.goal.id, "owner_id": OWNER},
        {"$set": {"prepared_text": previous,
                  "prepared_sources": h.goal.prepared_sources}})
    calls = []

    async def model(_system, encoded, *, response_schema=None):
        payload = json.loads(encoded)
        calls.append(payload)
        assert isinstance(response_schema, dict)
        if payload.get("stage") == "blind_source_challenge":
            assert payload["candidate_result"] == UNSUPPORTED
            assert "claim_review" not in payload
            assert payload["request"]["desired_outcome"] == h.goal.desired_outcome
            assert all(row["claim_passages"] for row in payload["evidence"])
            return challenge
        if "draft" in payload:
            return original
        return {"content": UNSUPPORTED, "evidence_ids": [s.id for s in h.sources]}

    monkeypatch.setattr(reasoning, "_ask_model", model)
    result = await preparation.prepare(h.db, OWNER, h.goal, h.step)
    assert result.status == "unavailable" and result.error_type == expected_error
    assert result.retryable is True and len(calls) == 3
    saved = await h.db.agent_goals.find_one({"owner_id": OWNER, "id": h.goal.id})
    assert saved["prepared_text"] == h.goal.prepared_text == previous
    assert not await h.db.agent_evidence.count_documents({"provenance.provider": "generated_draft"})


@pytest.mark.asyncio
async def test_blind_critic_accepts_compact_grounded_comparison_when_opted_in(monkeypatch):
    monkeypatch.setenv("ORA_PREPARATION_BLIND_CHALLENGE", "1")
    h = await seed()
    checked = audit(h)
    calls = []

    async def model(_system, encoded, *, response_schema=None):
        payload = json.loads(encoded)
        calls.append(payload)
        if payload.get("stage") == "blind_source_challenge":
            assert payload["candidate_result"] == TEXT
            assert all(row["claim_passages"] for row in payload["evidence"])
            return response(True)
        if "draft" in payload:
            return checked
        return {"content": TEXT, "evidence_ids": [s.id for s in h.sources]}

    monkeypatch.setattr(reasoning, "_ask_model", model)
    result = await preparation.prepare(h.db, OWNER, h.goal, h.step)
    assert result.status == "succeeded" and len(calls) == 3
    assert h.goal.prepared_text == TEXT


@pytest.mark.asyncio
async def test_challenge_stays_off_by_default_and_does_not_add_provider_calls(monkeypatch):
    monkeypatch.delenv("ORA_PREPARATION_BLIND_CHALLENGE", raising=False)
    h = await seed()
    checked = audit(h)
    count = 0

    async def model(_system, encoded, *, response_schema=None):
        nonlocal count
        count += 1
        assert json.loads(encoded).get("stage") != "blind_source_challenge"
        return checked if "draft" in json.loads(encoded) else {
            "content": TEXT, "evidence_ids": [s.id for s in h.sources]}

    monkeypatch.setattr(reasoning, "_ask_model", model)
    assert (await preparation.prepare(h.db, OWNER, h.goal, h.step)).status == "succeeded"
    assert count == 2
