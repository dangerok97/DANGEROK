"""Iterazione 22 — Document Understanding Engine tests.

Fixture sintetiche italiane realistiche (no dati personali reali).
Verifica classificazione + schema resolution + confidence + edge cases +
zero regressione con iterazioni 19/20/21.
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

from fastapi.testclient import TestClient  # noqa: E402
import server  # noqa: E402

TS = f"iter22_{int(time.time())}_{uuid.uuid4().hex[:6]}"


@pytest.fixture(scope="module")
def client(shared_client):
    return shared_client


@pytest.fixture(scope="module")
def user(client):
    r = client.post("/api/auth/register", json={
        "email": f"{TS}@ora.app", "password": "Passw0rd!", "name": "Iter22 User",
    })
    return {"token": r.json()["token"], "user_id": r.json()["user"]["user_id"]}


def h(user):
    return {"Authorization": f"Bearer {user['token']}"}


def _upload(client, user, name, content):
    files = {"file": (name, io.BytesIO(content.encode()), "text/plain")}
    r = client.post("/api/documents/upload", headers=h(user), files=files)
    assert r.status_code == 200, r.text
    return r.json()["document"]["id"]


def _insights(client, user, did):
    r = client.get(f"/api/documents/{did}/insights", headers=h(user))
    assert r.status_code == 200, r.text
    return r.json()


def _resolved_map(ins):
    return {f["field_key"]: f for f in ins.get("resolved_fields", [])}


# ---------------------------------------------------------------------
# Fixture sintetiche
# ---------------------------------------------------------------------
TICKET_TEXT = (
    "BIGLIETTO CONCERTO\n"
    "OLLY LIVE 2026\n"
    "Rock in Roma\n"
    "Data evento: 30 giugno 2026\n"
    "Ora inizio: 21:45\n"
    "Apertura porte: 17:00\n"
    "Numero ordine: 1284925775\n"
    "Numero biglietto: 998877\n"
    "TktID: 128492577\n"
    "Intestatario: Mario Rossi\n"
    "Posto: Tribuna Rossa Fila 3\n"
    "Prezzo: 55,00 €\n"
)

INVOICE_TEXT = (
    "FATTURA n. 2026-100\n"
    "Data emissione: 15/03/2026\n"
    "Data scadenza: 15/04/2026\n"
    "Cedente prestatore: ACME SRL\n"
    "Cessionario committente: BETA SPA\n"
    "P.IVA: 12345678901\n"
    "Imponibile: € 100,00\n"
    "IVA 22%: € 22,00\n"
    "Totale documento: € 122,00\n"
    "IBAN: IT60X0542811101000000123456\n"
)

RECEIPT_TEXT = (
    "SCONTRINO FISCALE\n"
    "Esercente: BAR DEL CORSO\n"
    "Documento commerciale n. 0042\n"
    "Data: 12/05/2026\n"
    "Totale complessivo: € 8,50\n"
)

CONTRACT_TEXT = (
    "CONTRATTO DI COLLABORAZIONE\n\n"
    "Premesso che le parti intendono regolare i loro rapporti,\n"
    "il presente contratto viene stipulato tra Mario Rossi e Anna Bianchi.\n\n"
    "Oggetto: consulenza informatica.\n"
    "Decorrenza: 01/09/2026\n"
    "Scadenza: 31/08/2027\n"
    "Data firma: 15/08/2026\n"
    "Articolo 1 — Descrizione del servizio\n"
)

BILL_TEXT = (
    "BOLLETTA ENERGIA ELETTRICA\n"
    "Fornitore: LUCE SPA\n"
    "Cliente: Mario Rossi\n"
    "POD: IT001E12345678\n"
    "Periodo: 01/03/2026 - 30/04/2026\n"
    "Consumo: 250 kWh\n"
    "Importo da pagare: € 75,40\n"
    "Scadenza pagamento: 25/05/2026\n"
)

MEDICAL_TEXT = (
    "REFERTO ANALISI CLINICHE\n"
    "Paziente: Mario Rossi\n"
    "Data referto: 10/04/2026\n"
    "Esame: emocromo completo\n"
    "Diagnosi: valori nella norma.\n"
    "Refertante: Dott. Giovanni Verdi\n"
)

ID_CARD_TEXT = (
    "REPUBBLICA ITALIANA\n"
    "CARTA D'IDENTITA'\n"
    "COMUNE DI ROMA\n"
    "Cognome: ROSSI\n"
    "Nome: MARIO\n"
    "Data di nascita: 15/06/1985\n"
    "Luogo di nascita: Roma\n"
    "Statura: 180\n"
    "Numero documento: CA1234567\n"
    "Data rilascio: 20/01/2020\n"
    "Data scadenza: 20/01/2030\n"
)

PASSPORT_TEXT = (
    "PASSPORT / PASSAPORTO\n"
    "Type/Tipo: P\n"
    "Nationality/Nazionalità: ITA\n"
    "Surname/Cognome: ROSSI\n"
    "Given names/Nome: MARIO\n"
    "Date of birth/Data di nascita: 15/06/1985\n"
    "Passport No/N° Passaporto: YA1234567\n"
    "Date of issue/Data rilascio: 12/03/2022\n"
    "Date of expiry/Data scadenza: 11/03/2032\n"
)

CV_TEXT = (
    "CURRICULUM VITAE\n"
    "Nome: Mario Rossi\n"
    "Email: mario.rossi@example.com\n"
    "Tel: +39 348 1234567\n"
    "Data di nascita: 15/06/1985\n"
    "Città: Roma\n\n"
    "ESPERIENZA LAVORATIVA\n"
    "2020-oggi — Senior Developer @ ACME\n\n"
    "ISTRUZIONE E FORMAZIONE\n"
    "2005-2010 — Laurea in Informatica\n\n"
    "COMPETENZE\n"
    "Python, TypeScript, React Native.\n"
)

CERTIFICATE_TEXT = (
    "CERTIFICATO DI FREQUENZA\n"
    "Si certifica che il Sig. Mario Rossi ha frequentato il corso.\n"
    "Data emissione: 10/06/2026\n"
    "Ente emittente: Ordine degli Ingegneri\n"
)

UNKNOWN_TEXT = "Nota sparsa senza label né struttura definita, giusto un appunto."


# ---------------------------------------------------------------------
# Classification tests
# ---------------------------------------------------------------------
class TestClassification:
    @pytest.mark.parametrize("content,expected_key", [
        (TICKET_TEXT, "ticket"),
        (INVOICE_TEXT, "invoice"),
        (RECEIPT_TEXT, "receipt"),
        (CONTRACT_TEXT, "contract"),
        (BILL_TEXT, "bill"),
        (MEDICAL_TEXT, "medical"),
        (ID_CARD_TEXT, "id_card"),
        (PASSPORT_TEXT, "passport"),
        (CV_TEXT, "cv"),
        (CERTIFICATE_TEXT, "certificate"),
    ])
    def test_type_key_correct(self, client, user, content, expected_key):
        did = _upload(client, user, f"cls-{expected_key}-{TS}.txt", content)
        ins = _insights(client, user, did)
        assert ins["classification"]["type_key"] == expected_key, (
            f"expected {expected_key}, got {ins['classification']['type_key']} "
            f"scores={ins['classification'].get('scores')}"
        )
        assert ins["type_key"] == expected_key
        assert ins["schema_used"] is not None
        assert ins["schema_used"]["type_key"] == expected_key

    def test_unknown_falls_back_to_generic(self, client, user):
        did = _upload(client, user, f"unk-{TS}.txt", UNKNOWN_TEXT)
        ins = _insights(client, user, did)
        assert ins["classification"]["type_key"] == "generic"
        assert ins["type_key"] == "generic"
        # schema_used è "generic" (esiste ma senza fields)
        assert ins["schema_used"] is None or ins["schema_used"]["type_key"] == "generic"


# ---------------------------------------------------------------------
# Resolved fields — per-type
# ---------------------------------------------------------------------
class TestResolvedFields:
    def test_ticket_resolved_fields(self, client, user):
        did = _upload(client, user, f"tkt-{TS}.txt", TICKET_TEXT)
        ins = _insights(client, user, did)
        rf = _resolved_map(ins)
        # Data evento vince su data ordine (context bias).
        assert "event_date" in rf
        assert "30 giugno 2026" in rf["event_date"]["value"]
        # Ore separate correttamente
        assert rf["event_time"]["value"] == "21:45"
        assert rf["doors_open"]["value"] == "17:00"
        # Numeri
        assert rf["order_number"]["value"] == "1284925775"
        # ticket_number viene dal label "Numero biglietto:"
        assert "ticket_number" in rf
        assert rf["ticket_number"]["value"] == "998877"
        # Ogni campo ha confidence ≥ 60
        for f in ins["resolved_fields"]:
            assert f["confidence"] >= 60
            # Ogni campo include chiavi obbligatorie
            for req in ("field_key", "label", "value", "confidence",
                        "source_snippet", "resolver_rule"):
                assert req in f

    def test_invoice_resolved_fields(self, client, user):
        did = _upload(client, user, f"fatt-{TS}.txt", INVOICE_TEXT)
        ins = _insights(client, user, did)
        rf = _resolved_map(ins)
        assert rf["invoice_number"]["value"] == "2026-100"
        assert "15/03/2026" in rf["issue_date"]["value"]
        assert "15/04/2026" in rf["due_date"]["value"]
        assert "100" in rf["subtotal"]["value"]
        assert "122" in rf["total"]["value"]
        assert rf["iban"]["value"] == "IT60X0542811101000000123456"
        assert rf["tax_id"]["value"] == "12345678901"

    def test_contract_dates_distinct(self, client, user):
        did = _upload(client, user, f"ct-{TS}.txt", CONTRACT_TEXT)
        ins = _insights(client, user, did)
        rf = _resolved_map(ins)
        # Decorrenza != Scadenza != Data firma
        assert rf["effective_date"]["value"] == "01/09/2026"
        assert rf["expiry_date"]["value"] == "31/08/2027"
        assert rf["signature_date"]["value"] == "15/08/2026"

    def test_id_card_extracts_names(self, client, user):
        did = _upload(client, user, f"cid-{TS}.txt", ID_CARD_TEXT)
        ins = _insights(client, user, did)
        rf = _resolved_map(ins)
        # Nome/Cognome dovrebbero essere estratti (label-tail per text field
        # o dal pool `persons` per ALLCAPS).
        # Almeno una delle due strade deve funzionare.
        assert "surname" in rf or "name" in rf, rf
        # Date rilascio/scadenza
        assert rf["issue_date"]["value"] == "20/01/2020"
        assert rf["expiry_date"]["value"] == "20/01/2030"


# ---------------------------------------------------------------------
# Priority / anti-hallucination rules — spec section 4 & 8
# ---------------------------------------------------------------------
class TestPriorityRules:
    def test_event_date_wins_over_order_date(self, client, user):
        content = (
            "BIGLIETTO CONCERTO\n"
            "OLLY LIVE 2026\n"
            "Data ordine: 18/12/2025\n"
            "Data evento: 30/06/2026\n"
            "Ora ordine: 08:10\n"
            "Ora inizio: 21:45\n"
            "Apertura porte: 17:00\n"
        )
        did = _upload(client, user, f"pri-{TS}.txt", content)
        ins = _insights(client, user, did)
        rf = _resolved_map(ins)
        # event_date deve essere 30/06/2026 (label "Data evento"), non 18/12/2025.
        assert rf["event_date"]["value"] == "30/06/2026"
        assert rf["event_time"]["value"] == "21:45"
        assert rf["doors_open"]["value"] == "17:00"

    def test_tktid_never_becomes_order_number(self, client, user):
        content = "Ordine: A1234567\nTktID: 999888777\n"
        did = _upload(client, user, f"tk-{TS}.txt", content)
        ins = _insights(client, user, did)
        # order_ids ha SOLO A1234567; TktID sta in technical_identifiers.
        assert "A1234567" in ins["entities"].get("order_ids", [])
        assert "999888777" not in ins["entities"].get("order_ids", [])
        assert "999888777" in ins["technical_identifiers"]["flat"]

    def test_posto_unico_never_becomes_person(self, client, user):
        content = (
            "BIGLIETTO CONCERTO\n"
            "OLLY LIVE 2026\n"
            "Posto Unico\n"
            "Tribuna Rossa\n"
            "Platea Sinistra\n"
            "Intestatario: Mario Rossi\n"
        )
        did = _upload(client, user, f"pu-{TS}.txt", content)
        ins = _insights(client, user, did)
        persons = ins["entities"].get("persons", [])
        for forbidden in ("Posto Unico", "Tribuna Rossa", "Platea Sinistra"):
            assert forbidden not in persons, f"'{forbidden}' erroneously as person"
        # Ma "Mario Rossi" deve essere riconosciuto (o dallo pool persons o
        # come intestatario nel schema).
        rf = _resolved_map(ins)
        holder_ok = "holder" in rf and "Mario Rossi" in rf["holder"]["value"]
        pool_ok = "Mario Rossi" in persons
        assert holder_ok or pool_ok

    def test_bare_11_digits_no_label_never_tax_id(self, client, user):
        content = "Sequenza tecnica: 12345678901\nAltro testo.\n"
        did = _upload(client, user, f"b11-{TS}.txt", content)
        ins = _insights(client, user, did)
        assert "12345678901" not in ins["entities"].get("tax_ids", [])

    def test_no_value_in_multiple_semantic_fields(self, client, user):
        did = _upload(client, user, f"nodup-{TS}.txt", TICKET_TEXT)
        ins = _insights(client, user, did)
        # Un valore non deve comparire in più di un resolved_field
        seen: dict[str, str] = {}
        for f in ins["resolved_fields"]:
            v = f["value"]
            assert v not in seen, (
                f"Value '{v}' appears in both {seen[v]} and {f['field_key']}"
            )
            seen[v] = f["field_key"]

    def test_technical_id_never_appears_as_phone(self, client, user):
        content = "TktID: 128492577\nBarcode: 4006381333931\nTel: +39 06 1234567\n"
        did = _upload(client, user, f"tp-{TS}.txt", content)
        ins = _insights(client, user, did)
        phones = ins["entities"].get("phones", [])
        tech = ins["technical_identifiers"]["flat"]
        assert "128492577" in tech
        assert "4006381333931" in tech
        # Il telefono legittimo è comunque presente
        assert any("1234567" in p for p in phones)
        # Nessun TktID/barcode dentro phones
        for p in phones:
            assert "128492577" not in p and "4006381333931" not in p


# ---------------------------------------------------------------------
# Confidence & hidden_fields
# ---------------------------------------------------------------------
class TestConfidence:
    def test_visible_and_hidden_thresholds_respected(self, client, user):
        did = _upload(client, user, f"ct-{TS}.txt", TICKET_TEXT)
        ins = _insights(client, user, did)
        vt = ins["classification"]["threshold_visible"]
        ht = ins["classification"]["threshold_hidden"]
        # Env default 60 / 40 — se venissero cambiati resta comunque coerente.
        for f in ins["resolved_fields"]:
            assert f["confidence"] >= vt
        for f in ins["hidden_fields"]:
            assert ht <= f["confidence"] < vt

    def test_source_snippet_bounded_length(self, client, user):
        did = _upload(client, user, f"sn-{TS}.txt", TICKET_TEXT)
        ins = _insights(client, user, did)
        for f in ins["resolved_fields"]:
            assert len(f.get("source_snippet", "")) <= 170


# ---------------------------------------------------------------------
# Regression — Iter21 backward-compat contract
# ---------------------------------------------------------------------
class TestRetrocompat:
    def test_iter21_payload_shape_preserved(self, client, user):
        did = _upload(client, user, f"rc-{TS}.txt", TICKET_TEXT)
        ins = _insights(client, user, did)
        # Iter21 keys STILL present
        for k in ("id", "filename", "type_key", "type_label",
                  "summary", "entities", "extraction", "technical_metadata",
                  "history", "content"):
            assert k in ins, f"legacy key missing: {k}"
        # summary.fields still list of {label,value}
        assert isinstance(ins["summary"]["fields"], list)
        for f in ins["summary"]["fields"]:
            assert "label" in f and "value" in f
        # entities still a dict of bucket → list
        assert isinstance(ins["entities"], dict)

    def test_generic_shows_no_schema_fields(self, client, user):
        did = _upload(client, user, f"g-{TS}.txt", UNKNOWN_TEXT)
        ins = _insights(client, user, did)
        assert ins["resolved_fields"] == []
        # hidden_fields può essere vuoto o assente
        assert not ins.get("hidden_fields")


# ---------------------------------------------------------------------
# Extensibility — a new schema can be registered without touching code
# ---------------------------------------------------------------------
class TestExtensibility:
    def test_register_new_document_type_works(self):
        from documents.schema_registry import (
            DocumentSchema, SchemaField, register_document_type,
            get_schema, all_schemas,
        )
        from documents.document_classifier import classify

        # Register a "porto d'armi" schema on the fly.
        schema = DocumentSchema(
            type_key="firearm_license",
            type_label="Porto d'armi",
            fields=[
                SchemaField("holder", "Titolare", "person",
                            ["titolare"], priority=90),
                SchemaField("expiry_date", "Scadenza", "date",
                            ["scadenza"], priority=70),
            ],
            info_order=["holder", "expiry_date"],
            classifier_keywords={"porto d'armi": 4.5, "questura": 3.0},
        )
        register_document_type(schema)
        assert get_schema("firearm_license") is not None
        assert "firearm_license" in all_schemas()

        # And the classifier picks it up on synthetic text.
        result = classify(
            "PORTO D'ARMI\nRilasciato dalla Questura di Roma\n"
            "Titolare: Mario Rossi\nScadenza: 12/12/2030\n",
            filename="", mime_type="text/plain",
        )
        assert result.type_key == "firearm_license"
