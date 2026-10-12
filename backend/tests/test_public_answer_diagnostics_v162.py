"""Keep original model copy observable; do not credit a rewritten answer.

The final wording below is the unmodified 636c0f7 public report (SHA256
e4f286a1381c25eedab6bba17fd4f1e50f1722ee2b9f2e69e8651020b0e0a3ce).
Replaying a pure check does not change that historical report or its verdict.
All integration I/O is the existing public runner's scripted HTTP boundary.
"""
from copy import deepcopy
import hashlib
import json

import pytest

from scripts import phase1_read_provider_eval as runner
from scripts.phase1_semantic_gate import review_trip_answer
from scripts.phase1_semantic_weather import discrepancies


FINAL_636 = (
    "Per Colosseo il percorso dura circa 12 minuti secondo la stima con il traffico attuale, per circa 2,8 km. "
    "Non ho confrontato altri orari di partenza: non posso indicare il momento migliore per il traffico. "
    "Il meteo osservato dal provider indica poco nuvoloso e 23 °C. "
    "La prima previsione oraria disponibile segnala probabilità di pioggia del 0%: non è una misura dell'intensità."
)
WEATHER = {"status": "ok", "current": {"temperature_c": 23}, "hours": [
    {"datetime": "2026-10-12T14:00", "temperature_c": 23, "rain_chance_pct": 0},
]}
OBSERVATIONS = [
    {"capability": "get_route", "payload": {"status": "ok", "duration_seconds": 699,
        "distance_meters": 2765, "reflects_current_traffic": True}},
    {"capability": "get_weather_forecast", "payload": WEATHER},
]


def test_exact_636_final_is_not_a_claim_of_forecast_intensity():
    assert discrepancies(FINAL_636, WEATHER) == []
    review = review_trip_answer(FINAL_636, OBSERVATIONS, grounding_rewrites=1)
    assert review["passed"] is False
    assert review["reasons"] == ["MODEL_CLAIM_REWRITTEN"]
    assert review["automatically_accepted"] is False


@pytest.mark.parametrize("answer", [
    "Probabilità di pioggia 0%: non è una misura dell'intensità.",
    "La probabilità di pioggia non indica l'intensità.",
    "Pioggia: dati di intensità non disponibili.",
    "Non si può stabilire l'intensità delle precipitazioni.",
])
def test_intensity_as_an_unknown_quantity_is_not_an_intense_forecast(answer):
    assert discrepancies(answer, WEATHER) == []


@pytest.mark.parametrize("answer", [
    "La pioggia si intensifica nel pomeriggio.",
    "La pioggia diventerà più forte.",
    "La pioggia sarà più forte.",
    "Sono previsti rovesci intensi.",
    "Sono previsti intensi rovesci.",
    "Sono previste forti piogge.",
    "La pioggia avrà intensità elevata.",
    "Pioggia intensissima nel pomeriggio.",
    "Precipitazioni in intensificazione.",
])
def test_actual_unsupported_intensity_claims_still_fail(answer):
    assert discrepancies(answer, WEATHER) == ["UNVERIFIED_FORECAST_INTENSITY"]


def test_explicit_hourly_intensity_keeps_existing_evidence_behavior():
    weather = deepcopy(WEATHER)
    weather["hours"][0]["intensity"] = "forte"
    assert discrepancies("La pioggia avrà intensità forte.", weather) == []


@pytest.mark.parametrize(("raw", "kind", "present"), [
    ({}, "missing", False),
    ({"message_to_user": None}, "null", True),
    ({"message_to_user": False}, "boolean", True),
    ({"message_to_user": 0}, "number", True),
    ({"message_to_user": ["first", None, 0]}, "array", True),
    ({"message_to_user": {"summary": "Originale", "details": [False, None, 0]}}, "object", True),
])
def test_parsed_message_type_is_recorded_without_coercing_the_decision(raw, kind, present):
    original = deepcopy(raw)
    observation = runner._model_message_observation(raw, decision_index=4)
    assert raw == original
    assert observation["decision_index"] == 4
    assert observation["field_present"] is present
    assert observation["value_type"] == kind
    if present:
        assert json.loads(observation["text"]) == raw["message_to_user"]
        assert observation["text_truncated"] is False


