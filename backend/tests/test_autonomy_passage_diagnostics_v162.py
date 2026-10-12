"""Passage-selection tracing observes the exact marked audit input, not truth."""
from copy import deepcopy
import json

from mongomock_motor import AsyncMongoMockClient
import pytest

from agent import preparation, reasoning
from agent.execution import StepExecutor
from agent.models import AgentBudget
from scripts import autonomy_completion_eval_v162 as gate
from test_autonomy_preparation_diagnostics_v162 import (
    no_provider_credentials, prepare_step, read_source, seed,
)


def check(ids):
    return {"claim": "Clausola sintetica da verificare.", "premises": "Premesse del controllo sintetico.",
            "inference_or_gap": "Il test osserva la selezione, senza certificare il supporto semantico.",
            "compatible_counterexample": "",
            "support": "stated", "correction": "", "evidence_ids": ["ev_input"],
            "source_passage_ids": ids}


def audit_payload(text="Passaggio effettivamente fornito."):
    return {"draft": "Bozza sintetica.", "evidence": [{"id": "ev_input",
        "claim_passages": [{"id": "p_supplied", "text": text},
                           {"id": "p_unused", "text": "UNSELECTED_PRIVATE_SOURCE"}]}]}


async def trace(monkeypatch, payload, response, *, violation=None):
    calls = []
    encoded = json.dumps(payload, ensure_ascii=False)

    async def model(system, user, *, response_schema=None):
        calls.append((system, user, response_schema))
        return response

    async def original_prepare(db, owner, goal, item):
        return await reasoning._ask_model("opaque synthetic instruction", encoded)

    monkeypatch.setattr(gate.baseline, "scripted_draft", model)
    monkeypatch.setattr(preparation, "prepare", original_prepare)
    db = AsyncMongoMockClient().passage_diagnostic_scope
    goal = await seed(db, marked=violation != "marker_missing")
    if violation == "goal_owner":
        goal.owner_id = "foreign-owner"
    owner = "foreign-owner" if violation == "owner" else gate.OWNER
    other = AsyncMongoMockClient().foreign_passage_diagnostics
    if violation == "database":
        await other.eval_guards.insert_one({"_id": gate.VERSION, "owner": gate.OWNER})
    with gate.isolated_engine(db) as probe:
        if violation == "outside_prepare":
            returned = await reasoning._ask_model("opaque synthetic instruction", encoded)
        else:
            returned = await preparation.prepare(other if violation == "database" else db,
                                                 owner, goal, prepare_step())
    assert returned is response and calls == [("opaque synthetic instruction", encoded, None)]
    assert probe.model_attempts == probe.model_http_requests == probe.blocked_effects == 0
    return probe


@pytest.mark.asyncio
async def test_native_audit_selection_is_observed_without_changing_the_real_prepared_result(monkeypatch):
    inputs, replies = [], []

    async def model(system, user, *, response_schema=None):
        payload = json.loads(user)
        inputs.append(payload)
        reply = {"content": gate.baseline.DRAFT, "evidence_ids": [payload["evidence"][0]["id"]]}
        if "draft" in payload:
            row = payload["evidence"][0]
            item = check([part["id"] for part in row["claim_passages"]])
            item["evidence_ids"] = [row["id"]]
            reply.update(verified=True, claim_review=[item])
        replies.append(deepcopy(reply))
        return reply

    monkeypatch.setattr(gate.baseline, "scripted_draft", model)
    db = AsyncMongoMockClient().native_passage_diagnostics
    goal = await seed(db, source=True)
    budget = AgentBudget()
    with gate.isolated_engine(db) as probe:
        await read_source(db, goal)
        result = await StepExecutor(db).run(gate.OWNER, goal, prepare_step(),
                                            may_touch_the_world=False, budget=budget)
    assert result.status == "succeeded" and goal.prepared_text == gate.baseline.DRAFT
    assert len(inputs) == 2 and budget.cognitive_calls == 2
    audit = probe.structured_decisions[-1]
    observed, = audit["claim_review"]
    original = replies[-1]["claim_review"][0]
    assert observed["source_passage_ids"] == original["source_passage_ids"]
    assert observed["source_passage_ids_count"] == len(original["source_passage_ids"])
    assert observed["source_passage_ids_omitted"] == 0 and observed["source_quotes_kind"] == "none"
    assert "source_quotes" not in replies[-1]["claim_review"][0]
    passages = inputs[-1]["evidence"][0]["claim_passages"]
    selected = observed["source_passage_selections"]
    assert len(selected) == len(passages)
    for row, part in zip(selected, passages):
        assert row["status"] == "materialized" and row["origin"] == "code_owned_audit_input"
        assert row["source_passage_id"] == part["id"] and row["quote"] == part["text"]
        assert row["evidence_id"] == goal.prepared_sources[0]
    assert audit["verified"] is True and audit["content"] == goal.prepared_text
    assert probe.model_attempts == probe.model_http_requests == probe.blocked_effects == 0
    assert await db.agent_action_attempts.count_documents({}) == 0


