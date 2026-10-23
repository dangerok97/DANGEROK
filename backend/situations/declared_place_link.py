"""Recover a model-declared, literally user-named Life Place after owner verification.

The AI decides Situation meaning and location. This resolver only fills a
missing canonical ID when the chosen human label is in the user's own turn and
uniquely identifies an existing saved place belonging to this user. It never
uses GPS, a guessed locality, inferred home, or another person's place.
"""
from __future__ import annotations

import re
import unicodedata

from situations.models import SituationUpdate

_MAX_OWNER_PLACES = 100


def _norm(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().strip()


async def restore_owned_place_reference(
    db, *, owner_id: str, user_message: str, update: SituationUpdate
) -> SituationUpdate:
    """Never let a missing/ambiguous read prevent the Situation's core write."""
    if (db is None or not owner_id or update.operation != "create"
            or update.source != "user_conversation"
            or any(str(ref).startswith("place:") for ref in update.linked_object_refs)
            or len(update.linked_object_refs) >= 20):
        return update
    label = _norm(update.location_label or "")
    statement = _norm((user_message or "")[:8000])
    if not 4 <= len(label) <= 120 or not statement:
        return update
    if not re.search(r"(?<!\w)" + re.escape(label) + r"(?!\w)", statement):
        return update
    try:
        cursor = db.life_places.find(
            {"user_id": owner_id, "state": {"$ne": "dismissed"}},
            {"_id": 0, "id": 1, "label": 1},
        ).limit(_MAX_OWNER_PLACES + 1)
        rows = await cursor.to_list(length=_MAX_OWNER_PLACES + 1)
    except Exception:
        return update
    if len(rows) > _MAX_OWNER_PLACES:
        return update
    matches = [str(row.get("id") or "").strip() for row in rows
               if isinstance(row, dict) and _norm(str(row.get("label") or "")) == label
               and str(row.get("id") or "").strip()]
    if len(matches) != 1:
        return update
    # SituationService still validates ref format, existence and user ownership.
    return update.model_copy(update={
        "linked_object_refs": [*update.linked_object_refs, f"place:{matches[0]}"],
    })


# An activity the person says they have JUST started is happening where they
# are. Owner decision 23/10/2026: ORA must understand where without asking.
# Production 23/10: "Ho appena steso i panni" read weather at the current
# position, but the Situation was stored without a place and another component
# then asked the person for the locality. Narrow, consent-gated rule.
CURRENT_PRESENCE_START_WINDOW_MINUTES = 15


async def attach_current_presence_label(
    db, *, owner_id: str, update: SituationUpdate, now=None, where=None,
) -> SituationUpdate:
    """Fill a missing place label from the current authorized position.

    Only for a new conversational Situation whose physical start is within the
    last 15 minutes, with no place stated and no linked place. Uses the same
    consent- and freshness-gated position as "Meteo dove sei"; a stale point,
    revoked consent or a missing locality changes nothing.
    """
    from datetime import datetime, timedelta, timezone

    if (db is None or not owner_id or update.operation != "create"
            or update.source != "user_conversation"
            or str(update.location_label or "").strip()
            or any(str(ref).startswith("place:") for ref in update.linked_object_refs)
            or not update.started_at):
        return update
    try:
        started = datetime.fromisoformat(str(update.started_at).replace("Z", "+00:00"))
    except ValueError:
        return update
    if started.tzinfo is None:
        return update
    moment = now or datetime.now(timezone.utc)
    window = timedelta(minutes=CURRENT_PRESENCE_START_WINDOW_MINUTES)
    if not (moment - window <= started <= moment + timedelta(minutes=2)):
        return update
    try:
        if where is None:
            from home.service import HomeService
            where = HomeService(db)._where_they_are
        point = await where(owner_id)
    except Exception:
        return update
    label = str((point or (None, None, ""))[2] or "").strip()[:180]
    if not label:
        return update
    return update.model_copy(update={"location_label": label})
