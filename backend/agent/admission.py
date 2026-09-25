"""Durable goal admission on opportunity records, consumed by the existing runtime.

No new scheduler. Saving a concern also saves its pending admission. A lease
serializes consumers; a revision fence prevents an old answer settling new facts.
Only records written through the new save path qualify (no historical backfill).
"""
import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument

COLLECTION = "opportunities"
LEASE_SECONDS = 120
TIMEOUT_SECONDS = 45
MAX_ATTEMPTS = 3
logger = logging.getLogger(__name__)


def fingerprint(opportunity):
    # Presentation timestamps / surfacing must not restart cognitive work.
    fields = ("status", "semantic_summary", "why_it_matters", "why_now",
              "initiative", "what_ora_can_do", "evidence", "requires_clarification",
              "clarifying_question", "needs_research", "research_question",
              "related_goal_id", "related_place_id", "related_work_id", "valid_until")
    payload = opportunity.model_dump(mode="json")
    return hashlib.sha256(json.dumps({k: payload.get(k) for k in fields},
                                     sort_keys=True).encode()).hexdigest()


async def drain(db, *, owner_id=None, now=None, limit=2):
    from agent.service import AgentService
    from opportunities.models import Opportunity

    moment = now or datetime.now(timezone.utc)
    stamp = moment.isoformat()
    handled = 0
    for _ in range(limit):
        query = {
            "status": "active",
            "agent_review_due": {"$type": "string", "$lte": stamp},
            "$or": [{"agent_review_lease_until": {"$exists": False}},
                    {"agent_review_lease_until": {"$lte": stamp}}],
        }
        if owner_id is not None:
            query["owner_id"] = owner_id
        token = uuid.uuid4().hex
        row = await db[COLLECTION].find_one_and_update(
            query, {"$set": {"agent_review_token": token,
                             "agent_review_lease_until": (moment + timedelta(seconds=LEASE_SECONDS)).isoformat()},
                    "$inc": {"agent_review_attempts": 1}},
            sort=[("agent_review_due", 1), ("id", 1)],
            return_document=ReturnDocument.AFTER,
        )
        if row is None:
            break
        fence = {"id": row["id"], "owner_id": row["owner_id"],
                 "agent_review_token": token, "agent_review_revision": row["agent_review_revision"]}
        answer = {"outcome": "unavailable"}
        error_kind = ""
        try:
            opp = Opportunity.model_validate(row)
            expiry = datetime.fromisoformat(opp.valid_until) if opp.valid_until else None
            if expiry is not None and expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry is not None and expiry <= moment:
                answer = {"outcome": "expired"}
            elif int(row["agent_review_attempts"]) > MAX_ATTEMPTS:
                answer = {"outcome": "paused"}
            else:
                answer = await asyncio.wait_for(AgentService(db).consider(
                    row["owner_id"], situation={
                        "what": opp.semantic_summary,
                        "why_it_matters": opp.why_it_matters,
                        "why_now": opp.why_now or None,
                        "waiting_on_an_answer": opp.requires_clarification,
                        "the_question": opp.clarifying_question or None,
                        "how_far_ora_meant_to_go": opp.initiative,
                        "what_ora_offered_to_do": opp.what_ora_can_do or None,
                        "needs_research": opp.needs_research,
                        "research_question": opp.research_question or None,
                    }, origin="agent_initiated", opportunity_id=opp.id,
                    source_kind="opportunity", source_refs=[e.ref for e in opp.evidence][:4],
                ), timeout=TIMEOUT_SECONDS)
        except Exception as exc:
            # Cancellation propagates: a dead worker leaves a reclaimable lease.
            error_kind = type(exc).__name__

        if not isinstance(answer, dict):
            answer = {"outcome": "unavailable"}
        outcome = answer.get("outcome", "unavailable")
        known = {"no_goal", "create_goal", "already_pursuing", "clarify", "wait", "expired", "paused", "unavailable"}
        if outcome not in known:
            outcome = "unavailable"
        attempts = int(row["agent_review_attempts"])
        due = None
        if outcome in ("unavailable", "wait") and attempts < MAX_ATTEMPTS:
            delay = 3600 if outcome == "wait" else 60 * (5 ** (attempts - 1))
            due = (moment + timedelta(seconds=delay)).isoformat()
        state = "pending" if due else ("paused" if outcome in ("unavailable", "wait", "paused") else "settled")
        await db[COLLECTION].update_one(fence, {"$set": {
            "agent_review_due": due, "agent_review_state": state,
            "agent_review_outcome": outcome,
            "agent_review_reason": str(answer.get("reasoning") or "")[:400],
            "agent_review_question": str(answer.get("question") or "")[:300],
            "agent_review_error_kind": error_kind,
            "agent_review_goal_id": str(answer.get("goal_id") or (answer.get("goal") or {}).get("id") or "")[:64],
            "agent_review_finished_at": datetime.now(timezone.utc).isoformat(),
        }})
        # Also release a stale revision's lease, but never somebody else's lease.
        await db[COLLECTION].update_one(
            {"id": row["id"], "owner_id": row["owner_id"], "agent_review_token": token},
            {"$unset": {"agent_review_token": "", "agent_review_lease_until": ""}},
        )
        logger.info("agent_admission outcome=%s state=%s attempt=%d", outcome, state, attempts)
        handled += 1
    return handled
