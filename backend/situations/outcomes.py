"""Source-bound useful Situation assessments on the existing autonomous goal.

Models choose meaning and timing. Code verifies ownership, source revision,
freshness and explicit timestamps; it never supplies a physical completion time.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import ValidationError

from agent.evidence import REAL_SOURCES
from agent.models import AgentEvidence
from situations.clock import local_check_fields
from situations.models import SituationOutcomeAssessment
from situations.repository import SituationRepository


def moment(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def statement_text(state) -> str:
    """What the person declared about a Situation, in one line (≤600)."""
    parts = [f"Dichiarato dalla persona: {state.summary}"]
    if state.facts:
        parts.append("fatti: " + "; ".join(str(f) for f in state.facts[:6]))
    if state.constraints:
        parts.append("vincoli: " + "; ".join(str(c) for c in state.constraints[:4]))
    if state.started_at:
        parts.append(f"inizio: {state.started_at}")
    if state.temporal_scope:
        parts.append(f"periodo: {state.temporal_scope}")
    if state.location_label:
        parts.append(f"luogo: {state.location_label}")
    return ". ".join(parts)[:600]


def situation_id(goal):
    if goal.source_kind not in ("situation_initial_review", "situation_followup"):
        return None
    refs = [ref.split(":", 1)[1] for ref in goal.source_refs if ref.startswith("situation:")]
    return refs[0] if len(refs) == 1 else None


def _evidence_usable(item, now):
    provenance = item.provenance
    observed = moment(provenance.observed_at)
    if (provenance.source_class not in REAL_SOURCES
            or provenance.provider == "generated_draft"
            or provenance.freshness not in ("fresh", "recent")
            or observed is None or observed > now + timedelta(minutes=1)):
        return False
    if provenance.capability == "web.research":
        expiry = moment(provenance.research_valid_until)
        return provenance.research_sufficient is True and expiry is not None and expiry > now
    if provenance.capability == "weather.read":
        expiry = moment(provenance.weather_valid_until)
        return provenance.freshness == "fresh" and expiry is not None and expiry > now
    return now - observed <= timedelta(hours=72)


def _settlement_matches(state, goal, assessment):
    """Only the exact code settlement may follow the assessed source revision."""
    if goal.status != "completed" or state.revision != assessment.situation_revision + 1:
        return False
    if not state.history or state.attention_intent or state.next_check_summary:
        return False
    event = state.history[-1]
    cycle = (goal.source_situation.get("attention_epoch")
             or goal.source_situation.get("situation_revision")
             or str(assessment.situation_revision))
    return bool(
        event.revision == state.revision and event.operation == "update"
        and event.source == "inferred"
        and event.reasoning_epoch == f"followup-complete:{goal.id}:{cycle}"
        and event.changes.get("attention_intent") == ""
        and event.changes.get("next_check_summary") == ""
    )


async def _weather_binding_current(db, owner, state, revision, evidence):
    """A changed Situation or changed saved place invalidates old local inputs."""
    from places.service import PlacesService

    expected = f"situation:{state.id}:revision:{revision}"
    linked = {ref for ref in state.linked_object_refs if ref.startswith("place:")}
    for item in evidence:
        if item.provenance.capability != "weather.read":
            continue
        refs = item.provenance.source_refs
        if expected not in refs:
            return False
        places = [ref for ref in refs if ref.startswith("place:")]
        if len(places) > 1 or (linked and (not places or not set(places).issubset(linked))):
            return False
        for ref in places:
            try:
                place = await PlacesService(db).get_place(owner, ref.split(":", 1)[1])
            except Exception:
                return False
            if (place is None or place.state != "confirmed"
                    or f"place_snapshot:{place.id}:{place.updated_at}" not in refs):
                return False
        if not places and not any(ref.startswith("google_place:") for ref in refs):
            return False
    return True


async def weather_evidence_current(db, owner, goal, evidence, *, now=None):
    """Whether live weather may support this Situation's next real review."""
    now = now or datetime.now(timezone.utc)
    sid = situation_id(goal)
    if not sid or goal.owner_id != owner:
        return False
    state = await SituationRepository(db).get(owner, sid)
    if (state is None or state.status not in ("active", "changed")
            or str(state.revision) != goal.source_situation.get("situation_revision")):
        return False
    if any(item.provenance.capability != "weather.read" or not _evidence_usable(item, now)
           for item in evidence):
        return False
    return bool(evidence) and await _weather_binding_current(db, owner, state, state.revision, evidence)


