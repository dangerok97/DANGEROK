"""
Una risposta, detta ad alta voce.

Un endpoint solo, e non e' una conversazione: il testo arriva gia' deciso da
chi ragiona, e qui si trasforma in suono. Non decide niente, non ricorda
niente, non scrive niente — e non tiene l'audio da nessuna parte.

    QUELLO CHE UNA PERSONA CHIEDE ALLA PROPRIA ASSISTENTE NON DIVENTA UN FILE
    SU UN DISCO PERCHE' L'HA CHIESTO A VOCE.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field

from deps import get_current_user

logger = logging.getLogger("ora.voice.router")

router = APIRouter(prefix="/voice", tags=["voice"])


class Say(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    language: str = Field(default="it", max_length=8)


@router.get("/available")
async def voice_available(user=Depends(get_current_user)):
    """
    Se esiste una voce migliore di quella del browser, adesso.

    Il client la chiede una volta e sa se vale la pena provarci. Non e' una
    promessa: un provider disponibile puo' comunque non farcela, e in quel
    caso si parla lo stesso — con l'altra voce.
    """
    from voice.providers import a_voice

    provider = a_voice()
    return {"ok": True, "premium": provider is not None}


@router.post("/say")
async def voice_say(body: Say, user=Depends(get_current_user)):
    """
    Le parole come suono, o 204 quando tocca al browser.

    Un 204 non e' un errore e non va mostrato a nessuno: vuol dire che la
    voce di sistema deve prendere la parola. La risposta scritta e' gia'
    sullo schermo in entrambi i casi, ed e' la stessa.
    """
    from voice.providers import say_it

    spoken = await say_it(body.text, language=body.language)
    if spoken is None:
        return Response(status_code=204)
    return Response(
        content=spoken.audio,
        media_type=spoken.mime,
        headers={
            # Utile a chi guarda cosa sta succedendo, e a nessun altro.
            "X-Ora-Voice": spoken.provider,
            "Cache-Control": "no-store",
        },
    )
