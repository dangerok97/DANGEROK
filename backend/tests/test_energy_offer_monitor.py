"""The monitor only makes comparable, dated, source-backed claims."""
from datetime import date
import os
import uuid

import pytest

from energy_offers.bill import parse_bill
from energy_offers.portal import export_url, parse_offers
from energy_offers.service import EnergyOfferService


def _offer(code: str, price: str, *, kind="01", end="2026-12-31", extra="") -> str:
    return f"""<offerta>
      <COD_OFFERTA>{code}</COD_OFFERTA><NOME_OFFERTA>{code} Casa</NOME_OFFERTA>
      <TIPO_CLIENTE>01</TIPO_CLIENTE><TIPO_OFFERTA>{kind}</TIPO_OFFERTA>
      <TIPOLOGIA_ATT_CONTR>99</TIPOLOGIA_ATT_CONTR>
      <TIPOLOGIA_FASCE>01</TIPOLOGIA_FASCE><DATA_INIZIO>2026-01-01</DATA_INIZIO>
      <DATA_FINE>{end}</DATA_FINE><URL_OFFERTA>https://example.com/{code}</URL_OFFERTA>
      <URL_SITO_VENDITORE>https://example.com</URL_SITO_VENDITORE>{extra}
      <ComponenteImpresa><IntervalloPrezzi><PREZZO>{price}</PREZZO><UNITA_MISURA>03</UNITA_MISURA></IntervalloPrezzi></ComponenteImpresa>
      <ComponenteImpresa><IntervalloPrezzi><PREZZO>120</PREZZO><UNITA_MISURA>01</UNITA_MISURA></IntervalloPrezzi></ComponenteImpresa>
    </offerta>"""


def test_bill_requires_comparable_annual_usage_and_public_offer_code():
    bill = """Bolletta energia elettrica
    POD: IT001E12345678
    Consumo annuo: 2700 kWh
    Codice offerta: CURRENT123
    Totale da pagare: 400,00 EUR
    """
    profile = parse_bill(bill, document_id="doc-1")
    assert profile["annual_consumption"] == 2700
    assert profile["current_offer_code"] == "CURRENT123"
    assert profile["comparison_ready"] is True
    assert "IT001E12345678" not in str(profile)
    assert "400" not in str(profile)


def test_bill_period_usage_starts_watch_without_claiming_savings():
    bill = """BOLLETTA ENERGIA ELETTRICA
    Periodo di riferimento: 01/06/2026 - 31/07/2026
    Consumo: 210 kWh
    Importo totale da pagare: EUR 87,40
    """
    profile = parse_bill(bill, document_id="doc-2")
    assert profile["annual_consumption_estimated"] is True
    assert profile["comparison_ready"] is False


def test_bill_without_usage_still_starts_watch_without_ranking():
    profile = parse_bill("Bolletta energia elettrica\nImporto da pagare: 87,40 EUR", document_id="doc-3")
    assert profile["annual_consumption"] is None
    assert profile["comparison_ready"] is False


def test_official_link_is_selected_and_foreign_link_ignored():
    html = """<a href='https://evil.example/PO_Offerte_E_MLIBERO_20260925.xml'>bad</a>
    <a href='/portaleOfferte/resources/opendata/csv/offerteML/2026_9/PO_Offerte_E_MLIBERO_20260925.xml'>real</a>"""
    assert export_url(html, "electricity").startswith("https://www.ilportaleofferte.it/")


def test_only_simple_live_offers_can_support_a_seller_component_comparison():
    xml = ("<root>" + _offer("CURRENT123", "0.30") + _offer("BETTER123", "0.20")
           + _offer("VARIABLE123", "0.01", kind="02")
           + _offer("EXPIRED123", "0.01", end="2026-08-01")
           + _offer("CONDITION123", "0.01", extra="<CondizioniContrattuali><LIMITANTE>01</LIMITANTE></CondizioniContrattuali>")
           + "</root>").encode()
    offers = parse_offers(xml, "electricity", today=date(2026, 9, 25))
    assert {offer["code"] for offer in offers} == {"CURRENT123", "BETTER123"}
    profile = parse_bill("Energia elettrica\nConsumo annuo: 2700 kWh\nCodice offerta: CURRENT123", document_id="doc-1")
    candidates = EnergyOfferService.compare(profile, offers)
    assert len(candidates) == 1
    assert candidates[0]["code"] == "BETTER123"
    assert candidates[0]["potential_saving_year"] == 270.0
    assert candidates[0]["comparison_basis"] == "seller_components_only"