RECENT_READ_MINUTES = 30
# Readiness: a reading from the same checkpoint, which may span two passes.
READY_READ_MINUTES = 3
# How early before its own estimated window readiness may be announced.
READY_EARLY_MINUTES = 10


def _reject(reasons, code):
    """A refused proposal stays unknown; the caller may learn which rule refused it."""
    if isinstance(reasons, list):
        reasons.append(code)
    return None


async def validate_assessment(db, owner, goal, raw, *, evidence, run_at=None, now=None, reasons=None):
    """Validate a judgement; invalid or insufficient proposals remain unknown.

    `reasons`, when given, receives the one rule that refused the proposal, so
    a rejection is diagnosable instead of a silent `None`.
    """
    now = now or datetime.now(timezone.utc)
    sid = situation_id(goal)
    if not sid or goal.owner_id != owner or not isinstance(raw, dict):
        return _reject(reasons, "no_binding")
    state = await SituationRepository(db).get(owner, sid)
    if (state is None or state.status not in ("active", "changed")
            or str(state.revision) != goal.source_situation.get("situation_revision")):
        return _reject(reasons, "situation_not_current")
    fields = {
        key: raw.get(key) for key in (
            "status", "headline", "action_summary", "basis", "action_reason",
            "window_start", "window_end", "valid_until", "evidence_ids",
        ) if key in raw
    }
    # Production 24/10 20:16: the model wrote the reason where the status
    # goes ("status": "early_risk"). The meaning is unambiguous, so it is
    # placed where it belongs instead of discarding a rain warning.
    if fields.get("status") in ("early_risk", "outcome_ready"):
        fields["action_reason"] = fields.get("action_reason") or fields["status"]
        fields["status"] = "action_now"
    assessed_at = now.isoformat()
    identity = hashlib.sha256(f"{goal.id}:{state.revision}:{assessed_at}".encode()).hexdigest()[:20]
    try:
        assessment = SituationOutcomeAssessment(
            id=f"sout_{identity}", situation_id=sid,
            situation_revision=state.revision, assessed_at=assessed_at, **fields,
        )
    except (TypeError, ValueError, ValidationError):
        return _reject(reasons, "schema_invalid")
    expiry = moment(assessment.valid_until)
    if not expiry or not now < expiry <= now + timedelta(hours=72):
        return _reject(reasons, "validity_out_of_range")
    start, end = moment(assessment.window_start), moment(assessment.window_end)
    if bool(start) != bool(end):
        return _reject(reasons, "window_half_open")
    if start and (end < start or end <= now or end > now + timedelta(hours=72)):
        return _reject(reasons, "window_out_of_range")
    physical_start = moment(state.started_at)
    if start and physical_start and start < physical_start:
        return _reject(reasons, "window_before_start")
    if assessment.action_reason == "outcome_ready":
        # Production 25/10 12:14: estimated dry 14:00-16:00, and at 12:14 the
        # model said "it should be ready now". Readiness cannot come before the
        # window ORA itself estimated, unless the estimate is revised first.
        previous = getattr(goal, "situation_outcome", None)
        if previous is None:
            row = await db.agent_goals.find_one({"id": goal.id, "owner_id": owner},
                                                {"_id": 0, "situation_outcome": 1})
            previous = (row or {}).get("situation_outcome")
        if previous is not None and not isinstance(previous, dict):
            previous = previous.model_dump()
        earliest = moment((previous or {}).get("window_start"))
        if ((previous or {}).get("status") == "estimated"
                and str((previous or {}).get("situation_revision")) == str(state.revision)
                and earliest and now < earliest - timedelta(minutes=READY_EARLY_MINUTES)):
            return _reject(reasons, "ready_before_window")
    if assessment.status == "needs_input":
        if assessment.basis != "missing_information" or start or assessment.action_reason:
            return _reject(reasons, "needs_input_inconsistent")
    else:
        if assessment.basis == "missing_information" or not assessment.action_summary.strip():
            return _reject(reasons, "no_action_or_missing_basis")
        if assessment.status == "action_now" and assessment.action_reason is None:
            return _reject(reasons, "action_now_without_reason")
        if assessment.status == "estimated" and (not start or assessment.action_reason is not None):
            return _reject(reasons, "estimated_shape_invalid")
        if assessment.status == "action_now" and start:
            # A future forecast window must never masquerade as action due now.
            return _reject(reasons, "action_now_with_future_window")

    ids = list(dict.fromkeys(assessment.evidence_ids))
    by_id = {item.id: item for item in evidence
             if item.owner_id == owner and item.goal_id == goal.id}
    if any(ref not in by_id for ref in ids):
        return _reject(reasons, "evidence_unknown")
    # Research that is not (or no longer) established is simply not support:
    # it is set aside rather than sinking a judgement that rests on other,
    # valid readings. The rules below still decide whether what remains is
    # enough — an estimate without a usable baseline is refused there.
    # Any other stale or unusable citation still refuses the whole proposal.
    ids = [ref for ref in ids if _evidence_usable(by_id[ref], now)
           or by_id[ref].provenance.capability != "web.research"]
    if any(not _evidence_usable(by_id[ref], now) for ref in ids):
        return _reject(reasons, "evidence_not_usable")
    cited = [by_id[ref] for ref in ids]
    if not await _weather_binding_current(db, owner, state, state.revision, cited):
        return _reject(reasons, "weather_binding_stale")
    if assessment.status != "needs_input":
        if not cited:
            return _reject(reasons, "no_cited_evidence")
        # A new useful-action decision must rest on a current reading.
        # Readiness ("pronto adesso") must re-read in this very pass: reaching
        # a timer alone cannot turn an older estimate into readiness. A risk
        # warning or an estimated window may use a reading from the last
        # RECENT_READ_MINUTES — production 23/10 19:16 refused "ritira i panni,
        # arriva la pioggia" because the forecast had been read 8 minutes
        # earlier, in the previous pass of the same check.
        #
        # Production 24/10 17:29: the checkpoint re-read the weather at 17:29:34
        # and the judgement came in the next pass, a minute later — readiness
        # was refused for a reading one minute old. A reading from the same
        # checkpoint (READY_READ_MINUTES) is this check, not an older estimate.
        since = moment(run_at)
        if since:
            since = since - timedelta(minutes=(
                READY_READ_MINUTES if assessment.action_reason == "outcome_ready"
                else RECENT_READ_MINUTES))
        # Production 25/10 12:14: the proposal cited this pass's reading and
        # two earlier ones of the same place. An older reading next to a fresh
        # one is not support but it is not a contradiction either: it is set
        # aside, and the fresh one carries the judgement.
        def _fresh(item):
            seen = moment(item.observed_at)
            return seen is not None and since is not None and seen >= since
        if since and any(item.provenance.capability == "weather.read" and _fresh(item) for item in cited):
            cited = [item for item in cited
                     if item.provenance.capability != "weather.read" or _fresh(item)]
            ids = [item.id for item in cited]
        if since and not any(moment(item.observed_at) and moment(item.observed_at) >= since for item in cited):
            return _reject(reasons, "no_fresh_evidence_this_run")
        if since and any(item.provenance.capability == "weather.read"
                         and (moment(item.observed_at) is None or moment(item.observed_at) < since)
                         for item in cited):
            return _reject(reasons, "weather_not_reread_this_run")
        if assessment.basis == "estimate" and assessment.action_reason != "early_risk":
            # Live conditions alone do not establish a physical rate/duration.
            # A sourced empirical baseline or a real computed estimate is needed.
            if not any(item.provenance.capability == "web.research"
                       or item.provenance.source_class == "deterministic_computation"
                       for item in cited):
                return _reject(reasons, "estimate_without_baseline")
        if (assessment.basis == "direct_observation"
                and assessment.action_reason != "early_risk"
                and all(item.provenance.capability in ("weather.read", "web.research") for item in cited)):
            # The same 17:29 proposal said "observed" for laundry nobody can
            # observe. "It should be ready now" is still the useful result —
            # so it is recorded as what it is, an estimate, and needs the
            # sourced baseline every estimate needs.
            if (assessment.action_reason == "outcome_ready"
                    and any(item.provenance.capability == "web.research" for item in cited)):
                assessment.basis = "estimate"
            else:
                return _reject(reasons, "direct_observation_unsupported")
    # The result cannot outlive evidence whose provider gives a shorter horizon.
    expiries = [moment(item.provenance.weather_valid_until or item.provenance.research_valid_until)
                for item in cited]
    expiry = min([expiry, *[value for value in expiries if value is not None]])
    assessment.valid_until = expiry.isoformat()
    assessment.evidence_ids = ids
    return assessment


