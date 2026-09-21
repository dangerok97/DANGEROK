"""Il meteo come superficie HTTP — GET /api/weather."""
from __future__ import annotations

from fastapi import APIRouter, Depends

import weather as meteo
from deps import db, get_current_user
from home.service import HomeService

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("")
async def get_weather(user=Depends(get_current_user)):
    """
    Il meteo per esteso, dove si trova la persona.

    La posizione la risolve la Home, con la stessa regola: prima il GPS che il
    telefono ha già condiviso, poi i luoghi salvati. Due modi diversi di
    scegliere il punto darebbero due meteo diversi nella stessa app.
    """
    punto = await HomeService(db)._where_they_are(user["user_id"])
    if punto is None:
        return meteo.unavailable("non so ancora dove sei")
    lat, lon, dove = punto
    return await meteo.forecast_at(lat=lat, lon=lon, place=dove)
