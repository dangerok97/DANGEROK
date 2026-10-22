"""Explicit, owner-scoped, review-before-save studio cutout.

An isolated Railway worker uses pinned U²-NetP ONNX. Images stay encrypted at
rest, worker receives one normalized JPEG in memory on the private network;
no model weights or heavyweight inference run in the ORA main backend.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import os
import re

import httpx
import numpy as np
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field

from .service import WardrobeError

MAX_PNG_BYTES = 550_000
CUTOUT_SIDE = 576

class CutoutApproval(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    revision: int = Field(ge=1)
    view: str = Field(pattern="^(front|back)$")
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    png_b64: str = Field(min_length=100, max_length=750_000)

class CutoutRemove(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    view: str = Field(pattern="^(front|back)$")

def cutout_ready() -> bool:
    url = os.environ.get("ORA_WARDROBE_CUTOUT_URL", "").strip()
    token = os.environ.get("ORA_WARDROBE_CUTOUT_TOKEN", "").strip()
    # Strict internal DNS prevents accidental user-file egress to the internet.
    return bool(len(token) >= 32 and re.fullmatch(
        r"http://[a-z0-9-]+[.]railway[.]internal:8080", url))

def source_signature(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def _validate_png(data: bytes) -> bytes:
    if not data or len(data) > MAX_PNG_BYTES:
        raise WardrobeError("La foto vetrina supera il limite.", 413)
    try:
        with Image.open(io.BytesIO(data), formats=["PNG"]) as opened:
            if opened.size != (CUTOUT_SIDE, CUTOUT_SIDE):
                raise WardrobeError("Formato foto vetrina non valido.", 422)
            if opened.mode != "RGBA":
                raise WardrobeError("La foto vetrina non contiene la trasparenza.", 422)
            opened.load()
            alpha = np.asarray(opened.getchannel("A"), dtype=np.uint8)
            meaningful = alpha >= 96
            coverage = float(meaningful.mean())
            if coverage < 0.03 or coverage > 0.92:
                raise WardrobeError("Ritaglio poco affidabile. Mantieni l'originale.", 422)
            if not np.any(alpha == 0) or not np.any(alpha >= 230):
                raise WardrobeError("Ritaglio senza sfondo trasparente utile.", 422)
            # Re-encode the actual decoded raster: drop any unknown metadata
            # or trailing chunks and disallow SVG/polyglot content.
            out = io.BytesIO()
            opened.save(out, format="PNG", optimize=True)
            if out.tell() > MAX_PNG_BYTES:
                raise WardrobeError("Foto vetrina compressa troppo grande.", 413)
            return out.getvalue()
    except WardrobeError:
        raise
    except (OSError, ValueError, UnidentifiedImageError):
        raise WardrobeError("Foto vetrina non valida.", 422) from None

async def generate_cutout_preview(source: bytes) -> bytes:
    if not cutout_ready():
        raise WardrobeError("Foto vetrina non ancora disponibile in ORA.", 503)
    if not source or len(source) > 675_000:
        raise WardrobeError("Immagine di riferimento non adatta.", 413)
    url = os.environ["ORA_WARDROBE_CUTOUT_URL"].strip() + "/cutout"
    token = os.environ["ORA_WARDROBE_CUTOUT_TOKEN"].strip()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=4, read=29, write=4, pool=2),
            follow_redirects=False,
        ) as client:
            resp = await client.post(
                url, headers={"X-Ora-Cutout-Token": token,
                              "Content-Type":"image/jpeg"}, content=source)
    except httpx.HTTPError:
        raise WardrobeError(
            "Servizio foto vetrina temporaneamente non disponibile. Originale conservato.",
            503) from None
    if resp.status_code == 422:
        raise WardrobeError(
            "ORA non è riuscita a isolare il capo con bordi affidabili. "
            "La foto originale resta disponibile.", 422)
    if resp.status_code != 200:
        raise WardrobeError("Servizio foto vetrina non disponibile.", 503)
    if resp.headers.get("content-type", "").split(";")[0] != "image/png":
        raise WardrobeError("Il servizio ha restituito un'immagine non valida.", 503)
    return _validate_png(resp.content)

def accept_png_b64(raw: str) -> bytes:
    try:
        decoded = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise WardrobeError("Anteprima foto vetrina non valida.", 422) from None
    return _validate_png(decoded)
