"""Explicit, isolated source-to-Home autonomy acceptance.

The production admission, persisted wakes, Ambient worker, planner, executor,
evidence, preparation, completion and visibility outbox stay connected. Only
one fictional account and a recorded internal note exist. Allowed capabilities
are information.read and document.create; external effects are blocked.

Scripted mode is the mandatory offline contract. Live mode uses the configured
LLM with the same synthetic sources, and fails explicitly when unavailable.
Neither mode claims live third-party facts, a process restart or device receipt;
the separate v162 Mongo/process test establishes restart persistence.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import re
from typing import Any
from unittest.mock import patch

from scripts import phase2_goal_outcome_eval_v140 as baseline
from scripts.phase1_read_provider_eval import _ReadBoundary

VERSION = "autonomy-completion-v162"
OWNER = "ora-synthetic-autonomy-owner-v162"
SCENARIOS = ("completed_result", "planning_outage", "home_write_retry",
             "source_revoked", "memory_revoked", "memory_corrected",
             "source_change_crash", "irrelevant")
LLM_KEYS = ("GEMINI_API_KEY", "GEMINI2_API_KEY", "GEMINI_API_KEY_2", "OPENAI_API_KEY",
            "GROQ_API_KEY", "MISTRAL_API_KEY")
ALLOWED = frozenset(baseline.EXPECTED.values())
MAX_MODEL_CALLS = 40
MAX_MODEL_HTTP_REQUESTS = 80
CASE_TIMEOUT_SECONDS = 240


class EvaluationFailure(RuntimeError):
    """Only fixed diagnostic codes, never provider errors or prompt contents."""


def require(condition, code):
    if not condition:
        raise EvaluationFailure(code)


@dataclass
class Probe:
    model_calls: list[dict[str, Any]] = field(default_factory=list)
    model_attempts: int = 0
    model_http_requests: int = 0
    steps: list[dict[str, str]] = field(default_factory=list)
    ticks: list[dict[str, int]] = field(default_factory=list)
    faults: list[str] = field(default_factory=list)
    blocked_effects: int = 0
    push_attempts: int = 0
    network: Any = None


def model_observations(probe):
    return {"real_model_executed": bool(probe.model_calls),
            "model_calls": probe.model_calls,
            "model_attempts": probe.model_attempts,
            "model_http_requests": probe.model_http_requests,
            # Failed calls may still be billable without returning usage.
            "token_usage_scope": "successful_responses_with_provider_usage_only"}


class BlockedPush:
    name = "evaluation_no_device"

    def __init__(self, probe):
        self.probe = probe

    async def send(self, **kwargs):
        self.probe.push_attempts += 1
        raise EvaluationFailure("DEVICE_SEND_FORBIDDEN")

    async def cancel(self, **kwargs):
        return {"ok": True, "provider": self.name}


@contextmanager
def isolated_engine(db, *, mode="scripted", scenario="completed_result", probe=None):
    """Bound effects without replacing the worker, persistence or Home handoff."""
    from agent import reasoning
    from agent.capabilities import CapabilityResolver
    from agent.execution import StepExecutor
    from agent.models import AgentBudget
    from agent.service import AgentService
    from delivery import provider, reasoning as delivery_reasoning
    from delivery.service import DeliveryService
    from llm.manager import ProviderManager
    from opportunities import reasoning as opportunity_reasoning
    from opportunities.service import OpportunityService

    require(mode in ("scripted", "live"), "UNKNOWN_MODE")
    require(scenario in SCENARIOS, "UNKNOWN_SCENARIO")
    probe = probe or Probe()
    # Scope is normally blocked; only ProviderManager.chat may enable the
    # exact HTTPS model endpoints already audited by the public-read harness.
    boundary = _ReadBoundary(model_live=mode == "live", provider_reply=None)
    probe.network = boundary
    original_chat, original_step = ProviderManager.chat, StepExecutor.run
    original_advance, original_note = AgentService.advance, DeliveryService.note_activity
    original_scan = OpportunityService.scan
    base_plan = baseline.scripted_make_plan if mode == "scripted" else reasoning.make_plan

    async def observed_chat(self, *args, **kwargs):
        probe.model_attempts += 1
        require(mode == "live", "SCRIPTED_CALLED_REAL_MODEL")
        if probe.model_attempts > MAX_MODEL_CALLS:
            boundary.blocked.append("MODEL_CALL_BOUND_EXCEEDED")
            raise EvaluationFailure("MODEL_CALL_BOUND_EXCEEDED")
        token = boundary.scope.set("model")
        try:
            result = await original_chat(self, *args, **kwargs)
            usage = result.usage if isinstance(getattr(result, "usage", None), dict) else {}
            probe.model_calls.append({
                "provider": str(result.provider)[:50], "model": str(result.model)[:100],
                "usage": {key: value for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                          if type(value := usage.get(key)) is int and value >= 0},
            })
            return result
        finally:
            boundary.scope.reset(token)

    async def available(self, owner_id):
        require(self.db is db and owner_id == OWNER, "CAPABILITY_OWNER_BOUNDARY")
        return [{"capability": cap, "status": "available_real", "can_be_used_now": True,
                 "really_does_something": True, "changes_something_in_the_world": False,
                 "why_not": None} for cap in sorted(ALLOWED)]

    async def step(self, owner_id, goal, item, **kwargs):
        if (self.db is not db or owner_id != OWNER or goal.owner_id != OWNER
                or item.capability_needed not in ALLOWED or item.step_type == "execute"):
            probe.blocked_effects += 1
            raise EvaluationFailure("STEP_EFFECT_OR_OWNER_BOUNDARY")
        result = await original_step(self, owner_id, goal, item, **kwargs)
        probe.steps.append({"capability": item.capability_needed, "status": str(getattr(result, "status", ""))})
        return result

    async def bounded_first_read(self, owner_id, goal_id, **kwargs):
        # A documented technical interruption after one real read proves that
        # completion comes from a subsequent persisted wake, not a single call.
        if self.db is db and owner_id == OWNER and not await db.agent_evidence.count_documents({
            "owner_id": OWNER, "goal_id": goal_id, "provenance.capability": "information.read",
        }):
            kwargs["budget"] = AgentBudget(max_steps=1)
        return await original_advance(self, owner_id, goal_id, **kwargs)

    async def plan(*args, **kwargs):
        if scenario == "planning_outage" and "planning_unavailable_once" not in probe.faults:
            probe.faults.append("planning_unavailable_once")
            return None
        result = await base_plan(*args, **kwargs)
        if mode == "scripted" and "memory_corrected_between_wakes" in probe.faults:
            for item in (result or {}).get("steps", []):
                item["expected_result"] = item.get("expected_result", "").replace(
                    "120 euro", "150 euro").replace("60 euro", "30 euro")
        return result

    async def note(self, *args, **kwargs):
        provenance = kwargs.get("provenance") or {}
        current = await db.agent_goals.find_one({
            "owner_id": OWNER, "id": provenance.get("goal"), "status": "completed",
        }) if provenance.get("agent") == "visibility" else None
        if (scenario == "home_write_retry" and current
                and "home_write_failed_once" not in probe.faults):
            probe.faults.append("home_write_failed_once")
            raise ConnectionError("synthetic_home_write_failure")
        return await original_note(self, *args, **kwargs)

    async def decide_goal(*args, **kwargs):
        if scenario == "irrelevant":
            return {"outcome": "no_goal", "reasoning": "Nessun bisogno documentato."}
        return baseline.scripted_goal()

    async def scan(self, *args, **kwargs):
        if scenario == "source_change_crash" and "source_scan_cancelled_once" not in probe.faults:
            probe.faults.append("source_scan_cancelled_once")
            raise asyncio.CancelledError()
        return await original_scan(self, *args, **kwargs)

    async def discover(snapshot, **kwargs):
        refs = [row["ref"] for row in snapshot.get("what_changed", [])
                if str(row.get("ref") or "").startswith("mem_")]
        require(len(refs) == 1, "DISCOVERY_LOST_CANONICAL_SOURCE")
        return {"opportunities": [{
            "identity_key": "v162:fictional-archive-cost-review",
            "what": "Il rinnovo dell'archivio è prossimo e la nota permette un confronto di dodici mesi.",
            "why_it_matters": "Preparare un confronto interno utile dei costi e dei limiti.",
            "why_now": "Il rinnovo è prossimo nello scenario sintetico.",
            "initiative": "prepare", "evidence_refs": refs,
            "what_i_can_do": "Leggere la nota e preparare un confronto, senza modificare il contratto.",
        }]}

    async def visible(goal, **kwargs):
        if goal.get("status") != "completed":
            return {"outcome": "silent", "reasoning": "Il risultato non è ancora pronto."}
        return {"outcome": "inform_user", "headline": "Il confronto dei costi per dodici mesi è pronto in ORA.",
                "reasoning": "La nota è stata letta e il confronto è disponibile.", "about": "confronto dodici mesi"}

    async def in_app(*args, **kwargs):
        return {"mode": "in_app", "timing": "now", "requires_recheck": False,
                "reason_to_open": "Il confronto verificato è consultabile.",
                "what_decided_the_mode": "Nessuna urgenza o invio necessario."}

    with ExitStack() as stack:
        # mongomock re-finds an updated document by its old filter when _id
        # was projected out; a real atomic Mongo claim does not. Keep _id for
        # that internal mock lookup, then restore the requested projection.
        # This adapter never affects Motor or the separate real-Mongo gate.
        from mongomock.collection import Collection
        mock_update = Collection.find_one_and_update

        def project_after_mock_claim(self, *args, **kwargs):
            projection = kwargs.get("projection")
            hide_id = isinstance(projection, dict) and projection.get("_id") == 0
            if hide_id:
                projection = {key: value for key, value in projection.items() if key != "_id"}
                kwargs["projection"] = projection or None
            result = mock_update(self, *args, **kwargs)
            if result is not None and hide_id:
                result.pop("_id", None)
            return result

        stack.enter_context(patch.object(Collection, "find_one_and_update", project_after_mock_claim))
        boundary.install(stack)
        # The manager can retry or fall back inside one logical call. Bound
        # those actual HTTP requests too, before any transport can spend.
        import httpx
        checked_send = httpx.AsyncClient.send

        async def bounded_model_send(client, request, **kwargs):
            if boundary.scope.get() == "model" and mode == "live":
                if probe.model_http_requests >= MAX_MODEL_HTTP_REQUESTS:
                    boundary.blocked.append("MODEL_HTTP_BOUND_EXCEEDED")
                    raise EvaluationFailure("MODEL_HTTP_BOUND_EXCEEDED")
                probe.model_http_requests += 1
            return await checked_send(client, request, **kwargs)

        stack.enter_context(patch.object(httpx.AsyncClient, "send", bounded_model_send))
        stack.enter_context(patch.object(ProviderManager, "chat", observed_chat))
        stack.enter_context(patch.object(CapabilityResolver, "available", available))
        stack.enter_context(patch.object(StepExecutor, "run", step))
        stack.enter_context(patch.object(AgentService, "advance", bounded_first_read))
        stack.enter_context(patch.object(DeliveryService, "note_activity", note))
        stack.enter_context(patch.object(provider, "get_provider", lambda: BlockedPush(probe)))
        stack.enter_context(patch.object(reasoning, "make_plan", plan))
        stack.enter_context(patch.object(OpportunityService, "scan", scan))
        if mode == "scripted":
            if scenario == "memory_corrected":
                stack.enter_context(patch.object(baseline, "DRAFT", baseline.DRAFT.replace(
                    "120 euro", "150 euro").replace("60 euro", "30 euro")))
            stack.enter_context(patch.object(reasoning, "decide_goal", decide_goal))
            stack.enter_context(patch.object(reasoning, "choose_next_action", baseline.scripted_choose))
            stack.enter_context(patch.object(reasoning, "verify_goal", baseline.scripted_verify))
            stack.enter_context(patch.object(reasoning, "_ask_model", baseline.scripted_draft))
            stack.enter_context(patch.object(reasoning, "decide_visibility", visible))
            stack.enter_context(patch.object(delivery_reasoning, "decide_delivery", in_app))
            stack.enter_context(patch.object(opportunity_reasoning, "scan", discover))
        yield probe


async def seed_case(db, scenario):
    """Called only with a newly-created evaluator database, never app Mongo."""
    from agent.service import AgentService
    from ambient.repository import AmbientRepository
    from conversation_engine.ai_core.models import MemoryCandidate
    from life_memory.governance import MemoryGovernanceService
    from opportunities.models import EvidenceRef, Opportunity
    from opportunities.repository import OpportunityRepository

    require(scenario in SCENARIOS, "UNKNOWN_SCENARIO")
    require(await db.users.count_documents({}) == 0, "EVALUATOR_DATABASE_NOT_EMPTY")
    await db.eval_guards.insert_one({"_id": VERSION, "owner": OWNER})
    await db.users.insert_one({"id": OWNER, "user_id": OWNER, "name": "Utente sintetico",
                               "settings": {"timezone": "Europe/Rome", "notifications_enabled": False}})
    await OpportunityRepository(db).ensure_indexes()
    await AgentService(db).ensure_indexes()
    await AmbientRepository(db).ensure_indexes()
    governance = MemoryGovernanceService(db)
    await governance.ensure_indexes()
    memory = await governance.apply(
        user_id=OWNER, session_id="synthetic-autonomy-evaluation",
        reasoning_epoch=VERSION, candidate_index=0,
        candidate=MemoryCandidate(
            summary=baseline.FACT, kind="service_contract_note",
            identity_key="v162:fictional-archive-note", confidence=0.95,
            authority="user_stated", epistemic_status="confirmed",
            provenance=["user_conversation"], permanence="indefinite",
            reason_for_future_utility="Confrontare le condizioni interne prima del rinnovo.",
            user_authorized=True,
        ),
    )
    require(memory.persisted and memory.memory_id, "CANONICAL_MEMORY_NOT_PERSISTED")
    if scenario == "source_change_crash":
        from opportunities.discovery import OpportunityDiscovery
        discovery = OpportunityDiscovery(db)
        await discovery.ensure_indexes()
        changed = await discovery.note(
            OWNER, source="conversation", kind="constraint.changed",
            entity_ref=memory.memory_id, after=baseline.FACT, wake=False,
        )
        require(changed.get("outcome") == "accepted", "SOURCE_CHANGE_NOT_RECORDED")
        return ""
    opportunity = Opportunity(
        owner_id=OWNER, identity_key="v162:fictional-archive-cost-review", status="active",
        semantic_summary=("Una nota interna descrive due costi per un archivio digitale con rinnovo "
                          "prossimo. Serve un confronto informativo di dodici mesi, senza cambiare contratto."),
        why_it_matters="Evitare una possibile spesa maggiore e rendere visibili i limiti.",
        why_now="Il rinnovo è prossimo nello scenario sintetico.",
        what_ora_can_do=("Leggere la nota salvata e preparare un confronto dei costi per dodici mesi "
                         "con i vincoli e i dati ancora da verificare. Nessun pagamento, invio o modifica."),
        initiative="prepare", evidence=[EvidenceRef(kind="memory", ref=memory.memory_id,
            summary="Nota interna sui costi e vincoli delle due opzioni di archivio.")],
    )
    if scenario == "irrelevant":
        opportunity.semantic_summary = "Newsletter pubblicitaria generica per un accessorio non richiesto."
        opportunity.why_it_matters = "Nessun bisogno, interesse, obbligo o scadenza documentato."
        opportunity.why_now = "Nessuna urgenza."
        opportunity.what_ora_can_do = "Nessun lavoro utile richiesto o necessario."
        opportunity.initiative = "inform"
        opportunity.evidence = []
    await OpportunityRepository(db).save(opportunity)
    return opportunity.id


async def discover_after_crash(db, probe):
    """Source claims survive a cancelled scan before normal goal admission."""
    from opportunities.discovery import OpportunityDiscovery
    try:
        await OpportunityDiscovery(db).review(OWNER)
    except asyncio.CancelledError:
        pass
    else:
        raise EvaluationFailure("SOURCE_SCAN_FAULT_NOT_EXERCISED")
    require("source_scan_cancelled_once" in probe.faults, "SOURCE_SCAN_FAULT_NOT_EXERCISED")
    require(await db.meaningful_changes.count_documents({"owner_id": OWNER, "status": "pending"}) == 1,
            "CANCELLED_SCAN_LOST_SOURCE_CHANGE")
    require(await db.opportunities.count_documents({"owner_id": OWNER}) == 0,
            "INTERRUPTED_SCAN_INVENTED_OPPORTUNITY")
    resumed = await OpportunityDiscovery(db).review(OWNER)
    require(resumed.ran and not resumed.unavailable and resumed.scan
            and len(resumed.scan.created) == 1, "SOURCE_DISCOVERY_DID_NOT_RECOVER")
    require(await db.meaningful_changes.count_documents({"owner_id": OWNER, "status": "consumed"}) == 1,
            "RECOVERED_SCAN_NOT_ACKNOWLEDGED")
    return resumed.scan.created[0].id


async def admit(db, scenario):
    from agent.admission import drain
    require(await drain(db, owner_id=OWNER, limit=1) == 1, "ADMISSION_NOT_PROCESSED")
    goals = await db.agent_goals.find({"owner_id": OWNER}, {"_id": 0}).to_list(3)
    if scenario == "irrelevant":
        require(not goals, "IRRELEVANT_GOAL_CREATED")
        require(await db.ambient_wakes.count_documents({"owner_id": OWNER}) == 0, "IRRELEVANT_WAKE_CREATED")
        source = await db.opportunities.find_one({"owner_id": OWNER})
        require(source.get("agent_review_outcome") == "no_goal", "SILENCE_NOT_DECIDED")
        return None
    require(len(goals) == 1 and goals[0]["status"] == "active", "ONE_ACTIVE_GOAL_REQUIRED")
    goal_id = goals[0]["id"]
    require(await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "source_ref": "goal:" + goal_id, "status": "pending",
    }) == 1, "ADMITTED_GOAL_WAKE_MISSING")
    return goal_id


async def fire_due(db, goal_id, probe):
    """Expedite only marked synthetic checkpoints, then let the real worker claim."""
    from agent.background import recover_due
    from ambient.runtime import tick
    guard = await db.eval_guards.find_one({"_id": VERSION, "owner": OWNER})
    require(guard is not None, "SYNTHETIC_CLOCK_GUARD_MISSING")
    due = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    # A missing continuation is a failure, not something the test repairs.
    current = await db.agent_goals.find_one({"owner_id": OWNER, "id": goal_id})
    require(current and current.get("next_run_at"), "DURABLE_CONTINUATION_MISSING")
    await db.agent_goals.update_one({"owner_id": OWNER, "id": goal_id}, {"$set": {"next_run_at": due}})
    await recover_due(db, now=datetime.now(timezone.utc), limit=2, admit=False)
    # Recovery may create a missing wake with the scheduler's minimum lead
    # time. Expedite it too, after production recovery has proved it exists.
    await db.ambient_wakes.update_many({"owner_id": OWNER, "source_ref": "goal:" + goal_id,
                                        "status": "pending"}, {"$set": {"scheduled_for": due}})
    out = await tick(db, now=datetime.now(timezone.utc), limit=2)
    probe.ticks.append(out)
    require(out["claimed"] >= 1 and out["failed"] == 0, "PERSISTED_WAKE_NOT_HANDLED")
    return await db.agent_goals.find_one({"owner_id": OWNER, "id": goal_id}, {"_id": 0})


async def first_read(db, goal_id, probe, *, planning_outage=False):
    current = await fire_due(db, goal_id, probe)
    if planning_outage:
        require(current["status"] == "active" and current.get("next_run_at"), "PLANNING_OUTAGE_KILLED_WORK")
        require(not current.get("prepared_text"), "OUTAGE_INVENTED_RESULT")
        current = await fire_due(db, goal_id, probe)
    require(current["status"] == "active" and current.get("next_run_at"), "UNFINISHED_WORK_LOST")
    require(not current.get("prepared_text"), "RESULT_CREATED_BEFORE_RESUME")
    require(await db.agent_evidence.count_documents({"owner_id": OWNER, "goal_id": goal_id,
        "provenance.capability": "information.read"}) == 1, "OWNED_SOURCE_NOT_READ_ONCE")


def review_comparison(text, *, values=(180, 120, 60)):
    """A fixture-specific independent check, not another self-approved draft."""
    text = str(text or "")
    reasons = []
    for value in values:
        if not re.search(rf"(?<!\d){value}(?:[.,]00)?(?!\d)", text):
            reasons.append(f"MISSING_COMPARISON_VALUE_{value}")
    if not re.search(r"\b12\b|dodici", text, re.I):
        reasons.append("PERIOD_NOT_PRESERVED")
    if not re.search(r"nota|dati.{0,35}(?:intern|utente)", text, re.I):
        reasons.append("INTERNAL_SOURCE_NOT_ATTRIBUTED")
    if not re.search(r"non.{0,35}rimbors|senza.{0,20}rimborso|nessun.{0,20}rimborso", text, re.I):
        reasons.append("NONREFUNDABLE_CONSTRAINT_MISSING")
    if not re.search(r"non\s+(?:ancora\s+)?(?:verificat\w*|confermat\w*)|"
                     r"(?:da|senza)\s+(?:verific\w*|conferm\w*)|"
                     r"richied\w*.{0,20}(?:conferma|verifica)", text, re.I):
        reasons.append("SOURCE_VERIFICATION_LIMIT_MISSING")
    return {"passed": not reasons, "reasons": reasons, "status": "bounded_check",
            "human_review_still_required": True}


async def recover_home(db):
    from agent.visibility import VisibilityService
    require(await db.eval_guards.find_one({"_id": VERSION, "owner": OWNER}),
            "SYNTHETIC_CLOCK_GUARD_MISSING")
    await db.agent_updates.update_many({"owner_id": OWNER, "home_pending": True}, {"$set": {
        "home_due_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
    }})
    return await VisibilityService(db).recover_pending_home()


async def verify_result(db, goal_id, probe, *, recover=True, source_corrected=False):
    from agent.service import AgentService
    from delivery.service import DeliveryService
    goal = await AgentService(db).repo.get_goal(OWNER, goal_id)
    require(goal and goal.status == "completed", "GOAL_NOT_COMPLETED")
    plan = await AgentService(db).repo.plan_for(OWNER, goal_id)
    require(plan and plan.status == "completed", "PLAN_NOT_COMPLETED")
    require(all(step.status in ("succeeded", "skipped") for step in plan.steps), "UNFINISHED_PLAN_STEPS")
    require(goal.prepared_text and goal.prepared_sources, "GROUNDED_RESULT_MISSING")
    evidence = await AgentService(db).evidence.for_goal(OWNER, goal_id)
    require(set(goal.prepared_sources).issubset({item.id for item in evidence}), "UNOWNED_RESULT_EVIDENCE")
    require(sum(item.provenance.capability == "information.read" for item in evidence) == 1, "READ_REPEATED_AFTER_RESUME")
    total_reads = await db.agent_evidence.count_documents({"owner_id": OWNER, "goal_id": goal_id,
                                                         "provenance.capability": "information.read"})
    require(total_reads == (2 if source_corrected else 1), "UNEXPECTED_TOTAL_SOURCE_READS")
    semantic = review_comparison(goal.prepared_text, values=(180, 150, 30) if source_corrected else (180, 120, 60))
    require(semantic["passed"], "SEMANTIC_RESULT_REJECTED:" + ",".join(semantic["reasons"]))
    if recover:
        await recover_home(db)
    updates = await db.agent_updates.find({"owner_id": OWNER, "goal_id": goal_id}, {"_id": 0}).to_list(8)
    require(any(not row.get("home_pending") and row.get("home_delivered_at") for row in updates), "HOME_OUTBOX_NOT_DELIVERED")
    activities = await db.ambient_activity.find({"owner_id": OWNER, "visibility": "ambient",
        "cognitive_provenance.agent": "visibility", "cognitive_provenance.goal": goal_id}, {"_id": 0}).to_list(8)
    require(activities, "VALIDATED_HOME_ACTIVITY_MISSING")
    home = await DeliveryService(db).ambient_line(OWNER)
    require(home and any(home["id"] == row["id"] for row in activities), "RESULT_NOT_RETRIEVABLE_FROM_HOME")
    before = await snapshot_counts(db, goal_id)
    model_before = probe.model_attempts
    replay = await AgentService(db).advance(OWNER, goal_id, worker_id="ambient:v162-replay")
    require(replay.get("state") == "completed", "TERMINAL_REPLAY_CHANGED_STATE")
    await recover_home(db)
    require(await snapshot_counts(db, goal_id) == before and probe.model_attempts == model_before, "REPLAY_DUPLICATED_WORK")
    foreign = await AgentService(db).advance("another-synthetic-owner", goal_id)
    require(foreign.get("reason") == "unknown_goal", "CROSS_OWNER_ACCESS")
    return {"state": goal.status, "read_reused": not source_corrected,
            "corrected_source_reread": source_corrected, "prepared": True,
            "prepared_text": goal.prepared_text[:6000],
            "prepared_text_truncated": len(goal.prepared_text) > 6000,
            "home_delivered": True, "replay_idempotent": True, "owner_isolation": True,
            "semantic_review": semantic, "counts": before}


async def snapshot_counts(db, goal_id):
    return {name: await db[name].count_documents({"owner_id": OWNER}) for name in (
        "agent_evidence", "agent_updates", "ambient_activity", "agent_needs", "agent_action_attempts",
    )}


async def change_memory(db, goal_id, *, correction=False):
    """A real canonical change between wakes, inside the marked synthetic DB."""
    from conversation_engine.ai_core.models import MemoryCandidate
    from life_memory.governance import MemoryGovernanceService
    require(await db.eval_guards.find_one({"_id": VERSION, "owner": OWNER}),
            "SYNTHETIC_MEMORY_GUARD_MISSING")
    goal = await db.agent_goals.find_one({"owner_id": OWNER, "id": goal_id})
    refs = [ref for ref in (goal or {}).get("source_refs", []) if ref.startswith("mem_")]
    require(len(refs) == 1, "CANONICAL_SOURCE_REFERENCE_MISSING")
    operation = "correct" if correction else "forget"
    changed = await MemoryGovernanceService(db).apply(
        user_id=OWNER, session_id="synthetic-autonomy-evaluation",
        reasoning_epoch=VERSION + ":" + operation, candidate_index=0,
        candidate=MemoryCandidate(operation=operation,
            summary=baseline.FACT.replace("120 euro", "150 euro") if correction else "Dimentica la nota ritirata.",
            existing_memory_ref=refs[0], user_authorized=True,
            kind="service_contract_note", identity_key="v162:fictional-archive-note",
            authority="user_stated", epistemic_status="confirmed", confidence=0.95,
            permanence="indefinite", provenance=["user_conversation"],
            reason_for_future_utility="Confrontare le condizioni interne prima del rinnovo."),
    )
    require(changed.persisted, "MEMORY_CHANGE_NOT_PERSISTED")
    return {"old": refs[0], "current": changed.memory_id}


async def run_case(scenario, *, mode="scripted", probe=None):
    from mongomock_motor import AsyncMongoMockClient
    from opportunities.service import OpportunityService
    from agent.service import AgentService
    require(scenario in SCENARIOS, "UNKNOWN_SCENARIO")
    db = AsyncMongoMockClient()["autonomy_v162_" + scenario]
    with isolated_engine(db, mode=mode, scenario=scenario, probe=probe) as probe:
        source_id = await seed_case(db, scenario)
        if scenario == "source_change_crash":
            source_id = await discover_after_crash(db, probe)
        goal_id = await admit(db, scenario)
        result = {"state": "no_goal"}
        if goal_id:
            await first_read(db, goal_id, probe, planning_outage=scenario == "planning_outage")
            if scenario == "source_revoked":
                before_steps = len(probe.steps)
                await OpportunityService(db).dismiss(OWNER, source_id)
                current = await AgentService(db).repo.get_goal(OWNER, goal_id)
                require(current and current.status == "cancelled" and not current.next_run_at, "REVOKED_WORK_NOT_STOPPED")
                require(not current.prepared_text and len(probe.steps) == before_steps, "REVOKED_SOURCE_PRODUCED_RESULT")
                require(await db.ambient_wakes.count_documents({"owner_id": OWNER,
                    "source_ref": "goal:" + goal_id, "status": "pending"}) == 0, "REVOKED_WAKE_SURVIVED")
                before = await snapshot_counts(db, goal_id)
                from ambient.runtime import tick
                idle = await tick(db, now=datetime.now(timezone.utc), limit=2)
                replay = await AgentService(db).advance(OWNER, goal_id, worker_id="ambient:v162-cancel-replay")
                require(not idle["claimed"] and replay.get("state") == "cancelled"
                        and await snapshot_counts(db, goal_id) == before,
                        "REVOKED_SOURCE_REPLAYED_WORK")
                result = {"state": "cancelled", "stopped_on_source_revocation": True,
                          "replay_idempotent": True}
            elif scenario == "memory_revoked":
                await change_memory(db, goal_id)
                before_steps = len(probe.steps)
                current = await AgentService(db).repo.get_goal(OWNER, goal_id)
                if current.next_run_at:
                    await fire_due(db, goal_id, probe)
                current = await AgentService(db).repo.get_goal(OWNER, goal_id)
                require(current.status == "abandoned" and not current.prepared_text,
                        "WITHDRAWN_MEMORY_PRODUCED_RESULT")
                require(not any(step["capability"] == "document.create" and step["status"] == "succeeded"
                                for step in probe.steps[before_steps:]), "WITHDRAWN_EVIDENCE_REUSED")
                result = {"state": current.status, "stopped_on_memory_revocation": True}
            elif scenario == "memory_corrected":
                changed = await change_memory(db, goal_id, correction=True)
                probe.faults.append("memory_corrected_between_wakes")
                for _ in range(3):
                    current = await AgentService(db).repo.get_goal(OWNER, goal_id)
                    if current.status == "completed":
                        break
                    require(current.is_open and current.next_run_at and not current.requires_user_input,
                            "CORRECTED_SOURCE_DID_NOT_CONTINUE")
                    await fire_due(db, goal_id, probe)
                evidence = await AgentService(db).evidence.for_goal(OWNER, goal_id)
                reads = [row for row in evidence if row.provenance.capability == "information.read"]
                require(reads and all(changed["current"] in row.provenance.source_refs
                                     and changed["old"] not in row.provenance.source_refs for row in reads),
                        "SUPERSEDED_MEMORY_USED_AS_CURRENT")
                result = await verify_result(db, goal_id, probe, source_corrected=True)
            else:
                await fire_due(db, goal_id, probe)
                if scenario == "home_write_retry":
                    require(await db.agent_updates.count_documents({"owner_id": OWNER, "home_pending": True}) == 1,
                            "FAILED_HOME_HANDOFF_NOT_DURABLE")
                result = await verify_result(db, goal_id, probe)
        require(await db.agent_action_attempts.count_documents({}) == 0, "WORLD_ACTION_ATTEMPT_CREATED")
        require(await db.action_intents.count_documents({}) == 0, "WORLD_ACTION_INTENT_CREATED")
        require(not probe.blocked_effects and not probe.push_attempts and not probe.network.blocked, "ISOLATION_BOUNDARY_ATTEMPTED")
        require(mode != "live" or bool(probe.model_calls), "LIVE_MODEL_NOT_OBSERVED")
        require(mode != "scripted" or not probe.model_attempts, "OFFLINE_MODEL_CALL")
        return {"version": VERSION, "scenario": scenario, "mode": mode, "passed": True,
                "scope": "synthetic_internal_note_to_home_no_external_effects",
                "model_mode": "real_llm" if mode == "live" else "scripted",
                "source_mode": "synthetic_owned_record_real_reader", "live_provider_reads": 0,
                "storage": "in_memory", "process_restart_tested": False,
                "synthetic_checkpoints_expedited": True,
                **model_observations(probe),
                "worker_ticks": probe.ticks, "executed_capabilities": probe.steps,
                "source_change_discovery_tested": scenario == "source_change_crash",
                "injected_faults": probe.faults, "external_effects": 0, "result": result}


async def main(*, mode="scripted", scenario="all", output=""):
    started_at = datetime.now(timezone.utc).isoformat()
    selected = SCENARIOS if scenario == "all" else (scenario,)
    if mode == "live" and not any(os.environ.get(key) for key in LLM_KEYS):
        report = {"version": VERSION, "mode": mode, "status": "blocked", "passed": False,
                  "reason": "LIVE_MODEL_CREDENTIALS_UNAVAILABLE", "real_model_executed": False, "cases": []}
        code = 3
    else:
        cases = []
        for name in selected:
            probe = Probe()
            try:
                case = await asyncio.wait_for(run_case(name, mode=mode, probe=probe),
                                              timeout=CASE_TIMEOUT_SECONDS)
            except Exception as exc:
                case = {"scenario": name, "mode": mode, "passed": False,
                        **model_observations(probe),
                        "reason": str(exc) if isinstance(exc, EvaluationFailure) else type(exc).__name__}
            cases.append(case)
        passed = all(case["passed"] for case in cases)
        report = {"version": VERSION, "mode": mode, "status": "passed" if passed else "failed",
                  "passed": passed, "real_model_executed": mode == "live" and all(
                      case.get("real_model_executed") for case in cases), "cases": cases}
        code = 0 if passed else 1
    revision = os.environ.get("RAILWAY_GIT_COMMIT_SHA") or os.environ.get("GITHUB_SHA") or ""
    report.update({"started_at": started_at, "finished_at": datetime.now(timezone.utc).isoformat(),
                   "limits": {"cases": len(selected), "case_timeout_seconds": CASE_TIMEOUT_SECONDS,
                              "model_calls_per_case": MAX_MODEL_CALLS,
                              "model_http_requests_per_case": MAX_MODEL_HTTP_REQUESTS,
                              "model_calls_total": len(selected) * MAX_MODEL_CALLS,
                              "model_http_requests_total": len(selected) * MAX_MODEL_HTTP_REQUESTS},
                   "code_revision": revision if re.fullmatch(r"[0-9a-fA-F]{40}", revision) else None,
                   "revision_source": "deployment_or_ci_metadata" if re.fullmatch(r"[0-9a-fA-F]{40}", revision) else None})
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("ORA_AUTONOMY_COMPLETION_SUMMARY " + json.dumps(report, ensure_ascii=False), flush=True)
    return code


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("scripted", "live"), default="scripted")
    parser.add_argument("--scenario", choices=("all", *SCENARIOS), default="all")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(mode=args.mode, scenario=args.scenario, output=args.output)))
