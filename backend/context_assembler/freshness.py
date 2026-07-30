"""Per-signal-key TTL policy → Freshness classification.

Configurable, additive, testable. Unknown keys → Freshness.UNKNOWN.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from .types import Freshness


# TTL in seconds: fresh_until (< fresh_until = fresh), stale_after (> stale_after = stale),
# in between = aging. Values chosen conservatively.
POLICY: Dict[str, Dict[str, int]] = {
    "location":         {"fresh": 5 * 60,       "stale": 30 * 60},
    "weather":          {"fresh": 60 * 60,      "stale": 6 * 3600},
    "traffic":          {"fresh": 10 * 60,      "stale": 60 * 60},
    "device_battery":   {"fresh": 5 * 60,       "stale": 60 * 60},
    "calendar":         {"fresh": 15 * 60,      "stale": 24 * 3600},
    "bank_balance":     {"fresh": 60 * 60,      "stale": 24 * 3600},
    # Long-lived facts
    "home_address":     {"fresh": 90 * 86400,   "stale": 365 * 86400},
    "car_plate":        {"fresh": 90 * 86400,   "stale": 365 * 86400},
    "document_expiry":  {"fresh": 24 * 3600,    "stale": 30 * 86400},
    "user_preference":  {"fresh": 30 * 86400,   "stale": 365 * 86400},
    "decision_deadline":{"fresh": 60,           "stale": 30 * 86400},
    "person_name":      {"fresh": 365 * 86400,  "stale": 5 * 365 * 86400},
    "provider_name":    {"fresh": 30 * 86400,   "stale": 365 * 86400},
}


def evaluate_freshness(key: str, observed_at_iso: Optional[str], *, now: Optional[datetime] = None) -> str:
    if not observed_at_iso:
        return Freshness.UNKNOWN.value
    policy = POLICY.get(key)
    if not policy:
        return Freshness.UNKNOWN.value
    try:
        observed = datetime.fromisoformat(observed_at_iso.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return Freshness.UNKNOWN.value
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    n = now or datetime.now(timezone.utc)
    age = (n - observed).total_seconds()
    if age <= policy["fresh"]:
        return Freshness.FRESH.value
    if age >= policy["stale"]:
        return Freshness.STALE.value
    return Freshness.AGING.value
