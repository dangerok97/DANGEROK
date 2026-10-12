"""Prior model judgments survive admission as context, never completion proof.

Owned in-memory data exercise candidate parsing, persistence/reload and the
actual admission service. The SDK case uses fake HTTP only; the other model
answers are explicit fixtures. No case proves real-model judgment quality.
"""
from copy import deepcopy
import json
from unittest.mock import AsyncMock

from mongomock_motor import AsyncMongoMockClient
import pytest

from agent import reasoning
from agent.admission import drain, fingerprint
from agent.memory_sources import read_memory_previews
from opportunities import reasoning as opportunity_reasoning
from opportunities.repository import OpportunityRepository
from opportunities.service import OpportunityService
from scripts import autonomy_completion_eval_v162 as gate
from test_agent_preparation_dependency_v162 import fake_gemini
from test_pending_outcome_contract_v162 import synthetic_transport_only  # noqa: F401


OWNER = gate.OWNER
MEMORY = "mem_assessment_context_owned"
OTHER = "mem_assessment_context_foreign"
SOURCE = gate.FIXTURE_NOTE
NO_GOAL = {"outcome": "no_goal", "reasoning": "Decisione sintetica: nessun lavoro ulteriore."}


def assessment(**changes):
    return {
        "desired_outcome": "Il confronto scritto è disponibile alla persona.",
        "outcome_state": "open",
        "remaining_internal_work": "Preparare il confronto dai dati attribuiti alla nota.",
        "supporting_refs": [MEMORY], "completion_refs": [], **changes,
    }


def proposal(value=None, *, include=True):
    result = {
        "identity_key": "synthetic:assessment-context",
        "what": "Confronto delle condizioni annotate.",
        "why_it_matters": "Il confronto scritto utile alla scelta è ancora da ricevere.",
        "why_now": "Non è documentata una scadenza.",
        "initiative": "prepare",
        "what_i_can_do": "Preparerò il confronto: mensile 15 × 12 = 180, annuale 120 anticipati.",
        "evidence_refs": [MEMORY],
    }
    if include:
        result["outcome_assessment"] = assessment() if value is None else value
    return result


async def seed(db):
    await db.users.insert_one({"id": OWNER, "user_id": OWNER,
                               "settings": {"timezone": "Europe/Rome"}})
    await db.memories.insert_many([
        {"id": MEMORY, "user_id": OWNER, "status": "active", "statement": SOURCE,
         "authority": "user_stated", "epistemic_status": "confirmed"},
        {"id": OTHER, "user_id": "synthetic-other-owner", "status": "active",
         "statement": "FOREIGN CONTENT MUST NOT BE EXPORTED"},
    ])
    # The real reader, not the test's allowed-ref list, establishes ownership.
    previews = await read_memory_previews(db, OWNER, [MEMORY, OTHER])
    assert [row["ref"] for row in previews] == [MEMORY]
    return {"memories": previews, "unavailable_sources": []}


async def scan(db, monkeypatch, state, item):
    model = AsyncMock(return_value={"verified": True, "opportunities": [deepcopy(item)]})
    monkeypatch.setattr(opportunity_reasoning, "scan", model)
    result = await OpportunityService(db).scan(OWNER, prepared_snapshot=state)
    assert not result.silence and not result.unavailable
    assert len(result.created) + len(result.updated) == 1
    assert model.await_count == 1
    return (result.created or result.updated)[0]


async def observe_admission(db, monkeypatch):
    model = AsyncMock(return_value=deepcopy(NO_GOAL))
    monkeypatch.setattr(reasoning, "_ask_model", model)
    assert await drain(db, owner_id=OWNER, limit=1) == 1
    assert model.await_count == 1
    return json.loads(model.await_args.args[1])


