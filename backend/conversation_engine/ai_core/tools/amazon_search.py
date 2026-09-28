"""Amazon.it shopping handoff: a search, never a reported order or offer.

Amazon retail does not expose a consumer checkout integration to ORA. This
capability does not access the shopper's Amazon account or product catalog.
"""
from urllib.parse import urlencode

from conversation_engine.ai_core.models import Observation
from conversation_engine.ai_core.tools.sanitize import sanitize_external_query


async def prepare_amazon_search(arguments, runtime):
    query, reason = sanitize_external_query(str(arguments.get("query") or ""))
    if not query:
        return Observation(kind="tool", name="prepare_amazon_search", status="failed",
            payload={"reason": reason, "message": "Indica il tipo di prodotto da cercare, senza dati personali."})
    url = "https://www.amazon.it/s?" + urlencode({"k": query})
    return Observation(kind="tool", name="prepare_amazon_search", status="ok",
        payload={
            "search_query": query, "search_url": url,
            "marketplace": "Amazon.it", "catalog_checked": False,
            "price_checked": False, "availability_checked": False,
            "order_placed": False, "checkout": "only_on_amazon_by_user",
            "message": "Ricerca pronta. L'utente può aprire Amazon.it e verificare prodotto, prezzo, disponibilità e acquisto.",
        })
