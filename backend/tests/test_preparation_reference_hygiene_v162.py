"""Owner-safe user-facing provenance: a model-approved internal ID is no citation.

Fully scripted model replies, synthetic Memory/evidence, no network, no real
person or device. The safety gate refuses; it does not rewrite source facts.
"""
from copy import deepcopy
import json

import pytest

from agent import preparation, reasoning
from test_preparation_source_quotes_v162 import OWNER, TEXT, audit, seed


@pytest.mark.parametrize("input_text,detected", [
    ("Fonte: mem_43262246ed92296b9353, dichiarata.", True),
    ("Rif. evd_1234567890abcdef", True),
    ("Sorgente sit_abcdefabcdefabcdef", True),
    ("Sorgente gol_abcdefabcdefabcdef", True),
    ("Bozza prep_abcdefabcdefabcdef", True),
    ("Secondo la nota salvata dalla persona, senza conferma esterna.", False),
    ("Riferimento me_m not machine identity", False),
    ("MEM_example", False),
    ("test mem_012", False),
])
def test_only_opaque_machine_handles_are_detected(input_text, detected):
    assert bool(preparation._exposes_internal_source_id(input_text)) is detected


@pytest.mark.asyncio
@pytest.mark.parametrize("challenge_enabled", [False, True])
async def test_model_approved_raw_memory_id_cannot_be_published_or_replace_prior_work(
    monkeypatch, challenge_enabled
):
    monkeypatch.setenv("ORA_PREPARATION_BLIND_CHALLENGE", "1" if challenge_enabled else "0")
    h = await seed()
    internal = "mem_43262246ed92296b9353"
    draft = f"Il confronto proviene da {internal}: A costa 42 e B 54."
    checked = audit(h)
    checked["content"] = draft
    original = deepcopy(checked)
    previous = "Risultato precedente, non da sostituire."
    h.goal.prepared_text, h.goal.prepared_sources = previous, [h.sources[0].id]
    await h.db.agent_goals.update_one(
        {"owner_id": OWNER, "id": h.goal.id},
        {"$set": {"prepared_text": previous, "prepared_sources": h.goal.prepared_sources}},
    )
    payloads = []

    async def model(system, encoded, *, response_schema=None):
        payload = json.loads(encoded)
        payloads.append(payload)
        if payload.get("stage") == "blind_source_challenge":
            pytest.fail("Raw machine references must be stopped before extra model billing")
        if "draft" in payload:
            return checked
        return {"content": draft, "evidence_ids": [s.id for s in h.sources]}

    monkeypatch.setattr(reasoning, "_ask_model", model)
    result = await preparation.prepare(h.db, OWNER, h.goal, h.step)
    assert result.status == "unavailable" and result.error_type == "preparation_reference_leak"
    assert result.retryable and len(payloads) == 2 and checked == original
    saved = await h.db.agent_goals.find_one({"owner_id": OWNER, "id": h.goal.id})
    assert saved["prepared_text"] == h.goal.prepared_text == previous
    assert not await h.db.agent_evidence.count_documents(
        {"provenance.provider": "generated_draft"}
    )
    feedback = await h.db.agent_journal.find_one({
        "owner_id": OWNER, "goal_id": h.goal.id, "kind": preparation._FEEDBACK_KIND
    })
    assert feedback["detail"]["feedback"]["origin"] == "preparation_protocol"
    assert feedback["detail"]["feedback"]["stage"] == "audit"
    assert feedback["detail"]["feedback"]["validation_errors"][0]["issue"] == "internal_reference"
    assert internal not in json.dumps(feedback, default=str) + result.observation


@pytest.mark.asyncio
async def test_human_readable_qualified_source_remains_eligible_for_saving(monkeypatch):
    monkeypatch.setenv("ORA_PREPARATION_BLIND_CHALLENGE", "0")
    h = await seed()
    positive = audit(h)
    positive["content"] = "Secondo la nota della persona, " + TEXT
    async def model(_system, encoded, *, response_schema=None):
        payload = json.loads(encoded)
        return positive if "draft" in payload else {
            "content": positive["content"],
            "evidence_ids": [s.id for s in h.sources],
        }
    monkeypatch.setattr(reasoning, "_ask_model", model)
    result = await preparation.prepare(h.db, OWNER, h.goal, h.step)
    assert result.status == "succeeded"
    assert h.goal.prepared_text == positive["content"]
