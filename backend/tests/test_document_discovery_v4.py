from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from opportunities import snapshot
from opportunities.changes import fingerprint


@pytest.mark.asyncio
async def test_discovery_previews_are_owner_scoped_bounded_and_citable():
    db = AsyncMongoMockClient().test
    for i in range(9):
        await db.documents.insert_one({"id": str(i), "user_id": "alice",
            "extracted_text": "A" * 1600, "updated_at": f"2026-09-{i+1:02d}"})
    for flags in ({"user_id": "bob"}, {"deleted": True}, {"archived": True}):
        await db.documents.insert_one({"id": str(flags), "user_id": "alice",
            "updated_at": "2026-10-01", "extracted_text": "EXCLUDED", **flags})
    rows = await snapshot._documents(db, "alice", datetime.now(timezone.utc))
    assert len(rows) == snapshot.MAX_PER_SOURCE
    assert [r["ref"] for r in rows] == [f"document:{i}" for i in range(8, 2, -1)]
    assert all(len(r["unverified_excerpt"]) == 1200 and r["excerpt_truncated"] for r in rows)
    assert all(r["freshness"] == "unknown" for r in rows)
    assert snapshot.evidence_refs({"documents": rows})["document:8"] == "document"


@pytest.mark.asyncio
async def test_changes_outside_preview_invalidate_discovery_fingerprint():
    db = AsyncMongoMockClient().test
    await db.documents.insert_one({"id": "d", "user_id": "alice", "extracted_text": "A"*1200+"old"})
    before = await snapshot._documents(db, "alice", datetime.now(timezone.utc))
    await db.documents.update_one({"id": "d"}, {"$set": {"extracted_text": "A"*1200+"new"}})
    after = await snapshot._documents(db, "alice", datetime.now(timezone.utc))
    assert before[0]["unverified_excerpt"] == after[0]["unverified_excerpt"]
    assert fingerprint({"documents": before}) != fingerprint({"documents": after})


@pytest.mark.asyncio
async def test_document_permission_denial_prevents_query(monkeypatch):
    from agent.capabilities import CapabilityResolver
    monkeypatch.setattr(CapabilityResolver, "resolve", AsyncMock(return_value=SimpleNamespace(permitted=False)))
    with pytest.raises(PermissionError):
        await snapshot._documents(object(), "alice", datetime.now(timezone.utc))


@pytest.mark.asyncio
async def test_missing_extraction_is_explicit():
    db = AsyncMongoMockClient().test
    await db.documents.insert_one({"id": "d", "user_id": "alice"})
    row = (await snapshot._documents(db, "alice", datetime.now(timezone.utc)))[0]
    assert row["text_available"] is False and row["unverified_excerpt"] == ""


@pytest.mark.asyncio
async def test_snapshot_includes_documents_and_reports_source_failure(monkeypatch):
    db = AsyncMongoMockClient().test
    for name in ("_open_questions", "_recently_settled", "_places", "_presence", "_routines", "_comparisons", "_calendar", "_situations", "_disagreements", "_money", "_existing_work"):
        monkeypatch.setattr(snapshot, name, AsyncMock(return_value=[]))
    await db.documents.insert_one({"id": "d", "user_id": "alice", "extracted_text": "Dati sintetici: costo annuo 120 euro."})
    state = await snapshot.build(db, "alice")
    assert "120 euro" in state["documents"][0]["unverified_excerpt"]
    monkeypatch.setattr(snapshot, "_documents", AsyncMock(side_effect=RuntimeError("offline")))
    state = await snapshot.build(db, "alice")
    assert state["documents"] == [] and "documents" in state["unavailable_sources"]
