"""
The loop: notice, decide, plan, do what is allowed, check, and stop.

    ORA MAY CREATE A GOAL WITHOUT A USER COMMAND.
    THE USER SHOULD EXPERIENCE OUTCOMES, NOT WORKFLOWS.

One engine, two doors into it. Somebody asking for something and ORA noticing
something both arrive at `consider()` and take exactly the same path — there
is no separate "autonomous" branch, and a test enforces that, because the day
there are two paths one of them stops being maintained.

The loop advances a plan as far as it can go on its own. Reading,
researching, comparing and drafting run for real against engines that already
exist; anything that would change the world stops with the work finished and a
question that is worth asking. What each capability found is kept as evidence
with its provenance, and the next thing to do is chosen from what is now known
rather than taken from the next line of a list.

Three things guard it, and all three are code.

A **claim** — one worker holds a goal at a time, so two processes reaching the
same goal produce one execution and not two.

A **budget** — iterations, model calls, capability calls, research calls and
wall time. An agent loop without a ceiling is a bill without a ceiling, and
the honest response to running out is to arrange to come back rather than to
stop having a plan.

And a **completion gate** — a goal is not closed because the model concluded
`achieved`. It is closed when the model concludes `achieved` and something
that actually happened supports it. A stand-in returning success is not the
world changing, and that is checked in code rather than asked about in a
prompt.
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from agent.authority import AuthorityService
from agent.capabilities import CapabilityResolver, is_really_wired
from agent.evidence import EvidenceStore, for_verification, real_support
from agent.execution import MAX_STEP_ATTEMPTS, StepExecutor
from agent.models import (
    ActionPlan,
    ActionEffect,
    CommunicationNeed,
    ActionStep,
    AgentBudget,
    AgentEvidence,
    AgentRun,
    AuthorityAssessment,
    AutonomousGoal,
    ExecutionReceipt,
    ExecutionResult,
    GoalVerification,
    ResultProvenance,
)
from agent.needs import NeedService
from agent.repository import AgentRepository
from agent.visibility import VisibilityService

logger = logging.getLogger(__name__)

# What one pass may cost. Bounds, not judgements: whether to keep going is
# the model's call, whether to keep paying is not.
MAX_ITERATIONS = 6
MAX_MODEL_CALLS = 8
MAX_PLAN_STEPS = 12

# The first planning pass plus three durable retries. Technical outages have
# their own budget: they have not executed a plan or disproved its outcome.
PLANNING_RETRY_SECONDS = (60, 300, 1800)
MAX_PLANNING_ATTEMPTS = len(PLANNING_RETRY_SECONDS) + 1


class _PlanNotPossible(Exception):
    """A validated negative planning judgement, never an adapter failure."""


class _PlanningStopped(Exception):
    """The source or the person's control changed while planning."""


class _InvalidNextSelection(Exception):
    """A model selected no pending step; reconsider without doing other work."""

    def __init__(self, context):
        super().__init__("action_selection_invalid")
        self.context = context


def _step_declaration(raw: Any):
    """Normalize only supplied, unambiguous aliases from ActionStep.for_ai.

    The display view is partial, not a serialized ActionStep. Its history
    cannot confer a new id, completion, evidence or authority. Missing values
    are never recovered from a capability name or an older step.
    """
    def reject(field, issue):
        return None, {"field": field, "issue": issue}

    def same(left, right):
        return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)

    def json_types(value):
        if value is None or type(value) in (str, bool, int, float):
            return True
        if type(value) is list:
            return all(json_types(item) for item in value)
        if type(value) is dict:
            return all(type(key) is str and json_types(item) for key, item in value.items())
        return False

    if not isinstance(raw, dict):
        return reject("step", "wrong_type")
    canonical = {
        "intent", "step_type", "capability_needed", "input_refs", "expected_result",
        "external_effect", "effect_type", "effect_target", "reaches_somebody_else",
        "parameters", "reversibility", "asks", "ask_kind",
    }
    aliases = {"type": "step_type", "what_kind_of_change": "effect_type"}
    parameter_aliases = (
        "document_offset", "document_version", "memory_offset", "memory_version",
        "wait_until", "wait_minutes", "wait_hours",
    )
    history = {"id", "ordinal", "status", "note"}
    if set(raw) - canonical - set(aliases) - set(parameter_aliases) - history - {"execution_parameters"}:
        return reject("step", "unsupported_field")
    data = {key: value for key, value in raw.items() if key in canonical}
    try:
        for alias, field in aliases.items():
            if alias in raw:
                if field in data and not same(data[field], raw[alias]):
                    return reject(field, "conflicting_alias")
                data[field] = raw[alias]

        parameters = data.get("parameters", {})
        if not isinstance(parameters, dict):
            return reject("parameters", "wrong_type")
        parameters = dict(parameters)
        displayed = raw.get("execution_parameters")
        if displayed is not None:
            if not isinstance(displayed, dict):
                return reject("parameters", "wrong_type")
            for key, value in displayed.items():
                if key in parameters and not same(parameters[key], value):
                    return reject("parameters", "conflicting_alias")
                parameters[key] = value
        for key in parameter_aliases:
            if key in raw:
                if key in parameters and not same(parameters[key], raw[key]):
                    return reject("parameters", "conflicting_alias")
                # Null in for_ai is a display placeholder for an absent value.
                if raw[key] is not None:
                    parameters[key] = raw[key]
        # Check finiteness/cycles before the recursive JSON type check.
        json.dumps(parameters, allow_nan=False)
        if not json_types(parameters):
            return reject("parameters", "wrong_type")
    except (TypeError, ValueError, RecursionError):
        return reject("parameters", "wrong_type")
    data["parameters"] = parameters

    # A non-effect step may explicitly say that effect metadata is N/A.
    # Some providers serialize optional fields as JSON null rather than
    # omitting them. Treat null exactly like omission ONLY when the step
    # cannot touch anything outside ORA: the existing default effect value
    # is then inert. No such repair is allowed for execute, an external
    # effect, a third-party impact, or a named effect target.
    internal_only = (
        data.get("step_type") in ("inspect", "research", "compare", "prepare", "ask_user", "verify", "wait")
        and data.get("external_effect") in (None, False)
        and data.get("reaches_somebody_else") in (None, False)
        and data.get("effect_target") in (None, "")
    )
    if internal_only:
        for optional in ("effect_type", "reversibility"):
            if optional in data and data[optional] is None:
                data.pop(optional)

    enums = {
        "step_type": ("inspect", "research", "compare", "prepare", "ask_user", "execute", "verify", "wait"),
        "effect_type": ("create", "modify", "cancel", "send", "transfer", "publish", "remove"),
        "reversibility": ("easily", "with_effort", "hardly", "irreversible"),
    }
    for field, values in enums.items():
        if field not in data:
            if field == "step_type":
                return reject(field, "missing")
            continue
        value = data[field]
        if type(value) is not str:
            return reject(field, "wrong_type")
        if value.strip() not in values:
            return reject(field, "unsupported_value")
        data[field] = value.strip()
    if type(data.get("intent")) is not str:
        return reject("intent", "wrong_type" if "intent" in data else "missing")
    if not data["intent"].strip():
        return reject("intent", "empty")
    for field in ("capability_needed", "expected_result", "effect_target", "asks"):
        if data.get(field) is not None and type(data[field]) is not str:
            return reject(field, "wrong_type")
    for field in ("external_effect", "reaches_somebody_else"):
        if field in data and type(data[field]) is not bool:
            return reject(field, "wrong_type")
    if "input_refs" in data and (not isinstance(data["input_refs"], list)
            or any(type(ref) is not str for ref in data["input_refs"])):
        return reject("input_refs", "wrong_type")
    if data.get("ask_kind") is not None and data["ask_kind"] not in ("knowledge", "authority"):
        return reject("ask_kind", "unsupported_value")
    if "step_type" not in raw:
        # for_ai omits these values. Accepting its type alias must not invent
        # a person's question/authority or the parameters of an unseen write.
        if data["step_type"] == "ask_user" and (not data.get("asks") or not data.get("ask_kind")):
            return reject("asks", "missing")
        if data["step_type"] == "execute":
            if "parameters" not in raw and displayed is None:
                return reject("parameters", "missing")
            for field in ("effect_type", "effect_target", "external_effect", "reaches_somebody_else", "reversibility"):
                if field not in data:
                    return reject(field, "missing")
    return data, None

# A model may choose a clock minute now. Keep one hard lower/upper bound so
# precision cannot turn into polling and a typo cannot schedule a year away.
MIN_WAIT_MINUTES = 1
MAX_WAIT_MINUTES = 14 * 24 * 60
DEFAULT_WAIT_MINUTES = 6 * 60

# Legacy names stay because stored v60 plans and tests still speak hours.
MIN_WAIT_HOURS = 1
MAX_WAIT_HOURS = 24 * 14

# How long to leave a goal alone when a run ran out of budget rather than out
# of work. Soon enough to be continuing; far enough away to not be a spin.
CONTINUE_IN_HOURS = 2


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _bounded_wait_minutes(value: Any, default: int = DEFAULT_WAIT_MINUTES) -> int:
    """Technical bound for duration-based autonomous follow-ups."""
    try:
        minutes = int(round(float(value)))
    except (TypeError, ValueError):
        minutes = int(default)
    return max(MIN_WAIT_MINUTES, min(MAX_WAIT_MINUTES, minutes))


def _bounded_wait_hours(value: Any, default: int = 6) -> int:
    """Backward-compatible hour bound for already-persisted plans."""
    try:
        hours = int(float(value))
    except (TypeError, ValueError):
        hours = int(default)
    return max(MIN_WAIT_HOURS, min(MAX_WAIT_HOURS, hours))


def _aware_wait_until(value: Any) -> Optional[datetime]:
    """Parse a model clock target only when it carries an explicit timezone."""
    if not value:
        return None
    try:
        target = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if target.tzinfo is None:
        return None
    return target.astimezone(timezone.utc)


def _wait_schedule(
    *,
    wait_until: Any = None,
    wait_minutes: Any = None,
    wait_hours: Any = None,
    default_minutes: int = DEFAULT_WAIT_MINUTES,
    now: Optional[datetime] = None,
) -> tuple[datetime, int]:
    """One canonical due instant for next_run_at and Ambient wake.

    Absolute timezone-aware time wins, then minute duration, then legacy hour
    duration. Past/invalid absolute targets fall through instead of becoming a
    one-minute retry loop. Targets beyond fourteen days are technically capped.
    """
    now = (now or _now()).astimezone(timezone.utc)
    target = _aware_wait_until(wait_until)
    if target is not None and target > now:
        latest = now + timedelta(minutes=MAX_WAIT_MINUTES)
        due = min(target, latest)
        minutes = max(
            MIN_WAIT_MINUTES,
            int(math.ceil((due - now).total_seconds() / 60)),
        )
        return due, minutes

    if wait_minutes is not None:
        minutes = _bounded_wait_minutes(wait_minutes, default=default_minutes)
    elif wait_hours is not None:
        hours = _bounded_wait_hours(
            wait_hours, default=max(1, int(default_minutes / 60))
        )
        minutes = hours * 60
    else:
        minutes = _bounded_wait_minutes(default_minutes, default=default_minutes)
    return now + timedelta(minutes=minutes), minutes


