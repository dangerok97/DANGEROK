"""Read a bounded public seller page for explicit tariff components only."""
from __future__ import annotations

import ipaddress
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

import aiohttp
from aiohttp.abc import AbstractResolver

from energy_offers.savings import offer_terms


class _PublicResolver(AbstractResolver):
    def __init__(self):
        self.resolver = aiohttp.DefaultResolver()

    async def resolve(self, host, port=0, family=0):
        addresses = await self.resolver.resolve(host, port, family)
        if not addresses or any(
            not ipaddress.ip_address(address["host"]).is_global
            for address in addresses
        ):
            raise ValueError("seller_page_not_public")
        return addresses

    async def close(self):
        await self.resolver.close()


class _VisibleText(HTMLParser):
    _BLOCKS = {"div", "p", "li", "section", "article", "br", "h1", "h2", "h3", "h4", "tr"}
    _HIDDEN = {"script", "style", "svg", "noscript", "nav", "footer"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._HIDDEN:
            self.hidden += 1
        if tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._BLOCKS:
            self.parts.append("\n")
        if tag in self._HIDDEN:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data + " ")


def terms_from_html(html: str, commodity: str) -> dict[str, float] | None:
    if commodity not in ("electricity", "gas"):
        return None
    parser = _VisibleText()
    parser.feed(html[:600_000])
    text = "".join(parser.parts).replace("\xa0", " ")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    unit = "kWh" if commodity == "electricity" else "Smc"
    # Multiple public rates on the page may represent bands, conditional
    # discounts or another tariff. In that case no single price is assumed.
    rates = set(re.findall(rf"\b\d{{1,3}}[.,]\d{{1,5}}\s*€\s*/\s*{unit}\b", text, re.I))
    normalized_rates = {re.sub(r"\s+", "", rate).lower().replace(",", ".") for rate in rates}
    if len(normalized_rates) > 1:
        return None
    found = set()
    for index, line in enumerate(lines):
        if not re.search(rf"€\s*/\s*{unit}\b", line, re.I):
            continue
        for start, end in ((index, index + 1), (max(0, index - 1), min(len(lines), index + 2))):
            window = " ".join(lines[start:end])[:700]
            terms = offer_terms(window, commodity)
            if terms:
                found.add((terms["unit_price"], terms["fixed_year"]))
    if len(found) != 1:
        return None
    rate, fixed = found.pop()
    return {"unit_price": rate, "fixed_year": fixed}


async def fetch_offer_terms(url: str, commodity: str) -> dict[str, float] | None:
    try:
        parsed = urlparse(url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or
            parsed.password or parsed.port not in (None, 443) or
            len(url) > 400 or not parsed.hostname.isascii()):
            return None
        timeout = aiohttp.ClientTimeout(total=10, connect=4)
        connector = aiohttp.TCPConnector(resolver=_PublicResolver(), use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout, trust_env=False) as session:
            async with session.get(url, allow_redirects=False, headers={"Accept": "text/html"}) as response:
                if response.status != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
                    return None
                body = await response.content.read(512_001)
                if len(body) > 512_000:
                    return None
                return terms_from_html(body.decode("utf-8", errors="replace"), commodity)
    except (aiohttp.ClientError, TimeoutError, ValueError, OSError):
        return None
