"""A persisted Situation is not a scheduled check. Reuse the existing Agent/Ambient runtime.

Cognition chooses the purpose, notification condition and first checkpoint. This
module validates ownership/lifecycle and reports only persisted execution state.
No prose classification, domain timers, new worker or external write authority.
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from agent.models import AutonomousGoal
from agent.repository import AgentRepository
from ambient.service import AmbientService
from conversation_engine.ai_core.models import Observation
from situations.repository import SituationRepository
from situations.models import SituationState
from situations.wake_audit import read_situation_wake_audit
from situations.clock import local_check_fields
from situations.history_identity import (
    explicit_dates, authoritative_place, record_event_day, location_matches,
)
from timezone_service import user_clock_context

logger = logging.getLogger("ora.situations.followup")

OPEN = ("proposed", "active", "waiting")
KIND = "situation_followup"
INITIAL_KIND = "situation_initial_review"


def _moment(value):
    try:
        value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return value.astimezone(timezone.utc) if value.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def _enabled():
    return os.environ.get("AMBIENT_RUNTIME", "").strip().lower() in ("1", "true", "on")


def goal_id_for(owner, situation_id):
    return "gol_sit_" + hashlib.sha256(f"{owner}:{situation_id}".encode()).hexdigest()[:24]


def followup_diagnosis(state):
    """Explain the actual persisted state; never infer weather or physical results.

    A missing wake is not proof of WHY the model failed to create it. Keep
    "no registered attempt" distinct from a recorded scheduling rejection.
    """
    status = str(state.get("status") or "unavailable")
    error = str(state.get("last_schedule_error") or "")
    why = {
        "runtime_disabled": "Sul server il motore dei controlli automatici non risulta attivo.",
        "timezone_aware_checkpoint_within_72h_required": (
            "La proposta di controllo non aveva un orario valido con fuso "
            "oppure era fuori dalla finestra consentita."
        ),
        "bounded_purpose_and_notification_condition_required": (
            "Mancava uno scopo preciso o la condizione in cui avvisarti."
        ),
        "revision_conflict": (
            "La situazione è cambiata mentre ORA provava a fissare il controllo."
        ),
        "situation_changed": (
            "La situazione è cambiata o è stata chiusa durante la programmazione."
        ),
        "active_owned_situation_required": (
            "Non risulta una situazione attiva utilizzabile per questo controllo."
        ),
        "already_being_arranged": (
            "Un altro tentativo stava già occupandosi della stessa programmazione."
        ),
        "goal_not_resumable": (
            "Il lavoro collegato era già chiuso o in attesa di una risposta/autorizzazione."
        ),
        "goal_not_persisted": (
            "Non è stato possibile registrare il lavoro che avrebbe effettuato il controllo."
        ),
        "followup_state_unavailable": (
            "Non è stato possibile verificare lo stato del controllo nel database."
        ),
    }
    if status in ("scheduled", "due"):
        label = str(state.get("next_check_label") or "").strip()
        return ("Risulta programmato un controllo." +
                (f" Prossima verifica: {label}." if label else ""))
    if status == "review_pending":
        label = str(state.get("assessment_label") or "").strip()
        failed = (
            f" Ultima proposta di controllo rifiutata: {why[error]}"
            if error in why else ""
        )
        return (
            "ORA ha preso in carico la valutazione di questa situazione, "
            "ma non ha ancora fissato un controllo verificato con fonti reali. "
            + (f"Il riesame del caso è previsto per {label}. " if label else "")
            + "Questo non è un orario di completamento né una notifica."
            + failed
        )
    if status == "running":
        return "È in corso una verifica registrata, ma non ne conosco ancora l'esito."
    if status == "waiting_for_user":
        return "Il lavoro risulta in attesa di un dato o di un'autorizzazione specifica."
    if status == "stopped":
        # Closed does not mean a past physical state was measured.
        if state.get("last_checked_at"):
            return ("Il monitoraggio è stato chiuso: non è previsto un altro controllo. "
                    "Esiste una verifica eseguita e documentata con fonti "
                    "collegate alla situazione.")
        if state.get("last_step_at"):
            return ("Il monitoraggio è stato chiuso: non è previsto un altro controllo. "
                    "Risulta un passaggio tecnico eseguito, ma NON ci sono "
                    "prove sufficienti per attribuirne il risultato alla "
                    "località dichiarata. Non dichiarare il meteo o l'esito "
                    "fisico come verificati.")
        return ("Il monitoraggio è stato chiuso: non è previsto un altro controllo. "
                "Non risulta un controllo eseguito e documentato per questa "
                "situazione; nessun nuovo controllo è programmato.")
    if status == "unavailable":
        if state.get("read_failure_code") == "situation_not_found_or_not_owned":
            return ("La situazione richiesta non risulta nell'archivio di questo "
                    "account con l'identificativo indicato. Non è una prova che "
                    "il controllo sia stato eseguito o cancellato: usa "
                    "list_situation_followups per recuperare gli identificativi "
                    "delle situazioni recenti, comprese quelle chiuse.")
        if state.get("read_failure_code") == "storage_read_failed":
            return ("La lettura del database non è riuscita; non posso "
                    "confermare lo stato del controllo.")
    if status == "runtime_disabled" or state.get("runtime_enabled") is False:
        return why["runtime_disabled"]
    if error and error in why:
        return f"Ultimo tentativo non riuscito: {why[error]}"
    if status == "recovery_pending":
        if state.get("goal_source_kind") == INITIAL_KIND:
            return (
                "La situazione è registrata, ma la prima valutazione non ha "
                "più una sveglia eseguibile. ORA deve recuperare il riesame "
                "prima di poter scegliere un controllo basato sulle fonti. "
                "Non risulta ancora un orario di monitoraggio confermato."
            )
        return ("ORA aveva registrato un orario, ma non risulta una sveglia "
                "eseguibile collegata al lavoro: deve riparare la programmazione.")
    if status == "not_scheduled":
        if state.get("goal_source_kind") == INITIAL_KIND:
            return (
                "La memoria della situazione esiste, ma non risulta neppure "
                "una prima valutazione eseguibile. Non è stato fissato "
                "alcun controllo futuro né osservato l'esito fisico."
            )
        if state.get("goal_id"):
            return ("La situazione è registrata e il lavoro esiste, ma non "
                    "risulta una prossima esecuzione confermata.")
        if state.get("attention_saved") is False:
            return ("È salvata una nota su questa situazione, ma non una richiesta "
                    "di seguirla nel tempo. Nessun controllo automatico risulta programmato.")
        return ("La situazione è registrata, ma non risulta un controllo "
                "con data e ora effettivamente salvato. Senza un errore "
                "registrato non posso attribuire la causa al meteo o ai permessi.")
    return ("Non riesco a leggere lo stato del controllo dal sistema. "
            "Questo non prova né che sia programmato né che sia terminato.")


async def read_followup(db, owner, situation_id):
    """Return verified schedule evidence with a meaningful human diagnosis."""
    state = await _read_followup_snapshot(db, owner, situation_id)
    # A stable goal ID may survive several user-initiated attention cycles.
    # Old failed schedules are historical; they must not be presented as the
    # reason a NEW cycle has no monitoring check. Read only the current cycle.
    if (db is not None and owner and situation_id
            and state.get("attention_saved") is True
            and state.get("status") in (
                "not_scheduled", "review_pending", "recovery_pending", "waiting_for_user",
            )):
        try:
            gid = goal_id_for(owner, situation_id)
            cycle = await db.agent_goals.find_one(
                {"owner_id": owner, "id": gid},
                {"_id": 0, "source_situation.attention_started_at": 1},
            )
            started = ((cycle or {}).get("source_situation") or {}).get("attention_started_at")
            query = {
                "owner_id": owner, "goal_id": gid,
                "kind": "situation_schedule_failed",
            }
            started_at = _moment(started)
            if started_at is not None:
                # Journal timestamps are stored in UTC. Comparing offsetful
                # ISO strings lexically can hide a later attempt (e.g. Rome
                # +02:00 versus a +00:00 journal entry on the same day).
                query["at"] = {"$gte": started_at.isoformat()}
            event = await db.agent_journal.find_one(
                query, {"_id": 0, "at": 1, "detail.error_code": 1},
                sort=[("at", -1)],
            )
            if event:
                code = str((event.get("detail") or {}).get("error_code") or "")
                if code:
                    state["last_schedule_error"] = code[:80]
                    state["last_schedule_attempt_at"] = event.get("at")
        except Exception:
            # Missing audit data never changes whether a wake really exists.
            pass
    state["diagnosis"] = followup_diagnosis(state)
    return state


async def _last_source_bounded_step(db, owner, situation, gid, *, cycle_started_at=None):
    """A successful step proves work, NOT that its place matches the case.

    Old journal notes include prose from providers. Geography cannot be
    established from that prose. A location-bound result needs matching
    durable evidence from the exact step, owner, goal and Situation revision.
    Missing provenance is made explicit instead of relabelled as local weather.
    """
    floor = [v for v in (
        _moment(situation.created_at), _moment(situation.started_at),
        _moment(cycle_started_at),
    ) if v is not None]
    earliest = max(floor) if floor else None
    candidates = await db.agent_journal.find(
        {"owner_id": owner, "goal_id": gid, "kind": "step_done",
         "detail.really_happened": True, "detail.status": "succeeded"},
        {"_id": 0, "at": 1, "note": 1, "detail.step_id": 1},
    ).sort("at", -1).limit(12).to_list(12)
    for row in candidates:
        at = _moment(row.get("at"))
        if at is None or (earliest and at < earliest):
            continue
        step_at = at.isoformat()
        if not str(situation.location_label or "").strip():
            return {"last_checked_at": step_at,
                    "last_result": str(row.get("note") or "")[:300],
                    "last_result_verification": "step_recorded_no_location"}
        # A model-written step note (including 'Leesburg') has no authority
        # over the user-confirmed locality. Require code-owned evidence with
        # the exact step, Situation revision and a place provider reference.
        step_id = str((row.get("detail") or {}).get("step_id") or "")
        if step_id:
            records = await db.agent_evidence.find(
                {"owner_id": owner, "goal_id": gid, "step_id": step_id,
                 "provenance.capability": "weather.read",
                 "superseded": {"$ne": True}},
                {"_id": 0, "provenance.source_refs": 1, "provenance.source_class": 1},
            ).limit(8).to_list(8)
            for evidence in records:
                prov = evidence.get("provenance") or {}
                refs = [str(x) for x in prov.get("source_refs") or []]
                has_revision = any(
                    ref.startswith(f"situation:{situation.id}:revision:")
                    for ref in refs
                )
                has_source = any(
                    ref.startswith(("google_place:", "place:")) for ref in refs
                )
                if (has_revision and has_source
                        and prov.get("source_class") not in ("", "simulated", None)):
                    return {"last_checked_at": step_at,
                            "last_result": str(row.get("note") or "")[:300],
                            "last_result_verification": "exact_step_geobound_evidence"}
        return {"last_step_at": step_at,
                "last_result": None,
                "last_result_verification": "location_not_proven"}
    return {"last_result_verification": "no_documented_step"}


async def _read_followup_snapshot(db, owner, situation_id):
    """Read back a real goal, wake and executed check, never presentation copy."""
    out = {"status": "unavailable", "situation_id": situation_id, "next_check_at": None, "last_checked_at": None,
           "next_check_at_local": None, "next_check_time_local": None, "next_check_label": None,
           "timezone": None, "timezone_authority": None,
           "goal_id": None, "purpose": None, "notify_when": None,
           "completion_when": None, "monitoring_goal": None, "ends_when": None,
           "desired_outcome": None, "outcome": None,
           "attention_saved": None,
           "runtime_enabled": _enabled(), "delivery_channel": "in_app",
           "assessment_at": None, "assessment_label": None,
           "delivery_note": "Gli aggiornamenti sono consultabili in ORA; nessuna push garantita.",
           "read_failure_code": None,
           "last_step_at": None, "last_result_verification": "no_documented_step"}
    if db is None or not owner or not situation_id:
        return out
    try:
        situation = await SituationRepository(db).get(owner, situation_id)
        if situation is None:
            return {**out, "read_failure_code": "situation_not_found_or_not_owned"}
        out["desired_outcome"] = situation.desired_outcome
        # Report only the intent read from this owner's persisted Situation.
        # An expected outcome or estimate alone does not authorise monitoring.
        out["attention_saved"] = bool(
            str(situation.attention_intent or "").strip()
            or str(situation.next_check_summary or "").strip()
        )
        clock = await user_clock_context(db, owner)
        out.update(timezone=clock["timezone"], timezone_authority=clock["authority"])
        if situation.status not in ("active", "changed"):
            # A red-star dismissal or a settled Situation is NOT a database
            # deletion. Read only evidence for the *same owner* and canonical
            # Situation goal. Never revive a closed monitor to answer history.
            gid = goal_id_for(owner, situation_id)
            out.update(await _last_source_bounded_step(
                db, owner, situation, gid,
            ))
            return {**out, "status": "stopped",
                    "situation_lifecycle": situation.status}
        ref = f"situation:{situation_id}"
        goals = await db.agent_goals.find({"owner_id": owner, "source_refs": ref,
                                           "status": {"$in": list(OPEN)}}, {"_id": 0}).sort("updated_at", -1).to_list(8)
        terminal = False
        if not goals and not (situation.attention_intent or situation.next_check_summary):
            completed = await db.agent_goals.find_one(
                {"owner_id": owner, "source_refs": ref,
                 "source_kind": {"$in": [KIND, INITIAL_KIND]},
                 "status": {"$in": ["completed", "cancelled", "failed", "abandoned"]}},
                {"_id": 0}, sort=[("updated_at", -1)],
            )
            if completed:
                goals, terminal = [completed], True
        if not goals:
            return {**out, "status": "not_scheduled"}
        # Prefer the dedicated watch, otherwise expose legacy work rather than
        # pretending old users have no follow-up. Never match titles or keywords.
        goals.sort(key=lambda g: (
            g.get("source_kind") not in (KIND, INITIAL_KIND),
            g.get("source_kind") != KIND,
        ))
        goal = goals[0]
        stop_conditions = [str(x)[:240] for x in (goal.get("stop_conditions") or []) if str(x).strip()]
        out.update(
            goal_id=goal["id"],
            goal_source_kind=str(goal.get("source_kind") or ""),
            purpose=str(goal.get("rationale") or "")[:300],
            completion_when=str(goal.get("desired_outcome") or "")[:400] or None,
            monitoring_goal=str(goal.get("desired_outcome") or "")[:400] or None,
            ends_when=(stop_conditions[-1] if stop_conditions else None),
        )
        from situations.outcomes import current_outcome
        out["desired_outcome"] = situation.desired_outcome or str(goal.get("desired_outcome") or "") or None
        if goal.get("situation_outcome"):
            # Legacy goal rows can still prove a missing checkpoint without
            # containing every current model field. An optional result must
            # not make the independent scheduling diagnosis unavailable.
            try:
                typed_goal = AutonomousGoal.model_validate(goal)
            except ValidationError:
                pass  # Invalid assessments remain absent, never half-published.
            else:
                out["outcome"] = await current_outcome(db, owner, typed_goal, allow_settled=True)
        cycle_start = (goal.get("source_situation") or {}).get("attention_started_at")
        cycle_query = {"at": {"$gte": cycle_start}} if cycle_start else {}
        arranged = await db.agent_journal.find_one(
            {"owner_id": owner, "goal_id": goal["id"], "kind": "situation_checkpoint_arranged", **cycle_query},
            {"_id": 0, "detail.notify_when": 1}, sort=[("at", -1)])
        if arranged:
            out["notify_when"] = str(((arranged.get("detail") or {}).get("notify_when") or ""))[:400] or None
        out.update(await _last_source_bounded_step(
            db, owner, situation, goal["id"], cycle_started_at=cycle_start,
        ))
        if terminal:
            return {**out, "status": "stopped"}
        if goal.get("requires_user_input") or goal.get("requires_user_authority"):
            return {**out, "status": "waiting_for_user"}
        now = datetime.now(timezone.utc)
        if goal.get("source_kind") == INITIAL_KIND:
            # A newly admitted goal is an intent to investigate, NOT a first
            # weather/physical check. Show its executable review separately
            # until cognition has selected and persisted the actual checkpoint.
            due = _moment(goal.get("next_run_at"))
            if due is None:
                return {**out, "status": "not_scheduled"}
            review = await db.ambient_wakes.find_one(
                {"owner_id": owner, "source_ref": f"goal:{goal['id']}",
                 "status": {"$in": ["pending", "claimed"]},
                 "scheduled_for": {"$gte": due.isoformat()}},
                {"_id": 0, "scheduled_for": 1},
                sort=[("scheduled_for", 1)],
            )
            if not review:
                return {**out, "status": "recovery_pending"}
            review_at = _moment(review.get("scheduled_for"))
            if review_at is None:
                return {**out, "status": "recovery_pending"}
            local = local_check_fields(review_at, clock["timezone"])
            return {
                **out, "status": "review_pending" if _enabled() else "runtime_disabled",
                "assessment_at": review_at.isoformat(),
                "assessment_label": local.get("next_check_label"),
            }
        running = await db.agent_runs.find_one(
            {"owner_id": owner, "goal_id": goal["id"], "lease_until": {"$gt": now.isoformat()}}, {"_id": 0, "goal_id": 1})
        # The scheduling lease is not an evidence-reading run.
        if running:
            run = await db.agent_runs.find_one({"owner_id": owner, "goal_id": goal["id"]}, {"_id": 0, "worker_id": 1})
            if not str((run or {}).get("worker_id") or "").startswith("schedule:"):
                return {**out, "status": "running" if _enabled() else "runtime_disabled"}
        due = _moment(goal.get("next_run_at"))
        if due is None:
            return {**out, "status": "not_scheduled"}
        wake = await db.ambient_wakes.find_one(
            {"owner_id": owner, "source_ref": f"goal:{goal['id']}",
             "status": {"$in": ["pending", "claimed"]}, "scheduled_for": {"$gte": due.isoformat()}},
            {"_id": 0, "scheduled_for": 1}, sort=[("scheduled_for", 1)])
        if not wake:
            return {**out, "status": "recovery_pending"}
        at = _moment(wake.get("scheduled_for"))
        if at is None:
            return out
        return {**out, "status": ("runtime_disabled" if not _enabled() else "due" if at <= now else "scheduled"),
                "next_check_at": at.isoformat(),
                **local_check_fields(at, clock["timezone"])}
    except Exception as exc:
        # Do not swallow storage failures into the same generic result as a
        # missing identifier. Log only the error class, never user content.
        logger.warning("followup snapshot read failed error=%s", type(exc).__name__)
        return {**out, "status": "unavailable",
                "read_failure_code": "storage_read_failed"}


async def arrange_followup(db, owner, *, situation_id, expected_revision, check_at, purpose, notify_when, completion_when=None, read_capability=None):
    """Ensure one real first checkpoint; reusing it must not move its deadline."""
    if not _enabled():
        return {"ok": False, "error": "runtime_disabled", "status": "runtime_disabled"}
    due = _moment(check_at)
    now = datetime.now(timezone.utc)
    if due is None or due < now - timedelta(minutes=1) or due > now + timedelta(hours=72):
        return {"ok": False, "error": "timezone_aware_checkpoint_within_72h_required"}
    purpose, notify_when = str(purpose or "").strip(), str(notify_when or "").strip()
    completion_when = str(completion_when or "").strip()
    from agent.checkpoint_source import checkpoint_capability
    requested_read = str(read_capability or "").strip()
    safe_read = checkpoint_capability(requested_read)
    if requested_read and not safe_read:
        return {"ok": False, "error": "unsupported_checkpoint_read_capability"}
    if not purpose or not notify_when or len(purpose) > 300 or len(notify_when) > 400:
        return {"ok": False, "error": "bounded_purpose_and_notification_condition_required"}
    situation = await SituationRepository(db).get(owner, situation_id)
    if not situation or situation.status not in ("active", "changed"):
        return {"ok": False, "error": "active_owned_situation_required"}
    if expected_revision != situation.revision:
        return {"ok": False, "error": "revision_conflict"}
    before = await read_followup(db, owner, situation_id)
    if before["status"] in ("scheduled", "due", "running", "waiting_for_user"):
        if before.get("goal_source_kind") not in (KIND, INITIAL_KIND):
            return {"ok": False, "error": "legacy_goal_pursuing", **before}
        if before["status"] == "waiting_for_user":
            return {"ok": False, "error": "goal_not_resumable", **before}
        return {"ok": True, "reused": True, **before}
    if before["status"] == "unavailable":
        return {"ok": False, "error": "followup_state_unavailable"}
    repo = AgentRepository(db)
    # A shared Situation reference does not transfer ownership of a generic
    # opportunity. Only a typed dedicated watch may be resumed here.
    gid = (
        before.get("goal_id")
        if before.get("goal_source_kind") in (KIND, INITIAL_KIND) and before.get("goal_id")
        else goal_id_for(owner, situation_id)
    )
    worker = f"schedule:{situation_id}"
    if not await repo.claim(owner, gid, worker_id=worker):
        return {"ok": False, "error": "already_being_arranged", **(await read_followup(db, owner, situation_id))}
    try:
        # Re-read after the lease. Cancellation and corrections beat stale work.
        fresh = await SituationRepository(db).get(owner, situation_id)
        if not fresh or fresh.status not in ("active", "changed") or fresh.revision != expected_revision:
            return {"ok": False, "error": "situation_changed"}
        goal = await repo.get_goal(owner, gid)
        if goal and (not goal.is_open or goal.requires_user_input or goal.requires_user_authority):
            return {"ok": False, "error": "goal_not_resumable"}
        # A retry repairs the existing schedule, not a newly invented time.
        # The initial review's wake is NOT a prior monitoring checkpoint.
        # Preserve only an already confirmed model-chosen check; otherwise
        # the initial immediate wake would replace the user's chosen future
        # checkpoint with an invented 60-second check.
        prior_due = (
            _moment(goal.next_run_at)
            if goal and goal.source_kind == KIND else None
        )
        due = max(now + timedelta(seconds=60), prior_due or due)
        if goal:
            from situations.outcomes import current_outcome
            assessment = await current_outcome(db, owner, goal, now=now)
            expiry = _moment(assessment["valid_until"]) if assessment else None
            if expiry:
                due = min(due, max(now + timedelta(seconds=30), expiry - timedelta(seconds=30)))
        source_snapshot = {
            **(goal.source_situation if goal else {}),
            "situation_id": situation_id,
            "situation_revision": str(fresh.revision),
            "attention_expected": "true" if fresh.attention_intent or fresh.next_check_summary else "false",
        }
        if safe_read:
            # The model explicitly chose a supported read-only skill; store
            # it with the approved due instant. A retry remains this same
            # checkpoint, never a new spontaneous provider invocation.
            source_snapshot["checkpoint_read_capability"] = safe_read
            source_snapshot["checkpoint_due_at"] = due.isoformat()
        source_snapshot.setdefault("attention_epoch", str(fresh.revision))
        source_snapshot.setdefault("attention_started_at", now.isoformat())
        fallback_outcome = str(
            fresh.desired_outcome or fresh.expected_outcome_summary
            or "il prossimo momento utile per la persona"
        ).strip()[:300]
        contract = {
            "objective": (fresh.desired_outcome or fresh.summary)[:280],
            "desired_outcome": (fresh.desired_outcome or completion_when or fallback_outcome)[:400],
            "why_now": purpose, "rationale": purpose,
            "source_kind": KIND,
            "source_refs": [f"situation:{situation_id}", *fresh.linked_object_refs][:8],
            "source_situation": source_snapshot,
            "success_criteria": [
                "Rileggere fonti reali pertinenti prima di decidere.",
                "Distinguere una condizione di allarme dal momento utile in cui il monitoraggio può concludersi.",
                "Se il momento utile non è ancora raggiunto, programmare un nuovo controllo giustificato.",
                "Se il momento utile è raggiunto, comunicarlo e terminare il monitoraggio senza inventare che il mondo fisico sia cambiato.",
                "Non scambiare il tempo trascorso per un esito osservato.",
            ],
            "stop_conditions": [
                "La situazione originale è risolta, annullata o l'attenzione è revocata.",
                "Il monitoraggio può terminare quando è stato raggiunto e comunicato un momento utile d'azione o ulteriori controlli non aggiungerebbero valore senza nuovo input della persona.",
            ],
        }
        if goal is None:
            goal = AutonomousGoal(
                id=gid, owner_id=owner, status="active", origin="agent_initiated",
                next_run_at=due.isoformat(), decision_provenance="model", **contract,
            )
            if await repo.create_goal(goal) is None:
                return {"ok": False, "error": "goal_not_persisted"}
        else:
            prior_checkpoint_due = str(
                (goal.source_situation or {}).get("checkpoint_due_at") or ""
            )
            if goal.source_kind == INITIAL_KIND:
                # An initial-review wake is not the requested future check.
                from ambient.repository import AmbientRepository
                await AmbientRepository(db).cancel_for(
                    owner, source_ref=f"goal:{gid}",
                )
                for field, value in contract.items():
                    setattr(goal, field, value)
            elif safe_read and goal.source_kind == KIND:
                # The same owned goal gets a NEW user-requested checkpoint;
                # persist its selected read-only skill rather than losing it
                # while reusing the old goal. Never rewrite the Situation.
                goal.source_situation = source_snapshot
            if safe_read and prior_checkpoint_due != due.isoformat():
                # The previous 3-pass budget was for an older checkpoint.
                # One explicit new request authorizes one *new* bounded pass;
                # retrying the same already scheduled time does not reset it.
                goal.background_runs = 0
                if goal.planning_unavailable:
                    goal.planning_attempts = 0
                    goal.planning_unavailable = False
            goal.next_run_at = due.isoformat()
            await repo.save_goal(goal)
        latest = await SituationRepository(db).get(owner, situation_id)
        if (not latest or latest.status not in ("active", "changed")
                or (source_snapshot["attention_expected"] == "true"
                    and not (latest.attention_intent or latest.next_check_summary))):
            await cancel_dedicated_followup(db, owner, situation_id)
            return {"ok": False, "error": "situation_changed"}
        if latest.revision != expected_revision or not goal.is_open:
            return {"ok": False, "error": "situation_changed"}
        wake = await AmbientService(db).schedule(owner, reason="opportunity_revisit", when=due,
                                                 source_ref=f"goal:{gid}", provenance="model")
        if wake and wake.scheduled_for != goal.next_run_at:
            goal.next_run_at = wake.scheduled_for
            if safe_read:
                goal.source_situation["checkpoint_due_at"] = wake.scheduled_for
            await repo.save_goal(goal)
        latest = await SituationRepository(db).get(owner, situation_id)
        current = await repo.get_goal(owner, gid)
        if (not latest or latest.status not in ("active", "changed")
                or (source_snapshot["attention_expected"] == "true"
                    and not (latest.attention_intent or latest.next_check_summary))):
            await cancel_dedicated_followup(db, owner, situation_id)
            return {"ok": False, "error": "situation_changed"}
        if latest.revision != expected_revision or not current or not current.is_open:
            # The runner refreshes a changed source before acting; an old
            # scheduling decision is not a success for the newer revision.
            return {"ok": False, "error": "situation_changed"}
        await repo.journal(owner, gid, kind="situation_checkpoint_arranged", note=purpose,
                           detail={"situation_id": situation_id, "until": goal.next_run_at,
                                   "notify_when": notify_when, "completion_when": goal.desired_outcome})
    finally:
        await repo.release(gid, stopped_because="checkpoint_arranged", worker_id=worker)
    state = await read_followup(db, owner, situation_id)
    return {"ok": state["status"] in ("scheduled", "due", "running"), **state}


async def repair_missing_dedicated_wakes(db, owner, *, limit=8):
    """Repair a lost persistent alarm WITHOUT inventing a new model decision.

    A goal with an already-approved next_run_at is the sole authority for
    rearming. No due time means there is nothing safe to repair: the ordinary
    cognitive review must choose it. This function never reads weather or
    claims the physical situation has completed.
    """
    if not _enabled() or db is None or not owner:
        return {"repaired": 0, "reason": "runtime_disabled" if not _enabled() else "unavailable"}
    repo = AgentRepository(db)
    rows = await db.agent_goals.find(
        {"owner_id": owner, "source_kind": {"$in": [KIND, INITIAL_KIND]},
         "status": {"$in": list(OPEN)}, "next_run_at": {"$ne": None},
         "requires_user_input": {"$ne": True},
         "requires_user_authority": {"$ne": True}},
        {"_id": 0},
    ).sort("updated_at", -1).to_list(max(1, min(limit, 8)))
    repaired = 0
    for raw in rows:
        refs = [str(x).split(":", 1)[1] for x in (raw.get("source_refs") or [])
                if str(x).startswith("situation:")]
        if len(refs) != 1:
            continue
        sid = refs[0]
        situation = await SituationRepository(db).get(owner, sid)
        if not situation or situation.status not in ("active", "changed"):
            continue
        due = _moment(raw.get("next_run_at"))
        if due is None:
            continue
        state = await read_followup(db, owner, sid)
        if state["status"] != "recovery_pending":
            continue
        # The actual due instant was chosen and persisted earlier. The
        # runtime's standard floor handles a checkpoint missed during outage.
        alarm = await AmbientService(db).schedule(
            owner, reason="opportunity_revisit", when=due,
            source_ref=f"goal:{raw['id']}", provenance="code_schedule",
        )
        if alarm is None:
            # An equivalent alarm may have been created concurrently. Never
            # claim recovery until a fresh owner-scoped read confirms it.
            check = await read_followup(db, owner, sid)
            if check["status"] in ("scheduled", "due", "running"):
                repaired += 1
            continue
        if str(raw.get("next_run_at")) != alarm.scheduled_for:
            goal = await repo.get_goal(owner, raw["id"])
            if goal and goal.is_open:
                goal.next_run_at = alarm.scheduled_for
                await repo.save_goal(goal)
        await repo.journal(
            owner, raw["id"], kind="situation_checkpoint_repaired",
            note="Ripristinato controllo persistente già previsto",
            detail={"situation_id": sid},
        )
        after = await read_followup(db, owner, sid)
        if after["status"] in ("scheduled", "due", "running", "review_pending"):
            repaired += 1
    return {"repaired": repaired}


async def settle_completed_followup(db, owner, goal):
    """Stop monitoring while preserving the real-world Situation until confirmed.

    A completed monitoring goal means ORA reached the useful action/conclusion
    moment. It does NOT prove the physical Situation itself has ceased to exist.
    Clear only the attention/check intent so the safety net cannot restart an
    already-finished watch; the red Situation may remain until user/world evidence
    resolves it separately.
    """
    if getattr(goal, "source_kind", "") not in (KIND, INITIAL_KIND):
        return False
    refs = [str(ref) for ref in (getattr(goal, "source_refs", None) or [])
            if str(ref).startswith("situation:")]
    if len(refs) != 1:
        return False
    sid = refs[0].split(":", 1)[1]
    current = await SituationRepository(db).get(owner, sid)
    if current is None or current.status not in ("active", "changed"):
        return False
    snapshot = getattr(goal, "source_situation", None) or {}
    source_revision = snapshot.get("situation_revision")
    if source_revision and str(current.revision) != str(source_revision):
        # An older completion cannot withdraw attention requested while that
        # worker was finishing. The newer revision has its own lifecycle.
        return False
    cycle = snapshot.get("attention_epoch") or source_revision or str(current.revision)
    from situations.models import SituationUpdate
    from situations.service import SituationService
    result = await SituationService(db).apply(
        user_id=owner,
        session_id=current.session_id or f"agent:{goal.id}",
        reasoning_epoch=f"followup-complete:{goal.id}:{cycle}",
        update=SituationUpdate(
            operation="update",
            situation_id=sid,
            expected_revision=current.revision,
            attention_intent="",
            next_check_summary="",
            source="inferred",
        ),
    )
    return result.get("status") == "success"


async def cancel_dedicated_followup(db, owner, situation_id):
    """Close only this Situation's dedicated watch, never unrelated user plans."""
    from agent.service import AgentService
    # Older dedicated watches may predate the canonical id. Their typed,
    # owner-scoped Situation reference still identifies exactly this work.
    rows = await db.agent_goals.find(
        {"owner_id": owner,
         "$or": [{"id": goal_id_for(owner, situation_id)}, {"source_refs": f"situation:{situation_id}"}],
         "source_kind": {"$in": [KIND, INITIAL_KIND]}},
        {"_id": 0, "id": 1, "status": 1},
    ).to_list(None)
    from ambient.repository import AmbientRepository
    ids = {goal_id_for(owner, situation_id), *[row["id"] for row in rows]}
    for row in rows:
        if row.get("status") in OPEN:
            await AgentService(db).cancel(
                owner, row["id"], reason="Il monitoraggio della situazione è stato interrotto.",
            )
    for gid in ids:
        await AmbientRepository(db).cancel_for(owner, source_ref=f"goal:{gid}")