async def current_outcome(db, owner, goal, *, allow_settled=False, now=None) -> dict[str, Any] | None:
    """Read the current persisted result, including its source/evidence fences."""
    from agent.models import AutonomousGoal

    now = now or datetime.now(timezone.utc)
    if db is None or goal.owner_id != owner:
        return None
    row = await db.agent_goals.find_one({"id": goal.id, "owner_id": owner}, {"_id": 0})
    if not row:
        return None
    try:
        current = AutonomousGoal.model_validate(row)
    except ValidationError:
        return None
    assessment = current.situation_outcome
    if (assessment is None or current.status in ("cancelled", "abandoned", "failed")
            or moment(assessment.valid_until) is None or moment(assessment.valid_until) <= now):
        return None
    if current.status == "completed" and assessment.status != "action_now":
        return None
    sid = situation_id(current)
    if sid != assessment.situation_id:
        return None
    state = await SituationRepository(db).get(owner, sid)
    if state is None or state.status not in ("active", "changed"):
        return None
    matching = state.revision == assessment.situation_revision
    if not matching and not (allow_settled and _settlement_matches(state, current, assessment)):
        return None
    if matching and current.is_open and not (state.attention_intent or state.next_check_summary):
        return None
    ids = assessment.evidence_ids
    rows = await db.agent_evidence.find({
        "owner_id": owner, "goal_id": current.id, "id": {"$in": ids},
        "superseded": {"$ne": True},
    }, {"_id": 0, "expires_at": 0}).to_list(6)
    try:
        evidence = [AgentEvidence.model_validate(item) for item in rows]
    except ValidationError:
        return None
    if set(ids) != {item.id for item in evidence} or any(not _evidence_usable(item, now) for item in evidence):
        return None
    if not await _weather_binding_current(db, owner, state, assessment.situation_revision, evidence):
        return None
    from timezone_service import user_clock_context
    clock = await user_clock_context(db, owner)
    result = assessment.model_dump()
    result.update(timezone=clock["timezone"], window_label=None,
                  assessment_revision=assessment.situation_revision,
                  situation_revision=state.revision)
    if assessment.window_start and assessment.window_end:
        first = local_check_fields(assessment.window_start, clock["timezone"])
        last = local_check_fields(assessment.window_end, clock["timezone"])
        if first and last:
            same_day = first["next_check_at_local"][:10] == last["next_check_at_local"][:10]
            result["window_label"] = (
                f"{first['next_check_label']}–{last['next_check_time_local']}"
                if same_day else f"{first['next_check_label']} – {last['next_check_label']}"
            )
    return result


def outcome_refs(assessment):
    return [f"situation:{assessment['situation_id']}",
            f"situation_outcome:{assessment['id']}", *assessment["evidence_ids"]][:8]
