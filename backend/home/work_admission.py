"""
What is allowed to become work.

ORA reads things: documents, calendars, what somebody told it during the setup.
Reading is how it becomes useful. It is not, by itself, a reason to put
something in front of a person.

    Knowledge acquisition must not create work by itself.

The failure this exists to stop was found in a real recording. Somebody
uploaded a car insurance policy during their first setup. ORA read it
perfectly — 0.95 confidence, no warnings, no ambiguity, `requires_review`
false — and produced five things to do: a card titled with the document's own
name and a "Verifica" button, a reminder about the deadline it had just
learned, a "Revisione richiesta", a proposed event to confirm, and an admin
item. Every one of them existed because a file had been read, and not one of
them was anything the person needed to decide, confirm, or act on.

A document is allowed to change what ORA knows — the profile, Vita, Documenti,
the deadlines it will watch, what it can reason about later. Turning that into
work is a separate step, and it needs a reason of its own.

There are eight, and they are all statements about the person's situation
rather than about ORA's processing:

    decision                an open decision that is theirs to make
    confirmation_required   a fact ORA cannot resolve and actually needs
    deadline                a concrete date, close enough to matter now
    risk                    something concrete that could go wrong
    goal_blocker            an active goal is stopped on this
    user_request            they asked for it, or deferred it to now
    opportunity             something real, worth acting on while it lasts
    consent                 a side effect that must not happen unasked

"I read a document", "I understood what it is", "I learned that a policy
exists" are not on the list, and no amount of confidence in the reading puts
them there. A quiet Home is the correct output of a well-read document.

Nothing here knows what a policy, a bill or an exam is. It reads what an item
declares about itself.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from home.models import HomeItem
from home.temporal import hours_until

# The reasons, and nothing else, may bring something into somebody's day.
WORK_REASONS = frozenset({
    "decision",
    "confirmation_required",
    "deadline",
    "risk",
    "goal_blocker",
    "user_request",
    "opportunity",
    "consent",
})

# Where existing is not, by itself, a reason to be in somebody's day.
#
# Ingestion is the obvious case: a document was read, so ORA knows more, and
# that is all that happened. A conversation is the same shape of thing and took
# longer to see. Somebody asked what a car inspection costs, ORA answered, and
# Home said "DA FARE ADESSO: conoscere il costo medio della revisione auto".
# Nobody had taken on anything. The exchange had simply occurred, and occurring
# was being read as work — the same mistake as the policy card, in a different
# place.
#
# A calendar event or a goal step is not on this list: those are the person's
# own commitments, and they belong on Home for reasons that predate all of
# this.
KNOWLEDGE_SOURCES = frozenset({
    "document",
    "document_action",
    "event_candidate",
    "life_experience",
    "conversation_session",
})

# How far ahead a date has to be before it stops being today's business.
#
# Not a new number: ranking already puts anything past a week into "later", so
# a deadline beyond it is, by the system's own account, not what the day is
# about. It is not forgotten — the fact stays in the profile and in Documenti,
# and the same date walks back through this gate on its own as it approaches.
ATTENTION_HORIZON_HOURS = 168.0


def _declared(item: HomeItem) -> Optional[str]:
    reason = (item.meta or {}).get("work_reason")
    return reason if reason in WORK_REASONS else None


def _has_live_deadline(item: HomeItem, now: datetime) -> bool:
    hrs = hours_until(item.due_at or item.start_at, now)
    if hrs is None:
        return False
    # Overdue counts: a date that has passed is more of a reason, not less.
    return hrs <= ATTENTION_HORIZON_HOURS


def reason_to_act(item: HomeItem, *, now: datetime) -> Optional[str]:
    """
    Why this belongs in somebody's day, or None if there is no reason.

    An item from anywhere else keeps the standing it always had; this decides
    only for what ingestion produced.
    """
    if (item.meta or {}).get("knowledge_only"):
        # Something ORA has become able to do. Real, and not a reason to speak.
        return None

    if item.source_type not in KNOWLEDGE_SOURCES:
        return "user_request"

    # The person already acted on this one: they were shown it and pushed it
    # back, or something they asked for is waiting. Their decision, not ours.
    state = (item.status or "").lower()
    if state in ("waiting", "deferred", "in_attesa") or (item.meta or {}).get("deferred"):
        return "user_request"

    declared = _declared(item)

    # Anything anchored to a date is answerable by the date.
    #
    # This covers the two shapes it arrives in: a deadline ORA read out of a
    # document, and an event ORA proposes to put in a calendar, which needs
    # asking before it happens — but only once it is near enough for the
    # asking to be worth an interruption. A payment due in two and a half
    # weeks is a fact today and work in a fortnight.
    if item.due_at or item.start_at:
        if not _has_live_deadline(item, now):
            return None
        return declared or "deadline"

    # No date. Then the only thing that can justify it is something it says
    # about the person's situation — an unresolved question, a decision, a
    # risk. Existing because a file was read is not one.
    return declared


def admit(items: Iterable[HomeItem], *, now: datetime) -> List[HomeItem]:
    """Keep what has a reason, and record which one it was."""
    kept: List[HomeItem] = []
    for item in items:
        reason = reason_to_act(item, now=now)
        if not reason:
            continue
        meta: Dict[str, Any] = dict(item.meta or {})
        meta["work_reason"] = reason
        item.meta = meta
        kept.append(item)
    return kept
