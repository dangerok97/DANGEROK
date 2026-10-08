"""Production route-advice guard: bounded factual rewrites."""
import pytest

from conversation_engine.ai_core.grounding.advice import (
    guard_route_advice, unsupported_traffic_claims,
)

ROUTE = [{"name": "get_route", "payload": {
    "status": "ok", "duration_seconds": 842,
    "reflects_current_traffic": True,
}}]


@pytest.mark.parametrize("claim", [
    "Ti consiglio di partire ora per evitare il traffico.",
    "Il traffico è favorevole: conviene partire adesso.",
    "Partire subito ti permette di sfruttare il tempo di percorrenza attuale.",
    "Non ho confrontato gli orari, ma il traffico è favorevole.",
])
def test_unsupported_traffic_comparison_rewritten(claim):
    safe, findings = guard_route_advice(claim, ROUTE)
    assert findings == ["UNSUPPORTED_TRAFFIC_COMPARISON"]
    assert claim not in safe
    assert "non ho confrontato orari di partenza diversi" in safe
    assert unsupported_traffic_claims(safe, ROUTE) == []


def test_current_eta_without_future_claim_is_untouched():
    answer = ("Il percorso ora richiede circa 14 minuti. "
              "Non posso dire se partire più tardi riduca il traffico.")
    assert guard_route_advice(answer, ROUTE) == (answer, [])


def test_no_route_has_no_automatic_rewrite():
    phrase = "Traffico favorevole."
    assert guard_route_advice(phrase, []) == (phrase, [])


def test_static_baseline_is_not_a_future_departure_comparison():
    data = [{"name": "get_route", "payload": {
        **ROUTE[0]["payload"], "duration_without_traffic_seconds": 700,
    }}]
    assert guard_route_advice("Traffico favorevole.", data)[1]


def test_verified_multi_departure_comparison_can_be_used():
    data = [{"name": "get_route", "payload": {
        **ROUTE[0]["payload"], "departure_time_comparison": {
            "verified": True, "departures": [
                {"departure_at": "2026-10-08T15:00", "estimated_seconds": 1200, "source": "provider"},
                {"departure_at": "2026-10-08T16:00", "estimated_seconds": 900, "source": "provider"},
            ],
        },
    }}]
    assert guard_route_advice("Traffico favorevole.", data)[1] == []
