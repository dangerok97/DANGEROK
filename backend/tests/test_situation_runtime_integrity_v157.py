"""Persisted runtime boundaries with synthetic sources; no provider/account calls."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import ActionPlan, ActionStep, AgentEvidence, AgentRun, ResultProvenance
from agent.service import AgentService, _wait_parameters
from agent.source_refresh import changed, refresh
from opportunities.discovery import OpportunityDiscovery
from situations.followup import INITIAL_KIND, goal_id_for, read_followup
from situations.models import SituationUpdate
from situations.service import SituationService

OWNER = "runtime-integrity-fixture"


async def setup(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    monkeypatch.setattr(OpportunityDiscovery, "note", AsyncMock(return_value={"outcome": "accepted"}))
    db = AsyncMongoMockClient().runtime_integrity
    await db.agent_goals.create_index("id", unique=True)
    await db.agent_runs.create_index("goal_id", unique=True)
    await db.ambient_wakes.create_index(
        "identity", unique=True,
        partialFilterExpression={"status": {"$in": ["pending", "claimed"]}},
    )
    result = await SituationService(db).apply(
        user_id=OWNER, session_id="fixture-session", reasoning_epoch="fixture-created",
        update=SituationUpdate(operation="create", summary="Una condizione temporanea da rivalutare",
                               attention_intent="Controllare la fonte al prossimo momento utile",
                               next_check_summary="Conoscere la condizione aggiornata", source="user_conversation"),
    )
    sid = result["situation"]["id"]
    service = AgentService(db)
    monkeypatch.setattr(service, "_note_ambient", AsyncMock())
    goal = await service.repo.get_goal(OWNER, goal_id_for(OWNER, sid))
    return db, service, goal, sid


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [{}, {"wait_minutes": "bad"}, {"wait_minutes": True},
                                  {"wait_minutes": -1}, {"wait_minutes": float("nan")},
                                  {"wait_until": "2020-01-01T12:00:00Z"}])
async def test_unspecified_or_invalid_wait_is_only_a_review_retry(monkeypatch, raw):
    db, service, goal, sid = await setup(monkeypatch)
    await service.evidence.record(AgentEvidence(
        owner_id=OWNER, goal_id=goal.id, claim="Una lettura sintetica valida esiste.",
        provenance=ResultProvenance(source_class="connected_provider", source_refs=["weather:fixture"], freshness="fresh"),
    ))
    timing = _wait_parameters(raw)
    plan = ActionPlan(owner_id=OWNER, goal_id=goal.id, status="active")
    await service._wait(OWNER, goal, plan, None, AgentRun(owner_id=OWNER, goal_id=goal.id),
                        minutes=timing.get("wait_minutes"), hours=timing.get("wait_hours"),
                        wait_until=timing.get("wait_until"), note="Rivalutare la fonte", model_decision=True)
    assert (await service.repo.get_goal(OWNER, goal.id)).source_kind == INITIAL_KIND
    state = await read_followup(db, OWNER, sid)
    assert state["status"] == "review_pending"
    assert state["next_check_at"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["none", "simulated", "other_owner", "self_reference", "stale", "technical_retry"])
async def test_review_requires_own_current_source_and_model_time(monkeypatch, case):
    db, service, goal, sid = await setup(monkeypatch)
    if case != "none":
        await service.evidence.record(AgentEvidence(
            owner_id="another-owner" if case == "other_owner" else OWNER,
            goal_id=goal.id, claim="Risultato interamente sintetico per il test.",
            provenance=ResultProvenance(
                source_class="simulated" if case == "simulated" else "connected_provider",
                source_refs=[f"situation:{sid}"] if case == "self_reference" else ["weather:fixture"],
                freshness="stale" if case == "stale" else "fresh",
            ),
        ))
    plan = ActionPlan(owner_id=OWNER, goal_id=goal.id, status="active")
    await service._wait(OWNER, goal, plan, None, AgentRun(owner_id=OWNER, goal_id=goal.id),
                        minutes=20, note="Ricontrollare una fonte", model_decision=case != "technical_retry")
    assert (await service.repo.get_goal(OWNER, goal.id)).source_kind == INITIAL_KIND
    assert (await read_followup(db, OWNER, sid))["next_check_at"] is None


@pytest.mark.asyncio
async def test_revoked_source_stops_runner_even_when_original_cancellation_failed(monkeypatch):
    db, service, goal, sid = await setup(monkeypatch)
    build = AsyncMock()
    monkeypatch.setattr(service, "_build_plan", build)
    await db.situations.update_one({"id": sid, "user_id": OWNER}, {
        "$set": {"attention_intent": None, "next_check_summary": None, "revision": 2},
    })
    assert await changed(db, goal)
    result = await service.advance(OWNER, goal.id, worker_id="ambient:synthetic-worker")
    assert result["state"] == "cancelled"
    build.assert_not_awaited()
    assert (await service.repo.get_goal(OWNER, goal.id)).next_run_at is None
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "source_ref": f"goal:{goal.id}", "status": {"$in": ["pending", "claimed"]},
    }) == 0


@pytest.mark.asyncio
async def test_revision_change_invalidates_stale_plan_and_keeps_one_new_review(monkeypatch):
    db, service, goal, sid = await setup(monkeypatch)
    await refresh(service, goal)
    old_plan = ActionPlan(owner_id=OWNER, goal_id=goal.id, status="active", steps=[
        ActionStep(ordinal=0, step_type="wait", intent="Vecchio controllo", parameters={"wait_minutes": 20}),
    ])
    await service.repo.save_plan(old_plan)
    evidence = AgentEvidence(owner_id=OWNER, goal_id=goal.id, claim="Vecchia condizione sintetica.",
                             provenance=ResultProvenance(source_class="connected_provider", source_refs=["weather:old"]))
    await service.evidence.record(evidence)
    await db.situations.update_one({"id": sid, "user_id": OWNER}, {
        "$set": {"revision": 2, "summary": "Condizione temporanea corretta"},
    })
    assert await changed(db, goal)
    assert await refresh(service, goal)
    assert goal.is_open and goal.source_kind == INITIAL_KIND
    assert goal.source_situation["situation_revision"] == "2"
    assert await service.repo.plan_for(OWNER, goal.id) is None
    assert await service.evidence.for_goal(OWNER, goal.id) == []
    assert await db.agent_goals.count_documents({"owner_id": OWNER}) == 1
    assert (await read_followup(db, OWNER, sid))["status"] == "review_pending"


@pytest.mark.asyncio
async def test_failed_cancellation_readback_never_reports_stopped(monkeypatch):
    db, service, goal, sid = await setup(monkeypatch)
    from situations import followup
    from conversation_engine.models import ConversationSession
    from conversation_engine.ai_core.loop import run_cognitive_loop
    # The update succeeds but its best-effort cancellation leaves durable
    # work behind, reproducing a database/runtime partial failure.
    monkeypatch.setattr(followup, "cancel_dedicated_followup", AsyncMock(return_value=None))
    session = ConversationSession(user_id=OWNER, meta={"ui_mode": "ai_core", "ai_core": {}})
    decide = AsyncMock(return_value={
        "response_mode": "answer", "message_to_user": "Ho fermato i controlli.",
        "situation_followup": {"disposition": "declined", "situation_id": sid,
                               "reason": "La persona revoca il monitoraggio",
                               "user_words": "Non avviare controlli"},
    })
    result = await run_cognitive_loop(sess=session, user_message="Non avviare controlli su questa situazione.",
                                      db=db, decision_fn=decide)
    assert "non sono riuscita a confermare l'annullamento" in result.ora_text
    assert result.ora_text != "Ho fermato i controlli."
    assert (await service.repo.get_goal(OWNER, goal.id)).is_open


@pytest.mark.asyncio
async def test_explicit_decline_cancels_an_already_scheduled_watch(monkeypatch):
    db, service, goal, sid = await setup(monkeypatch)
    from situations.followup import arrange_followup, attention_withdrawal_confirmed
    from conversation_engine.models import ConversationSession
    from conversation_engine.ai_core.loop import run_cognitive_loop
    await arrange_followup(db, OWNER, situation_id=sid, expected_revision=1,
                           check_at=(datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat(),
                           purpose="Ricontrollare condizioni", notify_when="Serve intervenire")
    assert (await read_followup(db, OWNER, sid))["status"] == "scheduled"
    session = ConversationSession(user_id=OWNER, meta={"ui_mode": "ai_core", "ai_core": {}})
    decide = AsyncMock(return_value={
        "response_mode": "answer", "message_to_user": "Il monitoraggio è stato fermato.",
        "situation_followup": {"disposition": "declined", "situation_id": sid,
                               "reason": "Revoca esplicita del controllo già programmato",
                               "user_words": "Non fare altri controlli"},
    })
    result = await run_cognitive_loop(sess=session, user_message="Non fare altri controlli su questa situazione.",
                                      db=db, decision_fn=decide)
    assert result.ok
    assert await attention_withdrawal_confirmed(db, OWNER, sid)


@pytest.mark.asyncio
async def test_plain_checkpoint_ignores_older_withdrawal_and_preserves_outcome_on_edit(monkeypatch):
    db, service, initial, sid = await setup(monkeypatch)
    from situations.followup import arrange_followup
    # A prior cycle ended. An explicit checkpoint is then arranged against
    # this newer revision without restoring the old attention fields.
    await db.situations.update_one({"id": sid, "user_id": OWNER}, {
        "$set": {"attention_intent": None, "next_check_summary": None, "revision": 2},
        "$push": {"history": {"revision": 2, "operation": "update", "source": "user_conversation",
                              "at": datetime.now(timezone.utc).isoformat(),
                              "changes": {"attention_intent": None, "next_check_summary": None}}},
    })
    # Reuse an open initial review as the explicit scheduling entry point.
    result = await arrange_followup(
        db, OWNER, situation_id=sid, expected_revision=2,
        check_at=(datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat(),
        purpose="Rileggere la condizione aggiornata", notify_when="Serve intervenire",
        completion_when="Comunicare il prossimo momento utile",
    )
    assert result["ok"]
    goal = await service.repo.get_goal(OWNER, initial.id)
    assert goal.source_situation["attention_expected"] == "false"
    assert not await changed(db, goal)
    await db.situations.update_one({"id": sid, "user_id": OWNER}, {
        "$set": {"revision": 3, "summary": "Descrizione corretta senza nuova revoca"},
    })
    assert await refresh(service, goal)
    saved = await service.repo.get_goal(OWNER, goal.id)
    assert saved.is_open
    assert saved.desired_outcome == "Comunicare il prossimo momento utile"
    assert saved.source_situation["situation_revision"] == "3"
    assert (await read_followup(db, OWNER, sid))["status"] == "review_pending"


@pytest.mark.asyncio
async def test_old_completion_cannot_clear_newer_attention(monkeypatch):
    db, service, goal, sid = await setup(monkeypatch)
    from situations.followup import settle_completed_followup
    await db.situations.update_one({"id": sid, "user_id": OWNER}, {
        "$set": {"revision": 2, "attention_intent": "Una nuova attenzione richiesta mentre il worker conclude"},
    })
    assert not await settle_completed_followup(db, OWNER, goal)
    row = await db.situations.find_one({"id": sid, "user_id": OWNER})
    assert row["attention_intent"] == "Una nuova attenzione richiesta mentre il worker conclude"
    assert row["revision"] == 2


@pytest.mark.asyncio
async def test_two_attention_cycles_on_same_goal_both_settle(monkeypatch):
    db, service, goal, sid = await setup(monkeypatch)
    from situations.followup import settle_completed_followup
    goal.status = "completed"
    await service.repo.save_goal(goal)
    assert await settle_completed_followup(db, OWNER, goal)
    reopened = await SituationService(db).apply(
        user_id=OWNER, session_id="fixture-session", reasoning_epoch="fixture-new-cycle",
        update=SituationUpdate(
            operation="update", situation_id=sid, expected_revision=2,
            attention_intent="Ricontrollare dopo una nuova richiesta esplicita", source="user_conversation",
        ),
    )
    assert reopened["status"] == "success"
    fresh = await service.repo.get_goal(OWNER, goal.id)
    assert fresh.is_open
    assert fresh.source_situation["attention_epoch"] != goal.source_situation["attention_epoch"]
    fresh.status = "completed"
    await service.repo.save_goal(fresh)
    assert await settle_completed_followup(db, OWNER, fresh)
    row = await db.situations.find_one({"id": sid, "user_id": OWNER})
    assert row["revision"] == 4
    assert row["attention_intent"] is None
    assert row["next_check_summary"] is None


@pytest.mark.asyncio
async def test_direct_goal_cancellation_during_source_refresh_cleans_new_wake(monkeypatch):
    db, service, goal, sid = await setup(monkeypatch)
    from ambient.service import AmbientService
    original_schedule = AmbientService.schedule

    async def cancel_during_schedule(self, owner_id, **kwargs):
        await db.agent_goals.update_one({"owner_id": OWNER, "id": goal.id}, {
            "$set": {"status": "cancelled", "next_run_at": None},
        })
        return await original_schedule(self, owner_id, **kwargs)

    monkeypatch.setattr(AmbientService, "schedule", cancel_during_schedule)
    await db.situations.update_one({"id": sid, "user_id": OWNER}, {"$set": {"revision": 2}})
    assert await refresh(service, goal)
    assert goal.status == "cancelled"
    assert (await service.repo.get_goal(OWNER, goal.id)).status == "cancelled"
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "source_ref": f"goal:{goal.id}", "status": {"$in": ["pending", "claimed"]},
    }) == 0
