"""Iterazione 19 — Documents Foundation tests (HTTP-only)."""
from __future__ import annotations

import io
import os
import sys
import time
import uuid

import pytest

os.environ.setdefault("CALENDAR_PROVIDER_MODE", "fake")
sys.path.insert(0, "/app/backend")

from fastapi.testclient import TestClient  # noqa: E402
import server  # noqa: E402

TS = f"iter19_{int(time.time())}_{uuid.uuid4().hex[:6]}"


@pytest.fixture(scope="module")
def client(shared_client):
    return shared_client


@pytest.fixture(scope="module")
def user_a(client):
    r = client.post("/api/auth/register", json={
        "email": f"{TS}_a@ora.app", "password": "Passw0rd!", "name": "Iter19 A",
    })
    return {"token": r.json()["token"], "user_id": r.json()["user"]["user_id"]}


@pytest.fixture(scope="module")
def user_b(client):
    r = client.post("/api/auth/register", json={
        "email": f"{TS}_b@ora.app", "password": "Passw0rd!", "name": "Iter19 B",
    })
    return {"token": r.json()["token"], "user_id": r.json()["user"]["user_id"]}


def h(user):
    return {"Authorization": f"Bearer {user['token']}"}


def _upload(client, user, name="ricevuta.pdf", content=b"%PDF-1.4 test doc",
            content_type="application/pdf", tags=None, notes=None):
    files = {"file": (name, io.BytesIO(content), content_type)}
    data = {}
    if tags is not None:
        data["tags"] = ",".join(tags) if isinstance(tags, list) else str(tags)
    if notes is not None:
        data["notes"] = notes
    return client.post("/api/documents/upload", headers=h(user), files=files, data=data)


# =====================================================================
# A) Upload / dedup / validation
# =====================================================================
class TestA_Upload:
    def test_a1_upload_returns_doc(self, client, user_a):
        r = _upload(client, user_a, name=f"contratto-{TS}.pdf",
                    content=b"%PDF-1.4 hello world", tags=["contratto", "lavoro"],
                    notes="Contratto firmato il 12/03")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["duplicate"] is False
        doc = body["document"]
        assert doc["filename"].startswith("contratto-")
        assert doc["mime_type"] == "application/pdf"
        assert doc["size"] > 0
        assert doc["hash"]
        assert doc["archived"] is False
        assert doc["deleted"] is False
        assert doc["tags"] == ["contratto", "lavoro"]
        assert doc["notes"].startswith("Contratto")
        assert doc["life_node_id"], "life_node_id must be attached"
        assert doc["knowledge_synced"] is True
        assert doc["storage_provider"] == "local"

    def test_a2_dedup_same_content(self, client, user_a):
        content = b"unique-payload-for-dedup-" + TS.encode()
        r1 = _upload(client, user_a, name="a.txt", content=content, content_type="text/plain")
        r2 = _upload(client, user_a, name="a.txt", content=content, content_type="text/plain")
        assert r1.status_code == r2.status_code == 200
        assert r1.json()["duplicate"] is False
        assert r2.json()["duplicate"] is True
        assert r1.json()["document"]["id"] == r2.json()["document"]["id"]

    def test_a3_mime_not_allowed(self, client, user_a):
        r = _upload(client, user_a, name="mal.exe", content=b"\x4d\x5a...",
                    content_type="application/x-msdownload")
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "mime_not_allowed"

    def test_a4_empty_file(self, client, user_a):
        r = _upload(client, user_a, name="empty.txt", content=b"", content_type="text/plain")
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "empty_content"


