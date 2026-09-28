"""Reliable handoff for an explicit request to shop on Amazon.it.

The user can always open a search even when the reasoning providers are down.
Only the product category is sent in the URL; ORA never implies it placed an order.
"""
from __future__ import annotations

import re

from conversation_engine.ai_core.models import CognitiveTurnResult
from conversation_engine.ai_core.tools.amazon_search import prepare_amazon_search
from conversation_engine.ai_core.tools.sanitize import sanitize_external_query


_AMAZON = re.compile(r"\bamazon(?:\.it)?\b", re.I)
_ACTION = re.compile(r"\b(?:compra(?:re|mi)?|acquista(?:re|mi)?|ordina(?:re|mi)?|cerca(?:re|mi)?)\b", re.I)
_FILLER = re.compile(r"^(?:su|da|di|un|uno|una|il|lo|la|i|gli|le|dei|delle|per favore)\s+", re.I)
_ADVICE = re.compile(r"\b(?:cosa|quale|quali|consigl\w*|sugger\w*|propon\w*|potrei|dovrei)\b", re.I)
_VAGUE = re.compile(r"^(?:qualcosa|oggett[oi]|prodott[oi]|articol[oi]|cos[ae])\b", re.I)


def _item(text: str) -> str:
    amazon = _AMAZON.search(text)
    action = _ACTION.search(text)
    if not amazon or not action:
        return ""
    # "compra una lampada su Amazon" and "cerca su Amazon una lampada".
    between = text[action.end():amazon.start()] if action.start() < amazon.start() else ""
    part = between if between.strip().lower() not in ("", "su") else text[amazon.end():]
    part = re.sub(r"\bsu\s*$", "", part, flags=re.I)
    # Remove contact details before punctuation splitting (an email contains a dot).
    part, _ = sanitize_external_query(part)
    if not part:
        return ""
    part = (part.splitlines() or [""])[0].split(".", 1)[0].split("?", 1)[0].split("!", 1)[0]
    part = re.split(r"\b(?:per|così|e dimmi|poi|senza|consegn|spedisc|mio|mia|miei|mie)\b", part, maxsplit=1, flags=re.I)[0]
    part = part.strip(" ,;:-\"'«»")
    while _FILLER.match(part):
        part = _FILLER.sub("", part, count=1)
    # A short category keeps names, addresses and personal context out of the link.
    part, _ = sanitize_external_query(part)
    if not part:
        return ""
    part = re.sub(r"[^\w\s\-]", " ", part, flags=re.UNICODE)
    item = " ".join(part.split()[:7]).strip(" -")
    return "" if _VAGUE.match(item) else item


async def explicit_amazon_handoff(text: str) -> CognitiveTurnResult | None:
    action = _ACTION.search(text)
    if not _AMAZON.search(text) or not action:
        return None
    # An open request for a recommendation needs the goal and its evidence;
    # turning "what should I buy?" into a search for "what" is not help.
    if _ADVICE.search(text[:action.start()]):
        return None
    item = _item(text)
    if not item:
        return CognitiveTurnResult(mode="ask", ora_text="Che tipo di oggetto vuoi cercare su Amazon.it? Posso prepararti una ricerca, ma non effettuare l'acquisto al posto tuo.", question="Che tipo di oggetto vuoi cercare su Amazon.it?")
    result = await prepare_amazon_search({"query": item}, {})
    if result.status != "ok":
        return CognitiveTurnResult(mode="ask", ora_text="Indica solo il tipo di oggetto da cercare, senza dati personali. Preparerò la ricerca su Amazon.it; l'acquisto si completa sul loro sito.", question="Che tipo di oggetto vuoi cercare?")
    payload = result.payload
    return CognitiveTurnResult(mode="answer", tool_calls=1,
        ora_text=(f"Ho preparato una ricerca Amazon.it per **{payload['search_query']}**: "
                  f"[apri la ricerca]({payload['search_url']}).\n\n"
                  "Non ho verificato prodotti, prezzi o disponibilità, né ho aggiunto articoli al carrello "
                  "o effettuato un ordine. Scegli il prodotto e completa l'acquisto su Amazon."),
        ui_actions=[{"kind": "amazon_search", "label": "Apri la ricerca su Amazon", "url": payload["search_url"]}],
        trace={"handoff": "amazon_search", "order_placed": False})
