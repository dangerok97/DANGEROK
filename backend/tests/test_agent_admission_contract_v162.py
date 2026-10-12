"""Malformed goal decisions stay technical, durable and bounded.

Owned in-memory records exercise the actual admission lease, service and wake
handoff. SDK transport tests use injected HTTP replies, never a live model.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from unittest.mock import AsyncMock, patch

from mongomock_motor import AsyncMongoMockClient
import pytest

from agent import reasoning
from agent.admission import MAX_ATTEMPTS, drain
from agent.service import AgentService
from opportunities.models import Opportunity
from opportunities.repository import OpportunityRepository
from scripts import autonomy_completion_eval_v162 as gate
from test_agent_preparation_dependency_v162 import fake_gemini
from test_pending_outcome_contract_v162 import synthetic_transport_only  # noqa: F401


OWNER = gate.OWNER
PRIVATE_MARKER = "SYNTHETIC_VALUE_MUST_NOT_BECOME_A_DIAGNOSTIC"


def valid_goal():
    return {
        "outcome": "create_goal", "reasoning": "Resta un risultato interno utile.",
        "objective": "Preparare il confronto richiesto.",
        "desired_outcome": "Il confronto scritto è disponibile con fonti e limiti.",
        "success_criteria": ["Il confronto è fondato sulle condizioni lette."],
        "stop_conditions": ["La richiesta viene ritirata."],
    }


def missing_desired():
    answer = valid_goal()
    answer["outcome_assessment"] = {
        "desired_outcome": answer.pop("desired_outcome"), "outcome_state": "open",
    }
    return answer


def invalid_cases():
    answer = missing_desired()
    yield pytest.param(answer, ["desired_outcome"], id="missing-top-level-desired-outcome")
    for field, value in (
        ("objective", " \t "),
        ("success_criteria", PRIVATE_MARKER),
        ("success_criteria", ["", {"private": PRIVATE_MARKER}]),
        ("stop_conditions", PRIVATE_MARKER),
    ):
        answer = valid_goal()
        answer[field] = value
        yield pytest.param(answer, [field], id=field + "-" + type(value).__name__)
    yield pytest.param({"outcome": "clarify", "question": "   "}, ["question"], id="empty-clarification")


@pytest.mark.asyncio
@pytest.mark.parametrize("answer,fields", list(invalid_cases()))
async def test_invalid_fields_stay_pending_without_invented_goal_or_question(monkeypatch, caplog, answer, fields):
    db = AsyncMongoMockClient().admission_contract_invalid
    model = AsyncMock(return_value=answer)
    with gate.isolated_engine(db) as probe, patch.object(reasoning, "decide_goal", model):
        oid = await gate.seed_case(db, "completed_result")
        assert await drain(db, owner_id=OWNER, limit=1) == 1
        row = await db.opportunities.find_one({"owner_id": OWNER, "id": oid})
        assert row["agent_review_outcome"] == "unavailable"
        assert row["agent_review_state"] == "pending" and row["agent_review_due"]
        assert row["agent_review_error_kind"] == "invalid_goal_decision"
        assert row["agent_review_invalid_fields"] == fields
        assert row["agent_review_attempts"] == 1
        assert not row.get("agent_review_token") and not row.get("agent_review_lease_until")
        assert not row["agent_review_question"] and not row["agent_review_goal_id"]
        assert await db.agent_goals.count_documents({}) == 0
        assert await db.ambient_wakes.count_documents({}) == 0
        assert PRIVATE_MARKER not in str(row) and PRIVATE_MARKER not in caplog.text
        assert model.await_count == 1 and probe.model_attempts == 0


def complete_branch_examples(system):
    decoder = json.JSONDecoder()
    examples = {}
    for outcome in ("create_goal", "no_goal", "wait", "clarify"):
        marker = f"\n{outcome}:\n"
        start = system.index(marker) + len(marker)
        examples[outcome], _ = decoder.raw_decode(system[start:])
        assert examples[outcome]["outcome"] == outcome
        assert "outcome_assessment" in examples[outcome]
    created = examples["create_goal"]
    for field in ("objective", "desired_outcome", "why_now", "success_criteria", "stop_conditions", "evidence_refs"):
        assert field in created
    assert isinstance(created["objective"], str) and created["objective"].strip()
    assert isinstance(created["desired_outcome"], str) and created["desired_outcome"].strip()
    assert isinstance(created["success_criteria"], list)
    assert examples["clarify"]["question"]
    return examples


@pytest.mark.asyncio
@pytest.mark.parametrize("next_outcome", ["create_goal", "no_goal"])
async def test_real_sdk_invalid_response_retries_durably_and_preserves_next_decision(monkeypatch, next_outcome):
    db = AsyncMongoMockClient().admission_contract_sdk
    next_answer = valid_goal() if next_outcome == "create_goal" else {
        "outcome": "no_goal", "reasoning": "Decisione sintetica valida: nessun lavoro ulteriore.",
        "outcome_assessment": {"outcome_state": "open"},
    }
    responses = [missing_desired(), next_answer]

    def reply(system, payload):
        complete_branch_examples(system)
        assert len(payload["source_context"]) == 1
        return responses.pop(0)

    transported = fake_gemini(monkeypatch, reply)
    with gate.isolated_engine(db, mode="live") as probe:
        oid = await gate.seed_case(db, "completed_result")
        assert await drain(db, owner_id=OWNER, limit=1) == 1
        first = await db.opportunities.find_one({"owner_id": OWNER, "id": oid})
        assert first["agent_review_outcome"] == "unavailable"
        assert first["agent_review_error_kind"] == "invalid_goal_decision"
        assert first["agent_review_invalid_fields"] == ["desired_outcome"]
        assert await db.agent_goals.count_documents({}) == 0  # No copy from assessment.
        due = datetime.fromisoformat(first["agent_review_due"])
        assert await drain(db, owner_id=OWNER, now=due - timedelta(milliseconds=1), limit=1) == 0
        assert len(transported) == 1

        # A separate admission pass, with the original source and its saved
        # retry time, obtains the next decision. There is no in-call retry loop.
        assert await drain(db, owner_id=OWNER, now=due + timedelta(milliseconds=1), limit=1) == 1
        current = await db.opportunities.find_one({"owner_id": OWNER, "id": oid})
        assert current["agent_review_outcome"] == next_outcome
        assert current["agent_review_state"] == "settled"
        assert current["agent_review_attempts"] == 2 and current["agent_review_due"] is None
        assert current["agent_review_error_kind"] == "" and current["agent_review_invalid_fields"] == []
        assert current["agent_review_revision"] == first["agent_review_revision"]
        assert await db.agent_goals.count_documents({}) == int(next_outcome == "create_goal")
        assert await db.ambient_wakes.count_documents({"status": "pending"}) == int(next_outcome == "create_goal")
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 2
        assert not probe.network.blocked and not probe.blocked_effects


@pytest.mark.asyncio
async def test_invalid_decisions_exhaust_only_the_existing_admission_budget(monkeypatch):
    db = AsyncMongoMockClient().admission_contract_bound
    model = AsyncMock(return_value=missing_desired())
    with gate.isolated_engine(db), patch.object(reasoning, "decide_goal", model):
        oid = await gate.seed_case(db, "completed_result")
        moment = datetime.now(timezone.utc)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            assert await drain(db, owner_id=OWNER, now=moment, limit=1) == 1
            row = await db.opportunities.find_one({"owner_id": OWNER, "id": oid})
            assert row["agent_review_attempts"] == attempt
            assert row["agent_review_outcome"] == "unavailable"
            assert row["agent_review_error_kind"] == "invalid_goal_decision"
            if attempt < MAX_ATTEMPTS:
                due = datetime.fromisoformat(row["agent_review_due"])
                assert (due - moment).total_seconds() == 60 * 5 ** (attempt - 1)
                moment = due
        assert row["agent_review_state"] == "paused" and row["agent_review_due"] is None
        assert not row.get("agent_review_token")
        assert await drain(db, owner_id=OWNER, now=moment + timedelta(days=1), limit=1) == 0
        assert model.await_count == MAX_ATTEMPTS
        assert await db.agent_goals.count_documents({}) == 0
        assert await db.ambient_wakes.count_documents({}) == 0


@pytest.mark.asyncio
async def test_invalid_old_decision_cannot_settle_new_revision_or_another_owner(monkeypatch):
    db = AsyncMongoMockClient().admission_contract_fences
    with gate.isolated_engine(db):
        oid = await gate.seed_case(db, "completed_result")
        repo = OpportunityRepository(db)
        source = await repo.get(OWNER, oid)
        foreign = await repo.save(Opportunity(owner_id="synthetic-other-owner", identity_key="unrelated",
            status="active", semantic_summary="Altro lavoro sintetico.", why_it_matters="Contesto separato."))
        original = await db.opportunities.find_one({"owner_id": OWNER, "id": oid})

        async def changed(*args, **kwargs):
            source.semantic_summary = "La fonte è cambiata durante il giudizio precedente."
            await repo.save(source)
            return missing_desired()

        model = AsyncMock(side_effect=changed)
        with patch.object(reasoning, "decide_goal", model):
            assert await drain(db, owner_id=OWNER, limit=1) == 1
        current = await db.opportunities.find_one({"owner_id": OWNER, "id": oid})
        other = await db.opportunities.find_one({"owner_id": foreign.owner_id, "id": foreign.id})
        assert current["agent_review_revision"] != original["agent_review_revision"]
        assert current["agent_review_state"] == "pending" and current["agent_review_attempts"] == 0
        assert current["agent_review_outcome"] is None and current["agent_review_error_kind"] == ""
        assert not current.get("agent_review_invalid_fields") and not current.get("agent_review_token")
        assert other["agent_review_state"] == "pending" and other["agent_review_attempts"] == 0
        assert not other.get("agent_review_invalid_fields") and not other.get("agent_review_token")
        assert await db.agent_goals.count_documents({}) == 0 and model.await_count == 1


@pytest.mark.asyncio
async def test_persisted_invalid_fields_are_allowlisted_and_bounded(monkeypatch):
    db = AsyncMongoMockClient().admission_contract_diagnostics
    consider = AsyncMock(return_value={
        "outcome": "unavailable", "error_kind": "invalid_goal_decision",
        "invalid_fields": ["objective", PRIVATE_MARKER, {"unsafe": PRIVATE_MARKER}] + ["objective"] * 100,
    })
    with gate.isolated_engine(db), patch.object(AgentService, "consider", consider):
        oid = await gate.seed_case(db, "completed_result")
        await drain(db, owner_id=OWNER, limit=1)
        row = await db.opportunities.find_one({"owner_id": OWNER, "id": oid})
        assert row["agent_review_invalid_fields"] == ["objective"]
        assert PRIVATE_MARKER not in str(row)


@pytest.mark.asyncio
@pytest.mark.parametrize("optional", ["missing", "empty"])
async def test_optional_empty_criteria_do_not_invent_a_new_semantic_requirement(monkeypatch, optional):
    db = AsyncMongoMockClient().admission_contract_optional
    answer = valid_goal()
    for field in ("success_criteria", "stop_conditions"):
        if optional == "missing":
            answer.pop(field)
        else:
            answer[field] = []
    model = AsyncMock(return_value=deepcopy(answer))
    with gate.isolated_engine(db), patch.object(reasoning, "decide_goal", model):
        oid = await gate.seed_case(db, "completed_result")
        await drain(db, owner_id=OWNER, limit=1)
        row = await db.opportunities.find_one({"owner_id": OWNER, "id": oid})
        assert row["agent_review_outcome"] == "create_goal"
        goal = await db.agent_goals.find_one({"owner_id": OWNER, "opportunity_id": oid})
        assert goal["success_criteria"] == [] and goal["stop_conditions"] == []
        assert goal["desired_outcome"] == answer["desired_outcome"]
        assert model.await_count == 1
