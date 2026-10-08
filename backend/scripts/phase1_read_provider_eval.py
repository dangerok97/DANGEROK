"""Opt-in Phase 1 route/weather evaluation, using only public test coordinates.

The production cognitive loop, catalogue, LLM manager, location resolution and
route/weather handlers run unchanged. The owner, saved places, consent and GPS
observation are synthetic, in a new in-memory database. No server, worker or
real account is opened. All other external capabilities and research are denied.

    python -m scripts.phase1_read_provider_eval --mode scripted
    python -m scripts.phase1_read_provider_eval --mode live --output /tmp/read-eval.json

Scripted mode uses predetermined decisions AND stubbed provider HTTP responses;
it does not prove live model or provider quality. Live mode needs a configured
LLM key, ROUTING_PROVIDER=google_routes|mapbox, ROUTING_API_KEY, and the default
WEATHER_PROVIDER=open_meteo. There is no implicit live default or scheduler.

A pass means usable, dated provider evidence reached the real loop. The bounded
final answer is retained for human semantic review, which remains a separate
gate. Transport timestamps are labelled separately from production tool payloads.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import json
import logging
import math
import os
from pathlib import Path
from typing import Any, Callable
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from scripts.phase1_cognitive_live_eval import _model_signal

VERSION = "phase1-read-provider-v126"
OWNER = "eval-public-route-weather-only"
FIXTURE_SOURCE = "synthetic_public_landmark_fixture"
TIMEZONE = "Europe/Rome"
ORIGIN = {"id": "eval-roma-termini", "label": "Roma Termini",
          "latitude": 41.9010, "longitude": 12.5018}
DESTINATION = {"id": "eval-colosseo", "label": "Colosseo",
               "latitude": 41.8902, "longitude": 12.4922}
REQUIRED_READS = frozenset({"get_route", "get_weather_forecast"})
LOCAL_READS = frozenset({
    "list_life_places", "get_life_place", "get_current_location",
    "get_current_presence", "get_recent_presence_context", "search_life_memory",
    "get_profile_snapshot",
})
LLM_KEYS = ("GEMINI_API_KEY", "GEMINI2_API_KEY", "OPENAI_API_KEY",
            "GROQ_API_KEY", "MISTRAL_API_KEY")
FINAL_ANSWER_LIMIT = 5000


class EvaluationBoundaryError(RuntimeError):
    """A disallowed operation; error text deliberately contains no request data."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _positive_number(value: Any) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and value > 0)


def _dated(value: Any, timezone_name: str | None = None) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            if not timezone_name:
                return None
            parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
        return parsed
    except (TypeError, ValueError, KeyError):
        return None


def _safe_text(value: Any, limit: int) -> str:
    text = str(value or "")
    for name in (*LLM_KEYS, "ROUTING_API_KEY", "WEATHER_API_KEY"):
        secret = os.environ.get(name) or ""
        if len(secret) >= 8:
            text = text.replace(secret, "[credential redacted]")
    return text[:limit]


def _scenario_message(now: datetime) -> str:
    local = now.astimezone(ZoneInfo(TIMEZONE))
    return (
        f"Oggi, {local.date().isoformat()}, alle {local:%H:%M} (Europe/Rome), "
        "devo valutare un tragitto in auto con partenza adesso da Roma Termini "
        "al Colosseo, entrambi già salvati tra i miei luoghi. La posizione "
        "corrente autorizzata è Roma Termini. Verifica il tempo di viaggio con "
        "il traffico attuale e il meteo al Colosseo nelle prossime ore. "
        "Dimmi cosa hai verificato, la durata stimata e cosa suggerisci per "
        "questo spostamento oggi, distinguendo previsioni da certezze. "
        "Non avviare la navigazione, creare appuntamenti, impostare notifiche, "
        "inviare messaggi o spendere denaro. Questo è un utente sintetico di "
        "valutazione: i due punti sono monumenti pubblici, non luoghi privati."
    )


