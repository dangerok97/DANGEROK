"""Bounded agentic reasoning loop — AI decides; tools/context observe."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from conversation_engine.ai_core.context_broker import (
    ContextBroker,
    context_payload_stats,
)
from conversation_engine.ai_core.context_sources import GRAPH_MAX_DEPTH
from conversation_engine.ai_core.fallback import (
    fallback_decision_after_malformed,
    provider_unavailable_result,
)
from conversation_engine.ai_core.governance import (
    clarification_ref_key,
    validate_decision,
    whole_sentences,
)
from conversation_engine.ai_core.grounding.temporal import merge_context_with_current
from conversation_engine.ai_core.models import (
    ActiveGoal,
    CognitiveDecision,
    CognitiveTurnResult,
    ContextFact,
    MissingInformation,
    Observation,
    UncertaintyState,
)
from conversation_engine.ai_core.prompt import (
    COGNITIVE_SYSTEM_PROMPT,
    build_user_payload,
)
from conversation_engine.ai_core import state as state_mod
from conversation_engine.ai_core.tools.registry import (
    ToolRegistry,
    new_reasoning_epoch,
    tool_signature,
)
from conversation_engine.ai_core.trace import add_step, new_trace, public_trace
from conversation_engine.models import ConversationSession, now_iso
from life_signals import emitters as life_signals

logger = logging.getLogger("ora.ai_core.loop")

MAX_STEPS = 8
MAX_TOOL_CALLS = 5
MAX_EXTERNAL_QUERIES = 2
# How many times in one turn ORA may go and research something. A ceiling
# on cost, not a view about how much research a question deserves — the
# run itself decides when it has enough.
MAX_RESEARCH_RUNS = 2
# How many decisions may be worked through in one turn. A ceiling on cost, not
# a view about how much a choice deserves.
MAX_COMPARISON_RUNS = 1
MAX_CONTEXT_CALLS = 2
MAX_WRITE_CALLS = 4
MAX_OBJECT_GENERATIONS = 2
MAX_SOURCES_UI = 5

_CALENDAR_WRITE_CAPS = frozenset(
    {"create_calendar_event", "update_calendar_event", "cancel_calendar_event"}
)
_WRITE_CAPS = frozenset(
    {
        "create_plan",
        "update_plan",
        "create_actions",
        "create_object",
        "update_object",
        "record_object_interaction",
        "mark_plan_progress",
        "note_intention",
        *_CALENDAR_WRITE_CAPS,
    }
)
# Durable Life OS objects — note_intention alone does NOT satisfy persist-before-claim.
_LIFE_OS_PERSIST_CAPS = frozenset(
    {
        "create_plan",
        "update_plan",
        "create_actions",
        "create_object",
        "update_object",
        "mark_plan_progress",
    }
)

def _effective_capability(
    requested_cap: str, observed_name: str, allowed_caps
) -> str:
    """Return the concrete effect capability when a wrapper owns the lifecycle.

    The AI may call a continuation skill, while the observation is emitted by
    the leaf capability that actually changed the world. Truth guards must
    credit the leaf observation rather than the wrapper name.
    """
    observed = str(observed_name or "").strip()
    requested = str(requested_cap or "").strip()
    if observed in allowed_caps:
        return observed
    if requested in allowed_caps:
        return requested
    return ""


def _calendar_write_observation_succeeded(
    requested_cap: str, obs: Observation
) -> bool:
    effective = _effective_capability(
        requested_cap, getattr(obs, "name", ""), _CALENDAR_WRITE_CAPS
    )
    return bool(
        effective
        and obs.status == "ok"
        and (obs.payload or {}).get("status") == "ok"
    )


def _merge_required_skill_caps(current: List[str], incoming) -> List[str]:
    """Keep the AI's declared requirements for the whole reasoning turn.

    Requirements are capability names chosen by the model from the live
    catalogue. Code never infers a domain or adds a capability on its own.
    """
    out = list(current or [])
    for cap in incoming or []:
        name = str(cap or "").strip()
        if name and name not in out:
            out.append(name)
    return out[:MAX_TOOL_CALLS]


def _pending_required_skill_caps(
    required: List[str], attempted: Set[str]
) -> List[str]:
    return [cap for cap in required if cap not in (attempted or set())]


def _has_empirical_estimate_evidence(observations) -> bool:
    """True only when the estimate has external research or a direct estimator."""
    for obs in reversed(list(observations or [])):
        if isinstance(obs, dict):
            kind = str(obs.get("kind") or "")
            name = str(obs.get("name") or "")
            status = str(obs.get("status") or "")
        else:
            kind = str(getattr(obs, "kind", "") or "")
            name = str(getattr(obs, "name", "") or "")
            status = str(getattr(obs, "status", "") or "")
        if kind == "research" and status == "ok":
            return True
        if name in _DIRECT_EMPIRICAL_ESTIMATE_CAPS and status == "ok":
            return True
    return False


def _record_skill_attempt(
    attempted: Set[str], requested_cap: str, observed_name: str
) -> Set[str]:
    out = set(attempted or set())
    requested = str(requested_cap or "").strip()
    observed = str(observed_name or "").strip()
    if requested:
        out.add(requested)
    if observed:
        out.add(observed)
    return out


def _skill_outcome_summary(
    requested_cap: str, observation
) -> Dict[str, str]:
    """Sanitised capability result for cross-turn planning — no tool payload."""
    if isinstance(observation, dict):
        observed = str(observation.get("name") or "").strip()
        status = str(observation.get("status") or "").strip()
        payload = observation.get("payload") or {}
    else:
        observed = str(getattr(observation, "name", "") or "").strip()
        status = str(getattr(observation, "status", "") or "").strip()
        payload = getattr(observation, "payload", None) or {}
    payload = payload if isinstance(payload, dict) else {}
    return {
        "capability": str(requested_cap or "").strip()[:120],
        "observed_capability": observed[:120],
        "status": status[:40],
        "result_status": str(payload.get("status") or "")[:60],
        "failure_kind": str(
            payload.get("failure_kind")
            or payload.get("failure_code")
            or ((payload.get("external") or {}).get("failure_code") if isinstance(payload.get("external"), dict) else "")
            or ""
        )[:100],
    }


def _merge_skill_outcomes(current, incoming) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for raw in [*(current or []), *(incoming or [])]:
        if not isinstance(raw, dict):
            continue
        item = {
            "capability": str(raw.get("capability") or "")[:120],
            "observed_capability": str(raw.get("observed_capability") or "")[:120],
            "status": str(raw.get("status") or "")[:40],
            "result_status": str(raw.get("result_status") or "")[:60],
            "failure_kind": str(raw.get("failure_kind") or "")[:100],
        }
        if not item["capability"] and not item["observed_capability"]:
            continue
        key = (
            item["capability"],
            item["observed_capability"],
            item["status"],
            item["result_status"],
            item["failure_kind"],
        )
        if key not in {
            (
                x["capability"], x["observed_capability"], x["status"],
                x["result_status"], x["failure_kind"]
            )
            for x in out
        }:
            out.append(item)
    return out[-12:]


def _words(value: str) -> str:
    return " ".join(str(value or "").split()).casefold()


def _apply_skill_plan_releases(
    required: List[str],
    releases,
    observations,
    *,
    persisted_outcomes=None,
    user_message: str = "",
) -> tuple[List[str], List[str], List[str]]:
    """Apply only explicit plan revisions grounded in real evidence/user words."""
    remaining = list(required or [])
    observed_names: Set[str] = set()
    for obs in observations or []:
        if isinstance(obs, dict):
            name = str(obs.get("name") or "").strip()
        else:
            name = str(getattr(obs, "name", "") or "").strip()
        if name:
            observed_names.add(name)
    for item in persisted_outcomes or []:
        if not isinstance(item, dict):
            continue
        for key in ("capability", "observed_capability"):
            name = str(item.get(key) or "").strip()
            if name:
                observed_names.add(name)

    spoken = _words(user_message)
    released: List[str] = []
    rejected: List[str] = []
    for release in releases or []:
        cap = str(getattr(release, "capability", "") or "").strip()
        basis = str(getattr(release, "basis", "") or "").strip()
        evidence = str(
            getattr(release, "observation_capability", "") or ""
        ).strip()
        quote = str(getattr(release, "user_instruction_quote", "") or "").strip()
        if not cap or cap not in remaining:
            if cap:
                rejected.append(cap)
            continue
        if basis == "observation":
            if not evidence or evidence not in observed_names:
                rejected.append(cap)
                continue
        elif basis == "user_message":
            if not quote or _words(quote) not in spoken:
                rejected.append(cap)
                continue
        else:
            rejected.append(cap)
            continue
        remaining = [name for name in remaining if name != cap]
        released.append(cap)
    return remaining, released, rejected


def _active_skill_plan_state(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Sanitised persisted execution-plan metadata, never tool arguments."""
    raw = state.get("active_skill_plan")
    if not isinstance(raw, dict):
        return None
    plan_ref = str(raw.get("plan_ref") or "").strip()[:80]
    objective = str(raw.get("objective") or "").strip()[:320]
    if not plan_ref or not objective:
        return None
    required = []
    for cap in raw.get("required_capabilities") or []:
        name = str(cap or "").strip()
        if name and name not in required:
            required.append(name)
    attempted = []
    for cap in raw.get("attempted_capabilities") or []:
        name = str(cap or "").strip()
        if name and name not in attempted:
            attempted.append(name)
    outcomes = _merge_skill_outcomes([], raw.get("capability_outcomes") or [])
    required = required[:MAX_TOOL_CALLS]
    attempted = attempted[: MAX_TOOL_CALLS * 2]
    return {
        "plan_ref": plan_ref,
        "objective": objective,
        "required_capabilities": required,
        "attempted_capabilities": attempted,
        "capability_outcomes": outcomes,
        "pending_capabilities": _pending_required_skill_caps(
            required, set(attempted)
        ),
        "waiting": bool(raw.get("waiting")),
        "updated_at": str(raw.get("updated_at") or "")[:80],
    }


def _persist_active_skill_plan(
    state: Dict[str, Any],
    *,
    objective: str,
    required: List[str],
    attempted: Set[str],
    outcomes=None,
    existing_ref: Optional[str] = None,
    waiting: bool = True,
) -> Dict[str, Any]:
    """Persist only orchestration metadata needed to resume a paused chain."""
    plan_ref = str(existing_ref or "").strip()[:80]
    if not plan_ref:
        plan_ref = f"skillplan_{uuid.uuid4().hex[:12]}"
    doc = {
        "plan_ref": plan_ref,
        "objective": str(objective or "").strip()[:320] or "Completare la richiesta",
        "required_capabilities": list(required or [])[:MAX_TOOL_CALLS],
        "attempted_capabilities": sorted(set(attempted or set()))[: MAX_TOOL_CALLS * 2],
        "capability_outcomes": _merge_skill_outcomes([], outcomes or []),
        "waiting": bool(waiting),
        "updated_at": now_iso(),
    }
    state["active_skill_plan"] = doc
    return doc


def _clear_active_skill_plan(
    state: Dict[str, Any], *, expected_ref: Optional[str] = None
) -> None:
    current = _active_skill_plan_state(state)
    if expected_ref and current and current.get("plan_ref") != expected_ref:
        return
    state["active_skill_plan"] = None


_USER_WAIT_STATUSES = frozenset(
    {
        "authority_required",
        "confirmation_required",
        "user_confirmation_required",
        "needs_user_input",
        "consent_required",
        "awaiting_confirmation",
    }
)


def _observations_wait_for_user(observations) -> bool:
    """Generic pause detector based on capability contract fields, not domains."""
    for obs in reversed(list(observations or [])):
        payload = getattr(obs, "payload", None)
        status = getattr(obs, "status", None)
        if isinstance(obs, dict):
            payload = obs.get("payload")
            status = obs.get("status")
        payload = payload if isinstance(payload, dict) else {}
        pstatus = str(payload.get("status") or "").strip().lower()
        failure = str(payload.get("failure_kind") or "").strip().lower()
        if isinstance(payload.get("confirmation_request"), dict):
            return True
        if pstatus in _USER_WAIT_STATUSES or failure in _USER_WAIT_STATUSES:
            return True
        if str(status or "").lower() in ("consent_required",):
            return True
    return False


async def _emit_life_change(
    trace: Dict[str, Any],
    source_system: str,
    emit: Callable[[], Awaitable[Any]],
    user_id: str = "",
) -> None:
    """Record a LifeChangeSignal for a mutation that is ALREADY persisted
    (V2.9.1).

    Failure isolation: the primary mutation has already committed by the time
    this runs, so a signal-layer failure must never propagate — the user's real
    life state is correct and only the derived event is lost. The failure stays
    observable via the `life_change_signal_failures` trace counter instead of
    being silently swallowed. This never mutates a life entity and never emits
    a second signal, so there is no signal → mutation → signal recursion.
    """
    try:
        result = await emit()
    except Exception as e:
        trace["life_change_signal_failures"] = int(
            trace.get("life_change_signal_failures") or 0
        ) + 1
        logger.warning(
            "life_change_signal emit failed source_system=%s error=%s",
            source_system,
            type(e).__name__,
        )
        return
    emitted = len(result) if isinstance(result, list) else (1 if result else 0)
    if emitted:
        trace["life_change_signals"] = int(trace.get("life_change_signals") or 0) + emitted
        # V2.9.4: something really changed, so ask for a bounded reasoning pass
        # for this user. Best-effort by design — it never blocks or fails this
        # turn, and if the wake-up is dropped the signal is still pending in
        # Mongo for a later pass. This is the ONLY place the pipeline is
        # triggered from the request path: no change means no wake-up, which
        # means no AI cost.
        try:
            from life_orchestration.scheduler import schedule_user_reasoning

            await schedule_user_reasoning(user_id, reason="signal")
        except Exception as e:
            logger.info("orchestration schedule soft-fail: %s", type(e).__name__)


# Soft re-entry when the model narrates durable Life OS writes without observations.
_PERSIST_CLAIM_RE = re.compile(
    r"(?i)\b("
    r"ho\s+(creato|impostato|organizzato|preparato|generato|salvato)|"
    r"piano\s+(è|e)\s+pronto|piano\s+di\s+\d+|"
    r"ti\s+ho\s+preparato|materiale\s+per\s+oggi|"
    r"ho\s+fatto\s+un\s+piano|"
    r"i('|\u2019)?ve\s+(created|set\s+up|prepared|generated)|"
    r"here\s+is\s+(your|the)\s+(plan|material|session)"
    r")\b"
)
_DURABLE_MEMORY_CLAIM_RE = re.compile(
    r"(?i)\b(ho\s+memorizzato|ho\s+salvato\s+(in\s+)?memoria|"
    r"ho\s+preso\s+nota|terrò\s+presente\s+(in\s+futuro|d'ora\s+in\s+poi)|"
    r"ho\s+dimenticato|ho\s+rimosso\s+(dalla\s+)?memoria|"
    r"ho\s+rimosso\b.{0,100}\bmemorizzat[oa]|"
    r"i('|’)?ve\s+memorized|saved\s+(it\s+)?to\s+memory|"
    r"i('|’)?ve\s+forgotten|removed\s+(it\s+)?from\s+memory|"
    r"i('ll|\s+will)\s+remember\s+(it|that)\s+(in\s+the\s+future|going\s+forward))\b"
)
_GRAPH_LINK_CLAIM_RE = re.compile(
    r"(?i)\b(ho\s+collegat[oi]|li\s+ho\s+collegati|ho\s+associat[oi]|"
    r"ho\s+creato\s+(un\s+)?collegamento|ho\s+messo\s+in\s+relazione|"
    r"i('|’)?ve\s+linked|i('|’)?ve\s+connected|"
    r"i('|’)?ve\s+related)\b"
)
_CALENDAR_ABSENCE_CLAIM_RE = re.compile(
    r"(?i)\b("
    r"non\s+c(?:'|’|i\s+)?e\s+nessun.{0,80}(evento|impegno)|"
    r"non\s+esiste.{0,80}(evento|impegno)?|"
    r"non\s+ho\s+trovato.{0,100}(evento|impegno|calendario)|"
    r"nessun.{0,80}(evento|impegno).{0,40}(calendario)|"
    r"there\s+is\s+no.{0,80}(event|appointment)|"
    r"no.{0,80}(event|appointment).{0,40}(calendar)|"
    r"i\s+couldn.?t\s+find.{0,80}(event|appointment)"
    r")\b"
)


_CALENDAR_CLAIM_RE = re.compile(
    r"(?i)\b("
    r"ho\s+(creato|aggiunto|inserito|messo|spostato|riprogrammato|cancellato|"
    r"eliminato|rimosso)\b.{0,60}\bcalendario|"
    r"(l'|lo\s+)?ho\s+(spostato|riprogrammato|cancellato|eliminato)\b.{0,40}\b(evento|impegno)|"
    r"aggiunto\s+al\s+(tuo\s+)?calendario|"
    r"i('|’)?ve\s+(created|added|scheduled|moved|rescheduled|cancel(l)?ed|deleted|removed)\b.{0,60}\b(calendar|event)"
    r")\b"
)
_LIKELY_EMPIRICAL_ESTIMATE_RE = re.compile(
    r"(?i)("
    r"\b(circa|indicativamente|all'incirca|approssimativamente|pi[uù]\s+o\s+meno|"
    r"stimo|stimerei|dovrebbe|dovrebbero|probabilmente|verosimilmente|verso)\b"
    r".{0,120}"
    r"(\b\d{1,3}([\.,:]\d{1,2})?\b|"
    r"\b(minut[oi]|or[ae]|giorn[oi]|settiman[ae]|mes[ei]|euro|€|%|"
    r"mattina|pomeriggio|sera|notte)\b)"
    r"|"
    r"(\b\d{1,3}([\.,:]\d{1,2})?\b|"
    r"\b(minut[oi]|or[ae]|giorn[oi]|settiman[ae]|mes[ei]|euro|€|%)\b)"
    r".{0,80}"
    r"\b(circa|indicativamente|approssimativamente|stimato|stimata|previsto|prevista)\b"
    r")"
)