@pytest.mark.asyncio
async def test_audited_assessment_survives_reload_to_sdk_without_overriding_no_goal(monkeypatch):
    db = AsyncMongoMockClient().opportunity_assessment_sdk
    state = await seed(db)
    opp = await scan(db, monkeypatch, state, proposal())
    saved = await db.opportunities.find_one({"owner_id": OWNER, "id": opp.id})
    before = {key: saved[key] for key in ("agent_review_revision", "agent_review_fingerprint")}
    # The actual SDK and HTTP serialization exercise the final context boundary.
    transported = fake_gemini(monkeypatch, lambda system, payload: deepcopy(NO_GOAL))
    await db.eval_guards.insert_one({"_id": gate.VERSION, "owner": OWNER})
    with gate.isolated_engine(db, mode="live") as probe:
        assert await drain(db, owner_id=OWNER, limit=1) == 1
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 1
        assert not probe.network.blocked and not probe.blocked_effects
    payload = transported[0]["payload"]
    previous = payload.get("previous_model_assessment")
    assert previous is not None, "Audited outcome_assessment was lost between discovery and admission"
    assert previous["origin"] == "model" and previous["authoritative"] is False
    assert previous["owner_id"] == OWNER and previous["opportunity_id"] == opp.id
    assert previous["proposal_revision"] == fingerprint(opp)
    assert previous["assessment"] == {**assessment(), "context_truncated": False}
    assert payload["source_context"][0]["statement"] == SOURCE
    assert payload["source_context"][0]["authority"] == "user_stated"
    assert payload["source_context_unavailable"] is False
    assert not any("assessment" in row for row in payload["source_context"])
    current = await db.opportunities.find_one({"owner_id": OWNER, "id": opp.id})
    assert all(current[key] == value for key, value in before.items())
    assert current["agent_review_outcome"] == "no_goal" and current["agent_review_state"] == "settled"
    assert current["agent_review_attempts"] == 1 and current["agent_review_due"] is None
    assert await db.agent_goals.count_documents({}) == 0
    assert await db.agent_evidence.count_documents({}) == 0
    assert await db.ambient_wakes.count_documents({}) == 0


def test_candidate_keeps_only_supplied_cited_refs_and_bounds_diagnostics_without_coercion():
    refs = [f"mem_owned_{number}" for number in range(10)]
    value = assessment(
        desired_outcome="D" * 400, remaining_internal_work="R" * 400,
        supporting_refs=[refs[0], refs[0], OTHER, refs[1] + ": invented description", *refs[1:]],
        completion_refs=[OTHER, {"ref": refs[0]}, refs[0]],
        owner_id="foreign-owner", authoritative=True, raw_prompt="DO NOT COPY",
    )
    item = proposal(value)
    item["evidence_refs"] = refs
    original = deepcopy(item)
    candidate, why = OpportunityService(None)._read_candidate(item, {ref: "memory" for ref in refs})
    assert candidate is not None and why == ""
    kept = candidate.model_dump().get("outcome_assessment")
    assert kept is not None
    assert kept["supporting_refs"] == refs[:8] and kept["completion_refs"] == [refs[0]]
    assert len(kept["desired_outcome"]) == len(kept["remaining_internal_work"]) == 280
    assert kept["context_truncated"] is True
    assert all(key not in kept for key in ("owner_id", "authoritative", "raw_prompt"))
    assert item == original


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, "open", {"outcome_state": "unknown"},
                                  assessment(desired_outcome={"wrong": "type"})])
async def test_absent_or_malformed_diagnostic_never_invalidates_legacy_admission(monkeypatch, value):
    db = AsyncMongoMockClient().opportunity_assessment_legacy
    state = await seed(db)
    item = proposal(value, include=value is not None)
    opp = await scan(db, monkeypatch, state, item)
    payload = await observe_admission(db, monkeypatch)
    assert "previous_model_assessment" not in payload
    assert payload["source_context"][0]["statement"] == SOURCE
    row = await db.opportunities.find_one({"owner_id": OWNER, "id": opp.id})
    assert row["agent_review_outcome"] == "no_goal" and row["agent_review_attempts"] == 1


@pytest.mark.asyncio
async def test_rescan_replaces_then_retires_assessment_without_resetting_admission_budget(monkeypatch):
    db = AsyncMongoMockClient().opportunity_assessment_replacement
    state = await seed(db)
    first = await scan(db, monkeypatch, state, proposal())
    await observe_admission(db, monkeypatch)
    before = await db.opportunities.find_one({"owner_id": OWNER, "id": first.id})
    assert before["agent_review_attempts"] == 1 and before["agent_review_due"] is None
    updated = assessment(remaining_internal_work="Rivalutare le sole condizioni ancora aperte.")
    second = await scan(db, monkeypatch, state, proposal(updated))
    saved = await db.opportunities.find_one({"owner_id": OWNER, "id": first.id})
    assert second.id == first.id
    assert saved.get("outcome_assessment", {}).get("assessment", {}).get("remaining_internal_work") == updated["remaining_internal_work"]
    assert saved["agent_review_revision"] == before["agent_review_revision"]
    assert saved["agent_review_attempts"] == before["agent_review_attempts"]
    third = await scan(db, monkeypatch, state, proposal(include=False))
    assert third.id == first.id and third.model_dump().get("outcome_assessment") is None
    assert await drain(db, owner_id=OWNER, limit=1) == 0


