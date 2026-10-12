"""Source qualifications must survive the preparation and verification boundary.

The real Memory reader, executor, evidence store and preparation code operate
on synthetic records. Model replies are injected: these tests prove the
payload, audit/persistence and decision contracts, not model semantic quality.
No model, network, account or external effect is exercised.
"""
import json
from unittest.mock import AsyncMock

import pytest
from test_preparation_passages_v162 import source_claim
from mongomock_motor import AsyncMongoMockClient

from agent import reasoning
from agent.evidence import EvidenceStore, for_verification
from agent.execution import StepExecutor
from agent.models import ActionStep, AgentBudget, AutonomousGoal
from test_agent_preparation_dependency_v162 import comparison_claim_review


OWNER = "synthetic-preparation-grounding-v162"
MEMORY = "mem_synthetic_comparison"
SOURCE = (
    "Ho annotato che A costa 84 crediti per quattro periodi e B costa 25 crediti "
    "per periodo. La quota di A non è rimborsabile."
)
UNSUPPORTED = (
    "Su quattro periodi A costa 84 crediti e B 100: la differenza è 16 crediti. "
    "B è sempre interrompibile senza vincoli. Interrompere A prima della fine "
    "annulla sempre il risparmio. Devi contattare il fornitore prima di ogni confronto."
)
CORRECTED = (
    "Secondo il promemoria che hai salvato, A costa 84 crediti per quattro periodi "
    "e la quota non è rimborsabile. Con il prezzo annotato di 25 crediti per periodo, "
    "B costa 100 crediti su quattro periodi: in questo confronto A costa 16 crediti "
    "in meno. Il risultato per una durata diversa dipende dalla durata e dalle "
    "condizioni applicabili; il promemoria non specifica le condizioni di interruzione di B."
)


@pytest.fixture(autouse=True)
def no_uncontrolled_model_calls(monkeypatch):
    monkeypatch.setattr(reasoning, "_ask_model", AsyncMock(
        side_effect=AssertionError("Every model reply must be injected; no network is allowed"),
    ))


async def seed_read(*, partial=False, authority="user_stated", epistemic="known"):
    db = AsyncMongoMockClient().preparation_grounding_v162
    goal = AutonomousGoal(
        owner_id=OWNER, status="active", source_kind="memory", source_refs=[MEMORY],
        objective="Preparare un confronto dai dati del promemoria.",
        desired_outcome="Un confronto scritto con premesse e limiti espliciti.",
    )
    text = SOURCE
    if partial:
        text += " Contesto ulteriore non ancora letto." * 25
        text += " CONDIZIONE_NEL_SEGUITO: il conteggio effettivo dipende dalla durata."
    await db.agent_goals.insert_one(goal.model_dump())
    await db.memories.insert_one({
        "id": MEMORY, "user_id": OWNER, "status": "known", "revision": 1,
        "statement": text, "authority": authority, "epistemic_status": epistemic,
        "created_at": "2020-01-01T00:00:00+00:00",
    })
    budget = AgentBudget()
    read = await StepExecutor(db).run(OWNER, goal, ActionStep(
        step_type="inspect", capability_needed="information.read",
        input_refs=[MEMORY], intent="Leggere la nota citata e i suoi limiti.",
    ), may_touch_the_world=False, budget=budget)
    # Reload as the next worker would: qualifications cannot live only in
    # the reader's immediate return value or an in-process object.
    source, = await EvidenceStore(db).for_goal(OWNER, goal.id)
    goal = AutonomousGoal(**await db.agent_goals.find_one({"owner_id": OWNER, "id": goal.id}))
    return db, goal, source, read, budget, text


