"""Opt-in first-cycle Situation evaluation, with no device or physical effects.

The fictional user has JUST hung laundry outside at a fixed public point in
Tarquinia. Production conversation, Situation admission, the initial Ambient
wake, Agent execution, source guards and subsequent scheduling remain connected.
Live mode uses the configured model/weather/research chain. Scripted mode uses
explicit model answers and HTTP fixtures, never a live provider or model.

The first persisted wake is awaited on the real clock (normally at least 30
seconds). Conversation may already have promoted the initial review to a
model-selected check. If that first check lies outside this run, it remains
unobserved, never monitoring success. No wait or physical timestamp is expedited.
A subsequent checkpoint is NOT RUN by this bounded first-cycle probe. Monitoring
success does not prove dryness, a later outcome, source fitness or receipt.

    python -m scripts.situation_live_eval_v162 --mode scripted
    python -m scripts.situation_live_eval_v162 --mode live --output /tmp/situation.json

No global scheduler is started. Every database operation targets a newly made
in-memory database, which does not survive process exit. Cancellation at the end
withdraws only this fictional test; it never says actual laundry was collected.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import traceback
from typing import Any
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from scripts.autonomy_completion_eval_v162 import (
    CASE_TIMEOUT_SECONDS, MAX_DECISION_OBSERVATIONS, MAX_MODEL_CALLS,
    MAX_MODEL_HTTP_REQUESTS,
)
from scripts.phase1_read_provider_eval import (
    _ReadBoundary, _gemini_httpx_options, _http_evidence, _llm_endpoint,
    _scripted_reply as _public_scripted_reply, _time_valid,
)

VERSION = "situation-live-v162"
CASE = "laundry_tarquinia_first_cycle"
OWNER = "ora-synthetic-situation-live-v162"
PLACE = {"id": "eval-tarquinia-public-point", "label": "Tarquinia",
         "latitude": 42.249, "longitude": 11.756}
TIMEZONE = "Europe/Rome"
# The public-read boundary already allows twelve provider requests per case.
MAX_PROVIDER_READS = 12
READ_CAPABILITIES = frozenset({"weather.read", "web.research", "information.read"})
LOCAL_TOOLS = frozenset({"list_life_places", "get_life_place", "get_situation_followup",
                         "schedule_situation_check", "search_life_memory", "get_profile_snapshot"})
EXTERNAL_TOOLS = frozenset({"get_weather_forecast", "web_search"})
_KEY_NAMES = ("GEMINI_API_KEY", "GEMINI2_API_KEY", "GEMINI_API_KEY_2", "OPENAI_API_KEY",
              "GROQ_API_KEY", "MISTRAL_API_KEY", "TAVILY_API_KEY", "BRAVE_SEARCH_API_KEY",
              "BRAVE_API_KEY", "ROUTING_API_KEY", "WEATHER_API_KEY")
_MODEL_NAMES = frozenset({"gemini", "gemini2", "groq", "mistral", "openai", "ollama", "emergent"})
_STAGE = ContextVar("situation_eval_stage", default="unclassified")


class EvaluationFailure(RuntimeError):
    """Only code-owned diagnostics, never request bodies or provider errors."""


def require(condition, code):
    if not condition:
        raise EvaluationFailure(code)


def require_synthetic_database(db):
    from mongomock_motor import AsyncMongoMockDatabase
    # This adapter intentionally advertises Motor's module name; exact type
    # identity distinguishes it from a real Motor database without opening one.
    require(type(db) is AsyncMongoMockDatabase, "SYNTHETIC_DATABASE_REQUIRED")


def now():
    return datetime.now(timezone.utc)


def moment(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result if result.tzinfo is not None else None
    except (TypeError, ValueError, AttributeError):
        return None


def safe_text(value, limit=600):
    text = value if isinstance(value, str) else ""
    for name in _KEY_NAMES:
        secret = os.environ.get(name) or ""
        if len(secret) >= 8:
            text = text.replace(secret, "[credential redacted]")
    return text[:limit]


def observed_json(value, limit=6000):
    """Bound report-only structures without pretending an excerpt is whole."""
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    clean = redact_report(json.loads(encoded))
    cleaned = json.dumps(clean, ensure_ascii=False)
    if len(cleaned) <= limit:
        return clean
    return {"excerpt": cleaned[:limit], "characters": len(encoded), "truncated": True}


def redact_report(value):
    if isinstance(value, str):
        return safe_text(value, len(value))
    if isinstance(value, list):
        return [redact_report(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_report(item) for key, item in value.items()}
    return value


def public_url(value):
    try:
        url = urlsplit(safe_text(value, 1000))
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
            return ""
        return urlunsplit((url.scheme, url.netloc, url.path, "", ""))[:600]
    except ValueError:
        return ""


def code_revision():
    value = os.environ.get("RAILWAY_GIT_COMMIT_SHA", "")
    if re.fullmatch(r"[a-fA-F0-9]{40}", value):
        return value.lower()
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                cwd=Path(__file__).resolve().parents[2], timeout=5)
        value = result.stdout.strip()
        return value if result.returncode == 0 and re.fullmatch(r"[a-f0-9]{40}", value) else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def scenario_message(started):
    local = started.astimezone(ZoneInfo(TIMEZONE))
    return (
        f"Oggi {local.date().isoformat()}, alle {local:%H:%M:%S} (Europe/Rome), "
        "ho appena steso i panni all'aperto a Tarquinia, nel luogo già salvato. "
        "Dimmi quando è il momento di ritirarli perché presumibilmente asciutti, "
        "oppure prima se il meteo richiede di metterli al riparo. "
        "Questo è un nuovo caso sintetico di valutazione, senza sensori sui panni."
    )


@dataclass
class Probe:
    mode: str
    logical_calls: int = 0
    manager_calls: int = 0
    grounded_search_calls: int = 0
    model_http: int = 0
    scripted_calls: int = 0
    model_calls: list = field(default_factory=list)
    decisions: list = field(default_factory=list)
    decisions_omitted: int = 0
    steps: list = field(default_factory=list)
    tools: list = field(default_factory=list)
    push_attempts: list = field(default_factory=list)
    blocked: list = field(default_factory=list)
    context_observations: list = field(default_factory=list)
    research_reads: list = field(default_factory=list)

    def reserve_model(self, kind):
        spent = self.logical_calls if self.mode == "live" else self.scripted_calls
        if spent >= MAX_MODEL_CALLS:
            self.blocked.append("MODEL_CALL_BOUND_EXCEEDED")
            raise EvaluationFailure("MODEL_CALL_BOUND_EXCEEDED")
        if self.mode == "scripted":
            self.scripted_calls += 1
        else:
            self.logical_calls += 1
            if kind == "manager":
                self.manager_calls += 1
            else:
                self.grounded_search_calls += 1

    def observe_model(self, system, user, result=None, error=None):
        # The fixture contains no real private material. Record bounded actual
        # input, not a reconstructed stronger claim about what the model saw.
        entry = {"stage": _STAGE.get(), "system_sha256": hashlib.sha256(system.encode()).hexdigest(),
                 "input": safe_text(user, 9000), "input_characters": len(user),
                 "input_truncated": len(user) > 9000,
                 "output": safe_text(getattr(result, "text", ""), 4000),
                 "output_characters": len(getattr(result, "text", "") or ""),
                 "output_truncated": len(getattr(result, "text", "") or "") > 4000,
                 "error_type": type(error).__name__[:80] if error is not None else None}
        if len(self.decisions) >= MAX_DECISION_OBSERVATIONS:
            self.decisions.pop(2)  # retain the initial two plus the latest calls
            self.decisions_omitted += 1
        self.decisions.append(entry)


class SituationReadBoundary(_ReadBoundary):
    """Runner-only scoped HTTPX boundary; not a global socket sandbox.

    Reuses the public runner's SDK transport selection and observation metadata.
    Only the fixed fixture point and existing search APIs extend its read scope.
    Gemini Search is both a model request and a provider read, sharing both caps.
    """

    def __init__(self, probe):
        super().__init__(model_live=probe.mode == "live",
                         provider_reply=scripted_http if probe.mode == "scripted" else None)
        self.probe = probe
        self.blocked = probe.blocked

    def endpoint(self, request):
        if request.url.scheme != "https":
            return None
        scope, host, path = self.scope.get(), request.url.host, request.url.path
        if scope == "weather" and request.method == "GET" and host == "api.open-meteo.com" and path == "/v1/forecast":
            try:
                pair = (float(request.url.params["latitude"]), float(request.url.params["longitude"]))
                return "open_meteo" if pair == (PLACE["latitude"], PLACE["longitude"]) else None
            except (KeyError, TypeError, ValueError):
                return None
        if scope == "research":
            if request.method == "POST" and host == "api.tavily.com" and path == "/search":
                return "tavily"
            if request.method == "GET" and host == "api.search.brave.com" and path == "/res/v1/web/search":
                return "brave"
        if scope == "grounded_search" and host == "generativelanguage.googleapis.com" and _llm_endpoint(request):
            return "gemini_search"
        return None

    def install(self, stack):
        import httpx
        original_send, original_init = httpx.AsyncClient.send, httpx.AsyncClient.__init__

        def checked_init(client, *args, **kwargs):
            if self.provider_reply:
                kwargs["trust_env"] = False
            original_init(client, *args, **kwargs)

        async def send(client, request, **kwargs):
            is_model = self.scope.get() == "model" and _llm_endpoint(request)
            provider = self.endpoint(request)
            if (((is_model or provider == "gemini_search") and not self.model_live)
                    or not is_model and provider is None):
                self.blocked.append("EVAL_HTTP_NOT_ALLOWLISTED")
                raise EvaluationFailure("EVAL_HTTP_NOT_ALLOWLISTED")
            if not is_model and len(self.reads) >= MAX_PROVIDER_READS:
                self.blocked.append("PROVIDER_READ_BOUND_EXCEEDED")
                raise EvaluationFailure("PROVIDER_READ_BOUND_EXCEEDED")
            if is_model or provider == "gemini_search":
                if self.probe.model_http >= MAX_MODEL_HTTP_REQUESTS:
                    self.blocked.append("MODEL_HTTP_BOUND_EXCEEDED")
                    raise EvaluationFailure("MODEL_HTTP_BOUND_EXCEEDED")
                self.probe.model_http += 1
            if is_model:
                return await original_send(client, request, **{**kwargs, "follow_redirects": False})
            started = now()
            row = {"id": f"http:{len(self.reads) + 1}", "capability": self.scope.get(),
                   "provider": provider, "source": self.source}
            self.reads.append(row)
            try:
                if self.provider_reply:
                    response = self.provider_reply(request)
                else:
                    response = await original_send(client, request, **{**kwargs, "follow_redirects": False})
                row.update(_http_evidence(provider, response, started, now()))
                return response
            except BaseException as exc:
                row.update(http_status=None, error_type=type(exc).__name__[:80],
                           request_started_at=started.isoformat(), received_at=now().isoformat())
                raise

        stack.enter_context(patch.object(httpx.AsyncClient, "send", send))
        stack.enter_context(patch.object(httpx.AsyncClient, "__init__", checked_init))
        try:
            from google import genai
        except ImportError:
            return
        original_gemini = genai.Client

        def client(*args, **kwargs):
            kwargs["http_options"] = _gemini_httpx_options(kwargs.get("http_options"))
            return original_gemini(*args, **kwargs)

        stack.enter_context(patch.object(genai, "Client", client))


SCRIPTED_BASELINE = (
    "Fixture non reale: con condizioni ambientali analoghe il campione di tessuto "
    "richiedeva una finestra di 3–5 ore. Tessuto, carico, esposizione e condizioni "
    "diverse limitano il trasferimento della misura; il bucato non è osservato."
)


def scripted_http(request):
    import httpx
    if request.url.host == "api.open-meteo.com":
        return _public_scripted_reply(request)
    if request.url.host == "api.tavily.com":
        return httpx.Response(200, request=request, json={"results": [{
            "url": "https://example.org/synthetic-laundry-observation",
            "title": "Misura sintetica per il solo contratto offline", "content": SCRIPTED_BASELINE,
        }]})
    raise EvaluationFailure("SCRIPTED_ENDPOINT_NOT_DEFINED")


def scripted_records(value):
    """Read the production lossless table in the explicit model fixture only.

    Missing fields remain absent, including trailing columns; null and false
    remain values. This does not infer sources, steps or a model decision.
    """
    if isinstance(value, list):
        require(all(isinstance(row, dict) for row in value), "SCRIPTED_RECORDS_INVALID")
        return value
    if isinstance(value, dict) and set(value) == {"record_groups"}:
        require(isinstance(value["record_groups"], list), "SCRIPTED_RECORD_TABLE_INVALID")
        return [row for group in value["record_groups"] for row in scripted_records(group)]
    require(isinstance(value, dict) and set(value) <= {"common", "columns", "rows", "missing"},
            "SCRIPTED_RECORD_TABLE_INVALID")
    common, columns, rows = value.get("common"), value.get("columns"), value.get("rows")
    missing = value.get("missing", {})
    require(isinstance(common, dict) and isinstance(columns, list)
            and all(isinstance(key, str) for key in columns) and len(set(columns)) == len(columns)
            and not set(common) & set(columns) and isinstance(rows, list) and isinstance(missing, dict),
            "SCRIPTED_RECORD_TABLE_INVALID")
    result = []
    for index, values in enumerate(rows):
        require(isinstance(values, list) and len(values) <= len(columns), "SCRIPTED_RECORD_TABLE_INVALID")
        absent = missing.get(str(index), [])
        require(isinstance(absent, list) and all(type(pos) is int and 0 <= pos < len(values) for pos in absent),
                "SCRIPTED_RECORD_TABLE_INVALID")
        row = json.loads(json.dumps(common, ensure_ascii=False))
        row.update({columns[pos]: item for pos, item in enumerate(values) if pos not in absent})
        result.append(row)
    require(all(key in {str(index) for index in range(len(rows))} for key in missing),
            "SCRIPTED_RECORD_TABLE_INVALID")
    return result


class ScriptedModel:
    """Explicit fixture answers. These prove the harness, never live quality."""

    _last_attempts = []

    def __init__(self, probe, started):
        self.probe, self.started = probe, started

    async def chat(self, *, system, user, **kwargs):
        from llm.base import LLMResult
        self.probe.reserve_model("manager")
        payload = json.loads(user)
        stage = _STAGE.get()
        if stage == "conversation":
            result = {"response_mode": "answer", "reasoning_status": "enough_information",
                "message_to_user": "Ho registrato questa nuova stesura a Tarquinia. L'esito del primo controllo non è ancora disponibile.",
                "situation_update": {"operation": "create", "summary": "Panni appena stesi all'aperto a Tarquinia.",
                    "desired_outcome": "Sapere quando ritirare i panni presumibilmente asciutti o prima in caso di rischio.",
                    "attention_intent": "Riesaminare le fonti e indicare il momento utile al ritiro.",
                    "started_at": self.started.isoformat(), "location_label": "Tarquinia",
                    "linked_object_refs": ["place:" + PLACE["id"]],
                    "facts": ["I panni sono stati appena stesi all'aperto."]}}
        elif stage == "make_plan":
            result = {"planning_outcome": "plan", "plan_summary": "Fonti attuali, base empirica e riesame.", "steps": [
                {"intent": "Leggere il meteo del luogo", "step_type": "inspect", "capability_needed": "weather.read",
                 "input_refs": ["place:" + PLACE["id"]]},
                {"intent": "Cercare una base empirica pertinente", "step_type": "research", "capability_needed": "web.research",
                 "expected_result": "Quali misure pubbliche sostengono una stima prudente con queste condizioni?"},
                {"intent": "Rileggere le condizioni al controllo successivo", "step_type": "verify", "capability_needed": "weather.read"},
            ]}
        elif stage == "research_plan":
            result = {"goal": "Cercare misure applicabili con limiti espliciti", "valid_for_hours": 6,
                "questions": [{"ref": "measurement", "question": "Quali misure e limiti sono documentati?",
                    "queries": ["synthetic fixture textile drying observations conditions"]}]}
        elif stage == "research_assess":
            result = {"sufficiency": "sufficient", "reason": "Sufficiente per la sola fixture controllata, non una validazione empirica live."}
        elif stage == "research_synthesize":
            result = {"claims": [{"statement": SCRIPTED_BASELINE, "supported_by": [payload["sources"][0]["source_id"]],
                                  "scope": "general_inference"}], "caveats": ["Fonte interamente sintetica."]}
        elif stage == "research_reuse":
            result = {"reuse_run_id": None, "why": "La fixture non riusa ricerca precedente."}
        elif stage == "choose_next_action":
            evidence = scripted_records(payload.get("what_has_been_found") or [])
            weather = [row for row in evidence if row.get("capability") == "weather.read"]
            research = [row for row in evidence if row.get("capability") == "web.research"]
            if weather and research:
                assessed = now()
                result = {"decision": "wait", "reasoning": "Stima condizionata, con rilettura prima della scadenza delle fonti.",
                    "wait_minutes": 30, "situation_outcome": {
                        "status": "estimated", "headline": "Ritiro stimato nella finestra indicata, da rivalutare.",
                        "action_summary": "La finestra della fixture è una stima; i panni non sono misurati.",
                        "basis": "estimate", "action_reason": None,
                        "window_start": (self.started + timedelta(hours=3)).isoformat(),
                        "window_end": (self.started + timedelta(hours=5)).isoformat(),
                        "valid_until": (assessed + timedelta(minutes=45)).isoformat(),
                        "evidence_ids": [weather[-1]["evidence_id"], research[-1]["evidence_id"]]}}
            else:
                result = {"decision": "execute", "step_id": payload["still_to_do"][0]["id"],
                          "reasoning": "Manca una delle letture della fixture."}
        elif stage == "decide_visibility":
            result = {"outcome": "quiet_update", "headline": "È disponibile una prima stima condizionata.",
                      "about": "prima stima", "reasoning": "Non è ancora il momento dell'azione."}
        elif stage == "decide_delivery":
            result = {"mode": "in_app", "reason_to_open": "La prima stima è nella scheda.",
                      "what_decided_the_mode": "Nessuna azione immediata nella fixture."}
        elif stage == "reconsider":
            result = {"decision": "wait", "reasoning": "La prova ha incontrato una fonte non disponibile.", "revisit_in_hours": 1}
        else:
            raise EvaluationFailure("SCRIPTED_MODEL_STAGE_NOT_DEFINED")
        answer = LLMResult(text=json.dumps(result, ensure_ascii=False), provider="scripted", model="fixture_only")
        self.probe.observe_model(system, user, answer)
        return answer


class BlockedNotification:
    name = "evaluation_no_device"

    def __init__(self, probe):
        self.probe = probe

    async def send(self, **kwargs):
        # Observe the attempted final handoff without returning a fake receipt.
        require(kwargs.get("owner_id") == OWNER, "NOTIFICATION_OWNER_BOUNDARY")
        if len(self.probe.push_attempts) < MAX_PROVIDER_READS:
            self.probe.push_attempts.append({key: safe_text(kwargs.get(key), 600)
                for key in ("plan_id", "title", "body", "deep_link")})
        raise EvaluationFailure("DEVICE_SEND_FORBIDDEN")

    async def cancel(self, **kwargs):
        require(kwargs.get("owner_id") == OWNER, "NOTIFICATION_OWNER_BOUNDARY")
        return {"ok": True, "provider": self.name}


async def seed_world(db, started):
    from places.models import Coordinates, LifePlace
    require_synthetic_database(db)
    await db.eval_guards.insert_one({"_id": VERSION, "owner": OWNER})
    await db.users.insert_one({"id": OWNER, "user_id": OWNER, "name": "Utente sintetico",
        "settings": {"timezone": TIMEZONE}, "preferences": {"place_monitoring_enabled": False}})
    await db.life_places.insert_one(LifePlace(id=PLACE["id"], user_id=OWNER,
        label=PLACE["label"], locality="Tarquinia", coordinates=Coordinates(
            latitude=PLACE["latitude"], longitude=PLACE["longitude"])).model_dump())
    require(await db.situations.count_documents({}) == 0, "NEW_SITUATION_WORLD_REQUIRED")


@contextmanager
def isolated_engine(db, probe, started):
    from agent import providers, reasoning
    from agent.capabilities import CapabilityResolver
    from agent.execution import StepExecutor
    from agent.service import AgentService
    from conversation_engine.ai_core import loop, calendar_ahead
    from conversation_engine.ai_core.context_broker import ContextBroker
    from conversation_engine.ai_core.models import ContextFact, Observation
    from conversation_engine.ai_core.tools.registry import ToolRegistry
    from conversation_engine.ai_core.tools.providers import gemini_search
    from delivery import provider as push_provider, reasoning as delivery_reasoning
    import life_orchestration.scheduler as scheduler
    import llm.manager as manager
    import research.service as research_service
    import weather

    require_synthetic_database(db)
    boundary = SituationReadBoundary(probe)
    original_chat, original_tool = manager.ProviderManager.chat, ToolRegistry.execute
    original_step, original_available = StepExecutor.run, CapabilityResolver.available
    original_weather, original_research = weather.forecast_at, research_service.ResearchService.run
    original_search = gemini_search.search
    original_action_dump = reasoning._action_dump

    def action_dump(payload):
        diagnostics = []
        original_info = reasoning.logger.info

        def record_diagnostic(message, *args, **kwargs):
            # Observe only existing code-owned causes. Do not infer a cause
            # from payload length or turn an unavailable choice into a call.
            known = {
                "action context unavailable: prepared_source_missing": "prepared_source_missing",
                "action context unavailable: material_context_exceeds_budget": "material_context_exceeds_budget",
            }
            if isinstance(message, str) and message in known:
                diagnostics.append(known[message])
            return original_info(message, *args, **kwargs)

        with patch.object(reasoning.logger, "info", record_diagnostic):
            result = original_action_dump(payload)
        if len(probe.context_observations) < MAX_DECISION_OBSERVATIONS:
            source = json.dumps(payload, ensure_ascii=False, default=str)
            probe.context_observations.append({"stage": "choose_next_action", "available": result is not None,
                "input_characters": len(source), "model_input_characters": len(result) if result is not None else None,
                "input_sha256": hashlib.sha256(source.encode()).hexdigest(),
                "unavailable_reason": diagnostics[-1] if diagnostics else None,
                "input": safe_text(source, 9000), "input_truncated": len(source) > 9000})
        return result

    async def live_chat(self, *args, **kwargs):
        probe.reserve_model("manager")
        before = probe.model_http
        token, result, error = boundary.scope.set("model"), None, None
        try:
            result = await original_chat(self, *args, **kwargs)
            require(probe.model_http > before, "MODEL_HTTP_NOT_OBSERVED")
            name = str(result.provider)
            probe.model_calls.append({"provider": name if name in _MODEL_NAMES else "unknown",
                "model": safe_text(result.model, 100), "stage": _STAGE.get()})
            return result
        except BaseException as exc:
            error = exc
            raise
        finally:
            boundary.scope.reset(token)
            probe.observe_model(kwargs.get("system", ""), kwargs.get("user", ""), result, error)

    async def grounded_search(*args, **kwargs):
        probe.reserve_model("grounded_search")
        token = boundary.scope.set("grounded_search")
        try:
            return await original_search(*args, **kwargs)
        finally:
            boundary.scope.reset(token)

    async def scoped_weather(*args, **kwargs):
        token = boundary.scope.set("weather")
        try:
            return await original_weather(*args, **kwargs)
        finally:
            boundary.scope.reset(token)

    async def research(self, owner, need, **kwargs):
        # Both foreground cognition and the Agent use this same research
        # service. One scope covers either entry, retaining the original path.
        require(self.db is db and owner == OWNER, "RESEARCH_OWNER_BOUNDARY")
        first = len(boundary.reads)
        token = boundary.scope.set("research")
        try:
            result = await original_research(self, owner, need, **kwargs)
            if len(probe.research_reads) < 12:
                probe.research_reads.append({"run_id": result.id, "status": result.status,
                    "http_refs": [row["id"] for row in boundary.reads[first:]
                                  if row["provider"] in ("tavily", "brave", "gemini_search")]})
            return result
        finally:
            boundary.scope.reset(token)

    async def available(self, owner_id):
        require(self.db is db and owner_id == OWNER, "CAPABILITY_OWNER_BOUNDARY")
        # Preserve actual resolution/status; do not fabricate available_real.
        return [row for row in await original_available(self, owner_id)
                if row.get("capability") in READ_CAPABILITIES]

    async def context(self, **kwargs):
        return [ContextFact(statement=(f"Luogo salvato dalla persona sintetica: Tarquinia; "
            f"ref place:{PLACE['id']}. Il punto è una fixture pubblica, non una posizione di un dispositivo reale."),
            source="synthetic_declared_place", authority="user_stated", status="known",
            ref="place:" + PLACE["id"])]

    async def tool(self, capability, arguments, *, runtime=None):
        spec = self.get(capability)
        allowed = self.db is db and spec is not None and capability in LOCAL_TOOLS | EXTERNAL_TOOLS
        if not allowed:
            probe.blocked.append("TOOL_EFFECT_OR_OWNER_BOUNDARY")
            return Observation(kind="tool", name=str(capability), status="failed", payload={
                "status": "failed", "failure_code": "EVAL_ISOLATION_BOUNDARY", "retryable": False})
        token = boundary.scope.set("research" if capability == "web_search" else "blocked")
        try:
            observation = await original_tool(self, capability, arguments, runtime={
                "db": db, "user_id": OWNER, "platform": "web"})
        finally:
            boundary.scope.reset(token)
        if len(probe.tools) < 20:
            recorded = {"capability": capability, "status": observation.status,
                        "production_handler_used": True}
            if capability in ("get_weather_forecast", "schedule_situation_check"):
                encoded = json.dumps(observation.payload, ensure_ascii=False, default=str)
                clean = json.dumps(redact_report(json.loads(encoded)), ensure_ascii=False)
                recorded.update(payload=observed_json(observation.payload, 6000),
                    payload_characters=len(encoded), payload_redacted_characters=len(clean),
                    payload_truncated=len(clean) > 6000, payload_redacted=clean != encoded)
            probe.tools.append(recorded)
        return observation

    async def step(self, owner, goal, item, **kwargs):
        if (self.db is not db or owner != OWNER or goal.owner_id != OWNER
                or item.step_type == "execute" or item.capability_needed not in READ_CAPABILITIES):
            probe.blocked.append("STEP_EFFECT_OR_OWNER_BOUNDARY")
            raise EvaluationFailure("STEP_EFFECT_OR_OWNER_BOUNDARY")
        first = len(boundary.reads)
        result = await original_step(self, owner, goal, item, **kwargs)
        if len(probe.steps) < 12:
            probe.steps.append({"id": item.id, "capability": item.capability_needed,
                "type": item.step_type, "status": result.status, "error_type": safe_text(result.error_type, 80),
                "http_refs": [row["id"] for row in boundary.reads[first:]],
                "source_refs": list(result.provenance.source_refs or [])[:8]})
        return result

    def observed(fn, stage):
        async def wrapped(*args, **kwargs):
            token = _STAGE.set(stage)
            try:
                return await fn(*args, **kwargs)
            finally:
                _STAGE.reset(token)
        return wrapped

    with ExitStack() as stack:
        # Same mongomock-only compatibility shim used by the existing autonomy
        # runner: real Mongo does not re-find the changed row by its OLD filter.
        from mongomock.collection import Collection
        original_update = Collection.find_one_and_update

        def projected_claim(self, *args, **kwargs):
            projection = kwargs.get("projection")
            hide_id = isinstance(projection, dict) and projection.get("_id") == 0
            if hide_id:
                kwargs["projection"] = {key: value for key, value in projection.items() if key != "_id"} or None
            result = original_update(self, *args, **kwargs)
            if result is not None and hide_id:
                result.pop("_id", None)
            return result

        stack.enter_context(patch.object(Collection, "find_one_and_update", projected_claim))
        # Only this opt-in process is changed; no ambient loop is launched.
        stack.enter_context(patch.dict(os.environ, {"AMBIENT_RUNTIME": "1", "ORA_ORCHESTRATION_ENABLED": "0"}))
        if probe.mode == "scripted":
            stack.enter_context(patch.dict(os.environ, {"WEATHER_PROVIDER": "open_meteo", "RESEARCH_ENABLED": "1",
                "TAVILY_API_KEY": "synthetic-unused-search-key", "BRAVE_API_KEY": "", "BRAVE_SEARCH_API_KEY": "",
                "GEMINI_SEARCH_ENABLED": "0"}))
            stack.enter_context(patch.object(manager, "get_manager", lambda: ScriptedModel(probe, started)))
        else:
            stack.enter_context(patch.object(manager.ProviderManager, "chat", live_chat))
        boundary.install(stack)
        stack.enter_context(patch.object(ContextBroker, "retrieve", context))
        stack.enter_context(patch.object(ToolRegistry, "execute", tool))
        stack.enter_context(patch.object(StepExecutor, "run", step))
        stack.enter_context(patch.object(reasoning, "_action_dump", action_dump))
        stack.enter_context(patch.object(CapabilityResolver, "available", available))
        stack.enter_context(patch.object(weather, "forecast_at", scoped_weather))
        stack.enter_context(patch.object(research_service.ResearchService, "run", research))
        stack.enter_context(patch.object(gemini_search, "search", grounded_search))
        stack.enter_context(patch.object(push_provider, "get_provider", lambda: BlockedNotification(probe)))
        stack.enter_context(patch.object(scheduler, "schedule_user_reasoning", AsyncMock(return_value=False)))
        stack.enter_context(patch.object(calendar_ahead, "the_next_two_days", AsyncMock(return_value=None)))
        stack.enter_context(patch.object(loop, "report_activity", AsyncMock()))
        stack.enter_context(patch.object(loop, "_ensure_navigation", AsyncMock(return_value="")))
        for name in ("make_plan", "choose_next_action", "verify_goal", "reconsider", "decide_visibility"):
            stack.enter_context(patch.object(reasoning, name, observed(getattr(reasoning, name), name)))
        stack.enter_context(patch.object(delivery_reasoning, "decide_delivery",
            observed(delivery_reasoning.decide_delivery, "decide_delivery")))
        for name, stage in (("plan_research", "research_plan"), ("assess_evidence", "research_assess"),
                            ("synthesize", "research_synthesize"), ("consider_reuse", "research_reuse")):
            stack.enter_context(patch.object(research_service, name, observed(getattr(research_service, name), stage)))
        yield boundary


async def admission_snapshot(db, sid, goal_id):
    """Read the actual owned admission before asserting the probe's contract.

    The conversation may have replaced the initial wake with a real scheduled
    check on the same goal. Preserve both states of that handoff in diagnostics;
    no observation here creates, repairs or reschedules work.
    """
    from agent.service import AgentService
    from situations.followup import INITIAL_KIND, read_followup
    from situations.repository import SituationRepository

    source = await SituationRepository(db).get(OWNER, sid)
    goal = await AgentService(db).repo.get_goal(OWNER, goal_id)
    followup = await read_followup(db, OWNER, sid)
    wakes = await db.ambient_wakes.find({"owner_id": OWNER, "source_ref": "goal:" + goal_id},
        {"_id": 0, "id": 1, "owner_id": 1, "source_ref": 1, "status": 1, "scheduled_for": 1}
    ).sort("scheduled_for", -1).limit(9).to_list(9)
    check_at = followup.get("assessment_at") if goal and goal.source_kind == INITIAL_KIND else followup.get("next_check_at")
    wake = next((row for row in wakes[:8] if row.get("status") == "pending"
                 and moment(row.get("scheduled_for")) == moment(check_at)), None)
    return {
        "owner_id": OWNER, "situation_id": sid, "goal_id": goal_id,
        "situation": ({key: getattr(source, key) for key in ("id", "user_id", "status", "revision",
            "attention_intent", "next_check_summary")} if source else None),
        "goal": ({key: getattr(goal, key) for key in ("id", "owner_id", "status", "source_kind",
            "source_refs", "source_situation", "desired_outcome", "next_run_at")} if goal else None),
        "follow_up": {key: followup.get(key) for key in ("status", "situation_id", "goal_id", "goal_source_kind",
            "next_check_at", "assessment_at", "last_checked_at", "desired_outcome", "completion_when", "notify_when")},
        "wake": wake, "wakes": wakes[:8], "wakes_truncated": len(wakes) > 8,
    }


def admission_route(state):
    """Recognise an owned current intent; a saved time is not an outcome."""
    from situations.followup import INITIAL_KIND, KIND, OPEN

    source, goal, followup = state.get("situation") or {}, state.get("goal") or {}, state.get("follow_up") or {}
    binding, wake = goal.get("source_situation") or {}, state.get("wake") or {}
    sid, gid = state["situation_id"], state["goal_id"]
    require(goal.get("id") == gid and goal.get("owner_id") == OWNER
            and goal.get("source_kind") in (INITIAL_KIND, KIND) and goal.get("status") in OPEN,
            "INITIAL_REVIEW_NOT_ADMITTED")
    require(source.get("id") == sid and source.get("user_id") == OWNER
            and source.get("status") in ("active", "changed")
            and (source.get("attention_intent") or source.get("next_check_summary"))
            and binding.get("situation_id") == sid
            and binding.get("situation_revision") == str(source.get("revision"))
            and "situation:" + sid in (goal.get("source_refs") or []),
            "SITUATION_ADMISSION_SOURCE_MISMATCH")
    initial = goal["source_kind"] == INITIAL_KIND
    check_at = moment(followup.get("assessment_at" if initial else "next_check_at"))
    due = moment(goal.get("next_run_at"))
    require(followup.get("situation_id") == sid and followup.get("goal_id") == gid
            and followup.get("goal_source_kind") == goal["source_kind"]
            and followup.get("status") in (("review_pending",) if initial else ("scheduled", "due"))
            and check_at is not None and due is not None and check_at >= due
            and wake.get("owner_id") == OWNER and wake.get("source_ref") == "goal:" + gid
            and wake.get("status") == "pending" and moment(wake.get("scheduled_for")) == check_at,
            "INITIAL_WAKE_MISSING_OR_INVALID")
    return "initial_review" if initial else "conversation_scheduled"


async def wait_for_initial_wake(db, goal_id, *, deadline, wake_id=None):
    """Wait for the persisted instant, never rewrite it or advance a clock."""
    while True:
        query = {"owner_id": OWNER, "source_ref": "goal:" + goal_id, "status": "pending"}
        if wake_id is not None:
            query["id"] = wake_id
        row = await db.ambient_wakes.find_one(query, {"_id": 0}, sort=[("scheduled_for", 1)])
        require(row and moment(row.get("scheduled_for")), "INITIAL_WAKE_MISSING_OR_INVALID")
        due = moment(row["scheduled_for"])
        delay = max(0.0, (due - now()).total_seconds())
        if delay == 0:
            return row
        if delay >= deadline - time.monotonic():
            return None
        await asyncio.sleep(min(delay, 45.0))


async def snapshot(db, goal_id, sid, boundary):
    from agent.evidence import EvidenceStore
    from agent.service import AgentService
    from situations.followup import read_followup
    from situations.outcomes import current_outcome, weather_evidence_current
    service = AgentService(db)
    goal = await service.repo.get_goal(OWNER, goal_id)
    # The production store handles superseded rows and the Mongo TTL datetime;
    # re-parsing raw database documents would conflate TTL and evidence fields.
    evidence = await EvidenceStore(db).for_goal(OWNER, goal_id, limit=30)
    weather = [item for item in evidence if item.provenance.capability == "weather.read"]
    current = await current_outcome(db, OWNER, goal, allow_settled=True)
    live_http = [row for row in boundary.reads if row["provider"] == "open_meteo" and row.get("http_status") == 200
                 and _time_valid(row, "get_weather_forecast", now())]
    weather_current = bool(weather) and await weather_evidence_current(db, OWNER, goal, weather)
    followup = await read_followup(db, OWNER, sid)
    saved = await db.ambient_wakes.find({"owner_id": OWNER, "source_ref": "goal:" + goal_id,
        "status": {"$in": ["pending", "claimed"]}}, {"_id": 0}).limit(4).to_list(4)
    research = await db.research_runs.find({"user_id": OWNER}, {"_id": 0}).limit(3).to_list(3)
    needs = await db.agent_needs.find({"owner_id": OWNER, "goal_id": goal_id}, {"_id": 0}).limit(6).to_list(6)
    plans = await db.delivery_plans.find({"owner_id": OWNER}, {"_id": 0}).limit(6).to_list(6)
    return {"goal_id": goal.id, "goal_status": goal.status, "goal_source_kind": goal.source_kind,
        "source_revision": goal.source_situation.get("situation_revision"),
        "next_run_at": goal.next_run_at, "background_runs": goal.background_runs,
        "weather_http_current": bool(live_http), "weather_binding_current": bool(weather_current),
        "outcome": current, "follow_up": observed_json(followup),
        "future_wakes": [{key: row.get(key) for key in ("id", "reason", "source_ref", "status", "scheduled_for")} for row in saved],
        "research_http_runs": [row["run_id"] for row in boundary.probe.research_reads
            if any(http["id"] in row["http_refs"] and http.get("http_status") == 200 for http in boundary.reads)],
        "evidence": [{"id": item.id, "claim": safe_text(item.claim, 600), "bears_on": safe_text(item.supports, 300),
                      "provider": safe_text(item.provenance.provider, 60),
                      "observed_at": item.observed_at, "provenance": item.provenance.for_ai()} for item in evidence],
        "research": [{"id": row.get("id"), "status": row.get("status"), "valid_until": row.get("valid_until"),
                      "plan": observed_json(row.get("plan")), "assessments": observed_json(row.get("assessments")),
                      "synthesis": observed_json(row.get("synthesis")),
                      "sources": [{"id": source.get("source_id"), "url": public_url(source.get("url")),
                                   "title": safe_text(source.get("title"), 200), "snippet": safe_text(source.get("snippet"), 600),
                                   "snippet_origin": source.get("snippet_origin", "unknown"),
                                   "snippet_characters": len(source.get("snippet") or ""),
                                   "snippet_truncated": len(source.get("snippet") or "") > 600,
                                   "retrieved_at": source.get("retrieved_at")} for source in row.get("sources", [])[:24]]}
                     for row in research],
        "needs": [{key: row.get(key) for key in ("id", "kind", "status", "summary", "reason", "source_refs", "valid_until",
                    "delivery_review_state", "delivery_review_due")} for row in needs],
        "delivery_plans": [{key: row.get(key) for key in ("id", "source_type", "source_id", "mode", "status", "words", "not_after")} for row in plans]}


def assess_monitoring(state):
    reasons = []
    if not state.get("weather_http_current") or not state.get("weather_binding_current"):
        reasons.append("CURRENT_BOUND_WEATHER_NOT_OBSERVED")
    outcome = state.get("outcome") or {}
    if outcome.get("status") != "estimated":
        reasons.append("GROUNDED_ESTIMATE_NOT_RECORDED")
    if outcome.get("basis") != "estimate":
        reasons.append("ESTIMATE_BASIS_REQUIRED")
    due = moment(state.get("next_run_at"))
    expiry = moment(outcome.get("valid_until"))
    if not due or not expiry or not now() < due < expiry:
        reasons.append("FUTURE_CHECK_BEFORE_EXPIRY_NOT_RECORDED")
    if not any(row.get("source_ref") == "goal:" + str(state.get("goal_id"))
               and row.get("scheduled_for") == state.get("next_run_at")
               for row in state.get("future_wakes", [])):
        reasons.append("DURABLE_FUTURE_WAKE_NOT_RECORDED")
    # Source appropriateness is not inferred from the mere existence of a run.
    # current_outcome validated cited sufficiency/expiry/owner/revision. Keep
    # the actual snippets and inference in the report for independent review.
    cited = set(outcome.get("evidence_ids") or [])
    empirical = [row for row in state.get("evidence", []) if row.get("id") in cited
                 and (row.get("provenance") or {}).get("capability") == "web.research"
                 and (row.get("provenance") or {}).get("research_sufficient") is True]
    if not empirical:
        reasons.append("CITED_EMPIRICAL_RESEARCH_NOT_VALIDATED")
    if empirical and any(not set(row["provenance"].get("source_refs") or []) & set(state.get("research_http_runs") or [])
                         for row in empirical):
        reasons.append("CITED_RESEARCH_HTTP_NOT_OBSERVED")
    return {"status": "passed" if not reasons else "failed", "reasons": reasons,
            "semantic_appropriateness": "pending_human_review"}


async def cancel_test(db, sid, goal_id):
    from situations.admission import ensure_initial_review
    from situations.models import SituationUpdate
    from situations.repository import SituationRepository
    from situations.service import SituationService
    state = await SituationRepository(db).get(OWNER, sid)
    result = await SituationService(db).apply(user_id=OWNER, session_id="situation-eval-stop",
        reasoning_epoch="situation-eval-cancel", update=SituationUpdate(operation="cancel",
            situation_id=sid, expected_revision=state.revision,
            summary="La prova sintetica è annullata; nessuna affermazione sullo stato fisico dei panni."))
    before = await db.agent_goals.count_documents({"owner_id": OWNER})
    replay = await ensure_initial_review(db, OWNER, sid)
    pending = await db.ambient_wakes.count_documents({"owner_id": OWNER, "source_ref": "goal:" + goal_id,
        "status": {"$in": ["pending", "claimed"]}})
    closed = await db.agent_goals.find_one({"owner_id": OWNER, "id": goal_id})
    passed = (result.get("status") == "success" and replay.get("status") == "no_attention"
              and pending == 0 and closed.get("status") in ("cancelled", "completed")
              and await db.agent_goals.count_documents({"owner_id": OWNER}) == before)
    return {"status": "passed" if passed else "failed", "pending_wakes": pending,
            "replay_admission": replay.get("status"), "physical_collection_claimed": False}


async def run_case(*, mode="scripted"):
    require(mode in ("scripted", "live"), "UNKNOWN_MODE")
    from mongomock_motor import AsyncMongoMockClient
    from agent.service import AgentService
    from ambient.runtime import tick
    from conversation_engine.ai_core import loop
    from conversation_engine.models import ConversationSession
    from situations.followup import goal_id_for
    from situations.repository import SituationRepository
    import llm.manager as manager
    import research.service as research_service
    import weather

    started, deadline = now(), time.monotonic() + CASE_TIMEOUT_SECONDS
    db = AsyncMongoMockClient()["ora_situation_eval_" + hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:16]]
    probe, sid, gid = Probe(mode), None, None
    report = {"version": VERSION, "case": CASE, "mode": mode, "code_revision": code_revision(),
        "started_at": started.isoformat(), "fixture_started_at": started.isoformat(),
        "owner": "new_synthetic_owner_in_memory_only", "place": "Tarquinia", "timezone": TIMEZONE,
        "physical_clock_advanced": False, "process_restart_tested": False,
        "limits": {"case_seconds": CASE_TIMEOUT_SECONDS, "logical_model_calls": MAX_MODEL_CALLS,
                   "model_http_requests": MAX_MODEL_HTTP_REQUESTS, "provider_reads": MAX_PROVIDER_READS},
        "phases": {key: {"status": "not_run"} for key in (
            "conversation", "initial_worker", "monitoring", "future_check", "useful_action", "device_receipt", "cancellation")},
        "semantic_review": {"status": "not_run", "automatically_accepted": False},
        "passed": False, "overall_outcome": "not_run"}
    await seed_world(db, started)
    await AgentService(db).ensure_indexes()
    await db.ambient_wakes.create_index("identity", unique=True,
        partialFilterExpression={"status": {"$in": ["pending", "claimed"]}})
    with isolated_engine(db, probe, started) as boundary:
        report["capabilities"] = {"weather_available": bool(weather.capabilities().get("available")),
            "research_available": research_service.research_available(),
            "configuration_presence_is_not_provider_success": True}
        try:
            if mode == "live":
                require(any(os.environ.get(key, "").strip() for key in _KEY_NAMES[:6]), "MODEL_NOT_CONFIGURED")
                require(weather.configured_provider() == "open_meteo" and report["capabilities"]["weather_available"],
                        "WEATHER_NOT_CONFIGURED")

            async def cycle():
                nonlocal sid, gid
                session = ConversationSession(user_id=OWNER, meta={"ui_mode": "ai_core", "ai_core": {}})

                async def decision(system, user):
                    token = _STAGE.set("conversation")
                    try:
                        response = await manager.get_manager().chat(system=system, user=user,
                            json_mode=True, latency_budget_s=18.0)
                        return loop._parse_json(response.text)
                    finally:
                        _STAGE.reset(token)

                report["phases"]["conversation"] = {"status": "running"}
                response = await loop.run_cognitive_loop(sess=session, user_message=scenario_message(started),
                    db=db, decision_fn=decision, max_steps=7)
                report["conversation_answer"] = safe_text(response.ora_text, 5000)
                require(response.ok, "CONVERSATION_NOT_OK")
                situations = await db.situations.find({"user_id": OWNER}, {"_id": 0}).limit(3).to_list(3)
                require(len(situations) == 1, "EXACTLY_ONE_NEW_SITUATION_REQUIRED")
                state = situations[0]
                sid, gid = state["id"], goal_id_for(OWNER, state["id"])
                report["situation_before_worker"] = (await SituationRepository(db).get(OWNER, sid)).context_preview()
                admission = await admission_snapshot(db, sid, gid)
                report["admission_before_worker"] = admission
                require(state.get("status") in ("active", "changed") and state.get("desired_outcome")
                        and "place:" + PLACE["id"] in state.get("linked_object_refs", [])
                        and moment(state.get("started_at"))
                        and abs((moment(state["started_at"]) - started).total_seconds()) <= 60,
                        "DECLARATION_PLACE_OR_START_NOT_PRESERVED")
                route = admission_route(admission)
                report["entry_route"] = route
                report["phases"]["conversation"] = {"status": "passed", "situation_id": sid, "goal_id": gid}
                initial = await wait_for_initial_wake(db, gid, deadline=deadline, wake_id=admission["wake"]["id"])
                if initial is None:
                    report["overall_outcome"] = (
                        "followup_pending_unobserved" if route == "conversation_scheduled" else "initial_check_pending")
                    return
                report["initial_wake"] = {key: initial.get(key) for key in ("id", "scheduled_for", "source_ref")}
                report["initial_dispatch_at"] = now().isoformat()
                report["phases"]["initial_worker"] = {"status": "running"}
                result = await tick(db, limit=1)
                report["initial_tick"] = result
                require(result.get("claimed") == 1 and result.get("failed") == 0, "INITIAL_WORKER_NOT_HANDLED")
                report["phases"]["initial_worker"] = {"status": "passed"}
                state = await snapshot(db, gid, sid, boundary)
                report["state_after_initial_worker"] = state
                report["phases"]["monitoring"] = assess_monitoring(state)
                report["semantic_review"]["status"] = "pending_human_review"
                if (state.get("outcome") or {}).get("status") == "action_now":
                    report["phases"]["useful_action"] = {"status": "observed_pending_human_review",
                        "action_reason": state["outcome"].get("action_reason"), "physical_state_measured": False}
                    report["overall_outcome"] = "action_assessment_requires_review"
                elif report["phases"]["monitoring"]["status"] == "passed":
                    report["overall_outcome"] = "followup_pending"
                    report["passed"] = True  # only the declared first-cycle monitoring contract
                else:
                    report["overall_outcome"] = "monitoring_failed"
                    unavailable = [row["unavailable_reason"] for row in probe.context_observations
                                   if not row["available"] and row.get("unavailable_reason")]
                    if unavailable:
                        report["diagnosis"] = unavailable[-1]

            await asyncio.wait_for(cycle(), timeout=max(0.01, deadline - time.monotonic()))
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit, asyncio.CancelledError)):
                raise
            report.update(passed=False, overall_outcome="failed",
                error=str(exc) if isinstance(exc, EvaluationFailure) else type(exc).__name__[:80])
            for phase in report["phases"].values():
                if phase.get("status") == "running":
                    phase["status"] = "failed"
            report["error_location"] = [{"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
                                        for frame in traceback.extract_tb(exc.__traceback__)[-4:]]
            from pydantic import ValidationError
            if isinstance(exc, ValidationError):
                report["validation_fields"] = [{"location": list(row["loc"]), "type": row["type"]}
                    for row in exc.errors(include_url=False, include_context=False, include_input=False)[:6]]
        finally:
            if sid and gid:
                try:
                    report["phases"]["cancellation"] = await cancel_test(db, sid, gid)
                    if report["phases"]["cancellation"]["status"] != "passed":
                        report["passed"] = False
                except Exception as exc:
                    report["phases"]["cancellation"] = {"status": "failed", "error_type": type(exc).__name__[:80]}
                    report["passed"] = False
            if probe.blocked:
                report["passed"] = False
            report.update(completed_at=now().isoformat(), real_model_attempted=probe.logical_calls > 0,
                real_model_executed=bool(probe.model_calls),
                model_calls=probe.model_calls, logical_model_calls=probe.logical_calls,
                manager_calls=probe.manager_calls, grounded_search_calls=probe.grounded_search_calls,
                model_http_requests=probe.model_http, scripted_model_calls=probe.scripted_calls,
                provider_reads=boundary.reads, live_provider_reads=sum(row["source"] == "live_provider_http" for row in boundary.reads),
                model_observations=probe.decisions, model_observations_omitted=probe.decisions_omitted,
                steps=probe.steps, tools=probe.tools, blocked_operations=probe.blocked,
                context_observations=probe.context_observations,
                research_reads=probe.research_reads,
                intercepted_notification_attempts=probe.push_attempts, real_notifications_sent=0,
                full_laundry_outcome_passed=False, source_appropriateness_accepted=False,
                persistence="in_memory_only_cancelled_after_snapshot",
                isolation="HTTPX_scope_allowlist_not_process_socket_sandbox")
    return redact_report(report)


async def main(*, mode="scripted", output=""):
    report = await run_case(mode=mode)
    encoded = json.dumps(report, ensure_ascii=False, allow_nan=False)
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded + "\n", encoding="utf-8")
    print("ORA_SITUATION_FIRST_CYCLE " + encoded, flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("scripted", "live"), default="scripted")
    parser.add_argument("--output", default="")
    arguments = parser.parse_args()
    raise SystemExit(asyncio.run(main(mode=arguments.mode, output=arguments.output)))
