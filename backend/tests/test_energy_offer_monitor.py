"""Recurring web research uses real source identities and survives restarts."""
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from energy_offers.bill import parse_bill
from energy_offers.service import EnergyOfferService, _advice, _alternatives, _apply_savings, _profile
from energy_offers.savings import offer_terms


def test_bill_profile_does_not_expose_identifiers_or_invoice_total():
    profile = parse_bill(
        "Bolletta energia elettrica\nPOD: IT001E12345678\n"
        "Consumo annuo: 2700 kWh\nCodice offerta: CURRENT123\n"
        "Totale da pagare: 400,00 EUR",
        document_id="doc-1",
    )
    assert profile["annual_consumption"] == 2700
    assert "IT001E12345678" not in str(profile)
    assert "400" not in str(profile)


def test_saving_advice_requires_explicit_comparable_seller_terms():
    profile = parse_bill(
        "Bolletta energia elettrica\nConsumo annuo: 2700 kWh\n"
        "Prezzo materia energia: 0,22 €/kWh\n"
        "Quota fissa di commercializzazione: 12 €/mese\n"
        "Totale da pagare: 400,00 EUR\n",
        document_id="bill-advice",
    )
    assert profile is not None and profile["comparison_ready"]
    assert profile["current_fixed_year"] == 144
    candidate = {
        "code": "named", "name": "Piano Fisso", "seller": "seller.example",
        "url": "https://seller.example/piano-fisso", "source_id": "named",
        "comparison_basis": "not_comparable", "potential_saving_year": None,
        "current_seller_year": None, "estimated_seller_year": None,
    }
    source = SimpleNamespace(
        source_id="named", url=candidate["url"],
        snippet="Prezzo fisso 0,159€/kWh + 8,75€ al mese (costi di commercializzazione)",
    )
    _apply_savings(profile, SimpleNamespace(sources=[source]), [candidate])
    assert candidate["comparison_basis"] == "seller_component_estimate"
    assert candidate["current_seller_year"] == 738
    assert candidate["estimated_seller_year"] == 534.3
    assert candidate["potential_saving_year"] == 203.7
    advice = _advice(profile, [candidate])
    assert advice["kind"] == "estimated_saving"
    assert "sola componente di vendita" in advice["text"]
    assert "400" not in advice["text"]
    candidate["comparison_basis"] = "not_comparable"
    candidate["potential_saving_year"] = None
    threshold = _advice(profile, [candidate])
    assert threshold["kind"] == "comparison_needed"
    assert "738.00 €" in threshold["text"]
    no_offer = _advice(profile, [])
    assert no_offer["kind"] == "comparison_needed"
    assert "738.00 €" in no_offer["text"]


def test_variable_or_incomplete_offer_cannot_claim_a_saving():
    assert offer_terms("Prezzo indicizzato PUN 0,15 €/kWh, quota fissa 10 €/mese", "electricity") is None
    assert offer_terms("Prezzo fisso 0,15 €/kWh", "electricity") is None
    profile = parse_bill("Energia elettrica\nConsumo annuo: 2700 kWh\nTotale da pagare: 700 €", document_id="incomplete")
    assert profile is not None and not profile["comparison_ready"]
    candidate = {"code": "x", "name": "Piano X", "comparison_basis": "not_comparable"}
    assert _advice(profile, [candidate])["kind"] == "comparison_needed"


def test_policy_profile_does_not_send_plate_or_person_to_search():
    profile = _profile({
        "id": "policy-1",
        "original_filename": "polizza_auto.pdf",
        "extracted_text": "Polizza RC auto\nTarga AB123CD\nMario Rossi",
    })
    assert profile["commodity"] == "insurance_auto"
    assert "AB123CD" not in str(profile)
    assert "Mario Rossi" not in str(profile)
    assert profile["comparison_ready"] is False


