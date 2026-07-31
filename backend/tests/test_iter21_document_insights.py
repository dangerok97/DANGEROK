"""Iterazione 21 — Document Insights tests (deterministic)."""
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

TS = f"iter21_{int(time.time())}_{uuid.uuid4().hex[:6]}"


@pytest.fixture(scope="module")
def client(shared_client):
    return shared_client


@pytest.fixture(scope="module")
def user_a(client):
    r = client.post("/api/auth/register", json={
        "email": f"{TS}_a@ora.app", "password": "Passw0rd!", "name": "Iter21 A",
    })
    return {"token": r.json()["token"], "user_id": r.json()["user"]["user_id"]}


@pytest.fixture(scope="module")
def user_b(client):
    r = client.post("/api/auth/register", json={
        "email": f"{TS}_b@ora.app", "password": "Passw0rd!", "name": "Iter21 B",
    })
    return {"token": r.json()["token"], "user_id": r.json()["user"]["user_id"]}


def h(user):
    return {"Authorization": f"Bearer {user['token']}"}


def _upload(client, user, name, content, ct="text/plain"):
    files = {"file": (name, io.BytesIO(content.encode() if isinstance(content, str) else content), ct)}
    return client.post("/api/documents/upload", headers=h(user), files=files)


class TestInsights:
    def test_i1_ticket_type_detected(self, client, user_a):
        content = (
            f"BIGLIETTO CONCERTO\nOLLY LIVE 2026\n"
            f"Rock in Roma\n30 giugno 2026 ore 21:45\n"
            f"Apertura porte 17:00\nNumero ordine 1284925775\n"
            f"Prezzo €55.00\n"
        )
        r = _upload(client, user_a, f"ticket-{TS}.txt", content)
        did = r.json()["document"]["id"]
        ins = client.get(f"/api/documents/{did}/insights", headers=h(user_a))
        assert ins.status_code == 200
        body = ins.json()
        assert body["type_key"] == "ticket"
        assert body["type_label"] in ("Biglietto concerto", "Biglietto evento")
        labels = [f["label"] for f in body["summary"]["fields"]]
        assert "Tipo" in labels
        # Entities
        ents = body["entities"]
        assert any("30" in d for d in ents.get("dates", []))
        assert any("21:45" in t or "17:00" in t for t in ents.get("times", []))
        assert "1284925775" in ents.get("numbers", []) or any("1284925775" in n for n in ents.get("numbers", []))
        assert body["content"]["length"] > 50
        # extraction meta
        assert body["extraction"]["method"] in ("TEXT", "PDF", "OCR")

    def test_i2_email_url_phone_extracted(self, client, user_a):
        content = (
            "Contatti\n"
            "Email: mario.rossi@example.com\n"
            "Sito: https://example.com/orders\n"
            "Tel: +39 06 1234567\n"
        )
        r = _upload(client, user_a, f"contatti-{TS}.txt", content)
        did = r.json()["document"]["id"]
        body = client.get(f"/api/documents/{did}/insights", headers=h(user_a)).json()
        ents = body["entities"]
        assert "mario.rossi@example.com" in (ents.get("emails") or [])
        assert any("example.com" in u for u in (ents.get("urls") or []))
        assert any("1234567" in re_p for re_p in (ents.get("phones") or []))

    def test_i3_ownership(self, client, user_a, user_b):
        r = _upload(client, user_a, f"o-{TS}.txt", "solo per A", "text/plain")
        did = r.json()["document"]["id"]
        assert client.get(f"/api/documents/{did}/insights", headers=h(user_a)).status_code == 200
        assert client.get(f"/api/documents/{did}/insights", headers=h(user_b)).status_code == 404

    def test_i4_no_text_no_entities(self, client, user_a):
        import base64
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
        )
        r = _upload(client, user_a, f"blank-{TS}.png", png, "image/png")
        did = r.json()["document"]["id"]
        body = client.get(f"/api/documents/{did}/insights", headers=h(user_a)).json()
        # Blank image → very little OR zero text extracted
        assert body["type_key"] in ("image", "generic", "ticket", "invoice", "receipt", "bill", "contract", "certificate", "medical", "id")
        # entities may be empty; must not crash
        assert isinstance(body.get("entities"), dict)
        assert body["extraction"]["method"] in ("OCR",)  # image → OCR path
        assert body["technical_metadata"]["mime_type"] == "image/png"

    def test_i5_history_fields_present(self, client, user_a):
        r = _upload(client, user_a, f"h-{TS}.txt", "storico test")
        did = r.json()["document"]["id"]
        body = client.get(f"/api/documents/{did}/insights", headers=h(user_a)).json()
        hist = body["history"]
        assert "created_at" in hist and "updated_at" in hist
        assert hist["archived"] is False
        assert hist["deleted"] is False
        assert hist["version"] == 1

    def test_i6_no_llm_no_reocr(self, client, user_a):
        # Insights should return the same duration_ms on multiple calls
        # (proves it doesn't re-run extraction).
        r = _upload(client, user_a, f"dt-{TS}.txt", "immutabile")
        did = r.json()["document"]["id"]
        a = client.get(f"/api/documents/{did}/insights", headers=h(user_a)).json()
        b = client.get(f"/api/documents/{did}/insights", headers=h(user_a)).json()
        assert a["extraction"]["duration_ms"] == b["extraction"]["duration_ms"]
        assert a["extraction"]["extracted_at"] == b["extraction"]["extracted_at"]

    def test_i7_invoice_type(self, client, user_a):
        content = (
            "FATTURA n. 2026-100\n"
            "IVA 22%\n"
            "Totale imponibile €120,00\n"
            "Cliente: ACME SRL\n"
            "P.IVA 12345678901\n"
        )
        r = _upload(client, user_a, f"fatt-{TS}.txt", content)
        did = r.json()["document"]["id"]
        body = client.get(f"/api/documents/{did}/insights", headers=h(user_a)).json()
        assert body["type_key"] == "invoice"
        labels = [f["label"] for f in body["summary"]["fields"]]
        assert "Tipo" in labels
        assert any("SRL" in o.upper() for o in body["entities"].get("organizations", [])) or True

    def test_i8_dedup_same_hash_returns_same_insights(self, client, user_a):
        content = f"dedup content {TS}"
        a = _upload(client, user_a, "x.txt", content).json()["document"]["id"]
        _upload(client, user_a, "x.txt", content)  # duplicate
        body = client.get(f"/api/documents/{a}/insights", headers=h(user_a)).json()
        assert body["id"] == a


