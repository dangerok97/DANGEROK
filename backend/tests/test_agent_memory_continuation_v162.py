"""A Memory excerpt is bounded evidence, never an unmarked complete read.

Synthetic records only. These tests cross the real executor/evidence boundary
and observe model payloads without invoking a model or external transport.
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.evidence import EvidenceStore, for_verification
from agent.execution import StepExecutor
from agent.memory_fence import inspect_memory_sources
from agent.models import ActionStep, AgentBudget, AutonomousGoal
from agent.providers import read_internal_state


OWNER = "memory-continuation-v162-synthetic"
MEMORY = "mem_bounded_read"
TEXT = (
    "La quota base è 20 euro mensili. "
    + "Dettaglio di contesto. " * 35
    + "CONDIZIONE_FINALE: costo aggiuntivo obbligatorio 120 euro e nessun rimborso."
)


async def seed(*, text=TEXT, ref=MEMORY):
    db = AsyncMongoMockClient().memory_continuation_v162
    goal = AutonomousGoal(
        owner_id=OWNER, status="active", source_kind="memory", source_refs=[ref],
        objective="Confrontare tutti i costi e le condizioni annotati.",
        desired_outcome="Un confronto con i costi complessivi e i limiti delle fonti.",
    )
    await db.agent_goals.insert_one(goal.model_dump())
    await db.memories.insert_one({
        "id": MEMORY, "user_id": OWNER, "status": "known", "revision": 1,
        "statement": text, "authority": "user_asserted", "epistemic_status": "known",
        "created_at": "2020-01-01T00:00:00+00:00",
    })
    return db, goal


def read_step(*refs, **parameters):
    return ActionStep(
        step_type="inspect", capability_needed="information.read",
        intent="Leggere la memoria citata conservando i suoi limiti.",
        input_refs=list(refs), parameters=parameters,
    )


def cursor(result):
    return result.provenance.for_ai()["memory_reads"][0]


@pytest.mark.asyncio
async def test_long_memory_is_partial_and_continues_after_evidence_reload():
    db, goal = await seed()
    budget = AgentBudget()
    first = await StepExecutor(db).run(
        OWNER, goal, read_step(MEMORY), may_touch_the_world=False, budget=budget,
    )
    assert first.status == "partial"
    assert budget.capability_calls == 1 and budget.cognitive_calls == 0
    # A new executor/store stands in for a subsequent worker process.
    evidence = await EvidenceStore(db).for_goal(OWNER, goal.id)
    projected = for_verification(evidence)
    assert len(evidence) == 1 and evidence[0].claim == TEXT[:600]
    assert "CONDIZIONE_FINALE" not in str(projected)
    page = projected[0]["memory_reads"][0]
    assert page == {
        "ref": MEMORY, "offset": 0, "end": 600, "total": len(TEXT),
        "next_offset": 600, "version": first.provenance.source_versions[MEMORY],
    }
    assert "incomplet" in projected[0]["note"].lower()
    assert "source_versions" not in projected[0]
    followup = read_step(page["ref"], memory_offset=page["next_offset"], memory_version=page["version"])
    assert followup.for_ai()["memory_offset"] == 600
    assert followup.for_ai()["memory_version"] == page["version"]
    second = await StepExecutor(db).run(
        OWNER, goal, followup, may_touch_the_world=False, budget=budget,
    )
    # This call read only the suffix. Completion belongs to verification of
    # the combined evidence, not to a success flag on a partial source read.
    assert second.status == "partial"
    assert cursor(second) == {**page, "offset": 600, "end": len(TEXT), "next_offset": None}
    assert "Fine del testo" in second.observation
    assert budget.capability_calls == 2 and budget.cognitive_calls == 0
    reloaded = await EvidenceStore(db).for_goal(OWNER, goal.id)
    assert "".join(item.claim for item in reloaded) == TEXT
    assert "CONDIZIONE_FINALE" in str(for_verification(reloaded))
    assert (await inspect_memory_sources(db, OWNER, goal)).status == "current"


@pytest.mark.asyncio
async def test_short_memory_is_the_only_complete_single_read():
    db, goal = await seed(text="Una nota completa e breve.")
    result = await read_internal_state(db, OWNER, goal, step=read_step(MEMORY))
    assert result.status == "succeeded"
    assert cursor(result)["offset"] == 0
    assert cursor(result)["end"] == cursor(result)["total"]
    assert cursor(result)["next_offset"] is None


@pytest.mark.asyncio
async def test_multiple_long_memories_keep_claim_and_metadata_budgets():
    db, goal = await seed()
    await db.memories.insert_many([
        {"id": f"mem_other_{i}", "user_id": OWNER, "status": "active", "statement": TEXT}
        for i in range(20)
    ])
    goal.source_refs = []
    result = await read_internal_state(db, OWNER, goal)
    assert result.status == "partial"
    assert len(result.claims) == 8
    assert len(result.provenance.source_refs) == len(result.provenance.source_versions) == 8
    pages = result.provenance.for_ai()["memory_reads"]
    assert len(pages) == 8
    assert all(len(claim.text) <= 600 and len(claim.supports) <= 300 for claim in result.claims)
    assert all(page["offset"] == 0 and page["end"] == page["next_offset"] == 600 for page in pages)
    assert {page["ref"] for page in pages} == set(result.provenance.source_versions)
    assert len(result.provenance.certainty_note) <= 200
    assert len(result.observation) <= 600
    assert "incomplet" in result.provenance.certainty_note.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("offset", [-1, True, "600", 1.5])
async def test_invalid_offset_never_becomes_a_read(offset):
    db, goal = await seed()
    result = await read_internal_state(
        db, OWNER, goal, step=read_step(MEMORY, memory_offset=offset),
    )
    assert result.status == "unavailable" and result.error_type == "invalid_memory_offset"
    assert not result.claims and not result.provenance.source_refs


@pytest.mark.asyncio
@pytest.mark.parametrize("refs", [[], [MEMORY, "mem_other"]])
async def test_continuation_requires_exactly_one_explicit_reference(refs):
    db, goal = await seed()
    result = await read_internal_state(
        db, OWNER, goal, step=read_step(*refs, memory_offset=600, memory_version="a" * 64),
    )
    assert result.status == "unavailable" and result.error_type == "memory_reference_required"
    assert not result.claims


@pytest.mark.asyncio
async def test_a_preview_without_reader_version_restarts_at_zero_explicitly():
    db, goal = await seed()
    result = await read_internal_state(
        db, OWNER, goal, step=read_step(MEMORY, memory_offset=600),
    )
    assert result.status == "partial"
    assert cursor(result)["offset"] == 0
    assert result.claims[0].text == TEXT[:600]
    assert "ripartita da zero" in result.observation


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["statement", "authority", "revision"])
async def test_version_change_rejects_the_next_page_and_keeps_fence(change):
    db, goal = await seed()
    first = await StepExecutor(db).run(OWNER, goal, read_step(MEMORY), may_touch_the_world=False)
    page = cursor(first)
    value = {"statement": TEXT + " Testo corretto.", "authority": "model_inferred", "revision": 2}[change]
    await db.memories.update_one({"user_id": OWNER, "id": MEMORY}, {"$set": {change: value}})
    second = await StepExecutor(db).run(
        OWNER, goal, read_step(MEMORY, memory_offset=600, memory_version=page["version"]),
        may_touch_the_world=False,
    )
    assert second.status == "unavailable" and second.error_type == "memory_version_changed"
    assert not second.evidence_refs and not second.provenance.source_refs
    assert len(await EvidenceStore(db).for_goal(OWNER, goal.id)) == 1
    assert (await inspect_memory_sources(db, OWNER, goal)).status == "changed"


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["forgotten", "superseded", "foreign", "missing"])
async def test_removed_or_foreign_memory_cannot_supply_a_later_page(change):
    db, goal = await seed()
    first = await read_internal_state(db, OWNER, goal, step=read_step(MEMORY))
    page = cursor(first)
    if change == "missing":
        await db.memories.delete_one({"id": MEMORY, "user_id": OWNER})
    else:
        mutation = {"user_id": "other-synthetic-owner"} if change == "foreign" else {"status": change}
        await db.memories.update_one({"id": MEMORY, "user_id": OWNER}, {"$set": mutation})
    await db.memories.insert_one({"id": "mem_unrelated", "user_id": OWNER, "statement": "Unrelated"})
    result = await read_internal_state(
        db, OWNER, goal, step=read_step(MEMORY, memory_offset=600, memory_version=page["version"]),
    )
    assert result.status == "unavailable" and result.error_type == "memory_not_observed"
    assert not result.claims and not result.provenance.source_refs


@pytest.mark.asyncio
async def test_continuation_read_outage_remains_retryable():
    def failed_find(*args, **kwargs):
        raise TimeoutError("synthetic read outage")
    db, goal = await seed()
    first = await read_internal_state(db, OWNER, goal, step=read_step(MEMORY))
    broken_db = SimpleNamespace(memories=SimpleNamespace(find=failed_find))
    result = await read_internal_state(
        broken_db, OWNER, goal, step=read_step(MEMORY, memory_offset=600, memory_version=cursor(first)["version"]),
    )
    assert result.status == "failed" and result.retryable
    assert not result.claims and not result.provenance.source_refs


@pytest.mark.asyncio
async def test_memory_alias_cursor_returns_the_observed_canonical_reference():
    db, goal = await seed(ref=f"user_memory:{MEMORY}")
    first = await read_internal_state(db, OWNER, goal, step=read_step(f"memory:{MEMORY}"))
    page = cursor(first)
    assert page["ref"] == first.provenance.source_refs[0] == MEMORY
    second = await read_internal_state(
        db, OWNER, goal, step=read_step(page["ref"], memory_offset=page["next_offset"], memory_version=page["version"]),
    )
    assert second.claims[0].text == TEXT[600:]


@pytest.mark.asyncio
async def test_offset_past_the_current_source_never_claims_an_empty_success():
    db, goal = await seed()
    first = await read_internal_state(db, OWNER, goal, step=read_step(MEMORY))
    result = await read_internal_state(
        db, OWNER, goal,
        step=read_step(MEMORY, memory_offset=len(TEXT), memory_version=cursor(first)["version"]),
    )
    assert result.status == "unavailable" and result.error_type == "invalid_memory_offset"
    assert not result.claims


@pytest.mark.asyncio
async def test_preparation_and_its_audit_both_receive_the_incomplete_read(monkeypatch):
    from agent import reasoning
    from agent.preparation import prepare

    db, goal = await seed()
    first = await StepExecutor(db).run(OWNER, goal, read_step(MEMORY), may_touch_the_world=False)
    evidence = await EvidenceStore(db).for_goal(OWNER, goal.id)
    draft = "L'estratto è parziale: le condizioni successive devono ancora essere lette."
    model = AsyncMock(side_effect=[
        {"content": draft, "evidence_ids": [evidence[0].id]},
        {"verified": True, "content": draft, "evidence_ids": [evidence[0].id],
         "claim_review": [{"claim": "La sintesi resta condizionata alla lettura del seguito.",
            "premises": "Il cursore della fonte segnala una lettura incompleta; non si affermano condizioni non lette.",
            "support": "conditional", "correction": "", "evidence_ids": [evidence[0].id], "source_quotes": []}]},
    ])
    monkeypatch.setattr(reasoning, "_ask_model", model)
    result = await prepare(db, OWNER, goal, ActionStep(
        step_type="prepare", capability_needed="document.create", intent="Preparare i limiti della lettura.",
    ))
    assert result.status == "succeeded" and model.await_count == 2
    for call in model.await_args_list:
        payload = json.loads(call.args[1])
        row = payload["evidence"][0]
        assert row["memory_reads"] == [cursor(first)]
        assert "incomplet" in row["limits"].lower()
        assert len(call.args[1]) <= 9000
    assert goal.prepared_text == draft


@pytest.mark.asyncio
@pytest.mark.parametrize("cite_all", [False, True])
async def test_audit_budget_only_drops_uncited_rows_or_stops_without_saving(monkeypatch, cite_all):
    from agent import reasoning
    from agent.preparation import prepare

    db, goal = await seed()
    await db.memories.insert_many([
        {"id": f"mem_audit_{i}", "user_id": OWNER, "status": "active", "statement": TEXT}
        for i in range(7)
    ])
    goal.source_refs = []
    await StepExecutor(db).run(OWNER, goal, read_step(), may_touch_the_world=False)
    captured = []
    draft = ("Testo sintetico con limiti espliciti. " * 130)[:4000].strip()
    cited = []

    async def model(_instruction, encoded, *, response_schema=None):
        assert len(encoded) <= 9000
        payload = json.loads(encoded)
        captured.append(payload)
        if len(captured) == 1:
            rows = payload["evidence"]
            assert len(rows) > 1
            cited.extend(row["id"] for row in (rows if cite_all else rows[:1]))
            # Establish that this concrete audit would exceed the existing
            # budget if it naively reused every generation evidence row.
            assert len(json.dumps({"draft": draft, "evidence": rows}, ensure_ascii=False)) > 9000
            return {"content": draft, "evidence_ids": cited}
        return {"verified": True, "content": draft, "evidence_ids": cited,
                "claim_review": [{"claim": "Riepilogo limitato alle letture disponibili.",
                    "premises": "I cursori segnalano parti non lette; nessuna condizione del seguito è dichiarata.",
                    "support": "conditional", "correction": "", "evidence_ids": list(cited), "source_quotes": []}]}

    monkeypatch.setattr(reasoning, "_ask_model", model)
    result = await prepare(db, OWNER, goal, ActionStep(
        step_type="prepare", capability_needed="document.create", intent="Preparare un riepilogo con i limiti delle letture.",
    ))
    if cite_all:
        assert result.status == "unavailable" and result.error_type == "preparation_context_too_large"
        assert not result.retryable and len(captured) == 1
        assert not goal.prepared_text
        assert not (await db.agent_goals.find_one({"id": goal.id})).get("prepared_text")
    else:
        assert result.status == "succeeded" and len(captured) == 2
        audited = captured[1]["evidence"]
        assert set(cited) <= {row["id"] for row in audited}
        originals = {row["id"]: row for row in captured[0]["evidence"]}
        assert all(row == originals[row["id"]] for row in audited)
        assert captured[1]["evidence_truncated"] is True
        assert goal.prepared_text == draft


@pytest.mark.asyncio
async def test_long_admission_payload_is_valid_json_and_keeps_source_limits(monkeypatch):
    from agent import reasoning

    context = [
        {
            "ref": f"mem_admission_{i}", "source": "memory", "statement": TEXT[:600],
            "excerpt_truncated": True, "freshness": "unknown", "authority": "user_asserted",
        }
        for i in range(8)
    ]
    situation = {"what": "Contesto descrittivo. " * 450, "source_context": context}
    model = AsyncMock(return_value={"outcome": "no_goal", "reasoning": "Contesto da leggere."})
    monkeypatch.setattr(reasoning, "_ask_model", model)
    await reasoning.decide_goal(situation)
    encoded = model.call_args.args[1]
    payload = json.loads(encoded)
    assert len(encoded) <= 9000 and payload["context_truncated"] is True
    sources = payload["source_context"]
    assert [source["ref"] for source in sources] == [source["ref"] for source in context]
    assert all(source["excerpt_truncated"] and source["freshness"] == "unknown" for source in sources)
    assert all(source["authority"] == "user_asserted" for source in sources)
    assert situation["source_context"] == context


@pytest.mark.asyncio
async def test_verifier_budget_keeps_complete_cursors_for_retained_evidence(monkeypatch):
    from agent import reasoning

    db, goal = await seed()
    await db.memories.insert_many([
        {"id": f"mem_budget_{i}", "user_id": OWNER, "status": "active", "statement": TEXT}
        for i in range(7)
    ])
    goal.source_refs = []
    await StepExecutor(db).run(OWNER, goal, read_step(), may_touch_the_world=False)
    evidence = await EvidenceStore(db).for_goal(OWNER, goal.id)
    rows = for_verification(evidence)
    supplied = {row["evidence_id"]: row for row in rows}
    model = AsyncMock(return_value={"outcome": "uncertain", "what_is_missing": "Testo mancante."})
    monkeypatch.setattr(reasoning, "_ask_model", model)
    await reasoning.verify_goal(goal.for_ai(), evidence={"what_was_found": rows})
    encoded = model.call_args.args[1]
    assert len(encoded) <= 9000
    payload = json.loads(encoded)
    assert payload["context_truncated"] is True
    retained = payload["what_was_done"]["what_was_found"]
    assert retained and retained[-1]["evidence_id"] == rows[-1]["evidence_id"]
    for row in retained:
        original = supplied[row["evidence_id"]]
        assert row["source_refs"] == original["source_refs"]
        assert row["memory_reads"] == original["memory_reads"]
        assert "incomplet" in row["note"].lower()
        if row["what_was_found"] != original["what_was_found"]:
            assert row["excerpt_truncated"] is True
    assert all(len(row["memory_reads"]) == 8 for row in rows)


def test_unfittable_protected_context_is_explicitly_unavailable_and_bounded():
    from agent.reasoning import _dump

    encoded = _dump({
        "goal": {"id": "goal_synthetic", "source_kind": "memory", "desired_outcome": "x" * 10000},
        "source_refs": ["memory:" + "r" * 2000 for _ in range(8)],
    })
    assert len(encoded) <= 9000
    payload = json.loads(encoded)
    assert payload["context_truncated"] is True
    assert payload["source_context_unavailable"] is True
    assert "reread" in payload["reason"]
