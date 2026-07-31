"""
Iterazione 21 — Bug fix regression test.

Verifica che dopo il fix del crash "Can't find variable: router" in
app/(tabs)/documenti.tsx (fix puramente FE), gli endpoint backend
usati dalla schermata Document Insights continuino a funzionare
correttamente.

Copertura:
- POST /api/auth/register
- POST /api/documents/upload  (con tag e note)
- GET  /api/documents         (list)
- GET  /api/documents/{id}
- GET  /api/documents/{id}/insights   (con 4 sezioni: summary/entities/content/meta)
- POST /api/documents/{id}/archive + GET insights su archiviato
- POST /api/documents/{id}/restore
- POST /api/memory/ask         (cita il documento caricato)
"""
from __future__ import annotations

import io
import os
import time
import uuid

import pytest
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
if not BASE:
    # backend/.env fallback: legge il valore dal file .env FE
    try:
        with open("/app/frontend/.env") as fh:
            for line in fh:
                if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                    BASE = line.split("=", 1)[1].strip().strip('"')
                    break
    except Exception:
        pass
assert BASE, "EXPO_PUBLIC_BACKEND_URL not configured"
BASE = BASE.rstrip("/")

TS = f"iter21bug_{int(time.time())}_{uuid.uuid4().hex[:6]}"


@pytest.fixture(scope="module")
def user():
    r = requests.post(
        f"{BASE}/api/auth/register",
        json={"email": f"{TS}@ora.app", "password": "Passw0rd!", "name": "Iter21 Bug"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    return {"token": data["token"], "user_id": data["user"]["user_id"]}


def h(user):
    return {"Authorization": f"Bearer {user['token']}"}


# --------- upload helper ---------
def _upload(user, name, content, ct="text/plain", tags=None, notes=None):
    files = {"file": (name, io.BytesIO(content.encode() if isinstance(content, str) else content), ct)}
    data = {}
    if tags:
        data["tags"] = ",".join(tags)
    if notes:
        data["notes"] = notes
    r = requests.post(
        f"{BASE}/api/documents/upload", headers=h(user), files=files, data=data, timeout=30,
    )
    return r


class TestDocumentsAPI:
    def test_a_upload_ticket(self, user):
        content = (
            "BIGLIETTO CONCERTO\n"
            "OLLY LIVE 2026\n"
            "Rock in Roma\n"
            "30 giugno 2026 ore 21:45\n"
            "Numero ordine 123456\n"
            "Prezzo €55.00\n"
        )
        r = _upload(user, f"biglietto-{TS}.txt", content, tags=["concerto", "olly"], notes="test iter21")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["duplicate"] is False
        assert body["document"]["filename"].endswith(".txt")
        assert "concerto" in body["document"]["tags"]
        pytest.doc_id = body["document"]["id"]

    def test_b_list_contains_doc(self, user):
        r = requests.get(f"{BASE}/api/documents?limit=200", headers=h(user), timeout=15)
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()["items"]]
        assert pytest.doc_id in ids

    def test_c_get_doc(self, user):
        r = requests.get(f"{BASE}/api/documents/{pytest.doc_id}", headers=h(user), timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == pytest.doc_id
        assert "_id" not in body  # ObjectId must be excluded

    def test_d_insights_shape(self, user):
        r = requests.get(f"{BASE}/api/documents/{pytest.doc_id}/insights", headers=h(user), timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        # 4 tab equivalenti presenti nella UI: info(summary+history)/insights(entities)/content/meta(extraction+technical_metadata)
        for key in ("summary", "entities", "content", "extraction", "technical_metadata", "history"):
            assert key in body, f"missing key {key}"
        # tipo ticket rilevato
        assert body["type_key"] in ("ticket", "generic")
        # entities parsed
        ents = body["entities"]
        assert isinstance(ents, dict)
        # Numeri o date presenti
        assert any(k in ents for k in ("dates", "times", "numbers"))
        # content non vuoto
        assert body["content"]["length"] > 20

    def test_e_archive_then_insights_no_crash(self, user):
        r = requests.post(f"{BASE}/api/documents/{pytest.doc_id}/archive", headers=h(user), timeout=15)
        assert r.status_code == 200
        assert r.json()["archived"] is True
        # apri insights su archived
        r2 = requests.get(f"{BASE}/api/documents/{pytest.doc_id}/insights", headers=h(user), timeout=15)
        assert r2.status_code == 200
        assert r2.json()["history"]["archived"] is True

    def test_f_restore(self, user):
        r = requests.post(f"{BASE}/api/documents/{pytest.doc_id}/restore", headers=h(user), timeout=15)
        assert r.status_code == 200
        assert r.json()["archived"] is False

    def test_g_upload_second_doc(self, user):
        r = _upload(user, f"nota-{TS}.txt", "Nota veloce iter21 fix router", tags=["nota"])
        assert r.status_code == 200
        pytest.doc_id_2 = r.json()["document"]["id"]

    def test_h_open_multiple_in_sequence(self, user):
        # simula avanti/indietro tra due dettagli
        for _ in range(2):
            for did in (pytest.doc_id, pytest.doc_id_2):
                r = requests.get(f"{BASE}/api/documents/{did}/insights", headers=h(user), timeout=15)
                assert r.status_code == 200


class TestMemoryAskRegression:
    def test_ask_cites_document(self, user):
        # documento già caricato dallo scenario precedente
        r = requests.post(
            f"{BASE}/api/memory/ask",
            headers={**h(user), "Content-Type": "application/json"},
            json={"question": "Ho caricato qualche documento?"},
            timeout=60,
        )
        # Se LLM 502 accettiamo come non-fatale (agent note)
        if r.status_code in (502, 503, 504):
            pytest.skip(f"LLM upstream {r.status_code} — non-fatale")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "answer" in body
        sources = body.get("sources", [])
        # almeno una source di tipo document per il file uploadato
        doc_sources = [s for s in sources if s.get("source") == "document"]
        assert doc_sources, f"nessuna doc source in {sources}"
        assert any(pytest.doc_id == s.get("id") or pytest.doc_id_2 == s.get("id") for s in doc_sources)