async def attention_withdrawal_confirmed(db, owner, situation_id) -> bool:
    """A saved intention is not proof that the executable work was stopped."""
    if db is None or not owner or not situation_id:
        return False
    try:
        situation = await SituationRepository(db).get(owner, situation_id)
        if situation is None or (
            situation.status in ("active", "changed")
            and (situation.attention_intent or situation.next_check_summary)
        ):
            return False
        rows = await db.agent_goals.find(
            {"owner_id": owner,
             "$or": [{"id": goal_id_for(owner, situation_id)}, {"source_refs": f"situation:{situation_id}"}],
             "source_kind": {"$in": [KIND, INITIAL_KIND]}},
            {"_id": 0, "id": 1, "status": 1},
        ).to_list(None)
        if any(row.get("status") in OPEN for row in rows):
            return False
        ids = {goal_id_for(owner, situation_id), *[row["id"] for row in rows]}
        wake = await db.ambient_wakes.find_one(
            {"owner_id": owner, "source_ref": {"$in": [f"goal:{gid}" for gid in ids]},
             "status": {"$in": ["pending", "claimed"]}}, {"_id": 0, "id": 1},
        )
        if wake is not None:
            return False
        latest = await SituationRepository(db).get(owner, situation_id)
        return bool(latest and latest.revision == situation.revision and (
            latest.status not in ("active", "changed")
            or not (latest.attention_intent or latest.next_check_summary)
        ))
    except Exception:
        return False