def test_published_nested_xml_schema_yields_prices_and_rejects_restricted_offers():
    # Shape and values reflect a 26 September 2026 Portale Offerte export.
    # The fields are nested; a flat-only parser silently discards the catalog.
    xml = b"""<ListaOfferteMercatoLibero><offerta>
      <IdentificativiOfferta><COD_OFFERTA>PUBLIC123</COD_OFFERTA></IdentificativiOfferta>
      <DettaglioOfferta><TIPO_CLIENTE>01</TIPO_CLIENTE><TIPO_OFFERTA>01</TIPO_OFFERTA>
        <TIPOLOGIA_ATT_CONTR>99</TIPOLOGIA_ATT_CONTR>
        <NOME_OFFERTA>Public fixed</NOME_OFFERTA>
        <Contatti><URL_SITO_VENDITORE>https://seller.example/</URL_SITO_VENDITORE>
        <URL_OFFERTA>https://seller.example/offer</URL_OFFERTA></Contatti>
      </DettaglioOfferta>
      <ValiditaOfferta><DATA_INIZIO>01/09/2026_00:00:00</DATA_INIZIO>
        <DATA_FINE>30/09/2026_23:59:59</DATA_FINE></ValiditaOfferta>
      <TipoPrezzo><TIPOLOGIA_FASCE>01</TIPOLOGIA_FASCE></TipoPrezzo>
      <ComponenteImpresa><IntervalloPrezzi><FASCIA_COMPONENTE>01</FASCIA_COMPONENTE>
        <PREZZO>0.175</PREZZO><UNITA_MISURA>03</UNITA_MISURA></IntervalloPrezzi></ComponenteImpresa>
      <ComponenteImpresa><IntervalloPrezzi><PREZZO>144</PREZZO>
        <UNITA_MISURA>01</UNITA_MISURA></IntervalloPrezzi></ComponenteImpresa>
    </offerta></ListaOfferteMercatoLibero>"""
    offer = parse_offers(xml, "electricity", today=date(2026, 9, 26))
    assert len(offer) == 1
    assert offer[0]["code"] == "PUBLIC123"
    assert offer[0]["unit_price"] == .175
    assert offer[0]["fixed_year"] == 144
    assert parse_offers(xml.replace(b"</ValiditaOfferta>",
                                   b"<CONSUMO_MAX>1500</CONSUMO_MAX></ValiditaOfferta>"),
                        "electricity", today=date(2026, 9, 26)) == []


def test_no_incumbent_match_means_no_savings_claim():
    profile = parse_bill("Energia elettrica\nConsumo annuo: 2700 kWh\nCodice offerta: OLD12345", document_id="doc-1")
    offers = parse_offers(("<root>" + _offer("BETTER123", "0.20") + "</root>").encode(), "electricity", today=date(2026, 9, 25))
    candidate = EnergyOfferService.compare(profile, offers)[0]
    assert candidate["potential_saving_year"] is None
    assert candidate["comparison_basis"] == "current_terms_missing"


def test_partial_year_price_is_excluded_from_annual_comparison():
    seasonal = _offer(
        "SEASONAL123", "0.01",
        extra="<ComponenteImpresa><IntervalloPrezzi><PREZZO>0.01</PREZZO>"
              "<UNITA_MISURA>03</UNITA_MISURA><PeriodoValidita>"
              "<DURATA>3</DURATA></PeriodoValidita></IntervalloPrezzi></ComponenteImpresa>",
    )
    offers = parse_offers(("<root>" + seasonal + "</root>").encode(),
                          "electricity", today=date(2026, 9, 25))
    assert offers == []


