"""An admission question is actionable even before a goal exists.

Replies stay attached to the exact question/revision. They enqueue the existing
admission worker; they are facts to consider, never authority to act.
"""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException


async def answer_question(db, owner, opportunity_id, reply, revision):
    reply = reply.strip()
    if not reply or len(reply) > 2000:
        raise HTTPException(422, "Scrivi una risposta alla domanda.")
    key = {"id": opportunity_id, "owner_id": owner, "status": "active"}
    row = await db.opportunities.find_one(key)
    if not row:
        raise HTTPException(404, "Aggiornamento non disponibile.")
    if (revision and row.get("agent_review_last_answer_revision") == revision
            and row.get("agent_review_last_answer") == reply):
        return  # A retried request must not spend another admission/model call.
    if (not revision or row.get("agent_review_revision") != revision
            or row.get("agent_review_outcome") != "clarify"
            or not row.get("agent_review_question")):
        raise HTTPException(409, "La domanda è cambiata. Rileggi l’aggiornamento prima di rispondere.")
    now = datetime.now(timezone.utc)
    if row.get("valid_until"):
        expiry = datetime.fromisoformat(row["valid_until"])
        if (expiry if expiry.tzinfo else expiry.replace(tzinfo=timezone.utc)) <= now:
            raise HTTPException(409, "Questo aggiornamento è scaduto.")
    result = await db.opportunities.update_one(
        {**key, "agent_review_revision": revision, "agent_review_outcome": "clarify"},
        {"$set": {
            "agent_review_revision": uuid.uuid4().hex,
            "agent_review_state": "pending", "agent_review_outcome": None,
            "agent_review_question": "", "agent_review_due": now.isoformat(),
            "agent_review_attempts": 0, "agent_review_last_answer_revision": revision,
            "agent_review_last_answer": reply,
        }, "$push": {"agent_review_answers": {"$each": [{
            "question": row["agent_review_question"], "answer": reply,
            "answered_at": now.isoformat(),
        }], "$slice": -3}}},
    )
    if not result.modified_count:
        latest = await db.opportunities.find_one(key)
        if (latest or {}).get("agent_review_last_answer_revision") == revision and latest.get("agent_review_last_answer") == reply:
            return
        raise HTTPException(409, "La domanda è cambiata. Rileggi l’aggiornamento.")


async def work_view(db, owner, opportunity_id):
    """Existing update detail can show automatic work without launching a copy."""
    row = await db.opportunities.find_one({"id": opportunity_id, "owner_id": owner})
    if not row or row.get("status") != "active":
        return None
    if row.get("agent_review_outcome") == "clarify" and row.get("agent_review_question"):
        return {"status": "needs_user", "question_revision": row["agent_review_revision"],
                "result": {"ok": True, "question": row["agent_review_question"]}}
    if row.get("agent_review_state") == "pending":
        # Admission already owns the work, including the first write-to-wake
        # gap and a revised source. Do not launch a parallel manual session or
        # expose an older preparation while its replacement is still pending.
        return {"status": "running", "message": (
            "Risposta ricevuta. Riprendo la verifica." if row.get("agent_review_answers")
            else "Sto verificando questo aggiornamento.")}
    goal_id = row.get("agent_review_goal_id")
    if goal_id:
        from agent.service import AgentService
        service = AgentService(db)
        goal = await service.repo.get_goal(owner, goal_id)
        if goal:
            needs = await service.needs.open_for_goal(owner, goal_id)
            need = next((n for n in needs if n.requires_response), None)
            route = f"/ora?needId={need.id}&goalId={goal.id}" if need else None
            return {"status": "needs_user" if need else "running" if goal.next_run_at else "ready",
                    "message": await service._progress_of(owner, goal),
                    "result": {"ok": True, "ora_text": goal.prepared_text or None,
                               "route": route}}
    if row.get("agent_review_answers"):
        pending = row.get("agent_review_state") == "pending"
        return {"status": "running" if pending else "ready",
                "message": "Risposta ricevuta. Riprendo la verifica." if pending else (
                    "Non sono riuscita a completare la verifica. La tua risposta è conservata."
                    if row.get("agent_review_state") == "paused" else
                    row.get("agent_review_reason") or "Verifica conclusa: non è emersa un’altra attività utile.")}
    return None
