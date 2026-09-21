"""
Che tempo fa, secondo qualcuno che lo sa davvero.

    NESSUN METEO INVENTATO. MAI.

Un numero sbagliato in alto a destra è peggio di nessun numero: qualcuno esce
di casa vestito come dice ORA. Quindi o il dato arriva da un servizio vero, o
l'interfaccia scrive «Meteo non disponibile» — non esistono vie di mezzo, e non
esiste il ripiego «più o meno così».

Il servizio predefinito è Open-Meteo: niente chiave, niente costo. Si spegne
con `WEATHER_PROVIDER=none` e si cambia mettendone un altro con la sua
`WEATHER_API_KEY`. La forma è quella di `places/routing.py`, per la stessa
ragione: il provider è una decisione di configurazione, non di codice.

Il punto da cui guardare lo decide chi chiama — nella Home è la posizione vera
del telefono, non un indirizzo scritto a mano.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger("ora.weather")

PROVIDER_ENV = "WEATHER_PROVIDER"
KEY_ENV = "WEATHER_API_KEY"

#     LE CONDIZIONI, IN ITALIANO E IN POCHE PAROLE.
# Una persona legge «Sereno», non «clear sky, code 0». L'elenco è chiuso: una
# condizione che non si sa dire in italiano non si mostra a metà.
COME_SI_DICE = {
    "clear": "Sereno",
    "mainly_clear": "Quasi sereno",
    "partly_cloudy": "Poco nuvoloso",
    "cloudy": "Nuvoloso",
    "fog": "Nebbia",
    "drizzle": "Pioviggine",
    "rain": "Pioggia",
    "snow": "Neve",
    "showers": "Rovesci",
    "thunderstorm": "Temporale",
}

#     «MATTINA SERENA», NON «MATTINA SERENO».
# Metà delle condizioni sono aggettivi e devono accordarsi con il momento
# (mattina, sera e notte sono femminili; pomeriggio no); l'altra metà sono
# sostantivi, e allora si dice «mattina di pioggia». Senza questa tabella la
# riga in alto a destra dell'app parlerebbe male l'italiano tutti i giorni.
COME_SI_ACCORDA = {
    "clear": ("sereno", "serena"),
    "mainly_clear": ("quasi sereno", "quasi serena"),
    "partly_cloudy": ("poco nuvoloso", "poco nuvolosa"),
    "cloudy": ("nuvoloso", "nuvolosa"),
    "fog": ("di nebbia", "di nebbia"),
    "drizzle": ("di pioviggine", "di pioviggine"),
    "rain": ("di pioggia", "di pioggia"),
    "snow": ("di neve", "di neve"),
    "showers": ("di rovesci", "di rovesci"),
    "thunderstorm": ("di temporali", "di temporali"),
}

# I momenti della giornata, con il loro genere.
MOMENTI = (
    (5, "Notte", "f"),
    (13, "Mattina", "f"),
    (18, "Pomeriggio", "m"),
    (24, "Sera", "f"),
)

#     E UN'ICONA PER OGNUNA, DALLO STESSO ELENCO.
CHE_ICONA = {
    "clear": "sunny-outline",
    "mainly_clear": "partly-sunny-outline",
    "partly_cloudy": "partly-sunny-outline",
    "cloudy": "cloud-outline",
    "fog": "cloudy-outline",
    "drizzle": "rainy-outline",
    "rain": "rainy-outline",
    "snow": "snow-outline",
    "showers": "rainy-outline",
    "thunderstorm": "thunderstorm-outline",
}

# I codici WMO che Open-Meteo restituisce, tradotti nelle condizioni di sopra.
_WMO = {
    0: "clear", 1: "mainly_clear", 2: "partly_cloudy", 3: "cloudy",
    45: "fog", 48: "fog",
    51: "drizzle", 53: "drizzle", 55: "drizzle",
    61: "rain", 63: "rain", 65: "rain",
    66: "rain", 67: "rain",
    71: "snow", 73: "snow", 75: "snow", 77: "snow",
    80: "showers", 81: "showers", 82: "showers",
    85: "snow", 86: "snow",
    95: "thunderstorm", 96: "thunderstorm", 99: "thunderstorm",
}


#     IL METEO FUNZIONA, E NON COSTA NIENTE.
# Open-Meteo non chiede chiavi e non si paga: è il servizio predefinito,
# perché un modulo che dice sempre «non disponibile» non è un modulo, è un
# buco con una scusa. Si spegne con `WEATHER_PROVIDER=none`, e si cambia
# servizio mettendone un altro con la sua chiave.
PROVIDER_PREDEFINITO = "open_meteo"


def configured_provider() -> Optional[str]:
    """Quale servizio meteo ha questa installazione, se ne ha uno."""
    provider = (os.environ.get(PROVIDER_ENV) or "").strip().lower()
    if provider in ("none", "off", "disabled"):
        return None
    if not provider:
        provider = PROVIDER_PREDEFINITO
    # open_meteo non chiede chiavi; gli altri sì, e senza chiave non esistono.
    if provider != "open_meteo" and not (os.environ.get(KEY_ENV) or "").strip():
        return None
    return provider


def capabilities() -> Dict[str, Any]:
    """Che cosa si può davvero dire del tempo, detto chiaramente."""
    provider = configured_provider()
    return {
        "available": provider is not None,
        "provider": provider,
        "why_unavailable": (
            None if provider
            else f"meteo spento in questa installazione ({PROVIDER_ENV})"
        ),
    }


def unavailable(reason: str = "") -> Dict[str, Any]:
    """Lo stato neutro: quello che la Home mostra quando ORA non sa il tempo."""
    return {
        "available": False,
        "label": "Meteo non disponibile",
        "why_unavailable": reason or (capabilities()["why_unavailable"] or ""),
    }


async def now_at(*, lat: float, lon: float, place: str = "") -> Dict[str, Any]:
    """
    Il tempo adesso in un punto, dal provider configurato.

    Torna `{"available": False, ...}` quando non c'è niente a cui chiedere, e
    chi chiama deve trattarla come una risposta vera: non esiste un ripiego
    silenzioso, perché un ripiego silenzioso è un'invenzione.
    """
    provider = configured_provider()
    if provider is None:
        return unavailable()
    try:
        if provider == "open_meteo":
            return await _from_open_meteo(lat=lat, lon=lon, place=place)
        return unavailable(f"provider meteo sconosciuto: {provider}")
    except Exception as e:  # pragma: no cover - dipende dalla rete
        logger.info("meteo non disponibile: %s", type(e).__name__)
        return unavailable("il servizio meteo non ha risposto")


async def _from_open_meteo(*, lat: float, lon: float, place: str) -> Dict[str, Any]:
    """Open-Meteo: niente chiave, niente costo, e il codice WMO per la condizione."""
    import httpx

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat:.4f}&longitude={lon:.4f}&current=temperature_2m,weather_code"
    )
    async with httpx.AsyncClient(timeout=6.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        dati = (r.json() or {}).get("current") or {}
    condizione = _WMO.get(int(dati.get("weather_code", -1)), "")
    if not condizione or dati.get("temperature_2m") is None:
        return unavailable("il servizio meteo ha risposto qualcosa che non so leggere")
    return {
        "available": True,
        "condition": condizione,
        # Il momento della giornata è la metà della frase: dice se quel sereno
        # è quello con cui esci adesso o quello che troverai stasera.
        "label": how_it_reads(condizione),
        "condition_label": COME_SI_DICE[condizione],
        "icon": CHE_ICONA[condizione],
        "temperature_c": round(float(dati["temperature_2m"])),
        "place": place or "",
        "why_unavailable": None,
    }


async def forecast_at(*, lat: float, lon: float, place: str = "") -> Dict[str, Any]:
    """
    Il meteo per esteso: adesso, le prossime ore, i prossimi giorni.

        LA STESSA FONTE DELLA RIGA IN ALTO, NON UN SECONDO METEO.

    Chi apre la pagina vuole sapere di più, non qualcosa di diverso: i numeri
    arrivano dalla stessa chiamata, e quello che il servizio non dà non viene
    riempito da nessuna parte.
    """
    provider = configured_provider()
    if provider is None:
        return unavailable()
    if provider != "open_meteo":
        return unavailable(f"il meteo esteso non è disponibile con {provider}")
    try:
        return await _detailed_from_open_meteo(lat=lat, lon=lon, place=place)
    except Exception as e:  # pragma: no cover - dipende dalla rete
        logger.info("meteo esteso non disponibile: %s", type(e).__name__)
        return unavailable("il servizio meteo non ha risposto")


async def _detailed_from_open_meteo(*, lat: float, lon: float, place: str) -> Dict[str, Any]:
    """Adesso, dodici ore, cinque giorni. Niente di più e niente di inventato."""
    import httpx

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat:.4f}&longitude={lon:.4f}"
        "&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
        "wind_speed_10m,precipitation,weather_code"
        "&hourly=temperature_2m,precipitation_probability,weather_code"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,"
        "precipitation_probability_max,sunrise,sunset"
        "&forecast_days=5&timezone=auto"
    )
    async with httpx.AsyncClient(timeout=8.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        dati = r.json() or {}

    adesso = dati.get("current") or {}
    condizione = _WMO.get(int(adesso.get("weather_code", -1)), "")
    if not condizione or adesso.get("temperature_2m") is None:
        return unavailable("il servizio meteo ha risposto qualcosa che non so leggere")

    orarie = dati.get("hourly") or {}
    giornaliere = dati.get("daily") or {}
    da_ora = _from_now(orarie.get("time") or [], str(adesso.get("time") or ""))

    return {
        "available": True,
        "place": place or "",
        "condition": condizione,
        "label": how_it_reads(condizione),
        "condition_label": COME_SI_DICE[condizione],
        "icon": CHE_ICONA[condizione],
        "temperature_c": round(float(adesso["temperature_2m"])),
        #     QUELLO CHE SI SENTE, NON SOLO QUELLO CHE SEGNA IL TERMOMETRO.
        "feels_like_c": _arrotonda(adesso.get("apparent_temperature")),
        "humidity_pct": _arrotonda(adesso.get("relative_humidity_2m")),
        "wind_kmh": _arrotonda(adesso.get("wind_speed_10m")),
        "precipitation_mm": adesso.get("precipitation"),
        "hours": [
            {
                "time": str((orarie.get("time") or [])[i])[11:16],
                "temperature_c": _arrotonda((orarie.get("temperature_2m") or [])[i]),
                "rain_chance_pct": _arrotonda((orarie.get("precipitation_probability") or [None])[i]),
                "icon": CHE_ICONA.get(_WMO.get(int((orarie.get("weather_code") or [0])[i]), ""), ""),
            }
            for i in da_ora[:12]
            if i < len(orarie.get("temperature_2m") or [])
        ],
        "days": [
            {
                "date": str((giornaliere.get("time") or [])[i]),
                "label": _che_giorno((giornaliere.get("time") or [])[i], i),
                "min_c": _arrotonda((giornaliere.get("temperature_2m_min") or [])[i]),
                "max_c": _arrotonda((giornaliere.get("temperature_2m_max") or [])[i]),
                "rain_chance_pct": _arrotonda(
                    (giornaliere.get("precipitation_probability_max") or [None])[i]
                ),
                "condition_label": COME_SI_DICE.get(
                    _WMO.get(int((giornaliere.get("weather_code") or [0])[i]), ""), ""
                ),
                "icon": CHE_ICONA.get(
                    _WMO.get(int((giornaliere.get("weather_code") or [0])[i]), ""), ""
                ),
            }
            for i in range(len(giornaliere.get("time") or []))
        ],
        "sunrise": str((giornaliere.get("sunrise") or [""])[0])[11:16],
        "sunset": str((giornaliere.get("sunset") or [""])[0])[11:16],
        "why_unavailable": None,
    }


def _from_now(orari: list, adesso: str) -> list:
    """Gli indici delle ore che devono ancora venire. Il passato non serve."""
    for i, quando in enumerate(orari):
        if str(quando) >= adesso:
            return list(range(i, len(orari)))
    return []


def _arrotonda(valore: Any) -> Optional[int]:
    try:
        return round(float(valore))
    except (TypeError, ValueError):
        return None


def _che_giorno(quando: Any, indice: int) -> str:
    """«Oggi», «Domani», o il nome del giorno. Mai una data nuda."""
    from datetime import date

    if indice == 0:
        return "Oggi"
    if indice == 1:
        return "Domani"
    try:
        g = date.fromisoformat(str(quando))
    except ValueError:
        return str(quando)
    return ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato",
            "domenica")[g.weekday()]


def _che_momento(ora: Optional[int] = None) -> tuple:
    """Il momento della giornata e il suo genere, dall'ora locale."""
    from datetime import datetime

    h = datetime.now().hour if ora is None else ora
    for limite, nome, genere in MOMENTI:
        if h < limite:
            return nome, genere
    return "Sera", "f"


def how_it_reads(condizione: str, ora: Optional[int] = None) -> str:
    """«Mattina serena», «Pomeriggio nuvoloso», «Sera di pioggia»."""
    momento, genere = _che_momento(ora)
    maschile, femminile = COME_SI_ACCORDA.get(condizione, ("", ""))
    parola = femminile if genere == "f" else maschile
    return f"{momento} {parola}".strip() if parola else momento
