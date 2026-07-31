"""Iter21 live smoke test via public EXPO_PUBLIC_BACKEND_URL.

Verifies the deterministic Document Insights extraction end-to-end
against the ingress-exposed URL (not the in-process TestClient).
Skipped automatically if the backend is unreachable.
"""
from __future__ import annotations

import io
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    "https://ora-decision-engine.preview.emergentagent.com",
).rstrip("/")

TS = f"iter21live_{int(time.time())}_{uuid.uuid4().hex[:6]}"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    # Availability probe
    try:
        r = s.get(f"{BASE_URL}/api/", timeout=10)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"backend unreachable at {BASE_URL}: {e}")
    if r.status_code >= 500:
        pytest.skip(f"backend 5xx at {BASE_URL}: {r.status_code}")
    return s


@pytest.fixture(scope="module")
def user(session):
    r = session.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": f"{TS}@ora.app", "password": "Passw0rd!", "name": "Iter21 Live"},
        timeout=20,
    )
    assert r.status_code in (200, 201), r.text
    body = r.json()
    return {"token": body["token"]}


def _headers(u):
    return {"Authorization": f"Bearer {u['token']}"}


def _upload_txt(session, u, name, content):
    files = {"file": (name, io.BytesIO(content.encode()), "text/plain")}
    r = session.post(
        f"{BASE_URL}/api/documents/upload",
        headers=_headers(u),
        files=files,
        timeout=30,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["document"]["id"]


def _digits(s: str) -> str:
    import re
    return re.sub(r"\D", "", s or "")


class TestIter21LiveExtraction:
    def test_ticketdirect_no_false_positives(self, session, user):
        content = (
            "TicketDirect\n"
            "Data: 15/07/2026 ore 20:30\n"
            "TktID: 128492577\n"
            "Numero ordine: 1750329600\n"
            "Timestamp: 2026-07-15T20:30:00\n"
            "Prezzo: €45,50\n"
            "CF: RSSMRA80A01H501U\n"
            "P.IVA emittente: 12345678901\n"
            "Tel supporto: +39 02 12345678\n"
            "Cell: 348 9876543\n"
            "Email: support@ticketdirect.it\n"
        )
        did = _upload_txt(session, user, f"tkt-{TS}.txt", content)
        r = session.get(
            f"{BASE_URL}/api/documents/{did}/insights",
            headers=_headers(user),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        ents = r.json()["entities"]

        # Phones: only labeled + IT mobile
        phones = ents.get("phones") or []
        assert any("12345678" in _digits(p) for p in phones), phones
        assert any("3489876543" in _digits(p) for p in phones), phones
        for forbidden in ("128492577", "1750329600", "12345678901"):
            assert not any(forbidden in _digits(p) for p in phones), (
                f"'{forbidden}' erroneously in phones: {phones}"
            )

        # Tax IDs: only CF alfanumerico + P.IVA labellata
        tax_ids = ents.get("tax_ids") or []
        assert "RSSMRA80A01H501U" in tax_ids, tax_ids
        assert "12345678901" in tax_ids, tax_ids
        for forbidden in ("128492577", "1750329600"):
            assert forbidden not in tax_ids

        # Order IDs
        order_ids = ents.get("order_ids") or []
        assert "128492577" in order_ids, order_ids
        assert "1750329600" in order_ids, order_ids

    def test_bare_11_digits_no_label(self, session, user):
        content = "Sequenza generica: 12345678901\n"
        did = _upload_txt(session, user, f"bare-{TS}.txt", content)
        ents = session.get(
            f"{BASE_URL}/api/documents/{did}/insights",
            headers=_headers(user),
            timeout=20,
        ).json()["entities"]
        assert "12345678901" not in (ents.get("tax_ids") or [])
        assert any("12345678901" in n for n in (ents.get("numbers") or []))

    def test_cf_strict_16_char(self, session, user):
        content = (
            "Codice fiscale non valido: ABCDEF12345\n"
            "Codice fiscale valido: RSSMRA80A01H501U\n"
        )
        did = _upload_txt(session, user, f"cf-{TS}.txt", content)
        tax_ids = session.get(
            f"{BASE_URL}/api/documents/{did}/insights",
            headers=_headers(user),
            timeout=20,
        ).json()["entities"].get("tax_ids") or []
        assert "RSSMRA80A01H501U" in tax_ids
        assert "ABCDEF12345" not in tax_ids

    def test_insights_404_for_unknown_doc(self, session, user):
        r = session.get(
            f"{BASE_URL}/api/documents/nonexistent-doc-id/insights",
            headers=_headers(user),
            timeout=20,
        )
        assert r.status_code == 404
