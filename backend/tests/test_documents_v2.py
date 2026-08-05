"""Documents V2 — hub, prefs, auto-add gates, pipeline states, migration stamp."""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest

os.environ.setdefault("CALENDAR_PROVIDER_MODE", "fake")
_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_pipeline_v2_states_include_new_aliases():
    from documents.intelligence.pipeline import PIPELINE_STATES, PIPELINE_VERSION, STATE_LABELS_IT
    assert PIPELINE_VERSION.startswith("intel-docs-2")
    for s in ("understanding", "generating_actions", "awaiting_confirmation", "analyzing", "action_required"):
        assert s in PIPELINE_STATES
        assert s in STATE_LABELS_IT


def test_migration_stamp_preserves_legacy():
    from documents.intelligence.migration import stamp_document_versions, with_versions
    doc = {"id": "d1", "filename": "old.pdf", "pipeline_version": "intel-docs-1.0", "analysis": {"summary": "x"}}
    patch = stamp_document_versions(doc)
    assert patch["document_schema_version"] == "2.0"
    assert patch["legacy_data_preserved"] is True
    assert patch["analysis_version"] == "2.0"
    view = with_versions({**doc, **patch})
    assert view["filename"] == "old.pdf"
    assert view["analysis"]["summary"] == "x"


def test_auto_add_disabled_by_default_and_gates():
    async def body():
        from motor.motor_asyncio import AsyncIOMotorClient
        from documents.intelligence.service import IntelligenceService
        from documents.service import DocumentService
        from documents.storage import LocalFilesystemStorage
        import tempfile

        client = AsyncIOMotorClient(MONGO)
        db = client[DBNAME]
        try:
            tmp = tempfile.mkdtemp(prefix="ora_v2_")
            dsvc = DocumentService(db=db, storage=LocalFilesystemStorage(base_dir=tmp), life_graph=None, knowledge=None)
            intel = IntelligenceService(db, dsvc)
            user = f"user_{uuid.uuid4().hex[:10]}"
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora", "preferences": {}})
            prefs = await intel.get_document_prefs(user)
            assert prefs["calendar_auto_add_enabled"] is False
            assert prefs["calendar_auto_add_threshold"] == 0.90

            # enable but low confidence → no attempt
            await intel.set_document_prefs(user, {"calendar_auto_add_enabled": True, "calendar_auto_add_threshold": 0.95})
            out = await intel._maybe_auto_add_calendar(
                user_id=user,
                doc_id="doc_x",
                events=[{
                    "id": "ev1", "status": "proposed", "confidence": 0.5,
                    "start_datetime": "2026-11-01T10:00:00+01:00", "timezone": "Europe/Rome",
                    "ambiguous_date": False,
                }],
                analysis={},
                user={"preferences": {"calendar_auto_add_enabled": True, "calendar_auto_add_threshold": 0.95}},
            )
            assert out["attempted"] is False
            assert out["reason"] == "low_confidence"

            # multiple events → no attempt
            out2 = await intel._maybe_auto_add_calendar(
                user_id=user,
                doc_id="doc_x",
                events=[
                    {"id": "a", "status": "proposed", "confidence": 0.99, "start_datetime": "2026-11-01T10:00:00+01:00", "timezone": "Europe/Rome"},
                    {"id": "b", "status": "proposed", "confidence": 0.99, "start_datetime": "2026-11-02T10:00:00+01:00", "timezone": "Europe/Rome"},
                ],
                analysis={},
                user={"preferences": {"calendar_auto_add_enabled": True, "calendar_auto_add_threshold": 0.9}},
            )
            assert out2["reason"] == "multiple_or_none"
            await db.users.delete_many({"user_id": user})
        finally:
            client.close()

    _run(body())


def test_hub_and_pipeline_on_upload():
    async def body():
        from motor.motor_asyncio import AsyncIOMotorClient
        from documents.intelligence.service import IntelligenceService
        from documents.service import DocumentService
        from documents.storage import LocalFilesystemStorage
        import tempfile

        client = AsyncIOMotorClient(MONGO)
        db = client[DBNAME]
        try:
            tmp = tempfile.mkdtemp(prefix="ora_v2hub_")
            dsvc = DocumentService(db=db, storage=LocalFilesystemStorage(base_dir=tmp), life_graph=None, knowledge=None)
            intel = IntelligenceService(db, dsvc)
            user = f"user_{uuid.uuid4().hex[:10]}"
            content = b"""Appuntamento concerto ORA V2 TEST
Data: 15 dicembre 2026 ore 21:00
Luogo: Milano Arena
Titolo: Concerto prova ORA V2
"""
            up = await dsvc.upload(
                user_id=user,
                content=content,
                original_filename="concerto_v2.txt",
                mime_type="text/plain",
            )
            doc_id = up["document"]["id"]
            # stamp versions via get
            got = await dsvc.get(user_id=user, doc_id=doc_id)
            assert got.get("document_schema_version") == "2.0"

            await intel.run_pipeline(user_id=user, doc_id=doc_id, force_local=True)
            analysis = await intel.get_analysis(user_id=user, doc_id=doc_id)
            assert analysis.get("analysis")
            assert analysis.get("display_title")
            hub = await intel.hub(user_id=user, limit=20)
            assert "recent" in hub and "counts" in hub
            assert any(c["id"] == doc_id for c in hub["recent"])
            await dsvc.delete(user_id=user, doc_id=doc_id)
        finally:
            client.close()

    _run(body())


@pytest.fixture(scope="module")
def client(shared_client):
    return shared_client


def test_http_hub_requires_auth(client):
    r = client.get("/api/documents/hub")
    assert r.status_code in (401, 403)
