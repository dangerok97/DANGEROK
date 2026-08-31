"""
The moments ORA has arranged to wake up, and what it means when it does.

    WAKE != NOTIFY.
    THE RUNTIME DECIDES WHEN ORA WAKES.
    THE AI DECIDES WHAT THAT WAKE MEANS.

A wake is an alarm and nothing more. It says a moment has come that somebody
— usually the model, sometimes a change in a life — thought worth looking at
again. It carries no opinion about what will be found, and reaching one
guarantees nothing: most wakes end in a review that concludes nothing has
changed and goes back to sleep.

The reasons are deliberately mechanical. `state_changed`, `delivery_recheck`,
`opportunity_revisit`, `ambient_review`, `retry` — none of them names a
domain, because the moment a wake can be called `flight_changed` the runtime
has started to know what a flight is, and the judgement has quietly moved out
of the model and into a scheduler.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

# Why the alarm was set. Technical, every one of them.
WakeReason = Literal[
    "state_changed",
    "delivery_recheck",
    "opportunity_revisit",
    "ambient_review",
    "retry",
]

# `claimed` is held by exactly one worker for the length of its lease. A
# worker that dies leaves the wake claimed until the lease runs out, and then
# it becomes eligible again — which is why the lease exists rather than a
# flag somebody has to remember to clear.
WakeStatus = Literal["pending", "claimed", "completed", "cancelled", "failed"]

# Why a wake was scheduled again. A retry after a provider outage and a
# revisit the model asked for are different things, and a history that files
# them under one word cannot answer "why did ORA look at this five times?".
WakeProvenance = Literal["model", "code_schedule", "technical_retry"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return _now().isoformat()


def new_wake_id() -> str:
    return f"wke_{uuid.uuid4().hex[:16]}"


class AmbientWake(BaseModel):
    """
    One arranged moment to look again.

    `identity` is what stops three updates to the same concern from becoming
    three alarms. It is built from who, what and why — never from the wording
    of the change that caused it — plus a coarse time bucket, so two wakes
    arranged a few seconds apart for the same reason are one wake and two
    arranged for genuinely different moments are two.
    """

    id: str = Field(default_factory=new_wake_id)
    owner_id: str

    reason: WakeReason
    # What this is about, by handle. A wake never carries content.
    opportunity_id: str = Field(default="", max_length=64)
    delivery_plan_id: str = Field(default="", max_length=64)
    source_ref: str = Field(default="", max_length=120)

    scheduled_for: str = Field(default_factory=now_iso)
    status: WakeStatus = "pending"
    provenance: WakeProvenance = "code_schedule"

    # Claiming. `lease_until` is the only thing that makes a dead worker
    # recoverable without anybody noticing it died.
    claimed_at: Optional[str] = None
    lease_until: Optional[str] = None
    worker_id: str = Field(default="", max_length=64)

    completed_at: Optional[str] = None
    attempts: int = 0
    # Sanitised: a type name, never a message that might carry a token or a
    # fragment of somebody's life.
    last_error: str = Field(default="", max_length=80)

    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    expires_at: Optional[datetime] = None

    def touch(self) -> None:
        self.updated_at = now_iso()

    @property
    def identity(self) -> str:
        """Two wakes with this identity are the same alarm set twice."""
        bucket = (self.scheduled_for or "")[:16]  # to the minute
        raw = "|".join(
            [
                self.owner_id,
                self.reason,
                self.opportunity_id or self.delivery_plan_id or self.source_ref,
                bucket,
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def public(self) -> Dict[str, Any]:
        """What a debug surface may see. No content, ever."""
        return {
            "id": self.id,
            "reason": self.reason,
            "status": self.status,
            "scheduled_for": self.scheduled_for,
            "opportunity_id": self.opportunity_id or None,
            "delivery_plan_id": self.delivery_plan_id or None,
            "attempts": self.attempts,
            "provenance": self.provenance,
            "last_error": self.last_error or None,
        }


class WakeOutcome(BaseModel):
    """What one wake did, for the log and for the tests."""

    wake_id: str = ""
    reason: WakeReason = "ambient_review"
    handled: bool = False
    # What the work decided, in the vocabulary of whatever ran.
    result: str = Field(default="", max_length=80)
    # A technical failure worth trying again, named by type.
    retry_after_seconds: Optional[int] = None
    error: str = Field(default="", max_length=80)


class PushEndpoint(BaseModel):
    """
    One device that can be reached, and whether it still can.

    The token is the sensitive part of this whole phase. It is never logged,
    never returned by an endpoint, never put in a report and never shown in a
    screenshot — `public()` exists precisely so there is a safe way to talk
    about an endpoint without carrying its token along.
    """

    id: str = Field(default_factory=lambda: f"pep_{uuid.uuid4().hex[:16]}")
    owner_id: str

    platform: Literal["ios", "android", "web", "unknown"] = "unknown"
    provider: Literal["expo", "stub"] = "expo"
    token: str = Field(default="", max_length=400)
    # A hash, not the device's own id: enough to recognise the same phone
    # again without keeping an identifier that follows somebody around.
    device_hash: str = Field(default="", max_length=64)

    status: Literal["active", "disabled", "revoked"] = "active"
    # What the OS last told us, as a fact about the device.
    permission_state: Literal["granted", "denied", "undetermined"] = "undetermined"

    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    last_seen_at: Optional[str] = None
    disabled_reason: str = Field(default="", max_length=80)

    def public(self) -> Dict[str, Any]:
        """Everything except the one field that must never travel."""
        return {
            "id": self.id,
            "platform": self.platform,
            "provider": self.provider,
            "status": self.status,
            "permission_state": self.permission_state,
            "last_seen_at": self.last_seen_at,
            "disabled_reason": self.disabled_reason or None,
        }


class AppPresence(BaseModel):
    """
    Whether somebody is inside ORA right now — which is not where they are.

        Life Presence: at home, at work, on the way.
        App Presence: looking at this screen, or not.

    Two different facts that a single word would blur. A person can be at home
    and not have opened ORA in a week, and the judgement about interrupting
    them needs both.

    Freshness is part of the fact. A flag saying `foreground` that was written
    forty minutes ago is not evidence that anybody is looking at anything, and
    treating it as such would suppress notifications for somebody who left.
    """

    owner_id: str
    state: Literal["foreground", "background", "unknown"] = "unknown"
    last_foreground_at: Optional[str] = None
    last_background_at: Optional[str] = None
    updated_at: str = Field(default_factory=now_iso)

    def resolved(self, *, fresh_for_seconds: int = 120) -> Dict[str, Any]:
        """
        What can honestly be said about it now.

        Stale evidence resolves to `unknown` rather than to its last value,
        because "we do not know" is true and "they are still here" is a guess
        that gets less right every minute.
        """
        age = _age_seconds(self.updated_at)
        stale = age is None or age > fresh_for_seconds
        return {
            "state": "unknown" if stale else self.state,
            "seconds_since_known": None if age is None else int(age),
            "stale": stale,
        }


def _age_seconds(when: Optional[str]) -> Optional[float]:
    if not when:
        return None
    try:
        moment = datetime.fromisoformat(str(when))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (_now() - moment).total_seconds()