# Direct tools whose returned quantity is itself the operational estimate.
# This is not domain routing: it only names capabilities whose contract directly
# returns an ETA/route estimate. Derived physical/process estimates still need
# research evidence.
_DIRECT_EMPIRICAL_ESTIMATE_CAPS = frozenset(
    {"get_route", "get_journeys_between_places"}
)


_MEMORY_NOT_FOUND_CLAIM_RE = re.compile(
    r"(?i)\b(non\s+ho\s+trovato.{0,120}\bmemoria|"
    r"non\s+c('|’|i\s+)è\s+alcun[ao].{0,100}\bda\s+dimenticare|"
    r"no\s+(matching|specific)\s+memory\s+(was\s+)?found|"
    r"there\s+is\s+nothing.{0,80}\bto\s+forget)\b"
)
# Current-location questions must go through location capabilities (consent bridge).
_LOCATION_NOW_ASK_RE = re.compile(
    r"(?i)\b("
    r"dove\s+sono(\s+adesso)?|"
    r"where\s+am\s+i|"
    r"posizione\s+attuale|"
    r"current\s+location|"
    r"my\s+location\s+now"
    r")\b"
)
_LOCATION_CAPS = frozenset(
    {
        "get_current_location",
        "get_current_presence",
        "get_recent_presence_context",
    }
)

# A direct request to telephone somebody must enter the governed phone
# preparation. Prompt text alone is not an invariant: in production the model
# once answered "I cannot place voice calls" even though the phone capability
# was present and healthy. Keep this deliberately narrow to imperative/request
# forms so questions *about* calling do not start a call.
_PHONE_ACTION_ASK_RE = re.compile(
    r"(?i)\b("
    r"chiama(?:lo|la|li|le|mi|ci)?|"
    r"telefon(?:a|agli|ale|ami|aci)|"
    r"(?:voglio|vorrei|puoi|potresti|devi)\s+che\s+(?:tu\s+)?chiami|"
    r"(?:fai|effettua|prepara)\s+(?:una\s+)?chiamata|"
    r"contatta(?:lo|la|li|le)?\s+(?:per\s+telefono|telefonicamente)|"
    r"call\s+(?:him|her|them|the|my|this)"
    r")\b"
)
_PHONE_CAPABILITY = "prepare_a_phone_call"

# Direct departure commands must end with an actual map handoff. This narrow
# extraction is a terminal safety net when a provider answers "Ok." without
# calling the capability. Questions about routes and durations remain with AI.
_NAVIGATION_COMMAND_RE = re.compile(
    r"(?i)^\s*(?:portami|accompagnami|guidami|naviga|avvia\s+(?:la\s+)?navigazione)"
    r"(?:\s+dalla\s+mia\s+posizione)?\s+(?:a|al|alla|allo|all['’]|il|la|lo|l['’]|verso|fino\s+a)\s+(.+?)\s*[.!?]?\s*$"
)
_ARRIVAL_TAIL_RE = re.compile(
    r"(?i)(?:,\s*(?:devo|voglio)\s+arrivare\s+|\s+)"
    r"(?:(oggi|domani)\s+)?(?:entro\s+le|alle)\s+"
    r"([01]?\d|2[0-3])(?::([0-5]\d))?\s*[.!?]?\s*$"
)


def _arrival_request(message: str) -> dict:
    """Only an explicit time in a direct departure command, never a guess."""
    match = _NAVIGATION_COMMAND_RE.match(message or "")
    tail = _ARRIVAL_TAIL_RE.search(_navigation_subject(match.group(1))) if match else None
    if not tail:
        return {}
    return {"day": (tail.group(1) or "oggi").lower(),
            "hour": int(tail.group(2)), "minute": int(tail.group(3) or 0)}


def _navigation_subject(raw: str) -> str:
    return re.split(
        r"(?i)(?:\s*,?\s+e\s+|\s*,\s*)(?:dimmi|mostrami|indicami|confronta|controlla|verifica|spiegami|fammi\s+sapere)\b",
        raw, maxsplit=1,
    )[0].strip(" ,.!?")


def _navigation_destination(message: str) -> str:
    match = _NAVIGATION_COMMAND_RE.match(message or "")
    if not match:
        return ""
    destination = match.group(1).strip(" .!?")
    # One utterance can ask to be taken somewhere AND ask for the briefing.
    # Keep the place name, but do not pass "e dimmi traffico..." to Maps or
    # a geocoder as if it were part of the address.
    destination = _navigation_subject(destination)
    destination = _ARRIVAL_TAIL_RE.sub("", destination).strip(" ,.!?")
    return re.sub(r"(?i)\s+per\s+favore$", "", destination)[:160]


_NAVIGATION_CONFIRM_RE = re.compile(
    r"(?i)^\s*(?:s[iì]|certo|va\s+bene|vai|procedi|parti|avvia|fallo|"
    r"ok(?:\s+(?:vai|procedi|parti|avvia|fallo))?)\s*[.!?]*\s*$"
)
_NAVIGATION_CANCEL_RE = re.compile(
    r"(?i)^\s*(?:no|annulla|lascia\s+stare|non\s+pi[uù]|fermo|stop)\s*[.!?]*\s*$"
)


def _safe_navigation_options(raw: Any) -> List[Dict[str, str]]:
    """Only code-generated navigation providers may survive into a pending action."""
    from urllib.parse import urlparse

    allowed_hosts = {"www.google.com", "maps.apple.com", "waze.com", "www.waze.com"}
    out: List[Dict[str, str]] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        label = str(item.get("label") or "").strip()
        ident = str(item.get("id") or "").strip()
        try:
            parsed = urlparse(url)
        except ValueError:
            continue
        if parsed.scheme != "https" or parsed.netloc.lower() not in allowed_hosts:
            continue
        if not label:
            continue
        out.append({"id": ident[:32], "label": label[:40], "url": url[:600]})
    return out[:3]


def _remember_pending_navigation(state: Dict[str, Any], observations: Any) -> List[Dict[str, str]]:
    """Persist one verified handoff for the immediate next conversational reply."""
    options = _safe_navigation_options(_navigation_options(observations))
    if options:
        state["pending_navigation"] = {
            "options": options,
            "created_at": _now_iso(),
        }
    return options


def _consume_pending_navigation(
    state: Dict[str, Any], text: str
) -> tuple[str, List[Dict[str, str]]]:
    """Interpret only the immediate reply to a prepared navigation handoff."""
    pending = state.pop("pending_navigation", None)
    if not isinstance(pending, dict):
        return ("none", [])

    options = _safe_navigation_options(pending.get("options"))
    if not options:
        return ("none", [])

    # A stale yes hours later must not launch yesterday's destination.
    try:
        from datetime import datetime, timedelta, timezone
        created = datetime.fromisoformat(str(pending.get("created_at") or ""))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - created > timedelta(minutes=30):
            return ("expired", [])
    except Exception:
        return ("expired", [])

    if _NAVIGATION_CONFIRM_RE.match(text or ""):
        return ("confirm", options)
    if _NAVIGATION_CANCEL_RE.match(text or ""):
        return ("cancel", [])
    # One turn deep by design: another topic invalidates the handoff.
    return ("other", [])


async def _ensure_navigation(observations, turn_start: int, message: str, db, uid: str) -> str:
    """Produce the map link once for an explicit departure, even on model failure."""
    destination = _navigation_destination(message)
    if not destination or db is None or not uid:
        return ""
    current = [o for o in observations[turn_start:] if isinstance(o, dict)
               and o.get("name") == "open_navigation"]
    if current:
        payload = current[-1].get("payload") or {}
    else:
        from places.caps import open_navigation

        obs = await open_navigation(
            {"destination": destination, "arrival_request": _arrival_request(message)},
            {"db": db, "user_id": uid, "platform": "web"},
        )
        observations.append(obs.model_dump())
        payload = obs.payload or {}
    return str(payload.get("say_this") or payload.get("why") or "")



def _spoken_phone_number(text: str) -> str:
    """Extract one complete phone-shaped number without interpreting the words.

    This is normalization, not dialogue understanding. Whether the observed
    number is a correction, a new contact, an example or unrelated information
    is for the cognitive model to decide from the conversation.
    """
    from preparation.contacts import _clean_number

    raw = str(text or "")
    # One contiguous phone-shaped run, allowing ordinary separators. Do not
    # concatenate unrelated digits elsewhere in the sentence.
    candidates = re.findall(
        r"(?<!\d)(?:\+?\d[\s().-]*){9,13}(?!\d)",
        raw,
    )
    normalized = []
    for candidate in candidates:
        clean = _clean_number(candidate.strip())
        if clean and clean not in normalized:
            normalized.append(clean)
    return normalized[0] if len(normalized) == 1 else ""


async def _phone_input_hint(db, user_id: str, state: dict, text: str) -> dict:
    """Bounded mechanical input for an active phone skill.

    No meaning is assigned here. Code may normalize a complete phone number
    from the latest message and bind it to the already-owned preparation id.
    The AI decides whether and how that observation should affect the call.
    """
    from preparation.preparation import by_id

    ref = str(state.get("active_preparation_id") or "")
    if not ref:
        return {}
    prep = await by_id(db, user_id, ref)
    if prep is None or prep.call_id:
        return {}

    number = _spoken_phone_number(text)
    if not number:
        return {}
    return {
        "preparation_id": ref,
        "observed_phone_number": number,
    }


def _phone_action_requested(text: str) -> bool:
    """Whether this turn explicitly asks ORA to make a phone call."""
    return bool(_PHONE_ACTION_ASK_RE.search(text or ""))


def _has_phone_observation(observations: List[Dict[str, Any]]) -> bool:
    """A phone observation proves the request entered the governed flow."""
    return any(
        isinstance(item, dict) and item.get("name") == _PHONE_CAPABILITY
        for item in observations
    )


async def _active_phone_skill_context(db, user_id: str, state: dict) -> dict:
    """Bounded durable phone state for the conversational AI.

    The model gets enough state to continue the same skill, but never carrier
    credentials or hidden implementation details. It decides what the person's
    words mean; the phone capability remains authoritative for validation.
    """
    ref = str(state.get("active_preparation_id") or "")
    if not ref or db is None or not user_id:
        return {}
    try:
        from preparation.preparation import by_id
        from preparation.service import as_a_card

        prep = await by_id(db, user_id, ref)
        if prep is None:
            return {}
        card = as_a_card(prep)
        contact = card.get("contact") or {}
        question = card.get("question") or {}
        return {
            "skill": "phone",
            "capability": _PHONE_CAPABILITY,
            "preparation_id": ref,
            "counterparty": str(card.get("counterparty") or prep.counterparty or "")[:160],
            "operation": str(prep.operation or "")[:40],
            "message_to_deliver": str(prep.message_to_deliver or "")[:300] or None,
            "contact": {
                "name": str(contact.get("name") or "")[:120],
                "number": str(contact.get("number") or "")[:40],
                "source_label": str(contact.get("source_label") or "")[:80],
            } if contact else None,
            "number_confirmed": bool(card.get("number_confirmed")),
            "identity_conflicts": [
                {"name": str(row.get("name") or "")[:120]}
                for row in (card.get("identity_conflicts") or [])[:6]
            ],
            "question": str(question.get("asks") or "")[:300] or None,
            "summary": str(card.get("summary") or "")[:400] or None,
            "ready": bool(card.get("ready")),
            "instruction": (
                "Interpret the latest user message naturally, then continue this "
                "same preparation with prepare_a_phone_call. Do not require magic phrases."
            ),
        }
    except Exception as exc:
        logger.info("active phone skill context soft-fail: %s", type(exc).__name__)
        return {}


def _pending_navigation_skill_context(state: dict) -> dict:
    """AI-visible description of a verified pending navigation handoff."""
    pending = state.get("pending_navigation")
    if not isinstance(pending, dict):
        return {}
    options = _safe_navigation_options(pending.get("options"))
    if not options:
        return {}
    return {
        "skill": "navigation",
        "capability": "continue_navigation",
        "awaiting_user_reply": True,
        "apps": [row["label"] for row in options],
        "created_at": str(pending.get("created_at") or "")[:40],
        "instruction": (
            "Interpret the latest reply. If they want to proceed, call "
            "continue_navigation; if they decline, answer naturally without the skill."
        ),
    }


def _pending_calendar_skill_context(state: dict) -> dict:
    """AI-visible description of a frozen pending calendar confirmation."""
    pending = state.get("pending_act")
    if not isinstance(pending, dict):
        return {}
    request = pending.get("calendar_cancel")
    if not isinstance(request, dict):
        return {}
    question = str(request.get("question") or "")[:300]
    if not question:
        return {}
    return {
        "skill": "calendar",
        "capability": "continue_calendar_action",
        "awaiting_user_reply": True,
        "question": question,
        "created_at": str(pending.get("at") or "")[:40],
        "instruction": (
            "Interpret the latest reply naturally. If it confirms the exact "
            "pending cancellation, call continue_calendar_action. If it declines "
            "or changes the request, do not execute the pending action."
        ),
    }


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _has_terminal_location_obs(observations: List[Dict[str, Any]]) -> bool:
    """True when a location tool already returned a terminal (non-bridge) result."""
    for o in observations:
        if not isinstance(o, dict):
            continue
        if o.get("name") not in _LOCATION_CAPS:
            continue
        if o.get("status") == "needs_client":
            continue
        payload = o.get("payload") or {}
        pstatus = str(payload.get("status") or "")
        if pstatus in (
            "stale",
            "needs_client",
            "consent_required",
            "permission_required",
        ):
            continue
        if payload.get("needs_client") and pstatus not in (
            "ok",
            "denied",
            "unavailable",
            "timeout",
            "error",
        ):
            continue
        return True
    return False


# Claims that saved material was adapted — require update_object observation.
_ADAPT_CLAIM_RE = re.compile(
    r"(?i)\b("
    r"ho\s+(semplificato|aggiornato|riscritto|modificato|ridotto|riorganizzato|accorciato)|"
    r"l('|\u2019)?ho\s+(semplificato|aggiornato|riscritto|modificato)|"
    r"materiale\s+(è|e)\s+(stato\s+)?(aggiornato|semplificato|modificato)|"
    r"oggetto\s+(è|e)\s+(stato\s+)?(aggiornato|semplificato)|"
    r"workspace\s+(è|e)\s+(aggiornato|semplificato)|"
    r"i('|\u2019)?ve\s+(simplified|updated|rewritten|shortened)|"
    r"i\s+simplified|i\s+updated\s+the\s+(material|object|workspace)"
    r")\b"
)

from conversation_engine.ai_core.activity import CAPABILITY_AREAS, report_activity

DecisionFn = Callable[[str, str], Awaitable[Dict[str, Any]]]


