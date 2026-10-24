"""A temporary Situation delivers a sourced action moment, not a weather task.

All facts/model replies are synthetic. These exercise the real persistence,
revision, wait, completion and projection contracts without asserting real-world
dryness or sending anything to a person.
"""
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient
from pydantic import ValidationError

from agent.evidence import EvidenceStore, for_verification
from agent.models import (ActionPlan, ActionStep, AgentBudget, AgentEvidence,
                          AgentRun, ResultProvenance, VisibilityDecision)
from agent.service import AgentService, _human_state
from agent.source_refresh import refresh
from situations.admission import _review_goal
from situations.followup import arrange_followup, read_followup
from situations.models import SituationState, SituationUpdate
from situations.outcomes import current_outcome, outcome_refs, validate_assessment
from situations.repository import SituationRepository
from situations.service import SituationService

OWNER = "outcome-v160-synthetic"


async def setup(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().outcome_v160
    await db.agent_goals.create_index("id", unique=True)
    await db.agent_evidence.create_index("id", unique=True)
    await db.agent_runs.create_index("goal_id", unique=True)
    await db.ambient_wakes.create_index("identity", unique=True)
    monkeypatch.setattr(SituationService, "_note_opportunity_change", AsyncMock())
    now = datetime.now(timezone.utc)
    state = SituationState(
        id="sit_useful_v160", user_id=OWNER, summary="Attività temporanea in corso",
        desired_outcome="Sapere quando è ragionevole concludere e ritirare il materiale.",
        attention_intent="Rileggere le condizioni esterne rilevanti.",
        started_at=(now - timedelta(minutes=30)).isoformat(),
        location_label="Luogo sintetico confermato",
        facts=["Attività iniziata trenta minuti fa; il materiale è ancora fuori."],
    )
    await SituationRepository(db).insert(state)
    goal = _review_goal(OWNER, state, "goal_useful_v160")
    service = AgentService(db)
    await service.repo.create_goal(goal)
    monkeypatch.setattr(service, "_note_ambient", AsyncMock())
    monkeypatch.setattr(service, "_resolve_opportunity", AsyncMock())
    monkeypatch.setattr(service, "_observe_life_change", AsyncMock())
    run = AgentRun(owner_id=OWNER, goal_id=goal.id,
                   at=(now - timedelta(seconds=1)).isoformat())
    baseline = AgentEvidence(
        id="evd_empirical_v160", owner_id=OWNER, goal_id=goal.id,
        observed_at=(now - timedelta(hours=2)).isoformat(),
        claim="Fonte sintetica: la durata osservata dipende da ventilazione ed esposizione, con un intervallo ampio.",
        provenance=ResultProvenance(
            source_class="external_research", capability="web.research", provider="research",
            source_refs=["research_fixture"], freshness="fresh",
            observed_at=(now - timedelta(hours=2)).isoformat(), research_sufficient=True,
            research_valid_until=(now + timedelta(hours=8)).isoformat(),
        ),
    )
    live = AgentEvidence(
        id="evd_conditions_v160", owner_id=OWNER, goal_id=goal.id,
        claim="Fonte sintetica: condizioni ora favorevoli e nessun rischio imminente segnalato.",
        provenance=ResultProvenance(
            source_class="external_research", capability="weather.read", provider="fixture",
            source_refs=["google_place:synthetic", f"situation:{state.id}:revision:1"], freshness="fresh",
            weather_valid_until=(now + timedelta(minutes=70)).isoformat(),
        ),
    )
    for item in (baseline, live):
        await service.evidence.record(item)
    plan = ActionPlan(owner_id=OWNER, goal_id=goal.id, status="active", steps=[
        ActionStep(intent="Valutare il momento utile", step_type="verify"),
    ])
    await service.repo.save_plan(plan)
    return db, service, state, goal, run, plan, baseline, live


def estimate(baseline, live, *, now=None):
    now = now or datetime.now(timezone.utc)
    return {
        "status": "estimated", "headline": "Ritiro stimato nella finestra indicata.",
        "action_summary": "Il momento utile è stimato; attendi la verifica aggiornata prima del ritiro.",
        "basis": "estimate", "action_reason": None,
        "window_start": (now + timedelta(minutes=90)).isoformat(),
        "window_end": (now + timedelta(minutes=150)).isoformat(),
        "valid_until": (now + timedelta(minutes=90)).isoformat(),
        "evidence_ids": [baseline.id, live.id],
    }


def action(baseline, live):
    raw = estimate(baseline, live)
    raw.update(status="action_now", headline="Puoi ritirare il materiale: dovrebbe essere pronto.",
               action_summary="Ritira ora; controlla il risultato perché è una stima, non una misura diretta.",
               action_reason="outcome_ready", window_start=None, window_end=None)
    return raw


@pytest.mark.asyncio
async def test_admission_and_refresh_preserve_useful_outcome_and_physical_start(monkeypatch):
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    assert goal.objective == state.desired_outcome
    assert goal.desired_outcome == state.desired_outcome
    assert goal.desired_outcome != state.attention_intent
    await service._record_situation_outcome(OWNER, goal, estimate(baseline, live), run)
    old_start = state.started_at
    await SituationService(db).apply(
        user_id=OWNER, session_id="fixture", reasoning_epoch="correction-v160",
        update=SituationUpdate(operation="update", situation_id=state.id, expected_revision=1,
                               current_state_summary="Il materiale è stato spostato al riparo.",
                               expected_outcome_summary="La previsione ora cambia."),
    )
    assert await refresh(service, goal)
    current = await service.repo.get_goal(OWNER, goal.id)
    state = await SituationRepository(db).get(OWNER, state.id)
    assert current.desired_outcome == state.desired_outcome
    assert current.situation_outcome is None
    assert state.started_at == old_start
    preview = state.context_preview()
    assert preview["started_at"] == old_start
    assert preview["created_at"] == state.created_at
    assert preview["started_at"] != preview["updated_at"]
    ai = await service._reasoning_goal(OWNER, current)
    assert ai["source_context"][0]["started_at"] == old_start


@pytest.mark.asyncio
async def test_reasoning_context_keeps_situation_refs_on_derived_goals(monkeypatch):
    _, service, state, _, _, _, _, _ = await setup(monkeypatch)
    goal = SimpleNamespace(id="derived-goal", owner_id=OWNER, source_kind="opportunity",
                           source_refs=[f"situation:{state.id}"], for_ai=lambda: {"objective": "Controllare l'esito"})
    payload = await service._reasoning_goal(OWNER, goal)
    assert payload["objective"] == "Controllare l'esito"
    assert payload["source_context"][0]["ref"] == f"situation:{state.id}"
    assert payload["source_context"][0]["started_at"] == state.started_at
    assert payload["source_context_unavailable"] is False


@pytest.mark.parametrize("value", ["2026-10-12T11:00:00", "not-a-time"])
def test_naive_or_invalid_physical_start_rejected(value):
    with pytest.raises(ValidationError):
        SituationUpdate(operation="create", summary="Sintetica", started_at=value)


@pytest.mark.asyncio
async def test_estimate_persists_and_restarts_with_source_bound_window_not_checkpoint(monkeypatch):
    db, service, state, goal, run, plan, baseline, live = await setup(monkeypatch)
    raw = estimate(baseline, live)
    assert await service._record_situation_outcome(OWNER, goal, raw, run)
    checkpoint = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    scheduled = await arrange_followup(
        db, OWNER, situation_id=state.id, expected_revision=1, check_at=checkpoint,
        purpose="Rileggere le condizioni", notify_when="Prima se emerge un rischio",
        completion_when="Testo procedurale che non deve sostituire l'esito desiderato",
    )
    assert scheduled["ok"]
    reloaded = await AgentService(db).repo.get_goal(OWNER, goal.id)
    followup = await read_followup(db, OWNER, state.id)
    assert reloaded.desired_outcome == state.desired_outcome
    assert followup["desired_outcome"] == state.desired_outcome
    outcome = followup["outcome"]
    assert outcome["window_start"] == raw["window_start"]
    assert outcome["window_end"] == raw["window_end"]
    assert outcome["window_start"] != followup["next_check_at"]
    assert outcome["valid_until"] == live.provenance.weather_valid_until
    assert outcome["window_label"] and outcome["timezone"]
    assert outcome["evidence_ids"] == [baseline.id, live.id]
    card = await service._open_card(OWNER, reloaded)
    assert card["situation"]["outcome"]["id"] == outcome["id"]
    assert card["outcome"] == state.desired_outcome
    assert "Prossimo controllo programmato" not in card["next_step"]
    assert "risposta" not in _human_state(reloaded)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["only_weather", "uncited", "foreign", "stale_weather",
                                 "expired_research", "naive_window", "reversed_window", "past_window"])
