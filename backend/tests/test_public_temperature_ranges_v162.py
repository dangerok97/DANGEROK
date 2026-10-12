"""Range punctuation must not invent a sign or hide an unsupported endpoint."""
from copy import deepcopy

import pytest

from scripts.phase1_semantic_gate import review_trip_answer
from scripts.phase1_semantic_numeric import discrepancies


def weather(*temperatures):
    return {
        "status": "ok",
        "current": {"temperature_c": temperatures[0]} if temperatures else {},
        "hours": [{"temperature_c": value} for value in temperatures[1:]],
    }


def test_original_630_answer_has_supported_temperature_numbers_only():
    # Exact saved answer, with the observed route and numeric weather facts.
    # This replay tests numeric extraction, not the unsupported certainty of
    # "senza possibilità di pioggia" or the human acceptance of the answer.
    answer = (
        "Ho verificato il tragitto in auto da Roma Termini al Colosseo. "
        "La distanza è di circa 2.765 metri e la durata stimata è di circa 11 minuti, "
        "considerando il traffico attuale. Per quanto riguarda il meteo, attualmente "
        "ci sono poche nuvole con una temperatura di 23°C e umidità al 58%. "
        "Nelle prossime ore, la temperatura dovrebbe rimanere intorno ai 23-24°C "
        "senza possibilità di pioggia. Ti consiglio di partire ora per evitare eventuali ritardi."
    )
    forecast = weather(23, 23, 24, 24, 24, 23, 22, 20, 19, 18, 17, 17, 16)
    forecast["current"]["humidity_pct"] = 58
    for hour, humidity in zip(forecast["hours"], (60, 55, 55, 54, 54, 57, 59, 62, 67, 67, 66, 69)):
        hour.update(humidity_pct=humidity, rain_chance_pct=0)
    observations = [
        {"capability": "get_route", "payload": {
            "status": "ok", "duration_seconds": 659, "distance_meters": 2765,
            "reflects_current_traffic": True,
        }},
        {"capability": "get_weather_forecast", "payload": forecast},
    ]
    original = deepcopy(observations)

    result = review_trip_answer(answer, observations)

    assert "TEMPERATURE_MISMATCH" not in result["reasons"], result
    assert "ETA_MISMATCH" not in result["reasons"], result
    assert result["automatically_accepted"] is False
    assert result["human_review_still_required"] is True
    assert observations == original


@pytest.mark.parametrize(("text", "temperatures"), [
    ("23-24°C", (23, 24)),
    ("23–24 °C", (23, 24)),
    ("23°C - 24°C", (23, 24)),
    ("-5--2°C", (-5, -2)),
    ("-5 – -2 °C", (-5, -2)),
    ("−5—−2 °C", (-5, -2)),
    ("-2-+3°C", (-2, 3)),
    ("-2,5–+3,5°C", (-2.5, 3.5)),
    ("+0.5 - +2.5 °C", (0.5, 2.5)),
])
def test_supported_ranges_preserve_both_signed_decimal_endpoints(text, temperatures):
    assert "TEMPERATURE_MISMATCH" not in discrepancies(text, {}, weather(*temperatures))


@pytest.mark.parametrize(("text", "temperatures"), [
    ("99–24°C", (23, 24)),
    ("23–99°C", (23, 24)),
    ("-99–-2°C", (-5, -2)),
    ("-5–+99°C", (-5, -2)),
    ("-2,5–+3,5°C", (-2.5,)),
    ("-2,5–+3,5°C", (3.5,)),
    ("99°C - 24°C", (23, 24)),
])
def test_one_supported_endpoint_does_not_hide_the_other(text, temperatures):
    assert "TEMPERATURE_MISMATCH" in discrepancies(text, {}, weather(*temperatures))


@pytest.mark.parametrize(("text", "temperatures", "mismatch"), [
    ("10–12°C", (11,), False),
    ("10–12°C", (11.11,), True),
    ("10–12°C", (10.89,), True),
    ("-5°C", (-5,), False),
    ("-5°C", (5,), True),
    ("23–24°C", (), True),
])
def test_existing_tolerance_signed_scalars_and_missing_evidence(text, temperatures, mismatch):
    assert ("TEMPERATURE_MISMATCH" in discrepancies(text, {}, weather(*temperatures))) is mismatch