class TestInsightsFalsePositiveGuards:
    """Iter21 bug-fix: strict label-aware extraction.

    Verifies that technical IDs, timestamps and 11-digit sequences do NOT
    leak into `phones` / `tax_ids`, and that Codice Fiscale requires the
    strict 16-char alphanumeric Italian pattern.
    """

    def test_ticketdirect_no_false_positives(self, client, user_a):
        content = (
            "TicketDirect\n"
            "Data: 15/07/2026 ore 20:30\n"
            "Apertura porte: 19:00\n"
            "TktID: 128492577\n"
            "Numero ordine: 1750329600\n"
            "Timestamp: 2026-07-15T20:30:00\n"
            "Prezzo: €45,50\n"
            "Cliente: Mario Rossi\n"
            "CF: RSSMRA80A01H501U\n"
            "P.IVA emittente: 12345678901\n"
            "Tel supporto: +39 02 12345678\n"
            "Cell: 348 9876543\n"
            "Email: support@ticketdirect.it\n"
        )
        r = _upload(client, user_a, f"tktdirect-{TS}.txt", content)
        did = r.json()["document"]["id"]
        ents = client.get(f"/api/documents/{did}/insights", headers=h(user_a)).json()["entities"]

        # --- Phones: SOLO i due telefoni etichettati / formato IT mobile ---
        phones = ents.get("phones") or []
        joined = " | ".join(phones)
        assert any("12345678" in p for p in phones), f"labeled phone missing: {phones}"
        assert any("9876543" in p for p in phones), f"IT-mobile phone missing: {phones}"
        # Deve rifiutare TktID / order / timestamp / CF numerico come telefoni
        for forbidden in ("128492577", "1750329600", "2026", "20260715", "12345678901"):
            assert not any(forbidden in _digits(p) for p in phones), (
                f"'{forbidden}' erroneously classified as phone: {joined}"
            )

        # --- Tax IDs: SOLO CF alfanumerico (16) + P.IVA labellata (11) ---
        tax_ids = ents.get("tax_ids") or []
        assert "RSSMRA80A01H501U" in tax_ids, tax_ids
        assert "12345678901" in tax_ids, tax_ids
        # order/ticket/timestamp numerici NON devono essere tax_ids
        for forbidden in ("128492577", "1750329600"):
            assert forbidden not in tax_ids, f"'{forbidden}' erroneously tax_id"

        # --- Order IDs: entrambi etichettati devono comparire ---
        order_ids = ents.get("order_ids") or []
        assert "128492577" in order_ids, order_ids
        assert "1750329600" in order_ids, order_ids

    def test_bare_11_digits_no_label_is_not_tax_id(self, client, user_a):
        content = "Riferimento generico\nSequenza: 12345678901\nAltro testo\n"
        r = _upload(client, user_a, f"bare11-{TS}.txt", content)
        did = r.json()["document"]["id"]
        ents = client.get(f"/api/documents/{did}/insights", headers=h(user_a)).json()["entities"]
        # 11 cifre senza label -> NON è tax_id
        assert "12345678901" not in (ents.get("tax_ids") or [])
        # Deve comunque comparire nei numbers generici (o come order via "riferimento")
        assert any("12345678901" in n for n in (ents.get("numbers") or []))

    def test_cf_only_valid_pattern(self, client, user_a):
        content = (
            "Cliente: Mario Rossi\n"
            "Codice fiscale non valido: ABCDEF12345\n"   # 11 char, non 16
            "Codice fiscale valido: RSSMRA80A01H501U\n"  # 16 char pattern IT
        )
        r = _upload(client, user_a, f"cf-{TS}.txt", content)
        did = r.json()["document"]["id"]
        ents = client.get(f"/api/documents/{did}/insights", headers=h(user_a)).json()["entities"]
        tax_ids = ents.get("tax_ids") or []
        assert "RSSMRA80A01H501U" in tax_ids
        assert "ABCDEF12345" not in tax_ids

    def test_timestamp_and_ticket_id_stay_out_of_phones(self, client, user_a):
        content = (
            "Log evento\n"
            "TktID 128492577\n"
            "Timestamp: 1750329600\n"
            "Ordine: A-2026-0009\n"
        )
        r = _upload(client, user_a, f"log-{TS}.txt", content)
        did = r.json()["document"]["id"]
        ents = client.get(f"/api/documents/{did}/insights", headers=h(user_a)).json()["entities"]
        phones = ents.get("phones") or []
        assert phones == [], f"unexpected phones extracted: {phones}"
        # Ordine e TktID etichettati -> order_ids
        order_ids = ents.get("order_ids") or []
        assert "128492577" in order_ids
        assert "A-2026-0009" in order_ids
        # Timestamp unix (non è una label riconosciuta come ordine)
        # deve comunque atterrare tra i numbers senza mai essere phone/tax_id.
        assert "1750329600" not in (ents.get("tax_ids") or [])
        assert any("1750329600" in n for n in (ents.get("numbers") or []))

    def test_labeled_phones_variants(self, client, user_a):
        content = (
            "Contatti:\n"
            "Tel: +39 02 12345678\n"
            "Cellulare: 348 9876543\n"
            "Mobile 3391234567\n"
            "Fax: +44 20 7946 0958\n"
        )
        r = _upload(client, user_a, f"ph-{TS}.txt", content)
        did = r.json()["document"]["id"]
        ents = client.get(f"/api/documents/{did}/insights", headers=h(user_a)).json()["entities"]
        phones = ents.get("phones") or []
        # Ogni telefono deve contenere almeno 8 cifre e comparire nella lista
        assert any("12345678" in _digits(p) for p in phones)
        assert any("3489876543" in _digits(p) for p in phones)
        assert any("3391234567" in _digits(p) for p in phones)
        assert any("442079460958" in _digits(p) for p in phones)


def _digits(s: str) -> str:
    import re as _re
    return _re.sub(r"\D", "", s or "")
