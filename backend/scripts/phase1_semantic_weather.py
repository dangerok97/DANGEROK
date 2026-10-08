"""Forecast semantics: a rain probability does not establish severity."""
import re


def discrepancies(answer, weather):
    hours = [h for h in weather.get("hours", []) if isinstance(h, dict)]
    has_future_intensity = any(h.get("precipitation_mm") is not None or h.get("intensity") for h in hours)
    unsupported = re.search(
        r"(?:pioggia|rovesci|precipitazioni).{0,55}(?:si\s+intensific\w*|"
        r"diventer\w*\s+pi[uù]\s+fort\w*|sar[aà]\s+pi[uù]\s+fort\w*|forti|intensi|"
        r"intensif\w*|intensit[aà]\s+(?:moderata|crescente|forte|elevata|alta))|"
        r"(?:forti|intensi)\s+(?:rovesci|piogge|temporali)",
        str(answer or ""), re.I,
    )
    return ["UNVERIFIED_FORECAST_INTENSITY"] if unsupported and not has_future_intensity else []
