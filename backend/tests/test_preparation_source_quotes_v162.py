"""Audit quotes must be authentic passages of the exact supplied evidence.

Synthetic answers exercise the real preparation and persistence boundary.
Authenticity is deliberately not a claim that a passage entails a conclusion.
"""
from copy import deepcopy
import json
from types import SimpleNamespace

from jsonschema import Draft202012Validator
from mongomock_motor import AsyncMongoMockClient
import pytest

from agent import preparation, reasoning
from agent.evidence import EvidenceStore
from agent.execution import StepExecutor
from agent.models import ActionStep, AgentBudget, AgentEvidence, AutonomousGoal, ResultProvenance


OWNER = "synthetic-audit-quotes-v162"
A = "A costa 42 unità per sei periodi; l'importo è anticipato e non rimborsabile."
B = "B costa 9 unità per periodo. La nota non specifica altre condizioni di B."
QUOTE_A = "A costa 42 unità per sei periodi"
QUOTE_B = "B costa 9 unità per periodo."
TEXT = ("Secondo la nota, su sei periodi A costa 42 unità e B 54: la differenza è 12. "
        "A richiede pagamento anticipato non rimborsabile; le altre condizioni di B non sono specificate.")
FALSE_QUOTE = "Entrambe le formule sono esplicitamente non rimborsabili."


async def seed():
    db = AsyncMongoMockClient().preparation_source_quotes_v162
    goal = AutonomousGoal(owner_id=OWNER, status="active", objective="Confrontare le condizioni annotate.",
                          desired_outcome="Un confronto attribuito alla nota con i suoi limiti.")
    await db.agent_goals.insert_one(goal.model_dump())
    sources = []
    for index, claim in enumerate((A, B)):
        row = AgentEvidence(owner_id=OWNER, goal_id=goal.id, claim=claim,
            provenance=ResultProvenance(source_class="internal_observation", provider="synthetic_reader",
                source_refs=[f"document:synthetic-{index}"], certainty_note="Qualifica esterna al claim."))
        await EvidenceStore(db).record(row)
        sources.append(row)
    return SimpleNamespace(db=db, goal=goal, sources=sources,
        step=ActionStep(step_type="prepare", capability_needed="document.create", intent="Confrontare le fonti lette."))


def quote(evidence_id, text):
    return {"evidence_id": evidence_id, "quote": text}


def audit(h):
    ids = [source.id for source in h.sources]
    return {"verified": True, "content": TEXT, "evidence_ids": ids, "reason": "Confronto attribuito alla nota.",
            "claim_review": [
                {"claim": "Su sei periodi A costa 42, B 54; differenza 12.", "evidence_ids": list(ids),
                 "premises": "Applicare entrambi i prezzi a sei periodi.", "support": "derived", "correction": "",
                 "source_quotes": [quote(ids[0], QUOTE_A), quote(ids[1], QUOTE_B)]},
                {"claim": "A è anticipato e non rimborsabile.", "evidence_ids": [ids[0]],
                 "premises": "Condizione riportata per A.", "support": "stated", "correction": "",
                 "source_quotes": [quote(ids[0], "l'importo è anticipato e non rimborsabile.")]},
            ]}


def install(monkeypatch, h, checked, *, before_audit=None):
    seen = []

    async def model(system, encoded, *, response_schema=None):
        payload = json.loads(encoded)
        seen.append((payload, response_schema))
        assert len(encoded) <= 9000
        if "draft" not in payload:
            return {"content": TEXT, "evidence_ids": [source.id for source in h.sources]}
        if before_audit:
            await before_audit()
        return checked

    monkeypatch.setattr(reasoning, "_ask_model", model)
    return seen


@pytest.mark.asyncio
async def test_previous_literal_quote_form_keeps_strict_guard_and_saves_once(monkeypatch):
    h = await seed()
    checked = audit(h)
    original = deepcopy(checked)
    seen = install(monkeypatch, h, checked)
    budget = AgentBudget()
    result = await StepExecutor(h.db).run(OWNER, h.goal, h.step, may_touch_the_world=False, budget=budget)
    assert result.status == "succeeded" and len(seen) == budget.cognitive_calls == 2
    saved = await h.db.agent_goals.find_one({"owner_id": OWNER, "id": h.goal.id})
    assert saved["prepared_text"] == TEXT and saved["prepared_sources"] == checked["evidence_ids"]
    schema = seen[-1][1]
    Draft202012Validator.check_schema(schema)
    # New calls request selections. An adapter returning the previous literal
    # form must still meet the original authenticity guard tested below.
    assert not Draft202012Validator(schema).is_valid(checked)
    review_schema = schema["properties"]["claim_review"]["items"]
    assert "source_passage_ids" in review_schema["required"]
    item = review_schema["properties"]["source_passage_ids"]["items"]
    assert item["enum"] == [p["id"] for row in seen[-1][0]["evidence"] for p in row["claim_passages"]]
    assert checked == original
    assert await h.db.agent_action_attempts.count_documents({}) == 0
    assert all(source.claim in (A, B) for source in h.sources)