def test_untruncated_model_copy_preserves_whitespace_unicode_length_and_hash():
    text = "  Dati del modello: 23 °C.\nSeconda riga: è una stima.  "
    raw = {"message_to_user": text}
    observation = runner._model_message_observation(raw, decision_index=3)
    assert observation["text"] == text
    assert observation["value_type"] == "string"
    assert observation["representation"] == "literal_string"
    assert observation["characters"] == len(text)
    assert observation["sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert observation["redacted_sha256"] == observation["sha256"]
    assert observation["text_truncated"] is False
    assert observation["redacted"] is False
    assert raw == {"message_to_user": text}


def test_redaction_precedes_limit_and_hashes_cover_the_full_representations(monkeypatch):
    secret = "TEST-SECRET-636-ONLY-12345"
    monkeypatch.setenv("GEMINI_API_KEY_2", secret)
    text = "x" * (runner.FINAL_ANSWER_LIMIT - 6) + secret + "tail" * 100
    redacted = text.replace(secret, "[credential redacted]")
    observation = runner._model_message_observation({"message_to_user": text}, decision_index=1)
    assert observation["text"] == redacted[:runner.FINAL_ANSWER_LIMIT]
    assert secret not in json.dumps(observation)
    assert secret[:6] not in observation["text"]
    assert observation["characters"] == len(text)
    assert observation["redacted_characters"] == len(redacted)
    assert observation["sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert observation["redacted_sha256"] == hashlib.sha256(redacted.encode()).hexdigest()
    assert observation["redacted"] is True
    assert observation["text_truncated"] is True


def test_real_grounding_events_are_allowlisted_and_bounded():
    steps = [{"event": "PRIVATE_UNKNOWN", "findings": ["do-not-export"]}]
    steps += [{"event": "GROUNDING_WEATHER_REWRITTEN", "findings": [
        "UNVERIFIED_FORECAST_INTENSITY", "do-not-export", {"private": "data"},
    ]} for _ in range(15)]
    original = deepcopy(steps)
    observed, omitted = runner._grounding_event_observations(steps)
    assert len(observed) == 12 and omitted == 3
    assert observed[0] == {"trace_step": 1, "event": "GROUNDING_WEATHER_REWRITTEN",
                           "findings": ["UNVERIFIED_FORECAST_INTENSITY"]}
    assert "do-not-export" not in json.dumps(observed)
    assert steps == original


@pytest.mark.asyncio
async def test_real_scripted_loop_retains_copy_before_last_step_formatting():
    reference = await runner._scripted_model_factory()
    text = '{"summary": "Testo del modello prima del renderer", "details": ["non è una fonte"]}'
    answers = []

    async def decide(system, user):
        raw = await reference(system, user)
        if raw.get("response_mode") == "answer":
            raw["message_to_user"] = text
            answers.append(raw)
        return raw

    # No extra pass remains: this proves the actual bounded fallback and its
    # trace independently of any future cognitive recovery before the bound.
    report = await runner.run_case(mode="scripted", decide=decide, max_steps=3)
    message = report["model_message_observations"][-1]
    assert message["text"] == text and message["text_truncated"] is False
    assert message["sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert message["characters"] == len(text)
    assert answers[-1]["message_to_user"] == text
    assert report["final_answer"] != text
    assert "Testo del modello" not in report["final_answer"]
    assert any(row["event"] == "GROUNDING_MESSAGE_RENDERED" and
               row["findings"] == ["STRUCTURED_MESSAGE_RENDERED_FROM_EVIDENCE"]
               for row in report["grounding_events"])
    assert report["semantic_review"]["grounding_rewrites"] == 1
    assert report["semantic_review"]["reasons"] == ["MODEL_CLAIM_REWRITTEN"]
    assert report["verdict"]["technical_passed"] is True
    assert report["verdict"]["passed"] is False
    assert report["verdict"]["ai_calls"] == 3
    assert report["verdict"]["tool_calls"] == 2
    assert report["real_model_executed"] is False
    assert report["blocked_operations"] == []


@pytest.mark.asyncio
async def test_diagnostic_failure_cannot_change_valid_answer_or_call_budget(monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("private observation must not be exported")

    monkeypatch.setattr(runner, "_model_message_observation", fail)
    report = await runner.run_case(mode="scripted")
    assert report["verdict"]["passed"] is True
    assert report["verdict"]["ai_calls"] == 3
    assert report["verdict"]["tool_calls"] == 2
    assert report["real_model_executed"] is False
    assert report["blocked_operations"] == []
    assert all(row["diagnostic_error_type"] == "ValueError"
               for row in report["model_message_observations"])
    assert "private observation" not in json.dumps(report)


@pytest.mark.asyncio
async def test_model_repair_is_observed_as_a_request_without_counting_it_as_rewrite():
    reference = await runner._scripted_model_factory()
    calls = 0
    rejected = '{"summary": "Correggere questa forma", "details": []}'

    async def decide(system, user):
        nonlocal calls
        calls += 1
        raw = await reference(system, user)
        if calls == 3:
            raw["message_to_user"] = rejected
        return raw

    report = await runner.run_case(mode="scripted", decide=decide, max_steps=5)
    assert report["model_message_observations"][2]["text"] == rejected
    assert report["model_message_observations"][3]["text"] == report["final_answer"]
    assert [row["event"] for row in report["grounding_events"]] == ["GROUNDING_REPLY_REPAIR_REQUESTED"]
    assert report["grounding_events"][0]["findings"] == ["STRUCTURED_MESSAGE_RENDERED_FROM_EVIDENCE"]
    assert report["semantic_review"]["grounding_rewrites"] == 0
    assert report["verdict"]["passed"] is True
    assert report["verdict"]["ai_calls"] == calls == 4
    assert report["verdict"]["tool_calls"] == 2


@pytest.mark.asyncio
async def test_real_object_before_governance_is_distinct_from_serialized_string():
    reference = await runner._scripted_model_factory()
    calls = 0
    rejected = {"summary": "Parsed object; not a prose string", "details": [0, False, None]}

    async def decide(system, user):
        nonlocal calls
        calls += 1
        raw = await reference(system, user)
        if calls == 3:
            raw["message_to_user"] = rejected
        return raw

    report = await runner.run_case(mode="scripted", decide=decide, max_steps=4)
    observed = report["model_message_observations"][2]
    assert observed["value_type"] == "object"
    assert observed["representation"] == "parsed_json_value"
    assert json.loads(observed["text"]) == rejected
    assert observed["text_truncated"] is False
    assert [row["event"] for row in report["grounding_events"]] == ["AI_DECISION_RETRY"]
    assert report["grounding_events"][0]["mode"] == "answer"
    assert report["semantic_review"]["grounding_rewrites"] == 0
    assert report["verdict"]["passed"] is True
    assert report["verdict"]["ai_calls"] == calls == 4
    assert report["verdict"]["tool_calls"] == 2