# =====================================================================
# B) List / search / sort / filter
# =====================================================================
class TestB_List:
    def test_b1_list_returns_user_docs_only(self, client, user_a, user_b):
        _upload(client, user_a, name=f"a-only-{TS}.txt", content=b"aaa" + TS.encode(), content_type="text/plain")
        _upload(client, user_b, name=f"b-only-{TS}.txt", content=b"bbb" + TS.encode(), content_type="text/plain")
        r = client.get("/api/documents", headers=h(user_a))
        assert r.status_code == 200
        items = r.json()["items"]
        assert all(d["user_id"] == user_a["user_id"] for d in items)
        filenames = [d["filename"] for d in items]
        assert any(f.startswith("a-only-") for f in filenames)
        assert not any(f.startswith("b-only-") for f in filenames)

    def test_b2_search_by_filename(self, client, user_a):
        needle = f"needle_{uuid.uuid4().hex[:6]}"
        _upload(client, user_a, name=f"{needle}.pdf", content=needle.encode() + b"content", content_type="application/pdf")
        r = client.get(f"/api/documents?q={needle}", headers=h(user_a))
        assert r.status_code == 200
        items = r.json()["items"]
        assert any(needle in d["filename"] for d in items)

    def test_b3_search_by_tag_and_mime_filter(self, client, user_a):
        _upload(client, user_a, name=f"note-{TS}.txt", content=b"txt-1" + TS.encode(),
                content_type="text/plain", tags=["fiscale"])
        r = client.get("/api/documents?tag=fiscale&mime=text/plain", headers=h(user_a))
        assert r.status_code == 200
        items = r.json()["items"]
        assert any("fiscale" in (d.get("tags") or []) for d in items)
        assert all(d.get("mime_type") == "text/plain" for d in items)

    def test_b4_sort_by_name_asc(self, client, user_a):
        r = client.get("/api/documents?sort=name_asc&limit=200", headers=h(user_a))
        items = r.json()["items"]
        names = [d["filename"] for d in items]
        assert names == sorted(names, key=lambda s: s.lower()) or names == sorted(names)


# =====================================================================
# C) Get / Patch / Download / Ownership
# =====================================================================
class TestC_Detail:
    def test_c1_get_by_id_ownership(self, client, user_a, user_b):
        r = _upload(client, user_a, name=f"secret-{TS}.txt", content=b"top-secret" + TS.encode(), content_type="text/plain")
        doc_id = r.json()["document"]["id"]
        # Owner can fetch
        r1 = client.get(f"/api/documents/{doc_id}", headers=h(user_a))
        assert r1.status_code == 200
        # Non-owner: 404
        r2 = client.get(f"/api/documents/{doc_id}", headers=h(user_b))
        assert r2.status_code == 404

    def test_c2_patch(self, client, user_a):
        r = _upload(client, user_a, name=f"patch-{TS}.txt", content=b"patch" + TS.encode(), content_type="text/plain")
        doc_id = r.json()["document"]["id"]
        r2 = client.patch(f"/api/documents/{doc_id}", headers=h(user_a),
                          json={"tags": ["updated"], "notes": "Nota aggiornata"})
        assert r2.status_code == 200
        assert r2.json()["tags"] == ["updated"]
        assert r2.json()["notes"] == "Nota aggiornata"

    def test_c3_download_returns_original_bytes(self, client, user_a, user_b):
        payload = b"download-payload-" + TS.encode()
        r = _upload(client, user_a, name=f"dl-{TS}.txt", content=payload, content_type="text/plain")
        doc_id = r.json()["document"]["id"]
        dr = client.get(f"/api/documents/{doc_id}/download", headers=h(user_a))
        assert dr.status_code == 200
        assert dr.content == payload
        # Ownership on download
        dr2 = client.get(f"/api/documents/{doc_id}/download", headers=h(user_b))
        assert dr2.status_code == 404