async def _seed_world(db, now: datetime) -> None:
    from location.models import LocationSignal
    from location.place_label import PLACE_RESOLVER_VERSION
    from places.models import Coordinates, LifePlace

    await db.users.insert_one({
        "id": OWNER, "user_id": OWNER, "name": "Utente sintetico",
        "settings": {"location_mode": "while_using", "timezone": TIMEZONE},
        "preferences": {"place_monitoring_enabled": False},
    })
    for point in (ORIGIN, DESTINATION):
        await db.life_places.insert_one(LifePlace(
            id=point["id"], user_id=OWNER, label=point["label"], locality="Roma",
            coordinates=Coordinates(latitude=point["latitude"], longitude=point["longitude"]),
        ).model_dump())
    # Direct fixture insertion avoids geocoding, opportunity wake-ups and any
    # claim that a real device supplied or consented to this coordinate.
    await db.location_signals.insert_one(LocationSignal(
        id="eval-public-location", user_id=OWNER, timestamp=now.isoformat(),
        latitude=ORIGIN["latitude"], longitude=ORIGIN["longitude"],
        accuracy_meters=15, source="foreground_device", freshness="CURRENT",
        permission_state="granted_foreground", place_label=ORIGIN["label"],
        place_locality="Roma", place_municipality="Roma", place_country="Italia",
        place_resolver_version=PLACE_RESOLVER_VERSION,
        expires_at=now + timedelta(hours=1),
    ).model_dump())