async def run_cognitive_loop(
    *,
    sess: ConversationSession,
    user_message: str,
    db=None,
    decision_fn: Optional[DecisionFn] = None,
    max_steps: int = MAX_STEPS,
    resume_client: bool = False,
) -> CognitiveTurnResult:
    t0 = time.perf_counter()
    trace = new_trace()
    #     DOVE VA IL TEMPO, MISURATO — NON IPOTIZZATO.
    # V3.21.3: «la chat è lenta» non è una diagnosi. Queste sono le fasi che un
    # turno attraversa, in millisecondi: contesto, modello, strumenti, guida.
    # Costano un `perf_counter` ciascuna e dicono da dove cominciare.
    fasi: Dict[str, float] = {}

    def _fase(nome: str, da: float) -> None:
        fasi[nome] = round(fasi.get(nome, 0.0) + (time.perf_counter() - da) * 1000, 1)
    tools = ToolRegistry(db)
    broker = ContextBroker(db)
    st = state_mod.get_ai_state(sess)

    # Client-resume continues the SAME user turn — do not duplicate recent_turns.
    if not resume_client:
        state_mod.append_turn(st, role="user", text=user_message)

        # Conversation is AI-first. Pending skill state is exposed below to the
        # cognitive model; deterministic code validates execution, but does not
        # interpret the person's meaning or compose the dialogue before the AI.
        # New user message: allow another foreground refresh after timeout/unavailable.
        if db is not None and sess.user_id:
            try:
                from location.service import LocationService

                await LocationService(db).clear_transient_acquisition_error(
                    sess.user_id
                )
            except Exception:
                pass
    add_step(
        trace,
        event="TURN_RESUME" if resume_client else "TURN",
        user_message=user_message[:200],
    )
    user_llm_preference = await _user_llm_preference(db, sess.user_id)

    _t = time.perf_counter()
    # Baseline account/context loading happens on every turn, not just memory
    # conversations. Keep the map neutral until a meaningful signal exists.
    await report_activity(db, sess, "context")
    context_facts = await broker.retrieve(
        user_id=sess.user_id,
        user_message=user_message,
        active_goal=st.get("active_goal"),
        stage="A",
        session_id=sess.id,
    )
    await report_activity(db, sess, "processing", keep_area=True)
    _fase("context", _t)
    # Merge temporary current_facts (do not overwrite durable Profile)
    context_facts = merge_context_with_current(context_facts, st)
    # Normalize any dict extras from temporal merge
    normalized: List[ContextFact] = []
    for f in context_facts:
        if isinstance(f, ContextFact):
            normalized.append(f)
        elif isinstance(f, dict):
            try:
                normalized.append(ContextFact.model_validate(f))
            except Exception:
                continue
    context_facts = normalized

    trace["context_calls"] = int(trace.get("context_calls") or 0) + 1
    stats_a = context_payload_stats(context_facts)
    trace["context_item_count"] = stats_a["item_count"]
    trace["context_payload_chars"] = stats_a["payload_chars"]
    add_step(
        trace,
        event="CONTEXT_A",
        refs=[f.ref for f in context_facts],
        n=len(context_facts),
        payload_chars=stats_a["payload_chars"],
        sources=[f.source for f in context_facts],
    )

    observations: List[Dict[str, Any]] = list(st.get("observations") or [])
    # Where this turn's observations begin: what came before belongs to turns
    # the person has already read.
    turn_start = len(observations)
    phone_input_hint = await _phone_input_hint(db, sess.user_id, st, user_message)
    # Set only when the turn ends on a question the reasoning called blocking.
    blocking_ask: Optional[Dict[str, Any]] = None
    # What guidance decided to ask, once it had resolved everything it could.
    guidance_ask: Optional[Dict[str, Any]] = None
    # One "you already know this" nudge per turn: a second would be the loop
    # arguing with itself rather than answering the person.
    guidance_nudge_used = False
    # Guidance corrections for this turn. More than one, because the drafts
    # fail differently: the first hands the choice back, the second narrates
    # the plan, and spending the whole budget on the first leaves the second to
    # reach the person. Still bounded well inside MAX_STEPS — the loop must
    # converge, and a fourth attempt is the model arguing with itself rather
    # than helping anyone.
    guidance_nudges_used = 0
    MAX_GUIDANCE_NUDGES = 3
    # The reconstruction carried across turns, so a revision replaces a state
    # rather than inventing one from nothing.
    guidance_state = _guidance_state_from(st)
    # V2.6.2 — mutation idempotency is TURN-SCOPED (reasoning epoch).
    # Session-persisted signatures must NOT ban legitimate cross-turn replanning
    # when the user provides new facts/evidence that change persisted state.
    epoch = str(st.get("reasoning_epoch") or "") if resume_client else ""
    if not epoch:
        epoch = new_reasoning_epoch()
    st["reasoning_epoch"] = epoch
    recent_tool_sigs: Set[str] = set()
    st["turn_tool_signatures"] = []
    turn_obs_by_sig: Dict[str, Dict[str, Any]] = {}
    last_decision: Optional[CognitiveDecision] = None
    ai_calls = 0
    tool_calls = 0
    external_queries = 0
    write_calls = 0
    object_gens = 0
    public_sources: List[Dict[str, str]] = []
    working_hint: Optional[str] = None
    persist_nudge_used = False
    location_nudge_used = False
    phone_nudge_used = False
    life_os_writes_this_turn = 0
    update_object_ok_this_turn = False
    situation_result: Optional[Dict[str, Any]] = None
    situation_plan_nudge_used = False
    linked_plan_pending_id: Optional[str] = None
    linked_plan_reconciled_this_turn = False
    memory_governance_rounds = 0
    memory_write_confirmed_this_turn = False
    memory_write_decisions_this_turn: List[str] = []
    memory_claim_nudge_used = False
    memory_result_nudge_used = False
    graph_write_confirmed_this_turn = False
    graph_claim_nudge_used = False
    calendar_write_confirmed_this_turn = False
    calendar_claim_nudge_used = False
    calendar_absence_nudge_used = False
    bare_ack_nudge_used = False
    required_skill_caps: List[str] = []
    attempted_skill_caps: Set[str] = set()
    skill_outcomes: List[Dict[str, str]] = []
    active_execution_plan = _active_skill_plan_state(st)
    active_execution_plan_ref: Optional[str] = (
        str((active_execution_plan or {}).get("plan_ref") or "") or None
    )
    current_skill_plan_ref: Optional[str] = None
    skill_plan_declared_this_turn = False
    skill_plan_resumed_this_turn = False
    clarification_attempts = {
        str(item.get("key")): int(item.get("attempts") or 0)
        for item in (st.get("clarification_history") or [])
        if isinstance(item, dict) and item.get("key")
    }

    # Hydrate plan/object conversational focus for linked sessions
    from conversation_engine.ai_core.life_os_context import (
        build_life_os_ai_payload,
        set_active_object_ref,
    )

    # Le prossime quarantotto ore, una volta sola per turno e non a ogni
    # passo: non cambiano mentre ORA ragiona, e rileggerle costerebbe senza
    # dire niente di nuovo.
    from conversation_engine.ai_core.calendar_ahead import the_next_two_days

    calendar_ahead = await the_next_two_days(db, sess.user_id)

    # Resolve one local clock per turn: date and time share the same instant.
    from timezone_service import user_clock_context

    clock_context = await user_clock_context(db, sess.user_id)

    for step in range(max(1, max_steps)):
        # Every conversational step reaches the cognitive model. A tool may
        # carry exact material facts in say_this, but that is a post-reasoning
        # truth/confirmation guard, never a pre-model dialogue branch.
        from conversation_engine.ai_core.calendar_confirmation import pending_request

        life_os_payload = await build_life_os_ai_payload(db, sess, st)
        active_skill_state = {
            "phone": await _active_phone_skill_context(db, sess.user_id, st),
            "navigation": _pending_navigation_skill_context(st),
            "calendar": _pending_calendar_skill_context(st),
            "execution_plan": active_execution_plan,
        }
        active_skill_state = {
            key: value for key, value in active_skill_state.items() if value
        }
        payload = build_user_payload(
            user_message=user_message,
            recent_turns=st.get("recent_turns") or [],
            active_goal=st.get("active_goal"),
            context_facts=[f.model_dump() for f in context_facts],
            tools=tools.list_public(),
            observations=observations[-6:],
            current_facts={
                **(st.get("current_facts") or {}),
                **(
                    {"active_phone_input_hint": phone_input_hint}
                    if phone_input_hint else {}
                ),
                **(
                    {"active_skill_state": active_skill_state}
                    if active_skill_state else {}
                ),
            },
            life_os=life_os_payload,
            # Da dove è entrata la frase decide come esce la risposta — e
            # nient'altro. Al telefono viene ascoltata, e si dice diversamente
            # da come si scrive.
            spoken_out_loud=((sess.meta or {}).get("entry_point") == "phone"
                             or (sess.meta or {}).get("response_channel") == "voice"),
            in_app_voice=((sess.meta or {}).get("response_channel") == "voice"
                          and (sess.meta or {}).get("entry_point") != "phone"),
            calendar_next_48h=calendar_ahead,
            clock_context=clock_context,
        )
        _t = time.perf_counter()
        raw = await _call_ai(
            decision_fn=decision_fn,
            system=COGNITIVE_SYSTEM_PROMPT,
            user=payload,
            user_preference=user_llm_preference,
            # Vale a ogni passo del ragionamento, e non c'è nessun tetto per
            # il turno intero: interrompere un turno a metà vorrebbe dire
            # decidere di non rispondere, e quella è una decisione di ORA, non
            # dell'infrastruttura.
            latency_budget_s=_how_long_we_wait(
                "voice" if (sess.meta or {}).get("response_channel") == "voice"
                else str((sess.meta or {}).get("entry_point") or "")
            ),
        )
        _fase("model", _t)
        ai_calls += 1
        trace["ai_calls"] = ai_calls

        if raw is None:
            add_step(trace, event="PROVIDER_FAIL")
            state_mod.save_ai_state(sess, st)
            out = provider_unavailable_result(session_id=sess.id)
            out.ai_calls = ai_calls
            out.tool_calls = tool_calls
            out.context_calls = int(trace.get("context_calls") or 0)
            out.external_queries = external_queries
            out.elapsed_ms = int((time.perf_counter() - t0) * 1000)
            trace["phases_ms"] = dict(fasi)
            out.trace = public_trace(trace)
            return out

        gov = validate_decision(
            raw,
            tools=tools,
            recent_tool_signatures=recent_tool_sigs,
            external_query_count=external_queries,
            max_external_queries=MAX_EXTERNAL_QUERIES,
            clarification_attempts=clarification_attempts,
        )
        validated_raw: Any = raw
        if not gov.ok or not gov.decision:
            raw2 = await _call_ai(
                decision_fn=decision_fn,
                system=COGNITIVE_SYSTEM_PROMPT
                + "\nPrevious output was invalid. Return valid JSON only.",
                user=payload,
                user_preference=user_llm_preference,
            )
            ai_calls += 1
            trace["ai_calls"] = ai_calls
            gov = validate_decision(
                raw2,
                tools=tools,
                recent_tool_signatures=recent_tool_sigs,
                external_query_count=external_queries,
                max_external_queries=MAX_EXTERNAL_QUERIES,
                clarification_attempts=clarification_attempts,
            )
            validated_raw = raw2
            if not gov.ok or not gov.decision:
                decision = fallback_decision_after_malformed()
                add_step(trace, event="MALFORMED_FALLBACK", errors=gov.errors)
            else:
                decision = gov.decision
                add_step(trace, event="AI_DECISION_RETRY", mode=decision.response_mode)
        else:
            decision = gov.decision
            add_step(
                trace,
                event="AI_DECISION",
                mode=decision.response_mode,
                status=decision.reasoning_status,
                tool=(
                    decision.tool_call.resolved_capability
                    if decision.tool_call
                    else None
                ),
                has_question=bool(decision.question),
            )

        last_decision = decision
        if decision.skill_plan:
            skill_plan_declared_this_turn = True
            resume_ref = str(
                decision.skill_plan.resume_plan_ref or ""
            ).strip()
            if resume_ref and not skill_plan_resumed_this_turn:
                if (
                    active_execution_plan
                    and resume_ref == active_execution_plan_ref
                ):
                    required_skill_caps = _merge_required_skill_caps(
                        required_skill_caps,
                        active_execution_plan.get("required_capabilities") or [],
                    )
                    attempted_skill_caps.update(
                        active_execution_plan.get("attempted_capabilities") or []
                    )
                    skill_outcomes = _merge_skill_outcomes(
                        skill_outcomes,
                        active_execution_plan.get("capability_outcomes") or [],
                    )
                    current_skill_plan_ref = resume_ref
                    skill_plan_resumed_this_turn = True
                    add_step(
                        trace,
                        event="SKILL_PLAN_RESUMED",
                        plan_ref=resume_ref,
                    )
                else:
                    observations.append(
                        Observation(
                            kind="system",
                            name="invalid_skill_plan_resume",
                            status="nudge",
                            payload={
                                "failure_code": "INVALID_SKILL_PLAN_RESUME",
                                "reason": (
                                    "The resume_plan_ref does not match the active "
                                    "execution plan shown in current_facts. Re-read "
                                    "active_skill_state.execution_plan. Continue it "
                                    "only if the user's latest message semantically "
                                    "belongs to that work; otherwise start a new plan "
                                    "without a resume ref."
                                ),
                            },
                        ).model_dump()
                    )
                    add_step(trace, event="SKILL_PLAN_RESUME_REJECTED")
                    if step + 1 < max_steps:
                        continue

            required_skill_caps = _merge_required_skill_caps(
                required_skill_caps,
                decision.skill_plan.required_capabilities,
            )

            if decision.skill_plan.release_capabilities:
                (
                    required_skill_caps,
                    released_skill_caps,
                    rejected_skill_releases,
                ) = _apply_skill_plan_releases(
                    required_skill_caps,
                    decision.skill_plan.release_capabilities,
                    observations[turn_start:],
                    persisted_outcomes=skill_outcomes,
                    user_message=user_message,
                )
                if released_skill_caps:
                    trace["skill_plan_released"] = list(
                        dict.fromkeys(
                            list(trace.get("skill_plan_released") or [])
                            + released_skill_caps
                        )
                    )
                    add_step(
                        trace,
                        event="SKILL_PLAN_REVISED",
                        released=released_skill_caps,
                    )
                if rejected_skill_releases:
                    observations.append(
                        Observation(
                            kind="system",
                            name="invalid_skill_plan_release",
                            status="nudge",
                            payload={
                                "failure_code": "INVALID_SKILL_PLAN_RELEASE",
                                "rejected_capabilities": rejected_skill_releases,
                                "reason": (
                                    "A required skill can be released only with "
                                    "verified evidence. For basis=observation, "
                                    "observation_capability must match a real current "
                                    "or persisted capability outcome. For "
                                    "basis=user_message, user_instruction_quote must "
                                    "be exact words from the latest user message. "
                                    "Do not silently drop the skill."
                                ),
                            },
                        ).model_dump()
                    )
                    add_step(
                        trace,
                        event="SKILL_PLAN_RELEASE_REJECTED",
                        rejected=rejected_skill_releases,
                    )
                    if step + 1 < max_steps:
                        continue

            trace["skill_plan_required"] = list(required_skill_caps)
            trace["skill_plan_objective"] = decision.skill_plan.objective[:240]
            trace["skill_plan_ref"] = current_skill_plan_ref
        await report_activity(
            db, sess, "processing", area=decision.display_area, basis="topic",
            keep_area=decision.display_area is None,
        )
        if "repeated_clarification" in gov.errors:
            trace["repeated_question_prevented"] = int(
                trace.get("repeated_question_prevented") or 0
            ) + 1
            add_step(trace, event="REPEATED_QUESTION_PREVENTED")
        # Same-turn duplicate: reuse prior observation; never surface internal guard UX
        if "duplicate_tool_call" in (gov.errors or []):
            # Recover signature from raw tool call if governance cleared it
            raw_tc = None
            if isinstance(validated_raw, dict):
                raw_tc = validated_raw.get("tool_call")
            elif hasattr(validated_raw, "tool_call"):
                raw_tc = validated_raw.tool_call
            cap_try = ""
            args_try: Dict[str, Any] = {}
            if isinstance(raw_tc, dict):
                cap_try = str(raw_tc.get("capability") or raw_tc.get("name") or "")
                args_try = dict(raw_tc.get("arguments") or {})
            elif raw_tc is not None:
                cap_try = str(
                    getattr(raw_tc, "capability", None)
                    or getattr(raw_tc, "name", None)
                    or ""
                )
                args_try = dict(getattr(raw_tc, "arguments", None) or {})
            # Mirror active plan/object injection used on execute path
            if cap_try in (
                "update_plan",
                "create_actions",
                "create_object",
                "update_object",
                "get_object",
                "record_object_interaction",
                "mark_plan_progress",
                "get_active_plan",
            ):
                if not args_try.get("plan_id") and not args_try.get("plan_ref"):
                    if st.get("active_plan_id"):
                        args_try["plan_id"] = st["active_plan_id"]
                if (
                    cap_try
                    in (
                        "update_object",
                        "get_object",
                        "record_object_interaction",
                    )
                    and not args_try.get("object_id")
                    and not args_try.get("id")
                ):
                    oid = (st.get("active_object_ref") or {}).get("id")
                    if oid:
                        args_try["object_id"] = oid
            sig_try = tool_signature(cap_try, args_try) if cap_try else ""
            prior = turn_obs_by_sig.get(sig_try) if sig_try else None
            if prior and step + 1 < max_steps:
                observations.append(
                    {
                        **prior,
                        "name": prior.get("name") or cap_try or "tool",
                        "payload": {
                            **dict(prior.get("payload") or {}),
                            "deduped": True,
                            "reused_from_turn": True,
                            "honesty": (
                                "Identical mutation already succeeded this turn — "
                                "reuse observation; do not claim a second write."
                            ),
                        },
                    }
                )
                add_step(trace, event="DUPLICATE_REUSED", capability=cap_try)
                continue
            # No reusable obs — ask model to continue without leaking guard copy
            if decision.response_mode == "answer" and not (
                decision.message_to_user and str(decision.message_to_user).strip()
            ):
                observations.append(
                    Observation(
                        kind="system",
                        name="duplicate_tool_call",
                        status="info",
                        payload={
                            "failure_code": "DUPLICATE_SAME_TURN",
                            "reason": (
                                "Identical tool call already ran in this turn. "
                                "Answer from existing observations, or call a "
                                "different mutation if new facts require it."
                            ),
                        },
                    ).model_dump()
                )
                add_step(trace, event="DUPLICATE_SOFT", capability=cap_try)
                if step + 1 < max_steps:
                    continue
        state_mod.apply_state_updates(st, decision.state_updates)

        # V3.2 — where this person is, before deciding what to do about it.
        # A reconstruction that does not validate leaves the previous one
        # standing: losing an update is recoverable, rebuilding somebody's plan
        # out of malformed output is not.
        if decision.goal_state is not None:
            try:
                from guidance.service import GuidanceService

                guidance_state = GuidanceService.reconstruct(
                    decision.goal_state, previous=guidance_state
                )
                st["guidance_state"] = guidance_state.model_dump()
                # Saved here rather than trusted to whichever branch ends the
                # turn: a reconstruction that only survives some exits is a
                # reconstruction that cannot be relied on next turn.
                state_mod.save_ai_state(sess, st)
                logger.info(
                    "guidance_reconstructed session=%s revision=%d milestones=%d residual=%d",
                    sess.id,
                    guidance_state.revision,
                    len(guidance_state.milestones),
                    len(guidance_state.residual()),
                )
            except Exception:
                logger.info("guidance reconstruction soft-fail", exc_info=True)
        phone_owns_turn = _has_phone_observation(observations[turn_start:]) or bool(
            decision.tool_call
            and decision.tool_call.resolved_capability == _PHONE_CAPABILITY
        )
        if (
            decision.situation_update
            and decision.situation_update.operation != "none"
            and phone_owns_turn
        ):
            # A governed phone preparation already owns follow-up, retries and
            # completion. Creating a second generic Situation for the same call
            # causes duplicate autonomy and misleading "I'll keep watching"
            # copy. Keep any relationship/memory updates, but do not create a
            # parallel situation tracker for work the phone lifecycle owns.
            add_step(trace, event="SITUATION_MUTATION_SUPPRESSED_FOR_PHONE")
        elif decision.situation_update and decision.situation_update.operation != "none":
            try:
                from situations.service import SituationService

                situation_result = await SituationService(db).apply(
                    user_id=sess.user_id,
                    session_id=sess.id,
                    update=decision.situation_update,
                    reasoning_epoch=epoch,
                )
                st["active_situation_ref"] = dict(
                    situation_result.get("situation") or {}
                )
                observations.append(
                    Observation(
                        kind="tool",
                        name="situation_mutation",
                        status="ok",
                        payload=situation_result,
                        provenance=list(
                            decision.situation_update.source_refs
                            or ["user_conversation"]
                        ),
                    ).model_dump()
                )
                add_step(
                    trace,
                    event="SITUATION_MUTATION",
                    operation=decision.situation_update.operation,
                )
                await _emit_life_change(
                    trace,
                    "situation",
                    lambda: life_signals.emit_situation_signal(
                        db,
                        user_id=sess.user_id,
                        session_id=sess.id,
                        reasoning_epoch=epoch,
                        operation=decision.situation_update.operation,
                        result=situation_result,
                    ),
                    user_id=sess.user_id,
                )
                linked_plan = ((situation_result or {}).get("situation") or {}).get(
                    "linked_plan_id"
                )
                if decision.situation_update.operation == "cancel" and linked_plan:
                    linked_plan_pending_id = str(linked_plan)
            except Exception as e:
                code = str(getattr(e, "code", "PERSISTENCE_ERROR"))[:80]
                observations.append(
                    Observation(
                        kind="error",
                        name="situation_mutation",
                        status="error",
                        payload={
                            "failure_code": code,
                            "reason": "Situation state was not persisted. Do not claim it was updated. Recover from context or explain honestly.",
                        },
                    ).model_dump()
                )
                add_step(trace, event="SITUATION_MUTATION_FAIL", code=code)
                if step + 1 < max_steps:
                    continue
        if decision.context_graph_updates:
            try:
                from context_graph.service import ContextGraphService

                graph_results = await ContextGraphService(db).apply(
                    user_id=sess.user_id,
                    session_id=sess.id,
                    updates=list(decision.context_graph_updates),
                    reasoning_epoch=epoch,
                )
                trace["context_graph_updates_proposed"] = int(
                    trace.get("context_graph_updates_proposed") or 0
                ) + len(decision.context_graph_updates)
                trace["context_graph_updates_persisted"] = int(
                    trace.get("context_graph_updates_persisted") or 0
                ) + sum(1 for r in graph_results if r.get("persisted"))
                trace["context_graph_conflicts_detected"] = int(
                    trace.get("context_graph_conflicts_detected") or 0
                ) + sum(
                    1
                    for r in graph_results
                    if r.get("decision") == "REQUIRES_SUPERSESSION"
                )
                trace["context_graph_supersessions"] = int(
                    trace.get("context_graph_supersessions") or 0
                ) + sum(1 for r in graph_results if r.get("decision") == "SUPERSEDED")
                graph_write_confirmed_this_turn = any(
                    r.get("persisted") for r in graph_results
                )
                observations.append(
                    Observation(
                        kind="tool",
                        name="context_graph_mutation",
                        status="ok",
                        payload={
                            "results": graph_results,
                            "reason": (
                                "Durable graph relationships exist only where persisted=true. "
                                "REQUIRES_SUPERSESSION means an active edge with the same "
                                "subject+predicate already exists with a different object — "
                                "decide supersede or coexists_with_refs, do not silently retry "
                                "the same create. Never claim a link was made without persisted=true."
                            ),
                        },
                        provenance=[
                            r.get("edge_id") for r in graph_results if r.get("edge_id")
                        ],
                    ).model_dump()
                )
                add_step(
                    trace,
                    event="CONTEXT_GRAPH_MUTATION",
                    outcomes=[r.get("decision") for r in graph_results],
                )
                await _emit_life_change(
                    trace,
                    "context_graph",
                    lambda: life_signals.emit_context_graph_signals(
                        db,
                        user_id=sess.user_id,
                        session_id=sess.id,
                        reasoning_epoch=epoch,
                        results=graph_results,
                    ),
                    user_id=sess.user_id,
                )
            except Exception as e:
                code = str(getattr(e, "code", "PERSISTENCE_ERROR"))[:80]
                graph_write_confirmed_this_turn = False
                observations.append(
                    Observation(
                        kind="error",
                        name="context_graph_mutation",
                        status="error",
                        payload={
                            "failure_code": code,
                            "reason": "Graph relationship was not persisted. Do not claim it was linked/connected. Recover from context or explain honestly.",
                        },
                    ).model_dump()
                )
                add_step(trace, event="CONTEXT_GRAPH_MUTATION_FAIL", code=code)
                if step + 1 < max_steps:
                    continue
        if decision.memory_candidates and memory_governance_rounds < 2:
            memory_governance_rounds += 1
            try:
                from life_memory.governance import MemoryGovernanceService

                memory_outcomes = await MemoryGovernanceService(db).process(
                    user_id=sess.user_id,
                    session_id=sess.id,
                    reasoning_epoch=epoch,
                    candidates=list(decision.memory_candidates),
                )
                memory_write_confirmed_this_turn = any(
                    item.persisted for item in memory_outcomes
                )
                memory_write_decisions_this_turn = [
                    item.decision for item in memory_outcomes if item.persisted
                ]
                observations.append(
                    Observation(
                        kind="tool",
                        name="memory_governance",
                        status="ok",
                        payload={
                            "outcomes": [item.public() for item in memory_outcomes],
                            "reason": (
                                "Durable Memory changes exist only where persisted=true. "
                                "CLARIFY requires a natural user question; REJECT means keep the "
                                "information conversational/Situation-only. Never claim an unpersisted write."
                            ),
                        },
                        provenance=["user_conversation"],
                    ).model_dump()
                )
                add_step(
                    trace,
                    event="MEMORY_GOVERNANCE",
                    outcomes=[item.decision for item in memory_outcomes],
                )
                await _emit_life_change(
                    trace,
                    "life_memory",
                    lambda: life_signals.emit_memory_signals(
                        db,
                        user_id=sess.user_id,
                        session_id=sess.id,
                        reasoning_epoch=epoch,
                        outcomes=memory_outcomes,
                    ),
                    user_id=sess.user_id,
                )
            except Exception as e:
                code = str(getattr(e, "code", "MEMORY_PERSISTENCE_ERROR"))[:80]
                observations.append(
                    Observation(
                        kind="error",
                        name="memory_governance",
                        status="error",
                        payload={
                            "failure_code": code,
                            "reason": (
                                "No durable Memory change was confirmed. Do not say it was saved; "
                                "continue honestly or ask the user to retry."
                            ),
                        },
                    ).model_dump()
                )
                add_step(trace, event="MEMORY_GOVERNANCE_FAIL", code=code)
            if step + 1 < max_steps:
                continue
        # Refresh context merge after current_facts updates
        context_facts = merge_context_with_current(
            [
                f
                for f in context_facts
                if not (f.ref or "").startswith("current_facts:")
            ],
            st,
        )
        context_facts = [
            f if isinstance(f, ContextFact) else ContextFact.model_validate(f)
            for f in context_facts
            if isinstance(f, (ContextFact, dict))
        ]

        if decision.active_goal_summary:
            goal = dict(st.get("active_goal") or {})
            if not goal.get("summary"):
                goal["summary"] = decision.active_goal_summary
                st["active_goal"] = goal
        state_mod.record_decision(st, decision)

        mode = decision.response_mode
        if mode in ("answer", "ask", "finish", "act"):
            if linked_plan_pending_id and not linked_plan_reconciled_this_turn:
                first_nudge = not situation_plan_nudge_used
                situation_plan_nudge_used = True
                observations.append(
                    Observation(
                        kind="system",
                        name="linked_plan_reconciliation",
                        status="nudge",
                        payload={
                            "failure_code": "LINKED_PLAN_DECISION_REQUIRED",
                            "plan_id": linked_plan_pending_id,
                            "reason": (
                                "The contextual Situation is cancelled but its linked plan was not changed. "
                                "Decide whether that plan still serves a valid outcome. If the abandoned activity "
                                "made the plan obsolete, call update_plan on the same id with patch.status=cancelled. "
                                "Otherwise preserve/adapt it and state that distinction honestly. "
                                "Do not repeat the Situation mutation; it already succeeded."
                            ),
                            "repeated_after_ignored_nudge": not first_nudge,
                        },
                    ).model_dump()
                )
                add_step(trace, event="SITUATION_PLAN_NUDGE")
                if step + 1 < max_steps:
                    continue
                decision.response_mode = "answer"
                decision.question = None
                decision.message_to_user = (
                    "Ho aggiornato la situazione, ma non sono riuscita a riconciliare il piano "
                    "collegato. Il piano potrebbe essere ancora attivo: non lo considero annullato."
                )
            ora = _compose_user_text(decision, observations[turn_start:])
            skill_plan_waits_for_user = bool(
                mode == "ask"
                or _observations_wait_for_user(observations[turn_start:])
            )
            if mode in ("answer", "finish", "act"):
                pending_skill_caps = _pending_required_skill_caps(
                    required_skill_caps, attempted_skill_caps
                )
                if (
                    pending_skill_caps
                    and not skill_plan_waits_for_user
                    and step + 1 < max_steps
                ):
                    observations.append(
                        Observation(
                            kind="system",
                            name="declared_skill_plan_incomplete",
                            status="nudge",
                            payload={
                                "failure_code": "DECLARED_SKILL_PLAN_INCOMPLETE",
                                "objective": (
                                    decision.skill_plan.objective
                                    if decision.skill_plan
                                    else str(trace.get("skill_plan_objective") or "")
                                ),
                                "pending_capabilities": pending_skill_caps,
                                "reason": (
                                    "Your own execution plan says these ORA skills are "
                                    "required for the user's requested outcome, but no "
                                    "observation from them exists yet. Do not finish or "
                                    "claim completion. Call the next required capability "
                                    "unless genuinely blocking user input is missing. If "
                                    "input is blocking, ask only for that input. Do not "
                                    "replace the skill with manual instructions."
                                ),
                            },
                        ).model_dump()
                    )
                    add_step(
                        trace,
                        event="SKILL_PLAN_INCOMPLETE_NUDGE",
                        pending=pending_skill_caps,
                    )
                    continue
                if pending_skill_caps and not skill_plan_waits_for_user:
                    decision.message_to_user = (
                        "Non sono riuscita a completare la richiesta in questo turno."
                    )
                    decision.question = None
                    mode = "answer"
                    ora = _compose_user_text(decision, observations[turn_start:])
                    add_step(
                        trace,
                        event="SKILL_PLAN_INCOMPLETE_TERMINAL",
                        pending=pending_skill_caps,
                    )
            likely_empirical_estimate = bool(
                mode in ("answer", "finish", "act")
                and _LIKELY_EMPIRICAL_ESTIMATE_RE.search(ora or "")
            )
            if (
                likely_empirical_estimate
                and not _has_empirical_estimate_evidence(
                    observations[turn_start:]
                )
                and step + 1 < max_steps
            ):
                observations.append(
                    Observation(
                        kind="system",
                        name="empirical_estimate_requires_evidence",
                        status="nudge",
                        payload={
                            "failure_code": "EMPIRICAL_ESTIMATE_EVIDENCE_REQUIRED",
                            "reason": (
                                "Your draft contains an approximate quantitative "
                                "real-world estimate, but this turn has no research "
                                "evidence or direct estimating capability supporting it. "
                                "Do not answer from model intuition. Use response_mode="
                                "research to find credible external evidence for the "
                                "empirical rate/range, then combine it with the user's "
                                "live/personal inputs. If evidence stays weak, widen the "
                                "range and say what limits it."
                            ),
                        },
                    ).model_dump()
                )
                add_step(trace, event="EMPIRICAL_ESTIMATE_EVIDENCE_NUDGE")
                continue
            if (
                likely_empirical_estimate
                and not _has_empirical_estimate_evidence(
                    observations[turn_start:]
                )
            ):
                decision.message_to_user = (
                    "Non ho abbastanza evidenza verificata per darti una stima "
                    "quantitativa attendibile in questo momento."
                )
                decision.question = None
                mode = "answer"
                ora = _compose_user_text(decision, observations[turn_start:])
                add_step(trace, event="EMPIRICAL_ESTIMATE_BLOCKED_TERMINAL")

            if decision.uncertainty:
                trace["uncertainty_turns"] = int(trace.get("uncertainty_turns") or 0) + 1
                trace["unresolved_uncertainty"] = bool(
                    decision.uncertainty.blocking
                    or decision.uncertainty.missing_information
                    or decision.uncertainty.ambiguities
                )
                if decision.uncertainty.assumptions:
                    trace["assumptions_used"] = int(
                        trace.get("assumptions_used") or 0
                    ) + len(decision.uncertainty.assumptions)
            if (
                memory_write_confirmed_this_turn
                and not memory_result_nudge_used
                and _MEMORY_NOT_FOUND_CLAIM_RE.search(ora or "")
                and step + 1 < max_steps
            ):
                memory_result_nudge_used = True
                observations.append(
                    Observation(
                        kind="system",
                        name="memory_result_consistency",
                        status="nudge",
                        payload={
                            "failure_code": "MEMORY_RESULT_CONTRADICTION",
                            "persisted_decisions": memory_write_decisions_this_turn,
                            "reason": (
                                "A Memory governance operation was persisted in this turn. "
                                "Answer from that persisted outcome; do not claim that no matching "
                                "memory existed merely because a later active-only lookup is empty."
                            ),
                        },
                    ).model_dump()
                )
                add_step(trace, event="MEMORY_RESULT_NUDGE")
                continue
            unpersisted_memory_claim = (
                mode in ("answer", "finish", "act")
                and not memory_write_confirmed_this_turn
                and _DURABLE_MEMORY_CLAIM_RE.search(ora or "")
            )
            if (
                unpersisted_memory_claim
                and not memory_claim_nudge_used
                and step + 1 < max_steps
            ):
                memory_claim_nudge_used = True
                observations.append(
                    Observation(
                        kind="system",
                        name="memory_persist_before_claim",
                        status="nudge",
                        payload={
                            "failure_code": "MEMORY_PERSIST_REQUIRED",
                            "reason": (
                                "No persisted Memory governance outcome exists for this turn. "
                                "If durable learning is warranted, emit a bounded memory_candidate "
                                "and wait for memory_governance. Otherwise answer without claiming "
                                "that anything was remembered, saved, forgotten, or noted for future use."
                            ),
                        },
                    ).model_dump()
                )
                add_step(trace, event="MEMORY_PERSIST_NUDGE")
                continue
            if unpersisted_memory_claim:
                # The model exhausted its reasoning budget without a persisted
                # governance outcome. Never let a final-turn wording bypass the
                # persist-before-claim invariant.
                decision.message_to_user = (
                    "Non sono riuscita a salvare questa informazione in memoria "
                    "in questo momento. Possiamo riprovare."
                )
                decision.question = None
                mode = "answer"
                ora = _compose_user_text(decision, observations[turn_start:])
                add_step(trace, event="MEMORY_CLAIM_BLOCKED_TERMINAL")
            unconfirmed_graph_claim = (
                mode in ("answer", "finish", "act")
                and not graph_write_confirmed_this_turn
                and _GRAPH_LINK_CLAIM_RE.search(ora or "")
            )
            if (
                unconfirmed_graph_claim
                and not graph_claim_nudge_used
                and step + 1 < max_steps
            ):
                graph_claim_nudge_used = True
                observations.append(
                    Observation(
                        kind="system",
                        name="context_graph_persist_before_claim",
                        status="nudge",
                        payload={
                            "failure_code": "CONTEXT_GRAPH_PERSIST_REQUIRED",
                            "reason": (
                                "No persisted context_graph_updates outcome exists for this "
                                "turn. If a durable relationship is warranted, emit a bounded "
                                "context_graph_updates entry and wait for its result. Otherwise "
                                "answer without claiming that anything was linked or connected."
                            ),
                        },
                    ).model_dump()
                )
                add_step(trace, event="CONTEXT_GRAPH_PERSIST_NUDGE")
                continue
            if unconfirmed_graph_claim:
                decision.message_to_user = (
                    "Non sono riuscita a salvare questo collegamento in questo momento. "
                    "Possiamo riprovare."
                )
                decision.question = None
                mode = "answer"
                ora = _compose_user_text(decision, observations[turn_start:])
                add_step(trace, event="CONTEXT_GRAPH_CLAIM_BLOCKED_TERMINAL")
            unconfirmed_calendar_claim = (
                mode in ("answer", "finish", "act")
                and not calendar_write_confirmed_this_turn
                and _CALENDAR_CLAIM_RE.search(ora or "")
            )
            if (
                unconfirmed_calendar_claim
                and not calendar_claim_nudge_used
                and step + 1 < max_steps
            ):
                calendar_claim_nudge_used = True
                observations.append(
                    Observation(
                        kind="system",
                        name="calendar_persist_before_claim",
                        status="nudge",
                        payload={
                            "failure_code": "CALENDAR_PERSIST_REQUIRED",
                            "reason": (
                                "No successful calendar tool observation (status=ok) exists "
                                "for this turn. If a calendar change is warranted, call the "
                                "appropriate calendar capability and wait for its result. "
                                "Otherwise answer without claiming an event was created, "
                                "moved, or cancelled."
                            ),
                        },
                    ).model_dump()
                )
                add_step(trace, event="CALENDAR_PERSIST_NUDGE")
                continue
            if unconfirmed_calendar_claim:
                decision.message_to_user = (
                    "Non sono riuscita a confermare questa modifica al calendario in questo "
                    "momento. Possiamo riprovare."
                )
                decision.question = None
                mode = "answer"
                ora = _compose_user_text(decision, observations[turn_start:])
                add_step(trace, event="CALENDAR_CLAIM_BLOCKED_TERMINAL")
            scoped_calendar_absence = (
                mode in ("answer", "finish", "act")
                and bool(_CALENDAR_ABSENCE_CLAIM_RE.search(ora or ""))
                and _calendar_empty_read_is_scope_limited(
                    observations[turn_start:]
                )
            )
            if (
                scoped_calendar_absence
                and not calendar_absence_nudge_used
                and step + 1 < max_steps
            ):
                calendar_absence_nudge_used = True
                observations.append(
                    Observation(
                        kind="system",
                        name="calendar_search_scope_incomplete",
                        status="nudge",
                        payload={
                            "failure_code": "CALENDAR_SEARCH_SCOPE_INCOMPLETE",
                            "reason": (
                                "You are about to turn an empty bounded calendar "
                                "window into a global absence claim. That is not "
                                "supported. The event may be on another day. For a "
                                "named action target with no explicit date, broaden the search or "
                                "call the intended calendar capability "
                                "with target_title so it can return real candidates. "
                                "Only say 'not found' with the exact scope you actually searched."
                            ),
                        },
                    ).model_dump()
                )
                add_step(trace, event="CALENDAR_SCOPE_NUDGE")
                continue
            if scoped_calendar_absence:
                decision.message_to_user = (
                    "Non l'ho trovato nella finestra che ho controllato; "
                    "non posso concludere che non esista nel resto del calendario."
                )
                decision.question = None
                mode = "answer"
                ora = _compose_user_text(decision, observations[turn_start:])
                add_step(trace, event="CALENDAR_SCOPE_CLAIM_BLOCKED_TERMINAL")

            # A bare acknowledgement is never a completed conversational
            # outcome. It contains no answer, no question and no evidence that
            # a requested skill was used. Do not guess which skill in code:
            # hand the turn back to the cognitive model with the observations
            # and full capability catalogue still visible.
            bare_ack = (
                mode in ("answer", "finish", "act")
                and bool(_BARE_ACK_RE.fullmatch(str(ora or "").strip()))
            )
            if (
                bare_ack
                and not bare_ack_nudge_used
                and step + 1 < max_steps
            ):
                bare_ack_nudge_used = True
                observations.append(
                    Observation(
                        kind="system",
                        name="bare_ack_not_progress",
                        status="nudge",
                        payload={
                            "failure_code": "BARE_ACK_NOT_PROGRESS",
                            "reason": (
                                "A bare acknowledgement is not progress. Re-read the "
                                "user's actual intent and the available ORA skills. If "
                                "they requested an action, use the capability that can "
                                "perform or prepare it and wait for its observation. If "
                                "something essential is missing, ask only for that. "
                                "Otherwise answer substantively. Do not end on 'Ok'."
                            ),
                        },
                    ).model_dump()
                )
                add_step(trace, event="BARE_ACK_NUDGE")
                continue
            if bare_ack:
                decision.message_to_user = (
                    "Non sono riuscita a completare la richiesta in questo turno."
                )
                decision.question = None
                mode = "answer"
                ora = _compose_user_text(decision, observations[turn_start:])
                add_step(trace, event="BARE_ACK_BLOCKED_TERMINAL")

            # Capability-before-answer: an explicit request to call must pass
            # through the phone preparation. This is about routing, not
            # permission: the capability itself resolves the number, exposes
            # provider failures honestly, and obtains the required staged
            # confirmations before anything rings.
            phone_requested = bool(phone_input_hint) or _phone_action_requested(user_message)
            phone_observed = _has_phone_observation(observations[turn_start:])
            if (
                mode in ("answer", "ask", "finish", "act")
                and phone_requested
                and not phone_observed
                and not phone_nudge_used
                and step + 1 < max_steps
            ):
                phone_nudge_used = True
                observations.append(
                    Observation(
                        kind="system",
                        name="phone_capability_required",
                        status="nudge",
                        payload={
                            "failure_code": "PHONE_CAPABILITY_REQUIRED",
                            "reason": (
                                "The user requested a call or corrected the number in an active preparation. "
                                "Do not answer, refuse, or redirect them to call manually. "
                                "Call prepare_a_phone_call now. Resolve the counterparty "
                                "from the visible conversation/update context, pass the "
                                "calendar_ref when the call concerns a calendar event, and "
                                "continue an existing preparation_id when one is visible. "
                                "When active_phone_input_hint is present, it is only a mechanically observed number. Use its preparation_id to continue the same skill, and use observed_phone_number as give_number only if your semantic reading of the user's message says they are correcting the number. "
                                "The capability owns number resolution, staged confirmation, "
                                "provider readiness, and dialing."
                            ),
                        },
                    ).model_dump()
                )
                add_step(trace, event="PHONE_CAPABILITY_NUDGE")
                continue
            if (
                decision.situation_update
                and decision.situation_update.operation != "none"
                and _DURABLE_MEMORY_CLAIM_RE.search(ora or "")
                and step + 1 < max_steps
            ):
                observations.append(
                    Observation(
                        kind="system",
                        name="situation_memory_separation",
                        status="nudge",
                        payload={
                            "failure_code": "SITUATION_IS_NOT_MEMORY",
                            "reason": (
                                "The Situation mutation succeeded only as contextual state. "
                                "Do not say it was memorized or saved to durable Memory. "
                                "Answer naturally that you are keeping the current situation in view."
                            ),
                        },
                    ).model_dump()
                )
                add_step(trace, event="SITUATION_MEMORY_NUDGE")
                continue
            # Location-before-claim: current-location asks (and pending refresh retries)
            # must call location caps so the FE consent / geolocation bridge can run.
            pending_loc = st.get("pending_client_capability") or {}
            pending_loc_cap = str(pending_loc.get("capability") or "")
            force_loc = pending_loc_cap in _LOCATION_CAPS
            has_loc_obs = _has_terminal_location_obs(observations)
            if (
                mode in ("answer", "ask", "finish")
                and not location_nudge_used
                and not has_loc_obs
                and step + 1 < max_steps
                and (force_loc or _LOCATION_NOW_ASK_RE.search(user_message or ""))
            ):
                location_nudge_used = True
                observations.append(
                    Observation(
                        kind="system",
                        name="location_before_claim",
                        status="nudge",
                        payload={
                            "failure_code": "LOCATION_CAPABILITY_REQUIRED",
                            "reason": (
                                "A current-location capability is still pending or the user "
                                "asked for current device location. Call get_current_location "
                                "(response_mode=tool) before answering. "
                                "STALE/needs_client observations are not final — refresh via the "
                                "client bridge. Do not claim permission is disabled unless the "
                                "observation status is denied. "
                                "requires_consent means the client will show ORA consent."
                            ),
                            "pending_capability": pending_loc_cap
                            or "get_current_location",
                        },
                    ).model_dump()
                )
                add_step(trace, event="LOCATION_NUDGE")
                continue
            # Persist-before-claim: one soft re-entry if AI narrates durable writes
            # without a successful write observation this turn.
            if (
                mode in ("answer", "act", "finish")
                and not persist_nudge_used
                and life_os_writes_this_turn == 0
                and step + 1 < max_steps
                and (
                    _claims_unverified_life_os_persist(
                        ora, has_active_plan=bool(st.get("active_plan_id"))
                    )
                    or (
                        not update_object_ok_this_turn
                        and _claims_unverified_object_adapt(
                            ora,
                            has_active_object=bool(
                                (st.get("active_object_ref") or {}).get("id")
                            ),
                        )
                    )
                )
            ):
                persist_nudge_used = True
                has_obj = bool((st.get("active_object_ref") or {}).get("id"))
                observations.append(
                    Observation(
                        kind="system",
                        name="persist_before_claim",
                        status="nudge",
                        payload={
                            "failure_code": "PERSIST_REQUIRED",
                            "reason": (
                                (
                                    "You claimed a durable object adaptation without a successful "
                                    "update_object observation. If the user wanted saved material "
                                    "changed, call update_object (same object_id from "
                                    "life_os.active_object_ref), then answer from observations. "
                                    "If you only explained conversationally, do not claim the "
                                    "workspace was updated."
                                )
                                if has_obj
                                and _claims_unverified_object_adapt(
                                    ora, has_active_object=True
                                )
                                else (
                                    "You claimed a durable Life OS plan/object without a successful "
                                    "create_plan / create_actions / create_object / update_object "
                                    "observation. note_intention is NOT enough. Call the Life OS "
                                    "capability (response_mode=tool), then answer from observations."
                                )
                            ),
                            "active_object_id": (
                                (st.get("active_object_ref") or {}).get("id")
                            ),
                        },
                    ).model_dump()
                )
                add_step(trace, event="PERSIST_NUDGE")
                continue
            # ---------------------------------------------------------------
            # V3.2 — ORA chooses the step. The person chooses their life.
            #
            # A turn that ends "su cosa vuoi concentrarti?" has handed the plan
            # back: the person is being asked to manage the process, which is
            # the work guidance exists to take off them. When ORA has actually
            # reconstructed where they are, it knows what comes next — so the
            # model is told to pick it and either say what it needs or say what
            # it is doing, and it reasons once more.
            #
            # This never fires without a reconstruction behind it. Offering a
            # choice is legitimate when ORA genuinely does not know the shape
            # of the goal yet.
            # ---------------------------------------------------------------
            #
            # The same block catches the other way a question escapes the gate.
            # Guidance sits on `response_mode=ask`; a question written into an
            # answer's prose never passes it. Live, the model marked a need
            # `useful`, `blocking: false` — and then asked for it anyway in the
            # sentence it wrote. Nothing here judges whether it was worth
            # asking: the model is simply held to its own declaration, which is
            # the only judgement available that is not a second opinion.
            #
            # And the quietest failure of the three: the plan, described.
            # ORA reconstructs the path, says what the next step would be, and
            # stops — nothing done, nothing asked. The person is left to work
            # out what ORA needs and volunteer it, which is the arrangement all
            # of this exists to end. Guidance either advances the work or asks
            # for what blocks advancement; describing what advancement would
            # look like is neither.
            #
            # Narrow on purpose: it takes a reconstruction, a narration of the
            # plan, no question, and nothing actually done this turn. An
            # ordinary answer to an ordinary question trips none of that. A
            # conclusion drawn about the person counts as movement it has not
            # earned, so it is caught the same way.
            # A question already asked is not asked twice — governance sees to
            # that. What it cannot do is decide what happens instead, so the
            # turn ended on "posso continuare con un'ipotesi prudente, oppure
            # fermarmi qui": neither movement nor a question, and an offer the
            # person cannot evaluate. Having been stopped from re-asking is
            # precisely the moment to proceed with what is known.
            already_asked_that = "repeated_clarification" in (gov.errors or [])
            # Refused a write or an action because something required is
            # missing, and wrote no question to go with it. Governance can only
            # say "mi manca un'informazione necessaria" — true, useless, and a
            # dead end: the person is told there is a problem and never told
            # what would solve it. This one does not wait for a reconstruction;
            # it is a dead end on any turn.
            blocked_without_a_question = mode != "ask" and bool(
                {"blocking_uncertainty_for_write", "blocking_uncertainty_for_action"}
                & set(gov.errors or [])
            )
            hands_back = _is_meta_choice(ora)
            asks_for_the_optional = _asks_for_the_optional(ora, decision)
            #
            # Writing the plan down does not count as movement here. That was
            # the live failure exactly: ORA created the plan, described it, and
            # stopped — the plan moved, the person's work did not. What
            # exempts a turn is asking, not persisting.
            asked_something = "?" in (ora or "")
            described_only = not asked_something and _describes_a_plan(ora)
            concluded_early = not asked_something and _claims_about_the_person(ora)
            if (
                mode in ("answer", "finish")
                and guidance_nudges_used < MAX_GUIDANCE_NUDGES
                and step + 1 < max_steps
                and (
                    blocked_without_a_question
                    or (
                        bool(_residual_of(guidance_state))
                        and (
                            hands_back
                            or asks_for_the_optional
                            or described_only
                            or concluded_early
                            or already_asked_that
                        )
                    )
                )
            ):
                guidance_nudges_used += 1
                observations.append(
                    Observation(
                        kind="system",
                        name="next_step_is_yours",
                        status="nudge",
                        payload={
                            "failure_code": (
                                "BLOCKED_WITHOUT_A_QUESTION"
                                if blocked_without_a_question
                                else "META_CHOICE_NOT_ALLOWED"
                                if hands_back
                                else "ASKED_FOR_WHAT_IS_NOT_REQUIRED"
                                if asks_for_the_optional
                                else "CONCLUSION_WITHOUT_SUFFICIENCY"
                                if concluded_early
                                else "ALREADY_ASKED_THAT"
                                if already_asked_that
                                else "DESCRIBED_INSTEAD_OF_ADVANCING"
                            ),
                            "reason": (
                                (
                                    "You could not carry out that action because "
                                    "something required is missing, and you wrote no "
                                    "question. The user is now told there is a problem "
                                    "and not what would solve it. Ask for it: declare "
                                    "the missing items as required in "
                                    "missing_information, put the question in "
                                    "`question`, and use response_mode=ask."
                                )
                                if blocked_without_a_question
                                else (
                                    "You ended by asking the user which step to work "
                                    "on, or how you should proceed. That is your "
                                    "decision, not theirs."
                                )
                                if hands_back
                                else (
                                    "You asked the user for something you yourself "
                                    "marked useful or optional rather than required. "
                                    "Only a required, unknown item may reach them. "
                                    "Either it is genuinely required — say so in "
                                    "missing_information and use response_mode=ask — "
                                    "or it is not, and you proceed without it."
                                )
                                if asks_for_the_optional
                                else (
                                    "You drew a conclusion about this person — what "
                                    "suits them, what they qualify for, what is best "
                                    "for them — without establishing what that "
                                    "conclusion rests on. A variable is required when "
                                    "not knowing it could change whether the option is "
                                    "feasible, which option fits, which is better, or "
                                    "whether you can proceed at all. Name those, ask "
                                    "for them together, and say what you can say "
                                    "generally in the meantime — without presenting it "
                                    "as a conclusion about them."
                                )
                                if concluded_early
                                else (
                                    "You asked for something you have already "
                                    "asked this person for. They have answered it, "
                                    "or chosen not to. Proceed with what you have: "
                                    "take the next step, state the assumption you are "
                                    "making if you must make one, or ask for something "
                                    "different that is genuinely required. Do not "
                                    "offer to stop."
                                )
                                if already_asked_that
                                else (
                                    "You described the plan instead of moving it. "
                                    "Nothing was done this turn and nothing was asked, "
                                    "so the user is left to guess what you need and "
                                    "volunteer it. Take the next step now — call the "
                                    "capability, make the change, give the answer — or "
                                    "name the required information that blocks it and "
                                    "ask for it, once, together. Saying what the next "
                                    "step would be is neither."
                                )
                            )
                            + (
                                " You have reconstructed the goal: choose the next "
                                "step on the residual path yourself, then either state "
                                "what you are doing or ask — once, together — only for "
                                "what that step genuinely requires. The user decides "
                                "real-life choices (money, dates, accepting or "
                                "declining, preferences); you decide process."
                            ),
                            "residual_path": [
                                {"ref": m.ref, "title": m.title, "state": m.state}
                                for m in _residual_of(guidance_state)
                            ][:6],
                        },
                    ).model_dump()
                )
                st["observations"] = observations[-12:]
                state_mod.save_ai_state(sess, st)
                add_step(trace, event="GUIDANCE_STEP_NUDGE")
                logger.info(
                    "guidance_step_nudge session=%s code=%s",
                    sess.id,
                    (observations[-1].get("payload") or {}).get("failure_code"),
                )
                continue
            # ---------------------------------------------------------------
            # V3.2 — a question is the last resort.
            #
            # The model has decided it cannot proceed. Before that reaches a
            # person, guidance answers what it can from what ORA already holds:
            # this turn, what has already been answered or declined, governed
            # memory, the profile, the work in progress. What survives is what
            # genuinely blocks the next step, asked once and together.
            #
            # When nothing survives, the question is not suppressed — the model
            # is told what is now known and reasons again, which is the
            # difference between hiding a question and answering it.
            # ---------------------------------------------------------------
            if (
                mode == "ask"
                and decision.uncertainty
                and not guidance_nudge_used
                and step + 1 < max_steps
            ):
                try:
                    from guidance.bridge import (
                        blocking_ask_payload,
                        declined_refs_from,
                        resolution_observation,
                        variables_from_missing,
                    )
                    from guidance.service import GuidanceService

                    wanted = variables_from_missing(
                        decision.uncertainty.missing_information,
                        blocking_default=decision.uncertainty.blocking,
                    )
                    if wanted:
                        outcome = await GuidanceService(db).evaluate(
                            user_id=sess.user_id,
                            variables=wanted,
                            state=guidance_state,
                            user_message=user_message,
                            active_goal=st.get("active_goal"),
                            session_id=sess.id,
                            # What guidance has already established this
                            # session. `clarification_history` is the loop's own
                            # attempt counter and gets rewritten on every ask —
                            # overloading it would make "already known" depend
                            # on how many passes the turn happened to take.
                            answered_refs=list(st.get("resolved_refs") or []),
                            declined_refs=declined_refs_from(
                                st.get("clarification_history") or []
                            ),
                            fallback_question=decision.question or "",
                        )
                        trace["guidance"] = outcome.public_trace()
                        if outcome.next_step.kind == "proceed":
                            guidance_nudge_used = True
                            observations.append(
                                Observation(
                                    kind="system",
                                    name="information_already_known",
                                    status="nudge",
                                    payload=resolution_observation(outcome),
                                ).model_dump()
                            )
                            st["resolved_refs"] = list(
                                dict.fromkeys(
                                    list(st.get("resolved_refs") or [])
                                    + [v.ref for v in outcome.sufficiency.resolved()]
                                )
                            )[:32]
                            st["observations"] = observations[-12:]
                            state_mod.save_ai_state(sess, st)
                            add_step(trace, event="GUIDANCE_NUDGE")
                            continue
                        guidance_ask = blocking_ask_payload(
                            outcome, fallback_question=decision.question or ""
                        )
                        # Remember what ORA turned out to know, so a later pass
                        # of the same turn — or a later turn — does not have to
                        # look it up again, and cannot ask for it.
                        st["resolved_refs"] = list(
                            dict.fromkeys(
                                list(st.get("resolved_refs") or [])
                                + [v.ref for v in outcome.sufficiency.resolved()]
                            )
                        )[:32]
                except Exception:
                    # Guidance is an improvement on asking, never a dependency
                    # of it. If it cannot run, the question the model wrote is
                    # still a legitimate question.
                    logger.info("guidance gate soft-fail", exc_info=True)

            # When guidance would not let the model's own wording stand — it
            # handed the process back, or arrived in another language — the
            # composed question replaces it *where the person reads it* too.
            # Storing a clean question on the OpenQuestion while the chat still
            # shows the rejected sentence guarantees nothing: the chat is where
            # the question is actually asked.
            # One question, one wording. What is stored on the OpenQuestion and
            # what the person reads in the thread are the same sentence — not
            # because they are generated together, but because this makes them
            # so. Home and Attività project the stored one; the conversation
            # showed `message_to_user`, and the two drifted whenever guidance
            # narrowed the set or refused the wording. A person answering in
            # the thread was then answering a different question from the one
            # ORA had recorded.
            if guidance_ask and mode == "ask":
                composed = str(guidance_ask.get("question") or "").strip()
                if composed:
                    ora = composed
            #     E LA FRASE DELLO STRUMENTO VINCE ANCHE SULLA GUIDA.
            # Misurato in app (V3.21.2): il turno era una domanda, la guida
            # l'ha riscritta in «È questo il numero corretto?» — senza nome,
            # senza numero, senza provenienza. Quello che si deve confermare
            # non si riassume, nemmeno da qui.
            detto_dallo_strumento = _the_tool_s_own_sentence(observations[turn_start:])
            if detto_dallo_strumento and detto_dallo_strumento not in (ora or ""):
                ora = detto_dallo_strumento

            phone_turn = _has_phone_observation(observations[turn_start:])
            ora = _with_situation_handoff(
                ora, situation_result, suppress=phone_turn
            )
            if situation_result and ora:
                add_step(
                    trace,
                    event=(
                        "SITUATION_HANDOFF_SUPPRESSED_FOR_PHONE"
                        if phone_turn else "SITUATION_HANDOFF_VISIBLE"
                    ),
                )
            state_mod.append_turn(st, role="ora", text=ora, kind=mode)
            if mode == "ask" and decision.uncertainty:
                asked_refs = [
                    item.ref
                    for item in decision.uncertainty.missing_information
                    if item.strategy == "ask"
                ]
                history = list(st.get("clarification_history") or [])
                for ref in asked_refs:
                    key = clarification_ref_key(ref)
                    clarification_attempts[key] = clarification_attempts.get(key, 0) + 1
                    history = [
                        item
                        for item in history
                        if not (isinstance(item, dict) and item.get("key") == key)
                    ]
                    history.append(
                        {
                            "key": key,
                            "attempts": clarification_attempts[key],
                            "reasoning_epoch": epoch,
                        }
                    )
                st["clarification_history"] = history[-12:]
                trace["clarifications_requested"] = int(
                    trace.get("clarifications_requested") or 0
                ) + len(asked_refs)
                # A question that blocks is a different thing from a question
                # that clarifies. Only the first one is worth surviving the
                # conversation: the reasoning says which by marking its own
                # uncertainty blocking, and this hands that decision — with the
                # refs it was asking about — to whoever wants to persist it.
                if guidance_ask is not None:
                    # Guidance already decided what genuinely blocks, in what
                    # words, and how much it managed not to ask.
                    blocking_ask = guidance_ask
                elif decision.uncertainty.blocking:
                    needs = [
                        item for item in decision.uncertainty.missing_information
                        if item.strategy == "ask"
                    ]
                    blocking_ask = {
                        "question": (decision.question or "").strip()[:600],
                        # Why the answer is needed, in the reasoning's own words.
                        "why_needed": (
                            (needs[0].purpose if needs and needs[0].purpose else None)
                            or decision.uncertainty.operational_reason
                            or ""
                        )[:400],
                        "asked_refs": asked_refs[:8],
                        # Several needs served by one question is a bundle; the
                        # count is the only honest signal available without
                        # asking the model to classify its own question.
                        "answer_kind": "bundle" if len(needs) > 1 else "free_text",
                        "sensitive": any(
                            item.sensitivity in ("sensitive", "high") for item in needs
                        ),
                    }
            elif mode in ("answer", "finish", "act"):
                # A terminal non-question represents progress, deferral or refusal
                # handling. Do not turn semantic refs into permanent session bans.
                st["clarification_history"] = []
            navigation_text = await _ensure_navigation(
                observations, turn_start, user_message, db, sess.user_id
            )
            if navigation_text:
                ora = navigation_text
                mode = "answer"
                blocking_ask = None
                decision.question = None
                add_step(trace, event="NAVIGATION_HANDOFF")
            # ORA proposing an external effect and waiting is a fact about the
            # conversation, and until now it lived only in the model's memory
            # of its own last turn. Written down, it becomes something code
            # can check: the next message is an answer to a question that was
            # actually asked, rather than a claim that one was.
            #
            # One turn deep on purpose. A proposal three messages ago is not
            # what the person is replying to now.
            calendar_pending = pending_request(observations[turn_start:])
            st["pending_act"] = (
                {
                    "at": _now_iso(),
                    "asked": str(
                        (calendar_pending or {}).get("question") or ora or ""
                    )[:300],
                    "calendar_cancel": calendar_pending,
                }
                if calendar_pending else None
            )

            # Persist unfinished orchestration across turns. This is metadata
            # only: tool arguments and confirmation payloads remain owned by
            # their governed lifecycle state.
            pending_skill_caps = _pending_required_skill_caps(
                required_skill_caps, attempted_skill_caps
            )
            waits_for_user_now = bool(
                mode == "ask"
                or blocking_ask
                or calendar_pending
                or _observations_wait_for_user(observations[turn_start:])
            )
            if required_skill_caps and (waits_for_user_now or pending_skill_caps):
                persisted_plan = _persist_active_skill_plan(
                    st,
                    objective=str(
                        trace.get("skill_plan_objective")
                        or decision.user_intent_summary
                        or "Completare la richiesta"
                    ),
                    required=required_skill_caps,
                    attempted=attempted_skill_caps,
                    existing_ref=(
                        current_skill_plan_ref
                        if skill_plan_resumed_this_turn
                        else None
                    ),
                    waiting=waits_for_user_now,
                )
                current_skill_plan_ref = persisted_plan["plan_ref"]
                active_execution_plan = _active_skill_plan_state(st)
                active_execution_plan_ref = current_skill_plan_ref
                trace["skill_plan_paused"] = True
                trace["skill_plan_ref"] = current_skill_plan_ref
            elif skill_plan_declared_this_turn and not pending_skill_caps:
                # A newly declared plan supersedes any stale paused plan once
                # it reaches a terminal state with no unfinished capability.
                _clear_active_skill_plan(
                    st,
                    expected_ref=(
                        current_skill_plan_ref
                        if skill_plan_resumed_this_turn
                        else None
                    ),
                )
                if not skill_plan_resumed_this_turn:
                    st["active_skill_plan"] = None
                trace["skill_plan_completed"] = True

            st["observations"] = observations[-12:]
            navigation_options = _remember_pending_navigation(
                st, observations[turn_start:]
            )
            state_mod.save_ai_state(sess, st)
            # What this turn actually amounts to for the person, named once and
            # recorded. A goal under way has to end somewhere real: a question,
            # something done, or the work finished. "Limbo" is the state this
            # whole section exists to remove — the plan described, nothing
            # asked, nothing done — and it is written down rather than assumed
            # gone, because a guarantee nobody measures is a hope.
            outcome = _turn_outcome(
                mode=mode,
                text=ora,
                blocking_ask=blocking_ask,
                did_write=bool(life_os_writes_this_turn or tool_calls),
                residual=bool(_residual_of(guidance_state)),
            )
            trace["guidance_outcome"] = outcome
            if outcome == "limbo":
                logger.warning(
                    "guidance_turn_limbo session=%s nudges=%d",
                    sess.id, guidance_nudges_used,
                )
            add_step(trace, event="FINAL", mode=mode, guidance_outcome=outcome)
            return CognitiveTurnResult(
                ok=True,
                mode=mode,  # type: ignore[arg-type]
                ora_text=ora,
                question=decision.question if mode == "ask" else None,
                blocking_ask=blocking_ask,
                session_id=sess.id,
                active_goal=ActiveGoal.model_validate(st.get("active_goal") or {}),
                memory_candidates=list(decision.memory_candidates or []),
                trace=public_trace({**trace, "phases_ms": dict(fasi)}),
                ai_calls=ai_calls,
                tool_calls=tool_calls,
                context_calls=int(trace.get("context_calls") or 0),
                external_queries=external_queries,
                elapsed_ms=int((time.perf_counter() - t0) * 1000),
                sources=public_sources[:MAX_SOURCES_UI],
                navigation=navigation_options,
                ui_actions=_ui_actions_from(observations[turn_start:]),
                journey=_journey_from(observations[turn_start:]),
                working_hint=None,
                situation=(situation_result or {}).get("situation")
                or st.get("active_situation_ref"),
            )

        if mode == "compare":
            need_raw = decision.comparison_need
            runs_done = int(trace.get("comparison_runs") or 0)
            if need_raw is None or len(need_raw.alternatives) < 2:
                observations.append(
                    Observation(
                        kind="comparison",
                        name="comparison",
                        status="failed",
                        payload={
                            "failure_code": "NOTHING_TO_COMPARE",
                            "reason": "response_mode=compare without alternatives.",
                        },
                    ).model_dump()
                )
                add_step(trace, event="COMPARE_NO_NEED")
                if step + 1 < max_steps:
                    continue
                break
            if runs_done >= MAX_COMPARISON_RUNS:
                observations.append(
                    Observation(
                        kind="comparison",
                        name="comparison",
                        status="budget_exhausted",
                        payload={
                            "failure_code": "COMPARISON_BUDGET_EXHAUSTED",
                            "reason": "No more comparisons are allowed this turn.",
                        },
                    ).model_dump()
                )
                add_step(trace, event="COMPARE_BUDGET")
                if step + 1 < max_steps:
                    continue
                break

            working_hint = "Sto mettendo a confronto le opzioni\u2026"

            from comparison.models import (
                Alternative as _Alternative,
                Attribute as _Attribute,
                ComparisonNeed as _ComparisonNeed,
            )
            from comparison.service import get_comparison_service

            built: list = []
            for raw in need_raw.alternatives:
                attributes = []
                for item in (raw.attributes or [])[:20]:
                    if not isinstance(item, dict) or not item.get("name"):
                        continue
                    number = item.get("number")
                    try:
                        number = float(number) if number is not None else None
                    except (TypeError, ValueError):
                        number = None
                    attributes.append(
                        _Attribute(
                            name=str(item.get("name"))[:120],
                            value=str(item.get("value") or "")[:300],
                            number=number,
                            unit=str(item.get("unit") or "")[:40],
                            source_ids=[str(x)[:64] for x in (item.get("source_ids") or [])][:6],
                            stated_by_user=bool(item.get("stated_by_user")),
                        )
                    )
                built.append(
                    _Alternative(
                        name=raw.name,
                        summary=(raw.summary or "")[:400],
                        attributes=attributes,
                        research_run_id=raw.research_run_id,
                    )
                )

            situation_ref = st.get("active_situation_ref")
            comparison = await get_comparison_service(db).run(
                sess.user_id,
                _ComparisonNeed(
                    decision=need_raw.decision,
                    purpose=need_raw.purpose or "",
                    already_known=list(need_raw.already_known or []),
                ),
                built,
                # The work this belongs to, carried straight through: a
                # comparison happens inside the reasoning that asked for it.
                session_id=sess.id,
                plan_id=st.get("active_plan_id"),
                situation_ref=(
                    situation_ref.get("ref")
                    if isinstance(situation_ref, dict)
                    else situation_ref
                ),
                personal_context=[f.statement for f in context_facts if f.statement][:12],
                research_run_ids=list(need_raw.research_run_ids or []),
            )
            trace["comparison_runs"] = runs_done + 1
            trace["comparison_status"] = comparison.status
            trace["comparison_verdict"] = (
                comparison.recommendation.verdict if comparison.recommendation else None
            )

            # Whatever the evidence rested on may be shown as a source.
            for run_id in comparison.research_run_ids:
                try:
                    from research.repository import ResearchRepository

                    found = await ResearchRepository(db).get(sess.user_id, run_id)
                except Exception:
                    found = None
                if found is None:
                    continue
                for src in found.citable_sources():
                    if src not in public_sources:
                        public_sources.append(src)

            observations.append(
                Observation(
                    kind="comparison",
                    name="comparison",
                    status="ok" if comparison.status == "completed" else "failed",
                    payload={
                        "comparison": comparison.to_reasoning_payload(),
                        "grounding": "TOOL_OBSERVATION",
                        # A reading of a choice on a given day is not a fact
                        # about a person.
                        "memory_eligible": False,
                    },
                    provenance=list(comparison.research_run_ids),
                ).model_dump()
            )
            add_step(trace, event="COMPARE", detail=comparison.status)
            if step + 1 < max_steps:
                continue
            break

        if mode == "research":
            need_raw = decision.research_need
            runs_done = int(trace.get("research_runs") or 0)
            if need_raw is None or not (need_raw.question or "").strip():
                observations.append(
                    Observation(
                        kind="research",
                        name="research",
                        status="failed",
                        payload={
                            "failure_code": "NO_RESEARCH_NEED",
                            "reason": "response_mode=research without a research_need.",
                        },
                    ).model_dump()
                )
                add_step(trace, event="RESEARCH_NO_NEED")
                if step + 1 < max_steps:
                    continue
                break
            if runs_done >= MAX_RESEARCH_RUNS:
                observations.append(
                    Observation(
                        kind="research",
                        name="research",
                        status="budget_exhausted",
                        payload={
                            "failure_code": "RESEARCH_BUDGET_EXHAUSTED",
                            "reason": "No more research runs are allowed this turn.",
                        },
                    ).model_dump()
                )
                add_step(trace, event="RESEARCH_BUDGET")
                if step + 1 < max_steps:
                    continue
                break

            from research.models import ResearchNeed as _ResearchNeed
            from research.service import get_research_service, research_available

            if not research_available():
                # Say it plainly rather than answering as though ORA had looked.
                observations.append(
                    Observation(
                        kind="research",
                        name="research",
                        status="failed",
                        payload={
                            "failure_code": "RESEARCH_UNAVAILABLE",
                            "reason": (
                                "Looking things up is not available right now. "
                                "Answer from what you know and say you could "
                                "not check current information."
                            ),
                            "evidence_is_real": False,
                        },
                    ).model_dump()
                )
                add_step(trace, event="RESEARCH_UNAVAILABLE")
                if step + 1 < max_steps:
                    continue
                break

            # What the person sees while this happens: a sentence, not a
            # progress bar over a search engine. Nothing of the loop — the
            # queries, the rounds, the provider — is theirs to watch.
            working_hint = "Sto verificando le informazioni più aggiornate…"

            situation_ref = st.get("active_situation_ref")
            run = await get_research_service(db).run(
                sess.user_id,
                _ResearchNeed(
                    question=need_raw.question,
                    purpose=need_raw.purpose or "",
                    already_known=list(need_raw.already_known or []),
                ),
                # The work this belongs to, carried straight through: research
                # happens inside the reasoning that asked for it and never
                # starts a goal, a plan or a conversation of its own.
                session_id=sess.id,
                plan_id=st.get("active_plan_id"),
                situation_ref=(
                    situation_ref.get("ref")
                    if isinstance(situation_ref, dict)
                    else situation_ref
                ),
                reasoning_epoch=None,
                context_lines=[f.statement for f in context_facts if f.statement][:12],
                locale_hint="it-IT",
            )
            trace["research_runs"] = runs_done + 1
            trace["research_status"] = run.status
            trace["research_sources"] = len(run.sources)
            trace["research_iterations"] = run.iterations

            # Only what a claim actually rests on may be shown as a source.
            for src in run.citable_sources():
                public_sources.append(src)

            observations.append(
                Observation(
                    kind="research",
                    name="research",
                    status="ok" if run.status in ("completed", "partial") else "failed",
                    payload={
                        "research": run.to_reasoning_payload(),
                        "grounding": "TOOL_OBSERVATION",
                        # External evidence is never a fact about this person.
                        "memory_eligible": False,
                    },
                    provenance=[s.source_id for s in run.sources],
                ).model_dump()
            )
            add_step(trace, event="RESEARCH", detail=run.status)
            if step + 1 < max_steps:
                continue
            break

        if mode == "context":
            cq = (decision.context_query or "").strip()
            if int(trace.get("context_calls") or 0) >= MAX_CONTEXT_CALLS:
                observations.append(
                    Observation(
                        kind="context",
                        name="context_broker",
                        status="budget_exhausted",
                        payload={
                            "failure_code": "CONTEXT_BUDGET_EXHAUSTED",
                            "reason": "No more personal-context retrieval calls are allowed this turn.",
                        },
                    ).model_dump()
                )
                add_step(trace, event="CONTEXT_BUDGET")
                if step + 1 < max_steps:
                    continue
                break
            # Generic retrieval spans all life sources; it is not a memory tool.
            await report_activity(db, sess, "context", keep_area=True)
            more = await broker.retrieve(
                user_id=sess.user_id,
                user_message=user_message,
                active_goal=st.get("active_goal"),
                query=cq or user_message,
                context_need=decision.context_need,
                stage="B",
                session_id=sess.id,
            )
            await report_activity(db, sess, "processing", keep_area=True)
            trace["context_calls"] = int(trace.get("context_calls") or 0) + 1
            existing = {f.ref or f.statement or f.fact for f in context_facts}
            for f in more:
                key = f.ref or f.statement or f.fact
                if key not in existing:
                    context_facts.append(f)
                    existing.add(key)
            stats_b = context_payload_stats(context_facts)
            trace["context_item_count"] = stats_b["item_count"]
            trace["context_payload_chars"] = stats_b["payload_chars"]
            report = broker.last_report.public()
            trace["context_sources"] = report.get("queried_sources") or []
            trace["context_candidate_count"] = report.get("candidate_count") or 0
            trace["context_final_count"] = report.get("final_count") or 0
            trace["context_failure_status"] = report.get("status")
            graph_facts = [f for f in more if f.source == "life_context_graph"]
            if "life_context_graph" in (report.get("queried_sources") or []):
                trace["context_graph_calls"] = int(
                    trace.get("context_graph_calls") or 0
                ) + 1
                trace["context_graph_depth"] = GRAPH_MAX_DEPTH
                trace["context_graph_returned_edge_count"] = int(
                    trace.get("context_graph_returned_edge_count") or 0
                ) + len(graph_facts)
                trace["context_graph_payload_chars"] = int(
                    trace.get("context_graph_payload_chars") or 0
                ) + sum(len(f.statement) for f in graph_facts)
                if not graph_facts:
                    trace["context_graph_failure_status"] = str(
                        report.get("status") or "no_relevant_evidence"
                    )
            obs = Observation(
                kind="context",
                name="context_broker",
                status=(
                    "ok"
                    if more
                    else str(report.get("status") or "no_relevant_evidence")
                ),
                payload={
                    "facts": [f.model_dump() for f in more],
                    "context_need": (
                        decision.context_need.model_dump()
                        if decision.context_need
                        else {"query": cq}
                    ),
                    "item_count": len(more),
                    "grounding": "PERSONAL_CONTEXT",
                    "retrieval": report,
                },
                provenance=[f.ref for f in more if f.ref],
            )
            observations.append(obs.model_dump())
            if decision.uncertainty and any(
                item.strategy == "retrieve"
                for item in decision.uncertainty.missing_information
            ):
                trace["clarification_context_attempts"] = int(
                    trace.get("clarification_context_attempts") or 0
                ) + 1
            add_step(
                trace,
                event="CONTEXT_B",
                n=len(more),
                query=(cq or "")[:120],
                payload_chars=stats_b["payload_chars"],
                sources=[f.source for f in more],
            )
            continue

        if mode == "tool" and decision.tool_call:
            cap = decision.tool_call.resolved_capability
            if tool_calls >= MAX_TOOL_CALLS:
                observations.append(
                    Observation(
                        kind="system",
                        name="tool_budget",
                        status="blocked",
                        payload={
                            "failure_code": "UNSUPPORTED",
                            "reason": "max_tool_calls",
                        },
                    ).model_dump()
                )
                add_step(trace, event="TOOL_BUDGET")
                continue
            if cap in _WRITE_CAPS and write_calls >= MAX_WRITE_CALLS:
                observations.append(
                    Observation(
                        kind="system",
                        name="write_budget",
                        status="blocked",
                        payload={
                            "failure_code": "UNSUPPORTED",
                            "reason": "max_write_calls",
                        },
                    ).model_dump()
                )
                add_step(trace, event="WRITE_BUDGET")
                continue
            if cap == "create_object" and object_gens >= MAX_OBJECT_GENERATIONS:
                observations.append(
                    Observation(
                        kind="system",
                        name="object_budget",
                        status="blocked",
                        payload={
                            "failure_code": "UNSUPPORTED",
                            "reason": "max_object_generations",
                        },
                    ).model_dump()
                )
                add_step(trace, event="OBJECT_BUDGET")
                continue

            args = dict(decision.tool_call.arguments or {})
            if cap == "prepare_a_phone_call" and phone_input_hint and not args.get("preparation_id"):
                args["preparation_id"] = phone_input_hint["preparation_id"]
            # Prefer active plan / object from state when AI omits ids
            if cap in (
                "update_plan",
                "create_actions",
                "create_object",
                "update_object",
                "list_goal_objects",
                "mark_plan_progress",
                "get_active_plan",
                "get_object",
                "record_object_interaction",
            ):
                if not args.get("plan_id") and not args.get("plan_ref"):
                    if st.get("active_plan_id"):
                        args["plan_id"] = st["active_plan_id"]
                        if cap == "create_object":
                            args["plan_ref"] = st["active_plan_id"]
                if (
                    cap
                    in (
                        "update_object",
                        "get_object",
                        "record_object_interaction",
                    )
                    and not args.get("object_id")
                    and not args.get("id")
                ):
                    oid = (st.get("active_object_ref") or {}).get("id")
                    if oid:
                        args["object_id"] = oid
            sig = tool_signature(cap, args)
            working_hint = "Controllo…" if cap == "web_search" else "Organizzo…"
            _t = time.perf_counter()
            #     QUELLO CHE STA FACENDO, MENTRE LO FA.
            # «Sto ragionando…» è la frase di chi non ha niente da dire. Qui
            # c'è lo strumento che sta davvero girando, scritto dove la chat
            # può leggerlo — e sparisce appena il turno finisce.
            await _say_what_is_happening(db, sess, what_is_happening(cap))
            await report_activity(
                db, sess, "tool", area=CAPABILITY_AREAS.get(cap), basis="tool",
                keep_area=cap not in CAPABILITY_AREAS,
            )
            obs = await tools.execute(
                cap,
                args,
                runtime={
                    "user_id": sess.user_id,
                    "session_id": sess.id,
                    "db": db,
                    "reasoning_epoch": epoch,
                    "platform": "web",
                    # What the person actually wrote this turn, and whether
                    # ORA had asked them something before they wrote it.
                    #
                    # Both travel as facts the runtime owns, never as
                    # something the model reports about itself. A capability
                    # that has to decide whether somebody authorised an
                    # external effect cannot take the model's word for what
                    # they said — it has to be able to look.
                    "user_message": user_message,
                    "pending_act": (st.get("pending_act") or None),
                    "pending_navigation": (st.get("pending_navigation") or None),
                },
            )
            if (
                cap == "continue_navigation"
                and obs.status in ("ok", "needs_client")
                and (obs.payload or {}).get("ready")
            ):
                st.pop("pending_navigation", None)
            await report_activity(db, sess, "processing", keep_area=True)
            _fase("tools", _t)
            tool_calls += 1
            trace["tool_calls"] = tool_calls
            # Client-side capability bridge (foreground location) — pause for FE
            if obs.status == "needs_client":
                ca = (obs.payload or {}).get("client_action")
                # Defensive: STALE historically set needs_client without client_action
                if not (isinstance(ca, dict) and ca.get("type")):
                    if (obs.payload or {}).get("needs_client") or (
                        (obs.payload or {}).get("status")
                        in (
                            "stale",
                            "needs_client",
                            "consent_required",
                        )
                    ):
                        ca = {
                            "type": "request_foreground_location",
                            "reason": "Refresh foreground location for this turn.",
                            "refresh": True,
                        }
                if isinstance(ca, dict) and ca.get("type"):
                    observations.append(obs.model_dump())
                    attempted_skill_caps = _record_skill_attempt(
                        attempted_skill_caps,
                        cap,
                        str(getattr(obs, "name", "") or ""),
                    )
                    if required_skill_caps:
                        persisted_plan = _persist_active_skill_plan(
                            st,
                            objective=str(
                                trace.get("skill_plan_objective")
                                or decision.user_intent_summary
                                or "Completare la richiesta"
                            ),
                            required=required_skill_caps,
                            attempted=attempted_skill_caps,
                            existing_ref=(
                                current_skill_plan_ref
                                if skill_plan_resumed_this_turn
                                else None
                            ),
                            waiting=True,
                        )
                        current_skill_plan_ref = persisted_plan["plan_ref"]
                        active_execution_plan = _active_skill_plan_state(st)
                        active_execution_plan_ref = current_skill_plan_ref
                        trace["skill_plan_paused"] = True
                        trace["skill_plan_ref"] = current_skill_plan_ref
                    st["pending_client_resume_message"] = user_message
                    st["pending_client_capability"] = {
                        "capability": cap,
                        "action": str(ca.get("type"))[:64],
                        "refresh": bool(ca.get("refresh")),
                    }
                    # Generic pending-turn contract (survives Home → /ora navigation)
                    st["pending_turn"] = {
                        "id": f"pt_{uuid.uuid4().hex[:12]}",
                        "status": "awaiting_client",
                        "capability": cap,
                        "client_actions": [ca],
                        "user_message_preview": (user_message or "")[:80],
                        "created_at": now_iso(),
                    }
                    st["observations"] = observations[-12:]
                    state_mod.save_ai_state(sess, st)
                    add_step(
                        trace,
                        event="CLIENT_ACTION",
                        name=str(ca.get("type"))[:64],
                    )
                    return CognitiveTurnResult(
                        ok=True,
                        mode="answer",
                        ora_text="",
                        session_id=sess.id,
                        active_goal=ActiveGoal.model_validate(
                            st.get("active_goal") or {}
                        ),
                        memory_candidates=[],
                        trace=public_trace({**trace, "phases_ms": dict(fasi)}),
                        ai_calls=ai_calls,
                        tool_calls=tool_calls,
                        context_calls=int(trace.get("context_calls") or 0),
                        external_queries=external_queries,
                        elapsed_ms=int((time.perf_counter() - t0) * 1000),
                        sources=[],
                        working_hint="Posizione…",
                        client_actions=[ca],
                    )
            # Fresh CURRENT/RECENT location — clear pending bridge so retries stop
            if (
                cap in _LOCATION_CAPS
                and obs.status == "ok"
                and not (obs.payload or {}).get("needs_client")
            ):
                st.pop("pending_client_capability", None)
                st.pop("pending_client_resume_message", None)
                st.pop("pending_client_actions", None)
                pt = dict(st.get("pending_turn") or {})
                if pt:
                    pt["status"] = "completed"
                    pt.pop("client_actions", None)
                    st["pending_turn"] = pt
            if cap == "web_search":
                external_queries += 1
                trace["external_queries"] = external_queries
                st["external_query_count_session"] = (
                    int(st.get("external_query_count_session") or 0) + 1
                )
            # A lifecycle/continuation skill can return the observation of the
            # concrete capability that actually performed the effect. Count and
            # verify the observed effect, not only the wrapper the model called.
            # Example: continue_calendar_action -> cancel_calendar_event.
            observed_cap = str(getattr(obs, "name", "") or "").strip()
            effective_write_cap = _effective_capability(
                cap, observed_cap, _WRITE_CAPS
            )
            effective_calendar_cap = _effective_capability(
                cap, observed_cap, _CALENDAR_WRITE_CAPS
            )

            if effective_write_cap in _WRITE_CAPS:
                write_calls += 1
                trace["write_calls"] = write_calls
            if _calendar_write_observation_succeeded(cap, obs):
                calendar_write_confirmed_this_turn = True
            if effective_calendar_cap:
                # Emitted for "partial" too: local ORA state really changed
                # even when the Google-side sync stayed unconfirmed.
                await _emit_life_change(
                    trace,
                    "calendar",
                    lambda: life_signals.emit_calendar_signal(
                        db,
                        user_id=sess.user_id,
                        session_id=sess.id,
                        reasoning_epoch=epoch,
                        capability=effective_calendar_cap,
                        observation_status=obs.status,
                        payload=obs.payload or {},
                    ),
                    user_id=sess.user_id,
                )
            if cap in _LIFE_OS_PERSIST_CAPS and (
                obs.status in ("ok", "success")
                or (obs.payload or {}).get("status") == "success"
            ):
                life_os_writes_this_turn += 1
                await _emit_life_change(
                    trace,
                    "life_os",
                    lambda: life_signals.emit_life_os_signal(
                        db,
                        user_id=sess.user_id,
                        session_id=sess.id,
                        reasoning_epoch=epoch,
                        capability=cap,
                        payload=obs.payload or {},
                    ),
                    user_id=sess.user_id,
                )
                if (
                    cap == "update_plan"
                    and linked_plan_pending_id
                    and str(args.get("plan_id") or "") == linked_plan_pending_id
                ):
                    linked_plan_reconciled_this_turn = True
            if cap == "create_object":
                object_gens += 1
                trace["object_generations"] = object_gens
                trace["artifact_generations"] = object_gens  # compat alias
            recent_tool_sigs.add(sig)
            st["turn_tool_signatures"] = list(recent_tool_sigs)[-20:]
            # Observability only — NOT used to ban cross-turn adaptation
            hist = list(st.get("last_mutations") or [])
            hist.append(
                {
                    "epoch": epoch,
                    "capability": cap,
                    "sig": sig[:240],
                    "status": obs.status,
                    "at": __import__(
                        "conversation_engine.models", fromlist=["now_iso"]
                    ).now_iso(),
                }
            )
            st["last_mutations"] = hist[-12:]
            # Clear legacy cross-turn ban list (keep empty / epoch-tagged)
            st["tool_signatures"] = []
            obs_dump = obs.model_dump()
            turn_obs_by_sig[sig] = obs_dump
            observations.append(obs_dump)
            # A required skill counts only after a real observation exists.
            # Record both the wrapper the AI invoked and the concrete leaf
            # capability that emitted the observation.
            attempted_skill_caps = _record_skill_attempt(
                attempted_skill_caps,
                cap,
                str(obs_dump.get("name") or ""),
            )
            trace["skill_plan_attempted"] = sorted(attempted_skill_caps)

            # Persist active plan/goal refs for Continue / later turns
            payload = obs.payload or {}
            if payload.get("plan_id") and (
                obs.status in ("ok", "success") or payload.get("status") == "success"
            ):
                st["active_plan_id"] = payload["plan_id"]
            if payload.get("goal_id") and (
                obs.status in ("ok", "success") or payload.get("status") == "success"
            ):
                st["active_goal_id"] = payload["goal_id"]
            #     LA PREPARAZIONE IN CORSO, PER LEGARCI LE DOMANDE.
            if payload.get("preparation_id"):
                st["active_preparation_id"] = str(payload["preparation_id"])[:64]
            if payload.get("object_id") and payload.get("status") == "success":
                objs = list(st.get("object_ids") or [])
                oid = str(payload["object_id"])
                objs = [x for x in objs if x != oid]
                objs.insert(0, oid)
                st["object_ids"] = objs[:20]
                st["artifact_ids"] = st["object_ids"]  # compat
                if cap in ("create_object", "update_object", "get_object"):
                    set_active_object_ref(
                        st,
                        {
                            "id": oid,
                            "title": payload.get("title"),
                            "object_kind": payload.get("object_kind"),
                            "revision": payload.get("revision"),
                            "updated_at": payload.get("updated_at"),
                            "plan_id": payload.get("plan_id")
                            or st.get("active_plan_id"),
                        },
                    )
                if cap == "update_object":
                    update_object_ok_this_turn = True

            for s in payload.get("public_sources") or []:
                if isinstance(s, dict) and (s.get("title") or s.get("url")):
                    public_sources.append(
                        {
                            "title": str(s.get("title") or "")[:80],
                            "url": str(s.get("url") or "")[:300],
                        }
                    )

            for f in payload.get("facts") or []:
                if isinstance(f, dict) and (f.get("fact") or f.get("statement")):
                    context_facts.append(ContextFact.model_validate(f))

            add_step(
                trace,
                event="TOOL",
                name=cap,
                status=obs.status,
                failure=payload.get("failure_code")
                or ((payload.get("external") or {}).get("failure_code")),
            )
            continue

        break

    ora = (
        (last_decision.message_to_user if last_decision else None)
        or (last_decision.question if last_decision else None)
        or "Sto ancora ragionando su questo — dimmi pure se vuoi aggiungere qualcosa."
    )
    if linked_plan_pending_id and not linked_plan_reconciled_this_turn:
        ora = (
            "Ho aggiornato la situazione, ma non sono riuscita a riconciliare il piano "
            "collegato. Il piano potrebbe essere ancora attivo: non lo considero annullato."
        )
    navigation_text = await _ensure_navigation(
        observations, turn_start, user_message, db, sess.user_id
    )
    if navigation_text:
        ora = navigation_text
        add_step(trace, event="NAVIGATION_HANDOFF_BOUND")
    phone_turn = _has_phone_observation(observations[turn_start:])
    ora = _with_situation_handoff(
        ora, situation_result, suppress=phone_turn
    )
    if situation_result and ora:
        add_step(
            trace,
            event=(
                "SITUATION_HANDOFF_SUPPRESSED_FOR_PHONE_BOUND"
                if phone_turn else "SITUATION_HANDOFF_VISIBLE_BOUND"
            ),
        )
    state_mod.append_turn(st, role="ora", text=ora, kind="answer")
    st["observations"] = observations[-12:]
    navigation_options = _remember_pending_navigation(
        st, observations[turn_start:]
    )
    state_mod.save_ai_state(sess, st)
    # The loop ran out of passes. Whatever it ends on is still a turn a person
    # reads, so it is classified like any other.
    bound_outcome = _turn_outcome(
        mode="answer",
        text=ora,
        blocking_ask=blocking_ask,
        did_write=bool(life_os_writes_this_turn or tool_calls),
        residual=bool(_residual_of(guidance_state)),
    )
    trace["guidance_outcome"] = bound_outcome
    if bound_outcome == "limbo":
        logger.warning(
            "guidance_turn_limbo session=%s nudges=%d bound=1",
            sess.id, guidance_nudges_used,
        )
    add_step(trace, event="LOOP_BOUND", guidance_outcome=bound_outcome)
    return CognitiveTurnResult(
        ok=True,
        mode="answer",
        ora_text=ora,
        session_id=sess.id,
        active_goal=ActiveGoal.model_validate(st.get("active_goal") or {}),
        memory_candidates=list(
            (last_decision.memory_candidates if last_decision else []) or []
        ),
        trace=public_trace({**trace, "phases_ms": dict(fasi)}),
        ai_calls=ai_calls,
        tool_calls=tool_calls,
        context_calls=int(trace.get("context_calls") or 0),
        external_queries=external_queries,
        elapsed_ms=int((time.perf_counter() - t0) * 1000),
        sources=public_sources[:MAX_SOURCES_UI],
        navigation=navigation_options,
        journey=_journey_from(observations[turn_start:]),
        ui_actions=_ui_actions_from(observations[turn_start:]),
        working_hint=working_hint,
        error="loop_bound" if ai_calls >= max_steps else None,
        situation=(situation_result or {}).get("situation")
        or st.get("active_situation_ref"),
    )


