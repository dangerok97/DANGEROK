"""Iter22 live smoke — verifies Document Understanding over public ingress.

Uploads ticket + invoice + contract text and asserts:
- classification.type_key correct
- resolved_fields[*] confidence >= 60 and 7 required keys
- technical_identifiers.flat contains TktID/UUID
- Iter21 legacy keys still present
"""
from __future__ import annotations

import io
import os
import time
import uuid

import pytest
import requests

BASE = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
    or ""
)
if not BASE:
    with open("/app/frontend/.env") as fh:
        for line in fh:
            if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                BASE = line.split("=", 1)[1].strip().strip('"')
                break
assert BASE, "EXPO_PUBLIC_BACKEND_URL not configured"
BASE = BASE.rstrip("/")

TS = f"iter22smoke_{int(time.time())}_{uuid.uuid4().hex[:6]}"

TICKET_TEXT = (
    "BIGLIETTO CONCERTO\n"
    "OLLY LIVE 2026\n"
    "Data evento: 30 giugno 2026\n"
    "Ora inizio: 21:45\n"
    "Apertura porte: 17:00\n"
    "Numero ordine: 1284925775\n"
    "TktID: 128492577\n"
    "Intestatario: Mario Rossi\n"
    "Posto: Tribuna Rossa Fila 3\n"
    "Prezzo: 55,00 EUR\n"
)
INVOICE_TEXT = (
    "FATTURA n. 2026-100\n"
    "Data emissione: 15/03/2026\n"
    "Data scadenza: 15/04/2026\n"
    "Cedente prestatore: ACME SRL\n"
    "P.IVA: 12345678901\n"
    "Imponibile: EUR 100,00\n"
    "IVA 22%: EUR 22,00\n"
    "Totale documento: EUR 122,00\n"
    "IBAN: IT60X0542811101000000123456\n"
)
CONTRACT_TEXT = (
    "CONTRATTO DI COLLABORAZIONE\n\n"
    "Premesso che le parti intendono regolare i loro rapporti,\n"
    "il presente contratto viene stipulato tra Mario Rossi e Anna Bianchi.\n\n"
    "Oggetto: consulenza informatica.\n"
    "Decorrenza: 01/09/2026\n"
    "Scadenza: 31/08/2027\n"
    "Data firma: 15/08/2026\n"
    "Articolo 1 - Descrizione del servizio\n"
)

REQUIRED_KEYS = {
    "field_key", "label", "value", "confidence",
    "source_snippet", "source_page", "resolver_rule",
}
LEGACY_KEYS = {
    "summary", "entities", "extraction",
    "technical_metadata", "history", "content",
}


@pytest.fixture(scope="module")
def user():
    r = requests.post(
        f"{BASE}/api/auth/register",
        json={"email": f"{TS}@ora.app", "password": "Passw0rd!", "name": "Iter22 Smoke"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _h(user):
    return {"Authorization": f"Bearer {user['token']}"}


def _upload(user, name, content):
    files = {"file": (name, io.BytesIO(content.encode()), "text/plain")}
    r = requests.post(
        f"{BASE}/api/documents/upload", headers=_h(user), files=files, timeout=30,
    )
    assert r.status_code == 200, r.text
    return r.json()["document"]["id"]


def _insights(user, did):
    r = requests.get(
        f"{BASE}/api/documents/{did}/insights", headers=_h(user), timeout=30,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _check_common(ins, expected_type):
    # New Iter22 keys
    assert ins["classification"]["type_key"] == expected_type, (
        f"classification={ins['classification']}"
    )
    assert ins["type_key"] == expected_type
    assert ins.get("schema_used") is not None or expected_type == "generic"
    # resolved_fields shape
    for f in ins["resolved_fields"]:
        assert f["confidence"] >= 60
        assert REQUIRED_KEYS.issubset(f.keys()), f
        assert len(f.get("source_snippet", "")) <= 170
    # Legacy Iter21 shape preserved
    for k in LEGACY_KEYS:
        assert k in ins, f"legacy key missing: {k}"
    assert isinstance(ins["summary"]["fields"], list)
    assert isinstance(ins["entities"], dict)


def test_ticket_smoke(user):
    did = _upload(user, f"ticket-{TS}.txt", TICKET_TEXT)
    ins = _insights(user, did)
    _check_common(ins, "ticket")
    rf = {f["field_key"]: f for f in ins["resolved_fields"]}
    assert "event_date" in rf
    assert "30 giugno 2026" in rf["event_date"]["value"]
    assert rf["event_time"]["value"] == "21:45"
    assert rf["doors_open"]["value"] == "17:00"
    # TktID must land in technical_identifiers.flat, NOT in order_ids
    tech = ins["technical_identifiers"]["flat"]
    assert "128492577" in tech, tech
    assert "128492577" not in ins["entities"].get("order_ids", [])
    # Posto Unico / Tribuna Rossa must NOT be persons
    persons = ins["entities"].get("persons", [])
    for forbidden in ("Tribuna Rossa", "Posto Unico", "Platea Sinistra"):
        assert forbidden not in persons


def test_invoice_smoke(user):
    did = _upload(user, f"invoice-{TS}.txt", INVOICE_TEXT)
    ins = _insights(user, did)
    _check_common(ins, "invoice")
    rf = {f["field_key"]: f for f in ins["resolved_fields"]}
    assert rf["invoice_number"]["value"] == "2026-100"
    assert "15/03/2026" in rf["issue_date"]["value"]
    assert "15/04/2026" in rf["due_date"]["value"]
    assert rf["iban"]["value"] == "IT60X0542811101000000123456"
    assert rf["tax_id"]["value"] == "12345678901"


def test_contract_smoke(user):
    did = _upload(user, f"contract-{TS}.txt", CONTRACT_TEXT)
    ins = _insights(user, did)
    _check_common(ins, "contract")
    rf = {f["field_key"]: f for f in ins["resolved_fields"]}
    assert rf["effective_date"]["value"] == "01/09/2026"
    assert rf["expiry_date"]["value"] == "31/08/2027"
    assert rf["signature_date"]["value"] == "15/08/2026"


def test_env_thresholds_module_constants():
    # Verify env-configurable thresholds are wired at module import.
    import sys
    sys.path.insert(0, "/app/backend")
    from documents import field_resolver
    assert field_resolver.VISIBLE_THRESHOLD == int(
        os.environ.get("DOCUMENT_INSIGHTS_CONFIDENCE_THRESHOLD", "60")
    )
    assert field_resolver.HIDDEN_LOWER == int(
        os.environ.get("DOCUMENT_INSIGHTS_HIDDEN_LOWER_THRESHOLD", "40")
    )
