"""Conservative, evidence-based audit of one synthetic journey answer."""
from __future__ import annotations

import re
from conversation_engine.ai_core.grounding.advice import unsupported_traffic_claims
from scripts.phase1_semantic_numeric import discrepancies as numerical_discrepancies
from scripts.phase1_semantic_weather import discrepancies as forecast_discrepancies


def review_trip_answer(answer, observations, *, grounding_rewrites=0):
    rows = list(observations)
    payloads = {r.get("capability"): r.get("payload", {}) for r in rows if isinstance(r, dict)}
    route = payloads.get("get_route", {})
    weather = payloads.get("get_weather_forecast", {})
    issues = list(unsupported_traffic_claims(answer, rows))
    issues.extend(numerical_discrepancies(str(answer or ""), route, weather))
    issues.extend(forecast_discrepancies(str(answer or ""), weather))
    if grounding_rewrites:
        issues.append("MODEL_CLAIM_REWRITTEN")
    if not str(answer or "").strip():
        issues.append("EMPTY_ANSWER")
    eta = route.get("duration_seconds")
    if not isinstance(eta, (int, float)) or isinstance(eta, bool) or eta <= 0:
        issues.append("NO_ROUTE_EVIDENCE")
    else:
        compound_pattern = r"(\d+)\s*minuti?\s+e\s+(\d+)\s*secondi?"
        compounds = re.findall(compound_pattern, answer, re.I)
        remaining = re.sub(compound_pattern, "", answer, flags=re.I)
        times = re.findall(r"(\d+)\s*(minuti?|min|secondi?)", remaining, re.I)
        if not times and not compounds:
            issues.append("MISSING_ETA")
        for minutes, seconds_part in compounds:
            if abs(int(minutes) * 60 + int(seconds_part) - eta) > max(75, eta * 0.12):
                issues.append("ETA_MISMATCH")
                break
        for raw, unit in times:
            seconds = int(raw) if unit.lower().startswith("second") else int(raw) * 60
            if abs(seconds - eta) > max(75, eta * 0.12):
                issues.append("ETA_MISMATCH")
                break
    if weather.get("status") != "ok":
        issues.append("NO_WEATHER_EVIDENCE")
    if not re.search(r"meteo|pioggia|rovesci|temperatura|weather|rain", answer, re.I):
        issues.append("NO_WEATHER_SUMMARY")
    issues = list(dict.fromkeys(issues))
    return {"status": "failed" if issues else "bounded_pass", "passed": not issues,
            "reasons": issues, "automatically_accepted": False,
            "human_review_still_required": True}
