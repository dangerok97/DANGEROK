"""Durable, bounded delivery review for Opportunities and agent Needs.

The scan result only accelerates this work. The opportunity itself carries the
due time, lease and revision fence, so batch limits and worker restarts do not
silently discard a concern before delivery has considered it.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument

COLLECTION = "opportunities"
NEEDS = "agent_needs"
LEASE_SECONDS = 120
TIMEOUT_SECONDS = 60
MAX_ATTEMPTS = 3
logger = logging.getLogger(__name__)


def _expiry_state(row, moment):
    raw = row.get("valid_until")
    if not raw:
        return ""
    try:
        until = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return "invalid_expiry"
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    return "expired" if until <= moment else ""


def _need_due_query(stamp, *, owner_id=None, need_id=None):
    query = {
        "status": {"$in": ["open", "satisfied", "cancelled", "expired"]},
        "delivery_review_due": {"$type": "string", "$lte": stamp},
        "$or": [{"delivery_review_lease_until": {"$exists": False}},
                {"delivery_review_lease_until": {"$lte": stamp}}],
    }
    if owner_id is not None:
        query["owner_id"] = owner_id
    if need_id is not None:
        query["id"] = need_id
    return query


def _opportunity_due_query(stamp, *, owner_id=None):
    query = {
        "status": {"$in": ["active", "dismissed", "suppressed", "resolved", "expired"]},
        "delivery_review_due": {"$type": "string", "$lte": stamp},
        "$or": [{"delivery_review_lease_until": {"$exists": False}},
                {"delivery_review_lease_until": {"$lte": stamp}}],
    }
    if owner_id is not None:
        query["owner_id"] = owner_id
    return query


def _selected_review(query, candidate):
    if candidate is None:
        return query
    return {"$and": [query, {
        "id": candidate["id"], "owner_id": candidate["owner_id"],
        "delivery_review_due": candidate["due_at"],
    }]}


async def _next_review_due(db, collection, query, *, owners_seen=None):
    fair_query = dict(query)
    if owners_seen:
        fair_query["owner_id"] = {"$nin": sorted(owners_seen)}
    row = await db[collection].find_one(
        fair_query, {"_id": 0, "id": 1, "owner_id": 1, "delivery_review_due": 1},
        sort=[("delivery_review_due", 1), ("id", 1)],
    )
    return {"id": row["id"], "owner_id": row["owner_id"],
            "due_at": row["delivery_review_due"]} if row else None


async def _claim_need(db, *, moment, owner_id=None, need_id=None, owners_seen=None,
                      allow_owner_fallback=True, candidate=None):
    query = _selected_review(
        _need_due_query(moment.isoformat(), owner_id=owner_id, need_id=need_id), candidate,
    )
    fair_query = dict(query)
    if candidate is None and owner_id is None and owners_seen:
        fair_query["owner_id"] = {"$nin": sorted(owners_seen)}
    # Atomically cap model attempts while still allowing a crashed last
    # attempt to hand an already-saved plan to its wake. Recovery-only claims
    # can never call a model; an absent handoff becomes explicitly paused.
    change = [{"$set": {
        "delivery_review_token": uuid.uuid4().hex,
        "delivery_review_lease_until": (moment + timedelta(seconds=LEASE_SECONDS)).isoformat(),
        "delivery_review_recovery_only": {"$gte": ["$delivery_review_attempts", MAX_ATTEMPTS]},
        "delivery_review_attempts": {"$min": [MAX_ATTEMPTS, {"$add": ["$delivery_review_attempts", 1]}]},
    }}]
    row = await db[NEEDS].find_one_and_update(
        fair_query, change, sort=[("delivery_review_due", 1), ("id", 1)],
        return_document=ReturnDocument.AFTER,
    )
    if row is None and candidate is None and fair_query != query and allow_owner_fallback:
        row = await db[NEEDS].find_one_and_update(
            query, change, sort=[("delivery_review_due", 1), ("id", 1)],
            return_document=ReturnDocument.AFTER,
        )
    return row


async def _recover_need_plan(service, row):
    """An existing plan is a real handoff, never permission to resend it.

    A crash after saving/sending a plan but before acknowledging admission
    must also be safe for questions whose Need is still open. A pending plan
    without an alarm is handed to the existing recheck path, not sent here.
    """
    from ambient.service import AmbientService
    from delivery.models import DeliveryPlan, DeliveryResult

    # Older cancelled/expired intentions do not prove that this judgement
    # was handed off. A receipt must belong to this admission, while a still
    # open plan is revalidated below against its exact current source.
    doc = await service.db.delivery_plans.find_one({
        "owner_id": row["owner_id"], "source_type": "agent_need", "source_id": row["id"],
        "$or": [{"status": {"$in": ["pending", "held"]}},
                {"status": "delivered", "delivered_at": {"$gte": row["delivery_review_started_at"]}}],
    }, {"_id": 0}, sort=[("created_at", -1), ("id", -1)])
    if doc is None:
        return None
    plan = DeliveryPlan.model_validate(doc)
    subject = await service._current_subject_for_plan(row["owner_id"], plan, allow_delivered=True)
    await service._check_admission_lease(row["owner_id"], "agent_need", row["id"])
    if subject is None:
        if plan.is_open:
            await service.cancel_for_source(
                row["owner_id"], row["id"], source_type="agent_need",
                reason="la richiesta o il suo esito non sono più attuali",
            )
        return DeliveryResult(blocked_by="agent_need_source_changed")
    if plan.is_open and service._expired(plan):
        plan.status = "expired"
        plan.decision_provenance = "code_expiry"
        await service.repo.save_plan(plan)
        return None  # An expired intention is not a completed handoff.
    if plan.status == "pending":
        wake_query = {
            "owner_id": row["owner_id"], "delivery_plan_id": plan.id,
            "reason": "delivery_recheck", "status": {"$in": ["pending", "claimed"]},
        }
        if not await service.db.ambient_wakes.find_one(wake_query, {"_id": 1}):
            when = (datetime.fromisoformat(plan.not_before.replace("Z", "+00:00"))
                    if plan.not_before else datetime.now(timezone.utc))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            await AmbientService(service.db).schedule(
                row["owner_id"], reason="delivery_recheck", when=when,
                plan_id=plan.id, source_ref=f"agent_need:{row['id']}",
                provenance="code_schedule",
            )
        if not await service.db.ambient_wakes.find_one(wake_query, {"_id": 1}):
            return DeliveryResult(unavailable=True, blocked_by="delivery_wake_unavailable")
    # Delivered is history; held follows its existing permission/transport
    # policy, including the prohibition on blindly retrying unknown receipt.
    return DeliveryResult(mode=plan.mode, plan=plan, blocked_by=f"existing_plan_{plan.status}")


async def _review_need(db, row, *, moment, app_state="unknown", language=None):
    from agent.models import CommunicationNeed
    from delivery.models import DeliveryResult, DeliverySubject
    from delivery.service import DeliveryService

    service = DeliveryService(db, admission_fence={
        "id": row["id"], "owner_id": row["owner_id"],
        "delivery_review_revision": row["delivery_review_revision"],
        "delivery_review_token": row["delivery_review_token"],
    })
    result = None
    outcome, error_kind = "unavailable", ""

    async def evaluate():
        await service._check_admission_lease(row["owner_id"], "agent_need", row["id"])
        if row["status"] != "open" or _expiry_state(row, moment) == "expired":
            await service.cancel_for_source(
                row["owner_id"], row["id"], source_type="agent_need",
                reason="la richiesta è chiusa o il momento utile è passato",
            )
            return DeliveryResult(blocked_by="agent_need_source_changed")
        if _expiry_state(row, moment) == "invalid_expiry":
            return DeliveryResult(unavailable=True, blocked_by="invalid_valid_until")
        if row["delivery_review_attempts"] > 1:
            recovered = await _recover_need_plan(service, row)
            if recovered is not None:
                return recovered
        if row.get("delivery_review_recovery_only") is True:
            return DeliveryResult(unavailable=True, blocked_by="review_attempts_exhausted")
        need = CommunicationNeed.model_validate(row)
        return await service.evaluate_subject(
            row["owner_id"], DeliverySubject.model_validate(need.as_subject()),
            app_state=app_state, language=language or row.get("delivery_review_language", "it"),
        )

    try:
        result = await asyncio.wait_for(evaluate(), TIMEOUT_SECONDS)
        if result is not None and not result.unavailable:
            outcome = result.blocked_by or result.mode
        elif result is not None:
            error_kind = result.blocked_by
    except Exception as exc:
        error_kind = type(exc).__name__
    attempts = row["delivery_review_attempts"]
    due = ((moment + timedelta(seconds=60 * (5 ** (attempts - 1)))).isoformat()
           if outcome == "unavailable" and attempts < MAX_ATTEMPTS else None)
    state = "pending" if due else ("paused" if outcome == "unavailable" else "settled")
    fence = {"id": row["id"], "owner_id": row["owner_id"],
             "delivery_review_revision": row["delivery_review_revision"],
             "delivery_review_token": row["delivery_review_token"]}
    await db[NEEDS].update_one(fence, {"$set": {
        "delivery_review_due": due, "delivery_review_state": state,
        "delivery_review_outcome": outcome, "delivery_review_error_kind": error_kind,
        "delivery_review_finished_at": datetime.now(timezone.utc).isoformat(),
    }})
    await db[NEEDS].update_one(fence, {"$unset": {
        "delivery_review_token": "", "delivery_review_lease_until": "",
    }})
    logger.info("need_delivery_admission outcome=%s state=%s attempt=%d", outcome, state, attempts)
    return result or DeliveryResult(unavailable=True, reason="Il giudizio di consegna non è disponibile.")


async def _record_need_review(db, owner_id, need_id, *, moment, language, renew_settled=False):
    query = {"id": need_id, "owner_id": owner_id, "status": "open"}
    if renew_settled:
        query["$or"] = [{"delivery_review_state": {"$exists": False}},
                        {"delivery_review_state": "settled"}]
    else:
        query["delivery_review_state"] = {"$exists": False}
    await db[NEEDS].update_one(query, {"$set": {
        "delivery_review_revision": uuid.uuid4().hex,
        "delivery_review_due": moment.isoformat(), "delivery_review_state": "pending",
        "delivery_review_started_at": moment.isoformat(),
        "delivery_review_attempts": 0, "delivery_review_outcome": None,
        "delivery_review_error_kind": "", "delivery_review_language": language,
    }})


async def register_need(db, owner_id, need_id, *, language="it") -> bool:
    """Persist only the intent, idempotently; spend no claim or model call.

    Completion replay can acknowledge an already settled, paused or closed
    Need's prior intent. It must not restart that judgement after a lost ack.
    Storage errors propagate so the caller keeps its own checkpoint pending.
    """
    await _record_need_review(db, owner_id, need_id, moment=datetime.now(timezone.utc), language=language)
    return bool(await db[NEEDS].find_one({
        "id": need_id, "owner_id": owner_id,
        "delivery_review_state": {"$in": ["pending", "paused", "settled"]},
        "delivery_review_revision": {"$type": "string"},
    }, {"_id": 1}))


async def offer_need(db, owner_id, need_id, *, app_state="unknown", language="it"):
    """Persist a judgement intent before evaluating; never choose a mode."""
    from delivery.models import DeliveryResult

    moment = datetime.now(timezone.utc)
    # A new explicit offer keeps its existing settled-review behaviour;
    # registration-only replay above never renews a settled judgement.
    await _record_need_review(db, owner_id, need_id, moment=moment, language=language, renew_settled=True)
    row = await _claim_need(db, moment=moment, owner_id=owner_id, need_id=need_id)
    if row is None:
        existing = await db[NEEDS].find_one({"id": need_id, "owner_id": owner_id}, {"status": 1})
        if existing is None or existing["status"] != "open":
            return DeliveryResult(blocked_by="agent_need_source_changed")
        return DeliveryResult(unavailable=True, reason="Il riesame di consegna è già registrato.")
    return await _review_need(db, row, moment=moment, app_state=app_state, language=language)


async def drain_needs(db, *, owner_id=None, now=None, limit=2, owners_seen=None,
                      allow_owner_fallback=True, candidate=None) -> int:
    """Use the current source and the existing admission budget, after reload."""
    moment = now or datetime.now(timezone.utc)
    seen = owners_seen if owners_seen is not None else set()
    handled = 0
    for _ in range(min(limit, 1) if candidate is not None else limit):
        row = await _claim_need(db, moment=moment, owner_id=owner_id, owners_seen=seen,
                                allow_owner_fallback=allow_owner_fallback, candidate=candidate)
        if row is None:
            break
        seen.add(str(row["owner_id"]))
        await _review_need(db, row, moment=moment)
        handled += 1
    return handled


async def drain(db, *, owner_id=None, now=None, limit=2, owners_seen=None,
                allow_owner_fallback=True, candidate=None) -> int:
    from delivery.service import DeliveryService

    moment = now or datetime.now(timezone.utc)
    stamp = moment.isoformat()
    handled = 0
    owners_seen = owners_seen if owners_seen is not None else set()
    for _ in range(min(limit, 1) if candidate is not None else limit):
        query = _selected_review(_opportunity_due_query(stamp, owner_id=owner_id), candidate)
        token = uuid.uuid4().hex
        # One owner with a deep inbox must not starve another owner whose
        # first pending update is equally due. The batch remains limited,
        # atomic Mongo claims are unchanged, and a single active owner still
        # gets all available slots.
        fair_query = dict(query)
        if candidate is None and owner_id is None and owners_seen:
            fair_query["owner_id"] = {"$nin": sorted(owners_seen)}
        change = {
            "$set": {
                "delivery_review_token": token,
                "delivery_review_lease_until": (
                    moment + timedelta(seconds=LEASE_SECONDS)
                ).isoformat(),
            },
            "$inc": {"delivery_review_attempts": 1},
        }
        row = await db[COLLECTION].find_one_and_update(
            fair_query, change,
            sort=[("delivery_review_due", 1), ("id", 1)],
            return_document=ReturnDocument.AFTER,
        )
        if row is None and candidate is None and owner_id is None and owners_seen and allow_owner_fallback:
            row = await db[COLLECTION].find_one_and_update(
                query, change,
                sort=[("delivery_review_due", 1), ("id", 1)],
                return_document=ReturnDocument.AFTER,
            )
        if row is None:
            break
        owners_seen.add(str(row["owner_id"]))

        outcome = "unavailable"
        error_kind = ""
        try:
            service = DeliveryService(db)
            expiry_state = _expiry_state(row, moment)
            if row["status"] != "active":
                await service.cancel_for_opportunity(
                    row["owner_id"], row["id"], reason="la questione non è più aperta"
                )
                outcome = "closed"
            elif expiry_state == "expired":
                await service.cancel_for_opportunity(
                    row["owner_id"], row["id"], reason="il momento utile è passato"
                )
                outcome = "expired"
            elif expiry_state == "invalid_expiry":
                error_kind = "invalid_valid_until"
            else:
                result = await asyncio.wait_for(
                    service.evaluate(row["owner_id"], row["id"]), TIMEOUT_SECONDS
                )
                if not result.unavailable:
                    outcome = result.mode or result.blocked_by or "in_app"
        except Exception as exc:
            # The due field stays on the record; an expired lease is reclaimable.
            error_kind = type(exc).__name__

        attempts = int(row["delivery_review_attempts"])
        due = None
        if outcome == "unavailable" and attempts < MAX_ATTEMPTS:
            due = (moment + timedelta(seconds=60 * (5 ** (attempts - 1)))).isoformat()
        state = "pending" if due else ("paused" if outcome == "unavailable" else "settled")
        fence = {"id": row["id"], "owner_id": row["owner_id"],
                 "delivery_review_token": token,
                 "delivery_review_revision": row["delivery_review_revision"]}
        await db[COLLECTION].update_one(fence, {"$set": {
            "delivery_review_due": due,
            "delivery_review_state": state,
            "delivery_review_outcome": outcome,
            "delivery_review_error_kind": error_kind,
            "delivery_review_finished_at": datetime.now(timezone.utc).isoformat(),
        }})
        # Do not remove another worker's lease; a new source revision stays due.
        await db[COLLECTION].update_one(
            {"id": row["id"], "owner_id": row["owner_id"], "delivery_review_token": token},
            {"$unset": {"delivery_review_token": "", "delivery_review_lease_until": ""}},
        )
        logger.info("delivery_admission outcome=%s state=%s attempt=%d", outcome, state, attempts)
        handled += 1
    return handled


async def _completion_candidates(db, moment, *, owners_seen=None, completion_candidate=None):
    from agent import completion_handoff

    need, opportunity = await asyncio.gather(
        _next_review_due(db, NEEDS, _need_due_query(moment.isoformat()), owners_seen=owners_seen),
        _next_review_due(db, COLLECTION, _opportunity_due_query(moment.isoformat()), owners_seen=owners_seen),
    )
    completion = completion_candidate
    if completion is None:
        completion = await completion_handoff.next_due(
            db, now=moment, owners_seen=owners_seen, allow_owner_fallback=False,
        )
    return [(kind, row) for kind, row in (
        ("need", need), ("opportunity", opportunity), ("completion", completion),
    ) if row is not None]


async def _drain_with_completion(db, moment, first_completion):
    """Share the same two slots; a peek cannot claim or spend a model call."""
    from agent import completion_handoff

    seen, used = set(), set()
    handled = 0
    candidates = await _completion_candidates(db, moment, completion_candidate=first_completion)
    runners = {"need": drain_needs, "opportunity": drain, "completion": completion_handoff.drain}
    for slot in range(2):
        if slot:
            moment = datetime.now(timezone.utc)
            # Owner precedence applies across all three queues. Only when no
            # other owner has due work may a slot return to an owner seen here.
            candidates = await _completion_candidates(db, moment, owners_seen=seen)
            if not candidates:
                candidates = await _completion_candidates(db, moment)
        candidates.sort(key=lambda item: (item[0] in used, item[1]["due_at"], item[0], item[1]["id"]))
        for kind, candidate in candidates:
            count = await runners[kind](
                db, now=moment, limit=1, owners_seen=seen, candidate=candidate,
            )
            if count:
                handled += count
                used.add(kind)
                break
            # A lost claim cannot select another record inside that queue.
            # Try only the other bounded candidates already observed.
        else:
            break
    return handled


async def drain_with_receipts(db) -> int:
    """Run bounded admission and check Expo receipts without adding a lane.

    This module owns the provider boundary. Ambient only schedules a generic
    delivery pass and cannot gain direct access to notification transport.
    """
    from agent import completion_handoff

    moment = datetime.now(timezone.utc)
    completion = await completion_handoff.next_due(db, now=moment)
    if completion is not None:
        handled = await _drain_with_completion(db, moment, completion)
    else:
        # Preserve the existing two-queue pass when no completion is due.
        # Keep the two-item/120-second budget, prefer another owner before
        # the other category, and lend unused capacity to the nonempty queue.
        seen: set[str] = set()
        handled = await drain_needs(db, limit=1, owners_seen=seen)
        if handled:
            other = await drain(db, limit=1, owners_seen=seen, allow_owner_fallback=False)
            if not other:
                other = await drain_needs(db, limit=1, owners_seen=seen, allow_owner_fallback=False)
            if not other:
                other = await drain(db, limit=1, owners_seen=seen)
            if not other:
                other = await drain_needs(db, limit=1, owners_seen=seen)
            handled += other
        else:
            handled = await drain(db)
    # Replay already-admitted Home news that a crash or transient Mongo error
    # prevented from becoming a visible AmbientActivity. No new judgement,
    # notifications or extra scheduler are created.
    try:
        from agent.visibility import VisibilityService

        await VisibilityService(db).recover_pending_home()
    except Exception as exc:
        logger.info("durable Home delivery deferred: %s", type(exc).__name__)
    # Recreate an authorized retry wake after a crash between persisting a
    # held plan and storing its scheduled alarm. It never sends directly.
    try:
        from delivery.transport_retry import recover_unscheduled_retries

        await recover_unscheduled_retries(db)
    except Exception as exc:
        logger.info("delivery retry recovery deferred: %s", type(exc).__name__)
    from ambient.push import ExpoNotificationProvider
    from delivery.provider import get_provider

    if isinstance(get_provider(), ExpoNotificationProvider):
        from delivery.expo_receipts import ExpoReceiptAudit

        try:
            await ExpoReceiptAudit(db).run_due()
        except Exception as exc:
            # Receipt claims remain durable for another pass.
            logger.info("expo receipt audit deferred: %s", type(exc).__name__)
    return handled