@pytest.mark.asyncio
async def test_only_exact_current_input_selections_are_materialized_and_unselected_text_is_absent(monkeypatch):
    for text in ("Primo snapshot sintetico.", "Secondo snapshot sintetico, differente."):
        payload = audit_payload(text)
        response = {"verified": True, "content": "Risposta invariata.", "evidence_ids": ["ev_input"],
                    "claim_review": [check(["p_supplied", "p_unknown", {"private": "PRIVATE_MALFORMED"}])]}
        original_payload, original_response = deepcopy(payload), deepcopy(response)
        probe = await trace(monkeypatch, payload, response)
        observed = probe.structured_decisions[0]["claim_review"][0]
        assert observed["source_passage_ids"] == ["p_supplied", "p_unknown"]
        assert observed["source_passage_ids_kind"] == "array" and observed["source_passage_ids_count"] == 3
        selected = observed["source_passage_selections"]
        assert [row["selection_index"] for row in selected] == [0, 1, 2]
        assert [row["status"] for row in selected] == ["materialized", "unknown", "malformed"]
        assert selected[0]["quote"] == text
        assert all("quote" not in row and "evidence_id" not in row for row in selected[1:])
        assert selected[2]["response_kind"] == "object" and "source_passage_id" not in selected[2]
        encoded = json.dumps(gate.model_observations(probe))
        assert "UNSELECTED_PRIVATE_SOURCE" not in encoded and "PRIVATE_MALFORMED" not in encoded
        assert payload == original_payload and response == original_response


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed", ["missing_input", "ambiguous_input", "malformed_passage"])
async def test_unknown_or_ambiguous_input_does_not_supply_an_inferred_quote(monkeypatch, malformed):
    payload = audit_payload()
    if malformed == "missing_input":
        payload["evidence"] = [{"id": "ev_input", "claim": "PRIVATE_UNMAPPED_CLAIM"}]
    elif malformed == "ambiguous_input":
        payload["evidence"].append({"id": "ev_another", "claim_passages": [
            {"id": "p_supplied", "text": "PRIVATE_CONFLICTING_QUOTE"}]})
    else:
        payload["evidence"][0]["claim_passages"][0]["text"] = {"private": "PRIVATE_MALFORMED_QUOTE"}
    response = {"verified": True, "claim_review": [check(["p_supplied"])]}
    probe = await trace(monkeypatch, payload, response)
    selected, = probe.structured_decisions[0]["claim_review"][0]["source_passage_selections"]
    assert selected["status"] == "unknown" and selected["source_passage_id"] == "p_supplied"
    assert "quote" not in selected and "evidence_id" not in selected
    assert "PRIVATE_" not in json.dumps(gate.model_observations(probe))


@pytest.mark.asyncio
async def test_passage_observations_are_bounded_redacted_and_never_match_truncated_ids(monkeypatch):
    secret = "key12345"
    monkeypatch.setenv("GEMINI_API_KEY_2", secret)
    selected_id = "p_" + secret
    prefix = "p_" + "x" * 158
    text = (secret + " ") * 30  # Redaction expands beyond the 280-character output cap.
    payload = {"draft": "Bozza sintetica.", "evidence": [{"id": "ev_" + secret,
        "claim_passages": [{"id": selected_id, "text": text},
                           {"id": prefix + "A", "text": "PRIVATE_PREFIX_MATCH"}]}]}
    item = check([selected_id, prefix + "B", False, "p_omitted"])
    response = {"verified": True, "claim_review": [deepcopy(item) for _ in range(13)]}
    before = deepcopy(response)
    probe = await trace(monkeypatch, payload, response)
    audit = probe.structured_decisions[0]
    assert audit["claim_review_count"] == 13 and audit["claim_review_omitted"] == 1
    assert len(audit["claim_review"]) == 12
    for observed in audit["claim_review"]:
        assert observed["source_passage_ids_count"] == 4 and observed["source_passage_ids_omitted"] == 1
        assert len(observed["source_passage_ids"]) == 2
        assert all(len(ref) <= 160 for ref in observed["source_passage_ids"])
        first, unknown, malformed = observed["source_passage_selections"]
        assert first["status"] == "materialized" and first["quote_characters"] == len(text)
        assert len(first["quote"]) == 280 and first["quote_truncated"] is True
        assert "[credential redacted]" in first["quote"]
        assert unknown["status"] == "unknown" and unknown["source_passage_id_truncated"] is True
        assert malformed["status"] == "malformed" and "quote" not in malformed
    exported = json.dumps(gate.model_observations(probe))
    assert secret not in exported and "PRIVATE_PREFIX_MATCH" not in exported and "p_omitted" not in exported
    assert response == before and audit["verified"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("violation", ["marker_missing", "owner", "goal_owner", "database", "outside_prepare"])
async def test_mapping_never_exports_unmarked_or_foreign_preparation_sources(monkeypatch, violation):
    payload = audit_payload("PRIVATE_FOREIGN_SOURCE")
    response = {"verified": True, "content": "PRIVATE_FOREIGN_RESULT",
                "claim_review": [check(["p_supplied"])]}
    probe = await trace(monkeypatch, payload, response, violation=violation)
    assert probe.structured_decisions == []
    assert "PRIVATE_" not in json.dumps(gate.model_observations(probe))


@pytest.mark.asyncio
async def test_negative_and_ambiguous_model_representations_remain_observations_not_repaired_answers(monkeypatch):
    item = check(["p_supplied"])
    item["source_quotes"] = [{"evidence_id": "ev_input", "quote": "A deliberately nonliteral quote."}]
    response = {"verified": False, "content": "", "claim_review": [item]}
    original = deepcopy(response)
    probe = await trace(monkeypatch, audit_payload(), response)
    observed = probe.structured_decisions[0]
    assert observed["verified"] is False and response == original
    row = observed["claim_review"][0]
    assert row["source_quotes"][0]["quote"] == item["source_quotes"][0]["quote"]
    assert row["source_passage_selections"][0]["quote"] == audit_payload()["evidence"][0]["claim_passages"][0]["text"]
    assert row["source_passage_selections"][0]["origin"] == "code_owned_audit_input"
