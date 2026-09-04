"""
The first things ORA actually does to the world, and how it checks afterwards.

    ORA DOES NOT JUST KNOW WHAT TO DO. ORA CAN DO IT.
    PROVIDER ACCEPTED IS NOT OUTCOME ACHIEVED.

One capability is wired here, and the choice was the point. A personal
calendar entry is reversible by the person in two taps, costs nothing,
commits nobody, reaches nobody else, and — the property that actually decided
it — **can be read back**. A write whose only evidence is the provider's own
"200 OK" teaches a system to believe itself; a write that can be looked up
afterwards teaches it to check.

Three things every effect here does, and the order matters.

It is **claimed** before it is attempted, atomically, so that two workers and
a double-tapped button produce one effect. It is **named** to the provider by
a stable id derived from what the effect is, so that a retry after a timeout
lands on the thing that may already exist rather than making a second one.
And it is **read back**, so what goes into evidence is what the world says,
not what the request hoped.

What is not here is as deliberate. Nothing sends, nothing pays, nothing
publishes, nothing deletes — not because those are hard, but because the
architecture is what this phase is proving, and proving it on something that
cannot hurt anybody is the only honest way to do that.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from agent.models import ActionIntent, ExecutionReceipt, ResultProvenance

logger = logging.getLogger(__name__)

# Google accepts a client-supplied event id in base32hex. Our idempotency key
# is hex, which is a subset — so the same effect asked for twice asks for the
# same id twice, and the second one collides instead of duplicating.
_ID_SAFE = re.compile(r"^[a-v0-9]{5,1024}$")

# How far ahead a calendar entry may be placed by an agent. Not a judgement
# about calendars — a bound on how wrong an unattended write can be.
MAX_AHEAD_DAYS = 400


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EffectOutcome:
    """What happened when the world was touched, and what it said back."""

    def __init__(
        self,
        *,
        receipt: ExecutionReceipt,
        observation: str,
        claims: Optional[List[Tuple[str, str]]] = None,
        provenance: Optional[ResultProvenance] = None,
        observed: bool = False,
    ):
        self.receipt = receipt
        self.observation = observation
        # (claim, what it bears on) — read back from the world, not from us.
        self.claims = claims or []
        self.provenance = provenance or ResultProvenance(source_class="simulated")
        # Whether anybody actually looked afterwards.
        self.observed = observed


async def run_effect(db, owner_id: str, intent: ActionIntent) -> Optional[EffectOutcome]:
    """
    Carry out one declared effect, or say there is nothing wired for it.

    Returns None when the capability has no real executor. That is not a
    failure to report to a person: it is the boundary this phase deliberately
    still has, and the caller turns it into a `prepared` result.
    """
    runner = _RUNNERS.get(intent.capability)
    if runner is None:
        return None
    return await runner(db, owner_id, intent)


# --- reaching the connector, and nothing else -------------------------------
#
# Resolved here rather than borrowed from the study flow's helpers, which is
# where the same three steps already live. The agent depending on another
# feature's action engine to put something in a calendar is a dependency
# pointing the wrong way, and it would have been the sort of thing nobody
# untangles later. Fifteen lines is the cheaper mistake.

def _calendar_service(db):
    """The connector, preferring the app's own wired singleton."""
    try:
        from deps import get_google_calendar_service

        return get_google_calendar_service()
    except Exception:
        from connectors.google_calendar.service import GoogleCalendarService
        from permissions import PermissionService
        from security import get_token_vault

        return GoogleCalendarService(
            db=db, permissions=PermissionService(db), ingestion=None,
            vault=get_token_vault(),
        )


async def _connected_instance(db, owner_id: str) -> Optional[Dict[str, Any]]:
    """
    A calendar this person actually connected, or nothing.

    Nothing is a real answer and a different one from an empty calendar: the
    plan needs to be able to tell "there is nowhere to write this" from "there
    is nothing there", and only one of them is a reason to find another way.
    """
    from connectors.google_calendar.scopes import CONNECTOR_ID

    found = await db.connector_instances.find(
        {
            "user_id": owner_id,
            "connector_id": CONNECTOR_ID,
            "status": {"$in": ["connected", "active", "authorized"]},
        },
        {"_id": 0},
    ).sort("updated_at", -1).to_list(5)
    return found[0] if found else None


