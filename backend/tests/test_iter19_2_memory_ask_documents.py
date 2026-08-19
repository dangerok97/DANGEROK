"""Iterazione 19.2 — Bug fix: POST /api/memory/ask ora include i documenti
caricati dall'utente nel contesto LLM (fonte additiva).

Verifica:
  * ZERO regressione: nuovo utente senza dati → risposta storica
  * ZERO regressione: memoria classica risponde ancora
  * Documenti singolo/plurale citati in ask
  * Soft-delete: doc con deleted=True NON compare tra le sources documento
  * Archived: doc con archived=True compare ma con flag archived
  * Ownership: user A non vede docs di user B
  * `sources` include entries con source='document' quando ci sono docs
"""
from __future__ import annotations

import io
import os
import sys
import time
import uuid

import pytest

os.environ.setdefault("CALENDAR_PROVIDER_MODE", "fake")
sys.path.insert(0, "/app/backend")

from fastapi.testclient import TestClient  # noqa: E402,F401
import server  # noqa: E402,F401

TS = f"iter192_{int(time.time())}_{uuid.uuid4().hex[:6]}"


# --- fixtures ---------------------------------------------------------
@pytest.fixture(scope="module")
def client(shared_client):
    return shared_client


def _register(client, tag: str):
    email = f"{TS}_{tag}_{uuid.uuid4().hex[:6]}@ora.app"
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": "Passw0rd!", "name": f"iter192 {tag}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    return {"token": body["token"], "user_id": body["user"]["user_id"], "email": email}


def h(user):
    return {"Authorization": f"Bearer {user['token']}"}


def _upload(client, user, name, content=b"%PDF-1.4 test", content_type="application/pdf",
            tags=None, notes=None):
    files = {"file": (name, io.BytesIO(content), content_type)}
    data = {}
    if tags is not None:
        data["tags"] = ",".join(tags) if isinstance(tags, list) else str(tags)
    if notes is not None:
        data["notes"] = notes
    r = client.post("/api/documents/upload", headers=h(user), files=files, data=data)
    return r


def _ask(client, user, question):
    return client.post("/api/memory/ask", headers=h(user), json={"question": question})


def _skip_if_provider_unavailable(response):
    """Accept legacy 502 and canonical V2.8.3a temporary-unavailable 503."""
    if response.status_code in (502, 503):
        pytest.skip(
            f"LLM {response.status_code} - external service temporarily unavailable"
        )


# =====================================================================
# A) ZERO REGRESSIONE
# =====================================================================
class TestA_ZeroRegression:
    def test_a1_new_user_no_data_returns_historic_answer(self, client):
        """User nuovo, zero memorie e zero documenti → risposta storica."""
        user = _register(client, "empty")
        r = _ask(client, user, "Ho caricato qualche documento?")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["sources"] == []
        assert "Non ho ancora nulla salvato nella tua memoria" in body["answer"]

    def test_a2_memory_only_still_answers(self, client):
        """User con SOLO memoria testuale → ask usa memorie come prima (no docs)."""
        user = _register(client, "memonly")
        # Aggiungi memoria classica
        m = client.post("/api/memory", headers=h(user), json={
            "content": "Ho comprato il televisore da MediaWorld il 3 aprile",
            "tags": ["acquisto"],
        })
        assert m.status_code == 200, m.text

        r = _ask(client, user, "Dove ho comprato il televisore?")
        # 200 se LLM disponibile; 502 legacy / 503 canonical unavailable sono accettati.
        _skip_if_provider_unavailable(r)
        assert r.status_code == 200, r.text
        body = r.json()
        # sources deve contenere memorie
        assert isinstance(body["sources"], list) and len(body["sources"]) >= 1
        # nessuna source di tipo document dato che l'utente non ha docs
        assert all(s.get("source") != "document" for s in body["sources"])
        # answer plausibile: cita MediaWorld
        assert "mediaworld" in body["answer"].lower() or "media" in body["answer"].lower()


