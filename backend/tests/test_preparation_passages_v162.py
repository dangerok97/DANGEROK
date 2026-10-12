"""Literal source selection uses current supplied passages, not model recopying."""
from copy import deepcopy
import json

from jsonschema import Draft202012Validator
import pytest

from agent import preparation, reasoning
from agent.execution import StepExecutor
from agent.models import AgentBudget
from agent.preparation_passages import build_audit_passages, materialize_audit_passages
from test_preparation_source_quotes_v162 import OWNER, TEXT, audit, seed


def source_claim(row):
    """Decode the actual generation/audit fixture representation without omission."""
    return row["claim"] if "claim" in row else "".join(p["text"] for p in row["claim_passages"])


def selected_answer(h, payload):
    answer = audit(h)
    by_evidence = {row["id"]: [p["id"] for p in row["claim_passages"]] for row in payload["evidence"]}
    for check in answer["claim_review"]:
        check.pop("source_quotes")
        check["source_passage_ids"] = [p for ref in check["evidence_ids"] for p in by_evidence[ref]]
    return answer


@pytest.mark.parametrize("claim", [
    "  Premessa.\nSeconda frase: è e\u0300 diverso; € e 🧺.\tFine.  ",
    "È un testo con condizioni e limiti. " * 16,
    "🧺" * 600,
    "x" * 210 + " " + "y" * 210 + "\n" + "z" * 178,
])
def test_passages_round_trip_every_character_and_preserve_provenance(claim):
    assert len(claim) <= 600
    rows = [{"id": "evd_owned", "claim": claim, "source_refs": ["source:owned"],
             "limits": "Condizioni da conservare.", "memory_reads": [{"revision": 7}]}]
    original = deepcopy(rows)
    projected, index = build_audit_passages(rows)
    assert "claim" not in projected[0]
    assert source_claim(projected[0]) == claim
    passages = projected[0]["claim_passages"]
    assert 1 <= len(passages) <= 3 and all(0 < len(p["text"]) <= 280 for p in passages)
    for passage in passages:
        assert index[passage["id"]] == {"evidence_id": "evd_owned", "quote": passage["text"]}
        assert passage["text"] in claim
    assert {k: v for k, v in projected[0].items() if k != "claim_passages"} == {
        k: v for k, v in rows[0].items() if k != "claim"}
    projected[0]["memory_reads"][0]["revision"] = 99
    assert rows == original


def test_passage_ids_bind_exact_source_and_revision_without_normalization():
    def ids(evidence, claim):
        return set(build_audit_passages([{"id": evidence, "claim": claim}])[1])

    original = ids("evd_a", "Prezzo 150. Rimborso non indicato.")
    assert original == ids("evd_a", "Prezzo 150. Rimborso non indicato.")
    assert not original & ids("evd_b", "Prezzo 150. Rimborso non indicato.")
    assert not original & ids("evd_a", "Prezzo 120. Rimborso non indicato.")
    assert not ids("evd_a", "è") & ids("evd_a", "e\u0300")


