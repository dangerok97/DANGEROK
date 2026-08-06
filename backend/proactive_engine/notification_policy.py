"""Notification policy layer — do NOT blast push.

Home surfaces suggestions; this policy decides whether a future channel
may deliver, batching and respecting quiet/study/sleep/events/driving.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from proactive_engine.decision_engine import (
    detect_likely_sleep,
    detect_quiet_hours,
)


@dataclass
class NotificationDecision:
    send_now: bool
    batch: bool
    reason: str
    earliest_at: Optional[str] = None
    channel: str = "none"  # none|home|push_later (push never immediate in foundation)


def _parse(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def next_batch_window(now: Optional[datetime] = None) -> datetime:
    """Morning (08:00) or afternoon (17:00) Europe/Rome-ish batch slots."""
    now = now or datetime.now(timezone.utc)
    local = now + timedelta(hours=2)
    candidates = []
    for hour in (8, 17):
        c = local.replace(hour=hour, minute=0, second=0, microsecond=0)
        if c <= local:
            c = c + timedelta(days=1)
        candidates.append(c - timedelta(hours=2))  # back to UTC approx
    return min(candidates)


def evaluate_notification(
    suggestion: Dict[str, Any],
    *,
    now: Optional[datetime] = None,
    in_study: bool = False,
    in_event: bool = False,
    driving: bool = False,
) -> NotificationDecision:
    """Foundation: never send push immediately. Prefer Home + deferred batch."""
    now = now or datetime.now(timezone.utc)
    urgency = float(suggestion.get("urgency") or 0)
    priority = suggestion.get("priority") or "medium"

    if driving:
        return NotificationDecision(
            send_now=False, batch=True, reason="driving",
            earliest_at=next_batch_window(now).isoformat(), channel="none",
        )
    if in_study and urgency < 0.85:
        return NotificationDecision(
            send_now=False, batch=True, reason="during_study",
            earliest_at=next_batch_window(now).isoformat(), channel="none",
        )
    if in_event and urgency < 0.8:
        return NotificationDecision(
            send_now=False, batch=True, reason="during_event",
            earliest_at=next_batch_window(now).isoformat(), channel="none",
        )
    if detect_likely_sleep(now) or detect_quiet_hours(now):
        return NotificationDecision(
            send_now=False, batch=True, reason="quiet_or_sleep",
            earliest_at=next_batch_window(now).isoformat(), channel="none",
        )

    # Even outside quiet hours: foundation does not push — Home only
    if priority == "critical" and urgency >= 0.9:
        return NotificationDecision(
            send_now=False, batch=False, reason="critical_home_only",
            channel="home",
        )

    return NotificationDecision(
        send_now=False, batch=True, reason="default_batch_home",
        earliest_at=next_batch_window(now).isoformat(), channel="home",
    )


def snooze_until_iso(
    preset: str,
    *,
    now: Optional[datetime] = None,
    custom_until: Optional[str] = None,
) -> str:
    now = now or datetime.now(timezone.utc)
    if preset == "15m":
        return (now + timedelta(minutes=15)).isoformat()
    if preset == "1h":
        return (now + timedelta(hours=1)).isoformat()
    if preset == "stasera":
        local = now + timedelta(hours=2)
        target_local = local.replace(hour=20, minute=0, second=0, microsecond=0)
        if target_local <= local:
            target_local = target_local + timedelta(days=1)
        return (target_local - timedelta(hours=2)).isoformat()
    if preset == "domani":
        local = now + timedelta(hours=2)
        target_local = (local + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        return (target_local - timedelta(hours=2)).isoformat()
    if preset == "custom":
        dt = _parse(custom_until)
        if not dt:
            raise ValueError("custom_until_required")
        return dt.isoformat()
    raise ValueError("invalid_snooze_preset")