def _calendar_empty_read_is_scope_limited(observations) -> bool:
    """True when the latest calendar evidence is an empty bounded window.

    This is epistemic validation only: it does not infer what event the person
    meant or which skill to use. It prevents a local search result from being
    promoted into a global fact about the calendar.
    """
    for obs in reversed(list(observations or [])):
        name = getattr(obs, "name", None) or (
            obs.get("name") if isinstance(obs, dict) else None
        )
        if name != "get_calendar_events":
            continue
        status = getattr(obs, "status", None) or (
            obs.get("status") if isinstance(obs, dict) else None
        )
        payload = getattr(obs, "payload", None) or (
            obs.get("payload") if isinstance(obs, dict) else None
        ) or {}
        return (
            status == "ok"
            and isinstance(payload.get("window"), dict)
            and not list(payload.get("events") or [])
        )
    return False


def _claims_unverified_life_os_persist(text: str, *, has_active_plan: bool) -> bool:
    """True when user-facing copy asserts durable Life OS objects without writes."""
    if not (text or "").strip() or not _PERSIST_CLAIM_RE.search(text):
        return False
    # Material/session claims need create_object this turn when plan already exists.
    if re.search(
        r"(?i)\b(materiale|sessione|ripasso|workspace|oggetto|cards?|deck)\b",
        text,
    ):
        return True
    # Plan/organize claims need create_plan when none is active yet.
    return not has_active_plan


