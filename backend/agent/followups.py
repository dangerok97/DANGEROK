"""Resume autonomous goals when an awaited external reply actually arrives.

This bridge is deliberately narrow and structural:
- a sent Gmail receipt records the provider thread id;
- a later external Gmail signal in that exact thread can wake the same goal;
- no subject matching, sender-name guessing or body inspection happens here.

The reply body is still private and transient. Resuming only adds one mail:<id>
handle; the ordinary mail.read capability decides whether/when to read it.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Set

from agent.models import ActionStep
from agent.repository import AgentRepository

logger = logging.getLogger(__name__)

THREAD_PREFIX = "gmail_thread:"
MAIL_PREFIX = "mail:"
MAX_MATCHED_GOALS = 4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def resume_email_reply(db, owner_id: str, signal) -> int:
    """Wake waiting goals bound to the exact Gmail thread of this external reply."""
    if (
        getattr(signal, "source_type", "") != "email"
        or getattr(signal, "origin", "") != "external"
    ):
        return 0

    provenance = dict(getattr(signal, "provenance", {}) or {})
    thread_id = str(provenance.get("thread_ref") or "").strip()
    message_id = str(getattr(signal, "source_object_ref", "") or "").strip()
    if not thread_id or not message_id:
        return 0

    thread_ref = f"{THREAD_PREFIX}{thread_id}"[:200]
    mail_ref = f"{MAIL_PREFIX}{message_id}"[:120]

    receipts = await db.agent_receipts.find(
        {
            "owner_id": owner_id,
            "capability": "mail.send",
            "result_refs": thread_ref,
            "provider_status": {"$in": ["accepted", "succeeded", "partial"]},
        },
        {"_id": 0, "goal_id": 1, "answered_at": 1},
    ).sort("answered_at", -1).to_list(20)

    repo = AgentRepository(db)
    resumed = 0
    seen_goals: Set[str] = set()

    for receipt in receipts:
        if resumed >= MAX_MATCHED_GOALS:
            break
        goal_id = str(receipt.get("goal_id") or "")
        if not goal_id or goal_id in seen_goals:
            continue
        seen_goals.add(goal_id)

        goal = await repo.get_goal(owner_id, goal_id)
        if (
            goal is None
            or goal.status != "waiting"
            or goal.requires_user_input
            or goal.requires_user_authority
        ):
            continue
        if mail_ref in goal.source_refs:
            continue

        plan = await repo.plan_for(owner_id, goal_id)
        if plan is None:
            continue

        # The external dependency happened. Keep that fact in the plan history.
        waiting_steps = [
            step for step in plan.steps
            if step.step_type == "wait" and step.status == "waiting"
        ]
        for step in waiting_steps:
            step.status = "succeeded"
            step.note = "La risposta esterna attesa è arrivata."

        already_planned = any(
            step.capability_needed == "mail.read"
            and mail_ref in step.input_refs
            and step.status in ("pending", "waiting", "blocked")
            for step in plan.steps
        )
        if not already_planned:
            followup = ActionStep(
                ordinal=max([step.ordinal for step in plan.steps] or [-1]) + 1,
                intent="Leggere la nuova risposta arrivata nel thread atteso",
                step_type="inspect",
                capability_needed="mail.read",
                input_refs=[mail_ref],
                expected_result=(
                    "Capire se la risposta cambia l'esito o richiede un altro passo"
                ),
            )
            if len(plan.steps) < 12:
                plan.steps.append(followup)
            elif waiting_steps:
                # Extremely full plans still need a continuation path. Reuse
                # the unresolved wait placeholder only in this bounded fallback;
                # all earlier completed work remains immutable.
                slot = waiting_steps[-1]
                slot.intent = followup.intent
                slot.step_type = followup.step_type
                slot.capability_needed = followup.capability_needed
                slot.input_refs = followup.input_refs
                slot.expected_result = followup.expected_result
                slot.status = "pending"
                slot.note = "La risposta è arrivata; verifico il nuovo messaggio."
            else:
                continue

        goal.source_refs = list(dict.fromkeys([*goal.source_refs, mail_ref]))[:8]
        goal.status = "active"
        goal.next_run_at = _now_iso()
        plan.status = "active"
        await repo.save_goal(goal)
        await repo.save_plan(plan)
        await repo.journal(
            owner_id,
            goal_id,
            kind="external_reply_arrived",
            note="È arrivata una nuova risposta nel thread Gmail atteso.",
            detail={"source_ref": mail_ref, "thread_ref": thread_ref},
        )

        try:
            from ambient.service import AmbientService
            await AmbientService(db).schedule(
                owner_id,
                reason="opportunity_revisit",
                when=datetime.now(timezone.utc),
                source_ref=f"goal:{goal_id}",
                provenance="code_schedule",
            )
        except Exception as exc:
            logger.info("external reply wake soft-fail: %s", type(exc).__name__)

        resumed += 1

    return resumed