@pytest.mark.asyncio
async def test_native_selection_reaches_real_preparation_with_two_calls_and_no_source_changes(monkeypatch):
    h = await seed()
    seen = []
    answers = []

    async def model(_system, encoded, *, response_schema=None):
        payload = json.loads(encoded)
        assert len(encoded) <= 9000
        answer = selected_answer(h, payload) if "draft" in payload else {
            "content": TEXT, "evidence_ids": [source.id for source in h.sources]}
        assert Draft202012Validator(response_schema).is_valid(answer)
        seen.append((payload, response_schema))
        answers.append((answer, deepcopy(answer)))
        return answer

    monkeypatch.setattr(reasoning, "_ask_model", model)
    budget = AgentBudget()
    result = await StepExecutor(h.db).run(OWNER, h.goal, h.step, may_touch_the_world=False, budget=budget)
    assert result.status == "succeeded" and len(seen) == budget.cognitive_calls == 2
    payload, schema = seen[-1]
    assert [source_claim(row) for row in payload["evidence"]] == [source.claim for source in h.sources]
    selection = schema["properties"]["claim_review"]["items"]["properties"]["source_passage_ids"]
    assert set(selection["items"]["enum"]) == {
        p["id"] for row in payload["evidence"] for p in row["claim_passages"]}
    rows = preparation._source_rows(h.sources)
    _, index = build_audit_passages(rows)
    materialized, errors = materialize_audit_passages(answers[-1][0], index)
    assert errors == preparation._audit_review_errors(materialized, rows) == []
    assert all(original == snapshot for original, snapshot in answers)
    saved = await h.db.agent_goals.find_one({"owner_id": OWNER, "id": h.goal.id})
    assert saved["prepared_text"] == TEXT
    assert await h.db.agent_action_attempts.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("violation", ["wrong_type", "wrong_item", "too_many", "unknown", "old_revision",
                                      "uncited", "ambiguous", "empty_stated"])
async def test_invalid_selection_cannot_save_or_manufacture_passages(monkeypatch, violation):
    h = await seed()
    original = []

    async def model(_system, encoded, *, response_schema=None):
        payload = json.loads(encoded)
        if "draft" not in payload:
            return {"content": TEXT, "evidence_ids": [source.id for source in h.sources]}
        answer = selected_answer(h, payload)
        check = answer["claim_review"][0]
        ids = check["source_passage_ids"]
        if violation == "wrong_type": check["source_passage_ids"] = ids[0]
        elif violation == "wrong_item": check["source_passage_ids"] = [True]
        elif violation == "too_many": check["source_passage_ids"] = [ids[0]] * 4
        elif violation == "unknown": check["source_passage_ids"] = ["PRIVATE_UNKNOWN_ID"]
        elif violation == "old_revision":
            rows = preparation._source_rows(h.sources)
            rows[0]["claim"] += " Vecchia revisione."
            check["source_passage_ids"] = [next(iter(build_audit_passages(rows)[1]))]
        elif violation == "uncited": check["evidence_ids"] = [h.sources[1].id]
        elif violation == "ambiguous": check["source_quotes"] = [{"evidence_id": h.sources[0].id, "quote": "PRIVATE_QUOTE"}]
        else: check["source_passage_ids"] = []
        original.append((answer, deepcopy(answer)))
        return answer

    monkeypatch.setattr(reasoning, "_ask_model", model)
    result = await preparation.prepare(h.db, OWNER, h.goal, h.step)
    assert result.error_type == "preparation_review_invalid" and result.retryable is False
    assert not h.goal.prepared_text and not result.claims
    saved = await h.db.agent_goals.find_one({"owner_id": OWNER, "id": h.goal.id})
    assert not saved.get("prepared_text") and not saved.get("prepared_sources")
    assert all(answer == before for answer, before in original)
    diagnostic = await h.db.agent_journal.find_one({"kind": preparation._FEEDBACK_KIND})
    assert "PRIVATE_" not in json.dumps(diagnostic, default=str)


@pytest.mark.asyncio
async def test_selected_authentic_passage_is_still_not_a_semantic_oracle(monkeypatch):
    h = await seed()

    async def model(_system, encoded, *, response_schema=None):
        payload = json.loads(encoded)
        if "draft" not in payload:
            return {"content": TEXT, "evidence_ids": [source.id for source in h.sources]}
        answer = selected_answer(h, payload)
        answer["content"] = "Affermazione qualitativa non sostenuta dalla fonte."
        return answer

    monkeypatch.setattr(reasoning, "_ask_model", model)
    result = await preparation.prepare(h.db, OWNER, h.goal, h.step)
    # This deliberately wrong model verdict remains wrong: source selection
    # authenticates passages, and must not be reported as semantic validation.
    assert result.status == "succeeded" and h.goal.prepared_text == "Affermazione qualitativa non sostenuta dalla fonte."
