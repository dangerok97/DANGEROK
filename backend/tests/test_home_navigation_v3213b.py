"""
V3.21.3b — il meteo che non si inventa, e l'agenda che è una cosa sua.

    «METEO NON DISPONIBILE» È UNA RISPOSTA. UN GRADO INVENTATO È UN DANNO.
    UN'AGENDA NON È UN RIASSUNTO DELLA SITUAZIONE.

Due decisioni di questo sprint vivono nel backend e sono tenute ferme qui.
"""

from __future__ import annotations

import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from test_post_call_application_v315 import FintoDb  # noqa: E402


# ===========================================================================
# 1 · Il meteo
# ===========================================================================

def test_the_weather_is_on_by_default_and_costs_nothing(monkeypatch):
    """
    Un modulo che dice sempre «non disponibile» non è un modulo: è un buco con
    una scusa. Open-Meteo non chiede chiavi e non si paga, quindi è acceso.
    """
    import weather

    monkeypatch.delenv(weather.PROVIDER_ENV, raising=False)
    capacita = weather.capabilities()
    assert capacita["available"] is True
    assert capacita["provider"] == "open_meteo"


def test_the_weather_can_be_switched_off_and_then_says_so(monkeypatch):
    import weather

    monkeypatch.setenv(weather.PROVIDER_ENV, "none")
    capacita = weather.capabilities()
    assert capacita["available"] is False
    assert weather.PROVIDER_ENV in (capacita["why_unavailable"] or "")

    stato = weather.unavailable()
    assert stato["available"] is False
    assert stato["label"] == "Meteo non disponibile"


def test_a_provider_that_needs_a_key_does_not_count_without_one(monkeypatch):
    """Una chiave mancante non è «configurato a metà»: è non configurato."""
    import weather

    monkeypatch.setenv(weather.PROVIDER_ENV, "openweather")
    monkeypatch.delenv(weather.KEY_ENV, raising=False)
    assert weather.configured_provider() is None

    monkeypatch.setenv(weather.KEY_ENV, "abc")
    assert weather.configured_provider() == "openweather"


@pytest.mark.asyncio
async def test_a_switched_off_weather_asks_nobody_anything(monkeypatch):
    import weather

    monkeypatch.setenv(weather.PROVIDER_ENV, "none")

    async def non_si_chiama(*_a, **_k):  # pragma: no cover
        raise AssertionError("ha chiesto il meteo con il modulo spento")

    monkeypatch.setattr(weather, "_from_open_meteo", non_si_chiama)
    stato = await weather.now_at(lat=45.46, lon=9.19, place="Milano")
    assert stato["label"] == "Meteo non disponibile"


def test_the_weather_speaks_italian_properly():
    """
    «Mattina sereno» è sbagliato, e sarebbe sbagliato tutti i giorni: metà
    delle condizioni sono aggettivi e devono accordarsi con il momento.
    """
    import weather

    assert weather.how_it_reads("clear", 8) == "Mattina serena"
    assert weather.how_it_reads("cloudy", 8) == "Mattina nuvolosa"
    assert weather.how_it_reads("clear", 15) == "Pomeriggio sereno"
    assert weather.how_it_reads("cloudy", 15) == "Pomeriggio nuvoloso"
    assert weather.how_it_reads("rain", 20) == "Sera di pioggia"
    assert weather.how_it_reads("snow", 2) == "Notte di neve"


def test_every_condition_can_be_said_in_both_genders():
    import weather

    for condizione in weather.COME_SI_DICE:
        assert condizione in weather.COME_SI_ACCORDA, condizione
        maschile, femminile = weather.COME_SI_ACCORDA[condizione]
        assert maschile and femminile


