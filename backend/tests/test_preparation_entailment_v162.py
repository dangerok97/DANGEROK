"""Separated audit reasoning stays fallible and preserves source-bound saving.

These controlled replies exercise native schema/SDK transport and the local
protocol boundary. They do not establish that a live model reasons correctly.
"""
from copy import deepcopy
import json

from jsonschema import Draft202012Validator
import pytest

from agent import preparation, reasoning
from agent.execution import StepExecutor
from agent.models import AgentBudget
from agent.preparation_schema import audit_schema
from scripts import autonomy_completion_eval_v162 as gate
from test_agent_preparation_dependency_v162 import fake_gemini
from test_pending_outcome_contract_v162 import synthetic_transport_only  # noqa: F401
from test_preparation_passages_v162 import selected_answer, source_claim
from test_preparation_source_quotes_v162 import OWNER, TEXT, audit, seed


FIELDS = ("inference_or_gap", "compatible_counterexample")


def separated(answer):
    """Supply the actual reasoning for this fixture, without changing its result."""
    answer["claim_review"][0].update(
        premises="A costa 42 per sei periodi; B costa 9 per periodo, secondo la nota.",
        inference_or_gap="Sul medesimo orizzonte: 9 × 6 = 54; 54 − 42 = 12.",
        compatible_counterexample="",
    )
    answer["claim_review"][1].update(
        premises="La nota attribuisce ad A pagamento anticipato e assenza di rimborso.",
        inference_or_gap="La condizione è riportata per A; non stabilisce quella di B.",
        compatible_counterexample="",
    )
    return answer


@pytest.mark.asyncio
async def test_native_schema_and_real_sdk_keep_separated_review_with_two_calls(monkeypatch):
    h = await seed()
    # This runner intentionally accepts its own synthetic owner only. Build
    # this isolated record under that owner; do not relax the runtime fence.
    await h.db.agent_goals.update_one({"id": h.goal.id}, {"$set": {"owner_id": gate.OWNER}})
    await h.db.agent_evidence.update_many({"goal_id": h.goal.id}, {"$set": {"owner_id": gate.OWNER}})
    h.goal.owner_id = gate.OWNER
    for source in h.sources:
        source.owner_id = gate.OWNER
    await h.db.eval_guards.insert_one({"_id": gate.VERSION, "owner": gate.OWNER})
    native = audit_schema([s.id for s in h.sources], ["p_synthetic"])
    assert set(FIELDS) <= set(native["properties"]["claim_review"]["items"]["required"])
    replies = []

    def reply(_system, payload):
        assert [source_claim(row) for row in payload["evidence"]] == [s.claim for s in h.sources]
        if "draft" not in payload:
            return {"content": TEXT, "evidence_ids": [s.id for s in h.sources]}
        answer = separated(selected_answer(h, payload))
        schema = audit_schema([row["id"] for row in payload["evidence"]],
            [p["id"] for row in payload["evidence"] for p in row["claim_passages"]])
        check_schema = schema["properties"]["claim_review"]["items"]
        for field in FIELDS:
            assert field in check_schema["required"]
            assert check_schema["properties"][field]["type"] == "string"
        assert Draft202012Validator(schema).is_valid(answer)
        replies.append(deepcopy(answer))
        return answer

    transported = fake_gemini(monkeypatch, reply)
    with gate.isolated_engine(h.db, mode="live") as probe:
        budget = AgentBudget()
        result = await StepExecutor(h.db).run(gate.OWNER, h.goal, h.step,
            may_touch_the_world=False, budget=budget)
    assert result.status == "succeeded"
    assert len(transported) == budget.cognitive_calls == probe.model_attempts == probe.model_http_requests == 2
    assert transported[1]["payload"]["draft"] == TEXT
    assert transported[1]["payload"]["request"]["desired_outcome"] == h.goal.desired_outcome
    observed = probe.structured_decisions[-1]["claim_review"]
    for actual, original in zip(observed, replies[0]["claim_review"]):
        assert {key: actual[key] for key in FIELDS} == {key: original[key] for key in FIELDS}
    saved = await h.db.agent_goals.find_one({"owner_id": gate.OWNER, "id": h.goal.id})
    assert saved["prepared_text"] == TEXT and saved["prepared_sources"] == replies[0]["evidence_ids"]
    assert not probe.blocked_effects and not probe.network.blocked
    assert await h.db.agent_action_attempts.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("bad", ["missing", None, {"private": "PRIVATE_PROTOCOL_VALUE"}, True])