def test_policy_advice_sets_a_personal_quote_target_without_claiming_a_saving():
    profile = _profile({
        "id": "policy-target", "original_filename": "polizza_auto.pdf",
        "extracted_text": "Polizza RC auto\nPremio annuo: 500 €\n",
    })
    assert profile is not None and profile["current_premium_year"] == 500
    advice = _advice(profile, [{"code": "insurer", "name": "Polizza Alfa"}])
    assert advice["kind"] == "comparison_needed"
    assert "500.00 €" in advice["text"]
    assert "massimali" in advice["text"]
    assert "500.00 €" in _advice(profile, [])["text"]
    assert _profile({
        "id": "ocr-policy", "original_filename": "polizza_auto.pdf", "ocr_used": True,
        "extracted_text": "Polizza RC auto\nPremio annuo: 500 €\n",
    })["current_premium_year"] is None


@pytest.mark.asyncio
async def test_only_cited_seller_pages_can_be_shown(monkeypatch):
    source = SimpleNamespace(
        source_id="seller", url="https://insurer.example/offerta-rca",
        title="Offerta RCA", snippet="Polizza auto disponibile",
        publisher="insurer.example",
    )
    article = SimpleNamespace(
        source_id="article", url="https://magazine.example/guida",
        title="Guida alle polizze", snippet="Confronta le polizze",
        publisher="magazine.example",
    )
    run = SimpleNamespace(
        sources=[source, article],
        citable_sources=lambda: [{"url": source.url}],
    )

    async def choose(_system, _user):
        return {"source_ids": ["seller", "article", "invented"]}

    monkeypatch.setattr("research.reasoning._ask_model", choose)
    offers = await _alternatives(run, "insurance_auto")
    assert len(offers) == 1
    assert offers[0]["url"] == source.url
    assert offers[0]["potential_saving_year"] is None
    assert offers[0]["comparison_basis"] == "not_comparable"


@pytest.mark.asyncio
async def test_energy_category_pages_are_not_presented_as_individual_offers(monkeypatch):
    category = SimpleNamespace(
        source_id="category", url="https://seller.example/casa/offerte-luce",
        title="Offerte luce per la casa a prezzo fisso e variabile",
        snippet="Scopri le nostre offerte luce", publisher="seller.example",
    )
    named = SimpleNamespace(
        source_id="named", url="https://seller.example/casa/offerte-luce/piano-verde",
        title="Piano Verde luce a prezzo fisso",
        snippet="Piano Verde disponibile", publisher="seller.example",
    )
    run = SimpleNamespace(
        sources=[category, named],
        citable_sources=lambda: [{"url": category.url}, {"url": named.url}],
    )

    async def choose(_system, user_payload):
        assert [source["source_id"] for source in json.loads(user_payload)["sources"]] == ["named"]
        return {"source_ids": ["category", "named"]}

    monkeypatch.setattr("research.reasoning._ask_model", choose)
    offers = await _alternatives(run, "electricity")
    assert [offer["url"] for offer in offers] == [named.url]


