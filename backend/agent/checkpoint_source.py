"""Carry out an explicitly chosen READ-ONLY checkpoint skill at its due time.

The model may select the skill when it first schedules the checkpoint; after
that, the scheduled wake executes the *same skill*, rather than asking an
LLM to re-plan the read and potentially doing nothing. The result is durable
evidence, not a claim about any physical object's state.

This supports one opt-in capability (weather.read). Expanding the allowlist
requires separate source/authority and user-acceptance tests.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from agent.models import ActionStep
from situations.repository import SituationRepository

logger = logging.getLogger(__name__)
_ALLOWED = frozenset({"weather.read"})


def checkpoint_capability(name: str) -> str:
    return name if str(name or "").strip() in _ALLOWED else ""


def _instant(value):
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return moment.astimezone(timezone.utc) if moment.tzinfo else None
    except (TypeError, ValueError, OverflowError):
        return None


async def run_due_checkpoint_source(service, owner_id: str, goal, *, budget):
    """Idempotent owner-scoped, read-only source step before AI deliberation.

    Called only by a due Ambient wake while AgentRepository holds the goal
    lease. Its durable checkpoint_due_at is independent of the temporary
    5-minute technical retry; retries never pretend to be a new checkpoint.
    """
    capability = checkpoint_capability(
        (goal.source_situation or {}).get("checkpoint_read_capability")
    )
    due = _instant((goal.source_situation or {}).get("checkpoint_due_at"))
    if not capability or due is None or due > datetime.now(timezone.utc):
        return {"state": "no_explicit_due_source"}
    if goal.source_kind != "situation_followup" or goal.owner_id != owner_id:
        return {"state": "source_not_applicable"}

    refs = [str(ref) for ref in (goal.source_refs or [])
            if str(ref).startswith("situation:")]
    if len(refs) != 1:
        return {"state": "ambiguous_source"}
    sid = refs[0].split(":", 1)[1]
    revision = str((goal.source_situation or {}).get("situation_revision") or "")
    situation = await SituationRepository(service.db).get(owner_id, sid)
    if (situation is None or situation.status not in ("active", "changed")
            or not revision or revision != str(situation.revision)):
        return {"state": "source_not_current"}

    canonical_due = due.isoformat()
    fingerprint = hashlib.sha256(
        f"{owner_id}|{goal.id}|{sid}|{revision}|{canonical_due}|{capability}".encode()
    ).hexdigest()[:22]
    step_id = "stp_chk_" + fingerprint
    was_done = await service.db.agent_journal.find_one(
        {"owner_id": owner_id, "goal_id": goal.id,
         "kind": "step_done", "detail.step_id": step_id,
         "detail.status": "succeeded", "detail.really_happened": True},
        {"_id": 0, "at": 1},
    )
    if was_done:
        return {"state": "already_verified", "step_id": step_id}

    step = ActionStep(
        id=step_id,
        step_type="inspect",
        intent="Rileggere la fonte esterna già selezionata per il controllo",
        capability_needed=capability,
        expected_result="Osservazione reale aggiornata con fonte, luogo e data",
    )
    result = await service.executor.run(
        owner_id, goal, step, may_touch_the_world=False, budget=budget,
    )
    # The normal StepExecutor persists claims before returning. Keep the
    # journal in the same format as a model-chosen step for audit compatibility.
    await service.repo.journal(
        owner_id, goal.id, kind="step_done",
        note=str(result.observation or "")[:200],
        detail={
            "step_id": step_id, "status": result.status,
            "really_happened": result.is_real,
            "came_from": result.provenance.source_class,
            "evidence": len(result.evidence_refs),
            "checkpoint_source": True,
            "error_code": str(result.error_type or "")[:72],
        },
    )
    if result.status != "succeeded" or not result.is_real or not result.evidence_refs:
        return {
            "state": "source_read_unavailable", "step_id": step_id,
            "reason": str(result.error_type or "no_verified_evidence")[:72],
        }

    # Never deliver an observation from a cancelled/revised Situation even
    # if a provider call returned after that change.
    current = await SituationRepository(service.db).get(owner_id, sid)
    if (current is None or current.status not in ("active", "changed")
            or str(current.revision) != revision):
        return {"state": "source_changed", "step_id": step_id}

    # A read has to be tied to this same provider location; GPS and a
    # different owner's or Situation's evidence are not substitutes.
    evidence_ids = set(result.evidence_refs)
    rows = [
        item for item in await service.evidence.for_goal(owner_id, goal.id)
        if item.id in evidence_ids and item.step_id == step_id
        and item.provenance.capability == capability and item.is_real
        and f"situation:{sid}:revision:{revision}" in item.provenance.source_refs
        and any(str(ref).startswith(("google_place:", "place:"))
                for ref in item.provenance.source_refs)
    ]
    if not rows:
        return {"state": "source_binding_unverified", "step_id": step_id}

    from delivery.service import DeliveryService
    provenance = rows[0].provenance
    weather_claim = next(
        (str(item.claim) for item in rows
         if str(item.claim).startswith("Condizioni riportate")), ""
    )
    place = str(current.location_label or "luogo verificato")[:65]
    # No calculated physical outcome. The claim is the provider's recorded
    # observation only and will be explained separately by the AI.
    summary = (
        weather_claim[:190] if weather_claim
        else f"ORA ha letto il meteo di {place} da {provenance.provider or 'fonte meteo'}; "
             "nessuna conclusione sullo stato fisico."
    )[:200]
    await DeliveryService(service.db).note_activity(
        owner_id, kind="evidence_refreshed", summary=summary,
        source_refs=[f"situation:{sid}", f"goal:{goal.id}", *list(evidence_ids)[:3]],
        provenance={
            "agent": "due_checkpoint_source",
            "capability": capability, "provider": provenance.provider,
            "checkpoint_due_at": canonical_due,
            "situation_revision": revision,
            "verified_provider_read": True,
            "physical_outcome_not_observed": True,
        },
        visible=True, activity_id="ambc_" + fingerprint,
    )
    await service.repo.journal(
        owner_id, goal.id, kind="checkpoint_source_verified",
        note="Una lettura esterna verificata è stata resa consultabile dentro ORA.",
        detail={"step_id": step_id, "evidence": len(rows),
                "capability": capability, "checkpoint_due_at": canonical_due},
    )
    return {"state": "source_verified", "step_id": step_id,
            "evidence_count": len(rows)}