# =====================================================================
# D) Archive / Restore / Soft Delete / Hard Delete
# =====================================================================
class TestD_Lifecycle:
    def test_d1_archive_then_restore(self, client, user_a):
        r = _upload(client, user_a, name=f"arch-{TS}.txt", content=b"arch" + TS.encode(), content_type="text/plain")
        doc_id = r.json()["document"]["id"]
        # Archive
        a = client.post(f"/api/documents/{doc_id}/archive", headers=h(user_a))
        assert a.status_code == 200
        assert a.json()["archived"] is True
        # Listing default should not include archived unless requested
        lst = client.get("/api/documents?archived=true", headers=h(user_a))
        assert any(d["id"] == doc_id for d in lst.json()["items"])
        # Restore
        rr = client.post(f"/api/documents/{doc_id}/restore", headers=h(user_a))
        assert rr.status_code == 200
        assert rr.json()["archived"] is False

    def test_d2_soft_delete_hides_from_default_listing(self, client, user_a):
        r = _upload(client, user_a, name=f"delme-{TS}.txt", content=b"delme" + TS.encode(), content_type="text/plain")
        doc_id = r.json()["document"]["id"]
        d = client.delete(f"/api/documents/{doc_id}", headers=h(user_a))
        assert d.status_code == 200
        assert d.json()["ok"] is True
        # Not visible in default listing
        lst = client.get("/api/documents", headers=h(user_a))
        assert not any(x["id"] == doc_id for x in lst.json()["items"])
        # Detail via GET returns 404 (default excludes deleted)
        g = client.get(f"/api/documents/{doc_id}", headers=h(user_a))
        assert g.status_code == 404

    def test_d3_hard_delete_removes_blob(self, client, user_a):
        r = _upload(client, user_a, name=f"hard-{TS}.txt", content=b"hard-" + TS.encode(), content_type="text/plain")
        doc_id = r.json()["document"]["id"]
        d = client.delete(f"/api/documents/{doc_id}?hard=true", headers=h(user_a))
        assert d.status_code == 200
        assert d.json()["hard"] is True
        g = client.get(f"/api/documents/{doc_id}", headers=h(user_a))
        assert g.status_code == 404


# =====================================================================
# E) Life Graph + Knowledge Layer + Memory tab
# =====================================================================
class TestE_Wiring:
    def test_e1_life_graph_node_created(self, client, user_a):
        r = _upload(client, user_a, name=f"lg-{TS}.pdf", content=b"%PDF life-graph-" + TS.encode(),
                    content_type="application/pdf")
        node_id = r.json()["document"]["life_node_id"]
        n = client.get(f"/api/life-graph/nodes/{node_id}", headers=h(user_a))
        assert n.status_code == 200
        node = n.json()
        assert node["type"] == "document"
        attrs = node.get("attributes") or {}
        assert attrs.get("mime_type") == "application/pdf"
        assert attrs.get("source") == "user_upload"

    def test_e2_knowledge_layer_facts_present(self, client, user_a):
        r = _upload(client, user_a, name=f"kl-{TS}.txt", content=b"knowledge-test-" + TS.encode(),
                    content_type="text/plain", tags=["kb"], notes="Test knowledge")
        node_id = r.json()["document"]["life_node_id"]
        k = client.get(f"/api/knowledge/nodes/{node_id}", headers=h(user_a))
        assert k.status_code == 200
        props = (k.json().get("properties") or {})
        assert "filename" in props
        assert "mime_type" in props
        assert "tags" in props
        assert "notes" in props

    def test_e3_memory_tab_includes_documents(self, client, user_a):
        r = client.get("/api/memory", headers=h(user_a))
        assert r.status_code == 200
        body = r.json()
        assert "documents" in body
        # We uploaded several docs across tests, at least one must show up
        assert isinstance(body["documents"], list) and len(body["documents"]) >= 1
        sample = body["documents"][0]
        assert set(["id", "filename", "mime_type", "created_at"]).issubset(sample.keys())


# =====================================================================
# F) Context Provider flag gate
# =====================================================================
class TestF_ContextProvider:
    def test_f1_provider_no_op_when_flag_off(self, monkeypatch):
        """Il provider deve essere un NO-OP quando DOCUMENT_CONTEXT_ENABLED=false."""
        monkeypatch.setenv("DOCUMENT_CONTEXT_ENABLED", "false")
        from documents.context_provider import documents_provider

        # Inline coroutine run
        import asyncio

        async def _run():
            # A dummy `db` that would fail if used
            class BoomDB:
                def __getattr__(self, name):
                    raise AssertionError("db should NOT be touched when flag is off")
            res = await documents_provider(BoomDB(), "user_xxx")
            return res

        result = asyncio.get_event_loop().run_until_complete(_run())
        assert result.error is None
        assert result.signals == []
