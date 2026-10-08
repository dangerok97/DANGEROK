"""Numerical cross-check for the bounded public-landmark evaluation."""
import math
import re


def number(raw, unit=""):
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", str(raw)) and unit == "metri":
        raw = str(raw).replace(".", "")
    try:
        value = float(str(raw).replace(",", "."))
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def discrepancies(answer, route, weather):
    problems = []
    distance = number(route.get("distance_meters"))
    if distance is not None:
        for raw, unit in re.findall(r"([\d.,]+)\s*(km|metri)\b", answer, re.I):
            value = number(raw, unit.lower())
            if value is None:
                problems.append("INVALID_DISTANCE")
            elif abs((value * 1000 if unit.lower() == "km" else value) - distance) > max(250, distance * 0.13):
                problems.append("DISTANCE_MISMATCH")
    current = weather.get("current") or {}
    hours = [h for h in weather.get("hours", []) if isinstance(h, dict)]
    temps = [number(h.get("temperature_c")) for h in [current, *hours]]
    temps = [v for v in temps if v is not None]
    for raw in re.findall(r"(-?\d+(?:[.,]\d+)?)\s*°\s*C?", answer):
        value = number(raw)
        if not temps or value is None or all(abs(value - t) > 1.1 for t in temps):
            problems.append("TEMPERATURE_MISMATCH")
            break
    percentages = [number(h.get(key)) for h in [current, *hours]
                   for key in ("humidity_pct", "rain_chance_pct")]
    percentages = [v for v in percentages if v is not None]
    for raw in re.findall(r"(\d+(?:[.,]\d+)?)\s*%", answer):
        value = number(raw)
        if not percentages or value is None or all(abs(value - p) > 2 for p in percentages):
            problems.append("PERCENTAGE_MISMATCH")
            break
    return problems
