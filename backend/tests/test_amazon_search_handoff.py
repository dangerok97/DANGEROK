import asyncio
from urllib.parse import parse_qs, urlparse

from conversation_engine.ai_core.tools.amazon_search import prepare_amazon_search
from conversation_engine.ai_core.tools.registry import ToolRegistry


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