# =====================================================================
# B) DOCUMENTI VISIBILI IN ASK
# =====================================================================
class TestB_DocsInAsk:
    def test_b1_single_document_appears_in_sources(self, client):
        user = _register(client, "onedoc")
        up = _upload(client, user, name=f"fattura-{TS}.pdf",
                     content=b"%PDF-1.4 fattura", content_type="application/pdf",
                     tags=["fiscale"], notes="fattura marzo 2026")
        assert up.status_code == 200, up.text

        r = _ask(client, user, "Ho caricato qualche documento?")
        # Anche se LLM down, la ricerca dei docs avviene prima del provider;
        # non possiamo però controllare sources senza risposta 200.
        _skip_if_provider_unavailable(r)
        assert r.status_code == 200, r.text
        body = r.json()
        doc_sources = [s for s in body["sources"] if s.get("source") == "document"]
        assert len(doc_sources) >= 1
        assert doc_sources[0]["filename"].startswith("fattura-")
        # answer dovrebbe menzionare il file
        assert "fattura" in body["answer"].lower()

    def test_b2_multiple_documents_all_returned(self, client):
        user = _register(client, "multidoc")
        for i, name in enumerate([f"doc-a-{TS}.pdf", f"doc-b-{TS}.pdf", f"doc-c-{TS}.txt"]):
            content = f"content-{i}-{TS}".encode()
            ct = "text/plain" if name.endswith(".txt") else "application/pdf"
            up = _upload(client, user, name=name, content=content, content_type=ct)
            assert up.status_code == 200

        r = _ask(client, user, "Quanti documenti ho caricato?")
        _skip_if_provider_unavailable(r)
        assert r.status_code == 200
        body = r.json()
        doc_sources = [s for s in body["sources"] if s.get("source") == "document"]
        assert len(doc_sources) >= 3

    def test_b3_search_by_filename_hits_specific_doc(self, client):
        user = _register(client, "byname")
        unique = f"contratto_lavoro_{uuid.uuid4().hex[:6]}"
        up = _upload(client, user, name=f"{unique}.pdf",
                     content=b"%PDF-1.4 " + unique.encode(),
                     content_type="application/pdf")
        assert up.status_code == 200

        r = _ask(client, user, f"Ho un file {unique}.pdf?")
        _skip_if_provider_unavailable(r)
        assert r.status_code == 200
        body = r.json()
        # answer cita il nome file oppure "sì"
        assert unique in body["answer"] or "sì" in body["answer"].lower() or "si" in body["answer"].lower()

    def test_b4_search_by_tag(self, client):
        user = _register(client, "bytag")
        up = _upload(client, user, name=f"tax-{TS}.pdf",
                     content=b"%PDF-1.4 tax-" + TS.encode(),
                     content_type="application/pdf", tags=["fiscale"],
                     notes="dichiarazione")
        assert up.status_code == 200

        r = _ask(client, user, "Ho documenti con tag fiscale?")
        _skip_if_provider_unavailable(r)
        assert r.status_code == 200
        body = r.json()
        doc_sources = [s for s in body["sources"] if s.get("source") == "document"]
        assert any("fiscale" in (s.get("tags") or []) for s in doc_sources)


# =====================================================================
# C) SOFT-DELETE / ARCHIVE / OWNERSHIP
# =====================================================================
class TestC_Filters:
    def test_c1_soft_deleted_excluded_from_ask(self, client):
        user = _register(client, "softdel")
        up = _upload(client, user, name=f"todel-{TS}.pdf",
                     content=b"%PDF-1.4 todel-" + TS.encode(),
                     content_type="application/pdf")
        assert up.status_code == 200
        doc_id = up.json()["document"]["id"]
        # soft delete
        d = client.delete(f"/api/documents/{doc_id}", headers=h(user))
        assert d.status_code == 200

        r = _ask(client, user, "Che documenti ho?")
        # We still can inspect DB behaviour but not sources; skip.
        _skip_if_provider_unavailable(r)
        assert r.status_code == 200
        body = r.json()
        # Assicurati che il documento eliminato NON sia tra le sources
        doc_ids = [s.get("id") for s in body["sources"] if s.get("source") == "document"]
        assert doc_id not in doc_ids

        # Extra: se non c'erano altri documenti, aspettiamo answer "non risulta"/"nessun documento"
        # (ma NON deve essere il messaggio "storico" perché sarà comunque una domanda LLM)

    def test_c2_archived_documents_present_but_flagged(self, client):
        user = _register(client, "archdoc")
        up = _upload(client, user, name=f"vecchio-{TS}.pdf",
                     content=b"%PDF-1.4 old-" + TS.encode(),
                     content_type="application/pdf")
        doc_id = up.json()["document"]["id"]
        a = client.post(f"/api/documents/{doc_id}/archive", headers=h(user))
        assert a.status_code == 200

        r = _ask(client, user, "Ho documenti?")
        _skip_if_provider_unavailable(r)
        assert r.status_code == 200
        body = r.json()
        matches = [s for s in body["sources"] if s.get("id") == doc_id]
        assert matches, "archived document should still be listed as source"
        assert matches[0].get("archived") is True

    def test_c3_ownership_user_a_does_not_see_user_b_docs(self, client):
        user_a = _register(client, "owna")
        user_b = _register(client, "ownb")
        up = _upload(client, user_b, name=f"privato-{TS}.pdf",
                     content=b"%PDF-1.4 private-" + TS.encode(),
                     content_type="application/pdf")
        assert up.status_code == 200
        b_doc_id = up.json()["document"]["id"]

        r = _ask(client, user_a, "Che documenti ho?")
        # user_a è nuovo → nessun dato: ci aspettiamo la risposta storica
        assert r.status_code == 200, r.text
        body = r.json()
        # user_a non deve mai vedere doc id di user_b
        for s in body["sources"]:
            assert s.get("id") != b_doc_id


# =====================================================================
# D) SOURCES CONTRACT
# =====================================================================
class TestD_SourcesContract:
    def test_d1_sources_include_document_shape(self, client):
        user = _register(client, "shape")
        up = _upload(client, user, name=f"shape-{TS}.pdf",
                     content=b"%PDF-1.4 shape-" + TS.encode(),
                     content_type="application/pdf", tags=["ref"])
        assert up.status_code == 200

        r = _ask(client, user, "Che documenti ho?")
        _skip_if_provider_unavailable(r)
        assert r.status_code == 200
        body = r.json()
        doc_sources = [s for s in body["sources"] if s.get("source") == "document"]
        assert doc_sources, "at least one document source expected"
        d0 = doc_sources[0]
        # Shape contract from router:
        for key in ("id", "filename", "mime_type", "tags", "archived", "source", "created_at"):
            assert key in d0, f"missing key '{key}' in document source: {d0}"
        assert d0["source"] == "document"
