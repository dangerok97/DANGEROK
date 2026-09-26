"""Recurring web research uses real source identities and survives restarts."""
import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from energy_offers.bill import parse_bill
from energy_offers.service import EnergyOfferService, _alternatives, _profile


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

    async def choose(_system, _user):
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
                          "Codice offerta: CURRENT123",
    }
    policy = {
        "id": "policy-1", "user_id": user_id,
        "original_filename": "polizza_auto.pdf",
        "extracted_text": "Polizza RC auto\nTarga AB123CD",
    }
    await db.users.insert_one({"user_id": user_id, "preferences": {}})
    await db.documents.insert_many([bill, policy])
    assert await service.register_document(user_id, bill)
    assert await service.register_document(user_id, policy)

    searches = []
    notices = []

    class FakeResearch:
        def __init__(self, _db):
            pass

        async def run(self, owner, need, **kwargs):
            searches.append((owner, need.question, need.already_known, kwargs))
            return SimpleNamespace(id=f"run-{len(searches)}", status="completed")

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