def _claims_unverified_object_adapt(text: str, *, has_active_object: bool) -> bool:
    """True when copy asserts saved material was adapted without update_object."""
    if not has_active_object or not (text or "").strip():
        return False
    return bool(_ADAPT_CLAIM_RE.search(text))


async def _what_day_it_is_for_them(db, user_id: str):
    """
    Che giorno è per la persona, non per il server.

        UN GIORNO SBAGLIATO NON SI VEDE FINCHÉ NON LO SENTI DIRE.

    Alle 00:16 di lunedì ORA diceva «oggi è domenica»: il payload portava la
    data UTC, e in Italia fra le ventidue e mezzanotte quella è la data di
    ieri. Con lei sbagliavano «domani», «stasera» e la finestra del calendario.

    `None` quando non si riesce a risolvere: chi costruisce il payload torna a
    UTC, che è il comportamento di sempre.
    """
    try:
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo

        from timezone_service import resolve_user_timezone

        risolto = await resolve_user_timezone(db, user_id)
        return _dt.now(ZoneInfo(risolto.tz_name)).date()
    except Exception as e:
        logger.info("fuso non risolto: %s", type(e).__name__)
        return None


def _how_long_we_wait(entry_point: str) -> Optional[float]:
    """
    Quanto si aspetta il primo provider, da dove è entrata la frase.

        CHI ASPETTA AD ALTA VOCE ASPETTA DIVERSAMENTE.

    Una tabella, non un ramo: non c'è nessuna logica del telefono qui dentro,
    e non ce n'è nessuna dentro `telephone/`. Cambia soltanto quando si decide
    di cambiare provider — non il prompt, non gli strumenti, non l'autorità,
    non quello che ORA decide. È la stessa forma di `spoken_out_loud`: la
    provenienza governa la forma e l'attesa, mai il contenuto.

    `None` vuol dire «come sempre», ed è la risposta per tutto il resto.
    """
    from llm.manager import VOICE_FIRST_ATTEMPT_S

    return VOICE_FIRST_ATTEMPT_S if entry_point in ("phone", "voice") else None


