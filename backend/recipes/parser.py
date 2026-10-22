"""Conservative, zero-cost text/link ingestion for ORA Cucina.

No arbitrary URL fetch: a social link may be stored, but is never misrepresented
as a successfully transcribed video. Ingredient quantities are never inferred.
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

MAX_SOURCE_LENGTH = 12000
TRACKING_KEYS = {"fbclid", "gclid", "igshid", "mc_cid", "mc_eid"}
URL_PATTERN = re.compile(r"^https?://\S+$", re.I)
INGREDIENT_HEADER = re.compile(r"^(?:ingredienti|occorrente|ingredients)(?:\s+per\s+\d+\s+\w+)?\s*:?\s*$", re.I)
METHOD_HEADER = re.compile(r"^(?:procedimento|preparazione|istruzioni|metodo|directions|instructions|preparation)(?:\s+di\s+\w+)?\s*:?\s*$", re.I)
STEP_NUMBER = re.compile(r"^\d{1,2}[.)]\s*")
BULLET = re.compile(r"^[•*\-–]\s*")


def canonical_url(value: str) -> str:
    """Store HTTPS links only. Never fetch or send them to an AI implicitly."""
    raw = (value or "").strip()
    if len(raw) > 2048 or any(ord(c) < 33 for c in raw):
        raise ValueError("Link non valido.")
    try:
        p = urlsplit(raw)
        host = (p.hostname or "").lower()
        if (p.scheme.lower() != "https" or not host or p.username or p.password or
            p.port is not None or "." not in host or host.endswith(".") or
            host in {"localhost", "localdomain"}):
            raise ValueError
        # URL is displayed/opened by the user only, not fetched by the server.
        query = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                           if k.lower() not in TRACKING_KEYS and not k.lower().startswith("utm_")])
        return urlunsplit(("https", host, p.path or "/", query, ""))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Incolla un indirizzo HTTPS pubblico valido.") from exc


def source_fingerprint(source_url: str, source_text: str) -> str:
    """Stable per-source identity; the owning account is additionally in Mongo _id."""
    value = ("url:" + canonical_url(source_url)) if source_url else (
        "text:" + re.sub(r"\s+", " ", source_text.strip()).casefold())
    if value == "text:":
        raise ValueError("Inserisci un link o il testo della ricetta.")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _clean(line: str) -> str:
    return STEP_NUMBER.sub("", BULLET.sub("", line)).strip()


def preview(source: str) -> dict:
    """Parse only explicit section lines. Nothing is fabricated or autosaved."""
    raw = (source or "").strip()
    if not raw or len(raw) > MAX_SOURCE_LENGTH:
        raise ValueError("Incolla un link o un testo fino a 12.000 caratteri.")
    if URL_PATTERN.fullmatch(raw):
        url = canonical_url(raw)
        host = urlsplit(url).hostname or "sito"
        label = ("Instagram" if "instagram.com" in host else
                 "TikTok" if "tiktok.com" in host else
                 "YouTube" if "youtube.com" in host or "youtu.be" in host else host)
        return {
            "draft": {"title": "Ricetta da " + label, "source_url": url, "source_text": "",
                      "ingredients": [], "steps": [], "tags": [], "servings": None,
                      "favorite": False, "status": "to_try"},
            "quality": "link_only",
            "warnings": ["Link conservabile, ma video e ingredienti non sono stati analizzati. Completa la scheda prima di cucinare."],
        }
    lines = [x.strip() for x in raw.replace("\r", "").split("\n") if x.strip()]
    title = "Ricetta da completare"
    if lines and len(lines[0]) <= 110 and not re.search(r"[.!?]\s", lines[0]) and not BULLET.match(lines[0]) and not STEP_NUMBER.match(lines[0]) and not INGREDIENT_HEADER.match(lines[0]) and not METHOD_HEADER.match(lines[0]):
        title = lines[0][:110]
    ingredients: list[str] = []
    steps: list[str] = []
    section = ""
    for line in lines:
        if INGREDIENT_HEADER.fullmatch(line):
            section = "ingredients"
            continue
        if METHOD_HEADER.fullmatch(line):
            section = "steps"
            continue
        if section == "ingredients" and len(ingredients) < 60:
            value = _clean(line)
            if value and len(value) <= 250:
                ingredients.append(value)
        elif section == "steps" and len(steps) < 40:
            value = _clean(line)
            if value and len(value) <= 800:
                steps.append(value)
    warnings = []
    if not ingredients:
        warnings.append("Ingredienti non identificati: aggiungili usando solo quantità note.")
    if not steps:
        warnings.append("Procedimento non identificato: inserisci i passaggi effettivi.")
    return {
        "draft": {"title": title, "source_url": "", "source_text": raw,
                  "ingredients": ingredients, "steps": steps, "tags": [],
                  "servings": None, "favorite": False, "status": "to_try"},
        "quality": "structured_text" if not warnings else "partial_text",
        "warnings": warnings,
    }
