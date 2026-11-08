"""8/11: «Ho appena steso i panni» got a status report about an unscheduled check."""
from conversation_engine.ai_core.loop import _with_situation_handoff, drying_sentence


def test_the_answer_is_the_forecast_said_plainly():
    text = drying_sentence({"dry_at_local": "17:10", "place": "Tarquinia", "weather": "14–16 °C"})
    assert text.startswith("Con il meteo di oggi a Tarquinia (14–16 °C) dovrebbero essere asciutti verso le 17:10: ti avviso io.")
    assert "stima" in text


def test_not_today_and_rain_are_said():
    t = drying_sentence({"not_today": True, "at_local": "16:35", "done_fraction_by_evening": 0.7,
                         "rain_at_local": "16:00"})
    assert "non si asciugano del tutto prima di sera" in t and "16:35" in t and "70%" in t
    assert "pioggia verso le 16:00" in t


def test_the_model_status_report_is_replaced():
    out = _with_situation_handoff(
        "Per «Panni appena stesi»: ORA ha preso in carico la valutazione di questa situazione…",
        {"status": "success", "operation": "create", "follow_up": {"status": "review_pending"},
         "stated_reminder": {"drying": True, "dry_at_local": "17:10"}})
    assert "preso in carico" not in out and "non risulta ancora programmato" not in out
    assert "17:10" in out