async def get_situation_followup(args, runtime):
    from conversation_engine.ai_core.models import Observation
    sid = str(args.get("situation_id") or "").strip()
    db, owner = runtime.get("db"), str(runtime.get("user_id") or "")
    spoken = str(runtime.get("user_message") or "")
    date_query, date_error = explicit_dates(spoken)
    if date_error:
        return Observation(
            kind="tool", name="get_situation_followup", status="error",
            payload={"status": "identity_ambiguous", "reason": date_error},
        )
    try:
        situation = await SituationRepository(db).get(owner, sid) if db is not None and owner and sid else None
        if situation and date_query:
            clock = await user_clock_context(db, owner)
            day, authority = record_event_day(situation.model_dump(), clock["timezone"])
            if day != date_query:
                return Observation(
                    kind="tool", name="get_situation_followup", status="error",
                    payload={
                        "status": "identity_mismatch",
                        "reason": "SITUATION_DATE_NOT_USER_REQUESTED",
                        "requested_date": date_query,
                        "recorded_event_date": day,
                        "date_authority": authority,
                        "diagnosis": (
                            "L'identificativo è di un'altra data: non "
                            "attribuire questa verifica alla richiesta attuale. "
                            "Usa list_situation_followups per trovare una "
                            "Situazione della data indicata, o segnala che manca."
                        ),
                    },
                )
        expected_place, place_error = authoritative_place(
            spoken, str(args.get("place_query") or ""),
            [situation.location_label] if situation else [],
        )
        if place_error:
            return Observation(
                kind="tool", name="get_situation_followup", status="error",
                payload={"status": "identity_ambiguous", "reason": place_error},
            )
        if (situation and expected_place
                and not location_matches(situation.location_label, expected_place)):
            return Observation(
                kind="tool", name="get_situation_followup", status="error",
                payload={"status": "identity_mismatch",
                         "reason": "SITUATION_LOCALITY_NOT_USER_REQUESTED",
                         "requested_place": expected_place,
                         "diagnosis": (
                             "La località salvata non corrisponde a quella "
                             "dichiarata. Non riutilizzare il risultato "
                             "di un'altra località."
                         )},
            )
    except Exception as exc:
        logger.warning("followup identity read failed error=%s", type(exc).__name__)
        return Observation(
            kind="tool", name="get_situation_followup", status="error",
            payload={"status": "unavailable", "reason": "storage_read_failed"},
        )
    state = await read_followup(db, owner, sid)
    if (situation is None and state.get("status") == "unavailable"
            and state.get("read_failure_code") == "situation_not_found_or_not_owned"
            and db is not None and owner):
        # Recover from a potentially model-invented identifier without ever
        # treating a merely similar record as the requested exact id.
        # Same account, bounded and READ_ONLY; the owner must distinguish
        # records semantically using exact date, subject and location.
        listing = await list_situation_followups({}, runtime)
        if listing.status == "ok":
            data = listing.payload or {}
            state["recent_owner_candidates"] = [
                {
                    "situation_id": row.get("situation_id"),
                    "summary": row.get("summary"),
                    "event_date": row.get("event_date"),
                    "created_at": row.get("created_at"),
                    "location_label": row.get("location_label"),
                    "lifecycle": row.get("lifecycle"),
                }
                for row in (data.get("items") or [])[:5]
            ]
            state["recent_candidate_count"] = len(state["recent_owner_candidates"])
            state["recovery_diagnosis"] = (
                "L'ID citato non esiste nell'archivio di questo account. "
                "La lista recente contiene SOLTANTO possibili record distinti "
                "dell'account: non attribuire automaticamente a quel vecchio "
                "ID il lavoro o il risultato di un altro record. Controlla "
                "data originale e località prima di proporre l'ID corretto."
            )
    if situation is not None and state["status"] != "unavailable":
        state.update(await read_situation_wake_audit(
            db, owner, situation, timezone_name=state.get("timezone") or "UTC",
        ))
    ref = f"situation:{sid}"
    if state["status"] != "unavailable":
        state["factual_readback"] = {
            "ref": ref, "label": "Stato verificato del monitoraggio ORA",
            "text": (
                state["diagnosis"] + " " + state.get("wake_audit_note", "")
            )[:1200],
        }
    return Observation(
        kind="tool", name="get_situation_followup",
        status="ok" if state["status"] != "unavailable" else "error",
        payload=state, provenance=[ref] if state["status"] != "unavailable" else [],
    )

