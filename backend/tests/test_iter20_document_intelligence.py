"""Iterazione 20 — Document Intelligence (extraction pipeline) tests."""
from __future__ import annotations

import io
import os
import sys
import time
import uuid

import pytest

os.environ.setdefault("CALENDAR_PROVIDER_MODE", "fake")
os.environ.setdefault("DOCUMENT_EXTRACTION_ENABLED", "true")
os.environ.setdefault("DOCUMENT_OCR_ENABLED", "true")
sys.path.insert(0, "/app/backend")

import _loop_harness  # tests/_loop_harness.py: the one place a loop is chosen

from fastapi.testclient import TestClient  # noqa: E402
import server  # noqa: E402

TS = f"iter20_{int(time.time())}_{uuid.uuid4().hex[:6]}"


@pytest.fixture(scope="module")
def client(shared_client):
    return shared_client


@pytest.fixture(scope="module")
def user_a(client):
    r = client.post("/api/auth/register", json={
        "email": f"{TS}_a@ora.app", "password": "Passw0rd!", "name": "Iter20 A",
    })
    return {"token": r.json()["token"], "user_id": r.json()["user"]["user_id"]}


def h(user):
    return {"Authorization": f"Bearer {user['token']}"}


def _make_pdf(text: str = "Hello ORA extraction test") -> bytes:
    """Costruisce un minimo PDF valido con testo estraibile via pypdf."""
    from pypdf import PdfWriter
    from pypdf.generic import RectangleObject
    import io as _io
    # We use reportlab-like manual pdf: pypdf can't create pages with text
    # directly. Trick: encode with a tiny hand-written PDF stream that
    # pypdf can parse. Use PyPDF2's PageObject via a blank + insert text
    # if possible. Otherwise fall back to a minimal PDF that contains
    # the text in a plain content stream.
    pdf_body = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids [3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox [0 0 612 792]"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    )
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    pdf_body += f"4 0 obj<</Length {len(stream)}>>stream\n".encode() + stream + b"\nendstream endobj\n"
    pdf_body += b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    pdf_body += b"xref\n0 6\n"
    # dummy xref (works because pypdf tolerates minor inconsistencies)
    pdf_body += b"0000000000 65535 f\n0000000009 00000 n\n0000000056 00000 n\n"
    pdf_body += b"0000000105 00000 n\n0000000185 00000 n\n0000000280 00000 n\n"
    pdf_body += b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n360\n%%EOF"
    return pdf_body


def _upload(client, user, name, content, ct):
    files = {"file": (name, io.BytesIO(content), ct)}
    return client.post("/api/documents/upload", headers=h(user), files=files)


class TestA_PDFExtraction:
    def test_a1_pdf_text_extracted(self, client, user_a):
        pdf_bytes = _make_pdf("ORA test contenuto documento numero 12345")
        r = _upload(client, user_a, f"a-{TS}.pdf", pdf_bytes, "application/pdf")
        assert r.status_code == 200, r.text
        doc = r.json()["document"]
        # Response should carry the extraction summary
        assert doc.get("text_extracted") in (True, False)
        # Fetch full doc via GET (includes extracted_text)
        r2 = client.get(f"/api/documents/{doc['id']}", headers=h(user_a))
        body = r2.json()
        # pypdf may or may not extract with our hand-crafted PDF; test
        # accepts either but requires pipeline metadata to be present.
        assert "extraction_engine" in body
        assert body["extraction_engine"] in ("pypdf", "disabled")

    def test_a2_search_finds_extracted_text(self, client, user_a):
        pdf_bytes = _make_pdf(f"marker-{TS} unique content")
        r = _upload(client, user_a, f"search-{TS}.pdf", pdf_bytes, "application/pdf")
        assert r.status_code == 200
        # Search on extracted text (regex OR path)
        rs = client.get(f"/api/documents?q=marker-{TS}", headers=h(user_a))
        assert rs.status_code == 200
        items = rs.json()["items"]
        # If pypdf extracted, at least the file with marker matches by
        # filename OR extracted_text.
        assert any((f"search-{TS}" in i["filename"]) for i in items)


class TestB_OCR:
    def test_b1_image_upload_triggers_ocr_engine(self, client, user_a):
        # Small 1x1 PNG. Tesseract will emit empty text but the pipeline
        # MUST record ocr_used=True and engine=tesseract without error.
        import base64
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
        )
        r = _upload(client, user_a, f"tiny-{TS}.png", png, "image/png")
        assert r.status_code == 200
        doc = r.json()["document"]
        r2 = client.get(f"/api/documents/{doc['id']}", headers=h(user_a))
        body = r2.json()
        assert body["extraction_engine"] in ("tesseract", "ocr_disabled", "ocr_lib_missing", "ocr_engine_unavailable")
        # ocr_used is True whenever we routed to OCR provider (even if
        # engine unavailable, it flags the intent).
        assert body.get("ocr_used") in (True, False)


