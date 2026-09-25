from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import ActionStep
from agent.providers import read_documents
from agent.service import AgentService


def step(**parameters):
    return ActionStep(intent="Leggi condizioni del documento", step_type="inspect",
                      capability_needed="document.read", input_refs=["document:d1"], parameters=parameters)


async def database(text="Condizioni del contratto: costo annuo 120 euro."):
    db = AsyncMongoMockClient().test
    await db.documents.insert_one({"id":"d1", "user_id":"alice", "original_filename":"contratto.pdf", "extracted_text":text})
    return db


@pytest.mark.asyncio
async def test_listing_has_reference_but_no_content():
    db = await database("RISERVATO contenuto")
    result = await read_documents(db, "alice", None)
    assert "document:d1" in result.claims[0].text
    assert "contratto.pdf" in result.claims[0].text
    assert "RISERVATO" not in str(result)


@pytest.mark.asyncio
async def test_targeted_excerpt_has_provenance_and_no_external_claim():
    db = await database()
    result = await read_documents(db, "alice", None, step=step())
    assert result.status == "succeeded"
    assert "120 euro" in result.claims[0].text
    assert result.provenance.source_refs[0] == "document:d1"
    assert result.provenance.freshness == "unknown"
    assert "non verificato" in result.claims[0].text


@pytest.mark.asyncio
async def test_each_read_rechecks_owner_and_deletion():
    db = await database()
    assert (await read_documents(db, "bob", None, step=step())).status == "unavailable"
    for flag in ("deleted", "archived"):
        await db.documents.update_one({"id":"d1"}, {"$set":{flag:True}})
        result = await read_documents(db, "alice", None, step=step())
        assert result.error_type == "document_unavailable" and not result.claims
        await db.documents.update_one({"id":"d1"}, {"$unset":{flag:""}})


@pytest.mark.asyncio
async def test_pagination_and_version_prevent_mixing_documents():
    db = await database("A"*4000 + "Fine documento")
    first = await read_documents(db, "alice", None, step=step())
    version = first.provenance.source_refs[1].split(":")[1]
    assert first.status == "partial" and len(first.claims) == 8
    assert all(len(c.text) <= 600 for c in first.claims)
    second = await read_documents(db, "alice", None, step=step(document_offset=4000, document_version=version))
    assert "Fine documento" in second.claims[0].text
    assert second.status == "partial"  # a later excerpt alone is not the whole file
    await db.documents.update_one({"id":"d1"}, {"$set":{"extracted_text":"B"*5000}})
    changed = await read_documents(db, "alice", None, step=step(document_offset=4000, document_version=version))
    assert changed.error_type == "document_version_changed" and not changed.claims


@pytest.mark.asyncio
async def test_absent_text_and_invalid_inputs_never_fake_success():
    db = await database("")
    assert (await read_documents(db,"alice",None,step=step())).error_type == "document_text_unavailable"
    for offset in (-1, True, "1"):
        assert (await read_documents(db,"alice",None,step=step(document_offset=offset))).error_type == "invalid_document_offset"
    invalid = step()
    invalid.input_refs = ["document:d1", "document:d2"]
    assert (await read_documents(db,"alice",None,step=invalid)).error_type == "document_reference_required"


def test_planner_reference_survives_parse_and_readback():
    parsed = AgentService._read_step({"intent":"Leggi", "step_type":"inspect",
        "capability_needed":"document.read", "input_refs":["document:d1"],
        "parameters":{"document_offset":4000,"document_version":"abc"}}, 0)
    assert parsed.input_refs == ["document:d1"]
    assert parsed.for_ai()["input_refs"] == ["document:d1"]


@pytest.mark.asyncio
async def test_executor_permission_boundary_and_evidence(monkeypatch):
    from agent.execution import StepExecutor
    db = await database()
    executor = StepExecutor(db)
    resolution = SimpleNamespace(known=True, permitted=False, writes=False, executable=True)
    monkeypatch.setattr(executor.capabilities,"resolve",AsyncMock(return_value=resolution))
    goal = SimpleNamespace(id="g1")
    denied = await executor.run("alice",goal,step(),may_touch_the_world=False)
    assert denied.error_type == "requires_connection"
    assert await db.agent_evidence.count_documents({}) == 0
    resolution.permitted = True
    result = await executor.run("alice",goal,step(),may_touch_the_world=False)
    assert result.status == "succeeded"
    evidence = await db.agent_evidence.find_one({"owner_id":"alice"})
    assert evidence["provenance"]["source_refs"][0] == "document:d1"
