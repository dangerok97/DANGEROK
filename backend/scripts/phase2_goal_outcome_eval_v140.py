"""Phase 2 v140: bounded end-to-end autonomous outcome, never a real user action.

This is an explicitly invoked evaluator. The life, account, memory and database
are synthetic. The actual admission, agent execution, evidence, draft,
verification and persistence code run. In live mode the configured LLM really
makes the decisions. No real accounts, third-party writes or notifications.
A separate CI gate proves the restart with two OS processes and real Mongo.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

VERSION = "phase2-autonomous-outcome-v140"
OWNER = "ora-synthetic-outcome-owner-v140"
FACT = (
    "Nota salvata in ORA, dati riferiti dall'utente e non confermati dal fornitore: "
    "il piano dell'archivio digitale costa 15 euro mensili; 12 mesi costano 180 euro. "
    "La seconda opzione indicata nella nota costa 120 euro anticipati per 12 mesi. "
    "In entrambe le opzioni 100 GB, assistenza uguale e spese iniziali nulle. "
    "L'annuale non prevede rimborso in caso di disdetta anticipata. "
    "Nessun cambio di contratto o pagamento autorizzato."
)
DRAFT = (
    "Secondo la nota interna non verificata presso il fornitore, il mensile "
    "costa 15 x 12 = 180 euro per dodici mesi; l'annuale costa 120 euro "
    "anticipati, con una differenza di 60 euro a favore dell'annuale se "
    "si mantiene il servizio per 12 mesi. Capacita' e assistenza risultano "
    "uguali nella nota; l'annuale non rimborsa i mesi non usati. "
    "Prima di qualsiasi scelta sono da verificare le condizioni correnti. "
    "Non ho modificato il piano né disposto pagamenti."
)
EXPECTED = {"read": "information.read", "draft": "document.create"}


def scripted_goal():
    return {
        "outcome": "create_goal",
        "objective": "Controllare la nota interna e preparare un confronto informativo",
        "desired_outcome": "Confronto scritto di 12 mesi con calcolo differenza, limiti e nessun cambio piano",
        "why_now": "Il rinnovo è prossimo nella situazione sintetica",
        "reasoning": "Una differenza potrebbe incidere sulla scelta, senza autorizzare azioni",
        "success_criteria": ["Confronto basato sulla nota e condizioni ancora da verificare"],
        "stop_conditions": ["La nota viene corretta o ritirata"],
    }


def scripted_plan():
    return {
        "plan_summary": "Leggere la nota già registrata, poi scrivere il confronto",
        "expected_outcome": "Bozza informativa con limiti e nessuna azione sul contratto",
        "steps": [
            {
                "step_type": "inspect",
                "intent": "Leggere il promemoria interno e le sue condizioni",
                "capability_needed": EXPECTED["read"],
                "expected_result": "Condizioni della nota recuperate con provenienza",
            },
            {
                "step_type": "prepare",
                "intent": "Preparare un confronto fondato sulle condizioni della nota",
                "capability_needed": EXPECTED["draft"],
                "expected_result": "180 euro contro 120 euro, 60 euro di differenza e limiti",
            },
        ],
    }


async def seed(db):
    """Populate only a caller-supplied isolated database."""
    from opportunities.models import Opportunity
    from opportunities.repository import OpportunityRepository
    from agent.service import AgentService
    from ambient.repository import AmbientRepository

    await OpportunityRepository(db).ensure_indexes()
    await AgentService(db).ensure_indexes()
    await AmbientRepository(db).ensure_indexes()
    await db.memories.insert_one({
        "id": "mem_synthetic_v140", "user_id": OWNER,
        "status": "active", "kind": "service_contract_note",
        "summary": FACT, "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return await OpportunityRepository(db).save(Opportunity(
        owner_id=OWNER,
        identity_key="v140:fictional-archive-cost-review",
        status="active",
        semantic_summary=(
            "Una nota interna di ORA descrive due costi per un servizio "
            "di archivio digitale con rinnovo prossimo. Conviene esaminare "
            "i dati registrati e preparare un confronto informativo "
            "di dodici mesi, senza cambiare contratto."
        ),
        why_it_matters="Evitare una possibile spesa maggiore e rendere visibili i limiti",
        why_now="L'utente sintetico potrebbe dover scegliere al rinnovo",
        what_ora_can_do=(
            "Leggere il proprio promemoria, confrontare costi e vincoli "
            "per dodici mesi e preparare un report fondato sulla nota; "
            "nessun pagamento, invio o modifica."
        ),
        initiative="prepare",
    ))


async def scripted_decide_goal(*args, **kwargs):
    return scripted_goal()


async def scripted_make_plan(*args, **kwargs):
    return scripted_plan()


async def scripted_choose(*args, **kwargs):
    candidates = kwargs.get("candidates") or []
    return {
        "decision": "execute" if candidates else "complete",
        "step_id": candidates[0].get("id", "") if candidates else "",
        "reasoning": "Il prossimo passo ha ancora senso secondo le fonti.",
    }


async def scripted_verify(*args, **kwargs):
    evidence = kwargs.get("evidence") or {}
    return {
        "outcome": "achieved" if evidence.get("prepared_result") else "uncertain",
        "reasoning": "La bozza di confronto esiste e cita i dati interni effettivamente letti.",
        "what_is_missing": "Manca la bozza" if not evidence.get("prepared_result") else "",
    }


async def scripted_draft(system, user):
    try:
        payload = json.loads(user)
        ids = [
            str(row.get("id"))
            for row in payload.get("evidence", [])
            if isinstance(row, dict) and row.get("id")
        ]
    except (TypeError, ValueError):
        return None
    if not ids:
        return None
    if "Audit this draft" in system:
        return {"verified": True, "content": DRAFT, "evidence_ids": ids[:2]}
    if "Produce the actual useful draft" in system:
        return {"content": DRAFT, "evidence_ids": ids[:2]}
    return None


@contextmanager
def isolated_engine(mode: str):
    """Keep all effects inside synthetic Mongo, regardless of model output."""
    from agent import reasoning
    from agent.capabilities import CapabilityResolver
    from agent.execution import StepExecutor
    from agent.service import AgentService

    allowed = frozenset(EXPECTED.values())
    original_run = StepExecutor.run

    async def guarded_run(self, owner_id, goal, step, **kwargs):
        if owner_id != OWNER or step.capability_needed not in allowed or step.step_type == "execute":
            raise RuntimeError("isolated_evaluator_blocked_effect_or_unknown_capability")
        return await original_run(self, owner_id, goal, step, **kwargs)

    async def only_available(self, owner_id):
        if owner_id != OWNER:
            raise RuntimeError("synthetic_account_only")
        return [
            {
                "capability": cap, "status": "available_real",
                "can_be_used_now": True, "really_does_something": True,
                "changes_something_in_the_world": False, "why_not": None,
            } for cap in sorted(allowed)
        ]

    with ExitStack() as stack:
        stack.enter_context(patch.object(StepExecutor, "run", guarded_run))
        stack.enter_context(patch.object(CapabilityResolver, "available", only_available))
        stack.enter_context(patch.object(AgentService, "_note_ambient", AsyncMock(return_value=None)))
        # Delivery to devices and user communication is outside this evaluator.
        stack.enter_context(patch.object(AgentService, "_consider_visibility", AsyncMock(return_value=None)))
        if mode == "scripted":
            stack.enter_context(patch.object(reasoning, "decide_goal", scripted_decide_goal))
            stack.enter_context(patch.object(reasoning, "make_plan", scripted_make_plan))
            stack.enter_context(patch.object(reasoning, "choose_next_action", scripted_choose))
            stack.enter_context(patch.object(reasoning, "verify_goal", scripted_verify))
            stack.enter_context(patch.object(reasoning, "_ask_model", scripted_draft))
        yield


async def admission(db) -> str:
    from agent.admission import drain

    processed = await drain(db, owner_id=OWNER, limit=1)
    if processed != 1:
        raise AssertionError("admission_not_processed")
    rows = await db.agent_goals.find({"owner_id": OWNER}, {"_id": 0}).to_list(3)
    if len(rows) != 1 or rows[0].get("status") != "active":
        raise AssertionError("one_active_goal_not_created")
    return str(rows[0]["id"])


async def first_read(db, goal_id: str) -> dict:
    from agent.service import AgentService
    from agent.models import AgentBudget

    # Exactly one actual read is allowed in this run. A technical ceiling
    # must persist the remaining plan instead of falsely completing the goal.
    result = await AgentService(db).advance(
        OWNER, goal_id, worker_id="ambient:v140-first",
        budget=AgentBudget(max_steps=1),
    )
    goal = await db.agent_goals.find_one({"owner_id": OWNER, "id": goal_id})
    plan = await db.agent_plans.find_one({"owner_id": OWNER, "goal_id": goal_id})
    evidence = await db.agent_evidence.find({
        "owner_id": OWNER, "goal_id": goal_id,
        "provenance.capability": EXPECTED["read"],
    }).to_list(10)
    if result.get("state") != "in_progress" or goal.get("status") != "active":
        raise AssertionError("unfinished_run_falsely_completed")
    if not plan or len(evidence) != 1 or not evidence[0]["claim"].startswith("Nota salvata"):
        raise AssertionError("real_owned_source_not_read")
    if not any(s.get("status") == "succeeded" and s.get("capability_needed") == EXPECTED["read"]
               for s in plan["steps"]):
        raise AssertionError("read_not_persisted")
    if goal.get("prepared_text"):
        raise AssertionError("prepared_too_early")
    if not goal.get("next_run_at"):
        raise AssertionError("continuation_not_durable")
    return {"first_state": result["state"], "read_evidence": len(evidence)}


async def finish_after_reopen(db, goal_id: str) -> dict:
    from agent.service import AgentService
    from agent.evidence import EvidenceStore

    # A brand-new service object has no in-memory plan: Mongo alone owns the
    # previous step, even after process exit in the separate CI integration.
    service = AgentService(db)
    before = await service.evidence.for_goal(OWNER, goal_id)
    result = await service.advance(OWNER, goal_id, worker_id="ambient:v140-resumed")
    saved = await service.repo.get_goal(OWNER, goal_id)
    plan = await service.repo.plan_for(OWNER, goal_id)
    evidence = await service.evidence.for_goal(OWNER, goal_id)
    if result.get("state") != "completed" or saved.status != "completed":
        raise AssertionError("goal_not_completed_after_resume:" + str(result.get("state")))
    if not plan or plan.status != "completed" or len(before) < 1:
        raise AssertionError("persisted_plan_or_source_lost")
    if not saved.prepared_text or not saved.prepared_sources:
        raise AssertionError("grounded_result_missing")
    if not all(step.status in ("succeeded", "skipped") for step in plan.steps):
        raise AssertionError("plan_contains_unfinished_step")
    if sum(e.provenance.capability == EXPECTED["read"] for e in evidence) != 1:
        raise AssertionError("initial_read_repeated_after_resume")
    prepared_ids = {e.id for e in evidence}
    if any(ref not in prepared_ids for ref in saved.prepared_sources):
        raise AssertionError("draft_has_unowned_evidence_ids")
    if await db.agent_action_attempts.count_documents({"owner_id": OWNER}):
        raise AssertionError("world_effect_created")
    if await db.agent_needs.count_documents({"owner_id": OWNER}):
        raise AssertionError("person_was_asked_in_isolated_read_only_case")
    return {
        "result": result["state"], "steps": len(plan.steps),
        "evidence": len(evidence), "prepared": True,
        "real_read_reused": True, "effects": 0,
    }


async def run(mode: str) -> dict:
    from mongomock_motor import AsyncMongoMockClient

    db = AsyncMongoMockClient().phase2_outcome_v140
    with isolated_engine(mode):
        await seed(db)
        goal_id = await admission(db)
        stage1 = await first_read(db, goal_id)
        stage2 = await finish_after_reopen(db, goal_id)
        # No new model call or duplicate work for a settled goal.
        from agent.service import AgentService
        replay = await AgentService(db).advance(OWNER, goal_id, worker_id="ambient:v140-replay")
        if replay.get("state") != "completed":
            raise AssertionError("settled_replay_not_idempotent")
        foreign = await AgentService(db).advance("synthetic-other-owner", goal_id)
        if foreign.get("reason") != "unknown_goal":
            raise AssertionError("cross_account_goal_read")
        return {
            "version": VERSION, "mode": mode,
            "scope": "synthetic_memory_in_memory_mongo_no_external_effect",
            "passed": True, "first": stage1, "resumed": stage2,
            "replay": replay["state"], "owner_isolation": True,
        }


async def main(mode: str) -> int:
    if mode == "live" and not any(os.environ.get(k) for k in (
        "OPENAI_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY",
    )):
        print("ORA_PHASE2_OUTCOME_BLOCKED " + json.dumps({"reason": "llm_credentials_missing"}), flush=True)
        return 3
    try:
        result = await asyncio.wait_for(run(mode), timeout=175)
    except Exception as exc:
        result = {
            "version": VERSION, "mode": mode, "passed": False,
            "reason": type(exc).__name__,
            # No source text, prompts, identities or credentials in logs.
            "scope": "synthetic_isolated",
        }
    print("ORA_PHASE2_OUTCOME_SUMMARY " + json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("scripted", "live"), default="scripted")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.mode)))