BAD = ["missing_review", "empty_review", "review_object", "too_many_claims", "claim_object",
       "missing_support", "invalid_support", "missing_quotes", "quotes_object", "empty_quotes",
       "too_many_quotes", "quote_object", "missing_quote", "empty_quote", "blank_quote",
       "too_long_quote", "invented_quote", "normalized_case", "wrong_evidence_type",
       "missing_evidence_id", "foreign_evidence", "uncited_evidence", "wrong_owned_evidence",
       "quote_only_in_metadata"]


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", BAD)
async def test_positive_audit_cannot_save_missing_fabricated_or_mismatched_quotes(monkeypatch, bad):
    h = await seed()
    checked = audit(h)
    claim = checked["claim_review"][0]
    first = claim["source_quotes"][0]
    if bad == "missing_review": checked.pop("claim_review")
    elif bad == "empty_review": checked["claim_review"] = []
    elif bad == "review_object": checked["claim_review"] = {"claim": claim}
    elif bad == "too_many_claims": checked["claim_review"] = [deepcopy(claim) for _ in range(13)]
    elif bad == "claim_object": checked["claim_review"] = [True]
    elif bad == "missing_support": claim.pop("support")
    elif bad == "invalid_support": claim["support"] = "externally_verified"
    elif bad == "missing_quotes": claim.pop("source_quotes")
    elif bad == "quotes_object": claim["source_quotes"] = first
    elif bad == "empty_quotes": claim["source_quotes"] = []
    elif bad == "too_many_quotes": claim["source_quotes"] = [deepcopy(first) for _ in range(4)]
    elif bad == "quote_object": first["quote"] = {"text": QUOTE_A}
    elif bad == "missing_quote": first.pop("quote")
    elif bad == "empty_quote": first["quote"] = ""
    elif bad == "blank_quote": first["quote"] = " \n "
    elif bad == "too_long_quote":
        h.sources[0].claim += " " + "q" * 300
        await h.db.agent_evidence.update_one({"id": h.sources[0].id}, {"$set": {"claim": h.sources[0].claim}})
        first["quote"] = "q" * 281  # Authentic but beyond the existing response budget.
    elif bad == "invented_quote": first["quote"] = FALSE_QUOTE
    elif bad == "normalized_case": first["quote"] = QUOTE_A.lower()
    elif bad == "wrong_evidence_type": first["evidence_id"] = 1
    elif bad == "missing_evidence_id": first.pop("evidence_id")
    elif bad == "foreign_evidence":
        foreign = h.sources[0].model_copy(update={"id": "evd_foreign", "owner_id": "other-owner"})
        await EvidenceStore(h.db).record(foreign)
        first["evidence_id"] = foreign.id
        claim["evidence_ids"].append(foreign.id)
    elif bad == "uncited_evidence": claim["evidence_ids"] = [h.sources[1].id]
    elif bad == "wrong_owned_evidence": first["evidence_id"] = h.sources[1].id
    elif bad == "quote_only_in_metadata": first["quote"] = "Qualifica esterna al claim."
    original = deepcopy(checked)
    seen = install(monkeypatch, h, checked)
    result = await StepExecutor(h.db).run(OWNER, h.goal, h.step, may_touch_the_world=False)
    assert result.status == "unavailable" and result.error_type == "preparation_review_invalid"
    assert result.retryable is False and len(seen) == 2
    saved = await h.db.agent_goals.find_one({"owner_id": OWNER, "id": h.goal.id})
    assert not saved.get("prepared_text") and not saved.get("prepared_sources")
    assert not result.evidence_refs
    assert not await h.db.agent_evidence.count_documents({"provenance.provider": "generated_draft"})
    feedback = await h.db.agent_journal.find_one({"owner_id": OWNER, "goal_id": h.goal.id,
                                                 "kind": preparation._FEEDBACK_KIND})
    diagnosis = feedback["detail"]["feedback"]
    assert diagnosis["origin"] == "preparation_protocol" and diagnosis["stage"] == "audit"
    assert diagnosis["validation_errors"]
    assert FALSE_QUOTE not in json.dumps(feedback, default=str) + result.observation
    assert "source_quotes" not in diagnosis  # No model quotations promoted to diagnostic facts.
    assert checked == original
    assert await h.db.agent_action_attempts.count_documents({}) == 0


@pytest.mark.asyncio
async def test_authentic_quote_is_not_a_semantic_entailment_oracle(monkeypatch):
    h = await seed()
    checked = audit(h)
    # Deliberate model error: a real price quote does not establish the
    # cancellation claim. This boundary promises authenticity only.
    checked["claim_review"][0]["claim"] = "B può essere interrotto senza vincoli."
    checked["content"] = "B può essere interrotto senza vincoli."
    install(monkeypatch, h, checked)
    result = await preparation.prepare(h.db, OWNER, h.goal, h.step)
    assert result.status == "succeeded"
    assert h.goal.prepared_text == checked["content"]