def _scripted_reply(request):
    """Stub HTTP, never stub the production weather/routing handlers."""
    import httpx

    if request.url.host == "api.open-meteo.com":
        now = _now().astimezone(ZoneInfo(TIMEZONE)).replace(second=0, microsecond=0)
        hour = now.replace(minute=0)
        times = [(hour + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M")
                 for i in range(15)]
        data = {
            "timezone": TIMEZONE, "utc_offset_seconds": int(now.utcoffset().total_seconds()),
            "current": {"time": now.strftime("%Y-%m-%dT%H:%M"),
                        "temperature_2m": 21, "apparent_temperature": 20,
                        "relative_humidity_2m": 55, "wind_speed_10m": 12,
                        "precipitation": 0, "weather_code": 2},
            "hourly": {"time": times, "temperature_2m": [21] * 15,
                       "relative_humidity_2m": [55] * 15,
                       "wind_speed_10m": [12] * 15,
                       "precipitation_probability": [10] * 15,
                       "weather_code": [2] * 15},
            "daily": {"time": [now.date().isoformat()], "weather_code": [2],
                      "temperature_2m_max": [23], "temperature_2m_min": [15],
                      "precipitation_probability_max": [10],
                      "sunrise": [now.strftime("%Y-%m-%dT07:10")],
                      "sunset": [now.strftime("%Y-%m-%dT18:40")]},
        }
    elif request.url.host == "routes.googleapis.com":
        data = {"routes": [{"duration": "900s", "staticDuration": "720s",
                            "distanceMeters": 3800}]}
    elif request.url.host == "api.mapbox.com":
        data = {"code": "Ok", "routes": [{"duration": 900, "distance": 3800,
                                           "duration_typical": 720, "legs": []}]}
    else:
        raise EvaluationBoundaryError("EVAL_HTTP_NOT_ALLOWLISTED")
    return httpx.Response(200, json=data, request=request)


def _llm_endpoint(request) -> bool:
    if request.method != "POST" or request.url.scheme != "https":
        return False
    host, path = request.url.host, request.url.path
    return (
        (host == "generativelanguage.googleapis.com" and path.startswith("/v1beta/models/")
         and path.endswith(":generateContent"))
        or (host == "api.openai.com" and path == "/v1/chat/completions")
        or (host == "api.groq.com" and path == "/openai/v1/chat/completions")
        or (host == "api.mistral.ai" and path == "/v1/chat/completions")
    )


def _provider_endpoint(request, capability: str) -> str | None:
    """Exact read endpoints and fixed public coordinates only; never log URLs."""
    if request.url.scheme != "https":
        return None
    host, path = request.url.host, request.url.path
    if capability == "get_weather_forecast" and request.method == "GET":
        if host != "api.open-meteo.com" or path != "/v1/forecast":
            return None
        try:
            pair = (float(request.url.params["latitude"]), float(request.url.params["longitude"]))
            if pair in {(point["latitude"], point["longitude"])
                        for point in (ORIGIN, DESTINATION)}:
                return "open_meteo"
        except (KeyError, TypeError, ValueError):
            return None
    if capability == "get_route":
        if (host == "routes.googleapis.com" and path == "/directions/v2:computeRoutes"
                and request.method == "POST"):
            try:
                body = json.loads(request.content)
                points = [body[key]["location"]["latLng"] for key in ("origin", "destination")]
                expected = [{key: point[key] for key in ("latitude", "longitude")}
                            for point in (ORIGIN, DESTINATION)]
                if (points == expected and body.get("travelMode") == "DRIVE"
                        and body.get("routingPreference") == "TRAFFIC_AWARE"):
                    return "google_routes"
            except (KeyError, TypeError, ValueError):
                return None
        coords = ";".join(f"{point['longitude']:.6f},{point['latitude']:.6f}"
                          for point in (ORIGIN, DESTINATION))
        if (host == "api.mapbox.com" and request.method == "GET"
                and path == "/directions/v5/mapbox/driving-traffic/" + coords):
            return "mapbox"
    return None


def _http_evidence(provider: str, response, started: datetime, received: datetime) -> dict:
    evidence = {
        "provider": provider, "http_status": response.status_code,
        "request_started_at": started.isoformat(), "received_at": received.isoformat(),
        "retrieval_time_source": "evaluation_clock_not_provider_observation_time",
        "metadata_added_to_model_observation": False,
    }
    if provider == "open_meteo" and response.status_code == 200:
        try:
            data = response.json()
            evidence["provider_timezone"] = _safe_text(data.get("timezone"), 60)
            evidence["provider_current_time"] = _safe_text((data.get("current") or {}).get("time"), 45)
            offset = data.get("utc_offset_seconds")
            evidence["provider_utc_offset_seconds"] = (
                offset if isinstance(offset, (int, float)) and not isinstance(offset, bool) else None
            )
            current = _dated(evidence["provider_current_time"], evidence["provider_timezone"])
            evidence["provider_hour_times"] = [
                _safe_text(value, 45) for value in (data.get("hourly") or {}).get("time", [])
                if (point := _dated(value, evidence["provider_timezone"]))
                and current and point >= current
            ][:12]
        except (TypeError, ValueError, AttributeError):
            evidence["provider_metadata_invalid"] = True
    return evidence


class _ReadBoundary:
    def __init__(self, *, model_live: bool, provider_reply: Callable | None):
        self.model_live = model_live
        self.provider_reply = provider_reply
        self.source = "stubbed_provider_http" if provider_reply else "live_provider_http"
        self.scope: ContextVar[str] = ContextVar("phase1_read_scope", default="blocked")
        self.reads: list[dict] = []
        self.blocked: list[str] = []

    def install(self, stack: ExitStack) -> None:
        import httpx

        original_send = httpx.AsyncClient.send
        original_init = httpx.AsyncClient.__init__

        def checked_init(client, *args, **kwargs):
            # Offline fixtures do not need a network proxy (or optional SOCKS
            # packages). Live provider/model requests keep deployment settings.
            if self.provider_reply and self.scope.get() != "model":
                kwargs["trust_env"] = False
            original_init(client, *args, **kwargs)

        async def checked_send(client, request, **kwargs):
            scope = self.scope.get()
            if scope == "model" and self.model_live and _llm_endpoint(request):
                # Provider-manager requests carry the synthetic prompt only.
                # Do not allow an allowlisted endpoint to redirect elsewhere.
                return await original_send(client, request, **{**kwargs, "follow_redirects": False})
            provider = _provider_endpoint(request, scope)
            if provider is None or len(self.reads) >= 12:
                self.blocked.append("EVAL_HTTP_NOT_ALLOWLISTED")
                raise EvaluationBoundaryError("EVAL_HTTP_NOT_ALLOWLISTED")
            started = _now()
            row = {"id": f"http:{len(self.reads) + 1}", "capability": scope,
                   "source": self.source, "provider": provider}
            self.reads.append(row)
            try:
                if self.provider_reply:
                    response = self.provider_reply(request)
                    if hasattr(response, "__await__"):
                        response = await response
                else:
                    response = await original_send(
                        client, request, **{**kwargs, "follow_redirects": False}
                    )
                row.update(_http_evidence(provider, response, started, _now()))
                return response
            except Exception as exc:
                row.update({"http_status": None, "error_type": type(exc).__name__[:70],
                            "request_started_at": started.isoformat(), "received_at": _now().isoformat()})
                raise

        stack.enter_context(patch.object(httpx.AsyncClient, "send", checked_send))
        stack.enter_context(patch.object(httpx.AsyncClient, "__init__", checked_init))


def _time_valid(evidence: dict, capability: str, evaluation_now: datetime) -> bool:
    started = _dated(evidence.get("request_started_at"))
    received = _dated(evidence.get("received_at"))
    if not started or not received or not (0 <= (received - started).total_seconds() <= 60):
        return False
    if not (-5 <= (evaluation_now - received).total_seconds() <= 300):
        return False
    if capability != "get_weather_forecast":
        return True
    timezone_name = str(evidence.get("provider_timezone") or "")
    current = _dated(evidence.get("provider_current_time"), timezone_name)
    if timezone_name != TIMEZONE or not current:
        return False
    offset = evidence.get("provider_utc_offset_seconds")
    if offset is not None and offset != current.utcoffset().total_seconds():
        return False
    if not (-300 <= (received - current).total_seconds() <= 7200):
        return False
    future = [_dated(value, timezone_name) for value in evidence.get("provider_hour_times", [])]
    return any(point and 0 <= (point - current).total_seconds() <= 7200 for point in future)


def _payload_view(capability: str, payload: dict) -> dict:
    keys = ("status", "available", "provider", "destination", "travel_mode",
            "duration_seconds", "distance_meters", "reflects_current_traffic",
            "duration_without_traffic_seconds", "failure_code", "retryable",
            "why_unavailable", "error", "place", "current", "hours", "sunrise", "sunset",
            "observed_at", "retrieved_at", "timezone", "utc_offset_seconds")
    return {key: payload[key] for key in keys if key in payload} if capability in REQUIRED_READS else {
        "status": payload.get("status"), "synthetic_local_read": True,
    }


def _verdict(result, decisions: list[dict], observations: list[dict], reads: list[dict],
             blocked: list[str], *, now: datetime | None = None) -> dict:
    now = now or _now()
    verified = []
    reasons = []
    for capability in sorted(REQUIRED_READS):
        valid = False
        for observation in observations:
            if observation.get("capability") != capability:
                continue
            payload = observation.get("payload") or {}
            matches = [row for row in reads if row["id"] in observation.get("http_refs", [])
                       and row.get("capability") == capability and row.get("http_status") == 200]
            usable = (observation.get("outer_status") == "ok" and payload.get("status") == "ok"
                      and observation.get("production_handler_used") is True
                      and observation.get("session_readback_verified") is True)
            if capability == "get_route":
                usable = (usable and payload.get("available") is True
                          and _positive_number(payload.get("duration_seconds"))
                          and _positive_number(payload.get("distance_meters"))
                          and payload.get("reflects_current_traffic") is True
                          and payload.get("provider") in ("google_routes", "mapbox"))
                matches = [row for row in matches if row.get("provider") == payload.get("provider")]
            else:
                current = payload.get("current") or {}
                temp = current.get("temperature_c")
                usable = (usable and isinstance(temp, (int, float)) and not isinstance(temp, bool)
                          and math.isfinite(temp) and -100 <= temp <= 60
                          and bool(current.get("condition")) and bool(payload.get("hours")))
                # The dated weather facts must reach the model as well as the
                # transport audit. HH:MM alone cannot identify a forecast day.
                usable = (usable and payload.get("provider") == "open_meteo"
                          and payload.get("timezone") == TIMEZONE
                          and _dated(payload.get("retrieved_at")) is not None
                          and bool(payload.get("observed_at"))
                          and all(_dated(row.get("datetime"), TIMEZONE)
                                  for row in payload.get("hours", [])))
                retrieved = _dated(payload.get("retrieved_at"))
                matches = [row for row in matches
                           if row.get("provider_current_time") == payload.get("observed_at")
                           and row.get("provider_timezone") == payload.get("timezone")
                           and retrieved and (received := _dated(row.get("received_at")))
                           and 0 <= (retrieved - received).total_seconds() <= 10
                           and any(hour.get("datetime") in row.get("provider_hour_times", [])
                                   for hour in payload.get("hours", []))]
            if usable and any(_time_valid(row, capability, now) for row in matches):
                valid = True
        if valid:
            verified.append(capability)
        else:
            reasons.append("missing_usable_dated_provider_read:" + capability)
    if not result or not result.ok:
        reasons.append("cognitive_loop_not_ok")
    if getattr(result, "error", None):
        reasons.append("cognitive_loop_incomplete:" + str(result.error)[:65])
    if not decisions:
        reasons.append("no_model_decisions")
    if not str(getattr(result, "ora_text", "") or "").strip():
        reasons.append("no_final_answer_for_review")
    if blocked or any(row.get("source") == "blocked" for row in observations):
        reasons.append("isolation_boundary_attempted")
    return {
        "passed": not reasons, "reasons": reasons, "verified_reads": verified,
        "required_reads": sorted(REQUIRED_READS), "model_decisions": len(decisions),
        "ai_calls": int(getattr(result, "ai_calls", 0) or 0),
        "tool_calls": int(getattr(result, "tool_calls", 0) or 0),
        "elapsed_ms": int(getattr(result, "elapsed_ms", 0) or 0),
        "final_mode": str(getattr(result, "mode", "") or "")[:30],
        "semantic_acceptance": "pending_human_review",
    }


async def _scripted_model_factory():
    calls = 0

    async def decide(_system: str, _user: str) -> dict:
        nonlocal calls
        calls += 1
        if calls <= 2:
            cap = "get_route" if calls == 1 else "get_weather_forecast"
            decision = {
                "response_mode": "tool", "reasoning_status": "needs_tool",
                "tool_call": {"capability": cap, "arguments": (
                    {"destination": DESTINATION["label"], "travel_mode": "drive"}
                    if calls == 1 else {"place_ref": "place:" + DESTINATION["id"]}
                )}, "situation_update": {"operation": "none"},
            }
            if calls == 1:
                decision["skill_plan"] = {
                    "objective": "Verificare tragitto e meteo per la partenza adesso",
                    "required_capabilities": sorted(REQUIRED_READS),
                }
            return decision
        return {
            "response_mode": "answer", "reasoning_status": "enough_information",
            "message_to_user": (
                "Nel controllo con dati HTTP sintetici il tragitto dura 15 minuti "
                "per 3,8 km e il meteo indica 21 °C. Questa risposta prestabilita "
                "verifica il percorso tecnico; non dimostra ragionamento di un modello live."
            ), "situation_update": {"operation": "none"},
        }
    return decide


async def run_case(*, mode: str = "scripted", decide: Callable | None = None,
                   max_steps: int = 7, provider_reply: Callable | None = None) -> dict:
    """One isolated vertical. Optional decision/HTTP injection is labelled scripted."""
    if mode not in ("scripted", "live"):
        raise ValueError("unknown_mode")
    from mongomock_motor import AsyncMongoMockClient
    from conversation_engine.ai_core.context_broker import ContextBroker
    from conversation_engine.ai_core.models import ContextFact, Observation
    from conversation_engine.ai_core.tools.registry import ToolRegistry
    from conversation_engine.ai_core import loop as cognitive_loop
    from conversation_engine.models import ConversationSession
    import conversation_engine.ai_core.calendar_ahead as calendar_ahead
    import research.service as research_service
    import life_orchestration.scheduler as scheduler
    import situations.followup as situation_followup
    from situations.turn_followup import FollowupTurnGate

    now = _now()
    db = AsyncMongoMockClient().ora_phase1_public_provider_eval
    await _seed_world(db, now)
    sess = ConversationSession(user_id=OWNER, meta={"ui_mode": "ai_core", "ai_core": {}})
    model_live = mode == "live" and decide is None
    boundary = _ReadBoundary(
        model_live=model_live,
        provider_reply=provider_reply or (_scripted_reply if mode == "scripted" else None),
    )
    if not model_live and decide is None:
        decide = await _scripted_model_factory()
    decisions: list[dict] = []
    observations: list[dict] = []
    originals: list[dict] = []
    llm_calls: list[dict] = []
    error_types: list[str] = []
    context = [ContextFact(
        statement=f"Luogo pubblico sintetico confermato: {point['label']}, Roma; "
                  f"coordinate di prova {point['latitude']}, {point['longitude']}; "
                  f"ref place:{point['id']}.",
        source=FIXTURE_SOURCE, authority="user_stated", status="known",
        ref="place:" + point["id"],
    ) for point in (ORIGIN, DESTINATION)]

    async def synthetic_context(self, **_kwargs):
        return list(context)

    original_execute = ToolRegistry.execute

    async def isolated_execute(self, capability, arguments, *, runtime=None):
        spec = self.get(capability)
        allowed = (self.db is db and spec is not None and spec.side_effect == "READ_ONLY"
                   and capability in REQUIRED_READS | LOCAL_READS)
        before = len(boundary.reads)
        if allowed:
            token = boundary.scope.set(capability)
            try:
                obs = await original_execute(self, capability, arguments, runtime={
                    "db": db, "user_id": OWNER, "session_id": sess.id, "platform": "web",
                })
            finally:
                boundary.scope.reset(token)
            source = boundary.source if capability in REQUIRED_READS else "synthetic_db_read"
        else:
            source = "blocked"
            obs = Observation(kind="tool", name=str(capability), status="failed", payload={
                "status": "failed", "failure_code": "EVAL_ISOLATION_BOUNDARY",
                "retryable": False,
            })
        originals.append(obs.model_dump())
        observations.append({
            "capability": str(capability)[:90], "source": source,
            "side_effect": getattr(spec, "side_effect", "unknown"),
            "outer_status": obs.status, "production_handler_used": allowed,
            "handler": (f"{spec.handler.__module__}.{spec.handler.__name__}"
                        if allowed and hasattr(spec.handler, "__name__") else None),
            "payload": _payload_view(capability, obs.payload or {}),
            "provenance": list(obs.provenance or [])[:10],
            "http_refs": [row["id"] for row in boundary.reads[before:]],
        })
        return obs

    async def decision(system: str, user: str):
        try:
            if model_live:
                from llm.manager import get_manager
                token = boundary.scope.set("model")
                try:
                    response = await get_manager().chat(
                        system=system, user=user, json_mode=True, latency_budget_s=18.0,
                    )
                finally:
                    boundary.scope.reset(token)
                llm_calls.append({"provider": str(response.provider)[:50],
                                  "model": str(response.model)[:100]})
                raw = cognitive_loop._parse_json(str(response.text or ""))
            else:
                raw = await decide(system, user)
            if not isinstance(raw, dict):
                raise ValueError("INVALID_MODEL_JSON")
            decisions.append(_model_signal(raw))
            return raw
        except Exception as exc:
            error_types.append(type(exc).__name__[:70])
            raise

    with ExitStack() as stack:
        if mode == "scripted":
            stack.enter_context(patch.dict(os.environ, {
                "ROUTING_PROVIDER": "google_routes", "ROUTING_API_KEY": "synthetic-unused-key",
                "WEATHER_PROVIDER": "open_meteo",
            }))
        stack.enter_context(patch.dict(os.environ, {"AI_CORE_TRACE": "1"}))
        boundary.install(stack)
        stack.enter_context(patch.object(ToolRegistry, "execute", isolated_execute))
        stack.enter_context(patch.object(ContextBroker, "retrieve", synthetic_context))
        stack.enter_context(patch.object(calendar_ahead, "the_next_two_days", AsyncMock(return_value=None)))
        stack.enter_context(patch.object(FollowupTurnGate, "refresh", AsyncMock(return_value=None)))
        stack.enter_context(patch.object(situation_followup, "_enabled", lambda: False))
        stack.enter_context(patch.object(scheduler, "schedule_user_reasoning", AsyncMock(return_value=False)))
        stack.enter_context(patch.object(research_service, "research_available", lambda: False))
        stack.enter_context(patch.object(cognitive_loop, "report_activity", AsyncMock()))
        # This separate, deterministic handoff can call open_navigation directly,
        # outside ToolRegistry. Navigation is explicitly outside this read test.
        stack.enter_context(patch.object(cognitive_loop, "_ensure_navigation", AsyncMock(return_value="")))
        result = await cognitive_loop.run_cognitive_loop(
            sess=sess, user_message=_scenario_message(now), db=db,
            decision_fn=decision, max_steps=max(1, min(8, max_steps)),
        )

    saved = (sess.meta.get("ai_core") or {}).get("observations") or []
    for row, original in zip(observations, originals):
        row["session_readback_verified"] = any(
            item.get("name") == original["name"]
            and item.get("status") == original["status"]
            and item.get("payload") == original["payload"]
            and item.get("provenance") == original["provenance"]
            for item in saved if isinstance(item, dict)
        )
    verdict = _verdict(result, decisions, observations, boundary.reads, boundary.blocked)
    final = str(getattr(result, "ora_text", "") or "")
    return {
        "version": VERSION, "case": "trip_today", "requested_mode": mode,
        "model_mode": "live_llm" if model_live else "scripted_decisions",
        "provider_mode": boundary.source, "real_model_executed": bool(model_live and llm_calls),
        "live_provider_reads": sum(row.get("http_status") == 200 and row["source"] == "live_provider_http"
                                   for row in boundary.reads),
        "owner": "synthetic_isolated_no_real_account", "fixture_source": FIXTURE_SOURCE,
        "synthetic_state": ["account", "consent", "current_location", "saved_public_places", "memory_database"],
        "public_points": [dict(ORIGIN), dict(DESTINATION)],
        "scenario_time": now.astimezone(ZoneInfo(TIMEZONE)).isoformat(),
        "scenario_message": _scenario_message(now), "verdict": verdict,
        "decisions": decisions[:12], "model_calls": llm_calls[:12],
        "observations": observations[:20], "http_reads": boundary.reads[:12],
        "blocked_operations": boundary.blocked[:12], "error_types": error_types[:12],
        "final_answer": _safe_text(final, FINAL_ANSWER_LIMIT),
        "final_answer_truncated": len(final) > FINAL_ANSWER_LIMIT,
        "semantic_review": {
            "status": "required", "automatically_accepted": False,
            "check": "Compare final prose, dates, travel duration and weather with recorded evidence.",
            "time_metadata_limit": "Weather provider dates/timezone must reach the model; route retrieval time is the evaluation clock, not a provider as-of timestamp.",
        },
    }


def _preflight() -> list[str]:
    reasons = []
    if not any(os.environ.get(name) for name in LLM_KEYS):
        reasons.append("live_llm_credentials_unavailable")
    if ((os.environ.get("ROUTING_PROVIDER") or "").strip().lower() not in ("google_routes", "mapbox")
            or not os.environ.get("ROUTING_API_KEY")):
        reasons.append("live_routing_configuration_unavailable")
    if (os.environ.get("WEATHER_PROVIDER") or "open_meteo").strip().lower() != "open_meteo":
        reasons.append("open_meteo_required_for_this_evaluation")
    return reasons


async def main(mode: str, max_steps: int = 7, output: str | None = None) -> int:
    reasons = _preflight() if mode == "live" else []
    if reasons:
        result = {"version": VERSION, "requested_mode": mode, "real_model_executed": False,
                  "verdict": {"passed": False, "reasons": reasons}}
        exit_code = 3
    else:
        try:
            result = await asyncio.wait_for(run_case(mode=mode, max_steps=max_steps), timeout=210)
            exit_code = 0 if result["verdict"]["passed"] else 1
        except Exception as exc:
            result = {"version": VERSION, "requested_mode": mode,
                      "verdict": {"passed": False, "reasons": ["runner_error:" + type(exc).__name__[:70]]}}
            exit_code = 1
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(serialized + "\n", encoding="utf-8")
    print("ORA_PHASE1_READ_EVAL " + json.dumps(result, ensure_ascii=False), flush=True)
    return exit_code


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("scripted", "live"), default="scripted")
    parser.add_argument("--max-steps", type=int, default=7)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.mode, max(1, min(8, args.max_steps)), args.output or None)))