async def schedule_situation_check(args, runtime):
    db, owner = runtime.get("db"), runtime.get("user_id")
    sid = str(args.get("situation_id") or "")
    state = await arrange_followup(db, owner,
        situation_id=sid, expected_revision=args.get("expected_revision"),
        check_at=args.get("check_at"), purpose=args.get("purpose"),
        notify_when=args.get("notify_when"),
        completion_when=args.get("completion_when"),
        read_capability=args.get("read_capability"))
    if not state.get("ok") and db is not None and owner and sid:
        # Failed attempts need a durable reason. Do not write any user prose,
        # provider payload, proposed appointment, or raw tool arguments.
        try:
            situation = await SituationRepository(db).get(owner, sid)
            if situation:
                from agent.repository import AgentRepository
                code = str(state.get("error") or "not_confirmed")[:80]
                await AgentRepository(db).journal(
                    owner, goal_id_for(owner, sid),
                    kind="situation_schedule_failed", note="Controllo non confermato",
                    detail={"error_code": code},
                )
                state = await read_followup(db, owner, sid)
                state["ok"] = False
                state["error"] = code
        except Exception:
            pass
    return Observation(kind="tool", name="schedule_situation_check",
                       status="ok" if state.get("ok") else "error", payload=state)



async def list_situation_followups(args, runtime):
    """Return recent owner-owned history matching the user's ACTUAL date.

    Never let a model's semantic similarity promote an older 11 October
    Situation into a 19 October record. Missing matches are reported as such;
    no records are created, amended, deleted or revived.
    """
    from conversation_engine.ai_core.models import Observation

    db, owner = runtime.get("db"), str(runtime.get("user_id") or "")
    spoken = str(runtime.get("user_message") or "")
    if db is None or not owner:
        return Observation(
            kind="tool", name="list_situation_followups", status="error",
            payload={"status": "unavailable", "reason": "owner_context_required"},
        )
    expected_date, date_error = explicit_dates(spoken)
    if date_error:
        return Observation(
            kind="tool", name="list_situation_followups", status="error",
            payload={"status": "identity_ambiguous", "reason": date_error,
                     "diagnosis": "Sono state citate più date: non posso "
                                  "attribuire le verifiche a un giorno unico."},
        )
    try:
        # Index limits work per person. Even when an old record exists outside
        # this bounded window, do not announce that the entire archive is empty.
        records = await db.situations.find(
            {"user_id": owner},
            {"_id": 0, "id": 1, "summary": 1, "status": 1,
             "created_at": 1, "started_at": 1, "updated_at": 1,
             "location_label": 1},
        ).sort("updated_at", -1).limit(64).to_list(64)
        expected_place, place_error = authoritative_place(
            spoken, str(args.get("place_query") or ""),
            [row.get("location_label") for row in records],
        )
        if place_error:
            return Observation(
                kind="tool", name="list_situation_followups", status="error",
                payload={"status": "identity_ambiguous", "reason": place_error,
                         "diagnosis": "La località proposta non risulta "
                                      "espressamente indicata nella richiesta."},
            )
        clock = await user_clock_context(db, owner)
        zone = clock["timezone"]
        items = []
        for row in records:
            sid = str(row.get("id") or "")
            if not sid:
                continue
            event_date, authority = record_event_day(row, zone)
            if expected_date and event_date != expected_date:
                continue
            if expected_place and not location_matches(
                str(row.get("location_label") or ""), expected_place
            ):
                continue
            status = await read_followup(db, owner, sid)
            audit_state = SituationState.model_validate({"user_id": owner, **row})
            audit = await read_situation_wake_audit(
                db, owner, audit_state, limit=8, timezone_name=zone,
            )
            items.append({
                **audit,
                "situation_id": sid,
                "situation_ref": f"situation:{sid}",
                "summary": str(row.get("summary") or "")[:180],
                "location_label": str(row.get("location_label") or "")[:100],
                "lifecycle": str(row.get("status") or "")[:30],
                "created_at": str(row.get("created_at") or "")[:64] or None,
                "started_at": str(row.get("started_at") or "")[:64] or None,
                "event_date": event_date,
                "date_authority": authority,
                "updated_at": str(row.get("updated_at") or "")[:64],
                "monitoring_status": status["status"],
                "diagnosis": status["diagnosis"],
                "last_checked_at": status.get("last_checked_at"),
                "last_step_at": status.get("last_step_at"),
                "last_result_verification": status.get("last_result_verification"),
                "last_result": status.get("last_result"),
                "next_check_at": status.get("next_check_at"),
                "identity_date_match": bool(expected_date and event_date == expected_date),
                "identity_place_match": bool(expected_place),
            })
            if len(items) == 8:
                break
    except Exception as exc:
        logger.warning("followup history scoped read failed error=%s", type(exc).__name__)
        return Observation(
            kind="tool", name="list_situation_followups", status="error",
            payload={"status": "unavailable", "reason": "storage_read_failed"},
        )
    matched = bool(items)
    if expected_date or expected_place:
        scope_label = "data e località" if expected_date and expected_place else "data" if expected_date else "località"
        note = (
            f"Archivio verificato per {scope_label} espressamente richieste. "
            f"{len(items)} Situazioni coerenti nei record recenti. "
            "NON attribuire a questa richiesta le verifiche di record "
            "esclusi o di date differenti. Se il risultato è vuoto, "
            "non affermare che l'evento sia stato cancellato: "
            "manca una corrispondenza verificabile nella finestra consultata."
        )
    else:
        note = (
            "Elenco cronologico limitato: ogni record include la data originaria. "
            "Non attribuire una Situazione a una data o località senza "
            "una verifica esplicita dell'identità."
        )
    ref = "situations:recent"
    return Observation(
        kind="tool", name="list_situation_followups", status="ok",
        payload={
            "status": "ok", "items": items, "count": len(items),
            "match_status": (
                "matched" if matched else
                "no_exact_match_in_recent_records" if (expected_date or expected_place)
                else "empty_recent_records"
            ),
            "requested_date": expected_date,
            "requested_place": expected_place,
            "timezone": zone,
            "search_limit": 64,
            "factual_readback": {
                "ref": ref, "label": "Identità verificata delle Situazioni ORA",
                "text": note,
            },
        },
        provenance=[ref],
    )

