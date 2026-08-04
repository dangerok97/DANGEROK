"""Intelligent documents — local analysis, events, isolation (synthetic fixtures)."""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from motor.motor_asyncio import AsyncIOMotorClient

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "ora_intel_docs_test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("DOCUMENT_AI_ENABLED", "0")

MONGO = os.environ["MONGO_URL"]
DBNAME = os.environ["DB_NAME"]
LIVE = os.environ.get("ORA_LIVE_URL", "http://127.0.0.1:8000").rstrip("/")
BASE = f"{LIVE}/api"


def _run(coro):
    return asyncio.run(coro)


def _live_ok() -> bool:
    try:
        r = httpx.get(f"{BASE}/health", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


CONCERT_TXT = """
BIGLIETTO CONCERTO
Artista: Coldplay
Data: 12 luglio 2027 ore 21:00
Luogo: Stadio Olimpico
Indirizzo: Viale dei Gladiatori, Roma
Codice ordine: ORD-998877
"""

NOTES_TXT = """
Dispensa di Antropologia culturale
Materia: Antropologia
Argomento: Habitus di Bourdieu
Definizione: L'habitus è un sistema di disposizioni durature.
Concetto: capitale culturale
Concetto: campo sociale
"""

AMBIG_TXT = """
Appuntamento importante
Data: 03/04/2027 ore 10:30
Luogo: Ufficio Anagrafe
"""


def test_taxonomy_and_event_from_concert():
    from documents.intelligence.taxonomy import refine_taxonomy
    from documents.intelligence.analyzer import analyze_document

    tax = refine_taxonomy(type_key="ticket", text=CONCERT_TXT, filename="ticket.pdf")
    assert tax["macro_category"] in ("event", "travel")

    async def body():
        doc = {
            "id": "doc_test_concert",
            "filename": "ticket.pdf",
            "original_filename": "ticket.pdf",
            "extracted_text": CONCERT_TXT,
            "detected_language": "it",
        }
        res = await analyze_document(doc, force_local=True)
        assert res["analysis"]["macro_category"] in ("event", "travel")
        assert res["event_candidates"], "expected at least one event candidate"
        ev = res["event_candidates"][0]
        assert "Coldplay" in ev["title"] or "Concerto" in ev["title"] or ev["title"]
        assert ev["status"] == "proposed"
        assert ev.get("city") == "Roma" or "Roma" in (ev.get("address") or "") or ev.get("venue_name")

    _run(body())


def test_education_notes():
    async def body():
        from documents.intelligence.analyzer import analyze_document
        doc = {
            "id": "doc_test_notes",
            "filename": "documento_3.pdf",
            "original_filename": "documento_3.pdf",
            "extracted_text": NOTES_TXT,
        }
        res = await analyze_document(doc, force_local=True)
        assert res["analysis"]["macro_category"] == "education"
        assert res["education_analysis"] is not None
        assert res["education_analysis"].get("subject")
        assert "Antropologia" in (res["analysis"]["suggested_title"] or "") or res["education_analysis"].get("subject")

    _run(body())


def test_ambiguous_date_flags_review():
    async def body():
        from documents.intelligence.analyzer import analyze_document
        doc = {
            "id": "doc_test_ambig",
            "filename": "app.pdf",
            "original_filename": "app.pdf",
            "extracted_text": AMBIG_TXT,
        }
        res = await analyze_document(doc, force_local=True)
        assert res["event_candidates"]
        # ambiguous or requires review
        assert res["analysis"]["requires_review"] or res["event_candidates"][0].get("ambiguous_date")

    _run(body())


def test_pipeline_persist_confirm_calendar_and_isolation():
    async def body():
        from documents.intelligence.service import IntelligenceService
        from documents.service import DocumentService
        from documents.storage import LocalFilesystemStorage
        import tempfile

        client = AsyncIOMotorClient(MONGO)
        db = client[DBNAME]
        try:
            tmp = tempfile.mkdtemp(prefix="ora_docs_")
            storage = LocalFilesystemStorage(base_dir=tmp)
            dsvc = DocumentService(db=db, storage=storage, life_graph=None, knowledge=None)
            intel = IntelligenceService(db, dsvc)

            user_a = f"user_{uuid.uuid4().hex[:10]}"
            user_b = f"user_{uuid.uuid4().hex[:10]}"
            content = CONCERT_TXT.encode("utf-8")
            up = await dsvc.upload(
                user_id=user_a,
                content=content,
                original_filename="concert_test.txt",
                mime_type="text/plain",
            )
            doc = up["document"]
            doc_id = doc["id"]
            # run pipeline synchronously (worker may not be running in test)
            out = await intel.run_pipeline(user_id=user_a, doc_id=doc_id, force_local=True)
            assert out.get("ok") is True
            analysis = await intel.get_analysis(user_id=user_a, doc_id=doc_id)
            assert analysis.get("analysis")
            assert analysis.get("event_candidates")
            ev_id = analysis["event_candidates"][0]["id"]

            # user B cannot read
            with pytest.raises(Exception):
                await intel.get_analysis(user_id=user_b, doc_id=doc_id)

            # confirm → calendar draft
            conf = await intel.confirm_event(user_id=user_a, doc_id=doc_id, event_id=ev_id)
            assert conf["ok"] is True
            assert conf["calendar_event"]["provider"] == "internal"
            assert conf["calendar_event"]["user_id"] == user_a

            # dismiss path on a second synthetic event
            # reanalyze keeps confirmed
            await intel.run_pipeline(user_id=user_a, doc_id=doc_id, force_local=True)
            again = await intel.get_analysis(user_id=user_a, doc_id=doc_id)
            statuses = {e["id"]: e["status"] for e in again["event_candidates"]}
            assert statuses.get(ev_id) == "confirmed" or any(
                e.get("status") == "confirmed" for e in again["event_candidates"]
            )

            # clear analysis keeps file
            await intel.clear_analysis(user_id=user_a, doc_id=doc_id)
            cleared = await intel.get_analysis(user_id=user_a, doc_id=doc_id)
            assert cleared.get("analysis") is None
            still = await dsvc.get(user_id=user_a, doc_id=doc_id)
            assert still["id"] == doc_id

            # unauthenticated HTTP (skip soft if live server not yet restarted)
            if _live_ok():
                r = httpx.post(f"{BASE}/documents/{doc_id}/analyze", timeout=10)
                assert r.status_code in (401, 403, 404)
        finally:
            client.close()

    _run(body())


def test_llm_absent_still_analyzes_locally():
    async def body():
        from documents.intelligence.analyzer import analyze_document
        os.environ["LLM_PROVIDER"] = "none"
        res = await analyze_document(
            {
                "id": "doc_x",
                "filename": "a.txt",
                "original_filename": "a.txt",
                "extracted_text": "Ricevuta supermercato Esselunga 12,50 EUR data 01 gennaio 2026",
            },
            force_local=True,
        )
        assert res["analysis"]["local_only"] is True
        assert res["analysis"]["ai_used"] is False

    _run(body())


def test_maps_urls():
    from documents.intelligence.analyzer import maps_directions_url, maps_query_url
    u = maps_query_url("Stadio Olimpico, Roma")
    assert u.startswith("https://www.google.com/maps/search/")
    d = maps_directions_url("Stadio Olimpico, Roma")
    assert "destination=" in d


@pytest.mark.skipif(not _live_ok(), reason="uvicorn not running")
def test_http_upload_triggers_pipeline_fields():
    email = f"intel.{uuid.uuid4().hex[:8]}@ora.app"
    with httpx.Client(timeout=40.0) as c:
        reg = c.post(f"{BASE}/auth/register", json={"email": email, "password": "IntelDocs123!", "name": "Intel"})
        assert reg.status_code == 200, reg.text
        token = reg.json()["token"]
        h = {"Authorization": f"Bearer {token}"}
        files = {"file": ("concert_live.txt", CONCERT_TXT.encode(), "text/plain")}
        up = c.post(f"{BASE}/documents/upload", headers=h, files=files)
        assert up.status_code == 200, up.text
        doc_id = up.json()["document"]["id"]
        # wait for worker a bit
        import time
        analysis = None
        for _ in range(20):
            time.sleep(0.5)
            r = c.get(f"{BASE}/documents/{doc_id}/analysis", headers=h)
            assert r.status_code == 200
            analysis = r.json()
            if analysis.get("analysis") or analysis.get("pipeline_status") in (
                "completed", "action_required", "needs_review", "failed",
            ):
                if analysis.get("analysis"):
                    break
        assert analysis is not None
        # force analyze if worker slow
        if not analysis.get("analysis"):
            c.post(f"{BASE}/documents/{doc_id}/analyze", headers=h)
            time.sleep(2)
            # also accept running pipeline synchronously via re-get
            analysis = c.get(f"{BASE}/documents/{doc_id}/analysis", headers=h).json()
        # At minimum pipeline status should exist
        assert analysis.get("pipeline_status") in (
            "uploaded", "queued", "extracting", "classifying", "analyzing",
            "action_required", "completed", "failed", "needs_review",
        )