@pytest.mark.asyncio
async def test_the_weather_looks_where_the_person_actually_is(monkeypatch):
    """
    La posizione è quella vera del telefono, non un indirizzo scritto a mano:
    è il GPS che già alimenta la presenza.
    """
    import weather
    from home.service import HomeService

    class FintaPresenza:
        latitude = 45.4642
        longitude = 9.19
        place_locality = "Milano"
        place_municipality = None
        place_label = "Casa"

    class FintoServizio:
        def __init__(self, *_a, **_k):
            pass

        async def build_presence(self, *_a, **_k):
            return FintaPresenza()

    import location.service as location_service

    monkeypatch.setattr(location_service, "LocationService", FintoServizio)
    monkeypatch.delenv(weather.PROVIDER_ENV, raising=False)

    visto = {}

    async def finto_meteo(*, lat, lon, place):
        visto.update(lat=lat, lon=lon, place=place)
        return {"available": True, "label": "Mattina serena", "place": place}

    monkeypatch.setattr(weather, "now_at", finto_meteo)
    stato = await HomeService(FintoDb())._weather_now("u1")

    assert visto == {"lat": 45.4642, "lon": 9.19, "place": "Milano"}
    assert stato["available"] is True


def test_every_condition_has_italian_words_and_an_icon():
    """Una condizione che non si sa dire in italiano non si mostra a metà."""
    import weather

    for codice, condizione in weather._WMO.items():
        assert condizione in weather.COME_SI_DICE, codice
        assert condizione in weather.CHE_ICONA, codice


@pytest.mark.asyncio
async def test_home_without_a_place_says_which_of_the_two_is_missing(monkeypatch):
    """
    «Non ho un provider» e «non so dove sei» sono due mancanze diverse:
    confonderle nasconde quella che si può ancora risolvere.
    """
    import weather
    from home.service import HomeService

    monkeypatch.setenv(weather.PROVIDER_ENV, "open_meteo")
    servizio = HomeService(FintoDb())
    stato = await servizio._weather_now("u1")
    assert stato["available"] is False
    assert "dove sei" in (stato["why_unavailable"] or "")


def test_the_detailed_forecast_only_looks_forward():
    """Le ore già passate non servono a chi apre il meteo adesso."""
    import weather

    orari = ["2026-09-21T08:00", "2026-09-21T09:00", "2026-09-21T10:00", "2026-09-21T11:00"]
    assert weather._from_now(orari, "2026-09-21T10:00") == [2, 3]
    # Un orario oltre l'ultimo campione non inventa ore che non ci sono.
    assert weather._from_now(orari, "2026-09-22T00:00") == []


def test_days_are_named_the_way_a_person_names_them():
    import weather

    assert weather._che_giorno("2026-09-21", 0) == "Oggi"
    assert weather._che_giorno("2026-09-22", 1) == "Domani"
    assert weather._che_giorno("2026-09-23", 2) == "mercoledì"


def test_a_missing_number_stays_missing():
    """Un dato che il servizio non dà non diventa uno zero."""
    import weather

    assert weather._arrotonda(None) is None
    assert weather._arrotonda("") is None
    assert weather._arrotonda(25.6) == 26


@pytest.mark.asyncio
async def test_the_detailed_forecast_is_off_when_the_weather_is(monkeypatch):
    import weather

    monkeypatch.setenv(weather.PROVIDER_ENV, "none")
    stato = await weather.forecast_at(lat=45.4, lon=9.1, place="Milano")
    assert stato["available"] is False
    assert stato["label"] == "Meteo non disponibile"


# ===========================================================================
# 2 · L'agenda
# ===========================================================================

def _evento(quando: str, titolo: str = "Dentista", **extra):
    attrs = {"starts_at": quando, "ends_at": None, "location": "", **extra}
    return {"id": f"ev_{quando[:10]}_{titolo[:4]}", "label": titolo, "attributes": attrs,
            "user_id": "u1", "type": "event", "status": "active"}