@pytest.mark.asyncio
async def test_durable_web_check_repeats_and_only_changes_wake_review(monkeypatch):
    if not os.environ.get("MONGO_URL"):
        pytest.skip("integration test uses the isolated CI Mongo service")
    from motor.motor_asyncio import AsyncIOMotorClient
    from opportunities.discovery import OpportunityDiscovery
    import research.service as research_service
    import energy_offers.service as market_service

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client.get_database(f"ora_market_test_{uuid.uuid4().hex[:12]}")
    service = EnergyOfferService(db)
    await service.ensure_indexes()
    user_id = "user-1"
    bill = {
        "id": "bill-1", "user_id": user_id,
        "extracted_text": "Energia elettrica\nConsumo annuo: 2700 kWh\n"
                          "Codice offerta: CURRENT123\n"
                          "Prezzo materia energia: 0,22 €/kWh\n"
                          "Quota fissa di commercializzazione: 12 €/mese",
    }
    policy = {
        "id": "policy-1", "user_id": user_id,
        "original_filename": "polizza_auto.pdf",
        "extracted_text": "Polizza RC auto\nTarga AB123CD\nPremio annuo: 500 €",
    }
    await db.users.insert_one({"user_id": user_id, "preferences": {}})
    await db.documents.insert_many([bill, policy])
    assert await service.register_document(user_id, bill)
    assert await service.register_document(user_id, policy)
    before_search = await service.status(user_id)
    assert {row["commodity"]: row["advice"]["kind"] for row in before_search} == {
        "electricity": "comparison_needed", "insurance_auto": "comparison_needed",
    }
    assert all(row["last_checked_at"] is None for row in before_search)

    searches = []
    notices = []

    class FakeResearch:
        def __init__(self, _db):
            pass

        async def run(self, owner, need, **kwargs):
            searches.append((owner, need.question, need.already_known, kwargs))
            return SimpleNamespace(id=f"run-{len(searches)}", status="completed", sources=[])

    async def alternatives(_run, category):
        return [{
            "code": f"{category}-offer", "name": f"{category} Offer",
            "seller": "seller.example", "url": "https://seller.example/offer",
            "valid_until": None, "potential_saving_year": None,
            "estimated_seller_year": None, "current_seller_year": None,
            "comparison_basis": "not_comparable",
        }]

    async def note(_self, owner, **kwargs):
        notices.append((owner, kwargs))

    monkeypatch.setattr(research_service, "research_available", lambda: True)
    monkeypatch.setattr(research_service, "ResearchService", FakeResearch)
    monkeypatch.setattr(market_service, "_alternatives", alternatives)
    monkeypatch.setattr(OpportunityDiscovery, "note", note)

    first = datetime.now(timezone.utc) + timedelta(minutes=1)
    assert (await service.run_due(now=first))["changed"] == 1
    assert (await service.run_due(now=first))["changed"] == 1
    assert len(notices) == 2
    assert (await service.run_due(now=first + timedelta(days=1)))["checked"] == 0

    # Persisted due time is consumed after a process restart. Repeated
    # evidence refreshes the check without creating another proposal.
    restarted = EnergyOfferService(db)
    assert (await restarted.run_due(now=first + timedelta(days=8)))["changed"] == 0
    assert len(notices) == 2
    assert len(searches) == 3
    assert all(item[3]["allow_reuse"] is False for item in searches)
    assert all("AB123CD" not in str(item) for item in searches)
    status = await restarted.status(user_id)
    assert {row["commodity"] for row in status} == {"electricity", "insurance_auto"}
    assert all(row["advice"]["kind"] == "comparison_needed" for row in status)
    await restarted.set_enabled(user_id, False)
    assert (await restarted.run_due(now=first + timedelta(days=16)))["checked"] == 0
    client.close()


@pytest.mark.asyncio
async def test_search_outage_retries_without_claiming_a_completed_check(monkeypatch):
    if not os.environ.get("MONGO_URL"):
        pytest.skip("integration test uses the isolated CI Mongo service")
    from motor.motor_asyncio import AsyncIOMotorClient
    import research.service as research_service

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client.get_database(f"ora_market_test_{uuid.uuid4().hex[:12]}")
    service = EnergyOfferService(db)
    await service.ensure_indexes()
    doc = {"id": "p1", "user_id": "u1", "original_filename": "polizza_auto.pdf",
           "extracted_text": "Polizza RC auto"}
    await db.users.insert_one({"user_id": "u1", "preferences": {}})
    await db.documents.insert_one(doc)
    assert await service.register_document("u1", doc)
    monkeypatch.setattr(research_service, "research_available", lambda: False)
    moment = datetime.now(timezone.utc) + timedelta(minutes=1)
    assert (await service.run_due(now=moment))["failed"] == 1
    row = (await service.status("u1"))[0]
    assert row["last_checked_at"] is None
    assert row["candidates"] == []
    assert row["next_check_at"] > moment.isoformat()
    client.close()
