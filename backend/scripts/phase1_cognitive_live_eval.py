"""ORA Phase 1: opt-in real-LLM evaluation with a synthetic, isolated user.

The cognitive loop, prompt, catalogue, governance and LLM manager are the
production implementations. Every user fact and tool response is synthetic.
All ToolRegistry execution is intercepted: no calendar writes, messages,
calls, real routing, live weather, payments or purchases can occur.

Usage:
    python -m scripts.phase1_cognitive_live_eval --mode scripted
    python -m scripts.phase1_cognitive_live_eval --mode live --scenario all

The live mode needs a configured LLM key. It is never run on production user
accounts. Results distinguish model choice, sandbox observations, durable
in-memory effects, and actual real-world capability (which is NOT tested).
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack
from datetime import datetime, timedelta
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Callable
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

LOG = logging.getLogger("ora.phase1_real_eval")
VERSION = "phase1-real-model-v125"
OWNER = "eval-fictional-user-only"
FIXTURE_SOURCE = "synthetic_eval_fixture"
READ_FIXTURES = frozenset({
    "get_calendar_events", "get_route", "get_weather_forecast",
    "list_life_places", "get_profile_snapshot", "search_my_life",
    "get_current_location", "search_life_memory", "get_life_place",
})
# The ONLY writes allowed are to the brand-new in-memory Mongo for this
# invocation, using production handlers that never contact outside services.
SAFE_LOCAL_WRITES = frozenset({
    "schedule_situation_check", "save_recurring_memo",
})
SAFE_LOCAL_READBACKS = frozenset({"get_situation_followup"})

SCENARIOS = {
    "trip": {
        "message": (
            "Domani devo raggiungere mia madre a Porto Esempio per una visita "
            "alle 11:00. Organizza lo spostamento: controlla il calendario, "
            "verifica il tragitto tenendo conto del traffico e controlla il meteo. "
            "Dimmi cosa hai verificato e a che ora converrebbe partire. "
            "Non creare appuntamenti, inviare messaggi o spendere denaro."
        ),
        "facts": [
            ("memory:fictional_mother", "La madre vive a Porto Esempio, in Piazza Giardino 2. È un luogo confermato nel profilo."),
            ("memory:fictional_home", "La persona abita a Colle Test; la posizione corrente è disponibile e autorizzata per i percorsi."),
        ],
        "required_read": ("get_calendar_events", "get_route", "get_weather_forecast"),
    },
    "situation": {
        "message": (
            "Ho appena steso i panni sul balcone di casa. Temo che possa "
            "piovere nel pomeriggio. Controlla il meteo e tieni presente "
            "questa situazione temporanea; avvisami soltanto se un controllo "
            "effettivamente programmato segnalerà un rischio. Non promettere "
            "una notifica se non puoi attivarla."
        ),
        "facts": [
            ("memory:fictional_home", "La persona si trova a casa a Colle Test, con posizione consentita."),
        ],
        "required_read": ("get_weather_forecast",),
    },
    "birthday": {
        "message": (
            "Il 13 marzo è il compleanno di mia zia Ada. Salvalo nella "
            "memoria permanente e ricordami questa data ogni 13 marzo, "
            "tutti gli anni. Conferma il promemoria solo se è stato "
            "effettivamente registrato."
        ),
        "facts": [],
        "required_read": (),
    },
}


def _next_visit() -> str:
    local = datetime.now(ZoneInfo("Europe/Rome")) + timedelta(days=1)
    return local.replace(hour=11, minute=0, second=0, microsecond=0).isoformat()


def _fixture(cap: str, arguments: dict[str, Any]) -> dict[str, Any]:
    visit = _next_visit()
    if cap == "get_calendar_events":
        event = {
            "title": "Visita familiare (dati sintetici)",
            "start_datetime": visit,
            "end_datetime": visit,
            "calendar_ref": "calendar:synthetic-visit",
            "source": FIXTURE_SOURCE,
        }
        return {"status": "ok", "items": [event], "events": [event]}
    if cap == "get_route":
        return {
            "status": "ok", "available": True,
            "duration_seconds": 4200, "distance_meters": 82000,
            "reflects_current_traffic": True,
            "travel_mode": "drive", "provider": FIXTURE_SOURCE,
            "destination": str(arguments.get("destination") or "Porto Esempio")[:90],
        }
    if cap == "get_weather_forecast":
        return {
            "status": "ok", "place": "Colle Test", "provider": FIXTURE_SOURCE,
            "current": {"condition": "Nuvoloso", "temperature_c": 19,
                        "humidity_pct": 70, "wind_kmh": 12},
            "hours": [{"time": "16:00", "temperature_c": 18,
                       "rain_chance_pct": 75, "wind_kmh": 18}],
        }
    if cap == "list_life_places":
        return {"status": "ok", "items": [
            {"label": "Casa", "ref": "place:synthetic-home"},
            {"label": "Casa della madre", "ref": "place:synthetic-mother"},
        ]}
    if cap == "get_current_location":
        return {"status": "ok", "available": True,
                "latitude": 42.4, "longitude": 11.8,
                "provider": FIXTURE_SOURCE}
    if cap == "get_life_place":
        return {"status": "ok", "ref": str(arguments.get("place_ref") or "place:synthetic-home"),
                "label": "Casa (dato sintetico)", "available": True}
    if cap in ("search_my_life", "search_life_memory", "get_profile_snapshot"):
        return {"status": "ok", "facts": [
            {"ref": "memory:fictional_mother",
             "statement": "La madre vive in Piazza Giardino 2 a Porto Esempio.",
             "source": FIXTURE_SOURCE},
            {"ref": "memory:fictional_home",
             "statement": "Casa è a Colle Test.", "source": FIXTURE_SOURCE},
        ]}
    raise ValueError("fixture_not_allowlisted")


def _model_signal(raw: dict[str, Any]) -> dict[str, Any]:
    tool = raw.get("tool_call") or {}
    if not isinstance(tool, dict):
        tool = {}
    plan = raw.get("skill_plan") or {}
    if not isinstance(plan, dict):
        plan = {}
    situation = raw.get("situation_update") or {}
    if not isinstance(situation, dict):
        situation = {}
    memory = raw.get("memory_candidates") or []
    return {
        "mode": str(raw.get("response_mode") or "")[:35],
        "reasoning_status": str(raw.get("reasoning_status") or "")[:42],
        "capability": str(tool.get("capability") or tool.get("name") or "")[:90],
        "required": [
            str(name)[:90] for name in (plan.get("required_capabilities") or [])[:12]
        ],
        "resume": bool(plan.get("resume_plan_ref")),
        "situation_op": str(situation.get("operation") or "")[:30],
        "memory_proposals": len(memory) if isinstance(memory, list) else 0,
    }


def _verdict(
    case: str, result: Any, decisions: list[dict[str, Any]],
    observations: list[dict[str, Any]], *,
    memory_count: int = 0, reminder_count: int = 0,
    situation_count: int = 0, followup_count: int = 0,
) -> dict[str, Any]:
    """Conservative evidence gate, never success solely because model said so."""
    seen = {
        row["capability"]
        for row in observations
        if row.get("outer_status") in ("ok", "success")
        and row.get("result_status") == "ok"
        and row.get("fixture") == FIXTURE_SOURCE
    }
    needed = set(SCENARIOS[case]["required_read"])
    missing = sorted(needed - seen)
    failure_reasons = []
    if result is None or not result.ok:
        failure_reasons.append("cognitive_loop_not_ok")
    if missing:
        failure_reasons.append("missing_verified_reads:" + ",".join(missing))
    if case == "situation" and situation_count == 0:
        failure_reasons.append("situation_not_persisted")
    if case == "situation" and followup_count == 0:
        failure_reasons.append("followup_not_actually_scheduled")
    if case == "birthday":
        if memory_count == 0:
            failure_reasons.append("permanent_memory_not_persisted")
        if reminder_count == 0:
            failure_reasons.append("annual_reminder_not_persisted")
    if any(
        x.get("fixture") == "blocked" and x.get("side_effect") != "READ_ONLY"
        for x in observations
    ):
        # Only approved in-memory local writes are allowed; external effects
        # remain blocked and cannot count towards product acceptance.
        failure_reasons.append("blocked_world_changing_capability")
    if not decisions:
        failure_reasons.append("no_model_decisions")
    return {
        "passed": not failure_reasons,
        "reasons": failure_reasons,
        "required_reads": sorted(needed),
        "verified_reads": sorted(seen),
        "model_decisions": len(decisions),
        "synthetic_situations": situation_count,
        "synthetic_scheduled_followups": followup_count,
        "synthetic_memories": memory_count,
        "synthetic_recurring_memos": reminder_count,
        "final_mode": str(getattr(result, "mode", "") or "")[:30],
        "ai_calls": int(getattr(result, "ai_calls", 0) or 0),
        "tool_calls": int(getattr(result, "tool_calls", 0) or 0),
        "skill_plan_completed": bool((getattr(result, "trace", {}) or {}).get("skill_plan_completed")),
    }


async def run_case(
    name: str, *, decide: Callable | None = None, max_steps: int = 7,
) -> dict[str, Any]:
    """Execute one synthetic session with actual AI Core and fake tools."""
    from mongomock_motor import AsyncMongoMockClient
    from conversation_engine.ai_core.context_broker import ContextBroker
    from conversation_engine.ai_core.models import ContextFact, Observation
    from conversation_engine.ai_core.tools.registry import ToolRegistry
    from conversation_engine.ai_core import loop as cognitive_loop
    from conversation_engine.models import ConversationSession
    import research.service as research_service
    import conversation_engine.ai_core.calendar_ahead as calendar_ahead

    if name not in SCENARIOS:
        raise ValueError("unknown_case")
    scenario = SCENARIOS[name]
    db = AsyncMongoMockClient()[f"ora_eval_{name}"]
    sess = ConversationSession(
        user_id=OWNER, meta={"ui_mode": "ai_core", "ai_core": {}},
    )
    context = [
        ContextFact(statement=text, fact=text, source=FIXTURE_SOURCE,
                    authority="user_stated", status="known", ref=ref)
        for ref, text in scenario["facts"]
    ]
    decisions: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    llm_error_types: list[str] = []

    async def synthetic_context(self, **_kwargs):
        return list(context)

    async def sandbox_execute(self, capability, arguments, *, runtime=None):
        spec = self.get(capability)
        side_effect = getattr(spec, "side_effect", "unknown") if spec else "unknown"
        if side_effect == "READ_ONLY" and capability in READ_FIXTURES:
            payload = _fixture(capability, arguments or {})
            outer = "ok"
            kind = "tool"
            synthetic = FIXTURE_SOURCE
        elif (
            spec is not None and spec.handler is not None
            and (
                (side_effect == "REVERSIBLE_WRITE"
                 and capability in SAFE_LOCAL_WRITES)
                or (side_effect == "READ_ONLY"
                    and capability in SAFE_LOCAL_READBACKS)
            )
        ):
            # Explicitly allow just two internal persisted operations, against
            # *this* synthetic Mongo instance. Never forward runtime-supplied
            # credentials or connection details.
            observation = await spec.handler(
                dict(arguments or {}), {"db": db, "user_id": OWNER}
            )
            payload = dict(observation.payload or {})
            outer = str(observation.status or "failed")
            kind = "tool"
            synthetic = (
                "synthetic_db_write" if side_effect == "REVERSIBLE_WRITE"
                else "synthetic_db_read"
            )
        else:
            # No Google Calendar, telephone, bank, real-world purchase,
            # location sensor, email or other service may execute.
            payload = {
                "status": "failed",
                "failure_code": "EVAL_ISOLATION_BOUNDARY",
                "reason": "Capability unavailable in synthetic evaluation.",
                "retryable": False,
            }
            outer = "failed"
            kind = "tool"
            synthetic = "blocked"
        observations.append({
            "capability": str(capability)[:90],
            "side_effect": side_effect,
            "outer_status": outer,
            "result_status": str(payload.get("status") or "")[:45],
            "fixture": synthetic,
        })
        return Observation(
            kind=kind, name=str(capability), status=outer, payload=payload,
            provenance=[FIXTURE_SOURCE] if synthetic == FIXTURE_SOURCE else [],
        )

    if decide is None:
        from llm.manager import get_manager
        from conversation_engine.ai_core.loop import _parse_json
        manager = get_manager()

        async def real_decide(system: str, user: str) -> dict[str, Any]:
            try:
                response = await manager.chat(
                    system=system, user=user, json_mode=True,
                    latency_budget_s=18.0,
                )
                raw = _parse_json(str(getattr(response, "text", "") or ""))
                if not isinstance(raw, dict):
                    llm_error_types.append("INVALID_MODEL_JSON")
                    raise ValueError("invalid_model_json")
            except Exception as exc:
                llm_error_types.append(type(exc).__name__[:90])
                raise
            decisions.append(_model_signal(raw))
            return raw
        decision = real_decide
    else:
        async def scripted_decide(system: str, user: str) -> dict[str, Any]:
            raw = await decide(system, user)
            decisions.append(_model_signal(raw))
            return raw
        decision = scripted_decide

    async def no_calendar_prefetch(db, user_id):
        return None

    async def no_followup_refresh(self, *args, **kwargs):
        return None

    # Strict scoped patches: real model remains enabled, but every skill call
    # and outgoing research gateway is either a fixture or a denied boundary.
    from situations.turn_followup import FollowupTurnGate
    import situations.followup as situation_followup
    with ExitStack() as stack:
        stack.enter_context(patch.object(
            ToolRegistry, "execute", sandbox_execute,
        ))
        stack.enter_context(patch.object(
            ContextBroker, "retrieve", synthetic_context,
        ))
        stack.enter_context(patch.object(
            calendar_ahead, "the_next_two_days", no_calendar_prefetch,
        ))
        stack.enter_context(patch.object(
            research_service, "research_available", lambda: False,
        ))
        stack.enter_context(patch.object(
            FollowupTurnGate, "refresh", no_followup_refresh,
        ))
        # Enable only the synthetic in-process scheduler. No background
        # worker, HTTP endpoint or production database is started.
        stack.enter_context(patch.object(
            situation_followup, "_enabled", lambda: True,
        ))
        stack.enter_context(patch.object(
            cognitive_loop, "report_activity", AsyncMock(),
        ))
        previous_trace = os.environ.get("AI_CORE_TRACE")
        os.environ["AI_CORE_TRACE"] = "1"
        try:
            result = await cognitive_loop.run_cognitive_loop(
                sess=sess, user_message=scenario["message"], db=db,
                decision_fn=decision, max_steps=max_steps,
            )
        finally:
            if previous_trace is None:
                os.environ.pop("AI_CORE_TRACE", None)
            else:
                os.environ["AI_CORE_TRACE"] = previous_trace

    async def count_any(names: tuple[str, ...]) -> int:
        return sum([await db[n].count_documents({}) for n in names])
    # Only synthetic, in-memory Mongo. Counting does not inspect private data.
    reminder_count = await count_any(("recurring_memos",))
    memory_count = await count_any(("life_memories", "memories"))
    situation_count = await db.situations.count_documents({
        "user_id": OWNER, "status": {"$in": ["active", "changed"]},
    })
    followup_count = 0
    for saved in await db.situations.find(
        {"user_id": OWNER}, {"_id": 0, "id": 1}
    ).to_list(10):
        # The actual readback contract, not a claim in the LLM's prose.
        check = await situation_followup.read_followup(
            db, OWNER, str(saved.get("id") or "")
        )
        if check.get("status") in ("scheduled", "due", "running"):
            followup_count += 1
    verdict = _verdict(
        name, result, decisions, observations,
        memory_count=memory_count, reminder_count=reminder_count,
        situation_count=situation_count, followup_count=followup_count,
    )
    return {
        "case": name,
        "version": VERSION,
        "scope": "real_model_in_memory_synthetic_tools" if decide is None
                 else "scripted_model_in_memory_synthetic_tools",
        "owner": "synthetic_isolated_no_real_account",
        "verdict": verdict,
        "decisions": decisions[:12],
        "observations": observations[:20],
        "events": [
            str(x.get("event") or "")[:80]
            for x in ((result.trace if result else {}).get("steps") or [])
            if x.get("event") in {
                "SKILL_PLAN_COMPLETED", "SKILL_PLAN_BOUND_COMPLETED",
                "SKILL_PLAN_FAILED", "SKILL_PLAN_BOUND_UNFINISHED",
                "SKILL_PLAN_FAILURE_USER_NOTICE", "SKILL_PLAN_PAUSED",
                "SKILL_PLAN_RESUMED", "READY_ACT_NO_EFFECT_BLOCKED",
            }
        ][:25],
        "llm_error_types": llm_error_types,
    }


async def _scripted_model_factory(case_name: str):
    """CI-controlled decisions: proves runner instrumentation, not model IQ."""
    calls = 0

    async def decide(system: str, user: str) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        required = list(SCENARIOS[case_name]["required_read"])
        if calls <= len(required):
            item = {
                "response_mode": "tool",
                "reasoning_status": "needs_tool",
                "tool_call": {
                    "capability": required[calls - 1],
                    "arguments": {"destination": "Porto Esempio"},
                },
                "situation_update": {"operation": "none"},
            }
            if calls == 1:
                item["skill_plan"] = {
                    "objective": "Verificare i controlli richiesti",
                    "required_capabilities": required,
                }
            return item
        return {
            "response_mode": "answer", "reasoning_status": "enough_information",
            "message_to_user": "Ho letto gli esiti sintetici.",
            "situation_update": {"operation": "none"},
        }

    return decide


async def main(mode: str, scenario: str, max_steps: int, output: str | None) -> int:
    selected = list(SCENARIOS) if scenario == "all" else [scenario]
    rows = []
    for name in selected:
        try:
            decide = (
                await _scripted_model_factory(name)
                if mode == "scripted" else None
            )
            row = await asyncio.wait_for(
                run_case(name, decide=decide, max_steps=max_steps),
                timeout=210,
            )
        except Exception as exc:
            # Fail closed. Never dump raw LLM responses, environment, prompts
            # or credentials into CI output/artifacts.
            row = {
                "case": name, "version": VERSION, "scope": mode,
                "owner": "synthetic_isolated_no_real_account",
                "verdict": {"passed": False, "reasons": [
                    "runner_error:" + type(exc).__name__[:65],
                ]},
            }
        rows.append(row)
        print("ORA_PHASE1_EVAL " + json.dumps(row, ensure_ascii=False), flush=True)
    aggregate = {
        "version": VERSION,
        "mode": mode,
        "case_count": len(rows),
        "passed": all(r["verdict"]["passed"] for r in rows),
        "passed_cases": [r["case"] for r in rows if r["verdict"]["passed"]],
        "failed_cases": [r["case"] for r in rows if not r["verdict"]["passed"]],
        "isolation": "synthetic_in_memory_no_real_world_effects",
        "real_model_executed": mode == "live" and any(
            r.get("verdict", {}).get("model_decisions", 0) > 0 for r in rows
        ),
    }
    print("ORA_PHASE1_SUMMARY " + json.dumps(aggregate, ensure_ascii=False), flush=True)
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(
            json.dumps({"summary": aggregate, "cases": rows},
                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
    return 0 if aggregate["passed"] else 1


def _args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("live", "scripted"), default="live")
    parser.add_argument("--scenario", choices=("all", *SCENARIOS), default="all")
    parser.add_argument("--max-steps", type=int, default=7)
    parser.add_argument("--output", default="")
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    args = _args()
    if args.mode == "live" and not any(
        os.environ.get(k) for k in (
            "GEMINI_API_KEY", "GEMINI_API_KEY_2", "OPENAI_API_KEY",
            "GROQ_API_KEY", "MISTRAL_API_KEY",
        )
    ):
        print("ORA_PHASE1_EVAL_BLOCKED " + json.dumps({
            "reason": "live_llm_credentials_unavailable",
            "real_model_executed": False,
        }), flush=True)
        raise SystemExit(3)
    raise SystemExit(asyncio.run(
        main(args.mode, args.scenario, max(1, min(8, args.max_steps)),
             args.output or None)
    ))