def prepare_step():
    return ActionStep(
        step_type="prepare", capability_needed="document.create",
        intent="Scrivere il confronto e distinguere le condizioni non stabilite.",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("partial,authority,epistemic", [
    (False, "user_stated", "known"),
    (False, "user_stated", "confirmed"),
    (False, "unknown", "unknown"),
    (True, "user_stated", "known"),
])
async def test_source_qualifications_reach_draft_audit_and_verifier(
    monkeypatch, partial, authority, epistemic,
):
    db, goal, source, read, budget, text = await seed_read(
        partial=partial, authority=authority, epistemic=epistemic,
    )
    assert read.status == ("partial" if partial else "succeeded")
    assert source.claim == text[:600]
    assert f"autorità: {authority}" in source.supports
    assert f"stato: {epistemic}" in source.supports
    pages = source.provenance.for_ai()["memory_reads"]
    assert pages[0]["total"] == len(text)
    assert pages[0]["next_offset"] == (600 if partial else None)
    conditional = (
        "Nel testo disponibile è riportato il prezzo di A e B. Questo riepilogo "
        "si limita a quanto annotato; non prova condizioni non specificate né "
        "una conferma attuale da parte di terzi."
    )
    if partial:
        conditional += " La lettura è incompleta: resta il seguito della nota."
    captured = []

    async def model(system, encoded, *, response_schema=None):
        payload = json.loads(encoded)
        captured.append((system, payload))
        assert len(encoded) <= 9000
        if "what_was_done" in payload:
            found = payload["what_was_done"]
            row, = [row for row in found["what_was_found"] if row["evidence_id"] == source.id]
            assert found["prepared_result"] == conditional
            assert row["what_was_found"] == source.claim
            assert row["bears_on"] == source.supports
            assert row["memory_reads"] == pages
            assert "validità attuale" in row["note"]
            return {
                "outcome": "uncertain", "criteria_met": [], "relied_on": [source.id],
                "what_is_missing": "Il risultato richiesto dipende da condizioni non stabilite.",
            }
        row, = payload["evidence"]
        assert row["id"] == source.id and source_claim(row) == source.claim
        assert row.get("bears_on") == source.supports
        assert row["memory_reads"] == pages
        assert "validità attuale" in row["limits"]
        if partial:
            assert "incomplet" in row["limits"].lower()
            assert "CONDIZIONE_NEL_SEGUITO" not in encoded
        answer = {"content": conditional, "evidence_ids": [source.id]}
        if "draft" in payload:
            answer.update(verified=True, claim_review=[{
                "claim": "Nel testo disponibile sono riportati i prezzi di A e B.",
                "premises": "Il riepilogo è limitato al testo letto, senza confermare condizioni ignote.",
                "support": "stated", "correction": "", "evidence_ids": [source.id],
                "source_quotes": comparison_claim_review(source.id)[0]["source_quotes"],
            }])
        return answer

    monkeypatch.setattr(reasoning, "_ask_model", model)
    prepared = await StepExecutor(db).run(
        OWNER, goal, prepare_step(), may_touch_the_world=False, budget=budget,
    )
    assert prepared.status == "succeeded"
    evidence = await EvidenceStore(db).for_goal(OWNER, goal.id)
    result = await reasoning.verify_goal(goal.for_ai(), evidence={
        "what_was_found": for_verification(evidence), "prepared_result": goal.prepared_text,
    })
    assert result["outcome"] == "uncertain" and result["criteria_met"] == []
    assert budget.capability_calls == 2 and budget.cognitive_calls == 2
    assert len(captured) == 3  # Draft, existing audit, existing verifier.
    for system, _ in captured:
        assert reasoning._GROUNDED_RESULT in system
    assert "CONDIZIONE_NEL_SEGUITO" not in str(captured)
    saved = await db.agent_goals.find_one({"owner_id": OWNER, "id": goal.id})
    assert saved["prepared_text"] == conditional and saved["prepared_sources"] == [source.id]
    assert saved["status"] == "active"  # A successful prepare is not goal completion.
    assert await db.agent_action_attempts.count_documents({}) == 0


@pytest.mark.asyncio
async def test_audit_corrects_individual_claims_before_any_text_or_evidence_is_saved(monkeypatch):
    db, goal, source, _, budget, _ = await seed_read()
    observed = []

    async def model(system, encoded, *, response_schema=None):
        payload = json.loads(encoded)
        observed.append((system, payload))
        if "draft" not in payload:
            return {"content": UNSUPPORTED, "evidence_ids": [source.id]}
        assert payload["draft"] == UNSUPPORTED
        assert payload["evidence"][0]["bears_on"] == source.supports
        saved = await db.agent_goals.find_one({"owner_id": OWNER, "id": goal.id})
        assert not saved.get("prepared_text")
        assert await db.agent_evidence.count_documents({"goal_id": goal.id}) == 1
        return {"verified": True, "content": CORRECTED, "evidence_ids": [source.id],
                "claim_review": comparison_claim_review(source.id)}

    monkeypatch.setattr(reasoning, "_ask_model", model)
    result = await StepExecutor(db).run(
        OWNER, goal, prepare_step(), may_touch_the_world=False, budget=budget,
    )
    assert result.status == "succeeded" and len(observed) == 2
    saved = await db.agent_goals.find_one({"owner_id": OWNER, "id": goal.id})
    assert saved["prepared_text"] == goal.prepared_text == CORRECTED
    assert saved["prepared_sources"] == [source.id]
    assert result.provenance.provider == "generated_draft"
    assert result.provenance.source_refs == [source.id]
    evidence = await EvidenceStore(db).for_goal(OWNER, goal.id)
    generated = [item for item in evidence if item.provenance.provider == "generated_draft"]
    assert generated and all(item.id in result.evidence_refs for item in generated)
    assert all("non è una verifica indipendente" in item.provenance.certainty_note for item in generated)
    assert "annulla sempre" not in str([item.claim for item in generated])
    assert "Devi contattare" not in str([item.claim for item in generated])
    for system, _ in observed:
        assert reasoning._GROUNDED_RESULT in system


@pytest.mark.asyncio
async def test_negative_audit_cannot_be_replaced_by_successful_read_or_valid_reference(monkeypatch):
    db, goal, source, read, budget, _ = await seed_read()
    assert read.status == "succeeded"
    model = AsyncMock(side_effect=[
        {"content": UNSUPPORTED, "evidence_ids": [source.id]},
        {"verified": False, "content": "", "evidence_ids": [source.id]},
    ])
    monkeypatch.setattr(reasoning, "_ask_model", model)
    result = await StepExecutor(db).run(
        OWNER, goal, prepare_step(), may_touch_the_world=False, budget=budget,
    )
    assert result.status == "unavailable" and result.error_type == "preparation_not_supported"
    assert not result.evidence_refs and not goal.prepared_text
    saved = await db.agent_goals.find_one({"owner_id": OWNER, "id": goal.id})
    assert not saved.get("prepared_text") and not saved.get("prepared_sources")
    assert await db.agent_evidence.count_documents({"goal_id": goal.id}) == 1
    assert model.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["achieved", "partially_achieved", "uncertain"])
async def test_verifier_preserves_qualified_result_and_its_own_judgement(monkeypatch, outcome):
    db, goal, source, _, _, _ = await seed_read()
    reply = {
        "outcome": outcome, "reasoning": "Synthetic judgement; not a semantic-model assertion.",
        "criteria_met": ["confronto condizionale"] if outcome == "achieved" else [],
        "what_is_missing": "" if outcome == "achieved" else "Una premessa della conclusione.",
        "relied_on": [source.id],
    }
    model = AsyncMock(return_value=reply)
    monkeypatch.setattr(reasoning, "_ask_model", model)
    result = await reasoning.verify_goal(goal.for_ai(), evidence={
        "what_was_found": for_verification([source]), "prepared_result": CORRECTED,
    })
    assert result is reply and result["outcome"] == outcome
    assert model.await_count == 1
    system, encoded = model.await_args.args
    assert reasoning._GROUNDED_RESULT in system
    payload = json.loads(encoded)
    assert payload["what_was_done"]["prepared_result"] == CORRECTED
    assert payload["what_was_done"]["what_was_found"][0]["bears_on"] == source.supports
    assert len(encoded) <= 9000