async def test_invalid_estimate_cannot_become_a_displayed_time(monkeypatch, bad):
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    raw = estimate(baseline, live)
    if bad == "only_weather":
        raw["evidence_ids"] = [live.id]
    elif bad == "uncited":
        raw["evidence_ids"] = []
    elif bad == "foreign":
        raw["evidence_ids"] = ["evd_foreign"]
    elif bad == "stale_weather":
        live.provenance.weather_valid_until = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    elif bad == "expired_research":
        baseline.provenance.research_valid_until = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    elif bad == "naive_window":
        raw["window_start"] = "2026-10-12T14:00:00"
    elif bad == "reversed_window":
        raw["window_start"], raw["window_end"] = raw["window_end"], raw["window_start"]
    elif bad == "past_window":
        raw["window_start"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        raw["window_end"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    result = await validate_assessment(db, OWNER, goal, raw, evidence=[baseline, live], run_at=run.at)
    assert result is None


@pytest.mark.asyncio
async def test_early_protective_action_is_not_a_readiness_claim(monkeypatch):
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    raw = action(baseline, live)
    raw.update(action_reason="early_risk", headline="Ritira ora: è segnalato un rischio imminente.",
               action_summary="Proteggi il materiale adesso; questo non significa che sia pronto.",
               evidence_ids=[live.id])
    result = await validate_assessment(db, OWNER, goal, raw, evidence=[live], run_at=run.at)
    assert result is not None
    assert result.action_reason == "early_risk"
    assert result.window_start is None
    raw["action_reason"] = "outcome_ready"
    assert await validate_assessment(db, OWNER, goal, raw, evidence=[live], run_at=run.at) is None


@pytest.mark.asyncio
async def test_weather_cannot_be_called_direct_observation_of_completion(monkeypatch):
    db, _, _, goal, run, _, baseline, live = await setup(monkeypatch)
    raw = action(baseline, live)
    raw.update(basis="direct_observation", evidence_ids=[live.id])
    assert await validate_assessment(db, OWNER, goal, raw, evidence=[live], run_at=run.at) is None


@pytest.mark.asyncio
async def test_missing_information_has_no_invented_window(monkeypatch):
    db, service, _, goal, run, _, _, _ = await setup(monkeypatch)
    raw = {"status": "needs_input", "basis": "missing_information",
           "headline": "In quale località si trova il materiale?", "action_summary": "",
           "valid_until": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
           "evidence_ids": []}
    assert await service._record_situation_outcome(OWNER, goal, raw, run)
    result = await current_outcome(db, OWNER, goal)
    assert result["window_label"] is None
    assert result["window_start"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["expiry", "revision", "resolution", "superseded_evidence"])
async def test_old_assessment_disappears_after_its_authority_changes(monkeypatch, change):
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    assert await service._record_situation_outcome(OWNER, goal, estimate(baseline, live), run)
    if change == "expiry":
        await db.agent_goals.update_one({"id": goal.id}, {"$set": {
            "situation_outcome.valid_until": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()}})
    elif change == "revision":
        await db.situations.update_one({"id": state.id}, {"$inc": {"revision": 1}})
    elif change == "resolution":
        await db.situations.update_one({"id": state.id}, {"$set": {"status": "resolved"}})
    else:
        await db.agent_evidence.update_one({"id": live.id}, {"$set": {"superseded": True}})
    assert await current_outcome(db, OWNER, goal, allow_settled=True) is None


@pytest.mark.asyncio
async def test_weather_read_alone_cannot_complete_useful_outcome(monkeypatch):
    from agent import reasoning
    db, service, _, goal, run, plan, _, _ = await setup(monkeypatch)
    monkeypatch.setattr(reasoning, "verify_goal", AsyncMock(return_value={
        "outcome": "achieved", "reasoning": "Il controllo meteo è stato eseguito.",
    }))
    result = await service._finish(OWNER, goal, plan, run, AgentBudget(), language="it")
    assert result["state"] == "in_progress"
    current = await service.repo.get_goal(OWNER, goal.id)
    assert current.is_open
    assert await db.agent_journal.find_one({"goal_id": goal.id,
        "detail.reason": "situation_action_assessment_required"})


@pytest.mark.asyncio
async def test_fresh_estimated_action_completes_watch_and_binds_final_need(monkeypatch):
    from agent import reasoning
    db, service, state, goal, run, plan, baseline, live = await setup(monkeypatch)
    raw = action(baseline, live)
    monkeypatch.setattr(reasoning, "verify_goal", AsyncMock(return_value={
        "outcome": "achieved", "reasoning": "È disponibile una valutazione utile aggiornata.",
        "situation_outcome": raw,
    }))
    result = await service._finish(OWNER, goal, plan, run, AgentBudget(), language="it")
    assert result["state"] == "completed"
    current = await service.repo.get_goal(OWNER, goal.id)
    physical = await SituationRepository(db).get(OWNER, state.id)
    assert physical.status == "changed" and physical.resolved_at is None
    assert physical.attention_intent is None
    outcome = await current_outcome(db, OWNER, current, allow_settled=True)
    assert outcome and outcome["status"] == "action_now"
    assert outcome["assessment_revision"] + 1 == physical.revision
    assert outcome["situation_revision"] == physical.revision
    monkeypatch.setattr(service.needs, "offer_to_delivery", AsyncMock())
    decision = VisibilityDecision(goal_id=goal.id, outcome="inform_user", headline="Risultato utile.", refs=[])
    need = await service._raise_need(OWNER, current, decision, {"what_ora_did_this_time": []})
    assert need.kind == "important_outcome"
    assert need.summary == outcome["headline"]
    assert need.source_refs == outcome_refs(outcome)
    assert need.valid_until == outcome["valid_until"]
    same = await service._raise_need(OWNER, current, decision, {"what_ora_did_this_time": []})
    assert same.id == need.id
    # A later user change is never the code-authored settlement exception.
    await SituationService(db).apply(user_id=OWNER, session_id="fixture", reasoning_epoch="collected",
        update=SituationUpdate(operation="resolve", situation_id=state.id, expected_revision=physical.revision))
    assert await current_outcome(db, OWNER, current, allow_settled=True) is None


@pytest.mark.asyncio
async def test_timer_without_fresh_read_cannot_announce_readiness(monkeypatch):
    db, _, _, goal, run, _, baseline, live = await setup(monkeypatch)
    # The last reading belongs to a check well before this timer pass. (A
    # reading from the same checkpoint, a minute or two earlier, is fresh:
    # see test_situation_ready_at_checkpoint_v1.)
    run.at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    assert await validate_assessment(db, OWNER, goal, action(baseline, live),
                                     evidence=[baseline, live], run_at=run.at) is None


@pytest.mark.asyncio
async def test_repeated_reads_keep_latest_conditions_and_empirical_baseline(monkeypatch):
    db, _, _, goal, _, _, baseline, _ = await setup(monkeypatch)
    store = EvidenceStore(db)
    now = datetime.now(timezone.utc)
    for n in range(55):
        await store.record(AgentEvidence(
            id=f"evd_recheck_{n}", owner_id=OWNER, goal_id=goal.id,
            observed_at=(now + timedelta(seconds=n)).isoformat(), claim=f"Condizioni sintetiche {n}",
            provenance=ResultProvenance(source_class="external_research", capability="weather.read", freshness="fresh"),
        ))
    evidence = await store.for_goal(OWNER, goal.id)
    assert len(evidence) == 40
    assert baseline.id in {item.id for item in evidence}, [(item.id, item.provenance.capability) for item in evidence[:2]]
    payload = for_verification(evidence)
    assert len(payload) == 12
    assert payload[-1]["evidence_id"] == "evd_recheck_54"
    assert baseline.id in {row["evidence_id"] for row in payload}
    assert "evd_recheck_0" not in {row["evidence_id"] for row in payload}


@pytest.mark.asyncio
async def test_explicit_unknown_start_clears_fact_and_invalidates_previous_estimate(monkeypatch):
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    original = state.started_at
    assert await service._record_situation_outcome(OWNER, goal, estimate(baseline, live), run)
    await SituationService(db).apply(user_id=OWNER, session_id="fixture", reasoning_epoch="start-unknown",
        update=SituationUpdate(operation="update", situation_id=state.id, expected_revision=1,
                               started_at="", facts=["L'ora di inizio non è nota."]))
    changed = await SituationRepository(db).get(OWNER, state.id)
    assert original is not None and changed.started_at is None
    assert changed.history[-1].changes["started_at"] == ""
    assert await current_outcome(db, OWNER, goal) is None
    assert await refresh(service, goal)
    assert (await service.repo.get_goal(OWNER, goal.id)).situation_outcome is None
    # Missing values do not reset an established physical start at restart.
    assert SituationUpdate(operation="update", started_at=None).started_at is None
    assert SituationState(id="empty", user_id=OWNER, summary="Fixture", started_at="").started_at is None


@pytest.mark.asyncio
async def test_new_city_cannot_reuse_fresh_weather_from_the_previous_revision(monkeypatch):
    db, service, state, goal, _, _, baseline, live = await setup(monkeypatch)
    await SituationService(db).apply(user_id=OWNER, session_id="fixture", reasoning_epoch="new-city",
        update=SituationUpdate(operation="update", situation_id=state.id, expected_revision=1,
                               location_label="Seconda località sintetica"))
    assert await refresh(service, goal)
    # A new research result must not make the old location's still-fresh
    # weather eligible again, even when both are from this goal and pass.
    run = AgentRun(owner_id=OWNER, goal_id=goal.id)
    baseline.observed_at = live.observed_at = datetime.now(timezone.utc).isoformat()
    result = await validate_assessment(db, OWNER, goal, estimate(baseline, live),
                                      evidence=[baseline, live], run_at=run.at)
    assert result is None


@pytest.mark.asyncio
async def test_moving_same_saved_place_invalidates_its_weather_snapshot(monkeypatch):
    from places.models import Coordinates
    from places.service import PlacesService

    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    place = await PlacesService(db).save_place(OWNER, label="Luogo della prova", role="other",
        locality="Località sintetica", coordinates=Coordinates(latitude=42, longitude=12))
    await db.situations.update_one({"id": state.id}, {"$set": {"linked_object_refs": [f"place:{place.id}"]}})
    live.provenance.source_refs = [f"place:{place.id}", f"place_snapshot:{place.id}:{place.updated_at}",
                                  f"situation:{state.id}:revision:1"]
    await db.agent_evidence.replace_one({"id": live.id}, live.model_dump())
    assert await service._record_situation_outcome(OWNER, goal, estimate(baseline, live), run)
    place.coordinates = Coordinates(latitude=43, longitude=13)
    place.updated_at = datetime.now(timezone.utc).isoformat()
    await PlacesService(db).repo.save_place(place)
    assert await current_outcome(db, OWNER, goal) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["unknown", "recent", "missing_expiry", "expired", "wrong_revision"])
async def test_noncurrent_weather_cannot_promote_initial_review_to_confirmed_check(monkeypatch, condition):
    db, service, _, goal, run, plan, baseline, live = await setup(monkeypatch)
    await db.agent_evidence.update_one({"id": baseline.id}, {"$set": {"superseded": True}})
    if condition in ("unknown", "recent"):
        live.provenance.freshness = condition
    elif condition == "missing_expiry":
        live.provenance.weather_valid_until = None
    elif condition == "expired":
        live.provenance.weather_valid_until = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    else:
        live.provenance.source_refs[-1] = live.provenance.source_refs[-1].replace("revision:1", "revision:2")
    await db.agent_evidence.replace_one({"id": live.id}, live.model_dump())
    expected_age = {"missing_expiry": "unknown", "expired": "stale", "wrong_revision": "fresh"}.get(condition, condition)
    assert for_verification([live])[0]["how_old"] == expected_age
    await service._wait(OWNER, goal, plan, None, run, minutes=20,
                        note="Valutare condizioni nuove al prossimo controllo.", model_decision=True)
    assert (await service.repo.get_goal(OWNER, goal.id)).source_kind == "situation_initial_review"
    assert (await read_followup(db, OWNER, goal.source_situation["situation_id"]))["status"] == "review_pending"


@pytest.mark.asyncio
async def test_old_visibility_judgement_cannot_raise_need_for_newer_assessment(monkeypatch):
    db, service, _, goal, run, _, baseline, live = await setup(monkeypatch)
    assert await service._record_situation_outcome(OWNER, goal, estimate(baseline, live), run)
    first = await current_outcome(db, OWNER, goal)
    decision = VisibilityDecision(goal_id=goal.id, outcome="inform_user", headline=first["headline"], refs=outcome_refs(first))
    assert await service._record_situation_outcome(OWNER, goal, action(baseline, live), run)
    assert await service._raise_need(OWNER, goal, decision, {}) is None
    assert await service.needs.open_for_goal(OWNER, goal.id) == []


@pytest.mark.asyncio
async def test_malformed_optional_result_does_not_hide_missing_checkpoint_recovery(monkeypatch):
    from ambient.eligibility import EligibilityService

    db, _, state, goal, _, _, _, _ = await setup(monkeypatch)
    await db.agent_goals.update_one({"id": goal.id}, {"$set": {
        "source_kind": "situation_followup", "next_run_at": None,
        "situation_outcome": {"status": "estimated", "window_start": "malformed"}}})
    result = await read_followup(db, OWNER, state.id)
    assert result["status"] == "not_scheduled"
    assert result["outcome"] is None
    assert result["next_check_at"] is None
    assert await EligibilityService(db)._has_unattended_situation(OWNER)
    assert await db.ambient_wakes.count_documents({}) == 0


async def admitted_situation(monkeypatch):
    """The real creation bridge, goal admission and durable initial wake."""
    from places.models import Coordinates
    from places.service import PlacesService
    from situations.followup import goal_id_for

    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    monkeypatch.setenv("ORA_ORCHESTRATION_ENABLED", "0")
    db = AsyncMongoMockClient().outcome_vertical_v160
    service = AgentService(db)
    await service.ensure_indexes()
    await db.ambient_wakes.create_index("identity", unique=True,
        partialFilterExpression={"status": {"$in": ["pending", "claimed"]}})
    place = await PlacesService(db).save_place(OWNER, label="Luogo della prova", role="other",
        locality="Località sintetica", coordinates=Coordinates(latitude=42, longitude=12))
    started = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    created = await SituationService(db).apply(user_id=OWNER, session_id="fixture-vertical",
        reasoning_epoch="vertical-create", update=SituationUpdate(operation="create",
            summary="Materiale all'aperto in un'attività temporanea.",
            desired_outcome="Sapere quando ritirare il materiale.",
            attention_intent="Valutare il momento utile e i rischi esterni.",
            started_at=started, facts=["Il materiale è ancora all'aperto."],
            location_label=place.locality, linked_object_refs=[f"place:{place.id}"]))
    state = await SituationRepository(db).get(OWNER, created["situation"]["id"])
    goal = await service.repo.get_goal(OWNER, goal_id_for(OWNER, state.id))
    assert goal and goal.source_kind == "situation_initial_review"
    wake = await db.ambient_wakes.find_one({"owner_id": OWNER, "source_ref": f"goal:{goal.id}", "status": "pending"})
    assert wake and wake["reason"] == "opportunity_revisit"
    return db, service, state, goal, place


@pytest.mark.asyncio
@pytest.mark.parametrize("choice", ["resolved", "stop_alerts"])
async def test_initial_review_controls_reach_the_owned_persisted_situation(monkeypatch, choice):
    import deps
    from agent.router import SituationAlertsIn, situation_alerts

    db, service, state, goal, _ = await admitted_situation(monkeypatch)
    monkeypatch.setattr(deps, "db", db)
    result = await situation_alerts(goal.id, SituationAlertsIn(decision=choice, expected_revision=1),
                                    user={"user_id": OWNER})
    assert result["monitor_stopped"] is True
    assert (await service.repo.get_goal(OWNER, goal.id)).status == "cancelled"
    assert (await SituationRepository(db).get(OWNER, state.id)).status == ("resolved" if choice == "resolved" else "changed")
    assert await db.ambient_wakes.count_documents({"source_ref": f"goal:{goal.id}",
                                                   "status": {"$in": ["pending", "claimed"]}}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("action_reason", ["outcome_ready", "early_risk"])
async def test_real_worker_admission_estimate_recheck_and_useful_action(monkeypatch, action_reason):
    """Only model answers and external forecast/research are synthetic.

    Both wakes use the production dispatch/worker/executor. The test expedites
    the due clock, then supplies a new weather read and model assessment of
    either estimated readiness or a protective action. It proves the wiring;
    the synthetic model judgement is not evidence of physical readiness.
    """
    from agent import reasoning
    from ambient.models import AmbientWake
    from ambient.runtime import _handle
    from delivery import reasoning as delivery_reasoning
    from research.models import (EvidenceClaim, EvidenceSource, ResearchAssessment,
                                 ResearchRun, ResearchSynthesis)
    from research.service import ResearchService
    import weather

    db, service, state, goal, place = await admitted_situation(monkeypatch)
    phase = {"risk": False}

    async def model_plan(payload, *, context, **kwargs):
        assert context["source_context"][0]["started_at"] == state.started_at
        assert payload["desired_outcome"] == state.desired_outcome
        return {"plan_summary": "Stima fondata e rilettura utile.", "steps": [
            {"intent": "Leggere le condizioni del luogo", "step_type": "inspect", "capability_needed": "weather.read"},
            {"intent": "Stabilire una base empirica pertinente", "step_type": "research", "capability_needed": "web.research",
             "expected_result": "Quali osservazioni pubbliche permettono una stima prudente della durata?"},
            {"intent": "Rileggere le condizioni prima dell'azione", "step_type": "verify", "capability_needed": "weather.read"},
        ]}

    async def forecast(**kwargs):
        assert kwargs == {"lat": 42.0, "lon": 12.0, "place": place.locality}
        now = datetime.now(timezone.utc)
        return {"available": True, "place": place.locality, "provider": "synthetic-fixture",
                "timezone": "UTC", "observed_at": now.isoformat(), "condition_label": "Fixture",
                "temperature_c": 22, "humidity_pct": 45, "wind_kmh": 14, "precipitation_mm": 0,
                "hours": [{"time": (now + timedelta(hours=n)).isoformat(), "temperature_c": 22,
                           "rain_chance_pct": 95 if phase["risk"] and action_reason == "early_risk" else 0,
                           "precipitation_mm": 2 if phase["risk"] and action_reason == "early_risk" else 0}
                          for n in (1, 2, 3, 4)], "days": []}

    async def research(owner, need, **kwargs):
        assert owner == OWNER and state.started_at in str(need.already_known)
        now = datetime.now(timezone.utc)
        source = EvidenceSource(url="https://example.org/synthetic-baseline", title="Fonte della fixture")
        return ResearchRun(user_id=owner, need=need, status="completed", sources=[source],
            assessments=[ResearchAssessment(sufficiency="sufficient")],
            synthesis=ResearchSynthesis(claims=[EvidenceClaim(
                statement="Base empirica sintetica: per queste condizioni è plausibile una finestra ampia, da verificare.",
                supported_by=[source.source_id])]), completed_at=now.isoformat(),
            valid_until=(now + timedelta(hours=8)).isoformat())

    def records(rows):
        baseline = next((SimpleNamespace(id=row["evidence_id"]) for row in rows if row["capability"] == "web.research"), None)
        # Since 24/10/2026 the person's own statement is evidence from the
        # first pass, so the model may be asked before any weather exists.
        live = ([SimpleNamespace(id=row["evidence_id"]) for row in rows if row["capability"] == "weather.read"] or [None])[-1]
        return baseline, live

    async def next_action(payload, *, evidence, candidates, **kwargs):
        assert payload["source_context"][0]["started_at"] == state.started_at
        baseline, live = records(evidence)
        if baseline is None or live is None or phase["risk"]:
            return {"decision": "execute", "step_id": candidates[0]["id"], "reasoning": "Servono le fonti pertinenti."}
        return {"decision": "wait", "reasoning": "Riesaminare le condizioni prima della finestra utile.",
                "wait_minutes": 180, "situation_outcome": estimate(baseline, live)}

    async def verify(payload, *, evidence, **kwargs):
        assert phase["risk"] and payload["source_context"][0]["started_at"] == state.started_at
        baseline, live = records(evidence["what_was_found"])
        raw = action(baseline, live)
        if action_reason == "early_risk":
            raw.update(action_reason="early_risk", evidence_ids=[live.id],
                       headline="Ritira il materiale ora: è previsto un rischio imminente.",
                       action_summary="Metti il materiale al riparo; questo non significa che sia pronto.")
        return {"outcome": "achieved", "reasoning": "È disponibile l'indicazione utile aggiornata.", "situation_outcome": raw}

    async def visibility(*args, **kwargs):
        return {"outcome": "requires_attention" if phase["risk"] else "quiet_update",
                "headline": "Il modello di visibilità non deve sostituire il risultato verificato.",
                "about": "azione utile" if phase["risk"] else "prima stima", "reasoning": "La valutazione è cambiata."}

    forecast_call, research_call = AsyncMock(side_effect=forecast), AsyncMock(side_effect=research)
    monkeypatch.setattr(weather, "capabilities", lambda: {"available": True})
    monkeypatch.setattr(weather, "forecast_at", forecast_call)
    monkeypatch.setattr(ResearchService, "run", research_call)
    monkeypatch.setattr(reasoning, "make_plan", model_plan)
    monkeypatch.setattr(reasoning, "choose_next_action", next_action)
    monkeypatch.setattr(reasoning, "verify_goal", verify)
    monkeypatch.setattr(reasoning, "decide_visibility", visibility)
    monkeypatch.setattr(delivery_reasoning, "decide_delivery", AsyncMock(return_value={
        "mode": "in_app", "timing": "now", "reason_to_interrupt": "Indicazione utile ora.",
        "reason_to_open": "Il risultato aggiornato è già nella scheda.", "what_decided_the_mode": "Prova locale in app.",
        "confidence": "strong", "sensitivity": "ordinary", "requires_recheck": True}))

    async def fire_due():
        wake = await db.ambient_wakes.find_one({"owner_id": OWNER, "source_ref": f"goal:{goal.id}", "status": "pending"}, {"_id": 0})
        assert wake
        due = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        await db.agent_goals.update_one({"id": goal.id}, {"$set": {"next_run_at": due}})
        await db.ambient_wakes.update_one({"id": wake["id"]}, {"$set": {"status": "claimed", "scheduled_for": due}})
        wake.update(status="claimed", scheduled_for=due)
        return await _handle(db, AmbientWake.model_validate(wake))

    first = await fire_due()
    assert first.result == "waiting"
    tracking = await read_followup(db, OWNER, state.id)
    assert tracking["status"] == "scheduled"
    estimate_result = tracking["outcome"]
    assert estimate_result and estimate_result["status"] == "estimated"
    assert tracking["next_check_at"] < estimate_result["valid_until"]
    assert tracking["next_check_at"] != estimate_result["window_start"]
    assert (await service.repo.get_goal(OWNER, goal.id)).source_kind == "situation_followup"
    assert await service.needs.open_for_goal(OWNER, goal.id) == []

    phase["risk"] = True
    second = await fire_due()
    assert second.result == "completed"
    assert forecast_call.await_count == 2 and research_call.await_count == 1
    completed = await service.repo.get_goal(OWNER, goal.id)
    current = await current_outcome(db, OWNER, completed, allow_settled=True)
    assert current and current["action_reason"] == action_reason
    assert current["window_start"] is None and current["id"] != estimate_result["id"]
    physical = await SituationRepository(db).get(OWNER, state.id)
    assert physical.status == "changed" and physical.resolved_at is None
    assert physical.started_at == state.started_at
    needs = await service.needs.open_for_goal(OWNER, goal.id)
    assert len(needs) == 1 and needs[0].kind == "important_outcome"
    assert needs[0].source_refs == outcome_refs(current)
    assert needs[0].summary == current["headline"]
    detail = await AgentService(db).for_detail(OWNER, goal.id)
    assert detail["situation"]["outcome"]["id"] == current["id"]
    assert detail["needs_you"] == ""
    home = await AgentService(db).for_home(OWNER)
    assert home[0]["situation"]["outcome"]["id"] == current["id"]
    await db.agent_goals.update_one({"id": goal.id}, {"$set": {
        "situation_outcome.valid_until": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()}})
    assert await AgentService(db).for_detail(OWNER, goal.id) is None
    assert await AgentService(db).for_home(OWNER) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["choose", "verify"])
async def test_large_model_payload_keeps_valid_json_current_weather_baseline_and_physical_clock(monkeypatch, boundary):
    from agent import reasoning

    _, service, state, goal, _, _, baseline, live = await setup(monkeypatch)
    now = datetime.now(timezone.utc)
    rows = [baseline.for_ai()]
    rows[0]["what_was_found"] = "Base empirica sintetica con qualifiche da conservare. " * 10
    for n in range(11):
        item = live.for_ai()
        item.update(evidence_id=f"evd_long_weather_{n}", what_was_found=(f"Condizione sintetica {n}. " * 24)[:600],
                    observed_at=(now - timedelta(minutes=20 - n) if n < 8 else now).isoformat())
        rows.append(item)
    plan = ActionPlan(owner_id=OWNER, goal_id=goal.id, status="active", steps=[
        ActionStep(ordinal=n, intent=("Controllo sintetico qualificato " * 8)[:240], step_type="inspect",
                   capability_needed="weather.read", expected_result=("Risultato con limiti della fonte " * 9)[:290],
                   status="succeeded" if n < 6 else "pending") for n in range(8)])
    payload_goal = await service._reasoning_goal(OWNER, goal)
    clock = {"now": now.isoformat(), "timezone": "Europe/Rome", "local_date": now.date().isoformat()}
    captured = {}

    async def model(_instruction, payload):
        captured["text"] = payload
        captured["json"] = json.loads(payload)
        return {"decision": "wait"} if boundary == "choose" else {"outcome": "uncertain"}

    monkeypatch.setattr(reasoning, "_ask_model", model)
    # Keep exercising compaction under pressure: the production Situation
    # bound is now larger, so force the former 9000 limit for this payload.
    monkeypatch.setattr(reasoning, "_SITUATION_CONTEXT_CHARS", 9000)
    if boundary == "choose":
        await reasoning.choose_next_action(payload_goal, plan=plan.for_ai(), evidence=rows,
            candidates=[step.for_ai() for step in plan.steps[-2:]],
            capabilities=[{"capability": f"fixture_{n}.read", "status": "unavailable", "can_be_used_now": False,
                           "why_not": "Non disponibile nella prova sintetica."} for n in range(22)], clock_context=clock)
    else:
        await reasoning.verify_goal(payload_goal, evidence={"what_was_found": rows,
                                                            "steps": [step.for_ai() for step in plan.steps], "local_clock": clock})
    result = captured["json"]
    assert len(captured["text"]) <= 9000
    assert result["context_truncated"] is True
    assert result["goal"]["source_context"][0]["started_at"] == state.started_at
    facts = result["what_has_been_found"] if boundary == "choose" else result["what_was_done"]["what_was_found"]
    assert {baseline.id, "evd_long_weather_8", "evd_long_weather_9", "evd_long_weather_10"}.issubset(
        {row["evidence_id"] for row in facts})
    for row in facts:
        original = next(value for value in rows if value["evidence_id"] == row["evidence_id"])
        for field in ("source_refs", "observed_at", "weather_valid_until", "research_valid_until"):
            assert row[field] == original[field]
    assert (result["local_clock"] if boundary == "choose" else result["what_was_done"]["local_clock"]) == clock
