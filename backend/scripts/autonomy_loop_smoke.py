"""Opt-in real-model loop on an in-memory synthetic account.

Requires test-only mongomock-motor. NEVER connects to Mongo. All discovery and
agent judgments are real; notification hooks are disabled and execution is
restricted to document.read/document.create. No real-world effect can run.
This validates an isolated loop, not real-account delivery or market research.
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from contextlib import ExitStack


def report(stage, **fields):
    print("AUTONOMY_LOOP_SMOKE " + json.dumps({"stage": stage, **fields}, ensure_ascii=False, default=str), flush=True)


def isolated_call_allowed(step, how):
    return ((how == "read" and step.capability_needed == "document.read")
            or (how in ("prepare", "compare") and step.capability_needed in ("", "document.create")))


async def run(scenario=None):
    import mongomock.collection
    from mongomock_motor import AsyncMongoMockClient
    from agent.capabilities import CapabilityResolver
    from agent.service import AgentService
    from agent.execution import StepExecutor
    from agent.models import ExecutionResult
    from agent.background import recover_due
    from ambient.runtime import tick
    from opportunities import snapshot
    from opportunities.discovery import OpportunityDiscovery

    db = AsyncMongoMockClient().isolated_synthetic_account
    owner = "synthetic-persona-no-real-account"
    text = (
        "Il piano attivo di archivio digitale passerà da 10 a 25 euro al mese al prossimo rinnovo. "
        "Il titolare mantiene il servizio per almeno dodici mesi. L'alternativa annuale è pubblicizzata "
        "a 120 euro, ma le condizioni economiche complete sono nella seconda parte del documento. "
        "Non è stata autorizzata alcuna modifica al piano.\n"
        + "Dettagli tecnici: archivio digitale con spazio e assistenza.\n" * 22
        + "\nCondizioni economiche complete: il piano mensile costa 25 euro ogni mese, imposte incluse. "
        "Il piano annuale costa 120 euro per i primi dodici mesi più 30 euro di attivazione una tantum. "
        "Dal secondo anno l'annuale costa 240 euro. Entrambi comprendono 100 GB e la stessa assistenza. "
        "L'annuale si paga anticipatamente e i mesi inutilizzati non sono rimborsati. "
        "Il mensile è cancellabile ogni mese. Non ci sono altri costi."
    )
    if scenario is not None:
        text = scenario["text"]
    await db.documents.insert_one({"id": "price-options", "user_id": owner,
        "original_filename": scenario["title"] if scenario else "Condizioni archivio digitale.txt", "extracted_text": text})
    await db.agent_runs.create_index("goal_id", unique=True)
    original_update = mongomock.collection.Collection.find_one_and_update
    original_call = StepExecutor._call
    original_resolve = CapabilityResolver.resolve
    allowed = {"document.read", "document.create"}

    def update(self, *args, **kwargs):
        kwargs.pop("projection", None)  # mongomock projection quirk, not production behavior
        return original_update(self, *args, **kwargs)

    async def resolve(self, owner_id, capability):
        if capability not in allowed:
            return await original_resolve(self, owner_id, "unknown_isolated_capability")
        return await original_resolve(self, owner_id, capability)

    async def available(self, owner_id):
        return [{"capability": name, "status": "available_real", "can_be_used_now": True,
                 "changes_something_in_the_world": False} for name in sorted(allowed)]

    async def guarded_call(self, owner_id, goal, step, how, **kwargs):
        if not isolated_call_allowed(step, how):
            from agent.providers import CapabilityOutcome
            return CapabilityOutcome(status="unavailable", error_type="isolated_capability_boundary",
                observation="Questa capacità non è disponibile nell'ambiente isolato.")
        return await original_call(self, owner_id, goal, step, how, **kwargs)

    async def deny_effect(self, owner_id, goal, step, *args, **kwargs):
        return ExecutionResult(step_id=step.id, status="unavailable", error_type="isolated_no_external_effects")

    with ExitStack() as stack:
        stack.enter_context(patch.object(mongomock.collection.Collection, "find_one_and_update", update))
        stack.enter_context(patch.object(CapabilityResolver, "resolve", resolve))
        stack.enter_context(patch.object(CapabilityResolver, "available", available))
        stack.enter_context(patch.object(StepExecutor, "_call", guarded_call))
        stack.enter_context(patch.object(StepExecutor, "_touch_the_world", deny_effect))
        for name in ("_note_ambient", "_consider_visibility", "_observe_life_change"):
            stack.enter_context(patch.object(AgentService, name, AsyncMock()))
        for name in ("_open_questions", "_recently_settled", "_places", "_presence", "_routines",
                     "_comparisons", "_calendar", "_situations", "_disagreements", "_money", "_existing_work"):
            stack.enter_context(patch.object(snapshot, name, AsyncMock(return_value=[])))
        discovery = OpportunityDiscovery(db)
        await discovery.note(owner, source="documents", kind="document.added", entity_ref="price-options", wake=False)
        reviewed = await discovery.review(owner)
        report("discovery", ran=reviewed.ran, created=len(reviewed.scan.created) if reviewed.scan else 0,
               reason=reviewed.scan.reason_for_silence if reviewed.scan else None,
               skipped=reviewed.scan.skipped if reviewed.scan else [])
        for _ in range(3):
            await recover_due(db)
            await recover_due(db)
            ticked = await tick(db, now=datetime.now(timezone.utc)+timedelta(minutes=1))
            report("tick", result=str(ticked))
            goal = await db.agent_goals.find_one({"owner_id": owner})
            if goal and (goal["status"] not in ("active", "waiting") or goal.get("requires_user_input")):
                break
            if goal and goal["status"] == "active" and goal.get("next_run_at"):
                # Fast-forward only the technical continuation delay in this
                # in-memory fixture; do not bypass a human/model waiting state.
                await db.agent_goals.update_one({"id": goal["id"]},
                    {"$set": {"next_run_at": datetime.now(timezone.utc).isoformat()}})
                # Continuations already have a durable wake: advance its clock
                # too. recover_due correctly refuses to enqueue a duplicate.
                await db.ambient_wakes.update_many(
                    {"owner_id": owner, "source_ref": f"goal:{goal['id']}", "status": "pending"},
                    {"$set": {"scheduled_for": datetime.now(timezone.utc).isoformat()}})
        goal = await db.agent_goals.find_one({"owner_id": owner}) or {}
        report("diagnostics", wakes=await db.ambient_wakes.find({}, {"_id": 0, "status": 1, "last_error": 1}).to_list(10), opportunities=await db.opportunities.find({}, {"_id": 0}).to_list(4), plans=await db.agent_plans.find({}, {"_id": 0}).to_list(10),
               journal=await db.agent_journal.find({}, {"_id": 0, "kind": 1, "note": 1, "detail": 1}).to_list(40))
        draft = str(goal.get("prepared_text") or "")
        report("result", status=goal.get("status"), needs_user=bool(goal.get("requires_user_input")),
               draft=draft, explanation=goal.get("rationale"),
               evidence_count=await db.agent_evidence.count_documents({"owner_id": owner}))
        # Fixture oracle: first year 300 - (120 + 30) = 150, with nonrefundability.
        passed = (goal.get("status") == "completed" and "150" in draft
                  and "rimbor" in draft.lower() and bool(goal.get("prepared_sources"))
                  and await db.agent_receipts.count_documents({}) == 0)
        if scenario is not None:
            if scenario.get("expect_silence"):
                passed = not goal and bool(reviewed.scan and reviewed.scan.silence)
            else:
                passed = (goal.get("status") == "completed" and bool(goal.get("prepared_sources"))
                          and not goal.get("requires_user_input")
                          and all(term.casefold() in draft.casefold() for term in scenario["terms"]))
            passed = passed and await db.agent_receipts.count_documents({}) == 0
        report("gate", passed=passed, scope="real_model_in_memory_loop_no_delivery_no_external_actions")
        if scenario is not None:
            return passed
        # Separate, explicitly seeded stage test. Never counts as loop success.
        from agent.models import AutonomousGoal, ActionStep, AgentEvidence, ResultProvenance
        from agent.preparation import prepare
        check_goal = AutonomousGoal(owner_id=owner, objective="Confronto dei costi e dei limiti",
            desired_outcome="Totali primo anno e rinnovo, differenze e limiti dalle fonti", status="active")
        await db.agent_goals.insert_one(check_goal.model_dump())
        for claim in ["Il mensile passa da 10 a 25 euro al mese. La persona intende usarlo per dodici mesi; il piano è cancellabile ogni mese.",
                      "L'annuale comprende gli stessi 100 GB e assistenza: 120 euro nel primo anno più 30 euro di attivazione una tantum; rinnovo 240 euro annui.",
                      "L'annuale si paga anticipatamente, senza rimborso dei mesi inutilizzati. Imposte incluse, nessun altro costo."]:
            ev = AgentEvidence(owner_id=owner, goal_id=check_goal.id, claim=claim,
                provenance=ResultProvenance(source_class="internal_observation", provider="documents", source_refs=["document:price-options"]))
            await db.agent_evidence.insert_one(ev.model_dump())
        prepared = await prepare(db, owner, check_goal, ActionStep(step_type="prepare", intent="Prepara il confronto utile con costi e limiti"))
        report("preparation_stage_only", status=prepared.status, draft=check_goal.prepared_text,
               error=prepared.error_type, scope="seeded_evidence_real_model_not_end_to_end")


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    try:
        asyncio.run(asyncio.wait_for(run(), timeout=240))
    except Exception as exc:
        report("gate", passed=False, error_type=type(exc).__name__)