@pytest.mark.asyncio
@pytest.mark.parametrize("support,verified", [("conditional", True), ("unsupported", True), ("stated", False)])
async def test_missing_premises_can_remain_unknown_and_negative_audit_still_blocks(monkeypatch, support, verified):
    h = await seed()
    checked = audit(h)
    checked["claim_review"] = [{"claim": "La nota non consente quella conclusione.", "evidence_ids": [],
        "premises": "Manca una premessa.", "support": support, "correction": "Omettere la clausola.", "source_quotes": []}]
    checked["verified"] = verified
    if not verified:
        checked["content"], checked["evidence_ids"] = "", []
    install(monkeypatch, h, checked)
    result = await preparation.prepare(h.db, OWNER, h.goal, h.step)
    assert result.status == ("succeeded" if verified else "unavailable")
    if not verified:
        assert result.error_type == "preparation_not_supported" and not h.goal.prepared_text


@pytest.mark.asyncio
async def test_rejected_audit_preserves_any_preexisting_artifact(monkeypatch):
    h = await seed()
    h.goal.prepared_text, h.goal.prepared_sources = "Bozza precedente.", [h.sources[0].id]
    await h.db.agent_goals.update_one({"id": h.goal.id}, {"$set": {
        "prepared_text": h.goal.prepared_text, "prepared_sources": h.goal.prepared_sources}})
    checked = audit(h)
    checked["claim_review"][0]["source_quotes"][0]["quote"] = FALSE_QUOTE
    install(monkeypatch, h, checked)
    result = await preparation.prepare(h.db, OWNER, h.goal, h.step)
    saved = await h.db.agent_goals.find_one({"id": h.goal.id})
    assert result.error_type == "preparation_review_invalid"
    assert saved["prepared_text"] == h.goal.prepared_text == "Bozza precedente."


@pytest.mark.asyncio
async def test_quotes_cannot_borrow_an_owned_row_pruned_from_the_exact_audit_payload(monkeypatch):
    from test_preparation_response_schema_v162 import seed as seed_many

    db, goal, step = await seed_many(sources=12)
    first_payload = None
    seen = []

    async def model(system, encoded, *, response_schema=None):
        nonlocal first_payload
        payload = json.loads(encoded)
        seen.append(payload)
        assert len(encoded) <= 9000
        kept = payload["evidence"][-1]
        if "draft" not in payload:
            first_payload = deepcopy(payload)
            return {"content": "La nota riporta sette unità. " * 135, "evidence_ids": [kept["id"]]}
        present = {row["id"] for row in payload["evidence"]}
        removed = next(row for row in first_payload["evidence"] if row["id"] not in present)
        return {"verified": True, "content": payload["draft"], "evidence_ids": [kept["id"]], "reason": "Sintesi.",
            "claim_review": [{"claim": "Sette unità dichiarate.", "support": "stated", "premises": "Nota letta.",
                "correction": "", "evidence_ids": [removed["id"]],
                "source_quotes": [quote(removed["id"], "sette unità dichiarate.")]}]}

    monkeypatch.setattr(reasoning, "_ask_model", model)
    result = await preparation.prepare(db, goal.owner_id, goal, step)
    assert len(seen) == 2 and seen[1]["evidence_truncated"] is True
    assert result.error_type == "preparation_review_invalid" and not goal.prepared_text


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["owner", "cancelled", "memory_forgotten", "memory_corrected"])
async def test_quote_authenticity_cannot_override_owner_closure_or_current_memory(monkeypatch, change):
    if change.startswith("memory"):
        from test_preparation_recovery_v162 import seed_recovery
        db, goal, plan, source, text = await seed_recovery()
        h = SimpleNamespace(db=db, goal=goal, sources=[source], step=plan.steps[1])
        checked = {"verified": True, "content": "La nota contiene i prezzi annotati.", "evidence_ids": [source.id],
            "reason": "Dati riferiti.", "claim_review": [{"claim": "A costa 84 crediti per quattro periodi.",
                "premises": "Prezzo annotato.", "support": "stated", "correction": "", "evidence_ids": [source.id],
                "source_quotes": [quote(source.id, "A costa 84 crediti per quattro periodi")]}]}

        async def mutate():
            update = {"status": "forgotten"} if change == "memory_forgotten" else {"statement": text + " Correzione."}
            await db.memories.update_one({"user_id": goal.owner_id}, {"$set": update, "$inc": {"revision": 1}})
    else:
        h = await seed()
        checked = audit(h)

        async def mutate():
            await h.db.agent_goals.update_one({"id": h.goal.id}, {"$set": {"status": "cancelled"}})

    seen = install(monkeypatch, h, checked, before_audit=mutate if change != "owner" else None)
    result = await preparation.prepare(h.db, "different-owner" if change == "owner" else h.goal.owner_id,
                                       h.goal, h.step)
    expected = "preparation_owner_mismatch" if change == "owner" else (
        "preparation_goal_unavailable" if change == "cancelled" else "preparation_memory_changed")
    assert result.error_type == expected
    assert len(seen) == (0 if change == "owner" else 2)
    saved = await h.db.agent_goals.find_one({"id": h.goal.id})
    assert not saved.get("prepared_text") and not result.claims