def register_followup_tools(registry):
    from conversation_engine.ai_core.tools.capability import CapabilitySpec
    registry.register(CapabilitySpec(
        capability="list_situation_followups",
        description=(
            "Read up to 8 most recent owner-owned Situation records, including "
            "closed/cancelled ones. Use FIRST when the person asks what happened "
            "to an earlier Situation or an exact situation_id is missing, stale "
            "or unverified. This returns exact situation_id, lifecycle, "
            "evidence-backed last_checked_at and next_check_at, never a "
            "guessed execution. A worker wake is NOT a weather check. " 
            "Use wake_attempts/wake_attempt_count to distinguish actual " 
            "scheduled background attempts from a verified last_checked_at. " 
            "Do not infer a date from updated_at: the "
            "server enforces the exact date written by the person. "
            "For an explicitly named locality, pass place_query. "
            "Select the correct record semantically from the user request. "
            "the user's request, then call get_situation_followup with its "
            "exact ID. Never interpret a missing record as successful work. "
            "This tool cannot schedule, restart or delete anything."
        ),
        input_schema={"type": "object", "properties": {
            "place_query": {"type": "string", "description":
                "Exact locality written by user THIS turn. Leave absent if not stated."}
        }},
        classification="personal", side_effect="READ_ONLY", freshness="fresh",
        risk="read", handler=list_situation_followups))
    registry.register(CapabilitySpec(
        capability="get_situation_followup", description="Read owner-verified scheduling state, diagnosis and last failed attempt for a Situation. For 'perché non è programmato?', 'a che punto siamo?' or a status-only question, CALL THIS TOOL: it returns a factual_readback with a situation ref. If an exact ID is missing or lookup unavailable, first call list_situation_followups and retry with the exact owner-owned ID. A closed Situation may still have a documented last check. Reading never starts or repairs a job.",
        input_schema={"type": "object", "properties": {
            "situation_id": {"type": "string"},
            "place_query": {"type": "string", "description":
                "Exact user-named locality for strict consistency check."}
        }, "required": ["situation_id"]},
        classification="personal", side_effect="READ_ONLY", freshness="fresh", handler=get_situation_followup))
    registry.register(CapabilitySpec(
        capability="schedule_situation_check", description="Persist a real first follow-up in the existing background runtime for an active Situation. Choose checkpoint and purpose from current evidence, not by asking the user to supervise ORA. Reuses existing work without postponing it. Does not send a notification, grant external write authority, or prove an outcome. Read the returned status before promising a check. For dialogue use next_check_label and timezone from the result, not the raw UTC hour or the proposed check_at. When the person explicitly asks for a live weather reading at this checkpoint, pass read_capability='weather.read'. It persists that read-only capability for the wake, so the worker performs the real provider read before asking the AI for the outcome. Do NOT pass a read capability for unrelated checks or infer device GPS; the provider still requires an owned confirmed place. This operation does not measure any physical state.",
        input_schema={"type": "object", "properties": {"situation_id": {"type": "string"}, "expected_revision": {"type": "integer"}, "check_at": {"type": "string", "description": "Timezone-aware ISO8601, within 72 hours. A recheck time, not a predicted completion."}, "purpose": {"type": "string", "maxLength": 300}, "completion_when": {"type": "string", "maxLength": 400, "description": "Plain user-facing condition/outcome ORA is trying to reach; no implementation wording. Must be grounded in evidence."}, "notify_when": {"type": "string", "maxLength": 400, "description": "Earlier exceptional condition worth warning about before completion."}, "read_capability": {"type": "string", "enum": ["weather.read"], "description": "OPTIONAL: only when user explicitly asks to check weather at this deadline, opt in to a real bounded read-only weather skill. Not evidence of physical completion."}}, "required": ["situation_id", "expected_revision", "check_at", "purpose", "completion_when", "notify_when"]},
        classification="personal", side_effect="REVERSIBLE_WRITE", risk="write_soft", freshness="fresh", handler=schedule_situation_check))