def _wait_parameters(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Persist the most precise valid wait contract while retaining v60 hours."""
    target = _aware_wait_until(raw.get("wait_until"))
    now = _now()
    if target is not None and target > now:
        due, _ = _wait_schedule(wait_until=target, now=now)
        return {"wait_until": due.isoformat()}
    if _explicit_wait_target(wait_minutes=raw.get("wait_minutes"), now=now):
        return {"wait_minutes": _bounded_wait_minutes(raw.get("wait_minutes"))}
    if _explicit_wait_target(wait_hours=raw.get("wait_hours"), now=now):
        return {"wait_hours": _bounded_wait_hours(raw.get("wait_hours"), default=6)}
    # _wait may still arrange a bounded technical retry. Keep the absent
    # model choice absent here, so that retry cannot become a claimed check.
    return {}


def _explicit_wait_target(*, wait_until=None, wait_minutes=None, wait_hours=None, now=None):
    now = now or _now()
    target = _aware_wait_until(wait_until)
    if target is not None and target > now:
        return True
    for value in (wait_minutes, wait_hours):
        if isinstance(value, bool) or value is None:
            continue
        try:
            number = float(value)
            if math.isfinite(number) and number > 0:
                return True
        except (TypeError, ValueError, OverflowError):
            continue
    return False


def _wait_hours_for(step: Optional[ActionStep], default: int = 6) -> int:
    """Legacy helper kept for v60 callers; new runtime uses _wait_schedule."""
    value = ((step.parameters or {}).get("wait_hours") if step is not None else default)
    return _bounded_wait_hours(value, default=default)


async def _user_clock_context(db, owner_id: str) -> dict:
    """Fresh local clock evidence for autonomous timing decisions.

    Timezone resolution reuses ORA's bounded resolver: confirmed account
    timezone first, calendar evidence second, explicitly-labelled system
    fallback last. No GPS or residence inference is introduced here.
    """
    from day_names import weekday_name
    from timezone_service import user_clock_context

    clock = await user_clock_context(db, owner_id)
    try:
        local_day = datetime.fromisoformat(str(clock["local_date"])).date()
    except Exception:
        local_day = _now().date()
    return {
        **clock,
        "today": local_day.isoformat(),
        "today_weekday": weekday_name(local_day),
    }

class AgentService:
    def __init__(self, db):
        self.db = db
        self.repo = AgentRepository(db)
        self.authority = AuthorityService(db)
        self.capabilities = CapabilityResolver(db)
        self.executor = StepExecutor(db)
        self.evidence = EvidenceStore(db)
        self.visibility = VisibilityService(db)
        self.needs = NeedService(db)

    async def ensure_indexes(self) -> None:
        await self.repo.ensure_indexes()
        await self.authority.ensure_indexes()
        await self.executor.ensure_indexes()
        await self.evidence.ensure_indexes()
        await self.visibility.ensure_indexes()
        await self.needs.ensure_indexes()

    # --- the way in --------------------------------------------------------

    async def consider(
        self,
        owner_id: str,
        *,
        situation: Dict[str, Any],
        origin: str = "agent_initiated",
        opportunity_id: str = "",
        source_kind: str = "",
        source_refs: Optional[List[str]] = None,
        language: str = "it",
        admission_revision: str = "",
        admission_token: str = "",
    ) -> Dict[str, Any]:
        """
        Is there an outcome here worth pursuing?

        The only entrance. A request and a noticing produce the same call with
        a different `origin`, so nothing downstream can behave differently
        depending on who started it.
        """
        from agent.reasoning import decide_goal, goal_decision_invalid_fields
        from agent.source_refresh import queue_existing, context

        source = None
        async def admission_is_current() -> bool:
            """Do not form a new spontaneous goal from a superseded claim.

            The model can take seconds to think. During that time the source
            may change, close, expire, or another backend may reclaim its
            admission lease. Only the owner-scoped source revision AND lease
            token claimed by admission may authorise this creation.
            """
            if not admission_revision:
                return True  # User-initiated goals do not have an admission.
            if not (origin == "agent_initiated" and opportunity_id and admission_token):
                return False
            current = await self.db.opportunities.find_one({
                "id": opportunity_id, "owner_id": owner_id,
                "status": "active",
                "agent_review_revision": admission_revision,
                "agent_review_token": admission_token,
            }, {"_id": 0, "valid_until": 1})
            if current is None:
                return False
            expiry = current.get("valid_until")
            if expiry:
                try:
                    target = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
                    if target.tzinfo is None:
                        target = target.replace(tzinfo=timezone.utc)
                    if target <= _now():
                        return False
                except (TypeError, ValueError):
                    return False
            return True

        situation_refs = [ref for ref in (source_refs or []) if ref.startswith("situation:")]
        if source_kind == "opportunity" and len(situation_refs) == 1 and all(
            ref.startswith(("situation:", "place:")) for ref in (source_refs or [])
        ):
            dedicated = await self.db.agent_goals.find_one(
                {"owner_id": owner_id,
                 "source_kind": {"$in": ["situation_followup", "situation_initial_review"]},
                 "source_refs": situation_refs[0], "status": {"$in": ["active", "waiting", "proposed"]}},
                {"_id": 0})
            if dedicated:
                existing = AutonomousGoal.model_validate(dedicated)
                return {"outcome": "already_pursuing", "goal": existing.for_human(), "goal_id": existing.id}
        if opportunity_id:
            source = await self.db.opportunities.find_one({"id": opportunity_id, "owner_id": owner_id})
            existing = await self.repo.goal_for_opportunity(owner_id, opportunity_id)
            if existing is not None:
                await queue_existing(self.db, owner_id, opportunity_id, source)
                return {"outcome": "already_pursuing", "goal": existing.for_human()}

        # A headline can omit exactly the uncertainty that requires work.
        # Re-read only cited document previews, with the same ownership/access
        # boundary as discovery; never infer completeness from a summary.
        source_context = []
        context_unavailable = False
        unavailable_memory_refs = []
        doc_ids = [ref[9:] for ref in (source_refs or []) if ref.startswith("document:")][:8]
        if doc_ids:
            try:
                from opportunities.snapshot import _documents
                source_context = await _documents(self.db, owner_id, _now(), document_ids=doc_ids)
                context_unavailable = len(source_context) < len(set(doc_ids))
            except Exception:
                context_unavailable = True
        from agent.memory_sources import memory_source_id, read_memory_previews
        memory_refs = list(dict.fromkeys(
            str(ref).strip() for ref in (source_refs or []) if memory_source_id(ref)
        ))[:8]
        if memory_refs:
            try:
                memories = await read_memory_previews(self.db, owner_id, memory_refs)
                source_context.extend(memories)
                observed = {memory_source_id(row["ref"]) for row in memories}
                unavailable_memory_refs = [ref for ref in memory_refs if memory_source_id(ref) not in observed]
            except Exception as exc:
                logger.info("admission memory preview unavailable: %s", type(exc).__name__)
                unavailable_memory_refs = memory_refs
            context_unavailable = context_unavailable or bool(unavailable_memory_refs)
        profile_refs = {ref for ref in (source_refs or []) if ref.startswith("life_profile:")}
        if profile_refs:
            try:
                from opportunities.snapshot import _life_profile
                facts = await _life_profile(self.db, owner_id, _now())
                cited = [fact for fact in facts if fact["ref"] in profile_refs]
                source_context.extend(cited)
                context_unavailable = context_unavailable or len(cited) < len(profile_refs)
            except Exception:
                context_unavailable = True
        calendar_refs = {ref for ref in (source_refs or []) if ref.startswith("calendar:")}
        if calendar_refs:
            try:
                from opportunities.snapshot import _calendar
                appointments = await _calendar(self.db, owner_id, _now())
                cited = [
                    row for row in appointments
                    if (
                        row["ref"] in calendar_refs
                        or f"calendar:{row['ref']}" in calendar_refs
                    )
                ]
                source_context.extend(cited)
                matched = {
                    ref for ref in calendar_refs
                    if any(
                        row["ref"] == ref or f"calendar:{row['ref']}" == ref
                        for row in cited
                    )
                }
                context_unavailable = context_unavailable or len(matched) < len(calendar_refs)
            except Exception:
                context_unavailable = True
        situation_refs = {
            ref for ref in (source_refs or [])
            if ref.startswith("situation:") and ":" in ref
        }
        if situation_refs:
            try:
                from situations.repository import SituationRepository

                repository = SituationRepository(self.db)
                matched_situations = set()
                for ref in list(situation_refs)[:8]:
                    sid = ref.split(":", 1)[1]
                    state = await repository.get(owner_id, sid)
                    if state is None:
                        continue
                    preview = state.context_preview()
                    source_context.append({
                        "ref": ref,
                        "source": "situation",
                        **preview,
                    })
                    matched_situations.add(ref)
                context_unavailable = (
                    context_unavailable
                    or len(matched_situations) < len(situation_refs)
                )
            except Exception:
                context_unavailable = True
        # Two current Home commitments that demonstrably overlap need a
        # prepared resolution. Missing travel data affects a proposed new
        # slot, not whether a request to reschedule can be drafted.
        pair = None
        if source_kind == "opportunity" and opportunity_id:
            from agent.calendar_conflict import active_home_pair
            pair = await active_home_pair(self.db, owner_id, source_refs or [])
        if pair:
            answer = {
                "outcome": "create_goal",
                "objective": "Risolvere i due impegni sovrapposti",
                "desired_outcome": (
                    "Una scelta esplicita su quale impegno spostare e, quando "
                    "autorizzata, una modifica verificata che elimini la sovrapposizione"
                ),
                "why_now": "I due impegni attivi si sovrappongono e serve decidere prima che inizino.",
                "success_criteria": [
                    "La scelta su quale impegno spostare è esplicita",
                    "Qualsiasi modifica autorizzata viene riletta dal calendario",
                    "I due impegni attivi non risultano più sovrapposti",
                ],
                "stop_conditions": ["Uno degli impegni viene annullato o gli orari non sono più sovrapposti"],
                "reasoning": "Sovrapposizione dei due impegni Home calcolata dalle fonti attive.",
                "decision_provenance": "code",
            }
        else:
            answer = await decide_goal(
                {**situation, "who_asked": origin, "source_context": source_context,
                 "source_context_unavailable": context_unavailable,
                 **({"unavailable_memory_refs": unavailable_memory_refs} if unavailable_memory_refs else {})},
                language=language
            )
        if answer is None:
            # No judgement was available. Nothing is created and nothing is
            # recorded as a decision that there was nothing to do.
            return {"outcome": "unavailable"}

        invalid_fields = goal_decision_invalid_fields(answer)
        if invalid_fields:
            # A malformed decision is a technical failure, never evidence
            # that there is no useful goal. Admission already owns its retry.
            logger.warning("goal admission invalid_goal_decision fields=%s", ",".join(invalid_fields))
            return {
                "outcome": "unavailable", "error_kind": "invalid_goal_decision",
                "invalid_fields": invalid_fields,
                "reasoning": "La valutazione ricevuta non definisce ancora un esito valido.",
            }

        decision = answer["outcome"].strip()
        if decision != "create_goal":
            return {
                "outcome": decision,
                "reasoning": str(answer.get("reasoning") or "")[:400],
                "question": str(answer.get("question") or "")[:300] or None,
            }

        if not await admission_is_current():
            return {"outcome": "unavailable", "reasoning": "Fonte cambiata prima della creazione"}

        goal = AutonomousGoal(
            owner_id=owner_id,
            status="active",
            next_run_at=_now().isoformat(),
            origin=origin,  # type: ignore[arg-type]
            objective=answer["objective"].strip()[:280],
            desired_outcome=answer["desired_outcome"].strip()[:400],
            why_now=str(answer.get("why_now") or "")[:400],
            success_criteria=[c.strip()[:200] for c in (answer.get("success_criteria") or [])][:6],
            stop_conditions=[c.strip()[:200] for c in (answer.get("stop_conditions") or [])][:6],
            source_kind=source_kind[:40],
            source_refs=[str(r)[:120] for r in (source_refs or [])][:8],
            opportunity_id=opportunity_id,
            opportunity_revision=str((source or {}).get("agent_review_revision") or ""),
            source_situation=context(source or {}),
            clarifications=[{str(k): str(v)[:2000] for k, v in item.items()
                             if k in ("question", "answer", "answered_at")}
                            for item in (situation.get("user_clarifications") or [])[-3:]
                            if isinstance(item, dict)],
            rationale=str(answer.get("reasoning") or "")[:300],
            decision_provenance=answer.get("decision_provenance", "model"),
        )
        created = await self.repo.create_goal(goal)
        if created is None:
            # A persistence failure is not evidence of another worker's goal.
            # Admission must retry unless the competing goal can be read back.
            existing = await self.repo.goal_for_opportunity(owner_id, opportunity_id) if opportunity_id else None
            if existing is not None:
                return {"outcome": "already_pursuing", "goal": existing.for_human(), "goal_id": existing.id}
            return {"outcome": "unavailable"}

        # Even the Mongo insert may race a source change after the check.
        # Invalidate the provisional goal before preparing, journaling or
        # exposing it. The newer opportunity revision remains pending and
        # will form its own goal on the next ordinary admission pass.
        if not await admission_is_current():
            await self.db.agent_goals.update_one({
                "id": goal.id, "owner_id": owner_id,
                "origin": "agent_initiated",
                "opportunity_revision": admission_revision,
                "status": {"$in": ["active", "waiting", "proposed"]},
            }, {"$set": {
                "status": "abandoned", "next_run_at": None,
                "rationale": "Fonte cambiata durante il salvataggio dell'obiettivo.",
            }})
            return {"outcome": "unavailable", "reasoning": "Fonte cambiata durante il salvataggio"}

        if pair:
            # The preparation is fully determined by two owner-scoped Home
            # events. Record the reads first; if they changed or persistence
            # failed, leave the goal due for the ordinary worker to retry.
            for start, end, zone, event, ref in pair[0]:
                await self.evidence.record(AgentEvidence(
                    owner_id=owner_id, goal_id=goal.id,
                    claim=(f"Impegno ORA {event['title']}: {event['starts_at']} / {event['ends_at']}; "
                           f"luogo: {event['location']}; note: {event['description']}")[:600],
                    supports=ref,
                    provenance=ResultProvenance(source_class="internal_observation",
                        provider="ora_local_calendar", capability="calendar.local.read",
                        source_refs=[ref], freshness="fresh"),
                ))
            from agent.preparation import prepare
            drafted = await prepare(self.db, owner_id, goal,
                ActionStep(intent="Preparare la richiesta di spostamento", step_type="prepare"))
            if drafted.status == "succeeded" and goal.prepared_text:
                # A useful preparation must end in a decision somebody can
                # actually answer, not in a draft card with no continuation.
                # Keep that decision as ordinary agent state so reloads and
                # process restarts resume the same goal instead of creating a
                # second conflict workflow.
                question = (
                    "Quale dei due impegni vuoi mantenere invariato e quale vuoi "
                    "spostare? Se sai già il nuovo orario, scrivilo."
                )
                choice = ActionStep(
                    ordinal=0,
                    intent="Scegliere quale impegno spostare e, se noto, il nuovo orario",
                    step_type="ask_user",
                    asks=question,
                    ask_kind="knowledge",
                    status="blocked",
                )
                plan = ActionPlan(
                    owner_id=owner_id,
                    goal_id=goal.id,
                    status="waiting",
                    plan_summary=(
                        "Risolvere la sovrapposizione senza modificare o contattare "
                        "nessuno finché la persona non sceglie come procedere."
                    ),
                    expected_outcome=(
                        "Una scelta esplicita su quale impegno spostare, seguita "
                        "soltanto da azioni autorizzate e verificabili."
                    ),
                    known_constraints=[
                        "Nessun nuovo orario viene inventato.",
                        "Una bozza non equivale a una modifica o a una prenotazione confermata.",
                    ],
                    steps=[choice],
                )
                await self.repo.save_plan(plan)
                goal.status, goal.next_run_at = "waiting", None
                goal.requires_user_input = True
                await self.repo.save_goal(goal)
                import hashlib
                from agent.needs import fingerprint as need_fingerprint
                from agent.prepared_review import prepared_result_ref
                prepared_reference = prepared_result_ref(goal)
                question_fingerprint = need_fingerprint(goal.id, "needs_information", question)
                need = await self.needs.raise_need(CommunicationNeed(
                    owner_id=owner_id,
                    goal_id=goal.id,
                    kind="needs_information",
                    summary=question,
                    reason=(
                        "Ho verificato una sovrapposizione reale e preparato il "
                        "prossimo passo; serve la tua scelta prima di cambiare qualcosa."
                    ),
                    source_refs=list(dict.fromkeys(goal.source_refs))[:8],
                    prepared_result_ref=prepared_reference,
                    fingerprint=hashlib.sha256(
                        f"{question_fingerprint}|{prepared_reference}".encode("utf-8")
                    ).hexdigest(),
                    requires_response=True,
                    response_kind="information",
                    work_already_done=[
                        "Ho verificato i due impegni e preparato una richiesta senza modificare il calendario."
                    ],
                    what_is_missing=question,
                    provenance="code",
                ))
                await self.repo.journal(owner_id, goal.id, kind="waiting",
                    note="Bozza pronta; la richiesta di spostamento attende la tua scelta.",
                    detail={"draft": True, "provider": "calendar_overlap_draft",
                            "step_id": choice.id, "need_id": need.id})
                await self.needs.offer_to_delivery(owner_id, need)

        await self.repo.journal(
            owner_id, goal.id, kind="goal_created", note=goal.objective,
            detail={"origin": origin, "opportunity_id": opportunity_id},
        )
        await self._note_ambient(owner_id, "agent_goal_created", goal)
        return {"outcome": "create_goal", "goal": goal.for_human(), "goal_id": goal.id}

    # --- the loop ----------------------------------------------------------

    async def advance(
        self, owner_id: str, goal_id: str, *, language: str = "it",
        worker_id: str = "", budget: Optional[AgentBudget] = None,
    ) -> Dict[str, Any]:
        """
        Take the goal as far as it can go without a person.

        Stops for exactly three reasons: the outcome is reached, something is
        needed that only a person can give, or a bound was hit. Everything
        else, it keeps doing.
        """
        goal = await self.repo.get_goal(owner_id, goal_id)
        if goal is None:
            return {"ok": False, "reason": "unknown_goal"}
        if not goal.is_open:
            return {"ok": True, "state": goal.status, "goal": goal.for_human()}

        # One worker at a time. A wake firing while a request is already
        # advancing the same goal is ordinary, not exceptional, and without
        # this both would research the same question and eventually prepare
        # the same effect twice.
        worker = worker_id or f"w_{uuid.uuid4().hex[:8]}"
        if not await self.repo.claim(owner_id, goal_id, worker_id=worker):
            return {
                "ok": True,
                "state": "already_running",
                "goal": goal.for_human(),
            }

        run = AgentRun(owner_id=owner_id, goal_id=goal.id, background=worker_id.startswith("ambient:"))
        allowance = budget or AgentBudget()
        try:
            from agent.source_refresh import refresh
            # Reload after the lease: a cancellation while waiting must win.
            goal = await self.repo.get_goal(owner_id, goal_id)
            if goal is None or not goal.is_open:
                return {"ok": True, "state": goal.status if goal else "goal_closed"}
            await refresh(self, goal)
            if not goal.is_open:
                return {"ok": True, "state": goal.status}
            # An old disputed time is not a pending mission forever. Retire
            # its pending actions when the actual appointment has ended.
            deadline = _aware_wait_until(goal.valid_until)
            if (deadline is not None and deadline <= _now()) or (
                await self._legacy_event_alert_expired(
                    owner_id, goal, include_unverifiable=False
                )
            ):
                goal.status = "abandoned"
                goal.next_run_at = None
                goal.requires_user_input = False
                goal.requires_user_authority = False
                goal.rationale = (
                    "Il momento utile è passato oppure la fonte non è più verificabile."
                )
                await self.repo.save_goal(goal)
                await self.needs.close_for_goal(
                    owner_id, goal.id, why="Appuntamento già concluso"
                )
                try:
                    from ambient.repository import AmbientRepository
                    await AmbientRepository(self.db).cancel_for(
                        owner_id, source_ref=f"goal:{goal.id}"
                    )
                except Exception:
                    pass  # The terminal goal independently fences subsequent wakes.
                await self.repo.journal(
                    owner_id, goal.id, kind="source_expired",
                    note="La fonte temporale è terminata: lavoro archiviato senza eseguire azioni.",
                )
                return {"ok": True, "state": "source_expired"}
            # Missing/disconnected original means no safe action, but is not
            # proof that a future appointment ended. Pause this run without
            # erasing work; a later source sync can make it useful again.
            if await self._legacy_event_alert_expired(
                owner_id, goal, include_unverifiable=True
            ):
                return {"ok": True, "state": "source_unverifiable"}

            revisit_due = bool(
                run.background
                and goal.status == "waiting"
                and goal.next_run_at
                and goal.next_run_at <= _now().isoformat()
                and not goal.requires_user_input
                and not goal.requires_user_authority
            )
            if revisit_due:
                goal.background_runs = 0

            needs_plan = await self.repo.plan_for(owner_id, goal.id) is None
            if not run.background and needs_plan and goal.planning_unavailable:
                # This entry point is an explicit request. Ordinary worker
                # retries preserve the counter and can never reset it.
                goal.planning_attempts = 0
                goal.planning_unavailable = False
                goal.background_runs = 0
            if run.background:
                if goal.background_runs >= 3 and not (needs_plan and goal.planning_attempts):
                    goal.next_run_at = None
                    await self.repo.save_goal(goal)
                    run.stopped_because = "background_budget"
                    return {"ok": True, "state": "background_paused"}
                goal.background_runs += 1
            # Persist recovery before execution; cancellation leaves due work.
            goal.next_run_at = (_now() + timedelta(minutes=5)).isoformat()
            await self.repo.save_goal(goal)
            result = await self._work(
                owner_id, goal, run, allowance, language=language,
                revisit_due=revisit_due,
            )
            if (not goal.is_open or goal.requires_user_input or goal.requires_user_authority
                    or (run.background and goal.background_runs >= 3 and not goal.planning_unavailable)):
                goal.next_run_at = None
            await self.repo.save_goal(goal)
        finally:
            await self.repo.release(goal_id, stopped_because=run.stopped_because, worker_id=worker)

        # Whether any of that was worth their knowing. Asked once, at the end,
        # about the run as a whole — a decision per step would be the
        # narration this is meant to prevent.
        await self._consider_visibility(
            owner_id, goal_id, run, allowance, language=language
        )
        return result

    async def _work(
        self, owner_id, goal, run: AgentRun, budget: AgentBudget, *, language: str,
        revisit_due: bool = False,
    ) -> Dict[str, Any]:
        """
        Keep going while there is something worth doing and something to spend.

        The plan is loaded rather than rebuilt. That is what makes a restart
        after a crash cheap and correct: everything already done is already
        written down, and a run that comes back finds the work where it left
        it instead of starting the goal again.
        """
        plan = await self.repo.plan_for(owner_id, goal.id)

        if plan is None:
            if goal.planning_attempts >= MAX_PLANNING_ATTEMPTS:
                if run.background:
                    goal.background_runs = max(0, goal.background_runs - 1)
                return await self._planning_retry(owner_id, goal, run)
            try:
                plan = await self._build_plan(
                    owner_id, goal, run, budget, language=language
                )
            except _PlanNotPossible as negative:
                run.stopped_because = "planning_not_possible"
                await self.repo.journal(
                    owner_id, goal.id, kind="planning_not_possible", note=str(negative),
                )
                return await self._stop(goal, run, str(negative))
            except _PlanningStopped as stopped:
                return {"ok": True, "state": str(stopped), "goal": goal.for_human()}
            if plan is None:
                return await self._planning_retry(owner_id, goal, run)
            if run.background:
                goal.background_runs += 1

        if revisit_due:
            outcome = await self._resume_due_wait(
                owner_id, goal, plan, run, budget, language=language
            )
            if outcome is not None:
                return outcome

        while True:
            from agent.source_refresh import changed, refresh
            current = await self.repo.get_goal(owner_id, goal.id)
            if current is None or current.status == "cancelled":
                goal.status, goal.next_run_at = "cancelled", None
                return {"ok": True, "state": "cancelled"}
            if await changed(self.db, goal):
                await refresh(self, goal)
                run.stopped_because = "source_changed"
                return {"ok": True, "state": "source_changed" if goal.is_open else goal.status}
            if (
                current.status == "waiting"
                and current.user_deferred_until
                and current.user_deferred_until > _now().isoformat()
                and not current.requires_user_input
                and not current.requires_user_authority
            ):
                # A person can say "più tardi" while a run is already in
                # flight. The provider call already under way is allowed to
                # finish, but the next loop boundary must honour the new
                # schedule instead of continuing from stale in-memory state.
                goal.status = "waiting"
                goal.next_run_at = current.next_run_at
                goal.user_deferred_until = current.user_deferred_until
                run.stopped_because = "user_deferred"
                return {
                    "ok": True,
                    "state": "waiting",
                    "until": current.next_run_at,
                    "goal": goal.for_human(),
                }
            if run.iterations >= MAX_ITERATIONS:
                run.stopped_because = "iterations"
                return await self._continue_later(owner_id, goal, plan, run, "iterations")

            run.iterations += 1
            invalid_selection = None
            try:
                decision, step = await self._next(
                    owner_id, goal, plan, run, budget, language=language
                )
            except _InvalidNextSelection as invalid:
                # The existing reconsideration owns the next decision and
                # consumes the same run budget as any other changed finding.
                decision, step = "replan", None
                invalid_selection = invalid.context
            source_change = await self._source_change_result(owner_id, goal, run)
            if source_change is not None:
                return source_change

            if decision == "finish":
                return await self._finish(
                    owner_id, goal, plan, run, budget, language=language
                )

            if decision == "stalled":
                return await self._pause(
                    owner_id, goal, plan, run, "il giudizio non era disponibile"
                )

            if decision == "budget":
                run.stopped_because = "cognitive_budget"
                return await self._continue_later(
                    owner_id, goal, plan, run, "cognitive_budget"
                )

            if decision == "wait":
                timing = (step.parameters or {}) if step is not None else {}
                return await self._wait(
                    owner_id, goal, plan, step, run,
                    wait_until=timing.get("wait_until"),
                    minutes=timing.get("wait_minutes"),
                    hours=timing.get("wait_hours"),
                    note=(step.intent if step is not None else ""),
                    model_decision=True,
                )

            if decision == "ask":
                return await self._ask(owner_id, goal, plan, step, run)

            if decision == "replan":
                outcome = await self._reconsider(
                    owner_id, goal, plan, run, budget,
                    what_happened={
                        "what_was_found": for_verification(
                            await self.evidence.for_goal(owner_id, goal.id)
                        ),
                        **(invalid_selection or {
                            "problem": "quello che si è scoperto cambia la strada",
                        }),
                    },
                    language=language,
                )
                if outcome is not None:
                    return outcome
                continue

            if decision == "skip":
                # The model dropped a step because what was found made it
                # pointless. The step stays in the plan, marked — history is
                # not rewritten, and a skipped step is a fact about the run.
                if step is not None:
                    step.status = "skipped"
                    await self.repo.save_plan(plan)
                    await self.repo.journal(
                        owner_id, goal.id, kind="step_skipped", note=step.intent,
                        detail={"step_id": step.id},
                    )
                continue

            if step is None:
                return await self._finish(
                    owner_id, goal, plan, run, budget, language=language
                )

            if step.step_type == "ask_user":
                return await self._ask(owner_id, goal, plan, step, run)

            if step.step_type == "wait":
                timing = step.parameters or {}
                return await self._wait(
                    owner_id, goal, plan, step, run,
                    wait_until=timing.get("wait_until"),
                    minutes=timing.get("wait_minutes"),
                    hours=timing.get("wait_hours"),
                    note=step.intent,
                    model_decision=True,
                )

            # The ceiling is on work done, not on deciding to stop. Checked
            # here rather than at the top of the loop because a goal that has
            # run out of budget must still be able to reach the sentence
            # «this is ready, may I» — a run that spent its allowance and
            # then could not ask would leave somebody waiting on a question
            # nobody was going to put.
            spent = budget.exhausted()
            if spent:
                run.stopped_because = spent
                return await self._continue_later(owner_id, goal, plan, run, spent)

            outcome = await self._do_step(
                owner_id, goal, plan, step, run, budget, language=language
            )
            if outcome is not None:
                return outcome

    async def _owned_memory_prerequisite(self, owner_id, goal, plan: ActionPlan):
        """Add at most one owner-verified read required by a generated draft.

        This is a code-owned, read-only dependency of an already planned
        internal document, never authority for world-changing actions.
        Ambiguous, missing and withdrawn sources still require replanning.
        """
        from agent.memory_sources import memory_source_id, read_memory_previews

        if len(plan.steps) >= MAX_PLAN_STEPS:
            return None
        refs = list(dict.fromkeys(
            str(ref) for ref in (getattr(goal, "source_refs", None) or [])
            if memory_source_id(ref)
        ))
        if len(refs) != 1:
            return None
        # Do not hide a failed read under a newly minted repeated step.
        if any(step.capability_needed == "information.read"
               and step.step_type == "inspect" for step in plan.steps):
            return None
        resolution = await self.capabilities.resolve(owner_id, "information.read")
        if not (resolution.usable and resolution.is_real and not resolution.writes):
            return None
        # The memory must still exist, be active and belong to this owner.
        current = await read_memory_previews(self.db, owner_id, refs, limit=1)
        if len(current) != 1 or current[0].get("ref") != refs[0]:
            return None
        step = ActionStep(
            ordinal=len(plan.steps),
            intent="Leggere la memoria associata prima di preparare il risultato",
            step_type="inspect",
            capability_needed="information.read",
            input_refs=refs,
            expected_result="Evidenza della lettura corrente, con versione e limiti della fonte",
        )
        plan.steps.append(step)
        await self.repo.save_plan(plan)
        await self.repo.journal(
            owner_id, goal.id, kind="planning_prerequisite_added",
            note="Inserita la lettura della memoria già associata al risultato.",
            detail={"step_id": step.id, "capability": "information.read"},
        )
        return step

    async def _next(
        self, owner_id, goal, plan: ActionPlan, run: AgentRun, budget: AgentBudget,
        *, language: str,
    ) -> Tuple[str, Optional[ActionStep]]:
        """
        What is worth doing now — not what comes next in the list.

            A PLAN IS STATE, NOT A SCRIPT.

        Two paths, and the split is a cost decision with a real argument
        behind it. Before anything has been found out, the plan is still its
        own best guess and there is nothing new for a judgement to be about,
        so the first step is taken deterministically and no model is called.
        Once evidence exists it can have made a later step pointless,
        premature or already answered, and walking the list in order would
        carry out a step whose reason evaporated two steps ago.
        """
        pending = [s for s in sorted(plan.steps, key=lambda x: x.ordinal)
                   if s.status == "pending"]
        if not pending:
            return ("finish", None)

        evidence = await self.evidence.for_goal(owner_id, goal.id)
        if not evidence:
            # An evidence-bound preparation is not itself a source read.
            # Before any evidence exists, take an explicitly planned internal
            # read first even when the model put the draft ahead of it.
            # If the planner omitted that prerequisite, reject that
            # impossible selection and let bounded reconsideration repair
            # the route, rather than running a guaranteed-to-fail draft.
            first = pending[0]
            if first.step_type == "prepare" and first.capability_needed == "document.create":
                prerequisite = next((
                    item for item in pending
                    if item.step_type in ("inspect", "research")
                    and (item.capability_needed.endswith(".read")
                         or item.capability_needed == "web.research")
                ), None)
                if prerequisite is not None:
                    return ("execute", prerequisite)
                owned_read = await self._owned_memory_prerequisite(
                    owner_id, goal, plan,
                )
                if owned_read is not None:
                    return ("execute", owned_read)
                await self.repo.journal(
                    owner_id, goal.id, kind="planning_prerequisite_missing",
                    note="La preparazione richiede una lettura reale che il piano non contiene.",
                    detail={"step_id": first.id, "reason": "preparation_sources_required"},
                )
                raise _InvalidNextSelection({
                    "problem": "preparation_sources_required",
                    "result": {"problem": "preparation_sources_required"},
                    "selection": {"candidate_step_ids": [item.id for item in pending[:MAX_PLAN_STEPS]]},
                })
            return ("execute", first)

        if budget.cognitive_calls >= budget.max_cognitive_calls:
            # Out of judgement for this run is NOT the same as out of work.
            # Pending steps still exist; finishing here asks the completion
            # verifier to judge an unfinished plan. Persist and resume later
            # instead, under a fresh bounded budget.
            return ("budget", None)

        from agent.reasoning import choose_next_action

        budget.cognitive_calls += 1
        run.model_calls = budget.cognitive_calls
        answer = await choose_next_action(
            await self._reasoning_goal(owner_id, goal),
            plan=plan.for_ai(),
            candidates=[s.for_ai() for s in pending],
            evidence=for_verification(evidence, required_refs=goal.prepared_sources),
            capabilities=await self.capabilities.available(owner_id),
            clock_context=await _user_clock_context(self.db, owner_id),
            prepared_result=goal.prepared_text or None,
            prepared_source_refs=list(goal.prepared_sources),
            language=language,
        )
        if answer is None:
            return ("stalled", None)

        decision = answer["decision"]
        requested_id = answer.get("step_id")
        chosen = next((s for s in pending if isinstance(requested_id, str) and s.id == requested_id), None)
        if decision in ("execute", "skip") and chosen is None:
            known = next((s for s in plan.steps if isinstance(requested_id, str) and s.id == requested_id), None)
            issue = ("missing_step_id" if requested_id is None or requested_id == "" else
                     "wrong_type" if not isinstance(requested_id, str) else
                     "not_pending" if known else "unknown_step")
            invalid = {"problem": "action_selection_invalid", "selection": {
                "decision": decision, "issue": issue,
                # Only identifiers already in this owned plan enter the
                # diagnosis; an arbitrary model value is not operational data.
                "requested_step_id": known.id if known else None,
                "candidate_step_ids": [s.id for s in pending[:MAX_PLAN_STEPS]],
            }}
            await self.repo.journal(
                owner_id, goal.id, kind="chose_next",
                note="La scelta non identifica un passo ancora eseguibile.",
                detail={"decision": decision, "step_id": "", **invalid},
            )
            raise _InvalidNextSelection(invalid)

        await self._record_situation_outcome(owner_id, goal, answer.get("situation_outcome"), run)
        await self.repo.journal(
            owner_id, goal.id, kind="chose_next",
            note=str(answer.get("reasoning") or "")[:300],
            detail={"decision": decision, "step_id": (chosen.id if chosen else "")},
        )

        if decision in ("execute", "skip"):
            return (decision, chosen)

        if decision == "complete":
            return ("finish", None)

        if decision == "verify":
            return ("finish", None)

        if decision == "ask":
            step = ActionStep(
                ordinal=len(plan.steps),
                intent=str(answer.get("asks") or answer.get("reasoning") or "")[:280],
                step_type="ask_user",
                asks=str(answer.get("asks") or "")[:300],
                ask_kind=(
                    answer.get("ask_kind")
                    if answer.get("ask_kind") in ("knowledge", "authority")
                    else "knowledge"
                ),
            )
            plan.steps.append(step)
            await self.repo.save_plan(plan)
            return ("ask", step)

        if decision == "wait":
            timing = _wait_parameters(answer)
            step = ActionStep(
                ordinal=len(plan.steps),
                intent=str(
                    answer.get("reasoning")
                    or "Aspettare prima di verificare di nuovo l'esito esterno"
                )[:280],
                step_type="wait",
                parameters=timing,
                expected_result="Arriva il momento giusto per verificare di nuovo con evidenza fresca",
            )
            plan.steps.append(step)
            await self.repo.save_plan(plan)
            return ("wait", step)

        return (decision, chosen)

    async def _continue_later(
        self, owner_id, goal, plan: ActionPlan, run: AgentRun, why: str
    ) -> Dict[str, Any]:
        """
        Out of budget, not out of work. Arrange to come back.

            IF THE BUDGET IS SPENT, SCHEDULE A CONTINUATION.

        The alternative — carrying on until it is done — is how one goal
        empties a month's allowance in an afternoon. The alternative to
        *that*, stopping silently, leaves somebody with a goal that says it
        is being handled and nothing that will ever handle it.
        """
        plan.status = "active"
        goal.next_run_at = (_now() + timedelta(hours=CONTINUE_IN_HOURS)).isoformat()
        await self.repo.save_goal(goal)
        await self.repo.save_plan(plan)
        await self.repo.journal(
            owner_id, goal.id, kind="continues_later", note=f"tetto raggiunto: {why}",
            detail={"iterations": run.iterations, "steps": run.steps_executed},
        )
        try:
            from ambient.service import AmbientService

            await AmbientService(self.db).schedule(
                owner_id,
                reason="opportunity_revisit",
                when=_now() + timedelta(hours=CONTINUE_IN_HOURS),
                source_ref=f"goal:{goal.id}",
                # A ceiling is a technical fact, not a judgement anybody made.
                provenance="code_schedule",
            )
        except Exception as e:
            logger.info("agent continuation soft-fail: %s", type(e).__name__)
        return {"ok": True, "state": "in_progress", "goal": goal.for_human()}

    # --- one step ----------------------------------------------------------

    async def _do_step(
        self, owner_id, goal, plan, step: ActionStep, run: AgentRun,
        budget: AgentBudget, *, language: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Run one step. Returns a stopping outcome, or None to keep going.
        """
        step.attempts += 1
        if step.attempts > MAX_STEP_ATTEMPTS:
            step.status = "failed"
            step.note = "provato troppe volte"
            await self.repo.save_plan(plan)
            return await self._reconsider(
                owner_id, goal, plan, run, budget,
                what_happened={"step": step.for_ai(), "problem": "troppi tentativi"},
                language=language,
            )

        may_touch = True
        if step.step_type == "execute":
            prepared_intent = self.executor._intent_for(owner_id, goal, step)
            preparation_problem = _unprepared_effect_reason(prepared_intent)
            if preparation_problem:
                await self.repo.journal(
                    owner_id,
                    goal.id,
                    kind="effect_not_ready",
                    note=preparation_problem,
                    detail={"step_id": step.id, "capability": step.capability_needed},
                )
                return await self._reconsider(
                    owner_id,
                    goal,
                    plan,
                    run,
                    budget,
                    what_happened={
                        "step": step.for_ai(),
                        "problem": "l'azione non è ancora completamente preparata",
                        "what_is_missing": preparation_problem,
                        "instruction": (
                            "Usa ciò che è già stato trovato per completare target e parametri; "
                            "non chiedere autorizzazione finché l'atto concreto non è definito."
                        ),
                    },
                    language=language,
                )

            assessment = await self._authority_for(
                owner_id, goal, step, run, budget, language=language
            )
            if assessment is None:
                return await self._pause(
                    owner_id, goal, plan, run, "il giudizio non era disponibile"
                )

            await self.repo.journal(
                owner_id, goal.id, kind="authority_assessed",
                note=assessment.code_reason or assessment.reasoning,
                detail=assessment.public(),
            )

            if assessment.effective_outcome == "cannot_proceed":
                step.status = "blocked"
                await self.repo.save_plan(plan)
                return await self._reconsider(
                    owner_id, goal, plan, run, budget,
                    what_happened={
                        "step": step.for_ai(),
                        "problem": "non è una cosa che si può fare così",
                        "why": assessment.code_reason or assessment.reasoning,
                    },
                    language=language,
                )

            effective = await self.authority.effective_authority(
                owner_id, prepared_intent, assessment
            )
            # The initial autonomous rollout reads/prepares; effects need a user turn.
            may_touch = effective.may_execute and not run.background
            await self.repo.journal(
                owner_id, goal.id, kind="authority_effective",
                note=effective.reason_code, detail=effective.public(),
            )
            if not may_touch:
                # Do the preparation, then stop with everything ready.
                result = await self.executor.run(
                    owner_id, goal, step, may_touch_the_world=False, budget=budget
                )
                step.status = "blocked"
                step.ask_kind = "authority"
                step.asks = step.intent
                await self.repo.save_plan(plan)
                await self.repo.journal(
                    owner_id, goal.id, kind="awaiting_authority",
                    note=result.observation, detail={"step_id": step.id},
                )
                return await self._awaiting_authority(owner_id, goal, plan, run, step)

        async def _recheck(intent):
            """
            The same question, asked again in the last moment before the world
            is touched. Ten minutes is long enough for somebody to change
            their mind, and an answer computed then is a claim about then.
            """
            from agent.source_refresh import changed
            from agent.models import EffectiveAuthority
            latest = await self.repo.get_goal(owner_id, goal.id)
            if latest is None or not latest.is_open or await changed(self.db, goal):
                return EffectiveAuthority(reason_code="consent_stale")
            return await self.authority.effective_authority(
                owner_id, intent, assessment
            ) if step.step_type == "execute" else None

        result = await self.executor.run(
            owner_id, goal, step, may_touch_the_world=may_touch, budget=budget,
            recheck=_recheck if step.step_type == "execute" else None,
        )
        budget.steps_executed += 1
        run.steps_executed += 1

        # A one-time yes is spent by the thing it was a yes to.
        #
        #     A ONE-TIME YES IS ONE TIME.
        #
        # Looked up rather than taken from the decision, and the difference is
        # the whole bug. Somebody who approves an act *and* allows it for the
        # future produces two things: a consent for this act and a standing
        # permission. The permission is what the executor then proceeds on —
        # it is checked first — so the consent was never the deciding basis
        # and, when the basis was all that got spent, it stayed unspent for
        # ever. Revoke the permission a week later and that forgotten yes
        # silently authorised the same act again.
        #
        # What is true regardless of which basis won: they said yes to this
        # act, and the act happened. The yes is used up.
        #
        # Here rather than inside the executor, and that is a boundary rather
        # than a preference: the executor may ask what it is allowed to do and
        # may never change it, which is why a guard walks that module for any
        # call into the authority service. Spending is a change.
        #
        # Only after the effect actually happened. A request that never
        # reached the provider has used nobody's permission up.
        if (
            step.step_type == "execute"
            and result.status in ("succeeded", "partial")
            and result.error_type not in ("authority_required", "authority_withdrawn")
        ):
            used, why = await self.authority.find_consent(
                owner_id, self.executor._intent_for(owner_id, goal, step)
            )
            if used is not None and why == "one_time_consent":
                await self.authority.spend_consent(owner_id, used.id)

        # A partial result is not a success. It is a step that got somewhere
        # and not all the way, and calling it done is how a plan sails past
        # the thing it was supposed to establish.
        step.status = {
            "succeeded": "succeeded", "partial": "succeeded",
            "failed": "failed", "unavailable": "failed", "waiting": "waiting",
        }[result.status]
        step.actual_result_ref = result.data_ref or (result.result_refs or [""])[0]
        step.note = result.observation[:200]
        plan.current_step = step.ordinal
        await self.repo.save_plan(plan)
        await self.repo.journal(
            owner_id, goal.id, kind="step_done", note=result.observation,
            detail={
                "step_id": step.id,
                "status": result.status,
                "came_from": result.provenance.source_class,
                "really_happened": result.is_real,
                "evidence": len(result.evidence_refs),
            },
        )

        if result.status in ("partial", "failed", "unavailable", "waiting") or result.error_type:
            # Something did not go as the plan assumed — it broke, it was not
            # connected, it found less than was needed. All of those are for
            # the model to weigh, and none of them are for code to route
            # around by trying the same thing again.
            return await self._reconsider(
                owner_id, goal, plan, run, budget,
                what_happened={
                    "step": step.for_ai(),
                    "result": {
                        "status": result.status,
                        "what_happened": result.observation,
                        "problem": result.error_type or None,
                        "worth_retrying": result.retryable,
                        **result.provenance.for_ai(),
                    },
                },
                language=language,
            )
        return None

    async def _authority_for(
        self, owner_id, goal, step: ActionStep, run: AgentRun, budget: AgentBudget,
        *, language: str,
    ) -> Optional[AuthorityAssessment]:
        """
        What kind of act this is, judged then narrowed.

        The model's reading is never used directly: `apply_ceiling` is the
        only thing that produces an effective outcome, and it can only make
        the answer more cautious.
        """
        from agent.reasoning import assess_authority

        resolution = await self.capabilities.resolve(owner_id, step.capability_needed)
        budget.cognitive_calls += 1
        run.model_calls = budget.cognitive_calls
        answer = await assess_authority(
            step.for_ai(),
            goal=goal.for_ai(),
            facts={
                "changes_something_in_the_world": resolution.writes,
                "reaches_somebody_else": resolution.reaches_third_party,
                "involves_money": resolution.financial,
                "how_hard_to_undo": resolution.reversibility,
                "they_have_allowed_this_kind_of_thing": await self.authority.has_grant(
                    owner_id, step.capability_needed
                ),
                "what_they_asked_for": (await self.authority.policy(owner_id)).for_ai(),
            },
            language=language,
        )
        if answer is None:
            return None

        assessment = AuthorityAssessment(
            step_id=step.id,
            capability=step.capability_needed,
            model_outcome=answer["outcome"],
            reasoning=str(answer.get("reasoning") or "")[:400],
            reversibility=(
                answer.get("reversibility")
                if answer.get("reversibility")
                in ("easily", "with_effort", "hardly", "irreversible")
                else "easily"
            ),
            financial_effect=bool(answer.get("financial_effect")),
            external_communication=bool(answer.get("external_communication")),
            third_party_impact=bool(answer.get("third_party_impact")),
            privacy_disclosure=bool(answer.get("privacy_disclosure")),
            legal_effect=bool(answer.get("legal_effect")),
            security_effect=bool(answer.get("security_effect")),
        )
        return await self.authority.apply_ceiling(owner_id, assessment)

    # --- planning and replanning -------------------------------------------

    async def _planning_source_context(
        self, owner_id: str, goal: AutonomousGoal
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """Re-read bounded governed context behind opaque goal refs.

        Goals deliberately persist handles, not copies of somebody's private
        life. Planning still needs to know what those handles mean, including
        after a source correction. Previews preserve ownership, current status
        and limitations; they never replace capability reads as evidence.
        """
        from agent.memory_sources import memory_source_id, read_memory_previews

        source_refs = list(getattr(goal, "source_refs", None) or [])[:8]
        refs = [
            str(ref)
            for ref in source_refs
            if str(ref).startswith("situation:") and ":" in str(ref)
        ]
        out: List[Dict[str, Any]] = []
        unavailable = False
        if refs:
            try:
                from situations.repository import SituationRepository

                repository = SituationRepository(self.db)
                matched = 0
                for ref in refs:
                    sid = ref.split(":", 1)[1]
                    state = await repository.get(owner_id, sid)
                    if state is None:
                        continue
                    out.append({
                        "ref": ref,
                        "source": "situation",
                        **state.context_preview(),
                    })
                    matched += 1
                out = out[:4]
                unavailable = matched < len(refs)
            except Exception as exc:
                logger.info("planning situation context soft-fail goal=%s error=%s", goal.id, type(exc).__name__)
                out, unavailable = [], True
        memory_refs = [ref for ref in source_refs if memory_source_id(ref)]
        if memory_refs:
            try:
                memories = await read_memory_previews(self.db, owner_id, memory_refs)
                out.extend(memories)
                observed = {memory_source_id(row["ref"]) for row in memories}
                unavailable = unavailable or any(memory_source_id(ref) not in observed for ref in memory_refs)
            except Exception as exc:
                logger.info("planning memory context soft-fail goal=%s error=%s", goal.id, type(exc).__name__)
                unavailable = True
        return out, unavailable

    @staticmethod
    def _current_memory_context(goal, source_context, unavailable):
        from agent.memory_sources import memory_source_id

        if not any(memory_source_id(ref) for ref in (getattr(goal, "source_refs", None) or [])):
            return None
        reason = str((getattr(goal, "source_situation", None) or {}).get("memory_refresh_reason") or "")[:300]
        return {
            "sources": [row for row in source_context if row.get("source") == "memory"],
            "unavailable": unavailable,
            "source_update_reason": reason or None,
            "previous_interpretation_may_be_obsolete": bool(reason),
            "goal_origin": str(getattr(goal, "origin", "") or "")[:40],
        }

    async def _build_plan(
        self, owner_id, goal, run: AgentRun, budget: AgentBudget, *, language: str
    ) -> Optional[ActionPlan]:
        from agent.reasoning import make_plan

        budget.cognitive_calls += 1
        run.model_calls = budget.cognitive_calls
        # Charge before the awaited call. A killed process cannot buy an
        # unlimited number of first attempts by losing its in-memory state.
        goal.planning_attempts += 1
        if run.background:
            # advance charges a generic pass before execution for crash
            # recovery. Transfer that charge to the durable planning budget;
            # _work counts it as actual work only after a valid plan exists.
            goal.background_runs = max(0, goal.background_runs - 1)
        await self.repo.save_goal(goal)
        planning_context = await _user_clock_context(self.db, owner_id)
        source_context, source_context_unavailable = await self._planning_source_context(
            owner_id, goal
        )
        situation_context = [row for row in source_context if row.get("source") == "situation"]
        if situation_context:
            planning_context["source_context"] = situation_context
        if source_context_unavailable and any(str(ref).startswith("situation:") for ref in goal.source_refs):
            planning_context["source_context_unavailable"] = True
        memory_context = self._current_memory_context(goal, source_context, source_context_unavailable)
        if memory_context is not None:
            planning_context["current_source_context"] = memory_context

        available = await self.capabilities.available(owner_id)
        error_kind = "invalid_response"
        try:
            answer = await make_plan(
                goal.for_ai(),
                capabilities=available,
                # Current clock and owned governed facts; no copied transcript.
                context=planning_context,
                language=language,
            )
            if answer is None:
                error_kind = "provider_unavailable"
        except Exception as exc:
            # Do not catch cancellation: it leaves the pre-persisted recovery
            # time and attempt budget for the next worker.
            answer = None
            error_kind = "provider_error"
            logger.info("planning unavailable error=%s", type(exc).__name__)

        await self._planning_fence(owner_id, goal, run)
        if not isinstance(answer, dict) or not isinstance(answer.get("steps"), list):
            goal.planning_unavailable = True
            run.stopped_because = error_kind
            return None
        outcome = answer.get("planning_outcome", "plan")
        if outcome == "not_possible" and not answer["steps"] and isinstance(answer.get("reasoning"), str) and answer["reasoning"].strip():
            goal.planning_unavailable = False
            goal.planning_attempts = 0
            raise _PlanNotPossible(answer["reasoning"].strip()[:300])
        if outcome != "plan":
            goal.planning_unavailable = True
            run.stopped_because = "invalid_response"
            return None

        steps: List[ActionStep] = []
        for ordinal, raw in enumerate(answer["steps"][:MAX_PLAN_STEPS]):
            errors = []
            try:
                step = self._read_step(raw, ordinal, validation_errors=errors)
            except (TypeError, ValueError):
                step = None
            if step is None:
                # The declaration stays rejected. Keep only code-owned field
                # names and issues so a durable retry can be diagnosed without
                # retaining the model's possibly sensitive invalid values.
                await self.repo.journal(
                    owner_id, goal.id, kind="planning_protocol_invalid",
                    note="Il piano proposto non rispettava il formato atteso; nessun passo è stato salvato.",
                    detail={"run_id": run.id, "attempt": goal.planning_attempts, "validation_errors": [{
                        "index": ordinal, **(errors[0] if errors else {
                            "field": "step", "issue": "invalid_shape",
                        }),
                    }]},
                )
                steps = []
                break
            steps.append(step)
        if not steps:
            goal.planning_unavailable = True
            run.stopped_because = "invalid_response"
            return None

        plan = ActionPlan(
            goal_id=goal.id,
            owner_id=owner_id,
            status="active",
            plan_summary=str(answer.get("plan_summary") or "")[:400],
            expected_outcome=str(answer.get("expected_outcome") or "")[:400],
            assumptions=[str(a)[:200] for a in answer.get("assumptions", [])][:6]
            if isinstance(answer.get("assumptions"), list) else [],
            known_constraints=[
                str(c)[:200] for c in answer.get("known_constraints", [])
            ][:6] if isinstance(answer.get("known_constraints"), list) else [],
            steps=steps[:MAX_PLAN_STEPS],
        )
        await self.repo.save_plan(plan)
        goal.planning_attempts = 0
        goal.planning_unavailable = False
        await self.repo.save_goal(goal)
        await self.repo.journal(
            owner_id, goal.id, kind="plan_made", note=plan.plan_summary,
            detail={"steps": len(plan.steps)},
        )
        return plan

    async def _planning_fence(self, owner_id, goal, run: AgentRun) -> None:
        """Do not publish a slow planning response after its source changed."""
        from agent.source_refresh import changed, refresh

        latest = await self.repo.get_goal(owner_id, goal.id)
        if latest is None or not latest.is_open:
            goal.status = latest.status if latest else "cancelled"
            goal.next_run_at = None
            run.stopped_because = goal.status
            raise _PlanningStopped(goal.status)
        if await changed(self.db, goal):
            await refresh(self, goal)
            state = "source_changed" if goal.is_open else goal.status
            run.stopped_because = state
            raise _PlanningStopped(state)
        if latest.user_deferred_until and latest.user_deferred_until > _now().isoformat():
            goal.status = latest.status
            goal.next_run_at = latest.next_run_at
            goal.user_deferred_until = latest.user_deferred_until
            goal.background_runs = latest.background_runs
            run.stopped_because = "user_deferred"
            raise _PlanningStopped("user_deferred")

    async def _planning_retry(self, owner_id, goal, run: AgentRun) -> Dict[str, Any]:
        """Keep failed planning recoverable without claiming work was done."""
        try:
            await self._planning_fence(owner_id, goal, run)
        except _PlanningStopped as stopped:
            return {"ok": True, "state": str(stopped), "goal": goal.for_human()}
        goal.status = "active"
        goal.planning_unavailable = True
        exhausted = goal.planning_attempts >= MAX_PLANNING_ATTEMPTS
        # Guard unusual legacy/mock callers too; a zero-attempt failure still
        # consumes one retry slot rather than spinning at the initial delay.
        goal.planning_attempts = max(1, goal.planning_attempts)
        delay = None if exhausted else PLANNING_RETRY_SECONDS[goal.planning_attempts - 1]
        goal.next_run_at = None if delay is None else (_now() + timedelta(seconds=delay)).isoformat()
        goal.rationale = (
            "Preparazione sospesa: non riesco ancora a formulare un piano affidabile. "
            "Il lavoro resta aperto; puoi riprovare e lo rivaluterò se cambiano le informazioni."
            if exhausted else
            "Non riesco ancora a preparare il lavoro per un problema temporaneo. Riproverò automaticamente."
        )
        await self.repo.save_goal(goal)
        if not goal.is_open:
            return {"ok": True, "state": goal.status}
        state = "planning_unavailable" if exhausted else "planning_retry_scheduled"
        await self.repo.journal(
            owner_id, goal.id, kind=state, note=goal.rationale,
            detail={"attempts": goal.planning_attempts, "error": run.stopped_because,
                    "retry_at": goal.next_run_at},
        )
        run.stopped_because = state
        if goal.next_run_at:
            await self._schedule_planning_retry(owner_id, goal)
        return {"ok": True, "state": state if goal.is_open else goal.status,
                "goal": goal.for_human()}

    async def _schedule_planning_retry(self, owner_id, goal) -> None:
        """An accelerator; next_run_at remains the durable recovery contract."""
        from ambient.service import AmbientService
        try:
            await AmbientService(self.db).schedule(
                owner_id, reason="opportunity_revisit",
                when=datetime.fromisoformat(goal.next_run_at),
                source_ref=f"goal:{goal.id}", provenance="code_schedule",
            )
        except Exception as exc:
            logger.info("planning wake soft-fail: %s", type(exc).__name__)
        latest = await self.repo.get_goal(owner_id, goal.id)
        if latest is None or not latest.is_open:
            goal.status = latest.status if latest else "cancelled"
            goal.next_run_at = None
            from ambient.repository import AmbientRepository
            await AmbientRepository(self.db).cancel_for(owner_id, source_ref=f"goal:{goal.id}")

    async def _reasoning_goal(self, owner_id, goal):
        """Carry current source context across planning, decisions and verification."""
        from agent.memory_sources import memory_source_id

        payload = goal.for_ai()
        refs = getattr(goal, "source_refs", None) or []
        situation_refs = any(str(ref).startswith("situation:") for ref in refs)
        if not situation_refs and not any(memory_source_id(ref) for ref in refs):
            return payload
        context, unavailable = await self._planning_source_context(owner_id, goal)
        if situation_refs and (context or unavailable):
            payload["source_context"] = [row for row in context if row.get("source") == "situation"]
            payload["source_context_unavailable"] = unavailable
        memory_context = self._current_memory_context(goal, context, unavailable)
        if memory_context is not None:
            payload["current_source_context"] = memory_context
        return payload

    @staticmethod
    def _read_step(raw: Any, ordinal: int, *, validation_errors=None) -> Optional[ActionStep]:
        raw, error = _step_declaration(raw)
        if error:
            if validation_errors is not None:
                validation_errors.append(error)
            return None
        step_type = raw["step_type"]
        intent = raw["intent"].strip()
        ask_kind = raw.get("ask_kind")
        return ActionStep(
            ordinal=ordinal,
            intent=intent[:280],
            step_type=step_type,  # type: ignore[arg-type]
            capability_needed=str(raw.get("capability_needed") or "")[:60],
            input_refs=[str(ref)[:160] for ref in (raw.get("input_refs") or []) if isinstance(ref, str)][:8]
            if isinstance(raw.get("input_refs"), list) else [],
            expected_result=str(raw.get("expected_result") or "")[:300],
            external_effect=bool(raw.get("external_effect")),
            effect_type=(
                raw.get("effect_type")
                if raw.get("effect_type") in (
                    "create", "modify", "cancel", "send", "transfer", "publish", "remove"
                )
                else "create"
            ),
            effect_target=str(raw.get("effect_target") or "")[:200],
            reaches_somebody_else=bool(raw.get("reaches_somebody_else")),
            parameters=(
                raw.get("parameters") if isinstance(raw.get("parameters"), dict) else {}
            ),
            reversibility=(
                raw.get("reversibility")
                if raw.get("reversibility")
                in ("easily", "with_effort", "hardly", "irreversible")
                else "easily"
            ),
            asks=str(raw.get("asks") or "")[:300],
            ask_kind=ask_kind if ask_kind in ("knowledge", "authority") else None,
        )

    async def _reconsider(
        self, owner_id, goal, plan: ActionPlan, run: AgentRun, budget: AgentBudget,
        *, what_happened: Dict[str, Any], language: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Something happened. Change as little of the plan as accounts for it.
        """
        from agent.reasoning import reconsider
        source_change = await self._source_change_result(owner_id, goal, run)
        if source_change is not None:
            return source_change

        if budget.cognitive_calls >= budget.max_cognitive_calls:
            # Nothing left to think with. Stopping here is honest; carrying
            # on with the old plan after it has just been contradicted is not.
            return await self._continue_later(
                owner_id, goal, plan, run, "cognitive_calls"
            )

        budget.cognitive_calls += 1
        run.model_calls = budget.cognitive_calls
        run.replans += 1
        answer = await reconsider(
            await self._reasoning_goal(owner_id, goal),
            plan=plan.for_ai(),
            what_happened=what_happened,
            capabilities=await self.capabilities.available(owner_id),
            clock_context=await _user_clock_context(self.db, owner_id),
            language=language,
        )
        if answer is None:
            return await self._pause(owner_id, goal, plan, run, "il giudizio non era disponibile")

        source_change = await self._source_change_result(owner_id, goal, run)
        if source_change is not None:
            return source_change

        decision = answer["decision"]
        fresh = []
        if decision == "modify":
            errors = []
            raw_steps = answer.get("revised_steps")
            if not isinstance(raw_steps, list):
                errors.append({"field": "revised_steps", "issue": "wrong_type"})
            elif not raw_steps:
                errors.append({"field": "revised_steps", "issue": "empty"})
            elif len(raw_steps) > MAX_PLAN_STEPS - len(plan.steps):
                errors.append({"field": "revised_steps", "issue": "step_limit"})
            else:
                for index, raw in enumerate(raw_steps):
                    step_errors = []
                    try:
                        step = self._read_step(raw, len(plan.steps) + index, validation_errors=step_errors)
                    except (TypeError, ValueError):
                        step = None
                    if step is None:
                        errors.append({"index": index, **(step_errors[0] if step_errors else {
                            "field": "step", "issue": "invalid_shape",
                        })})
                    else:
                        fresh.append(step)
            replace = answer.get("replace_step_ids", [])
            if not isinstance(replace, list) or any(type(ref) is not str for ref in replace):
                errors.append({"field": "replace_step_ids", "issue": "wrong_type"})
            if errors:
                # A partial route is not the model's proposed route. Validate
                # the whole modification before retiring history, publishing
                # an assessment or calling this a successfully revised plan.
                run.stopped_because = "replan_protocol_invalid"
                note = "La revisione proposta non rispettava il formato atteso; nessun passo è stato modificato."
                await self.repo.journal(owner_id, goal.id, kind="replan_protocol_invalid", note=note,
                    detail={"validation_errors": errors[:MAX_PLAN_STEPS + 1]})
                result = await self._pause(owner_id, goal, plan, run, note)
                result["reason"] = "replan_protocol_invalid"
                return result

        await self._record_situation_outcome(owner_id, goal, answer.get("situation_outcome"), run)

        note = str(answer.get("reasoning") or "")[:300]
        plan.revisions += 1
        await self.repo.journal(
            owner_id, goal.id, kind="replanned", note=note, detail={"decision": decision}
        )

        if decision == "continue":
            await self.repo.save_plan(plan)
            return None

        if decision == "modify":
            # A replan is not an append-only log. If the model explicitly says
            # a pending step has been replaced, retire exactly that step so the
            # obsolete route cannot wake up again after the revised one succeeds.
            # Completed work is immutable and unknown ids are ignored.
            pending_ids = {
                step.id for step in plan.steps
                if step.status in ("pending", "blocked", "waiting")
            }
            replace_ids = {
                str(step_id) for step_id in (answer.get("replace_step_ids") or [])
                if str(step_id) in pending_ids
            }
            for old in plan.steps:
                if old.id in replace_ids:
                    old.status = "skipped"
                    old.note = "Sostituito dal piano aggiornato."

            # The history stays: finished steps are not rewritten, and what
            # was learned is not thrown away.
            plan.steps.extend(fresh)
            await self.repo.save_plan(plan)
            return None

        if decision == "wait":
            return await self._wait(
                owner_id, goal, plan, None, run,
                wait_until=answer.get("wait_until"),
                minutes=answer.get("wait_minutes"),
                hours=answer.get("wait_hours"),
                note=note,
                model_decision=True,
            )

        if decision == "ask":
            step = ActionStep(
                ordinal=len(plan.steps),
                intent=str(answer.get("asks") or note)[:280],
                step_type="ask_user",
                asks=str(answer.get("asks") or "")[:300],
                ask_kind=(
                    answer.get("ask_kind")
                    if answer.get("ask_kind") in ("knowledge", "authority")
                    else "knowledge"
                ),
            )
            plan.steps.append(step)
            await self.repo.save_plan(plan)
            return await self._ask(owner_id, goal, plan, step, run)

        if decision == "abandon":
            return await self._close(owner_id, goal, plan, run, "abandoned", note)

        return await self._finish(owner_id, goal, plan, run, budget, language=language)

    # --- ends --------------------------------------------------------------

    async def _source_change_result(self, owner_id, goal, run):
        """A source correction outranks an in-flight planning judgement."""
        from agent.source_refresh import changed, refresh
        # Partial domain payloads do not declare the persisted goal contract.
        if not isinstance(goal, AutonomousGoal):
            return None
        if not await changed(self.db, goal):
            return None
        await refresh(self, goal)
        run.stopped_because = "source_changed"
        return {"ok": True, "state": "source_changed" if goal.is_open else goal.status,
                "goal": goal.for_human()}

    async def _finish(
        self, owner_id, goal, plan: ActionPlan, run: AgentRun, budget: AgentBudget,
        *, language: str,
    ) -> Dict[str, Any]:
        """
        Every step done. That is not the same as the outcome being true.

        Two judgements, and they are not the same kind of thing. The model is
        shown what was actually found — with each piece saying where it came
        from and how old it is — and decides whether the outcome holds. Then
        code decides whether anything real is behind that conclusion, and
        that second decision cannot be argued with because it is never asked.
        """
        from agent.reasoning import verify_goal

        source_change = await self._source_change_result(owner_id, goal, run)
        if source_change is not None:
            return source_change

        evidence = await self.evidence.for_goal(owner_id, goal.id)
        intents = await self.executor.intents_for(owner_id, goal.id)
        receipts = await self.executor.receipts_for(owner_id, goal.id)

        # An autonomous read-only investigation owes the person a concrete
        # result. Reading sources alone is not a delivered recommendation.
        # This is a completion contract, not a new decision about relevance.
        if (goal.origin == "agent_initiated" and goal.opportunity_id and not intents
                and not receipts and real_support(evidence) and not goal.prepared_text):
            if budget.exhausted() or budget.cognitive_calls + 2 >= budget.max_cognitive_calls:
                return await self._continue_later(owner_id, goal, plan, run, "result_budget")
            result_step = ActionStep(ordinal=len(plan.steps), step_type="prepare", capability_needed="document.create",
                intent="Consegna le conclusioni utili, con confronto, limiti e conseguenze sostenuti dalle fonti; non il resoconto della lettura.",
                expected_result=goal.desired_outcome[:300])
            plan.steps.append(result_step)
            await self.repo.save_plan(plan)
            result = await self.executor.run(owner_id, goal, result_step,
                may_touch_the_world=False, budget=budget)
            result_step.status = "succeeded" if result.status == "succeeded" else "failed"
            result_step.actual_result_ref = result.data_ref or (result.result_refs or [""])[0]
            result_step.note = result.observation[:200]
            result_step.attempts = 1
            run.steps_executed += 1
            budget.steps_executed += 1
            await self.repo.save_plan(plan)
            if result.status != "succeeded" or not goal.prepared_text:
                source_change = await self._source_change_result(owner_id, goal, run)
                if source_change is not None:
                    return source_change
                # This is the same preparation as a normal plan step. Its
                # failure must reach reconsideration with the actual cause,
                # not disappear behind a generic pause in the final path.
                problem = result.error_type or "preparation_result_missing"
                await self.repo.journal(
                    owner_id, goal.id, kind="step_done", note=result.observation,
                    detail={"step_id": result_step.id, "status": result.status,
                            "came_from": result.provenance.source_class,
                            "really_happened": result.is_real,
                            "evidence": len(result.evidence_refs),
                            "error_type": problem, "retryable": result.retryable},
                )
                outcome = await self._reconsider(
                    owner_id, goal, plan, run, budget,
                    what_happened={"step": result_step.for_ai(), "result": {
                        "status": result.status if result.status != "succeeded" else "unavailable",
                        "what_happened": result.observation, "problem": problem,
                        "worth_retrying": result.retryable, **result.provenance.for_ai(),
                    }}, language=language,
                )
                if outcome is not None:
                    return outcome
                # A revised/continued plan is already saved. advance wrote
                # its continuation before this pass; do not add another loop.
                return await self._pause(owner_id, goal, plan, run,
                    "La preparazione non è riuscita; ho rivalutato il piano.")
            evidence = await self.evidence.for_goal(owner_id, goal.id)

        if budget.cognitive_calls >= budget.max_cognitive_calls:
            return await self._continue_later(
                owner_id, goal, plan, run, "cognitive_calls"
            )

        budget.cognitive_calls += 1
        run.model_calls = budget.cognitive_calls
        from agent.prepared_review import capture_prepared_result
        prepared_snapshot = capture_prepared_result(goal)
        answer = await verify_goal(
            await self._reasoning_goal(owner_id, goal),
            evidence={
                "what_was_found": for_verification(evidence, required_refs=list(prepared_snapshot.sources) if prepared_snapshot else []),
                "steps": [s.for_ai() for s in plan.steps],
                "what_was_prepared": intents,
                "prepared_result": prepared_snapshot.text if prepared_snapshot else None,
                "prepared_source_refs": list(prepared_snapshot.sources) if prepared_snapshot else [],
                "local_clock": await _user_clock_context(self.db, owner_id),
                # What services said back, and the warning that goes with it.
                "what_the_services_said": [
                    ExecutionReceipt.model_validate(r).for_ai() for r in receipts
                ],
            },
            language=language,
        )
        if answer is None:
            return await self._pause(owner_id, goal, plan, run, "la verifica non era disponibile")

        source_change = await self._source_change_result(owner_id, goal, run)
        if source_change is not None:
            return source_change

        await self._record_situation_outcome(owner_id, goal, answer.get("situation_outcome"), run)

        verification = GoalVerification(
            goal_id=goal.id,
            outcome=answer["outcome"],
            reasoning=str(answer.get("reasoning") or "")[:400],
            what_is_missing=str(answer.get("what_is_missing") or "")[:300],
            revisit_in_hours=answer.get("revisit_in_hours"),
        )
        if (verification.outcome in ("partially_achieved", "uncertain")
                and prepared_snapshot is not None and not intents and not receipts):
            from agent.prepared_review import (
                current_prepared_result, persist_prepared_review, PreparedReviewUnavailable,
            )
            if not await persist_prepared_review(
                self.db, owner_id, goal, prepared_snapshot, verification,
            ):
                # The verifier saw a prior artifact. Do not attach its critique
                # or replan against it, and do not let advance save that older
                # in-memory draft over a newer preparation or user control.
                current = await current_prepared_result(self.db, owner_id, goal.id)
                if current is None:
                    raise PreparedReviewUnavailable("prepared_goal_missing")
                for field in type(current.goal).model_fields:
                    setattr(goal, field, getattr(current.goal, field))
                run.stopped_because = "prepared_result_changed"
                return {"ok": True, "state": "in_progress" if goal.is_open else goal.status,
                        "goal": goal.for_human()}
        await self.repo.journal(
            owner_id, goal.id, kind="verified", note=verification.reasoning,
            detail={
                "outcome": verification.outcome,
                "evidence": len(evidence),
                "anything_real": real_support(evidence),
            },
        )

        if verification.outcome == "achieved":
            if goal.source_kind in ("situation_initial_review", "situation_followup"):
                from situations.outcomes import current_outcome, moment
                assessment = await current_outcome(self.db, owner_id, goal)
                if (not assessment or assessment["status"] != "action_now"
                        or moment(assessment["assessed_at"]) < moment(run.at)):
                    await self.repo.journal(
                        owner_id, goal.id, kind="completion_refused",
                        note="La lettura delle fonti non è ancora una valutazione utile del momento d'azione.",
                        detail={"model_said": "achieved", "reason": "situation_action_assessment_required"},
                    )
                    return await self._pause(
                        owner_id, goal, plan, run,
                        "Manca ancora una valutazione attuale di quando agire; il solo controllo delle condizioni non conclude il lavoro.",
                    )
            refusal = _why_not_complete(evidence, intents, receipts)
            if refusal:
                # The gate. Two ways of not being allowed to finish, and both
                # are the same mistake wearing different clothes: concluding
                # that the world changed from something that did not touch
                # it. This is the debt Sprint 1 closed with, and it is paid
                # in code rather than in a prompt, because a prompt can be
                # talked round and a boolean cannot.
                await self.repo.journal(
                    owner_id, goal.id, kind="completion_refused", note=refusal,
                    detail={"model_said": "achieved", "evidence": len(evidence)},
                )
                logger.info(
                    "agent completion refused goal=%s: %s", goal.id, refusal
                )
                return await self._pause(
                    owner_id, goal, plan, run,
                    "quello che è stato fatto non prova che sia davvero risolto",
                )

            internal_preparation = prepared_snapshot if not intents and not receipts else None
            if internal_preparation is None:
                await self.executor.mark_verified(owner_id, goal.id)
            result = await self._close(
                owner_id, goal, plan, run, "completed", verification.reasoning,
                visibility_budget=budget, language=language,
                **({"prepared_snapshot": internal_preparation} if internal_preparation else {}),
            )
            if result.get("state") == "completed" and not result.get("verification_superseded"):
                await self._observe_life_change(owner_id, goal, verification, evidence)
            return result

        if verification.outcome in ("waiting_for_external_result", "needs_followup"):
            return await self._wait(
                owner_id, goal, plan, None, run,
                hours=verification.revisit_in_hours or 12,
                note=verification.reasoning,
                model_decision=_explicit_wait_target(wait_hours=verification.revisit_in_hours),
            )

        if verification.outcome == "not_achieved":
            return await self._close(
                owner_id, goal, plan, run, "failed", verification.reasoning
            )

        # An incomplete internal result may need a different preparation,
        # not repeated verification of the same text on every wake. Retain
        # the review as fallible feedback; only the existing reconsideration
        # can choose a repair, and only a real preparation may change the draft.
        if (verification.outcome in ("partially_achieved", "uncertain")
                and goal.prepared_text and not intents and not receipts):
            from agent.preparation import remember_preparation_feedback

            observation = await remember_preparation_feedback(
                self.db, owner_id, goal,
                reason="\n".join(value for value in (
                    verification.what_is_missing, verification.reasoning,
                ) if value),
                origin="goal_verification",
            )
            outcome = await self._reconsider(
                owner_id, goal, plan, run, budget,
                what_happened={"result": {
                    "status": "partial" if verification.outcome == "partially_achieved" else "unavailable",
                    "verification_outcome": verification.outcome,
                    "what_is_missing": verification.what_is_missing,
                    "reasoning": verification.reasoning,
                    "what_happened": observation or "La verifica non ha confermato la bozza; il giudizio resta da valutare contro le fonti.",
                    "problem": "prepared_result_verification_incomplete",
                    "worth_retrying": True,
                }}, language=language,
            )
            if outcome is not None:
                return outcome

        # A revised plan and its existing continuation are already durable.
        # Other partial/uncertain outcomes retain the previous pause behavior.
        return await self._pause(
            owner_id, goal, plan, run,
            verification.what_is_missing or verification.reasoning,
        )

    async def _ask(
        self, owner_id, goal, plan: ActionPlan, step: ActionStep, run: AgentRun
    ) -> Dict[str, Any]:
        step.status = "blocked"
        plan.status = "waiting"
        goal.status = "waiting"
        goal.requires_user_input = step.ask_kind == "knowledge"
        goal.requires_user_authority = step.ask_kind == "authority"
        await self.repo.save_plan(plan)
        await self.repo.save_goal(goal)
        await self.repo.journal(
            owner_id, goal.id, kind="asked", note=step.asks or step.intent,
            detail={"kind": step.ask_kind},
        )
        await self._note_ambient(owner_id, "agent_waiting", goal)
        return {
            "ok": True,
            "state": "waiting_for_person",
            "asks": step.asks or step.intent,
            "kind": step.ask_kind,
            "goal": goal.for_human(),
        }

    async def _awaiting_authority(
        self, owner_id, goal, plan: ActionPlan, run: AgentRun, step: ActionStep
    ) -> Dict[str, Any]:
        plan.status = "waiting"
        goal.status = "waiting"
        goal.requires_user_authority = True
        intent = self.executor._intent_for(owner_id, goal, step)
        question = _authority_question(intent)
        step.asks = question
        await self.repo.save_plan(plan)
        await self.repo.save_goal(goal)
        await self.repo.journal(
            owner_id, goal.id, kind="awaiting_authority", note=question,
            detail={
                "step_id": step.id,
                "effect_hash": intent.effect_hash,
                "effect_type": intent.effect.effect_type,
            },
        )
        await self._note_ambient(owner_id, "agent_preparation_completed", goal)
        return {
            "ok": True,
            "state": "awaiting_authority",
            "asks": question,
            "kind": "authority",
            "goal": goal.for_human(),
        }

    async def _resume_due_wait(
        self, owner_id, goal, plan: ActionPlan, run: AgentRun, budget: AgentBudget,
        *, language: str,
    ) -> Optional[Dict[str, Any]]:
        """Resume a planned external checkpoint without treating time as evidence."""
        waiting_steps = [s for s in plan.steps if s.status == "waiting"]
        for step in waiting_steps:
            step.status = "succeeded" if step.step_type == "wait" else "pending"
            if step.step_type == "wait":
                step.note = "l'intervallo di attesa è trascorso"

        plan.status = "active"
        goal.status = "active"
        # advance already persisted a technical retry before this wake. Keep
        # it if judgement is unavailable; a new wait, person request, closure
        # or the background cap replaces/clears it through the usual paths.
        goal.user_deferred_until = None
        await self.repo.save_plan(plan)
        await self.repo.save_goal(goal)
        await self.repo.journal(
            owner_id,
            goal.id,
            kind="external_checkpoint_due",
            note="È arrivato il momento di verificare di nuovo ciò che ORA stava aspettando.",
            detail={"waiting_steps": [s.id for s in waiting_steps]},
        )

        if any(s.status == "pending" for s in plan.steps):
            return None

        outcome = await self._reconsider(
            owner_id,
            goal,
            plan,
            run,
            budget,
            what_happened={
                "problem": "scheduled_external_checkpoint",
                "what_happened": (
                    "È trascorso l'intervallo scelto per aspettare un esito esterno. "
                    "Il tempo trascorso non prova che l'esito sia avvenuto."
                ),
                "instruction": (
                    "Prima di concludere, aggiungi il più piccolo passo reale che "
                    "possa rileggere una fonte autorizzata pertinente. Se nessuna "
                    "fonte può ridurre l'incertezza adesso, aspetta ancora. Non "
                    "considerare il timer come evidenza del risultato."
                ),
            },
            language=language,
        )
        if outcome is not None:
            return outcome

        if not any(s.status == "pending" for s in plan.steps):
            return await self._wait(
                owner_id, goal, plan, None, run, hours=6,
                note="Il checkpoint è arrivato ma non c'è ancora nuova evidenza da verificare.",
            )
        return None


    async def _wait(
        self, owner_id, goal, plan: ActionPlan, step: Optional[ActionStep],
        run: AgentRun, *, hours: Optional[int] = None,
        minutes: Optional[int] = None, wait_until: Optional[str] = None,
        note: str = "",
        model_decision: bool = False,
    ) -> Dict[str, Any]:
        """
        Depend on something that has not happened, and arrange one exact recheck.

            NO POLLING. ONE DUE INSTANT.

        Situation checkpoints are confirmed against the persisted wake, including
        Ambient's time bounds and an equivalent alarm that was already present.
        """
        now = _now()
        situation_wait = goal.source_kind in ("situation_initial_review", "situation_followup")

        async def interrupted():
            # User cancellation does not have to alter the Situation. The goal
            # itself must still be open before and after scheduling a wake.
            latest = await self.repo.get_goal(owner_id, goal.id)
            if latest is None or not latest.is_open:
                if latest:
                    for field in type(goal).model_fields:
                        setattr(goal, field, getattr(latest, field))
                else:
                    goal.status, goal.next_run_at = "cancelled", None
                from ambient.repository import AmbientRepository
                await AmbientRepository(self.db).cancel_for(owner_id, source_ref=f"goal:{goal.id}")
                return {"ok": False, "state": latest.status if latest else "goal_closed"}
            from agent.source_refresh import changed, refresh
            if await changed(self.db, goal):
                await refresh(self, goal)
                # A direct cancellation can also arrive while source refresh
                # is saving its revised goal and arranging a replacement wake.
                latest = await self.repo.get_goal(owner_id, goal.id)
                if latest is None or not latest.is_open:
                    if latest:
                        for field in type(goal).model_fields:
                            setattr(goal, field, getattr(latest, field))
                    else:
                        goal.status, goal.next_run_at = "cancelled", None
                    from ambient.repository import AmbientRepository
                    await AmbientRepository(self.db).cancel_for(owner_id, source_ref=f"goal:{goal.id}")
                return {"ok": False, "state": "source_changed" if goal.is_open else goal.status}
            return None

        if situation_wait:
            stopped = await interrupted()
            if stopped:
                return stopped
        due, total_minutes = _wait_schedule(
            wait_until=wait_until,
            wait_minutes=minutes,
            wait_hours=hours,
            now=now,
        )
        if situation_wait:
            from situations.outcomes import current_outcome, moment
            assessment = await current_outcome(self.db, owner_id, goal)
            if assessment:
                # A useful estimate cannot lose its supporting live evidence
                # while the only next read is hours later. This bounds a
                # re-evaluation, never the estimated physical completion time.
                expiry = moment(assessment["valid_until"])
                if expiry:
                    due = min(due, max(now + timedelta(seconds=30), expiry - timedelta(seconds=30)))
                    total_minutes = max(1, math.ceil((due - now).total_seconds() / 60))
        for_hours = (
            total_minutes // 60
            if total_minutes % 60 == 0
            else round(total_minutes / 60, 4)
        )
        if step is not None:
            step.status = "waiting"
        plan.status = "waiting"
        goal.status = "waiting"
        goal.background_runs = 0
        # Technical retries and a wait with no source observation remain an
        # initial assessment. Promotion requires an explicit, valid model
        # time and real, current evidence owned by this same goal.
        promote = False
        if goal.source_kind == "situation_initial_review" and model_decision and note.strip():
            explicit_time = _explicit_wait_target(
                wait_until=wait_until, wait_minutes=minutes, wait_hours=hours, now=now,
            )
            evidence = await self.evidence.for_goal(owner_id, goal.id)
            supporting = [e for e in evidence if e.provenance.freshness != "stale"
                          and (e.provenance.capability != "web.research"
                               or (e.provenance.research_sufficient is True
                                   and (research_until := _aware_wait_until(e.provenance.research_valid_until))
                                   and research_until > now))
                          and any(not ref.startswith(("situation:", "goal:", "plan:", "agent:"))
                                  for ref in e.provenance.source_refs)]
            from situations.outcomes import weather_evidence_current
            supporting = [e for e in supporting if e.provenance.capability != "weather.read"
                          or await weather_evidence_current(self.db, owner_id, goal, [e], now=now)]
            promote = explicit_time and total_minutes <= 72 * 60 and real_support(supporting)
        if promote:
            from ambient.repository import AmbientRepository
            await AmbientRepository(self.db).cancel_for(owner_id, source_ref=f"goal:{goal.id}")
            goal.source_kind = "situation_followup"
            goal.rationale = note[:300]
        goal.next_run_at = due.isoformat()
        await self.repo.save_plan(plan)
        await self.repo.save_goal(goal)

        if situation_wait:
            stopped = await interrupted()
            if stopped:
                return stopped
            # save_goal preserves a concurrent explicit user defer. Its durable
            # target is stronger than the older model decision in this run.
            latest = await self.repo.get_goal(owner_id, goal.id)
            if latest and latest.user_deferred_until and latest.user_deferred_until > _now().isoformat():
                for field in type(goal).model_fields:
                    setattr(goal, field, getattr(latest, field))
                return {"ok": False, "state": "user_deferred", "goal": goal.for_human()}

        scheduled = None
        schedule_started = _now()
        try:
            from ambient.service import AmbientService

            scheduled = await AmbientService(self.db).schedule(
                owner_id,
                reason="opportunity_revisit",
                when=due,
                source_ref=f"goal:{goal.id}",
                provenance="model",
            )
        except Exception as e:
            logger.info("agent wake soft-fail: %s", type(e).__name__)

        if situation_wait:
            schedule_finished = _now()
            stopped = await interrupted()
            if stopped:
                return stopped
            wake_query = {
                "owner_id": owner_id, "source_ref": f"goal:{goal.id}",
                "reason": "opportunity_revisit", "status": {"$in": ["pending", "claimed"]},
                "scheduled_for": {"$gt": _now().isoformat()},
            }
            if scheduled is not None:
                wake_query["id"] = scheduled.id
            else:
                # None can mean either a failed write or minute-bucket dedup.
                # Match only the bucket(s) Ambient could have scheduled during
                # this call, so an older assessment wake cannot prove a recheck.
                from ambient.service import MAX_HOLD_HOURS
                earliest = max(schedule_started + timedelta(seconds=30),
                               min(due, schedule_started + timedelta(hours=MAX_HOLD_HOURS)))
                latest = max(schedule_finished + timedelta(seconds=30),
                             min(due, schedule_finished + timedelta(hours=MAX_HOLD_HOURS)))
                wake_query["scheduled_for"].update({
                    "$gte": earliest.replace(second=0, microsecond=0).isoformat(),
                    "$lt": (latest.replace(second=0, microsecond=0) + timedelta(minutes=1)).isoformat(),
                })
            try:
                wake = await self.db.ambient_wakes.find_one(wake_query, {"_id": 0}, sort=[("scheduled_for", 1)])
            except Exception as exc:
                logger.info("agent wake readback soft-fail: %s", type(exc).__name__)
                wake = None
            actual_due = _aware_wait_until((wake or {}).get("scheduled_for"))
            if actual_due is None:
                await self.repo.journal(
                    owner_id, goal.id, kind="waiting_recovery_pending",
                    note="La richiesta di attesa è salvata; manca la conferma della wake futura.",
                )
                return {"ok": False, "state": "recovery_pending", "goal": goal.for_human()}

            # Update only this still-open wait. A concurrent cancellation/defer
            # must not be undone while adopting Ambient's actual instant.
            aligned = await self.db.agent_goals.update_one(
                {"id": goal.id, "owner_id": owner_id,
                 "status": {"$in": ["proposed", "active", "waiting"]},
                 "next_run_at": goal.next_run_at,
                 "source_situation": goal.source_situation},
                {"$set": {"next_run_at": actual_due.isoformat()}},
            )
            stopped = await interrupted()
            if stopped:
                return stopped
            if not aligned.matched_count:
                latest = await self.repo.get_goal(owner_id, goal.id)
                if latest:
                    for field in type(goal).model_fields:
                        setattr(goal, field, getattr(latest, field))
                return {"ok": False, "state": "goal_changed", "goal": goal.for_human()}
            due = actual_due
            goal.next_run_at = due.isoformat()
            total_minutes = max(MIN_WAIT_MINUTES, int(math.ceil((due - now).total_seconds() / 60)))
            for_hours = total_minutes // 60 if total_minutes % 60 == 0 else round(total_minutes / 60, 4)

        await self.repo.journal(
            owner_id,
            goal.id,
            kind="waiting",
            note=note,
            detail={
                "for_minutes": total_minutes,
                "for_hours": for_hours,
                "until": due.isoformat(),
                "step_id": (step.id if step is not None else ""),
            },
        )
        await self._note_ambient(owner_id, "agent_waiting", goal)
        if situation_wait:
            stopped = await interrupted()
            if stopped:
                return stopped
            # A removed/consumed wake is not a promise of a future checkpoint,
            # even while this goal's current execution lease still says running.
            wake_query["id"] = wake["id"]
            wake_query["scheduled_for"] = due.isoformat()
            if due <= _now() or not await self.db.ambient_wakes.find_one(wake_query, {"_id": 1}):
                return {"ok": False, "state": "recovery_pending", "goal": goal.for_human()}
        return {
            "ok": True,
            "state": "waiting",
            "for_minutes": total_minutes,
            "for_hours": for_hours,
            "until": due.isoformat(),
            "goal": goal.for_human(),
        }

    async def _pause(
        self, owner_id, goal, plan: ActionPlan, run: AgentRun, note: str
    ) -> Dict[str, Any]:
        plan.status = "active"
        await self.repo.save_plan(plan)
        await self.repo.journal(owner_id, goal.id, kind="paused", note=note)
        return {"ok": True, "state": "in_progress", "goal": goal.for_human()}

    async def _stop(self, goal, run: AgentRun, note: str) -> Dict[str, Any]:
        goal.status = "failed"
        goal.rationale = note[:300]
        await self.repo.save_goal(goal)
        return {"ok": False, "state": "failed", "reason": note}

    async def _close(
        self, owner_id, goal, plan: ActionPlan, run: AgentRun, status: str, note: str,
        *, prepared_snapshot=None, visibility_budget=None, language="it",
    ) -> Dict[str, Any]:
        from agent.source_refresh import changed, refresh
        if await changed(self.db, goal):
            await refresh(self, goal)
            return {"ok": True, "state": "source_changed" if goal.is_open else goal.status}
        latest = await self.repo.get_goal(owner_id, goal.id)
        if latest and latest.status == "cancelled":
            goal.status = "cancelled"
            goal.next_run_at = None
            return {"ok": True, "state": "cancelled"}
        goal.status = status  # type: ignore[assignment]
        goal.rationale = note[:300]
        goal.completed_at = _now().isoformat()
        if status == "completed" and isinstance(goal, AutonomousGoal):
            from agent.completion_handoff import stage, HandoffUnavailable
            if not await stage(self.db, owner_id, goal, run,
                               visibility_budget or AgentBudget(), language=language):
                current = await self.repo.get_goal(owner_id, goal.id)
                if current is None:
                    raise HandoffUnavailable("completion_goal_missing")
                for field in type(current).model_fields:
                    setattr(goal, field, getattr(current, field))
                return {"ok": True, "state": goal.status, "goal": goal.for_human()}
        if status == "completed" and prepared_snapshot is not None:
            from agent.prepared_review import (
                complete_prepared_result, current_prepared_result, PreparedReviewUnavailable,
            )
            goal.touch()
            if not await complete_prepared_result(self.db, owner_id, goal, prepared_snapshot):
                current = await current_prepared_result(self.db, owner_id, goal.id)
                if current is None:
                    raise PreparedReviewUnavailable("prepared_goal_missing")
                for field in type(current.goal).model_fields:
                    setattr(goal, field, getattr(current.goal, field))
                run.stopped_because = "prepared_result_changed"
                return {"ok": True, "state": "in_progress" if goal.is_open else goal.status,
                        "goal": goal.for_human(), "verification_superseded": True}
        else:
            await self.repo.save_goal(goal)
        if goal.status != status:
            return {"ok": True, "state": goal.status}
        plan.status = "completed" if status == "completed" else "cancelled"
        if status == "completed":
            # Verification can establish the outcome before every planned
            # step is needed. Retire only unfinished work after the goal's
            # closure was accepted; past attempts and results remain history.
            for step in plan.steps:
                if step.status in ("pending", "running", "blocked", "waiting"):
                    step.status = "skipped"
                    step.note = "L'esito è stato verificato; questo passo non è più necessario."
        await self.repo.save_plan(plan)
        await self.repo.journal(owner_id, goal.id, kind=f"goal_{status}", note=note)
        # A goal that ended has no use for the question it was going to ask.
        # What it already told them is history and stays: the two are settled
        # differently because they are different things.
        await self.needs.close_for_goal(
            owner_id, goal.id, why="l'obiettivo si è chiuso",
            kinds={"needs_information", "needs_authority"},
        )
        if status == "completed":
            await self._note_ambient(owner_id, "agent_goal_completed", goal)
            await self._resolve_opportunity(owner_id, goal)
            if goal.source_kind in ("situation_followup", "situation_initial_review"):
                try:
                    from situations.followup import settle_completed_followup
                    await settle_completed_followup(self.db, owner_id, goal)
                except Exception as exc:
                    logger.warning("completed Situation follow-up settlement failed: %s", type(exc).__name__)
        return {"ok": True, "state": status, "goal": goal.for_human()}


    # --- whether to say anything about it ----------------------------------

    async def _record_situation_outcome(self, owner_id, goal, raw, run):
        """Persist the existing model's judgement only with an intact source binding."""
        if raw is None or goal.source_kind not in ("situation_initial_review", "situation_followup"):
            return False
        from situations.outcomes import validate_assessment, current_outcome
        assessment = await validate_assessment(
            self.db, owner_id, goal, raw,
            evidence=await self.evidence.for_goal(owner_id, goal.id), run_at=run.at,
        )
        saved = await self.db.agent_goals.update_one({
            "id": goal.id, "owner_id": owner_id, "status": {"$in": ["active", "waiting"]},
            "source_situation.situation_revision": goal.source_situation.get("situation_revision"),
        }, {"$set": {"situation_outcome": assessment.model_dump() if assessment else None}})
        if not saved.matched_count:
            return False
        goal.situation_outcome = assessment
        await self.repo.journal(
            owner_id, goal.id,
            kind="situation_outcome_assessed" if assessment else "situation_outcome_rejected",
            note=assessment.headline if assessment else "La proposta non aveva tempi, revisione e fonti sufficienti per essere mostrata.",
            detail={"outcome_id": assessment.id if assessment else None,
                    "status": assessment.status if assessment else None},
        )
        return assessment is not None and await current_outcome(self.db, owner_id, goal) is not None

    async def _consider_visibility(
        self, owner_id: str, goal_id: str, run: AgentRun, budget: AgentBudget,
        *, language: str = "it", _handoff=None, offer_delivery=True,
    ) -> Optional[Any]:
        """
        Ask whether the work just done is worth showing.

            DO NOT CONFUSE AVOIDING INTERRUPTION WITH HIDING USEFUL WORK.

        Asked at the end of a run rather than after each step, because a
        judgement per step is the narration it exists to prevent — and asked
        only when the run actually wrote something down, because a run that
        did nothing offers nothing to judge. That second gate is about
        whether there is any material, never about what the answer should be:
        nothing here reads the goal's status, and a test walks this file to
        keep it that way.
        """
        goal = await self.repo.get_goal(owner_id, goal_id)
        if goal is None:
            return None
        if _handoff is None and goal.status == "completed":
            from agent.completion_handoff import FIELD, resume_initial
            if await self.db.agent_goals.find_one(
                {"id": goal_id, "owner_id": owner_id, FIELD: {"$exists": True}}, {"_id": 1},
            ):
                return await resume_initial(self, owner_id, goal_id, budget)

        what_happened = await self._run_facts(owner_id, goal, run)
        if goal.status == "cancelled":
            return None
        if not what_happened["refs"]:
            # The run left no trace, so there is nothing that could be shown
            # with proof behind it. Not a decision that it was uninteresting.
            return None

        cached = _handoff and (_handoff.state.get("candidate") or _handoff.state.get("decision"))
        if not cached and budget.visibility_calls >= budget.max_visibility_calls:
            logger.info("visibility skipped: visibility budget spent goal=%s", goal_id)
            return None

        if not cached:
            budget.visibility_calls += 1
        # Keep run.model_calls as a total count of model judgements this run,
        # while leaving work-budget accounting untouched.
        run.model_calls = budget.cognitive_calls + budget.visibility_calls
        if _handoff:
            await _handoff.check()
            what_happened["_completion_handoff"] = _handoff
        if _handoff and _handoff.state.get("decision"):
            from agent.models import VisibilityDecision
            decision = VisibilityDecision.model_validate(_handoff.state["decision"])
        else:
            decision = await self.visibility.consider(
                owner_id, goal, what_happened=what_happened, language=language
            )
            if _handoff:
                await _handoff.save(decision=decision.model_dump())
        latest = await self.repo.get_goal(owner_id, goal_id)
        from agent.source_refresh import changed
        if latest is None or latest.status == "cancelled" or (goal.is_open and await changed(self.db, goal)):
            return None
        await self.repo.journal(
            owner_id, goal_id, kind="visibility",
            note=decision.headline or decision.quietened_by_code or decision.reasoning,
            detail={
                "outcome": decision.outcome,
                "decided_by": decision.decided_by,
                "quietened": decision.quietened_by_code or None,
            },
        )
        if decision.is_visible:
            if _handoff:
                await _handoff.check()
            await self.visibility.show(owner_id, goal, decision)
            await self._raise_need(owner_id, goal, decision, what_happened,
                                   offer_delivery=offer_delivery, _handoff=_handoff)
        return decision

    async def _raise_need(
        self, owner_id: str, goal, decision, what_happened: Dict[str, Any],
        *, offer_delivery=True, _handoff=None,
    ) -> Optional[CommunicationNeed]:
        """
        Turn a judgement that this is worth showing into a need that can reach
        somebody — and then hand it to the layer that decides whether it does.

            A NEED FOR THE USER IS NOT AUTOMATICALLY A PUSH.

        `quiet_update` stops at the ambient line above: it is worth finding,
        not worth reaching for anybody, and giving it a need would put it in
        front of a judgement about interrupting that it has no business being
        in front of. Everything louder gets one.

        What this does NOT do is pick a channel. There is no push here, no
        in-app, no timing, and no branch on what delivery answers — the moment
        one existed, somebody would write `if requires_attention: push()`
        underneath it.
        """
        if goal.owner_id != owner_id or decision.goal_id != goal.id:
            return None
        kind = _need_kind(decision.outcome, goal)
        if kind is None:
            return None
        from agent.memory_fence import memory_result_current
        memory_snapshot = getattr(decision, "memory_source_snapshot", "")
        if not await memory_result_current(self.db, owner_id, goal, memory_snapshot):
            return None
        from agent.visibility import prepared_communication_current
        prepared_reference = getattr(decision, "prepared_result_ref", None)
        if prepared_reference is None and "_prepared_result_ref" in what_happened:
            # This reference was captured with the facts judged by Visibility.
            # Never bind a delayed judgement to a preparation loaded later.
            prepared_reference = what_happened["_prepared_result_ref"]
        response_kind = (
            "authority" if kind == "needs_authority"
            else "information" if kind == "needs_information" else None
        )
        if not await prepared_communication_current(
            self.db, owner_id, goal.id, prepared_reference,
            question=response_kind is not None, response_kind=response_kind,
        ):
            return None

        outcome = None
        if goal.source_kind in ("situation_initial_review", "situation_followup"):
            from situations.outcomes import current_outcome, outcome_refs
            outcome = await current_outcome(self.db, owner_id, goal, allow_settled=True)
            if kind in ("important_outcome", "useful_result"):
                if not outcome:
                    return None
                if goal.status == "completed" and outcome["status"] != "action_now":
                    return None
                bound = [ref for ref in decision.refs if ref.startswith("situation_outcome:")]
                if decision.refs and bound != [f"situation_outcome:{outcome['id']}"]:
                    # A visibility judgement about an older result cannot be
                    # relabelled with a newer result while being handed off.
                    return None
                decision.refs = outcome_refs(outcome)
                decision.headline = outcome["headline"][:200]
                if outcome["status"] == "action_now":
                    kind = "important_outcome"

        completed_at = (
            goal.completed_at if goal.status == "completed"
            and kind in ("important_outcome", "useful_result") else None
        )
        fingerprint = (f"situation_outcome:{outcome['id']}" if outcome else
                       decision.fingerprint if memory_snapshot else "")
        if completed_at and not outcome:
            import hashlib
            # The same final result is offered once, independently of an
            # earlier update's wording, kind or unchanged Memory snapshot.
            fingerprint = hashlib.sha256(
                f"completed:{owner_id}:{goal.id}:{completed_at}".encode("utf-8")
            ).hexdigest()
        if prepared_reference:
            import hashlib
            from agent.needs import fingerprint as need_fingerprint
            base = fingerprint or need_fingerprint(
                goal.id, kind, _what_is_missing(goal) or decision.headline,
            )
            fingerprint = hashlib.sha256(
                f"{base}|{prepared_reference}".encode("utf-8")
            ).hexdigest()

        need = CommunicationNeed(
            owner_id=owner_id,
            goal_id=goal.id,
            kind=kind,
            summary=decision.headline[:200],
            reason=decision.reasoning[:400] or decision.headline[:400],
            source_refs=list(decision.refs)[:8],
            memory_source_snapshot=memory_snapshot,
            prepared_result_ref=prepared_reference,
            goal_completed_at=completed_at,
            visibility=decision.outcome,
            requires_response=kind in ("needs_information", "needs_authority"),
            response_kind=response_kind,
            work_already_done=[
                str(row.get("what") or "")[:200]
                for row in (what_happened.get("what_ora_did_this_time") or [])
                if row.get("really_happened")
            ][:6],
            what_is_missing=_what_is_missing(goal),
            valid_until=outcome["valid_until"] if outcome else goal.valid_until,
            fingerprint=fingerprint,
        )
        if not await prepared_communication_current(
            self.db, owner_id, goal.id, prepared_reference,
            question=need.requires_response, response_kind=need.response_kind,
        ):
            return None
        if _handoff:
            from agent.completion_handoff import HandoffUnavailable
            await _handoff.check()
            # The same completion cannot create a second Need after a crash,
            # even when the first one has already been answered or closed.
            need.id = "ned_" + _handoff.id
            persisted = await self.needs.get(owner_id, need.id)
            if persisted is not None and not persisted.is_open:
                return persisted
            if persisted is not None:
                offer_delivery = False  # Registration-only replay never re-offers a settled intent.
        raised = await self.needs.raise_need(need)
        if _handoff:
            if raised.id != need.id:
                offer_delivery = False
            persisted = await self.needs.get(owner_id, raised.id)
            if persisted is None:
                raise HandoffUnavailable("completion_need_not_persisted")
            raised = persisted
            await _handoff.save(need_id=raised.id)
            if raised.is_open:
                from delivery.admission import register_need
                if not await register_need(self.db, owner_id, raised.id):
                    raise HandoffUnavailable("completion_need_not_registered")
        await self.repo.journal(
            owner_id, goal.id, kind="need_raised", note=raised.summary,
            detail={"need_id": raised.id, "need_kind": raised.kind,
                    "requires_response": raised.requires_response},
        )

        # And now it is out of the agent's hands. Silence is one of the
        # answers, and it changes nothing about the need.
        if offer_delivery:
            await self.needs.offer_to_delivery(owner_id, raised)
        return raised

    async def _run_facts(self, owner_id: str, goal, run: AgentRun) -> Dict[str, Any]:
        """
        What this run actually did, in facts and handles.

        Facts, not verdicts: what was done, what was found, whether anything
        is needed from the person, and what they were told before. Nothing
        here weighs any of it — weighing is what is being bought.
        """
        from agent.memory_fence import inspect_memory_sources
        from agent.prepared_review import prepared_result_ref, current_prepared_review
        memory = await inspect_memory_sources(self.db, owner_id, goal)
        if memory.status != "current":
            return {"refs": []}
        history = await self.repo.history(owner_id, goal.id, limit=30)
        fresh = [row for row in history if str(row.get("at") or "") >= run.at]

        did: List[Dict[str, Any]] = []
        refs: List[str] = []
        for row in fresh:
            detail = row.get("detail") or {}
            if row.get("kind") in ("step_done", "verified", "goal_completed",
                                   "goal_abandoned", "asked", "awaiting_authority",
                                   "completion_refused", "life_observation"):
                did.append({
                    "what": row.get("note", "")[:200],
                    "really_happened": detail.get("really_happened"),
                    "came_from": detail.get("came_from"),
                })
                refs.append(f"journal:{row.get('at')}")

        evidence = await self.evidence.for_goal(owner_id, goal.id)
        found = [e.for_ai() for e in evidence if e.is_real][-6:]
        refs.extend(e.id for e in evidence if e.is_real)

        outcome = None
        if goal.source_kind in ("situation_initial_review", "situation_followup"):
            from situations.outcomes import current_outcome, outcome_refs
            outcome = await current_outcome(self.db, owner_id, goal, allow_settled=True)
            if outcome:
                refs = [*outcome_refs(outcome), *refs]
        return {
            # Stripped before the model call; the outbox must bind the same
            # Memory versions as these already-assembled facts.
            "_memory_source_snapshot": memory.snapshot,
            "_prepared_result_ref": prepared_result_ref(goal),
            "prepared_review": current_prepared_review(goal),
            "situation_outcome": outcome,
            "what_ora_did_this_time": did[-8:],
            "what_it_found": found,
            "how_it_stands": {
                # State as a fact about the world, said in the same words a
                # person would hear — not a status code to switch on.
                "still_going": goal.is_open,
                "finished": goal.status == "completed",
                "gave_up": goal.status in ("abandoned", "failed"),
                "needs_something_only_they_know": goal.requires_user_input,
                "needs_their_permission": goal.requires_user_authority,
                "what_it_was_for": goal.desired_outcome,
            },
            "is_there_something_for_them_to_do": (
                goal.requires_user_input or goal.requires_user_authority
            ),
            "refs": refs[:8],
        }

    # --- what a person may do about it -------------------------------------

    async def retry_planning(self, owner_id: str, goal_id: str) -> Dict[str, Any]:
        """Retry a suspended owned goal; queue work without granting authority."""
        goal = await self.repo.get_goal(owner_id, goal_id)
        if goal is None:
            return {"ok": False, "reason": "unknown_goal"}
        if (not goal.is_open or not goal.planning_unavailable
                or goal.requires_user_input or goal.requires_user_authority):
            return {"ok": False, "reason": "planning_not_suspended"}
        deadline = _aware_wait_until(goal.valid_until)
        if deadline is not None and deadline <= _now():
            return {"ok": False, "reason": "source_expired"}
        worker = f"retry:{uuid.uuid4().hex[:20]}"
        if not await self.repo.claim(owner_id, goal_id, worker_id=worker):
            return {"ok": True, "state": "already_running", "goal_id": goal_id}
        try:
            goal = await self.repo.get_goal(owner_id, goal_id)
            if goal is None:
                return {"ok": False, "reason": "unknown_goal"}
            if (not goal.is_open or not goal.planning_unavailable
                    or goal.requires_user_input or goal.requires_user_authority):
                return {"ok": False, "reason": "planning_not_suspended"}
            from agent.source_refresh import refresh
            if await refresh(self, goal):
                return {"ok": goal.is_open, "state": "source_changed" if goal.is_open else goal.status,
                        "reason": "source_closed" if not goal.is_open else "",
                        "goal_id": goal_id}
            if goal.next_run_at:
                # A double tap does not buy a new budget or pull a person's
                # explicit defer forward. Missing wakes are recovered normally.
                return {"ok": True, "state": "already_scheduled", "goal_id": goal_id}
            if await self._legacy_event_alert_expired(owner_id, goal):
                return {"ok": False, "reason": "source_unverifiable"}
            goal.planning_attempts = 0
            goal.background_runs = 0
            goal.status = "active"
            goal.next_run_at = (_now() + timedelta(seconds=30)).isoformat()
            goal.rationale = "Mi hai chiesto di riprovare; riprendo la preparazione."
            await self.repo.save_goal(goal)
            if not goal.is_open:
                return {"ok": False, "reason": "planning_not_suspended"}
            await self._schedule_planning_retry(owner_id, goal)
            await self.repo.journal(owner_id, goal_id, kind="planning_retry_requested",
                                    note=goal.rationale, detail={"by": "user"})
            return {"ok": goal.is_open, "state": "planning_retry_scheduled" if goal.is_open else goal.status,
                    "reason": "source_closed" if not goal.is_open else "", "goal_id": goal_id}
        finally:
            await self.repo.release(goal_id, stopped_because="planning_retry_requested", worker_id=worker)

    async def defer_opportunity_goal(
        self, owner_id: str, opportunity_id: str, *, until: str,
        reason: str = "l'utente ha scelto più tardi",
    ) -> Dict[str, Any]:
        """Move existing autonomous work to the same moment as its deferred concern.

        This never creates a goal. If the goal is already waiting for a person's
        information or authority, it is already stopped and its question remains
        the thing that governs resumption. Otherwise the goal, plan and wake move
        together so hiding the Opportunity cannot leave ORA working invisibly.
        """
        goal = await self.repo.goal_for_opportunity(owner_id, opportunity_id)
        if goal is None:
            return {"ok": True, "deferred": False, "reason": "no_open_goal"}

        try:
            due = datetime.fromisoformat(str(until))
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            due = due.astimezone(timezone.utc)
        except (TypeError, ValueError):
            return {"ok": False, "reason": "invalid_defer_time"}
        if due <= _now():
            return {"ok": False, "reason": "defer_time_not_future"}

        if goal.requires_user_input or goal.requires_user_authority:
            await self.repo.journal(
                owner_id, goal.id, kind="user_deferred_surface",
                note=reason,
                detail={
                    "until": due.isoformat(),
                    "work_already_waiting_for_person": True,
                },
            )
            return {
                "ok": True,
                "deferred": False,
                "state": "waiting_for_person",
                "goal_id": goal.id,
            }

        deferred_goal = await self.repo.defer_goal(
            owner_id, goal.id, until=due.isoformat()
        )
        if deferred_goal is None:
            # It may have completed, been cancelled, or become blocked on the
            # person between the first read and this atomic transition.
            latest = await self.repo.get_goal(owner_id, goal.id)
            if latest is not None and latest.is_open and (
                latest.requires_user_input or latest.requires_user_authority
            ):
                await self.repo.journal(
                    owner_id, latest.id, kind="user_deferred_surface",
                    note=reason,
                    detail={
                        "until": due.isoformat(),
                        "work_already_waiting_for_person": True,
                    },
                )
                return {
                    "ok": True,
                    "deferred": False,
                    "state": "waiting_for_person",
                    "goal_id": latest.id,
                }
            return {
                "ok": True,
                "deferred": False,
                "reason": "goal_no_longer_open",
            }

        goal = deferred_goal
        plan = await self.repo.plan_for(owner_id, goal.id)
        if plan is not None and plan.status not in ("completed", "cancelled", "failed"):
            plan.status = "waiting"
            await self.repo.save_plan(plan)

        try:
            from ambient.repository import AmbientRepository
            from ambient.service import AmbientService

            await AmbientRepository(self.db).cancel_for(
                owner_id, source_ref=f"goal:{goal.id}"
            )
            await AmbientService(self.db).schedule(
                owner_id,
                reason="opportunity_revisit",
                when=due,
                source_ref=f"goal:{goal.id}",
                provenance="model",
            )
        except Exception as exc:
            logger.info("agent user defer wake soft-fail: %s", type(exc).__name__)

        await self.repo.journal(
            owner_id, goal.id, kind="user_deferred",
            note=reason,
            detail={"until": due.isoformat(), "opportunity_id": opportunity_id},
        )
        return {
            "ok": True,
            "deferred": True,
            "state": "waiting",
            "until": due.isoformat(),
            "goal_id": goal.id,
        }

    async def cancel(self, owner_id: str, goal_id: str, *, reason: str = "") -> Dict[str, Any]:
        """
        "Lascia perdere." Future work stops; what already happened stands.

        The wakes go too — an alarm for a goal nobody is pursuing is a process
        that will wake up, find nothing, and have cost something.
        """
        goal = await self.repo.get_goal(owner_id, goal_id)
        if goal is None:
            return {"ok": False, "reason": "unknown_goal"}

        goal.status = "cancelled"
        goal.next_run_at = None
        goal.user_deferred_until = None
        goal.decision_provenance = "user"
        goal.rationale = (reason or "l'utente ha detto di lasciar perdere")[:300]
        await self.repo.save_goal(goal)

        plan = await self.repo.plan_for(owner_id, goal_id)
        if plan is not None:
            plan.status = "cancelled"
            await self.repo.save_plan(plan)

        try:
            from ambient.repository import AmbientRepository

            await AmbientRepository(self.db).cancel_for(owner_id, source_ref=f"goal:{goal_id}")
        except Exception as e:
            logger.info("agent wake cancel soft-fail: %s", type(e).__name__)

        # Nobody is pursuing this any more, so nobody has to answer anything
        # about it. Needs, plans and alarms go together or the leftovers of
        # one keep the others alive.
        await self.needs.close_for_goal(
            owner_id, goal_id, why="l'utente ha lasciato perdere"
        )
        await self.repo.journal(owner_id, goal_id, kind="cancelled", note=goal.rationale)
        return {"ok": True, "state": "cancelled"}

    async def answer(
        self, owner_id: str, goal_id: str, *, reply: str, step_id: str = "",
        language: str = "it",
    ) -> Dict[str, Any]:
        """A person supplied what was missing. Carry on from where it stopped."""
        goal = await self.repo.get_goal(owner_id, goal_id)
        plan = await self.repo.plan_for(owner_id, goal_id)
        if goal is None or plan is None or not goal.is_open:
            return {"ok": False, "reason": "unknown_goal"}
        deadline = _aware_wait_until(goal.valid_until)
        if (deadline is not None and deadline <= _now()) or (
            await self._legacy_event_alert_expired(owner_id, goal)
        ):
            return {"ok": False, "reason": "expired_source_event"}
        if not reply.strip():
            return {"ok": False, "reason": "empty_answer"}

        # The answer attaches to the blocker it answers, and becomes
        # evidence like anything else — with `user_statement` as its
        # provenance, because somebody saying a thing is a real source and a
        # different kind of source from having looked.
        answered = None
        for step in plan.steps:
            if step.step_type == "ask_user" and step.status == "blocked" and step.ask_kind == "knowledge":
                if step_id and step.id != step_id:
                    continue
                step.status = "succeeded"
                step.note = f"risposta: {reply[:150]}"
                answered = step
                break

        if answered is not None:
            await self.evidence.record(AgentEvidence(
                owner_id=owner_id,
                goal_id=goal_id,
                step_id=answered.id,
                kind="ask_user",
                claim=reply[:600],
                supports=(answered.asks or answered.intent)[:300],
                provenance=ResultProvenance(
                    source_class="user_statement",
                    capability="ask_user",
                    freshness="fresh",
                ),
            ))

        if answered is None:
            return {"ok": False, "reason": "question_not_open"}

        continuation = None
        continuation_reason = ""
        from agent.calendar_conflict import is_home_calendar_pair
        if is_home_calendar_pair(goal):
            followup = str((answered.parameters or {}).get("conflict_followup") or "")
            if followup == "coordination":
                from agent.calendar_conflict import resolution_step_from_coordination_answer
                continuation, continuation_reason = await resolution_step_from_coordination_answer(
                    self.db, owner_id, goal, answered, reply, language=language
                )
            elif followup == "external_confirmation":
                prepared_params = {
                    **dict(answered.parameters or {}),
                    "conflict_followup": "external_channel",
                    "external_contact_reply": reply[:300],
                }
                # If the person already said «chiamalo» and supplied the
                # contact in the same answer, do not ask them to choose the
                # channel a second time. The helper still only PREPARES the
                # call; the ordinary authority step is what can make it ring.
                if any(word in reply.lower() for word in ("chiam", "telefon")):
                    from agent.calendar_conflict import external_confirmation_step_from_answer
                    prepared = ActionStep(
                        ordinal=len(plan.steps), intent="Preparare la chiamata di conferma",
                        step_type="ask_user", parameters=prepared_params,
                    )
                    continuation, continuation_reason = await external_confirmation_step_from_answer(
                        self.db, owner_id, goal, prepared, reply, language=language
                    )
                else:
                    continuation = ActionStep(
                        ordinal=len(plan.steps),
                        intent="Preparare il contatto per ottenere la conferma esterna",
                        step_type="ask_user",
                        asks=(
                            "Ho registrato chi deve confermare. Non considero ancora "
                            "spostato l’appuntamento finché non arriva una conferma "
                            "reale. Preferisci che la richiesta parta come messaggio "
                            "o come chiamata?"
                        ),
                        ask_kind="knowledge",
                        parameters=prepared_params,
                    )
            elif followup == "external_channel":
                from agent.calendar_conflict import external_confirmation_step_from_answer
                continuation, continuation_reason = await external_confirmation_step_from_answer(
                    self.db, owner_id, goal, answered, reply, language=language
                )
            else:
                from agent.calendar_conflict import resolution_step_from_answer
                continuation, continuation_reason = await resolution_step_from_answer(
                    self.db, owner_id, goal, reply, language=language
                )
            if continuation_reason == "choice_unavailable":
                # The person did answer. A temporary interpretation failure is
                # not permission to guess, and not a reason to mark the answer
                # consumed and silently close the work.
                answered.status = "blocked"
                answered.note = "risposta ricevuta; interpretazione non disponibile"
                await self.repo.save_plan(plan)
                return {"ok": False, "reason": "interpretation_unavailable"}
            if continuation_reason == "calendar_changed":
                from agent.source_refresh import refresh
                await refresh(self, goal)
                await self.repo.journal(
                    owner_id, goal_id, kind="answered", note=reply[:200],
                    detail={"source_changed": True},
                )
                return {"ok": True, "state": "source_changed", "goal": goal.for_human()}
            if continuation is None and continuation_reason:
                # The answer was received but did not produce an executable
                # real-world path. Keep the question open rather than letting
                # a dead end look like completed work.
                answered.status = "blocked"
                answered.note = f"risposta ricevuta; {continuation_reason}"[:200]
                await self.repo.save_plan(plan)
                return {"ok": False, "reason": continuation_reason}
            if continuation is not None:
                continuation.ordinal = len(plan.steps)
                plan.steps.append(continuation)

        # They answered. That settles the need — and only an answer does: a
        # notification that was delivered, or opened, or ignored, leaves it
        # exactly as open as it was.
        for need in await self.needs.open_for_goal(owner_id, goal_id):
            if need.kind == "needs_information":
                await self.needs.satisfy(
                    owner_id, need.id, how="ha risposto", by="user"
                )

        if continuation is not None and continuation.step_type == "ask_user":
            continuation.status = "blocked"
            goal.status = "waiting"
            goal.requires_user_input = True
            goal.requires_user_authority = False
            goal.background_runs = 0
            plan.status = "waiting"
            await self.repo.save_goal(goal)
            await self.repo.save_plan(plan)
            import hashlib
            from agent.needs import fingerprint as need_fingerprint
            from agent.prepared_review import prepared_result_ref
            prepared_reference = prepared_result_ref(goal)
            question_fingerprint = need_fingerprint(
                goal_id, "needs_information", continuation.asks or continuation.intent,
            )
            raised = await self.needs.raise_need(CommunicationNeed(
                owner_id=owner_id,
                goal_id=goal_id,
                kind="needs_information",
                summary=continuation.asks or continuation.intent,
                reason="Serve un dettaglio in più prima di cambiare il calendario.",
                source_refs=list(dict.fromkeys(goal.source_refs))[:8],
                prepared_result_ref=prepared_reference,
                fingerprint=hashlib.sha256(
                    f"{question_fingerprint}|{prepared_reference}".encode("utf-8")
                ).hexdigest(),
                requires_response=True,
                response_kind="information",
                what_is_missing=continuation.asks or continuation.intent,
                provenance="code",
            ))
            await self.needs.offer_to_delivery(owner_id, raised)
            await self.repo.journal(
                owner_id, goal_id, kind="answered", note=reply[:200],
                detail={"next_question": continuation.id},
            )
            await self.repo.journal(
                owner_id, goal_id, kind="asked",
                note=continuation.asks or continuation.intent,
                detail={"kind": "knowledge", "step_id": continuation.id},
            )
            return {
                "ok": True,
                "state": "waiting_for_person",
                "asks": continuation.asks or continuation.intent,
                "kind": "knowledge",
                "goal": goal.for_human(),
            }

        goal.status = "active"
        goal.requires_user_input = False
        goal.background_runs = 0
        plan.status = "active"
        await self.repo.save_goal(goal)
        await self.repo.save_plan(plan)
        await self.repo.journal(owner_id, goal_id, kind="answered", note=reply[:200])
        return await self.advance(owner_id, goal_id, language=language)

    async def standing_offer(self, owner_id: str, goal_id: str) -> Optional[str]:
        """
        What a standing permission would allow here, if offering one is safe.

            A PERSISTENT GRANT MUST BE EXPLICIT.
            NO GLOBAL AUTONOMY.

        `None` is the ordinary answer and the safe one: nothing is offered
        unless there is a prepared effect small enough that a person reading
        one sentence has read the whole permission. Anything that reaches
        somebody else, costs money, commits them, is public or destroys
        something is never offered — not because the engine could not scope a
        grant for it, but because «puoi farlo anche in futuro» is a decision
        somebody makes in two seconds, and it must not be possible to make it
        about something that deserves longer.

        The sentence is the promise, never the mechanism. A surface cannot
        show a capability name, an effect scope or a grant id because it is
        never given one.
        """
        from agent.authority import effect_is_commandable

        goal = await self.repo.get_goal(owner_id, goal_id)
        plan = await self.repo.plan_for(owner_id, goal_id)
        if goal is None or plan is None:
            return None

        for step in plan.steps:
            if step.status != "blocked" or step.step_type != "execute":
                continue
            intent = self.executor._intent_for(owner_id, goal, step)
            # The same predicate that decides whether an instruction may carry
            # authority. Not a coincidence: both questions are «is this small
            # enough that one sentence from a person settles it», and having
            # two answers to that would be having two safety boundaries.
            allowed, _why = effect_is_commandable(intent.effect)
            if not allowed:
                continue
            if await self.authority.has_grant(owner_id, step.capability_needed):
                # Already allowed. Offering it again would be asking somebody
                # to decide something they have decided.
                continue
            return _grant_sentence(intent.effect)
        return None

    async def authorise(
        self, owner_id: str, goal_id: str, *, capability: str = "",
        persistent: bool = False, language: str = "it",
    ) -> Dict[str, Any]:
        """
        A person said yes to the thing that was prepared.

            APPROVE IS NOT A GENERIC YES.
            ONE-TIME APPROVAL IS NOT A STANDING PERMISSION.

        Two things can happen here and they are deliberately different. A
        plain yes records a **consent**, bound by hash to exactly the effect
        that was shown — change the time or add a guest afterwards and it
        stops matching, and the person is asked again. `persistent` is the
        second thing, and it only ever happens because somebody asked for it:
        approving five times does not quietly become a standing permission,
        because the fifth approval is not a different act from the first.

        The grant, when there is one, is scoped from the effect that was
        actually approved. Nothing here widens it, and there is nowhere for a
        model to reach.
        """
        goal = await self.repo.get_goal(owner_id, goal_id)
        plan = await self.repo.plan_for(owner_id, goal_id)
        if goal is None or plan is None:
            return {"ok": False, "reason": "unknown_goal"}
        deadline = _aware_wait_until(goal.valid_until)
        if (deadline is not None and deadline <= _now()) or (
            await self._legacy_event_alert_expired(owner_id, goal)
        ):
            return {"ok": False, "reason": "expired_source_event"}

        approved: List[Dict[str, Any]] = []
        for step in plan.steps:
            if step.status != "blocked" or step.step_type != "execute":
                continue
            if capability and step.capability_needed != capability:
                continue

            intent = self.executor._intent_for(owner_id, goal, step)
            consent = await self.authority.consent(
                owner_id, intent, decision="approved", goal_id=goal_id,
                shown=_authority_question(intent),
            )
            step.status = "pending"
            step.attempts = 0
            approved.append({
                "capability": step.capability_needed,
                "consent_id": consent.id,
                "effect": intent.effect.for_human(),
            })

            if persistent:
                # Scoped to what was approved and nothing wider: the kind of
                # change, and every flag that was false stays disallowed.
                await self.authority.grant(
                    owner_id, step.capability_needed, by="user",
                    effect_scope=[intent.effect.effect_type],
                    allows_external_party=intent.effect.external_party,
                    allows_financial=intent.effect.financial_effect,
                    allows_public=intent.effect.public_visibility,
                    allows_destructive=intent.effect.destructive,
                    human_summary=_grant_sentence(intent.effect),
                )

        if not approved:
            return {"ok": False, "reason": "nothing_to_authorise"}

        for need in await self.needs.open_for_goal(owner_id, goal_id):
            if need.kind == "needs_authority":
                await self.needs.satisfy(
                    owner_id, need.id, how="ha dato il via libera", by="user"
                )

        goal.status = "active"
        goal.requires_user_authority = False
        plan.status = "active"
        await self.repo.save_goal(goal)
        await self.repo.save_plan(plan)
        await self.repo.journal(
            owner_id, goal_id, kind="authorised",
            note="; ".join(a["capability"] for a in approved),
            detail={"by": "user", "also_for_the_future": bool(persistent),
                    "consents": [a["consent_id"] for a in approved]},
        )
        return await self.advance(owner_id, goal_id, language=language)

    async def deny(
        self, owner_id: str, goal_id: str, *, capability: str = "", reason: str = "",
        language: str = "it",
    ) -> Dict[str, Any]:
        """
        A person said no to what was prepared.

            A REFUSAL IS AN ANSWER, NOT A ROUND OF NEGOTIATION.

        Nothing is executed. The no is recorded twice, against two different
        things, because they stop two different mistakes: against the *effect*,
        so this exact act is not re-proposed, and against the *capability*, so
        the same door is not knocked on again this month. Then the model gets
        to decide what the goal looks like without that action — another
        route, or no goal at all. What it may not do is come back with the
        same request, because the ceiling now refuses it outright.
        """
        goal = await self.repo.get_goal(owner_id, goal_id)
        plan = await self.repo.plan_for(owner_id, goal_id)
        if goal is None or plan is None:
            return {"ok": False, "reason": "unknown_goal"}

        refused = capability
        for step in plan.steps:
            if step.status == "blocked" and step.step_type == "execute":
                refused = refused or step.capability_needed
                # Against the effect: a no to this act is a no to this act.
                await self.authority.consent(
                    owner_id, self.executor._intent_for(owner_id, goal, step),
                    decision="denied", goal_id=goal_id,
                )
                step.status = "skipped"
                step.note = "l'utente ha detto di no"

        if refused:
            await self.authority.deny(owner_id, refused, reason=reason)

        # A no is an answer. The need is settled, not left hanging — asking
        # again is exactly what the refusal was about.
        for need in await self.needs.open_for_goal(owner_id, goal_id):
            if need.kind == "needs_authority":
                await self.needs.satisfy(
                    owner_id, need.id, how="ha detto di no", by="user"
                )

        goal.requires_user_authority = False
        goal.status = "active"
        plan.status = "active"
        await self.repo.save_goal(goal)
        await self.repo.save_plan(plan)
        await self.repo.journal(
            owner_id, goal_id, kind="authority_denied", note=refused,
            detail={"by": "user", "reason": reason[:200]},
        )

        run = AgentRun(owner_id=owner_id, goal_id=goal_id)
        budget = AgentBudget()
        outcome = await self._reconsider(
            owner_id, goal, plan, run, budget,
            what_happened={
                "problem": "la persona non ha autorizzato questa azione",
                "capability": refused,
                "why": reason[:200] or None,
            },
            language=language,
        )
        if outcome is not None:
            return outcome
        return {"ok": True, "state": "in_progress", "goal": goal.for_human()}

    # --- what a person sees ------------------------------------------------

    async def for_home(self, owner_id: str) -> List[Dict[str, Any]]:
        """
        Outcomes and states of affairs. Never steps, never plan status.

            THE USER SHOULD EXPERIENCE OUTCOMES, NOT WORKFLOWS.
        """
        out: List[Dict[str, Any]] = []
        completed = await self.db.agent_goals.find({
            "owner_id": owner_id, "status": "completed",
            "completed_at": {"$gte": (_now() - timedelta(hours=24)).isoformat()},
        }, {"_id": 0}).sort("completed_at", -1).to_list(1)
        for row in completed:
            goal = AutonomousGoal.model_validate(row)
            if not await self._memory_renderable(owner_id, goal):
                continue
            if goal.source_kind in ("situation_initial_review", "situation_followup"):
                card = await self._open_card(owner_id, goal)
                if not card.get("stale") and (card.get("situation") or {}).get("outcome"):
                    out.append(card)
                continue
            # Only verified work with real evidence becomes a completed card.
            evidence = await self.evidence.for_goal(owner_id, goal.id)
            if not real_support(evidence):
                continue
            out.append({**goal.for_human(), "state": "Verifica completata",
                "outcome": goal.rationale, "why_now": goal.rationale,
                "source": await self._where_it_really_came_from(owner_id, goal),
                "needs_you": "", "unknown": "",
                "autonomous": goal.origin == "agent_initiated",
                "detected": goal.why_now or goal.rationale,
                "already_done": "Ho completato e verificato il risultato.",
                "next_step": ""})
        for goal in await self.repo.open_goals(owner_id, limit=6):
            # A pending task tied to a finished event must not remain an
            # actionable Home update after the source's own validity expires.
            deadline = _aware_wait_until(goal.valid_until)
            if deadline is not None and deadline <= _now():
                continue
            if await self._legacy_event_alert_expired(owner_id, goal):
                continue
            card = await self._open_card(owner_id, goal)
            if card.get("stale"):
                continue
            # A future schedule is not an update. Home is for something that
            # actually happened, something the person must answer, or a
            # concrete failure/overdue condition worth surfacing now.
            if (
                card.get("has_real_activity")
                or card.get("needs_you")
                or card.get("problem")
            ):
                out.append(card)
            if len(out) >= 3:
                break
        return out

    async def for_detail(self, owner_id: str, goal_id: str) -> Optional[Dict[str, Any]]:
        """Read one owner's still relevant goal, independently of Home ranking."""
        goal = await self.repo.get_goal(owner_id, goal_id)
        if goal is None:
            return None
        if not await self._memory_renderable(owner_id, goal):
            return None
        if goal.is_open:
            deadline = _aware_wait_until(goal.valid_until)
            if deadline is not None and deadline <= _now():
                return None
            if await self._legacy_event_alert_expired(owner_id, goal):
                return None
            card = await self._open_card(owner_id, goal)
            return None if card.get("stale") else card
        if goal.status == "completed":
            if goal.source_kind in ("situation_initial_review", "situation_followup"):
                card = await self._open_card(owner_id, goal)
                return card if not card.get("stale") and (card.get("situation") or {}).get("outcome") else None
            evidence = await self.evidence.for_goal(owner_id, goal.id)
            if real_support(evidence):
                return {**goal.for_human(), "state": "Verifica completata",
                    "outcome": goal.rationale, "why_now": goal.rationale,
                    "source": await self._where_it_really_came_from(owner_id, goal),
                    "needs_you": "", "unknown": "",
                    "autonomous": goal.origin == "agent_initiated",
                    "detected": goal.why_now or goal.rationale,
                    "already_done": "Ho completato e verificato il risultato.",
                    "next_step": ""}
        return None

    async def _legacy_event_alert_expired(
        self, owner_id: str, goal, *, include_unverifiable: bool = True
    ) -> bool:
        """No stale pre-event question, even when old records lack an expiry.

        v144 assumed the AI labelled every appointment discrepancy "perishable"
        and every agent carried an opportunity id. Neither is guaranteed.
        Use the actual owner-owned calendar target and the stored source handles.
        """
        if goal.origin != "agent_initiated" or not goal.is_open:
            return False
        from opportunities.repository import OpportunityRepository
        from opportunities.source_lifecycle import (
            perishable_opportunity_expired, source_event_expired,
            appointment_disagreement_unverifiable,
        )
        if goal.opportunity_id:
            # Legacy admission fixtures and old migrations can retain only
            # {id, owner_id, status, revision}, not a complete Opportunity.
            # Their exact calendar handles are still on the goal itself.
            # Never let a malformed historic source block a valid new action.
            from pydantic import ValidationError
            try:
                linked = await OpportunityRepository(self.db).get(
                    owner_id, goal.opportunity_id
                )
            except ValidationError:
                linked = None
            if linked:
                if await perishable_opportunity_expired(
                    self.db, owner_id, linked
                ):
                    return True
                if include_unverifiable and await appointment_disagreement_unverifiable(
                    self.db, owner_id, linked
                ):
                    return True
        if goal.source_kind != "opportunity":
            return False
        references = list(dict.fromkeys(str(x) for x in (goal.source_refs or [])))[:8]
        linked_events = [x for x in references if x.startswith("calendar:")]
        for ref in references:
            link = await self.db.connected_situation_links.find_one(
                {"owner_id": owner_id, "id": ref, "target_kind": "appointment"},
                {"_id": 0, "target_ref": 1},
            )
            if link and link.get("target_ref"):
                linked_events.append(str(link["target_ref"]))
        # A missing original cannot support an actionable "which time?"
        # prompt. Hide/hold it, without treating it as a proven past event.
        if include_unverifiable and linked_events:
            from opportunities.source_lifecycle import source_event_has_verifiable_date
            for ref in list(dict.fromkeys(linked_events))[:8]:
                if not await source_event_has_verifiable_date(
                    self.db, owner_id, ref
                ):
                    return True
        # If several events are cited, one still to occur keeps the question
        # actionable. An unknown source is never treated as a known expiry.
        return bool(linked_events) and all([
            await source_event_expired(self.db, owner_id, [ref])
            for ref in list(dict.fromkeys(linked_events))[:8]
        ])

    async def _open_card(self, owner_id: str, goal: AutonomousGoal) -> Dict[str, Any]:
        if not await self._memory_renderable(owner_id, goal):
            return {"stale": True}
        from agent.situation_cards import situation_card, concrete_need
        monitored = await situation_card(self.db, owner_id, goal)
        if monitored and monitored.get("inactive"):
            return {"stale": True}
        scheda = {**goal.for_human(), "state": await self._progress_of(owner_id, goal)}
        if monitored:
            situation = monitored["situation"]
            scheda["situation"] = situation
            scheda["what"] = situation["summary"]
            scheda["why_now"] = situation["reason"] or goal.why_now
            scheda["source"] = "Situazione temporanea registrata in ORA"
            scheda["outcome"] = situation["desired_outcome"] or goal.desired_outcome
        if not monitored:
            scheda["source"] = await self._where_it_really_came_from(owner_id, goal)
        scheda["unknown"] = scheda.pop("unclear", "") or self._what_is_still_vague(goal)
        # Internal placeholders are not questions. An actual open Need must
        # supply its own concrete wording before the user is asked anything.
        if goal.requires_user_input or goal.requires_user_authority:
            scheda["needs_you"] = ""

        # Proof-of-work narrative for Home. Every sentence below is grounded
        # either in the goal that admitted the work or in a journal row written
        # by an action that really happened.
        history = await self.repo.history(owner_id, goal.id, limit=20)
        done = [
            row for row in history
            if row.get("kind") == "step_done"
            and (row.get("detail") or {}).get("really_happened")
        ]
        last_done = done[-1] if done else None
        came_from = str(((last_done or {}).get("detail") or {}).get("came_from") or "")
        scheda["autonomous"] = goal.origin == "agent_initiated"
        scheda["detected"] = (goal.why_now or "")[:300]
        scheda["already_done"] = _what_was_done(came_from) if last_done else ""
        scheda["has_real_activity"] = bool(last_done)
        scheda["problem"] = ""
        scheda["retry_available"] = bool(
            goal.is_open and goal.planning_unavailable and not goal.next_run_at
            and not (goal.requires_user_input or goal.requires_user_authority)
        )
        if scheda["retry_available"]:
            # This makes an exhausted technical retry visible on Home without
            # a fabricated result, question, delivery need or notification.
            scheda["problem"] = await self._progress_of(owner_id, goal)

        # A due time that has passed without a real execution is a useful
        # problem. A future due time is merely scheduling state and must not
        # masquerade as an update.
        due = _aware_wait_until(goal.next_run_at)
        if (
            due is not None
            and due < _now() - timedelta(minutes=5)
            and goal.is_open
            and not last_done
            and not (goal.requires_user_input or goal.requires_user_authority)
        ):
            scheda["problem"] = (
                "Il controllo previsto è in ritardo: non risulta ancora "
                "un'esecuzione reale."
            )
            scheda["state"] = scheda["problem"]

        needs = [need for need in await self.needs.open_for_goal(owner_id, goal.id)
                 if need.kind in ("needs_information", "needs_authority")]
        if needs:
            question = concrete_need(needs[0])
            if question:
                scheda["needs_you"] = question
                scheda["next_step"] = question
                scheda["action"] = {"id": needs[0].id, "kind": "route", "label": "Rispondi alla richiesta",
                    "route": "/ora", "params": {"needId": needs[0].id, "goalId": goal.id, "entry": "agent_need"}}
            else:
                scheda["next_step"] = "ORA non ha formulato una domanda specifica; non devi indovinare cosa rispondere."
        elif scheda["retry_available"]:
            scheda["next_step"] = "Puoi riprovare; rivaluterò anche eventuali nuove informazioni."
        elif goal.background_runs >= 3 and not goal.next_run_at:
            scheda["next_step"] = ""
        elif goal.next_run_at:
            scheda["next_step"] = "Ricontrollo automaticamente al prossimo momento utile."
        elif goal.is_open:
            scheda["next_step"] = "Proseguo da sola finché non serve una tua decisione."
        else:
            scheda["next_step"] = ""
        if monitored:
            tracking = monitored["situation"]
            status = tracking.get("followup_status")
            outcome = tracking.get("outcome")
            # Concrete result/window lives only in the expiry-aware DTO. The
            # surrounding state stays a short category and never duplicates a
            # recommendation which an already-open page could keep after expiry.
            scheda["state"] = "Situazione in corso"
            if outcome:
                scheda["state"] = {"estimated": "Stima disponibile", "action_now": "Indicazione disponibile",
                                   "needs_input": "Serve un'informazione"}[outcome["status"]]
                scheda["next_step"] = outcome["action_summary"] or outcome["headline"]
            elif not scheda.get("needs_you"):
                scheda["next_step"] = "La stima del momento utile non è ancora disponibile."
            if status in ("not_scheduled", "recovery_pending", "runtime_disabled", "unavailable"):
                scheda["problem"] = "Non risulta un prossimo controllo confermato per questa situazione."
            if goal.requires_user_input and not scheda.get("needs_you"):
                scheda["next_step"] = "Serve un chiarimento preciso da ORA prima di poter rispondere."
        if scheda["retry_available"]:
            scheda["state"] = await self._progress_of(owner_id, goal)
            scheda["problem"] = scheda["state"]
            scheda["next_step"] = "Puoi riprovare; rivaluterò anche eventuali nuove informazioni."
        return scheda

    async def _memory_renderable(self, owner_id, goal) -> bool:
        from agent.memory_fence import inspect_memory_sources, MemorySourcesUnavailable
        try:
            return (await inspect_memory_sources(self.db, owner_id, goal)).status == "current"
        except MemorySourcesUnavailable:
            return False  # Reading Home never declares a failed read a revocation.

    async def _where_it_really_came_from(self, owner_id: str, goal) -> str:
        """
        La fonte, con il riferimento umano quando esiste.

            «FONTE: APPUNTAMENTO NEL CALENDARIO DEL 4 SETTEMBRE» — O NIENTE.

        Il riferimento che il goal ha conservato è un identificativo: qui si
        prova a tradurlo nel nome che una persona riconosce — il titolo di un
        appuntamento, di un documento, di un segnale. Se non si trova, resta
        la sorgente senza nome; se non c'è nemmeno quella, si dice che
        l'originale non è più ricostruibile.
        """
        base = goal.where_it_came_from()
        riferimento = ""
        for ref in list(goal.source_refs or [])[:3]:
            riferimento = await self._human_name_of(owner_id, str(ref))
            if riferimento:
                break
        if base == "originale non disponibile":
            return "originale non disponibile" if not riferimento else riferimento
        return f"{base} — «{riferimento}»" if riferimento else base

    async def _human_name_of(self, owner_id: str, ref: str) -> str:
        """Il nome leggibile di un riferimento opaco, se si riesce a trovarlo."""
        if not ref:
            return ""
        #     OGNI LETTURA PORTA IL NOME DEL PROPRIETARIO, SCRITTO.
        # Un `$or` fra `user_id` e `owner_id` restringe lo stesso, ma non si
        # legge: la guardia dell'agente cerca la chiave nella query, e ha
        # ragione a pretenderla — una lettura che non dice di chi è, a
        # guardarla, non si distingue da una che legge tutti.
        prove = (
            ("calendar_event_drafts", "user_id", ("title",)),
            ("documents", "user_id", ("title", "filename")),
            ("documents", "owner_id", ("title", "filename")),
            ("connected_signals", "user_id", ("title", "subject")),
            ("goals", "owner_id", ("title", "objective")),
        )
        for collezione, chiave, campi in prove:
            try:
                if chiave == "owner_id":
                    riga = await self.db[collezione].find_one(
                        {"id": ref, "owner_id": owner_id}, {"_id": 0},
                    )
                else:
                    riga = await self.db[collezione].find_one(
                        {"id": ref, "user_id": owner_id}, {"_id": 0},
                    )
            except Exception:  # pragma: no cover
                riga = None
            if riga:
                for campo in campi:
                    valore = str(riga.get(campo) or "").strip()
                    if valore:
                        return valore[:120]
        return ""

    @staticmethod
    def _what_is_still_vague(goal) -> str:
        """
        Che cosa ORA non sa ancora di questo lavoro. Vuoto quando sa tutto.

        Non è una supposizione sul testo: è il fatto che il goal non abbia
        nessun riferimento a cui agganciarsi — nessun appuntamento, nessun
        documento, nessun segnale — pur parlando di una cosa precisa.
        """
        if goal.source_refs or goal.opportunity_id:
            return ""
        return (
            "Non ho un documento o un appuntamento a cui collegarlo: "
            "se mi dici a che cosa si riferisce, lo aggancio."
        )

    async def _progress_of(self, owner_id: str, goal) -> str:
        """
        What to say about a goal that is still open, from what really happened.

            NO FAKE PROGRESS.

        «Sto lavorando…» is the sentence a system says when it has nothing to
        report and would rather not admit it. Everything below either comes
        from a state that is true by definition — waiting on a person, done —
        or from a journal line written by work that actually ran, with the
        provenance it was written with. A goal that has done nothing yet says
        so.
        """
        if getattr(goal, "planning_unavailable", False) and goal.is_open:
            return ("Preparazione sospesa: non riesco ancora a formulare un piano affidabile."
                    if not goal.next_run_at else
                    "La preparazione ha incontrato un problema temporaneo. Riproverò automaticamente.")
        if goal.background_runs >= 3 and not goal.next_run_at and goal.is_open and not (
            goal.requires_user_input or goal.requires_user_authority
        ):
            return "Verifica sospesa: non ho raggiunto un esito entro i tentativi disponibili."
        if goal.status == "waiting" and not (
            goal.requires_user_input or goal.requires_user_authority
        ):
            # Waiting on the world, not on them — and «sto aspettando una
            # risposta» is then a false sentence, newly visible now that a
            # person can answer inside the thread and read the reply. What is
            # true is whatever the run wrote down when it decided to wait, so
            # that is what gets said.
            history = await self.repo.history(owner_id, goal.id, limit=20)
            waited = [row for row in history if row.get("kind") == "waiting"]
            note = str((waited[-1].get("note") if waited else "") or "").strip()
            if note:
                return note[:200]
        if not goal.is_open or goal.status == "waiting":
            return _human_state(goal)

        history = await self.repo.history(owner_id, goal.id, limit=20)
        done = [
            row for row in history
            if row.get("kind") == "step_done"
            and (row.get("detail") or {}).get("really_happened")
        ]
        if not done:
            # Nothing real has happened. Saying it is being handled would be
            # the fake presence this whole rule exists against.
            return "Non ho ancora cominciato."

        return _what_was_being_done((done[-1].get("detail") or {}).get("came_from", ""))


    async def _observe_life_change(
        self, owner_id: str, goal, verification, evidence
    ) -> None:
        """
        A verified outcome may have changed something worth remembering.

            ACTION RESULT -> OBSERVATION -> VALIDATION -> LIFE UPDATE.
            NEVER TOOL OUTPUT -> CANONICAL FACT.

        This is the loop that makes the agent worth having: work produces a
        result, the result is checked, and what is now true about somebody's
        life is available the next time anything reasons about them.

        It is also the most dangerous thing in the file, so it does not write
        anything itself. It proposes, through the governance that already
        owns durable learning, and that governance is free to refuse, ask for
        confirmation, or decide this contradicts something already known. The
        two conditions below are checked here anyway rather than delegated:
        an outcome that was not verified, or was verified on nothing real,
        never even becomes a proposal.
        """
        if verification.outcome != "achieved":
            return
        if not real_support(evidence):
            return

        try:
            from conversation_engine.ai_core.models import MemoryCandidate
            from life_memory.governance import MemoryGovernanceService
        except Exception as e:
            logger.info("life observation import soft-fail: %s", type(e).__name__)
            return

        supporting = [e for e in evidence if e.is_real][:6]
        candidate = MemoryCandidate(
            operation="propose",
            summary=goal.desired_outcome[:600],
            kind="agent_outcome",
            authority="structured",
            epistemic_status="asserted",
            confidence=0.7,
            permanence="unknown",
            # Handles, so anybody asking «how do you know» has somewhere to
            # look. Never the content of what was found.
            provenance=[f"agent_goal:{goal.id}"] + [e.id for e in supporting][:6],
            evidence_refs=[e.id for e in supporting][:6],
            reason_for_future_utility=(
                "Risultato di un obiettivo portato a termine e verificato."
            ),
        )

        try:
            outcome = await MemoryGovernanceService(self.db).apply(
                user_id=owner_id,
                session_id=f"agent:{goal.id}",
                # The same goal proposing twice is the same proposal, and
                # governance keys off this to say so rather than duplicating.
                reasoning_epoch=f"agent:{goal.id}",
                candidate=candidate,
                candidate_index=0,
            )
        except Exception as e:
            logger.info("life observation soft-fail: %s", type(e).__name__)
            return

        await self.repo.journal(
            owner_id, goal.id, kind="life_observation",
            note=goal.desired_outcome[:300],
            detail={"decision": outcome.decision, "persisted": outcome.persisted},
        )

    async def _note_ambient(self, owner_id: str, kind: str, goal) -> None:
        """
        Proof of work, written by the work.

        Reuses V3.8's AmbientActivity, which means the same rule applies: the
        record is written because something happened, and a surface that
        wanted a line cannot produce one.

        A finished goal is the one case that carries a sentence and is
        visible. Everything else here is internal, because a goal being
        started or waiting is not news — but a goal that is done disappears
        from the list of what ORA is handling, and disappearing silently is
        indistinguishable from never having happened.
        """
        finished = kind == "agent_goal_completed"
        try:
            from delivery.service import DeliveryService

            summary = goal.rationale[:200] if finished else ""
            source_refs = [goal.id]
            if goal.source_kind in ("situation_initial_review", "situation_followup"):
                from situations.outcomes import current_outcome, outcome_refs
                assessment = await current_outcome(self.db, owner_id, goal, allow_settled=True)
                finished = finished and bool(assessment)
                summary = assessment["headline"] if finished else ""
                if assessment:
                    source_refs.extend(outcome_refs(assessment))

            await DeliveryService(self.db).note_activity(
                owner_id,
                kind="review_completed",
                summary=summary,
                source_refs=source_refs,
                provenance={"agent": kind, "objective": goal.objective[:120]},
                visible=finished,
            )
        except Exception as e:
            logger.info("agent ambient note soft-fail: %s", type(e).__name__)

    async def _resolve_opportunity(self, owner_id: str, goal) -> None:
        """A goal reaching its outcome may settle the concern it came from."""
        if not goal.opportunity_id:
            return
        try:
            from opportunities.service import OpportunityService

            await OpportunityService(self.db).resolve(owner_id, goal.opportunity_id)
        except Exception as e:
            logger.info("opportunity resolve soft-fail: %s", type(e).__name__)


def _unprepared_effect_reason(intent) -> str:
    """Why an effect is not concrete enough to ask permission for yet.

    This is structural validation, not a judgement about whether the action is
    desirable. A person can only approve a specific act; missing target/time
    means there is not yet an act to approve.
    """
    capability = str(intent.capability or "")
    effect_type = str(intent.effect.effect_type or "")
    params = dict(intent.parameters or {})
    target = str(intent.target_ref or "")

    if capability == "calendar.write":
        if effect_type == "modify" and not target.startswith("calendar:"):
            return "manca il riferimento esatto all'evento Google da modificare"
        if not str(params.get("title") or "").strip():
            return "manca il titolo dell'appuntamento da scrivere"
        if not str(params.get("starts_at") or "").strip():
            return "manca il nuovo orario verificato dell'appuntamento"
    elif capability == "calendar.local.write":
        if effect_type != "modify":
            return "il calendario ORA autonomo può solo modificare un impegno esistente"
        if not target.startswith("calendar:node_home_"):
            return "manca il riferimento esatto all'impegno ORA da modificare"
        if not str(params.get("start_datetime") or "").strip():
            return "manca il nuovo orario verificato dell'impegno"
        if not str(params.get("expected_revision") or "").strip():
            return "manca la revisione corrente dell'impegno da modificare"
    return ""


def _authority_question(intent) -> str:
    """The exact, human-readable act a one-time approval will authorize.

    Parameters matter because approval is already bound to them in effect_hash.
    The question should expose the same concrete act without leaking internal
    refs, hashes, provider names or private message bodies.
    """
    params = dict(intent.parameters or {})
    effect = intent.effect
    capability = str(intent.capability or "")

    if capability in ("calendar.write", "calendar.local.write"):
        title = str(params.get("title") or "").strip()
        starts = str(
            params.get("starts_at")
            or params.get("start_datetime")
            or ""
        ).strip()
        when = _human_authority_time(starts)
        named = f"«{title[:100]}»" if title else "questo appuntamento"
        if effect.effect_type == "modify":
            action = f"Ho preparato lo spostamento di {named}"
        else:
            action = f"Ho preparato l'aggiunta di {named} al calendario"
        if when:
            action += f" per {when}"
        return (action + ". Vuoi che applichi questa modifica?")[:300]

    summary = str(effect.for_human() or intent.effect_summary or "").strip()
    if not summary:
        summary = "l'azione che ho preparato"
    return f"Ho preparato: {summary[:220]}. Vuoi che proceda?"[:300]


def _human_authority_time(value: str) -> str:
    if not value:
        return ""
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return value[:80]
    return moment.strftime("%d/%m alle %H:%M")


def _grant_sentence(effect) -> str:
    """
    What a standing permission says, in words somebody would recognise.

    Shown back when they ask what they allowed, so it has to be the promise
    rather than the mechanism — and narrow enough that reading it is the same
    as reading the scope.
    """
    # The target names a place; the verb has to name an act that fits inside
    # it. Written as a phrase rather than a bare infinitive because "aggiungere
    # il tuo calendario" is not a sentence anybody would say, and a permission
    # people have to decode is one they cannot weigh.
    act = {
        "create": "posso aggiungere quello che serve",
        "modify": "posso cambiare quello che c'è",
        "cancel": "posso annullare quello che c'è",
        "remove": "posso togliere quello che c'è",
        "send": "posso mandare quello che serve",
        "transfer": "posso spostare quello che serve",
        "publish": "posso pubblicare quello che serve",
    }.get(effect.effect_type, "posso agire")
    where = (effect.target or "questa cosa").strip()

    # Every clause after the first is a *limit*, and they are here because a
    # permission whose boundaries are invisible is one nobody can weigh. What
    # is deliberately absent is any way to say "everything": no branch below
    # produces an unbounded sentence, because there is no unbounded grant for
    # it to describe.
    limits = ["senza chiedertelo ogni volta"]
    if not effect.external_party:
        limits.append("senza coinvolgere altre persone")
    if not effect.destructive and effect.effect_type not in ("cancel", "remove"):
        limits.append("senza cancellare niente")
    head = where[0].upper() + where[1:] if where else where
    return f"{head}: {act}, " + ", ".join(limits) + "."


def _need_kind(visibility: str, goal) -> Optional[str]:
    """
    From "how much is this worth showing" to "why the person is being brought in".

    Two semantic fields, both decided upstream by a model — not a channel.
    `silent` and `quiet_update` produce nothing: the first has nothing to say
    and the second is already where somebody will find it, and putting it in
    front of a judgement about interrupting would be asking the wrong question
    about it.

    Which *kind* of asking follows the agent's own earlier judgement about
    what it is blocked on. Code is not deciding that a waiting goal needs
    permission; it is reading which of the two the reasoning already said.
    """
    if visibility in ("silent", "quiet_update"):
        return None
    if visibility == "inform_user":
        return "useful_result"

    # ask_user and requires_attention both mean somebody is wanted.
    if goal.requires_user_authority:
        return "needs_authority"
    if goal.requires_user_input:
        return "needs_information"
    # Worth their attention, and not a question. A finished thing, or a
    # stopped one.
    return "important_outcome"


def _what_is_missing(goal) -> str:
    """The one thing still wanted, in the words the plan already used."""
    if goal.requires_user_authority:
        return "Serve il tuo via libera."
    if goal.requires_user_input:
        return "Manca una cosa che sai solo tu."
    return ""


def _why_not_complete(evidence, intents, receipts=None) -> str:
    """
    Whether anything real stands behind calling this done. Code's answer.

        NO COMPLETION THEATRE.
        SIMULATED IS NOT OBSERVED.

    Two refusals, and the second is the one that matters most. The first says
    a goal cannot be closed when nothing that happened says anything about
    the world. The second says a goal cannot be closed when the thing that
    was supposed to change the world was a stand-in — even if plenty of real
    reading happened around it, because reading is not doing, and an outcome
    that depended on an act being carried out is not true because the act was
    convincingly imitated.

    Never shown to a model, never passed through a prompt, and deliberately
    dull: it reads a source class and a capability name that the executing
    code wrote down, and returns a string or nothing.
    """
    if not real_support(evidence):
        return "niente di reale sostiene questo esito"
    pretended = sorted({
        str(i.get("capability") or "")
        for i in intents
        if i.get("status") in ("executed", "verified")
        and not is_really_wired(str(i.get("capability") or ""))
    })
    if pretended:
        return f"l'azione che avrebbe cambiato le cose era simulata: {', '.join(pretended)}"

    # The third bar, and the one this sprint added. A service taking a request
    # is not the world changing: an event that was accepted and could not
    # afterwards be found is exactly the case where a system that stops at the
    # receipt tells somebody it is in their calendar when it is not.
    unseen = sorted({
        str(r.get("capability") or "")
        for r in (receipts or [])
        if r.get("provider_status") == "accepted"
    })
    if unseen:
        return (
            "il servizio ha accettato la richiesta ma non risulta ancora fatta: "
            + ", ".join(unseen)
        )
    return ""


def _what_was_being_done(came_from: str) -> str:
    """
    One sentence for the kind of work that last actually happened.

    Keyed on where the last result came from — which is a fact the executing
    code wrote down — and not on anything about the subject. A sentence
    chosen by what the goal is about would be a domain template, and it would
    be wrong the first time somebody's life did not match it.
    """
    return {
        "external_research": "Ho cercato quello che serviva.",
        "deterministic_computation": "Sto confrontando le opzioni.",
        "connected_provider": "Sto controllando come stanno le cose.",
        "internal_observation": "Sto guardando quello che ho già.",
        "user_statement": "Sto tenendo conto di quello che mi hai detto.",
    }.get(came_from, "Me ne sto occupando.")


def _what_was_done(came_from: str) -> str:
    """Past-tense proof of work, only from a real journaled step."""
    return {
        "external_research": "Ho cercato le informazioni necessarie.",
        "deterministic_computation": "Ho confrontato le opzioni disponibili.",
        "connected_provider": "Ho controllato i dati collegati.",
        "internal_observation": "Ho verificato ciò che ORA sa già.",
        "user_statement": "Ho integrato quello che mi hai detto.",
    }.get(came_from, "Ho completato un passaggio reale.")


def _human_state(goal) -> str:
    """
    One sentence a person would say. Never a status.

    `waiting` splits in two because the two mean entirely different things to
    somebody reading it: one is ORA waiting on the world, the other is ORA
    waiting on them.
    """
    if goal.status == "waiting" and goal.requires_user_authority:
        return "È tutto pronto, mi serve solo il tuo via libera."
    if goal.status == "waiting" and goal.requires_user_input:
        return "Mi manca una cosa che sai solo tu."
    if goal.status == "waiting":
        return "L'esito è ancora in attesa di verifica."
    if goal.status == "completed":
        return "Fatto."
    return "Me ne sto occupando."