#     COSA SI STA FACENDO, IN ITALIANO E SENZA INVENTARE.
# Solo capacità che esistono: se una non è in elenco, si dice la cosa vera più
# generica invece di descrivere un lavoro che non sta avvenendo.
_SI_STA_FACENDO = {
    "get_calendar": "Controllo il tuo calendario…",
    "calendar_search": "Controllo il tuo calendario…",
    "create_calendar_event": "Scrivo in calendario…",
    "update_calendar_event": "Aggiorno il calendario…",
    "open_navigation": "Verifico il percorso e il traffico…",
    "resolve_place": "Cerco l'indirizzo…",
    "prepare_a_phone_call": "Cerco il contatto…",
    "search_documents": "Cerco fra i tuoi documenti…",
    "read_document": "Leggo il documento…",
    "web_search": "Cerco sul web…",
    "situation_mutation": "Aggiorno la tua situazione…",
    "remember": "Scrivo quello che ho capito…",
}


def what_is_happening(capability: str) -> str:
    """La frase da mostrare mentre gira `capability`."""
    return _SI_STA_FACENDO.get(capability or "", "Sto cercando quello che serve…")


async def _say_what_is_happening(db, sess, phrase: str) -> None:
    """Scrive sulla sessione che cosa sta succedendo adesso. Non solleva mai."""
    if db is None or not phrase:
        return
    try:
        await db["conversation_sessions"].update_one(
            {"id": sess.id, "user_id": sess.user_id},
            {"$set": {"meta.working_on": phrase[:120]}},
        )
    except Exception:  # pragma: no cover
        pass