@pytest.mark.asyncio
async def test_the_agenda_keeps_the_empty_days(monkeypatch):
    """
    Un'agenda che salta i giorni liberi fa sembrare pieno un calendario che è
    vuoto — ed è proprio l'informazione che sta cercando chi la apre.
    """
    from agenda.service import AgendaService

    db = FintoDb()
    service = AgendaService(db)
    dati = await service.days_ahead("u1", days=5)

    assert len(dati["days"]) == 5
    assert dati["total_events"] == 0
    assert dati["days"][0]["label"] == "Oggi"
    assert dati["days"][1]["label"] == "Domani"
    assert dati["days"][0]["is_today"] is True
    # Il terzo giorno si chiama per nome, non «fra tre giorni».
    assert any(m in dati["days"][2]["label"] for m in ("gennaio", "febbraio", "marzo", "aprile",
                                                       "maggio", "giugno", "luglio", "agosto",
                                                       "settembre", "ottobre", "novembre", "dicembre"))


@pytest.mark.asyncio
async def test_events_land_on_their_day_and_say_their_hour():
    from datetime import datetime, timedelta, timezone

    from agenda.service import AgendaService

    domani = (datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=9, minute=30)
    db = FintoDb()
    db.life_nodes.righe.append(_evento(
        domani.isoformat(),
        "Studio Dentistico",
        ends_at=(domani + timedelta(minutes=30)).isoformat(),
        location="Via Roma 1",
        connector_id="calendar_google",
    ))

    dati = await AgendaService(db).days_ahead("u1", days=3)
    giorno = dati["days"][1]
    assert giorno["label"] == "Domani"
    assert len(giorno["events"]) == 1
    e = giorno["events"][0]
    assert e["title"] == "Studio Dentistico"
    assert e["time_label"] == "09:30 — 10:00"
    assert e["location"] == "Via Roma 1"
    assert e["source_label"] == "Google Calendar"
    assert dati["total_events"] == 1


@pytest.mark.asyncio
async def test_an_all_day_event_does_not_pretend_to_have_an_hour():
    from datetime import datetime, timezone

    from agenda.service import AgendaService

    oggi = datetime.now(timezone.utc).replace(hour=0, minute=0)
    db = FintoDb()
    db.life_nodes.righe.append(_evento(oggi.isoformat(), "Ferie", all_day=True))

    dati = await AgendaService(db).days_ahead("u1", days=1)
    assert dati["days"][0]["events"][0]["time_label"] == "Tutto il giorno"


@pytest.mark.asyncio
async def test_ora_says_what_it_has_to_do_with_an_appointment_only_when_it_does():
    """
    «L'ho aggiunto io da un documento» è un fatto che si legge nei dati. Una
    riga che comparisse su ogni appuntamento non direbbe niente.
    """
    from datetime import datetime, timezone

    from agenda.service import AgendaService

    oggi = datetime.now(timezone.utc).replace(hour=11, minute=0)
    db = FintoDb()
    mio = _evento(oggi.isoformat(), "Visita")
    db.life_nodes.righe.append(mio)
    db.calendar_event_drafts.righe.append(
        {"id": mio["id"], "user_id": "u1", "source_document_id": "doc_1"}
    )

    dati = await AgendaService(db).days_ahead("u1", days=1)
    assert "documento" in dati["days"][0]["events"][0]["ora_note"]

    # Senza bozza e senza telefonata, ORA non ha niente da dire.
    db2 = FintoDb()
    db2.life_nodes.righe.append(_evento(oggi.isoformat(), "Cena"))
    dati2 = await AgendaService(db2).days_ahead("u1", days=1)
    assert dati2["days"][0]["events"][0]["ora_note"] == ""


@pytest.mark.asyncio
async def test_the_agenda_never_returns_more_than_two_weeks():
    """Il limite esiste perché una richiesta sbagliata non diventi un'estrazione."""
    from agenda.service import AgendaService, MAX_DAYS

    dati = await AgendaService(FintoDb()).days_ahead("u1", days=999)
    assert len(dati["days"]) == MAX_DAYS