@pytest.mark.asyncio
async def test_reopened_proposal_binds_only_the_new_assessment(monkeypatch):
    db = AsyncMongoMockClient().opportunity_assessment_reopen
    state = await seed(db)
    original = await scan(db, monkeypatch, state, proposal())
    original.status = "resolved"
    await OpportunityRepository(db).save(original)
    assert original.outcome_assessment is None
    new_ref = "mem_assessment_context_new"
    await db.memories.insert_one({"user_id": OWNER, "id": new_ref, "status": "active",
                                 "statement": "È emersa una nuova condizione da includere nel confronto."})
    state["memories"] = await read_memory_previews(db, OWNER, [MEMORY, new_ref])
    updated = assessment(supporting_refs=[new_ref], remaining_internal_work="Includere la nuova condizione.")
    item = proposal(updated)
    item["evidence_refs"].append(new_ref)
    reopened = await scan(db, monkeypatch, state, item)
    assert reopened.id == original.id and reopened.status == "active"
    payload = await observe_admission(db, monkeypatch)
    assert payload.get("previous_model_assessment", {}).get("assessment") == {
        **updated, "context_truncated": False,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["proposal", "resolved", "suppressed"])
async def test_changed_or_withdrawn_proposal_retires_previous_judgment(monkeypatch, change):
    db = AsyncMongoMockClient().opportunity_assessment_revoke
    state = await seed(db)
    opp = await scan(db, monkeypatch, state, proposal())
    assert opp.model_dump().get("outcome_assessment") is not None
    reloaded = await OpportunityRepository(db).get(OWNER, opp.id)
    if change == "proposal":
        reloaded.semantic_summary = "La proposta è stata aggiornata sulla base di una fonte diversa."
    else:
        reloaded.status = change
    await OpportunityRepository(db).save(reloaded)
    saved = await db.opportunities.find_one({"owner_id": OWNER, "id": opp.id})
    assert saved.get("outcome_assessment") is None
    if change == "proposal":
        payload = await observe_admission(db, monkeypatch)
        assert "previous_model_assessment" not in payload
    else:
        model = AsyncMock(return_value=NO_GOAL)
        monkeypatch.setattr(reasoning, "_ask_model", model)
        assert await drain(db, owner_id=OWNER, limit=1) == 1
        assert model.await_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ["owner_id", "opportunity_id", "proposal_revision", "prose_without_save", "references", "stored_format"])
async def test_admission_rechecks_owner_proposal_revision_and_references(monkeypatch, tamper):
    db = AsyncMongoMockClient().opportunity_assessment_binding
    state = await seed(db)
    opp = await scan(db, monkeypatch, state, proposal())
    saved = await db.opportunities.find_one({"owner_id": OWNER, "id": opp.id})
    assert saved.get("outcome_assessment") is not None
    if tamper == "prose_without_save":
        changes = {"semantic_summary": "Changed after the proposal snapshot"}
    elif tamper == "stored_format":
        changes = {"outcome_assessment": {"raw_prompt": "FOREIGN CONTENT MUST NOT BE EXPORTED"}}
    elif tamper == "references":
        changes = {"outcome_assessment.assessment.supporting_refs": [OTHER]}
    else:
        changes = {"outcome_assessment." + tamper:
                   "f" * 64 if tamper == "proposal_revision" else "foreign-context"}
    await db.opportunities.update_one({"owner_id": OWNER, "id": opp.id}, {"$set": changes})
    payload = await observe_admission(db, monkeypatch)
    assert "previous_model_assessment" not in payload
    assert payload["source_context"][0]["statement"] == SOURCE
    assert "FOREIGN CONTENT MUST NOT BE EXPORTED" not in json.dumps(payload)