async def _calendar_id(gcal, owner_id: str, instance: Dict[str, Any]) -> str:
    """Which calendar. The one they chose, or their primary."""
    meta = instance.get("metadata") or {}
    chosen = meta.get("default_calendar_id") or (
        (instance.get("selected_resource_ids") or [None])[0]
    )
    if chosen:
        return str(chosen)
    try:
        calendars = await gcal.list_calendars_for_instance(
            user_id=owner_id, instance_id=instance["id"]
        )
        primary = next((c for c in calendars if c.get("primary")), None)
        pick = primary or (calendars[0] if calendars else None)
        return str((pick or {}).get("id") or "primary")
    except Exception as e:
        logger.info("calendar id soft-fail: %s — uso primary", type(e).__name__)
        return "primary"


# --- calendar ---------------------------------------------------------------

async def calendar_write(db, owner_id: str, intent: ActionIntent) -> EffectOutcome:
    """
    Put something in this person's own calendar, then go and look at it.

    Everything before the provider call is a reason not to make it. A calendar
    that is not connected, a time that cannot be read, a date far enough away
    that something has clearly gone wrong upstream — each returns a receipt
    saying so, because a request that should not be sent is more useful
    recorded than attempted.
    """
    receipt = ExecutionReceipt(
        owner_id=owner_id,
        goal_id=intent.goal_id,
        action_intent_id=intent.id,
        idempotency_key=intent.idempotency_key,
        capability=intent.capability,
        provider="calendar",
    )

    try:
        gcal = _calendar_service(db)
    except Exception as e:
        logger.info("calendar import soft-fail: %s", type(e).__name__)
        return _refused(receipt, "not_wired", "Il calendario non è collegato a niente.")

    instance = await _connected_instance(db, owner_id)
    if not instance:
        # No calendar, which is a different thing from an empty one and from a
        # broken one. Named, so the plan can find another way.
        return _refused(
            receipt, "requires_connection",
            "Non c'è nessun calendario collegato, quindi non posso scriverci.",
        )

    body, problem = _event_body(intent)
    if problem:
        return _refused(receipt, problem, "Quello che c'era da mettere in agenda non tornava.")

    try:
        access = await gcal._get_access_token(user_id=owner_id, instance=instance)
        calendar_id = await _calendar_id(gcal, owner_id, instance)
    except Exception as e:
        logger.info("calendar access soft-fail: %s", type(e).__name__)
        return _refused(receipt, "provider_unavailable",
                        "Non sono riuscita a raggiungere il calendario.", retryable=True)

    receipt.external_ref = ""
    try:
        created = await gcal.provider.create_event(
            access_token=access, calendar_id=calendar_id, body=body
        )
    except Exception as e:
        logger.info("calendar write failed: %s", type(e).__name__)
        receipt.provider_status = "failed"
        # The status code, when the provider gave one. «GoogleCalendarAPIError»
        # is a receipt nobody can act on: a 409 means the thing is already
        # there, a 401 means the connection needs renewing, and a 503 means try
        # again. Same shape the conversation side already records.
        status = getattr(e, "status_code", None)
        receipt.error_type = (
            f"google_http_{status}" if status else type(e).__name__
        )[:80]
        receipt.retryable = True
        receipt.answered_at = _now().isoformat()
        return EffectOutcome(
            receipt=receipt,
            observation="Il calendario non ha accettato la richiesta.",
            provenance=ResultProvenance(
                source_class="connected_provider", capability=intent.capability,
                provider="calendar",
            ),
        )

    event_id = str((created or {}).get("id") or "")
    receipt.external_ref = event_id[:200]
    receipt.answered_at = _now().isoformat()
    # Accepted, and no more than that. What it means is decided by looking.
    receipt.provider_status = "accepted"

    read_back, seen = await _read_back(gcal, access, calendar_id, event_id)
    if not seen:
        # The request was taken and the thing is not there yet. Common, and
        # exactly the case a system that stops at the receipt gets wrong.
        return EffectOutcome(
            receipt=receipt,
            observation=(
                "Il calendario ha preso la richiesta, ma l'evento non risulta "
                "ancora quando vado a guardarlo."
            ),
            provenance=ResultProvenance(
                source_class="connected_provider", capability=intent.capability,
                provider="calendar", source_refs=[event_id] if event_id else [],
                certainty_note="accettato, non ancora osservato",
            ),
        )

    receipt.provider_status = "succeeded"
    receipt.result_refs = [event_id]
    title = str(read_back.get("summary") or "").strip()
    when = _human_when(read_back)
    return EffectOutcome(
        receipt=receipt,
        observation=f"L'ho messo in calendario: {title}{when}.",
        claims=[(
            f"In calendario risulta: {title}{when}."[:600],
            intent.effect.expected_outcome[:300] or "l'appuntamento è in agenda",
        )],
        provenance=ResultProvenance(
            source_class="connected_provider",
            capability=intent.capability,
            provider="calendar",
            source_refs=[event_id],
            freshness="fresh",
            certainty_note="riletto dal calendario dopo averlo scritto",
        ),
        observed=True,
    )


