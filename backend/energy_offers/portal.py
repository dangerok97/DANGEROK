"""Read only the public, dated XML exports linked by the Portale Offerte.

Reject unfamiliar price structures instead of guessing their annual cost.
The result is a comparison of seller components, not a full-bill estimate.
"""
from __future__ import annotations

import asyncio
from http.cookiejar import CookieJar
from datetime import date
from html.parser import HTMLParser
from io import BytesIO
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener
import xml.etree.ElementTree as ET

PAGE = "https://www.ilportaleofferte.it/portaleOfferte/it/open-data.page"
MAX_XML_BYTES = 64 * 1024 * 1024


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _direct(element: ET.Element, name: str) -> str:
    # The published XML groups offer fields under IdentificativiOfferta,
    # DettaglioOfferta, ValiditaOfferta and TipoPrezzo.
    for child in element.iter():
        if child is element:
            continue
        if _local(child.tag) == name:
            return (child.text or "").strip()
    return ""


def _children(element: ET.Element, name: str):
    return (child for child in element.iter() if _local(child.tag) == name)


def _amount(raw: str) -> float | None:
    try:
        value = float(raw.replace(",", "."))
    except ValueError:
        return None
    return value if 0 <= value < 100_000 else None


def _day(raw: str) -> date | None:
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%Y%m%d"):
        try:
            from datetime import datetime
            return datetime.strptime(raw[:10], pattern).date()
        except ValueError:
            pass
    return None


def _safe_url(raw: str) -> bool:
    u = urlparse(raw)
    return u.scheme == "https" and bool(u.hostname) and not u.username and not u.password


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            if href:
                self.links.append(href)


def export_url(page_html: str, commodity: str) -> str:
    code = "E" if commodity == "electricity" else "G"
    links = _Links()
    links.feed(page_html)
    suffix = f"PO_Offerte_{code}_MLIBERO_"
    found = []
    for href in links.links:
        url = urljoin(PAGE, href)
        parsed = urlparse(url)
        if parsed.hostname != "www.ilportaleofferte.it":
            continue
        if "/resources/opendata/" not in parsed.path:
            continue
        filename = parsed.path.rsplit("/", 1)[-1]
        if filename.startswith(suffix) and filename.endswith(".xml"):
            found.append(url)
    if not found:
        raise ValueError("official_export_unavailable")
    return sorted(found)[-1]


def _read_limited(url: str, maximum: int, opener) -> bytes:
    request = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; ORA/1.0; public-offer-monitor)",
        "Referer": PAGE,
    })
    with opener.open(request, timeout=20) as response:
        data = response.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError("official_export_too_large")
    return data


def parse_offers(xml: bytes, commodity: str, *, today: date | None = None) -> list[dict]:
    if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise ValueError("unsafe_xml")
    today = today or date.today()
    offers: list[dict] = []
    stream = ET.iterparse(BytesIO(xml), events=("start", "end"))
    root = None
    for event, node in stream:
        if root is None and event == "start":
            root = node
        if event != "end" or _local(node.tag) != "offerta":
            continue
        try:
            if _direct(node, "TIPO_CLIENTE") != "01":
                continue
            if _direct(node, "TIPO_OFFERTA") != "01":
                continue  # indexed offers need a current index projection
            activations = {(c.text or "").strip()
                           for c in _children(node, "TIPOLOGIA_ATT_CONTR")}
            if not activations.intersection({"02", "99"}):
                continue  # switching or every activation type
            if _direct(node, "DOMESTICO_RESIDENTE") not in ("", "03"):
                continue  # residence-specific offers need a verified profile
            if _direct(node, "CONSUMO_MIN") not in ("", "0") or _direct(node, "CONSUMO_MAX"):
                continue  # usage-restricted offers need profile-aware filtering
            if _direct(node, "TIPOLOGIA_FASCE") not in ("", "01"):
                continue
            start, end = _day(_direct(node, "DATA_INIZIO")), _day(_direct(node, "DATA_FINE"))
            if (start and start > today) or (end and end < today):
                continue
            if any(True for _ in _children(node, "Sconto")):
                continue
            if any(_direct(c, "LIMITANTE") == "01" for c in _children(node, "CondizioniContrattuali")):
                continue
            if any(True for _ in _children(node, "REGIONE")) or any(True for _ in _children(node, "PROVINCIA")):
                continue  # bill profile has no verified location yet
            code, name = _direct(node, "COD_OFFERTA"), _direct(node, "NOME_OFFERTA")
            url = _direct(node, "URL_OFFERTA")
            if not code or not name or not _safe_url(url):
                continue
            vendor_url = _direct(node, "URL_SITO_VENDITORE")
            host = urlparse(vendor_url if _safe_url(vendor_url) else url).hostname or ""
            if commodity == "gas":
                offers.append({"code": code[:100], "name": name[:160],
                               "seller": host.removeprefix("www.")[:100], "url": url,
                               "unit_price": None, "fixed_year": None, "power_year": None,
                               "valid_until": end.isoformat() if end else None})
                continue
            price, fixed, power = 0.0, 0.0, 0.0
            energy_found = False
            invalid = False
            for component in _children(node, "ComponenteImpresa"):
                intervals = list(_children(component, "IntervalloPrezzi"))
                if not intervals:
                    invalid = True
                    break
                for interval in intervals:
                    if _direct(interval, "CONSUMO_DA") or _direct(interval, "CONSUMO_A"):
                        invalid = True
                        break
                    if any(True for _ in _children(interval, "PeriodoValidita")):
                        invalid = True
                        break
                    if _direct(interval, "FASCIA_COMPONENTE") not in ("", "01"):
                        invalid = True
                        break
                    value = _amount(_direct(interval, "PREZZO"))
                    unit = _direct(interval, "UNITA_MISURA")
                    if value is None:
                        invalid = True
                        break
                    if unit == "01":
                        fixed += value
                    elif unit == "02":
                        power += value
                    elif unit == "03":
                        price += value
                        energy_found = True
                    else:
                        invalid = True
                        break
                if invalid:
                    break
            if invalid or not energy_found or price <= 0 or price > 3:
                continue
            offers.append({
                "code": code[:100], "name": name[:160], "seller": host.removeprefix("www.")[:100],
                "url": url, "unit_price": round(price, 6),
                "fixed_year": round(fixed, 2), "power_year": round(power, 2),
                "valid_until": end.isoformat() if end else None,
            })
        finally:
            node.clear()
            if root is not None:
                root.clear()
    return offers


def _fetch_sync(commodity: str) -> tuple[str, list[dict]]:
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    page = _read_limited(PAGE, 2_000_000, opener).decode("utf-8")
    url = export_url(page, commodity)
    xml = _read_limited(url, MAX_XML_BYTES, opener)
    return url, parse_offers(xml, commodity)


async def fetch_offers(commodity: str) -> tuple[str, list[dict]]:
    return await asyncio.to_thread(_fetch_sync, commodity)