async def _user_llm_preference(db, user_id: str) -> Optional[str]:
    if db is None or not user_id:
        return None
    try:
        account = await db.users.find_one(
            {"user_id": user_id}, {"_id": 0, "preferences.llm_provider": 1},
        )
        preference = ((account or {}).get("preferences") or {}).get("llm_provider")
        return preference if isinstance(preference, str) else None
    except Exception:
        # Missing preferences must not interrupt a conversation.
        return None


async def _call_ai(
    *,
    decision_fn: Optional[DecisionFn],
    system: str,
    user: str,
    latency_budget_s: Optional[float] = None,
    user_preference: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if decision_fn is not None:
        try:
            return await decision_fn(system, user)
        except Exception:
            return None
    try:
        from llm.manager import get_manager

        mgr = get_manager()
        res = await mgr.chat(
            system=system, user=user, json_mode=True,
            latency_budget_s=latency_budget_s,
            user_preference=user_preference,
        )
        text = getattr(res, "text", None) or ""
        return _parse_json(text)
    except Exception as e:
        logger.info("ai_core llm soft-fail: %s", type(e).__name__)
        return None


def _parse_json(text: str) -> Optional[Dict[str, Any]]:
    t = (text or "").strip()
    if not t:
        return None
    if t.startswith("```"):
        t = t.strip("`")
        if t.startswith("json"):
            t = t[4:].strip()
    try:
        data = json.loads(t)
        return data if isinstance(data, dict) else None
    except Exception:
        start, end = t.find("{"), t.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(t[start : end + 1])
                return data if isinstance(data, dict) else None
            except Exception:
                return None
        return None


def _residual_of(state: Any) -> List[Any]:
    """What of the reconstruction is still ahead of the person.

    Empty when there is no reconstruction — and an empty result is what keeps
    the meta-choice nudge honest: ORA may legitimately offer a choice of
    direction when it does not yet know the shape of the goal.
    """
    try:
        return list(state.residual())
    except Exception:
        return []


def _looks_english(text: str) -> bool:
    """Soft, same reason as the others."""
    try:
        from guidance.wording import looks_english

        return looks_english(text or "")
    except Exception:
        return False


def _turn_outcome(
    *,
    mode: str,
    text: str,
    blocking_ask: Optional[Dict[str, Any]],
    did_write: bool,
    residual: bool,
) -> str:
    """
    The one thing this turn was, from the person's side.

    `ask` and `complete` are self-evident. `act` needs something durable to
    have happened, not a description of what would happen — that distinction is
    the entire point. Everything else on a goal still under way is `limbo`.
    """
    if blocking_ask or mode == "ask":
        return "ask"
    if mode == "finish":
        return "complete"
    if did_write:
        return "act"
    if residual and _describes_a_plan(text):
        return "limbo"
    return "continue"


def _describes_a_plan(text: str) -> bool:
    """Soft: a wording check must never be able to fail a turn."""
    try:
        from guidance.wording import describes_a_plan

        return describes_a_plan(text or "")
    except Exception:
        return False


def _claims_about_the_person(text: str) -> bool:
    """Soft, same reason."""
    try:
        from guidance.wording import claims_about_the_person

        return claims_about_the_person(text or "")
    except Exception:
        return False


def _asks_for_the_optional(text: str, decision: Any) -> bool:
    """
    Did the turn ask for something the reasoning itself called optional?

    Only when nothing required is outstanding: a turn that legitimately needs
    something may mention the rest in passing, and this is not an argument
    about phrasing. It is the model's own `necessity` read back to it.
    """
    if "?" not in (text or ""):
        return False
    unc = getattr(decision, "uncertainty", None)
    items = list(getattr(unc, "missing_information", None) or []) if unc else []
    if not items:
        return False
    if any(str(getattr(i, "necessity", "")) == "required" for i in items):
        return False
    return any(
        str(getattr(i, "necessity", "")) in ("useful", "optional")
        and str(getattr(i, "strategy", "")) == "ask"
        for i in items
    )


def _is_meta_choice(text: str) -> bool:
    """Soft: a wording check must never be able to fail a turn."""
    try:
        from guidance.wording import is_meta_choice

        return is_meta_choice(text or "")
    except Exception:
        return False


def _guidance_state_from(state: Dict[str, Any]):
    """The reconstruction carried across turns, or an empty one.

    Persisted inside the session's own `ai_core` state rather than in a new
    collection: Life OS already owns the plan and its items, and guidance holds
    a projection over them. Two stores for one truth is how they drift.
    """
    from guidance.models import GoalState

    raw = state.get("guidance_state")
    if not isinstance(raw, dict):
        return GoalState()
    try:
        return GoalState.model_validate(raw)
    except Exception:
        return GoalState()


_BARE_ACK_RE = re.compile(r"(?i)^\s*(ok|va bene|capito|ricevuto|perfetto)[.!…\s]*$")


def _with_situation_handoff(
    text: str,
    situation_result: Optional[Dict[str, Any]],
    *,
    suppress: bool = False,
) -> str:
    """Make the handling of user-given contextual information visible.

    Every persisted create/update is queued for the ordinary autonomy review.
    attention_intent carries the AI-owned reason for future attention when one
    is already known. This function exposes only that persisted/queued truth;
    it never invents a provider, sensor, notification channel or outcome.
    """
    if suppress:
        return text or ""

    result = situation_result or {}
    if result.get("status") != "success" or result.get("operation") not in (
        "create",
        "update",
    ):
        return text or ""

    situation = result.get("situation") or {}
    intent = " ".join(str(situation.get("attention_intent") or "").split()).strip()
    intent = intent.rstrip(" .;:")

    if intent:
        sentence = (
            "Terrò questa situazione sotto controllo per "
            f"{intent}. Se emerge qualcosa di utile, te lo segnalo; "
            "altrimenti non ti disturbo."
        )
    else:
        sentence = (
            "Terrò questa situazione tra quelle attive e la rivaluterò nelle "
            "prossime valutazioni di ORA. Se emerge qualcosa di utile, te lo "
            "segnalo; altrimenti non ti disturbo."
        )

    base = (text or "").strip()
    if not base or _BARE_ACK_RE.fullmatch(base):
        return sentence

    # The cognitive model owns the conversation. Once it produced a
    # substantive answer, do not append a second backend-authored voice. The
    # sentence above is only the safety net for an empty/bare acknowledgement.
    return base


def _compose_user_text(decision: CognitiveDecision, observations=None) -> str:
    detto = _the_tool_s_own_sentence(observations)
    if decision.response_mode == "ask":
        parts = []
        if decision.message_to_user and decision.message_to_user != decision.question:
            parts.append(decision.message_to_user.strip())
        if decision.question:
            parts.append(decision.question.strip())
        testo = whole_sentences("\n\n".join(p for p in parts if p))
    else:
        testo = whole_sentences((decision.message_to_user or "").strip())
    if detto and detto not in (testo or ""):
        #     LA FRASE DELLO STRUMENTO FA FEDE, QUANDO C'E'.
        # Misurato in app: la preparazione restituiva «Ho trovato Giulia
        # Test, +39…, dalla rubrica. È questo il numero corretto?» e il
        # modello diceva solo «È questo il numero corretto?» — una conferma
        # chiesta su un numero che non si vedeva. Nome, numero e provenienza
        # non sono stile: sono la cosa da confermare.
        return detto
    return testo or "Ok."


# Gli strumenti la cui frase per la persona è parte del risultato, non un
# suggerimento: quello che chiedono di confermare non si riassume.
_TOOLS_THAT_SPEAK = ("prepare_a_phone_call", "open_navigation")


def _the_tool_s_own_sentence(observations) -> str:
    """La frase pronta dell'ultima osservazione, se viene da uno strumento che parla."""
    if not observations:
        return ""
    #     L'ULTIMA FRASE DELLO STRUMENTO IN QUESTO TURNO, ANCHE SE NON E'
    #     L'ULTIMA COSA SUCCESSA.
    # Misurato in app: il modello ha ritentato lo stesso strumento, la
    # guardia dei duplicati ha messo in coda la sua nota, poi è passato a un
    # altro strumento — e la frase da confermare è sparita: la persona ha
    # letto «Ok.». Chi chiama passa solo le osservazioni di questo turno.
    for o in reversed(observations):
        if not isinstance(o, dict) or str(o.get("name") or "") not in _TOOLS_THAT_SPEAK:
            continue
        detto = str(((o.get("payload") or {}).get("say_this")) or "").strip()
        if detto:
            return detto
    return ""


def _journey_from(observations) -> dict:
    """
    Il confronto fra i modi di arrivarci, se `open_navigation` l'ha prodotto.

    Niente di calcolato qui: si prende quello che la capacità ha ottenuto da
    chi conosce i percorsi, e se non c'è si torna vuoto.
    """
    for obs in reversed(list(observations or [])):
        payload = getattr(obs, "payload", None) or (
            obs.get("payload") if isinstance(obs, dict) else None
        ) or {}
        if payload.get("capability") != "open_navigation":
            continue
        scelte = payload.get("journey_options") or []
        if not scelte:
            #     NIENTE TEMPI: SI DICE PERCHE', NON SI INVENTANO.
            nota = payload.get("routing") or {}
            perche = str(nota.get("why_unavailable") or "")
            return {
                "unavailable": perche,
                "destination_weather": payload.get("destination_weather"),
            } if perche or payload.get("destination_weather") else {}
        return {
            "destination": ((payload.get("place") or {}).get("label") or "")[:120],
            "options": scelte[:3],
            "advice": str(payload.get("advice") or "")[:300],
            "road_choices": (payload.get("road_choices") or [])[:3],
            "route_weather": (payload.get("route_weather") or [])[:3],
            "route_provider": payload.get("route_provider"),
            "destination_weather": payload.get("destination_weather"),
        }
    return {}


def _ui_actions_from(observations) -> list:
    """Only successful, openable destinations produced during this turn."""
    from urllib.parse import parse_qs, urlparse
    import re

    out = []
    for obs in reversed(list(observations or [])):
        payload = getattr(obs, "payload", None) or (
            obs.get("payload") if isinstance(obs, dict) else None
        ) or {}
        status = getattr(obs, "status", None) or (
            obs.get("status") if isinstance(obs, dict) else None
        )
        if status not in ("ok", "success"):
            continue
        capability = getattr(obs, "name", None) or (
            obs.get("name") if isinstance(obs, dict) else None
        )
        if capability == "prepare_amazon_search" and not any(a["kind"] == "amazon_search" for a in out):
            url = str(payload.get("search_url") or "")
            try:
                parsed = urlparse(url)
                if parsed.scheme == "https" and parsed.netloc == "www.amazon.it" and parsed.path == "/s" and parse_qs(parsed.query).get("k") and len(url) <= 600:
                    out.append({"kind": "amazon_search", "label": "Apri la ricerca su Amazon", "url": url})
            except ValueError:
                pass
        plan_id = str(payload.get("plan_id") or "")
        if plan_id and re.fullmatch(r"lop_[A-Za-z0-9_-]{4,76}", plan_id) and not any(a["kind"] == "workspace" for a in out):
            out.append({"kind": "workspace", "label": "Apri il piano", "plan_id": plan_id})
    return out[:2]


def _navigation_options(observations) -> list:
    """
    The map apps from the most recent handoff in this turn.

    Only what `open_navigation` actually produced, and only when it produced
    something openable: an option with no link is a button that does nothing,
    and a sentence ending "con quale app vuoi navigare?" beside no buttons is
    a question nobody can answer.
    """
    for obs in reversed(list(observations or [])):
        payload = getattr(obs, "payload", None) or (
            obs.get("payload") if isinstance(obs, dict) else None
        ) or {}
        if payload.get("capability") not in ("open_navigation", "continue_navigation") or not payload.get("ready"):
            continue
        if payload.get("url") and payload.get("app"):
            app = str(payload["app"])
            return [
                {
                    "id": app[:32],
                    "label": {
                        "google_maps": "Google Maps",
                        "apple_maps": "Apple Maps",
                        "waze": "Waze",
                    }.get(app, app)[:40],
                    "url": str(payload["url"])[:600],
                }
            ]
        out = []
        for option in payload.get("options") or []:
            if option.get("url") and option.get("label"):
                out.append(
                    {
                        "id": str(option.get("id") or "")[:32],
                        "label": str(option["label"])[:40],
                        "url": str(option["url"])[:600],
                    }
                )
        return out[:3]
    return []
