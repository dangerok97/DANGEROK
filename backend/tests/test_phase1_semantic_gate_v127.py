"""Evidence-grounded semantic gate: technical tool success alone is insufficient."""
import pytest

from scripts.phase1_semantic_gate import review_trip_answer


@pytest.fixture
def observations():
    return [
        {"capability": "get_route", "payload": {
            "status": "ok", "duration_seconds": 842, "distance_meters": 2765,
            "reflects_current_traffic": True,
        }},
        {"capability": "get_weather_forecast", "payload": {
            "status": "ok", "provider": "open_meteo",
            "current": {"condition": "Rovesci", "temperature_c": 25, "humidity_pct": 72},
            "hours": [
                {"datetime": "2026-10-08T15:00", "temperature_c": 24, "rain_chance_pct": 75},
                {"datetime": "2026-10-08T16:00", "temperature_c": 22, "rain_chance_pct": 66},
            ],
        }},
    ]


def test_bounded_claims_pass_but_do_not_replace_human_review(observations):
    text = ("Il percorso attuale è di circa 14 minuti per 2,7 km. "
            "Meteo: 25 °C ora e probabilità di pioggia 75% alle 15:00. "
            "Non ho confrontato gli orari di partenza.")
    review = review_trip_answer(text, observations)
    assert review["status"] == "bounded_pass", review
    assert review["automatically_accepted"] is False
    assert review["human_review_still_required"] is True


@pytest.mark.parametrize(("text", "reason"), [
    ("Parti ora per evitare il traffico. Viaggio 14 minuti. Meteo: 25 °C.",
     "UNSUPPORTED_TRAFFIC_COMPARISON"),
    ("Il traffico è favorevole. Viaggio 14 minuti. Meteo: 25 °C.",
     "UNSUPPORTED_TRAFFIC_COMPARISON"),
    ("Il viaggio richiede 27 minuti. Meteo: 25 °C.", "ETA_MISMATCH"),
    ("Il viaggio richiede 14 minuti per 10 km. Meteo: 25 °C.", "DISTANCE_MISMATCH"),
    ("Il viaggio richiede 14 minuti. Meteo: 7 °C.", "TEMPERATURE_MISMATCH"),
    ("Il viaggio richiede 14 minuti. Meteo: pioggia 95%.", "PERCENTAGE_MISMATCH"),
    ("Il viaggio richiede 14 minuti. Meteo: la pioggia si intensifica.",
     "UNVERIFIED_FORECAST_INTENSITY"),
    ("Meteo 25 °C, strada per il Colosseo.", "MISSING_ETA"),
])
def test_false_or_unverifiable_claim_blocks_acceptance(observations, text, reason):
    review = review_trip_answer(text, observations)
    assert review["passed"] is False
    assert reason in review["reasons"], review


def test_a_rewritten_model_claim_is_not_treated_as_clean_model_output(observations):
    answer = "Percorso circa 14 minuti. Meteo: 25 °C."
    review = review_trip_answer(answer, observations, grounding_rewrites=1)
    assert "MODEL_CLAIM_REWRITTEN" in review["reasons"]
