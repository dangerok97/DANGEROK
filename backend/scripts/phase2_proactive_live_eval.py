"""ORA: evidence-gated proactive AI evaluation against an isolated synthetic life.

The production autonomous admission, judgement, goal repository and wake
scheduler run unmodified. Only sample life facts are fictional and stored in
an in-memory MongoDB. Scripted mode is CI-safe; opt-in live mode calls ONE
configured LLM manager but never any connected personal service or real-world
action capability.

Examples:
  python -m scripts.phase2_proactive_live_eval --mode scripted --scenario all
  python -m scripts.phase2_proactive_live_eval --mode live --scenario all

A PASS is bounded acceptance of the initial proactive judgement, not proof
of an end-to-end action, external provider result or mobile notification.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional
from unittest.mock import AsyncMock, patch

VERSION = "phase2-proactive-real-model-v137"
OWNER_PREFIX = "ora-synthetic-proactive-eval"
LOG = logging.getLogger("ora.phase2_proactive_eval")

SCENARIOS = {
    "actionable_conflict": {
        "expect": "create_goal",
        "summary": (
            "Un appuntamento confermato in calendario è alle 15:00, "
            "ma una nuova comunicazione del professionista lo sposta alle 16:30."
        ),
        "why": (
            "L'utente rischia di presentarsi a un orario errato. "
            "Non è stata verificata l'autenticità della comunicazione."
        ),
        "now": "La comunicazione è arrivata ora. L'appuntamento è domani.",
        "initiative": "prepare",
        "goal": (
            "Verificare quale orario è confermato e preparare una proposta "
            "di aggiornamento del calendario, senza modificare nulla "
            "o contattare terzi prima di una specifica autorizzazione."
        ),
    },
    "unrelated_promotion": {
        "expect": "no_goal",
        "summary": (
            "È arrivata una newsletter pubblicitaria generica: "
            "sconto su un accessorio che non è stato richiesto "
            "e non è collegato a nessuna necessità nota."
        ),
        "why": (
            "Nessuna scadenza o interesse dell'utente documentato. "
            "È soltanto una comunicazione commerciale non sollecitata."
        ),
        "now": "Nessuna urgenza; nessun contratto o vincolo da verificare.",
        "initiative": "inform",
        "goal": (
            "Nessun lavoro utile o decisione dell'utente dipende dal messaggio."
        ),
    },
    "already_resolved": {
        "expect": "no_goal",
        "summary": (
            "La conferma di un appuntamento coincide già con "
            "il calendario verificato alle 15:00."
        ),
        "why": (
            "L'utente ha già l'informazione corretta; "
            "nessuna discrepanza o passaggio mancante."
        ),
        "now": "La situazione è stata già risolta e comunicata.",
        "initiative": "inform",
        "goal": "Nessuna modifica, proposta o messaggio da preparare.",
    },
    "provider_unavailable": {
        "expect": "unavailable",
        "summary": "Un documento ricevuto potrebbe modificare un impegno.",
        "why": "Serve capire se nasce un lavoro utile.",
        "now": "Il servizio di ragionamento non risponde.",
        "initiative": "prepare",
        "goal": "Il guasto non va interpretato come nessun bisogno.",
    },
}


def _scripted_reply(name: str) -> Optional[dict]:
    if name == "provider_unavailable":
        return None
    if SCENARIOS[name]["expect"] == "create_goal":
        return {
            "outcome": "create_goal",
            "objective": "Verificare la comunicazione e preparare la correzione",
            "desired_outcome": "Orario corretto e verificato senza scritture esterne",
            "why_now": "Gli orari osservati si contraddicono",
            "success_criteria": ["Identificare la fonte autorevole"],
            "stop_conditions": ["La discrepanza viene smentita"],
            "reasoning": "Il conflitto di orario richiede un riscontro prima dell'azione.",
        }
    return {"outcome": "no_goal", "reasoning": "La situazione non richiede altro lavoro."}


async def run_case(name: str, *, mode: str = "scripted") -> dict:
    """Use production admission, reasoning, persistence and wake scheduling."""
    if name not in SCENARIOS:
        raise ValueError("unknown_scenario")
    if mode not in ("scripted", "live"):
        raise ValueError("unknown_mode")
    from mongomock_motor import AsyncMongoMockClient
    from opportunities.models import Opportunity
    from opportunities.repository import OpportunityRepository
    from agent.service import AgentService
    from agent.admission import drain
    from agent import reasoning

    now = datetime.now(timezone.utc)
    fixture = SCENARIOS[name]
    owner = f"{OWNER_PREFIX}-{name}"
    db = AsyncMongoMockClient()[f"proactive_{name}"]
    repo = OpportunityRepository(db)
    await repo.ensure_indexes()
    agent = AgentService(db)
    await agent.ensure_indexes()

    opportunity = await repo.save(Opportunity(
        owner_id=owner,
        identity_key=f"synthetic_eval:{name}",
        status="active",
        semantic_summary=fixture["summary"],
        why_it_matters=fixture["why"],
        why_now=fixture["now"],
        what_ora_can_do=fixture["goal"],
        initiative=fixture["initiative"],
        valid_until=(now + timedelta(days=2)).isoformat(),
    ))

    model_requests = 0
    model_answered = False
    original = reasoning._ask_model

    async def observed_model(system, user):
        nonlocal model_requests, model_answered
        model_requests += 1
        result = await original(system, user)
        model_answered = isinstance(result, dict)
        return result

    async def synthetic_decision(situation, *, language="it"):
        return _scripted_reply(name)

    context = (
        patch.object(reasoning, "decide_goal", synthetic_decision)
        if mode == "scripted" or name == "provider_unavailable"
        else patch.object(reasoning, "_ask_model", observed_model)
    )
    with context:
        # Repository.save records the admission due-time after the fixture
        # timestamp was created. Use the worker clock AFTER persistence:
        # otherwise a synthetic race would see no due row and report failure.
        handled = await drain(db, owner_id=owner, limit=1)

    goal_rows = await db.agent_goals.find(
        {"owner_id": owner}, {"_id": 0},
    ).to_list(5)
    wakes = await db.ambient_wakes.find(
        {"owner_id": owner, "status": "pending"}, {"_id": 0},
    ).to_list(5)
    admission = await db.opportunities.find_one(
        {"owner_id": owner, "id": opportunity.id},
        {"_id": 0, "agent_review_outcome": 1, "agent_review_state": 1,
         "agent_review_due": 1, "agent_review_goal_id": 1},
    )
    count = await db.action_intents.count_documents({"owner_id": owner})
    pending = admission.get("agent_review_outcome")
    expected = fixture["expect"]

    failure_codes = []
    if handled != 1:
        failure_codes.append("ADMISSION_DID_NOT_PROCESS")
    if pending != expected:
        failure_codes.append("UNEXPECTED_PROACTIVE_JUDGEMENT")
    if expected == "create_goal":
        if len(goal_rows) != 1:
            failure_codes.append("GOAL_NOT_PERSISTED")
        if len(wakes) != 1 or not str(wakes[0].get("source_ref") or "").startswith("goal:"):
            failure_codes.append("GOAL_WAKE_NOT_PERSISTED")
        if goal_rows and (goal_rows[0].get("requires_user_authority")
                          or goal_rows[0].get("requires_user_input")):
            failure_codes.append("SPONTANEOUS_WORK_MARKED_UNNECESSARILY_BLOCKED")
    elif expected == "no_goal":
        if goal_rows or wakes:
            failure_codes.append("UNNECESSARY_WORK_CREATED")
    elif expected == "unavailable":
        if admission.get("agent_review_state") != "pending" or not admission.get("agent_review_due"):
            failure_codes.append("PROVIDER_ERROR_NOT_RETRYABLE")
        if goal_rows or wakes:
            failure_codes.append("PROVIDER_ERROR_FAKED_AS_WORK")
    if count:
        failure_codes.append("EXTERNAL_ACTION_INTENT_CREATED")
    if mode == "live" and name != "provider_unavailable" and not model_answered:
        failure_codes.append("REAL_MODEL_NOT_VERIFIED")
    if mode == "scripted" and model_requests:
        failure_codes.append("SCRIPTED_MODE_CALLED_LLM")

    return {
        "version": VERSION,
        "scenario": name,
        "mode": mode,
        "scope": "isolated_synthetic_no_real_user_or_world_effects",
        "real_model_answered": mode == "live" and model_answered,
        "llm_requests": model_requests,
        "admission_processed": handled,
        "outcome": str(pending or ""),
        "expected_outcome": expected,
        "persisted_goals": len(goal_rows),
        "pending_wakes": len(wakes),
        "action_intents": count,
        "verdict": {"passed": not failure_codes, "reasons": failure_codes},
    }


async def main(*, mode: str, scenario: str, output: str = "") -> int:
    if mode == "live" and not any(
        os.environ.get(k) for k in (
            "GEMINI_API_KEY", "GEMINI_API_KEY_2", "OPENAI_API_KEY",
            "GROQ_API_KEY", "MISTRAL_API_KEY",
        )
    ):
        print("ORA_PHASE2_PROACTIVE_BLOCKED " + json.dumps({
            "reason": "live_credentials_unavailable", "real_model_answered": False,
        }), flush=True)
        return 3
    selected = SCENARIOS.keys() if scenario == "all" else (scenario,)
    rows = []
    for name in selected:
        try:
            row = await asyncio.wait_for(run_case(name, mode=mode), timeout=85)
        except Exception as exc:
            row = {
                "version": VERSION, "scenario": name, "mode": mode,
                "real_model_answered": False,
                "verdict": {
                    "passed": False,
                    "reasons": ["EVALUATOR_ERROR:" + type(exc).__name__[:50]],
                },
            }
        print("ORA_PHASE2_PROACTIVE_EVAL " + json.dumps(row, ensure_ascii=False), flush=True)
        rows.append(row)
    summary = {
        "version": VERSION, "mode": mode, "cases": len(rows),
        "passed": all(row["verdict"]["passed"] for row in rows),
        "passed_cases": [r["scenario"] for r in rows if r["verdict"]["passed"]],
        "failed_cases": [r["scenario"] for r in rows if not r["verdict"]["passed"]],
        "real_model_executed": mode == "live" and any(
            row.get("real_model_answered") for row in rows
        ),
    }
    print("ORA_PHASE2_PROACTIVE_SUMMARY " + json.dumps(summary), flush=True)
    if output:
        dest = Path(output)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps({"summary": summary, "cases": rows},
                                   ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("scripted", "live"), default="scripted")
    parser.add_argument("--scenario", choices=("all", *SCENARIOS), default="all")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(mode=args.mode, scenario=args.scenario,
                                      output=args.output)))