async def test_native_review_rejects_missing_or_non_text_reasoning_without_saving(monkeypatch, field, bad):
    h = await seed()
    calls, answers = [], []
    h.goal.prepared_text = "Bozza precedente, da preservare."
    h.goal.prepared_sources = [h.sources[0].id]
    await h.db.agent_goals.update_one({"owner_id": OWNER, "id": h.goal.id}, {"$set": {
        "prepared_text": h.goal.prepared_text, "prepared_sources": h.goal.prepared_sources}})

    async def model(_system, encoded, *, response_schema=None):
        payload = json.loads(encoded)
        calls.append(payload)
        if "draft" not in payload:
            return {"content": TEXT, "evidence_ids": [s.id for s in h.sources]}
        answer = separated(selected_answer(h, payload))
        if bad == "missing":
            answer["claim_review"][0].pop(field)
        else:
            answer["claim_review"][0][field] = bad
        assert not Draft202012Validator(response_schema).is_valid(answer)
        answers.append((answer, deepcopy(answer)))
        return answer  # An adapter can violate the schema; the local guard must hold.

    monkeypatch.setattr(reasoning, "_ask_model", model)
    result = await preparation.prepare(h.db, OWNER, h.goal, h.step)
    assert result.status == "unavailable" and result.error_type == "preparation_review_invalid"
    assert result.retryable is False and len(calls) == 2 and not result.claims
    saved = await h.db.agent_goals.find_one({"owner_id": OWNER, "id": h.goal.id})
    assert saved["prepared_text"] == "Bozza precedente, da preservare."
    assert not await h.db.agent_evidence.count_documents({"provenance.provider": "generated_draft"})
    record = await h.db.agent_journal.find_one({"kind": preparation._FEEDBACK_KIND})
    feedback = record["detail"]["feedback"]
    assert feedback["origin"] == "preparation_protocol" and feedback["stage"] == "audit"
    assert feedback["validation_errors"][0]["field"] == "claim_review." + field
    assert feedback["validation_errors"][0]["issue"] == ("missing" if bad == "missing" else "wrong_type")
    assert "PRIVATE_PROTOCOL_VALUE" not in json.dumps(record, default=str) + result.observation
    assert all(answer == original for answer, original in answers)


@pytest.mark.asyncio
@pytest.mark.parametrize("form", ["old", "separated", "partial", "wrong_type"])
async def test_legacy_literal_quotes_are_explicit_and_never_filled_in(monkeypatch, form):
    h = await seed()
    checked = audit(h)
    if form != "old":
        separated(checked)
    if form == "partial":
        checked["claim_review"][0].pop(FIELDS[1])
    if form == "wrong_type":
        checked["claim_review"][0][FIELDS[0]] = []
    original = deepcopy(checked)

    async def model(_system, encoded, *, response_schema=None):
        if "draft" not in json.loads(encoded):
            return {"content": TEXT, "evidence_ids": [s.id for s in h.sources]}
        return checked

    monkeypatch.setattr(reasoning, "_ask_model", model)
    result = await preparation.prepare(h.db, OWNER, h.goal, h.step)
    assert result.status == ("succeeded" if form in ("old", "separated") else "unavailable")
    assert checked == original
    if form == "old":
        assert all(field not in row for row in checked["claim_review"] for field in FIELDS)
    if form in ("partial", "wrong_type"):
        assert result.error_type == "preparation_review_invalid" and not h.goal.prepared_text


def test_review_feedback_and_report_keep_reasoning_bounded_and_non_authoritative():
    checked = {"verified": False, "reason": "La conseguenza richiede una premessa non nota.",
        "claim_review": [{"claim": "Una conclusione da rivedere.", "premises": "La nota riporta un solo vincolo.",
            "inference_or_gap": "Non è dato il requisito necessario per estendere quel vincolo.",
            "compatible_counterexample": "L'altra situazione potrebbe avere un requisito diverso.",
            "support": "unsupported", "correction": "Lasciare la conseguenza irrisolta.",
            "evidence_ids": ["ev_owned"], "source_quotes": []}]}
    original = deepcopy(checked)
    feedback = preparation._review_feedback(checked, {"ev_owned"})
    assert feedback["origin"] == "preparation_audit"
    assert {key: feedback["claim_review"][0][key] for key in FIELDS} == {
        key: checked["claim_review"][0][key] for key in FIELDS}
    assert len(preparation._json(feedback)) <= 1400
    observed = gate._preparation_claim_review(checked)["claim_review"][0]
    assert all(observed[key] == checked["claim_review"][0][key] for key in FIELDS)
    for field in FIELDS:
        checked["claim_review"][0][field] = "Una diagnosi lunga. " * 200
    bounded = preparation._review_feedback(checked, {"ev_owned"})
    assert bounded["truncated"] and len(preparation._json(bounded)) <= 1400
    observed = gate._preparation_claim_review(checked)["claim_review"][0]
    assert set(FIELDS) <= set(observed["truncated_fields"])
    assert all(len(observed[key]) <= gate.PREPARATION_CLAIM_TEXT_LIMIT for key in FIELDS)
    assert "source_quotes" not in feedback and original["verified"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("verified", [False, True])
async def test_new_reasoning_text_never_changes_the_model_verdict_or_proves_entailment(monkeypatch, verified):
    h = await seed()

    async def model(_system, encoded, *, response_schema=None):
        payload = json.loads(encoded)
        if "draft" not in payload:
            return {"content": TEXT, "evidence_ids": [s.id for s in h.sources]}
        checked = separated(selected_answer(h, payload))
        checked["verified"] = verified
        checked["content"] = "Una conclusione deliberatamente non sostenuta."
        checked["claim_review"][0]["inference_or_gap"] = "Esiste una premessa non stabilita."
        checked["claim_review"][0]["compatible_counterexample"] = "Un caso possibile smentisce la conclusione."
        return checked

    monkeypatch.setattr(reasoning, "_ask_model", model)
    result = await preparation.prepare(h.db, OWNER, h.goal, h.step)
    # This deliberately inconsistent positive response is still a model error.
    # Formatting checks must not be presented as an independent semantic oracle.
    assert result.status == ("succeeded" if verified else "unavailable")
    if verified:
        assert h.goal.prepared_text == "Una conclusione deliberatamente non sostenuta."
    else:
        assert result.error_type == "preparation_not_supported" and not h.goal.prepared_text
