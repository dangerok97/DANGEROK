"""A new user-declared occurrence is not an update of an old Situation.

The AI understands meaning; this boundary prevents a particularly costly
identity error when it proposes 'update' despite a fresh first-person event.
Only an explicit, current-turn onset qualifies. Corrections, continuations
and old planned future events are kept for the ordinary cognitive decision.
No background writes or automatic closure happen in this module.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from situations.models import SituationState, SituationUpdate

_IMMEDIATE = re.compile(
    r"(?<!\w)(?:adesso|appena|ora|proprio\s+ora|poco\s+fa)(?!\w)",
    re.IGNORECASE,
)
_PERSONAL_OCCURRENCE = re.compile(
    r"(?<!\w)(?:ho|abbiamo|mi\s+(?:è|e'|hanno)|sono|siamo)(?!\w)",
    re.IGNORECASE,
)
# Corrections to an existing observation are not new life events.
_CORRECTION = re.compile(
    r"\b(?:ho\s+sbagliato|mi\s+sono\s+sbagliat[oa]|corregg[ie]|"
    r"rettific[ao]|intendevo|in\s+realt[aà]|la\s+data\s+(?:è|e'|era)|"
    r"l['’]orario\s+(?:è|e'|era)|lo\s+stesso\s+episodio|"
    r"stessa\s+situazione|quell[oa]\s+di\s+(?:ieri|prima)|"
    r"ancora|tuttora|prosegui|continuo|stess[oa])\b",
    re.IGNORECASE,
)
# A previously declared *future intention* can begin today without a new
# Situation. This uses general temporal grammar, not a list of activities.
_FUTURE_PLAN = re.compile(
    r"\b(?:domani|dopodomani|in\s+futuro|vorrei|prevedo|"
    r"previst[oa]|pianificat[oa]|programmat[oa]|intenzione|"
    r"da\s+fare|non\s+ancora\s+iniziat[oa])\b|"
    r"\b[a-zà-ÿ]{2,}rò\b",
    re.IGNORECASE,
)

def _instant(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return value.astimezone(timezone.utc) if value.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def fresh_declared_episode(
    *, old: SituationState, update: SituationUpdate, user_message: str,
    now: datetime | None = None,
) -> SituationUpdate | None:
    """One conservatively grounded rewrite to a new create, or no rewrite.

    Detect only when the user's text asserts an *immediate* occurrence,
    the model explicitly proposed changing an old Situation, and that
    historical Situation predates the new event. No activity-specific
    classifier and no assumed device GPS.
    """
    if update.operation != "update" or not update.situation_id:
        return None
    utterance = " ".join(str(user_message or "")[:1200].split())
    # 'ORA, ho steso...' addresses the assistant; the app's name is not
    # evidence for the temporal adverb 'ora' (= just now).
    cleaned = re.sub(r"^ORA\s*[,!:—-]\s*", "", utterance, flags=re.IGNORECASE)
    clauses = re.split(r"[.!?;\n]+", cleaned)
    # Both the first-person event and the temporal marker must occur in the
    # *same clause*. 'Ho steso ieri. Ora voglio sapere...' is a status query,
    # not a fresh event today.
    declared_now = any(
        _IMMEDIATE.search(clause) and _PERSONAL_OCCURRENCE.search(clause)
        and abs(_IMMEDIATE.search(clause).start()
                - _PERSONAL_OCCURRENCE.search(clause).start()) <= 115
        for clause in clauses
    )
    if not declared_now:
        return None
    if _CORRECTION.search(utterance):
        return None
    # Do not split a predeclared future intention when the person says
    # the activity has now begun. That is the ordinary plan lifecycle.
    if not old.started_at and (
        _FUTURE_PLAN.search(old.summary or "")
        or _FUTURE_PLAN.search(old.temporal_scope or "")
    ):
        return None
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        return None
    moment = moment.astimezone(timezone.utc)
    asserted = _instant(update.started_at) if update.started_at else moment
    if asserted is None:
        return None
    # The phrase "adesso" is grounded by the server's clock, not by a
    # model-chosen time three days ago or five hours into the future.
    if abs((moment - asserted).total_seconds()) > 90 * 60:
        return None
    previous = _instant(old.started_at) or _instant(old.created_at)
    if previous is None:
        return None
    # Repeated messages in a single ongoing physical episode do not produce
    # duplicates. Conversely, a new declaration days later must not
    # overwrite the start and history of an old episode.
    if (asserted - previous) < timedelta(hours=12):
        return None
    # Closed historic records must also remain closed. A new event is not
    # allowed to reopen or mutate them merely because it shares the subject.
    # New episode, new server-created id, new journal, and no inherited
    # place/source/participants from the old record.
    summary = (update.summary or "").strip() or utterance[:320]
    source_refs = [
        str(ref) for ref in update.source_refs
        if ref and str(ref) != f"situation:{old.id}"
        and not str(ref).startswith("goal:")
    ][:20]
    return update.model_copy(update={
        "operation": "create",
        "situation_id": None,
        "expected_revision": None,
        "summary": summary[:400],
        "started_at": asserted.isoformat(),
        "source_refs": source_refs or ["user_conversation"],
        "supersedes": [],
        "linked_plan_id": None,
        # An old object's attachment is not a new-occurrence fact.
        "linked_object_refs": [
            ref for ref in update.linked_object_refs
            if not str(ref).startswith(("situation:", "goal:"))
        ],
    })