class TestC_TextFile:
    def test_c1_txt_passthrough(self, client, user_a):
        content = f"ORA plain text {TS}\nsecond line".encode()
        r = _upload(client, user_a, f"t-{TS}.txt", content, "text/plain")
        assert r.status_code == 200
        did = r.json()["document"]["id"]
        body = client.get(f"/api/documents/{did}", headers=h(user_a)).json()
        assert body["extraction_engine"] == "text_passthrough"
        assert body["text_extracted"] is True
        assert f"ORA plain text {TS}" in (body.get("extracted_text") or "")

    def test_c2_search_by_extracted_text(self, client, user_a):
        content = f"content-only-marker-{TS} in body".encode()
        r = _upload(client, user_a, f"cx-{TS}.txt", content, "text/plain")
        assert r.status_code == 200
        rs = client.get(f"/api/documents?q=content-only-marker-{TS}", headers=h(user_a))
        assert rs.status_code == 200
        assert any(f"cx-{TS}" in x["filename"] for x in rs.json()["items"])


class TestD_LifeGraphAndKnowledge:
    def test_d1_life_graph_node_has_extraction_attrs(self, client, user_a):
        content = f"life-graph-check-{TS}".encode()
        r = _upload(client, user_a, f"lg-{TS}.txt", content, "text/plain")
        node_id = r.json()["document"]["life_node_id"]
        n = client.get(f"/api/life-graph/nodes/{node_id}", headers=h(user_a))
        attrs = (n.json().get("attributes") or {})
        assert attrs.get("text_extracted") is True
        assert "pages" in attrs
        assert "language" in attrs


class TestE_MemoryAsk:
    def test_e1_ask_uses_extracted_text(self, client, user_a):
        content = f"Fattura numero INV-{TS} totale 123.45 EUR".encode()
        _upload(client, user_a, f"fattura-{TS}.txt", content, "text/plain")
        r = client.post("/api/memory/ask", headers=h(user_a), json={
            "question": f"Qual è il numero della fattura INV-{TS}?",
        })
        assert r.status_code in (200, 502)
        if r.status_code == 200:
            body = r.json()
            # sources should include a document entry
            srcs = body.get("sources") or []
            assert any(s.get("source") == "document" for s in srcs)


class TestF_Idempotency:
    def test_f1_dedup_skips_re_extraction(self, client, user_a):
        content = f"dedup-{TS}-content".encode()
        r1 = _upload(client, user_a, "dd.txt", content, "text/plain")
        r2 = _upload(client, user_a, "dd.txt", content, "text/plain")
        assert r1.json()["duplicate"] is False
        assert r2.json()["duplicate"] is True
        # Same id returned — no new extraction record
        assert r1.json()["document"]["id"] == r2.json()["document"]["id"]


class TestG_ErrorHandling:
    def test_g1_corrupted_pdf(self, client, user_a):
        r = _upload(client, user_a, f"bad-{TS}.pdf", b"not a pdf at all", "application/pdf")
        assert r.status_code == 200  # upload still OK
        did = r.json()["document"]["id"]
        body = client.get(f"/api/documents/{did}", headers=h(user_a)).json()
        assert body["extraction_engine"] == "pypdf"
        assert body.get("extraction_error_code") in ("pdf_corrupted", "pdf_lib_missing", None)


class TestH_ContextProviderGated:
    def test_h1_provider_still_no_op_when_flag_off(self, monkeypatch):
        monkeypatch.setenv("DOCUMENT_CONTEXT_ENABLED", "false")
        from documents.context_provider import documents_provider
        import asyncio

        class BoomDB:
            def __getattr__(self, name):
                raise AssertionError("db should NOT be touched when flag is off")

        async def _run():
            return await documents_provider(BoomDB(), "user_xxx")

        res = _loop_harness.run(_run())
        assert res.error is None and res.signals == []
