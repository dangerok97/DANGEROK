"""Planning sees bounded recorded-work metadata, never an implicit source read.

The service/store and installed Gemini SDK are real; HTTP answers are synthetic.
This verifies transport and scope, not that a real model chooses a useful plan.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from unittest.mock import AsyncMock

from mongomock_motor import AsyncMongoMockClient
import pytest

from agent import reasoning
from agent.evidence import EvidenceStore
from agent.models import ActionStep, AgentBudget, AgentEvidence, AgentRun, MemoryReadRange, ResultProvenance
from agent.providers import read_internal_state
from agent.service import AgentService
from scripts import autonomy_completion_eval_v162 as gate
from test_agent_preparation_dependency_v162 import (
    MEMORY, OWNER, fake_gemini, prepare_step, seed,
)
from test_pending_outcome_contract_v162 import synthetic_transport_only  # noqa: F401


REPLY = {
    "planning_outcome": "plan", "plan_summary": "Una decisione sintetica invariata.",
    "steps": [prepare_step()],
}


async def record_read(db, goal):
    """Obtain real Memory coverage, version and qualifications without any LLM."""
    step = ActionStep(step_type="inspect", capability_needed="information.read",
                      intent="Leggere la nota citata.", input_refs=[MEMORY])
    result = await read_internal_state(db, OWNER, goal, step=step)
    assert result.status == "partial"
    claim, = result.claims
    item = AgentEvidence(owner_id=OWNER, goal_id=goal.id, step_id=step.id,
                         claim=claim.text, supports=claim.supports,
                         provenance=result.provenance)
    await EvidenceStore(db).record(item)
    return item


async def record_other(db, goal, *, index=0, provider="synthetic_read", owner=OWNER,
                       goal_id=None):
    observed = (datetime.now(timezone.utc) + timedelta(seconds=index)).isoformat()
    item = AgentEvidence(
        owner_id=owner, goal_id=goal_id or goal.id, claim=f"Testo privato sintetico {index}.",
        observed_at=observed,
        provenance=ResultProvenance(
            source_class="internal_observation", capability="document.read",
            provider=provider, source_refs=[f"document:synthetic-{index}"],
            observed_at=observed, freshness="fresh",
            certainty_note="Testo riferito; l'attualità esterna non è verificata.",
        ),
    )
    await EvidenceStore(db).record(item)
    return item


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["empty", "recorded", "unavailable"])
async def test_actual_planner_sdk_separates_empty_recorded_and_unavailable_without_changing_plan(
    monkeypatch, state,
):
    db = AsyncMongoMockClient().planning_inventory_sdk
    goal, _ = await seed(db, partial=True)
    service = AgentService(db)
    read = None
    if state == "recorded":
        read = await record_read(db, goal)
        for provider in ("generated_draft", "calendar_overlap_draft"):
            await record_other(db, goal, provider=provider)
        await record_other(db, goal, owner="foreign-owner")
        await record_other(db, goal, goal_id="foreign-goal")
        superseded = await record_other(db, goal)
        await db.agent_evidence.update_one({"id": superseded.id}, {"$set": {"superseded": True}})
        await db.agent_evidence.insert_one({"owner_id": OWNER, "goal_id": goal.id, "claim": None})
    elif state == "unavailable":
        monkeypatch.setattr(service.evidence, "for_goal", AsyncMock(side_effect=TimeoutError("private db details")))

    transported = fake_gemini(monkeypatch, lambda _system, _payload: deepcopy(REPLY))
    before_records = await db.agent_evidence.count_documents({})
    with gate.isolated_engine(db, mode="live"):
        run, budget = AgentRun(owner_id=OWNER, goal_id=goal.id), AgentBudget()
        plan = await service._build_plan(OWNER, goal, run, budget, language="it")

    inventory = transported[0]["payload"]["context"]["executed_evidence"]
    assert len(transported) == 1 and budget.cognitive_calls == run.model_calls == 1
    assert [step.step_type for step in plan.steps] == ["prepare"]
    assert plan.steps[0].input_refs == REPLY["steps"][0]["input_refs"]
    assert await db.agent_evidence.count_documents({}) == before_records
    assert await db.agent_action_attempts.count_documents({}) == 0
    assert not goal.prepared_text
    assert inventory["scope"]["selection_limit"] == 40
    assert inventory["scope"]["not_complete"] is True
    assert inventory["scope"]["may_omit"] == ["outside_selected_window", "invalid_documents"]
    assert inventory["scope"]["metadata_only"] is True
    if state == "unavailable":
        assert inventory["available"] is False and inventory["reason"] == "store_unavailable"
        assert "selected_evidence_count" not in inventory and "records" not in inventory
        assert "private db details" not in json.dumps(transported)
    else:
        assert inventory["available"] is True
        assert inventory["selected_evidence_count"] == (3 if read else 0)
        assert inventory["generated_record_count"] == (2 if read else 0)
        assert inventory["non_generated_record_count"] == (1 if read else 0)
        assert inventory["omitted_record_count"] == 0
        if read:
            row, = inventory["records"]
            assert row["evidence_id"] == read.id and row["step_id"] == read.step_id
            assert row["capability"] == "information.read"
            assert row["where_this_came_from"] == "internal_observation"
            assert row["really_happened"] is True and row["source_refs"] == [MEMORY]
            assert row["observed_at"] == read.provenance.observed_at
            assert row["how_old"] == "fresh"
            assert row["note"] == read.provenance.certainty_note
            assert row["memory_reads"] == [item.model_dump() for item in read.provenance.memory_reads]
            assert row["memory_reads"][0]["next_offset"] == 600
            assert "what_was_found" not in row and row["bears_on"] == read.supports
            assert "source_versions" not in row
        else:
            assert inventory["records"] == []


@pytest.mark.asyncio
async def test_inventory_owner_mismatch_does_not_query_another_owners_records(monkeypatch):
    db = AsyncMongoMockClient().planning_inventory_owner
    goal, _ = await seed(db)
    service = AgentService(db)
    reader = AsyncMock(side_effect=AssertionError("must not read"))
    monkeypatch.setattr(service.evidence, "for_goal", reader)
    inventory = await service._planning_evidence_inventory("foreign-owner", goal)
    assert inventory["available"] is False and inventory["reason"] == "owner_mismatch"
    assert "selected_evidence_count" not in inventory and "records" not in inventory
    reader.assert_not_awaited()


@pytest.mark.asyncio
async def test_inventory_reports_bounded_parsed_selection_and_omits_whole_metadata_records(monkeypatch):
    db = AsyncMongoMockClient().planning_inventory_window
    goal, _ = await seed(db)
    service = AgentService(db)
    for index in range(41):
        await record_other(db, goal, index=index)
    await db.agent_evidence.insert_one({
        "owner_id": OWNER, "goal_id": goal.id, "claim": None,
        "observed_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    })
    reader = AsyncMock(wraps=service.evidence.for_goal)
    monkeypatch.setattr(service.evidence, "for_goal", reader)
    inventory = await service._planning_evidence_inventory(OWNER, goal)
    reader.assert_awaited_once_with(OWNER, goal.id, limit=40)
    assert inventory["selected_evidence_count"] == inventory["non_generated_record_count"] == 39
    assert inventory["generated_record_count"] == 0
    assert len(inventory["records"]) == 4
    assert inventory["omitted_record_count"] == 35
    assert inventory["scope"]["not_complete"] is True
    assert [row["source_refs"] for row in inventory["records"]] == [
        [f"document:synthetic-{index}"] for index in range(37, 41)
    ]


@pytest.mark.asyncio
async def test_one_oversized_metadata_record_is_omitted_with_nonzero_count_and_no_cut_cursor(monkeypatch):
    db = AsyncMongoMockClient().planning_inventory_whole_record
    goal, _ = await seed(db, partial=True)
    item = await record_read(db, goal)
    # A bounded multi-source result can carry more metadata than the planning
    # view can include. Omitting the whole row must not imply no prior read.
    item.provenance.source_refs = ["memory:" + str(i) + "x" * 152 for i in range(8)]
    original_cursor = item.provenance.memory_reads[0].model_dump()
    item.provenance.memory_reads = [
        MemoryReadRange(**{**original_cursor, "ref": ref}) for ref in item.provenance.source_refs
    ]
    item = AgentEvidence.model_validate(item.model_dump())
    service = AgentService(db)
    monkeypatch.setattr(service.evidence, "for_goal", AsyncMock(return_value=[item]))
    before = item.model_dump()
    inventory = await service._planning_evidence_inventory(OWNER, goal)
    assert inventory["selected_evidence_count"] == inventory["non_generated_record_count"] == 1
    assert inventory["records"] == [] and inventory["omitted_record_count"] == 1
    assert item.model_dump() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("capability,recorded_age,expired,expected", [
    ("document.read", "unknown", False, "unknown"),
    ("weather.read", "stale", False, "stale"),
    ("weather.read", "recent", False, "recent"),
    ("weather.read", "fresh", True, "stale"),
])
async def test_inventory_never_upgrades_provider_freshness_from_retrieval_time(
    monkeypatch, capability, recorded_age, expired, expected,
):
    db = AsyncMongoMockClient().planning_inventory_age
    goal, _ = await seed(db)
    item = await record_other(db, goal)
    item.provenance.capability = capability
    item.provenance.freshness = recorded_age
    item.provenance.weather_valid_until = (
        datetime.now(timezone.utc) + timedelta(minutes=-1 if expired else 20)
    ).isoformat()
    service = AgentService(db)
    monkeypatch.setattr(service.evidence, "for_goal", AsyncMock(return_value=[item]))
    inventory = await service._planning_evidence_inventory(OWNER, goal)
    row, = inventory["records"]
    assert row["how_old"] == expected
    assert row["observed_at"] == item.provenance.observed_at
    assert row["weather_valid_until"] == item.provenance.weather_valid_until
    assert row["note"] == item.provenance.certainty_note


@pytest.mark.asyncio
async def test_actual_sdk_reduction_preserves_inventory_and_partial_read_metadata_exactly(monkeypatch):
    db = AsyncMongoMockClient().planning_inventory_reducer
    goal, _ = await seed(db, partial=True)
    item = await record_read(db, goal)
    inventory = await AgentService(db)._planning_evidence_inventory(OWNER, goal)
    context = {"executed_evidence": inventory, "descriptive_history": "Contesto già noto. " * 1500}
    before = deepcopy(context)
    transported = fake_gemini(monkeypatch, lambda _system, _payload: deepcopy(REPLY))
    with gate.isolated_engine(db, mode="live"):
        answer = await reasoning.make_plan(goal.for_ai(), capabilities=[], context=context)
    assert answer == REPLY and len(transported) == 1
    payload = transported[0]["payload"]
    assert payload["context_truncated"] is True
    assert payload["context"]["executed_evidence"] == inventory
    assert payload["context"]["executed_evidence"]["records"][0]["memory_reads"] == [
        cursor.model_dump() for cursor in item.provenance.memory_reads
    ]
    assert context == before


@pytest.mark.parametrize("oversized_inventory", [False, True])
def test_reducer_last_resort_keeps_inventory_or_declares_unavailable_never_healthy_zero(oversized_inventory):
    inventory = {
        "available": True, "selected_evidence_count": 1, "non_generated_record_count": 1,
        "records": [{"evidence_id": "evd_owned", "note": "x" * (10000 if oversized_inventory else 200)}],
    }
    payload = {"goal": {"id": "goal_owned"}, "context": {"executed_evidence": inventory},
               "source_refs": ["document:" + "x" * 150 for _ in range(80)]}
    before = deepcopy(payload)
    encoded = reasoning._dump(payload)
    result = json.loads(encoded)
    assert len(encoded) <= 9000 and result["source_context_unavailable"] is True
    if oversized_inventory:
        assert result["context"]["executed_evidence"] == {
            "available": False, "reason": "metadata_exceeds_context",
        }
    else:
        assert result["context"]["executed_evidence"] == inventory
    assert payload == before
