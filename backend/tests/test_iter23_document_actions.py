"""Iterazione 23 — Document Actions.

Backend-level checks garantendo che il payload di /api/documents/{id}/insights
sia strutturato correttamente per la barra "Azioni disponibili" del frontend:

  1. ``classification.threshold_visible`` esposto (usato dalla UI per filtrare
     resolved_fields sotto soglia).
  2. Nessun resolved_field ha confidence < threshold_visible.
  3. hidden_fields mai visibili nella barra (verifica strutturale).
  4. technical_identifiers è sempre presente ma separato.
  5. Retrocompat piena di Iter19/20/21/22.

La logica delle azioni è puramente frontend (src/utils/document_actions.ts)
e verrà validata via Playwright + evidenza testuale nella session di test.
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

TS = f"iter23_{int(time.time())}_{uuid.uuid4().hex[:6]}"


@pytest.fixture(scope="module")
def client(shared_client):
    return shared_client


@pytest.fixture(scope="module")
def user(client):
    r = client.post("/api/auth/register", json={
        "email": f"{TS}@ora.app", "password": "Passw0rd!", "name": "Iter23 User",
    })
    return {"token": r.json()["token"]}


def h(u):
    return {"Authorization": f"Bearer {u['token']}"}


def _upload(client, user, name, content):
    files = {"file": (name, io.BytesIO(content.encode()), "text/plain")}
    r = client.post("/api/documents/upload", headers=h(user), files=files)
    assert r.status_code == 200
    return r.json()["document"]["id"]


TICKET = (
    "BIGLIETTO CONCERTO\n"
    "OLLY LIVE 2026\n"
    "Data evento: 30 giugno 2026\n"
    "Ora inizio: 21:45\n"
    "Apertura porte: 17:00\n"
    "Luogo: Ippodromo Capannelle\n"
    "Numero ordine: 1284925775\n"
    "TktID: 128492577\n"
    "Prezzo: 55,00 €\n"
)
INVOICE = (
    "FATTURA n. 2026-100\n"
    "Data emissione: 15/03/2026\n"
    "Data scadenza: 15/04/2026\n"
    "Cedente prestatore: ACME SRL\n"
    "P.IVA: 12345678901\n"
    "Totale documento: € 122,00\n"
    "IBAN: IT60X0542811101000000123456\n"
    "Email: fatture@acme.it\n"
    "Sito: https://acme.it\n"
    "Tel: +39 02 12345678\n"
)


class TestActionsPayloadContract:
    def test_threshold_exposed_in_classification(self, client, user):
        did = _upload(client, user, f"t-{TS}.txt", TICKET)
        r = client.get(f"/api/documents/{did}/insights", headers=h(user))
        assert r.status_code == 200
        body = r.json()
        cls = body.get("classification") or {}
        assert "threshold_visible" in cls
        assert cls["threshold_visible"] >= 40
        assert "threshold_hidden" in cls
        assert cls["threshold_hidden"] <= cls["threshold_visible"]

    def test_all_resolved_fields_above_threshold(self, client, user):
        did = _upload(client, user, f"inv-{TS}.txt", INVOICE)
        body = client.get(f"/api/documents/{did}/insights", headers=h(user)).json()
        threshold = body["classification"]["threshold_visible"]
        for f in body["resolved_fields"]:
            assert f["confidence"] >= threshold, f
            # Iter22 field contract required for actions
            for k in ("field_key", "label", "value",
                      "confidence", "source_snippet", "resolver_rule"):
                assert k in f, f"resolved_field missing {k}"

    def test_hidden_fields_are_below_threshold(self, client, user):
        did = _upload(client, user, f"h-{TS}.txt", TICKET)
        body = client.get(f"/api/documents/{did}/insights", headers=h(user)).json()
        threshold = body["classification"]["threshold_visible"]
        for f in body.get("hidden_fields", []):
            assert f["confidence"] < threshold

    def test_technical_ids_separate_from_resolved_fields(self, client, user):
        did = _upload(client, user, f"tk-{TS}.txt", TICKET)
        body = client.get(f"/api/documents/{did}/insights", headers=h(user)).json()
        tech = body["technical_identifiers"]["flat"]
        assert "128492577" in tech, tech
        # TktID must never leak into a resolved_field
        resolved_values = {f["value"] for f in body["resolved_fields"]}
        assert "128492577" not in resolved_values

    def test_invoice_has_iban_resolved_for_copy_action(self, client, user):
        did = _upload(client, user, f"ib-{TS}.txt", INVOICE)
        body = client.get(f"/api/documents/{did}/insights", headers=h(user)).json()
        rmap = {f["field_key"]: f for f in body["resolved_fields"]}
        assert "iban" in rmap
        assert rmap["iban"]["value"] == "IT60X0542811101000000123456"

    def test_iter22_retrocompat(self, client, user):
        """Iterazione 23 non introduce NUOVE api. Payload identico a Iter22."""
        did = _upload(client, user, f"rc-{TS}.txt", TICKET)
        body = client.get(f"/api/documents/{did}/insights", headers=h(user)).json()
        for k in (
            "id", "filename", "type_key", "type_label",
            "classification", "schema_used", "resolved_fields",
            "hidden_fields", "technical_identifiers",
            "summary", "entities", "extraction",
            "technical_metadata", "history", "content",
        ):
            assert k in body, k

    def test_no_new_backend_side_effects(self, client, user):
        """Iter23 non deve toccare estrattore, resolver, classifier."""
        # Ci basiamo su un doc TicketDirect già coperto in Iter22.
        content = (
            "TicketDirect\n"
            "Data: 15/07/2026 ore 20:30\n"
            "TktID: 128492577\n"
            "Numero ordine: 1750329600\n"
            "Prezzo: €45,50\n"
            "CF: RSSMRA80A01H501U\n"
            "P.IVA emittente: 12345678901\n"
            "Tel: +39 02 12345678\n"
            "Email: support@ticketdirect.it\n"
        )
        did = _upload(client, user, f"td-{TS}.txt", content)
        body = client.get(f"/api/documents/{did}/insights", headers=h(user)).json()
        # Le stesse garanzie Iter22 devono continuare a valere.
        assert "128492577" in body["technical_identifiers"]["flat"]
        assert "1750329600" in body["entities"].get("order_ids", [])
        assert "RSSMRA80A01H501U" in body["entities"].get("tax_ids", [])
        assert "12345678901" in body["entities"].get("tax_ids", [])