def test_gas_offers_are_named_without_an_unsupported_cost_projection():
    offers = parse_offers(("<root>" + _offer("GAS12345", "0.20") + "</root>").encode(), "gas", today=date(2026, 9, 25))
    profile = parse_bill("Gas naturale\nConsumo annuo: 1000 Smc\nCodice offerta: GASOLD123", document_id="doc-gas")
    candidate = EnergyOfferService.compare(profile, offers)[0]
    assert candidate["name"] == "GAS12345 Casa"
    assert candidate["potential_saving_year"] is None
    assert candidate["comparison_basis"] == "price_not_comparable"


@pytest.mark.asyncio
async def test_upload_creates_durable_weekly_watch_and_only_changes_wake_review(monkeypatch):
    if not os.environ.get("MONGO_URL"):
        pytest.skip("integration test uses the isolated CI Mongo service")
    from motor.motor_asyncio import AsyncIOMotorClient
    from datetime import datetime, timedelta, timezone
    from opportunities.discovery import OpportunityDiscovery

    db = AsyncIOMotorClient(os.environ["MONGO_URL"]).get_database(f"ora_energy_test_{uuid.uuid4().hex[:12]}")
    service = EnergyOfferService(db)
    await service.ensure_indexes()
    user_id = "user-1"
    doc = {"id": "bill-1", "user_id": user_id,
           "extracted_text": "Energia elettrica\nConsumo annuo: 2700 kWh\nCodice offerta: CURRENT123"}
    await db.users.insert_one({"user_id": user_id, "preferences": {}})
    await db.documents.insert_one(doc)
    assert await service.register_bill(user_id, doc)
    seen = []

    async def fake_fetch(_commodity):
        return "https://www.ilportaleofferte.it/official.xml", [
            {"code": "CURRENT123", "name": "Current", "seller": "current.example", "url": "https://current.example", "unit_price": .30, "fixed_year": 120, "power_year": 0, "valid_until": None},
            {"code": "BETTER123", "name": "Better", "seller": "better.example", "url": "https://better.example", "unit_price": .20, "fixed_year": 120, "power_year": 0, "valid_until": None},
        ]

    async def fake_note(self, owner, **kwargs):
        seen.append((owner, kwargs))

    monkeypatch.setattr("energy_offers.service.fetch_offers", fake_fetch)
    monkeypatch.setattr(OpportunityDiscovery, "note", fake_note)
    first = datetime.now(timezone.utc) + timedelta(minutes=1)
    assert (await service.run_due(now=first))["changed"] == 1
    assert len(seen) == 1
    assert (await service.run_due(now=first + timedelta(days=1)))["checked"] == 0
    # After restart, the Mongo due time still drives the check. Same offers
    # produce no second attention request.
    second = EnergyOfferService(db)
    assert (await second.run_due(now=first + timedelta(days=8)))["changed"] == 0
    assert len(seen) == 1
    replacement = {**{key: value for key, value in doc.items() if key != "_id"},
                   "id": "bill-2", "extracted_text":
                   "Energia elettrica\nConsumo annuo: 3500 kWh\nCodice offerta: CURRENT123"}
    await db.documents.insert_one(replacement)
    assert await second.register_bill(user_id, replacement)
    current = (await second.status(user_id))[0]
    assert current["document_id"] == "bill-2"
    assert current["candidates"] == []
    assert current["source_fetched_at"] is None
    await db.energy_offer_monitors.update_one(
        {"user_id": user_id}, {"$set": {
            "source_fetched_at": (datetime.now(timezone.utc) - timedelta(days=11)).isoformat(),
            "candidates": [{"code": "OLD", "valid_until": None}],
        }}
    )
    stale = (await second.status(user_id))[0]
    assert stale["source_stale"] is True
    assert stale["candidates"] == []
    await db.energy_offer_monitors.update_one(
        {"user_id": user_id}, {"$set": {
            "source_fetched_at": datetime.now(timezone.utc).isoformat(),
            "candidates": [{"code": "EXPIRED", "valid_until":
                            (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()}],
        }}
    )
    expired = (await second.status(user_id))[0]
    assert expired["source_stale"] is False
    assert expired["candidates"] == []
    await second.set_enabled(user_id, False)
    assert (await second.run_due(now=first + timedelta(days=16)))["checked"] == 0

