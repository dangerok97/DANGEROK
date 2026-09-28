import asyncio
from urllib.parse import parse_qs, urlparse
import pytest

from conversation_engine.ai_core.amazon_handoff import explicit_amazon_handoff
from conversation_engine.ai_core.orchestrator import AICoreOrchestrator
from conversation_engine.ai_core.tools.amazon_search import prepare_amazon_search
from conversation_engine.ai_core.tools.registry import ToolRegistry
from conversation_engine.tests.test_ora_surface_v25 import FakeDB


def test_amazon_handoff_is_a_search_and_never_an_order():
    spec = ToolRegistry().get("prepare_amazon_search")
    assert spec.side_effect == "READ_ONLY"
    result = asyncio.run(spec.handler({"query": "lampada da scrivania regolabile"}, {}))
    assert result.status == "ok"
    url = urlparse(result.payload["search_url"])
    assert url.netloc == "www.amazon.it"
    assert parse_qs(url.query) == {"k": ["lampada da scrivania regolabile"]}
    assert not result.payload["order_placed"]
    assert not result.payload["catalog_checked"]
    assert not result.payload["price_checked"]


def test_amazon_query_drops_contact_details_before_handoff():
    result = asyncio.run(prepare_amazon_search(
        {"query": "lampada da scrivania francesco@example.com"}, {}))
    assert result.status == "ok"
    assert "francesco" not in result.payload["search_url"]
    assert "lampada" in result.payload["search_query"]


@pytest.mark.asyncio
async def test_explicit_purchase_persists_clickable_search_without_a_model():
    async def no_model(*args):
        raise AssertionError("explicit Amazon handoff must work during provider outage")

    orch = AICoreOrchestrator(FakeDB(), decision_fn=no_model)
    response = await orch.start("u", text=(
        "Vorrei comprare una lampada da scrivania su Amazon per studiare la sera. "
        "Preparami una ricerca e dimmi cosa hai fatto davvero."))
    assert response["ok"] and response["tool_calls"] == 1
    assert "[apri la ricerca](https://www.amazon.it/s?k=lampada+da+scrivania)" in response["ora_text"]
    assert "Non ho verificato prodotti, prezzi o disponibilità" in response["ora_text"]
    assert "né ho aggiunto articoli al carrello o effettuato un ordine" in response["ora_text"]
    stored = await orch.get("u", response["session_id"])
    assert stored["ora_text"] == response["ora_text"]
    assert (await orch.get("other", response["session_id"]))["error"] == "not_found"


@pytest.mark.asyncio
async def test_amazon_handoff_in_existing_session_and_missing_item_question():
    orch = AICoreOrchestrator(FakeDB())
    response = await explicit_amazon_handoff("Cerca su Amazon cuffie wireless")
    assert "k=cuffie+wireless" in response.ora_text
    assert await explicit_amazon_handoff("Ho comprato cuffie su Amazon ieri") is None
    assert await explicit_amazon_handoff("Cosa potrei comprare su Amazon per studiare?") is None
    private = await explicit_amazon_handoff("Compra lampada mario@example.com su Amazon")
    assert "mario" not in private.ora_text and "lampada" in private.ora_text
    first = await explicit_amazon_handoff("Acquista su Amazon")
    assert first.mode == "ask" and "Che tipo di oggetto" in first.ora_text
    vague = await explicit_amazon_handoff("Comprami qualcosa su Amazon")
    assert vague.mode == "ask" and "Che tipo di oggetto" in vague.ora_text
    assert (await explicit_amazon_handoff("Comprami un oggetto su Amazon")).mode == "ask"
    # Use an existing session via the same deterministic start path.
    started = await orch.start("u", text="Comprami una lampada su Amazon")
    next_turn = await orch.message("u", started["session_id"], text="Cerca su Amazon cuffie wireless")
    assert "k=cuffie+wireless" in next_turn["ora_text"]
    assert (await orch.get("u", started["session_id"]))["ora_text"] == next_turn["ora_text"]
