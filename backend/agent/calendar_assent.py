"""Narrow, auditable assent to one already-proposed native calendar deletion.

This is not a general intent classifier. Unrecognised/conditional replies do
not grant authority. A model argument can never supply this confirmation:
only the original runtime utterance and the backend-frozen proposal are read.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
import unicodedata
from typing import Any, Mapping

SNAPSHOT_FIELDS = ("title", "starts_at", "ends_at", "location", "description", "updated_at")


def _words(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).casefold()
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in text if not unicodedata.combining(c))).strip()


def confirms_named_cancellation(spoken: str, title: str) -> bool:
    """Accept a complete explicit sentence naming exactly the frozen title.

    No prefix-only yes, free trailing prose, conditions, second action, target
    replacement, quoted instruction or changed date/time is accepted here.
    Plain short confirmations retain their existing separate authority path.
    """
    if not isinstance(spoken, str) or not isinstance(title, str):
        return False
    if not 1 <= len(spoken) <= 1000 or not 1 <= len(title) <= 200:
        return False
    if any(unicodedata.category(c).startswith("C") for c in spoken + title):
        return False
    raw = spoken.strip()
    if not raw or raw[0] in "\"'«“‘`>" or raw.endswith("?"):
        return False
    target = _words(title)
    if not target:
        return False
    pattern = (
        r"(?:si(?: confermo)?|confermo|ok(?: confermo)?|va bene) "
        r"(?:elimina|cancella|rimuovi) "
        r"(?:(?:solo|soltanto|esclusivamente) )?l (?:appuntamento|evento) "
        + re.escape(target)
        + r"(?: (?:appena indicato|appena proposto|che hai appena indicato|che hai appena proposto))?"
    )
    return re.fullmatch(pattern, _words(raw)) is not None


def _snapshot(snapshot: Mapping[str, Any]) -> str:
    return json.dumps({key: snapshot.get(key) for key in SNAPSHOT_FIELDS},
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _recent(at: str) -> bool:
    try:
        then = datetime.fromisoformat(at.replace("Z", "+00:00"))
        return then.tzinfo is not None and 0 <= (datetime.now(timezone.utc) - then).total_seconds() <= 900
    except (TypeError, ValueError, OverflowError):
        return False


@dataclass(frozen=True)
class CalendarCancellationConfirmation:
    owner_id: str
    calendar_ref: str
    title: str
    starts_at: str
    snapshot_json: str
    spoken: str
    proposed_at: str

    def matches_readback(self, owner_id: str, calendar_ref: str, snapshot: Mapping[str, Any]) -> bool:
        return bool(owner_id == self.owner_id and calendar_ref == self.calendar_ref
                    and _recent(self.proposed_at) and _snapshot(snapshot) == self.snapshot_json)

    def permits(self, owner_id: str, intent: Any, spoken: str) -> bool:
        """Bind parsed assent to the exact local deletion, not merely its label."""
        params, effect = intent.parameters, intent.effect
        return bool(
            owner_id == self.owner_id == intent.owner_id
            and spoken == self.spoken and _recent(self.proposed_at)
            and confirms_named_cancellation(spoken, self.title)
            and intent.capability == "calendar.local.write"
            and params.get("operation") == "delete"
            and "calendar:" + str(params.get("calendar_ref") or "") == self.calendar_ref
            and str(params.get("starts_at") or "") == self.starts_at
            and not params.get("google_event_id")
            and effect.effect_type == "remove" and effect.effect_summary == self.title
            and not (effect.external_party or effect.financial_effect or effect.legal_effect
                     or effect.privacy_effect or effect.public_visibility)
        )

    def audit(self) -> dict:
        return {"source": "user_message", "user_utterance": self.spoken,
                "calendar_ref": self.calendar_ref, "proposal_at": self.proposed_at,
                "snapshot_sha256": hashlib.sha256(self.snapshot_json.encode()).hexdigest(),
                "parser": "named_native_calendar_cancellation_v163"}


def cancellation_confirmation(runtime: Mapping[str, Any]) -> CalendarCancellationConfirmation | None:
    """Read only the owner-scoped proposal already persisted by the backend."""
    uid, spoken = runtime.get("user_id"), runtime.get("user_message")
    pending = runtime.get("pending_act")
    if not isinstance(uid, str) or not uid or not isinstance(pending, dict):
        return None
    request, at = pending.get("calendar_cancel"), pending.get("at")
    if not isinstance(request, dict) or request.get("owner_id") != uid or not isinstance(at, str) or not _recent(at):
        return None
    frozen = request.get("arguments")
    if not isinstance(frozen, dict):
        return None
    ref, snapshot = frozen.get("calendar_ref"), frozen.get("confirmation_snapshot")
    if not isinstance(ref, str) or not ref.startswith("calendar:node_home_") or not isinstance(snapshot, dict):
        return None
    title, starts = snapshot.get("title"), snapshot.get("starts_at")
    if not isinstance(starts, str) or not starts or not confirms_named_cancellation(spoken, title):
        return None
    if not all(key in snapshot for key in SNAPSHOT_FIELDS):
        return None
    try:
        encoded = _snapshot(snapshot)
    except (TypeError, ValueError):
        return None
    return CalendarCancellationConfirmation(uid, ref, title, starts, encoded, spoken, at)
