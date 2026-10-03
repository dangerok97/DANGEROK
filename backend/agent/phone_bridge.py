"""Wake a durable agent goal when its real phone mission finishes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger("ora.agent.phone_bridge")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def on_call_finished(db, call) -> bool:
    receipt = await db.agent_receipts.find_one(
        {"owner_id": call.owner_id, "capability": "phone.call", "external_ref": call.id},
        {"_id": 0},
    )
    if not receipt:
        return False

    from telephone.application import application_for
    application = await application_for(db, call.id)
    status = str(getattr(application, "application_status", "") or "")
    if status not in ("applied", "conflict", "failed", "skipped"):
        return False

    succeeded = status == "applied"
    await db.agent_receipts.update_one(
        {"id": receipt.get("id"), "owner_id": call.owner_id},
        {"$set": {
            "provider_status": "succeeded" if succeeded else "failed",
            "answered_at": _now(),
            "error_type": "" if succeeded else status[:80],
            "retryable": False,
            "result_refs": list(getattr(application, "writes", None) or [])[:8] if succeeded else [],
        }},
    )

    goal_id = str(receipt.get("goal_id") or "")
    if not goal_id:
        return True

    if succeeded:
        try:
            from telephone.binding import binding_for, calendar_event_snapshot
            binding = await binding_for(db, call.id)
            row = (
                await calendar_event_snapshot(db, call.owner_id, binding.target.entity_id)
                if binding is not None else None
            )
            if binding is not None and row:
                from agent.evidence import EvidenceStore
                from agent.models import AgentEvidence, ResultProvenance
                await EvidenceStore(db).record(AgentEvidence(
                    owner_id=call.owner_id,
                    goal_id=goal_id,
                    step_id=str(receipt.get("action_intent_id") or ""),
                    kind="verify",
                    claim=(
                        f"Nel calendario ORA «{row.get('title') or 'l’impegno'}» "
                        f"risulta ora con inizio {row.get('start_datetime') or ''}; "
                        "la modifica è stata riletta dopo la conferma telefonica."
                    )[:600],
                    supports="lo spostamento concordato è presente nello stato canonico",
                    provenance=ResultProvenance(
                        source_class="internal_observation",
                        capability="calendar.local.read",
                        provider="ora_calendar",
                        source_refs=[
                            f"calendar:{binding.target.entity_id}", f"phone:{call.id}"
                        ],
                        freshness="fresh",
                        certainty_note="stato canonico riletto dopo l'esito telefonico",
                    ),
                ))
        except Exception as exc:
            logger.info("phone-agent evidence soft-fail: %s", type(exc).__name__)

    await db.agent_goals.update_one(
        {
            "id": goal_id, "owner_id": call.owner_id,
            "status": {"$in": ["active", "waiting", "proposed"]},
        },
        {"$set": {
            "status": "active",
            "requires_user_input": False,
            "requires_user_authority": False,
            "next_run_at": _now(),
        }},
    )
    try:
        from ambient.service import AmbientService
        await AmbientService(db).schedule(
            call.owner_id,
            reason="opportunity_revisit",
            when=datetime.now(timezone.utc),
            source_ref=f"goal:{goal_id}",
            provenance="code_schedule",
        )
    except Exception as exc:
        logger.info("phone-agent wake soft-fail: %s", type(exc).__name__)
    return True
