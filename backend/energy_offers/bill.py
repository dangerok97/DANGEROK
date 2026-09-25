"""Conservative extraction of comparison inputs from an Italian utility bill.

No customer name, address, POD or PDR leaves this module. A bill total is never
treated as a tariff: it may contain tax, deposits, adjustments and arrears.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any


def _number(raw: str) -> float | None:
    value = raw.strip().replace(" ", "")
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    try:
        result = float(value)
    except ValueError:
        return None
    return result if 0 <= result < 1_000_000 else None


def _labelled(text: str, labels: tuple[str, ...], unit: str) -> float | None:
    for label in labels:
        pattern = rf"(?im)^\s*{label}\s*[:=\-]?\s*(?:€\s*)?([\d.,]+)\s*(?:{unit})\b"
        hit = re.search(pattern, text)
        if hit:
            return _number(hit.group(1))
    return None


def parse_bill(text: str, *, document_id: str) -> dict[str, Any] | None:
    if not text or not document_id:
        return None
    low = text.lower()
    pod = re.search(r"(?i)\bPOD\s*[:=\-]?\s*(IT[A-Z0-9]{10,18})\b", text)
    pdr = re.search(r"(?i)\bPDR\s*[:=\-]?\s*(\d{10,20})\b", text)
    if bool(pod) != bool(pdr):
        electricity, gas = bool(pod), bool(pdr)
    else:
        electricity = bool(re.search(r"\b(?:energia elettrica|fornitura elettrica|luce)\b", low))
        gas = bool(re.search(r"\b(?:gas naturale|fornitura gas)\b", low))
    # A dual-fuel bill needs two independently extracted profiles.
    if electricity == gas:
        return None
    commodity = "electricity" if electricity else "gas"
    unit = r"kwh" if electricity else r"smc"
    annual = _labelled(text, (r"consumo\s+annuo(?:\s+stimato)?", r"consumi\s+annui"), unit)
    annual_estimated = False
    if annual is None:
        period = re.search(r"(?i)periodo\s+(?:di\s+riferimento|fatturato)\s*[:=\-]?\s*(\d{2}/\d{2}/\d{4})\s*[-–]\s*(\d{2}/\d{2}/\d{4})", text)
        consumed = _labelled(text, (r"consumo", r"consumi\s+del\s+periodo"), unit)
        if period and consumed is not None:
            try:
                first = datetime.strptime(period.group(1), "%d/%m/%Y").date()
                last = datetime.strptime(period.group(2), "%d/%m/%Y").date()
                days = (last - first).days + 1
                if 25 <= days <= 370:
                    annual = round(consumed * 365 / days)
                    annual_estimated = True
            except ValueError:
                pass
    if annual is not None and (annual <= 0 or annual > (100_000 if electricity else 50_000)):
        return None
    offer = re.search(r"(?im)^\s*codice\s+(?:identificativo\s+)?offerta\s*[:=\-]?\s*([A-Z0-9_\-]{6,100})\b", text)
    power = _labelled(text, (r"potenza\s+impegnata",), r"kw") if electricity else None
    identifier = pod if electricity else pdr
    supply_key = (
        hashlib.sha256(identifier.group(1).upper().encode()).hexdigest()[:20]
        if identifier else "default"
    )
    return {
        "commodity": commodity,
        "document_id": document_id,
        "supply_key": supply_key,
        "annual_consumption": annual,
        "annual_consumption_estimated": annual_estimated,
        "current_offer_code": offer.group(1).upper() if offer else None,
        "power_kw": power if power is not None and power <= 30 else None,
        "comparison_ready": bool(offer) and annual is not None and not annual_estimated and commodity == "electricity",
    }