async def _read_back(gcal, access: str, calendar_id: str, event_id: str):
    """
    Go and look at what was just written.

        READ AFTER WRITE.

    The single most valuable line in this file. Without it the only evidence
    an effect happened is that we asked for it, which is not evidence of
    anything.
    """
    if not event_id:
        return {}, False
    try:
        found = await gcal.provider.get_event(
            access_token=access, calendar_id=calendar_id, event_id=event_id
        )
        return (found or {}), bool(found)
    except Exception as e:
        logger.info("calendar read-back: %s", type(e).__name__)
        return {}, False


def _event_body(intent: ActionIntent) -> Tuple[Dict[str, Any], str]:
    """
    The event as the provider wants it, or the reason it cannot be built.

    `ora_event_id` is the provider's own idempotency handle, set to our key:
    the same effect asked for twice asks under the same name, and the
    connector returns what already exists rather than making a second one.
    Ours does not go away because of it — two guards against one duplicate is
    the right number when the duplicate is in somebody's calendar.
    """
    params = intent.parameters or {}
    title = str(params.get("title") or intent.effect.effect_summary or "").strip()
    starts = str(params.get("starts_at") or "").strip()
    ends = str(params.get("ends_at") or "").strip()
    if not title or not starts:
        return {}, "missing_parameters"

    try:
        start_at = datetime.fromisoformat(starts)
    except ValueError:
        return {}, "unreadable_time"
    if start_at.tzinfo is None:
        start_at = start_at.replace(tzinfo=timezone.utc)
    if start_at > _now() + timedelta(days=MAX_AHEAD_DAYS):
        return {}, "too_far_ahead"

    if ends:
        try:
            end_at = datetime.fromisoformat(ends)
        except ValueError:
            return {}, "unreadable_time"
        if end_at.tzinfo is None:
            end_at = end_at.replace(tzinfo=timezone.utc)
    else:
        # Same number as every other calendar write in the project. It used
        # to be 30 here and 60 elsewhere, which is the kind of disagreement
        # nobody notices until two paths produce different events for the
        # same request.
        from documents.intelligence.google_sync import DEFAULT_EVENT_MINUTES

        end_at = start_at + timedelta(
            minutes=int(params.get("minutes") or DEFAULT_EVENT_MINUTES)
        )
    if end_at <= start_at:
        return {}, "unreadable_time"

    key = intent.idempotency_key
    body: Dict[str, Any] = {
        "summary": title[:200],
        "description": (params.get("description") or "")[:500],
        "start": {"dateTime": start_at.isoformat()},
        "end": {"dateTime": end_at.isoformat()},
        # Nobody else is on this. An event with a guest is a different act and
        # a different grant, and there is deliberately nowhere here to put one.
        "extendedProperties": {"private": {"ora_event_id": key}},
    }
    if _ID_SAFE.match(f"ora{key}"):
        body["id"] = f"ora{key}"
    tz = params.get("timezone")
    if tz:
        body["start"]["timeZone"] = str(tz)[:60]
        body["end"]["timeZone"] = str(tz)[:60]
    return body, ""


def _human_when(event: Dict[str, Any]) -> str:
    start = (event.get("start") or {})
    raw = str(start.get("dateTime") or start.get("date") or "")
    if not raw:
        return ""
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return f", {moment.strftime('%d/%m alle %H:%M')}"


def _refused(
    receipt: ExecutionReceipt, why: str, observation: str, *, retryable: bool = False
) -> EffectOutcome:
    """A request that was not made, recorded as one."""
    receipt.provider_status = "failed"
    receipt.error_type = why
    receipt.retryable = retryable
    receipt.answered_at = _now().isoformat()
    return EffectOutcome(
        receipt=receipt,
        observation=observation,
        provenance=ResultProvenance(
            source_class="connected_provider",
            capability=receipt.capability,
            provider=receipt.provider,
        ),
    )


# Which capabilities have something real behind them. One, and adding to it is
# a decision somebody should have to make on purpose.
_RUNNERS = {
    "calendar.write": calendar_write,
}


def is_wired_for_real(capability: str) -> bool:
    return (capability or "").strip() in _RUNNERS


def wired_capabilities() -> List[str]:
    return sorted(_RUNNERS)
