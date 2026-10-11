"""ORA Vision X-Ray: grounded object recognition and illustrative exploded parts.

A single photo cannot prove an object's hidden geometry. Results distinguish
visible evidence from typical (inferred) parts. Captured bytes are processed
in memory and never persisted by this feature.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from deps import get_current_user
from visual.seeing import MAX_BYTES, _ask_with_image, can_see

router = APIRouter(prefix="/vision-xray", tags=["vision-xray"])
_SCAN_LIMIT = asyncio.Semaphore(3)

Mime = Literal["image/jpeg", "image/png", "image/webp"]


class ScanRequest(BaseModel):
    mime_type: Mime
    image_base64: str = Field(min_length=16, max_length=8_500_000)


SYSTEM = """Sei ORA Vision X-Ray, un assistente per esplorare oggetti reali.
Guarda la fotografia e identifica SOLO l'oggetto fisico principale.
Rispondi in ITALIANO con JSON, mai con Markdown. Se non puoi riconoscere
l'oggetto, dichiara confidenza bassa e NON inventare una scomposizione.

Distingui rigorosamente:
- visible: componente realmente distinguibile nella foto;
- typical: componente che spesso esiste in oggetti di quel tipo, ma non e'
  visibile, verificabile o necessariamente presente nell'esemplare fotografato.
Una foto esterna NON verifica la presenza di parti nascoste, il modello
esatto, il circuito interno o le dimensioni. Per le parti nascoste usa
sempre certainty="typical". Non dare istruzioni pericolose per smontare
batterie al litio, dispositivi alimentati dalla rete, oggetti sotto
pressione o altri elementi rischiosi.

Schema JSON ESATTO:
{
 "object_name": "nome comune dell'oggetto, non inventare modello o marca",
 "object_category": "categoria in massimo 5 parole",
 "what_i_see": "breve frase su cio' che vedi",
 "confidence": "high|medium|low",
 "parts": [
  {
   "name": "nome componente",
   "function": "a cosa serve",
   "how_it_works": "come funziona, in parole semplici",
   "certainty": "visible|typical",
   "visual_kind": "body|board|button|battery|sensor|connector|other"
  }
 ],
 "safety_note": "breve cautela utile, oppure stringa vuota",
 "unknowns": "cosa non e' verificabile dalla foto"
}
Da 2 a 7 componenti SOLO se riconosci l'oggetto con sufficiente
confidenza. Se la foto mostra soltanto una persona, un documento, o
un oggetto indistinguibile, parts deve essere [].
I campi sono spiegazioni educative, non istruzioni operative di riparazione.
"""


def decode_photo(mime_type: str, encoded: str) -> bytes:
    """Reject malformed, oversized or falsely labelled uploads."""
    try:
        blob = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(status_code=400, detail="Immagine non valida")
    if not blob or len(blob) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Immagine troppo grande (massimo 6 MB)")
    signatures = {
        "image/jpeg": blob.startswith(b"\xff\xd8\xff"),
        "image/png": blob.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": blob.startswith(b"RIFF") and blob[8:12] == b"WEBP",
    }
    if not signatures.get(mime_type, False):
        raise HTTPException(status_code=415, detail="Formato immagine non coerente")
    return blob


def _clip(value: Any, length: int) -> str:
    return str(value).strip()[:length] if isinstance(value, str) else ""


def normalize_result(data: dict[str, Any]) -> dict[str, Any]:
    """Model output is untrusted: cap text, number of parts and enumerations."""
    confidence = data.get("confidence")
    if confidence not in {"high", "medium", "low"}:
        confidence = "low"
    name = _clip(data.get("object_name"), 90)
    if not name:
        confidence = "low"
        name = "Oggetto non identificato"
    allowed_kinds = {"body", "board", "button", "battery", "sensor", "connector", "other"}
    parts = []
    if confidence != "low":
        for item in (data.get("parts") if isinstance(data.get("parts"), list) else [])[:7]:
            if not isinstance(item, dict):
                continue
            part_name = _clip(item.get("name"), 70)
            if not part_name:
                continue
            certainty = item.get("certainty")
            # Never upgrade an uncertain claim to a verified observation.
            certainty = "visible" if certainty == "visible" else "typical"
            kind = item.get("visual_kind")
            parts.append({
                "id": "part_" + str(len(parts) + 1),
                "name": part_name,
                "function": _clip(item.get("function"), 260),
                "how_it_works": _clip(item.get("how_it_works"), 380),
                "certainty": certainty,
                "visual_kind": kind if kind in allowed_kinds else "other",
            })
    return {
        "object_name": name,
        "object_category": _clip(data.get("object_category"), 80),
        "what_i_see": _clip(data.get("what_i_see"), 280),
        "confidence": confidence,
        "parts": parts,
        "safety_note": _clip(data.get("safety_note"), 240),
        "unknowns": _clip(data.get("unknowns"), 300),
        "visualization": "illustrative_exploded_2d",
        "verified_3d_model": False,
    }


@router.get("/available")
async def vision_available(user=Depends(get_current_user)):
    return {"available": can_see(), "camera_mode": "foreground_capture", "verified_3d": False}


@router.post("/scan")
async def scan_object(body: ScanRequest, user=Depends(get_current_user)):
    if not can_see():
        raise HTTPException(status_code=503, detail="Analisi visiva non configurata")
    blob = decode_photo(body.mime_type, body.image_base64)
    try:
        async with _SCAN_LIMIT:
            observation = await asyncio.wait_for(
                _ask_with_image(
                    system=SYSTEM,
                    user="Riconosci questo oggetto. Non inventare parti nascoste.",
                    image=blob,
                    mime_type=body.mime_type,
                ),
                timeout=48,
            )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Analisi troppo lenta. Riprova.")
    if not isinstance(observation, dict):
        raise HTTPException(status_code=503, detail="Modello visivo momentaneamente indisponibile")
    # Explicitly avoid saving the photo, detected components or user identity.
    return normalize_result(observation)
