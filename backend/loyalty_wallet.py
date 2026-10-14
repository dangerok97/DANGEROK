"""Private, static loyalty cards. No LLM, payment, NFC or issuer integration.

One encrypted aggregate per owner; compare-and-swap prevents lost updates.
The existing vault master secret derives a separate domain-specific AES key.
Images are decoded in memory and never sent to an external provider.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
from datetime import datetime, timezone
from typing import Literal

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pydantic import BaseModel, ConfigDict, Field, model_validator

FORMATS = {
    "CODE_128": "Code128", "EAN_13": "EAN13", "EAN_8": "EAN8",
    "UPC_A": "UPCA", "CODE_39": "Code39", "ITF": "ITF", "QR_CODE": "QRCode",
}
MAX_CARDS = 100
MAX_UPLOAD = 8 * 1024 * 1024
MAX_ENCRYPTED_BYTES = 12_000_000


class WalletError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def validate_code(fmt: str, code: str) -> str:
    """Validate, never trim, complete a checksum, cast to int or guess a format."""
    if fmt not in FORMATS:
        raise ValueError("Formato non supportato.")
    if not code or any(ord(c) < 32 or ord(c) == 127 for c in code):
        raise ValueError("Codice vuoto o con caratteri di controllo non supportati.")
    if fmt == "QR_CODE":
        if len(code.encode("utf-8")) > 512:
            raise ValueError("Il QR supera il limite di 512 byte di questa versione.")
    elif fmt in ("EAN_13", "EAN_8", "UPC_A"):
        length = {"EAN_13": 13, "EAN_8": 8, "UPC_A": 12}[fmt]
        if not re.fullmatch(r"[0-9]{%d}" % length, code):
            raise ValueError(f"{fmt}: servono esattamente {length} cifre, incluso il controllo.")
        total = sum(int(c) * (3 if i % 2 == 0 else 1) for i, c in enumerate(code[-2::-1]))
        if (10 - total % 10) % 10 != int(code[-1]):
            raise ValueError("Cifra di controllo errata: ricontrolla la tessera originale.")
    elif fmt == "ITF":
        if not re.fullmatch(r"[0-9]{2,64}", code) or len(code) % 2:
            raise ValueError("ITF richiede un numero pari di cifre (da 2 a 64).")
    elif fmt == "CODE_39":
        if not re.fullmatch(r"[0-9A-Z .$/+%-]{1,40}", code):
            raise ValueError("Code 39: massimo 40 caratteri, lettere maiuscole e simboli ammessi.")
    elif not re.fullmatch(r"[\x20-\x7e]{1,64}", code):
        raise ValueError("Code 128: massimo 64 caratteri ASCII stampabili.")
    return code


class CardInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    id: str = Field(pattern=r"^[0-9a-f]{32}$")
    name: str = Field(min_length=1, max_length=80)
    format: Literal["CODE_128", "EAN_13", "EAN_8", "UPC_A", "CODE_39", "ITF", "QR_CODE"]
    code: str = Field(min_length=1, max_length=512)
    static_confirmed: Literal[True]
    source: Literal["manual", "image"] = "manual"
    revision: int = Field(default=0, ge=0)
    favorite: bool = False

    @model_validator(mode="after")
    def validate_card(self):
        self.name = self.name.strip()
        if not self.name or any(ord(c) < 32 or ord(c) == 127 for c in self.name):
            raise ValueError("Inserisci un nome leggibile per la tessera.")
        validate_code(self.format, self.code)
        return self


def _codec():
    try:
        import zxingcpp
        return zxingcpp
    except ImportError as exc:
        raise WalletError("Lettore tessere non disponibile sul server.", 503) from exc


def render_code(fmt: str, code: str) -> str:
    """Generate a PNG and prove an exact software read-back before accepting it."""
    from PIL import Image, ImageOps
    validate_code(fmt, code)
    zx = _codec()
    try:
        barcode_format = getattr(zx.BarcodeFormat, FORMATS[fmt])
        barcode = zx.create_barcode(code, barcode_format)
        image = Image.fromarray(barcode.to_image(scale=4, add_hrt=False, add_quiet_zones=True)).convert("L")
        image = ImageOps.expand(image, border=16, fill=255)
        found = zx.read_barcodes(image, formats=barcode_format, text_mode=zx.TextMode.Plain)
        # ZXing 3 transmits UPC-A as 13-digit EAN content (ISO/IEC 15420).
        # Compare that exact standard representation, not a truncated guess.
        expected_text = "0" + code if fmt == "UPC_A" else code
        if not any(b.text == expected_text and b.format == barcode_format for b in found):
            raise WalletError("Non riesco a riprodurre fedelmente questo codice. Usa la tessera originale.", 422)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        png = buffer.getvalue()
        if len(png) > 48_000:
            raise WalletError("Codice troppo complesso per questa versione.", 422)
        return "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    except WalletError:
        raise
    except Exception as exc:
        raise WalletError("Impossibile riprodurre il codice senza modificarlo.", 422) from exc


def decode_image(raw: bytes) -> list[dict]:
    """A photo is transient input, not a stored card or a prompt for an AI."""
    from PIL import Image, ImageOps, UnidentifiedImageError
    if not raw or len(raw) > MAX_UPLOAD:
        raise WalletError("Carica una foto fino a 8 MB.", 413)
    try:
        image = Image.open(io.BytesIO(raw), formats=["PNG", "JPEG", "WEBP"])
        if image.width * image.height > 16_000_000:
            raise WalletError("Foto troppo grande: ritaglia la zona del codice.", 413)
        image = ImageOps.exif_transpose(image).convert("L")
        image.thumbnail((3000, 3000))
    except WalletError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise WalletError("Usa un'immagine JPEG, PNG o WebP valida.", 422) from exc
    zx = _codec()
    try:
        results = zx.read_barcodes(image, text_mode=zx.TextMode.Plain)
    except Exception as exc:
        raise WalletError("Non riesco a leggere la foto: riprova con il codice ben a fuoco.", 422) from exc
    candidates: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for result in results:
        fmt = next((key for key, value in FORMATS.items() if result.format == getattr(zx.BarcodeFormat, value)), None)
        if not fmt:
            continue
        text = result.text
        # UPC-A and an EAN-13 beginning with 0 have the same physical bars.
        # Offer both explicitly when a photo cannot establish the printed
        # 12/13-digit representation. Never discard an EAN leading zero.
        if fmt == "UPC_A" and len(text) == 13 and text.startswith("0"):
            text = text[1:]
        variants = [(fmt, text)]
        if fmt == "EAN_13" and len(text) == 13 and text.startswith("0"):
            variants.append(("UPC_A", text[1:]))
        for variant_fmt, variant_text in variants:
            if (variant_fmt, variant_text) in seen:
                continue
            try:
                validate_code(variant_fmt, variant_text)
            except ValueError:
                continue
            seen.add((variant_fmt, variant_text))
            candidates.append({"format": variant_fmt, "code": variant_text})
            if len(candidates) == 8:
                break
        if len(candidates) == 8:
            break
    if not candidates:
        raise WalletError("Nessun codice compatibile leggibile. Ritaglia il codice o inseriscilo manualmente.", 422)
    return candidates


class WalletCipher:
    def __init__(self, secret: str):
        if len(secret) < 32:
            raise WalletError("Archivio tessere non configurato in modo sicuro.", 503)
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"ora-wallet-v1", info=b"loyalty-cards").derive(secret.encode())
        self.aes = AESGCM(key)

    @classmethod
    def configured(cls):
        return cls((os.environ.get("TOKEN_VAULT_KEY") or os.environ.get("OAUTH_TOKEN_ENCRYPTION_KEY") or "").strip())

    def encrypt(self, owner: str, card: dict) -> dict:
        nonce = os.urandom(12)
        aad = json.dumps([owner, card["id"]], separators=(",", ":")).encode()
        payload = json.dumps(card, ensure_ascii=False, separators=(",", ":")).encode()
        encrypted = self.aes.encrypt(nonce, payload, aad)
        return {"id": card["id"], "ciphertext": base64.b64encode(nonce + encrypted).decode("ascii")}

    def decrypt(self, owner: str, entry: dict) -> dict:
        try:
            raw = base64.b64decode(entry["ciphertext"], validate=True)
            aad = json.dumps([owner, entry["id"]], separators=(",", ":")).encode()
            card = json.loads(self.aes.decrypt(raw[:12], raw[12:], aad))
            if card["id"] != entry["id"]:
                raise ValueError("identity")
            return card
        except Exception as exc:
            raise WalletError("Una tessera non è leggibile in modo sicuro. Nessun dato è stato modificato.", 503) from exc


class WalletService:
    def __init__(self, db, cipher: WalletCipher, renderer=render_code):
        self.col = db.loyalty_wallets
        self.cipher = cipher
        self.renderer = renderer

    async def _snapshot(self, owner: str) -> dict:
        return await self.col.find_one({"_id": owner, "user_id": owner}) or {
            "_id": owner, "user_id": owner, "revision": 0, "cards": [],
        }

    async def list_cards(self, owner: str) -> list[dict]:
        snap = await self._snapshot(owner)
        cards = [self.cipher.decrypt(owner, entry) for entry in snap["cards"]]
        return sorted(cards, key=lambda c: (not c["favorite"], c["name"].casefold(), c["id"]))

    async def _commit(self, before: dict, cards: list[dict]) -> bool:
        if sum(len(c["ciphertext"]) for c in cards) > MAX_ENCRYPTED_BYTES:
            raise WalletError("Spazio del portafoglio esaurito. Rimuovi una tessera prima di aggiungerne altre.", 409)
        after = {**before, "revision": before["revision"] + 1, "cards": cards}
        if before["revision"] == 0:
            try:
                await self.col.insert_one(after)
                return True
            except Exception as exc:
                if getattr(exc, "code", None) == 11000:
                    return False
                raise
        result = await self.col.replace_one(
            {"_id": before["_id"], "user_id": before["user_id"], "revision": before["revision"]}, after,
        )
        return result.matched_count == 1

    async def save(self, owner: str, data: CardInput) -> dict:
        image = None
        for _ in range(8):
            snap = await self._snapshot(owner)
            entry = next((c for c in snap["cards"] if c["id"] == data.id), None)
            old = self.cipher.decrypt(owner, entry) if entry else None
            if (old["revision"] if old else 0) != data.revision:
                if data.revision == 0 and old and old["revision"] == 1 and all(old.get(k) == v for k, v in data.model_dump(exclude={"revision"}).items()):
                    return old
                raise WalletError("La tessera è cambiata su un altro dispositivo. Aggiorna prima di salvarla.", 409)
            if not old and len(snap["cards"]) >= MAX_CARDS:
                raise WalletError("Hai raggiunto il limite di 100 tessere.", 409)
            # One loyalty number can legitimately belong to different shops
            # (e.g. a phone number). Reject only an exact same-shop duplicate;
            # don't claim that the code alone identifies an issuer.
            for sibling in snap["cards"]:
                if sibling["id"] == data.id:
                    continue
                existing = self.cipher.decrypt(owner, sibling)
                if (existing["format"] == data.format
                    and existing["code"] == data.code
                    and existing["name"].strip().casefold() == data.name.casefold()):
                    raise WalletError("Questa tessera è già salvata per questo negozio. Apri quella esistente.", 409)
            if old and old["code"] == data.code and old["format"] == data.format:
                image = old["image"]
            elif image is None:
                from starlette.concurrency import run_in_threadpool
                image = await run_in_threadpool(self.renderer, data.format, data.code)
            now = datetime.now(timezone.utc).isoformat()
            card = {**data.model_dump(), "revision": data.revision + 1, "image": image,
                    "created_at": old["created_at"] if old else now, "updated_at": now,
                    "acceptance": "not_verified_at_checkout"}
            cards = [c for c in snap["cards"] if c["id"] != data.id]
            cards.append(self.cipher.encrypt(owner, card))
            if await self._commit(snap, cards):
                return card
        raise WalletError("Portafoglio occupato da un altro aggiornamento: riprova.", 409)

    async def delete(self, owner: str, card_id: str, revision: int) -> None:
        for _ in range(8):
            snap = await self._snapshot(owner)
            entry = next((c for c in snap["cards"] if c["id"] == card_id), None)
            if not entry:
                return
            if self.cipher.decrypt(owner, entry)["revision"] != revision:
                raise WalletError("La tessera è cambiata. Aggiorna prima di eliminarla.", 409)
            if await self._commit(snap, [c for c in snap["cards"] if c["id"] != card_id]):
                return
        raise WalletError("Portafoglio occupato: aggiorna e riprova.", 409)
